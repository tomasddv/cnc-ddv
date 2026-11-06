"""Regresión de filtros comerciales: CZA solo licencia SI, UNG conserva toda la cartera."""
from pathlib import Path
import pandas as pd
from logica import (cargar_clientes,cargar_ventas,generar_casos,cartera_vigencia_3m,
                    tiene_licencia_alcohol,tiene_promotor_asignado,resumen_cnc_por_promotor)

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/"data/clientes.csv.gz"
V=ROOT/"data/ventas_resumen.csv.gz"

def test_snapshot_incluye_licencia_y_supervisor():
    clientes=cargar_clientes(C)
    assert len(clientes)==6400
    assert int(tiene_licencia_alcohol(clientes).sum())==2385
    assert int((clientes.licencia_alcohol=='NO').sum())==4015
    con_promotor=clientes[tiene_promotor_asignado(clientes)]
    assert set(con_promotor.supervisor_asignado.unique()) == {
        "BRUNO ISMAEL","HERNAN CASCO","ANIBAL VITI"}
    assert int((con_promotor.supervisor_asignado=="BRUNO ISMAEL").sum())==1162
    assert int((con_promotor.supervisor_asignado=="HERNAN CASCO").sum())==967

def test_cza_restringe_licencia_sin_afectar_ung():
    clientes=cargar_clientes(C)
    ventas=cargar_ventas(V)
    casos,meta=generar_casos(clientes,ventas,'2026-10',set(ventas.mes))
    assert not casos[casos.negocio=="CZA"].licencia_alcohol.ne('SI').any()
    # NABS no hereda el filtro: debe contener clientes sin licencia alcohol.
    nabs=casos[casos.negocio=='NABS']
    assert nabs.licencia_alcohol.eq('NO').any()
    assert nabs.cliente.nunique()==meta['activos']
    assert casos[casos.negocio=="CZA"].cliente.nunique()<nabs.cliente.nunique()

def test_supervisor_no_mueve_clientes_entre_equipos():
    c=cargar_clientes(C);v=cargar_ventas(V)
    a=c[c.supervisor_asignado=="BRUNO ISMAEL"]
    b=c[c.supervisor_asignado=="HERNAN CASCO"]
    assert not (set(a.cliente)&set(b.cliente))
    ca,_=generar_casos(a,v,"2026-10",set(v.mes))
    cb,_=generar_casos(b,v,"2026-10",set(v.mes))
    assert ca.supervisor_asignado.eq("BRUNO ISMAEL").all()
    assert cb.supervisor_asignado.eq("HERNAN CASCO").all()
    for casos in (ca,cb):
        rank,metadata=resumen_cnc_por_promotor(casos[casos.negocio=='CZA'],
                  "2026-10",set(v.mes),3)
        assert metadata['verificable']
        assert rank['clientes_cnc'].sum() >= 0
    ha,_=cartera_vigencia_3m(a,"2026-10")
    assert ha.supervisor_asignado.eq("BRUNO ISMAEL").all()

def test_sintetico_un_negocio_no_excluye_el_otro():
    c=pd.DataFrame([
        {'cliente':'1','fantasia':'A','alta':pd.Timestamp('2024-01-01'),'fecha_baja':pd.NaT,'anulado':'NO','promotor':'BRUNO','licencia_alcohol':'NO'},
        {'cliente':'2','fantasia':'B','alta':pd.Timestamp('2024-01-01'),'fecha_baja':pd.NaT,'anulado':'NO','promotor':'HERNAN','licencia_alcohol':'SI'}
    ])
    v=pd.DataFrame([{'mes':'2026-10','cliente':'9','unidad':'UNG','neto':2},
                    {'mes':'2026-10','cliente':'9','unidad':'CERVEZAS CMQ','neto':2}])
    cv={str(x) for x in pd.period_range('2025-11','2026-10',freq='M')}
    casos,_=generar_casos(c,v,'2026-10',cv)
    assert set(casos[casos.negocio=='CZA'].cliente)=={'2'}
    assert set(casos[casos.negocio=='NABS'].cliente)=={'1','2'}
