"""Integración motivo promotor -> cuadro/filtro -> plan masivo CNC."""
from pathlib import Path
import pandas as pd
from motivos_relevamiento import MOTIVOS_PROMOTOR, filtrar_motivo_promotor
from planes_masivos import construir_planes_masivos
from store import Store


def fila(cliente,negocio,motivo,comentario=''):
    return {
        'cliente':cliente,'negocio':negocio,'promotor':'P UNO',
        'motivo_relevamiento':motivo,'comentario_relevamiento':comentario,
        'motivo_force':'Precio','motivo':'', 'accion':'','cnc_u3m':True,
        'supervisor_asignado':'BRUNO ISMAEL','fecha_relevamiento':'',
    }


def test_filtro_motivos_y_sin_relevar_ambos_negocios():
    d=pd.DataFrame([
        fila('10','CZA','Sin dinero'),fila('10','NABS','Sin dinero'),
        fila('20','CZA','Cerrado'),fila('30','NABS','Compra en súper/mayorista'),
        fila('40','CZA','Otro','Vende menos'),fila('50','NABS',''),
    ])
    assert len(filtrar_motivo_promotor(d,'Todos'))==6
    assert len(filtrar_motivo_promotor(d,'Sin dinero'))==2
    assert filtrar_motivo_promotor(d,'Sin dinero')['cliente'].unique().tolist()==['10']
    assert filtrar_motivo_promotor(d,'Sin relevar')['cliente'].tolist()==['50']
    assert filtrar_motivo_promotor(d,'Otro')['cliente'].tolist()==['40']
    assert set(MOTIVOS_PROMOTOR)=={'Sin dinero','Cerrado','Compra en súper/mayorista','Otro'}


def test_filtro_preserva_indices_para_seleccion_masiva():
    d=pd.DataFrame([fila('1','CZA','Sin dinero'),fila('2','CZA','Cerrado'),fila('3','NABS','Sin dinero')],index=[14,17,28])
    filtered=filtrar_motivo_promotor(d,'Sin dinero')
    assert filtered.index.tolist()==[14,28]
    seleccionados=filtered.reset_index(drop=True).iloc[[0,1]].to_dict('records')
    planes,resumen=construir_planes_masivos(seleccionados,'2026-10',objetivo='Recuperar',accion='Ofrecer pago flexible',fecha_objetivo='2026-11-30',estado='Pendiente')
    assert len(planes)==2
    assert {x['cliente'] for x in planes}=={'1','3'}
    assert {x['motivo'] for x in planes}=={'Sin dinero'}


def test_motivo_promotor_tiene_preferencia_sobre_force_pero_respeta_motivo_manual():
    filas=[fila('1','CZA','Cerrado'),fila('2','NABS','Otro'),fila('3','NABS',''),fila('4','CZA','Cerrado')]
    filas[-1]['motivo']='Acuerdo comercial'
    planes,_=construir_planes_masivos(filas,'2026-10',objetivo='Recuperar',accion='Volver a contactar',fecha_objetivo='2026-11-30',estado='Pendiente')
    assert [x['motivo'] for x in planes]==['Cerrado','Otro','Precio']  # protege el plan existente
    editados,_=construir_planes_masivos(filas,'2026-10',objetivo='Recuperar',accion='Volver a contactar',fecha_objetivo='2026-11-30',estado='Pendiente',sobrescribir=True)
    assert editados[-1]['motivo']=='Acuerdo comercial'
    comun,_=construir_planes_masivos(filas[:2],'2026-10',objetivo='Recuperar',accion='Volver a contactar',fecha_objetivo='2026-11-30',estado='Pendiente',motivo_comun='Motivo unificado')
    assert {x['motivo'] for x in comun}=={'Motivo unificado'}


def test_nuevas_columnas_y_filtro_estan_en_la_interfaz():
    app=(Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8')
    for text in ('filtrar_motivo_promotor(posibles,motivo_promotor_filtro)',
                 "'motivo_relevamiento':'Motivo promotor'",
                 "'comentario_relevamiento':'Detalle del promotor'",
                 "'fecha_relevamiento':'Fecha relevada'",
                 'qplan,motivo_promotor_filtro])',
                 "actual=dato['motivo'] or motivo_pr or sugerido_force"):
        assert text in app


def test_con_db_compartida_mismo_motivo_se_aplica_ambos_negocios(tmp_path):
    db=Store(sqlite_path=tmp_path/'compartida.sqlite')
    registros=[]
    for neg in ('CZA','UNG'):
        registros.append({'periodo':'2026-10','cliente':'100','negocio':neg,
            'promotor':'P UNO','supervisor_asignado':'BRUNO ISMAEL',
            'fantasia':'COMERCIO','razon_social':'RAZON','ultima_compra':'',
            'licencia_alcohol':'SI','cnc_u3m':'SI','alta':'2025-01-01'})
    db.seed(registros)
    assert db.record_for_client('2026-10','100','P UNO','Sin dinero')==2
    tabla=pd.DataFrame(db.campaign('2026-10'))
    tabla['negocio']=tabla['negocio'].replace({'UNG':'NABS'})
    tabla=tabla.rename(columns={'motivo':'motivo_relevamiento'})
    assert len(filtrar_motivo_promotor(tabla,'Sin dinero'))==2
