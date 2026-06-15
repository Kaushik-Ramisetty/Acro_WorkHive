"""One-shot logging configuration helper.

The codebase currently relies on per-module ``logger = logging.getLogger(__name__)``
calls plus whatever uvicorn / pytest provides. That works fine but means a
production deploy can't easily reroute logs to JSON, structured handlers, or
a centralised aggregator without editing many files.

This module is **opt-in**. It is *not* called by ``app.main`` to avoid any
behavioural change in this refactor pass. Production deployments can invoke
:func:`configure_logging` from their entry-point (or set the ``HRMS_LOG_JSON``
env var) when ready.

Design constraints
------------------
- Never raises at import time.
- Does not silence existing handlers — it adds a root handler only if none
  is configured (typical when not running under uvicorn).
- Reads level from ``HRMS_LOG_LEVEL`` (default INFO).
- Reads ``HRMS_LOG_JSON=true`` for one-line JSON-ish records suitable for
  log aggregators. Default is a human-readable format.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Optional


# Field names the request-logging middleware injects via ``extra=``. Listed
# explicitly so we never serialise unrelated LogRecord attributes.
_REQUEST_EXTRA_FIELDS = ("request_id", "method", "path", "user_id", "role", "ip", "status_code", "duration_ms")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field_name in _REQUEST_EXTRA_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class _ContextHumanFormatter(logging.Formatter):
    """Human-readable formatter that appends request-context fields when
    present. If no request context is attached, output matches the legacy
    `"%(asctime)s %(levelname)-7s %(name)s :: %(message)s"` format byte-for-byte
    so dev log output is unchanged."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        suffix_parts = []
        for field_name in _REQUEST_EXTRA_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                suffix_parts.append(f"{field_name}={value}")
        if suffix_parts:
            return f"{base}  [{' '.join(suffix_parts)}]"
        return base


def configure_logging(level: Optional[str] = None, *, force: bool = False) -> None:
    """Idempotently install a root logging handler.

    If a handler is already configured on the root logger (uvicorn does this)
    and ``force`` is False, this function is a no-op — so existing log lines
    are preserved verbatim.
    """
    root = logging.getLogger()
    if root.handlers and not force:
        return
    level_name = (level or os.getenv("HRMS_LOG_LEVEL") or "INFO").upper()
    handler = logging.StreamHandler(stream=sys.stdout)
    if os.getenv("HRMS_LOG_JSON", "").lower() == "true":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(_ContextHumanFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level_name, logging.INFO))


__all__ = ["configure_logging"]
