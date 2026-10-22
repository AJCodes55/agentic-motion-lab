"""Typed, bounded and stateless natural-language ad-hoc routing."""
from mobility.agent import AgentService
from mobility.contracts import Period
from mobility.storage import DatasetStore
from test_agent import FakeModel, version


def test_adhoc_routes_without_report_planning(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    result = AgentService(store, FakeModel([{'kind': 'supported_ad_hoc', 'metric': 'total_trips'}])).run(
        Period(year=2026, month=2), 'How many trips?')
    assert result.status == 'complete'
    assert result.counters.llm_calls == 1
    assert result.report_html
    assert (tmp_path / 'reports' / result.run_id / 'agent' / 'agent-run.json').exists()


def test_adhoc_missing_metric_refuses_without_default(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    result = AgentService(store, FakeModel([{'kind': 'supported_ad_hoc'}])).run(
        Period(year=2026, month=2), 'show it')
    assert result.status == 'refused'
    assert not result.report_html


def test_adhoc_missing_comparison_data_refuses(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    result = AgentService(store, FakeModel([{'kind': 'supported_ad_hoc', 'metric': 'total_trips', 'comparison': True}])).run(
        Period(year=2026, month=2), 'compare trips to previous month')
    assert result.status == 'refused'
    assert not result.report_html


def test_misclassified_forecast_cannot_execute(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    result = AgentService(store, FakeModel([{'kind': 'supported_ad_hoc', 'metric': 'total_trips'}])).run(
        Period(year=2026, month=2), 'forecast trips next month')
    assert result.status == 'refused'
    assert result.counters.tool_calls == 0


def test_adhoc_ambiguous_station_returns_explicit_choices(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'Station A': 2, 'Station B': 3})
    result = AgentService(store, FakeModel([{
        'kind': 'supported_ad_hoc', 'metric': 'station_starts', 'station_query': 'Station',
    }])).run(Period(year=2026, month=2), 'starts at Station')
    assert result.status == 'refused'
    assert result.error_code == 'ERR_STATION_SELECTION'
    assert {choice['station_id'] for choice in result.station_choices} == {'Station A', 'Station B'}


def test_adhoc_route_uses_snapshot_pinned_before_model_call(tmp_path):
    store = DatasetStore(tmp_path)
    original = version(store, 2, {'S': 2})

    def replace_during_routing(payload):
        version(store, 2, {'S': 9})
        return {'kind': 'supported_ad_hoc', 'metric': 'total_trips'}

    result = AgentService(store, FakeModel([replace_during_routing])).run(
        Period(year=2026, month=2), 'How many trips?')
    assert result.status == 'complete'
    assert result.datasets[0] == original
    assert any(value.exact_tool_value == 2 for record in result.trace for value in record.values)


def test_invalid_extracted_arguments_refuse_instead_of_baseline(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    result = AgentService(store, FakeModel([{
        'kind': 'supported_ad_hoc', 'metric': 'total_trips', 'station_id': 'S',
    }])).run(Period(year=2026, month=2), 'trips for S')
    assert result.status == 'refused'
    assert not result.report_html


def test_standard_report_conflicting_command_month_refuses(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    result = AgentService(store, FakeModel([{
        'kind': 'standard_report', 'requested_period': {'year': 2026, 'month': 1},
    }])).run(Period(year=2026, month=2), 'monthly report for January')
    assert result.status == 'refused'
    assert not result.report_html
    assert result.counters.tool_calls == 0


def test_refusal_categories_fail_closed_even_when_misclassified(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    cases = [
        ('Why did trips drop?', {'kind': 'supported_ad_hoc', 'metric': 'total_trips'}),
        ('Compare January February March trips', {'kind': 'supported_ad_hoc', 'metric': 'total_trips'}),
        ('Average distance', {'kind': 'supported_ad_hoc', 'metric': 'average_duration'}),
        ('Compare to December', {'kind': 'standard_report', 'comparison': True,
                                 'comparison_period': {'year': 2025, 'month': 12}}),
    ]
    for command, intent in cases:
        result = AgentService(store, FakeModel([intent])).run(Period(year=2026, month=2), command)
        assert result.status == 'refused', command
        assert not result.report_html
        assert result.counters.tool_calls == 0


def test_extracted_long_station_id_preserves_supported_identifier(tmp_path):
    store = DatasetStore(tmp_path)
    station = 'S' * 300
    version(store, 2, {station: 2})
    result = AgentService(store, FakeModel([{
        'kind': 'supported_ad_hoc', 'metric': 'station_starts', 'station_id': station,
    }])).run(Period(year=2026, month=2), f'starts for {station}')
    assert result.status == 'complete'
