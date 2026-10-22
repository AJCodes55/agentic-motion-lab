import pytest
from pydantic import ValidationError
from mobility.contracts import QualitySummary, CategoryMapping, FetchRequest, Period, MonthIngestionResult


def test_rejected_rows_are_not_valid_or_double_counted():
    quality = QualitySummary(status='rejected', rejection_reason='Missing stations at threshold', stopped_stage='stations', source_rows=100, valid_rows=0, excluded_rows=0, candidate_rows=100)
    assert quality.valid_rows == 0
    assert quality.candidate_rows == 100
    with pytest.raises(ValidationError):
        QualitySummary(source_rows=100, valid_rows=99, excluded_rows=1, candidate_rows=1)


def test_rejected_quality_requires_reason_and_no_accepted_rows():
    with pytest.raises(ValidationError):
        QualitySummary(status='rejected', source_rows=1, valid_rows=1, excluded_rows=0)


def test_mapping_and_fetch_are_strict():
    assert CategoryMapping(raw_value='odd', normalized_value='Unknown', count=1).count == 1
    assert FetchRequest(period=Period(year=2026, month=1)).period.month == 1
    with pytest.raises(ValidationError):
        FetchRequest(period=Period(year=2026, month=1), url='https://untrusted.invalid')


def test_rejected_month_has_no_active_dataset():
    quality = QualitySummary(status='rejected', source_rows=0, valid_rows=0, excluded_rows=0, rejection_reason='Schema mismatch')
    result = MonthIngestionResult(period=None, status='rejected', dataset=None, quality=quality, message='Schema mismatch', error_code='ERR_SCHEMA_MISMATCH')
    assert result.dataset is None


def test_public_source_labels_are_bounded_but_stored_quality_is_unchanged():
    from mobility.contracts import PublicQualitySummary
    name = 'nested/' * 100 + 'JC-202601-citibike-tripdata.csv'
    full = QualitySummary(source_rows=1, valid_rows=1, excluded_rows=0,
                          source_filenames=(name,), per_csv_parsed_counts=(1,))
    public = PublicQualitySummary.from_summary(full)
    assert public.source_labels_truncated
    assert len(public.source_filenames[0]) == 256
    assert full.source_filenames[0] == name
    assert 'member_value_mappings' not in public.model_dump()
