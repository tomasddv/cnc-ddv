"""Regresión: los clientes nuevos no son CNC de 3/6/12 meses."""
from pathlib import Path
import pandas as pd
from logica import cargar_clientes, cargar_ventas, generar_casos, resumen_cnc_por_promotor

ROOT = Path(__file__).resolve().parents[1]

def _datos_ficticios():
    clientes = pd.DataFrame([
        {"cliente": "nuevo_septiembre", "alta": "2026-09-17", "anulado": "NO",
         "fecha_baja": None, "promotor": "P1"},
        {"cliente": "alta_primero_agosto", "alta": "2026-08-01", "anulado": "NO",
         "fecha_baja": None, "promotor": "P1"},
        {"cliente": "alta_dos_agosto", "alta": "2026-08-02", "anulado": "NO",
         "fecha_baja": None, "promotor": "P2"},
        {"cliente": "antiguo", "alta": "2024-10-01", "anulado": "NO",
         "fecha_baja": None, "promotor": "P2"},
    ])
    clientes["licencia_alcohol"] = "SI"
    clientes["alta"] = pd.to_datetime(clientes["alta"])
    clientes["fecha_baja"] = pd.to_datetime(clientes["fecha_baja"])
    # Todos sin compra en CZA: no deben contarse por antigüedad insuficiente.
    ventas = pd.DataFrame([
        {"mes": "2026-10", "cliente": "otro", "unidad": "CERVEZAS CMQ", "neto": 50}
    ])
    cobertura = {str(x) for x in pd.period_range("2025-11", "2026-10", freq="M")}
    return clientes, ventas, cobertura

def test_u3m_y_u12m_respetan_fecha_alta():
    clientes, ventas, cobertura = _datos_ficticios()
    casos, control = generar_casos(clientes, ventas, "2026-10", cobertura)
    cza = casos[casos.negocio == "CZA"].set_index("cliente")
    assert not bool(cza.loc["nuevo_septiembre", "cnc_u3m"])
    assert not bool(cza.loc["nuevo_septiembre", "cnc_u12m"])
    assert cza.loc["nuevo_septiembre", "clasificacion"].startswith("Alta reciente")
    assert bool(cza.loc["alta_primero_agosto", "cnc_u3m"])
    assert not bool(cza.loc["alta_primero_agosto", "cnc_u12m"])
    assert not bool(cza.loc["alta_dos_agosto", "cnc_u3m"])
    assert bool(cza.loc["antiguo", "cnc_u3m"])
    assert bool(cza.loc["antiguo", "cnc_u12m"])

def test_ranking_3_6_12_no_considera_altas_recientes():
    clientes, ventas, cobertura = _datos_ficticios()
    casos, _ = generar_casos(clientes, ventas, "2026-10", cobertura)
    for ventana in (3, 6, 12):
        ranking, meta = resumen_cnc_por_promotor(casos, "2026-10", cobertura, ventana)
        assert meta["verificable"]
        assert int(ranking.clientes_cnc.sum()) == (2 if ventana == 3 else 1)
        assert int(ranking.casos_cnc.sum()) == (8 if ventana == 3 else 4)

def test_cliente_5542_real_no_es_cnc_octubre():
    clientes = cargar_clientes(ROOT / "data/clientes.csv.gz")
    ventas = cargar_ventas(ROOT / "data/ventas_resumen.csv.gz")
    caso_cliente = clientes[clientes.cliente == "5542"].iloc[0]
    assert str(caso_cliente.alta.date()) == "2026-09-17"
    casos, _ = generar_casos(clientes, ventas, "2026-10", set(ventas.mes.unique()))
    filas = casos[casos.cliente == "5542"]
    assert len(filas) >= 1
    assert not filas.cnc_u3m.any()
    assert not filas.cnc_u12m.any()
    marketplace = filas[filas.negocio == "MARKETPLACE"]
    assert len(marketplace) == 1
    assert marketplace.iloc[0].clasificacion.startswith("Alta reciente")
    for ventana in (3, 6, 12):
        resumen, _ = resumen_cnc_por_promotor(casos, "2026-10", set(ventas.mes.unique()), ventana)
        # Cuenta ningún caso CNC del cliente reciente en el motor compartido.
        # El estado marcado en la fuente es determinante de la elegibilidad.
        from logica import cumple_antiguedad_cnc
        assert not bool(cumple_antiguedad_cnc(filas.alta, "2026-10", ventana).any())

def test_ventana_cambia_con_mes():
    from logica import cumple_antiguedad_cnc
    altas = pd.Series(pd.to_datetime(["2025-05-01", "2025-05-02", "2025-06-02"]))
    assert cumple_antiguedad_cnc(altas, "2025-07", 3).tolist() == [True, False, False]
    assert cumple_antiguedad_cnc(altas, "2025-08", 3).tolist() == [True, True, False]
