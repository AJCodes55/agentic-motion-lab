"""Agent run must stay on pinned evidence and fail closed on invalid model choices."""
from types import SimpleNamespace
import json

import pandas as pd

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
    assert result.counters.llm_calls == 1
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
    assert result.warning and 'Narrative validation failed' in result.warning


def test_comparative_follow_up_and_no_raw_rows_in_prompts(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    version(store, 2, {'S': 150})
    model = FakeModel([
        {'kind': 'standard_report'},
        {'tools': ['station_movers']},
        {'name': 'analyze_station_variance', 'station_id': 'S'},
        lambda payload: {'claims': [next(value | {'claim_id': 'claim-1', 'tool_call_id': record['tool_call_id'], 'run_id': payload['run_id'], 'datasets': record['datasets'], 'transition': 'decrease'} for record in payload['evidence'] if record['tool_name'] == 'station_movers' for value in record['values'] if value['entity_id'] == 'S' and value['metric_type'] == 'absolute_change')]},
    ])
    result = AgentService(store, model).run(Period(year=2026, month=2), 'standard report')
    assert result.status == 'complete', (result.error_code, result.warning, result.counters, [(t.tool_name,t.status,t.validation_reason) for t in result.trace], [name for name,_ in model.payloads])
    assert result.counters.llm_calls == 4
    assert result.counters.tool_calls == 3
    assert any(t.tool_name == 'analyze_station_variance' and t.status == 'success' for t in result.trace)
    assert all('ride_id' not in str(payload) and 'started_at' not in str(payload) for _, payload in model.payloads)
    draft_payload = model.payloads[-1][1]
    assert 'aggregate_results' not in draft_payload
    assert {record['tool_name'] for record in draft_payload['evidence']} == {
        'station_movers', 'analyze_station_variance'}
    assert all(value['entity_id'] == 'S' for record in draft_payload['evidence']
               for value in record['values'])
    assert draft_payload['allowed_claims']
    assert all(claim['run_id'] == result.run_id and claim['transition'] == 'standalone'
               for claim in draft_payload['allowed_claims'])


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


def test_llm_budget_exhaustion_is_exact_baseline_warning(tmp_path):
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
    assert result.status == 'partial'
    assert result.error_code == 'ERR_BUDGET_EXCEEDED'
    assert result.warning == 'Pass with limitations: Reasoning budget exhausted. Displaying standard baseline metrics only.'
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


def test_forged_claim_retries_once_and_leaks_no_narrative(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})

    def forged(payload):
        record = next(item for item in payload['evidence'] if item['tool_name'] == 'station_analysis')
        value = record['values'][0]
        return {'claims': [value | {'claim_id': 'fake', 'tool_call_id': record['tool_call_id'],
            'run_id': payload['run_id'], 'datasets': record['datasets'],
            'transition': 'standalone', 'exact_tool_value': 999_999}]}

    result = AgentService(store, FakeModel([
        {'kind': 'standard_report'},
        {'tools': ['station_analysis']},
        forged, forged,
    ])).run(Period(year=2026, month=2), 'report')
    assert result.status == 'partial'
    assert result.error_code == 'ERR_UNGROUNDED_CLAIM'
    assert result.validation_reason == 'ungrounded_claim'
    assert result.counters.llm_calls == 4
    assert '999,999' not in result.report_html
    assert 'KPI Scorecard' in result.report_html


def test_malformed_follow_up_uses_retry_then_validates(tmp_path):
    from mobility.llm import ProviderSchemaError
    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 300})
    version(store, 2, {'S': 150})

    def verified(payload):
        record = next(item for item in payload['evidence'] if item['tool_name'] == 'station_movers')
        value = next(item for item in record['values'] if item['entity_id'] == 'S' and item['metric_type'] == 'absolute_change')
        return {'claims': [value | {'claim_id': 'valid', 'tool_call_id': record['tool_call_id'],
            'run_id': payload['run_id'], 'datasets': record['datasets'], 'transition': 'decrease'}]}

    result = AgentService(store, FakeModel([
        {'kind': 'standard_report'},
        {'tools': ['station_movers']},
        ProviderSchemaError(),
        {'name': 'analyze_station_variance', 'station_id': 'S'},
        verified,
    ])).run(Period(year=2026, month=2), 'report')
    assert result.status == 'complete'
    assert result.counters.llm_calls == 5
    assert 'decreased by 150 trips' in result.report_html


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

    def verified(payload):
        record = next(item for item in payload['evidence'] if item['tool_name'] == 'station_analysis' and item['status'] == 'success')
        value = record['values'][0]
        return {'claims': [value | {'claim_id': 'valid', 'tool_call_id': record['tool_call_id'],
            'run_id': payload['run_id'], 'datasets': record['datasets'], 'transition': 'standalone'}]}

    plan = {'tools': ['station_analysis']}
    result = AgentService(store, FakeModel([
        {'kind': 'standard_report'}, plan, plan, verified,
    ])).run(Period(year=2026, month=2), 'report')
    assert result.status == 'complete'
    assert result.counters.llm_calls == 4
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

    def verified(payload):
        record = next(item for item in payload['evidence'] if item['tool_name'] == 'station_movers')
        value = next(item for item in record['values'] if item['metric_type'] == 'absolute_change')
        return {'claims': [value | {'claim_id': 'valid', 'tool_call_id': record['tool_call_id'],
            'run_id': payload['run_id'], 'datasets': record['datasets'], 'transition': 'decrease'}]}

    plan = {'tools': ['station_movers']}
    follow = {'name': 'analyze_station_variance', 'station_id': 'S'}
    result = AgentService(store, FakeModel([{'kind': 'standard_report'}, plan, follow, follow, verified])).run(
        Period(year=2026, month=2), 'report')
    assert result.status == 'complete'
    assert result.counters.llm_calls == 5
    assert result.counters.tool_calls == 4
    variances = [item for item in result.trace if item.tool_name == 'analyze_station_variance']
    assert [item.status for item in variances] == ['failed', 'success']
    assert variances[0].values == ()
    assert variances[0].validation_reason == 'incomplete_or_wrong_follow_up'
