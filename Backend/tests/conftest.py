"""
tests/conftest.py — Pytest fixtures for the WorkHive HRMS backend.

Strategy
--------
Each test gets a fresh in-memory SQLite database. We override the FastAPI
`get_db` dependency to point at this transient session, so tests don't
collide with the developer's local `workhive.db` file or with each other.

A `client` fixture returns a configured `TestClient` and exposes an
`auth_headers(role=...)` helper for issuing JWT bearers without going
through `/api/v1/auth/login` end-to-end (we exercise that flow separately
in test_auth).
"""

from __future__ import annotations

import os

# Force a clean test environment BEFORE importing the app — env vars are read
# at module load time. Setting these here makes test runs deterministic
# regardless of what's in the developer's .env.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("EMAIL_SIMULATE", "true")
os.environ.setdefault("DB_ENGINE", "sqlite")
os.environ.setdefault("SQLITE_PATH", ":memory:")
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("SECRET_KEY", "test-secret-must-be-at-least-16-chars-long")
# Fernet test key — generated once for the suite. NOT used in production.
os.environ.setdefault("PII_ENCRYPTION_KEY", "Pp7zQOu8u-IH-y7R5Rf3DZd18sFU3DYmIsT0Fw3uP3I=")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Import after env is set up so the app picks up our test config.
from main import app  # noqa: E402
from database import Base, get_db  # noqa: E402
from utils.jwt_auth import create_access_token  # noqa: E402


@pytest.fixture(scope="function")
def db_engine():
    """A fresh in-memory SQLite engine per test, with all tables created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """A SQLAlchemy session bound to the in-memory engine."""
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_engine):
    """
    A FastAPI TestClient with `get_db` overridden to use the test engine.

    Also exposes:
      client.auth_headers(role="admin", sub="admin@test.com", **claims)
        -> dict with `Authorization: Bearer <jwt>` for that role.
    """
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db

    test_client = TestClient(app)

    def _auth_headers(role: str = "admin", sub: str | None = None, **claims):
        token = create_access_token(
            sub=sub or f"{role}@test.com",
            role=role,
            **claims,
        )
        return {"Authorization": f"Bearer {token}"}

    test_client.auth_headers = _auth_headers   # type: ignore[attr-defined]
    yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def seeded_master_data(db_session):
    """Seed minimal Department + Designation rows for conversion tests."""
    from api.models import Department, Designation

    dept = Department(id="DEP001", name="Engineering")
    desig = Designation(id="D1", title="Software Engineer", level=3)
    db_session.add_all([dept, desig])
    db_session.commit()
    return {"department": dept, "designation": desig}


@pytest.fixture
def seeded_leave_types(db_session):
    """Seed the leave-type master data so conversion creates leave balances."""
    from api.models import LeaveType

    rows = [
        LeaveType(id="LT001", name="Sick Leave",       annual_quota=12, carry_forward_limit=0,  is_paid=True,  applicable_gender="all"),
        LeaveType(id="LT002", name="Casual Leave",     annual_quota=12, carry_forward_limit=0,  is_paid=True,  applicable_gender="all"),
        LeaveType(id="LT005", name="Earned Leave",     annual_quota=12, carry_forward_limit=12, is_paid=True,  applicable_gender="all"),
    ]
    db_session.add_all(rows)
    db_session.commit()
    return rows


@pytest.fixture
def candidate_factory(db_session):
    """Factory: produces a Candidate row in the requested status."""
    from api.models import Candidate, CandidateStatus
    counter = {"n": 0}

    def _make(
        status: str = CandidateStatus.OFFER_ACCEPTED.value,
        email: str | None = None,
        name: str = "Test Candidate",
    ):
        counter["n"] += 1
        n = counter["n"]
        c = Candidate(
            candidate_ref=f"CAND-T{n:03d}",
            first_name=name.split()[0],
            last_name=" ".join(name.split()[1:]) or "User",
            name=name,
            email=email or f"cand{n}@test.com",
            role="Software Engineer",
            status=status,
            is_offer_accepted=status != "CREATED",
        )
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)
        return c

    return _make
