"""Agent run must stay on pinned evidence and fail closed on invalid model choices."""
from types import SimpleNamespace
import json

import pandas as pd
import pytest

from mobility.agent import AgentService
from mobility.contracts import Period, QualitySummary
from mobility.storage import DatasetStore


class FakeModel:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.payloads = []

    def request(self, schema, system, payload):
        self.payloads.append((schema.__name__, payload))
        answer = next(self.answers)
        if callable(answer):
            answer = answer(payload)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(value=schema.model_validate_json(json.dumps(answer)), usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2))


def version(store, month, counts):
    rows = [dict(ride_id=f'{month}-{station}-{i}', started_at=f'2026-{month:02d}-01 10:00:00',
                 start_station_id=station, start_station_name=station, member_casual='Member',
                 rideable_type='Classic', duration_seconds=120.0)
            for station, count in counts.items() for i in range(count)]
    frame = pd.DataFrame(rows)
    return store.persist_and_activate(SimpleNamespace(period=Period(year=2026, month=month), frame=frame,
        quality=QualitySummary(source_rows=len(rows), valid_rows=len(rows), excluded_rows=0), sources=()))


def test_missing_model_yields_baseline_only_and_persists_status(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    model = FakeModel([RuntimeError('private provider detail')])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'standard report')
    assert result.status == 'partial'
    assert result.counters.llm_calls == 1
    assert 'private provider detail' not in result.model_dump_json()
    assert 'KPI Scorecard' in result.report_html
    assert result.warning and 'baseline metrics only' in result.warning
    assert (tmp_path / 'reports' / result.run_id / 'agent' / 'agent-run.json').exists()


def test_unsupported_intent_refuses_without_selected_narrative(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    model = FakeModel([{'kind': 'refusal', 'reason': 'Forecasts are unsupported.'}])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'forecast next month')
    assert result.status == 'refused'
    assert result.error_code == 'ERR_UNSUPPORTED_INTENT'
    assert result.counters.llm_calls == 0
    assert not result.report_html


def test_bad_plan_retries_once_then_baseline_only(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    model = FakeModel([
        {'kind': 'standard_report'},
        {'tools': ['make_chart']},
        {'tools': ['make_chart']},
    ])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'standard report')
    assert result.status == 'partial'
    assert result.counters.llm_calls == 3
    assert result.counters.tool_calls == 1  # available-period lookup before planning
    assert result.validation_reason == 'invalid_plan'
    assert not result.report_html
    assert result.warning == 'No report was added.'
    assert 'Narrative validation failed' not in (result.warning or '')


def test_comparative_follow_up_and_no_raw_rows_in_prompts(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    version(store, 2, {'S': 150})
    model = FakeModel([
        {'kind': 'standard_report'}, {'tools': ['station_movers']},
        {'name': 'analyze_station_variance', 'station_id': 'S'},
    ])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'standard report')
    assert result.status == 'complete', result.warning
    assert result.counters.llm_calls == 3
    assert result.counters.tool_calls == 3
    assert any(t.tool_name == 'analyze_station_variance' and t.status == 'success' for t in result.trace)
    assert all('ride_id' not in str(payload) and 'started_at' not in str(payload) for _, payload in model.payloads)
    assert [name for name, _ in model.payloads] == ['RequestIntent', 'AnalysisPlan', 'FollowUp']
    assert 'S member casual in 2026-02: Driven entirely by Member.' in result.report_html
    assert '<div class="report-panel"><h2>Verified findings</h2>' in result.report_html
    assert result.report_html.index('Verified findings') < result.report_html.index('</main>')


def test_malformed_route_retries_once_then_schema_fallback(tmp_path):
    from mobility.llm import ProviderSchemaError
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    result = AgentService(store, FakeModel([ProviderSchemaError(), ProviderSchemaError()])).run(
        Period(year=2026, month=2), 'report')
    assert result.status == 'partial'
    assert result.error_code == 'ERR_SCHEMA_MISMATCH'
    assert result.validation_reason == 'route_schema_mismatch'
    assert result.counters.llm_calls == 2
    assert 'KPI Scorecard' in result.report_html


def test_wrong_follow_up_retries_and_marks_execution_failed(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    version(store, 2, {'S': 150})
    wrong = {'name': 'analyze_station_variance', 'station_id': 'OTHER'}
    result = AgentService(store, FakeModel([
        {'kind': 'standard_report'},
        {'tools': ['station_movers']},
        wrong, wrong,
    ])).run(Period(year=2026, month=2), 'report')
    assert result.status == 'partial'
    assert result.validation_reason == 'invalid_follow_up'
    assert result.counters.llm_calls == 4
    assert result.counters.tool_calls == 2
    assert next(stage.status for stage in result.stages if stage.name == 'Tool Execution') == 'failed'
    assert all(item.tool_name != 'analyze_station_variance' for item in result.trace)


def test_standard_report_can_finish_at_the_six_call_budget(tmp_path):
    from mobility.llm import ProviderSchemaError
    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    version(store, 2, {'S': 150})
    model = FakeModel([
        ProviderSchemaError(), {'kind': 'standard_report'},
        {'tools': ['make_chart']},
        {'tools': ['station_movers']},
        {'name': 'analyze_station_variance', 'station_id': 'OTHER'},
        {'name': 'analyze_station_variance', 'station_id': 'S'},
    ])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'report')
    assert result.status == 'complete'
    assert result.error_code is None
    assert result.warning is None
    assert result.counters.llm_calls == 6
    assert result.counters.tool_calls <= 10
    assert 'KPI Scorecard' in result.report_html


def test_replacement_after_baseline_keeps_original_snapshot(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    original = version(store, 2, {'S': 150})

    def replace(_payload):
        version(store, 2, {'S': 2})
        return {'kind': 'standard_report'}

    model = FakeModel([
        replace,
        {'tools': ['station_movers']},
        RuntimeError('stop after evidence'),
    ])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'report')
    assert result.status == 'partial'
    assert result.datasets[0] == original
    assert store.pin_periods((Period(year=2026, month=2),))[0] != original
    movers = next(item for item in result.trace if item.tool_name == 'station_movers')
    assert movers.datasets[0] == original
    assert any(value.entity_id == 'S' and value.exact_tool_value == -150 for value in movers.values)


@pytest.mark.parametrize('defect', ['value', 'station', 'period'])
def test_generated_standard_claim_is_grounded_before_rendering(tmp_path, monkeypatch, defect):
    import mobility.agent as agent

    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    original = agent._allowed_claims

    def forged(trace, candidate_id):
        claims = original(trace, candidate_id)
        field, value = ({'value': ('exact_tool_value', 999_999),
                         'station': ('entity_id', 'OTHER'),
                         'period': ('period', {'year': 2026, 'month': 1})})[defect]
        return [claims[0] | {field: value}, *claims[1:]]

    monkeypatch.setattr(agent, '_allowed_claims', forged)
    model = FakeModel([{'kind': 'standard_report'}, {'tools': ['station_analysis']}])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'report')
    assert result.status == 'partial'
    assert result.error_code == 'ERR_UNGROUNDED_CLAIM'
    assert result.validation_reason == 'ungrounded_claim'
    assert result.counters.llm_calls == 2
    assert '999,999' not in result.report_html
    assert result.report_html == (tmp_path / 'reports' / result.run_id / 'index.html').read_text()


def test_malformed_follow_up_uses_retry_then_validates(tmp_path):
    from mobility.llm import ProviderSchemaError
    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    version(store, 2, {'S': 150})

    result = AgentService(store, FakeModel([
        {'kind': 'standard_report'},
        {'tools': ['station_movers']},
        ProviderSchemaError(),
        {'name': 'analyze_station_variance', 'station_id': 'S'},
    ])).run(Period(year=2026, month=2), 'report')
    assert result.status == 'complete'
    assert result.counters.llm_calls == 4
    assert 'Driven entirely by Member' in result.report_html


def test_failed_initial_tool_gets_one_replan_and_counts_failure(tmp_path, monkeypatch):
    from mobility.agent_tools import AgentTools
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    original = AgentTools.execute
    attempts = 0

    def fail_first(self, name, args, call_id):
        nonlocal attempts
        if name == 'station_analysis' and attempts == 0:
            attempts += 1
            result, _ = original(self, name, args, call_id)
            return result.model_copy(update={'status': 'failed', 'values': (),
                                             'validation_reason': 'Tool execution failed.'}), {}
        return original(self, name, args, call_id)

    monkeypatch.setattr(AgentTools, 'execute', fail_first)

    plan = {'tools': ['station_analysis']}
    result = AgentService(store, FakeModel([
        {'kind': 'standard_report'}, plan, plan,
    ])).run(Period(year=2026, month=2), 'report')
    assert result.status == 'complete'
    assert result.counters.llm_calls == 3
    assert result.counters.tool_calls == 3
    assert [item.status for item in result.trace if item.tool_name == 'station_analysis'] == ['failed', 'success']


def test_incomplete_follow_up_is_failed_evidence_then_retried(tmp_path, monkeypatch):
    from mobility.agent_tools import AgentTools
    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    version(store, 2, {'S': 150})
    original = AgentTools.execute
    attempts = 0

    def incomplete_first(self, name, args, call_id):
        nonlocal attempts
        result, payload = original(self, name, args, call_id)
        if name == 'analyze_station_variance' and attempts == 0:
            attempts += 1
            return result, {'member_casual': payload['member_casual']}
        return result, payload

    monkeypatch.setattr(AgentTools, 'execute', incomplete_first)

    plan = {'tools': ['station_movers']}
    follow = {'name': 'analyze_station_variance', 'station_id': 'S'}
    result = AgentService(store, FakeModel([{'kind': 'standard_report'}, plan, follow, follow])).run(
        Period(year=2026, month=2), 'report')
    assert result.status == 'complete'
    assert result.counters.llm_calls == 4
    assert result.counters.tool_calls == 4
    variances = [item for item in result.trace if item.tool_name == 'analyze_station_variance']
    assert [item.status for item in variances] == ['failed', 'success']
    assert variances[0].values == ()
    assert variances[0].validation_reason == 'incomplete_or_wrong_follow_up'


@pytest.mark.parametrize('defect', ['current_period', 'comparison_period', 'station_id', 'failed'])
def test_wrong_or_failed_variance_evidence_is_rejected(tmp_path, monkeypatch, defect):
    """Synthetic tool corruption must never become draft evidence or narrative."""
    from mobility.agent_tools import AgentTools

    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    version(store, 2, {'S': 150})
    original = AgentTools.execute

    def corrupt_variance(self, name, args, call_id):
        result, payload = original(self, name, args, call_id)
        if name != 'analyze_station_variance':
            return result, payload
        if defect == 'failed':
            return result.model_copy(update={'status': 'failed'}), payload
        replacement = ('OTHER' if defect == 'station_id' else Period(year=2026, month=3))
        return result.model_copy(update={
            'arguments': args.model_copy(update={defect: replacement}),
        }), payload

    monkeypatch.setattr(AgentTools, 'execute', corrupt_variance)
    follow = {'name': 'analyze_station_variance', 'station_id': 'S'}
    model = FakeModel([
        {'kind': 'standard_report'}, {'tools': ['station_movers']}, follow, follow,
    ])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'report')

    assert result.status == 'partial'
    assert result.validation_reason == 'invalid_follow_up'
    assert result.counters.llm_calls == 4
    assert result.counters.tool_calls == 4
    variances = [item for item in result.trace if item.tool_name == 'analyze_station_variance']
    assert len(variances) == 2
    assert all(item.status == 'failed' and item.values == () for item in variances)
    assert all(item.validation_reason == 'incomplete_or_wrong_follow_up' for item in variances)
    assert all(schema != 'ReportDraft' for schema, _ in model.payloads)
    assert 'KPI Scorecard' in result.report_html
    assert result.report_html == (tmp_path / 'reports' / result.run_id / 'index.html').read_text()


def test_initial_failure_consumes_shared_result_retry(tmp_path, monkeypatch):
    """A replan cannot allocate a second retry to invalid follow-up evidence."""
    from mobility.agent_tools import AgentTools

    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    version(store, 2, {'S': 150})
    original = AgentTools.execute
    initial_calls = 0

    def fail_initial_then_follow_up(self, name, args, call_id):
        nonlocal initial_calls
        result, payload = original(self, name, args, call_id)
        if name == 'station_movers':
            initial_calls += 1
            if initial_calls == 1:
                return result.model_copy(update={'status': 'failed', 'values': ()}), {}
        if name == 'analyze_station_variance':
            return result, {'member_casual': payload['member_casual']}
        return result, payload

    monkeypatch.setattr(AgentTools, 'execute', fail_initial_then_follow_up)
    plan = {'tools': ['station_movers']}
    model = FakeModel([
        {'kind': 'standard_report'}, plan, plan,
        {'name': 'analyze_station_variance', 'station_id': 'S'},
    ])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'report')

    assert result.status == 'partial'
    assert result.validation_reason == 'invalid_follow_up'
    assert result.counters.llm_calls == 4
    assert result.counters.tool_calls == 4
    assert [item.status for item in result.trace if item.tool_name == 'station_movers'] == [
        'failed', 'success']
    variances = [item for item in result.trace if item.tool_name == 'analyze_station_variance']
    assert len(variances) == 1
    assert variances[0].status == 'failed' and variances[0].values == ()
    assert all(schema != 'ReportDraft' for schema, _ in model.payloads)
    assert 'KPI Scorecard' in result.report_html
    assert result.report_html == (tmp_path / 'reports' / result.run_id / 'index.html').read_text()


def test_tool_budget_blocks_eleventh_dispatch_before_execution(tmp_path, monkeypatch):
    """Defensive cap: bypass duplicate-plan gate to reach an otherwise unreachable budget."""
    from mobility.agent_tools import AgentTools

    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    original = AgentTools.execute
    dispatched = []
    station_calls = 0

    def fail_eighth_station_call(self, name, args, call_id):
        nonlocal station_calls
        dispatched.append((name, call_id))
        result, payload = original(self, name, args, call_id)
        if name == 'station_analysis':
            station_calls += 1
            if station_calls == 8:
                return result.model_copy(update={'status': 'failed', 'values': ()}), {}
        return result, payload

    monkeypatch.setattr(AgentTools, 'execute', fail_eighth_station_call)
    monkeypatch.setattr(AgentService, '_validate_plan', staticmethod(lambda *_: None))
    plan = {'tools': ['station_analysis'] * 8}
    model = FakeModel([{'kind': 'standard_report'}, plan, plan])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'report')

    assert result.status == 'partial'
    assert result.error_code == 'ERR_BUDGET_EXCEEDED'
    assert result.counters.tool_calls == len(dispatched) == len(result.trace) == 10
    assert station_calls == 9
    assert result.counters.llm_calls == 3
    assert dispatched[-1][1].endswith('_selected_10')
    assert not any(call_id.endswith('_selected_11') for _, call_id in dispatched)
    assert result.warning == (
        'Pass with limitations: Reasoning budget exhausted. Displaying standard baseline metrics only.')
    assert 'KPI Scorecard' in result.report_html
    assert result.report_html == (tmp_path / 'reports' / result.run_id / 'index.html').read_text()


def test_standard_report_completes_without_model_copying_claims(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 6, {'S': 300})
    version(store, 7, {'S': 150})
    model = FakeModel([
        {'kind': 'standard_report'}, {'tools': ['compare_periods', 'station_movers']},
        {'name': 'analyze_station_variance', 'station_id': 'S'},
    ])
    result = AgentService(store, model).run(Period(year=2026, month=7),
        'Generate report for July 2026 and compare it with June 2026')
    assert result.status == 'complete', result.warning
    assert result.warning is None
    assert all(stage.status == 'complete' for stage in result.stages)
    assert [name for name, _ in model.payloads] == ['RequestIntent', 'AnalysisPlan', 'FollowUp']
    assert 'Driven entirely by Member' in result.report_html
    assert (tmp_path / 'reports' / result.run_id / 'agent' / 'index.html').read_text() == result.report_html
