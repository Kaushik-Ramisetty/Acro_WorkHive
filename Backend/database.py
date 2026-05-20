"""database.py — compatibility shim re-exporting Base/engine/SessionLocal/get_db."""

from sqlalchemy import text

from app.db.base import Base                              # noqa: F401
from app.db.session import engine, SessionLocal, get_db   # noqa: F401


def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


__all__ = ["Base", "engine", "SessionLocal", "get_db", "check_db_connection"]
