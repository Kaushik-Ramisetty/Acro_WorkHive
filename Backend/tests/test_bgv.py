"""
tests/test_bgv.py — BGV initiation + vendor portal submission.

Covers
------
  • POST /bgv/start/{id}          — admin initiates legacy BGV
  • PATCH /bgv/update/{id}        — admin sets CLEAR / FAILED / ON_HOLD
  • Status mirroring:               BGV → candidate.status
  • Vendor portal submit          — token consumed, "HOLD" → "ON_HOLD" canonical
"""

import pytest


def _make_candidate_with_doc(db_session, email="bgv@test.com"):
    """Helper — candidate at OFFER_ACCEPTED with one uploaded doc (BGV needs one)."""
    from api.models import Candidate, CandidateDocument, CandidateStatus, DocumentStatus

    cand = Candidate(
        candidate_ref="CAND-BGV01",
        first_name="Bgv", last_name="Tester",
        name="Bgv Tester", email=email, role="Engineer",
        status=CandidateStatus.OFFER_ACCEPTED.value,
    )
    db_session.add(cand); db_session.flush()

    db_session.add(CandidateDocument(
        candidate_id=cand.id,
        doc_type="aadhar",
        original_filename="aadhaar.pdf",
        file_url="/uploads/documents/x/aadhaar.pdf",
        status=DocumentStatus.UPLOADED.value,
    ))
    db_session.commit()
    return cand


def test_bgv_start_then_update_clear_mirrors_candidate(client, db_session):
    cand = _make_candidate_with_doc(db_session)

    start = client.post(f"/bgv/start/{cand.id}", json={"vendor_name": "AcmeBGV"},
                        headers=client.auth_headers(role="hr"))
    assert start.status_code == 201
    assert start.json()["data"]["status"] == "IN_PROGRESS"

    update = client.patch(f"/bgv/update/{cand.id}",
                          json={"status": "CLEAR", "remarks": "All good"},
                          headers=client.auth_headers(role="hr"))
    assert update.status_code == 200
    assert update.json()["data"]["status"] == "CLEAR"

    # Candidate mirrored to BGV_CLEAR
    db_session.expire_all()
    from api.models import Candidate
    refreshed = db_session.query(Candidate).get(cand.id)
    assert refreshed.status == "BGV_CLEAR"


def test_bgv_update_to_on_hold_mirrors_candidate(client, db_session):
    """ON_HOLD via the legacy update endpoint must sync the candidate too."""
    cand = _make_candidate_with_doc(db_session, email="hold@test.com")

    client.post(f"/bgv/start/{cand.id}", json={},
                headers=client.auth_headers(role="hr"))

    res = client.patch(f"/bgv/update/{cand.id}",
                       json={"status": "ON_HOLD", "remarks": "Vendor needs more info"},
                       headers=client.auth_headers(role="hr"))
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "ON_HOLD"

    db_session.expire_all()
    from api.models import Candidate
    assert db_session.query(Candidate).get(cand.id).status == "BGV_ON_HOLD"


def test_bgv_update_blocks_after_terminal(client, db_session):
    """Once a BGV is CLEAR / FAILED / ON_HOLD, further /bgv/update calls are 409."""
    cand = _make_candidate_with_doc(db_session, email="terminal@test.com")
    client.post(f"/bgv/start/{cand.id}", json={},
                headers=client.auth_headers(role="hr"))
    client.patch(f"/bgv/update/{cand.id}", json={"status": "CLEAR", "remarks": "ok"},
                 headers=client.auth_headers(role="hr"))

    res = client.patch(f"/bgv/update/{cand.id}",
                       json={"status": "FAILED", "remarks": "actually no"},
                       headers=client.auth_headers(role="hr"))
    assert res.status_code == 409


def test_vendor_submit_hold_persists_canonical_on_hold(client, db_session):
    """
    Vendor submits "HOLD"; backend must store BGVStatus.ON_HOLD ("ON_HOLD"),
    not the raw "HOLD", so that the duplicate-finalize guard works.
    """
    cand = _make_candidate_with_doc(db_session, email="vendor@test.com")

    init = client.post(
        f"/api/v1/bgv/initiate/{cand.id}",
        json={"vendor_name": "VendorCo"},
        headers=client.auth_headers(role="hr"),
    )
    assert init.status_code == 201, init.text
    vendor_link = init.json()["data"]["vendor_link"]
    token = vendor_link.rsplit("/", 1)[-1]

    submit = client.post(
        f"/api/v1/bgv/vendor/{token}/submit",
        json={"status": "HOLD", "remarks": "Need additional documents"},
    )
    assert submit.status_code == 200, submit.text
    assert submit.json()["data"]["bgv_status"] == "ON_HOLD"
    assert submit.json()["data"]["candidate_status"] == "BGV_ON_HOLD"

    # Token is one-time-use — re-submission should 409
    again = client.post(
        f"/api/v1/bgv/vendor/{token}/submit",
        json={"status": "CLEAR", "remarks": "changed mind"},
    )
    assert again.status_code == 409
