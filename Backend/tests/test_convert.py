"""
tests/test_convert.py — Candidate → Employee conversion flow.

Covers
------
  • happy path: OFFER_ACCEPTED candidate becomes an Employee with leave balances
  • idempotent: second call returns the existing employee, not 500
  • soft-delete revival: a previously NOT_JOINED candidate, if the candidate is
    flipped back to a convertible status, restores the soft-deleted Employee
    instead of triggering a UNIQUE-email collision
  • PII encryption: aadhaar/pan/bank_account columns store ciphertext, not the
    plain value
  • role guard: a candidate role can't trigger conversion
"""

import pytest


CONVERT_PAYLOAD_BASE = {
    "department_id": "DEP001",
    "designation_id": "D1",
    "employment_status": "active",
    "first_name": "Test",
    "last_name":  "User",
    "phone": None,
    "gender": "male",
    "Nationality": "Indian",
    "Marital_status": "Single",
    "blood_group": "O+",
    "aadhaar":      "123412341234",
    "pan":          "ABCDE1234F",
    "bank_account": "9876543210",
    "bank_ifsc":    "HDFC0001234",
    "password": "employee123",
}


def test_convert_happy_path_creates_employee_and_balances(
    client, db_session, candidate_factory, seeded_master_data, seeded_leave_types,
):
    """OFFER_ACCEPTED → CONVERTED, Employee + 3 LeaveBalances created."""
    cand = candidate_factory(email="newhire@test.com")

    res = client.post(
        f"/convert/{cand.id}",
        json=CONVERT_PAYLOAD_BASE,
        headers=client.auth_headers(role="hr"),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["email"] == "newhire@test.com"
    assert data["employee_code"].startswith("EMP")
    assert data["leave_balances_created"] == 3   # one per seeded leave type

    # Candidate advanced to CONVERTED
    db_session.expire_all()
    from api.models import Candidate, Employee, LeaveBalance, CandidateStatus
    refreshed = db_session.query(Candidate).get(cand.id)
    assert refreshed.status == CandidateStatus.CONVERTED.value

    # Employee row written
    emp = db_session.query(Employee).filter_by(email="newhire@test.com").first()
    assert emp is not None
    assert emp.is_activated is False                  # IT activates later
    assert emp.force_password_change is True
    assert emp.Password is not None and emp.Password.startswith("$2b$")

    # 3 leave balances seeded for this employee
    bal_count = db_session.query(LeaveBalance).filter_by(employee_id=emp.id).count()
    assert bal_count == 3


def test_convert_is_idempotent(
    client, candidate_factory, seeded_master_data, seeded_leave_types,
):
    """Calling /convert twice returns the existing employee, not 409 or 500."""
    cand = candidate_factory(email="dup@test.com")

    first  = client.post(f"/convert/{cand.id}", json=CONVERT_PAYLOAD_BASE,
                         headers=client.auth_headers(role="hr"))
    assert first.status_code == 201

    second = client.post(f"/convert/{cand.id}", json=CONVERT_PAYLOAD_BASE,
                         headers=client.auth_headers(role="hr"))
    assert second.status_code == 200
    assert "already exists" in second.json()["message"].lower()
    assert second.json()["data"]["employee_code"] == first.json()["data"]["employee_code"]


def test_convert_revives_soft_deleted_employee(
    client, db_session, candidate_factory, seeded_master_data, seeded_leave_types,
):
    """If an Employee row exists with is_deleted=True, /convert revives it
    instead of hitting the UNIQUE(email) constraint."""
    cand = candidate_factory(email="revive@test.com")

    # First conversion
    first = client.post(f"/convert/{cand.id}", json=CONVERT_PAYLOAD_BASE,
                        headers=client.auth_headers(role="hr"))
    assert first.status_code == 201
    emp_code = first.json()["data"]["employee_code"]

    # Soft-delete the employee (mimicking NOT_JOINED)
    from api.models import Employee, CandidateStatus
    emp = db_session.query(Employee).filter_by(email="revive@test.com").first()
    emp.is_deleted = True
    emp.employment_status = "exited"
    db_session.commit()

    # Flip candidate back to a convertible state
    cand.status = CandidateStatus.OFFER_ACCEPTED.value
    db_session.commit()

    # Re-convert
    res = client.post(f"/convert/{cand.id}", json=CONVERT_PAYLOAD_BASE,
                      headers=client.auth_headers(role="hr"))
    assert res.status_code == 200, res.text
    assert res.json()["data"].get("revived") is True
    assert res.json()["data"]["employee_code"] == emp_code

    # Employee is no longer soft-deleted
    db_session.expire_all()
    emp2 = db_session.query(Employee).filter_by(email="revive@test.com").first()
    assert emp2.is_deleted is False


def test_convert_encrypts_pii_fields(
    client, db_session, candidate_factory, seeded_master_data, seeded_leave_types,
):
    """Aadhaar/PAN/Bank account are persisted as Fernet ciphertext, not plain bytes."""
    cand = candidate_factory(email="pii@test.com")

    res = client.post(f"/convert/{cand.id}", json=CONVERT_PAYLOAD_BASE,
                      headers=client.auth_headers(role="hr"))
    assert res.status_code == 201

    from api.models import Employee
    emp = db_session.query(Employee).filter_by(email="pii@test.com").first()

    # The plaintext must NOT appear in the stored bytes.
    assert b"123412341234" not in (emp.aadhaar_encrypted or b"")
    assert b"ABCDE1234F"   not in (emp.pan_encrypted or b"")
    assert b"9876543210"   not in (emp.bank_account_encrypted or b"")

    # Ciphertext starts with the Fernet version byte (0x80 = "gAAAAA..." in b64).
    assert emp.aadhaar_encrypted is not None
    assert emp.aadhaar_encrypted[:1] in (b"g", b"\x80")  # b64 'g' or raw 0x80

    # And we can round-trip via the helper
    from utils.crypto import decrypt_pii
    assert decrypt_pii(emp.aadhaar_encrypted) == "123412341234"
    assert decrypt_pii(emp.pan_encrypted)      == "ABCDE1234F"


def test_convert_rejects_candidate_role(
    client, candidate_factory, seeded_master_data, seeded_leave_types,
):
    """A candidate-role JWT cannot trigger conversion of themselves or anyone else."""
    cand = candidate_factory(email="self@test.com")

    res = client.post(
        f"/convert/{cand.id}",
        json=CONVERT_PAYLOAD_BASE,
        headers=client.auth_headers(role="candidate", sub="self@test.com",
                                    candidate_id=cand.id),
    )
    assert res.status_code == 403
