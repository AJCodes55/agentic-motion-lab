"""API behavior at the ingestion boundary."""
import pytest
from fastapi.testclient import TestClient
from mobility.app import create_app
from mobility.config import Settings
from mobility.contracts import Period
from test_ingestion import source, row

@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(data_root=tmp_path)))

def upload(client, *sources):
    return client.post('/ingestions', files=[('files', (s.name, s.content, 'application/octet-stream')) for s in sources])

def test_upload_and_restart(client, tmp_path):
    response = upload(client, source([row()]))
    assert response.status_code == 200
    result = response.json()['data']['results'][0]
    assert result['status'] == 'accepted'
    assert result['quality']['valid_rows'] == 1
    assert TestClient(create_app(Settings(data_root=tmp_path))).get('/periods').json()['data']['periods'] == [result['dataset']]

def test_partial_acceptance(client):
    response = upload(client, source([row()]), source([row(started_at='bad')], 'JC-202602-citibike-tripdata.csv'))
    assert response.status_code == 200
    assert [r['status'] for r in response.json()['data']['results']] == ['accepted', 'rejected']
    assert len(client.get('/periods').json()['data']['periods']) == 1

def test_upload_count_and_filename(client):
    assert client.post('/ingestions').status_code == 422
    assert upload(client, *[source([row()])]*3).status_code == 400
    response = upload(client, source([row()], '../secret.csv'))
    assert response.status_code == 200
    assert response.json()['data']['results'][0]['status'] == 'rejected'
    assert 'secret' not in response.text

def test_size_limit(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path, max_file_bytes=10)))
    assert upload(client, source([row()])).status_code == 413

def test_busy_before_body(client):
    from mobility.service import _PROCESS_LOCK
    assert _PROCESS_LOCK.acquire(blocking=False)
    try:
        response = upload(client, source([row()]))
    finally:
        _PROCESS_LOCK.release()
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'ERR_INGESTION_BUSY'

def test_body_bound_before_parsing(tmp_path):
    client = TestClient(create_app(Settings(data_root=tmp_path, max_total_bytes=10)))
    response = client.post('/ingestions', content=b'x' * 65_547)
    assert response.status_code == 413
    assert response.json()['error']['code'] == 'ERR_UPLOAD_LIMIT'

def test_fetch_approved_source(client, monkeypatch):
    from mobility.service import IngestionService
    monkeypatch.setattr(IngestionService, 'fetch', lambda self, period: source([row()]))
    response = client.post('/ingestions/fetch', json={'period': {'year': 2026, 'month': 1}})
    assert response.status_code == 200
    assert response.json()['data']['results'][0]['status'] == 'accepted'
    assert client.post('/ingestions/fetch', json={'period': {'year': 2026, 'month': 1}, 'url': 'http://private'}).status_code == 422

def test_fetch_fallback_and_network_bounds(tmp_path, monkeypatch):
    import httpx
    from mobility.service import IngestionService
    requests = []
    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(404 if str(request.url).endswith('tripdata.zip') else 200, content=b'zip')
    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    result = IngestionService(Settings(data_root=tmp_path)).fetch(Period(year=2026, month=1))
    assert result.content == b'zip'
    assert requests == ['https://s3.amazonaws.com/tripdata/JC-202601-citibike-tripdata.zip', 'https://s3.amazonaws.com/tripdata/JC-202601-citibike-tripdata.csv.zip']

def test_rejected_replacement_keeps_active(client):
    first = upload(client, source([row()])).json()['data']['results'][0]['dataset']
    assert upload(client, source([row(started_at='bad')])).json()['data']['results'][0]['status'] == 'rejected'
    assert client.get('/periods').json()['data']['periods'] == [first]

def test_global_expanded_budget_precedes_activation(tmp_path):
    first = source([row()])
    second = source([row(started_at='2026-02-01 00:00:00', ended_at='2026-02-01 00:01:00')], 'JC-202602-citibike-tripdata.csv')
    client = TestClient(create_app(Settings(data_root=tmp_path, max_expanded_bytes=len(first.content)+1)))
    assert upload(client, first, second).status_code == 413
    assert client.get('/periods').json()['data']['periods'] == []
    assert len(list((tmp_path/'rejections').glob('*.json'))) == 1

def test_storage_failure_partial_result(client, monkeypatch):
    from mobility.storage import DatasetStore
    original = DatasetStore.persist_and_activate
    def persist(self, cleaned):
        if cleaned.period.month == 1:
            raise OSError('sensitive disk detail')
        return original(self, cleaned)
    monkeypatch.setattr(DatasetStore, 'persist_and_activate', persist)
    second = source([row(started_at='2026-02-01 00:00:00', ended_at='2026-02-01 00:01:00')], 'JC-202602-citibike-tripdata.csv')
    response = upload(client, source([row()]), second)
    assert response.status_code == 200
    assert 'sensitive' not in response.text
    assert [r['status'] for r in response.json()['data']['results']] == ['rejected', 'accepted']
    assert response.json()['data']['results'][0]['quality']['candidate_rows'] == 1

@pytest.mark.parametrize('status,content,expected', [(302,b'',502), (404,b'',404), (200,b'x'*11,413)])
def test_fetch_failures(tmp_path, monkeypatch, status, content, expected):
    import httpx
    from fastapi import HTTPException
    from mobility.service import IngestionService
    from mobility.contracts import Period
    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(lambda request: httpx.Response(status, content=content)), **kwargs))
    with pytest.raises(HTTPException) as caught:
        IngestionService(Settings(data_root=tmp_path, max_file_bytes=10)).fetch(Period(year=2026, month=1))
    assert caught.value.status_code == expected

def test_fetch_network_error(tmp_path, monkeypatch):
    import httpx
    from fastapi import HTTPException
    from mobility.service import IngestionService
    from mobility.contracts import Period
    def fail(request):
        raise httpx.ConnectError('private network detail')
    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(fail), **kwargs))
    with pytest.raises(HTTPException) as caught:
        IngestionService(Settings(data_root=tmp_path)).fetch(Period(year=2026, month=1))
    assert caught.value.status_code == 502


def test_stalled_body_times_out_and_releases_ingestion_lock(tmp_path):
    import asyncio
    import httpx
    app = create_app(Settings(data_root=tmp_path, body_read_timeout_seconds=0.01))

    async def check():
        async def stalled():
            await asyncio.sleep(0.05)
            yield b'never reaches parser'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/ingestions', content=stalled())
            assert response.status_code == 408
            assert response.json()['error']['code'] == 'ERR_UPLOAD_TIMEOUT'
    asyncio.run(check())
    assert upload(TestClient(app), source([row()])).json()['data']['results'][0]['status'] == 'accepted'


def test_large_category_dictionary_stays_on_disk_not_in_upload_response(client, tmp_path):
    data = source([row(ride_id=str(i), member_casual=f'{i:06d}' + 'x' * 100) for i in range(8000)])
    response = upload(client, data)
    assert response.status_code == 200
    result = response.json()['data']['results'][0]
    assert result['status'] == 'accepted'
    assert len(response.content) < 1_000_000
    assert 'member_value_mappings' not in result['quality']
    from mobility.storage import DatasetStore
    from mobility.contracts import DatasetReference
    reference = DatasetReference.model_validate_json(__import__('json').dumps(result['dataset']))
    metadata = DatasetStore(tmp_path).read_metadata(reference)
    assert len(metadata['quality']['member_value_mappings']) == 8000


def test_rejection_keeps_source_identity_and_quarantined_bytes(client, tmp_path):
    import hashlib
    import json
    data = source([row(started_at='invalid')])
    response = upload(client, data)
    assert response.json()['data']['results'][0]['status'] == 'rejected'
    record = json.loads(next((tmp_path / 'rejections').glob('*.json')).read_text())
    original = record['sources'][0]
    assert original['source_name'] == data.name
    raw = tmp_path / 'quarantine' / record['upload_id'] / original['quarantine_file']
    assert raw.read_bytes() == data.content
    assert original['sha256'] == hashlib.sha256(data.content).hexdigest()
