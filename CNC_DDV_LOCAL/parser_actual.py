"""Procesa el mes corriente desde `ventadiaria.txt` sin cargar Excel."""
import csv,io,re,collections
import pandas as pd
MESES={'ENE':1,'FEB':2,'MAR':3,'ABR':4,'MAY':5,'JUN':6,'JUL':7,'AGO':8,'SEP':9,'OCT':10,'NOV':11,'DIC':12}
RX=re.compile(r'(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)[A-Z]*[-\s/]*(20\d\d|\d\d)',re.I)

def parsear_mes(value):
    m=RX.search(str(value or '').upper())
    if not m:return None
    y=int(m.group(2));y=y+2000 if y<100 else y
    return f'{y:04d}-{MESES[m.group(1)]:02d}'

def monto(text):
    s=str(text or '').strip()
    if ',' in s:s=s.replace('.','').replace(',','.')
    try:return float(s)
    except ValueError:return 0.

def consolidar_actual(raw,mes_minimo):
    f=io.TextIOWrapper(io.BytesIO(raw),encoding='latin1',errors='replace',newline='')
    reader=csv.reader(f,delimiter='\t');next(reader,None)
    a=collections.defaultdict(float)
    for r in reader:
        if len(r)<43:continue
        ym=parsear_mes(r[2]);cliente=r[4].strip();unidad=r[35].strip().upper()
        if not ym or ym<mes_minimo or not cliente:continue
        try:cliente=str(int(float(cliente)))
        except ValueError:continue
        a[(ym,cliente,unidad)]+=monto(r[42])
    return pd.DataFrame([{'mes':m,'cliente':c,'unidad':u,'neto':round(v,2)} for (m,c,u),v in a.items()],columns=['mes','cliente','unidad','neto'])
