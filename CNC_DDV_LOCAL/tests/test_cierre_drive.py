"""Pruebas de cierres desde Drive, sin credenciales ni cambios remotos."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from cierre_mensual import (detectar_ventas_cierre, comprobar_reporte_al_cierre,
                            integrar_ventas,integracion_cierre_clientes,leer_index)
from logica import cartera_al_cierre,cartera_vigencia_3m


def maestro_ejemplo():
    return pd.DataFrame([
        dict(cliente='1',alta='2024-01-01',anulado='NO',fecha_baja='',promotor='ANA',
             fantasia='Almacen 1',razon_social='Uno',licencia_alcohol='SI'),
        dict(cliente='2',alta='2024-01-01',anulado='NO',fecha_baja='',promotor='JUAN',
             fantasia='Almacen 2',razon_social='Dos',licencia_alcohol='NO'),
        dict(cliente='3',alta='2024-01-01',anulado='SI',fecha_baja='2025-07-10',promotor='JUAN',
             fantasia='Almacen 3',razon_social='Tres',licencia_alcohol='SI'),
    ])


def reporte(ids):
    return pd.DataFrame([{
        'Cliente':str(i), 'Razon social':f'Razón {i}', 'Nombre de fantasia':f'Tienda {i}',
        'Alta fecha':'2024-01-01','Anulado':'NO', 'Licencia alcohol':'SI',
        'Fuerza de venta 1 Descripcion personal comercial':'ANA',
        'Fuerza de venta 1 Ruta de venta':'123',
    } for i in ids])


def test_archivo_mensual_y_no_actual():
    a=[dict(name='ventadiaria.txt',modifiedTime='2026-11-30T12:00:00Z'),
       dict(name='ventadiaria noviembre.txt',modifiedTime='2026-12-01T14:00:00Z'),
       dict(name='ventadiaria bultos noviembre.txt',modifiedTime='2026-12-02T14:00:00Z')]
    assert detectar_ventas_cierre(a,'2026-11')['name']=='ventadiaria noviembre.txt'
    assert detectar_ventas_cierre(a,'2026-12') is None


def test_reporte_debe_ser_posterior_al_fin():
    assert not comprobar_reporte_al_cierre('2026-11-30T20:00:00Z','2026-11')
    assert comprobar_reporte_al_cierre('2026-12-01T13:00:00Z','2026-11')
    assert not comprobar_reporte_al_cierre('2026-10-26T19:30:38.538Z','2026-10')


def test_inferencia_no_inventa_fecha_y_no_borra_historia():
    nuevo,stats=integracion_cierre_clientes(maestro_ejemplo(),reporte(['1','4']),'2026-11')
    x=nuevo.set_index('cliente')
    assert stats['bajas_detectadas']==1
    assert stats['altas_nuevas']==1
    assert x.at['2','anulado']=='SI'
    assert x.at['2','baja_inferida_mes']=='2026-11'
    assert not str(x.at['2','fecha_baja']).strip()
    for col in ('alta','fecha_baja'):
        nuevo[col]=pd.to_datetime(nuevo[col],errors='coerce')
    assert '2' in cartera_al_cierre(nuevo,'2026-10').cliente.tolist()
    assert '2' not in cartera_al_cierre(nuevo,'2026-11').cliente.tolist()
    hist,meta=cartera_vigencia_3m(nuevo,'2026-11')
    u=hist.set_index('cliente').loc['2']
    assert 'día sin confirmar' in u.alerta
    assert 'detectada' in u['estado_2026-11']
    assert u['estado_2026-10']=='🟢 Vigente'
    assert meta['bajas_ventana']>=1


def test_ventas_no_duplicadas_en_cierre():
    orig=pd.DataFrame([
        dict(mes='2026-10',cliente='1',unidad='UNG',neto=50.0),
        dict(mes='2026-11',cliente='1',unidad='UNG',neto=12.0),
    ])
    nov=pd.DataFrame([
        dict(mes='2026-11',cliente='1',unidad='UNG',neto=100.0),
        dict(mes='2026-11',cliente='1',unidad='UNG',neto=25.0),
    ])
    actual=integrar_ventas(orig,nov,'2026-11').set_index(['mes','cliente','unidad'])
    assert actual.loc[('2026-11','1','UNG'),'neto']==125
    assert actual.loc[('2026-10','1','UNG'),'neto']==50


def test_registry_default():
    assert leer_index(None)=={'version':1,'cierres':{}}
