"""Backend-root shim so `from main import app` (used by tests/conftest.py)
resolves without requiring callers to know the canonical module path is
`app.main`. The runtime entrypoint (`run.py`) still imports `app.main:app`
directly — this file does NOT add any new behaviour, just a re-export."""
from app.main import app  # noqa: F401

__all__ = ["app"]
