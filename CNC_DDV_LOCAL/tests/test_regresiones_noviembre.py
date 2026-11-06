"""Pruebas sobre la fuente real y la interfaz solicitada."""
from pathlib import Path
import pandas as pd
from logica import (cargar_clientes,cargar_ventas,generar_casos,
                    tiene_promotor_asignado,cartera_al_cierre,cartera_vigencia_3m)
from force import cargar_respuestas

P = Path(__file__).resolve().parents[1]

def test_cnc_u3m_excluye_anulados_y_no_asignados():
    c=cargar_clientes(P/'data/clientes.csv.gz')
    v=cargar_ventas(P/'data/ventas_resumen.csv.gz')
    casos,meta=generar_casos(c,v,'2026-10',set(v.mes.unique()))
    vista=casos.loc[casos.cnc_u3m]
    activos=set(cartera_al_cierre(c,'2026-10').cliente)
    assert len(vista)>0
    assert set(vista.cliente).issubset(activos)
    assert tiene_promotor_asignado(vista).all()
    h,k=cartera_vigencia_3m(c,'2026-10')
    anulados=set(h.loc[~h.vigente_cierre,'cliente'])
    assert not (set(vista.cliente) & anulados)
    assert int(k['bajas_ventana'])==38

def test_force_no_es_solo_cza_y_tiene_271_encuestas():
    c=cargar_clientes(P/'data/clientes.csv.gz')
    force=cargar_respuestas(P/'data/force_respuestas.csv.gz')
    validos=set(c.loc[tiene_promotor_asignado(c),'cliente'].astype(str))
    f=force.loc[force.cliente.astype(str).isin(validos)]
    assert len(f)==271
    octubre=f.loc[f.mes=='2026-10']
    assert len(octubre)==27
    assert len(octubre.loc[octubre.negocio=='CZA'])==5
    assert len(octubre.loc[octubre.negocio=='NABS'])==22

def test_interfaz_lista_clic_y_force_con_filtro_propio():
    app=(P/'app.py').read_text(encoding='utf-8')
    assert "on_select='rerun',selection_mode='multi-row'" in app
    assert "Seleccionar TODOS" in app
    assert "key='mes_solo_force'" in app
    assert "key='negocio_solo_force'" in app
    assert "if negocio!='Todos': fview=fview" not in app
    assert "CNC U3M" in app
    assert "'Vigencia histórica · 3 meses'" not in app
    assert "cartera,rk_promotor,gestion,respuestas,auditoria,seguimiento=st.tabs(" in app
    assert "Bajas durante 3M" in app
