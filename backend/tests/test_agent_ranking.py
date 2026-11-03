"""Station ranking questions use a bounded ReAct loop over rank_stations and analyze_station_variance."""
import json

import pytest

from mobility.agent import AgentService, AgentStep, _comparison_requested, _ranking_request, RequestIntent
from mobility.contracts import Period
from mobility.llm import _strict_schema
from mobility.storage import DatasetStore
from test_agent import FakeModel, version

FEB = Period(year=2026, month=2)
COMPOUND = 'What is the least-used station in February 2026, and how does its trip count compare to January 2026?'


def rank_step(metric='total_starts', order='bottom', limit=1, period='2026-02', filter_by=None):
    return {'action': 'rank_stations', 'station_id': None, 'current_period': None, 'prior_period': None,
            'rank_stations': {'period': period, 'metric': metric, 'order': order, 'limit': limit,
                              'filter_by': filter_by}}


def variance_step(station_id, current='2026-02', prior='2026-01'):
    return {'action': 'analyze_station_variance', 'rank_stations': None, 'station_id': station_id,
            'current_period': current, 'prior_period': prior}


def leader_variance(payload):
    observation = payload['observations'][-1]
    assert observation['tool_name'] == 'rank_stations'
    return variance_step(observation['result']['leader_station_id'])


def two_months(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 1, {'LOW': 300, 'HIGH': 400})
    version(store, 2, {'LOW': 150, 'HIGH': 500})
    return store


@pytest.mark.parametrize('command, expected', [
    ('What is the least-used station in February 2026?', True),
    ('Top 5 stations by e-bike share in February 2026', True),
    ('Which station was busiest?', True),
    ('Rank the stations by casual share', True),
    ('Generate the February report with top stations', False),
    ('Station starts at HB106 for February 2026', False),
    ('Member share for February 2026', False),
])
def test_ranking_phrases_are_detected(command, expected):
    assert _ranking_request(command) is expected


def test_comparison_detection():
    plain = RequestIntent(kind='station_ranking')
    assert _comparison_requested(COMPOUND, plain)
    assert _comparison_requested('Least-used station compared with the previous month', plain)
    assert not _comparison_requested('What is the least-used station in February 2026?', plain)
    assert _comparison_requested('busiest station', plain.model_copy(update={'comparison': True}))


def test_agent_step_schema_is_strict_and_arguments_match_action():
    schema = _strict_schema(AgentStep.model_json_schema())
    assert schema['additionalProperties'] is False
    assert set(schema['required']) == {'action', 'rank_stations', 'station_id', 'current_period', 'prior_period'}
    args = schema['$defs']['RankStationsArgs']
    assert set(args['required']) == {'period', 'metric', 'order', 'limit', 'filter_by'}
    assert schema['$defs']['RankFilter']['additionalProperties'] is False
    with pytest.raises(ValueError):
        AgentStep.model_validate(rank_step() | {'station_id': 'LOW'})
    with pytest.raises(ValueError):
        AgentStep.model_validate(variance_step('LOW') | {'action': 'rank_stations'})


def test_single_step_leaderboard_is_no_longer_refused(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'A': 150, 'B': 120, 'C': 1})
    model = FakeModel([{'kind': 'refusal', 'reason': 'Highest-station questions are unsupported.'},
                       rank_step('ebike_share_pct', 'top', 5)])
    result = AgentService(store, model).run(FEB, 'Top 5 stations by e-bike share in February 2026')
    assert result.status == 'complete', (result.warning, result.validation_reason)
    assert [name for name, _ in model.payloads] == ['RequestIntent', 'AgentStep']
    assert (result.counters.llm_calls, result.counters.tool_calls) == (2, 2)
    assert [item.tool_name for item in result.trace] == ['get_available_periods', 'rank_stations']
    rank = result.trace[1]
    assert (rank.arguments.metric, rank.arguments.order, rank.arguments.top_n) == ('ebike_share_pct', 'top', 5)
    assert [value.entity_id for value in rank.values if value.metric_type == 'share'] == ['A', 'B']
    assert 'Station leaderboard' in result.report_html
    assert '1 stations with fewer than 100 starts were excluded' in result.report_html
    assert 'A (A) ranked #1 (highest, tied) by e-bike share for 2026-02: 0 %.' in result.report_html
    assert 'Station comparison' not in result.report_html
    assert all(stage.status == 'complete' for stage in result.stages)
    assert (tmp_path / 'reports' / result.run_id / 'agent' / 'index.html').read_text() == result.report_html


def test_least_used_station_with_chart(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'A': 150, 'B': 2})
    model = FakeModel([{'kind': 'station_ranking', 'chart': True}, rank_step(limit=2)])
    result = AgentService(store, model).run(FEB, 'Chart the least-used stations in February 2026')
    assert result.status == 'complete'
    assert [item.tool_name for item in result.trace] == ['get_available_periods', 'rank_stations', 'make_chart']
    assert result.counters.tool_calls == 3
    assert '<svg' in result.report_html and '#1 B' in result.report_html
    assert 'B (B) ranked #1 (lowest) by total starts for 2026-02: 2 trips.' in result.report_html


def test_two_step_chaining_investigates_the_discovered_station(tmp_path):
    store = two_months(tmp_path)
    events = []
    model = FakeModel([{'kind': 'station_ranking'}, rank_step()])
    result = AgentService(store, model).run(FEB, COMPOUND, progress=events.append)
    assert result.status == 'complete', (result.warning, result.validation_reason)
    assert [name for name, _ in model.payloads] == ['RequestIntent', 'AgentStep']
    assert (result.counters.llm_calls, result.counters.tool_calls) == (2, 3)
    assert [item.tool_name for item in result.trace] == [
        'get_available_periods', 'rank_stations', 'analyze_station_variance']
    variance = result.trace[2]
    assert variance.arguments.station_id == 'LOW'
    assert (variance.arguments.current_period, variance.arguments.comparison_period) == (
        FEB, Period(year=2026, month=1))
    assert all('ride_id' not in str(payload) for _, payload in model.payloads)
    html = result.report_html
    assert html.index('Station leaderboard') < html.index('Station comparison') < html.index('Verified findings')
    assert 'LOW (LOW) ranked #1 (lowest) by total starts for 2026-02: 150 trips.' in html
    assert 'LOW current volume for 2026-01: 300 trips.' in html
    assert 'LOW absolute change decreased by 150 trips for 2026-02.' in html
    assert 'LOW member casual in 2026-02: Driven entirely by Member.' in html
    assert [event['data']['tool_name'] for event in events if event['type'] == 'tool'] == [
        'get_available_periods', 'rank_stations', 'analyze_station_variance']


def test_unsurfaced_station_in_turn_two_is_rejected(tmp_path):
    store = two_months(tmp_path)
    model = FakeModel([{'kind': 'station_ranking'}, rank_step(limit=2), variance_step('UNKNOWN'), variance_step('UNKNOWN')])
    result = AgentService(store, model).run(FEB, COMPOUND)
    assert result.status == 'partial'
    assert result.validation_reason == 'invalid_follow_up'
    assert result.counters.llm_calls == 4
    assert all(item.tool_name != 'analyze_station_variance' for item in result.trace)
    assert all(name != 'ReportDraft' for name, _ in model.payloads)
    assert model.payloads[3][1]['retry_reason'] == 'station_not_surfaced'
    assert next(stage.status for stage in result.stages if stage.name == 'Tool Execution') == 'failed'
    assert 'Station leaderboard' in result.report_html
    assert 'Monthly mobility baseline' not in result.report_html
    assert result.warning == 'The model did not investigate the ranked station, so the comparison was not added.'


def test_turn_two_retry_recovers_once(tmp_path):
    store = two_months(tmp_path)
    model = FakeModel([{'kind': 'station_ranking'}, rank_step(limit=2), variance_step('LOW', prior='2025-12'),
                       leader_variance])
    result = AgentService(store, model).run(FEB, COMPOUND)
    assert result.status == 'complete'
    assert model.payloads[3][1]['retry_reason'] == 'wrong_period'
    assert result.counters.llm_calls == 4


def test_wrong_first_tool_or_month_rejects_the_plan(tmp_path):
    store = two_months(tmp_path)
    model = FakeModel([{'kind': 'station_ranking'}, variance_step('LOW'), rank_step(period='2026-01')])
    result = AgentService(store, model).run(FEB, COMPOUND)
    assert result.status == 'partial'
    assert result.validation_reason == 'invalid_plan'
    assert result.warning == 'No report was added.' and not result.report_html
    assert [model.payloads[i][1]['retry_reason'] for i in (1, 2)] == [None, 'wrong_tool']
    assert result.counters.tool_calls == 1


def test_malformed_step_uses_the_gate_retry(tmp_path):
    from mobility.llm import ProviderSchemaError
    store = two_months(tmp_path)
    model = FakeModel([{'kind': 'station_ranking'}, ProviderSchemaError(), rank_step(limit=2)])
    result = AgentService(store, model).run(FEB, 'What are the 2 least-used stations in February 2026?')
    assert result.status == 'complete'
    assert model.payloads[2][1]['retry_reason'] == 'invalid_arguments'
    diagnostics = json.loads((tmp_path / 'reports' / result.run_id / 'agent' / 'rejected-steps.json').read_text())
    assert diagnostics == [{'expected_action': 'rank_stations', 'attempt': 1,
                            'reason': 'invalid_arguments', 'arguments': None}]


def test_missing_prior_month_refuses_before_any_tool(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'LOW': 150})
    result = AgentService(store, FakeModel([{'kind': 'station_ranking'}])).run(FEB, COMPOUND)
    assert result.status == 'refused'
    assert 'preceding month is unavailable' in result.warning
    assert (result.counters.llm_calls, result.counters.tool_calls) == (1, 0)


def test_no_eligible_station_refuses_cleanly(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'A': 5})
    model = FakeModel([{'kind': 'station_ranking'}, rank_step('casual_share_pct', 'top', 3)])
    result = AgentService(store, model).run(FEB, 'Top 3 stations by casual share')
    assert result.status == 'refused'
    assert 'No station met the ranking rules' in result.warning
    assert result.counters.tool_calls == 2


@pytest.mark.parametrize('field', ['rank', 'station', 'value'])
def test_generated_rank_claims_still_require_grounding(tmp_path, monkeypatch, field):
    import mobility.agent as agent

    original = agent._ranking_claims

    def forged(selected):
        claims = original(selected)
        claim = dict(claims[0])
        if field == 'rank':
            claim['ranking'] = claim['ranking'] | {'rank': 2}
        elif field == 'station':
            claim['entity_id'] = 'HIGH'
        else:
            claim['exact_tool_value'] = 999
        return [claim, *claims[1:]]

    monkeypatch.setattr(agent, '_ranking_claims', forged)
    model = FakeModel([{'kind': 'station_ranking'}, rank_step()])
    result = AgentService(two_months(tmp_path), model).run(FEB, 'What is the least-used station?')
    assert result.status == 'partial'
    assert result.error_code == 'ERR_UNGROUNDED_CLAIM'
    assert 'Verified findings' not in result.report_html
    assert 'ranked #' not in result.report_html


def test_retries_finish_inside_the_six_call_budget(tmp_path):
    model = FakeModel([{'kind': 'station_ranking'}, rank_step(period='2026-01'), rank_step(limit=2),
                       variance_step('UNKNOWN'), leader_variance])
    result = AgentService(two_months(tmp_path), model).run(FEB, COMPOUND)
    assert result.status == 'complete', result.warning
    assert result.counters.llm_calls == 5
    assert all(stage.status == 'complete' for stage in result.stages)


def test_hard_refusals_still_win_over_ranking(tmp_path):
    store = two_months(tmp_path)
    for command in ('Forecast the busiest station next month', 'Which station has the highest average speed?',
                    'Top stations in December, January and February'):
        result = AgentService(store, FakeModel([{'kind': 'station_ranking'}])).run(FEB, command)
        assert result.status == 'refused', command
        assert result.counters.tool_calls == 0


def test_model_classified_ranking_without_keywords_routes_to_tools(tmp_path):
    store = two_months(tmp_path)
    model = FakeModel([{'kind': 'station_ranking'}, rank_step(order='top')])
    result = AgentService(store, model).run(FEB, 'Where did riders start most often?')
    assert result.status == 'complete'
    assert result.trace[1].values[0].entity_id == 'HIGH'


def test_comparison_demo_still_refuses_ranking(tmp_path):
    from mobility.baseline import generate_standard_dashboard
    store = two_months(tmp_path)
    snapshot = generate_standard_dashboard(store, FEB)
    result = AgentService(store, FakeModel([{'kind': 'station_ranking'}])).run(
        FEB, 'least-used station', snapshot=snapshot, comparison_mode=True)
    assert result.status == 'refused'


@pytest.mark.parametrize('june_count', [0, 20])
def test_exact_july_question_completes_without_model_drafting(tmp_path, june_count):
    store = DatasetStore(tmp_path)
    version(store, 6, {'HB107': june_count, 'HIGH': 50})
    version(store, 7, {'HB107': 8, 'HIGH': 40})
    model = FakeModel([{'kind': 'station_ranking'}, rank_step(period='2026-07')])
    result = AgentService(store, model).run(Period(year=2026, month=7),
        'What is the least-used station in July 2026, and how does its trip count compare to June?')
    assert result.status == 'complete', result.warning
    assert result.counters.llm_calls == 2
    comparison = result.trace[-1]
    assert comparison.tool_name == 'analyze_station_variance'
    assert comparison.arguments.station_id == 'HB107'
    assert comparison.arguments.comparison_period == Period(year=2026, month=6)
    assert 'Station comparison' in result.report_html
    assert f'HB107 current volume for 2026-06: {june_count} trips.' in result.report_html
    change = 'increased by 8' if june_count == 0 else 'decreased by 12'
    assert f'HB107 absolute change {change} trips for 2026-07.' in result.report_html
    assert 'Verified findings' in result.report_html
    assert all(stage.status == 'complete' for stage in result.stages)
    assert result.warning is None


def test_rejected_ranking_steps_are_archived_with_arguments_and_reasons(tmp_path):
    store = two_months(tmp_path)
    model = FakeModel([{'kind': 'station_ranking'}, rank_step(limit=2),
                       variance_step('UNKNOWN'), variance_step('LOW', prior='2025-12')])
    result = AgentService(store, model).run(FEB, COMPOUND)
    assert result.status == 'partial'
    path = tmp_path / 'reports' / result.run_id / 'agent' / 'rejected-steps.json'
    diagnostics = json.loads(path.read_text())
    assert [item['reason'] for item in diagnostics] == ['station_not_surfaced', 'wrong_period']
    assert [item['attempt'] for item in diagnostics] == [1, 2]
    assert diagnostics[0]['arguments']['station_id'] == 'UNKNOWN'
    assert diagnostics[1]['arguments']['prior_period'] == '2025-12'
    assert all(item['expected_action'] == 'analyze_station_variance' for item in diagnostics)
    assert all(set(item) == {'expected_action', 'attempt', 'reason', 'arguments'} for item in diagnostics)
    assert 'rejected_steps' not in result.model_dump()


def test_automatic_comparison_tool_failure_stays_partial(tmp_path, monkeypatch):
    from mobility.agent_tools import AgentTools

    original = AgentTools.execute

    def fail_comparison(self, name, args, call_id):
        result, payload = original(self, name, args, call_id)
        if name == 'analyze_station_variance':
            return result.model_copy(update={'status': 'failed', 'values': ()}), {}
        return result, payload

    monkeypatch.setattr(AgentTools, 'execute', fail_comparison)
    model = FakeModel([{'kind': 'station_ranking'}, rank_step()])
    result = AgentService(two_months(tmp_path), model).run(FEB, COMPOUND)
    assert result.status == 'partial'
    assert result.error_code == 'ERR_TOOL_EXECUTION'
    assert result.validation_reason == 'tool_failed'
    assert result.counters.llm_calls == 2
    assert result.counters.tool_calls == 4
    assert 'comparison tool failed' in result.warning
    assert 'Station comparison' not in result.report_html
    assert 'Station leaderboard' in result.report_html
