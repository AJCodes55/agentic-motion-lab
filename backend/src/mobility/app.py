"""Bounded local ingestion API with safe errors and structured request logs."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
from queue import Queue
from threading import Thread
from time import perf_counter
from uuid import uuid4
from collections.abc import Awaitable, Callable
from starlette.responses import Response

from fastapi import FastAPI, Request
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool

from .maintenance import application_lock
from .config import Settings
from .service import IngestionService
from .baseline import BaselineReport, generate_standard_dashboard
from .agent import AgentRun, AgentService
from .llm import OpenAIProvider
from .adhoc import AdhocRequest, AdhocResult, AdhocService
from .history import ReportHistoryEntry, list_report_history, read_archived_report
from .contracts import Contract
from .contracts import IngestionBatch, AvailablePeriods, FetchRequest, AnalysisRequest
from .ingestion import UploadedSource
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException

from .contracts import ApiError, ApiResponse, HealthData

logger = logging.getLogger('mobility.requests')


class ReportHistory(Contract):
    reports: tuple[ReportHistoryEntry, ...]


class ArchivedReport(Contract):
    html: str


def configure_logging() -> None:
    """Emit JSON records even when Uvicorn only configures its own loggers."""
    if not any(getattr(handler, '_mobility_json', False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        handler._mobility_json = True
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    request_id = request.state.request_id
    body = ApiResponse(success=False, data=None, error=ApiError(
        code=code, message=message, request_id=request_id))
    return JSONResponse(status_code=status, content=body.model_dump(),
                        headers={'X-Request-ID': request_id})


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or Settings()
    service = IngestionService(settings)
    @asynccontextmanager
    async def lifespan(_app):
        settings.data_root.mkdir(parents=True, exist_ok=True)
        with application_lock(settings.data_root):
            yield

    app = FastAPI(title='Monthly Mobility API', version='0.1.0', lifespan=lifespan)

    @app.middleware('http')
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.request_id = str(uuid4())
        started = perf_counter()
        try:
            if request.url.path in ('/ingestions', '/ingestions/fetch'):
                with service.exclusive():
                    maximum = settings.max_total_bytes + 65_536 if request.url.path == '/ingestions' else 4096
                    size = 0
                    chunks = []
                    async with asyncio.timeout(settings.body_read_timeout_seconds):
                        async for chunk in request.stream():
                            size += len(chunk)
                            if size > maximum:
                                raise HTTPException(413)
                            chunks.append(chunk)
                    request._body = b''.join(chunks)
                    response = await call_next(request)
            else:
                response = await call_next(request)
        except TimeoutError:
            response = error_response(request, 408, 'ERR_UPLOAD_TIMEOUT', 'Upload body read timed out.')
        except HTTPException as error:
            response = error_response(request, error.status_code,
                                      'ERR_INGESTION_BUSY' if error.status_code == 409 else 'ERR_UPLOAD_LIMIT',
                                      'An ingestion is already running.' if error.status_code == 409 else 'Upload limit exceeded.')
        except Exception as error:
            logger.error(json.dumps({"event": "request_failed", "request_id": request.state.request_id, "exception_type": type(error).__name__}))
            response = error_response(request, 500, 'INTERNAL_ERROR', 'The service could not complete the request.')
        response.headers['X-Request-ID'] = request.state.request_id
        route = request.scope.get('route')
        logger.info(json.dumps({
            'event': 'http_request', 'request_id': request.state.request_id,
            'method': request.method, 'route': getattr(route, 'path', 'unmatched'),
            'status_code': response.status_code,
            'duration_ms': round((perf_counter() - started) * 1000, 2),
        }))
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, _error: RequestValidationError) -> JSONResponse:
        return error_response(request, 422, 'VALIDATION_ERROR', 'Request fields are invalid.')

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        codes = {409: 'ERR_INGESTION_BUSY', 413: 'ERR_UPLOAD_LIMIT', 502: 'ERR_SOURCE_UNAVAILABLE'}
        return error_response(request, error.status_code, codes.get(error.status_code, 'HTTP_ERROR'), 'The requested operation is unavailable.')

    @app.get('/health', response_model=ApiResponse[HealthData])
    async def health() -> ApiResponse[HealthData]:
        return ApiResponse(success=True, data=HealthData(status='ok', service='citibike-analytics'), error=None)

    @app.get('/periods', response_model=ApiResponse[AvailablePeriods])
    def periods() -> ApiResponse[AvailablePeriods]:
        return ApiResponse(success=True, data=AvailablePeriods(periods=service.store.list_active()), error=None)

    @app.post('/reports', response_model=ApiResponse[BaselineReport])
    def report(body: FetchRequest, request: Request):
        try:
            result = generate_standard_dashboard(service.store, body.period)
        except KeyError:
            return error_response(request, 404, 'HTTP_ERROR', 'No accepted dataset exists for the reporting month.')
        return ApiResponse(success=True, data=result, error=None)

    @app.post('/adhoc', response_model=ApiResponse[AdhocResult])
    def adhoc(body: AdhocRequest, request: Request):
        try:
            result = AdhocService(service.store).run(body)
        except KeyError:
            return error_response(request, 404, 'HTTP_ERROR', 'No accepted dataset exists for the reporting month.')
        return ApiResponse(success=True, data=result, error=None)

    @app.get('/reports/history', response_model=ApiResponse[ReportHistory])
    def history():
        return ApiResponse(success=True, data=ReportHistory(reports=list_report_history(service.store)), error=None)

    @app.get('/reports/history/{report_id}', response_model=ApiResponse[ArchivedReport])
    def archived(report_id: str, request: Request):
        try:
            html = read_archived_report(service.store, report_id)
        except (KeyError, ValueError, FileNotFoundError):
            return error_response(request, 404, 'HTTP_ERROR', 'Archived report is unavailable.')
        return ApiResponse(success=True, data=ArchivedReport(html=html), error=None)

    @app.post('/agent-runs', response_model=ApiResponse[AgentRun])
    def agent_run(body: AnalysisRequest, request: Request) -> ApiResponse[AgentRun] | JSONResponse:
        try:
            result = AgentService(service.store, OpenAIProvider(settings)).run(body.period, body.command, body.station_id)
        except KeyError:
            return error_response(request, 404, 'HTTP_ERROR', 'No accepted dataset exists for the reporting month.')
        return ApiResponse(success=True, data=result, error=None)

    @app.post('/agent-runs/stream')
    def agent_run_stream(body: AnalysisRequest) -> StreamingResponse:
        events: Queue[dict | None] = Queue()

        def produce() -> None:
            try:
                result = AgentService(service.store, OpenAIProvider(settings)).run(
                    body.period, body.command, body.station_id, progress=events.put)
                events.put({'type': 'result', 'data': result.model_dump(mode='json')})
            except KeyError:
                events.put({'type': 'error', 'message': 'No accepted dataset exists for the reporting month.'})
            except Exception as error:
                logger.error('agent_stream_failed', extra={'exception_type': type(error).__name__})
                events.put({'type': 'error', 'message': 'The service could not complete the request.'})
            finally:
                events.put(None)

        Thread(target=produce, daemon=True).start()

        def stream():
            while (event := events.get()) is not None:
                yield json.dumps(event, allow_nan=False) + '\n'

        return StreamingResponse(stream(), media_type='application/x-ndjson',
                                 headers={'Cache-Control': 'no-store'})

    @app.post('/ingestions', response_model=ApiResponse[IngestionBatch], openapi_extra={
        'requestBody': {'required': True, 'content': {'multipart/form-data': {'schema': {
            'type': 'object', 'required': ['files'], 'properties': {'files': {
                'type': 'array', 'minItems': 1, 'maxItems': 2,
                'items': {'type': 'string', 'format': 'binary'}}}}}}}})
    async def ingest(request: Request) -> ApiResponse[IngestionBatch]:
        async with request.form(max_files=2, max_fields=0) as form:
            files = form.getlist('files')
            if not 1 <= len(files) <= 2 or len(form.multi_items()) != len(files):
                raise HTTPException(422)
            sources = []
            total = 0
            for uploaded in files:
                if not isinstance(uploaded, UploadFile):
                    raise HTTPException(422)
                content = await uploaded.read(settings.max_file_bytes + 1)
                total += len(content)
                if len(content) > settings.max_file_bytes or total > settings.max_total_bytes:
                    raise HTTPException(413)
                sources.append(UploadedSource(uploaded.filename or '', content))
            result = await run_in_threadpool(service.ingest, tuple(sources))
        return ApiResponse(success=True, data=result, error=None)

    @app.post('/ingestions/fetch', response_model=ApiResponse[IngestionBatch])
    def fetch(body: FetchRequest) -> ApiResponse[IngestionBatch]:
        result = service.ingest((service.fetch(body.period),))
        return ApiResponse(success=True, data=result, error=None)

    return app


app = create_app()
