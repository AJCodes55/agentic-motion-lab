"""Offline, read-only local data inspection; never expires, repairs or deletes files."""
import argparse
from contextlib import closing, contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3

from mobility.contracts import DatasetReference, Period, QualitySummary
from mobility.storage import DatasetStore


class _ReadOnlyStore(DatasetStore):
    enforce_retention = False

    def __init__(self, root: Path) -> None:
        self.root = root
        self.registry = root / 'registry.sqlite'

    @contextmanager
    def _connect(self):
        with closing(sqlite3.connect(self.registry.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            yield db

    def read_kpis(self, reference):
        path = self._resolve(reference) / 'kpis.sqlite'
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('KPI integrity check failed')
            row = db.execute('SELECT payload FROM monthly_kpis WHERE version_id=?', (reference.version_id,)).fetchone()
            embedded = db.execute('SELECT payload FROM metadata').fetchall()
        if len(embedded) != 1 or json.loads(embedded[0][0]) != self.read_metadata(reference) or row is None:
            raise ValueError('KPI metadata mismatch')
        return json.loads(row[0])


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_data_root(root: Path) -> dict:
    """Inspect a stopped service's data root or isolated restored copy.

    Inactive and unregistered directories are inventory only, never deletion
    candidates: saved reports may still reference inactive datasets.
    """
    root = Path(root).absolute()
    issues, manifest = [], {}
    inactive, unregistered = [], []
    if root.is_symlink() or not root.is_dir():
        return {'ok': False, 'issues': ['Data root must be an existing real directory.'],
                'sha256': {}, 'inactive_versions': [], 'unregistered_directories': []}
    paths = sorted(root.rglob('*'))
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            issues.append(f'Unsafe symlink: {relative}')
        elif path.is_file():
            try:
                manifest[relative] = _digest(path)
                if path.name.endswith(('-wal', '-journal')) and path.stat().st_size:
                    issues.append(f'Unsettled SQLite sidecar: {relative}')
            except OSError:
                issues.append(f'Unreadable file: {relative}')
        elif not path.is_dir():
            issues.append(f'Unsupported filesystem entry: {relative}')
    if issues:
        return {'ok': False, 'issues': issues, 'sha256': manifest,
                'inactive_versions': inactive, 'unregistered_directories': unregistered}
    store = _ReadOnlyStore(root)
    try:
        with store._connect() as db:
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                issues.append('Registry integrity check failed.')
            if db.execute('PRAGMA foreign_key_check').fetchall():
                issues.append('Registry contains dangling references.')
            rows = db.execute('SELECT version_id, year, month, sha256, complete FROM versions').fetchall()
            active = db.execute('SELECT year, month, version_id FROM active').fetchall()
        registered = {row[0] for row in rows}
        inactive = sorted(registered - {row[2] for row in active})
        versions = root / 'versions'
        unregistered = sorted(path.name for path in versions.iterdir()
                              if path.is_dir() and path.name not in registered)
        for version_id, year, month, digest, complete in rows:
            try:
                ref = DatasetReference(period=Period(year=year, month=month), version_id=version_id, sha256=digest)
                if complete != 1:
                    raise ValueError('Incomplete version')
                metadata = store.read_metadata(ref)
                metrics = store.read_kpis(ref)
                if metrics != store._metrics(store.read_frame(ref), QualitySummary.model_validate_json(json.dumps(metadata['quality']))):
                    raise ValueError('Metrics mismatch')
            except (OSError, ValueError, KeyError, TypeError, AttributeError, sqlite3.Error):
                issues.append(f'Invalid registered dataset: {version_id}')
        for year, month, version_id in active:
            if not any(row[0] == version_id and row[1:3] == (year, month) and row[4] == 1 for row in rows):
                issues.append('Active pointer does not match a complete dataset period.')
    except (OSError, ValueError, TypeError, AttributeError, sqlite3.Error):
        issues.append('Data registry cannot be inspected.')
    return {'ok': not issues, 'issues': issues, 'sha256': manifest,
            'inactive_versions': inactive, 'unregistered_directories': unregistered}


def main() -> None:
    parser = argparse.ArgumentParser(description='Inspect an offline local data root without modifying it.')
    parser.add_argument('data_root', type=Path)
    args = parser.parse_args()
    result = inspect_data_root(args.data_root)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
