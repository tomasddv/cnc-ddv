"""DDV | Gestión CNC 2.1.2.5. Optimizado para Streamlit Community Cloud."""
from __future__ import annotations
from datetime import date,datetime
import hashlib
from pathlib import Path
import io
import os
import pandas as pd
import streamlit as st
from store import Store, preparar_csv
from relevamientos_monitor import resumen_relevamientos, validar_sincronizacion
from force import cargar_respuestas, cruzar_mes
from motivos_relevamiento import MOTIVOS_PROMOTOR, filtrar_motivo_promotor
from logica import (NEGOCIOS,UNIDADES_POR_DEFECTO,cargar_clientes,cargar_ventas,fecha_fin,
                    generar_casos,meses_ventana, control_contactos_u12m, cartera_vigencia_3m,
                    tiene_promotor_asignado, tiene_licencia_alcohol, preparar_ventas, resumen_cnc_por_promotor)

st.set_page_config(page_title='DDV | Gestión CNC',page_icon='📋',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
.stApp{background:#fff;color:#151515} .stMarkdown,p,h1,h2,h3,span,label{color:#151515!important}
[data-testid="stMetricValue"]{color:#151515!important} .block-container{padding-top:1.3rem}
[data-testid="stSidebar"]{background:#f7f8fc} [data-testid="stHeader"]{background:#fff}
</style>''',unsafe_allow_html=True)
ROOT=Path(__file__).parent
LOCAL_MODE=os.environ.get('CNC_LOCAL','0')=='1'
DB_LOCAL=str(ROOT/'data'/'cnc_local.sqlite')


def secrets_opt(name,default=None):
    try:return st.secrets.get(name,default)
    except Exception:return default


def info_google():
    info=secrets_opt('gcp_service_account')
    return dict(info) if info else None

@st.cache_data(ttl=1800,show_spinner='Leyendo datos de Google Drive...')
def datos_de_drive(file_id,info):
    from drive_util import credenciales,descargar_bytes
    return descargar_bytes(credenciales(info),file_id).getvalue()

@st.cache_data(ttl=3600,show_spinner=False)
def leer_datos(tipo,archivo,drive_id,info):
    if drive_id and info:
        contenido=datos_de_drive(drive_id,info)
        return pd.read_csv(io.BytesIO(contenido),compression='gzip',keep_default_na=False,dtype={'cliente':'string','mes':'string'})
    if Path(archivo).exists():
        return pd.read_csv(archivo,compression='gzip',keep_default_na=False,dtype={'cliente':'string','mes':'string'})
    raise FileNotFoundError(f'Falta {tipo}: configure el ID privado de Drive en Secrets.')

@st.cache_resource(ttl=900)
def conexion_planes(info, spreadsheet_id):
    from drive_util import credenciales
    from almacen import get_sheet
    return get_sheet(credenciales(info),spreadsheet_id)

@st.cache_data(ttl=90,show_spinner=False)
def leer_tablas(info,spreadsheet_id):
    from almacen import leer
    sh=conexion_planes(info,spreadsheet_id)
    return leer(sh,'planes'),leer(sh,'contactos')


def filtro_lista(title,values):
    opts=['Todos']+sorted(str(x) for x in values if pd.notna(x) and str(x).strip())
    return st.sidebar.selectbox(title,opts)


def formato_fecha(df,col):
    if col in df.columns:
        return pd.to_datetime(df[col],errors='coerce')
    return pd.Series(pd.NaT,index=df.index)

info=None if LOCAL_MODE else info_google()
sales_id=secrets_opt('sales_snapshot_id','')
clients_id=secrets_opt('clients_snapshot_id','')
plans_id=secrets_opt('plans_sheet_id','')
actual_id=secrets_opt('current_sales_file_id','')
cierres_index_id=secrets_opt('cierres_index_id','')
private_data_folder_id=secrets_opt('private_data_folder_id','')

st.title('Gestión de clientes no compradores')
st.caption('DDV · Manual 2.1.2.5 · Cierres mensuales de Drive, CNC históricos y relevamientos')
if LOCAL_MODE:
    st.info('MODO PRUEBA LOCAL · Cierres ya archivados y ventas históricas. Los planes/contactos se guardan en SQLite. Los datos solo cambian si se actualizan los snapshots locales.')

@st.cache_resource(show_spinner=False)
def conectar_relevamientos(database_url, sqlite_path):
    storage=Store(database_url=database_url or None,sqlite_path=sqlite_path)
    semilla=ROOT/'data'/'campana_2026-10.csv'
    if storage.total()==0 and semilla.exists():
        storage.seed(preparar_csv(semilla.read_bytes()))
    return storage

# En local las dos apps escriben/leen el MISMO archivo de la carpeta compartida.
# Publicadas en servicios distintos, las dos usan la MISMA DATABASE_URL PostgreSQL.
relev_db_url=os.environ.get('DATABASE_URL') or secrets_opt('DATABASE_URL','')
relev_db_path=os.environ.get('CNC_RELEVAMIENTOS_DB',str(ROOT.parent/'datos_compartidos'/'relevamientos.sqlite'))
relev_db=None
if LOCAL_MODE or relev_db_url:
    try:
        relev_db=conectar_relevamientos(relev_db_url,relev_db_path)
    except Exception as e:
        st.error('No pude conectar el relevamiento de promotores: '+str(e))
else:
    st.info('Seguimiento de promotores todavía sin conectar: configurá DATABASE_URL compartida en Secrets al publicar ambos tableros.')


def datos_relevamiento(mes, supervisor='Todos',promotor='Todos',negocio='Todos'):
    if negocio not in ('Todos','CZA','UNG','NABS'):
        return pd.DataFrame(),pd.DataFrame()
    if relev_db is None or mes not in relev_db.periods():
        return pd.DataFrame(),pd.DataFrame()
    return resumen_relevamientos(relev_db.campaign(mes),supervisor,promotor,negocio)


@st.fragment(run_every='30s')
def alerta_relevamiento(mes, supervisor, promotor, negocio):
    if relev_db is None:
        return
    if mes not in relev_db.periods():
        st.info(f'Aún no se cargó la campaña de relevamientos de {mes}. La falta de campaña no equivale a cero pendientes.')
        return
    resumen,detalle=datos_relevamiento(mes,supervisor,promotor,negocio)
    if resumen.empty:
        st.info('No hay clientes de CZA/UNG asignados en la campaña para este filtro.')
        return
    pendientes=int(resumen['pendientes'].sum())
    prom_pend=int((resumen['pendientes']>0).sum())
    if pendientes:
        st.warning(f'🔔 Relevamientos CNC {mes}: faltan **{pendientes} clientes** en **{prom_pend} promotores**. '
                   'Ver el detalle en «Seguimiento relevamientos». Se actualiza cada 30 segundos.')
    else:
        st.success(f'✅ Relevamientos CNC {mes}: todos los {int(resumen["asignados"].sum())} clientes asignados están respondidos.')


@st.fragment(run_every='30s')
def panel_relevamiento(mes, supervisor, promotor, negocio):
    if relev_db is None:
        st.error('La base compartida de relevamientos no está configurada.')
        return
    if mes not in relev_db.periods():
        st.warning(f'No hay campaña para {mes}. Importá la cartera CNC U3M del período antes de medir cumplimiento.')
        return
    resumen,detalle=datos_relevamiento(mes,supervisor,promotor,negocio)
    if resumen.empty:
        st.info('No hay promotores con clientes en el alcance seleccionado.')
        return
    total=int(resumen['asignados'].sum());listos=int(resumen['respondidos'].sum());pend=total-listos
    k1,k2,k3,k4=st.columns(4)
    k1.metric('Clientes asignados',total)
    k2.metric('Relevados',listos)
    k3.metric('Pendientes',pend)
    k4.metric('Promotores pendientes',int((resumen['pendientes']>0).sum()))
    st.progress(listos/total if total else 0)
    st.caption('Clientes únicos por promotor; CZA + UNG se releva una sola vez. '
               'Una respuesta solo cuenta como completa cuando cubre todos los negocios elegidos. '
               'No equivale a BEES Force oficial ni a visita U12M.')
    tabla=resumen.rename(columns={
        'promotor':'Promotor','supervisor':'Supervisor','asignados':'Asignados',
        'respondidos':'Relevados','pendientes':'Pendientes','avance_pct':'Avance %',
        'alerta':'Estado','casos_cza':'Casos CZA','casos_ung':'Casos UNG'})
    orden=['Promotor','Supervisor','Asignados','Relevados','Pendientes','Avance %','Estado','Casos CZA','Casos UNG']
    st.dataframe(tabla[orden],hide_index=True,use_container_width=True,height=min(640,max(180,35*(len(tabla)+1))))
    st.download_button('Exportar alertas por promotor (CSV)',
        tabla[orden].to_csv(index=False,sep=';').encode('utf-8-sig'),
        file_name=f'CNC_relevamientos_pendientes_{mes}.csv',mime='text/csv')
    if not detalle.empty:
        with st.expander(f'Ver clientes pendientes ({pend})'):
            clientes_pend=detalle[detalle['estado']=='Pendiente'].rename(columns={
                'promotor':'Promotor','supervisor':'Supervisor','cliente':'Código',
                'fantasia':'Comercio','razon_social':'Razón social',
                'negocios':'Negocio(s)','estado':'Estado'})
            st.dataframe(clientes_pend[['Promotor','Supervisor','Código','Comercio','Razón social','Negocio(s)','Estado']],
                use_container_width=True,hide_index=True,height=380)
            st.download_button('Descargar clientes pendientes (CSV)',
                clientes_pend.to_csv(index=False,sep=';').encode('utf-8-sig'),
                file_name=f'CNC_clientes_pendientes_{mes}.csv',mime='text/csv')


try:
    clientes=leer_datos('clientes',str(ROOT/'data/clientes.csv.gz'),clients_id,info)
    faltantes=[c for c in ['licencia_alcohol','supervisor_asignado'] if c not in clientes.columns]
    if faltantes:
        raise ValueError('El padrón compactado no tiene '+', '.join(faltantes)+
                         '. Reprocesá el maestro para incluir licencia de alcohol y supervisores.')
    for c in ['alta','fecha_baja','fecha_baja_fuerza']:
        clientes[c]=pd.to_datetime(clientes[c],errors='coerce')
    clientes['cliente']=clientes['cliente'].astype('string').str.replace(r'\.0$','',regex=True).str.lstrip('0').replace('', '0')
    ventas=leer_datos('ventas',str(ROOT/'data/ventas_resumen.csv.gz'),sales_id,info)
    ventas['cliente']=ventas['cliente'].astype('string').str.replace(r'\.0$','',regex=True).str.lstrip('0').replace('', '0')
    ventas['neto']=pd.to_numeric(ventas['neto'],errors='coerce').fillna(0)
    ruta_force=ROOT/'data'/'force_respuestas.csv.gz'
    force=cargar_respuestas(ruta_force) if ruta_force.exists() else pd.DataFrame(
        columns=['mes','fecha','cliente','negocio','motivo_principal','detalle','estado_force','bdr_id','fuente','preguntas'])
    # El tablero es por CIERRES: nunca sumar ventadiaria.txt en curso.
    # El cierre mensual reemplaza el mes completo en ventas_resumen.csv.gz.
except Exception as exc:
    st.error('No se pueden abrir los datos compactos. Revisá los ID de Drive, permisos y el archivo de Secrets.')
    st.code(str(exc));st.stop()

@st.cache_data(ttl=600,show_spinner=False)
def leer_indice_de_cierres(indice_id,credenciales_gcp,carpeta_privada):
    from cierre_mensual import leer_index
    if credenciales_gcp and indice_id:
        return leer_index(datos_de_drive(indice_id,credenciales_gcp))
    if credenciales_gcp and carpeta_privada:
        # El índice puede crearse en diciembre con el primer cierre, sin
        # modificar Secrets ni pedir un ID nuevo cada mes.
        from google.auth.transport.requests import AuthorizedSession
        from drive_util import credenciales
        ses=AuthorizedSession(credenciales(credenciales_gcp))
        q=f"'{carpeta_privada}' in parents and name = 'cierres_index.json' and trashed = false"
        r=ses.get('https://www.googleapis.com/drive/v3/files',params={
            'q':q,'fields':'files(id,name),nextPageToken','pageSize':100},timeout=30)
        r.raise_for_status()
        encontrados=r.json().get('files',[])
        if encontrados:
            return leer_index(datos_de_drive(encontrados[0]['id'],credenciales_gcp))
    local=ROOT/'data'/'cierres_index.json'
    return leer_index(local.read_bytes() if local.exists() else None)

try:
    indice_cierres=leer_indice_de_cierres(cierres_index_id,info,private_data_folder_id)
except Exception as exc:
    st.error('No se puede leer el índice de cierres de Drive: '+str(exc))
    st.stop()

# Mayo/2025 a octubre/2026 son históricos procesados; desde noviembre/2026
# solo se habilitan meses con cierre registrado en Drive.
from zoneinfo import ZoneInfo
mes_corriente=datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).strftime('%Y-%m')
meses=sorted(x for x in ventas['mes'].dropna().astype(str).unique()
             if len(x)==7 and x < mes_corriente and
             (x<='2026-10' or x in indice_cierres.get('cierres',{})))
if not meses:
    st.error('No hay cierres mensuales completos en las fuentes.');st.stop()
mes=st.sidebar.selectbox('Período de cierre',meses,
     index=meses.index('2026-10') if '2026-10' in meses and not indice_cierres['cierres']
     else len(meses)-1)
if mes in indice_cierres['cierres']:
    datos_cierre=indice_cierres['cierres'][mes]
    c_id=datos_cierre.get('clientes_id')
    if not c_id:
        st.error('El cierre '+mes+' no tiene snapshot de clientes.');st.stop()
    try:
        clientes=leer_datos('clientes_cierre',str(ROOT/'data'/f'clientes_cierre_{mes}.csv.gz'),c_id,info)
        for c in ['alta','fecha_baja','fecha_baja_fuerza']:
            clientes[c]=pd.to_datetime(clientes[c],errors='coerce')
        clientes['cliente']=clientes['cliente'].astype('string').str.replace(r'\.0$','',regex=True).str.lstrip('0').replace('', '0')
    except Exception as exc:
        st.error('No puedo cargar el padrón histórico de '+mes+': '+str(exc));st.stop()
    st.sidebar.success(f'Cierre {mes} archivado · fuente Drive')
else:
    st.sidebar.caption('Cierre histórico inicial, antes de la automatización de Drive.')

# Un único criterio de promotor se aplica a todo el tablero, incluidas respuestas Force.
# El maestro no contiene asignaciones históricas de promotor: se usa la asignación
# disponible y no se inventa un promotor para clientes anulados.
total_clientes_fuente=len(clientes)
mascara_promotor=tiene_promotor_asignado(clientes)
clientes_excluidos_sin_promotor=int((~mascara_promotor).sum())
clientes=clientes.loc[mascara_promotor].copy()
clientes_base_para_campana=clientes.copy()
if not force.empty:
    force=force[force['cliente'].astype(str).isin(set(clientes['cliente'].astype(str)))].copy()

if not LOCAL_MODE and not info and (not sales_id or not clients_id):
    st.info('Vista con archivos compactos locales. Para GitHub + Streamlit Cloud, configurá los ID privados de Drive en Secrets.')

st.sidebar.header('Filtros')
# 'UNG' es el nombre del origen de ventas; internamente se presenta como NABs.
negocio_etiqueta=st.sidebar.selectbox('Negocio',['Todos','CZA','UNG','MATCH','AGUAS','MARKETPLACE'])
negocio='NABS' if negocio_etiqueta=='UNG' else negocio_etiqueta
supervisor=st.sidebar.selectbox('Supervisor',['Todos','BRUNO ISMAEL','HERNAN CASCO'],
                                 help='Estructura comercial 2026. Los promotores de otros supervisores se conservan en Todos.')
if supervisor!='Todos':
    clientes=clientes.loc[clientes['supervisor_asignado'].astype(str).eq(supervisor)].copy()
    if not force.empty:
        force=force.loc[force['cliente'].astype(str).isin(set(clientes['cliente'].astype(str)))].copy()
modo=st.sidebar.selectbox('Cartera',['CNC U3M','CNC U12M','Todos los activos','Solo sin plan','Pendiente de contacto','Toda la cartera histórica 3M','Bajas durante 3M'])
promotor=filtro_lista('Promotor',clientes['promotor'].dropna().unique())
localidad=filtro_lista('Localidad',clientes['localidad'].dropna().unique())
buscar=st.sidebar.text_input('Buscar cliente (código o nombre)')
if negocio=='CZA':
    st.sidebar.caption('CZA: solo clientes con Licencia alcohol = SI.')
elif negocio=='NABS':
    st.sidebar.caption('UNG/NABs: sin exclusión por licencia de alcohol.')
if st.sidebar.button('Recalcular con los archivos disponibles',help='Limpia caché y vuelve a leer los datos de la carpeta local'):
    st.cache_data.clear();st.rerun()

mapeo=dict(UNIDADES_POR_DEFECTO)
custom=secrets_opt('unit_mapping')
if custom:
    for k,v in dict(custom).items():
        if v in NEGOCIOS:mapeo[k.strip().upper()]=v

casos,meta=generar_casos(clientes,ventas,mes,set(meses),mapeo)
# Un cierre NO pisa campañas anteriores. Solo se habilita una campaña nueva
# cuando el cierre ya existe, y a solicitud del administrador.
if mes in indice_cierres.get('cierres',{}) and relev_db is not None and mes not in relev_db.periods():
    with st.sidebar.expander(f'Nueva campaña de promotores {mes}',expanded=True):
        st.info('El cierre está disponible, pero aún no se creó su campaña de relevamiento. '
                'Los promotores no verán el mes hasta que la actives.')
        if st.button('Activar campaña U3M del cierre',key='crear_campana_cnc_cierre'):
            candidatos=casos.loc[casos['cnc_u3m'] & casos['negocio'].isin(['CZA','NABS'])].copy()
            candidatos['periodo']=mes
            candidatos['negocio']=candidatos['negocio'].replace({'NABS':'UNG'})
            candidatos['cnc_u3m']='SI'
            candidatos['ultima_compra']=candidatos['ultima_compra'].fillna('')
            candidatos['alta']=candidatos['alta'].astype(str)
            from store import COLUMNAS
            import io as _io
            datos_csv=candidatos[list(COLUMNAS)].fillna('').to_csv(index=False)
            registros=preparar_csv(datos_csv)
            relev_db.seed(registros,replace_period=False)
            st.success(f'Campaña {mes}: {len(registros)} casos CZA/UNG activados. '
                'Cada cliente aparece una sola vez en la app.')
            st.rerun()
historico_3m,meta_hist=cartera_vigencia_3m(clientes,mes)
# Fuente histórica usada para KPI y vistas de Cartera y CNC; una fila por cliente con vigencia en
# algún momento de los tres meses, incluidos los anulados en la ventana.
h_filtrado=historico_3m.copy()
# Histórico de CZA solo para licenciatarios. UNG mantiene toda la cartera.
if negocio=='CZA':
    h_filtrado=h_filtrado.loc[tiene_licencia_alcohol(h_filtrado)].copy()
if promotor!='Todos':
    h_filtrado=h_filtrado[h_filtrado['promotor'].astype(str)==promotor]
if localidad!='Todos':
    h_filtrado=h_filtrado[h_filtrado['localidad'].astype(str)==localidad]
if buscar:
    q=buscar.strip().lower()
    h_filtrado=h_filtrado[
        h_filtrado['cliente'].astype(str).str.contains(q,regex=False)
        | h_filtrado['razon_social'].astype(str).str.lower().str.contains(q,regex=False)
        | h_filtrado['fantasia'].astype(str).str.lower().str.contains(q,regex=False)
    ]
if casos.empty:
    st.error('No se pudo construir la cartera del período.');st.stop()

planes=pd.DataFrame(columns=['clave','mes','cliente','negocio','motivo','objetivo','accion','responsable','supervisor','fecha_objetivo','estado','oportunidad_censo','fecha_actualizacion','evidencia'])
contactos=pd.DataFrame(columns=['id','mes','cliente','negocio','fecha','tipo','actor','resultado','observacion','evidencia'])
persistencia_lista=LOCAL_MODE or bool(info and plans_id)
if LOCAL_MODE:
    from almacen_local import leer_local
    planes,contactos=leer_local(DB_LOCAL)
elif persistencia_lista:
    try: planes,contactos=leer_tablas(info,plans_id)
    except Exception as exc:
        st.error(f'No se pudo leer la hoja de planes: {exc}. Guardado deshabilitado.');persistencia_lista=False

for df in (planes,contactos):
    for c in ['cliente','negocio','mes']:
        if c in df.columns:df[c]=df[c].astype(str).str.strip()

planes_mes=planes.loc[planes['mes']==mes].copy()
if len(planes_mes):
    planes_mes=planes_mes.sort_values('fecha_actualizacion').drop_duplicates(['cliente','negocio'],keep='last')
    extra=['cliente','negocio','motivo','objetivo','accion','responsable','supervisor','fecha_objetivo','estado','oportunidad_censo','evidencia']
    casos=casos.merge(planes_mes[extra],on=['cliente','negocio'],how='left')
else:
    for c in ['motivo','objetivo','accion','responsable','supervisor','fecha_objetivo','estado','oportunidad_censo','evidencia']:casos[c]=''

for c in ['motivo','objetivo','accion','responsable','supervisor','fecha_objetivo','estado','oportunidad_censo','evidencia']:
    casos[c]=casos[c].fillna('').astype(str)

hasta=fecha_fin(mes)
if len(contactos):
    contactos['fecha_dt']=pd.to_datetime(contactos['fecha'],errors='coerce')
    prev=contactos.loc[contactos['fecha_dt']<=hasta].copy()
    ultima=prev.groupby(['cliente','negocio'],as_index=False)['fecha_dt'].max().rename(columns={'fecha_dt':'ultimo_contacto'})
    casos=casos.merge(ultima,on=['cliente','negocio'],how='left')
else: casos['ultimo_contacto']=pd.NaT

# Enlazar evidencia BEES Force por cliente, negocio y período; no duplicar encuestas por pregunta.
casos=cruzar_mes(casos,force,mes)
if relev_db is not None and mes in relev_db.periods():
    registros=pd.DataFrame(relev_db.campaign(mes))
    if not registros.empty:
        registros=registros[['cliente','negocio','promotor','motivo','comentario','respondido']].copy()
        registros['negocio']=registros['negocio'].replace({'UNG':'NABS'})
        registros=registros.rename(columns={'motivo':'motivo_relevamiento',
            'comentario':'comentario_relevamiento','respondido':'fecha_relevamiento'})
        casos=casos.merge(registros,on=['cliente','negocio','promotor'],how='left',validate='one_to_one')
for c in ('motivo_relevamiento','comentario_relevamiento','fecha_relevamiento'):
    if c not in casos.columns: casos[c]=''
    casos[c]=casos[c].fillna('').astype(str)
casos['estado_relevamiento']=casos['motivo_relevamiento'].str.strip().ne('').map({True:'Respondido',False:'Pendiente'})
casos=control_contactos_u12m(casos,contactos,mes)
casos['fecha_objetivo_dt']=pd.to_datetime(casos['fecha_objetivo'],errors='coerce')
casos['plan_vencido']=casos['cnc_u3m'] & casos['fecha_objetivo_dt'].notna() & (casos['fecha_objetivo_dt']<hasta) & ~casos['estado'].isin(['Completado','Recuperado'])

vis=casos.copy()
if negocio!='Todos':vis=vis[vis.negocio==negocio]
if promotor!='Todos':vis=vis[vis.promotor.astype(str)==promotor]
if localidad!='Todos':vis=vis[vis.localidad.astype(str)==localidad]
if buscar:
    q=buscar.strip().lower()
    vis=vis[vis['cliente'].astype(str).str.contains(q,regex=False) | vis['razon_social'].astype(str).str.lower().str.contains(q,regex=False) | vis['fantasia'].astype(str).str.lower().str.contains(q,regex=False)]
if modo=='CNC U3M':vis=vis[vis['cnc_u3m']]
elif modo=='CNC U12M':vis=vis[vis['cnc_u12m']]
elif modo=='Solo sin plan':vis=vis[vis['cnc_u3m'] & vis['negocio'].isin(['CZA','NABS']) & (vis['accion'].str.strip()=='')]
elif modo=='Pendiente de contacto':vis=vis[vis['contacto_pendiente']]

if mes==datetime.now().strftime('%Y-%m'):
    st.warning('Mes en curso: la detección CNC es provisoria hasta que cierre el período y se consoliden las ventas.')
if not meta['u3_completo']:
    st.warning('U3M no verificable. Faltan meses: '+', '.join(meta['meses_faltantes_u3']))
if not meta['u12_completo']:
    st.info('U12M todavía no verificable. Meses fuera de cobertura: '+', '.join(meta['meses_faltantes_u12']))
if 'MATCH' not in meta['disponibles']:
    st.warning('MATCH: sin correspondencia validada con una unidad/SKU de ventas. No se publican CNC de MATCH hasta configurar el mapeo.')
if negocio=='NABS' or negocio=='Todos':
    st.caption('Clasificación provisional: UNG se muestra como NABS. Confirmar si productos MATCH deben separarse antes de usar el indicador en auditoría.')

# Las tarjetas obedecen los filtros (antes de aplicar el selector 'Cartera').
alcance_filtros=casos.copy()
if negocio!='Todos':alcance_filtros=alcance_filtros[alcance_filtros.negocio==negocio]
if promotor!='Todos':alcance_filtros=alcance_filtros[alcance_filtros.promotor.astype(str)==promotor]
if localidad!='Todos':alcance_filtros=alcance_filtros[alcance_filtros.localidad.astype(str)==localidad]
if buscar:
    q=buscar.strip().lower()
    alcance_filtros=alcance_filtros[
        alcance_filtros.cliente.astype(str).str.contains(q,regex=False) |
        alcance_filtros.razon_social.astype(str).str.lower().str.contains(q,regex=False) |
        alcance_filtros.fantasia.astype(str).str.lower().str.contains(q,regex=False)]
# Estos KPI distinguen: cartera 3M = clientes únicos, CNC = casos por negocio
# de los que siguen vigentes al cierre (sin sumar bajas como CNC).
k1,k2,k3,k4,k5=st.columns(5)
k1.metric('Cartera 3M · elegible',f"{len(h_filtrado):,}".replace(',','.'))
k2.metric('Activos al cierre · elegibles',f"{int(h_filtrado['vigente_cierre'].sum()):,}".replace(',','.'))
k3.metric('Bajas durante 3M',f"{int(h_filtrado['baja_en_ventana'].sum()):,}".replace(',','.'))
k4.metric('CNC U3M · casos al cierre',f"{int(alcance_filtros.cnc_u3m.sum()):,}".replace(',','.'))
k5.metric('CNC U12M · subconjunto U3M',f"{int(alcance_filtros.cnc_u12m.sum()):,}".replace(',','.'))
st.caption(f'Excluidos del universo operativo: {clientes_excluidos_sin_promotor:,} clientes sin promotor individual asignado en el padrón disponible. '
           'CZA: solo licencia de alcohol SI del padrón disponible; UNG/NABs: cartera completa. '
           'Los tres primeros indicadores son CLIENTES ÚNICOS; CNC cuenta CASOS por negocio. '
           'La asignación de supervisor y la licencia se toman del padrón/estructura disponible, no de un historial mensual.'.replace(',','.'))

alerta_relevamiento(mes,supervisor,promotor,negocio_etiqueta)
cartera,rk_promotor,gestion,respuestas,auditoria,seguimiento=st.tabs(['Cartera y CNC','CNC por promotor','Planes de acción y contactos','Respuestas BEES Force','Auditoría y cobertura','🔔 Seguimiento relevamientos'])

with cartera:
    # La selección lateral de CNC SIEMPRE muestra exclusivamente clientes con
    # promotor asignado y vigentes AL CIERRE. Los dados de baja solo se muestran
    # al pedir explícitamente la cartera histórica.
    if modo in ['Toda la cartera histórica 3M', 'Bajas durante 3M']:
        st.subheader(f'Cartera histórica de 3 meses · {meta_hist["meses"][0]} a {mes}')
        st.caption('Esta vista histórica conserva clientes dados de baja durante el trimestre. '
                   'No implica que sean CNC elegibles ni que deban tener un plan.')
        base_cnc=casos if negocio=='Todos' else casos[casos['negocio']==negocio]
        resumen_cnc=base_cnc.groupby('cliente',as_index=False).agg(
            cnc_u3m_negocios=('cnc_u3m','sum'),cnc_u12m_negocios=('cnc_u12m','sum'))
        h_cartera=h_filtrado.merge(resumen_cnc,on='cliente',how='left',validate='one_to_one')
        for c in ['cnc_u3m_negocios','cnc_u12m_negocios']:
            h_cartera[c]=h_cartera[c].fillna(0).astype(int)
        h_cartera['estado_cnc']='Sin CNC U3M al cierre'
        h_cartera.loc[h_cartera['cnc_u3m_negocios']>0,'estado_cnc']='CNC U3M al cierre'
        h_cartera.loc[h_cartera['cnc_u12m_negocios']>0,'estado_cnc']='CNC U12M al cierre'
        h_cartera.loc[~h_cartera['vigente_cierre'],'estado_cnc']='No elegible: baja anterior al cierre'
        if modo=='Bajas durante 3M':
            h_cartera=h_cartera[h_cartera.baja_en_ventana].copy()
        cols_h=['cliente','fantasia','razon_social','promotor','supervisor_asignado','licencia_alcohol','ruta','localidad']
        cols_h += [f'estado_{m}' for m in meta_hist['meses']]
        cols_h += ['fecha_baja_ventana','estado_cnc','cnc_u3m_negocios','cnc_u12m_negocios','alerta']
        etiq={'cliente':'Código','fantasia':'Comercio','razon_social':'Razón social',
              'promotor':'Promotor','supervisor_asignado':'Supervisor comercial','licencia_alcohol':'Licencia alcohol','ruta':'Ruta','localidad':'Localidad',
              'fecha_baja_ventana':'Fecha baja','estado_cnc':'Estado CNC al cierre',
              'cnc_u3m_negocios':'CNC U3M (negocios)',
              'cnc_u12m_negocios':'CNC U12M (negocios)','alerta':'Alerta',
              **{f'estado_{m}':f'Estado {m[5:7]}/{m[:4]}' for m in meta_hist['meses']}}
        tabla=h_cartera[cols_h].rename(columns=etiq)
        st.caption(f'{len(tabla):,} clientes históricos seleccionados, sin promotores vacíos. '
                   'Si figuran bajas, se informa la fecha.')
        st.dataframe(tabla,use_container_width=True,hide_index=True,height=520)
        st.download_button('Exportar histórico 3M (CSV para Excel)',
            tabla.to_csv(index=False,sep=';').encode('utf-8-sig'),
            file_name=f'CNC_historico_3M_{mes}.csv',mime='text/csv')
    else:
        st.subheader(f'{modo} · {mes} · clientes activos al cierre')
        st.caption('La tabla solo muestra clientes que seguían vigentes al último día del mes '
                   'y que tienen promotor asignado. No incluye bajas de la ventana 3M ni '
                   'clientes sin promotor; las bajas pueden consultarse en «Cartera» → «Bajas durante 3M». '
                   'Para ser CNC se requiere antigüedad desde el primer día de la ventana U3M/U12M; '
                   'los clientes nuevos no se cuentan como CNC.')
        if vis.empty:
            st.info('No hay casos que cumplan los filtros.')
        else:
            etiquetas={
                'cliente':'Código','fantasia':'Comercio','razon_social':'Razón social',
                'negocio':'Negocio','promotor':'Promotor','supervisor_asignado':'Supervisor comercial','licencia_alcohol':'Licencia alcohol','ruta':'Ruta',
                'ultima_compra':'Última compra','clasificacion':'Estado de compra',
                'motivo':'Motivo no compra','estado':'Estado del plan',
                'frecuencia_contacto':'Frecuencia U12M','contactos_mes':'Contactos mes',
                'contactos_requeridos':'Meta mes','ultimo_contacto':'Último contacto',
                'fecha_objetivo':'Vence plan','supervisor':'Supervisor del plan',
                'fecha_force':'Force fecha','motivo_force':'Motivo Force',
                'estado_relevamiento':'Relevamiento promotor','motivo_relevamiento':'Motivo promotor',
                'fecha_relevamiento':'Fecha relevada'
            }
            tabla=vis[[c for c in etiquetas if c in vis.columns]].rename(columns=etiquetas).copy()
            if 'Último contacto' in tabla:
                tabla['Último contacto']=pd.to_datetime(
                    tabla['Último contacto'],errors='coerce').dt.strftime('%d/%m/%Y').fillna('')
            st.caption(f'{len(tabla):,} casos por negocio · no sumar distintas categorías '
                       'como si fueran clientes únicos.')
            st.dataframe(tabla,use_container_width=True,hide_index=True,height=520)
            st.download_button('Exportar CNC elegibles (CSV para Excel)',
                tabla.to_csv(index=False,sep=';').encode('utf-8-sig'),
                file_name=f'CNC_elegibles_{mes}.csv',mime='text/csv')
        if negocio=='Todos':
            resumen=alcance_filtros.groupby('negocio',as_index=False).agg(
                clientes_activos=('cliente','nunique'),cnc_u3m=('cnc_u3m','sum'),
                cnc_u12m=('cnc_u12m','sum'),
                con_motivo_force=('motivo_force',lambda s:s.astype(str).str.strip().ne('').sum()))
            st.markdown('**Resumen por negocio (universos no aditivos)**')
            st.dataframe(resumen,hide_index=True,use_container_width=True)


with rk_promotor:
    st.subheader('CNC por promotor')
    st.caption(
        'Ranking de CLIENTES ÚNICOS sin compra según el horizonte elegido. '
        'Solo incluye clientes vigentes al cierre del mes, con promotor asignado. '
        'Se respetan los filtros laterales de período, negocio, promotor, localidad y búsqueda; '
        'el selector lateral «Cartera» no altera este ranking.'
    )
    h_periodo = st.radio(
        'Período sin compra',
        options=[3, 6, 12],
        format_func=lambda x: f'{x} meses',
        horizontal=True,
        key='ranking_cnc_horizonte'
    )
    resumen_prom, control_prom = resumen_cnc_por_promotor(
        alcance_filtros, mes, set(meses), h_periodo
    )
    st.caption(
        f'Período analizado: {control_prom["inicio"]} a {control_prom["fin"]} '
        f'({h_periodo} meses calendario, inclusive).'
    )
    if not control_prom['verificable']:
        st.warning(
            'No es posible calcular CNC para este período porque faltan ventas de: '
            + ', '.join(control_prom['faltantes'])
            + '. Se oculta el ranking para no mostrar ceros incorrectos.'
        )
    elif resumen_prom.empty:
        st.info('No hay promotores con clientes activos para los filtros seleccionados.')
    else:
        num_clientes = int(resumen_prom['clientes_cnc'].sum())
        num_casos = int(resumen_prom['casos_cnc'].sum())
        num_activos = int(resumen_prom['clientes_activos'].sum())
        num_prom = int((resumen_prom['clientes_cnc'] > 0).sum())
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f'CNC {h_periodo}M · clientes únicos', f'{num_clientes:,}'.replace(',', '.'))
        c2.metric('Promotores con CNC', num_prom)
        c3.metric('CNC · casos por negocio', f'{num_casos:,}'.replace(',', '.'))
        c4.metric('Clientes activos al cierre', f'{num_activos:,}'.replace(',', '.'))

        st.markdown(f'**CNC de {h_periodo} meses por promotor · {mes}**')
        st.caption(
            'La columna «Clientes CNC» cuenta cada cliente una vez por promotor. '
            '«Casos CNC» cuenta cliente-negocio: un cliente sin compra en cerveza '
            'y NABs suma dos casos, pero un único cliente. '
            'Las altas posteriores al inicio de la ventana 3M/6M/12M '
            'se excluyen del CNC de ese horizonte.'
        )
        tabla_prom = resumen_prom.rename(columns={
            'promotor': 'Promotor',
            'clientes_activos': 'Clientes activos',
            'clientes_cnc': 'Clientes CNC',
            'casos_cnc': 'Casos CNC',
            'porcentaje_cnc': '% de cartera CNC'
        })
        st.dataframe(
            tabla_prom, use_container_width=True, hide_index=True,
            height=min(590, max(220, (len(tabla_prom) + 1) * 36))
        )
        st.markdown('**Comparación visual entre promotores**')
        st.bar_chart(
            tabla_prom[['Promotor', 'Clientes CNC']].set_index('Promotor'),
            horizontal=True,
            height=min(620, max(240, len(tabla_prom) * 33 + 45))
        )
        st.download_button(
            'Exportar CNC por promotor (CSV para Excel)',
            data=tabla_prom.to_csv(index=False, sep=';').encode('utf-8-sig'),
            file_name=f'CNC_promotores_{h_periodo}M_{mes}.csv',
            mime='text/csv'
        )
    st.caption(
        'Los indicadores U6M y U12M son subconjuntos del U3M cuando los tres '
        'períodos tienen cobertura completa; no se suman entre sí. '
        'Se utiliza la asignación de promotor del padrón disponible, '
        'no la asignación histórica si hubo cambios posteriores.'
    )


with gestion:
    st.subheader('Plan de recuperación y seguimiento mensual · CZA / NABs U3M')
    st.button('↻ Actualizar relevamientos de promotores',
              help='Vuelve a consultar los motivos registrados en la base compartida; no borra planes ni respuestas.',
              key='actualizar_motivos_en_planes')
    aviso_masivo=st.session_state.pop('aviso_planes_masivos',None)
    if aviso_masivo:
        st.success(aviso_masivo)

    if not persistencia_lista:
        st.error('Para el modo online, se debe configurar la hoja privada de Google Sheets y permisos de escritura.')
    elif LOCAL_MODE:
        st.caption('Los cambios se guardan en data/cnc_local.sqlite, incluso después de cerrar y volver a abrir.')
    posibles=casos.loc[casos.cnc_u3m & casos.negocio.isin(['CZA','NABS'])].copy()
    if negocio!='Todos':posibles=posibles[posibles.negocio==negocio]
    if promotor!='Todos':posibles=posibles[posibles.promotor.astype(str)==promotor]
    if len(posibles)==0:
        st.info('No hay CNC verificables del segmento seleccionado.')
    else:
        # Tabla con selección de una sola fila, sin desplegable de cientos de clientes.
        # Solo los CNC U3M que siguen activos al cierre y tienen promotor.
        posibles=posibles.copy()
        if localidad!='Todos':
            posibles=posibles[posibles['localidad'].astype(str)==localidad]
        if buscar:
            texto=buscar.strip().lower()
            posibles=posibles[
                posibles['cliente'].astype(str).str.contains(texto,regex=False) |
                posibles['fantasia'].astype(str).str.lower().str.contains(texto,regex=False) |
                posibles['razon_social'].astype(str).str.lower().str.contains(texto,regex=False)]
        # El motivo se toma de la aplicación móvil de promotores (no de Force).
        # Este filtro también determina el alcance de «Seleccionar TODOS».
        motivo_promotor_filtro=st.selectbox(
            'Filtrar planes por motivo relevado por el promotor',
            ['Todos',*MOTIVOS_PROMOTOR,'Sin relevar'],
            key='filtro_motivo_promotor_plan',
            help='Filtra por la respuesta registrada en la app de promotores para este cliente y mes. '
                 'Sin relevar incluye los clientes que todavía no respondieron.'
        )
        posibles=filtrar_motivo_promotor(posibles,motivo_promotor_filtro)
        qplan=st.text_input('Buscar en el listado de planes (código o comercio)',
                            placeholder='Ej.: 163 o PIZZERIA',key='buscar_plan_lista')
        if qplan.strip():
            t=qplan.strip().lower()
            posibles=posibles[
                posibles['cliente'].astype(str).str.contains(t,regex=False) |
                posibles['fantasia'].astype(str).str.lower().str.contains(t,regex=False) |
                posibles['razon_social'].astype(str).str.lower().str.contains(t,regex=False)]
        posibles=posibles.reset_index(drop=True)
        st.caption(
            f'{len(posibles)} casos CNC U3M elegibles para el motivo «{motivo_promotor_filtro}». '
            'Podés marcar varias filas o asignar un plan a TODOS los casos del filtro. '
            'El relevamiento corresponde a la app de promotores; no es la validación oficial de BEES Force.'
        )
        if posibles.empty:
            st.warning('No hay clientes con ese motivo dentro de los filtros aplicados. Elegí otro motivo o quitá la búsqueda.')
        else:
            listado=posibles[['cliente','fantasia','razon_social','negocio','promotor',
                               'motivo_relevamiento','comentario_relevamiento','fecha_relevamiento',
                               'motivo_force','estado','accion']].copy()
            listado['motivo_relevamiento']=listado['motivo_relevamiento'].replace({'':'Sin relevar'})
            listado['estado']=listado['estado'].replace({'':'Sin plan'}).fillna('Sin plan')
            listado['accion']=listado['accion'].fillna('').astype(str).str.slice(0,80)
            listado=listado.rename(columns={
                'cliente':'Código','fantasia':'Nombre de fantasía','razon_social':'Razón social',
                'negocio':'Negocio','promotor':'Promotor',
                'motivo_relevamiento':'Motivo promotor',
                'comentario_relevamiento':'Detalle del promotor',
                'fecha_relevamiento':'Fecha relevada',
                'motivo_force':'Motivo Force','estado':'Estado del plan','accion':'Acción prevista'})
            clave_filtro='|'.join(str(x) for x in [mes,negocio,supervisor,promotor,localidad,buscar,qplan,motivo_promotor_filtro])
            clave_visual=hashlib.sha1(clave_filtro.encode('utf-8')).hexdigest()[:12]
            todos_visibles=st.checkbox(
                f'Seleccionar TODOS los {len(posibles)} clientes del listado filtrado',
                value=False,key=f'masivo_todos_{clave_visual}',
                help='Incluye solamente los clientes elegibles mostrados tras aplicar los filtros y la búsqueda.'
            )
            seleccion=st.dataframe(
                listado,hide_index=True,use_container_width=True,height=370,
                on_select='rerun',selection_mode='multi-row',
                key=f'tabla_clientes_plan_{clave_visual}'
            )
            elegidas=(list(range(len(posibles))) if todos_visibles
                     else sorted(set(int(i) for i in seleccion.selection.rows if int(i)<len(posibles))))
            st.caption(
                f'Seleccionados: {len(elegidas)} de {len(posibles)} · '
                'Marcá varias casillas de la tabla o usá «Seleccionar TODOS».'
            )
            if len(elegidas)>1:
                seleccionadas=posibles.iloc[elegidas].copy()
                n_preexistentes=sum(
                    bool(str(d.get('accion','')).strip() or str(d.get('estado','')).strip()
                         or str(d.get('motivo','')).strip())
                    for d in seleccionadas.to_dict('records')
                )
                st.markdown(f'### Plan de acción compartido · {len(seleccionadas)} clientes')
                st.info(
                    'Se aplicarán los mismos objetivo, acción, fecha y estado. '
                    'El responsable será el promotor asignado a cada cliente, salvo que indiques uno común. '
                    'El motivo del promotor se conserva por cliente, y solo en su ausencia se usa BEES Force. '
                )
                if n_preexistentes:
                    st.warning(
                        f'{n_preexistentes} seleccionados ya tienen algún dato de plan. '
                        'No se modificarán salvo que marques la opción de sobrescribir.'
                    )
                with st.form(f'plan_masivo_{clave_visual}'):
                    pm_objetivo=st.text_input('Objetivo de recuperación COMÚN')
                    pm_accion=st.text_area('Plan de acción COMÚN *',height=110)
                    ma,mb=st.columns(2)
                    pm_motivo=ma.text_input(
                        'Motivo COMÚN (opcional)',
                        help='Si queda vacío, respeta el motivo existente; si no hay, usa la respuesta del promotor y por último BEES Force.'
                    )
                    pm_responsable=mb.text_input(
                        'Responsable COMÚN (opcional)',
                        help='Dejar vacío para utilizar el promotor de cada cliente.'
                    )
                    mc,md=st.columns(2)
                    pm_supervisor=mc.text_input('Supervisor COMÚN (opcional)')
                    pm_fecha=md.date_input('Fecha compromiso para todos',value=hasta.date())
                    me,mf=st.columns(2)
                    pm_estado=me.selectbox(
                        'Estado del plan para todos',
                        ['Pendiente','En curso','Completado','Recuperado','Sin oportunidad']
                    )
                    pm_oportunidad=mf.selectbox(
                        'Oportunidad de Censo',
                        ['Mantener la de cada cliente','Sin validar','No','Sí']
                    )
                    pm_evidencia=st.text_input('Referencia o evidencia COMÚN (opcional)')
                    pm_sobrescribir=st.checkbox(
                        'Sobrescribir también los planes existentes de los clientes seleccionados',
                        value=False
                    )
                    pm_guardar=st.form_submit_button(
                        f'Guardar el plan para los {len(seleccionadas)} seleccionados',
                        type='primary',disabled=not persistencia_lista
                    )
                if pm_guardar:
                    from planes_masivos import construir_planes_masivos
                    try:
                        planes_nuevos,resumen=construir_planes_masivos(
                            seleccionadas.to_dict('records'),mes,
                            objetivo=pm_objetivo,accion=pm_accion,
                            fecha_objetivo=pm_fecha,estado=pm_estado,
                            motivo_comun=pm_motivo,responsable_comun=pm_responsable,
                            supervisor_comun=pm_supervisor,
                            oportunidad_comun=(
                                '' if pm_oportunidad=='Mantener la de cada cliente'
                                else pm_oportunidad
                            ),
                            evidencia_comun=pm_evidencia,sobrescribir=pm_sobrescribir,
                        )
                        if not planes_nuevos:
                            st.warning(
                                'No hay planes para guardar con estas opciones. '
                                'Revisá si todos ya tenían un plan y la opción de sobrescribir.'
                            )
                        else:
                            if LOCAL_MODE:
                                from almacen_local import guardar_planes_local_masivo
                                guardados=guardar_planes_local_masivo(DB_LOCAL,planes_nuevos)
                            else:
                                from almacen import guardar_planes_masivos_sheet
                                guardados=guardar_planes_masivos_sheet(
                                    conexion_planes(info,plans_id),planes_nuevos
                                )
                            st.session_state['aviso_planes_masivos']=(
                                f'Plan aplicado a {guardados} clientes del período {mes}. '
                                f'Planes existentes protegidos: {resumen["ya_tenian_plan"]}. '
                                f'Casos sin motivo relevado: {resumen["sin_motivo"]}.'
                            )
                            st.cache_data.clear()
                            st.rerun()
                    except Exception as exc:
                        st.error(f'No se pudo completar la carga masiva: {exc}')
            elif not elegidas:
                st.info('Marcá una o varias filas, o activá «Seleccionar TODOS» para aplicar un plan compartido.')
            else:
                dato=posibles.iloc[int(elegidas[0])]
                codigo=str(dato['cliente']);neg=str(dato['negocio']);clave=f'{mes}|{codigo}|{neg}'
                st.caption(f"Ruta: {dato.get('ruta','')}  · Promotor: {dato.get('promotor','')}  · Última compra: {dato.get('ultima_compra') or 'Sin registro'}")
                motivo_pr=str(dato.get('motivo_relevamiento') or '').strip()
                detalle_pr=str(dato.get('comentario_relevamiento') or '').strip()
                fecha_pr=str(dato.get('fecha_relevamiento') or '').strip()
                if motivo_pr:
                    st.success(f'📋 Relevamiento del promotor · {fecha_pr or mes} · Motivo: {motivo_pr}')
                    if detalle_pr:
                        st.caption('Observación del promotor: '+detalle_pr[:1200])
                else:
                    st.warning('Este cliente todavía no tiene motivo registrado en la app de promotores para el período seleccionado.')
                historial_force=force.loc[(force.cliente==codigo)&(force.negocio==neg)&(force.mes<=mes)].sort_values('fecha',ascending=False) if len(force) else pd.DataFrame()
                sugerido_force=''
                if len(historial_force):
                    f=historial_force.iloc[0]
                    sugerido_force=str(f.get('motivo_principal',''))
                    etiqueta='MES SELECCIONADO' if f['mes']==mes else 'MES ANTERIOR · no computa como relevamiento del período'
                    st.info(f"BEES Force ({etiqueta}) · {f['fecha']} · Motivo: {sugerido_force or 'Sin motivo principal'}")
                    if str(f.get('detalle','')).strip():
                        st.caption('Detalles de la encuesta: '+str(f['detalle'])[:1200])
                else:
                    st.warning('Sin encuesta BEES Force disponible para este cliente y negocio hasta el período seleccionado.')
                if bool(dato['cnc_u12m']): st.info('CNC U12M adicional: programar contacto mensual (0,25) o quincenal (0,50) si el Censo detectó oportunidad.')
                with st.form(f'plan_cnc_{mes}_{codigo}_{neg}'):
                    r1,r2=st.columns(2)
                    motivos=['','Sin dinero','Cerrado','Compra en súper/mayorista','Otro','Cliente cerrado temporalmente','Sin stock / precio','Compra a competencia','Falta de visita','Problemas de aplicación / BEES','Problemas de entrega','Cliente ocasional','Problemas de crédito','Sin demanda']
                    actual=dato['motivo'] or motivo_pr or sugerido_force; motivo_sel=r1.selectbox('Motivo de no compra',motivos,index=motivos.index(actual) if actual in motivos else 0)
                    motivo_extra=r2.text_input('Motivo específico / otro',value=actual if actual not in motivos else '')
                    objetivo=st.text_input('Objetivo de recuperación',value=dato['objetivo'])
                    accion=st.text_area('Plan de acción concreto',value=dato['accion'],height=95)
                    x1,x2,x3=st.columns(3)
                    responsable=x1.text_input('Responsable / promotor',value=dato['responsable'] or str(dato['promotor']))
                    supervisor_plan=x2.text_input('Supervisor',value=dato['supervisor'] or str(dato.get('supervisor_asignado','')))
                    oportunidad=x3.selectbox('¿Oportunidad según Censo?',['Sin validar','No','Sí'],index={'SIN VALIDAR':0,'NO':1,'SÍ':2,'SI':2}.get(dato['oportunidad_censo'].upper(),0))
                    y1,y2=st.columns(2)
                    default_date=pd.to_datetime(dato['fecha_objetivo'],errors='coerce')
                    if pd.isna(default_date):default_date=hasta
                    fecha_objetivo=y1.date_input('Fecha compromiso',value=default_date.date())
                    estado=y2.selectbox('Estado del plan',['Pendiente','En curso','Completado','Recuperado','Sin oportunidad'],index=['Pendiente','En curso','Completado','Recuperado','Sin oportunidad'].index(dato['estado']) if dato['estado'] in ['Pendiente','En curso','Completado','Recuperado','Sin oportunidad'] else 0)
                    evidencia=st.text_input('Link a evidencia (BEES Force / documento)',value=dato['evidencia'])
                    guardar=st.form_submit_button('Guardar plan de acción',disabled=not persistencia_lista,type='primary')
                if guardar:
                    motivo_final=(motivo_extra or motivo_sel).strip()
                    if not motivo_final or not accion.strip() or not responsable.strip():
                        st.error('Completá motivo de no compra, acción y responsable.')
                    else:
                        from almacen import guardar_plan
                        plan={'clave':clave,'mes':mes,'cliente':codigo,'negocio':neg,'motivo':motivo_final,
                            'objetivo':objetivo,'accion':accion,'responsable':responsable,'supervisor':supervisor_plan,
                            'fecha_objetivo':fecha_objetivo.isoformat(),'estado':estado,'oportunidad_censo':oportunidad,
                            'fecha_actualizacion':datetime.now().isoformat(timespec='seconds'),'evidencia':evidencia}
                        try:
                            if LOCAL_MODE:
                                from almacen_local import guardar_plan_local
                                guardar_plan_local(DB_LOCAL,plan)
                            else:
                                guardar_plan(conexion_planes(info,plans_id),plan)
                            st.cache_data.clear();st.success('Plan guardado correctamente.');st.rerun()
                        except Exception as exc:st.error(f'No pudo guardarse el plan: {exc}')
                st.divider()
                st.markdown('**Registrar una gestión / visita / contacto**')
                with st.form(f'contacto_cnc_{mes}_{codigo}_{neg}'):
                    b1,b2,b3=st.columns(3)
                    fecha=b1.date_input('Fecha de gestión',value=min(date.today(),hasta.date()))
                    tipo=b2.selectbox('Tipo de contacto',['Visita promotor','Llamado supervisor','Visita supervisor','WhatsApp','Otro'])
                    actor=b3.text_input('Realizado por',value=str(dato.get('promotor','')))
                    resultado=st.selectbox('Resultado',['Motivo relevado','Cliente contactado','Pendiente de respuesta','Rechaza propuesta','Compromiso de compra','Compra confirmada','Sin contacto'])
                    observacion=st.text_area('Detalle y acciones acordadas',height=85)
                    evidencia_g=st.text_input('URL o referencia de evidencia')
                    save_contacto=st.form_submit_button('Registrar gestión',disabled=not persistencia_lista,type='primary')
                if save_contacto:
                    from almacen import agregar_contacto
                    try:
                        registro={'mes':mes,'cliente':codigo,'negocio':neg,'fecha':fecha.isoformat(),
                            'tipo':tipo,'actor':actor,'resultado':resultado,'observacion':observacion,'evidencia':evidencia_g}
                        if LOCAL_MODE:
                            from almacen_local import agregar_contacto_local
                            agregar_contacto_local(DB_LOCAL,registro)
                        else:
                            agregar_contacto(conexion_planes(info,plans_id),registro)
                        st.cache_data.clear();st.success('Gestión registrada correctamente.');st.rerun()
                    except Exception as exc:st.error(f'No pudo registrarse: {exc}')
                if len(contactos):
                    hist=contactos[(contactos.cliente==codigo)&(contactos.negocio==neg)].sort_values('fecha',ascending=False)
                    if len(hist):
                        st.markdown('**Historial de contactos**')
                        st.dataframe(hist[['fecha','tipo','actor','resultado','observacion','evidencia']],hide_index=True,use_container_width=True)

with respuestas:
    st.subheader('Respuestas BEES Force · Distribuidora del Valle')
    st.caption('Solo DDV (70549) y clientes con promotor asignado. '
               'Esta pestaña tiene filtros propios: el filtro lateral de CZA no oculta NABs.')
    meses_force=sorted(force['mes'].dropna().astype(str).unique(),reverse=True)
    f1,f2=st.columns(2)
    mes_force=f1.selectbox('Período de respuestas',['Todos los meses']+meses_force,
                           index=0,key='mes_solo_force')
    negocio_force=f2.selectbox('Negocio en Force',['Todos']+sorted(force['negocio'].dropna().astype(str).unique()),
                               key='negocio_solo_force')
    fview=force.copy()
    if mes_force!='Todos los meses':fview=fview[fview.mes==mes_force]
    if negocio_force!='Todos':fview=fview[fview.negocio==negocio_force]
    # Los registros Force se conservan íntegros en 'Todos'. Si el usuario filtra
    # CZA en esta pestaña, también se aplica la licencia para mantener el mismo
    # universo operativo; NABs/UNG no usa esa restricción.
    if negocio_force=='CZA':
        codigos_con_licencia=set(clientes.loc[tiene_licencia_alcohol(clientes),'cliente'].astype(str))
        fview=fview.loc[fview['cliente'].astype(str).isin(codigos_con_licencia)]
    if promotor!='Todos':
        asignados=set(clientes.loc[clientes.promotor.astype(str)==promotor,'cliente'].astype(str))
        fview=fview[fview.cliente.astype(str).isin(asignados)]
    if localidad!='Todos':
        asignados=set(clientes.loc[clientes.localidad.astype(str)==localidad,'cliente'].astype(str))
        fview=fview[fview.cliente.astype(str).isin(asignados)]
    if buscar:
        t=buscar.strip().lower()
        codigos=set(clientes.loc[
            clientes.cliente.astype(str).str.contains(t,regex=False) |
            clientes.fantasia.astype(str).str.lower().str.contains(t,regex=False) |
            clientes.razon_social.astype(str).str.lower().str.contains(t,regex=False),
            'cliente'].astype(str))
        fview=fview[fview.cliente.astype(str).isin(codigos)]
    m1,m2,m3,m4=st.columns(4)
    m1.metric('Encuestas de DDV · filtros Force',len(fview))
    m2.metric('Clientes únicos',int(fview.cliente.nunique()))
    m3.metric('CZA (Beer)',int((fview.negocio=='CZA').sum()))
    m4.metric('NABs',int((fview.negocio=='NABS').sum()))
    if fview.empty:
        st.info('No hay respuestas de Force para los filtros elegidos.')
    else:
        st.caption('Cada fila es una ENCUESTA, no una pregunta. '
                   'Las respuestas de varias preguntas se muestran agrupadas en el detalle.')
        ver=fview[['mes','fecha','cliente','negocio','motivo_principal','detalle',
                   'estado_force','bdr_id','preguntas']].sort_values(['mes','fecha'],ascending=False).copy()
        ver.columns=['Mes','Fecha','Código','Negocio','Motivo principal',
                     'Respuestas adicionales','Estado tarea','BDR','Preguntas']
        st.dataframe(ver,use_container_width=True,hide_index=True,height=480)
        st.download_button('Exportar respuestas Force',ver.to_csv(index=False,sep=';').encode('utf-8-sig'),
                           file_name=f'force_ddv_{mes_force.replace(" ","_")}.csv',mime='text/csv')
    st.caption('La fuente de febrero contiene estado FINISHED/JUSTIFIED; '
               'marzo–octubre contiene las respuestas pero no certifica validación.')

with auditoria:
    st.subheader('Control de cumplimiento · manual 2.1.2.5')
    alcance=alcance_filtros[alcance_filtros['cnc_u3m'] & alcance_filtros['negocio'].isin(['CZA','NABS'])]
    total=len(alcance)
    con_motivo=int((alcance.motivo_force.str.strip()!='').sum())
    b1,b2,b3=st.columns(3)
    b1.metric('CNC U3M CZA/NABS',total)
    b2.metric('Con motivo relevado en Force · mes',f'{con_motivo}/{total}' if total else '0/0')
    b3.metric('Con plan de acción',int(alcance.accion.str.strip().ne('').sum()))
    st.caption('Cruce entre cartera CNC y encuestas Force del mes seleccionado. No equivale a una calificación oficial: se requiere revisar completadas/validadas, visitas y planes.')
    st.markdown('**Frecuencia de CNC U12M**')
    u12=alcance_filtros[alcance_filtros.cnc_u12m]
    if len(u12):
        f=u12.groupby('frecuencia_contacto',as_index=False).agg(casos=('cliente','count'),contactos_exigidos=('contactos_requeridos','sum'),contactos_registrados=('contactos_mes','sum'),casos_al_dia=('cumple_contacto','sum'),casos_pendientes=('contacto_pendiente','sum'))
        st.dataframe(f,use_container_width=True,hide_index=True)
        st.caption('Contacto válido: visita, llamado o WhatsApp con resultado diferente de Sin contacto. Se cuentan gestiones documentadas del mes, no tareas BEES Force por sí solas.')
    else:st.caption('No hay CNC U12M verificables para este período.')
    st.markdown('**Controles de calidad del cruce**')
    checks=pd.DataFrame([
      {'Control':'Clientes del maestro completo','Valor':total_clientes_fuente,'Estado':'Fuente'},
      {'Control':'Excluidos por no tener promotor asignado','Valor':clientes_excluidos_sin_promotor,'Estado':'Excluidos del cálculo'},
      {'Control':'Clientes con promotor en padrón','Valor':len(clientes),'Estado':'OK'},
      {'Control':'Altas y bajas aplicadas al cierre','Valor':meta['activos'],'Estado':'OK'},
      {'Control':'Clientes activos sin antigüedad U3M','Valor':int(casos.loc[~casos['antiguedad_u3m'],'cliente'].nunique()),'Estado':'No se clasifican CNC'},
      {'Control':'Clientes activos sin antigüedad U12M','Valor':int(casos.loc[~casos['antiguedad_u12m'],'cliente'].nunique()),'Estado':'No se clasifican CNC'},
      {'Control':'Fechas de baja no informadas en anulados','Valor':int(((clientes.anulado=='SI') & clientes.fecha_baja.isna()).sum()),'Estado':'Revisar si >0'},
      {'Control':'Diferencia entre estado maestro y fuerza de ventas','Valor':int(clientes['auditoria_estado_diferente'].astype(str).str.lower().isin(['true','1']).sum()),'Estado':'Revisar diferencias'},
      {'Control':'Ventana U3M completa','Valor':str(meta['u3_completo']),'Estado':'OK' if meta['u3_completo'] else 'Parcial'},
      {'Control':'Ventana U12M completa','Valor':str(meta['u12_completo']),'Estado':'OK' if meta['u12_completo'] else 'Parcial'},
      {'Control':'Negocios sin clasificar','Valor':', '.join(meta['sin_mapeo']) or 'Ninguno','Estado':'Revisar equivalencias'},
      {'Control':'MATCH','Valor':'Sin mapeo confirmado','Estado':'Pendiente'},
      {'Control':'BEES Force - meses cargados','Valor':str(force.mes.nunique()) if len(force) else '0','Estado':'Fuente histórica local'},
       {'Control':'Force de otros distribuidores','Valor':'Filtrados por ID 70549 + BDR','Estado':'OK'}
    ])
    st.dataframe(checks,use_container_width=True,hide_index=True)
    if LOCAL_MODE:
        from almacen_local import exportar_todo_csv
        st.download_button('Descargar respaldo de planes y contactos (ZIP)',exportar_todo_csv(DB_LOCAL),
            file_name=f'CNC_gestiones_respaldo_{date.today().isoformat()}.zip',mime='application/zip')
    st.markdown('**Metodología**')
    st.caption('Criterio histórico 3M (visible en Cartera y CNC): meses calendario inclusivos (ej. julio 2025 = mayo, junio, julio). El universo de vigencia conserva a clientes activos en CUALQUIER día del período, aunque hayan sido anulados antes del mes seleccionado. Cada mes muestra Vigente, Baja con fecha, Aún sin alta o Baja anterior. Solo los vigentes al último día cuentan en activos al cierre; las bajas se muestran por separado.')
    st.caption('Activo al cierre si Alta fecha <= último día del mes y Anulado fecha > último día del mes (o actualmente activo). '
               'CNC U3M/U6M/U12M requiere que el alta sea anterior o igual al primer día de la ventana completa '
               'de 3/6/12 meses calendario. Las altas posteriores no son CNC aunque no hayan comprado ese negocio. '
               'Las ventas se consolidan por mes, cliente y unidad con importe neto mensual positivo; '
               'ventas negativas netas no cuentan como compra. U12M es subconjunto de U3M. '
               'Los cierres incompletos se identifican; los cambios históricos de promotores no pueden '
               'reconstruirse con el padrón actual.')
    st.caption('Filtros comerciales: CZA exige Licencia alcohol = SI; UNG/NABs, Aguas y Marketplace no restringen por licencia. '
               'Supervisor: estructura comercial 2026, con Bruno Ismael y Hernán Casco disponibles para filtrar; '
               'el grupo de Aníbal Viti permanece dentro de Todos. '
               'La licencia y la estructura no tienen reconstrucción histórica mensual: se aplican las del padrón disponible. '
               'Se excluyen promotores vacíos, SIN PREVENTA y VENDEDOR LIBRE.')
    st.caption('Origen: venta 2025.xlsx (mayo-diciembre 2025), venta anual.txt (enero-mayo 2026), ventas mensuales de junio a octubre 2026 y ventadiaria.txt (noviembre en curso). Sin duplicar ventanas superpuestas.')


with seguimiento:
    st.subheader('Alertas de relevamiento CNC por promotor')
    promotores_link=os.environ.get('PROMOTORES_URL') or secrets_opt('PROMOTORES_URL','http://localhost:8520' if LOCAL_MODE else '')
    if promotores_link:
        st.link_button('Abrir la app de relevamiento de promotores',promotores_link)
    st.caption('Las respuestas se leen de la misma base que utiliza la app móvil. '
               'Al registrar un motivo, el cliente deja de figurar como pendiente. '
               'La pantalla verifica cambios cada 30 segundos; también podés actualizarla manualmente.')
    panel_relevamiento(mes,supervisor,promotor,negocio_etiqueta)
    if st.button('↻ Actualizar respuestas ahora',key='refresh_relevamientos'):
        st.rerun()
    with st.expander('Administrar campaña del período seleccionado'):
        st.caption('Generá la cartera de promotores desde el mismo motor CNC. '
                   'Solo U3M de CZA con licencia SI y UNG completo, activos al cierre, '
                   'con promotor y antigüedad suficiente. Para evitar sobrescribir '
                   'la campaña de todo el equipo desde un filtro parcial, el botón '
                   'siempre toma la cartera general del período.')
        if not meta['u3_completo']:
            st.error('No se puede crear campaña: faltan meses de ventas para U3M.')
        elif relev_db is None:
            st.error('Primero configurá la base compartida.')
        else:
            if st.button('Calcular y revisar campaña del mes',key='preparar_campana'):
                try:
                    completos,_=generar_casos(clientes_base_para_campana,ventas,mes,set(meses),mapeo)
                    nuevos=validar_sincronizacion(completos,mes)
                    st.session_state['campana_preparada']={'mes':mes,'registros':nuevos}
                except Exception as ex:
                    st.error(f'No fue posible preparar la campaña: {ex}')
            info_camp=st.session_state.get('campana_preparada')
            if info_camp and info_camp['mes']==mes:
                nuevos=info_camp['registros']
                st.info(f'Campaña calculada: {len(nuevos)} casos CZA/UNG, '
                        f'{len(set(r["cliente"] for r in nuevos))} clientes únicos. '
                        f'La base ya tiene {len(relev_db.campaign(mes)) if mes in relev_db.periods() else 0} casos en este mes.')
                confirm=st.checkbox('Confirmo actualizar la cartera de TODO el equipo para este mes. '
                                     'Las respuestas existentes de clientes que permanecen se conservan.',
                                    key=f'confirmar_campana_{mes}')
                if st.button('Actualizar campaña compartida',disabled=not confirm,
                             key='actualizar_campana_confirmada',type='primary'):
                    try:
                        relev_db.seed(nuevos,replace_period=True)
                        st.session_state.pop('campana_preparada',None)
                        st.success('Campaña actualizada en la base compartida.')
                        st.rerun()
                    except Exception as ex:
                        st.error(f'Error de actualización: {ex}')
