"""Comparison streaming boundary never needs a real model for verification."""
import json
from fastapi.testclient import TestClient
from mobility.app import create_app
from mobility.config import Settings
from mobility.storage import DatasetStore
from test_agent import FakeModel, version


def events(response):
    return [json.loads(line) for line in response.text.splitlines() if line]


def test_missing_months_and_wrong_period_do_not_dispatch(tmp_path, monkeypatch):
    monkeypatch.setattr('mobility.app.OpenAIProvider', lambda _: FakeModel([]))
    client = TestClient(create_app(Settings(data_root=tmp_path)))
    missing = events(client.post('/comparisons/stream', json={'period': {'year': 2026, 'month': 2}}))
    assert missing == [{'type': 'error', 'message': 'Both January and February 2026 must be accepted before this demo.'}]
    wrong = events(client.post('/comparisons/stream', json={'period': {'year': 2026, 'month': 1}}))
    assert wrong[0]['type'] == 'error'
    assert client.post('/comparisons/stream', json={'period': {'year': 2026, 'month': 2}, 'snapshot': {}}).status_code == 422


def test_stream_baseline_then_safe_provider_fallback(tmp_path, monkeypatch):
    store = DatasetStore(tmp_path)
    version(store, 1, {'S': 3})
    version(store, 2, {'S': 2})
    monkeypatch.setattr('mobility.app.OpenAIProvider', lambda _: FakeModel([RuntimeError('private provider details')]))
    response = TestClient(create_app(Settings(data_root=tmp_path))).post('/comparisons/stream', json={'period': {'year': 2026, 'month': 2}})
    streamed = events(response)
    assert streamed[0]['type'] == 'baseline'
    assert streamed[-1]['type'] == 'result'
    assert streamed[-1]['data']['agent']['status'] == 'partial'
    assert all(row['status'] == 'unavailable' for row in streamed[-1]['data']['rows'])
    assert 'private provider' not in response.text
    assert 'ride_id' not in response.text
