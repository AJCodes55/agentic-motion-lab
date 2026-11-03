"""rank_stations must be deterministic, sample-aware and pinned to one dataset version."""
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

from mobility.agent_tools import AgentTools
from mobility.analytics import AnalyticsService
from mobility.contracts import Period, QualitySummary, RankFilter, RankStationsArgs, ToolArguments
from mobility.storage import DatasetStore

FEB = Period(year=2026, month=2)


def trips(station, count, *, member='Member', bike='Classic', seconds=600.0, end=None):
    end = end or station
    return [dict(started_at='2026-02-03 08:00:00', start_station_id=station, start_station_name=f'{station} Plaza',
                 end_station_id=end, end_station_name=f'{end} Plaza', member_casual=member, rideable_type=bike,
                 duration_seconds=seconds) for _ in range(count)]


@pytest.fixture
def ranked(tmp_path):
    rows = (trips('A', 120, bike='E-bike', end='B') + trips('A', 30, member='Casual', end='B')
            + trips('B', 60, bike='E-bike', seconds=1200.0, end='A') + trips('B', 60, seconds=1200.0, end='A')
            + trips('F', 100, bike='E-bike') + trips('F', 100)
            + trips('C', 1, member='Casual', bike='E-bike', seconds=3000.0, end='Z')
            + trips('D', 1))
    frame = pd.DataFrame(rows)
    frame.insert(0, 'ride_id', [f'r{i}' for i in range(len(frame))])
    store = DatasetStore(tmp_path)
    ref = store.persist_and_activate(SimpleNamespace(period=FEB, frame=frame,
        quality=QualitySummary(source_rows=len(frame), valid_rows=len(frame), excluded_rows=0), sources=()))
    return AnalyticsService(store), ref, store


def rank(service, ref, metric, order='top', limit=5, filter_by=None):
    return service.rank_stations(ref, RankStationsArgs(period='2026-02', metric=metric, order=order,
                                                       limit=limit, filter_by=filter_by))


def ids(result):
    return [row.station_id for row in result.rows]


def test_total_starts_top_breaks_ties_by_station_id(ranked):
    service, ref, _ = ranked
    result = rank(service, ref, 'total_starts')
    assert ids(result) == ['F', 'A', 'B', 'C', 'D']
    assert [row.metric_value for row in result.rows] == [200, 150, 120, 1, 1]
    assert [row.is_tied for row in result.rows] == [False, False, False, True, True]
    assert result.leader_station_id == 'F'
    assert result.dataset_version_id == ref.version_id
    assert result.minimum_sample is None and result.excluded_low_sample_count == 0
    assert result.eligible_station_count == 5


def test_bottom_total_starts_keeps_one_trip_stations(ranked):
    service, ref, _ = ranked
    result = rank(service, ref, 'total_starts', 'bottom', 2)
    assert ids(result) == ['C', 'D']
    assert result.leader_station_id == 'C'
    assert result.rows[0].rank == 1 and result.rows[0].station_name == 'C Plaza'


def test_total_ends_uses_end_station_and_secondary_starts(ranked):
    service, ref, _ = ranked
    result = rank(service, ref, 'total_ends', limit=10)
    assert ids(result) == ['F', 'B', 'A', 'D', 'Z']
    z = result.rows[-1]
    assert (z.metric_value, z.total_starts, z.total_ends, z.station_name) == (1, 0, 1, 'Z Plaza')


def test_share_metrics_exclude_low_samples_and_break_ties_by_starts(ranked):
    service, ref, _ = ranked
    result = rank(service, ref, 'ebike_share_pct')
    assert ids(result) == ['A', 'F', 'B']
    assert [row.metric_value for row in result.rows] == [80.0, 50.0, 50.0]
    assert [row.is_tied for row in result.rows] == [False, True, True]
    assert 'C' not in ids(result)
    assert (result.eligible_station_count, result.excluded_low_sample_count, result.minimum_sample) == (3, 2, 100)
    casual = rank(service, ref, 'casual_share_pct', 'bottom')
    assert ids(casual) == ['F', 'B', 'A']
    assert casual.rows[-1].metric_value == 20.0


def test_average_duration_is_minutes(ranked):
    service, ref, _ = ranked
    result = rank(service, ref, 'avg_duration_min', limit=1)
    assert ids(result) == ['B'] and result.rows[0].metric_value == 20.0


def test_filter_applies_before_aggregation(ranked):
    service, ref, _ = ranked
    result = rank(service, ref, 'total_starts', filter_by=RankFilter(member_casual='casual'))
    assert ids(result) == ['A', 'C']
    assert result.rows[0].metric_value == 30
    bikes = rank(service, ref, 'casual_share_pct', filter_by=RankFilter(rideable_type='electric_bike'))
    assert ids(bikes) == ['A', 'F']  # B has 60 e-bike starts, below the 100-start minimum
    assert bikes.rows[0].metric_value == 0.0


@pytest.mark.parametrize('metric, filter_by', [
    ('ebike_share_pct', {'rideable_type': 'electric_bike'}),
    ('casual_share_pct', {'member_casual': 'member'}),
])
def test_conflicting_filters_are_rejected(metric, filter_by):
    with pytest.raises(ValidationError):
        RankStationsArgs(period='2026-02', metric=metric, filter_by=RankFilter(**filter_by))


def test_arguments_are_bounded_and_pinned(ranked):
    service, ref, _ = ranked
    for bad in ({'limit': 11}, {'limit': 0}, {'period': '2026-13'}, {'order': 'middle'}):
        with pytest.raises(ValidationError):
            RankStationsArgs(**({'period': '2026-02', 'metric': 'total_starts'} | bad))
    with pytest.raises(ValidationError):
        RankFilter.model_validate({'station': 'A'})
    with pytest.raises(ValueError, match='pinned dataset'):
        service.rank_stations(ref, RankStationsArgs(period='2026-01', metric='total_starts'))


def test_agent_tool_emits_ranked_evidence_with_context(ranked):
    _, ref, store = ranked
    tools = AgentTools(store, (ref,), 'run-1')
    result, payload = tools.execute('rank_stations', ToolArguments(
        current_period=FEB, metric='ebike_share_pct', order='top', top_n=2), 'call-1')
    assert result.status == 'success' and payload['leader_station_id'] == 'A'
    ranked_values = [value for value in result.values if value.metric_type == 'share']
    assert [(v.entity_id, v.ranking.rank, v.exact_tool_value, v.category) for v in ranked_values] == [
        ('A', 1, 80.0, 'E-bike'), ('F', 2, 50.0, 'E-bike')]
    starts = [value for value in result.values if value.metric_type == 'current_volume']
    assert [(v.entity_id, v.exact_tool_value, v.ranking.ranked_by) for v in starts] == [
        ('A', 150, 'ebike_share_pct'), ('F', 200, 'ebike_share_pct')]
    only_starts, _ = tools.execute('rank_stations', ToolArguments(
        current_period=FEB, metric='total_starts', order='bottom'), 'call-2')
    assert all(value.metric_type == 'current_volume' and value.ranking for value in only_starts.values)
    assert len(only_starts.values) == 5


def test_grounding_renders_filtered_ranking_and_rejects_changed_filter(ranked):
    from mobility.contracts import Claim
    from mobility.grounding import GroundingError, ReportDraft, render_verified_claims, validate_draft

    _, ref, store = ranked
    result, _ = AgentTools(store, (ref,), 'run-1').execute('rank_stations', ToolArguments(
        current_period=FEB, metric='avg_duration_min', order='top', top_n=1,
        filter_by=RankFilter(member_casual='member')), 'call-1')
    claims = tuple(Claim.model_validate(value.model_dump() | {
        'claim_id': f'c{index}', 'tool_call_id': 'call-1', 'run_id': 'run-1', 'datasets': result.datasets,
        'transition': 'standalone'}) for index, value in enumerate(result.values))
    html = render_verified_claims(validate_draft(ReportDraft(claims=claims), (result,), 'run-1'))
    assert 'B Plaza (B) ranked #1 (highest) by average trip duration among members for 2026-02: 20 minutes.' in html
    assert 'B Plaza (B), ranked #1 (highest) by average trip duration among members, had current volume for 2026-02: 120 trips.' in html
    other = claims[0].ranking.model_copy(update={'filter_by': RankFilter(member_casual='casual')})
    with pytest.raises(GroundingError):
        validate_draft(ReportDraft(claims=(claims[0].model_copy(update={'ranking': other}),)), (result,), 'run-1')


@pytest.mark.parametrize('args', [
    ToolArguments(current_period=FEB, metric='total_starts', order='top', top_n=11),
    ToolArguments(current_period=FEB, order='top'),
    ToolArguments(current_period=FEB, metric='total_starts', order='top', station_id='A'),
    ToolArguments(current_period=Period(year=2026, month=1), metric='total_starts', order='top'),
])
def test_agent_tool_rejects_invalid_rank_arguments(ranked, args):
    _, ref, store = ranked
    result, payload = AgentTools(store, (ref,), 'run-1').execute('rank_stations', args, 'call-1')
    assert result.status == 'failed' and payload == {} and result.values == ()
