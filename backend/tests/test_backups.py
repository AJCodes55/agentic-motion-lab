from datetime import datetime, timezone
import json

import pytest

from mobility.backups import create_backup, restore_backup, prune_backups
from mobility.storage import DatasetStore
from test_storage import cleaned


def source(tmp_path):
    root = tmp_path / 'source'
    DatasetStore(root).persist_and_activate(cleaned())
    return root


def test_roundtrip_and_no_overwrite(tmp_path):
    root = source(tmp_path)
    snapshot = create_backup(root, tmp_path / 'backups')
    target = tmp_path / 'restore'
    result = restore_backup(snapshot, target)
    assert result['ok'] and result['within_rto_target']
    assert (target / 'registry.sqlite').read_bytes() == (root / 'registry.sqlite').read_bytes()
    with pytest.raises(ValueError):
        restore_backup(snapshot, target)


def test_corruption_missing_and_extra_files_rejected(tmp_path):
    root = source(tmp_path)
    snapshot = create_backup(root, tmp_path / 'backups')
    registry = snapshot / 'data' / 'registry.sqlite'
    registry.write_bytes(b'broken')
    with pytest.raises(ValueError):
        restore_backup(snapshot, tmp_path / 'restore')
    assert not (tmp_path / 'restore').exists()


def test_overlap_symlink_and_secrets_fail(tmp_path):
    root = source(tmp_path)
    with pytest.raises(ValueError):
        create_backup(root, root / 'backups')
    (root / '.env').write_text('secret')
    with pytest.raises(ValueError):
        create_backup(root, tmp_path / 'backups')
    (root / '.env').unlink()
    (root / 'link').symlink_to('/etc/passwd')
    with pytest.raises(ValueError):
        create_backup(root, tmp_path / 'backups')


def test_expired_snapshot_restore_refused_and_pruning_explicit(tmp_path, monkeypatch):
    root = source(tmp_path)
    snapshot = create_backup(root, tmp_path / 'backups')
    monkeypatch.setattr('mobility.backups._now', lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        restore_backup(snapshot, tmp_path / 'restore')
    assert prune_backups(snapshot.parent)['candidates'] == [snapshot.name]
    assert snapshot.exists()
    prune_backups(snapshot.parent, apply=True)
    assert not snapshot.exists()


def test_legacy_retained_and_freshness_reported(tmp_path, monkeypatch):
    import sqlite3
    from contextlib import closing
    root = source(tmp_path)
    with closing(sqlite3.connect(root / 'registry.sqlite')) as db, db:
        db.execute('DELETE FROM retention')
    snapshot = create_backup(root, tmp_path / 'backups')
    manifest = json.loads((snapshot / 'manifest.json').read_text())
    assert manifest['expires_at'] is None
    assert manifest['legacy_versions_without_upload_time']
    monkeypatch.setattr('mobility.backups._now', lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))
    assert not restore_backup(snapshot, tmp_path / 'restore')['within_rpo_target']
    assert prune_backups(snapshot.parent)['candidates'] == []


def test_locked_source_and_partial_copy_leave_no_snapshot(tmp_path, monkeypatch):
    from mobility.maintenance import application_lock
    root = source(tmp_path)
    with application_lock(root), pytest.raises(RuntimeError):
        create_backup(root, tmp_path / 'backups')
    def fail(*args, **kwargs):
        raise OSError('simulated disk failure')
    monkeypatch.setattr('mobility.backups.shutil.copytree', fail)
    with pytest.raises(OSError):
        create_backup(root, tmp_path / 'backups')
    assert list((tmp_path / 'backups').iterdir()) == []


def test_report_restores_pinned_evidence_and_source_unchanged(tmp_path):
    from mobility.baseline import generate_standard_dashboard
    from mobility.history import list_report_history, read_archived_report
    from mobility.operations import _ReadOnlyStore
    from test_baseline import publish
    root = tmp_path / 'source'
    store = DatasetStore(root)
    original = publish(store)
    report = generate_standard_dashboard(store, original.period)
    publish(store, name='Corrected station')
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    snapshot = create_backup(root, tmp_path / 'backups')
    restore_backup(snapshot, tmp_path / 'restore')
    restored = _ReadOnlyStore(tmp_path / 'restore')
    assert list_report_history(restored)[0].datasets == (original,)
    assert read_archived_report(restored, report.report_id) == report.html
    assert all((root / path).read_bytes() == content for path, content in before.items())


@pytest.mark.parametrize('change', ['missing', 'extra'])
def test_snapshot_inventory_mismatch(tmp_path, change):
    snapshot = create_backup(source(tmp_path), tmp_path / 'backups')
    if change == 'missing':
        (snapshot / 'data' / 'registry.sqlite').unlink()
    else:
        (snapshot / 'data' / 'extra.txt').write_text('unexpected')
    with pytest.raises(ValueError):
        restore_backup(snapshot, tmp_path / 'restore')


def test_cli_create_restore_prune(tmp_path, monkeypatch, capsys):
    import sys
    from mobility.backups import main
    root = source(tmp_path)
    backup_dir = tmp_path / 'backups'
    monkeypatch.setattr(sys, 'argv', ['backups', 'create', str(root), str(backup_dir)])
    main()
    snapshot = json.loads(capsys.readouterr().out)['snapshot']
    monkeypatch.setattr(sys, 'argv', ['backups', 'restore', snapshot, str(tmp_path / 'restore')])
    main()
    assert json.loads(capsys.readouterr().out)['ok']
    monkeypatch.setattr(sys, 'argv', ['backups', 'prune', str(backup_dir)])
    main()
    assert json.loads(capsys.readouterr().out)['apply'] is False


def test_restore_copy_failure_does_not_publish(tmp_path, monkeypatch):
    snapshot = create_backup(source(tmp_path), tmp_path / 'backups')
    def fail(*args, **kwargs):
        raise OSError('disk failure')
    monkeypatch.setattr('mobility.backups.shutil.copytree', fail)
    with pytest.raises(OSError):
        restore_backup(snapshot, tmp_path / 'restore')
    assert not (tmp_path / 'restore').exists()
    assert not list(tmp_path.glob('.restore-*'))


def test_pruning_preserves_unmanaged_directory(tmp_path):
    backup_dir = tmp_path / 'backups'
    (backup_dir / 'personal').mkdir(parents=True)
    result = prune_backups(backup_dir, apply=True)
    assert result['skipped'] == ['personal']
    assert (backup_dir / 'personal').exists()


def test_fsync_failure_never_publishes_backup_or_restore(tmp_path, monkeypatch):
    root = source(tmp_path)
    snapshot = create_backup(root, tmp_path / 'valid-backups')
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    def fail(_descriptor):
        raise OSError('simulated fsync failure')
    monkeypatch.setattr('mobility.backups.os.fsync', fail)
    with pytest.raises(OSError):
        create_backup(root, tmp_path / 'failed-backups')
    assert not list((tmp_path / 'failed-backups').iterdir())
    with pytest.raises(OSError):
        restore_backup(snapshot, tmp_path / 'restore')
    assert not (tmp_path / 'restore').exists()
    assert not list(tmp_path.glob('.restore-*'))
    assert all((root / p).read_bytes() == data for p, data in before.items())


def test_mixed_legacy_backup_pruning_reports_copy_deletion_only(tmp_path, monkeypatch):
    import sqlite3
    from contextlib import closing
    root = source(tmp_path)
    store = DatasetStore(root)
    legacy = store.prepare_version(cleaned().period, cleaned().frame, cleaned().quality)
    with closing(sqlite3.connect(root / 'registry.sqlite')) as db, db:
        db.execute('DELETE FROM retention WHERE artifact_id=?', (legacy.version_id,))
    snapshot = create_backup(root, tmp_path / 'backups')
    monkeypatch.setattr('mobility.backups._now', lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))
    result = prune_backups(snapshot.parent, apply=True)
    assert result['legacy_backup_copies_deleted_with_expired_snapshot'] == {snapshot.name: [legacy.version_id]}
    assert (root / 'versions' / legacy.version_id).exists()
