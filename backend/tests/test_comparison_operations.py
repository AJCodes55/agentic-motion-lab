"""Comparison archives share report backup and retention authority."""
import json

import pytest

from mobility.backups import create_backup
from mobility.baseline import generate_standard_dashboard
from mobility.retention import validate_reports
from mobility.storage import DatasetStore
from test_baseline import publish


def test_malformed_comparison_blocks_backup_and_retention(tmp_path):
    store = DatasetStore(tmp_path / 'data')
    publish(store)
    current = publish(store, month=2)
    report = generate_standard_dashboard(store, current.period)
    archive = store.root / 'reports' / report.report_id / 'comparison.json'
    archive.write_text(json.dumps({'report_id': report.report_id}))
    with pytest.raises(ValueError):
        validate_reports(store)
    with pytest.raises(ValueError):
        create_backup(store.root, tmp_path / 'backups')
    assert archive.exists()


def test_symlinked_comparison_blocks_backup_and_cleanup(tmp_path):
    from mobility.retention import plan_cleanup

    store = DatasetStore(tmp_path / 'data')
    publish(store)
    current = publish(store, month=2)
    report = generate_standard_dashboard(store, current.period)
    outside = tmp_path / 'untrusted.json'
    outside.write_text('{}')
    archive = store.root / 'reports' / report.report_id / 'comparison.json'
    archive.symlink_to(outside)
    with pytest.raises(ValueError):
        create_backup(store.root, tmp_path / 'backups')
    with pytest.raises(ValueError):
        plan_cleanup(store.root)
    assert archive.is_symlink()
    assert outside.read_text() == '{}'


def comparison_store(root):
    from mobility.comparison import ComparisonService
    from test_comparison import FEB, model, ready

    store = ready(root)
    result = ComparisonService(store, model()).run(FEB)
    return store, result


def test_comparison_backup_restore_preserves_pinned_archive_after_replacement(tmp_path):
    from mobility.backups import restore_backup
    from mobility.comparison import validate_archive
    from mobility.operations import _ReadOnlyStore
    from test_agent import version

    store, result = comparison_store(tmp_path / 'data')
    version(store, 1, {'replacement': 1})
    version(store, 2, {'replacement': 1})
    path = store.root / 'reports' / result.report_id / 'comparison.json'
    original = path.read_bytes()
    snapshot = create_backup(store.root, tmp_path / 'backups')
    restored = tmp_path / 'restored'
    assert restore_backup(snapshot, restored)['ok']
    assert validate_archive(_ReadOnlyStore(restored), result.report_id) == result
    assert (restored / 'reports' / result.report_id / 'comparison.json').read_bytes() == original
    assert path.read_bytes() == original


@pytest.mark.parametrize('target', ['report_id', 'datasets', 'python_total', 'linked_agent'])
def test_comparison_corruption_blocks_backup_and_cleanup(tmp_path, target):
    from mobility.retention import plan_cleanup

    store, result = comparison_store(tmp_path / 'data')
    path = store.root / 'reports' / result.report_id / 'comparison.json'
    data = json.loads(path.read_text())
    if target == 'report_id':
        data['report_id'] = '0' * 32
    elif target == 'datasets':
        data['datasets'][0]['version_id'] = 'forged'
    elif target == 'python_total':
        data['baseline']['monthly_totals']['2026-01'] += 1
    else:
        linked = path.parent / 'agent' / 'agent-run.json'
        agent = json.loads(linked.read_text())
        agent['counters']['input_tokens'] += 1
        linked.write_text(json.dumps(agent))
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        create_backup(store.root, tmp_path / 'backups')
    with pytest.raises(ValueError):
        plan_cleanup(store.root)
    assert path.exists()


def test_restore_semantically_validates_comparison_even_with_updated_checksum(tmp_path):
    import hashlib
    from mobility.backups import restore_backup

    store, result = comparison_store(tmp_path / 'data')
    snapshot = create_backup(store.root, tmp_path / 'backups')
    relative = f'reports/{result.report_id}/comparison.json'
    archive = snapshot / 'data' / relative
    data = json.loads(archive.read_text())
    data['report_id'] = 'f' * 32
    archive.write_text(json.dumps(data))
    manifest_path = snapshot / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['sha256'][relative] = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        restore_backup(snapshot, tmp_path / 'restore')
    assert not (tmp_path / 'restore').exists()


def test_comparison_expires_with_earliest_dependency_and_whole_archive_is_cleaned(tmp_path):
    from contextlib import closing
    import sqlite3
    from mobility.history import read_archived_report
    from mobility.retention import apply_cleanup, plan_cleanup

    store, result = comparison_store(tmp_path / 'data')
    prior = next(ref for ref in result.datasets if ref.period.month == 1)
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute("UPDATE retention SET uploaded_at='2000-01-01T00:00:00+00:00' WHERE artifact_id=?",
                   (prior.version_id,))
    with pytest.raises(KeyError):
        read_archived_report(store, result.report_id)
    plan = plan_cleanup(store.root)
    assert plan['delete_reports'] == [result.report_id]
    assert plan['delete_versions'] == [prior.version_id]
    archive = store.root / 'reports' / result.report_id
    assert (archive / 'comparison.json').exists()
    apply_cleanup(store.root, plan)
    assert not archive.exists()
    assert len(store.list_active()) == 1


def test_interrupted_comparison_publication_blocks_cleanup_and_backup(tmp_path):
    from mobility.retention import plan_cleanup

    store, result = comparison_store(tmp_path / 'data')
    incomplete = store.root / 'reports' / result.report_id / ('.comparison-' + 'a' * 32 + '.tmp')
    incomplete.write_text('{"unfinished":')
    with pytest.raises(ValueError, match='Incomplete comparison'):
        plan_cleanup(store.root)
    with pytest.raises(ValueError, match='Incomplete comparison'):
        create_backup(store.root, tmp_path / 'backups')
    assert incomplete.read_text() == '{"unfinished":'
