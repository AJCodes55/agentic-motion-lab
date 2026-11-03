"""Detailed trace events are observable but never archived."""
from mobility.agent import AgentService
from mobility.contracts import Period
from mobility.storage import DatasetStore
from test_agent import FakeModel, version


def test_trace_captures_full_tool_payload_and_stays_out_of_archive(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    events = []
    result = AgentService(store, FakeModel([{'kind': 'supported_ad_hoc', 'metric': 'total_trips'}])).run(
        Period(year=2026, month=2), 'How many trips?', progress=events.append)
    trace = [event['data'] for event in events if event['type'] == 'trace']
    assert trace[0]['operation'] == 'request'
    assert [event['sequence'] for event in trace] == list(range(1, len(trace) + 1))
    assert any(event['operation'] == 'kpi_summary' and event['status'] == 'success' and event['output']['total_trips'] == 2 for event in trace)
    assert any(event['source'] == 'model' and event['output']['metric'] == 'total_trips' for event in trace if isinstance(event.get('output'), dict))
    assert trace[-1]['operation'] == 'final_response'
    assert trace[-1]['output']['report_html'] == result.report_html
    archive = tmp_path / 'reports' / result.run_id / 'agent' / 'agent-run.json'
    assert '"sequence"' not in archive.read_text()
    assert '"final_response"' not in archive.read_text()


def test_unknown_station_trace_records_lookup_before_refusal(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    events = []
    result = AgentService(store, FakeModel([{'kind': 'supported_ad_hoc', 'metric': 'station_starts',
                                           'station_id': 'OC8765'}])).run(
        Period(year=2026, month=2), 'total rides for station OC8765', progress=events.append)
    trace = [event['data'] for event in events if event['type'] == 'trace']
    lookup = next(event for event in trace if event['operation'] == 'station_lookup')
    assert lookup['inputs']['station_id'] == 'OC8765'
    assert lookup['output'] == []
    assert result.status == 'refused'
    assert trace[-1]['output']['status'] == 'refused'


def test_trace_exposes_model_substitution_and_effective_station_scope(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    events = []
    AgentService(store, FakeModel([{'kind': 'supported_ad_hoc', 'metric': 'station_starts',
                                   'station_id': 'S'}])).run(
        Period(year=2026, month=2), 'total rides for station OC8765', progress=events.append)
    trace = [event['data'] for event in events if event['type'] == 'trace']
    assert trace[0]['inputs']['command'].endswith('OC8765')
    classified = next(event for event in trace if event['operation'] == 'RequestIntent' and event['status'] == 'success')
    assert classified['output']['station_id'] == 'S'
    scope = next(event for event in trace if event['operation'] == 'station_scope')
    assert scope['source'] == 'application'
    assert 'station_id' in scope['output']


def test_final_trace_contains_actual_persistence_fallback(tmp_path, monkeypatch):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    service = AgentService(store, FakeModel([{'kind': 'supported_ad_hoc', 'metric': 'total_trips'}]))
    def fail_persist(*args):
        raise OSError('private file path must not reach trace')
    monkeypatch.setattr(service, '_persist', fail_persist)
    events = []
    result = service.run(Period(year=2026, month=2), 'How many trips?', progress=events.append)
    trace = [event['data'] for event in events if event['type'] == 'trace']
    assert result.status == 'partial'
    assert trace[-1]['output']['validation_reason'] == 'artifact_persistence_failed'
    assert trace[-1]['output']['report_html'] == result.report_html
    assert 'private file path' not in str(trace)


def test_stream_traces_missing_dataset_failure(tmp_path):
    from fastapi.testclient import TestClient
    from mobility.app import create_app
    from mobility.config import Settings
    import json
    client = TestClient(create_app(Settings(data_root=tmp_path, openai_api_key=None)))
    response = client.post('/agent-runs/stream', json={
        'period': {'year': 2026, 'month': 2}, 'command': 'standard report'})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]['data']['operation'] == 'request'
    assert events[-2]['data']['operation'] == 'request_failed'
    assert events[-2]['data']['status'] == 'failed'
    assert events[-1]['type'] == 'error'


def test_rejected_plan_attempts_are_visible_before_retry(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    events = []
    AgentService(store, FakeModel([{'kind': 'standard_report'},
                                   {'tools': ['make_chart']}, {'tools': ['make_chart']}])).run(
        Period(year=2026, month=2), 'standard report', progress=events.append)
    rejected = [event['data'] for event in events if event['type'] == 'trace'
                and event['data']['operation'] == 'analysis_plan' and event['data']['status'] == 'failed']
    assert len(rejected) == 2
    assert [event['output']['attempt'] for event in rejected] == [1, 2]


def test_provider_error_is_explicit_without_private_error_text(tmp_path):
    store = DatasetStore(tmp_path)
    version(store, 2, {'S': 2})
    events = []
    AgentService(store, FakeModel([RuntimeError('private provider detail')])).run(
        Period(year=2026, month=2), 'standard report', progress=events.append)
    trace = [event['data'] for event in events if event['type'] == 'trace']
    assert any(event['operation'] == 'run_error' and event['status'] == 'failed' for event in trace)
    assert 'private provider detail' not in str(trace)
