import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mobility.app import create_app
from mobility.contracts import DatasetReference, Period, QualitySummary


def test_health_and_request_id(caplog):
    with caplog.at_level(logging.INFO), TestClient(create_app()) as client:
        response = client.get('/health', headers={'X-Request-ID': 'unsafe\tvalue'})
    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': {'status': 'ok', 'service': 'citibike-analytics'}, 'error': None}
    assert len(response.headers['X-Request-ID']) == 36
    record = next(json.loads(r.message) for r in caplog.records if r.name == 'mobility.requests')
    assert record['status_code'] == 200
    assert record['request_id'] == response.headers['X-Request-ID']


def test_not_found_is_consistent(caplog):
    with caplog.at_level(logging.INFO):
        response = TestClient(create_app()).get('/private-user-path?secret=never-log')
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'HTTP_ERROR'
    assert response.json()['data'] is None
    records = [r.message for r in caplog.records if r.name == 'mobility.requests']
    assert records and all('never-log' not in r and 'private-user-path' not in r for r in records)


def test_validation_does_not_echo_input():
    app = create_app()

    @app.post('/test-period')
    def validate_period(period: Period):
        return period

    response = TestClient(app).post('/test-period', json={'year': 'private-secret', 'month': 13})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    assert 'private-secret' not in response.text


def test_unexpected_error_is_safe(caplog):
    app = create_app()

    @app.get('/test-error')
    def fail():
        raise RuntimeError('secret-credential')

    with caplog.at_level(logging.INFO):
        response = TestClient(app, raise_server_exceptions=False).get('/test-error')
    assert response.status_code == 500
    assert response.json()['error']['code'] == 'INTERNAL_ERROR'
    assert response.headers['X-Request-ID'] == response.json()['error']['request_id']
    assert 'secret-credential' not in response.text
    assert 'secret-credential' not in caplog.text


@pytest.mark.parametrize('payload', [{'year': 2026, 'month': 0}, {'year': '2026', 'month': 1}, {'year': 2026, 'month': 1, 'extra': 1}])
def test_period_rejects_invalid(payload):
    with pytest.raises(ValidationError):
        Period(**payload)


def test_contracts_are_frozen_and_validated():
    period = Period(year=2026, month=1)
    ref = DatasetReference(period=period, version_id='version-1', sha256='a' * 64)
    assert ref.period == period
    with pytest.raises(ValidationError):
        period.month = 2
    with pytest.raises(ValidationError):
        QualitySummary(source_rows=2, valid_rows=3, excluded_rows=0)
    assert QualitySummary(source_rows=3, valid_rows=2, excluded_rows=1).valid_rows == 2


def test_contract_export_and_outcomes():
    from mobility.contracts import AnalysisRequest, ApiResponse, Claim, ToolResult
    from mobility.export_openapi import export_schema
    from mobility.config import Settings
    schema = export_schema()
    assert set(('AnalysisRequest', 'Claim', 'QualitySummary')) <= schema['components']['schemas'].keys()
    assert '/health' in schema['paths']
    assert Settings().host == '127.0.0.1'
    request = AnalysisRequest(period=Period(year=2026, month=1), command='Summarize')
    assert request.station_id is None
    from mobility.contracts import EvidenceValue, ToolArguments
    value = EvidenceValue(entity_id='all', metric_type='trip_count', period=request.period,
                          unit='trips', exact_tool_value=42, eligible=True)
    datasets = (DatasetReference(period=request.period, version_id='v1', sha256='a' * 64),)
    evidence = ToolResult(run_id='run-1', tool_call_id='call-1', tool_name='kpi_summary', stage='baseline',
                          status='success', arguments=ToolArguments(current_period=request.period),
                          datasets=datasets, values=(value,))
    claim = Claim(claim_id='c1', run_id='run-1', tool_call_id=evidence.tool_call_id,
                  datasets=datasets, transition='standalone', **value.model_dump())
    assert claim.exact_tool_value == 42
    with pytest.raises(ValidationError):
        ApiResponse(success=True, data=None, error={'code': 'HTTP_ERROR', 'message': 'error', 'request_id': 'id'})


@pytest.mark.parametrize('value,eligible', [(42, False), (None, True), (float('inf'), True)])
def test_evidence_rejects_invalid_eligibility(value, eligible):
    from mobility.contracts import EvidenceValue
    with pytest.raises(ValidationError):
        EvidenceValue(entity_id='all', metric_type='trip_count', period=Period(year=2026, month=1),
                      unit='trips', exact_tool_value=value, eligible=eligible)


@pytest.mark.parametrize('patch', [{'sha256': 'invalid'}, {'version_id': '../unsafe'}])
def test_dataset_identity_invalid(patch):
    with pytest.raises(ValidationError):
        DatasetReference(**{'period': Period(year=2026, month=1), 'version_id': 'v1', 'sha256': 'a' * 64, **patch})


def test_quality_file_counts_reconcile():
    with pytest.raises(ValidationError):
        QualitySummary(source_rows=3, valid_rows=3, excluded_rows=0, source_filenames=('file.csv',))
    with pytest.raises(ValidationError):
        QualitySummary(source_rows=3, valid_rows=3, excluded_rows=0, source_filenames=('file.csv',), per_csv_parsed_counts=(2,))
    with pytest.raises(ValidationError):
        QualitySummary(source_rows=3, valid_rows=0, excluded_rows=3)


def test_default_logger_emits_json_and_config_is_idempotent():
    from io import StringIO
    from mobility.app import configure_logging
    logger = logging.getLogger('mobility.requests')
    configure_logging()
    handlers = tuple(logger.handlers)
    configure_logging()
    assert tuple(logger.handlers) == handlers
    assert logger.isEnabledFor(logging.INFO)
    handler = next(h for h in handlers if getattr(h, '_mobility_json', False))
    stream = StringIO()
    previous = handler.setStream(stream)
    try:
        TestClient(create_app()).get('/health')
    finally:
        handler.setStream(previous)
    assert json.loads(stream.getvalue())['event'] == 'http_request'


def test_calendar_year_one_is_valid():
    assert Period(year=1, month=1).year == 1
