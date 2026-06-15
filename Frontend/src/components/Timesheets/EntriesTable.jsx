import { useState } from 'react';
import { EMPLOYEE_EDITABLE } from './workflow/statuses';

// ── Status badge ──────────────────────────────────────────────────────────────

const STATUS_BADGE = {
  draft:     { bg: 'var(--hrms-surface-2)', color: 'var(--hrms-text-muted)', border: '0.5px solid var(--hrms-border)' },
  submitted: { bg: '#EBF4FF', color: '#1D5FA5', border: 'none' },
  approved:  { bg: '#EAF3DE', color: '#3B6D11', border: 'none' },
  Weekend:   { bg: 'var(--hrms-surface-2)', color: 'var(--hrms-text-muted)', border: '0.5px solid var(--hrms-border)' },
  Holiday:   { bg: '#F3E8FF', color: '#6B21A8', border: 'none' },
};

function StatusBadge({ text }) {
  const s = STATUS_BADGE[text] || STATUS_BADGE.draft;
  return (
    <span style={{
      fontSize: 11, padding: '2px 8px', borderRadius: 10,
      fontWeight: 500, display: 'inline-block', whiteSpace: 'nowrap',
      background: s.bg, color: s.color, border: s.border || 'none',
    }}>
      {text}
    </span>
  );
}

// ── Attendance hours display ──────────────────────────────────────────────────

/**
 * loggedHours — fallback from TimesheetEntry.logged_hours.
 * Used when there is no AttendanceRecord for the day (e.g. seeded entries,
 * manually-created entries, or attendance not yet processed).
 */
function HoursCell({ attendance, loggedHours = 0 }) {
  if (!attendance) {
    if (loggedHours > 0) {
      return <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--hrms-text)' }}>{loggedHours}h</span>;
    }
    return <span style={{ fontSize: 11, color: 'var(--hrms-text-faint)' }}>—</span>;
  }
  const { attendance_status, effective_hours, status } = attendance;
  if (attendance_status === 'NO_ATTENDANCE' && (status === 'Weekend' || status === 'Holiday')) {
    return <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--hrms-text-muted)' }}>0h</span>;
  }
  if (attendance_status === 'PENDING_CHECKOUT') {
    return (
      <span style={{
        fontSize: 11, color: '#854F0B', background: '#FAEEDA',
        borderRadius: 4, padding: '2px 7px', border: '0.5px solid #F3D9B5',
        whiteSpace: 'nowrap',
      }}>
        Pending checkout
      </span>
    );
  }
  if (attendance_status === 'NO_ATTENDANCE' || !effective_hours) {
    if (loggedHours > 0) {
      return <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--hrms-text)' }}>{loggedHours}h</span>;
    }
    return <span style={{ fontSize: 11, color: 'var(--hrms-text-faint)', fontStyle: 'italic' }}>No attendance</span>;
  }
  return (
    <span style={{ fontWeight: 600, fontSize: 13, color: 'var(--hrms-text)' }}>
      {effective_hours}h
    </span>
  );
}

// ── Options ───────────────────────────────────────────────────────────────────

const CLIENTS  = ['Infosys', 'Internal', 'Accenture', 'TCS', 'Wipro', 'Other'];
const PROJECTS = ['HRMS Portal', 'Team Meeting', 'Payroll App', 'BGV System', 'Onboarding Flow', 'Other'];

// ── Inline edit row (client / project / task only) ────────────────────────────

function EditRow({ entry, attendance, loggedHours, onSave, onCancel }) {
  const [form, setForm]     = useState({ client: entry.client, project: entry.project, task: entry.task });
  const [errors, setErrors] = useState({});
  const [shake, setShake]   = useState(false);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const isPlaceholderDay =
    attendance?.attendance_status === 'NO_ATTENDANCE' &&
    ['Weekend', 'Holiday'].includes(attendance.status);
  const isAttendanceMissing =
    !attendance || (attendance.attendance_status !== 'FINALIZED' && !isPlaceholderDay);

  const validate = () => {
    const errs = {};
    if (!form.client)  errs.client  = 'Required';
    if (!form.project) errs.project = 'Required';
    if (isAttendanceMissing) errs.attendance = 'Attendance not finalized for this day';
    return errs;
  };

  const handleSave = () => {
    const errs = validate();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      setShake(true);
      setTimeout(() => setShake(false), 450);
      return;
    }
    onSave(form);
  };

  const inp = (hasErr) => ({
    padding: '4px 7px', border: `0.5px solid ${hasErr ? '#EF4444' : 'var(--hrms-border)'}`,
    borderRadius: 5, fontSize: 12, width: '100%',
    boxSizing: 'border-box', outline: 'none', fontFamily: 'inherit',
    background: 'var(--hrms-surface)', color: 'var(--hrms-text)',
  });

  return (
    <>
      <tr style={{
        background: '#FFFBF0',
        animation: shake ? 'tsShake 0.4s ease' : 'none',
      }}>
        {/* Day — readonly in edit mode */}
        <td style={{ padding: '6px 9px' }}>
          <span style={{
            fontSize: 11, fontWeight: 500, background: 'var(--hrms-surface-2)',
            borderRadius: 4, padding: '2px 7px', display: 'inline-block',
            border: '0.5px solid var(--hrms-border)',
          }}>
            {entry.day}
          </span>
        </td>

        {/* Client */}
        <td style={{ padding: '6px 9px' }}>
          <select value={form.client} onChange={(e) => set('client', e.target.value)} style={inp(!!errors.client)}>
            <option value="">— Select —</option>
            {CLIENTS.map((c) => <option key={c}>{c}</option>)}
          </select>
          {errors.client && <div style={{ color: '#EF4444', fontSize: 10, marginTop: 1 }}>{errors.client}</div>}
        </td>

        {/* Project */}
        <td style={{ padding: '6px 9px' }}>
          <select value={form.project} onChange={(e) => set('project', e.target.value)} style={inp(!!errors.project)}>
            <option value="">— Select —</option>
            {PROJECTS.map((p) => <option key={p}>{p}</option>)}
          </select>
          {errors.project && <div style={{ color: '#EF4444', fontSize: 10, marginTop: 1 }}>{errors.project}</div>}
        </td>

        {/* Task */}
        <td style={{ padding: '6px 9px' }}>
          <input
            value={form.task}
            onChange={(e) => set('task', e.target.value)}
            placeholder="Task / work notes"
            style={inp(false)}
          />
        </td>

        {/* Hours — readonly; attendance takes priority, entry.logged_hours is fallback */}
        <td style={{ padding: '6px 9px' }}>
          <HoursCell attendance={attendance} loggedHours={loggedHours} />
          {errors.attendance && (
            <div style={{ color: '#EF4444', fontSize: 10, marginTop: 1 }}>{errors.attendance}</div>
          )}
        </td>

        {/* Status */}
        <td style={{ padding: '6px 9px' }}>
          <StatusBadge text={isPlaceholderDay ? attendance.status : (entry.status || 'draft')} />
        </td>

        {/* Actions */}
        <td style={{ padding: '6px 9px' }}>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              onClick={handleSave}
              disabled={isAttendanceMissing}
              title={isAttendanceMissing ? 'Attendance not finalized for this day' : 'Save'}
              style={{
                padding: '3px 10px',
                background: isAttendanceMissing ? 'var(--hrms-border)' : '#0F172A',
                color: isAttendanceMissing ? 'var(--hrms-text-faint)' : '#fff',
                border: 'none', borderRadius: 5, fontSize: 12,
                cursor: isAttendanceMissing ? 'not-allowed' : 'pointer',
                fontFamily: 'inherit',
              }}
            >
              Save
            </button>
            <button
              onClick={onCancel}
              style={{
                padding: '3px 8px', background: 'var(--hrms-surface-2)', color: 'var(--hrms-text-2)',
                border: '0.5px solid var(--hrms-border)', borderRadius: 5, fontSize: 12,
                cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              ✕
            </button>
          </div>
        </td>
      </tr>
      <style>{`
        @keyframes tsShake {
          0%,100% { transform: none; }
          25%      { transform: translateX(-4px); }
          75%      { transform: translateX(4px); }
        }
      `}</style>
    </>
  );
}

// ── Main table ────────────────────────────────────────────────────────────────

export default function EntriesTable({
  entries,
  filters,
  weekStatus,
  attendanceMap,
  attendanceLoading,
  onUpdate,
}) {
  const [editingId, setEditingId] = useState(null);
  const isLocked = !EMPLOYEE_EDITABLE.has(weekStatus);

  const filtered = entries.filter((e) => {
    if (filters.client  && e.client  !== filters.client)  return false;
    if (filters.project && e.project !== filters.project) return false;
    if (filters.status  && e.status  !== filters.status)  return false;
    return true;
  });

  const handleSave = (id, data) => { onUpdate(id, data); setEditingId(null); };
  const rowStatus = (entry, attendance) => (
    attendance?.attendance_status === 'NO_ATTENDANCE' && ['Weekend', 'Holiday'].includes(attendance.status)
      ? attendance.status
      : entry.status
  );

  return (
    <div style={{
      background: 'var(--hrms-surface)', border: '0.5px solid var(--hrms-border)',
      borderRadius: 8, marginBottom: '0.625rem', overflow: 'hidden',
    }}>
      {/* Header row */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0.5rem 1rem 0.375rem',
      }}>
        <p style={{
          fontSize: 11, fontWeight: 600, color: 'var(--hrms-text-faint)',
          textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0,
        }}>
          Weekly entries
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {attendanceLoading && (
            <span style={{ fontSize: 11, color: 'var(--hrms-text-faint)', fontStyle: 'italic' }}>
              Syncing attendance…
            </span>
          )}
          <span style={{ fontSize: 11, color: 'var(--hrms-text-faint)' }}>
            {entries.length} entr{entries.length === 1 ? 'y' : 'ies'}
          </span>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse', tableLayout: 'fixed' }}>
          <colgroup>
            <col style={{ width: '7%' }} />
            <col style={{ width: '17%' }} />
            <col style={{ width: '21%' }} />
            <col style={{ width: '26%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '10%' }} />
            <col style={{ width: '7%' }} />
          </colgroup>
          <thead>
            <tr style={{ borderBottom: '0.5px solid var(--hrms-border)', background: 'var(--hrms-surface-2)' }}>
              {['Day', 'Client', 'Project', 'Task', 'Hours', 'Status', isLocked ? '' : 'Actions'].map((h) => (
                <th key={h} style={{
                  padding: '5px 10px', textAlign: 'left',
                  fontSize: 11, fontWeight: 600, color: 'var(--hrms-text-faint)',
                  textTransform: 'uppercase', letterSpacing: '0.04em',
                  whiteSpace: 'nowrap',
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: '24px 20px', textAlign: 'center', color: 'var(--hrms-text-faint)', fontSize: 12 }}>
                  No entries for this week.
                </td>
              </tr>
            )}

            {filtered.map((entry) => {
              const att         = attendanceMap?.[entry.date];
              const loggedHours = entry.logged_hours || 0;
              return editingId === entry.id && !isLocked ? (
                <EditRow
                  key={entry.id}
                  entry={entry}
                  attendance={att}
                  loggedHours={loggedHours}
                  onSave={(data) => handleSave(entry.id, data)}
                  onCancel={() => setEditingId(null)}
                />
              ) : (
                <tr
                  key={entry.id}
                  style={{ borderBottom: '0.5px solid var(--hrms-border)', transition: 'background 0.1s' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--hrms-surface-2)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = ''; }}
                >
                  <td style={{ padding: '7px 10px' }}>
                    <span style={{
                      fontSize: 11, fontWeight: 500, background: 'var(--hrms-surface-2)',
                      borderRadius: 4, padding: '2px 7px', display: 'inline-block',
                      border: '0.5px solid var(--hrms-border)',
                    }}>
                      {entry.day}
                    </span>
                  </td>
                  <td style={{ padding: '7px 10px', color: 'var(--hrms-text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {entry.client || <span style={{ color: 'var(--hrms-text-faint)', fontStyle: 'italic' }}>—</span>}
                  </td>
                  <td style={{ padding: '7px 10px', color: 'var(--hrms-text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {entry.project || <span style={{ color: 'var(--hrms-text-faint)', fontStyle: 'italic' }}>—</span>}
                  </td>
                  <td style={{ padding: '7px 10px', color: 'var(--hrms-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {entry.task || <span style={{ color: 'var(--hrms-text-faint)', fontStyle: 'italic' }}>—</span>}
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    <HoursCell attendance={att} loggedHours={loggedHours} />
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    <StatusBadge text={rowStatus(entry, att)} />
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    {!isLocked && (
                      <button
                        onClick={() => setEditingId(entry.id)}
                        style={{
                          padding: '2px 7px', background: 'transparent', color: 'var(--hrms-text-muted)',
                          border: '0.5px solid var(--hrms-border)', borderRadius: 4, fontSize: 11, cursor: 'pointer',
                        }}
                        title="Edit client / project / task"
                      >
                        ✏
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer note */}
      <div style={{ padding: '5px 1rem', borderTop: '0.5px solid var(--hrms-border)' }}>
        <span style={{ fontSize: 11, color: 'var(--hrms-text-faint)' }}>
          Hours are read-only and synced automatically from your attendance records.
        </span>
      </div>
    </div>
  );
}
