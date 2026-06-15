"""db_compat.py — SQL Server / SQLite dialect-aware DDL helpers.

All raw-SQL migration scripts should use these helpers instead of writing
dialect-specific SQL directly.  The helpers detect the current engine dialect
at runtime and emit the correct syntax.

Usage:
    from app.utils.db_compat import is_mssql, create_table_if_not_exists, ...

    with engine.connect() as conn:
        create_table_if_not_exists(conn, "my_table", column_defs, constraints)
        add_column_if_not_exists(conn, "my_table", "new_col", "VARCHAR(100)")
        conditional_insert(conn, "my_table", unique_cols, value_dict)
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Connection

log = logging.getLogger("hrms.db_compat")


# ─── Dialect detection ────────────────────────────────────────────────────────

def is_mssql(conn: Connection) -> bool:
    """Return True when connected to SQL Server (mssql/pyodbc)."""
    return conn.dialect.name in ("mssql", "pyodbc")


def dialect_name(conn: Connection) -> str:
    return conn.dialect.name


# ─── Table existence ──────────────────────────────────────────────────────────

def table_exists(conn: Connection, table_name: str) -> bool:
    """Check whether a table already exists — works for both SQLite and MSSQL."""
    if is_mssql(conn):
        row = conn.execute(
            text("SELECT OBJECT_ID(:tn, 'U')"),
            {"tn": table_name},
        ).scalar()
        return row is not None
    else:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:tn"),
            {"tn": table_name},
        ).fetchone()
        return row is not None


def column_exists(conn: Connection, table_name: str, column_name: str) -> bool:
    """Check whether a column exists in a table."""
    if is_mssql(conn):
        row = conn.execute(
            text("""
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = :tn AND COLUMN_NAME = :cn
            """),
            {"tn": table_name, "cn": column_name},
        ).fetchone()
        return row is not None
    else:
        # SQLite: PRAGMA table_info returns one row per column
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        return any(r[1] == column_name for r in rows)


def index_exists(conn: Connection, index_name: str, table_name: Optional[str] = None) -> bool:
    """Check whether a named index exists."""
    if is_mssql(conn):
        if table_name:
            row = conn.execute(
                text("""
                    SELECT 1 FROM sys.indexes
                    WHERE name = :ix AND object_id = OBJECT_ID(:tn)
                """),
                {"ix": index_name, "tn": table_name},
            ).fetchone()
        else:
            row = conn.execute(
                text("SELECT 1 FROM sys.indexes WHERE name = :ix"),
                {"ix": index_name},
            ).fetchone()
        return row is not None
    else:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND name=:ix"),
            {"ix": index_name},
        ).fetchone()
        return row is not None


# ─── DDL helpers ──────────────────────────────────────────────────────────────

def add_column_if_not_exists(
    conn: Connection,
    table_name: str,
    column_name: str,
    column_def: str,
) -> bool:
    """Add a column to a table only if it doesn't already exist.

    Returns True if the column was added, False if it already existed.
    ``column_def`` should be dialect-neutral where possible, e.g.:
        "VARCHAR(100) NULL"
        "INTEGER NOT NULL DEFAULT 0"
        "FLOAT NOT NULL DEFAULT 0.0"
        "TEXT"
        "DATE"
        "DATETIME"   (SQLite) / "DATETIME2" (MSSQL) — use "DATETIME" for compat
    """
    if column_exists(conn, table_name, column_name):
        return False
    try:
        conn.execute(text(f"ALTER TABLE {table_name} ADD {column_name} {column_def}"))
        conn.commit()
        log.info("Added column %s.%s (%s)", table_name, column_name, column_def)
        return True
    except Exception as exc:
        log.warning("add_column_if_not_exists failed for %s.%s: %s", table_name, column_name, exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def create_index_if_not_exists(
    conn: Connection,
    index_name: str,
    table_name: str,
    columns: str,          # e.g. "employee_id, created_at DESC"
    unique: bool = False,
) -> bool:
    """Create an index only if it doesn't already exist."""
    if index_exists(conn, index_name, table_name):
        return False
    unique_kw = "UNIQUE " if unique else ""
    try:
        conn.execute(text(
            f"CREATE {unique_kw}INDEX {index_name} ON {table_name}({columns})"
        ))
        conn.commit()
        log.info("Created index %s on %s(%s)", index_name, table_name, columns)
        return True
    except Exception as exc:
        log.warning("create_index_if_not_exists failed for %s: %s", index_name, exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def _normalize_col_def(col_def: str, mssql: bool) -> str:
    """Translate SQLite-specific types/defaults to MSSQL-compatible equivalents."""
    if not mssql:
        return col_def
    # AUTOINCREMENT → IDENTITY(1,1) PRIMARY KEY (handled at create_table level)
    col_def = col_def.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "INT IDENTITY(1,1) PRIMARY KEY")
    col_def = col_def.replace("INTEGER PRIMARY KEY", "INT PRIMARY KEY")
    col_def = col_def.replace("AUTOINCREMENT", "")
    # SQLite date defaults
    col_def = col_def.replace("DEFAULT (datetime('now'))", "DEFAULT GETDATE()")
    col_def = col_def.replace("DEFAULT CURRENT_TIMESTAMP", "DEFAULT GETDATE()")
    # REAL → FLOAT
    col_def = col_def.replace("REAL", "FLOAT")
    # BOOLEAN → BIT
    col_def = col_def.replace("BOOLEAN", "BIT")
    return col_def


def create_table_if_not_exists(
    conn: Connection,
    table_name: str,
    column_defs: Sequence[str],
    table_constraints: Optional[Sequence[str]] = None,
    indexes: Optional[Sequence[tuple[str, str, str]]] = None,
) -> bool:
    """Create a table if it doesn't already exist.

    Args:
        table_name: SQL table name.
        column_defs: List of column definition strings.
        table_constraints: Optional list of table-level constraints
            (e.g. UNIQUE(col1, col2)).
        indexes: Optional list of (index_name, table_name, columns) tuples
            to create after table creation.

    Returns True if the table was created, False if it already existed.
    """
    if table_exists(conn, table_name):
        return False

    mssql = is_mssql(conn)
    normalized = [_normalize_col_def(c, mssql) for c in column_defs]
    all_parts = list(normalized)
    if table_constraints:
        all_parts.extend(table_constraints)

    cols_sql = ",\n    ".join(all_parts)
    ddl = f"CREATE TABLE {table_name} (\n    {cols_sql}\n)"

    try:
        conn.execute(text(ddl))
        conn.commit()
        log.info("Created table %s", table_name)
    except Exception as exc:
        log.warning("create_table_if_not_exists failed for %s: %s", table_name, exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return False

    # Create indexes after table
    if indexes:
        for idx_name, idx_table, idx_cols in indexes:
            create_index_if_not_exists(conn, idx_name, idx_table, idx_cols)

    return True


def conditional_insert(
    conn: Connection,
    table_name: str,
    unique_cols: dict[str, Any],
    value_cols: dict[str, Any],
) -> bool:
    """Insert a row only if no row matching unique_cols already exists.

    Replaces `INSERT OR IGNORE` (SQLite) with a portable IF NOT EXISTS pattern.

    Returns True if a row was inserted, False if it was skipped.
    """
    all_vals = {**unique_cols, **value_cols}
    where_clauses = " AND ".join(f"{k} = :{k}" for k in unique_cols)
    insert_cols = ", ".join(all_vals.keys())
    insert_params = ", ".join(f":{k}" for k in all_vals.keys())

    if is_mssql(conn):
        sql = f"""
            IF NOT EXISTS (SELECT 1 FROM {table_name} WHERE {where_clauses})
            BEGIN
                INSERT INTO {table_name} ({insert_cols}) VALUES ({insert_params})
            END
        """
    else:
        sql = f"""
            INSERT OR IGNORE INTO {table_name} ({insert_cols})
            SELECT {insert_params}
            WHERE NOT EXISTS (SELECT 1 FROM {table_name} WHERE {where_clauses})
        """

    try:
        conn.execute(text(sql), all_vals)
        conn.commit()
        return True
    except Exception as exc:
        log.warning("conditional_insert failed on %s: %s", table_name, exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def safe_execute(conn: Connection, sql: str, params: Optional[dict] = None) -> bool:
    """Execute a statement, silently ignoring errors (idempotent helper).

    Use for ALTER TABLE statements that may fail if the column already exists.
    """
    try:
        conn.execute(text(sql), params or {})
        conn.commit()
        return True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def select_top_1(conn: Connection, sql: str, params: Optional[dict] = None):
    """Execute a SELECT and return the first row — compatible across dialects.

    Replace ``LIMIT 1`` / ``TOP 1`` with this helper.
    """
    if is_mssql(conn):
        # Wrap in a subquery with TOP 1 if LIMIT is present (simple cases)
        fixed = sql.replace("LIMIT 1", "").strip().rstrip(";")
        # Insert TOP 1 after SELECT
        fixed = fixed.replace("SELECT ", "SELECT TOP 1 ", 1)
    else:
        fixed = sql if "LIMIT" in sql.upper() else sql + " LIMIT 1"

    return conn.execute(text(fixed), params or {}).fetchone()
