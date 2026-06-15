from datetime import date, datetime

from app.core.security import create_access_token
from app.models.department import Department
from app.models.employee import Employee
from app.models.monthly_attendance_summary import MonthlyAttendanceSummary
from app.models.notification import Notification
from app.models.payroll import PayrollApproval, PayrollError, PayrollRun, PayrollRunEmployee, SalaryStructure
from app.models.payroll_extended import Payslip
from app.models.role import Role
from app.services import payroll_service


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
        "admin": Role(id=1, name="admin"),
    }
    db_session.add_all(roles.values())
    db_session.commit()
    return roles


def _employee(
    db_session,
    role: Role,
    code: str,
    email: str,
    *,
    department_id: str | None = None,
) -> Employee:
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
        department_id=department_id,
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    return emp


def _seed_people(db_session):
    roles = _seed_roles(db_session)
    dept = Department(id="DEP001", name="HR")
    db_session.add(dept)
    db_session.commit()
    hr = _employee(db_session, roles["hr"], "HR001", "hr-payroll@test.local")
    finance = _employee(db_session, roles["finance"], "FIN001", "finance-payroll@test.local")
    head = _employee(db_session, roles["finance_head"], "HEAD001", "head-payroll@test.local")
    employee = _employee(
        db_session,
        roles["hr"],
        "EMP001",
        "employee-payroll@test.local",
        department_id=dept.id,
    )
    return hr, finance, head, employee


def _payroll_run(db_session, employee: Employee, *, status: str = "under_review") -> PayrollRun:
    run = PayrollRun(
        pay_period_start=date(2026, 4, 1),
        pay_period_end=date(2026, 4, 30),
        month_label="April 2026",
        month=4,
        year=2026,
        status=status,
        total_employees=1,
        total_gross=50000,
        total_deductions=8200,
        total_net=41800,
        total_pf=3600,
        total_esi=0,
        total_tds=5000,
        total_pt=200,
        attendance_locked=True,
        payroll_locked=False,
        processed_at=datetime.utcnow(),
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    row = PayrollRunEmployee(
        run_id=run.id,
        employee_id=employee.id,
        total_working_days=30,
        working_days=30,
        payable_days=28,
        present_days=28,
        leave_days=0,
        lop_days=2,
        gross_earnings=50000,
        basic_pay=25000,
        hra=10000,
        special_allowance=15000,
        employee_pf=1800,
        employer_pf=1800,
        employee_esi=0,
        employer_esi=0,
        professional_tax=200,
        tds=5000,
        lop_deduction=2500,
        other_deductions=400,
        total_deductions=8200,
        net_pay=41800,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(run)
    return run


def test_create_payroll_run_defaults_variance_threshold(db_session):
    _, finance, _, _ = _seed_people(db_session)

    run = payroll_service.create_payroll_run(
        db_session,
        {
            "pay_period_start": date(2026, 6, 1),
            "pay_period_end": date(2026, 6, 30),
            "notes": "Regression test",
        },
        finance,
    )

    assert run.id is not None
    assert run.variance_threshold_pct == 20.0
    assert run.status == "draft"


def _salary_structure(db_session, employee: Employee) -> SalaryStructure:
    structure = SalaryStructure(
        employee_id=employee.id,
        basic=25000,
        hra=10000,
        special_allowance=15000,
        gross_monthly=50000,
        total_deductions=8200,
        net_monthly=41800,
        annual_ctc=600000,
        bank_name="Test Bank",
        account_number="1234567890",
        ifsc_code="TEST0001234",
        effective_from=date(2026, 4, 1),
        is_active=True,
    )
    db_session.add(structure)
    db_session.commit()
    db_session.refresh(structure)
    return structure


def _finance_review_approval(db_session, run: PayrollRun, finance: Employee) -> None:
    db_session.add(
        PayrollApproval(
            run_id=run.id,
            actor_id=finance.id,
            approver_id=finance.id,
            action="finance_review",
            approval_level="FINANCE_REVIEW",
            approval_status="APPROVED",
            comments="Finance reviewed",
            remarks="Finance reviewed",
            approved_at=datetime.utcnow(),
        )
    )
    db_session.commit()


def test_finance_head_reviews_details_then_final_approves_and_unlocks_payslips(client, db_session):
    _, finance, head, employee = _seed_people(db_session)
    run = _payroll_run(db_session, employee)

    finance_review = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "approve", "remarks": "Finance review complete"},
        headers=_headers(finance),
    )
    assert finance_review.status_code == 200, finance_review.text
    assert finance_review.json()["status"] == "pending_head_approval"

    details = client.get(f"/finance/runs/{run.id}", headers=_headers(head))
    assert details.status_code == 200, details.text
    summary = details.json()
    assert summary["month_label"] == "April 2026"
    assert summary["finance_reviewed"] is True
    assert summary["open_errors"] == 0

    employees = client.get(f"/finance/runs/{run.id}/employees", headers=_headers(head))
    assert employees.status_code == 200, employees.text
    row = employees.json()[0]
    assert row["employee_code"] == "EMP001"
    assert row["employee_name"] == "EMP001 User"
    assert row["department"] == "HR"
    assert row["lop_days"] == 2
    assert row["gross_earnings"] == 50000
    assert row["lop_deduction"] == 2500
    assert row["employee_pf"] == 1800
    assert row["professional_tax"] == 200
    assert row["tds"] == 5000
    assert row["total_deductions"] == 8200
    assert row["net_pay"] == 41800

    final_approval = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "head_approve", "remarks": "Final approval"},
        headers=_headers(head),
    )
    assert final_approval.status_code == 200, final_approval.text
    approved = final_approval.json()
    assert approved["status"] == "approved"
    assert approved["lifecycle_status"] == "FINAL_APPROVED"
    assert approved["payroll_locked"] is True
    assert approved["payslip_generation_unlocked"] is True

    db_session.expire_all()
    locked_run = db_session.get(PayrollRun, run.id)
    assert locked_run.payroll_locked is True
    assert locked_run.status == "approved"
    assert db_session.query(PayrollRunEmployee).filter_by(run_id=run.id, is_locked=True).count() == 1

    payslips = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "generate_payslips", "remarks": "Generate after final approval"},
        headers=_headers(finance),
    )
    assert payslips.status_code == 200, payslips.text
    assert payslips.json()["status"] == "payslip_generated"


def test_final_approval_requires_finance_review_and_zero_open_errors(client, db_session):
    _, finance, head, employee = _seed_people(db_session)
    run = _payroll_run(db_session, employee, status="pending_head_approval")

    missing_review = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "head_approve", "remarks": "No finance review"},
        headers=_headers(head),
    )
    assert missing_review.status_code == 400, missing_review.text
    assert "Finance review must be completed" in missing_review.json()["detail"]

    _finance_review_approval(db_session, run, finance)
    db_session.add(
        PayrollError(
            run_id=run.id,
            employee_id=employee.id,
            error_type="lop_mismatch",
            description="Open LOP issue",
            severity="error",
            is_resolved=False,
        )
    )
    db_session.commit()

    open_error = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "head_approve", "remarks": "Has open errors"},
        headers=_headers(head),
    )
    assert open_error.status_code == 400, open_error.text
    assert "unresolved error" in open_error.json()["detail"]


def test_finance_cannot_final_approve_and_finance_head_cannot_mutate_payroll(client, db_session):
    _, finance, head, employee = _seed_people(db_session)
    admin = _employee(
        db_session,
        db_session.query(Role).filter_by(name="admin").one(),
        "ADMIN001",
        "admin-payroll@test.local",
    )
    run = _payroll_run(db_session, employee, status="pending_head_approval")
    _finance_review_approval(db_session, run, finance)

    finance_attempt = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "head_approve", "remarks": "Finance tries final approval"},
        headers=_headers(finance),
    )
    assert finance_attempt.status_code == 403, finance_attempt.text

    admin_attempt = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "head_approve", "remarks": "Admin tries final approval"},
        headers=_headers(admin),
    )
    assert admin_attempt.status_code == 403, admin_attempt.text

    head_process = client.post(
        f"/finance/runs/{run.id}/process",
        headers=_headers(head),
    )
    assert head_process.status_code == 403, head_process.text

    head_salary_edit = client.post(
        "/finance/salary-structures/from-ctc",
        json={
            "employee_id": employee.id,
            "annual_ctc": 720000,
            "effective_from": "2026-04-01",
        },
        headers=_headers(head),
    )
    assert head_salary_edit.status_code == 403, head_salary_edit.text

    db_session.expire_all()
    unchanged = db_session.get(PayrollRun, run.id)
    assert unchanged.status == "pending_head_approval"
    assert unchanged.payroll_locked is False


def test_completion_reports_are_available_only_after_final_approval(client, db_session):
    hr, finance, head, employee = _seed_people(db_session)
    _salary_structure(db_session, employee)
    run = _payroll_run(db_session, employee)

    blocked = client.get(f"/finance/runs/{run.id}/bank-advice", headers=_headers(finance))
    assert blocked.status_code == 400, blocked.text
    assert "Finance Head final approval" in blocked.json()["detail"]

    finance_review = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "approve", "remarks": "Finance review complete"},
        headers=_headers(finance),
    )
    assert finance_review.status_code == 200, finance_review.text

    final_approval = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "head_approve", "remarks": "Final approval"},
        headers=_headers(head),
    )
    assert final_approval.status_code == 200, final_approval.text
    assert final_approval.json()["lifecycle_status"] == "FINAL_APPROVED"
    assert final_approval.json()["payroll_locked"] is True

    hr_view = client.get(f"/finance/runs/{run.id}", headers=_headers(hr))
    assert hr_view.status_code == 200, hr_view.text

    bank_advice = client.get(f"/finance/runs/{run.id}/bank-advice", headers=_headers(finance))
    assert bank_advice.status_code == 200, bank_advice.text
    assert "Employee Name" in bank_advice.text
    assert "EMP001 User" in bank_advice.text
    assert "1234567890" in bank_advice.text
    assert "TEST0001234" in bank_advice.text
    assert "41800.00" in bank_advice.text

    payroll_register = client.get(f"/finance/runs/{run.id}/payroll-register", headers=_headers(head))
    assert payroll_register.status_code == 200, payroll_register.text
    assert "Net Salary" in payroll_register.text


def test_generate_publish_to_ess_scopes_employee_payslips(client, db_session):
    _, finance, head, employee = _seed_people(db_session)
    hr_role = db_session.query(Role).filter_by(name="hr").one()
    dept = db_session.query(Department).filter_by(id="DEP001").one()
    other = _employee(
        db_session,
        hr_role,
        "EMP002",
        "other-payroll@test.local",
        department_id=dept.id,
    )
    _salary_structure(db_session, employee)
    _salary_structure(db_session, other)
    run = _payroll_run(db_session, employee)
    db_session.add(
        PayrollRunEmployee(
            run_id=run.id,
            employee_id=other.id,
            total_working_days=30,
            working_days=30,
            payable_days=30,
            present_days=30,
            gross_earnings=60000,
            basic_pay=30000,
            hra=12000,
            special_allowance=18000,
            employee_pf=1800,
            employer_pf=1800,
            professional_tax=200,
            tds=6000,
            total_deductions=8000,
            net_pay=52000,
        )
    )
    db_session.commit()

    publish_too_early = client.post(
        f"/finance/runs/{run.id}/payslips/publish-all",
        headers=_headers(finance),
    )
    assert publish_too_early.status_code == 400, publish_too_early.text
    assert "Generate payslips" in publish_too_early.json()["detail"]

    assert client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "approve", "remarks": "Finance review complete"},
        headers=_headers(finance),
    ).status_code == 200
    assert client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "head_approve", "remarks": "Final approval"},
        headers=_headers(head),
    ).status_code == 200

    generated = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "generate_payslips", "remarks": "Generate payslips"},
        headers=_headers(finance),
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["status"] == "payslip_generated"

    published = client.post(
        f"/finance/runs/{run.id}/action",
        json={"action": "publish", "remarks": "Publish to ESS"},
        headers=_headers(finance),
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    db_session.expire_all()
    assert db_session.query(Payslip).filter_by(run_id=run.id, is_published=True).count() == 2
    assert db_session.query(Notification).filter_by(
        recipient_id=employee.id,
        type="payslip_published",
    ).count() == 1
    assert db_session.query(Notification).filter_by(
        recipient_id=other.id,
        type="payslip_published",
    ).count() == 1

    employee_slips = client.get("/employee/payroll/payslips", headers=_headers(employee))
    assert employee_slips.status_code == 200, employee_slips.text
    assert len(employee_slips.json()) == 1
    assert employee_slips.json()[0]["run_id"] == run.id

    other_slips = client.get("/employee/payroll/payslips", headers=_headers(other))
    assert other_slips.status_code == 200, other_slips.text
    assert len(other_slips.json()) == 1
    assert other_slips.json()[0]["run_id"] == run.id


def test_employee_payroll_status_ignores_attendance_without_active_run(client, db_session):
    _, _, _, employee = _seed_people(db_session)
    _salary_structure(db_session, employee)
    db_session.add(
        MonthlyAttendanceSummary(
            employee_id=employee.id,
            month=6,
            year=2026,
            total_working_days=22,
            present_days=22,
            payable_days=22,
            attendance_status="validated",
            timesheet_status="approved",
            validation_status="passed",
            is_ready_for_payroll=True,
            is_frozen=False,
        )
    )
    db_session.commit()

    response = client.get("/employee/payroll/status", headers=_headers(employee))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["payroll_cycle_started"] is False
    assert body["message"] == "No payroll cycle started yet."
    assert body["payroll_month"] is None
    assert body["net_monthly"] is None
    assert body["gross_monthly"] is None
    assert body["payslip_status"] is None
    assert body["attendance_status"] == "pending_cycle"


def test_employee_payroll_status_uses_active_run_not_latest_attendance(client, db_session):
    _, _, _, employee = _seed_people(db_session)
    _salary_structure(db_session, employee)
    run = _payroll_run(db_session, employee, status="processing")
    run.pay_period_start = date(2026, 5, 1)
    run.pay_period_end = date(2026, 5, 31)
    run.month_label = "May 2026"
    run.month = 5
    run.year = 2026
    row = db_session.query(PayrollRunEmployee).filter_by(run_id=run.id, employee_id=employee.id).one()
    row.gross_earnings = 60000
    row.net_pay = 46200
    db_session.add_all([
        MonthlyAttendanceSummary(
            employee_id=employee.id,
            month=5,
            year=2026,
            total_working_days=22,
            present_days=22,
            payable_days=22,
            attendance_status="finalized",
            timesheet_status="approved",
            validation_status="passed",
            is_ready_for_payroll=True,
            is_frozen=True,
        ),
        MonthlyAttendanceSummary(
            employee_id=employee.id,
            month=6,
            year=2026,
            total_working_days=22,
            present_days=22,
            payable_days=22,
            attendance_status="validated",
            timesheet_status="approved",
            validation_status="passed",
            is_ready_for_payroll=True,
            is_frozen=False,
        ),
    ])
    db_session.commit()

    response = client.get("/employee/payroll/status", headers=_headers(employee))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["payroll_cycle_started"] is True
    assert body["payroll_run_id"] == run.id
    assert body["payroll_month"] == "May 2026"
    assert body["net_monthly"] == 46200
    assert body["attendance_status"] == "finalized"
    assert body["attendance_frozen"] is True
    assert body["payslip_status"] == "pending"
