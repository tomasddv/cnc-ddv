"""Persistencia local SQLite: modo demo funcional sin Google, GitHub ni claves."""
from __future__ import annotations
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime
import pandas as pd
from almacen import HEADERS

def _con(ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    cn=sqlite3.connect(str(ruta),timeout=15)
    cn.row_factory=sqlite3.Row
    cn.execute("PRAGMA busy_timeout=15000")
    cn.execute("PRAGMA journal_mode=WAL")
    return cn

def inicializar(ruta):
    with _con(ruta) as cn:
        cn.execute("""CREATE TABLE IF NOT EXISTS planes (
              clave TEXT PRIMARY KEY, mes TEXT NOT NULL, cliente TEXT NOT NULL, negocio TEXT NOT NULL,
              motivo TEXT, objetivo TEXT, accion TEXT, responsable TEXT, supervisor TEXT,
              fecha_objetivo TEXT, estado TEXT, oportunidad_censo TEXT, fecha_actualizacion TEXT,
              evidencia TEXT
            )""")
        cn.execute("""CREATE TABLE IF NOT EXISTS contactos (
             id TEXT PRIMARY KEY, mes TEXT NOT NULL, cliente TEXT NOT NULL, negocio TEXT NOT NULL,
             fecha TEXT NOT NULL, tipo TEXT, actor TEXT, resultado TEXT, observacion TEXT, evidencia TEXT
            )""")
        cn.execute("CREATE INDEX IF NOT EXISTS idx_planes_cnc ON planes(cliente,negocio,mes)")
        cn.execute("CREATE INDEX IF NOT EXISTS idx_contactos_cnc ON contactos(cliente,negocio,fecha)")

def leer_local(ruta):
    inicializar(ruta)
    with _con(ruta) as cn:
        planes=pd.read_sql_query("SELECT * FROM planes",cn)
        contactos=pd.read_sql_query("SELECT * FROM contactos",cn)
    return planes.fillna(""),contactos.fillna("")

def guardar_plan_local(ruta,registro):
    inicializar(ruta)
    cols=HEADERS['planes']
    vals=[str(registro.get(k,'')) for k in cols]
    cols_sql=','.join(cols)
    marks=','.join('?' for _ in cols)
    changes=','.join(f'{k}=excluded.{k}' for k in cols if k!='clave')
    with _con(ruta) as cn:
        cn.execute(f"INSERT INTO planes ({cols_sql}) VALUES ({marks}) ON CONFLICT(clave) DO UPDATE SET {changes}",vals)

def guardar_planes_local_masivo(ruta,registros):
    """Guarda todos los planes en una sola transacción; rollback si alguno falla."""
    if not registros:
        return 0
    inicializar(ruta)
    cols=HEADERS["planes"]
    vals=[[str(registro.get(k, "")) for k in cols] for registro in registros]
    cols_sql=",".join(cols)
    marks=",".join("?" for _ in cols)
    changes=",".join(f"{k}=excluded.{k}" for k in cols if k!="clave")
    with _con(ruta) as cn:
        cn.executemany(
            f"INSERT INTO planes ({cols_sql}) VALUES ({marks}) "
            f"ON CONFLICT(clave) DO UPDATE SET {changes}", vals
        )
    return len(registros)


def agregar_contacto_local(ruta,registro):
    inicializar(ruta)
    cols=HEADERS['contactos']
    registro={**registro,'id':str(registro.get('id') or uuid.uuid4().hex)}
    vals=[str(registro.get(k,'')) for k in cols]
    with _con(ruta) as cn:
        cn.execute(f"INSERT INTO contactos ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",vals)

def exportar_todo_csv(ruta):
    import io,zipfile
    ps,cs=leer_local(ruta)
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('planes.csv',ps.to_csv(index=False,sep=';',encoding='utf-8-sig'))
        z.writestr('contactos.csv',cs.to_csv(index=False,sep=';',encoding='utf-8-sig'))
    return b.getvalue()
