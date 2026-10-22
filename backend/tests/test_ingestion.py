"""Synthetic boundary checks for the ingestion pipeline."""
import csv
import io
import zipfile

import pytest

from mobility.ingestion import IngestionError, IngestionLimits, UploadedSource, clean_month

COLUMNS = ('ride_id rideable_type started_at ended_at start_station_name start_station_id end_station_name end_station_id start_lat start_lng end_lat end_lng member_casual').split()
LIMITS = IngestionLimits(1_000_000, 2_000_000, 4_000_000, 20)


def row(index=0, **changes):
    return dict(zip(COLUMNS, [str(index), 'classic_bike', '2026-01-01 00:00:00', '2026-01-01 00:01:00', 'Start', '001', 'End', '002', '1', '2', '3', '4', 'member'])) | changes


def source(rows, name='JC-202601-citibike-tripdata.csv'):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return UploadedSource(name, stream.getvalue().encode())


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as zipped:
        for name, data in entries:
            zipped.writestr(name, data)
    return UploadedSource('JC-202601-citibike-tripdata.zip', stream.getvalue())


def test_normalization_ids_duration_boundaries():
    result = clean_month((source([row(), row(1, ended_at='2026-01-02 00:00:00', member_casual='other', rideable_type='other'), row(2, ended_at='2026-01-01 00:00:59'), row(3, ended_at='2026-01-02 00:00:01')]),), LIMITS)
    assert result.frame.start_station_id.tolist() == ['001', '001']
    assert result.frame.duration_seconds.tolist() == [60, 86400]
    assert result.frame.member_casual.tolist() == ['Member', 'Unknown']
    assert result.quality.invalid_duration_rows == 2
    assert result.quality.unknown_member_rows == 1


@pytest.mark.parametrize('outside,rejected', [(1, False), (2, True)])
def test_month_threshold(outside, rejected):
    data = source([row(i, started_at='2025-12-31 23:59:00') if i < outside else row(i) for i in range(100)])
    if rejected:
        with pytest.raises(IngestionError) as caught:
            clean_month((data,), LIMITS)
        assert caught.value.quality.month_threshold_denominator == 100
    else:
        assert clean_month((data,), LIMITS).quality.outside_month_rows == 1


@pytest.mark.parametrize('missing,rejected', [(4, False), (5, True)])
def test_station_threshold(missing, rejected):
    data = source([row(i, start_station_id='NaN') if i < missing else row(i) for i in range(100)])
    if rejected:
        with pytest.raises(IngestionError):
            clean_month((data,), LIMITS)
    else:
        assert clean_month((data,), LIMITS).quality.valid_rows == 96


def test_order_duplicate_metadata():
    data = archive([('__MACOSX/._x', b'ignored'), ('z/JC-202601-citibike-tripdata.csv', source([row(member_casual='casual')]).content), ('a/JC-202601-citibike-tripdata.csv', source([row()]).content)])
    result = clean_month((data,), LIMITS)
    assert result.frame.member_casual.tolist() == ['Member']
    assert result.quality.duplicate_rows == 1
    assert result.quality.per_csv_parsed_counts == (1, 1)


@pytest.mark.parametrize('member', ['../JC-202601-citibike-tripdata.csv', '/JC-202601-citibike-tripdata.csv', 'hello.txt', 'JC-202602-citibike-tripdata.csv'])
def test_unsafe_archive(member):
    with pytest.raises(IngestionError):
        clean_month((archive([(member, source([row()]).content)]),), LIMITS)


@pytest.mark.parametrize('data', [b'bad,header\n1,2\n', b','.join(x.encode() for x in COLUMNS)+b'\n1,2\n', b'\xff', source([]).content])
def test_invalid_csv(data):
    with pytest.raises(IngestionError) as caught:
        clean_month((UploadedSource('JC-202601-citibike-tripdata.csv', data),), LIMITS)
    assert '1,2' not in str(caught.value)


def test_invalid_timestamp_and_exact_duplicate_ids():
    result = clean_month((source([row(0, started_at='broken'), row('01'), row('1'), row('1')]),), LIMITS)
    assert result.quality.invalid_timestamp_rows == 1
    assert result.frame.ride_id.tolist() == ['01', '1']
    assert result.quality.source_rows == result.quality.valid_rows + result.quality.excluded_rows


def test_aware_timestamps_use_new_york_month():
    result = clean_month((source([row(started_at='2026-02-01T04:00:00Z', ended_at='2026-02-01T04:01:00Z')]),), LIMITS)
    assert result.frame.started_at.iloc[0].month == 1


@pytest.mark.parametrize('limits', [IngestionLimits(1, 100, 100, 10), IngestionLimits(10000, 1, 10000, 10), IngestionLimits(10000, 10000, 1, 10)])
def test_limits(limits):
    with pytest.raises(IngestionError):
        clean_month((source([row()]),), limits)


def test_station_denominator_after_deduplication():
    rows = [row(i) for i in range(19)] + [row(19, start_station_id='')]
    with pytest.raises(IngestionError) as caught:
        clean_month((source(rows + [row(0) for _ in range(80)]),), LIMITS)
    assert caught.value.quality.station_threshold_denominator == 20
    assert caught.value.quality.duplicate_rows == 80


def test_invalid_timestamp_denominator_and_final_empty():
    with pytest.raises(IngestionError):
        clean_month((source([row(started_at='invalid')]),), LIMITS)
    with pytest.raises(IngestionError) as caught:
        clean_month((source([row(ended_at='2026-01-01 00:00:59')]),), LIMITS)
    assert caught.value.quality.invalid_duration_rows == 1


def test_all_members_schema_validated():
    with pytest.raises(IngestionError):
        clean_month((archive([('a/JC-202601-citibike-tripdata.csv', source([row()]).content), ('b/JC-202601-citibike-tripdata.csv', b'bad\n')]),), LIMITS)


def test_source_order_stable_across_files():
    csv_source = source([row(member_casual='casual')])
    zip_source = archive([('JC-202601-citibike-tripdata.csv', source([row()]).content)])
    result = clean_month((zip_source, csv_source), LIMITS)
    assert result.frame.member_casual.tolist() == ['Casual']


def test_symlink_archive_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as zipped:
        entry = zipfile.ZipInfo('JC-202601-citibike-tripdata.csv')
        entry.create_system = 3
        entry.external_attr = 0o120777 << 16
        zipped.writestr(entry, b'/etc/passwd')
    with pytest.raises(IngestionError):
        clean_month((UploadedSource('JC-202601-citibike-tripdata.zip', stream.getvalue()),), LIMITS)


def test_archive_member_limit():
    with pytest.raises(IngestionError):
        clean_month((archive([('a/JC-202601-citibike-tripdata.csv', source([row()]).content), ('b/JC-202601-citibike-tripdata.csv', source([row()]).content)]),), IngestionLimits(10000, 10000, 10000, 1))


def test_bad_archive_and_filename_and_limits():
    for data in (UploadedSource('JC-202601-citibike-tripdata.zip', b'bad'), source([row()], 'invalid.csv')):
        with pytest.raises(IngestionError):
            clean_month((data,), LIMITS)
    with pytest.raises(ValueError):
        IngestionLimits(0, 1, 1, 1)


def test_batch_global_budget():
    from mobility.ingestion import validate_batch_sources
    first = source([row()])
    second = source([row()], 'JC-202602-citibike-tripdata.csv')
    validate_batch_sources((first, second), LIMITS)
    with pytest.raises(IngestionError):
        validate_batch_sources((first, second), IngestionLimits(10000, 20000, len(first.content), 20))
    with pytest.raises(IngestionError):
        validate_batch_sources((first, second), IngestionLimits(10000, 20000, 20000, 1))


def test_i03_month_denominator_after_timestamp_exclusion():
    rows = [row(i) for i in range(99)] + [row(99, started_at='2025-12-31 23:59:00'), row(100, started_at='invalid')]
    result = clean_month((source(rows),), LIMITS)
    assert result.quality.month_threshold_denominator == 100
    assert result.quality.outside_month_rows == 1
    assert result.quality.valid_rows == 99


def test_i06_missing_five_of_101_accepted_without_rounding():
    result = clean_month((source([row(i, start_station_id='') if i < 5 else row(i) for i in range(101)]),), LIMITS)
    assert result.quality.station_threshold_denominator == 101
    assert result.quality.valid_rows == 96


def test_i11_missing_station_representations_count_once():
    rows = [row(i) for i in range(96)] + [row(96, start_station_id=''), row(97, end_station_id='   '), row(98, start_station_id='NaN'), row(99, start_station_id='', end_station_id='NaN')]
    result = clean_month((source(rows),), LIMITS)
    assert result.quality.missing_station_rows == 4
    assert result.quality.valid_rows == 96


def test_invalid_archive_members_do_not_spend_global_csv_budget():
    from mobility.ingestion import validate_batch_sources
    bad = archive([(f'bad{i}.txt', b'x') for i in range(101)])
    validate_batch_sources((source([row()]), bad), IngestionLimits(100000, 200000, 200000, 1))
    with pytest.raises(IngestionError):
        clean_month((bad,), LIMITS)


def test_literal_station_identifiers_are_preserved():
    result = clean_month((source([row(i, start_station_id=station) for i, station in enumerate(('NULL', 'None', 'NA'))]),), LIMITS)
    assert result.frame.start_station_id.tolist() == ['NULL', 'None', 'NA']
