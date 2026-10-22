"""Safe Phase 4 API boundary with the model unavailable."""
from fastapi.testclient import TestClient
from mobility.app import create_app
from mobility.config import Settings
from test_ingestion import source, row


def test_agent_endpoint_requires_data_and_preserves_baseline_on_missing_credentials(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path, openai_api_key=None)))
    payload = {'period': {'year': 2026, 'month': 1}, 'command': 'standard report'}
    missing = client.post('/agent-runs', json=payload)
    assert missing.status_code == 404
    data = source([row()])
    assert client.post('/ingestions', files=[('files', (data.name, data.content))]).json()['data']['results'][0]['status'] == 'accepted'
    result = client.post('/agent-runs', json=payload)
    assert result.status_code == 200
    body = result.json()['data']
    assert body['status'] == 'partial'
    assert body['counters']['llm_calls'] == 1
    assert 'KPI Scorecard' in body['report_html']
    assert body['error_code'] == 'ERR_TOOL_EXECUTION'
    assert 'openai-secret' not in result.text.lower()
    assert (tmp_path / 'reports' / body['run_id'] / 'agent' / 'agent-run.json').exists()


def test_agent_request_rejects_extra_fields(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path)))
    response = client.post('/agent-runs', json={'period': {'year': 2026, 'month': 1},
                                               'command': 'standard report', 'api_key': 'leak'})
    assert response.status_code == 422


def test_stream_exposes_stages_and_final_safe_fallback(tmp_path):
    import json
    client = TestClient(create_app(Settings(data_root=tmp_path, openai_api_key=None)))
    data = source([row()])
    client.post('/ingestions', files=[('files', (data.name, data.content))])
    with client.stream('POST', '/agent-runs/stream', json={
        'period': {'year': 2026, 'month': 1}, 'command': 'standard report'}) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]
    assert events[0] == {'type': 'stage', 'name': 'Data Ingest', 'status': 'complete'}
    assert events[-1]['type'] == 'result'
    assert events[-1]['data']['status'] == 'partial'
    assert 'KPI Scorecard' in events[-1]['data']['report_html']
    assert all('started_at' not in str(event) and 'ride_id' not in str(event) for event in events)
