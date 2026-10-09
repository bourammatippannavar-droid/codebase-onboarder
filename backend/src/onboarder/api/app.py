import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from onboarder.api.routes import health_router, router
from onboarder.api.schemas import Problem
from onboarder.bootstrap import ApplicationContainer, create_container
from onboarder.services.api import ServiceError

logger = logging.getLogger("onboarder.api")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def create_app(container: ApplicationContainer | None = None) -> FastAPI:
    active_container = container or create_container()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        active_container.recover_interrupted()
        try:
            yield
        finally:
            active_container.shutdown()

    application = FastAPI(
        title="Onboarder API",
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.container = active_container
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    application.include_router(health_router)

    @application.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if _REQUEST_ID_PATTERN.fullmatch(incoming) else str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "route": request.url.path,
                    "status": response.status_code,
                },
                separators=(",", ":"),
            )
        )
        return response

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return _problem_response(
            request,
            exc.status,
            exc.code,
            _title(exc.code),
            exc.detail,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return _problem_response(
            request,
            422,
            "validation_error",
            "Request validation failed",
            "One or more request fields are invalid.",
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        detail = "The requested resource was not found." if exc.status_code == 404 else "The request could not be completed."
        return _problem_response(request, exc.status_code, code, _title(code), detail)

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            json.dumps(
                {
                    "event": "internal_error",
                    "request_id": getattr(request.state, "request_id", "unknown"),
                    "error_type": type(exc).__name__,
                },
                separators=(",", ":"),
            )
        )
        return _problem_response(
            request,
            500,
            "internal_error",
            "Internal server error",
            "An unexpected error occurred.",
        )

    return application


def _problem_response(
    request: Request, status: int, code: str, title: str, detail: str
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    body = Problem(
        type=f"https://onboarder.local/problems/{code}",
        title=title,
        status=status,
        detail=detail,
        code=code,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(mode="json"),
        media_type="application/problem+json",
        headers={"X-Request-ID": request_id},
    )


def _title(code: str) -> str:
    return code.replace("_", " ").capitalize()


app = create_app()
