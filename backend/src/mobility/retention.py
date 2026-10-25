"""Offline, explicit retention cleanup. Unknown upload dates never authorize deletion."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3

from mobility.baseline import BaselineReport
from mobility.history import _load, read_archived_report
from mobility.lifecycle import expires_at, parse_time, utc_now
from mobility.maintenance import maintenance_lock
from mobility.operations import _ReadOnlyStore, inspect_data_root

JOURNAL = '.cleanup-journal.json'


def validate_reports(store):
    """Validate complete baseline reference supersets and archive identities."""
    reports, unknown = {}, []
    root = store.root / 'reports'
    if not root.exists():
        return reports, unknown
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or not re.fullmatch('[a-f0-9]{32}', directory.name):
            unknown.append(f'reports/{directory.name}')
            continue
        baseline = BaselineReport.model_validate_json((directory / 'evidence.json').read_text())
        if baseline.report_id != directory.name or not baseline.datasets:
            raise ValueError('Invalid report identity or missing dataset references')
        if baseline.period != baseline.datasets[0].period or not baseline.evidence:
            raise ValueError('Missing or inconsistent baseline evidence')
        for evidence in baseline.evidence:
            if evidence.run_id != baseline.report_id or any(ref not in baseline.datasets for ref in evidence.datasets):
                raise ValueError('Forged baseline evidence references')
        for ref in baseline.datasets:
            store.read_metadata(ref)
        _load(store, directory.name)
        read_archived_report(store, directory.name)
        if (directory / 'index.html').read_text() != baseline.html:
            raise ValueError('Baseline archive HTML mismatch')
        reports[directory.name] = [ref.version_id for ref in baseline.datasets]
    return reports, unknown


def _now(value):
    return parse_time(value) if isinstance(value, str) else (value or utc_now())


def _fingerprint(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def _plan(root, now):
    if (root / JOURNAL).exists():
        raise ValueError('Pending cleanup journal; recover cleanup first')
    inspection = inspect_data_root(root)
    if not inspection['ok']:
        raise ValueError('Integrity inspection failed: ' + '; '.join(inspection['issues']))
    store = _ReadOnlyStore(root)
    reports, unknown = validate_reports(store)
    blocked = [f'Unregistered: versions/{name}' for name in inspection['unregistered_directories']]
    blocked.extend(f'Unregistered: {name}' for name in unknown)
    with store._connect() as db:
        versions = {row[0] for row in db.execute('SELECT version_id FROM versions')}
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='retention'").fetchone()
        dates = {(kind, identity): date for kind, identity, date in db.execute('SELECT artifact_kind, artifact_id, uploaded_at FROM retention')} if exists else {}
    expired = set()
    rejections = {p.name for p in (root / 'rejections').iterdir() if p.is_file()}
    for kind, identities in [('version', versions), ('rejection', rejections)]:
        for identity in sorted(identities):
            date = dates.get((kind, identity))
            if date is None:
                blocked.append(f'Unknown upload date: {kind}/{identity}')
            elif _now(expires_at(date)) <= now:
                expired.add((kind, identity))
    deleted_versions = sorted(identity for kind, identity in expired if kind == 'version')
    deleted_rejections = sorted(identity for kind, identity in expired if kind == 'rejection')
    deleted_reports = sorted(identity for identity, refs in reports.items() if set(refs) & set(deleted_versions))
    quarantine_refs = {}
    for name in sorted(rejections):
        record = json.loads((root / 'rejections' / name).read_text())
        upload = record['upload_id']
        if not re.fullmatch('[A-Za-z0-9_-]{1,128}', upload):
            raise ValueError('Unsafe rejection upload identity')
        quarantine_refs.setdefault(upload, []).append(name)
        for source in record['sources']:
            filename = source.get('quarantine_file')
            if filename is not None:
                if not re.fullmatch('[a-f0-9]{32}\\.bin', filename):
                    raise ValueError('Unsafe quarantine file identity')
                path = root / 'quarantine' / upload / filename
                if hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
                    raise ValueError('Quarantine checksum mismatch')
    deleted_quarantine = sorted(upload for upload, refs in quarantine_refs.items() if set(refs) <= set(deleted_rejections))
    quarantine = root / 'quarantine'
    if quarantine.exists():
        blocked.extend(f'Unregistered: quarantine/{p.name}' for p in sorted(quarantine.iterdir()) if p.name not in quarantine_refs)
    return {'fingerprint': _fingerprint(inspection['sha256']), 'delete_versions': deleted_versions,
            'delete_reports': deleted_reports, 'delete_rejections': deleted_rejections,
            'delete_quarantine': deleted_quarantine, 'blocked': sorted(blocked)}


def plan_cleanup(root, now=None):
    root = Path(root).absolute()
    with maintenance_lock(root):
        return _plan(root, _now(now))


def _write_journal(path, payload):
    temporary = path.with_suffix('.tmp')
    payload = {**payload, 'checksum': _fingerprint(payload)}
    with temporary.open('x') as stream:
        json.dump(payload, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _recover(root):
    journal = root / JOURNAL
    if not journal.exists():
        return {'recovered': False}
    if journal.is_symlink():
        raise ValueError('Unsafe cleanup journal')
    payload = json.loads(journal.read_text())
    checksum = payload.pop('checksum', None)
    if checksum != _fingerprint(payload):
        raise ValueError('Cleanup journal checksum mismatch')
    cutoff = parse_time(payload['cutoff'])
    for kind, identity, uploaded in payload['dates']:
        if kind not in {'version', 'rejection'} or expires_at(uploaded) > cutoff:
            raise ValueError('Cleanup journal includes unexpired data')
    if sorted((kind, identity) for kind, identity, _ in payload['dates']) != sorted([('version', identity) for identity in payload['versions']] + [('rejection', identity) for identity in payload['rejections']]):
        raise ValueError('Cleanup journal missing expiry authority')
    expected = [f'{directory}/{identity}' for key, directory in [('reports', 'reports'), ('versions', 'versions'), ('rejections', 'rejections'), ('quarantine', 'quarantine')] for identity in payload[key]]
    paths = payload['paths']
    if paths != expected:
        raise ValueError('Cleanup journal path closure mismatch')
    if not isinstance(paths, list) or len(paths) != len(set(paths)):
        raise ValueError('Invalid cleanup journal')
    for key, directory in [('versions', 'versions'), ('rejections', 'rejections')]:
        if sorted(f'{directory}/{identity}' for identity in payload[key]) != sorted(p for p in paths if p.startswith(directory + '/')):
            raise ValueError('Cleanup journal identities disagree')
    for relative in paths:
        parts = Path(relative).parts
        if len(parts) != 2 or parts[0] not in {'versions', 'reports', 'rejections', 'quarantine'} or not re.fullmatch('[A-Za-z0-9_.-]+', parts[1]) or parts[1] in {'.', '..'}:
            raise ValueError('Unsafe cleanup journal path')
        path = root / relative
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('Unsafe cleanup target')
        if path.is_dir() and any(p.is_symlink() or (not p.is_dir() and not p.is_file()) for p in path.rglob('*')):
            raise ValueError('Unsafe cleanup descendant')
    for identity, refs in payload['report_refs'].items():
        if identity not in payload['reports'] or not set(refs).intersection(payload['versions']):
            raise ValueError('Cleanup journal report dependency mismatch')
    if set(payload['report_refs']) != set(payload['reports']):
        raise ValueError('Cleanup journal missing report dependencies')
    for identity, refs in payload['quarantine_refs'].items():
        if identity not in payload['quarantine'] or not refs or not set(refs) <= set(payload['rejections']):
            raise ValueError('Cleanup journal quarantine dependency mismatch')
    if set(payload['quarantine_refs']) != set(payload['quarantine']):
        raise ValueError('Cleanup journal missing quarantine dependencies')
    # Registry changes and journal commitment are idempotent across interruption.
    with closing(sqlite3.connect(root / 'registry.sqlite')) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        for identity in payload['versions']:
            db.execute('DELETE FROM active WHERE version_id=?', (identity,))
            db.execute('DELETE FROM versions WHERE version_id=?', (identity,))
            db.execute("DELETE FROM retention WHERE artifact_kind='version' AND artifact_id=?", (identity,))
        for identity in payload['rejections']:
            db.execute("DELETE FROM retention WHERE artifact_kind='rejection' AND artifact_id=?", (identity,))
    for relative in paths:
        path = root / relative
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    journal.unlink()
    return {'recovered': True, 'deleted': paths}


def recover_cleanup(root):
    root = Path(root).absolute()
    with maintenance_lock(root):
        return _recover(root)


def apply_cleanup(root, plan, now=None):
    root = Path(root).absolute()
    with maintenance_lock(root):
        current = _plan(root, _now(now))
        if current != plan:
            raise ValueError('Cleanup plan is stale; generate and review a new dry run')
        paths = [f'{directory}/{identity}' for key, directory in [('delete_reports', 'reports'), ('delete_versions', 'versions'), ('delete_rejections', 'rejections'), ('delete_quarantine', 'quarantine')] for identity in current[key]]
        if not paths:
            return {'recovered': False, 'deleted': []}
        with _ReadOnlyStore(root)._connect() as db:
            dates = [list(row) for row in db.execute('SELECT artifact_kind, artifact_id, uploaded_at FROM retention')
                     if (row[0] == 'version' and row[1] in current['delete_versions']) or (row[0] == 'rejection' and row[1] in current['delete_rejections'])]
        reports, _ = validate_reports(_ReadOnlyStore(root))
        quarantine_refs = {}
        for name in current['delete_rejections']:
            upload = json.loads((root / 'rejections' / name).read_text())['upload_id']
            if upload in current['delete_quarantine']:
                quarantine_refs.setdefault(upload, []).append(name)
        _write_journal(root / JOURNAL, {'report_refs': {identity: reports[identity] for identity in current['delete_reports']},
                       'quarantine_refs': quarantine_refs, 'paths': paths, 'versions': current['delete_versions'],
                       'rejections': current['delete_rejections'], 'reports': current['delete_reports'],
                       'quarantine': current['delete_quarantine'], 'dates': dates,
                       'cutoff': _now(now).isoformat()})
        return _recover(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--recover', action='store_true')
    args = parser.parse_args()
    plan = recover_cleanup(args.root) if args.recover else plan_cleanup(args.root)
    print(json.dumps(apply_cleanup(args.root, plan) if args.apply and not args.recover else plan, indent=2))


if __name__ == '__main__':
    main()
