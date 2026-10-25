"""Offline recovery checks must never repair or delete evidence."""
from contextlib import closing
import shutil
import sqlite3

from mobility.operations import inspect_data_root
from mobility.storage import DatasetStore
from test_storage import cleaned


def test_missing_root_is_not_created(tmp_path):
    root = tmp_path / 'missing'
    result = inspect_data_root(root)
    assert not result['ok']
    assert not root.exists()


def test_offline_copy_preserves_manifest_and_inactive_versions(tmp_path):
    source = tmp_path / 'source'
    store = DatasetStore(source)
    data = cleaned()
    store.persist_and_activate(data)
    inactive = store.prepare_version(data.period, data.frame, data.quality)
    (source / 'versions' / 'interrupted').mkdir()
    before = inspect_data_root(source)
    assert before['ok']
    assert before['inactive_versions'] == [inactive.version_id]
    assert before['unregistered_directories'] == ['interrupted']
    restored = tmp_path / 'restore'
    shutil.copytree(source, restored)
    assert inspect_data_root(restored) == before
    assert (source / 'versions' / 'interrupted').exists()


def test_corrupted_artifact_and_dangling_pointer_fail(tmp_path):
    store = DatasetStore(tmp_path)
    ref = store.persist_and_activate(cleaned())
    path = tmp_path / 'versions' / ref.version_id / 'cleaned.csv'
    path.chmod(0o644)
    path.write_text('corrupt')
    assert not inspect_data_root(tmp_path)['ok']
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute("UPDATE active SET version_id='missing'")
    assert not inspect_data_root(tmp_path)['ok']


def test_symlinks_are_reported_without_reading_target(tmp_path):
    DatasetStore(tmp_path)
    (tmp_path / 'external').symlink_to('/etc/passwd')
    result = inspect_data_root(tmp_path)
    assert not result['ok']
    assert 'external' not in result['sha256']


def test_inspection_preserves_bytes_and_reports_unsettled_sqlite(tmp_path):
    store = DatasetStore(tmp_path)
    ref = store.persist_and_activate(cleaned())
    original = {path.relative_to(tmp_path): path.read_bytes()
                for path in tmp_path.rglob('*') if path.is_file()}
    assert inspect_data_root(tmp_path)['ok']
    assert original == {path.relative_to(tmp_path): path.read_bytes()
                        for path in tmp_path.rglob('*') if path.is_file()}
    (tmp_path / 'registry.sqlite-wal').write_bytes(b'unsettled')
    result = inspect_data_root(tmp_path)
    assert not result['ok']
    assert any('sidecar' in issue for issue in result['issues'])
    assert (tmp_path / 'versions' / ref.version_id).exists()


def test_missing_registry_does_not_create_one_and_wrong_period_fails(tmp_path):
    assert not inspect_data_root(tmp_path)['ok']
    assert not (tmp_path / 'registry.sqlite').exists()
    store = DatasetStore(tmp_path)
    store.persist_and_activate(cleaned())
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute('UPDATE active SET month=2')
    assert not inspect_data_root(tmp_path)['ok']


def test_malformed_metadata_shape_is_reported(tmp_path):
    store = DatasetStore(tmp_path)
    ref = store.persist_and_activate(cleaned())
    path = tmp_path / 'versions' / ref.version_id / 'metadata.json'
    path.chmod(0o644)
    path.write_text('[]')
    assert not inspect_data_root(tmp_path)['ok']


def test_nonregular_registry_is_rejected_before_opening(tmp_path):
    import os

    os.mkfifo(tmp_path / 'registry.sqlite')
    result = inspect_data_root(tmp_path)
    assert not result['ok']
    assert any('Unsupported filesystem entry' in issue for issue in result['issues'])


def test_restored_archive_keeps_original_evidence_after_replacement(tmp_path):
    from mobility.baseline import generate_standard_dashboard
    from mobility.history import list_report_history, read_archived_report
    from test_baseline import publish

    source = tmp_path / 'source'
    store = DatasetStore(source)
    original = publish(store)
    report = generate_standard_dashboard(store, original.period)
    replacement = publish(store, name='Corrected station')
    before = inspect_data_root(source)
    assert before['ok']
    assert original.version_id in before['inactive_versions']
    assert any(name.startswith(f'reports/{report.report_id}/') for name in before['sha256'])
    restored = tmp_path / 'restored'
    shutil.copytree(source, restored)
    assert inspect_data_root(restored) == before
    reopened = DatasetStore(restored)
    assert reopened.pin_periods((original.period,)) == (replacement,)
    entry, = list_report_history(reopened)
    assert entry.datasets == (original,)
    assert read_archived_report(reopened, entry.report_id) == report.html
    assert reopened.read_metadata(original)['version_id'] == original.version_id
    assert inspect_data_root(restored) == before


def test_malformed_registry_inventory_returns_diagnostic(tmp_path):
    store = DatasetStore(tmp_path)
    store.persist_and_activate(cleaned())
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute('INSERT INTO versions VALUES (NULL, 2026, 1, ?, 1)', ('0' * 64,))
        db.execute('INSERT INTO versions VALUES (?, 2026, 1, ?, 1)', ('invalid', '0' * 64))
    result = inspect_data_root(tmp_path)
    assert not result['ok']
    assert result['issues']
