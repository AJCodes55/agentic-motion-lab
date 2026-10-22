from types import SimpleNamespace

import pandas as pd
import pytest

from mobility.analytics import AnalyticsService, station_change, contribution_breakdown
from mobility.contracts import Period, QualitySummary
from mobility.storage import DatasetStore


def test_station_eligibility_materiality_and_trigger_boundaries():
    assert station_change('S', 'S', 50, 99).percentage_change is None
    assert station_change('S', 'S', 50, 100).percentage_change == -50
    assert station_change('S', 'S', 0, 150).status == 'removed'
    assert station_change('S', 'S', 150, 0).status == 'new'
    for current, expected in [(951, 'Flat'), (950, 'Moderate Change'), (900, 'Moderate Change'), (899, 'Significant Change')]:
        assert station_change('S', 'S', current, 1000).materiality == expected


def test_contributions_ties_unknown_zero_and_sample():
    result = contribution_breakdown({'Member': 50, 'Unknown': 50}, {'Member': 100, 'Unknown': 100}, -100, 'member_casual')
    assert [leader.category for leader in result.leaders] == ['Member', 'Unknown']
    assert result.wording == 'Jointly led by Member, Unknown (unclassified) (each 50%).'
    assert contribution_breakdown({'Member': 110, 'Casual': 90}, {'Member': 100, 'Casual': 100}, 0, 'member_casual').wording is None
    result = contribution_breakdown({'Member': 0, 'Casual': 100}, {'Member': 99, 'Casual': 101}, -100, 'member_casual')
    assert result.categories[0].contribution_pct is None
    assert result.leaders[0].category == 'Casual'


def fixture(store, month, stations):
    rows = [dict(ride_id=f'{station}-{i}', started_at=f'2026-{month:02d}-01 10:00:00', start_station_id=station,
                 start_station_name=station, member_casual='Member', rideable_type='Classic', duration_seconds=120.0)
            for station, count in stations.items() for i in range(count)]
    return store.persist_and_activate(SimpleNamespace(period=Period(year=2026, month=month), frame=pd.DataFrame(rows),
        quality=QualitySummary(source_rows=len(rows), valid_rows=len(rows), excluded_rows=0), sources=()))


def test_pinned_metrics_ranking_daily_global_candidate_and_adjacency(tmp_path):
    store = DatasetStore(tmp_path)
    prior = fixture(store, 1, {'R1': 1000, 'R2': 900, 'R3': 800, 'R4': 700, 'R5': 600, 'S': 500})
    current = fixture(store, 2, {'S': 399})
    service = AnalyticsService(store)
    movers = service.station_movers(current, prior)
    assert len(movers.top_5_decreases) == 5
    assert movers.mandatory_investigation_candidate.station_id == 'S'
    assert service.kpi_summary(current).total_trips == 399
    assert service.kpi_summary(current).average_duration_minutes == 2
    assert len(service.daily_trend(current).days) == 28
    assert service.daily_trend(current).days[1].count == 0
    assert service.station_analysis(current).stations[0].current_count == 399
    assert service.analyze_station_variance('S', current, prior).member_casual.leaders[0].category == 'Member'
    replacement = fixture(store, 2, {'S': 1})
    assert service.kpi_summary(current).total_trips == 399
    assert service.kpi_summary(replacement).total_trips == 1
    wrong = current.model_copy(update={'period': Period(year=2026, month=3)})
    with pytest.raises(ValueError, match='adjacent'):
        service.compare_periods(wrong, prior)


@pytest.mark.parametrize(('current', 'prior', 'expected'), [
    ({'Member': 20, 'Casual': 80}, {'Member': 100, 'Casual': 100}, 'Primarily driven by Member.'),
    ({'Member': 0, 'Casual': 100}, {'Member': 100, 'Casual': 100}, 'Driven entirely by Member.'),
    ({'Member': 80, 'Casual': 120}, {'Member': 200, 'Casual': 100}, 'More than accounted for by Member.'),
    ({'Member': 40, 'Casual': 60}, {'Member': 100, 'Casual': 100}, 'Driven by a mix of factors.'),
    ({'Member': 80, 'Unknown': 120}, {'Member': 100, 'Unknown': 200}, 'Driven primarily by unclassified data.'),
])
def test_single_leader_templates(current, prior, expected):
    assert contribution_breakdown(current, prior, sum(current.values()) - sum(prior.values()), 'member_casual').wording == expected


def test_tie_order_trigger_edges_strict_inputs_and_year_boundary(tmp_path):
    from pydantic import ValidationError
    from mobility.analytics import prior_period
    assert prior_period(Period(year=2026, month=1)) == Period(year=2025, month=12)
    with pytest.raises(ValueError):
        prior_period(Period(year=1, month=1))
    store = DatasetStore(tmp_path)
    prior = fixture(store, 1, {'A': 1000, 'B': 1000, 'C': 2000, 'D': 500, 'E': 1000})
    current = fixture(store, 2, {'A': 800, 'B': 800, 'C': 1800, 'D': 400, 'E': 899, 'N': 150})
    service = AnalyticsService(store)
    movers = service.station_movers(current, prior)
    assert movers.mandatory_investigation_candidate.station_id == 'A'
    assert [item.station_id for item in movers.top_5_decreases[:3]] == ['A', 'B', 'C']
    assert movers.top_5_increases[0].status == 'new'
    comparison = service.compare_periods(current, prior)
    assert comparison.total_trips_change == 4849 - 5500
    assert len(service.daily_trend(prior).days) == 31
    with pytest.raises(ValidationError):
        service.station_analysis(current, True)
    with pytest.raises(ValueError, match='absent'):
        service.analyze_station_variance('missing', current, prior)
    assert service.analyze_station_variance('N', current, prior).station.status == 'new'


def test_comparison_metrics_have_explicit_units_and_exact_shares(tmp_path):
    store = DatasetStore(tmp_path)
    prior = fixture(store, 1, {'S': 300})
    current = fixture(store, 2, {'S': 200})
    result = AnalyticsService(store).compare_periods(current, prior)
    assert len(result.metrics) == 8
    total, duration, member, casual, unknown, classic, electric, fleet_unknown = result.metrics
    assert total.delta == -100 and total.unit == 'trips'
    assert total.materiality == 'Significant Change'
    assert duration.delta == 0 and duration.unit == 'minutes'
    assert member.delta == 0 and member.unit == 'percentage_points'
    assert member.eligible is False
    assert member.percentage_change is None
    assert member.eligibility_reason == 'percentage_not_applicable'
    assert casual.percentage_change is None and casual.eligible is False


def test_low_sample_aggregate_percentage_is_null(tmp_path):
    store = DatasetStore(tmp_path)
    prior = fixture(store, 1, {'S': 2})
    current = fixture(store, 2, {'S': 4})
    comparison = AnalyticsService(store).compare_periods(current, prior)
    assert comparison.total_trips_change == 2
    assert comparison.total_trips_percentage_change is None
    assert comparison.metrics[0].eligibility_reason == 'prior_sample_below_100'
