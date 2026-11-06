"""Cierres CNC DDV: ventas cerradas, padrón activo y bajas inferidas por mes.

No confunde ausencia en el padrón con una fecha oficial de anulación.
Los cierres se archivan como snapshots independientes; nunca editan los anteriores.
"""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import json
import pandas as pd

from logica import normalizar_id, fecha_fin
from parser_actual import consolidar_actual

ACTIVOS_REQUERIDOS = {
    'Cliente','Razon social','Nombre de fantasia','Alta fecha',
    'Anulado','Licencia alcohol','Fuerza de venta 1 Descripcion personal comercial',
}


def detectar_ventas_cierre(archivos: list[dict], mes: str) -> dict|None:
    """Solo archivos cuyo nombre identifica el mes, no ventadiaria.txt en curso."""
    meses = ['enero','febrero','marzo','abril','mayo','junio','julio',
             'agosto','septiembre','octubre','noviembre','diciembre']
    nombre_mes=meses[int(mes[-2:])-1]
    candidatos=[]
    for f in archivos:
        nom=f.get('name', '').casefold().strip()
        if not nom.endswith(('.txt','.tsv')):
            continue
        if any(x in nom for x in ('bultos','anual','combos','backup','copia')):
            continue
        # Ej.: ventadiaria noviembre.txt, venta noviembre.txt, ventadiaria_noviembre_2026.txt.
        if not (nom.startswith('ventadiaria') or nom.startswith('venta ')):
            continue
        if nombre_mes not in nom:
            continue
        if ('20' in nom) and mes[:4] not in nom:
            continue
        candidatos.append(f)
    return max(candidatos, key=lambda r:r.get('modifiedTime','')) if candidatos else None


def comprobar_reporte_al_cierre(modificado_iso:str, mes:str, permitir_fecha_anticipada=False)->bool:
    """Verifica modificación en o después del comienzo del mes siguiente.

    Un reporte modificado el 26/10 no sirve para cerrar octubre; un archivo
    sin fecha tampoco. La confirmación manual debe ser explícita.
    """
    if permitir_fecha_anticipada:
        return bool(modificado_iso)
    from zoneinfo import ZoneInfo
    try:
        fecha=datetime.fromisoformat(modificado_iso.replace('Z','+00:00'))
        if fecha.tzinfo is None:return False
        ultimo=fecha_fin(mes).date()
        return fecha.astimezone(ZoneInfo('America/Argentina/Buenos_Aires')).date()>ultimo
    except (ValueError,TypeError):
        return False


def procesar_ventas_mes(raw:bytes, mes:str)->pd.DataFrame:
    """Una fila por mes, cliente y unidad, reemplazando el mes antiguo entero."""
    resumen=consolidar_actual(raw,mes)
    resumen=resumen.loc[resumen.mes.eq(mes)].copy()
    if resumen.empty:
        raise ValueError(f'El archivo de ventas no tiene datos del mes {mes}.')
    resumen['cliente']=normalizar_id(resumen['cliente'])
    resumen['unidad']=resumen['unidad'].astype(str).str.strip().str.upper().replace({'':'SIN IDENTIFICAR'})
    resumen['neto']=pd.to_numeric(resumen['neto'],errors='coerce').fillna(0)
    return resumen.groupby(['mes','cliente','unidad'],as_index=False)['neto'].sum()


def integrar_ventas(ventas_anteriores:pd.DataFrame,ventas_mes:pd.DataFrame,mes:str)->pd.DataFrame:
    a=ventas_anteriores.copy()
    a=a.loc[a.mes.ne(mes)]
    nueva=pd.concat([a,ventas_mes],ignore_index=True)
    nueva['cliente']=normalizar_id(nueva['cliente'])
    nueva['neto']=pd.to_numeric(nueva['neto'],errors='coerce').fillna(0)
    return nueva.groupby(['mes','cliente','unidad'],as_index=False)['neto'].sum()


def preparar_reporte_activo(reporte:pd.DataFrame)->pd.DataFrame:
    faltantes=ACTIVOS_REQUERIDOS-set(reporte.columns)
    if faltantes:
        raise ValueError('El reporte de clientes cambió de estructura: '+', '.join(sorted(faltantes)))
    r=reporte.copy()
    r['cliente']=normalizar_id(r['Cliente'].astype('string'))
    r=r.loc[~r.cliente.isin(['0',''])].drop_duplicates('cliente',keep='last')
    r['Anulado']=r['Anulado'].fillna('').astype(str).str.upper().str.strip()
    # Un archivo denominado clientes activos no puede contener anomalías silenciosas.
    no_activos=r.loc[~r.Anulado.eq('NO')]
    if len(no_activos):
        raise ValueError(f'El reporte de activos incluye {len(no_activos)} clientes anulados o sin estado NO.')
    if r.empty:
        raise ValueError('El reporte de clientes activos está vacío.')
    return r


def integracion_cierre_clientes(maestro:pd.DataFrame, activos:pd.DataFrame, mes:str,
                                mapa_supervisores:dict|None=None)->tuple[pd.DataFrame,dict]:
    """Conserva el maestro completo y detecta bajas comparando cierre vs cierre.

    'baja_inferida_mes' declara el MES de detección, nunca una fecha inventada.
    """
    r=preparar_reporte_activo(activos)
    maestro=maestro.copy()
    maestro['cliente']=normalizar_id(maestro['cliente'])
    maestro=maestro.drop_duplicates('cliente',keep='last').set_index('cliente',drop=False)
    if 'baja_inferida_mes' not in maestro:
        maestro['baja_inferida_mes']=''
    if 'fecha_baja_origen' not in maestro:
        maestro['fecha_baja_origen']=''
    for f in ('baja_inferida_mes','fecha_baja_origen'):
        maestro[f]=maestro[f].fillna('').astype(str)
    r=r.set_index('cliente',drop=False)
    estado=maestro['anulado'].fillna('').astype(str).str.strip().str.upper()
    actuales=set(r.index)
    prev_activos=set(maestro.index[estado.eq('NO')])
    bajas=prev_activos-actuales
    # La inferencia conserva el período histórico, pero no pretende saber el día exacto.
    if bajas:
        maestro.loc[list(bajas),'anulado']='SI'
        maestro.loc[list(bajas),'baja_inferida_mes']=mes
        maestro.loc[list(bajas),'fecha_baja_origen']='ausente_reporte_activos'
        maestro.loc[list(bajas),'fecha_baja']=''
    reingresos=[]
    nuevos=[]
    cols={
        'Razon social':'razon_social',
        'Nombre de fantasia':'fantasia',
        'Alta fecha':'alta',
        'Licencia alcohol':'licencia_alcohol',
        'Fuerza de venta 1 Descripcion personal comercial':'promotor',
        'Fuerza de venta 1 Ruta de venta':'ruta',
        'Fuerza de venta 1 Dias de visita':'dias_visita',
        'Domicilio':'domicilio',
        'Telefonos':'telefono',
        'Descripcion localidad':'localidad',
        'Descripcion subcanal':'subcanal',
    }
    # Si el repositorio no contiene el mapa comercial, recuperar las asignaciones
    # conocidas del maestro anterior; nunca borrar supervisores existentes.
    if not mapa_supervisores:
        import re,unicodedata
        def k_super(s):
            txt=unicodedata.normalize('NFKD',str(s or '').upper())
            txt=''.join(c for c in txt if not unicodedata.combining(c))
            return ' '.join(sorted(re.sub('[^A-Z ]',' ',txt).split()))
        mapa_supervisores={k_super(row.get('promotor','')):str(row.get('supervisor_asignado','')).strip()
                           for _,row in maestro.iterrows() if str(row.get('supervisor_asignado','')).strip()
                           and str(row.get('promotor','')).strip()}
    for id_,f in r.iterrows():
        is_new=id_ not in maestro.index
        if is_new:
            nuevos.append(id_)
            maestro.loc[id_, 'cliente']=id_
        elif str(maestro.at[id_,'anulado']).strip().upper()=='SI':
            reingresos.append(id_)
        for origen,destino in cols.items():
            if origen not in r.columns:continue
            val=f.get(origen)
            if pd.isna(val):continue
            if destino=='alta':
                if isinstance(val,(int,float)) and 20000 < float(val) < 80000:
                    val=pd.Timestamp('1899-12-30') + pd.to_timedelta(int(val),unit='D')
                val=pd.to_datetime(val,errors='coerce')
                if pd.isna(val):continue
                val=val.strftime('%Y-%m-%d')
            elif destino in ('telefono','ruta','dias_visita'):
                val=str(val).strip()
            else:
                val=str(val).strip()
            maestro.loc[id_,destino]=val
        maestro.loc[id_,'anulado']='NO'
        maestro.loc[id_,'baja_inferida_mes']=''
        maestro.loc[id_,'fecha_baja_origen']=''
        maestro.loc[id_,'fecha_baja']=''
        maestro.loc[id_,'anulado_fuerza']='NO'
        maestro.loc[id_,'fecha_baja_fuerza']=''
        promotor=str(maestro.at[id_,'promotor'])
        if mapa_supervisores:
            # El mapa normalizado se carga desde el archivo de estructura existente.
            import re,unicodedata
            def clave(s):
                txt=unicodedata.normalize('NFKD',s.upper())
                txt=''.join(c for c in txt if not unicodedata.combining(c))
                return ' '.join(sorted(re.sub(r'[^A-Z ]',' ',txt).split()))
            maestro.loc[id_,'supervisor_asignado']=mapa_supervisores.get(clave(promotor),
                str(maestro.at[id_,'supervisor_asignado']) if pd.notna(maestro.at[id_,'supervisor_asignado']) else '')
    maestro=maestro.reset_index(drop=True)
    # Campos retenidos del padrón original si no aparecen en el reporte nuevo.
    stats={'periodo':mes,'activos_reporte':len(r),'bajas_detectadas':len(bajas),
           'altas_nuevas':len(nuevos),'reingresos':len(reingresos),
           'bajas_sin_fecha_exacta':len(bajas),
           'observacion':'La ausencia del reporte identifica el mes de baja, NO el día exacto.'}
    return maestro,stats


def leer_index(raw:bytes|str|None)->dict:
    if raw is None:return {'version':1,'cierres':{}}
    d=json.loads(raw.decode('utf-8') if isinstance(raw,bytes) else raw)
    if not isinstance(d,dict) or not isinstance(d.get('cierres',{}),dict):
        raise ValueError('El índice de cierres no tiene formato válido.')
    d.setdefault('version',1)
    d.setdefault('cierres',{})
    return d


def serializar_csv_gz(df:pd.DataFrame)->bytes:
    from gzip import compress
    return compress(df.to_csv(index=False).encode('utf-8'),compresslevel=6,mtime=0)
