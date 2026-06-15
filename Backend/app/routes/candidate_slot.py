"""
Public candidate slot-selection routes — NO authentication required.

GET  /candidate/select-slot/{token}
    Returns a self-contained HTML page that lists available slots and lets
    the candidate choose one.

POST /candidate/confirm-slot/{token}
    Processes the selection (slot_id in JSON body), marks the slot selected,
    and returns JSON so the HTML page can show a success/error message.

The token is a URL-safe random string (secrets.token_urlsafe(32)) stored in
interview_rounds.selection_token.  It is single-use — once the candidate has
confirmed, token_used is set to 1 and the GET page shows a "already confirmed"
message.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recruitment import CandidatePipeline, InterviewRound, InterviewSlot, JobRequirement, RecruitmentCandidate
from app.services import recruiter_service as svc

logger = logging.getLogger("hrms.candidate_slot")

router = APIRouter(prefix="/candidate", tags=["candidate-slot"])


# ── Shared HTML helpers ───────────────────────────────────────────────────────

_BASE_STYLE = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f0f4f8;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px 16px;
  }
  .card {
    background: #fff;
    border-radius: 16px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.10);
    max-width: 540px;
    width: 100%;
    padding: 40px 36px;
  }
  .logo {
    font-size: 22px;
    font-weight: 700;
    color: #2563eb;
    margin-bottom: 24px;
    letter-spacing: -0.5px;
  }
  h1 { font-size: 20px; font-weight: 700; color: #111827; margin-bottom: 6px; }
  .subtitle { font-size: 14px; color: #6b7280; margin-bottom: 28px; }
  .slot-list { display: flex; flex-direction: column; gap: 12px; margin-bottom: 28px; }
  .slot-item {
    border: 2px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px 16px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    display: flex;
    align-items: center;
    gap: 14px;
    user-select: none;
  }
  .slot-item:hover { border-color: #93c5fd; background: #eff6ff; }
  .slot-item.selected { border-color: #2563eb; background: #eff6ff; }
  .slot-item input[type=radio] { accent-color: #2563eb; width: 18px; height: 18px; flex-shrink: 0; }
  .slot-date { font-weight: 600; color: #111827; font-size: 15px; }
  .slot-time { font-size: 13px; color: #6b7280; margin-top: 2px; }
  .btn {
    display: block; width: 100%;
    background: #2563eb; color: #fff;
    border: none; border-radius: 10px;
    padding: 14px;
    font-size: 15px; font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
  }
  .btn:hover { background: #1d4ed8; }
  .btn:disabled { background: #93c5fd; cursor: not-allowed; }
  .msg { text-align: center; padding: 24px 0 8px; }
  .msg-icon { font-size: 48px; margin-bottom: 12px; }
  .msg h2 { font-size: 18px; font-weight: 700; color: #111827; margin-bottom: 8px; }
  .msg p  { font-size: 14px; color: #6b7280; line-height: 1.6; }
  .msg.success .msg-icon { color: #16a34a; }
  .msg.error   .msg-icon { color: #dc2626; }
  #status-msg { display: none; margin-top: 16px; padding: 12px 16px; border-radius: 8px;
                font-size: 14px; font-weight: 500; }
  #status-msg.ok  { background: #f0fdf4; color: #15803d; }
  #status-msg.err { background: #fef2f2; color: #b91c1c; }
</style>
"""


def _page(body_html: str, title: str = "Interview Slot Selection") -> HTMLResponse:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet"/>
  {_BASE_STYLE}
</head>
<body>
  <div class="card">
    <div class="logo">WorkHive HRMS</div>
    {body_html}
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)


def _fmt_date(date_str: Optional[str]) -> str:
    """'2026-06-01' -> 'Mon, 01 Jun 2026'"""
    if not date_str:
        return "TBD"
    try:
        from datetime import date
        d = date.fromisoformat(date_str)
        return d.strftime("%a, %d %b %Y")
    except Exception:
        return date_str


def _fmt_time(time_str: Optional[str]) -> str:
    """'14:00' -> '2:00 PM'"""
    if not time_str:
        return "TBD"
    try:
        from datetime import datetime as _dt
        t = _dt.strptime(time_str[:5], "%H:%M")
        return t.strftime("%I:%M %p").lstrip("0") or t.strftime("%I:%M %p")
    except Exception:
        return time_str


# ── GET /candidate/select-slot/{token} ───────────────────────────────────────

@router.get("/select-slot/{token}", response_class=HTMLResponse)
def candidate_slot_page(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """Render the slot-selection page for the candidate."""

    # 1. Look up the round by token
    r = db.query(InterviewRound).filter(InterviewRound.selection_token == token).first()

    if not r:
        return _page("""
        <div class="msg error">
          <div class="msg-icon">&#9888;</div>
          <h2>Invalid Link</h2>
          <p>This link is not valid or has expired.<br/>Please contact your recruiter for assistance.</p>
        </div>
        """, "Invalid Link")

    # 2. Already used?
    if r.token_used:
        selected_slot = (
            db.query(InterviewSlot)
            .filter(InterviewSlot.round_id == r.id, InterviewSlot.is_selected == 1)
            .first()
        )
        date_label = _fmt_date(selected_slot.slot_date) if selected_slot else "N/A"
        time_label = _fmt_time(selected_slot.slot_time) if selected_slot else "N/A"

        return _page(f"""
        <div class="msg success">
          <div class="msg-icon">&#10003;</div>
          <h2>Slot Already Confirmed</h2>
          <p>You have already selected your interview slot:<br/>
             <strong>{date_label} at {time_label}</strong><br/><br/>
             You will receive a calendar invite and Teams meeting link shortly.<br/>
             Please contact your recruiter if you need to make changes.</p>
        </div>
        """, "Interview Confirmed")

    # 3. Fetch pipeline / candidate / req info for the page header
    p    = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
    cand = None
    req  = None
    if p:
        cand = db.query(RecruitmentCandidate).filter(
            RecruitmentCandidate.candidate_id == p.candidate_id
        ).first()
        req = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first()

    cand_name = f"{cand.first_name} {cand.last_name or ''}".strip() if cand else "Candidate"
    req_title = req.title if req else "the position"

    # 4. Fetch available (unselected) slots
    from sqlalchemy import or_
    slots = (
        db.query(InterviewSlot)
        .filter(
            or_(InterviewSlot.round_id == r.id, InterviewSlot.round_id == r.round_order),
            InterviewSlot.is_selected == 0,
        )
        .order_by(InterviewSlot.slot_date, InterviewSlot.slot_time)
        .all()
    )

    if not slots:
        return _page(f"""
        <div class="msg error">
          <div class="msg-icon">&#128205;</div>
          <h2>No Slots Available</h2>
          <p>There are currently no available interview slots for your round.<br/>
             Please contact your recruiter — they will add more slots shortly.</p>
        </div>
        """, "No Slots Available")

    # 5. Build slot radio buttons
    slot_items_html = ""
    for s in slots:
        slot_items_html += f"""
        <label class="slot-item" onclick="selectSlot(this, {s.id})">
          <input type="radio" name="slot" value="{s.id}"/>
          <div>
            <div class="slot-date">{_fmt_date(s.slot_date)}</div>
            <div class="slot-time">{_fmt_time(s.slot_time)}</div>
          </div>
        </label>"""

    body_html = f"""
    <h1>Select Your Interview Slot</h1>
    <p class="subtitle">Hi <strong>{cand_name}</strong>, please choose a preferred time for your
    <strong>{r.round_name}</strong> for the role of <strong>{req_title}</strong>.</p>

    <form id="slot-form" onsubmit="confirmSlot(event)">
      <div class="slot-list">{slot_items_html}</div>
      <button type="submit" class="btn" id="confirm-btn" disabled>Confirm My Slot</button>
      <div id="status-msg"></div>
    </form>

    <script>
      var selectedSlotId = null;

      function selectSlot(label, slotId) {{
        document.querySelectorAll('.slot-item').forEach(function(el) {{
          el.classList.remove('selected');
        }});
        label.classList.add('selected');
        selectedSlotId = slotId;
        document.getElementById('confirm-btn').disabled = false;
      }}

      async function confirmSlot(e) {{
        e.preventDefault();
        if (!selectedSlotId) return;

        var btn = document.getElementById('confirm-btn');
        var msg = document.getElementById('status-msg');
        btn.disabled = true;
        btn.textContent = 'Confirming…';
        msg.style.display = 'none';

        try {{
          var res = await fetch('/candidate/confirm-slot/{token}', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ slot_id: selectedSlotId }}),
          }});
          var data = await res.json();
          if (res.ok && !data.error) {{
            document.getElementById('slot-form').innerHTML = `
              <div class="msg success" style="padding: 0;">
                <div class="msg-icon">&#10003;</div>
                <h2>Slot Confirmed!</h2>
                <p>Your interview has been scheduled.<br/>
                   You will receive a confirmation email and calendar invite shortly.</p>
              </div>`;
          }} else {{
            msg.textContent = data.error || data.detail || 'Something went wrong. Please try again.';
            msg.className = 'err';
            msg.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Confirm My Slot';
          }}
        }} catch (err) {{
          msg.textContent = 'Network error. Please check your connection and try again.';
          msg.className = 'err';
          msg.style.display = 'block';
          btn.disabled = false;
          btn.textContent = 'Confirm My Slot';
        }}
      }}
    </script>
    """
    return _page(body_html)


# ── GET /candidate/quick-select/{token}/{slot_id} ────────────────────────────

@router.get("/quick-select/{token}/{slot_id}", response_class=HTMLResponse)
def candidate_quick_select(
    token: str,
    slot_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """
    Direct slot confirmation from the email 'Select This Slot' button.
    No form interaction required — validates and selects the slot, then
    shows a confirmation page.
    """
    from sqlalchemy import or_

    # 1. Validate token
    r = db.query(InterviewRound).filter(InterviewRound.selection_token == token).first()
    if not r:
        return _page("""
        <div class="msg error">
          <div class="msg-icon">&#9888;</div>
          <h2>Invalid Link</h2>
          <p>This link is not valid or has expired.<br/>
             Please contact your recruiter for assistance.</p>
        </div>
        """, "Invalid Link")

    # 2. Already used
    if r.token_used:
        selected = (
            db.query(InterviewSlot)
            .filter(InterviewSlot.round_id == r.id, InterviewSlot.is_selected == 1)
            .first()
        )
        date_label = _fmt_date(selected.slot_date) if selected else "N/A"
        time_label = _fmt_time(selected.slot_time) if selected else "N/A"
        return _page(f"""
        <div class="msg success">
          <div class="msg-icon">&#10003;</div>
          <h2>Slot Already Confirmed</h2>
          <p>You have already selected your interview slot:<br/>
             <strong>{date_label} at {time_label}</strong><br/><br/>
             You will receive a calendar invite and meeting link shortly.</p>
        </div>
        """, "Interview Confirmed")

    # 3. Validate the slot belongs to this round
    slot = (
        db.query(InterviewSlot)
        .filter(
            InterviewSlot.id == slot_id,
            or_(InterviewSlot.round_id == r.id, InterviewSlot.round_id == r.round_order),
        )
        .first()
    )
    if not slot:
        return _page("""
        <div class="msg error">
          <div class="msg-icon">&#9888;</div>
          <h2>Slot Not Found</h2>
          <p>This slot is not available. It may have been removed.<br/>
             <a href="/candidate/select-slot/""" + token + """" style="color:#2563eb;">
               View all available slots
             </a></p>
        </div>
        """, "Slot Not Found")

    if slot.is_selected:
        return _page("""
        <div class="msg error">
          <div class="msg-icon">&#9888;</div>
          <h2>Slot Already Taken</h2>
          <p>This slot has already been selected.<br/>
             <a href="/candidate/select-slot/""" + token + """" style="color:#2563eb;">
               View other available slots
             </a></p>
        </div>
        """, "Slot Taken")

    # 4. Select the slot
    result = svc.select_interview_slot(db, slot_id, token=token)
    if "error" in result:
        return _page(f"""
        <div class="msg error">
          <div class="msg-icon">&#9888;</div>
          <h2>Unable to Confirm Slot</h2>
          <p>{result.get("error", "Something went wrong.")}<br/>
             Please contact your recruiter for assistance.</p>
        </div>
        """, "Error")

    date_label = _fmt_date(result.get("interview_date"))
    time_label = _fmt_time(result.get("interview_time"))

    # 5. Fetch round/req context for confirmation page
    p    = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
    req  = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first() if p else None
    req_title = req.title if req else "the position"

    return _page(f"""
    <div class="msg success">
      <div class="msg-icon">&#10003;</div>
      <h2>Interview Slot Confirmed!</h2>
      <p>Your interview has been scheduled for:<br/>
         <strong>{date_label} at {time_label}</strong><br/><br/>
         Round: <strong>{r.round_name}</strong><br/>
         Position: <strong>{req_title}</strong><br/><br/>
         You will receive a confirmation email and meeting details shortly.<br/>
         Please contact your recruiter if you need to make any changes.</p>
    </div>
    """, "Interview Confirmed")


# ── POST /candidate/confirm-slot/{token} ─────────────────────────────────────

@router.post("/confirm-slot/{token}")
def candidate_confirm_slot(
    token: str,
    payload: dict,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """
    Process the candidate's slot selection.
    Body: { "slot_id": <int> }
    Returns JSON { message, interview_date, interview_time } on success
    or { error: "..." } on failure.
    """
    slot_id = payload.get("slot_id")
    if not slot_id:
        return JSONResponse(status_code=422, content={"error": "slot_id is required"})

    # Validate the token first
    r = db.query(InterviewRound).filter(InterviewRound.selection_token == token).first()
    if not r:
        return JSONResponse(status_code=404, content={"error": "Invalid or expired link"})
    if r.token_used:
        return JSONResponse(status_code=409, content={"error": "You have already selected a slot"})

    # Verify the requested slot belongs to this round
    from sqlalchemy import or_
    slot = (
        db.query(InterviewSlot)
        .filter(
            InterviewSlot.id == slot_id,
            or_(InterviewSlot.round_id == r.id, InterviewSlot.round_id == r.round_order),
        )
        .first()
    )
    if not slot:
        return JSONResponse(
            status_code=400,
            content={"error": "The selected slot does not belong to this interview round"},
        )

    result = svc.select_interview_slot(db, slot_id, token=token)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)

    return JSONResponse(content=result)
