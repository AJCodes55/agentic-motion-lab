"""Expired evidence becomes unavailable through the ordinary public contracts."""
from contextlib import closing
from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient

from mobility.app import create_app
from mobility.baseline import generate_standard_dashboard
from mobility.config import Settings
from mobility.storage import DatasetStore
from test_baseline import publish


def test_expired_period_and_its_archive_are_unavailable(tmp_path, monkeypatch):
    import mobility.storage as storage
    monkeypatch.setattr(storage, 'utc_now', lambda: datetime(2026, 10, 24, 12, tzinfo=timezone.utc))
    store = DatasetStore(tmp_path)
    ref = publish(store)
    report = generate_standard_dashboard(store, ref.period)
    monkeypatch.setattr(storage, 'utc_now', lambda: datetime(2027, 4, 24, 12, tzinfo=timezone.utc))
    with TestClient(create_app(Settings(data_root=tmp_path))) as client:
        assert client.get('/periods').json()['data']['periods'] == []
        assert client.get('/reports/history').json()['data']['reports'] == []
        assert client.get(f'/reports/history/{report.report_id}').status_code == 404
        missing = client.post('/reports', json={'period': ref.period.model_dump()})
        assert missing.status_code == 404
        assert missing.json()['error']['message'] == 'No accepted dataset exists for the reporting month.'
    assert (tmp_path / 'reports' / report.report_id / 'index.html').exists()


def test_legacy_period_remains_available_until_dates_supplied(tmp_path):
    store = DatasetStore(tmp_path)
    ref = publish(store)
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute('DELETE FROM retention')
    with TestClient(create_app(Settings(data_root=tmp_path))) as client:
        assert client.get('/periods').json()['data']['periods'][0]['version_id'] == ref.version_id
