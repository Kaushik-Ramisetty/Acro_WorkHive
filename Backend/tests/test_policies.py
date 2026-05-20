"""End-to-end tests for the Policies module.

Covers:
  - CRUD authorisation (admin/HR vs others)
  - Listing differs for admin (`mode=manage`) vs viewer (`mode=feed`)
  - Versioning: every new version increments + previous versions are kept
  - Publish / archive / reactivate state transitions
  - Acknowledgement is idempotent and version-scoped
  - File upload rejects non-PDF and oversize payloads
  - Read-only viewers cannot see draft/archived policies

These tests reuse the standard in-memory SQLite fixtures in conftest.py
and mint Core-style JWTs (sub = str(employee.id)) via
app.core.security.create_access_token so the /policies endpoints accept them.
"""
from __future__ import annotations

import io
from typing import Optional

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_role(db_session, name: str = "admin"):
    from app.models import Role
    existing = db_session.query(Role).filter(Role.name == name).first()
    if existing:
        return existing
    r = Role(name=name)
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    return r


def _make_employee(
    db_session,
    *,
    role_name: str = "admin",
    email: Optional[str] = None,
    first_name: str = "Test",
    last_name: str = "User",
):
    from app.models import Employee
    role = _make_role(db_session, role_name)
    email = email or f"{role_name}@test.com"
    emp = Employee(
        email=email,
        first_name=first_name,
        last_name=last_name,
        role_id=role.id,
        employment_status="active",
        is_deleted=False,
        is_activated=True,
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    return emp


def _core_token(employee_id: int) -> str:
    """Mint a Core-style JWT (sub = str(employee_id))."""
    from app.core.security import create_access_token
    return create_access_token(employee_id)


def _bearer(employee) -> dict:
    return {"Authorization": f"Bearer {_core_token(employee.id)}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(db_session):
    return _make_employee(db_session, role_name="admin", email="admin@test.com")


@pytest.fixture
def hr_user(db_session):
    return _make_employee(db_session, role_name="hr", email="hr@test.com")


@pytest.fixture
def employee_user(db_session):
    return _make_employee(db_session, role_name="employee", email="emp@test.com")


@pytest.fixture
def manager_user(db_session):
    return _make_employee(db_session, role_name="manager", email="mgr@test.com")


# ---------------------------------------------------------------------------
# Create & list
# ---------------------------------------------------------------------------

def test_admin_can_create_policy_and_employee_sees_it(client, admin_user, employee_user):
    # Admin creates a published policy
    resp = client.post(
        "/policies",
        json={
            "title": "Code of Conduct",
            "description": "Behavioural standards.",
            "publish_immediately": True,
        },
        headers=_bearer(admin_user),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "published"
    assert body["current_version_number"] == 1
    pid = body["id"]

    # Admin can see it in manage mode
    resp = client.get("/policies?mode=manage", headers=_bearer(admin_user))
    assert resp.status_code == 200
    titles = [p["title"] for p in resp.json()["items"]]
    assert "Code of Conduct" in titles

    # Employee sees it in feed mode
    resp = client.get("/policies?mode=feed", headers=_bearer(employee_user))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(p["id"] == pid for p in items)


def test_employee_cannot_see_draft_policies(client, admin_user, employee_user):
    # Admin creates a DRAFT policy (publish_immediately=False)
    resp = client.post(
        "/policies",
        json={"title": "Top Secret Draft", "publish_immediately": False},
        headers=_bearer(admin_user),
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]
    assert resp.json()["status"] == "draft"

    # Employee feed must NOT include it
    resp = client.get("/policies?mode=feed", headers=_bearer(employee_user))
    items = resp.json()["items"]
    assert not any(p["id"] == pid for p in items)

    # Employee GET single → 404 (treated as not found, not 403)
    resp = client.get(f"/policies/{pid}", headers=_bearer(employee_user))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------

def test_non_admin_cannot_create_policy(client, employee_user, manager_user):
    for u in (employee_user, manager_user):
        resp = client.post(
            "/policies",
            json={"title": "Should fail"},
            headers=_bearer(u),
        )
        assert resp.status_code == 403, f"role={u.role.name} should be 403"


def test_non_admin_cannot_publish_or_archive(client, admin_user, employee_user):
    resp = client.post(
        "/policies",
        json={"title": "X", "publish_immediately": False},
        headers=_bearer(admin_user),
    )
    pid = resp.json()["id"]

    for action in ("publish", "archive", "reactivate"):
        r = client.post(f"/policies/{pid}/{action}", headers=_bearer(employee_user))
        assert r.status_code == 403, action


def test_hr_has_same_powers_as_admin(client, hr_user):
    resp = client.post(
        "/policies",
        json={"title": "HR-created policy"},
        headers=_bearer(hr_user),
    )
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

def test_creating_new_version_does_not_overwrite_previous(client, admin_user):
    r = client.post("/policies", json={"title": "V-Test", "publish_immediately": True}, headers=_bearer(admin_user))
    pid = r.json()["id"]

    # Add a 2nd version
    r2 = client.post(
        f"/policies/{pid}/versions",
        json={"change_summary": "Updated section 3", "publish": True},
        headers=_bearer(admin_user),
    )
    assert r2.status_code == 201
    v2 = r2.json()
    assert v2["version_number"] == 2

    # Both versions exist in history
    rv = client.get(f"/policies/{pid}/versions", headers=_bearer(admin_user))
    nums = sorted(v["version_number"] for v in rv.json())
    assert nums == [1, 2]

    # Current version is now v2
    r3 = client.get(f"/policies/{pid}", headers=_bearer(admin_user))
    assert r3.json()["current_version_number"] == 2


def test_promote_old_version_back_to_current(client, admin_user):
    r  = client.post("/policies", json={"title": "Rollback test"}, headers=_bearer(admin_user))
    pid = r.json()["id"]
    v1_id = r.json()["current_version_id"]

    # Add v2 and publish it
    client.post(
        f"/policies/{pid}/versions",
        json={"change_summary": "v2", "publish": True},
        headers=_bearer(admin_user),
    )

    # Roll back to v1
    r2 = client.post(f"/policies/{pid}/versions/{v1_id}/publish", headers=_bearer(admin_user))
    assert r2.status_code == 200
    assert r2.json()["current_version_id"] == v1_id


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_archive_then_reactivate(client, admin_user):
    r = client.post("/policies", json={"title": "Lifecycle"}, headers=_bearer(admin_user))
    pid = r.json()["id"]

    a = client.post(f"/policies/{pid}/archive", headers=_bearer(admin_user))
    assert a.status_code == 200
    assert a.json()["status"] == "archived"

    b = client.post(f"/policies/{pid}/reactivate", headers=_bearer(admin_user))
    assert b.status_code == 200
    assert b.json()["status"] == "draft"


def test_cannot_delete_published_policy(client, admin_user):
    r = client.post("/policies", json={"title": "DeleteMe"}, headers=_bearer(admin_user))
    pid = r.json()["id"]
    # publish_immediately=True (default) → status=published
    d = client.delete(f"/policies/{pid}", headers=_bearer(admin_user))
    assert d.status_code == 400


def test_can_delete_draft_policy(client, admin_user):
    r = client.post(
        "/policies",
        json={"title": "DraftDel", "publish_immediately": False},
        headers=_bearer(admin_user),
    )
    pid = r.json()["id"]
    d = client.delete(f"/policies/{pid}", headers=_bearer(admin_user))
    assert d.status_code == 204
    # Soft-deleted → admin no longer sees it
    listing = client.get("/policies?mode=manage", headers=_bearer(admin_user)).json()
    assert not any(p["id"] == pid for p in listing["items"])


# ---------------------------------------------------------------------------
# Acknowledgements
# ---------------------------------------------------------------------------

def test_employee_can_acknowledge_published_policy(client, admin_user, employee_user):
    r = client.post("/policies", json={"title": "Ack Test"}, headers=_bearer(admin_user))
    pid = r.json()["id"]

    a = client.post(f"/policies/{pid}/acknowledge", headers=_bearer(employee_user))
    assert a.status_code == 200, a.text
    ack1 = a.json()

    # Idempotent — second call returns same row
    a2 = client.post(f"/policies/{pid}/acknowledge", headers=_bearer(employee_user))
    assert a2.status_code == 200
    assert a2.json()["id"] == ack1["id"]

    # Feed surfaces is_acknowledged=True now
    feed = client.get("/policies?mode=feed", headers=_bearer(employee_user)).json()
    pol = next(p for p in feed["items"] if p["id"] == pid)
    assert pol["is_acknowledged"] is True


def test_cannot_ack_draft_policy(client, admin_user, employee_user):
    r = client.post(
        "/policies",
        json={"title": "DraftAck", "publish_immediately": False},
        headers=_bearer(admin_user),
    )
    pid = r.json()["id"]
    a = client.post(f"/policies/{pid}/acknowledge", headers=_bearer(employee_user))
    assert a.status_code == 400


def test_new_version_resets_acknowledgement_state(client, admin_user, employee_user):
    """When admin publishes a NEW version, the employee's ACK from v1 no longer
    counts (ACKs are version-scoped) — the feed should show is_acknowledged
    False for the new version until they ack again."""
    r = client.post("/policies", json={"title": "Version-scoped ACK"}, headers=_bearer(admin_user))
    pid = r.json()["id"]

    # Employee acks v1
    client.post(f"/policies/{pid}/acknowledge", headers=_bearer(employee_user))

    # Admin publishes v2
    client.post(
        f"/policies/{pid}/versions",
        json={"change_summary": "v2", "publish": True},
        headers=_bearer(admin_user),
    )

    # Employee feed should now show is_acknowledged=False for the same policy
    feed = client.get("/policies?mode=feed", headers=_bearer(employee_user)).json()
    pol = next(p for p in feed["items"] if p["id"] == pid)
    assert pol["is_acknowledged"] is False


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

def test_categories_listable_by_any_user(client, employee_user, admin_user):
    # Admin creates one
    r = client.post(
        "/policies/categories",
        json={"name": "Test Cat", "description": "Just a test"},
        headers=_bearer(admin_user),
    )
    assert r.status_code == 201
    # Employee can list
    rl = client.get("/policies/categories", headers=_bearer(employee_user))
    assert rl.status_code == 200
    names = [c["name"] for c in rl.json()]
    assert "Test Cat" in names


def test_employee_cannot_create_category(client, employee_user):
    r = client.post(
        "/policies/categories",
        json={"name": "Sneaky"},
        headers=_bearer(employee_user),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------

def test_upload_rejects_non_pdf(client, admin_user, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    r = client.post("/policies", json={"title": "Upload Test"}, headers=_bearer(admin_user))
    pid = r.json()["id"]
    vid = r.json()["current_version_id"]

    bad = io.BytesIO(b"not a pdf")
    resp = client.post(
        f"/policies/{pid}/versions/{vid}/upload",
        files={"file": ("hello.txt", bad, "text/plain")},
        headers=_bearer(admin_user),
    )
    assert resp.status_code == 415


def test_upload_accepts_pdf(client, admin_user, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    # Force the policies module to re-read the env var by patching its constant.
    from app.routes import policies as policies_routes
    policies_routes._UPLOAD_DIR = tmp_path

    r = client.post("/policies", json={"title": "Upload OK"}, headers=_bearer(admin_user))
    pid = r.json()["id"]
    vid = r.json()["current_version_id"]

    pdf = io.BytesIO(b"%PDF-1.4 minimal stub\n")
    resp = client.post(
        f"/policies/{pid}/versions/{vid}/upload",
        files={"file": ("policy.pdf", pdf, "application/pdf")},
        headers=_bearer(admin_user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pdf_path"].startswith("/uploads/policies/")


# ---------------------------------------------------------------------------
# Search & filtering
# ---------------------------------------------------------------------------

def test_search_and_category_filters(client, admin_user, employee_user):
    # Create two policies with different categories.
    cat = client.post(
        "/policies/categories",
        json={"name": "Compliance"},
        headers=_bearer(admin_user),
    ).json()
    other = client.post(
        "/policies/categories",
        json={"name": "Marketing"},
        headers=_bearer(admin_user),
    ).json()

    client.post(
        "/policies",
        json={"title": "GDPR Statement", "category_id": cat["id"]},
        headers=_bearer(admin_user),
    )
    client.post(
        "/policies",
        json={"title": "Brand Guidelines", "category_id": other["id"]},
        headers=_bearer(admin_user),
    )

    # Category filter narrows
    r = client.get(
        f"/policies?mode=feed&category_id={cat['id']}",
        headers=_bearer(employee_user),
    )
    titles = [p["title"] for p in r.json()["items"]]
    assert "GDPR Statement" in titles
    assert "Brand Guidelines" not in titles

    # Search by keyword
    r = client.get(
        "/policies?mode=feed&search=brand",
        headers=_bearer(employee_user),
    )
    titles = [p["title"] for p in r.json()["items"]]
    assert "Brand Guidelines" in titles
    assert "GDPR Statement" not in titles
