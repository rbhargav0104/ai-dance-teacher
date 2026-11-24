"""Consistent API error envelope: {"error": {"code", "message"}, "request_id"}."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _body(request: Request, code: str, message: str) -> dict[str, object]:
    return {
        "error": {"code": code, "message": message},
        "request_id": getattr(request.state, "request_id", None),
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(request, exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(_body(request, code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            _body(request, "invalid_request", "The request was not valid."), status_code=422
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Never leak stack traces, paths or secrets to clients.
        log.exception("unhandled_error", extra={"request_id": request.state.request_id})
        return JSONResponse(
            _body(request, "internal_error", "Something went wrong on our side."), status_code=500
        )
