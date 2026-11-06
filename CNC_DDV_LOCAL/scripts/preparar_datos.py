"""Consolida fuentes DDV a un archivo liviano. Ejecutar fuera de Streamlit.

python scripts/preparar_datos.py --origen /ruta/ventas --destino data/ventas_resumen.csv.gz

Prioridad sin solapamientos: 2025.xlsx (05-12/2025), venta anual.txt
(01-05/2026), fuentes mensuales (06-10/2026), ventadiaria.txt
(11/2026 y meses posteriores). La selección es deliberada: sumar archivos
completos superpuestos duplicaría ventas.
"""
from __future__ import annotations
import argparse, collections, csv, datetime as dt, gzip, json, re, zipfile
from pathlib import Path
from lxml import etree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
MONTHS = {'ENE':1,'FEB':2,'MAR':3,'ABR':4,'MAY':5,'JUN':6,'JUL':7,'AGO':8,'SEP':9,'SET':9,'OCT':10,'NOV':11,'DIC':12}
RX = re.compile(r'(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|SET|OCT|NOV|DIC)[A-Z]*[\s._/-]*(20\d\d|\d\d)\b',re.I)


def period(text):
    v = (str(text or '')).upper()
    m = RX.search(v)
    if not m: return None
    y = int(m.group(2)); y = y + 2000 if y < 100 else y
    return f'{y:04}-{MONTHS[m.group(1)]:02}'


def decimal(x):
    if x is None: return 0.
    s = str(x).strip().replace('\xa0','').replace(' ', '')
    if not s: return 0.
    if ',' in s: s = s.replace('.','').replace(',','.')
    try: return float(s)
    except ValueError: return 0.


def code(x):
    v = str(x or '').strip()
    if not v: return ''
    try: return str(int(float(v)))
    except (TypeError,ValueError):return v


def normal_unit(u):
    return re.sub(r'\s+',' ',str(u or '').strip().upper()) or 'SIN IDENTIFICAR'


def process_txt(path,lo,hi,agg,months):
    n=0; included=0
    with path.open('r', encoding='latin1',errors='replace',newline='') as fh:
        reader=csv.reader(fh,delimiter='\t')
        next(reader,None)
        for row in reader:
            n+=1
            if len(row)<43:continue
            ym=period(row[2]) or period(row[0]); id_=code(row[4]); u=normal_unit(row[35]);
            if not ym or not id_ or not lo<=ym<=hi:continue
            months.add(ym)
            agg[(ym,id_,u)]+=decimal(row[42]);included+=1
    print(f'{path.name}: registros {n:,} / incluidos {included:,}',flush=True)
    return included


def process_2025_xlsx(path,lo,hi,agg,months):
    n=0; included=0
    with zipfile.ZipFile(path) as z:
        root=ET.fromstring(z.read('xl/sharedStrings.xml'))
        shared=[''.join(t.itertext()) for t in root.findall(NS+'si')]
        root.clear()
        with z.open('xl/worksheets/sheet1.xml') as f:
            for _evt,row in ET.iterparse(f,events=('end',),tag=NS+'row'):
                n+=1
                if n==1:row.clear();continue
                values={}
                for c in row:
                    ref=c.get('r','');letter=ref.rstrip('0123456789')
                    if letter not in ('A','C','E','AJ','AQ'):continue
                    valnode=c.find(NS+'v')
                    if valnode is None or valnode.text is None: continue
                    val=valnode.text
                    if c.get('t')=='s': val=shared[int(val)]
                    values[letter]=val
                ym=None
                try:
                    raw=float(values.get('C',''))
                    ym=(dt.datetime(1899,12,30)+dt.timedelta(days=int(raw))).strftime('%Y-%m')
                except (ValueError,TypeError,OverflowError):
                    ym=period(values.get('A'))
                id_=code(values.get('E'))
                if ym and id_ and lo<=ym<=hi:
                    months.add(ym)
                    agg[(ym,id_,normal_unit(values.get('AJ')))]+=decimal(values.get('AQ'))
                    included+=1
                row.clear()
                if n%250000==0:print('XLSX 2025:',format(n,','),'filas',flush=True)
    print(f'{path.name}: registros {n:,} / incluidos {included:,}',flush=True)
    return included


SOURCES=[
    ('venta 2025.xlsx','2025-05','2025-12','xlsx'),
    ('venta anual.txt','2026-01','2026-05','txt'),
    ('venta junio 2026.txt','2026-06','2026-06','txt'),
    ('venta JULIO.txt','2026-07','2026-07','txt'),
    ('venta agosto.txt','2026-08','2026-08','txt'),
    ('venta septiembre.txt','2026-09','2026-09','txt'),
    ('ventadiaria octubre.txt','2026-10','2026-10','txt'),
]

def main():
    p=argparse.ArgumentParser();p.add_argument('--origen',default='/mnt/data');p.add_argument('--destino',default='data/ventas_resumen.csv.gz'); a=p.parse_args()
    source=Path(a.origen); target=Path(a.destino);target.parent.mkdir(parents=True,exist_ok=True)
    agg=collections.defaultdict(float); months=set(); files=[]; missing=[]
    # Guardar cada cierre posterior a octubre de 2026 en historicos/YYYY-MM.txt.
    # Al recalcular, el mes corriente se toma directamente de ventadiaria.txt.
    mes_actual=dt.date.today().strftime('%Y-%m')
    for name,lo,hi,typ in SOURCES:
        filepath=source/name
        if not filepath.exists(): missing.append(name);continue
        num=process_2025_xlsx(filepath,lo,hi,agg,months) if typ=='xlsx' else process_txt(filepath,lo,hi,agg,months)
        files.append({'nombre':name,'desde':lo,'hasta':hi,'filas_incluidas':num})
    for pth in sorted((source/'historicos').glob('20??-??.txt')) if (source/'historicos').exists() else []:
        archivado=pth.stem
        if archivado<='2026-10' or archivado>=mes_actual: continue
        num=process_txt(pth,archivado,archivado,agg,months)
        files.append({'nombre':str(pth.relative_to(source)),'desde':archivado,'hasta':archivado,'filas_incluidas':num})
    actual=source/'ventadiaria.txt'
    if actual.exists():
        num=process_txt(actual,mes_actual,mes_actual,agg,months)
        files.append({'nombre':'ventadiaria.txt','desde':mes_actual,'hasta':mes_actual,'filas_incluidas':num})
    else:missing.append('ventadiaria.txt')
    with gzip.open(target,'wt',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['mes','cliente','unidad','neto'])
        for (ym,id_,u),net in sorted(agg.items()):w.writerow([ym,id_,u,round(net,2)])
    meta={'desde':'2025-05','meses':sorted(months),'archivos':files,'faltantes':missing,
          'filas_agregadas':len(agg),'generado':dt.datetime.now().isoformat(timespec='seconds')}
    target.with_name('cobertura.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Terminado:',target,len(agg),'registros compactos. Meses:',sorted(months),flush=True)

if __name__=='__main__': main()
