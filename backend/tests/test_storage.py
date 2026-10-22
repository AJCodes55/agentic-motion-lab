from types import SimpleNamespace

import pandas as pd
import pytest

from mobility.contracts import Period, QualitySummary
from mobility.storage import DatasetStore


def cleaned():
    frame = pd.DataFrame({
        'ride_id': ['a', 'b'], 'started_at': ['2026-01-01 10:00:00', '2026-01-02 10:00:00'],
        'start_station_id': ['x', 'y'], 'member_casual': ['Member', 'Unknown'],
        'rideable_type': ['Classic', 'E-bike'], 'duration_seconds': [60.0, 120.0],
    })
    return SimpleNamespace(period=Period(year=2026, month=1), frame=frame,
                           quality=QualitySummary(source_rows=2, valid_rows=2, excluded_rows=0), sources=())


def test_persist_restart_and_exact_metrics(tmp_path):
    store = DatasetStore(tmp_path)
    data = cleaned()
    ref = store.persist_and_activate(data)
    reopened = DatasetStore(tmp_path)
    assert reopened.pin_periods((data.period,)) == (ref,)
    metrics = reopened.read_kpis(ref)
    assert metrics['total_trips'] == 2
    assert metrics['duration_seconds_sum'] == 180
    assert metrics['average_duration_minutes'] == 1.5
    assert metrics['categories']['member_casual']['Unknown']['count'] == 1
    assert len(reopened.read_frame(ref)) == 2
    assert reopened.read_metadata(ref)['quality']['valid_rows'] == 2


def test_replacement_keeps_pinned_version_and_orphan_inactive(tmp_path):
    store = DatasetStore(tmp_path)
    data = cleaned()
    old = store.persist_and_activate(data)
    new = store.prepare_version(data.period, data.frame, data.quality)
    assert store.pin_periods((data.period,)) == (old,)
    store.activate(new)
    assert store.pin_periods((data.period,)) == (new,)
    assert len(store.read_frame(old)) == 2


def test_failed_prepare_leaves_active_untouched(tmp_path, monkeypatch):
    store = DatasetStore(tmp_path)
    data = cleaned()
    old = store.persist_and_activate(data)
    monkeypatch.setattr(store, '_write_artifacts', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        store.persist_and_activate(data)
    assert store.pin_periods((data.period,)) == (old,)


def test_reject_mismatch_and_unknown_reference(tmp_path):
    store = DatasetStore(tmp_path)
    data = cleaned()
    with pytest.raises(ValueError):
        store.prepare_version(data.period, data.frame.iloc[:1], data.quality)
    ref = store.prepare_version(data.period, data.frame, data.quality)
    forged = ref.model_copy(update={'sha256': '0' * 64})
    with pytest.raises(ValueError):
        store.read_frame(forged)
    with pytest.raises(KeyError):
        store.pin_periods((data.period,))


def test_rejection_evidence(tmp_path):
    store = DatasetStore(tmp_path)
    quality = QualitySummary(source_rows=2, valid_rows=0, excluded_rows=2, rejection_reason='invalid')
    path = store.record_rejection('upload-a', quality)
    assert 'invalid' in path.read_text()
    with pytest.raises(ValueError):
        store.record_rejection('../escape', quality)


def test_failure_before_activation_and_after_committed_activation(tmp_path, monkeypatch):
    store = DatasetStore(tmp_path)
    data = cleaned()
    old = store.persist_and_activate(data)
    original = store.activate
    monkeypatch.setattr(store, 'activate', lambda ref: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        store.persist_and_activate(data)
    assert DatasetStore(tmp_path).pin_periods((data.period,)) == (old,)

    def committed_then_interrupted(reference):
        original(reference)
        raise OSError('interrupted after commit')

    monkeypatch.setattr(store, 'activate', committed_then_interrupted)
    with pytest.raises(OSError):
        store.persist_and_activate(data)
    new = DatasetStore(tmp_path).pin_periods((data.period,))[0]
    assert new != old
    assert len(store.read_frame(new)) == 2


def test_reconcile_categories_durations_dates_and_quality(tmp_path):
    store = DatasetStore(tmp_path)
    data = cleaned()
    for column, value in [('member_casual', 'unexpected'), ('rideable_type', None),
                          ('duration_seconds', float('inf')), ('duration_seconds', 0),
                          ('started_at', '2026-02-01'), ('start_station_id', None)]:
        modified = data.frame.assign(**{column: value})
        with pytest.raises(ValueError):
            store.prepare_version(data.period, modified, data.quality)
    quality = QualitySummary(source_rows=3, valid_rows=2, excluded_rows=1)
    with pytest.raises(ValueError):
        store.prepare_version(data.period, data.frame, quality)


def test_kpi_corruption_prevents_activation(tmp_path):
    import sqlite3

    store = DatasetStore(tmp_path)
    data = cleaned()
    ref = store.prepare_version(data.period, data.frame, data.quality)
    path = tmp_path / 'versions' / ref.version_id / 'kpis.sqlite'
    path.chmod(0o644)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE monthly_kpis SET payload='{}'")
    db.close()
    with pytest.raises(ValueError, match='reconcile'):
        store.activate(ref)
    assert store.list_active() == ()


def test_mixed_dst_offsets_preserve_local_month_days(tmp_path):
    store = DatasetStore(tmp_path)
    data = cleaned()
    frame = data.frame.assign(started_at=['2026-03-01 00:15:00-05:00', '2026-03-31 23:15:00-04:00'])
    period = Period(year=2026, month=3)
    reference = store.prepare_version(period, frame, data.quality)
    store.activate(reference)
    assert store.pin_periods((period,)) == (reference,)


def test_literal_na_and_leading_zero_identifiers_roundtrip(tmp_path):
    store = DatasetStore(tmp_path)
    data = cleaned()
    data.frame = data.frame.assign(ride_id=['NULL', '0007'],
                                  start_station_id=['NA', '001'],
                                  start_station_name=['NA', 'NULL'],
                                  end_station_id=['NULL', '0002'])
    reference = store.persist_and_activate(data)
    loaded = store.read_frame(reference)
    for column in ('ride_id', 'start_station_id', 'start_station_name', 'end_station_id'):
        assert loaded[column].tolist() == data.frame[column].tolist()


def test_two_period_snapshot_survives_concurrent_writer(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store = DatasetStore(tmp_path)
    # WAL permits a writer to commit while an existing read transaction stays pinned.
    with store._connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
    data = cleaned()
    january = store.persist_and_activate(data)
    february_period = Period(year=2026, month=2)
    february_frame = data.frame.assign(started_at=['2026-02-01 10:00:00', '2026-02-02 10:00:00'])
    old_february = store.prepare_version(february_period, february_frame, data.quality)
    store.activate(old_february)
    new_february = store.prepare_version(february_period, february_frame, data.quality)

    class ActivateBetweenPeriods(tuple):
        def __iter__(self):
            yield january.period
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(DatasetStore(tmp_path).activate, new_february).result(timeout=10)
            yield february_period

    pinned = store.pin_periods(ActivateBetweenPeriods((january.period, february_period)))
    assert pinned == (january, old_february)
    assert store.pin_periods((february_period,)) == (new_february,)
