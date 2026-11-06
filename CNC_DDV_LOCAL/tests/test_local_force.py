from __future__ import annotations
import sys
from pathlib import Path
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from force import cargar_respuestas, cruzar_mes
from almacen_local import leer_local,guardar_plan_local,agregar_contacto_local
from logica import cargar_clientes,cargar_ventas,generar_casos

ROOT=Path(__file__).resolve().parents[1]

def test_force_es_solo_ddv_y_no_duplica_preguntas():
    f=cargar_respuestas(ROOT/'data/force_respuestas.csv.gz')
    assert len(f)==271
    assert f.cliente.nunique()==206
    assert int(f.negocio.isin(['CZA','NABS']).sum())==217
    assert f.bdr_id.astype(str).str.startswith('AR070549').all()
    assert f.groupby(['mes','cliente','negocio','fecha','id_evento']).size().max()==1

def test_cruce_force_con_cartera_historica():
    c=cargar_clientes(ROOT/'data/clientes.csv.gz')
    v=cargar_ventas(ROOT/'data/ventas_resumen.csv.gz')
    f=cargar_respuestas(ROOT/'data/force_respuestas.csv.gz')
    casos,meta=generar_casos(c,v,'2026-10',set(v.mes.unique()))
    assert meta['activos']==1504
    assert meta['u3_completo'] and meta['u12_completo']
    r=cruzar_mes(casos,f,'2026-10')
    assert len(r)==len(casos)
    assert r.groupby(['cliente','negocio']).size().max()==1
    assert ((r.cnc_u3m)&(r.negocio.isin(['CZA','NABS']))&r.motivo_force.ne('')).sum() ==20

def test_sqlite_crear_actualizar_y_contactar():
    with tempfile.TemporaryDirectory() as tmp:
        db=str(Path(tmp)/'local.sqlite')
        f={'clave':'2026-10|123|CZA','mes':'2026-10','cliente':'123','negocio':'CZA','motivo':'Precio','accion':'Primera acción'}
        guardar_plan_local(db,f)
        guardar_plan_local(db,{**f,'accion':'Segunda acción'})
        agregar_contacto_local(db,{'mes':'2026-10','cliente':'123','negocio':'CZA','fecha':'2026-10-10','tipo':'Visita promotor','resultado':'Cliente contactado'})
        p,c=leer_local(db)
        assert len(p)==1
        assert p.accion.iloc[0]=='Segunda acción'
        assert len(c)==1
        assert c.cliente.iloc[0]=='123'
