"""Normalización del volcado de respuestas BEES Force por cliente, fecha y negocio."""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
import pandas as pd

DISTRIBUIDOR = "070549"  # DDV: 70549
BDR_PREFIJO = "AR070549"
NEGOCIOS_FORCE = ("CZA", "NABS", "MARKETPLACE", "BEYOND BEER")

def limpiar_texto(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    if "Ã" in s or "Â" in s:
        try:
            s = s.encode("latin-1").decode("utf-8")
        except (UnicodeError, ValueError):
            pass
    try:
        v = json.loads(s)
        if isinstance(v, list):
            s = "; ".join(str(i) for i in v if i is not None)
    except (ValueError, TypeError):
        pass
    # Exportaciones de Force con comillas y barras rotas.
    s = s.replace(r'\\"', '"').replace("\\\\", "")
    s = s.strip().strip('[]\\" ')
    return s.strip()

def sin_tildes(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))

def negocio_de_tarea(tarea: object) -> str:
    s = sin_tildes(limpiar_texto(tarea)).upper()
    if "BEYOND BEER" in s:
        return "BEYOND BEER"
    if "MARKETPLACE" in s:
        return "MARKETPLACE"
    if re.search(r"\bNAB(?:S)?\b", s):
        return "NABS"
    if re.search(r"\bBEER\b", s) or re.search(r"\bCZA\b", s):
        return "CZA"
    return "SIN CLASIFICAR"

def codigo_cliente_completo(value: object) -> str:
    s = re.sub(r"\.0$", "", str(value or "").strip())
    s = re.sub(r"\D", "", s)
    return s.zfill(14) if s else ""

def cargar_respuestas(path):
    df = pd.read_csv(path, compression="gzip", dtype="string", keep_default_na=False)
    for c in ['cliente','negocio','mes','fecha','motivo_principal','detalle','estado_force','bdr_id']:
        if c not in df: df[c] = ''
    return df

def procesar_meses(mes_a_ruta: dict[str, str | Path]):
    registros = []
    conteo = []
    for mes, ruta in sorted(mes_a_ruta.items()):
        df = pd.read_excel(ruta, dtype=str)
        feb = "vendor_account_id" in df
        col_id = "vendor_account_id" if feb else "cliente"
        col_tarea = "task_name" if feb else "tarea"
        col_fecha = "task_start_date" if feb else "fecha_tarea"
        col_pregunta = "subtasks_title" if feb else "pregunta"
        col_estado = "task_status" if feb else None
        id_full = df[col_id].map(codigo_cliente_completo)
        bdr = df['bdr_id'].fillna('').astype(str).str.strip()
        mask = id_full.str.startswith(DISTRIBUIDOR) & bdr.str.startswith(BDR_PREFIJO)
        x = df.loc[mask].copy()
        x["codigo_normalizado"] = id_full[mask].str[6:].str.lstrip("0").replace("", "0")
        x["negocio"] = x[col_tarea].map(negocio_de_tarea)
        x['fecha'] = pd.to_datetime(x[col_fecha], errors="coerce", utc=True).dt.strftime("%Y-%m-%d").fillna("")
        x['respuesta'] = x['subtasks_answers'].map(limpiar_texto)
        x['pregunta_limpia'] = x[col_pregunta].map(limpiar_texto)
        x['tarea_limpia'] = x[col_tarea].map(limpiar_texto)
        x['estado_force'] = x[col_estado].fillna('').str.upper() if col_estado else 'RESPUESTA'
        x['es_principal'] = (x['pregunta_limpia'].map(lambda s: 'principal razon' in sin_tildes(s).lower()) |
           ((x['orden'].astype(str).str.contains('Pregunta 1', case=False)) if 'orden' in x else False))
        # Identificador de encuesta; evitar contar preguntas como distintas tareas.
        x['id_evento'] = (x['task_id'].fillna('').astype(str) if feb else
          x['fecha'].astype(str)+'|'+x['codigo_normalizado'].astype(str)+'|'+x['negocio'].astype(str)+'|'+bdr[mask].astype(str))
        if x.empty:
            conteo.append({'mes':mes,'filas_ddv':0,'eventos':0,'sin_motivo_principal':0})
            continue
        for eid, g in x.groupby('id_evento', sort=False):
            primero=g.iloc[0]
            p1=g.loc[g['es_principal'] & g['respuesta'].ne(''), 'respuesta']
            motivo=p1.iloc[0] if not p1.empty else ''
            adicionales=g.loc[~g['es_principal'] & g['respuesta'].ne(''), ['pregunta_limpia','respuesta']]
            detalle=' | '.join(f"{r.pregunta_limpia}: {r.respuesta}" for r in adicionales.itertuples(index=False))
            # Para una misma tarea pueden existir campos vacíos/no completados.
            estado='FINISHED' if 'FINISHED' in g.estado_force.values else ('JUSTIFIED' if 'JUSTIFIED' in g.estado_force.values else 'RESPUESTA')
            registros.append({
                'mes':mes,'fecha':str(primero['fecha']), 'cliente':str(primero['codigo_normalizado']),
                'negocio':str(primero['negocio']), 'motivo_principal':str(motivo),
                'detalle':detalle,'estado_force':estado,'bdr_id':str(primero['bdr_id']),
                'tarea':str(primero['tarea_limpia']),'preguntas':int(len(g)),
                'fuente':Path(ruta).name,'id_evento':str(eid)})
        conteo.append({'mes':mes,'filas_ddv':len(x),'eventos':x['id_evento'].nunique(),
                       'sin_motivo_principal':len([a for a in registros if a['mes']==mes and not a['motivo_principal']])})
    out=pd.DataFrame.from_records(registros)
    if not out.empty:
        out=out.sort_values(['mes','cliente','negocio','fecha']).drop_duplicates(
            ['mes','cliente','negocio','fecha','id_evento'],keep='last')
    return out, pd.DataFrame(conteo)

def cruzar_mes(casos, force, mes):
    """Un registro máximo por cliente+negocio del mes, preferentemente con motivo y finalizado."""
    if force.empty:
        r=casos.copy()
        for k in ('fecha_force','motivo_force','detalle_force','estado_force'):
            r[k]=''
        return r
    ff=force.loc[(force.mes==mes)&(force.negocio.isin(['CZA','NABS']))].copy()
    ff['calidad']=ff.motivo_principal.fillna('').str.strip().ne('').astype(int)*2 + ff.estado_force.eq('FINISHED').astype(int)
    ff=ff.sort_values(['fecha','calidad']).drop_duplicates(['cliente','negocio'],keep='last')
    ff=ff[['cliente','negocio','fecha','motivo_principal','detalle','estado_force']].rename(
        columns={'fecha':'fecha_force','motivo_principal':'motivo_force','detalle':'detalle_force'})
    r=casos.merge(ff,on=['cliente','negocio'],how='left')
    for k in ('fecha_force','motivo_force','detalle_force','estado_force'):
        r[k]=r[k].fillna('')
    return r
