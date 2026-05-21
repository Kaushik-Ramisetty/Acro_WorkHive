"""Timesheet HTML email builder and dispatcher.

Public API
----------
send_client_approval_email(db, ts_id, *, is_reminder=False)
    Fetches timesheet + attendance data, builds a complete HTML email with an
    embedded monthly calendar, and sends it to the client manager.
    Skips silently if the manager has no email address.

html_confirmation_page(variant, title, message)
    Returns an HTML page string for the browser-visible action confirmation
    screen (shown after the client clicks Approve / Reject in the email).

html_approval_form(token, ts_id, emp_name, period, error=None)
    Returns an HTML page with the approval confirmation form (optional remarks).
    The form POSTs back to POST /timesheet/client-action with action=approve.

html_rejection_form(token, ts_id, error=None)
    Returns an HTML page with the rejection comment <form>. The form POSTs
    back to POST /timesheet/client-action with action=reject.
"""
from __future__ import annotations

import logging
from datetime import date as date_t, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AttendanceRecord, Employee, Project, Timesheet, TimesheetEntry

logger = logging.getLogger("hrms.timesheet_email")

# ── Status badge helpers ──────────────────────────────────────────────────────

_STATUS_STYLE: dict[str, tuple[str, str, str]] = {
    "present":  ("#dcfce7", "#166534", "Present"),
    "late":     ("#fef9c3", "#854d0e", "Late"),
    "wfh":      ("#dbeafe", "#1e40af", "WFH"),
    "on_leave": ("#e0e7ff", "#3730a3", "On Leave"),
    "half_day": ("#fef3c7", "#92400e", "Half Day"),
    "holiday":  ("#f3e8ff", "#6b21a8", "Holiday"),
    "absent":   ("#fee2e2", "#991b1b", "Absent"),
    "weekend":  ("#f1f5f9", "#64748b", "Weekend"),
}

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _fmt_date(d) -> str:
    return d.strftime("%d %b %Y") if isinstance(d, date_t) else (str(d) if d else "—")


def _fmt_hours(h: Optional[float]) -> str:
    return f"{h:.1f}h" if h is not None else "—"


# ── Calendar builder ──────────────────────────────────────────────────────────

# (code, bg, fg) for each calendar status code
_CAL: dict[str, tuple[str, str]] = {
    "P":  ("#dcfce7", "#166534"),
    "A":  ("#fee2e2", "#991b1b"),
    "L":  ("#e0e7ff", "#3730a3"),
    "W":  ("#f1f5f9", "#64748b"),
    "WW": ("#dbeafe", "#1e40af"),
    "H":  ("#f3e8ff", "#6b21a8"),
    "HW": ("#fef3c7", "#854d0e"),
}


def _day_code(status: str, is_weekend: bool, has_checkin: bool) -> str:
    s = status.lower()
    if is_weekend:
        return "WW" if s in {"present", "late", "wfh"} else "W"
    if s == "holiday":
        return "HW" if has_checkin else "H"
    if s in {"present", "late", "wfh"}:
        return "P"
    if s in {"on_leave", "half_day"}:
        return "L"
    return "A"


def _build_calendar_table(ts: Timesheet, att_map: dict) -> tuple[str, dict]:
    """Return (calendar_html, summary_dict) for the monthly calendar view."""
    summary = {"present": 0, "absent": 0, "ww": 0, "hw": 0,
               "total_hours": 0.0, "overtime": 0.0}
    if not (ts.period_start and ts.period_end):
        return "", summary

    days: list[date_t] = []
    cur = ts.period_start
    while cur <= ts.period_end:
        days.append(cur)
        cur += timedelta(days=1)

    date_cells = day_cells = status_cells = ""

    for d in days:
        wd = d.weekday()
        is_we = wd >= 5
        rec = att_map.get(d)
        s = (rec.status if rec else "") or ""
        has_ci = bool(rec and rec.check_in_time)
        code = _day_code(s, is_we, has_ci)

        if code == "P":    summary["present"] += 1
        elif code == "A":  summary["absent"]  += 1
        elif code == "WW": summary["ww"]      += 1
        elif code == "HW": summary["hw"]      += 1
        if rec:
            summary["total_hours"] += rec.working_hours  or 0.0
            summary["overtime"]    += rec.overtime_hours or 0.0

        bg, fg = _CAL[code]
        hdr_bg = "#2d4a6f" if is_we else "#1e3a5f"
        day_abbr = _WEEKDAYS[wd][:2]

        date_cells += (
            f'<td style="padding:3px 1px;text-align:center;background:{hdr_bg};'
            f'color:#e2e8f0;font-size:10px;font-weight:700;'
            f'border-right:1px solid rgba(255,255,255,0.15);">{d.day}</td>'
        )
        day_cells += (
            f'<td style="padding:2px 1px;text-align:center;background:#f8fafc;'
            f'color:#64748b;font-size:9px;font-weight:600;'
            f'border-right:1px solid #e2e8f0;">{day_abbr}</td>'
        )
        status_cells += (
            f'<td style="padding:4px 1px;text-align:center;background:{bg};'
            f'color:{fg};font-size:10px;font-weight:700;'
            f'border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;">{code}</td>'
        )

    cal_html = (
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%"'
        ' style="border-collapse:collapse;border:1px solid #e2e8f0;">'
        '<tbody>'
        f'<tr>{date_cells}</tr>'
        f'<tr>{day_cells}</tr>'
        f'<tr>{status_cells}</tr>'
        '</tbody></table>'
    )
    return cal_html, summary


# ── Plain-text row builder ────────────────────────────────────────────────────

def _build_plain_rows(ts: Timesheet, att_map: dict) -> str:
    lines = []
    if not (ts.period_start and ts.period_end):
        return ""
    cur = ts.period_start
    while cur <= ts.period_end:
        rec  = att_map.get(cur)
        wday = _WEEKDAYS[cur.weekday()]
        hrs  = _fmt_hours(rec.working_hours if rec else None)
        stat = (rec.status if rec else ("—" if cur.weekday() >= 5 else "absent")).upper()
        lines.append(f"  {cur.strftime('%d %b')}  {wday}  {hrs:>6}  {stat}")
        cur += timedelta(days=1)
    return "\n".join(lines)


# ── Full HTML email builder ───────────────────────────────────────────────────

def _build_html(
    ts: Timesheet,
    employee: Employee,
    manager_name: str,
    att_map: dict,
    approve_url: str,
    reject_url: str,
    project_name: Optional[str] = None,
    is_reminder: bool = False,
) -> tuple[str, str]:
    """Return (html_body, plain_text_fallback)."""

    emp_name  = employee.full_name if employee else f"Employee #{ts.employee_id}"
    emp_code  = (employee.employee_code or "—") if employee else "—"
    desig     = getattr(employee.designation, "title", "N/A") if employee and employee.designation else "N/A"
    proj_str  = project_name or "—"
    period    = f"{_fmt_date(ts.period_start)} → {_fmt_date(ts.period_end)}"
    submitted = ts.submitted_at.strftime("%d %b %Y %H:%M") if ts.submitted_at else "—"
    remarks   = ts.review_comment or ""

    cal_html, summary = _build_calendar_table(ts, att_map)
    abs_str = str(summary["absent"])
    pr_str  = str(summary["present"])
    ww_str  = str(summary["ww"])
    hw_str  = str(summary["hw"])

    reminder_banner = (
        '<tr><td colspan="1" style="background:#fef9c3;padding:10px 32px;text-align:center;">'
        '<p style="margin:0;font-size:12px;font-weight:700;color:#854d0e;">'
        '&#9201; REMINDER &mdash; This timesheet has been awaiting your approval for over 2 days.'
        '</p></td></tr>'
    ) if is_reminder else ""

    remarks_block = ""
    if remarks:
        remarks_block = (
            '<tr><td style="padding:0 32px 16px;">'
            '<div style="background:#fffbeb;border-left:3px solid #f59e0b;padding:12px 16px;border-radius:4px;">'
            '<p style="margin:0 0 4px;font-size:10px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:0.5px;">Employee Remarks</p>'
            f'<p style="margin:0;font-size:13px;color:#374151;">{remarks}</p>'
            '</div></td></tr>'
        )

    prefix = "Reminder: " if is_reminder else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{prefix}Timesheet Approval &mdash; WorkHive HRMS</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#f0f4f8;padding:24px 0;">
<tr><td align="center">
<table role="presentation" cellpadding="0" cellspacing="0" width="640"
  style="max-width:640px;background:#ffffff;border-radius:8px;overflow:hidden;
         box-shadow:0 2px 12px rgba(0,0,0,0.10);">

<!-- ── Header ── -->
<tr>
  <td style="background:#1e3a5f;padding:20px 32px;">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr>
      <td>
        <span style="font-size:19px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;">WorkHive</span>
        <span style="font-size:11px;color:#93c5fd;margin-left:8px;">HRMS</span>
      </td>
      <td align="right">
        <span style="font-size:10px;color:#93c5fd;background:rgba(255,255,255,0.12);
                     padding:3px 10px;border-radius:10px;">
          {'&#9201; REMINDER &nbsp;|&nbsp; ' if is_reminder else ''}Timesheet Approval
        </span>
      </td>
    </tr></table>
  </td>
</tr>

{reminder_banner}

<!-- ── Greeting ── -->
<tr>
  <td style="padding:24px 32px 14px;">
    <p style="margin:0 0 10px;font-size:16px;font-weight:700;color:#1a2b45;">
      {prefix}Action Required &mdash; Timesheet Approval
    </p>
    <p style="margin:0;font-size:13px;color:#4b5563;line-height:1.7;">
      Dear {manager_name},<br><br>
      <strong>{emp_name}</strong> has submitted their monthly timesheet for your review.
      Please review the calendar breakdown below and click <strong>Approve</strong> or
      <strong>Reject</strong> to take action.
    </p>
  </td>
</tr>

<!-- ── Employee info box ── -->
<tr>
  <td style="padding:0 32px 18px;">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%"
      style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;">
      <tr><td style="padding:16px;">
        <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
          <tr>
            <td width="50%" style="vertical-align:top;padding-right:16px;">
              <p style="margin:0 0 3px;font-size:10px;font-weight:700;color:#94a3b8;
                        text-transform:uppercase;letter-spacing:0.6px;">Employee</p>
              <p style="margin:0;font-size:14px;font-weight:700;color:#1a2b45;">{emp_name}</p>
              <p style="margin:2px 0 0;font-size:12px;color:#64748b;">{emp_code} &bull; {desig}</p>
              <p style="margin:4px 0 0;font-size:11px;color:#64748b;">Project: <strong>{proj_str}</strong></p>
            </td>
            <td width="50%" style="vertical-align:top;">
              <p style="margin:0 0 3px;font-size:10px;font-weight:700;color:#94a3b8;
                        text-transform:uppercase;letter-spacing:0.6px;">Reporting Period</p>
              <p style="margin:0;font-size:14px;font-weight:700;color:#1a2b45;">{period}</p>
              <p style="margin:2px 0 0;font-size:12px;color:#64748b;">Submitted: {submitted}</p>
            </td>
          </tr>
          <tr><td colspan="2" style="padding-top:14px;">
            <table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr>
              <td style="text-align:center;padding:10px 6px;background:#f0fdf4;border-radius:5px;">
                <p style="margin:0;font-size:10px;color:#64748b;">Present Days</p>
                <p style="margin:3px 0 0;font-size:17px;font-weight:700;color:#166534;">{pr_str}</p>
              </td>
              <td width="6"></td>
              <td style="text-align:center;padding:10px 6px;background:#fef2f2;border-radius:5px;">
                <p style="margin:0;font-size:10px;color:#64748b;">Absent Days</p>
                <p style="margin:3px 0 0;font-size:17px;font-weight:700;color:#991b1b;">{abs_str}</p>
              </td>
              <td width="6"></td>
              <td style="text-align:center;padding:10px 6px;background:#dbeafe;border-radius:5px;">
                <p style="margin:0;font-size:10px;color:#64748b;">Wknd Worked</p>
                <p style="margin:3px 0 0;font-size:17px;font-weight:700;color:#1e40af;">{ww_str}</p>
              </td>
              <td width="6"></td>
              <td style="text-align:center;padding:10px 6px;background:#fef3c7;border-radius:5px;">
                <p style="margin:0;font-size:10px;color:#64748b;">Hol Worked</p>
                <p style="margin:3px 0 0;font-size:17px;font-weight:700;color:#854d0e;">{hw_str}</p>
              </td>
            </tr></table>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </td>
</tr>

<!-- ── Monthly attendance calendar ── -->
<tr>
  <td style="padding:0 32px 18px;">
    <p style="margin:0 0 8px;font-size:10px;font-weight:700;color:#94a3b8;
              text-transform:uppercase;letter-spacing:0.6px;">Monthly Attendance Calendar</p>
    {cal_html}
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:8px;border-collapse:collapse;">
      <tr>
        <td style="padding:2px 5px;background:#dcfce7;border-radius:3px;font-size:9px;font-weight:700;color:#166534;">P&nbsp;Present</td>
        <td width="4"></td>
        <td style="padding:2px 5px;background:#fee2e2;border-radius:3px;font-size:9px;font-weight:700;color:#991b1b;">A&nbsp;Absent</td>
        <td width="4"></td>
        <td style="padding:2px 5px;background:#e0e7ff;border-radius:3px;font-size:9px;font-weight:700;color:#3730a3;">L&nbsp;Leave</td>
        <td width="4"></td>
        <td style="padding:2px 5px;background:#f1f5f9;border-radius:3px;font-size:9px;font-weight:700;color:#64748b;">W&nbsp;Weekend</td>
        <td width="4"></td>
        <td style="padding:2px 5px;background:#dbeafe;border-radius:3px;font-size:9px;font-weight:700;color:#1e40af;">WW&nbsp;Wknd&nbsp;Worked</td>
        <td width="4"></td>
        <td style="padding:2px 5px;background:#f3e8ff;border-radius:3px;font-size:9px;font-weight:700;color:#6b21a8;">H&nbsp;Holiday</td>
        <td width="4"></td>
        <td style="padding:2px 5px;background:#fef3c7;border-radius:3px;font-size:9px;font-weight:700;color:#854d0e;">HW&nbsp;Hol&nbsp;Worked</td>
      </tr>
    </table>
  </td>
</tr>

{remarks_block}

<!-- ── Action buttons ── -->
<tr>
  <td style="padding:8px 32px 28px;">
    <p style="margin:0 0 12px;font-size:13px;font-weight:600;color:#374151;">Your Action Required:</p>
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td style="border-radius:6px;background:#15803d;">
        <a href="{approve_url}" target="_blank"
          style="display:inline-block;padding:11px 28px;color:#ffffff;
                 font-size:13px;font-weight:700;text-decoration:none;">
          &#10003; Approve
        </a>
      </td>
      <td width="10"></td>
      <td style="border-radius:6px;background:#b91c1c;">
        <a href="{reject_url}" target="_blank"
          style="display:inline-block;padding:11px 28px;color:#ffffff;
                 font-size:13px;font-weight:700;text-decoration:none;">
          &#10007; Reject
        </a>
      </td>
    </tr></table>
    <p style="margin:12px 0 0;font-size:11px;color:#94a3b8;">
      These action links expire in 72 hours. Clicking <strong>Approve</strong> opens a
      confirmation page where you can add optional remarks. The <strong>Reject</strong>
      button opens a short form requiring a rejection reason.
    </p>
  </td>
</tr>

<!-- ── Footer ── -->
<tr>
  <td style="background:#f8fafc;padding:14px 32px;border-top:1px solid #e2e8f0;">
    <p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.6;">
      This is an automated notification from <strong>WorkHive HRMS</strong>.
      Do not reply to this email directly.<br>
      If you believe you received this in error, please contact your HR team.
    </p>
  </td>
</tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    # ── Plain text fallback ──
    plain = (
        f"{'[REMINDER] ' if is_reminder else ''}TIMESHEET APPROVAL — WorkHive HRMS\n"
        f"{'=' * 60}\n"
        f"Employee : {emp_name} ({emp_code})\n"
        f"Project  : {proj_str}\n"
        f"Period   : {period}\n"
        f"Submitted: {submitted}\n"
        f"Present: {pr_str}  Absent: {abs_str}  Wknd Worked: {ww_str}  Hol Worked: {hw_str}\n"
        "\nMONTHLY ATTENDANCE  (P=Present A=Absent L=Leave W=Weekend WW=WkndWorked H=Holiday HW=HolWorked)\n"
        f"{'-' * 50}\n"
        f"{_build_plain_rows(ts, att_map)}\n"
    )
    if remarks:
        plain += f"\nEmployee Remarks: {remarks}\n"
    plain += (
        f"\nACTION REQUIRED\n"
        f"{'-' * 50}\n"
        f"Approve : {approve_url}\n"
        f"Reject  : {reject_url}\n"
        "\nThese links expire in 72 hours.\n"
        "This is an automated message from WorkHive HRMS. Do not reply.\n"
    )

    return html, plain


# ── Confirmation page (browser) ───────────────────────────────────────────────

def html_confirmation_page(variant: str, title: str, message: str) -> str:
    """variant: 'success' | 'error' | 'info' | 'warning'"""
    styles = {
        "success": ("#15803d", "#f0fdf4", "✓"),
        "error":   ("#b91c1c", "#fef2f2", "✗"),
        "info":    ("#1e40af", "#eff6ff", "ℹ"),
        "warning": ("#b45309", "#fffbeb", "⚠"),
    }
    btn_c, bg_c, icon = styles.get(variant, styles["info"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} — WorkHive HRMS</title>
</head>
<body style="margin:0;padding:40px 20px;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif;min-height:100vh;">
<div style="max-width:500px;margin:0 auto;">
  <div style="background:#1e3a5f;padding:16px 28px;border-radius:8px 8px 0 0;">
    <span style="font-size:17px;font-weight:700;color:#fff;">WorkHive</span>
    <span style="font-size:11px;color:#93c5fd;margin-left:8px;">HRMS</span>
  </div>
  <div style="background:#fff;padding:36px 28px;border-radius:0 0 8px 8px;
              box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <div style="width:56px;height:56px;line-height:56px;border-radius:28px;
                background:{bg_c};margin:0 auto 20px;text-align:center;">
      <span style="font-size:26px;color:{btn_c};">{icon}</span>
    </div>
    <h2 style="text-align:center;margin:0 0 10px;font-size:19px;color:#1a2b45;">{title}</h2>
    <p style="text-align:center;margin:0 0 20px;font-size:13px;color:#555;line-height:1.6;">{message}</p>
    <p style="text-align:center;margin:0;font-size:11px;color:#94a3b8;">
      You may close this window. Contact HR if you need further assistance.
    </p>
  </div>
</div>
</body>
</html>"""


# ── Approval form (browser) ───────────────────────────────────────────────────

def html_approval_form(
    token: str,
    ts_id: str,
    emp_name: str,
    period: str,
    error: Optional[str] = None,
) -> str:
    """HTML page with the approval confirmation form (optional remarks). POSTs to /timesheet/client-action."""
    error_block = ""
    if error:
        error_block = (
            f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:4px;'
            f'padding:10px 14px;margin-bottom:16px;color:#991b1b;font-size:13px;">{error}</div>'
        )

    settings = get_settings()
    action_url = f"{settings.CLIENT_ACTION_BASE_URL.rstrip('/')}/timesheet/client-action"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Approve Timesheet — WorkHive HRMS</title>
</head>
<body style="margin:0;padding:40px 20px;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif;min-height:100vh;">
<div style="max-width:500px;margin:0 auto;">
  <div style="background:#1e3a5f;padding:16px 28px;border-radius:8px 8px 0 0;">
    <span style="font-size:17px;font-weight:700;color:#fff;">WorkHive</span>
    <span style="font-size:11px;color:#93c5fd;margin-left:8px;">HRMS</span>
  </div>
  <div style="background:#fff;padding:32px 28px;border-radius:0 0 8px 8px;
              box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <h2 style="margin:0 0 8px;font-size:17px;color:#1a2b45;">Approve Timesheet</h2>
    <p style="margin:0 0 20px;font-size:13px;color:#555;line-height:1.6;">
      You are approving <strong>{emp_name}</strong>'s timesheet for
      <strong>{period}</strong>. You may add optional remarks before confirming.
    </p>
    {error_block}
    <form method="POST" action="{action_url}">
      <input type="hidden" name="token" value="{token}">
      <input type="hidden" name="action" value="approve">
      <div style="margin-bottom:16px;">
        <label style="display:block;font-size:12px;font-weight:600;color:#374151;margin-bottom:6px;">
          Approval Remarks <span style="color:#94a3b8;">(optional)</span>
        </label>
        <textarea name="comments" rows="3"
          placeholder="e.g. Hours verified against project records. Approved."
          style="width:100%;box-sizing:border-box;padding:10px 12px;
                 border:1px solid #d1d5db;border-radius:6px;font-size:13px;
                 font-family:inherit;color:#374151;resize:vertical;outline:none;"></textarea>
      </div>
      <button type="submit"
        style="width:100%;padding:11px 20px;background:#15803d;color:#fff;
               border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">
        &#10003; Confirm Approval
      </button>
    </form>
    <p style="margin:16px 0 0;font-size:11px;color:#94a3b8;text-align:center;">
      Changed your mind? Close this window — no action will be taken.
    </p>
  </div>
</div>
</body>
</html>"""


# ── Rejection form (browser) ──────────────────────────────────────────────────

def html_rejection_form(token: str, ts_id: str, error: Optional[str] = None) -> str:
    """HTML page with the rejection comment form. POSTs to /timesheet/client-action."""
    error_block = ""
    if error:
        error_block = (
            f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:4px;'
            f'padding:10px 14px;margin-bottom:16px;color:#991b1b;font-size:13px;">{error}</div>'
        )

    settings = get_settings()
    action_url = f"{settings.CLIENT_ACTION_BASE_URL.rstrip('/')}/timesheet/client-action"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Reject Timesheet — WorkHive HRMS</title>
</head>
<body style="margin:0;padding:40px 20px;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif;min-height:100vh;">
<div style="max-width:500px;margin:0 auto;">
  <div style="background:#1e3a5f;padding:16px 28px;border-radius:8px 8px 0 0;">
    <span style="font-size:17px;font-weight:700;color:#fff;">WorkHive</span>
    <span style="font-size:11px;color:#93c5fd;margin-left:8px;">HRMS</span>
  </div>
  <div style="background:#fff;padding:32px 28px;border-radius:0 0 8px 8px;
              box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <h2 style="margin:0 0 8px;font-size:17px;color:#1a2b45;">Reject Timesheet</h2>
    <p style="margin:0 0 20px;font-size:13px;color:#555;line-height:1.6;">
      Please provide a reason for rejection. This will be shared with the employee
      so they can make the necessary corrections and resubmit.
    </p>
    {error_block}
    <form method="POST" action="{action_url}">
      <input type="hidden" name="token" value="{token}">
      <input type="hidden" name="action" value="reject">
      <div style="margin-bottom:16px;">
        <label style="display:block;font-size:12px;font-weight:600;color:#374151;margin-bottom:6px;">
          Rejection Reason <span style="color:#b91c1c;">*</span>
        </label>
        <textarea name="comments" rows="4" required
          placeholder="e.g. Hours on 5–8 May do not match project records. Please review and resubmit."
          style="width:100%;box-sizing:border-box;padding:10px 12px;
                 border:1px solid #d1d5db;border-radius:6px;font-size:13px;
                 font-family:inherit;color:#374151;resize:vertical;outline:none;"></textarea>
      </div>
      <button type="submit"
        style="width:100%;padding:11px 20px;background:#b91c1c;color:#fff;
               border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">
        Confirm Rejection
      </button>
    </form>
    <p style="margin:16px 0 0;font-size:11px;color:#94a3b8;text-align:center;">
      Changed your mind? Close this window — no action will be taken.
    </p>
  </div>
</div>
</body>
</html>"""


# ── Main dispatcher ───────────────────────────────────────────────────────────

def send_client_approval_email(
    db: Session,
    ts_id: str,
    *,
    is_reminder: bool = False,
) -> None:
    """Build the HTML approval/reminder email and dispatch it to the client manager.

    Uses ts.client_manager_email directly — no FK lookup through client_manager_id.

    Silently skips if:
      - ts.client_manager_email is blank
      - period dates are missing
      - employee record not found
    """
    from app.services.email_dispatcher import send_html_email  # local import avoids circular

    ts = db.get(Timesheet, ts_id)
    if not ts:
        return

    send_to = (ts.client_manager_email or "").strip()
    if not send_to:
        logger.debug("No client_manager_email on timesheet %s — skipping email", ts_id)
        return

    employee = db.get(Employee, ts.employee_id)
    if not employee:
        return

    if not ts.period_start or not ts.period_end:
        return

    token = ts.client_token
    if not token:
        logger.warning("No client token on timesheet %s - skipping approval email", ts_id)
        return

    settings = get_settings()
    base = settings.CLIENT_ACTION_BASE_URL.rstrip("/")
    approve_url = f"{base}/timesheet/client-action?token={token}&action=approve"
    reject_url  = f"{base}/timesheet/client-action?token={token}&action=reject"

    # Fetch attendance records for the period to build the calendar
    att_records = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.employee_id == ts.employee_id,
            AttendanceRecord.date >= ts.period_start,
            AttendanceRecord.date <= ts.period_end,
        )
        .all()
    )
    att_map = {r.date: r for r in att_records}

    # Resolve project name from the first entry that has one
    project_name: Optional[str] = None
    entry = (
        db.query(TimesheetEntry)
        .filter(
            TimesheetEntry.timesheet_id == ts_id,
            TimesheetEntry.project_id.isnot(None),
        )
        .first()
    )
    if entry and entry.project_id:
        proj = db.get(Project, entry.project_id)
        project_name = proj.name if proj else None

    manager_name = (getattr(ts, "client_manager_name", None) or "").strip() or "Client Manager"
    html_body, text_body = _build_html(
        ts, employee,
        manager_name=manager_name,
        att_map=att_map,
        approve_url=approve_url,
        reject_url=reject_url,
        project_name=project_name,
        is_reminder=is_reminder,
    )

    emp_name = employee.full_name
    period   = f"{_fmt_date(ts.period_start)} to {_fmt_date(ts.period_end)}"
    prefix   = "Reminder: " if is_reminder else ""
    subject  = f"{prefix}Timesheet Approval Required — {emp_name} ({period})"

    send_html_email(send_to, subject, html_body, text_fallback=text_body)
    logger.info(
        "Approval email sent for %s to %s (reminder=%s)", ts_id, send_to, is_reminder
    )
