"""Consolida un cierre mensual de CNC desde el Drive de planificación de DDV.

La ejecución programada NO procesa el mes en curso. Requiere:
 - venta/ventadiaria MES.txt (nombre de mes explícito), cargado al final del mes
 - reporte de clientes.xlsx (solo activos), actualizado DESPUÉS del último día
 - carpeta de salida privada con clientes.csv.gz y ventas_resumen.csv.gz.

Conserva todos los snapshots de clientes y un índice, en vez de sobrescribir
el padrón histórico original. Nunca modifica reportes originales de la fuente.

Uso:
 python scripts/cerrar_mes_drive.py --origen ID_PLANIFICACION --destino ID_CNC_PRIVADOS \
  --credenciales /ruta/service-account.json

Solo con supervisión explícita:
 python scripts/cerrar_mes_drive.py ... --periodo 2026-11 --confirmar-reporte
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import datetime,date,timezone
from pathlib import Path

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload,MediaIoBaseUpload

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cierre_mensual import (
    comprobar_reporte_al_cierre, detectar_ventas_cierre, procesar_ventas_mes,
    integracion_cierre_clientes, integrar_ventas, leer_index, serializar_csv_gz,
)
from logica import normalizar_id

SCOPE=['https://www.googleapis.com/auth/drive']


def catalogo(api,folder_id):
    archivos=[];pagina=None
    while True:
        q=f"'{folder_id}' in parents and trashed = false"
        ret=api.files().list(q=q,fields='nextPageToken,files(id,name,mimeType,modifiedTime,size)',
                             pageSize=1000,pageToken=pagina,supportsAllDrives=True,
                             includeItemsFromAllDrives=True).execute()
        archivos.extend(ret.get('files',[]))
        pagina=ret.get('nextPageToken')
        if not pagina:break
    return archivos


def descargar(api,file_id):
    req=api.files().get_media(fileId=file_id,supportsAllDrives=True)
    buf=io.BytesIO();down=MediaIoBaseDownload(buf,req,chunksize=1024*1024)
    done=False
    while not done:
        _,done=down.next_chunk()
    return buf.getvalue()


def publicar(api,folder,nombre,contenido,mime='application/octet-stream',existing=None):
    media=MediaIoBaseUpload(io.BytesIO(contenido),mimetype=mime,resumable=False)
    if existing:
        res=api.files().update(fileId=existing,media_body=media,fields='id,name,modifiedTime',
                               supportsAllDrives=True).execute()
    else:
        res=api.files().create(body={'name':nombre,'parents':[folder]},media_body=media,
                               fields='id,name,modifiedTime',supportsAllDrives=True).execute()
    return res['id']


def mejor(archivos,nombre):
    encontrados=[a for a in archivos if a['name'].lower().strip()==nombre.lower()]
    return max(encontrados,key=lambda a:a.get('modifiedTime','')) if encontrados else None


def credenciales(args):
    info=None
    if args.credenciales:
        info=json.loads(Path(args.credenciales).read_text(encoding='utf-8'))
    elif os.environ.get('GCP_SERVICE_ACCOUNT_JSON'):
        info=json.loads(os.environ['GCP_SERVICE_ACCOUNT_JSON'])
    if not info:raise ValueError('Faltan credenciales de cuenta de servicio en archivo o GCP_SERVICE_ACCOUNT_JSON.')
    return service_account.Credentials.from_service_account_info(info,scopes=SCOPE)


def periodo_default():
    actual=pd.Period(datetime.now().strftime('%Y-%m'),freq='M')
    return str(actual-1)


def nombre_mapa(n):
    import re,unicodedata
    x=unicodedata.normalize('NFKD',str(n or '').upper())
    x=''.join(c for c in x if not unicodedata.combining(c))
    return ' '.join(sorted(re.sub('[^A-Z ]',' ',x).split()))


def mapa_supervisores(raiz):
    f=raiz/'data/supervisores_estructura_2026.csv'
    if not f.exists():return {}
    a=pd.read_csv(f,dtype='string').fillna('')
    return dict(zip(a['promotor_clave'].map(nombre_mapa),a['supervisor'].str.upper().str.strip()))


def cerrar(args):
    periodo=args.periodo or periodo_default()
    if pd.Period(periodo,freq='M')>=pd.Period(datetime.now().strftime('%Y-%m'),freq='M'):
        raise ValueError('Nunca se puede cerrar el mes corriente o uno futuro.')
    if periodo<'2026-11':
        raise ValueError('Cierres desde noviembre 2026; el historial anterior ya está consolidado.')
    api=build('drive','v3',credentials=credenciales(args),cache_discovery=False)
    origen=catalogo(api,args.origen)
    destino=catalogo(api,args.destino)
    sales=detectar_ventas_cierre(origen,periodo)
    report=mejor(origen,'reporte de clientes.xlsx')
    base_ventas=mejor(destino,'ventas_resumen.csv.gz')
    base_cliente=mejor(destino,'clientes.csv.gz')
    index_f=mejor(destino,'cierres_index.json')
    index=leer_index(descargar(api,index_f['id']) if index_f else None)
    if periodo in index['cierres']:
        print('Cierre ya registrado; se conserva sin reescribir:',periodo,flush=True)
        return {'status':'ya_cerrado','mes':periodo}
    if not index['cierres'] and periodo!='2026-11':
        print('CIERRE PENDIENTE: primero debe archivarse noviembre 2026; no saltar meses.',flush=True)
        return {'status':'pendiente','mes':periodo,'razon':'falta_primer_cierre_2026-11'}
    anteriores=[x for x in index['cierres'] if x<periodo]
    anterior=max(anteriores) if anteriores else None
    if anterior is not None and str(pd.Period(anterior,freq='M')+1)!=periodo:
        raise ValueError('Hay cierres mensuales intermedios sin procesar. No saltar meses.')
    if not all([sales,report,base_ventas,base_cliente]):
        faltan=[x for x,v in [('ventas nombradas por mes',sales),('reporte de clientes',report),
                               ('ventas_resumen.csv.gz privado',base_ventas),('clientes.csv.gz privado',base_cliente)] if v is None]
        print('CIERRE PENDIENTE: faltan '+', '.join(faltan),flush=True)
        return {'status':'pendiente','mes':periodo,'faltan':faltan}
    if not comprobar_reporte_al_cierre(report['modifiedTime'],periodo,args.confirmar_reporte):
        print(f"CIERRE PENDIENTE: reporte modificado el {report['modifiedTime']}; no acredita cierre {periodo}.",flush=True)
        return {'status':'pendiente','mes':periodo,'razon':'reporte_previo_al_cierre'}
    if not args.confirmar_reporte:
        # El padrón de un mes no puede extraerse de un reporte actualizado
        # meses después: el archivo reemplazable habría perdido el cierre.
        from zoneinfo import ZoneInfo
        fecha_rep=datetime.fromisoformat(report['modifiedTime'].replace('Z','+00:00'))
        fecha_local=fecha_rep.astimezone(ZoneInfo('America/Argentina/Buenos_Aires')).date()
        mes_siguiente=pd.Period(periodo,freq='M')+1
        if fecha_local.year!=mes_siguiente.year or fecha_local.month!=mes_siguiente.month or fecha_local.day>15:
            print('CIERRE PENDIENTE: reporte de activos no es de los primeros 15 días del mes siguiente.',flush=True)
            return {'status':'pendiente','mes':periodo,'razon':'reporte_fuera_de_ventana'}
        # Archivo de venta del mes debe estar cargado desde el último día del mes.
        from zoneinfo import ZoneInfo
        fc=datetime.fromisoformat(sales['modifiedTime'].replace('Z','+00:00'))
        if fc.astimezone(ZoneInfo('America/Argentina/Buenos_Aires')).date()<pd.Period(periodo).end_time.date():
            print(f"CIERRE PENDIENTE: ventas del mes actualizadas antes de finalizar {periodo}.",flush=True)
            return {'status':'pendiente','mes':periodo,'razon':'ventas_sin_cierre'}
    ventas=procesar_ventas_mes(descargar(api,sales['id']),periodo)
    lectura=pd.read_excel(io.BytesIO(descargar(api,report['id'])),dtype={'Cliente':'string'})
    # Si ya existe snapshot del cierre previo, usarlo para detectar exactamente
    # quién desapareció; nunca comparar únicamente contra el maestro original.
    if anterior is not None:
        prev_id=index['cierres'][anterior]['clientes_id']
        maestro=pd.read_csv(io.BytesIO(descargar(api,prev_id)),compression='gzip',
                            dtype={'cliente':'string'},keep_default_na=False)
    else:
        maestro=pd.read_csv(io.BytesIO(descargar(api,base_cliente['id'])),compression='gzip',
                            dtype={'cliente':'string'},keep_default_na=False)
    # Validación de cobertura: evitar marcar miles de bajas por un Excel parcial.
    anterior_activos=int(maestro['anulado'].astype(str).str.upper().eq('NO').sum())
    act_nuevos=int(lectura['Anulado'].fillna('').astype(str).str.strip().str.upper().eq('NO').sum())
    if anterior_activos and act_nuevos<anterior_activos*.7:
        raise ValueError(f'Padrón sospechoso: pasó de {anterior_activos} a {act_nuevos} activos. Se cancela sin tocar Drive.')
    clientes,stats=integracion_cierre_clientes(maestro,lectura,periodo,mapa_supervisores(Path(__file__).resolve().parents[1]))
    anteri_sales=pd.read_csv(io.BytesIO(descargar(api,base_ventas['id'])),compression='gzip',
                            dtype={'cliente':'string','mes':'string'},keep_default_na=False)
    # No publicar meses posteriores al cierre: el TXT del mes en curso no es válido.
    anteri_sales=anteri_sales[anteri_sales.mes.le(periodo)]
    ventas_total=integrar_ventas(anteri_sales,ventas,periodo)
    reporte={**stats,'archivo_ventas':sales['name'],'fecha_archivo_ventas':sales['modifiedTime'],
             'reporte_clientes':report['name'],'fecha_reporte_clientes':report['modifiedTime'],
             'filas_ventas_mes':len(ventas),'meses_ventas':sorted(ventas_total.mes.unique().tolist()),
             'creado_utc':datetime.now(timezone.utc).isoformat(timespec='seconds')}
    print(json.dumps(reporte,ensure_ascii=False,indent=2),flush=True)
    if args.simular:
        print('SIMULACIÓN: no se han modificado los archivos de Google Drive.',flush=True)
        return {'status':'simulacion','mes':periodo,'reporte':reporte}
    # Guardar instantáneas inmutables; el índice se actualiza al FINAL.
    nombre_cliente=f'clientes_cierre_{periodo}.csv.gz'
    nombre_ventas=f'ventas_cierre_{periodo}.csv.gz'
    cliente_id=publicar(api,args.destino,nombre_cliente,serializar_csv_gz(clientes),'application/gzip')
    venta_mes_id=publicar(api,args.destino,nombre_ventas,serializar_csv_gz(ventas),'application/gzip')
    # ventas_resumen.csv.gz se actualiza en el MISMO ID usado por Streamlit.
    publicar(api,args.destino,base_ventas['name'],serializar_csv_gz(ventas_total),
             'application/gzip',existing=base_ventas['id'])
    index['cierres'][periodo]={**reporte,'clientes_id':cliente_id,'ventas_mes_id':venta_mes_id,
        'ventas_resumen_id':base_ventas['id'],'venta_fuente_id':sales['id'],
        'reporte_fuente_id':report['id']}
    index_id=publicar(api,args.destino,'cierres_index.json',json.dumps(index,ensure_ascii=False,indent=2).encode('utf-8'),
                      'application/json',existing=index_f['id'] if index_f else None)
    print('CIERRE PUBLICADO',periodo,'cierres_index_id=',index_id,'ventas_resumen_id=',base_ventas['id'],flush=True)
    return {'status':'cerrado','mes':periodo,'index_id':index_id,'reporte':reporte}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--origen',required=True,help='ID carpeta planificacion Drive')
    p.add_argument('--destino',required=True,help='ID carpeta privada CNC')
    p.add_argument('--periodo',help='YYYY-MM, por defecto mes anterior')
    p.add_argument('--credenciales',help='Ruta JSON de cuenta servicio; alternativo GCP_SERVICE_ACCOUNT_JSON')
    p.add_argument('--confirmar-reporte',action='store_true',help='Usar solo si usuario verificó manualmente el cierre del padrón')
    p.add_argument('--simular',action='store_true',help='Validar sin guardar archivos')
    args=p.parse_args()
    cerrar(args)
if __name__=='__main__':main()
