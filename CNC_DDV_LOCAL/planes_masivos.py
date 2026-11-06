"""Construcción segura y auditable de planes compartidos para clientes CNC elegibles."""
from __future__ import annotations
from datetime import datetime


def _texto(valor):
    if valor is None:
        return ""
    txt = str(valor).strip()
    return "" if txt.lower() in ("nan", "none", "<na>", "nat") else txt


def tiene_plan_existente(registro):
    """La presencia de cualquier campo de un plan indica que no debe sobrescribirse por defecto."""
    return any(_texto(registro.get(c)) for c in ("accion", "objetivo", "estado", "motivo", "fecha_objetivo"))


def construir_planes_masivos(
    filas, mes, *, objetivo, accion, fecha_objetivo, estado,
    motivo_comun="", responsable_comun="", supervisor_comun="",
    oportunidad_comun="", evidencia_comun="", sobrescribir=False,
    actualizado_en=None,
):
    """Retorna (planes, conteo), sin tocar el almacenamiento ni modificar las filas.

    Motivos por cliente/promotor/Force y responsables se preservan por defecto;
    solo se reemplazan cuando se suministra explícitamente un valor común.
    """
    if not _texto(accion):
        raise ValueError("Completá una acción concreta antes de guardar.")
    fecha = fecha_objetivo.isoformat() if hasattr(fecha_objetivo, "isoformat") else _texto(fecha_objetivo)
    if not fecha:
        raise ValueError("Indicá una fecha compromiso.")
    registrado = actualizado_en or datetime.now().isoformat(timespec="seconds")
    conteo = {"seleccionados": 0, "ya_tenian_plan": 0, "no_elegibles": 0,
              "sin_responsable": 0, "sin_motivo": 0, "duplicados": 0}
    planes = []
    vistos = set()
    for fila in filas:
        conteo["seleccionados"] += 1
        cliente = _texto(fila.get("cliente"))
        negocio = _texto(fila.get("negocio")).upper()
        promotor = _texto(fila.get("promotor"))
        if not cliente or negocio not in ("CZA", "NABS") or not bool(fila.get("cnc_u3m", False)):
            conteo["no_elegibles"] += 1
            continue
        clave = f"{mes}|{cliente}|{negocio}"
        if clave in vistos:
            conteo["duplicados"] += 1
            continue
        vistos.add(clave)
        if not sobrescribir and tiene_plan_existente(fila):
            conteo["ya_tenian_plan"] += 1
            continue
        responsable = _texto(responsable_comun) or promotor
        if not responsable:
            conteo["sin_responsable"] += 1
            continue
        motivo = (_texto(motivo_comun) or _texto(fila.get("motivo"))
                  or _texto(fila.get("motivo_relevamiento"))
                  or _texto(fila.get("motivo_force")))
        if not motivo:
            conteo["sin_motivo"] += 1
        planes.append({
            "clave": clave, "mes": mes, "cliente": cliente, "negocio": negocio,
            "motivo": motivo, "objetivo": _texto(objetivo),
            "accion": _texto(accion), "responsable": responsable,
            "supervisor": (_texto(supervisor_comun) or _texto(fila.get("supervisor"))
                           or _texto(fila.get("supervisor_asignado"))),
            "fecha_objetivo": fecha,
            "estado": _texto(estado) or "Pendiente",
            "oportunidad_censo": _texto(oportunidad_comun)
               or _texto(fila.get("oportunidad_censo")) or "Sin validar",
            "fecha_actualizacion": registrado,
            "evidencia": _texto(evidencia_comun) or _texto(fila.get("evidencia"))
        })
    return planes, conteo
