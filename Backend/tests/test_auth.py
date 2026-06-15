"""tests/test_auth.py — JWT issuance, login, change-password, role guards."""

from datetime import date
import bcrypt as _bcrypt


def _hash(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def test_login_employee_via_official_email(client, db_session):
    """Employee logs in with their official_email + password. Receives a JWT."""
    from api.models import Department, Designation, Employee

    db_session.add_all([
        Department(id="DEP001", name="HR"),
        Designation(id="D1", title="Delivery Head", level=10),
    ])
    db_session.flush()

    emp = Employee(
        employee_code="EMP0001",
        first_name="Alex", last_name="Tester",
        email="alex@candidate.com",
        official_email="alex@workhive.com",
        date_of_joining=date(2025, 1, 1),
        department_id="DEP001",
        designation_id="D1",
        employment_status="active",
        Password=_hash("p@ssword123"),
        is_activated=True,
        force_password_change=False,
        is_deleted=False,
    )
    db_session.add(emp)
    db_session.commit()

    res = client.post("/api/v1/auth/login", json={
        "email": "alex@workhive.com",
        "password": "p@ssword123",
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["role"] == "employee"
    assert data["email"] == "alex@workhive.com"
    assert data["access_token"]
    assert data["token_type"] == "bearer"


def test_login_rejects_inactive_employee(client, db_session):
    """An employee with is_activated=False can't log in."""
    from api.models import Department, Designation, Employee

    db_session.add_all([
        Department(id="DEP001", name="HR"),
        Designation(id="D1", title="Delivery Head", level=10),
    ])
    db_session.flush()
    db_session.add(Employee(
        employee_code="EMP9999", first_name="Pre", last_name="Active",
        email="pre@candidate.com", date_of_joining=date(2025, 1, 1),
        department_id="DEP001", designation_id="D1",
        employment_status="active",
        Password=_hash("p@ssword123"), is_activated=False,
        is_deleted=False,
    ))
    db_session.commit()

    res = client.post("/api/v1/auth/login", json={
        "email": "pre@candidate.com",
        "password": "p@ssword123",
    })
    assert res.status_code == 403


def test_login_wrong_password(client, db_session):
    """Bad credentials → 401."""
    res = client.post("/api/v1/auth/login", json={
        "email": "ghost@nowhere.com",
        "password": "wrong",
    })
    assert res.status_code == 401


def test_protected_route_without_token_401(client):
    """A protected route returns 401 when called without Authorization."""
    res = client.get("/employees/")
    assert res.status_code == 401


def test_protected_route_with_wrong_role_403(client):
    headers = client.auth_headers(role="candidate", sub="cand@test.com", candidate_id=42)
    res = client.get("/employees/", headers=headers)
    assert res.status_code == 403


def test_protected_route_with_admin_role_200(client):
    headers = client.auth_headers(role="admin")
    res = client.get("/employees/", headers=headers)
    assert res.status_code == 200
    assert res.json() == []


def test_change_password_happy_path(client, db_session):
    from api.models import Department, Designation, Employee

    db_session.add_all([
        Department(id="DEP001", name="HR"),
        Designation(id="D1", title="Delivery Head", level=10),
    ])
    db_session.flush()
    emp = Employee(
        employee_code="EMP0010",
        first_name="Bob", last_name="Pwd",
        email="bob@candidate.com",
        official_email="bob@workhive.com",
        date_of_joining=date(2025, 1, 1),
        department_id="DEP001", designation_id="D1",
        employment_status="active",
        Password=_hash("temp1234"),
        is_activated=True, force_password_change=True,
        is_deleted=False,
    )
    db_session.add(emp); db_session.commit()

    headers = client.auth_headers(role="employee", sub="bob@workhive.com",
                                  employee_id=emp.id, employee_code="EMP0010")
    res = client.post("/api/v1/auth/change-password",
                      json={
                          "official_email": "bob@workhive.com",
                          "current_password": "temp1234",
                          "new_password": "NewStrongPwd!9",
                      },
                      headers=headers)
    assert res.status_code == 200, res.text
    db_session.refresh(emp)
    assert emp.force_password_change is False
