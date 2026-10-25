from contextlib import closing
from datetime import datetime, timezone
import sqlite3

import pytest

from mobility.lifecycle import expires_at, parse_time, timestamp
from mobility.storage import DatasetStore
from test_storage import cleaned


@pytest.mark.parametrize(('uploaded', 'expiry'), [
    ('2026-10-24T12:34:56.123456+00:00', '2027-04-24T12:34:56.123456+00:00'),
    ('2026-08-31T23:59:59+00:00', '2027-02-28T23:59:59+00:00'),
    ('2027-08-31T00:00:00+00:00', '2028-02-29T00:00:00+00:00'),
])
def test_calendar_expiry_preserves_time_and_clamps_days(uploaded, expiry):
    assert expires_at(uploaded) == parse_time(expiry)
    assert parse_time(expiry) >= expires_at(uploaded)


def test_timestamp_requires_timezone_and_normalizes_utc():
    with pytest.raises(ValueError):
        parse_time('2026-10-24T12:00:00')
    with pytest.raises(ValueError):
        timestamp(datetime(2026, 10, 24))
    assert timestamp(parse_time('2026-10-24T12:00:00-05:00')) == '2026-10-24T17:00:00+00:00'


def test_new_upload_versions_have_independent_clocks_and_legacy_is_preserved(tmp_path):
    store = DatasetStore(tmp_path)
    data = cleaned()
    first = store.persist_and_activate(data, uploaded_at=parse_time('2026-10-24T12:00:00Z'))
    second = store.persist_and_activate(data, uploaded_at=parse_time('2026-10-25T12:00:00Z'))
    with closing(sqlite3.connect(store.registry)) as db, db:
        rows = dict(db.execute("SELECT artifact_id, uploaded_at FROM retention WHERE artifact_kind='version'"))
        assert rows == {first.version_id: '2026-10-24T12:00:00+00:00', second.version_id: '2026-10-25T12:00:00+00:00'}
        db.execute('DELETE FROM retention WHERE artifact_id=?', (first.version_id,))
    reopened = DatasetStore(tmp_path)
    reopened.activate(first)
    with closing(sqlite3.connect(store.registry)) as db, db:
        assert db.execute('SELECT uploaded_at FROM retention WHERE artifact_id=?', (first.version_id,)).fetchone() is None
        assert db.execute('SELECT uploaded_at FROM retention WHERE artifact_id=?', (second.version_id,)).fetchone() == (rows[second.version_id],)


def test_ingestion_uses_one_timestamp_for_versions_and_multiple_rejections(tmp_path, monkeypatch):
    from mobility.config import Settings
    from mobility.service import IngestionService
    from test_ingestion import source, row
    now = datetime(2026, 10, 24, 12, 34, tzinfo=timezone.utc)
    monkeypatch.setattr('mobility.service.utc_now', lambda: now)
    service = IngestionService(Settings(data_root=tmp_path))
    service.ingest((source([row()]),))
    batch = service.ingest((source([row()], 'bad.csv'), source([row()], 'other.csv')))
    assert len(batch.results) == 2
    with closing(sqlite3.connect(tmp_path / 'registry.sqlite')) as db, db:
        rows = db.execute('SELECT artifact_kind, artifact_id, uploaded_at FROM retention').fetchall()
    assert len(rows) == 3
    assert {entry[2] for entry in rows} == {timestamp(now)}
    assert len({entry[1] for entry in rows}) == 3
    assert all(entry[1].endswith('.json') for entry in rows if entry[0] == 'rejection')


def test_expiry_exact_boundary_and_read_access(tmp_path, monkeypatch):
    from datetime import timedelta
    store = DatasetStore(tmp_path)
    data = cleaned()
    uploaded = parse_time('2026-10-24T12:00:00Z')
    reference = store.persist_and_activate(data, uploaded_at=uploaded)
    expiry = expires_at(timestamp(uploaded))
    monkeypatch.setattr('mobility.storage.utc_now', lambda: expiry - timedelta(microseconds=1))
    assert store.list_active() == (reference,)
    assert not store.is_expired(reference)
    monkeypatch.setattr('mobility.storage.utc_now', lambda: expiry)
    assert store.is_expired(reference)
    assert store.list_active() == ()
    with pytest.raises(KeyError):
        store.pin_periods((data.period,))
    with pytest.raises(ValueError, match='expired'):
        store.read_metadata(reference)
    # Offline operational inspection can still validate the expired material.
    store.enforce_retention = False
    assert store.read_metadata(reference)['version_id'] == reference.version_id


def test_one_batch_accepted_and_rejected_share_upload_clock(tmp_path, monkeypatch):
    from mobility.config import Settings
    from mobility.service import IngestionService
    from test_ingestion import source, row
    calls = []
    def now():
        calls.append(True)
        return parse_time('2026-10-24T12:00:00Z')
    monkeypatch.setattr('mobility.service.utc_now', now)
    result = IngestionService(Settings(data_root=tmp_path)).ingest((
        source([row()]), source([row()], 'bad.csv')))
    assert {item.status for item in result.results} == {'accepted', 'rejected'}
    assert len(calls) == 1
    with closing(sqlite3.connect(tmp_path / 'registry.sqlite')) as db, db:
        rows = db.execute('SELECT artifact_kind, uploaded_at FROM retention').fetchall()
    assert set(rows) == {('version', '2026-10-24T12:00:00+00:00'),
                         ('rejection', '2026-10-24T12:00:00+00:00')}
