"""Extrae campos mínimos del padrón, manteniendo altas/bajas históricas."""
import argparse,json,re,unicodedata
from pathlib import Path
import pandas as pd

COLS={
 'Cliente':'cliente','Razon social':'razon_social','Nombre de fantasia':'fantasia',
 'Alta fecha':'alta','Anulado':'anulado','Anulado fecha':'fecha_baja',
 'Fuerza de venta 1 Anulado':'anulado_fuerza','Fuerza de venta 1 Fecha de anulacion':'fecha_baja_fuerza',
 'Fuerza de venta 1 Descripcion personal comercial':'promotor',
 'Fuerza de venta 1 Ruta de venta':'ruta','Fuerza de venta 1 Dias de visita':'dias_visita',
 'Licencia alcohol':'licencia_alcohol',
 'Domicilio':'domicilio','Telefonos':'telefono', 'Descripcion localidad':'localidad','Descripcion subcanal':'subcanal',
}

def fecha(x):
    if pd.isna(x): return ''
    v=str(x).split(' ')[0]
    if v.startswith('9999'):return ''
    try: return pd.to_datetime(x,dayfirst=False,errors='coerce').date().isoformat()
    except (TypeError,OverflowError,ValueError):return ''


def nombre_clave(x):
    raw=unicodedata.normalize('NFKD',str(x or '').upper())
    texto=''.join(c for c in raw if not unicodedata.combining(c))
    return ' '.join(sorted(re.sub(r'[^A-Z ]',' ',texto).split()))


def mapa_supervisores(path):
    tabla=pd.read_csv(path,dtype=str).fillna('')
    return dict(zip(tabla['promotor_clave'].map(nombre_clave),tabla['supervisor'].str.strip().str.upper()))


def main():
    p=argparse.ArgumentParser();p.add_argument('--origen',required=True);p.add_argument('--destino',default='data/clientes.csv.gz')
    p.add_argument('--mapa-supervisores',
                   default=str(Path(__file__).resolve().parents[1]/'data/supervisores_estructura_2026.csv'))
    a=p.parse_args()
    df=pd.read_excel(a.origen,usecols=list(COLS),dtype={'Cliente':str})
    df=df.rename(columns=COLS)
    df['cliente']=df['cliente'].astype(str).str.replace(r'\.0$','',regex=True).str.lstrip('0').replace('', '0')
    for c in ['alta','fecha_baja','fecha_baja_fuerza']:df[c]=df[c].apply(fecha)
    for c in ['anulado','anulado_fuerza','licencia_alcohol']:
        df[c]=df[c].fillna('').astype(str).str.strip().str.upper()
    df['licencia_alcohol']=df['licencia_alcohol'].replace({'':'SIN DATO'})
    mapeo=mapa_supervisores(a.mapa_supervisores)
    df['supervisor_asignado']=df['promotor'].fillna('').map(
        lambda x:mapeo.get(nombre_clave(x),''))
    # En el maestro existen algunas rutas asignadas al propio supervisor.
    df.loc[df['promotor'].fillna('').str.strip().str.upper().eq('HERNAN CASCO'),'supervisor_asignado']='HERNAN CASCO'
    # Prioridad: estado y fecha del maestro de clientes, no estado de fuerza de venta.
    df['auditoria_estado_diferente']=df['anulado'].map({'SI':True,'NO':False}).ne(df['anulado_fuerza'].map({'YES':True,'NO':False}))
    target=Path(a.destino);target.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(target,index=False,compression='gzip')
    report={'clientes':len(df),'activos_hoy':int((df.anulado=='NO').sum()),'anulados_hoy':int((df.anulado=='SI').sum()),
            'inconsistencias_maestro_fuerza_venta':int(df.auditoria_estado_diferente.sum())}
    target.with_name('control_clientes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(report)
if __name__=='__main__':main()
