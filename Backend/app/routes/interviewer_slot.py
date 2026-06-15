"""
Public interviewer slot-submission routes — NO authentication required.

GET  /interviews/slot-selection/{token}
    Returns a self-contained HTML page that lets the interviewer add their
    available time slots for a candidate interview round.

POST /interviews/slot-selection/{token}
    Accepts { "slots": [{"slot_date": "...", "slot_time": "..."}, ...] }.
    Creates InterviewSlot rows, notifies the recruiter (in-app), and
    emails the candidate with individual "Select This Slot" buttons.

The token is interview_rounds.selection_token, generated when the recruiter
assigns the interviewer (assign_interviewer service function).  The same
token is later used by the candidate's selection page (/candidate/select-slot/{token})
— no new DB columns are needed.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.recruitment import (
    CandidatePipeline, InterviewRound, InterviewSlot,
    JobRequirement, RecruitmentCandidate,
)
from app.services import recruiter_service as svc

logger = logging.getLogger("hrms.interviewer_slot")

router = APIRouter(prefix="/interviews", tags=["interviewer-slot"])


# ── Shared HTML helpers ───────────────────────────────────────────────────────

_BASE_STYLE = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #f0f4f8;
    min-height: 100vh;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 40px 16px;
  }
  .card {
    background: #fff;
    border-radius: 16px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.10);
    max-width: 600px;
    width: 100%;
    padding: 40px 36px;
  }
  .logo { font-size: 22px; font-weight: 700; color: #2563eb; margin-bottom: 24px; letter-spacing: -0.5px; }
  h1 { font-size: 20px; font-weight: 700; color: #111827; margin-bottom: 6px; }
  .subtitle { font-size: 14px; color: #6b7280; margin-bottom: 28px; line-height: 1.6; }
  .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 28px; }
  .info-item { background: #f8fafc; border-radius: 8px; padding: 12px 14px; border: 1px solid #e5e7eb; }
  .info-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #9ca3af; margin-bottom: 4px; }
  .info-value { font-size: 13px; font-weight: 600; color: #111827; }
  .section-title { font-size: 13px; font-weight: 700; color: #111827; margin-bottom: 12px; }
  .slot-row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
  .slot-row input[type=date], .slot-row input[type=time] {
    flex: 1; padding: 10px 12px; border: 1.5px solid #e5e7eb; border-radius: 8px;
    font-size: 14px; font-family: inherit; background: #fff; color: #111827;
    outline: none; transition: border-color .15s;
  }
  .slot-row input:focus { border-color: #2563eb; }
  .remove-btn {
    width: 32px; height: 32px; border-radius: 8px; border: none;
    background: #fee2e2; color: #dc2626; cursor: pointer; font-size: 15px;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    transition: background .15s;
  }
  .remove-btn:hover { background: #fecaca; }
  .add-btn {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    padding: 10px 16px; border: 1.5px dashed #2563eb; border-radius: 8px;
    background: #eff6ff; color: #2563eb; font-size: 13px; font-weight: 600;
    cursor: pointer; font-family: inherit; transition: all .15s; width: 100%;
    margin-bottom: 24px;
  }
  .add-btn:hover { background: #dbeafe; border-style: solid; }
  .submit-btn {
    display: block; width: 100%; background: #2563eb; color: #fff;
    border: none; border-radius: 10px; padding: 14px;
    font-size: 15px; font-weight: 600; cursor: pointer; font-family: inherit;
    transition: background .15s;
  }
  .submit-btn:hover { background: #1d4ed8; }
  .submit-btn:disabled { background: #93c5fd; cursor: not-allowed; }
  #status-msg { margin-top: 16px; padding: 12px 16px; border-radius: 8px;
                font-size: 14px; font-weight: 500; display: none; }
  #status-msg.ok  { background: #f0fdf4; color: #15803d; display: block; }
  #status-msg.err { background: #fef2f2; color: #b91c1c; display: block; }
  .msg { text-align: center; padding: 24px 0 8px; }
  .msg-icon { font-size: 48px; margin-bottom: 12px; }
  .msg h2 { font-size: 18px; font-weight: 700; color: #111827; margin-bottom: 8px; }
  .msg p  { font-size: 14px; color: #6b7280; line-height: 1.6; }
  @media (max-width: 480px) {
    .card { padding: 28px 20px; }
    .info-grid { grid-template-columns: 1fr; }
  }
</style>
"""


def _page(body_html: str, title: str = "Add Interview Slots") -> HTMLResponse:
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


def _today_iso() -> str:
    return date.today().isoformat()


def _fmt_date(date_str: Optional[str]) -> str:
    if not date_str:
        return "TBD"
    try:
        d = date.fromisoformat(date_str)
        return d.strftime("%a, %d %b %Y")
    except Exception:
        return date_str


# ── GET /interviews/slot-selection/{token} ────────────────────────────────────

@router.get("/slot-selection/{token}", response_class=HTMLResponse)
def interviewer_slot_page(token: str, db: Session = Depends(get_db)) -> HTMLResponse:
    """Render the slot-submission page for the interviewer (no login required)."""

    r = db.query(InterviewRound).filter(InterviewRound.selection_token == token).first()

    if not r:
        return _page("""
        <div class="msg">
          <div class="msg-icon">&#9888;</div>
          <h2>Invalid Link</h2>
          <p>This link is not valid or has expired.<br/>
             Please contact the recruiter for a new link.</p>
        </div>
        """, "Invalid Link")

    # Candidate has already confirmed a slot
    if r.token_used:
        p    = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
        cand = None
        if p:
            cand = db.query(RecruitmentCandidate).filter(
                RecruitmentCandidate.candidate_id == p.candidate_id
            ).first()
        cand_name = f"{cand.first_name} {cand.last_name or ''}".strip() if cand else "The candidate"
        return _page(f"""
        <div class="msg">
          <div class="msg-icon">&#10003;</div>
          <h2>Interview Confirmed</h2>
          <p>{cand_name} has already selected an interview slot.<br/>
             Please check your email or the HRMS portal for the confirmed schedule.</p>
        </div>
        """, "Interview Confirmed")

    # Fetch context
    p    = db.query(CandidatePipeline).filter(CandidatePipeline.id == r.pipeline_id).first()
    cand = None
    req  = None
    if p:
        cand = db.query(RecruitmentCandidate).filter(
            RecruitmentCandidate.candidate_id == p.candidate_id
        ).first()
        req = db.query(JobRequirement).filter(JobRequirement.id == p.requirement_id).first()

    cand_name  = f"{cand.first_name} {cand.last_name or ''}".strip() if cand else "Candidate"
    req_id     = req.req_id if req else "—"
    req_title  = req.title if req else "the position"
    round_name = r.round_name or "Interview"
    today      = _today_iso()

    existing_count = (
        db.query(InterviewSlot)
        .filter(InterviewSlot.round_id == r.id, InterviewSlot.is_selected == 0)
        .count()
    )
    submitted_note = ""
    if existing_count > 0:
        submitted_note = f"""
        <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;
                    padding:12px 14px;margin-bottom:20px;font-size:13px;color:#15803d;">
          &#10003; You have already submitted <strong>{existing_count}</strong> slot(s).
          You can add more slots below — the candidate will receive an updated email.
        </div>"""

    body_html = f"""
    <h1>Add Interview Slots</h1>
    <p class="subtitle">
      You have been assigned to interview <strong>{cand_name}</strong> for the
      <strong>{req_title}</strong> position. Please add your available time slots
      so the candidate can choose a preferred time.
    </p>

    <div class="info-grid">
      <div class="info-item">
        <div class="info-label">Candidate</div>
        <div class="info-value">{cand_name}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Requirement ID</div>
        <div class="info-value">{req_id}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Position</div>
        <div class="info-value">{req_title}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Interview Round</div>
        <div class="info-value">{round_name}</div>
      </div>
    </div>

    {submitted_note}

    <p class="section-title">Available Slots</p>
    <div id="slots-container">
      <div class="slot-row" id="slot-0">
        <input type="date" id="date-0" min="{today}" placeholder="Date" aria-label="Slot date"/>
        <input type="time" id="time-0" placeholder="Time" aria-label="Slot time"/>
        <button type="button" class="remove-btn" onclick="removeSlot('slot-0')"
                title="Remove this slot">&#10005;</button>
      </div>
    </div>

    <button type="button" class="add-btn" onclick="addSlot()">&#43; Add Another Slot</button>

    <button type="button" class="submit-btn" id="submit-btn" onclick="submitSlots()">
      Submit Slots
    </button>
    <div id="status-msg"></div>

    <script>
      var _rowIdx = 1;
      var _today  = '{today}';

      function addSlot() {{
        var idx = _rowIdx++;
        var container = document.getElementById('slots-container');
        var row = document.createElement('div');
        row.className = 'slot-row';
        row.id = 'slot-' + idx;
        row.innerHTML =
          '<input type="date" id="date-' + idx + '" min="' + _today + '" aria-label="Slot date"/>' +
          '<input type="time" id="time-' + idx + '" aria-label="Slot time"/>' +
          '<button type="button" class="remove-btn" onclick="removeSlot(\\'slot-' + idx + '\\')" title="Remove this slot">&#10005;</button>';
        container.appendChild(row);
      }}

      function removeSlot(rowId) {{
        var rows = document.querySelectorAll('.slot-row');
        if (rows.length <= 1) {{
          showMsg('You must keep at least one slot.', 'err');
          return;
        }}
        var row = document.getElementById(rowId);
        if (row) row.remove();
      }}

      async function submitSlots() {{
        var rows   = document.querySelectorAll('.slot-row');
        var slots  = [];
        var hasErr = false;

        rows.forEach(function (row) {{
          var d = row.querySelector('input[type=date]');
          var t = row.querySelector('input[type=time]');
          if (!d || !t) return;
          if (!d.value || !t.value) {{ hasErr = true; return; }}
          slots.push({{ slot_date: d.value, slot_time: t.value }});
        }});

        if (hasErr || slots.length === 0) {{
          showMsg('Please fill in both date and time for every slot.', 'err');
          return;
        }}

        var btn = document.getElementById('submit-btn');
        btn.disabled    = true;
        btn.textContent = 'Submitting…';
        hideMsg();

        try {{
          var res  = await fetch('/interviews/slot-selection/{token}', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ slots: slots }}),
          }});
          var data = await res.json();
          if (res.ok && !data.error) {{
            document.getElementById('slots-container').style.display = 'none';
            document.querySelector('.add-btn').style.display = 'none';
            btn.style.display = 'none';
            showMsg('&#10003; ' + (data.message || 'Slots submitted! The candidate has been notified by email.'), 'ok');
          }} else {{
            showMsg(data.error || data.detail || 'Something went wrong. Please try again.', 'err');
            btn.disabled    = false;
            btn.textContent = 'Submit Slots';
          }}
        }} catch (_) {{
          showMsg('Network error. Please check your connection and try again.', 'err');
          btn.disabled    = false;
          btn.textContent = 'Submit Slots';
        }}
      }}

      function showMsg(text, cls) {{
        var el = document.getElementById('status-msg');
        el.innerHTML  = text;
        el.className  = cls;
      }}
      function hideMsg() {{
        var el = document.getElementById('status-msg');
        el.style.display = 'none';
        el.className = '';
      }}
    </script>
    """
    return _page(body_html)


# ── POST /interviews/slot-selection/{token} ───────────────────────────────────

@router.post("/slot-selection/{token}")
def interviewer_submit_slots(
    token: str,
    payload: dict,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """
    Process the interviewer's slot submission.
    Body: { "slots": [{"slot_date": "YYYY-MM-DD", "slot_time": "HH:MM"}, ...] }
    On success: creates InterviewSlot rows, notifies recruiter, emails candidate.
    """
    slots = payload.get("slots", [])
    if not slots:
        return JSONResponse(status_code=422, content={"error": "At least one slot is required"})

    for s in slots:
        if not s.get("slot_date") or not s.get("slot_time"):
            return JSONResponse(
                status_code=422,
                content={"error": "Each slot must have both slot_date and slot_time"},
            )

    r = db.query(InterviewRound).filter(InterviewRound.selection_token == token).first()
    if not r:
        return JSONResponse(status_code=404, content={"error": "Invalid or expired link"})
    if r.token_used:
        return JSONResponse(
            status_code=409,
            content={"error": "The candidate has already selected a slot for this round"},
        )

    result = svc.add_interview_slots(db, r.id, slots, None)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)

    return JSONResponse(content=result)
