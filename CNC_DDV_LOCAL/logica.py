"""Motor auditable de cartera CNC; no requiere Streamlit."""
from __future__ import annotations
import calendar,json
from pathlib import Path
import pandas as pd

NEGOCIOS=['CZA','NABS','MATCH','AGUAS','MARKETPLACE']
UNIDADES_POR_DEFECTO={
 'CERVEZAS CMQ':'CZA',
 'UNG':'NABS', # Provisorio: validar si MATCH está dentro del catálogo UNG.
 'AGUAS ECO':'AGUAS',
 'MARKETPLACE ALIMENTOS':'MARKETPLACE',
 'MARKETPLACE (BEES)':'MARKETPLACE',
}
MAPEO_NO_VALIDADO=['NABS','MATCH']

# Estos valores no identifican a una persona responsable de la cartera.
PROMOTORES_NO_ASIGNADOS = {'', 'SIN PREVENTA', 'VENDEDOR LIBRE', 'SIN ASIGNAR',
                           'NO ASIGNADO', 'N/A', 'NA', '-', '0', 'NONE', 'NAN'}

def tiene_licencia_alcohol(clientes):
    """Licencia declarada SI en padrón (el dato NO es histórico)."""
    if 'licencia_alcohol' not in clientes.columns:
        raise KeyError('Falta licencia_alcohol en clientes: reprocesar el maestro antes de calcular CZA.')
    return clientes['licencia_alcohol'].astype('string').fillna('').str.strip().str.upper().eq('SI').fillna(False)


def tiene_promotor_asignado(clientes):
    """Máscara común de elegibilidad comercial para histórico, CNC y Force.

    No filtrar exclusivamente la ruta 9999: existen clientes con promotor vacío
    y otras rutas (por ejemplo 999).
    """
    if 'promotor' not in clientes.columns:
        raise KeyError('El maestro de clientes no tiene la columna promotor')
    p = clientes['promotor'].astype('string').fillna('').str.strip().str.upper()
    return ~p.isin(PROMOTORES_NO_ASIGNADOS)



def normalizar_id(serie):
    return serie.astype('string').str.strip().str.replace(r'\.0$','',regex=True).str.lstrip('0').replace('', '0')


def fecha_fin(mes):
    y,m=map(int,mes.split('-'));return pd.Timestamp(y,m,calendar.monthrange(y,m)[1])


def mes_anterior(mes,restar):
    return (pd.Period(mes,freq='M')-restar).strftime('%Y-%m')


def meses_ventana(mes,n):
    return [(pd.Period(mes,freq='M')-i).strftime('%Y-%m') for i in range(n)]


def cumple_antiguedad_cnc(altas, mes, meses):
    """Requiere alta desde el inicio de TODOS los meses de la ventana.

    Ejemplo: cierre octubre/2026, U3M = agosto, septiembre y octubre.
    Un alta del 17/09/2026 NO es elegible U3M aunque nunca haya comprado
    un negocio; un alta del 01/08/2026 sí estuvo habilitada en los
    tres meses calendario.
    """
    if meses not in (3, 6, 12):
        raise ValueError('El horizonte debe ser 3, 6 o 12 meses')
    inicio = pd.Timestamp(f"{mes_anterior(mes, meses - 1)}-01")
    fechas = pd.to_datetime(altas, errors='coerce')
    return fechas.notna() & fechas.le(inicio)


def cargar_clientes(ruta):
    df=pd.read_csv(ruta,compression='gzip',dtype={'cliente':'string'},keep_default_na=False)
    df['cliente']=normalizar_id(df['cliente'])
    for f in ['alta','fecha_baja','fecha_baja_fuerza']:
        df[f]=pd.to_datetime(df[f],errors='coerce')
    return df.drop_duplicates('cliente',keep='last')


def cargar_ventas(ruta):
    df=pd.read_csv(ruta,compression='gzip',dtype={'cliente':'string','mes':'string'},keep_default_na=False)
    df['cliente']=normalizar_id(df['cliente'])
    df['neto']=pd.to_numeric(df['neto'],errors='coerce').fillna(0)
    return df


def cartera_al_cierre(clientes,mes):
    fin=fecha_fin(mes)
    # La fecha de baja de la ficha maestra manda; NO equivale a fecha de descarga.
    # Quien se dio de baja durante el mes no figura activo AL CIERRE.
    asignado=tiene_promotor_asignado(clientes)
    # Para un cliente ausente del padrón ACTIVO de un cierre posterior,
    # conocemos el mes de detección de la baja, no el día. En cierres
    # ANTERIORES sigue vigente; desde ese mes ya no cuenta como activo.
    mes_baja=clientes.get('baja_inferida_mes',pd.Series('',index=clientes.index))
    mes_baja=mes_baja.astype('string').fillna('').str.strip()
    activos=(asignado & clientes['alta'].notna() & (clientes['alta']<=fin) & (
        (clientes['anulado'].str.upper()=='NO') |
        ((clientes['anulado'].str.upper()=='SI') & (
            ((clientes['fecha_baja'].notna()) & (clientes['fecha_baja']>fin)) |
            (mes_baja.ne('') & mes_baja.gt(mes))
        ))))
    return clientes.loc[activos].copy()


def preparar_ventas(ventas,mapeo=None):
    mapeo=mapeo or UNIDADES_POR_DEFECTO
    v=ventas.copy()
    v['negocio']=v['unidad'].astype(str).str.upper().str.strip().map(mapeo)
    v=v.loc[v['negocio'].isin(NEGOCIOS)].copy()
    # Sumar por mes, cliente y negocio antes de evaluar compra: devoluciones
    # pueden anular o superar importes positivos de otros renglones.
    v=v.groupby(['mes','cliente','negocio'],as_index=False)['neto'].sum()
    return v[v['neto']>0]


def generar_casos(clientes,ventas,mes,cobertura,mapeo=None):
    """Genera universo por cliente/negocio, excluyendo no verificables.
    U12M está contenido en U3M; las dos métricas no se suman.
    """
    activos=cartera_al_cierre(clientes,mes)
    mapeo=mapeo or UNIDADES_POR_DEFECTO
    habilitados=sorted({v for v in mapeo.values() if v in NEGOCIOS})
    if not habilitados:
        return pd.DataFrame(),{'activos':len(activos),'disponibles':[],'u3_completo':False,'u12_completo':False}
    mensual=preparar_ventas(ventas[ventas['mes']<=mes],mapeo)
    # Solo categorías con correspondencia documentada; MATCH queda sin inventar.
    a=activos.assign(_k=1).merge(pd.DataFrame({'negocio':habilitados,'_k':1}),on='_k').drop(columns='_k')
    # Restricción exclusiva de CZA: solo clientes con licencia alcohol SI.
    # UNG/NABs, Aguas y Marketplace conservan a toda la cartera elegible.
    if 'CZA' in habilitados:
        a=a.loc[(a['negocio']!='CZA') | tiene_licencia_alcohol(a)].copy()
    ult=mensual.groupby(['cliente','negocio'],as_index=False)['mes'].max().rename(columns={'mes':'ultima_compra'})
    a=a.merge(ult,on=['cliente','negocio'],how='left')
    fecha_ult=pd.to_datetime(a['ultima_compra'],format='%Y-%m',errors='coerce')
    umbral3=pd.Timestamp(mes_anterior(mes,2)+'-01')
    umbral12=pd.Timestamp(mes_anterior(mes,11)+'-01')
    completos3=all(k in cobertura for k in meses_ventana(mes,3))
    completos12=all(k in cobertura for k in meses_ventana(mes,12))
    # No confundir "sin compra" con "sin compra hace N meses": un alta
    # reciente no tuvo oportunidad de comprar durante TODA la ventana.
    a['antiguedad_u3m']=cumple_antiguedad_cnc(a['alta'], mes, 3)
    a['antiguedad_u12m']=cumple_antiguedad_cnc(a['alta'], mes, 12)
    a['cnc_u3m']=completos3 & a['antiguedad_u3m'] & (fecha_ult.isna() | (fecha_ult<umbral3))
    a['cnc_u12m']=completos12 & a['antiguedad_u12m'] & (fecha_ult.isna() | (fecha_ult<umbral12))
    a['clasificacion']='Con compra U3M'
    a.loc[completos3 & ~a['antiguedad_u3m'] &
          (fecha_ult.isna() | (fecha_ult<umbral3)), 'clasificacion']='Alta reciente · aún no U3M'
    a.loc[a['cnc_u3m'],'clasificacion']='CNC U3M'
    a.loc[a['cnc_u12m'],'clasificacion']='CNC U12M'
    if not completos3:a['clasificacion']='Historial U3M incompleto'
    # U12 incompleto no invalida U3 confirmado.
    a['u12m_verificable']=completos12
    a['u3m_verificable']=completos3
    result={'activos':len(activos),'disponibles':habilitados,'u3_completo':completos3,
            'u12_completo':completos12,'meses_faltantes_u3':[x for x in meses_ventana(mes,3) if x not in cobertura],
            'meses_faltantes_u12':[x for x in meses_ventana(mes,12) if x not in cobertura],
            'sin_mapeo':sorted(set(ventas.unidad.unique())-set(mapeo)),
            'clasificacion_provisoria':['NABS: UNG puede incluir subsegmentos que requieren validar','MATCH: sin equivalencia verificada en ventas']}
    return a,result


def siguiente_contacto(ultima_gestion,fecha_alta_plan,oportunidad=False):
    dias=15 if oportunidad else 30
    origen=pd.to_datetime(ultima_gestion,errors='coerce')
    if pd.isna(origen): origen=pd.to_datetime(fecha_alta_plan,errors='coerce')
    return (origen+pd.Timedelta(days=dias)).date() if not pd.isna(origen) else None


def control_contactos_u12m(casos, contactos, mes):
    """Control operativo mensual U12M; los formularios BEES no son visitas.

    Para una oportunidad censal desconocida mantiene meta mínima de 1
    y muestra que la validación de Censo está pendiente.
    """
    a=casos.copy()
    a['oportunidad_censo_bool']=a['oportunidad_censo'].astype(str).str.lower().isin(['si','sí','true','1'])
    a['censo_pendiente']=~a['oportunidad_censo'].astype(str).str.lower().isin(['si','sí','no','true','false','1','0'])
    a['frecuencia_contacto']='No aplica (no U12M)'
    a.loc[a['cnc_u12m'],'frecuencia_contacto']='Mensual (0,25)'
    a.loc[a['cnc_u12m'] & a['oportunidad_censo_bool'],'frecuencia_contacto']='Quincenal (0,50)'
    a.loc[a['cnc_u12m'] & a['censo_pendiente'],'frecuencia_contacto']='Censo pendiente · mínimo mensual'
    a['contactos_requeridos']=0
    a.loc[a['cnc_u12m'],'contactos_requeridos']=1
    a.loc[a['cnc_u12m'] & a['oportunidad_censo_bool'],'contactos_requeridos']=2
    a['contactos_mes']=0
    if not contactos.empty:
        con=contactos.copy()
        con['fecha_dt']=pd.to_datetime(con['fecha'],errors='coerce')
        desde_mes=pd.Timestamp(f'{mes}-01')
        hasta=fecha_fin(mes)
        tipos_contacto=['Visita promotor','Llamado supervisor','Visita supervisor','WhatsApp','Otro']
        validos=con.loc[con['fecha_dt'].between(desde_mes,hasta) & con['tipo'].isin(tipos_contacto) &
                       con['resultado'].ne('Sin contacto')]
        hechos=validos.groupby(['cliente','negocio']).size()
        a['contactos_mes']=a.set_index(['cliente','negocio']).index.map(hechos).fillna(0).astype(int)
    a['contacto_pendiente']=a['cnc_u12m'] & (a['contactos_mes']<a['contactos_requeridos'])
    a['cumple_contacto']=a['cnc_u12m'] & ~a['contacto_pendiente']
    return a


def cartera_vigencia_3m(clientes, mes):
    """Reconstruye el universo de clientes con vigencia EN ALGÚN DÍA de los
    tres meses calendarios terminados en ``mes``.

    Por ejemplo, mes=2025-07 comprende 01/05/2025 a 31/07/2025.
    Una baja de mayo/junio/julio no borra al cliente del histórico:
    se marca su fecha, pero NO cuenta como activo al cierre si la baja
    fue anterior o igual al último día de julio.

    Solo la fecha de alta y la baja del MAESTRO determinan vigencia;
    los campos de fuerza de ventas quedan como auditoría.
    """
    meses = list(reversed(meses_ventana(mes, 3)))
    inicio = pd.Timestamp(f'{meses[0]}-01')
    cierre = fecha_fin(mes)

    x = clientes.loc[tiene_promotor_asignado(clientes)].copy()
    x['cliente'] = normalizar_id(x['cliente'])
    x['_alta'] = pd.to_datetime(x['alta'], errors='coerce')
    x['_baja'] = pd.to_datetime(x['fecha_baja'], errors='coerce')
    # Fecha real cuando existe; si la baja solo se detectó por ausencia
    # de un reporte de activos, usar el cierre del mes SOLO para lógica.
    x['_baja_inferida_mes']=x.get('baja_inferida_mes',pd.Series('',index=x.index))
    x['_baja_inferida_mes']=x['_baja_inferida_mes'].astype('string').fillna('').str.strip()
    x['_baja_aprox']=pd.to_datetime(x['_baja_inferida_mes'].where(
        x['_baja_inferida_mes'].str.fullmatch(r'\d{4}-\d{2}')),errors='coerce')+pd.offsets.MonthEnd(0)
    x['_baja_logica']=x['_baja'].where(x['_baja'].notna(),x['_baja_aprox'])
    anulados = x['anulado'].astype('string').str.strip().str.upper().eq('SI').fillna(False)

    alta_valida = x['_alta'].notna() & x['_alta'].le(cierre)
    baja_conocida = x['_baja_logica'].notna()
    pudo_estar_vigente = alta_valida & (~anulados | (baja_conocida & x['_baja_logica'].ge(inicio)))
    x = x.loc[pudo_estar_vigente].copy()
    anulados = anulados.loc[x.index]
    x['baja_en_ventana'] = anulados & x['_baja_logica'].between(inicio,cierre,inclusive='both')
    x['vigente_cierre'] = ~anulados | x['_baja_logica'].gt(cierre)
    x['baja_meses_previos'] = x['baja_en_ventana'] & x['_baja_logica'].lt(pd.Timestamp(f'{mes}-01'))
    x['fecha_baja_ventana'] = x['_baja'].dt.strftime('%d/%m/%Y').where(x['baja_en_ventana'],'')
    inferida=x['baja_en_ventana'] & x['_baja'].isna() & x['_baja_inferida_mes'].ne('')
    x.loc[inferida,'fecha_baja_ventana']='Mes '+x.loc[inferida,'_baja_inferida_mes']+' (día sin confirmar)'
    x['alta_en_ventana'] = x['_alta'].between(inicio, cierre, inclusive='both')
    x['situacion'] = 'Vigente al cierre'
    x.loc[x['baja_en_ventana'], 'situacion'] = 'Baja durante los 3 meses'
    x['alerta'] = ''
    x.loc[x['baja_en_ventana'], 'alerta'] = (
        'BAJA: ' + x.loc[x['baja_en_ventana'], 'fecha_baja_ventana']
    )

    for periodo in meses:
        m_inicio = pd.Timestamp(f'{periodo}-01')
        m_fin = fecha_fin(periodo)
        col = f'estado_{periodo}'
        x[col] = '🟢 Vigente'
        x.loc[x['_alta'].gt(m_fin), col] = '— Aún sin alta'
        antes = anulados & x['_baja_logica'].lt(m_inicio)
        x.loc[antes, col] = '— Baja anterior'
        baja_en_mes = anulados & x['_baja_logica'].between(m_inicio, m_fin, inclusive='both')
        oficial=baja_en_mes & x['_baja'].notna()
        infer=baja_en_mes & x['_baja'].isna()
        x.loc[oficial, col] = '🔴 Baja ' + x.loc[oficial, '_baja'].dt.strftime('%d/%m/%Y')
        x.loc[infer, col] = '🔴 Baja detectada '+periodo+' (día sin confirmar)'

    cols_orden = [
        'cliente','fantasia','razon_social','localidad','promotor',
        'supervisor_asignado','licencia_alcohol','ruta',
        'alta','anulado','fecha_baja','vigente_cierre','baja_en_ventana',
        'baja_meses_previos','fecha_baja_ventana','alta_en_ventana','situacion',
        'alerta',
    ] + [f'estado_{p}' for p in meses]
    x = x[[c for c in cols_orden if c in x.columns]].sort_values(
        ['baja_en_ventana','cliente'], ascending=[False,True]
    ).reset_index(drop=True)
    datos = {
        'desde': inicio.strftime('%d/%m/%Y'),
        'hasta': cierre.strftime('%d/%m/%Y'),
        'meses': meses,
        'universo_3m': len(x),
        'vigentes_cierre': int(x['vigente_cierre'].sum()),
        'bajas_ventana': int(x['baja_en_ventana'].sum()),
        'bajas_previas': int(x['baja_meses_previos'].sum()),
        'altas_ventana': int(x['alta_en_ventana'].sum()),
        'anulados_sin_fecha': int((
            clientes.loc[tiene_promotor_asignado(clientes),'anulado'].astype('string').str.strip().str.upper().eq('SI').fillna(False)
            & pd.to_datetime(clientes.loc[tiene_promotor_asignado(clientes),'fecha_baja'], errors='coerce').isna()
        ).sum()),
    }
    return x, datos


def resumen_cnc_por_promotor(casos, mes, cobertura, horizonte):
    """Ranking de CNC al cierre para una ventana móvil de 3, 6 o 12 meses.

    `casos` es el universo cliente-negocio emitido por generar_casos y puede
    estar filtrado por negocio, promotor, localidad o búsqueda.
    Cuenta clientes únicos por promotor en la columna principal, sin sumar un
    mismo cliente varias veces si no compra en más de un negocio.
    `casos_cnc` sí conserva el grano cliente-negocio como segunda métrica.

    Devuelve un resumen no verificable si falta cualquier mes de cobertura.
    """
    if horizonte not in (3, 6, 12):
        raise ValueError("El horizonte debe ser 3, 6 o 12 meses")
    meses = list(reversed(meses_ventana(mes, horizonte)))
    faltantes = [m for m in meses if m not in cobertura]
    meta = {
        'horizonte': horizonte,
        'inicio': meses[0],
        'fin': mes,
        'faltantes': faltantes,
        'verificable': not faltantes,
    }
    columnas = ['promotor','clientes_activos','clientes_cnc','casos_cnc','porcentaje_cnc']
    if faltantes or casos.empty:
        return pd.DataFrame(columns=columnas), meta

    x = casos.loc[tiene_promotor_asignado(casos)].copy()
    if {'alta', 'anulado', 'fecha_baja'}.issubset(x.columns):
        x = cartera_al_cierre(x, mes)
    if x.empty:
        return pd.DataFrame(columns=columnas), meta

    # `ultima_compra` es el último mes con importe neto positivo, ya consolidado
    # por negocio; venta en cualquier mes de la ventana invalida la condición CNC.
    comienzo = pd.Timestamp(f'{meses[0]}-01')
    ultima = pd.to_datetime(x['ultima_compra'], errors='coerce', format='%Y-%m')
    x['antiguedad_suficiente'] = cumple_antiguedad_cnc(x['alta'], mes, horizonte)
    x['es_cnc'] = x['antiguedad_suficiente'] & (ultima.isna() | ultima.lt(comienzo))
    x['cliente'] = normalizar_id(x['cliente'])

    activos = x.groupby('promotor', dropna=False)['cliente'].nunique().rename('clientes_activos')
    cnc = x.loc[x['es_cnc']]
    unicos = cnc.groupby('promotor')['cliente'].nunique().rename('clientes_cnc')
    pares = cnc.groupby('promotor').size().rename('casos_cnc')

    resumen = activos.to_frame().join([unicos, pares]).fillna(0).reset_index()
    for col in ['clientes_activos', 'clientes_cnc', 'casos_cnc']:
        resumen[col] = resumen[col].astype(int)
    resumen['porcentaje_cnc'] = (
        resumen['clientes_cnc'] / resumen['clientes_activos']
        .replace({0: float('nan')}) * 100
    ).fillna(0).round(1)
    resumen = resumen.sort_values(
        ['clientes_cnc', 'casos_cnc', 'promotor'],
        ascending=[False, False, True]
    ).reset_index(drop=True)
    return resumen[columnas], meta
