"""Plan común: selección múltiple / todos, protección de históricos y persistencia local."""
from pathlib import Path
import pandas as pd
from planes_masivos import construir_planes_masivos
from almacen_local import leer_local, guardar_planes_local_masivo


def fila(codigo, negocio="CZA", promotor="PROMOTOR UNO", **kw):
    dato={
        "cliente":str(codigo),"negocio":negocio,"promotor":promotor,
        "cnc_u3m":True,"motivo_force":"Precio","motivo":"",
        "objetivo":"","accion":"","estado":"","supervisor":"",
        "oportunidad_censo":"","evidencia":"","fecha_objetivo":""
    }
    dato.update(kw)
    return dato


def test_plan_compartido_a_varios_y_seleccionar_todos(tmp_path):
    filas=[fila("50"),fila("57",promotor="PROMOTOR DOS"),fila("60",motivo_force="Competencia")]
    planes,stats=construir_planes_masivos(
        filas,"2026-10",objetivo="Retomar ventas",
        accion="Presentar propuesta comercial",fecha_objetivo="2026-11-25",estado="Pendiente",
        actualizado_en="2026-11-05T12:00:00",
    )
    assert stats["seleccionados"] == 3
    assert len(planes)==3
    assert len({p["clave"] for p in planes})==3
    assert {p["responsable"] for p in planes}=={"PROMOTOR UNO","PROMOTOR DOS"}
    assert [p["motivo"] for p in planes]==["Precio","Precio","Competencia"]
    assert {p["accion"] for p in planes}=={"Presentar propuesta comercial"}
    db=tmp_path/"cnc.sqlite"
    assert guardar_planes_local_masivo(db,planes)==3
    guardados,_=leer_local(db)
    assert len(guardados)==3
    assert set(guardados["mes"])=={"2026-10"}


def test_no_sobrescribe_planes_existentes_por_defecto(tmp_path):
    filas=[fila("50",accion="Plan existente",estado="En curso"),
           fila("57",motivo_force="")]
    planes,stats=construir_planes_masivos(
        filas,"2026-10",objetivo="Ventas",accion="Plan masivo",
        fecha_objetivo="2026-12-01",estado="Pendiente"
    )
    assert stats["ya_tenian_plan"]==1
    assert len(planes)==1 and planes[0]["cliente"]=="57"
    assert stats["sin_motivo"]==1
    planes2,stats2=construir_planes_masivos(
        filas,"2026-10",objetivo="Ventas",accion="Plan masivo",
        fecha_objetivo="2026-12-01",estado="Pendiente",
        sobrescribir=True,motivo_comun="Precio",responsable_comun="SUPERVISOR"
    )
    assert len(planes2)==2
    assert all(p["motivo"]=="Precio" and p["responsable"]=="SUPERVISOR" for p in planes2)


def test_no_escribe_no_elegibles_ni_duplica():
    filas=[fila("50"),fila("50"),fila("57",cnc_u3m=False),
           fila("60",negocio="AGUAS"),fila("61",promotor="")]
    planes,stats=construir_planes_masivos(
        filas,"2026-10",objetivo="",accion="Acción",fecha_objetivo="2026-11-27",estado="Pendiente"
    )
    assert len(planes)==1
    assert stats["duplicados"]==1
    assert stats["no_elegibles"]==2
    assert stats["sin_responsable"]==1


def test_actualizacion_sqlite_respeta_periodos_y_restantes(tmp_path):
    db=tmp_path/"cnc.sqlite"
    primera,_=construir_planes_masivos(
        [fila("50")],"2026-09",objetivo="Original",accion="No tocar",
        fecha_objetivo="2026-09-30",estado="Pendiente"
    )
    guardar_planes_local_masivo(db,primera)
    segundo,_=construir_planes_masivos(
        [fila("50"),fila("57")],"2026-10",objetivo="Nuevo",accion="Acción masiva",
        fecha_objetivo="2026-11-30",estado="En curso"
    )
    guardar_planes_local_masivo(db,segundo)
    guardados,_=leer_local(db)
    assert len(guardados)==3
    assert guardados.loc[guardados.mes=="2026-09","accion"].iloc[0]=="No tocar"
    assert (guardados.loc[guardados.mes=="2026-10","accion"]=="Acción masiva").all()


def test_interfaz_soporta_multi_y_todos():
    app=(Path(__file__).resolve().parents[1]/"app.py").read_text()
    assert "selection_mode='multi-row'" in app
    assert "todos_visibles=st.checkbox" in app
    assert "construir_planes_masivos(" in app
    assert "guardar_planes_local_masivo(DB_LOCAL,planes_nuevos)" in app
