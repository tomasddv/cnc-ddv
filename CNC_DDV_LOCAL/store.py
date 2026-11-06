"""Base de relevamientos DDV: SQLite local o PostgreSQL en la nube.

La clave de una gestión es (periodo, cliente, negocio). La misma cuenta de
cliente puede ser relevada separadamente para CZA y UNG.
"""
from __future__ import annotations
import csv
import hashlib
import hmac
import io
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text

MOTIVOS = (
    "Sin dinero",
    "Cerrado",
    "Compra en súper/mayorista",
    "Otro",
)
COLUMNAS = (
    'periodo','cliente','negocio','promotor','supervisor_asignado',
    'fantasia','razon_social','ultima_compra','licencia_alcohol','cnc_u3m','alta'
)


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def preparar_csv(raw: bytes|str) -> list[dict]:
    """Valida una campaña elegible: altas y licencia no se reevalúan en la app.

    El CSV lo genera el motor CNC con vigencia, antigüedad y última compra.
    No se acepta un archivo genérico sin marca CNC: evitar envíos erróneos.
    """
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8-sig')
    df = pd.read_csv(io.StringIO(raw), dtype='string', keep_default_na=False)
    faltantes = [c for c in COLUMNAS if c not in df.columns]
    if faltantes:
        raise ValueError('Faltan columnas del archivo CNC: ' + ', '.join(faltantes))
    df = df[list(COLUMNAS)].copy()
    for col in COLUMNAS:
        df[col] = df[col].fillna('').astype(str).str.strip()
    df['promotor'] = df['promotor'].str.upper()
    df['supervisor_asignado'] = df['supervisor_asignado'].str.upper()
    df['negocio'] = df['negocio'].str.upper()
    df['periodo'] = df['periodo'].str.strip()
    df['licencia_alcohol'] = df['licencia_alcohol'].str.upper()
    df['cnc_u3m'] = df['cnc_u3m'].str.upper()
    df['cliente'] = df['cliente'].str.replace(r'\.0$', '', regex=True).str.lstrip('0').replace('', '0')

    no_validos = df[
        ~df['periodo'].str.fullmatch(r'\d{4}-(0[1-9]|1[0-2])') |
        ~df['negocio'].isin(('CZA','UNG')) |
        ~df['cnc_u3m'].isin(('SI','TRUE','1')) |
        df['cliente'].eq('0') |
        df['promotor'].isin(('','VENDEDOR LIBRE','SIN PREVENTA','SIN ASIGNAR','NO ASIGNADO')) |
        (df['negocio'].eq('CZA') & ~df['licencia_alcohol'].eq('SI'))
    ]
    if not no_validos.empty:
        raise ValueError(f'El archivo incluye {len(no_validos)} filas no elegibles. Generá nuevamente la cartera desde el motor CNC; no se importaron datos.')
    periodos = df['periodo'].unique().tolist()
    if len(periodos) != 1:
        raise ValueError('Cada importación debe corresponder a un único mes de cierre.')
    if df.duplicated(['periodo','cliente','negocio']).any():
        raise ValueError('El archivo repite clientes dentro del mismo período y negocio.')
    if df.groupby(['periodo','cliente'])['promotor'].nunique().gt(1).any():
        raise ValueError('Hay clientes asignados a distintos promotores dentro de un mismo período.')
    return df.to_dict(orient='records')


class Store:
    def __init__(self, database_url: str|None=None, sqlite_path: str|Path='data/relevamientos.sqlite'):
        if database_url:
            if database_url.startswith('postgres://'):
                database_url = 'postgresql://' + database_url[len('postgres://'):]
            if database_url.startswith('postgresql://'):
                database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
            if not database_url.startswith(('postgresql+psycopg://','sqlite:')):
                raise ValueError('DATABASE_URL debe ser PostgreSQL o SQLite.')
            url = database_url
        else:
            p = Path(sqlite_path).resolve()
            p.parent.mkdir(parents=True,exist_ok=True)
            url = 'sqlite:///' + str(p)
        self.engine = create_engine(url, pool_pre_ping=True, future=True,
                                    connect_args={'check_same_thread': False, 'timeout': 20} if url.startswith('sqlite:') else {})
        if url.startswith('sqlite:'):
            with self.engine.connect() as conn:
                conn.exec_driver_sql('PRAGMA busy_timeout=20000')
                conn.exec_driver_sql('PRAGMA journal_mode=WAL')
        self.init()

    def init(self):
        sqls = [
            """CREATE TABLE IF NOT EXISTS campana (
                 periodo TEXT NOT NULL, cliente TEXT NOT NULL, negocio TEXT NOT NULL,
                 promotor TEXT NOT NULL, supervisor TEXT NOT NULL,
                 fantasia TEXT NOT NULL, razon_social TEXT NOT NULL,
                 ultima_compra TEXT NOT NULL, fecha_carga TEXT NOT NULL,
                 PRIMARY KEY(periodo,cliente,negocio))""",
            """CREATE TABLE IF NOT EXISTS enlaces (
                 promotor TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
                 creado TEXT NOT NULL, habilitado INTEGER NOT NULL DEFAULT 1)""",
            """CREATE TABLE IF NOT EXISTS respuestas (
                 periodo TEXT NOT NULL, cliente TEXT NOT NULL, negocio TEXT NOT NULL,
                 promotor TEXT NOT NULL, motivo TEXT NOT NULL, comentario TEXT NOT NULL,
                 respondido TEXT NOT NULL,
                 PRIMARY KEY(periodo,cliente,negocio))""",
            """CREATE TABLE IF NOT EXISTS historial (
                 evento TEXT PRIMARY KEY, periodo TEXT NOT NULL, cliente TEXT NOT NULL,
                 negocio TEXT NOT NULL, promotor TEXT NOT NULL, motivo TEXT NOT NULL,
                 comentario TEXT NOT NULL, registrado TEXT NOT NULL, operacion TEXT NOT NULL)""",
            'CREATE INDEX IF NOT EXISTS ix_campana_promotor ON campana(promotor,periodo)',
            'CREATE INDEX IF NOT EXISTS ix_respuestas_promotor ON respuestas(promotor,periodo)',
        ]
        with self.engine.begin() as conn:
            for sql in sqls:
                conn.execute(text(sql))

    def _fetch(self, sql: str, **params) -> list[dict]:
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]

    def total(self) -> int:
        return self._fetch('SELECT COUNT(*) AS n FROM campana')[0]['n']

    def periods(self) -> list[str]:
        return [r['periodo'] for r in self._fetch('SELECT DISTINCT periodo FROM campana ORDER BY periodo DESC')]

    def promoters(self, period: str|None=None) -> list[str]:
        sql = 'SELECT DISTINCT promotor FROM campana'
        if period:
            sql += ' WHERE periodo=:p'
        return [r['promotor'] for r in self._fetch(sql+' ORDER BY promotor',p=period)]

    def seed(self, records: list[dict], replace_period: bool=False) -> int:
        if not records:
            return 0
        period = records[0]['periodo']
        if any(r['periodo'] != period for r in records):
            raise ValueError('La campaña tiene períodos mezclados.')
        with self.engine.begin() as conn:
            if replace_period:
                # Evitamos dejar respuestas obsoletas después de cambiar la cartera.
                # Las respuestas fuera del nuevo padrón se conservan históricamente
                # pero no se muestran como cartera activa en los reportes.
                conn.execute(text('DELETE FROM campana WHERE periodo=:p'), {'p':period})
            q = text('''INSERT INTO campana
                (periodo,cliente,negocio,promotor,supervisor,fantasia,razon_social,ultima_compra,fecha_carga)
                VALUES (:periodo,:cliente,:negocio,:promotor,:supervisor,:fantasia,:razon_social,:ultima_compra,:fecha_carga)
                ON CONFLICT (periodo,cliente,negocio) DO UPDATE SET
                promotor=excluded.promotor,supervisor=excluded.supervisor,
                fantasia=excluded.fantasia,razon_social=excluded.razon_social,
                ultima_compra=excluded.ultima_compra,fecha_carga=excluded.fecha_carga''')
            for r in records:
                conn.execute(q, dict(periodo=r['periodo'],cliente=r['cliente'],negocio=r['negocio'],
                                     promotor=r['promotor'],supervisor=r['supervisor_asignado'],
                                     fantasia=r['fantasia'],razon_social=r['razon_social'],
                                     ultima_compra=r['ultima_compra'],fecha_carga=timestamp()))
        return len(records)

    def campaign(self, period: str, promoter: str|None=None) -> list[dict]:
        sql = '''SELECT c.periodo,c.cliente,c.negocio,c.promotor,c.supervisor,c.fantasia,
                  c.razon_social,c.ultima_compra,r.motivo,r.comentario,r.respondido
                 FROM campana c LEFT JOIN respuestas r
                 ON (c.periodo=r.periodo AND c.cliente=r.cliente AND c.negocio=r.negocio AND c.promotor=r.promotor)
                 WHERE c.periodo=:p'''
        if promoter:
            sql += ' AND c.promotor=:pr'
        sql += ' ORDER BY c.negocio,c.fantasia,c.cliente'
        return self._fetch(sql, p=period, pr=promoter)

    def progress(self, period: str) -> list[dict]:
        return self._fetch('''SELECT c.promotor,c.supervisor,COUNT(*) AS asignados,
            SUM(CASE WHEN r.motivo IS NULL THEN 0 ELSE 1 END) AS respondidos,
            SUM(CASE WHEN c.negocio='CZA' THEN 1 ELSE 0 END) AS cza,
            SUM(CASE WHEN c.negocio='UNG' THEN 1 ELSE 0 END) AS ung
            FROM campana c LEFT JOIN respuestas r ON
            c.periodo=r.periodo AND c.cliente=r.cliente AND c.negocio=r.negocio AND c.promotor=r.promotor
            WHERE c.periodo=:p GROUP BY c.promotor,c.supervisor ORDER BY c.promotor''', p=period)

    def generate_links(self, period: str) -> list[dict]:
        """Rota todos los enlaces de los promotores de un período.

        Devuelve tokens originales una sola vez; la BD guarda solo SHA-256.
        """
        promoters = self.promoters(period)
        result = []
        with self.engine.begin() as conn:
            for pr in promoters:
                t = secrets.token_urlsafe(32)
                conn.execute(text('''INSERT INTO enlaces(promotor,token_hash,creado,habilitado)
                    VALUES (:p,:h,:d,1) ON CONFLICT (promotor) DO UPDATE
                    SET token_hash=excluded.token_hash,creado=excluded.creado,habilitado=1'''),
                    dict(p=pr,h=digest(t),d=timestamp()))
                result.append({'promotor':pr,'token':t})
        return result

    def authenticate(self, token: str) -> str|None:
        if not token or len(token)<24 or len(token)>300:
            return None
        d = digest(token)
        rows = self._fetch('SELECT promotor FROM enlaces WHERE token_hash=:h AND habilitado=1',h=d)
        return rows[0]['promotor'] if rows else None

    def record(self, period: str, cliente: str, negocio: str, promoter: str,
               reason: str, note: str='') -> None:
        if reason not in MOTIVOS:
            raise ValueError('Motivo no permitido.')
        note = (note or '').strip()
        if reason == 'Otro' and not note:
            raise ValueError('Especificá el motivo en el campo Otro.')
        if len(note)>700:
            raise ValueError('El comentario supera los 700 caracteres.')
        now = timestamp()
        with self.engine.begin() as conn:
            autorizado = conn.execute(text('''SELECT 1 FROM campana WHERE periodo=:p AND cliente=:c
                      AND negocio=:n AND promotor=:pr'''), dict(p=period,c=cliente,n=negocio,pr=promoter)).first()
            if not autorizado:
                raise PermissionError('El cliente no corresponde a este promotor y período.')
            was = conn.execute(text('''SELECT 1 FROM respuestas WHERE periodo=:p AND cliente=:c
                                     AND negocio=:n'''), dict(p=period,c=cliente,n=negocio)).first()
            conn.execute(text('''INSERT INTO respuestas(periodo,cliente,negocio,promotor,motivo,comentario,respondido)
                VALUES (:p,:c,:n,:pr,:mo,:co,:now) ON CONFLICT(periodo,cliente,negocio) DO UPDATE
                SET promotor=excluded.promotor,motivo=excluded.motivo,
                    comentario=excluded.comentario,respondido=excluded.respondido'''),
                dict(p=period,c=cliente,n=negocio,pr=promoter,mo=reason,co=note,now=now))
            conn.execute(text('''INSERT INTO historial(evento,periodo,cliente,negocio,promotor,motivo,comentario,registrado,operacion)
                 VALUES (:e,:p,:c,:n,:pr,:mo,:co,:now,:op)'''),
                 dict(e=uuid.uuid4().hex,p=period,c=cliente,n=negocio,pr=promoter,mo=reason,co=note,now=now,
                      op='CORRECCION' if was else 'ALTA'))

    def report(self, period: str) -> list[dict]:
        return self._fetch('''SELECT c.periodo,c.promotor,c.supervisor,c.negocio,c.cliente,
            c.fantasia,c.razon_social,c.ultima_compra,
            COALESCE(r.motivo,'PENDIENTE') AS motivo,COALESCE(r.comentario,'') AS comentario,
            COALESCE(r.respondido,'') AS respondido
            FROM campana c LEFT JOIN respuestas r ON
            c.periodo=r.periodo AND c.cliente=r.cliente AND c.negocio=r.negocio AND c.promotor=r.promotor
            WHERE c.periodo=:p ORDER BY c.promotor,c.negocio,c.fantasia''',p=period)

    def audit(self, period: str) -> list[dict]:
        return self._fetch('''SELECT periodo,cliente,negocio,promotor,motivo,comentario,registrado,operacion
            FROM historial WHERE periodo=:p ORDER BY registrado DESC''', p=period)

    # ---------- Operación unificada por cliente (CZA + UNG = una tarjeta) ----------
    def unique_clients(self, period: str, promoter: str|None=None) -> list[dict]:
        """Una fila por cliente, aunque tenga dos unidades de negocio.

        Conservamos el detalle por negocio en campana/respuestas para auditoría.
        Si una encuesta histórica solo cubre un negocio, se considera pendiente
        hasta que estén respondidos TODOS los negocios de la campaña.
        """
        rows = self.campaign(period, promoter)
        grouped = {}
        for r in rows:
            key = (r['periodo'], r['cliente'])
            if key not in grouped:
                grouped[key] = {
                    'periodo':r['periodo'],'cliente':r['cliente'],
                    'promotor':r['promotor'],'supervisor':r['supervisor'],
                    'fantasia':r['fantasia'],'razon_social':r['razon_social'],
                    'negocios':[], 'ultima_compra':{}, 'motivo':'', 'comentario':'',
                    'respondido':'', 'completo':False, 'respondidos_negocio':0,
                }
            g = grouped[key]
            if g['promotor'] != r['promotor']:
                raise ValueError(f'Cliente {r["cliente"]} asignado a dos promotores en el mismo período.')
            g['negocios'].append(r['negocio'])
            g['ultima_compra'][r['negocio']] = r['ultima_compra']
            if r['motivo']:
                g['respondidos_negocio'] += 1
                if not g['respondido'] or r['respondido'] > g['respondido']:
                    g['respondido'] = r['respondido']
                    g['motivo'] = r['motivo']
                    g['comentario'] = r['comentario']
        for r in grouped.values():
            r['negocios'] = sorted(r['negocios'], key=lambda v: {'CZA':0,'UNG':1}.get(v,10))
            r['completo'] = r['respondidos_negocio'] == len(r['negocios'])
        return sorted(grouped.values(), key=lambda r: (r['completo'],r['fantasia'].casefold(),r['cliente']))

    def resolve_promoter(self, period: str, identifier: str) -> str|None:
        """Identificación amigable. NO autenticación: requiere PIN en producción."""
        value = ' '.join((identifier or '').upper().split())
        if not value:
            return None
        promoters = self.promoters(period)
        names = [p for p in promoters if ' '.join(p.upper().split()) == value]
        if len(names) == 1:
            return names[0]
        # Código de un cliente asignado al promotor. Puede no ser exclusivo entre meses;
        # la búsqueda siempre queda limitada al período seleccionado.
        if value.replace(' ', '').isdigit():
            code = str(int(value))
            rs = self._fetch('''SELECT DISTINCT promotor FROM campana
                      WHERE periodo=:p AND cliente=:c''',p=period,c=code)
            if len(rs) == 1:
                return rs[0]['promotor']
        return None

    def record_for_client(self, period: str, cliente: str, promoter: str,
                          reason: str, note: str='') -> int:
        """UNA acción por cliente, almacenada transaccionalmente en todos sus negocios.

        Una sola respuesta se replica a CZA y UNG si ambos son CNC.
        Si la validación falla no se guarda ninguna fila.
        """
        if reason not in MOTIVOS:
            raise ValueError('Motivo no permitido.')
        note = (note or '').strip()
        if reason == 'Otro' and not note:
            raise ValueError('Especificá el motivo en Otro.')
        if len(note) > 700:
            raise ValueError('El comentario supera los 700 caracteres.')
        now = timestamp()
        with self.engine.begin() as conn:
            negocios = [r[0] for r in conn.execute(text('''SELECT negocio FROM campana
                WHERE periodo=:p AND cliente=:c AND promotor=:pr ORDER BY negocio'''),
                dict(p=period,c=cliente,pr=promoter)).all()]
            if not negocios:
                raise PermissionError('El cliente no corresponde a este promotor y período.')
            for negocio in negocios:
                params=dict(p=period,c=cliente,n=negocio,pr=promoter,mo=reason,co=note,now=now)
                existing = conn.execute(text('''SELECT 1 FROM respuestas
                    WHERE periodo=:p AND cliente=:c AND negocio=:n'''),params).first()
                conn.execute(text('''INSERT INTO respuestas
                    (periodo,cliente,negocio,promotor,motivo,comentario,respondido)
                    VALUES (:p,:c,:n,:pr,:mo,:co,:now)
                    ON CONFLICT(periodo,cliente,negocio) DO UPDATE SET
                    promotor=excluded.promotor,motivo=excluded.motivo,
                    comentario=excluded.comentario,respondido=excluded.respondido'''),params)
                conn.execute(text('''INSERT INTO historial
                    (evento,periodo,cliente,negocio,promotor,motivo,comentario,registrado,operacion)
                    VALUES (:e,:p,:c,:n,:pr,:mo,:co,:now,:op)'''),
                    dict(params, e=uuid.uuid4().hex,op='CORRECCION' if existing else 'ALTA'))
        return len(negocios)

    def progress_unique(self, period: str) -> list[dict]:
        groups = {}
        for r in self.unique_clients(period):
            pr=r['promotor']
            if pr not in groups:
                groups[pr]={'promotor':pr,'supervisor':r['supervisor'],'clientes':0,
                            'respondidos':0,'pendientes':0,'casos_cza':0,'casos_ung':0}
            g=groups[pr]
            g['clientes']+=1
            g['respondidos']+=int(r['completo'])
            g['pendientes']+=int(not r['completo'])
            g['casos_cza']+=int('CZA' in r['negocios'])
            g['casos_ung']+=int('UNG' in r['negocios'])
        return sorted(groups.values(),key=lambda g:g['promotor'])

    def report_unique(self, period: str) -> list[dict]:
        out=[]
        for r in self.unique_clients(period):
            out.append({'periodo':period,'cliente':r['cliente'],
                        'fantasia':r['fantasia'],'razon_social':r['razon_social'],
                        'promotor':r['promotor'],'supervisor':r['supervisor'],
                        'negocios':' + '.join(r['negocios']),
                        'motivo':r['motivo'] if r['completo'] else 'PENDIENTE',
                        'comentario':r['comentario'] if r['completo'] else '',
                        'respondido':r['respondido'] if r['completo'] else ''})
        return out

    def ensure_pins_table(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(text('''CREATE TABLE IF NOT EXISTS acceso_promotor (
                promotor TEXT PRIMARY KEY, salt TEXT NOT NULL,
                pin_hash TEXT NOT NULL, habilitado INTEGER NOT NULL DEFAULT 1)'''))

    def issue_pins(self, period: str, only_missing=True) -> list[dict]:
        """Códigos aleatorios para enviar individualmente; se muestran una vez."""
        self.ensure_pins_table()
        result=[]
        alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        with self.engine.begin() as conn:
            for name in self.promoters(period):
                existing=conn.execute(text('SELECT 1 FROM acceso_promotor WHERE promotor=:pr'),{'pr':name}).first()
                if only_missing and existing:
                    continue
                pin=''.join(secrets.choice(alphabet) for _ in range(8))
                salt=secrets.token_hex(16)
                h=hashlib.pbkdf2_hmac('sha256',pin.encode(),bytes.fromhex(salt),260000).hex()
                conn.execute(text('''INSERT INTO acceso_promotor(promotor,salt,pin_hash,habilitado)
                    VALUES (:pr,:salt,:hash,1) ON CONFLICT(promotor) DO UPDATE SET
                    salt=excluded.salt,pin_hash=excluded.pin_hash,habilitado=1'''),
                    {'pr':name,'salt':salt,'hash':h})
                result.append({'promotor':name,'codigo_acceso':pin})
        return result

    def check_pin(self, promoter:str, pin:str)->bool:
        self.ensure_pins_table()
        rows=self._fetch('SELECT salt,pin_hash FROM acceso_promotor WHERE promotor=:pr AND habilitado=1',pr=promoter)
        if len(rows)!=1 or not pin or len(pin)>50:
            return False
        row=rows[0]
        h=hashlib.pbkdf2_hmac('sha256',pin.strip().upper().encode(),bytes.fromhex(row['salt']),260000).hex()
        return hmac.compare_digest(h,row['pin_hash'])
