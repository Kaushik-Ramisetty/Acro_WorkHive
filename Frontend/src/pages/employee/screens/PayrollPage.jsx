import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import employeePayrollApi from '../../../services/employeePayrollApi';
import { api } from '../../../services/api';

function fmt(n) {
  if (n == null || n === undefined) return '—';
  return `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function Badge({ children, color = '#10B981', bg = '#D1FAE5' }) {
  return (
    <span style={{ background: bg, color, borderRadius: 99, padding: '2px 10px', fontSize: 11, fontWeight: 700 }}>
      {children}
    </span>
  );
}

function Tab({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '8px 20px', borderRadius: 8, border: 'none', cursor: 'pointer',
        fontWeight: 600, fontSize: 13,
        background: active ? '#3B5BDB' : 'transparent',
        color: active ? '#fff' : 'var(--text-secondary)',
        transition: 'all 0.15s',
      }}
    >
      {children}
    </button>
  );
}

function PayslipsTab() {
  const [slips, setSlips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [downloading, setDownloading] = useState(null);

  const downloadPdf = async (runId, label) => {
    setDownloading(runId);
    try {
      const { blob, contentType, filename } = await api.downloadBlob(
        employeePayrollApi.payslipPdfUrl(runId)
      );
      const objectUrl = URL.createObjectURL(new Blob([blob], { type: contentType }));
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename || `payslip_${label || runId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    } catch (e) {
      alert(e.status === 403 ? 'Access denied' : e.message || 'Download failed');
    } finally {
      setDownloading(null);
    }
  };

  useEffect(() => {
    employeePayrollApi.listPayslips()
      .then(setSlips)
      .catch(() => setSlips([]))
      .finally(() => setLoading(false));
  }, []);

  const openDetail = (runId) => {
    setDetailLoading(true);
    employeePayrollApi.getPayslipDetail(runId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  };

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading payslips…</div>;

  return (
    <div>
      {slips.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📄</div>
          <p>Payslip will be available after payroll is published.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {slips.map(slip => (
            <div key={slip.run_id} className="card" style={{ padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>{slip.month_label}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {slip.pay_period_start} → {slip.pay_period_end}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 24, alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Gross</div>
                  <div style={{ fontWeight: 600 }}>{fmt(slip.gross_salary)}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Deductions</div>
                  <div style={{ fontWeight: 600, color: '#EF4444' }}>{fmt(slip.total_deductions)}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Net Pay</div>
                  <div style={{ fontWeight: 700, fontSize: 16, color: '#10B981' }}>{fmt(slip.net_salary)}</div>
                </div>
                {slip.is_published ? (
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={() => openDetail(slip.run_id)}
                      className="btn btn-ghost"
                      style={{ padding: '6px 14px', fontSize: 12 }}
                    >
                      View
                    </button>
                    <button
                      onClick={() => downloadPdf(slip.run_id, slip.month_label)}
                      disabled={downloading === slip.run_id}
                      className="btn btn-primary"
                      style={{ padding: '6px 14px', fontSize: 12 }}
                    >
                      {downloading === slip.run_id ? '…' : '↓ PDF'}
                    </button>
                  </div>
                ) : (
                  <span style={{ fontSize: 12, color: '#94A3B8', fontStyle: 'italic' }}>
                    Payslip will be available after payroll is published.
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail drawer */}
      {detail && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }} onClick={() => setDetail(null)}>
          <div style={{ background: '#fff', borderRadius: 16, padding: 28, maxWidth: 520, width: '90%', maxHeight: '85vh', overflow: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>{detail.month_label} Payslip</h2>
              <button onClick={() => setDetail(null)} style={{ background: 'none', border: 'none', fontSize: 18, cursor: 'pointer', color: '#94A3B8' }}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>Pay Period: {detail.pay_period}</div>

            {detail.working_days != null && (
              <div style={{ background: '#F8FAFC', borderRadius: 8, padding: '10px 14px', marginBottom: 16, display: 'flex', gap: 20, fontSize: 13 }}>
                <span>Working: <strong>{detail.working_days}d</strong></span>
                <span>Present: <strong>{detail.present_days}d</strong></span>
                <span>Leave: <strong>{detail.leave_days || 0}d</strong></span>
                <span>Holidays: <strong>{detail.holiday_days || 0}d</strong></span>
                <span style={{ color: detail.lop_days > 0 ? '#EF4444' : 'inherit' }}>LOP: <strong>{detail.lop_days || 0}d</strong></span>
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 12, color: '#059669', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Earnings</div>
                {Object.entries(detail.earnings || {}).map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #F1F5F9', fontSize: 13 }}>
                    <span style={{ color: k === 'Gross Salary' ? '#1e293b' : 'var(--text-secondary)', fontWeight: k === 'Gross Salary' ? 700 : 400 }}>{k}</span>
                    <span style={{ fontWeight: k === 'Gross Salary' ? 700 : 400 }}>{fmt(v)}</span>
                  </div>
                ))}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 12, color: '#EF4444', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Deductions</div>
                {Object.entries(detail.deductions || {}).map(([k, v]) => (
                  <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #F1F5F9', fontSize: 13 }}>
                    <span style={{ color: k === 'Total Deductions' ? '#1e293b' : 'var(--text-secondary)', fontWeight: k === 'Total Deductions' ? 700 : 400 }}>{k}</span>
                    <span style={{ color: '#EF4444', fontWeight: k === 'Total Deductions' ? 700 : 400 }}>{fmt(v)}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ background: '#F0FDF4', borderRadius: 10, padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 700, fontSize: 15, color: '#059669' }}>Net Pay</span>
              <span style={{ fontWeight: 800, fontSize: 22, color: '#059669' }}>{fmt(detail.net_salary)}</span>
            </div>

            <div style={{ marginTop: 16, textAlign: 'right' }}>
              <button
                onClick={() => downloadPdf(detail.run_id, detail.month_label)}
                disabled={downloading === detail.run_id}
                className="btn btn-primary"
                style={{ fontSize: 13 }}
              >
                {downloading === detail.run_id ? 'Downloading…' : 'Download PDF'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── YTD Tab ──────────────────────────────────────────────────────────────────
function YtdTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    employeePayrollApi.getYtdSummary()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading YTD summary…</div>;
  if (!data) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No YTD data available.</div>;

  return (
    <div>
      <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-muted)', fontWeight: 600 }}>
        Financial Year: {data.financial_year} · {data.months_paid} month(s) paid
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 14, marginBottom: 20 }}>
        {[
          { label: 'YTD Gross', value: fmt(data.total_gross), color: '#3B5BDB' },
          { label: 'YTD Net', value: fmt(data.total_net), color: '#10B981' },
          { label: 'TDS Deducted', value: fmt(data.total_tds), color: '#EF4444' },
          { label: 'PF Deducted', value: fmt(data.total_pf), color: '#F59E0B' },
        ].map(c => (
          <div key={c.label} className="card" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontWeight: 700, fontSize: 20, color: c.color }}>{c.value}</div>
          </div>
        ))}
      </div>

      {data.monthly_breakdown?.length > 0 && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Month</th>
                <th>Gross</th>
                <th>Deductions</th>
                <th>Net Pay</th>
              </tr>
            </thead>
            <tbody>
              {data.monthly_breakdown.map((m, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{m.month_label}</td>
                  <td>{fmt(m.gross)}</td>
                  <td style={{ color: '#EF4444' }}>{fmt(m.deductions)}</td>
                  <td style={{ fontWeight: 700, color: '#10B981' }}>{fmt(m.net)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Reimbursements Tab ───────────────────────────────────────────────────────
function ReimbursementsTab() {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ claim_type: 'Travel', claim_amount: '', description: '', is_taxable: false });
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    employeePayrollApi.listReimbursements()
      .then(setClaims)
      .catch(() => setClaims([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const submit = () => {
    if (!form.claim_amount || parseFloat(form.claim_amount) <= 0) return;
    setSubmitting(true);
    employeePayrollApi.submitReimbursement({ ...form, claim_amount: parseFloat(form.claim_amount) })
      .then(() => { setShowForm(false); setForm({ claim_type: 'Travel', claim_amount: '', description: '', is_taxable: false }); load(); })
      .catch(e => alert(e?.data?.detail || 'Failed to submit'))
      .finally(() => setSubmitting(false));
  };

  const STATUS_COLOR = { pending: '#F59E0B', manager_approved: '#3B5BDB', approved: '#10B981', paid: '#059669', rejected: '#EF4444', cancelled: '#94A3B8' };

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading claims…</div>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ New Claim'}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ padding: 20, marginBottom: 16, border: '1px solid #C7D2FE' }}>
          <h3 style={{ marginTop: 0, marginBottom: 16, fontSize: 15 }}>Submit Reimbursement Claim</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Claim Type</label>
              <select value={form.claim_type} onChange={e => setForm(f => ({ ...f, claim_type: e.target.value }))}
                style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                {['Travel', 'Internet', 'Medical', 'Food', 'Equipment', 'Other'].map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Amount (₹)</label>
              <input type="number" value={form.claim_amount} onChange={e => setForm(f => ({ ...f, claim_amount: e.target.value }))}
                placeholder="0.00" min="0"
                style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid #E2E8F0', boxSizing: 'border-box' }} />
            </div>
            <div style={{ gridColumn: '1/-1' }}>
              <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Description</label>
              <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Brief description of the expense"
                style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid #E2E8F0', boxSizing: 'border-box' }} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="checkbox" checked={form.is_taxable} onChange={e => setForm(f => ({ ...f, is_taxable: e.target.checked }))} />
              <label style={{ fontSize: 13 }}>This reimbursement is taxable</label>
            </div>
          </div>
          <div style={{ marginTop: 14, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
            <button className="btn btn-primary" onClick={submit} disabled={submitting}>
              {submitting ? 'Submitting…' : 'Submit Claim'}
            </button>
          </div>
        </div>
      )}

      {claims.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>💼</div>
          <p>No reimbursement claims yet. Click "New Claim" to submit one.</p>
        </div>
      ) : (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Claimed</th>
                <th>Approved</th>
                <th>Status</th>
                <th>Description</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {claims.map(c => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 600 }}>{c.claim_type}</td>
                  <td>{fmt(c.claim_amount)}</td>
                  <td style={{ color: '#10B981', fontWeight: c.approved_amount > 0 ? 600 : 400 }}>
                    {c.approved_amount > 0 ? fmt(c.approved_amount) : '—'}
                  </td>
                  <td>
                    <span style={{ background: `${STATUS_COLOR[c.status]}20`, color: STATUS_COLOR[c.status] || '#94A3B8', borderRadius: 99, padding: '2px 10px', fontSize: 11, fontWeight: 700 }}>
                      {(c.status || '').replace(/_/g, ' ').replace(/\b\w/g, x => x.toUpperCase())}
                    </span>
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {c.description || '—'}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    {c.created_at ? new Date(c.created_at).toLocaleDateString('en-IN') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Salary Structure Tab ─────────────────────────────────────────────────────
function SalaryStructureTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    employeePayrollApi.getSalaryStructure()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading salary structure…</div>;

  if (!data) {
    return (
      <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>💼</div>
        <p>No salary structure assigned yet. Contact HR for details.</p>
      </div>
    );
  }

  const earnings = [
    { label: 'Basic',                  value: data.basic },
    { label: 'HRA',                    value: data.hra },
    { label: 'DA (Dearness Allowance)',value: data.da },
    { label: 'LTA',                    value: data.lta },
    { label: 'Special Allowance',      value: data.special_allowance },
    { label: 'Transport Allowance',    value: data.transport_allowance },
    { label: 'Medical Allowance',      value: data.medical_allowance },
    { label: 'Other Allowances',       value: data.other_allowances },
  ].filter(r => r.value > 0);

  const deductions = [
    { label: 'PF (Employee)',          value: data.pf_employee },
    { label: 'Professional Tax (PT)',  value: data.professional_tax },
    { label: 'TDS (estimated monthly)',value: data.tds },
  ].filter(r => r.value > 0);

  const effectiveDate = data.effective_from
    ? new Date(data.effective_from).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
    : '—';
  const revisedDate = data.last_revised
    ? new Date(data.last_revised).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
    : '—';

  return (
    <div>
      {/* Top CTC / Net summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14, marginBottom: 20 }}>
        {[
          { label: 'Annual CTC',            value: fmt(data.annual_ctc),    color: '#3B5BDB' },
          { label: 'Monthly Gross',         value: fmt(data.gross_monthly), color: '#0EA5E9' },
          {
            label: 'Net Monthly Take Home',
            value: data.net_monthly != null ? fmt(data.net_monthly) : '—',
            color: data.net_monthly != null ? '#10B981' : '#94A3B8',
          },
        ].map(c => (
          <div key={c.label} className="card" style={{ padding: '14px 16px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontWeight: 700, fontSize: 20, color: c.color }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Earnings & Deductions breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        {/* Earnings */}
        <div className="card" style={{ padding: '16px 20px' }}>
          <div style={{ fontWeight: 700, fontSize: 12, color: '#059669', marginBottom: 12,
            textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Earnings (Monthly)
          </div>
          {earnings.map(r => (
            <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between',
              padding: '6px 0', borderBottom: '1px solid #F1F5F9', fontSize: 13 }}>
              <span style={{ color: 'var(--text-secondary)' }}>{r.label}</span>
              <span style={{ fontWeight: 600 }}>{fmt(r.value)}</span>
            </div>
          ))}
          <div style={{ display: 'flex', justifyContent: 'space-between',
            padding: '8px 0', fontSize: 13, fontWeight: 700, marginTop: 4 }}>
            <span>Gross Monthly</span>
            <span style={{ color: '#059669' }}>{fmt(data.gross_monthly)}</span>
          </div>
        </div>

        {/* Deductions */}
        <div className="card" style={{ padding: '16px 20px' }}>
          <div style={{ fontWeight: 700, fontSize: 12, color: '#EF4444', marginBottom: 12,
            textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Deductions (Monthly)
          </div>
          {deductions.length > 0 ? deductions.map(r => (
            <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between',
              padding: '6px 0', borderBottom: '1px solid #F1F5F9', fontSize: 13 }}>
              <span style={{ color: 'var(--text-secondary)' }}>{r.label}</span>
              <span style={{ fontWeight: 600, color: '#EF4444' }}>{fmt(r.value)}</span>
            </div>
          )) : (
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>No statutory deductions on record.</div>
          )}
          {deductions.length > 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between',
              padding: '8px 0', fontSize: 13, fontWeight: 700, marginTop: 4 }}>
              <span>Total Deductions</span>
              <span style={{ color: '#EF4444' }}>{fmt(data.total_deductions)}</span>
            </div>
          )}

          {/* Net Take Home */}
          <div style={{
            background: data.net_monthly != null ? '#F0FDF4' : '#F8FAFC',
            borderRadius: 10, padding: '12px 14px',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16,
          }}>
            <span style={{ fontWeight: 700, fontSize: 13, color: data.net_monthly != null ? '#059669' : '#94A3B8' }}>Net Take Home</span>
            <span style={{ fontWeight: 800, fontSize: 18, color: data.net_monthly != null ? '#059669' : '#94A3B8' }}>
              {data.net_monthly != null ? fmt(data.net_monthly) : 'Available after first payroll run'}
            </span>
          </div>
        </div>
      </div>

      {/* Effective & Revision dates */}
      <div className="card" style={{ padding: '12px 18px', display: 'flex', gap: 40, fontSize: 13 }}>
        <div>
          <span style={{ color: 'var(--text-muted)', marginRight: 8 }}>Effective From:</span>
          <strong>{effectiveDate}</strong>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)', marginRight: 8 }}>Last Revised:</span>
          <strong>{revisedDate}</strong>
        </div>
        <div style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic' }}>
          Read-only — contact HR to request revisions
        </div>
      </div>
    </div>
  );
}

// ─── Attendance Used for Payroll Tab ──────────────────────────────────────────
function AttendanceForPayrollTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    employeePayrollApi.getAttendanceSummary()
      .then(d => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading attendance…</div>;

  if (rows.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
        <div style={{ fontSize: 40, marginBottom: 12 }}>📅</div>
        <p>No attendance summary available yet.</p>
        <p style={{ fontSize: 12, marginTop: 8 }}>HR will populate this after each month is finalised for payroll.</p>
      </div>
    );
  }

  const ATT_STATUS_COLOR = {
    pending:   { bg: '#FEF3C720', color: '#D97706' },
    submitted: { bg: '#DBEAFE20', color: '#3B82F6' },
    validated: { bg: '#D1FAE520', color: '#059669' },
    finalized: { bg: '#D1FAE520', color: '#059669' },
    issues:    { bg: '#FEE2E220', color: '#EF4444' },
  };
  const TS_STATUS_COLOR = {
    pending:   { bg: '#FEF3C720', color: '#D97706' },
    submitted: { bg: '#DBEAFE20', color: '#3B82F6' },
    approved:  { bg: '#D1FAE520', color: '#059669' },
  };

  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12 }}>
        Showing up to 24 months. Data is populated by HR after attendance is reviewed.
      </div>
      <div className="card">
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Month</th>
                <th>Working Days</th>
                <th>Present</th>
                <th>Leave</th>
                <th>LOP</th>
                <th>Payable Days</th>
                <th>Attendance Status</th>
                <th>Payroll Freeze</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const attStyle = ATT_STATUS_COLOR[r.attendance_status] || { bg: '#F1F5F920', color: '#64748B' };
                return (
                  <tr key={`${r.year}-${r.month}`}>
                    <td style={{ fontWeight: 600 }}>{r.month_label}</td>
                    <td>{r.working_days}</td>
                    <td style={{ color: '#059669', fontWeight: 600 }}>{r.present_days}</td>
                    <td>{r.leave_days}</td>
                    <td style={{ color: r.lop_days > 0 ? '#EF4444' : 'inherit', fontWeight: r.lop_days > 0 ? 700 : 400 }}>
                      {r.lop_days}
                    </td>
                    <td style={{ fontWeight: 600 }}>{r.payable_days}</td>
                    <td>
                      <span style={{
                        background: attStyle.bg, color: attStyle.color,
                        borderRadius: 99, padding: '2px 10px', fontSize: 11, fontWeight: 700,
                      }}>
                        {(r.attendance_status || 'pending').replace(/\b\w/g, c => c.toUpperCase())}
                      </span>
                    </td>
                    <td>
                      {r.is_frozen ? (
                        <span style={{ background: '#D1FAE520', color: '#059669', borderRadius: 99,
                          padding: '2px 10px', fontSize: 11, fontWeight: 700 }}>
                          🔒 Frozen
                        </span>
                      ) : (
                        <span style={{ background: '#F1F5F920', color: '#94A3B8', borderRadius: 99,
                          padding: '2px 10px', fontSize: 11, fontWeight: 700 }}>
                          Open
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── Tax Declaration Tab ──────────────────────────────────────────────────────
function TaxDeclarationTab() {
  const [decls, setDecls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    sec_80c: 0, sec_80d: 0, sec_80ccd: 0, hra_exemption: 0,
    sec_24b: 0, other_deductions: 0, opted_new_regime: false, submit_proof: false,
  });
  const [saving, setSaving] = useState(false);

  const load = () => {
    employeePayrollApi.listTaxDeclarations()
      .then(d => {
        setDecls(d);
        if (d.length > 0) {
          const current = d[0];
          setForm({
            sec_80c: current.sec_80c || 0,
            sec_80d: current.sec_80d || 0,
            sec_80ccd: current.sec_80ccd || 0,
            hra_exemption: current.hra_exemption || 0,
            sec_24b: current.sec_24b || 0,
            other_deductions: current.other_deductions || 0,
            opted_new_regime: current.opted_new_regime || false,
            submit_proof: false,
          });
        }
      })
      .catch(() => setDecls([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const save = () => {
    setSaving(true);
    employeePayrollApi.upsertTaxDeclaration(form)
      .then(() => { setEditing(false); load(); })
      .catch(e => alert(e?.data?.detail || 'Failed to save declaration'))
      .finally(() => setSaving(false));
  };

  const current = decls[0];

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>Loading declarations…</div>;

  const FIELDS = [
    { key: 'sec_80c', label: '80C — PPF, ELSS, LIC, PF', max: 150000 },
    { key: 'sec_80d', label: '80D — Health Insurance', max: 25000 },
    { key: 'sec_80ccd', label: '80CCD(1B) — NPS', max: 50000 },
    { key: 'hra_exemption', label: 'HRA Exemption (rent receipts)', max: null },
    { key: 'sec_24b', label: '24(b) — Home Loan Interest', max: 200000 },
    { key: 'other_deductions', label: 'Other Deductions', max: null },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15 }}>Tax Declaration</div>
          {current && (
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              FY {current.financial_year} ·{' '}
              {current.proof_verified
                ? <Badge color="#059669" bg="#D1FAE5">Proof Verified ✓</Badge>
                : current.proof_submitted
                ? <Badge color="#D97706" bg="#FEF3C7">Proof Submitted</Badge>
                : <Badge color="#94A3B8" bg="#F1F5F9">Proof Pending</Badge>}
            </div>
          )}
        </div>
        {!editing && !current?.proof_verified && (
          <button className="btn btn-primary" onClick={() => setEditing(true)}>
            {current ? 'Edit Declaration' : 'Submit Declaration'}
          </button>
        )}
      </div>

      {editing ? (
        <div className="card" style={{ padding: 20 }}>
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 14 }}>
              <input type="checkbox" checked={form.opted_new_regime}
                onChange={e => setForm(f => ({ ...f, opted_new_regime: e.target.checked }))} />
              <span>Opt for <strong>New Tax Regime</strong> (Budget 2024 — no deductions, lower slabs)</span>
            </label>
          </div>

          {!form.opted_new_regime && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
              {FIELDS.map(f => (
                <div key={f.key}>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
                    {f.label}{f.max ? ` (max ₹${f.max.toLocaleString('en-IN')})` : ''}
                  </label>
                  <input type="number" value={form[f.key]} min="0" max={f.max || undefined}
                    onChange={e => setForm(ff => ({ ...ff, [f.key]: parseFloat(e.target.value) || 0 }))}
                    style={{ width: '100%', padding: '8px 10px', borderRadius: 8, border: '1px solid #E2E8F0', boxSizing: 'border-box' }} />
                </div>
              ))}
            </div>
          )}

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={form.submit_proof}
                onChange={e => setForm(f => ({ ...f, submit_proof: e.target.checked }))} />
              <span>I confirm proofs are submitted to HR (marks proof as submitted)</span>
            </label>
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-ghost" onClick={() => setEditing(false)}>Cancel</button>
            <button className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save Declaration'}
            </button>
          </div>
        </div>
      ) : current ? (
        <div className="card" style={{ padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 0 }}>
            <div style={{ padding: '8px 12px', background: '#F8FAFC', borderRadius: '8px 0 0 0', fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>Tax Regime</div>
            <div style={{ padding: '8px 12px', fontSize: 13, fontWeight: 700, color: current.opted_new_regime ? '#059669' : '#3B5BDB' }}>
              {current.opted_new_regime ? 'New Regime' : 'Old Regime'}
            </div>
            {FIELDS.map((f, i) => (
              <>
                <div key={`l${f.key}`} style={{ padding: '8px 12px', background: i % 2 === 0 ? '#F8FAFC' : '#fff', fontSize: 12, color: 'var(--text-muted)' }}>{f.label}</div>
                <div key={`v${f.key}`} style={{ padding: '8px 12px', background: i % 2 === 0 ? '#F8FAFC' : '#fff', fontSize: 13, fontWeight: current[f.key] > 0 ? 600 : 400 }}>
                  {current[f.key] > 0 ? `₹${Number(current[f.key]).toLocaleString('en-IN')}` : '—'}
                </div>
              </>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📋</div>
          <p>No declaration submitted yet. Click "Submit Declaration" to declare your investments for TDS computation.</p>
        </div>
      )}
    </div>
  );
}

function PayrollStatusCard() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    employeePayrollApi.getPayrollStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  if (!status) return null;

  if (status.payroll_cycle_started === false) {
    return (
      <div style={{
        background: '#F8FAFC',
        border: '1px solid #E2E8F0',
        borderRadius: 12,
        padding: '14px 20px',
        marginBottom: 20,
        display: 'flex',
        flexWrap: 'wrap',
        gap: 16,
        alignItems: 'center',
      }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.06em', marginRight: 4 }}>
          Current Payroll Status
        </div>
        <div style={{ fontWeight: 700, fontSize: 14, color: '#334155' }}>
          {status.message || 'No payroll cycle started yet.'}
        </div>
      </div>
    );
  }

  const attLabel = status.attendance_frozen
    ? 'Finalized'
    : (status.attendance_status || 'not_available')
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());

  const statusItems = [
    (status.net_monthly != null || status.gross_monthly != null) && {
      label: 'Salary',
      value: status.net_monthly != null
        ? fmt(status.net_monthly)
        : `${fmt(status.gross_monthly)} (est.)`,
      color: '#10B981',
    },
    {
      label: 'Payroll Month',
      value: status.payroll_month || '—',
      color: '#1e293b',
    },
    {
      label: 'Attendance',
      value: attLabel,
      color: status.attendance_frozen ? '#059669' : '#D97706',
    },
    status.payslip_status && {
      label: 'Payslip',
      value: status.payslip_status === 'published'
        ? `Published (${status.latest_payslip_month || status.payroll_month})`
        : status.payslip_status === 'generated'
          ? 'Generated'
          : 'Pending',
      color: status.payslip_status === 'published'
        ? '#059669'
        : status.payslip_status === 'generated'
          ? '#0F766E'
          : '#94A3B8',
    },
  ].filter(Boolean);

  return (
    <div style={{
      background: 'linear-gradient(135deg, #EFF6FF 0%, #F0FDF4 100%)',
      border: '1px solid #BFDBFE',
      borderRadius: 12,
      padding: '14px 20px',
      marginBottom: 20,
      display: 'flex',
      flexWrap: 'wrap',
      gap: 28,
      alignItems: 'center',
    }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: '#3B5BDB', textTransform: 'uppercase', letterSpacing: '0.06em', marginRight: 4 }}>
        Current Payroll Status
      </div>

      {statusItems.map(item => (
        <div key={item.label}>
          <div style={{ fontSize: 10, color: '#94A3B8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {item.label}
          </div>
          <div style={{ fontWeight: 700, fontSize: 14, color: item.color, marginTop: 2 }}>
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Main PayrollPage ─────────────────────────────────────────────────────────
// Tabs: Payslips | Salary Structure | Reimbursements | Tax Declaration
// (YTD Summary and Attendance tabs have been removed from the employee view)
const TABS = ['Payslips', 'Salary Structure', 'Reimbursements', 'Tax Declaration'];

export default function PayrollPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [tab, setTab] = useState('Payslips');
  const isAdminSelfPayroll = location.pathname.startsWith('/admin-dashboard/my-payroll');
  const backToPayrollDashboard = location.state?.fromPayrollDashboard || isAdminSelfPayroll
    ? location.state?.backTo || '/admin-dashboard/payroll'
    : null;
  const payrollDashboardState = location.state?.payrollDashboardState || {};

  const handleBackToPayrollDashboard = () => {
    if (!backToPayrollDashboard) return;
    navigate(backToPayrollDashboard, {
      state: { payrollDashboardState },
    });
  };

  return (
    <div className="fade-in">
      <div className="page-header" style={{ marginBottom: 20 }}>
        {backToPayrollDashboard && (
          <button
            type="button"
            onClick={handleBackToPayrollDashboard}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              marginBottom: 10,
              padding: 0,
              border: 'none',
              background: 'transparent',
              color: '#64748B',
              fontSize: 16,
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            <span aria-hidden="true" style={{ fontSize: 22, lineHeight: 1 }}>&lsaquo;</span>
            <span>Back to Payroll Dashboard</span>
          </button>
        )}
        <h1 style={{ margin: 0 }}>My Payroll</h1>
        <p style={{ margin: '4px 0 0', color: 'var(--text-muted)', fontSize: 13 }}>
          Download payslips, view your salary structure, manage reimbursements and tax declarations.
        </p>
      </div>

      {/* Current Payroll Status header card */}
      <PayrollStatusCard />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, background: '#F8FAFC', borderRadius: 10, padding: 4, width: 'fit-content', flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <Tab key={t} active={tab === t} onClick={() => setTab(t)}>{t}</Tab>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'Payslips'         && <PayslipsTab />}
      {tab === 'Salary Structure' && <SalaryStructureTab />}
      {tab === 'Reimbursements'   && <ReimbursementsTab />}
      {tab === 'Tax Declaration'  && <TaxDeclarationTab />}

    </div>
  );
}
