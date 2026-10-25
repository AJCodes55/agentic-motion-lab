"""Persistent immutable monthly artifacts with one transactional active pointer."""
from contextlib import contextmanager, closing
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4
from typing import Any, Protocol

from mobility.ingestion import SourceManifest
from mobility.lifecycle import expires_at, timestamp, utc_now

import pandas as pd

from mobility.contracts import DatasetReference, Period, QualitySummary


SourceEvidence = SourceManifest | dict[str, Any]


class CleanedDataset(Protocol):
    period: Period
    frame: pd.DataFrame
    quality: QualitySummary
    manifest: tuple[SourceManifest, ...]


class DatasetStore:
    enforce_retention = True

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'versions').mkdir(exist_ok=True)
        (self.root / 'rejections').mkdir(exist_ok=True)
        self.registry = (self.root / 'registry.sqlite').resolve()
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS versions (
                  version_id TEXT PRIMARY KEY, year INTEGER, month INTEGER,
                  sha256 TEXT NOT NULL, complete INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS active (
                  year INTEGER, month INTEGER, version_id TEXT NOT NULL REFERENCES versions(version_id),
                  PRIMARY KEY(year, month));
                CREATE TABLE IF NOT EXISTS retention (
                  artifact_kind TEXT NOT NULL, artifact_id TEXT NOT NULL,
                  uploaded_at TEXT NOT NULL,
                  PRIMARY KEY(artifact_kind, artifact_id));
            ''')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.registry, timeout=30)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _dates(values):
        def local(value):
            timestamp = pd.Timestamp(value)
            if timestamp.tzinfo is None:
                return timestamp.tz_localize('America/New_York', ambiguous='raise', nonexistent='raise')
            return timestamp.tz_convert('America/New_York')
        return pd.Series(pd.DatetimeIndex([local(value) for value in values]), index=values.index)

    @classmethod
    def _metrics(cls, frame, quality):
        total = len(frame)
        exclusions = sum(getattr(quality, key) for key in (
            'invalid_timestamp_rows', 'outside_month_rows', 'duplicate_rows',
            'missing_station_rows', 'invalid_duration_rows'))
        if not total or total != quality.valid_rows or exclusions != quality.excluded_rows:
            raise ValueError('Cleaned quality counts do not reconcile')
        dates = cls._dates(frame['started_at'])
        if dates.isna().any() or frame['start_station_id'].isna().any():
            raise ValueError('Cleaned starts require dates and station IDs')
        if dates.dt.date.value_counts().sum() != total or frame.groupby('start_station_id').size().sum() != total:
            raise ValueError('Daily and station starts must reconcile')
        durations = pd.to_numeric(frame['duration_seconds'], errors='raise')
        if not durations.map(math.isfinite).all() or (durations <= 0).any():
            raise ValueError('Cleaned durations must be finite and positive')
        categories = {}
        for dimension, allowed in (('member_casual', ('Member', 'Casual', 'Unknown')),
                                   ('rideable_type', ('Classic', 'E-bike', 'Unknown'))):
            counts = frame[dimension].value_counts()
            if sum(counts.get(c, 0) for c in allowed) != total:
                raise ValueError('Category counts do not reconcile')
            categories[dimension] = {c: {'count': int(counts.get(c, 0)),
                                         'share': int(counts.get(c, 0)) / total * 100} for c in allowed}
        duration_sum = float(durations.sum())
        return {'total_trips': total, 'duration_seconds_sum': duration_sum,
                'duration_count': total, 'average_duration_minutes': duration_sum / total / 60,
                'categories': categories}

    def prepare_version(self, period: Period, frame: pd.DataFrame, quality: QualitySummary,
                        sources: tuple[SourceEvidence, ...] = (),
                        uploaded_at: datetime | None = None) -> DatasetReference:
        upload_time = timestamp(uploaded_at if uploaded_at is not None else utc_now())
        metrics = self._metrics(frame, quality)
        dates = self._dates(frame['started_at'])
        if not ((dates.dt.year == period.year) & (dates.dt.month == period.month)).all():
            raise ValueError('Cleaned rows must match the requested period')
        version_id = f'jc_{period.year:04d}_{period.month:02d}_{uuid4().hex}'
        directory = self.root / 'versions' / version_id
        directory.mkdir()
        digest = self._write_artifacts(directory, frame, period, version_id, quality, sources, metrics)
        reference = DatasetReference(period=period, version_id=version_id, sha256=digest)
        with self._connect() as db:
            db.execute('INSERT INTO versions VALUES (?, ?, ?, ?, 1)',
                       (version_id, period.year, period.month, digest))
            db.execute('INSERT INTO retention VALUES (?, ?, ?)',
                       ('version', version_id, upload_time))
        return reference

    @staticmethod
    def _sync_directory(directory):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _write_artifacts(self, directory, frame, period, version_id, quality, sources, metrics):
        csv_path = directory / 'cleaned.csv'
        frame.to_csv(csv_path, index=False)
        digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        metadata = {'period': period.model_dump(), 'version_id': version_id, 'sha256': digest,
                    'quality': quality.model_dump(mode='json'), 'sources': self._serialize_sources(sources)}
        (directory / 'metadata.json').write_text(json.dumps(metadata, allow_nan=False), encoding='utf-8')
        with closing(sqlite3.connect(directory / 'kpis.sqlite')) as db:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE monthly_kpis (version_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('INSERT INTO monthly_kpis VALUES (?, ?)', (version_id, json.dumps(metrics, allow_nan=False)))
            db.execute('CREATE TABLE metadata (payload TEXT NOT NULL)')
            db.execute('INSERT INTO metadata VALUES (?)', (json.dumps(metadata, allow_nan=False),))
            db.commit()
        # Read persisted representations before making the version eligible for activation.
        if len(pd.read_csv(csv_path)) != metrics['total_trips']:
            raise ValueError('Persisted Raw Lake count does not reconcile')
        for path in directory.iterdir():
            with path.open('rb') as file:
                os.fsync(file.fileno())
            path.chmod(0o444)
        self._sync_directory(directory)
        self._sync_directory(directory.parent)
        return digest

    def is_expired(self, reference: DatasetReference, now: datetime | None = None) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT uploaded_at FROM retention WHERE artifact_kind='version' AND artifact_id=?",
                (reference.version_id,)).fetchone()
        return row is not None and expires_at(row[0]) <= (now if now is not None else utc_now())

    def _resolve(self, reference):
        reference = DatasetReference.model_validate(reference)
        if self.enforce_retention and self.is_expired(reference):
            raise ValueError('Dataset retention period has expired')
        with self._connect() as db:
            row = db.execute('SELECT year, month, sha256, complete FROM versions WHERE version_id=?',
                             (reference.version_id,)).fetchone()
        expected = (reference.period.year, reference.period.month, reference.sha256, 1)
        if row != expected:
            raise ValueError('Dataset reference is not a complete registered version')
        directory = self.root / 'versions' / reference.version_id
        if hashlib.sha256((directory / 'cleaned.csv').read_bytes()).hexdigest() != reference.sha256:
            raise ValueError('Raw Lake checksum mismatch')
        return directory

    def activate(self, reference: DatasetReference) -> None:
        metadata = self.read_metadata(reference)
        persisted = self.read_kpis(reference)
        recomputed = self._metrics(self.read_frame(reference), QualitySummary.model_validate_json(json.dumps(metadata['quality'])))
        if persisted != recomputed:
            raise ValueError('Persisted monthly KPIs do not reconcile')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO active VALUES (?, ?, ?) ON CONFLICT(year, month) DO UPDATE SET version_id=excluded.version_id',
                       (reference.period.year, reference.period.month, reference.version_id))

    def persist_and_activate(self, cleaned: CleanedDataset,
                             uploaded_at: datetime | None = None) -> DatasetReference:
        reference = self.prepare_version(cleaned.period, cleaned.frame, cleaned.quality, getattr(cleaned, 'manifest', getattr(cleaned, 'sources', ())), uploaded_at=uploaded_at)
        self.activate(reference)
        return reference

    def pin_periods(self, periods: tuple[Period, ...]) -> tuple[DatasetReference, ...]:
        references = []
        with self._connect() as db:
            db.execute('BEGIN')
            for period in periods:
                row = db.execute('SELECT v.version_id, v.sha256 FROM active a JOIN versions v ON a.version_id=v.version_id WHERE a.year=? AND a.month=? AND v.complete=1',
                                 (period.year, period.month)).fetchone()
                if row is None:
                    raise KeyError(f'No active dataset for {period.year:04d}-{period.month:02d}')
                reference = DatasetReference(period=period, version_id=row[0], sha256=row[1])
                if self.enforce_retention and self.is_expired(reference):
                    raise KeyError(f'No active dataset for {period.year:04d}-{period.month:02d}')
                references.append(reference)
        return tuple(references)

    def read_frame(self, reference: DatasetReference) -> pd.DataFrame:
        frame = pd.read_csv(self._resolve(reference) / 'cleaned.csv', keep_default_na=False,
                            float_precision='round_trip',
                            dtype={name: str for name in (
                                'ride_id', 'rideable_type', 'started_at', 'ended_at',
                                'start_station_name', 'start_station_id', 'end_station_name',
                                'end_station_id', 'start_lat', 'start_lng', 'end_lat', 'end_lng',
                                'member_casual')})
        return frame

    def read_metadata(self, reference: DatasetReference) -> dict[str, Any]:
        metadata = json.loads((self._resolve(reference) / 'metadata.json').read_text(encoding='utf-8'))
        if any(metadata.get(key) != value for key, value in reference.model_dump(mode='json').items()):
            raise ValueError('Dataset metadata identity mismatch')
        return metadata

    def read_kpis(self, reference: DatasetReference) -> dict[str, Any]:
        path = self._resolve(reference) / 'kpis.sqlite'
        with closing(sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)) as db:
            row = db.execute('SELECT payload FROM monthly_kpis WHERE version_id=?', (reference.version_id,)).fetchone()
            embedded = db.execute('SELECT payload FROM metadata').fetchall()
        if len(embedded) != 1 or json.loads(embedded[0][0]) != self.read_metadata(reference):
            raise ValueError('SQLite metadata identity mismatch')
        if row is None:
            raise ValueError('KPI store version mismatch')
        return json.loads(row[0])

    @staticmethod
    def _serialize_sources(sources):
        return [asdict(source) if is_dataclass(source) else source for source in sources]

    def list_active(self) -> tuple[DatasetReference, ...]:
        with self._connect() as db:
            rows = db.execute('SELECT a.year, a.month, v.version_id, v.sha256 FROM active a JOIN versions v ON a.version_id=v.version_id WHERE v.complete=1 ORDER BY a.year, a.month').fetchall()
        references = tuple(DatasetReference(period=Period(year=row[0], month=row[1]),
                                            version_id=row[2], sha256=row[3]) for row in rows)
        return tuple(reference for reference in references
                     if not self.enforce_retention or not self.is_expired(reference))

    def record_rejection(self, upload_id: str, quality: QualitySummary,
                         sources: Sequence[SourceEvidence] = (),
                         uploaded_at: datetime | None = None) -> Path:
        upload_time = timestamp(uploaded_at if uploaded_at is not None else utc_now())
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', upload_id):
            raise ValueError('Invalid upload ID')
        path = self.root / 'rejections' / f'{upload_id}_{uuid4().hex}.json'
        with path.open('x', encoding='utf-8') as file:
            json.dump({'upload_id': upload_id, 'quality': quality.model_dump(mode='json'), 'sources': self._serialize_sources(sources)}, file, allow_nan=False)
            file.flush()
            os.fsync(file.fileno())
        self._sync_directory(path.parent)
        with self._connect() as db:
            db.execute('INSERT INTO retention VALUES (?, ?, ?)',
                       ('rejection', path.name, upload_time))
        return path
