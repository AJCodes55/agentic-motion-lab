"""Bounded, deterministic monthly ingestion; no activation side effects."""
import csv
import hashlib
import io
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

import pandas as pd

from mobility.contracts import CategoryMapping, Period, QualitySummary

COLUMNS = tuple(('ride_id rideable_type started_at ended_at start_station_name start_station_id '
                 'end_station_name end_station_id start_lat start_lng end_lat end_lng member_casual').split())
_FILENAME = re.compile(r'JC-(\d{4})(\d{2})-citibike-tripdata\.(?:csv|zip|csv\.zip)\Z')


@dataclass(frozen=True)
class UploadedSource:
    name: str
    content: bytes


@dataclass(frozen=True)
class IngestionLimits:
    max_file_bytes: int
    max_total_bytes: int
    max_expanded_bytes: int
    max_members: int

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in vars(self).values()):
            raise ValueError('Ingestion limits must be positive integers')


@dataclass(frozen=True)
class SourceManifest:
    name: str
    sha256: str
    csv_members: tuple[str, ...]
    member_sha256: tuple[str, ...]


@dataclass(frozen=True)
class CleanedMonth:
    period: Period
    frame: pd.DataFrame
    quality: QualitySummary
    manifest: tuple[SourceManifest, ...]


class IngestionError(ValueError):
    def __init__(self, message: str, quality: QualitySummary, code='ERR_SCHEMA_MISMATCH'):
        super().__init__(message)
        self.quality = quality
        self.code = code


def source_period(name: str) -> Period:
    match = _FILENAME.fullmatch(name)
    if not match:
        raise ValueError('Unsupported source filename')
    try:
        return Period(year=int(match[1]), month=int(match[2]))
    except ValueError:
        raise ValueError('Invalid filename period') from None


def _quality(counts, stages, reason=None):
    total = sum(count for _, count in counts)
    excluded = sum(stages.get(key, 0) for key in (
        'invalid_timestamp_rows', 'outside_month_rows', 'duplicate_rows',
        'missing_station_rows', 'invalid_duration_rows'))
    return QualitySummary(
        source_filenames=tuple(name for name, _ in counts),
        per_csv_parsed_counts=tuple(count for _, count in counts), source_rows=total,
        valid_rows=0 if reason else total-excluded, excluded_rows=excluded,
        candidate_rows=total-excluded if reason else 0, status='rejected' if reason else 'accepted',
        rejection_reason=reason, **stages)


def _reject(message, counts=(), stages=None, stage='validation'):
    raise IngestionError(message, _quality(counts, (stages or {}) | {'stopped_stage': stage}, message))


def _members(source, period, limits):
    if source.name.endswith('.csv'):
        return ((source.name, source.content),)
    try:
        with zipfile.ZipFile(io.BytesIO(source.content)) as zipped:
            infos = zipped.infolist()
            output = []
            expanded = 0
            for info in sorted(infos, key=lambda entry: entry.filename):
                name = info.filename
                path = PurePosixPath(name)
                mode = info.external_attr >> 16
                if (path.is_absolute() or '..' in path.parts or '\\' in name
                        or stat.S_ISLNK(mode) or info.flag_bits & 1):
                    _reject('Unsafe archive member')
                if info.is_dir():
                    continue
                if '__MACOSX' in path.parts or path.name.startswith('._'):
                    continue
                if not path.name.endswith('.csv') or source_period(path.name) != period:
                    _reject('Unsupported archive member or mismatched month')
                expanded += info.file_size
                if expanded > limits.max_expanded_bytes:
                    _reject('Expanded archive limit exceeded')
                if len(output) >= limits.max_members:
                    _reject('Archive CSV member limit exceeded')
                content = zipped.read(info)
                output.append((name, content))
            if not output:
                _reject('Archive contains no CSV data')
            return tuple(output)
    except IngestionError:
        raise
    except (ValueError, OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError):
        _reject('Invalid or unsupported archive')


def _parse(content):
    # csv checks malformed-width records explicitly; Pandas then preserves all strings.
    text = content.decode('utf-8-sig')
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    header = next(reader, None)
    if header is None or len(header) != len(COLUMNS) or set(header) != set(COLUMNS):
        raise ValueError('schema')
    if any(len(record) != len(COLUMNS) for record in reader):
        raise ValueError('row width')
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False,
                       na_filter=False, on_bad_lines='error', skip_blank_lines=False)


def _timestamp(value):
    try:
        parsed = pd.Timestamp(value).as_unit('ns')
        if pd.isna(parsed):
            return pd.NaT
        if parsed.tzinfo is None:
            return parsed.tz_localize('America/New_York', ambiguous='NaT', nonexistent='NaT')
        return parsed.tz_convert('America/New_York')
    except (ValueError, TypeError, OverflowError):
        return pd.NaT


def _clean(frame, period, counts):
    stages = {}
    converted = frame.assign(started_at=frame.started_at.map(_timestamp),
                             ended_at=frame.ended_at.map(_timestamp))
    valid = converted.started_at.notna() & converted.ended_at.notna()
    stages['invalid_timestamp_rows'] = int((~valid).sum())
    frame = converted.loc[valid].copy()
    denominator = len(frame)
    stages['month_threshold_denominator'] = denominator
    if not denominator:
        _reject('No rows with valid timestamps', counts, stages, 'timestamps')
    outside = frame.started_at.map(lambda value: (value.year, value.month) != (period.year, period.month))
    outside_count = int(outside.sum())
    if outside_count * 100 > denominator:
        _reject('Out-of-month rows exceed 1 percent', counts, stages, 'month')
    stages['outside_month_rows'] = outside_count
    frame = frame.loc[~outside].copy()
    duplicate = frame.ride_id.duplicated(keep='first')
    stages['duplicate_rows'] = int(duplicate.sum())
    frame = frame.loc[~duplicate].copy()
    denominator = len(frame)
    stages['station_threshold_denominator'] = denominator
    missing = frame[['start_station_id', 'end_station_id']].apply(
        lambda column: column.str.strip().str.lower().isin(('', 'nan'))).any(axis=1)
    missing_count = int(missing.sum())
    if missing_count * 100 >= denominator * 5:
        _reject('Missing stations reach 5 percent', counts, stages, 'stations')
    stages['missing_station_rows'] = missing_count
    frame = frame.loc[~missing].copy()
    durations = pd.Series([(end.value - start.value) / 1_000_000_000
                           for start, end in zip(frame.started_at, frame.ended_at)],
                          index=frame.index, dtype=float)
    valid = durations.between(60, 86400)
    stages['invalid_duration_rows'] = int((~valid).sum())
    frame = frame.assign(duration_seconds=durations).loc[valid].copy()
    members = frame.member_casual.map({'member': 'Member', 'casual': 'Casual'}).fillna('Unknown')
    bikes = frame.rideable_type.map({'classic_bike': 'Classic', 'electric_bike': 'E-bike'}).fillna('Unknown')
    stages['member_value_mappings'] = tuple(
        CategoryMapping(raw_value=raw, normalized_value={'member': 'Member', 'casual': 'Casual'}.get(raw, 'Unknown'), count=int(count))
        for raw, count in sorted(frame.member_casual.value_counts().items()))
    stages['bike_value_mappings'] = tuple(
        CategoryMapping(raw_value=raw, normalized_value={'classic_bike': 'Classic', 'electric_bike': 'E-bike'}.get(raw, 'Unknown'), count=int(count))
        for raw, count in sorted(frame.rideable_type.value_counts().items()))
    stages['unknown_member_rows'] = int((members == 'Unknown').sum())
    stages['unknown_bike_rows'] = int((bikes == 'Unknown').sum())
    if frame.empty:
        _reject('No valid trips remain', counts, stages, 'duration')
    return frame.assign(member_casual=members, rideable_type=bikes).reset_index(drop=True), stages


def clean_month(sources: tuple[UploadedSource, ...], limits: IngestionLimits) -> CleanedMonth:
    """Clean sources for one month; errors expose aggregate quality only."""
    if not sources or len(sources) > 2:
        _reject('Supply one or two source files')
    if sum(len(item.content) for item in sources) > limits.max_total_bytes:
        _reject('Total upload byte limit exceeded')
    counts, frames, manifest = [], [], []
    expanded = 0
    member_count = 0
    try:
        period = source_period(sources[0].name)
        for source in sorted(sources, key=lambda item: item.name):
            if len(source.content) > limits.max_file_bytes:
                _reject('Source byte limit exceeded', counts)
            if source_period(source.name) != period:
                _reject('Sources must belong to one month', counts)
            members = _members(source, period, limits)
            member_count += len(members)
            if member_count > limits.max_members:
                _reject('Upload CSV member limit exceeded', counts)
            for name, content in members:
                expanded += len(content)
                if expanded > limits.max_expanded_bytes:
                    _reject('Expanded upload byte limit exceeded', counts)
                parsed = _parse(content)
                counts.append((source.name + ':' + name if source.name.endswith('.zip') else name, len(parsed)))
                frames.append(parsed)
            manifest.append(SourceManifest(source.name, hashlib.sha256(source.content).hexdigest(),
                                           tuple(name for name, _ in members),
                                           tuple(hashlib.sha256(content).hexdigest() for _, content in members)))
    except IngestionError as error:
        if counts and not error.quality.source_rows:
            _reject(str(error), counts)
        raise
    except (ValueError, UnicodeError, csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError):
        _reject('Invalid CSV schema, content, or source filename', counts)
    frame, stages = _clean(pd.concat(frames, ignore_index=True), period, counts)
    return CleanedMonth(period, frame, _quality(counts, stages), tuple(manifest))


def validate_batch_sources(sources: tuple[UploadedSource, ...], limits: IngestionLimits) -> None:
    """Reject request-global budget excess before any month can activate.

    Invalid containers are left to per-month validation, allowing independent results.
    ZIP sizes are inspected without decompressing or exposing member content.
    """
    if not sources or len(sources) > 2:
        _reject('Supply one or two source files')
    if sum(len(source.content) for source in sources) > limits.max_total_bytes:
        _reject('Total upload byte limit exceeded')
    expanded, members = 0, 0
    for source in sources:
        if len(source.content) > limits.max_file_bytes:
            _reject('Source byte limit exceeded')
        try:
            period = source_period(source.name)
        except ValueError:
            continue
        if source.name.endswith('.csv'):
            expanded += len(source.content)
            members += 1
        elif source.name.endswith('.zip'):
            try:
                with zipfile.ZipFile(io.BytesIO(source.content)) as zipped:
                    for info in zipped.infolist():
                        path = PurePosixPath(info.filename)
                        if info.is_dir() or '__MACOSX' in path.parts or path.name.startswith('._'):
                            continue
                        mode = info.external_attr >> 16
                        if (path.is_absolute() or '..' in path.parts or '\\' in info.filename
                                or stat.S_ISLNK(mode) or info.flag_bits & 1
                                or not path.name.endswith('.csv')):
                            continue
                        try:
                            if source_period(path.name) != period:
                                continue
                        except ValueError:
                            continue
                        expanded += info.file_size
                        members += 1
            except (zipfile.BadZipFile, OSError, ValueError):
                continue
    if expanded > limits.max_expanded_bytes:
        _reject('Expanded upload byte limit exceeded')
    if members > limits.max_members:
        _reject('Upload CSV member limit exceeded')
