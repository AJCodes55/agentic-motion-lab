"""One immutable comparison, independent Python totals and attributed agent evidence."""
import json

import pytest

from mobility.agent import AgentService
from mobility.baseline import generate_standard_dashboard
from mobility.comparison import ComparisonService, comparison_rows, validate_archive
from mobility.contracts import Period
from mobility.storage import DatasetStore
from test_agent import FakeModel, version

FEB = Period(year=2026, month=2)


def ready(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 1, {'001': 300})
    version(store, 2, {'001': 150})
    return store


def model():
    return FakeModel([{'kind': 'standard_report'},
        {'tools': ['compare_periods', 'station_movers']},
        {'name': 'analyze_station_variance', 'station_id': '001'}])


def test_baseline_streams_before_model_and_shared_snapshot_survives_replacement(tmp_path):
    store = ready(tmp_path)
    events = []
    provider = model()
    def progress(event):
        events.append(event)
        if event['type'] == 'baseline':
            assert not provider.payloads
            version(store, 1, {'replacement': 1})
            version(store, 2, {'replacement': 1})
    result = ComparisonService(store, provider).run(FEB, progress)
    assert result.agent.status == 'complete'
    assert [row.status for row in result.rows] == ['match', 'match']
    assert [row.python_total for row in result.rows] == [300, 150]
    assert events[0]['type'] == 'baseline'
    assert result.agent.datasets == result.datasets
    assert len(list((tmp_path / 'reports').iterdir())) == 1
    assert validate_archive(store, result.report_id) == result


def test_missing_month_prevents_dispatch(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 1})
    provider = model()
    with pytest.raises((KeyError, ValueError)):
        ComparisonService(store, provider).run(FEB)
    assert not provider.payloads


def test_partial_can_have_verified_matches_and_rejected_claim_never_appears(tmp_path, monkeypatch):
    monkeypatch.setattr('mobility.agent._allowed_claims', lambda *_: [])
    store = ready(tmp_path)
    provider = FakeModel([{'kind': 'standard_report'},
        {'tools': ['compare_periods', 'station_movers']},
        {'name': 'analyze_station_variance', 'station_id': '001'}])
    result = ComparisonService(store, provider).run(FEB)
    assert result.agent.status == 'partial'
    assert all(row.status == 'match' for row in result.rows)
    assert result.agent.error_code == 'ERR_UNGROUNDED_CLAIM'


def test_failure_is_unavailable_not_zero(tmp_path):
    result = ComparisonService(ready(tmp_path), FakeModel([RuntimeError('secret')])).run(FEB)
    assert result.agent.status == 'partial'
    assert all(row.agent_total is None and row.difference is None and row.status == 'unavailable' for row in result.rows)
    assert 'secret' not in result.model_dump_json()


@pytest.mark.parametrize('change', ['run_id', 'datasets', 'period', 'arguments', 'failed', 'call_id'])
def test_wrong_attribution_is_unavailable(tmp_path, change):
    store = ready(tmp_path)
    result = ComparisonService(store, model()).run(FEB)
    trace = next(item for item in result.agent.trace if item.tool_name == 'compare_periods')
    updates = {'run_id': 'wrong'} if change == 'run_id' else {'datasets': tuple(reversed(trace.datasets))} if change == 'datasets' else {'status': 'failed'} if change == 'failed' else {'tool_call_id': 'forged'} if change == 'call_id' else {'arguments': trace.arguments.model_copy(update={'comparison_period': FEB})} if change == 'arguments' else {'values': tuple(value.model_copy(update={'period': Period(year=2025, month=1)}) for value in trace.values)}
    agent = result.agent.model_copy(update={'trace': tuple(trace.model_copy(update=updates) if item.tool_name == 'compare_periods' else item for item in result.agent.trace)})
    rows = comparison_rows(result.baseline, agent, result.report_id, result.datasets)
    assert all(row.status == 'unavailable' for row in rows)


def test_mismatch_uses_tool_value_not_comparator(tmp_path):
    result = ComparisonService(ready(tmp_path), model()).run(FEB)
    trace = next(item for item in result.agent.trace if item.tool_name == 'compare_periods')
    trace = trace.model_copy(update={'values': tuple(value.model_copy(update={'exact_tool_value': 99}) if value.entity_id == 'month' and value.metric_type == 'trip_count' else value for value in trace.values)})
    rows = comparison_rows(result.baseline, result.agent.model_copy(update={'trace': tuple(trace if item.tool_name == 'compare_periods' else item for item in result.agent.trace)}), result.report_id, result.datasets)
    assert all(row.status == 'mismatch' and row.agent_total == 99 for row in rows)


def test_comparison_mode_without_snapshot_does_not_pin(tmp_path, monkeypatch):
    monkeypatch.setattr('mobility.agent.generate_standard_dashboard', lambda *_args, **_kwargs: pytest.fail('must not pin'))
    with pytest.raises(ValueError, match='precomputed snapshot'):
        AgentService(DatasetStore(tmp_path), model()).run(FEB, 'report', comparison_mode=True)


def test_snapshot_period_identity_is_validated_without_repinning(tmp_path, monkeypatch):
    store = ready(tmp_path)
    snapshot = generate_standard_dashboard(store, FEB)
    monkeypatch.setattr(store, 'pin_periods', lambda *_: pytest.fail('must not repin'))
    assert AgentService(store, model()).run(FEB, 'standard report', snapshot=snapshot, comparison_mode=True).status == 'complete'
    with pytest.raises(ValueError):
        AgentService(store, model()).run(Period(year=2026, month=1), 'standard report', snapshot=snapshot)


def test_comparison_plan_requires_both_tools_on_retry(tmp_path):
    provider = FakeModel([{'kind': 'standard_report'}, {'tools': ['station_movers']}, {'tools': ['station_movers']}])
    result = ComparisonService(ready(tmp_path), provider).run(FEB)
    assert result.agent.status == 'partial'
    assert result.agent.validation_reason == 'invalid_plan'
    assert result.agent.counters.llm_calls == 3


def test_corrupt_archive_is_rejected(tmp_path):
    store = ready(tmp_path)
    result = ComparisonService(store, model()).run(FEB)
    path = tmp_path / 'reports' / result.report_id / 'comparison.json'
    data = json.loads(path.read_text())
    data['rows'][0]['agent_total'] = 999
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        validate_archive(store, result.report_id)


@pytest.mark.parametrize('change', ['version', 'metric', 'entity', 'unit', 'category', 'duplicate', 'conflict'])
def test_invalid_or_ambiguous_total_evidence_is_unavailable(tmp_path, change):
    result = ComparisonService(ready(tmp_path), model()).run(FEB)
    item = next(item for item in result.agent.trace if item.tool_name == 'compare_periods')
    if change == 'version':
        item = item.model_copy(update={'datasets': (item.datasets[0].model_copy(update={'version_id': 'wrong'}), item.datasets[1])})
    else:
        updates = {'metric_type': 'current_volume'} if change == 'metric' else {'entity_id': 'station'} if change == 'entity' else {'unit': 'minutes'} if change == 'unit' else {'category': 'Member'} if change == 'category' else {}
        values = tuple(value.model_copy(update=updates) if value.entity_id == 'month' and value.metric_type == 'trip_count' else value for value in item.values)
        if change == 'conflict':
            values += tuple(value.model_copy(update={'exact_tool_value': 99}) for value in values if value.entity_id == 'month' and value.metric_type == 'trip_count')
        item = item.model_copy(update={'values': values})
    trace = tuple(item if old.tool_name == 'compare_periods' else old for old in result.agent.trace)
    if change == 'duplicate':
        trace += (item,)
    assert all(row.status == 'unavailable' for row in comparison_rows(result.baseline, result.agent.model_copy(update={'trace': trace}), result.report_id, result.datasets))


@pytest.mark.parametrize('change', ['html', 'report_id', 'datasets'])
def test_forged_precomputed_snapshot_rejected(tmp_path, change):
    store = ready(tmp_path)
    snapshot = generate_standard_dashboard(store, FEB)
    updates = {'html': 'forged'} if change == 'html' else {'report_id': 'f' * 32} if change == 'report_id' else {'datasets': tuple(reversed(snapshot.datasets))}
    with pytest.raises((ValueError, FileNotFoundError)):
        AgentService(store, model()).run(FEB, 'report', snapshot=snapshot.model_copy(update=updates), comparison_mode=True)


def test_execution_replan_cannot_drop_required_comparison_tool(tmp_path, monkeypatch):
    from mobility.agent_tools import AgentTools
    original = AgentTools.execute
    def execute(self, name, args, call_id):
        result, payload = original(self, name, args, call_id)
        if name == 'compare_periods':
            return result.model_copy(update={'status': 'failed', 'values': ()}), {}
        return result, payload
    monkeypatch.setattr(AgentTools, 'execute', execute)
    provider = FakeModel([{'kind': 'standard_report'}, {'tools': ['compare_periods', 'station_movers']}, {'tools': ['station_movers']}])
    result = ComparisonService(ready(tmp_path), provider).run(FEB)
    assert result.agent.status == 'partial'
    assert result.agent.validation_reason == 'missing_required_tool'
    assert all(row.status == 'unavailable' for row in result.rows)


def test_comparison_retries_finish_within_the_six_call_budget(tmp_path):
    from mobility.llm import ProviderSchemaError
    provider = FakeModel([ProviderSchemaError(), {'kind': 'standard_report'}, {'tools': ['station_movers']},
        {'tools': ['compare_periods', 'station_movers']},
        {'name': 'analyze_station_variance', 'station_id': 'UNKNOWN'},
        {'name': 'analyze_station_variance', 'station_id': '001'}])
    result = ComparisonService(ready(tmp_path), provider).run(FEB)
    assert result.agent.status == 'complete'
    assert result.agent.error_code is None
    assert result.agent.counters.llm_calls == 6
    assert all(row.status == 'match' for row in result.rows)


def test_shared_calculation_matches_cli_and_v1_is_unchanged(tmp_path):
    from pathlib import Path
    import hashlib
    import importlib.util
    from mobility.python_baseline import calculate
    root = Path(__file__).resolve().parents[2]
    v1 = root / 'Baseline Python Script v1.py'
    before = hashlib.sha256(v1.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location('comparison_cli_v2', root / 'Baseline Python Script v2.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.calculate is calculate
    store = ready(tmp_path)
    result = ComparisonService(store, model()).run(FEB)
    snapshot = __import__('mobility.baseline', fromlist=['BaselineReport']).BaselineReport.model_validate_json((tmp_path / 'reports' / result.report_id / 'evidence.json').read_text())
    assert cli.calculate(cli.ReadOnlyStore(tmp_path), snapshot)['monthly_totals'] == result.baseline.monthly_totals
    assert hashlib.sha256(v1.read_bytes()).hexdigest() == before


def test_pattern_valid_but_forged_call_id_is_unavailable(tmp_path):
    result = ComparisonService(ready(tmp_path), model()).run(FEB)
    trace = tuple(item.model_copy(update={'tool_call_id': f'{result.report_id}_selected_999'}) if item.tool_name == 'compare_periods' else item for item in result.agent.trace)
    assert all(row.status == 'unavailable' for row in comparison_rows(result.baseline, result.agent.model_copy(update={'trace': trace}), result.report_id, result.datasets))


def test_failed_agent_archive_retains_early_baseline_without_comparison(tmp_path, monkeypatch):
    events = []
    def fail(*args):
        raise OSError('private disk failure')
    monkeypatch.setattr(AgentService, '_persist', fail)
    with pytest.raises(FileNotFoundError):
        ComparisonService(ready(tmp_path), model()).run(FEB, events.append)
    assert events[0]['type'] == 'baseline'
    assert not list(tmp_path.rglob('comparison.json'))
    assert 'private disk failure' not in str(events)
