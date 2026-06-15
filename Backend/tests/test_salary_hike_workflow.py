from datetime import date

from app.core.security import create_access_token
from app.models.employee import Employee
from app.models.payroll import SalaryStructure
from app.models.role import Role
from app.models.salary_hike_request import SalaryHikeRequest


def _headers(employee: Employee) -> dict[str, str]:
    token = create_access_token(employee.id)
    return {"Authorization": f"Bearer {token}"}


def _seed_roles(db_session) -> dict[str, Role]:
    # IDs match the target role mapping: admin=1, manager=2, employee=3, finance=4, finance_head=5
    # "hr" is a test-only role; id=6 avoids conflicts with the 5 production roles.
    roles = {
        "hr": Role(id=6, name="hr"),
        "finance": Role(id=4, name="finance"),
        "finance_head": Role(id=5, name="finance_head"),
    }
    db_session.add_all(roles.values())
    db_session.commit()
    return roles


def _employee(db_session, role: Role, code: str, email: str) -> Employee:
    emp = Employee(
        employee_code=code,
        first_name=code,
        last_name="User",
        email=email,
        official_email=email,
        employment_status="active",
        is_deleted=False,
        is_activated=True,
        role_id=role.id,
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    return emp


def _active_structure(
    db_session,
    employee_id: int,
    annual_ctc: float = 600000.0,
    effective_from: date = date(2026, 1, 1),
) -> SalaryStructure:
    struct = SalaryStructure(
        employee_id=employee_id,
        basic=25000,
        hra=10000,
        special_allowance=15000,
        gross_monthly=50000,
        total_deductions=0,
        net_monthly=50000,
        annual_ctc=annual_ctc,
        effective_from=effective_from,
        is_active=True,
    )
    db_session.add(struct)
    db_session.commit()
    db_session.refresh(struct)
    return struct


def _seed_workflow_people(db_session):
    roles = _seed_roles(db_session)
    hr = _employee(db_session, roles["hr"], "HR001", "hr@test.local")
    finance = _employee(db_session, roles["finance"], "FIN001", "finance@test.local")
    head = _employee(db_session, roles["finance_head"], "HEAD001", "head@test.local")
    target = _employee(db_session, roles["hr"], "EMP001", "employee@test.local")
    return hr, finance, head, target


def test_finance_review_forwards_without_applying_salary_revision(client, db_session):
    hr, finance, _, target = _seed_workflow_people(db_session)
    _active_structure(db_session, target.id)

    created = client.post(
        "/finance/hike-requests",
        json={
            "employee_id": target.id,
            "hike_type": "percentage",
            "hike_value": 20,
            "effective_from": "2026-04-01",
            "reason": "Annual appraisal",
        },
        headers=_headers(hr),
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    reviewed = client.post(
        f"/finance/hike-requests/{request_id}/approve",
        json={"comment": "Reviewed by Finance"},
        headers=_headers(finance),
    )
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["status"] == "pending_finance_head_approval"
    assert body["reviewed_by_id"] == finance.id
    assert body["approved_by_id"] is None
    assert body["approved_at"] is None

    db_session.expire_all()
    req = db_session.get(SalaryHikeRequest, request_id)
    assert req.status == "pending_finance_head_approval"
    assert req.reviewed_by_id == finance.id
    assert req.approved_by_id is None
    assert db_session.query(SalaryStructure).filter_by(employee_id=target.id).count() == 1
    assert (
        db_session.query(SalaryStructure)
        .filter_by(employee_id=target.id, is_active=True)
        .one()
        .annual_ctc
        == 600000.0
    )


def test_only_finance_head_can_final_approve_and_apply_salary_revision(client, db_session):
    hr, finance, head, target = _seed_workflow_people(db_session)
    _active_structure(db_session, target.id)

    req = SalaryHikeRequest(
        employee_id=target.id,
        old_ctc=600000,
        new_ctc=720000,
        hike_type="percentage",
        hike_value=20,
        effective_from=date(2026, 4, 1),
        reason="Annual appraisal",
        status="pending_finance_head_approval",
        requested_by_id=hr.id,
        reviewed_by_id=finance.id,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    finance_attempt = client.post(
        f"/finance/hike-requests/{req.id}/head-approve",
        json={"comment": "Trying final approval"},
        headers=_headers(finance),
    )
    assert finance_attempt.status_code == 403, finance_attempt.text

    db_session.expire_all()
    assert db_session.get(SalaryHikeRequest, req.id).status == "pending_finance_head_approval"
    assert db_session.query(SalaryStructure).filter_by(employee_id=target.id).count() == 1

    head_approval = client.post(
        f"/finance/hike-requests/{req.id}/head-approve",
        json={"comment": "Final approval"},
        headers=_headers(head),
    )
    assert head_approval.status_code == 200, head_approval.text
    assert head_approval.json()["status"] == "approved"

    db_session.expire_all()
    approved_req = db_session.get(SalaryHikeRequest, req.id)
    assert approved_req.approved_by_id == head.id
    assert approved_req.approved_at is not None

    structures = db_session.query(SalaryStructure).filter_by(employee_id=target.id).all()
    assert len(structures) == 2
    active = (
        db_session.query(SalaryStructure)
        .filter_by(employee_id=target.id, is_active=True)
        .one()
    )
    assert active.annual_ctc == 720000.0
    assert active.effective_from == date(2026, 4, 1)


def test_direct_salary_revision_write_endpoints_are_blocked(client, db_session):
    _, finance, _, target = _seed_workflow_people(db_session)
    _active_structure(db_session, target.id)

    payload = {
        "employee_id": target.id,
        "new_ctc_annual": 720000,
        "effective_from": "2026-04-01",
        "revision_reason": "Direct write should be blocked",
    }

    for path in ("/finance/salary-revisions", "/payroll/salary-revisions"):
        res = client.post(path, json=payload, headers=_headers(finance))
        assert res.status_code == 403, res.text
        assert "Finance Head approval workflow" in res.json()["detail"]

    assert db_session.query(SalaryStructure).filter_by(employee_id=target.id).count() == 1


def test_salary_structure_write_blocks_existing_revision_but_allows_initial_setup(client, db_session):
    _, finance, _, target = _seed_workflow_people(db_session)

    initial = client.post(
        "/finance/salary-structures/from-ctc",
        json={
            "employee_id": target.id,
            "annual_ctc": 600000,
            "effective_from": "2026-01-01",
        },
        headers=_headers(finance),
    )
    assert initial.status_code == 200, initial.text

    revision = client.post(
        "/finance/salary-structures/from-ctc",
        json={
            "employee_id": target.id,
            "annual_ctc": 720000,
            "effective_from": "2026-04-01",
            "revision_reason": "Annual appraisal",
        },
        headers=_headers(finance),
    )
    assert revision.status_code == 403, revision.text
    assert "Finance Head approval workflow" in revision.json()["detail"]

    db_session.expire_all()
    structures = db_session.query(SalaryStructure).filter_by(employee_id=target.id).all()
    assert len(structures) == 1
    assert structures[0].annual_ctc == 600000.0
