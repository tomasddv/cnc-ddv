"""Persistencia segura de planes y registros en Google Sheets."""
from __future__ import annotations
import uuid
import pandas as pd

HEADERS={
 'planes':['clave','mes','cliente','negocio','motivo','objetivo','accion','responsable','supervisor','fecha_objetivo','estado','oportunidad_censo','fecha_actualizacion','evidencia'],
 'contactos':['id','mes','cliente','negocio','fecha','tipo','actor','resultado','observacion','evidencia']
}

def get_sheet(creds,spreadsheet_id):
    import gspread
    gc=gspread.authorize(creds)
    sh=gc.open_by_key(spreadsheet_id)
    for name,head in HEADERS.items():
        try:ws=sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws=sh.add_worksheet(title=name,rows=5000,cols=max(len(head),15));ws.append_row(head)
        if not ws.row_values(1):ws.append_row(head)
    return sh


def leer(sh,name):
    head=HEADERS[name]
    data=sh.worksheet(name).get_all_records(expected_headers=head)
    return pd.DataFrame(data,columns=head).fillna('')


def guardar_plan(sh,registro):
    ws=sh.worksheet('planes')
    clave=registro['clave'];ids=ws.col_values(1)
    row=[str(registro.get(k,'')) for k in HEADERS['planes']]
    if clave in ids[1:]: ws.update(range_name=f'A{ids.index(clave)+1}',values=[row])
    else: ws.append_row(row,value_input_option='RAW')


def guardar_planes_masivos_sheet(sh, registros):
    """Actualiza lotes en Sheets. Se usa solo después de preparar/validar la selección."""
    if not registros:
        return 0
    ws=sh.worksheet("planes")
    ids=ws.col_values(1)
    row_ids={clave:i + 1 for i,clave in enumerate(ids) if i and clave}
    cambios=[]
    nuevos=[]
    for registro in registros:
        fila=[str(registro.get(k, "")) for k in HEADERS["planes"]]
        clave=registro["clave"]
        if clave in row_ids:
            n=row_ids[clave]
            cambios.append({"range": f"A{n}:N{n}", "values": [fila]})
        else:
            nuevos.append(fila)
    if cambios:
        ws.batch_update(cambios,value_input_option="RAW")
    if nuevos:
        ws.append_rows(nuevos,value_input_option="RAW")
    return len(registros)


def agregar_contacto(sh,registro):
    registro={**registro,'id':uuid.uuid4().hex}
    sh.worksheet('contactos').append_row([str(registro.get(k,'')) for k in HEADERS['contactos']],value_input_option='RAW')
