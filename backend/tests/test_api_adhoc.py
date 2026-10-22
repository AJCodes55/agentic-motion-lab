"""Phase 5 public query and immutable history contracts."""
import pytest
from fastapi.testclient import TestClient
from mobility.app import create_app
from mobility.config import Settings
from test_ingestion import source, row


def test_query_history_and_archive(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path)))
    data = source([row()])
    client.post('/ingestions', files=[('files', (data.name, data.content))])
    response = client.post('/adhoc', json={'period': {'year': 2026, 'month': 1}, 'metric': 'total_trips', 'chart': True})
    assert response.status_code == 200
    result = response.json()['data']
    assert result['status'] == 'success'
    history = client.get('/reports/history').json()['data']['reports']
    assert any(item['report_id'] == result['report_id'] for item in history)
    archived = client.get('/reports/history/' + result['report_id'])
    assert archived.status_code == 200
    assert archived.json()['data']['html'] == result['html']
    assert client.get('/reports/history/' + '0' * 32).status_code == 404


def test_query_requires_explicit_month_and_catalog(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path)))
    for body in ({'metric': 'total_trips'}, {'period': {'year': 2026, 'month': 1}, 'metric': 'revenue'}):
        assert client.post('/adhoc', json=body).status_code == 422


def test_metric_values_and_chart_match_independent_mixed_rows(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path)))
    data = source([row(), row(1, member_casual='casual', rideable_type='electric_bike', ended_at='2026-01-01 00:03:00'),
                   row(2, member_casual='unclassified', rideable_type='unclassified', ended_at='2026-01-01 00:02:00')])
    client.post('/ingestions', files=[('files', (data.name, data.content))])
    for metric, expected in [('total_trips', [3]), ('average_duration', [2.0]),
                             ('member_share', [100 / 3] * 3), ('fleet_share', [100 / 3] * 3)]:
        result = client.post('/adhoc', json={'period': {'year': 2026, 'month': 1}, 'metric': metric, 'chart': True}).json()['data']
        query, chart = result['evidence'][-2:]
        assert [value['exact_tool_value'] for value in query['values']] == pytest.approx(expected)
        assert chart['values'] == query['values']
        if metric.endswith('share'):
            assert 'Unknown (unclassified)' in result['html']
