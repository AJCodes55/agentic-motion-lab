"""Report generation uses accepted immutable versions without any model calls."""
from fastapi.testclient import TestClient
from mobility.app import create_app
from mobility.config import Settings
from test_ingestion import source, row


def test_generate_baseline_and_missing_month(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path)))
    missing = client.post('/reports', json={'period': {'year': 2026, 'month': 1}})
    assert missing.status_code == 404
    assert missing.json()['error']['message'] == 'No accepted dataset exists for the reporting month.'
    uploaded = client.post('/ingestions', files=[('files', (source([row()]).name, source([row()]).content))])
    assert uploaded.json()['data']['results'][0]['status'] == 'accepted'
    response = client.post('/reports', json={'period': {'year': 2026, 'month': 1}})
    assert response.status_code == 200
    report = response.json()['data']
    assert report['llm_calls'] == 0
    assert len(report['datasets']) == 1
    assert 'KPI Scorecard' in report['html']
    assert (tmp_path / 'reports' / report['report_id'] / 'index.html').is_file()


def test_report_request_is_strict(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path)))
    for body in ({}, {'period': {'year': 2026, 'month': 13}},
                 {'period': {'year': 2026, 'month': 1}, 'path': '/tmp/private'}):
        assert client.post('/reports', json=body).status_code == 422


def test_accepted_long_station_identifier_can_be_reported(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path)))
    data = source([row(start_station_id='S' * 129)])
    assert client.post('/ingestions', files=[('files', (data.name, data.content))]).json()['data']['results'][0]['status'] == 'accepted'
    response = client.post('/reports', json={'period': {'year': 2026, 'month': 1}})
    assert response.status_code == 200
    assert 'S' * 129 in response.json()['data']['html']
