"""Local bounded ingestion orchestration and approved public-source fetching."""
from contextlib import contextmanager
from collections.abc import Iterator, Sequence
import fcntl
import hashlib
import sqlite3
from threading import Lock
from uuid import uuid4

import httpx
from fastapi import HTTPException

from .config import Settings
from .contracts import IngestionBatch, MonthIngestionResult, Period, QualitySummary
from .ingestion import IngestionError, IngestionLimits, UploadedSource, clean_month, source_period, validate_batch_sources
from .storage import DatasetStore

_PROCESS_LOCK = Lock()


class IngestionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.limits = IngestionLimits(settings.max_file_bytes, settings.max_total_bytes,
                                      settings.max_expanded_bytes, settings.max_csv_members)

    @property
    def store(self) -> DatasetStore:
        return DatasetStore(self.settings.data_root)

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        if not _PROCESS_LOCK.acquire(blocking=False):
            raise HTTPException(409)
        try:
            self.settings.data_root.mkdir(parents=True, exist_ok=True)
            with (self.settings.data_root / 'ingestion.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise HTTPException(409) from None
                try:
                    yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        finally:
            _PROCESS_LOCK.release()

    def ingest(self, sources: tuple[UploadedSource, ...]) -> IngestionBatch:
        ingestion_id = str(uuid4())
        try:
            validate_batch_sources(tuple(sources), self.limits)
        except IngestionError as error:
            self._quarantine(ingestion_id, sources, error.quality)
            raise HTTPException(413) from None
        groups = {}
        results = []
        for source in sources:
            try:
                period = source_period(source.name)
            except ValueError:
                quality = QualitySummary(source_rows=0, valid_rows=0, excluded_rows=0,
                                         status='rejected', stopped_stage='validation', rejection_reason='Unsupported source filename')
                self._quarantine(ingestion_id, (source,), quality)
                results.append(MonthIngestionResult(period=None, status='rejected', dataset=None,
                    quality=quality, error_code='ERR_SCHEMA_MISMATCH', message='Unsupported source filename'))
                continue
            groups.setdefault((period.year, period.month), []).append(source)
        for grouped in groups.values():
            try:
                cleaned = clean_month(tuple(grouped), self.limits)
                try:
                    reference = self.store.persist_and_activate(cleaned)
                except (OSError, ValueError, sqlite3.Error):
                    quality = QualitySummary(**(cleaned.quality.model_dump() | {
                        'status': 'rejected', 'stopped_stage': 'storage',
                        'candidate_rows': cleaned.quality.valid_rows, 'valid_rows': 0,
                        'rejection_reason': 'Storage validation or activation failed.'}))
                    raise IngestionError('Storage validation or activation failed.', quality, 'ERR_TOOL_EXECUTION') from None
                results.append(MonthIngestionResult(period=cleaned.period, status='accepted', dataset=reference,
                    quality=cleaned.quality, error_code=None, message='Month activated.'))
            except IngestionError as error:
                self._quarantine(ingestion_id, grouped, error.quality)
                results.append(MonthIngestionResult(period=source_period(grouped[0].name), status='rejected',
                    dataset=None, quality=error.quality, error_code=error.code, message=str(error)))
        return IngestionBatch(ingestion_id=ingestion_id, results=tuple(results))

    def _quarantine(self, ingestion_id: str, sources: Sequence[UploadedSource], quality: QualitySummary) -> None:
        directory = self.settings.data_root / 'quarantine' / ingestion_id
        directory.mkdir(parents=True, exist_ok=True)
        manifests = []
        for source in sources:
            # Generated names prevent untrusted filenames from becoming filesystem paths.
            name = f'{uuid4().hex}.bin'
            (directory / name).write_bytes(source.content)
            manifests.append({'source_name': source.name, 'quarantine_file': name,
                              'sha256': hashlib.sha256(source.content).hexdigest()})
        self.store.record_rejection(ingestion_id, quality, manifests)

    def fetch(self, period: Period) -> UploadedSource:
        prefix = f'JC-{period.year:04d}{period.month:02d}-citibike-tripdata'
        try:
            with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False) as client:
                for suffix in ('.zip', '.csv.zip'):
                    name = prefix + suffix
                    with client.stream('GET', 'https://s3.amazonaws.com/tripdata/' + name) as response:
                        if response.status_code == 404:
                            continue
                        if response.status_code != 200:
                            raise HTTPException(502)
                        chunks = []
                        total = 0
                        for chunk in response.iter_bytes():
                            total += len(chunk)
                            if total > self.settings.max_file_bytes:
                                raise HTTPException(413)
                            chunks.append(chunk)
                        return UploadedSource(name, b''.join(chunks))
        except httpx.HTTPError:
            raise HTTPException(502) from None
        raise HTTPException(404)
