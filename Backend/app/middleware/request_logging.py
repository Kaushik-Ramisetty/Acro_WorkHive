"""Non-invasive request-logging middleware.

Logs one line per HTTP request with method, path, status code, and
duration. Also installs a per-request :class:`RequestContext` so any
logger called *inside* the request (services, repositories, etc.) can
have its records enriched with ``request_id`` / ``user_id`` / etc.

Guarantees
----------
- **Never** modifies the request or response body.
- **Never** changes status codes, headers, or response shape.
- **Never** raises into the request pipeline — every operation here is
  wrapped in a defensive try/except so a misbehaving log line cannot
  break a working endpoint.
- A single ``X-Request-ID`` header is **added** to the response. If the
  client supplied one, that value is honoured. If not, a fresh 12-char
  request id is generated. Adding a response header is the only
  externally-visible effect of this middleware; the frontend ignores
  unknown response headers, so this does not change UI behaviour.

Disable at runtime by setting ``HRMS_DISABLE_REQUEST_LOG=true``.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_utils import (
    RequestContext,
    reset_request_context,
    set_request_context,
)


logger = logging.getLogger("hrms.request")

_REQUEST_ID_HEADER = "X-Request-ID"
_DISABLED = (os.getenv("HRMS_DISABLE_REQUEST_LOG", "").lower() == "true")


def _extract_user_id(request: Request) -> Optional[int]:
    """Best-effort: peek at the JWT to grab the user id without touching
    the DB. Failures are silently ignored — this is observability data
    only, not used for authorization."""
    try:
        auth = request.headers.get("authorization") or ""
        if not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        from app.core.security import decode_access_token
        claims = decode_access_token(token)
        sub = claims.get("sub")
        if sub is None:
            return None
        # ``sub`` is a string of either the employee id (Core 2FA flow) or,
        # for some legacy tokens, the email. Only return an int.
        try:
            return int(sub)
        except (TypeError, ValueError):
            return None
    except Exception:
        return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _DISABLED:
            return await call_next(request)

        # Honour an inbound X-Request-ID, else generate one.
        inbound_id = request.headers.get(_REQUEST_ID_HEADER)
        request_id = (inbound_id.strip() if inbound_id else "") or uuid.uuid4().hex[:12]

        ctx = RequestContext(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            user_id=_extract_user_id(request),
            ip=(request.client.host if request.client else None),
        )
        token = set_request_context(ctx)
        start = time.perf_counter()
        status_code = 500  # default if the downstream raises
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            try:
                duration_ms = round((time.perf_counter() - start) * 1000.0, 1)
                extra = ctx.to_dict()
                extra["status_code"] = status_code
                extra["duration_ms"] = duration_ms
                # 5xx -> ERROR. 4xx -> INFO. 2xx/3xx -> INFO.
                lvl = logging.ERROR if status_code >= 500 else logging.INFO
                logger.log(lvl, "%s %s -> %s (%sms)",
                           ctx.method, ctx.path, status_code, duration_ms, extra=extra)
                # Attach the request id to the response — frontend ignores
                # unknown headers, so this is non-breaking.
                try:
                    if "response" in locals():
                        response.headers[_REQUEST_ID_HEADER] = request_id
                except Exception:
                    pass
            except Exception:
                # Logging must never break a request. Swallow.
                pass
            finally:
                reset_request_context(token)


__all__ = ["RequestLoggingMiddleware"]
