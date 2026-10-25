"""Offline, manually invoked snapshots. No scheduler or remote durability implied.

The maintenance and ingestion advisory lock files are excluded: neither contains
application data and copying their inodes would not preserve lock ownership.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
from uuid import uuid4

from mobility.operations import inspect_data_root, _ReadOnlyStore

_EXCLUDED = {'maintenance.lock', 'ingestion.lock'}
_MARKER = 'mobility-backup-v1'


def _now():
    return datetime.now(timezone.utc)


def _parse(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return result.astimezone(timezone.utc)


def _safe(path):
    path = Path(path).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Symlink paths are not supported')
    return path


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _inventory(root):
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError('Unsafe filesystem entry')
        relative = path.relative_to(root).as_posix()
        if relative in _EXCLUDED:
            continue
        if path.is_file():
            if root.name == 'data' or (root / 'registry.sqlite').exists():
                if len(path.relative_to(root).parts) == 1 and relative not in {'registry.sqlite', 'registry.sqlite-shm', 'registry.sqlite-wal'}:
                    raise ValueError('Unexpected root file; review before backup')
            if path.name.startswith('.env') or any(word in path.name.lower() for word in ('secret', 'credential', '.pem', '.key')):
                raise ValueError('Secret-like files must not be included in application backups')
            files[relative] = _hash(path)
    return files


def _sync_tree(root):
    """Flush copied contents and directory entries before publishing a snapshot."""
    from mobility.storage import DatasetStore
    paths = list(root.rglob('*'))
    for path in paths:
        if path.is_file():
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
    for directory in sorted((path for path in paths if path.is_dir()),
                            key=lambda path: len(path.parts), reverse=True):
        DatasetStore._sync_directory(directory)
    DatasetStore._sync_directory(root)


def _validate(root):
    result = inspect_data_root(root)
    if not result['ok']:
        raise ValueError('Data integrity validation failed: ' + '; '.join(result['issues']))
    from mobility.retention import validate_reports
    _, unknown = validate_reports(_ReadOnlyStore(root))
    if unknown:
        raise ValueError('Unrecognized report artifacts require review before backup')
    return result


def _retention(root):
    from mobility.lifecycle import expires_at
    with closing(sqlite3.connect((root / 'registry.sqlite').as_uri() + '?mode=ro', uri=True)) as db:
        tables = {row[0] for row in db.execute('SELECT name FROM sqlite_master WHERE type="table"')}
        rows = db.execute('SELECT artifact_kind, artifact_id, uploaded_at FROM retention').fetchall() if 'retention' in tables else []
        versions = {row[0] for row in db.execute('SELECT version_id FROM versions')}
    expiries = [expires_at(row[2]) for row in rows]
    known = {row[1] for row in rows if row[0] == 'version'}
    return (min(expiries).isoformat() if expiries else None), sorted(versions - known)


def create_backup(source: Path, destination: Path) -> Path:
    """Create a validated snapshot under caller-selected external destination."""
    from mobility.maintenance import maintenance_lock
    source, destination = _safe(source), _safe(destination)
    if source == destination or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Backup destination and source must not overlap')
    if not source.is_dir():
        raise ValueError('Source must exist')
    with maintenance_lock(source):
        _validate(source)
        files = _inventory(source)
        expiry, unknown = _retention(source)
        if expiry and _parse(expiry) <= _now():
            raise ValueError('Expired data must be cleaned before backup')
        destination.mkdir(parents=True, exist_ok=True)
        identifier = 'snapshot-' + uuid4().hex
        staging, final = destination / ('.' + identifier), destination / identifier
        try:
            staging.mkdir()
            data = staging / 'data'
            shutil.copytree(source, data, ignore=lambda folder, names: [name for name in names if Path(folder) == source and name in _EXCLUDED])
            if files != _inventory(data):
                raise ValueError('Source changed during backup')
            _validate(data)
            manifest = {'format': _MARKER, 'created_at': _now().isoformat(), 'expires_at': expiry,
                        'legacy_versions_without_upload_time': unknown, 'sha256': files}
            (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2))
            _sync_tree(staging)
            staging.rename(final)
            try:
                from mobility.storage import DatasetStore
                DatasetStore._sync_directory(destination)
            except BaseException:
                shutil.rmtree(final)
                raise
            return final
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def _manifest(snapshot):
    snapshot = _safe(snapshot)
    if not snapshot.is_dir() or not snapshot.name.startswith('snapshot-'):
        raise ValueError('Not a managed snapshot')
    if {path.name for path in snapshot.iterdir()} != {'manifest.json', 'data'}:
        raise ValueError('Unexpected snapshot contents')
    _inventory(snapshot)
    manifest = json.loads((snapshot / 'manifest.json').read_text())
    if manifest.get('format') != _MARKER or not isinstance(manifest.get('sha256'), dict):
        raise ValueError('Invalid backup manifest')
    _parse(manifest['created_at'])
    if manifest.get('expires_at'):
        _parse(manifest['expires_at'])
    if manifest['sha256'] != _inventory(snapshot / 'data'):
        raise ValueError('Backup checksum or file inventory mismatch')
    actual_expiry, unknown = _retention(snapshot / 'data')
    if manifest.get('expires_at') != actual_expiry or manifest.get('legacy_versions_without_upload_time') != unknown:
        raise ValueError('Backup retention metadata mismatch')
    return manifest


def restore_backup(snapshot: Path, destination: Path) -> dict:
    """Verify and publish an isolated restore; existing destinations always fail."""
    started = time.monotonic()
    snapshot, destination = _safe(snapshot), _safe(destination)
    if destination.exists() or destination.is_relative_to(snapshot) or snapshot.is_relative_to(destination):
        raise ValueError('Restore requires a new nonoverlapping directory')
    manifest = _manifest(snapshot)
    now = _now()
    if manifest.get('expires_at') and _parse(manifest['expires_at']) <= now:
        raise ValueError('Expired backups cannot be restored')
    _validate(snapshot / 'data')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / ('.restore-' + uuid4().hex)
    try:
        shutil.copytree(snapshot / 'data', staging)
        if manifest['sha256'] != _inventory(staging):
            raise ValueError('Restore copy mismatch')
        _validate(staging)
        _sync_tree(staging)
        try:
            destination.mkdir()
        except FileExistsError as error:
            raise ValueError('Restore destination appeared during validation') from error
        try:
            for child in staging.iterdir():
                child.rename(destination / child.name)
            from mobility.storage import DatasetStore
            DatasetStore._sync_directory(destination)
            DatasetStore._sync_directory(destination.parent)
        except BaseException:
            shutil.rmtree(destination)
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    elapsed = time.monotonic() - started
    age = (now - _parse(manifest['created_at'])).total_seconds()
    return {'ok': True, 'elapsed_seconds': elapsed, 'within_rto_target': elapsed <= 3600,
            'backup_age_seconds': age, 'within_rpo_target': 0 <= age <= 86400,
            'note': 'Measured restore only; neither recovery target is a service guarantee.'}


def prune_backups(destination: Path, *, apply: bool = False) -> dict:
    """Inventory expired managed snapshots; explicit apply deletes whole snapshots."""
    destination = _safe(destination)
    candidates, skipped, legacy_copies = [], [], {}
    for snapshot in sorted(destination.iterdir()):
        if not snapshot.name.startswith('snapshot-'):
            skipped.append(snapshot.name)
            continue
        manifest = _manifest(snapshot)
        if manifest.get('expires_at') and _parse(manifest['expires_at']) <= _now():
            candidates.append(snapshot.name)
            if manifest['legacy_versions_without_upload_time']:
                legacy_copies[snapshot.name] = manifest['legacy_versions_without_upload_time']
    if apply:
        for name in candidates:
            snapshot = destination / name
            manifest = _manifest(snapshot)
            if not manifest.get('expires_at') or _parse(manifest['expires_at']) > _now():
                raise ValueError('Snapshot expiry changed')
            shutil.rmtree(snapshot)
    return {'apply': apply, 'candidates': candidates, 'skipped': skipped,
            'legacy_backup_copies_deleted_with_expired_snapshot': legacy_copies,
            'note': 'Whole expired snapshots are removed, including legacy backup copies. Live legacy uploads are untouched.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('create', 'restore'):
        command = sub.add_parser(name)
        command.add_argument('source', type=Path)
        command.add_argument('destination', type=Path)
    prune = sub.add_parser('prune')
    prune.add_argument('destination', type=Path)
    prune.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.command == 'create':
        result = {'snapshot': str(create_backup(args.source, args.destination))}
    elif args.command == 'restore':
        result = restore_backup(args.source, args.destination)
    else:
        result = prune_backups(args.destination, apply=args.apply)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
