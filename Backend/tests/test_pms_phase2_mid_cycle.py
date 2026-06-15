from __future__ import annotations

from datetime import datetime, timedelta

from app.core.security import create_access_token
from app.models import AuditLog, Employee, Notification, Role
from app.models.pms import AssignedKPI, AssignedKRA, GoalAssignment, MidCycleReview
from app.models.pms_settings import PMSPhaseSettings
from app.services import pms_phase2_service as phase2_service


def _bearer(employee: Employee) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(employee.id)}"}


def _make_role(db_session, name: str) -> Role:
    role = db_session.query(Role).filter(Role.name == name).first()
    if role:
        return role
    role = Role(name=name)
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


def _make_employee(
    db_session,
    *,
    role_name: str,
    email: str,
    first_name: str,
    last_name: str = "User",
    manager_id: int | None = None,
) -> Employee:
    emp = Employee(
        email=email,
        first_name=first_name,
        last_name=last_name,
        role_id=_make_role(db_session, role_name).id,
        reporting_manager_id=manager_id,
        employment_status="active",
        is_deleted=False,
        is_activated=True,
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    return emp


def _seed_mid_cycle_setting(db_session, days: int = 5) -> PMSPhaseSettings:
    row = db_session.query(PMSPhaseSettings).filter(PMSPhaseSettings.phase_key == "mid_cycle").first()
    if row:
        row.default_days = days
    else:
        row = PMSPhaseSettings(phase_key="mid_cycle", label="Mid Cycle Review", default_days=days)
        db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _make_assignment(
    db_session,
    *,
    employee: Employee,
    manager: Employee,
    period: str,
    status: str = "goals_locked",
) -> GoalAssignment:
    assignment = GoalAssignment(
        employee_id=employee.id,
        manager_id=manager.id,
        period=period,
        status=status,
        created_by=manager.id,
    )
    db_session.add(assignment)
    db_session.flush()

    kra = AssignedKRA(
        assignment_id=assignment.id,
        title="Delivery",
        weightage=100.0,
        from_template=True,
    )
    db_session.add(kra)
    db_session.flush()

    db_session.add(
        AssignedKPI(
            kra_id=kra.id,
            title="Release commitments",
            weightage=100.0,
            from_template=True,
        )
    )
    db_session.commit()
    db_session.refresh(assignment)
    return assignment


def _mid_cycle_notifications(db_session) -> list[Notification]:
    return db_session.query(Notification).filter(
        Notification.reference_table == "pms_mid_cycle_reviews"
    ).all()


def _mid_cycle_audits(db_session) -> list[AuditLog]:
    return db_session.query(AuditLog).filter(
        AuditLog.target_table == "pms_mid_cycle_reviews"
    ).all()


def test_bulk_create_mid_cycle_creates_reviews_and_side_effects(client, db_session, monkeypatch):
    sent_emails: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        phase2_service.pms_email,
        "email_mid_cycle_created",
        lambda *args, **kwargs: sent_emails.append(("email_mid_cycle_created", kwargs)),
    )

    hr = _make_employee(db_session, role_name="hr", email="hr@test.com", first_name="Hira")
    manager = _make_employee(db_session, role_name="manager", email="manager@test.com", first_name="Manny")
    employee_one = _make_employee(
        db_session,
        role_name="employee",
        email="employee1@test.com",
        first_name="Esha",
        manager_id=manager.id,
    )
    employee_two = _make_employee(
        db_session,
        role_name="employee",
        email="employee2@test.com",
        first_name="Aadi",
        manager_id=manager.id,
    )
    _seed_mid_cycle_setting(db_session, days=5)
    assignment_one = _make_assignment(db_session, employee=employee_one, manager=manager, period="FY2026")
    assignment_two = _make_assignment(db_session, employee=employee_two, manager=manager, period="FY2026")

    before_call = datetime.utcnow()
    resp = client.post(
        "/pms/mid-cycle/bulk/create",
        json={
            "assignment_ids": [assignment_one.id, assignment_two.id],
            "cycle_period": "H1-2026",
            "allow_goal_modification": True,
        },
        headers=_bearer(hr),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success_count"] == 2
    assert body["failure_count"] == 0
    assert all(item["success"] for item in body["results"])

    reviews = db_session.query(MidCycleReview).order_by(MidCycleReview.id).all()
    assert len(reviews) == 2
    assert all(review.status == "draft" for review in reviews)
    assert all(review.allow_goal_modification is True for review in reviews)
    assert all(review.cycle_period == "H1-2026" for review in reviews)
    assert all(review.deadline is not None for review in reviews)
    assert all(review.deadline >= before_call + timedelta(days=4, hours=23) for review in reviews)
    assert all(review.deadline <= before_call + timedelta(days=5, hours=1) for review in reviews)

    notifications = _mid_cycle_notifications(db_session)
    assert len(notifications) == 2
    assert {n.type for n in notifications} == {"pms_mid_cycle_created"}
    assert {n.recipient_id for n in notifications} == {employee_one.id, employee_two.id}

    audits = _mid_cycle_audits(db_session)
    assert len(audits) == 2
    assert {a.action for a in audits} == {"pms.mid_cycle.create"}

    assert [name for name, _ in sent_emails] == [
        "email_mid_cycle_created",
        "email_mid_cycle_created",
    ]


def test_bulk_create_mid_cycle_returns_conflict_instead_of_500(client, db_session):
    hr = _make_employee(db_session, role_name="hr", email="hr@test.com", first_name="Hira")
    manager = _make_employee(db_session, role_name="manager", email="manager@test.com", first_name="Manny")
    employee = _make_employee(
        db_session,
        role_name="employee",
        email="employee@test.com",
        first_name="Esha",
        manager_id=manager.id,
    )
    _make_assignment(db_session, employee=employee, manager=manager, period="FY2026")

    resp = client.post(
        "/pms/mid-cycle/bulk/create",
        json={
            "assignment_ids": [1, 1],
            "cycle_period": "H1-2026",
        },
        headers=_bearer(hr),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success_count"] == 1
    assert body["failure_count"] == 1
    failed = [item for item in body["results"] if not item["success"]]
    assert len(failed) == 1
    assert "active mid-cycle review already exists" in failed[0]["reason"].lower()


def test_mid_cycle_workflow_single_create_rbac_notifications_audit_and_emails(client, db_session, monkeypatch):
    sent_emails: list[str] = []
    for fn_name in (
        "email_mid_cycle_created",
        "email_progress_submitted",
        "email_manager_reviewed_mid_cycle",
        "email_mid_cycle_manager_approved",
        "email_mid_cycle_hr_reviewed",
        "email_mid_cycle_locked",
    ):
        monkeypatch.setattr(
            phase2_service.pms_email,
            fn_name,
            lambda *args, _fn=fn_name, **kwargs: sent_emails.append(_fn),
        )

    hr = _make_employee(db_session, role_name="hr", email="hr@test.com", first_name="Hira")
    manager = _make_employee(db_session, role_name="manager", email="manager@test.com", first_name="Manny")
    employee = _make_employee(
        db_session,
        role_name="employee",
        email="employee@test.com",
        first_name="Esha",
        manager_id=manager.id,
    )
    _seed_mid_cycle_setting(db_session, days=7)
    assignment = _make_assignment(db_session, employee=employee, manager=manager, period="FY2026")
    kpi = db_session.query(AssignedKPI).join(AssignedKRA).filter(AssignedKRA.assignment_id == assignment.id).first()
    assert kpi is not None

    forbidden = client.post(
        "/pms/mid-cycle",
        json={"assignment_id": assignment.id, "cycle_period": "H1-2026"},
        headers=_bearer(employee),
    )
    assert forbidden.status_code == 403

    create_resp = client.post(
        "/pms/mid-cycle",
        json={"assignment_id": assignment.id, "cycle_period": "H1-2026"},
        headers=_bearer(hr),
    )
    assert create_resp.status_code == 201, create_resp.text
    review_id = create_resp.json()["id"]

    submit_resp = client.post(
        f"/pms/mid-cycle/{review_id}/submit",
        json={
            "employee_comments": "On track for the half-year goals.",
            "kpi_progress": [
                {
                    "assigned_kpi_id": kpi.id,
                    "current_value": "2 releases shipped",
                    "progress_percent": 55,
                    "employee_notes": "Major milestone completed",
                }
            ],
        },
        headers=_bearer(employee),
    )
    assert submit_resp.status_code == 200, submit_resp.text
    assert submit_resp.json()["status"] == "submitted"

    review_resp = client.post(
        f"/pms/mid-cycle/{review_id}/manager-review",
        json={
            "manager_comments": "Good progress so far.",
            "kpi_notes": [{"assigned_kpi_id": kpi.id, "manager_notes": "Keep the release quality steady"}],
        },
        headers=_bearer(manager),
    )
    assert review_resp.status_code == 200, review_resp.text
    assert review_resp.json()["status"] == "manager_reviewed"

    approve_resp = client.post(
        f"/pms/mid-cycle/{review_id}/manager-approve",
        json={"comment": "Approved from manager side."},
        headers=_bearer(manager),
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["status"] == "manager_approved"

    hr_review_resp = client.post(
        f"/pms/mid-cycle/{review_id}/hr-review",
        json={"comment": "HR reviewed."},
        headers=_bearer(hr),
    )
    assert hr_review_resp.status_code == 200, hr_review_resp.text
    assert hr_review_resp.json()["status"] == "hr_reviewed"

    employee_cannot_lock = client.post(
        f"/pms/mid-cycle/{review_id}/lock",
        json={"comment": "nope"},
        headers=_bearer(employee),
    )
    assert employee_cannot_lock.status_code == 403

    lock_resp = client.post(
        f"/pms/mid-cycle/{review_id}/lock",
        json={"comment": "Locking the review."},
        headers=_bearer(hr),
    )
    assert lock_resp.status_code == 200, lock_resp.text
    locked_body = lock_resp.json()
    assert locked_body["status"] == "mid_cycle_locked"
    assert locked_body["manager_comments"] == "Approved from manager side."
    assert locked_body["hr_comments"] == "Locking the review."

    review_row = db_session.get(MidCycleReview, review_id)
    assert review_row is not None
    assert review_row.deadline is not None
    assert review_row.manager_reviewed_by == manager.id
    assert review_row.manager_approved_by == manager.id
    assert review_row.hr_reviewed_by == hr.id
    assert review_row.locked_by == hr.id

    notification_types = [n.type for n in _mid_cycle_notifications(db_session)]
    assert notification_types.count("pms_mid_cycle_created") == 1
    assert notification_types.count("pms_progress_submitted") == 1
    assert notification_types.count("pms_manager_reviewed_progress") == 1
    assert notification_types.count("pms_mid_cycle_manager_approved") == 2
    assert notification_types.count("pms_mid_cycle_hr_reviewed") == 1
    assert notification_types.count("pms_mid_cycle_locked") == 2

    audit_actions = [a.action for a in _mid_cycle_audits(db_session)]
    assert audit_actions == [
        "pms.mid_cycle.create",
        "pms.mid_cycle.submit",
        "pms.mid_cycle.manager_review",
        "pms.mid_cycle.manager_approve",
        "pms.mid_cycle.hr_review",
        "pms.mid_cycle.lock",
    ]

    assert sent_emails == [
        "email_mid_cycle_created",
        "email_progress_submitted",
        "email_manager_reviewed_mid_cycle",
        "email_mid_cycle_manager_approved",
        "email_mid_cycle_hr_reviewed",
        "email_mid_cycle_locked",
    ]
