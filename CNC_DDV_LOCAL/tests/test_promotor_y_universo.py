from __future__ import annotations
import pandas as pd
from pathlib import Path
from logica import (cargar_clientes,cargar_ventas,generar_casos,
                    cartera_vigencia_3m,cartera_al_cierre,tiene_promotor_asignado)

P=Path(__file__).resolve().parents[1]

def test_excluir_no_asignados_en_ambas_vistas():
    df=pd.DataFrame([
        {'cliente':'1','fantasia':'A','razon_social':'A','localidad':'Trelew','promotor':'PABLO','ruta':'712','alta':'2020-01-01','anulado':'NO','fecha_baja':''},
        {'cliente':'2','fantasia':'B','razon_social':'B','localidad':'Trelew','promotor':'','ruta':'9999','alta':'2020-01-01','anulado':'NO','fecha_baja':''},
        {'cliente':'3','fantasia':'C','razon_social':'C','localidad':'Trelew','promotor':'  ','ruta':'999','alta':'2020-01-01','anulado':'SI','fecha_baja':'2025-06-07'},
        {'cliente':'4','fantasia':'D','razon_social':'D','localidad':'Trelew','promotor':'SIN PREVENTA','ruta':'911','alta':'2020-01-01','anulado':'NO','fecha_baja':''},
        {'cliente':'5','fantasia':'E','razon_social':'E','localidad':'Trelew','promotor':'VENDEDOR LIBRE','ruta':'911','alta':'2020-01-01','anulado':'NO','fecha_baja':''},
        {'cliente':'6','fantasia':'F','razon_social':'F','localidad':'Trelew','promotor':'MARÍA','ruta':'7','alta':'2020-01-01','anulado':'SI','fecha_baja':'2025-06-10'},
        {'cliente':'7','fantasia':'G','razon_social':'G','localidad':'Trelew','promotor':'NICASTRO','ruta':'7','alta':'2020-01-01','anulado':'NO','fecha_baja':''},
    ])
    df['licencia_alcohol']='SI'
    for col in ['alta','fecha_baja']:
        df[col]=pd.to_datetime(df[col],errors='coerce')
    assert set(df.loc[tiene_promotor_asignado(df),'cliente']) == {'1','6','7'}
    hist,k=cartera_vigencia_3m(df,'2025-07')
    assert set(hist.cliente)=={'1','6','7'}
    assert k['bajas_ventana']==1
    assert hist.set_index('cliente').loc['6','estado_2025-06']=='🔴 Baja 10/06/2025'
    actual=cartera_al_cierre(df,'2025-07')
    assert set(actual.cliente)=={'1','7'}
    ventas=pd.DataFrame([{'mes':'2025-05','cliente':'1','unidad':'CERVEZAS CMQ','neto':100}])
    cases,meta=generar_casos(df,ventas,'2025-07',{'2025-05','2025-06','2025-07'})
    assert set(cases.cliente)=={'1','7'}
    assert meta['activos']==2

def test_cartera_con_promotor_mismo_universo_3m_y_cnc_al_cierre():
    c=cargar_clientes(P/'data'/'clientes.csv.gz')
    v=cargar_ventas(P/'data'/'ventas_resumen.csv.gz')
    for mes in ['2025-07','2026-10']:
        hist,k=cartera_vigencia_3m(c,mes)
        cases,meta=generar_casos(c,v,mes,set(v.mes.unique()))
        assert set(cases.cliente)==set(hist.loc[hist.vigente_cierre,'cliente'])
        assert k['vigentes_cierre']==meta['activos']
        assert (hist.promotor.astype(str).str.strip()!='').all()
        assert not hist.promotor.astype(str).str.upper().isin(['SIN PREVENTA','VENDEDOR LIBRE']).any()
        assert (~hist.vigente_cierre).sum()==k['bajas_ventana']
    hist,k=cartera_vigencia_3m(c,'2025-07')
    assert (k['universo_3m'],k['vigentes_cierre'],k['bajas_ventana'],k['bajas_previas'])==(1510,1480,30,20)
