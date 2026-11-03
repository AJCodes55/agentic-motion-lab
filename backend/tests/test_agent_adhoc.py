"""Typed, bounded and stateless natural-language ad-hoc routing."""
import pytest

from mobility.agent import AgentService
from mobility.contracts import Period
from mobility.storage import DatasetStore
from test_agent import FakeModel, version


@pytest.mark.parametrize('wording', ['ride share for station', 'trip counts at', 'trip count at', 'trip starts at'])
def test_explicit_station_count_comparison_does_not_depend_on_model(tmp_path, wording):
    store = DatasetStore(tmp_path)
    version(store, 6, {'HB107': 20})
    version(store, 7, {'HB107': 8})
    model = FakeModel([])
    result = AgentService(store, model).run(Period(year=2026, month=7),
        f'Compare the {wording} HB107 for the month june and july')
    assert result.status == 'complete', result.warning
    assert result.counters.llm_calls == 0
    assert all(stage.status == 'complete' for stage in result.stages)
    comparison = next(item for item in result.trace if item.tool_name == 'analyze_station_variance')
    counts = {value.period.month: value.exact_tool_value for value in comparison.values
              if value.metric_type == 'current_volume' and value.category is None}
    assert counts == {6: 20, 7: 8}
    if wording.startswith('ride'):
        assert 'trip starts' in result.warning


def test_catalog_station_comparison_runs_without_model_classification(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 6, {'HB107': 20})
    version(store, 7, {'HB107': 8})
    result = AgentService(store, FakeModel([])).run(Period(year=2026, month=7),
        'Compare trip starts at HB107 in July 2026 with June 2026.')
    assert result.status == 'complete', result.warning
    assert result.counters.llm_calls == 0
    assert result.warning is None


@pytest.mark.parametrize('months', ['May and July', 'June 2025 and July 2026', 'June and August'])
def test_explicit_station_count_comparison_keeps_period_bounds(tmp_path, months):
    store = DatasetStore(tmp_path)
    version(store, 6, {'HB107': 20})
    version(store, 7, {'HB107': 8})
    result = AgentService(store, FakeModel([])).run(Period(year=2026, month=7),
        f'Compare trip counts at HB107 for {months}')
    assert result.status == 'refused'
    assert result.counters.llm_calls == 0
    assert not result.trace


def test_explicit_station_count_comparison_still_requires_prior_data(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 7, {'HB107': 8})
    result = AgentService(store, FakeModel([])).run(Period(year=2026, month=7),
        'Compare trip counts at HB107 in June and July')
    assert result.status == 'refused'
    assert 'preceding month' in result.warning


@pytest.mark.parametrize('command', [
    'Compare trip counts at Central Park in June and July',
    'Compare the ride share for station HB107 as a percentage in June and July',
    'Compare the member ride share for station HB107 in June and July',
    'Generate a report and compare trip counts at HB107 in June and July',
    'Compare trip counts at HB107 with HB108 in June and July',
    'Compare ride share for station HB107 in June and July as a fraction of all trips',
    'Compare ride share for station HB107 in June and July as share of all trips',
    'Compare trip counts at May in June and July',
    'Compare trip counts at HB107 for June and July in 2025',
])
def test_count_shortcut_does_not_guess_a_name_or_share_metric(command):
    from mobility.request_scope import _station_count_comparison

    assert _station_count_comparison(command, 2026, 7) is None


def test_explicit_station_count_comparison_handles_year_boundary(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 1, {'HB107': 8})
    result = AgentService(store, FakeModel([])).run(Period(year=2026, month=1),
        'Compare trip counts at HB107 in December 2025 and January 2026')
    assert result.status == 'refused'
    assert 'preceding month' in result.warning


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


def test_metric_phrase_uses_short_table_when_model_says_standard_report(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    result = AgentService(store, FakeModel([{'kind': 'standard_report'}])).run(
        Period(year=2026, month=2), 'Member share for February 2026')
    assert result.status == 'complete'
    assert result.counters.llm_calls == 1
    assert 'Member share' in result.report_html
    assert 'KPI Scorecard' not in result.report_html


def test_report_sentence_stays_on_the_monthly_plan(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    model = FakeModel([{'kind': 'standard_report'}, {'tools': ['station_analysis']}])
    AgentService(store, model).run(Period(year=2026, month=2), 'Generate the February 2026 report with member share')
    assert any(name == 'AnalysisPlan' for name, _payload in model.payloads)
