"""Regresiones de conexión entre los dos Streamlit, sin iniciar interfaz."""
import tempfile
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from store import Store,preparar_csv
from relevamientos_monitor import resumen_relevamientos,validar_sincronizacion


def example(client,neg,pr='PROMOTOR UNO',su='BRUNO ISMAEL'):
    return dict(periodo='2026-10',cliente=client,negocio=neg,promotor=pr,
        supervisor_asignado=su,fantasia='PRUEBA '+client,razon_social='RAZON '+client,
        ultima_compra='',licencia_alcohol='SI' if neg=='CZA' else 'NO',
        cnc_u3m='SI',alta='2025-01-01')


def test_import_and_shared_store_unique_and_live_alert():
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'shared.sqlite'
        promoter=Store(sqlite_path=path)
        promoter.seed([example('101','CZA'),example('101','UNG'),example('102','UNG'),
                       example('201','CZA','PROMOTOR DOS','HERNAN CASCO')])
        main=Store(sqlite_path=path)
        a,b=resumen_relevamientos(main.campaign('2026-10'))
        assert (a['asignados'].sum(),a['pendientes'].sum(),a['casos_cza'].sum(),a['casos_ung'].sum())==(3,3,2,2)
        assert (len(b),b['estado'].eq('Pendiente').sum())==(3,3)
        # 1 answer stored across the two businesses, same client no longer pending.
        assert promoter.record_for_client('2026-10','101','PROMOTOR UNO','Sin dinero')==2
        a,b=resumen_relevamientos(main.campaign('2026-10'))
        assert (a['respondidos'].sum(),a['pendientes'].sum())==(1,2)
        assert b.loc[b['cliente']=='101','motivo'].iloc[0]=='Sin dinero'
        # Completing second promoter updates only that promoter.
        promoter.record_for_client('2026-10','201','PROMOTOR DOS','Cerrado')
        a,b=resumen_relevamientos(main.campaign('2026-10'),supervisor='BRUNO ISMAEL')
        assert len(a)==1 and a.iloc[0]['pendientes']==1
        a,b=resumen_relevamientos(main.campaign('2026-10'),negocio='CZA')
        assert a['asignados'].sum()==2 and a['pendientes'].sum()==0
        # Reopening main store sees persisted updates (no import or caching).
        reopen=Store(sqlite_path=path)
        c,_=resumen_relevamientos(reopen.campaign('2026-10'))
        assert c['respondidos'].sum()==2


def test_reassign_client_does_not_credit_old_promoters_answer():
    with tempfile.TemporaryDirectory() as d:
        db=Store(sqlite_path=Path(d)/'shared.sqlite')
        db.seed([example('101','CZA')]);db.record_for_client('2026-10','101','PROMOTOR UNO','Cerrado')
        db.seed([example('101','CZA','PROMOTOR DOS','HERNAN CASCO')],replace_period=True)
        a,_=resumen_relevamientos(db.campaign('2026-10'))
        assert a.iloc[0]['respondidos']==0
        assert a.iloc[0]['pendientes']==1


def test_campaign_from_main_data_matches_promoter_package():
    from logica import cargar_clientes,cargar_ventas,generar_casos
    cli=cargar_clientes(ROOT/'data/clientes.csv.gz')
    ventas=cargar_ventas(ROOT/'data/ventas_resumen.csv.gz')
    casos,_=generar_casos(cli,ventas,'2026-10',set(ventas.mes.unique()))
    records=validar_sincronizacion(casos,'2026-10')
    assert len(records)==357
    assert len({r['cliente'] for r in records})==268
    assert len({r['promotor'] for r in records})==13
    seed=preparar_csv((ROOT/'data/campana_2026-10.csv').read_bytes())
    assert {(r['cliente'],r['negocio']) for r in records}=={(r['cliente'],r['negocio']) for r in seed}
    assert all(r['licencia_alcohol']=='SI' for r in records if r['negocio']=='CZA')
