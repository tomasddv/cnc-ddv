"""Relevamiento móvil CNC DDV · una tarjeta por cliente, aunque figure en CZA y UNG."""
from __future__ import annotations

import csv
import hmac
import io
import os
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from store import MOTIVOS, Store, preparar_csv

BASE = Path(__file__).resolve().parent
st.set_page_config(page_title='Relevamiento CNC | DDV', page_icon='🧭', layout='centered', initial_sidebar_state='collapsed')


def setting(name: str, default: str='') -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


LOCAL_DEMO = setting('LOCAL_DEMO') == '1'
PIN_REQUIRED = not LOCAL_DEMO
ADMIN_PASSWORD = setting('ADMIN_PASSWORD')
DB_URL = setting('DATABASE_URL')
DB_PATH = setting('CNC_RELEVAMIENTOS_DB', str(BASE.parent / 'datos_compartidos' / 'relevamientos.sqlite'))


@st.cache_resource(show_spinner=False)
def storage(url: str) -> Store:
    store = Store(database_url=url or None, sqlite_path=DB_PATH)
    # Primer inicio: importar exclusivamente el CSV de la campaña CNC validada.
    if store.total() == 0:
        path = BASE/'data'/'campana_2026-10.csv'
        if path.exists():
            store.seed(preparar_csv(path.read_bytes()))
    return store


if not LOCAL_DEMO and not DB_URL:
    st.error('Para publicar los relevamientos de varios celulares, configurá DATABASE_URL con PostgreSQL compartido. No se permite guardar respuestas en un archivo temporal del servidor.')
    st.stop()

try:
    db = storage(DB_URL)
except Exception as ex:
    st.error(f'No pude iniciar la base de relevamientos: {ex}')
    st.stop()

st.markdown('''
<style>
  :root {--brand:#123f63;--mint:#0d7667;}
  #MainMenu, footer, .stDeployButton {visibility:hidden}
  .block-container {max-width:800px!important; padding-top:1.25rem!important; padding-bottom:5rem}
  div[data-testid="stAppViewContainer"] {background: #f5f8fc}
  div[data-testid="stMarkdownContainer"] p {line-height:1.45}
  .brand {font-size:12px;font-weight:800;letter-spacing:.16em;color:#317e9b; margin-bottom:.15rem}
  .hero {font-weight:850; font-size:clamp(1.65rem,5vw,2.5rem);letter-spacing:-.045em;color:#152e4c;line-height:1.1; margin:.15rem 0 .5rem}
  .intro {color:#556982;font-size:.95rem;margin-bottom:1.3rem}
  .client-card{background:#fff;border:1px solid #dbe5ef;border-radius:22px; padding:22px 23px;
     box-shadow:0 8px 28px rgba(15,42,70,.055);margin:12px 0 18px}
  .eyebrow{font-size:11px;font-weight:850;text-transform:uppercase;color:#547692;letter-spacing:.1em;margin-bottom:8px}
  .name{font-size:clamp(1.65rem,6vw,2.35rem);font-weight:850;line-height:1.15;color:#122b46;margin-bottom:12px}
  .meta-label{font-weight:700;color:#587087;font-size:12px;margin-bottom:4px}
  .meta-value{font-weight:700;color:#203953;font-size:15px;margin-bottom:16px;overflow-wrap:anywhere}
  .pill {display:inline-block;background:#e5f4ef;color:#135e50;font-weight:800;font-size:12px;
     border-radius:999px;padding:7px 12px;margin:2px 8px 6px 0}
  .pill-cza{background:#e5f1fb;color:#145b96}
  div.stButton > button {border-radius:14px;min-height:52px;font-weight:760;font-size:1.03rem;}
  div.stButton > button[kind="primary"]{background:#116c78;color:white;border:1px solid #116c78}
  div.stButton > button:hover{border-color:#1c8d9a}
  input,textarea{border-radius:12px!important}
  div[data-testid="stMetric"]{border:1px solid #dae5ef;background:#fff;border-radius:16px;padding:12px 16px}
  div[data-testid="stMetricLabel"]{color:#5a718a}
  div[data-testid="stMetricValue"]{font-size:1.65rem}
  div[data-testid="stProgressBar"] > div > div {background:#11a389}
  .smallnote{color:#6a7d92;font-size:13px}
</style>
''', unsafe_allow_html=True)


def brand(title: str, subtitle: str=''):
    st.markdown('<div class="brand">DISTRIBUIDORA DEL VALLE · CNC</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="hero">{escape(title)}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="intro">{escape(subtitle)}</div>', unsafe_allow_html=True)


def csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b''
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=rows[0].keys(), extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return ('\ufeff'+out.getvalue()).encode('utf-8')


def choose_view(view: str):
    st.session_state['view'] = view
    st.rerun()


def render_client(item: dict, label: str):
    business=''.join(f'<span class="pill {"pill-cza" if n=="CZA" else ""}">{escape(n)}</span>' for n in item['negocios'])
    st.markdown('''<section class="client-card">
      <div class="eyebrow">''' + escape(label) + '''</div>
      <div class="name">''' + escape(item['fantasia'] or 'Comercio sin nombre') + '''</div>
      <div class="meta-label">Razón social</div>
      <div class="meta-value">''' + escape(item['razon_social'] or 'Sin dato') + '''</div>
      <div class="meta-label">Código de cliente</div>
      <div class="meta-value">''' + escape(item['cliente']) + '''</div>
      <div class="meta-label">Negocios sin compra</div>
      <div>''' + business + '''</div>
    </section>''', unsafe_allow_html=True)
    if len(item['negocios'])==2:
        st.caption('Una respuesta completará CZA y UNG para este cliente.')


def store_answer(item: dict, answer: str, note: str=''):
    try:
        n = db.record_for_client(item['periodo'],item['cliente'],item['promotor'],answer,note)
        st.session_state['saved_notice'] = f'✓ {item["fantasia"]}: relevado para {" y ".join(item["negocios"])}.'
        st.session_state['other_open'] = False
        st.session_state['mode'] = 'pending'
        st.session_state['skip_index'] = 0
        st.rerun()
    except Exception as exc:
        st.error(f'No se guardó la respuesta: {exc}')


def login_view():
    brand('Motivos de no compra','Un cliente por vez. Cuatro opciones. Sin planillas.')
    if LOCAL_DEMO:
        st.info('Modo de prueba en esta computadora: identificación simplificada. En Internet se exige un código personal.')
    periods = db.periods()
    if not periods:
        st.warning('Todavía no hay una campaña CNC cargada.')
        return
    period = periods[0] if len(periods)==1 else st.selectbox('Mes del relevamiento',periods)
    with st.form('login_promotor', border=True):
        st.markdown('**Ingresá a tu cartera**')
        identifier = st.text_input('Tu nombre completo o código de un cliente asignado',placeholder='Ej.: NICASTRO LUCAS o 5542')
        pin = st.text_input('Código personal de acceso',type='password',help='Cada promotor recibe su código del administrador') if PIN_REQUIRED else ''
        sent = st.form_submit_button('Entrar a mis clientes',type='primary',use_container_width=True)
    if sent:
        promotor = db.resolve_promoter(period,identifier)
        if not promotor:
            st.error('No encontramos el nombre o código en esta campaña. Revisá lo ingresado.')
        elif PIN_REQUIRED and not db.check_pin(promotor,pin):
            st.error('El código de acceso no coincide. Consultá con el administrador.')
        else:
            st.session_state.update({'view':'promoter','promotor':promotor,'period':period,'mode':'pending',
                                     'skip_index':0,'other_open':False})
            st.rerun()
    if LOCAL_DEMO:
        with st.expander('¿No recordás el nombre exacto?'):
            st.write('En la prueba local podés elegir uno de estos nombres y copiarlo en el campo superior:')
            st.write(', '.join(db.promoters(period)))
    st.divider()
    if st.button('🔐 Control de supervisión',use_container_width=True):
        choose_view('admin')


def promoter_view():
    promotor=st.session_state.get('promotor','')
    period=st.session_state.get('period','')
    if not promotor or period not in db.periods():
        st.session_state['view']='login'
        st.rerun()
    left,right=st.columns([4,1])
    with left:
        brand('Mi recorrido CNC',f'{promotor} · {period}')
    with right:
        if st.button('Salir',key='logout'):
            st.session_state['view']='login'
            st.session_state.pop('promotor',None)
            st.rerun()
    clients=db.unique_clients(period,promotor)
    completed=[r for r in clients if r['completo']]
    pending=[r for r in clients if not r['completo']]
    c1,c2,c3=st.columns(3)
    c1.metric('Pendientes',len(pending))
    c2.metric('Listos',len(completed))
    c3.metric('Avance',f'{len(completed)/len(clients):.0%}' if clients else '—')
    st.progress(len(completed)/len(clients) if clients else 1.0)
    if 'saved_notice' in st.session_state:
        st.success(st.session_state.pop('saved_notice'))
    mode=st.session_state.get('mode','pending')
    if mode=='edit':
        if not completed:
            st.session_state['mode']='pending';st.rerun()
        options={f'{x["fantasia"]} · {x["cliente"]}':x for x in completed}
        st.info('Estás corrigiendo una respuesta guardada.')
        chosen=st.selectbox('Cliente ya relevado',list(options),key='edit_target')
        item=options[chosen]
        if st.button('← Volver a pendientes'):
            st.session_state['mode']='pending';st.rerun()
        render_client(item,'Revisar respuesta guardada')
        st.caption(f'Motivo anterior: {item["motivo"]}'+(f' · {item["comentario"]}' if item['comentario'] else ''))
    elif pending:
        pos=int(st.session_state.get('skip_index',0))%len(pending)
        item=pending[pos]
        st.markdown(f'**Cliente pendiente {pos+1} de {len(pending)}**')
        render_client(item,'¿Por qué dejó de comprar?')
    else:
        st.balloons()
        st.success('¡Terminaste todos tus clientes! No quedan relevamientos pendientes de esta campaña.')
        item=None
    if item:
        st.markdown('**Tocá el motivo principal:**')
        a,b=st.columns(2)
        with a:
            if st.button('💸  Sin dinero',use_container_width=True,key=f'sin_{mode}_{item["cliente"]}'):
                store_answer(item,'Sin dinero')
            if st.button('🛒  Super / mayorista',use_container_width=True,key=f'sup_{mode}_{item["cliente"]}'):
                store_answer(item,'Compra en súper/mayorista')
        with b:
            if st.button('🚪  Cerrado',use_container_width=True,key=f'cer_{mode}_{item["cliente"]}'):
                store_answer(item,'Cerrado')
            if st.button('✍️  Otro motivo',use_container_width=True,key=f'otr_{mode}_{item["cliente"]}'):
                st.session_state['other_open']=True
        if st.session_state.get('other_open'):
            with st.form(f'otro_{item["cliente"]}'):
                other = st.text_area('Escribí brevemente el motivo',placeholder='Ej.: tiene stock, trabaja por temporada...',max_chars=700)
                if st.form_submit_button('Guardar y pasar al siguiente',type='primary',use_container_width=True):
                    store_answer(item,'Otro',other)
        if mode=='pending' and len(pending)>1:
            c1,c2=st.columns(2)
            with c1:
                if st.button('Saltar por ahora →',use_container_width=True):
                    st.session_state['skip_index']=(int(st.session_state.get('skip_index',0))+1)%len(pending)
                    st.session_state['other_open']=False
                    st.rerun()
            with c2:
                if st.button('↩ Empezar desde el primero',use_container_width=True):
                    st.session_state['skip_index']=0
                    st.session_state['other_open']=False
                    st.rerun()
    if completed:
        with st.expander(f'✅ Ver mis {len(completed)} clientes completados'):
            st.dataframe(pd.DataFrame([{'Código':x['cliente'],'Comercio':x['fantasia'],
                'Negocio':'+'.join(x['negocios']),'Motivo':x['motivo']} for x in completed]),
                use_container_width=True,hide_index=True)
            if mode!='edit' and st.button('Corregir una respuesta',use_container_width=True):
                st.session_state['mode']='edit'
                st.session_state['other_open']=False
                st.rerun()
    st.caption('Tus respuestas quedan guardadas. Solo ves los clientes que te fueron asignados.')


def admin_view():
    brand('Control de relevamientos','Seguimiento de cada promotor y exportación para el tablero CNC.')
    if st.button('← Volver al inicio'):
        st.session_state['view']='login';st.rerun()
    if not st.session_state.get('admin_ok'):
        if LOCAL_DEMO:
            st.session_state['admin_ok']=True
        elif not ADMIN_PASSWORD:
            st.error('Control no configurado. Definí ADMIN_PASSWORD en los Secrets del servidor.')
            st.stop()
        else:
            with st.form('admin_login'):
                p=st.text_input('Clave de administrador',type='password')
                if st.form_submit_button('Abrir control',type='primary'):
                    if hmac.compare_digest(p,ADMIN_PASSWORD):
                        st.session_state['admin_ok']=True;st.rerun()
                    else:
                        st.error('Clave incorrecta.')
            st.stop()
    periods=db.periods()
    if not periods:
        st.warning('No hay períodos cargados. Importá una campaña CSV validada.');return
    month=st.selectbox('Período',periods,key='admin_period')
    progress=db.progress_unique(month)
    unique=db.report_unique(month)
    full=db.report(month)
    total=len(unique);done=sum(r['motivo']!='PENDIENTE' for r in unique)
    c1,c2,c3=st.columns(3)
    c1.metric('Clientes únicos',total)
    c2.metric('Respondidos',done)
    c3.metric('Pendientes',total-done)
    st.progress(done/total if total else 0)
    st.subheader('Avance por promotor')
    if progress:
        panel=pd.DataFrame(progress).rename(columns={
            'promotor':'Promotor','supervisor':'Supervisor','clientes':'Clientes',
            'respondidos':'Listos','pendientes':'Pendientes','casos_cza':'CZA','casos_ung':'UNG'})
        panel['Avance %']=(panel['Listos']/panel['Clientes']*100).round(1)
        st.dataframe(panel,use_container_width=True,hide_index=True)
    else:
        st.info('No hay promotores en este período.')
    st.subheader('Descargar información')
    c1,c2,c3=st.columns(3)
    with c1:
        st.download_button('Clientes (una fila)',csv_bytes(unique),f'cnc_clientes_{month}.csv',
            'text/csv',use_container_width=True)
    with c2:
        st.download_button('Detalle CZA / UNG',csv_bytes(full),f'cnc_negocios_{month}.csv',
            'text/csv',use_container_width=True)
    with c3:
        st.download_button('Avance promotores',csv_bytes(progress),f'cnc_avance_{month}.csv',
            'text/csv',use_container_width=True)
    st.caption('En el detalle por negocio, una respuesta de un cliente de ambos negocios aparece en dos filas para análisis. En el relevamiento se respondió una sola vez.')
    with st.expander('Cargar nueva campaña mensual'):
        st.write('Subí el CSV que genera el motor del dashboard CNC (solo clientes vigentes, con promotor y elegibles).')
        file=st.file_uploader('CSV CNC',type=['csv'],key='campaign_csv')
        replace=st.checkbox('Reemplazar el listado de ese mes si ya existe',value=False)
        if file is not None:
            try:
                records=preparar_csv(file.getvalue())
                st.info(f'{len(records)} casos por negocio; {len({r["cliente"] for r in records})} clientes únicos para {records[0]["periodo"]}.')
                if st.button('Confirmar importación',type='primary'):
                    db.seed(records,replace_period=replace)
                    st.success('Campaña cargada. Las respuestas ya registradas se conservaron.')
                    st.rerun()
            except Exception as ex:
                st.error(str(ex))
    with st.expander('Códigos personales de acceso (para la publicación)'):
        st.warning('Los códigos generados se muestran una sola vez. Descargalos y entregá el correspondiente a cada promotor por un canal privado.')
        if st.button('Crear códigos para promotores que aún no tienen'):
            st.session_state['new_pins']=db.issue_pins(month,only_missing=True)
        if st.session_state.get('new_pins') is not None:
            pins=st.session_state['new_pins']
            if pins:
                st.download_button('Descargar códigos (privado)',csv_bytes(pins),
                    f'credenciales_promotores_{month}.csv','text/csv',use_container_width=True)
                st.success(f'Se crearon {len(pins)} códigos. Descargalos antes de cerrar.')
            else:
                st.info('Todos los promotores ya tienen código. Para rotarlos, usá la opción siguiente.')
        rotate=st.checkbox('Confirmo que quiero cambiar TODOS los códigos y anular los anteriores')
        if st.button('Regenerar todos los códigos',disabled=not rotate):
            st.session_state['new_pins']=db.issue_pins(month,only_missing=False)
            st.rerun()


view=st.session_state.get('view','login')
if view=='admin':
    admin_view()
elif view=='promoter':
    promoter_view()
else:
    login_view()
