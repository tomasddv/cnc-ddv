from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from store import Store, preparar_csv


@pytest.fixture
def store(tmp_path):
    s=Store(sqlite_path=tmp_path/'relevamientos.sqlite')
    rows=preparar_csv((ROOT/'data'/'campana_2026-10.csv').read_bytes())
    s.seed(rows)
    return s


def test_included_campaign_counts(store):
    assert store.total() == 357
    assert len(store.unique_clients('2026-10')) == 268
    assert sum(len(c['negocios'])==2 for c in store.unique_clients('2026-10')) == 89
    assert len(store.promoters('2026-10')) == 13


def test_one_client_one_card_even_when_both(store):
    both=next(c for c in store.unique_clients('2026-10') if len(c['negocios'])==2)
    assert not both['completo']
    store.record_for_client('2026-10',both['cliente'],both['promotor'],'Sin dinero')
    revised=next(c for c in store.unique_clients('2026-10') if c['cliente']==both['cliente'])
    assert revised['completo'] and revised['respondidos_negocio']==2
    assert revised['motivo']=='Sin dinero'
    data=[r for r in store.report('2026-10') if r['cliente']==both['cliente']]
    assert {r['negocio'] for r in data}=={'CZA','UNG'}
    assert all(r['motivo']=='Sin dinero' for r in data)
    assert len(store.audit('2026-10'))==2


def test_client_removed_from_pending_once_completed(store):
    original=store.unique_clients('2026-10')
    one=original[0]
    store.record_for_client('2026-10',one['cliente'],one['promotor'],'Cerrado')
    after=store.unique_clients('2026-10')
    assert len(after)==268
    assert sum(not x['completo'] for x in after)==267


def test_other_needs_a_comment_and_atomic(store):
    one=store.unique_clients('2026-10')[0]
    with pytest.raises(ValueError):
        store.record_for_client('2026-10',one['cliente'],one['promotor'],'Otro','  ')
    assert store.audit('2026-10')==[]
    store.record_for_client('2026-10',one['cliente'],one['promotor'],'Otro','baja rotación')
    assert next(x for x in store.unique_clients('2026-10') if x['cliente']==one['cliente'])['comentario']=='baja rotación'


def test_access_cannot_change_other_promoters(store):
    clients=store.unique_clients('2026-10')
    one=clients[0]
    another=next(c for c in clients if c['promotor']!=one['promotor'])
    with pytest.raises(PermissionError):
        store.record_for_client('2026-10',one['cliente'],another['promotor'],'Sin dinero')
    assert store.audit('2026-10')==[]


def test_name_and_client_code_resolve_same_promoter(store):
    one=store.unique_clients('2026-10')[0]
    assert store.resolve_promoter('2026-10',one['promotor'].lower())==one['promotor']
    assert store.resolve_promoter('2026-10',one['cliente'])==one['promotor']
    assert store.resolve_promoter('2026-10','123000999999') is None


def test_pins_are_stored_hashed_and_verifiable(store):
    pins=store.issue_pins('2026-10')
    assert len(pins)==13
    for p in pins:
        assert store.check_pin(p['promotor'],p['codigo_acceso'])
        assert not store.check_pin(p['promotor'],'A1B2C3D4')
    assert not store.issue_pins('2026-10',only_missing=True)
    refreshed=store.issue_pins('2026-10',only_missing=False)
    assert len(refreshed)==13
    assert not store.check_pin(pins[0]['promotor'],pins[0]['codigo_acceso'])


def test_progress_unique_not_double_counted(store):
    rows=store.progress_unique('2026-10')
    assert sum(r['clientes'] for r in rows)==268
    assert sum(r['casos_cza'] for r in rows)==132
    assert sum(r['casos_ung'] for r in rows)==225
    both=next(r for r in store.unique_clients('2026-10') if len(r['negocios'])==2)
    store.record_for_client('2026-10',both['cliente'],both['promotor'],'Compra en súper/mayorista')
    rows2=store.progress_unique('2026-10')
    assert sum(r['respondidos'] for r in rows2)==1


def test_revising_one_answer_updates_both_and_audits(store):
    both=next(c for c in store.unique_clients('2026-10') if len(c['negocios'])==2)
    store.record_for_client('2026-10',both['cliente'],both['promotor'],'Cerrado')
    store.record_for_client('2026-10',both['cliente'],both['promotor'],'Otro','se fue de vacaciones')
    assert len(store.audit('2026-10'))==4
    assert all(r['motivo']=='Otro' for r in store.report('2026-10') if r['cliente']==both['cliente'])


def test_no_mix_with_different_periods(store):
    one=store.unique_clients('2026-10')[0]
    with pytest.raises(PermissionError):
        store.record_for_client('2026-09',one['cliente'],one['promotor'],'Cerrado')


def test_rejects_conflicting_promoter_csv():
    records=(ROOT/'data'/'campana_2026-10.csv').read_text(encoding='utf-8-sig').splitlines()
    head=records[0]
    sample=records[1].split(',')
    import csv,io
    reader=csv.DictReader(io.StringIO('\n'.join(records[:10])))
    rows=list(reader)
    a=rows[0].copy();a['negocio']='CZA' if a['negocio']=='UNG' else 'UNG';a['promotor']='OTRO PROMOTOR';a['licencia_alcohol']='SI'
    rows.append(a)
    buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=reader.fieldnames);w.writeheader();w.writerows(rows)
    with pytest.raises(ValueError,match='distintos promotores'):
        preparar_csv(buf.getvalue())
