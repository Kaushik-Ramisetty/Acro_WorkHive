"""Centralised application exception hierarchy.

These exceptions are an **additive** complement to FastAPI's ``HTTPException``.
The existing codebase raises ``HTTPException`` directly in places, and
``ValueError`` / domain-specific errors in services — neither pattern is
deprecated by this module. New code can opt into :class:`AppException` for
a cleaner mapping between service-layer failures and HTTP responses; the
shared handler converts them to the same JSON shape FastAPI already emits
(``{"detail": "..."}``), so frontend behaviour is unchanged.

Wire-up
-------
The handler is registered in :mod:`app.main` if and only if this module is
imported there. Registration is idempotent. Existing handlers keep priority.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse


logger = logging.getLogger("hrms.errors")


class AppException(Exception):
    """Base class for domain errors that map cleanly to an HTTP status.

    The default shape ``{"detail": <message>}`` matches what FastAPI emits
    for ``HTTPException``, so a frontend that already handles ``err.detail``
    needs zero changes to consume :class:`AppException` instances.
    """
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, *, status_code: Optional[int] = None,
                 extra: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.extra: Dict[str, Any] = extra or {}

    def to_response_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"detail": self.message}
        # ``extra`` is merged at the top level so callers can include
        # contextual fields without breaking the FastAPI shape.
        payload.update(self.extra)
        return payload


# Concrete subclasses keep the call site readable.

class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND


class ValidationError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST


class AuthenticationError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED


class PermissionDenied(AppException):
    status_code = status.HTTP_403_FORBIDDEN


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT


def _safe_extra_from_request(request: Request) -> Dict[str, Any]:
    """Pull a minimal, safe context dict off the request for log lines.

    Read-only; never raises. Used so that the global handlers can emit
    structured log records without leaking request bodies or headers.
    """
    extra: Dict[str, Any] = {}
    try:
        extra["method"] = request.method
        extra["path"] = request.url.path
        if request.client and request.client.host:
            extra["ip"] = request.client.host
    except Exception:  # pragma: no cover — never break on logging
        pass
    return extra


def register_exception_handlers(app: FastAPI) -> None:
    """Idempotently attach AppException + global error handlers.

    Safe to call multiple times: FastAPI keeps the last-registered handler
    for a given exception class. The handlers preserve the exact JSON
    shape FastAPI's defaults already emit (``{"detail": ...}``) so the
    frontend's existing error-parsing code (which reads ``err.data.detail``)
    is unaffected.

    Handlers registered:
      * ``AppException``     → ``{"detail": ...}`` at the exception's
        ``status_code``. Logs at WARNING.
      * ``HTTPException``    → re-emits FastAPI's default JSON, *and* logs
        the failure with request context. Logging only — body shape is
        identical to the framework default.
      * ``SQLAlchemyError``  → ``{"detail": "Database error."}`` at 500.
        Logged at ERROR with full traceback. **Without this handler an
        unhandled DB error would produce the same 500 + traceback in
        stderr**, just without our structured log enrichment.
      * ``Exception`` (catch-all) → ``{"detail": "Internal Server Error"}``
        at 500. Logged at ERROR with full traceback. Without this handler
        FastAPI emits the same shape — we are strictly enriching logs.
    """

    @app.exception_handler(AppException)
    async def _handle_app_exception(request: Request, exc: AppException):  # noqa: D401
        extra = _safe_extra_from_request(request)
        extra["status_code"] = exc.status_code
        # AppException is a *known* condition — log at WARNING, not ERROR.
        logger.warning("AppException: %s", exc.message, extra=extra)
        return JSONResponse(status_code=exc.status_code, content=exc.to_response_dict())

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException):  # noqa: D401
        extra = _safe_extra_from_request(request)
        extra["status_code"] = exc.status_code
        # 4xx is client error — INFO. 5xx is server error — ERROR.
        if 500 <= exc.status_code < 600:
            logger.error("HTTPException %s: %s", exc.status_code, exc.detail, extra=extra)
        else:
            logger.info("HTTPException %s: %s", exc.status_code, exc.detail, extra=extra)
        # Identical body + headers to FastAPI's built-in handler. Status
        # codes that disallow a response body (1xx, 204, 304) must NOT
        # carry one — matches fastapi.exception_handlers.http_exception_handler.
        headers = getattr(exc, "headers", None)
        sc = exc.status_code
        no_body = sc < 200 or sc in (204, 304)
        if no_body:
            return Response(status_code=sc, headers=headers or {})
        return JSONResponse(status_code=sc, content={"detail": exc.detail},
                            headers=headers)

    # SQLAlchemy is an optional dep at import-time of this module. Wire the
    # handler only if SQLAlchemy is installed (it always is for this app,
    # but the guard keeps the module importable in isolation).
    try:
        from sqlalchemy.exc import SQLAlchemyError

        @app.exception_handler(SQLAlchemyError)
        async def _handle_sqlalchemy_error(request: Request, exc: SQLAlchemyError):  # noqa: D401
            extra = _safe_extra_from_request(request)
            extra["status_code"] = 500
            logger.exception("Unhandled database error", extra=extra)
            return JSONResponse(status_code=500, content={"detail": "Database error."})
    except Exception:  # pragma: no cover
        pass

    @app.exception_handler(Exception)
    async def _handle_unhandled(request: Request, exc: Exception):  # noqa: D401
        extra = _safe_extra_from_request(request)
        extra["status_code"] = 500
        logger.exception("Unhandled exception", extra=extra)
        # Same body shape FastAPI emits by default — frontend is unaffected.
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


__all__ = [
    "AppException",
    "AuthenticationError",
    "ConflictError",
    "NotFoundError",
    "PermissionDenied",
    "ValidationError",
    "register_exception_handlers",
]
