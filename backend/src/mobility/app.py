"""Health-only application with safe API errors and structured request logs."""
import json
import logging
from time import perf_counter
from uuid import uuid4
from collections.abc import Awaitable, Callable
from starlette.responses import Response

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .contracts import ApiError, ApiResponse, HealthData

logger = logging.getLogger('mobility.requests')


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


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title='Monthly Mobility API', version='0.1.0')

    @app.middleware('http')
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.request_id = str(uuid4())
        started = perf_counter()
        try:
            response = await call_next(request)
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
        return error_response(request, error.status_code, 'HTTP_ERROR', 'The requested operation is unavailable.')

    @app.get('/health', response_model=ApiResponse[HealthData])
    async def health() -> ApiResponse[HealthData]:
        return ApiResponse(success=True, data=HealthData(status='ok', service='citibike-analytics'), error=None)

    return app


app = create_app()
