
from __future__ import annotations
import pandas as pd
from logica import cartera_vigencia_3m, cartera_al_cierre, cargar_clientes
from pathlib import Path


def padrón_ejemplo():
    return pd.DataFrame([
        dict(cliente="1", fantasia="Siempre", razon_social="A", localidad="Trelew", promotor="P", ruta="1", alta="2020-01-01", anulado="NO", fecha_baja=""),
        dict(cliente="2", fantasia="Baja mayo", razon_social="B", localidad="Trelew", promotor="P", ruta="1", alta="2020-01-01", anulado="SI", fecha_baja="2025-05-12"),
        dict(cliente="3", fantasia="Baja junio", razon_social="C", localidad="Trelew", promotor="P", ruta="1", alta="2020-01-01", anulado="SI", fecha_baja="2025-06-03"),
        dict(cliente="4", fantasia="Baja julio", razon_social="D", localidad="Trelew", promotor="P", ruta="1", alta="2020-01-01", anulado="SI", fecha_baja="2025-07-31"),
        dict(cliente="5", fantasia="Baja abril", razon_social="E", localidad="Trelew", promotor="P", ruta="1", alta="2020-01-01", anulado="SI", fecha_baja="2025-04-30"),
        dict(cliente="6", fantasia="Alta junio", razon_social="F", localidad="Trelew", promotor="P", ruta="1", alta="2025-06-20", anulado="NO", fecha_baja=""),
        dict(cliente="7", fantasia="Alta agosto", razon_social="G", localidad="Trelew", promotor="P", ruta="1", alta="2025-08-01", anulado="NO", fecha_baja=""),
        dict(cliente="8", fantasia="Baja sin fecha", razon_social="H", localidad="Trelew", promotor="P", ruta="1", alta="2020-01-01", anulado="SI", fecha_baja=""),
    ])


def test_ventana_julio_2025_incluye_bajas_mayo_y_junio():
    x, k=cartera_vigencia_3m(padrón_ejemplo(), "2025-07")
    assert k['meses'] == ["2025-05","2025-06","2025-07"]
    assert k['desde']=='01/05/2025' and k['hasta']=='31/07/2025'
    assert set(x['cliente'])==set(["1","2","3","4","6"])
    assert (k['universo_3m'], k['vigentes_cierre'],k['bajas_ventana'], k['bajas_previas']) == (5,2,3,2)
    by=x.set_index('cliente')
    assert by.loc['2','estado_2025-05']=='🔴 Baja 12/05/2025'
    assert by.loc['2','estado_2025-06']=='— Baja anterior'
    assert by.loc['3','estado_2025-05']=='🟢 Vigente'
    assert by.loc['3','estado_2025-06']=='🔴 Baja 03/06/2025'
    assert by.loc['6','estado_2025-05']=='— Aún sin alta'
    assert by.loc['4','fecha_baja_ventana']=='31/07/2025'
    assert not by.loc['4','vigente_cierre']


def test_ventana_rolling_mensual():
    x, k=cartera_vigencia_3m(padrón_ejemplo(),"2025-06")
    assert k['meses'] == ["2025-04","2025-05","2025-06"]
    assert '5' in set(x['cliente'])  # dado de baja en abril, parte de la ventana
    assert '4' in set(x['cliente'])  # todavía vigente en junio
    assert k['bajas_ventana']==3
    assert k['vigentes_cierre']==3


def test_totales_octubre_y_julio_reconcilian_con_universo_al_cierre():
    archivo=Path(__file__).parent.parent/"data"/"clientes.csv.gz"
    if not archivo.exists():
        return
    fuente=cargar_clientes(archivo)
    for mes in ['2025-07','2026-10']:
        x,k=cartera_vigencia_3m(fuente,mes)
        cierre=cartera_al_cierre(fuente,mes)
        assert k['vigentes_cierre']==len(cierre)
        assert set(x.loc[x['vigente_cierre'],'cliente'])==set(cierre['cliente'])
    x,k=cartera_vigencia_3m(fuente,'2025-07')
    assert k['universo_3m']==1510
    assert k['vigentes_cierre']==1480
    assert k['bajas_ventana']==30
    assert k['bajas_previas']==20
