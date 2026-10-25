"""Retention deletes only explicitly dated expired synthetic artifacts."""
import json
from contextlib import closing
import sqlite3

import pytest

from mobility.retention import apply_cleanup, plan_cleanup, recover_cleanup
from mobility.storage import DatasetStore
from test_storage import cleaned


def dated(root, date='2025-01-01T00:00:00+00:00'):
    store = DatasetStore(root)
    ref = store.persist_and_activate(cleaned())
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS retention (artifact_kind TEXT, artifact_id TEXT, uploaded_at TEXT, PRIMARY KEY(artifact_kind, artifact_id))')
        db.execute('INSERT OR REPLACE INTO retention VALUES (?, ?, ?)', ('version', ref.version_id, date))
    return store, ref


def test_dry_run_and_expiry_remove_active_without_rollback(tmp_path):
    store, ref = dated(tmp_path)
    plan = plan_cleanup(tmp_path, '2026-10-24T00:00:00+00:00')
    assert plan['delete_versions'] == [ref.version_id]
    assert (tmp_path / "versions" / ref.version_id).exists()
    apply_cleanup(tmp_path, plan, '2026-10-24T00:00:00+00:00')
    assert not store.list_active()
    assert not (tmp_path / 'versions' / ref.version_id).exists()


def test_legacy_and_unknown_preserved(tmp_path):
    from mobility.baseline import generate_standard_dashboard
    from test_baseline import publish

    store = DatasetStore(tmp_path)
    ref = publish(store)
    report = generate_standard_dashboard(store, ref.period)
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute('DELETE FROM retention WHERE artifact_kind=? AND artifact_id=?',
                   ('version', ref.version_id))
    (tmp_path / 'versions' / 'unknown').mkdir()
    before = {p.relative_to(tmp_path): p.read_bytes()
              for directory in ['versions', 'reports']
              for p in (tmp_path / directory).rglob('*') if p.is_file()}
    plan = plan_cleanup(tmp_path)
    assert not plan['delete_versions']
    assert not plan['delete_reports']
    assert f'Unknown upload date: version/{ref.version_id}' in plan['blocked']
    assert 'Unregistered: versions/unknown' in plan['blocked']
    assert apply_cleanup(tmp_path, plan)['deleted'] == []
    assert (tmp_path / 'versions' / ref.version_id).exists()
    assert (tmp_path / 'reports' / report.report_id).exists()
    assert before == {p.relative_to(tmp_path): p.read_bytes()
                      for directory in ['versions', 'reports']
                      for p in (tmp_path / directory).rglob('*') if p.is_file()}


def test_stale_and_symlink_rejected(tmp_path):
    dated(tmp_path)
    plan = plan_cleanup(tmp_path)
    (tmp_path / 'new-file').write_text('new')
    with pytest.raises(ValueError, match='stale'):
        apply_cleanup(tmp_path, plan)
    (tmp_path / 'unsafe').symlink_to('/etc/passwd')
    with pytest.raises(ValueError):
        plan_cleanup(tmp_path)


def test_corrupt_report_blocks_deletion(tmp_path):
    dated(tmp_path)
    report = tmp_path / 'reports' / ('a' * 32)
    report.mkdir(parents=True)
    (report / 'evidence.json').write_text('{}')
    with pytest.raises(ValueError):
        plan_cleanup(tmp_path)


def test_failed_delete_is_resumable(tmp_path, monkeypatch):
    import mobility.retention as retention
    store, ref = dated(tmp_path)
    plan = plan_cleanup(tmp_path)
    original = retention.shutil.rmtree
    monkeypatch.setattr(retention.shutil, 'rmtree', lambda path: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        apply_cleanup(tmp_path, plan)
    assert not store.list_active()
    monkeypatch.setattr(retention.shutil, 'rmtree', original)
    recover_cleanup(tmp_path)
    assert not (tmp_path / 'versions' / ref.version_id).exists()


def test_report_expiry_and_survivors_are_unchanged(tmp_path):
    from mobility.baseline import generate_standard_dashboard
    from test_baseline import publish
    store = DatasetStore(tmp_path)
    old = publish(store)
    expired = generate_standard_dashboard(store, old.period)
    publish(store, name='replacement')
    survivor = generate_standard_dashboard(store, old.period)
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute("UPDATE retention SET uploaded_at='2025-01-01T00:00:00+00:00' WHERE artifact_id=?", (old.version_id,))
    survivor_root = tmp_path / 'reports' / survivor.report_id
    before = {p.name: p.read_bytes() for p in survivor_root.rglob('*') if p.is_file()}
    plan = plan_cleanup(tmp_path)
    assert plan['delete_reports'] == [expired.report_id]
    apply_cleanup(tmp_path, plan)
    assert before == {p.name: p.read_bytes() for p in survivor_root.rglob('*') if p.is_file()}


def test_rejections_share_quarantine_until_all_expire(tmp_path):
    from mobility.contracts import QualitySummary
    import hashlib
    store = DatasetStore(tmp_path)
    raw = tmp_path / 'quarantine' / 'upload'
    raw.mkdir(parents=True)
    filename = 'a' * 32 + '.bin'
    (raw / filename).write_bytes(b'data')
    sources = ({'quarantine_file': filename, 'sha256': hashlib.sha256(b'data').hexdigest()},)
    first = store.record_rejection('upload', QualitySummary(source_rows=0, valid_rows=0, excluded_rows=0), sources)
    second = store.record_rejection('upload', QualitySummary(source_rows=0, valid_rows=0, excluded_rows=0), sources)
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute("UPDATE retention SET uploaded_at='2025-01-01T00:00:00+00:00' WHERE artifact_id=?", (first.name,))
    plan = plan_cleanup(tmp_path)
    assert plan['delete_rejections'] == [first.name]
    assert not plan['delete_quarantine']
    apply_cleanup(tmp_path, plan)
    assert (raw / filename).exists()
    with closing(sqlite3.connect(store.registry)) as db, db:
        db.execute("UPDATE retention SET uploaded_at='2025-01-01T00:00:00+00:00' WHERE artifact_id=?", (second.name,))
    apply_cleanup(tmp_path, plan_cleanup(tmp_path))
    assert not raw.exists()


def test_journal_traversal_cannot_delete_outside_root(tmp_path):
    dated(tmp_path)
    outside = tmp_path.parent / 'untouched.txt'
    outside.write_text('preserve')
    (tmp_path / '.cleanup-journal.json').write_text(json.dumps({'paths': ['versions/../../untouched.txt'], 'versions': ['../../untouched.txt'], 'rejections': []}))
    with pytest.raises(ValueError):
        recover_cleanup(tmp_path)
    assert outside.read_text() == 'preserve'


def test_missing_or_forged_evidence_is_not_cleanup_authority(tmp_path):
    from mobility.baseline import generate_standard_dashboard
    from test_baseline import publish
    store = DatasetStore(tmp_path)
    publish(store)
    report = generate_standard_dashboard(store, cleaned().period)
    path = tmp_path / 'reports' / report.report_id / 'evidence.json'
    data = json.loads(path.read_text())
    data['evidence'][0]['run_id'] = 'forged'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Forged'):
        plan_cleanup(tmp_path)


def test_modified_valid_json_journal_fails_closed(tmp_path, monkeypatch):
    import mobility.retention as retention
    _, ref = dated(tmp_path)
    plan = plan_cleanup(tmp_path)
    original = retention.shutil.rmtree
    monkeypatch.setattr(retention.shutil, 'rmtree', lambda path: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        apply_cleanup(tmp_path, plan)
    journal = tmp_path / '.cleanup-journal.json'
    payload = json.loads(journal.read_text())
    payload['paths'].append('reports/' + 'b' * 32)
    journal.write_text(json.dumps(payload))
    monkeypatch.setattr(retention.shutil, 'rmtree', original)
    with pytest.raises(ValueError, match='checksum'):
        recover_cleanup(tmp_path)
    assert (tmp_path / 'versions' / ref.version_id).exists()
