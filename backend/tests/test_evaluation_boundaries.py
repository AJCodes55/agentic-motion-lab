"""Synthetic Phase 0 boundary regressions; no curator authorship is implied."""
from types import SimpleNamespace

import pandas as pd
import pytest

from mobility.analytics import AnalyticsService, contribution_breakdown
from mobility.contracts import Period, QualitySummary
from mobility.ingestion import IngestionError, clean_month
from mobility.storage import DatasetStore
from test_analytics import fixture
from test_ingestion import LIMITS, row, source


@pytest.mark.parametrize(('prior_count', 'current_count', 'qualifies'), [
    (2000, 1800, False), (500, 400, False), (1000, 899, True),
])
def test_n05_each_trigger_threshold_isolated(tmp_path, prior_count, current_count, qualifies):
    store = DatasetStore(tmp_path)
    prior = fixture(store, 1, {'S': prior_count})
    current = fixture(store, 2, {'S': current_count})
    result = AnalyticsService(store).station_movers(current, prior)
    candidate = result.mandatory_investigation_candidate
    assert (candidate is not None) is qualifies
    if candidate is not None:
        assert candidate.station_id == 'S'
        assert candidate.delta == -101


def test_i04_invalid_start_null_end_invalid_end_excluded_before_month_gate():
    rows = [row(0, started_at='invalid'), row(1, ended_at=None), row(2, ended_at='invalid')]
    with pytest.raises(IngestionError) as caught:
        clean_month((source(rows),), LIMITS)
    quality = caught.value.quality
    assert quality.invalid_timestamp_rows == 3
    assert quality.month_threshold_denominator == 0
    assert quality.valid_rows == 0


def test_n16_arrivals_do_not_inflate_station_starts_or_mix(tmp_path):
    store = DatasetStore(tmp_path)
    rows = [
        {'ride_id': 'a', 'start_station_id': 'A', 'end_station_id': 'B',
         'member_casual': 'Member', 'rideable_type': 'Classic', 'duration_seconds': 60.0},
        {'ride_id': 'b', 'start_station_id': 'A', 'end_station_id': 'B',
         'member_casual': 'Casual', 'rideable_type': 'E-bike', 'duration_seconds': 180.0},
        {'ride_id': 'arrival', 'start_station_id': 'B', 'end_station_id': 'A',
         'member_casual': 'Unknown', 'rideable_type': 'Unknown', 'duration_seconds': 600.0},
    ]
    frame = pd.DataFrame([item | {'started_at': '2026-01-01 10:00:00'} for item in rows])
    ref = store.persist_and_activate(SimpleNamespace(
        period=Period(year=2026, month=1), frame=frame,
        quality=QualitySummary(source_rows=3, valid_rows=3, excluded_rows=0), sources=()))
    service = AnalyticsService(store)
    stations = {item.station_id: item for item in service.station_analysis(ref).stations}
    assert stations['A'].current_count == 2
    assert stations['B'].current_count == 1
    # The station-specific aggregate also excludes the arriving Unknown trip.
    station_rows = store.read_frame(ref).loc[lambda data: data.start_station_id == 'A']
    assert station_rows.duration_seconds.mean() / 60 == 2
    for dimension, categories in [('member_casual', {'Member', 'Casual'}),
                                  ('rideable_type', {'Classic', 'E-bike'})]:
        assert station_rows[dimension].value_counts().to_dict() == dict.fromkeys(categories, 1)


def test_n08_membership_and_fleet_contributions_remain_independent():
    membership = contribution_breakdown({'Member': 20, 'Casual': 80, 'Unknown': 0},
        {'Member': 100, 'Casual': 100, 'Unknown': 0}, -100, 'member_casual')
    fleet = contribution_breakdown({'Classic': 50, 'E-bike': 50, 'Unknown': 0},
        {'Classic': 100, 'E-bike': 100, 'Unknown': 0}, -100, 'rideable_type')
    assert membership.wording == 'Primarily driven by Member.'
    assert {item.category: item.contribution_pct for item in membership.categories} == {
        'Member': 80, 'Casual': 20, 'Unknown': None}
    assert {item.category: item.contribution_pct for item in fleet.categories} == {
        'Classic': 50, 'E-bike': 50, 'Unknown': None}
    assert {item.category for item in fleet.leaders} == {'Classic', 'E-bike'}
