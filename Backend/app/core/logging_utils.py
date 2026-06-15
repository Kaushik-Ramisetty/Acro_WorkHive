"""Centralised logging helpers.

This module is **additive** and **safe to import everywhere** — it has no
SQLAlchemy / FastAPI dependency at module load time, never reconfigures
existing handlers, and never raises.

Two pieces:

1. :func:`get_logger` — preferred way to obtain a module logger. Returns a
   stdlib ``logging.Logger`` so any existing log call you already wrote
   keeps working unchanged.

2. :class:`RequestContext` — a thread-local that the request-logging
   middleware (see :mod:`app.middleware.request_logging`) populates per
   request with ``request_id`` / ``user_id`` / ``method`` / ``path``.
   Anywhere in the codebase you can call
   :func:`current_request_context` to enrich a log line with that data.

Design constraints
------------------
- Existing log calls (`logger.info(...)`, `logger.exception(...)`) are
  unchanged in behaviour. This module never patches the stdlib logger.
- The structured fields are emitted via ``extra=`` so formatters that
  don't know about them simply ignore them — no surprise crashes.
- ``get_logger(__name__)`` is interchangeable with
  ``logging.getLogger(__name__)``. Adoption is purely cosmetic.
"""
from __future__ import annotations

import contextvars
import logging
import uuid
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Request context (populated by request_logging middleware)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RequestContext:
    """Per-request metadata. Populated by the request-logging middleware
    and readable from anywhere via :func:`current_request_context`."""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    method: Optional[str] = None
    path: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[str] = None
    ip: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


# Use contextvars so the context is correct across async/await boundaries
# *and* thread-pool offloads (run_in_threadpool copies context).
_request_ctx: contextvars.ContextVar[Optional[RequestContext]] = (
    contextvars.ContextVar("hrms_request_context", default=None)
)


def set_request_context(ctx: RequestContext) -> contextvars.Token:
    """Install a request context. Returns a token to pass to
    :func:`reset_request_context` once the request finishes."""
    return _request_ctx.set(ctx)


def reset_request_context(token: contextvars.Token) -> None:
    try:
        _request_ctx.reset(token)
    except Exception:
        # Token may already have been reset on this context — fine.
        pass


def current_request_context() -> Optional[RequestContext]:
    """Read the current request context, or ``None`` if outside a request
    (e.g. Celery task, startup hook, REPL)."""
    return _request_ctx.get()


# ─────────────────────────────────────────────────────────────────────────────
# Logger factory
# ─────────────────────────────────────────────────────────────────────────────

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Drop-in replacement for ``logging.getLogger(name)``.

    Provided as a single import surface so future enhancements (per-logger
    filters, redaction, structured-extras injection) can be added in one
    place without touching every call site.
    """
    return logging.getLogger(name or "hrms")


def log_with_context(logger: logging.Logger, level: int, msg: str,
                     *args: Any, **kwargs: Any) -> None:
    """Emit a log line with the current :class:`RequestContext` merged into
    ``extra``. Existing extras are preserved.

    Equivalent to ``logger.log(level, msg, *args, **kwargs)`` when no
    request context is active.
    """
    ctx = current_request_context()
    if ctx is not None:
        extra = kwargs.pop("extra", None) or {}
        # Don't shadow caller-provided fields.
        for k, v in ctx.to_dict().items():
            extra.setdefault(k, v)
        kwargs["extra"] = extra
    logger.log(level, msg, *args, **kwargs)


__all__ = [
    "RequestContext",
    "current_request_context",
    "get_logger",
    "log_with_context",
    "reset_request_context",
    "set_request_context",
]
