import { useEffect, useMemo, useRef, useState } from 'react';
import Modal from '../../../components/Modal';
import PageHeader from '../../../components/PageHeader';
import Toast from '../../../components/Timesheets/Toast';
import { employeesApi } from '../../../services/employees';
import {
  pmsApi,
  PMS_STATUS, PMS_STATUS_LABEL, MCR_STATUS, MCR_STATUS_LABEL, MCR_STATUS_TONE,
  ECA_STATUS, ECA_STATUS_LABEL, ECA_STATUS_TONE,
  NORM_STATUS, NORM_STATUS_LABEL, NORM_STATUS_TONE, RATING_LABELS,
  isAutoLocked,
} from '../../../services/pms';
import GoalDetailDrawer from './GoalDetailDrawer';
import MidCycleReviewDrawer from './MidCycleReviewDrawer';
import EndCycleAssessmentDrawer from './EndCycleAssessmentDrawer';

// HR-side hub for PMS Phase 1.
// Visual language matches the admin leave/approvals pages:
//   • PageHeader for the top
//   • White cards w/ rounded-xl + slate-100 borders + soft shadow
//   • Pill chips for status, blue accents for primary actions
//   • Tailwind throughout (no inline styles)

const TABS = [
  { id: 'my-goals',       label: 'My Goals'             },
  { id: 'templates',      label: 'Goal Templates'       },
  { id: 'assignments',    label: 'Goal Assignment'      },
  { id: 'locking',        label: 'Goal Locking'         },
  { id: 'mid-cycle',      label: 'Mid-Cycle Review'     },
  { id: 'end-cycle',      label: 'End Cycle Assessment' },
  { id: 'normalization',  label: 'Normalization'        },
  { id: 'compensation',   label: 'Compensation'         },
];

const STATUS_TONE = {
  draft:              'bg-slate-100 text-slate-600',
  goals_sent:         'bg-blue-50 text-blue-700',
  under_discussion:   'bg-amber-50 text-amber-700',
  employee_confirmed: 'bg-indigo-50 text-indigo-700',
  manager_approved:   'bg-emerald-50 text-emerald-700',
  hr_reviewed:        'bg-cyan-50 text-cyan-700',
  goals_locked:       'bg-rose-50 text-rose-700',
};

export function StatusPill({ status }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ${STATUS_TONE[status] || 'bg-slate-100 text-slate-600'}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {PMS_STATUS_LABEL[status] || status}
    </span>
  );
}

export default function PerformanceHubPage() {
  const [tab, setTab] = useState('templates');

  return (
    <div>
      <PageHeader
        title="Performance Management"
        subtitle="Author goal templates, send them to employees, and lock final goals."
      />

      <div className="mb-6 flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={
                'px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors ' +
                (active
                  ? 'text-blue-700 border-blue-600'
                  : 'text-slate-500 border-transparent hover:text-slate-700 hover:border-slate-200')
              }
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'my-goals'      && <MyGoalsTab />}
      {tab === 'templates'     && <TemplatesTab />}
      {tab === 'assignments'   && <AssignmentsTab />}
      {tab === 'locking'       && <LockingTab />}
      {tab === 'mid-cycle'     && <MidCycleTab />}
      {tab === 'end-cycle'     && <EndCycleTab />}
      {tab === 'normalization' && <NormalizationTab />}
      {tab === 'compensation'  && <CompensationTab />}
    </div>
  );
}


// ── Toast / Confirm utilities ──────────────────────────────────────

function usePmsToast() {
  const [state, setState] = useState(null);
  const toast = (msg, type = 'success') => setState({ msg, type });
  const el = state ? (
    <Toast message={state.msg} type={state.type} onClose={() => setState(null)} />
  ) : null;
  return [toast, el];
}

function useConfirm() {
  const [state, setState] = useState(null);
  const confirm = (msg, onYes) => setState({ msg, onYes });
  const el = state ? (
    <ConfirmModal
      msg={state.msg}
      onYes={() => { const fn = state.onYes; setState(null); fn(); }}
      onNo={() => setState(null)}
    />
  ) : null;
  return [confirm, el];
}

function ConfirmModal({ msg, onYes, onNo }) {
  return (
    <Modal title="Confirm" onClose={onNo} width="max-w-sm">
      <p className="py-2 text-sm text-slate-700">{msg}</p>
      <div className="-mx-6 -mb-5 mt-4 flex justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-6 py-4">
        <button type="button" onClick={onNo}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50">
          Cancel
        </button>
        <button type="button" onClick={onYes}
          className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-700">
          Confirm
        </button>
      </div>
    </Modal>
  );
}

// ── Import Selection Dialog (Change 1) ─────────────────────────────

function ImportSelectionDialog({ designations, selected, onToggle, onToggleAll, onConfirm, onClose }) {
  const allSelected = selected.size === designations.length && designations.length > 0;
  return (
    <Modal title="Select Templates to Import" onClose={onClose} width="max-w-2xl">
      <p className="mb-4 text-sm text-slate-500">
        Choose which templates to create. Unselected templates will be skipped.
      </p>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500">
          {selected.size} of {designations.length} selected
        </span>
        <button type="button" onClick={onToggleAll}
          className="text-xs font-semibold text-blue-700 hover:underline">
          {allSelected ? 'Deselect All' : 'Select All'}
        </button>
      </div>
      <div className="max-h-80 overflow-y-auto rounded-xl border border-slate-200">
        {designations.map((d, idx) => {
          const kraCount = (d.kras || []).length;
          const kpiCount = (d.kras || []).reduce((n, k) => n + (k.kpis?.length || 0), 0);
          const checked = selected.has(idx);
          return (
            <label key={idx}
              className="flex cursor-pointer items-start gap-3 border-b border-slate-100 px-4 py-3 last:border-b-0 transition hover:bg-blue-50/40">
              <input type="checkbox" checked={checked} onChange={() => onToggle(idx)}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-500" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-800">
                  {d.designation_name || d.name || 'Unnamed'}
                </p>
                {d.designation_id && (
                  <p className="text-xs text-slate-400">ID: {d.designation_id}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                  {kraCount} KRA{kraCount !== 1 ? 's' : ''}
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-violet-50 px-2 py-0.5 text-xs font-semibold text-violet-700">
                  {kpiCount} KPI{kpiCount !== 1 ? 's' : ''}
                </span>
              </div>
            </label>
          );
        })}
      </div>
      <div className="-mx-6 -mb-5 mt-5 flex justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-6 py-4">
        <button type="button" onClick={onClose}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50">
          Cancel
        </button>
        <button type="button" onClick={onConfirm} disabled={selected.size === 0}
          className="inline-flex items-center gap-1.5 rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800 disabled:opacity-50">
          Import {selected.size} Template{selected.size !== 1 ? 's' : ''}
        </button>
      </div>
    </Modal>
  );
}


// ── My Goals ───────────────────────────────────────────────────────


function MyGoalsTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState(null);

  const load = () => {
    setLoading(true);
    pmsApi.assignments({ scope: 'employee' })
      .then((data) => setRows(Array.isArray(data) ? data : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  return (
    <div>
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
      )}
      {!loading && rows.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center">
          <p className="text-sm font-semibold text-slate-700">No goals assigned to you</p>
          <p className="mt-1 text-xs text-slate-400">Goals assigned to you by HR will appear here.</p>
        </div>
      )}
      {!loading && rows.map((a) => {
        const kraCount = (a.kras || []).length;
        const kpiCount = (a.kras || []).reduce((n, k) => n + (k.kpis?.length || 0), 0);
        return (
          <div
            key={a.id}
            onClick={() => setDrawer(a)}
            className="mb-3 cursor-pointer rounded-xl border border-slate-100 bg-white p-4 shadow-sm transition hover:border-violet-200 hover:bg-violet-50/20"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-slate-800">
                  {a.period || 'No period'}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">
                  {a.manager_name ? `Manager: ${a.manager_name}` : 'No manager assigned'}
                </p>
              </div>
              <StatusPill status={a.status} />
            </div>
            <div className="mt-3 flex items-center gap-4 text-xs text-slate-500">
              <span>{kraCount} KRA{kraCount !== 1 ? 's' : ''}</span>
              <span>{kpiCount} KPI{kpiCount !== 1 ? 's' : ''}</span>
              <span>{(a.competencies || []).length} Competencies</span>
            </div>
            <div className="mt-3 flex justify-end border-t border-slate-100 pt-3">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setDrawer(a); }}
                className="inline-flex items-center gap-1 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-violet-700"
              >
                Open
              </button>
            </div>
          </div>
        );
      })}

      {drawer && (
        <GoalDetailDrawer
          assignment={drawer}
          viewerRole="employee"
          onClose={() => setDrawer(null)}
          onChanged={() => { load(); setDrawer(null); }}
        />
      )}
    </div>
  );
}


// ── Templates ──────────────────────────────────────────────────────


function TemplatesTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');
  // Import flow state
  const [importedDesignations, setImportedDesignations] = useState(null);
  const [importWarnings, setImportWarnings] = useState([]);
  const [importMeta, setImportMeta] = useState(null);
  const [importing, setImporting] = useState(false);
  // Import selection dialog state (Change 1)
  const [importSelectionData, setImportSelectionData] = useState(null);
  const [importSelected, setImportSelected] = useState(new Set());
  const fileInputRef = useRef(null);

  const [toast, toastEl] = usePmsToast();
  const [confirm, confirmEl] = useConfirm();

  const load = () => {
    setLoading(true);
    pmsApi.templates()
      .then((data) => setRows(Array.isArray(data) ? data : []))
      .catch((e) => setError(e?.data?.detail || e?.message || 'Failed to load templates'))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const save = async (payload, id) => {
    try {
      if (id) await pmsApi.updateTemplate(id, payload);
      else    await pmsApi.createTemplate(payload);
      setEditing(null);
      load();
    } catch (e) {
      toast(e?.data?.detail || e?.message || 'Save failed', 'error');
    }
  };

  // Called from TemplateEditor when saving an imported multi-designation set.
  const saveImport = async (allDesignations) => {
    try {
      const result = await pmsApi.importCommit({
        period: importMeta?.period || null,
        source_filename: importMeta?.source_filename || 'upload.xlsx',
        designations: allDesignations.map((d) => ({
          designation_name: d.designation_name || d.name || '',
          designation_id: d.designation_id || null,
          name: d.name || d.designation_name || '',
          description: d.description || null,
          period: d.period || importMeta?.period || null,
          department_id: d.department_id || null,
          role_id: d.role_id ? Number(d.role_id) : null,
          is_active: d.is_active !== false,
          kras: Array.isArray(d.kras) ? d.kras : [],
          competencies: Array.isArray(d.competencies) ? d.competencies : [],
        })),
        warnings: Array.isArray(importWarnings) ? importWarnings : [],
      });
      setEditing(null);
      setImportedDesignations(null);
      setImportWarnings([]);
      setImportMeta(null);
      load();
      const count = Array.isArray(result) ? result.length : '?';
      toast(`${count} template(s) created from Excel import.`);
    } catch (e) {
      toast(e?.data?.detail || e?.message || 'Import commit failed', 'error');
    }
  };

  const remove = (id) => {
    confirm('Delete this template? Existing assignments are not affected.', async () => {
      try { await pmsApi.deleteTemplate(id); load(); }
      catch (e) { toast(e?.data?.detail || e?.message || 'Delete failed', 'error'); }
    });
  };

  const handleExport = async (t) => {
    const slug = (t.name || 'template').replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '');
    const ver  = t.template_version || 1;
    const hint = slug + '_v' + ver + '.xlsx';
    try {
      await pmsApi.exportTemplate(t.id, hint);
    } catch (e) {
      toast(e?.message || 'Export failed', 'error');
    }
  };

  // Change 1: parse → show selection dialog → editor → commit
  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setImporting(true);
    try {
      const preview = await pmsApi.importPreview(file);
      const templates = Array.isArray(preview)
        ? preview
        : (preview?.designations || preview?.templates || []);
      const warnings = preview?.warnings || [];
      if (!templates.length) {
        toast('No designation columns with weights found in the workbook.', 'error');
        return;
      }
      // Show selection dialog with all templates pre-selected.
      setImportSelectionData({
        designations: templates,
        warnings,
        meta: {
          period: preview?.period || null,
          source_filename: preview?.source_filename || file.name || 'upload.xlsx',
        },
      });
      setImportSelected(new Set(templates.map((_, i) => i)));
    } catch (e) {
      toast(e?.data?.detail || e?.message || 'Preview failed — check the file format.', 'error');
    } finally {
      setImporting(false);
    }
  };

  const proceedWithImport = () => {
    if (!importSelectionData) return;
    const chosen = importSelectionData.designations.filter((_, i) => importSelected.has(i));
    setImportSelectionData(null);
    setImportedDesignations(chosen);
    setImportWarnings(importSelectionData.warnings);
    setImportMeta(importSelectionData.meta);
    setEditing({ __import: true });
  };

  return (
    <div>
      {/* Hidden file input for Excel import */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx"
        className="hidden"
        onChange={handleFileSelect}
      />

      <div className="mb-5 flex items-center justify-between gap-3">
        <p className="text-sm text-slate-500">
          {rows.length} template{rows.length === 1 ? '' : 's'}
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={importing}
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-60"
          >
            {importing ? (
              <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M21 12a9 9 0 11-6.219-8.56"/></svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            )}
            {importing ? 'Parsing…' : 'Import from Excel'}
          </button>
          <button
            type="button"
            onClick={() => setEditing({ __new: true })}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Template
          </button>
        </div>
      </div>

      {loading && <SkeletonGrid count={3} />}
      {error && <p className="rounded-lg bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">{error}</p>}

      {!loading && rows.length === 0 && !error && (
        <EmptyState
          title="No templates yet"
          description="Create your first goal template to start assigning goals."
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((t) => (
          <div
            key={t.id}
            className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-blue-300 hover:shadow-md"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <h3 className="text-base font-semibold text-slate-900 truncate">{t.name}</h3>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  {t.period && (
                    <span className="inline-flex items-center rounded-md bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                      {t.period}
                    </span>
                  )}
                  {t.imported_from_excel && (
                    <span className="inline-flex items-center rounded-md bg-violet-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-violet-700">
                      Imported
                    </span>
                  )}
                  <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">
                    v{t.template_version || 1}
                  </span>
                </div>
              </div>
              <span
                className={
                  'inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ' +
                  (t.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500')
                }
              >
                {t.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>

            {t.description && (
              <p className="mt-2 line-clamp-2 text-sm text-slate-500">{t.description}</p>
            )}

            <div className="mt-4 flex items-center gap-3 text-xs text-slate-500">
              <Metric label="KRAs"  value={(t.kras || []).length} />
              <span className="text-slate-300">·</span>
              <Metric label="KPIs"  value={(t.kras || []).reduce((n, k) => n + (k.kpis?.length || 0), 0)} />
              <span className="text-slate-300">·</span>
              <Metric label="Comp." value={(t.competencies || []).length} />
            </div>

            <div className="mt-4 flex gap-2 border-t border-slate-100 pt-3">
              <button
                type="button"
                onClick={() => setEditing(t)}
                className="flex-1 rounded-lg bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-700 transition hover:bg-blue-100"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => handleExport(t)}
                className="rounded-lg bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-200"
                title="Export as Excel"
              >
                Export
              </button>
              <button
                type="button"
                onClick={() => remove(t.id)}
                className="rounded-lg bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 transition hover:bg-rose-100"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {editing && !editing.__import && (
        <TemplateEditor
          template={editing.__new ? null : editing}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}

      {editing?.__import && importedDesignations && (
        <TemplateEditor
          template={null}
          importedDesignations={importedDesignations}
          importWarnings={importWarnings}
          onClose={() => { setEditing(null); setImportedDesignations(null); setImportWarnings([]); setImportMeta(null); }}
          onSave={save}
          onSaveImport={saveImport}
        />
      )}

      {importSelectionData && (
        <ImportSelectionDialog
          designations={importSelectionData.designations}
          selected={importSelected}
          onToggle={(idx) => setImportSelected((s) => {
            const n = new Set(s);
            n.has(idx) ? n.delete(idx) : n.add(idx);
            return n;
          })}
          onToggleAll={() => setImportSelected((s) =>
            s.size === importSelectionData.designations.length
              ? new Set()
              : new Set(importSelectionData.designations.map((_, i) => i))
          )}
          onConfirm={proceedWithImport}
          onClose={() => setImportSelectionData(null)}
        />
      )}

      {toastEl}
      {confirmEl}
    </div>
  );
}


// Helper to coerce a parsed designation object into editor state fields.
function designationToEditorState(d) {
  return {
    name:          d.name || '',
    description:   d.description || '',
    period:        d.period || '',
    departmentId:  d.department_id || '',
    designationId: d.designation_id || '',
    roleId:        d.role_id || '',
    isActive:      d.is_active !== false,
    kras: (d.kras || []).map((k) => ({
      title: k.title || '', description: k.description || '',
      weightage: k.weightage || 0, sort_order: k.sort_order || 0,
      kpis: (k.kpis || []).map((p) => ({
        title: p.title || '', description: p.description || '',
        weightage: p.weightage || 0,
      })),
    })),
    comps: (d.competencies || []).map((c) => ({
      title: c.title || '', description: c.description || '', weightage: c.weightage || 0,
    })),
  };
}

function TemplateEditor({ template, onClose, onSave, onSaveImport, importedDesignations, importWarnings }) {
  const isEdit = !!(template && template.id);
  // Import mode: managing N designation templates.
  const isImport = !!(importedDesignations && importedDesignations.length > 0);

  const [editorToast, editorToastEl] = usePmsToast();

  const [ref, setRef] = useState(null);
  useEffect(() => {
    employeesApi.reference().then(setRef).catch(() => setRef({ departments: [], designations: [], roles: [] }));
  }, []);

  // For import mode we keep a mutable copy of all designations and track which one is being reviewed.
  const [importIdx, setImportIdx] = useState(0);
  const [allDesignations, setAllDesignations] = useState(() =>
    isImport ? importedDesignations.map((d) => ({ ...d })) : [],
  );

  // Current template fields — sourced from import designation[importIdx] or from the passed template.
  const currentSource = isImport ? allDesignations[importIdx] : template;

  const [name, setName] = useState(currentSource?.name || '');
  const [description, setDescription] = useState(currentSource?.description || '');
  const [period, setPeriod] = useState(currentSource?.period || '');
  const [departmentId, setDepartmentId] = useState(currentSource?.department_id || '');
  const [designationId, setDesignationId] = useState(currentSource?.designation_id || '');
  const [roleId, setRoleId] = useState(currentSource?.role_id || '');
  const [isActive, setIsActive] = useState(currentSource ? !!currentSource.is_active : true);
  const [kras, setKras] = useState(() => {
    const src = isImport ? (allDesignations[0]?.kras || []) : (template?.kras || []);
    return src.map((k) => ({
      title: k.title, description: k.description || '', weightage: k.weightage || 0, sort_order: k.sort_order || 0,
      kpis: (k.kpis || []).map((p) => ({
        title: p.title, description: p.description || '',
        weightage: p.weightage || 0,
      })),
    }));
  });
  const [comps, setComps] = useState(() => {
    const src = isImport ? (allDesignations[0]?.competencies || []) : (template?.competencies || []);
    return src.map((c) => ({ title: c.title, description: c.description || '', weightage: c.weightage || 0 }));
  });
  const [saving, setSaving] = useState(false);

  // When switching designation in import mode, flush current edits into allDesignations then load the new one.
  const switchDesignation = (newIdx) => {
    if (!isImport) return;
    // Persist current edits.
    setAllDesignations((prev) => {
      const updated = [...prev];
      updated[importIdx] = {
        ...updated[importIdx],
        name, description, period,
        department_id: departmentId || null,
        designation_id: designationId || null,
        role_id: roleId ? Number(roleId) : null,
        is_active: isActive,
        kras: kras.map((k) => ({
          title: k.title, description: k.description || null,
          weightage: Number(k.weightage) || 0, sort_order: Number(k.sort_order) || 0,
          kpis: k.kpis.map((p) => ({
            title: p.title, description: p.description || null,
            weightage: Number(p.weightage) || 0,
          })),
        })),
        competencies: comps.map((c) => ({
          title: c.title, description: c.description || null, weightage: Number(c.weightage) || 0,
        })),
      };
      return updated;
    });
    // Load new designation's fields.
    const nd = allDesignations[newIdx];
    const s = designationToEditorState(nd);
    setName(s.name); setDescription(s.description); setPeriod(s.period);
    setDepartmentId(s.departmentId); setDesignationId(s.designationId);
    setRoleId(s.roleId); setIsActive(s.isActive);
    setKras(s.kras); setComps(s.comps);
    setImportIdx(newIdx);
  };

  const addKra = () => setKras((k) => [...k, { title: '', description: '', weightage: 0, sort_order: k.length, kpis: [] }]);
  const removeKra = (i) => setKras((k) => k.filter((_, idx) => idx !== i));
  const editKra = (i, patch) => setKras((k) => k.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  const addKpi = (i) => editKra(i, { kpis: [...kras[i].kpis, { title: '', description: '', weightage: 0 }] });
  const removeKpi = (i, j) => editKra(i, { kpis: kras[i].kpis.filter((_, idx) => idx !== j) });
  const editKpi = (i, j, patch) => editKra(i, { kpis: kras[i].kpis.map((p, idx) => (idx === j ? { ...p, ...patch } : p)) });
  const addComp = () => setComps((c) => [...c, { title: '', description: '', weightage: 0 }]);
  const removeComp = (i) => setComps((c) => c.filter((_, idx) => idx !== i));
  const editComp = (i, patch) => setComps((c) => c.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));

  const totalKraWeight = kras.reduce((n, k) => n + (Number(k.weightage) || 0), 0);
  const totalCompWeight = comps.reduce((n, c) => n + (Number(c.weightage) || 0), 0);

  // Build the payload for the current designation's edits.
  const buildCurrentPayload = () => ({
    name: name.trim(),
    description: description.trim() || null,
    period: period.trim() || null,
    department_id: departmentId || null,
    designation_id: designationId || null,
    role_id: roleId ? Number(roleId) : null,
    is_active: isActive,
    kras: kras.map((k) => ({
      title: k.title, description: k.description || null,
      weightage: Number(k.weightage) || 0, sort_order: Number(k.sort_order) || 0,
      kpis: k.kpis.map((p) => ({
        title: p.title, description: p.description || null,
        weightage: Number(p.weightage) || 0,
      })),
    })),
    competencies: comps.map((c) => ({
      title: c.title, description: c.description || null, weightage: Number(c.weightage) || 0,
    })),
  });

  const submit = async () => {
    if (!name.trim()) { editorToast('Template name is required.', 'error'); return; }
    setSaving(true);
    try {
      if (isImport) {
        // Flush current edits into allDesignations then commit all.
        const finalAll = allDesignations.map((d, idx) => {
          if (idx !== importIdx) return d;
          return { ...d, ...buildCurrentPayload() };
        });
        await onSaveImport(finalAll);
      } else {
        await onSave(buildCurrentPayload(), isEdit ? template.id : undefined);
      }
    } finally { setSaving(false); }
  };

  const modalTitle = isImport
    ? `Import from Excel (${importedDesignations.length} designation${importedDesignations.length === 1 ? '' : 's'})`
    : (isEdit ? 'Edit Template' : 'New Goal Template');

  return (
    <Modal title={modalTitle} onClose={onClose} width="max-w-4xl">
      {/* Import warnings banner */}
      {isImport && importWarnings && importWarnings.length > 0 && (
        <div className="mb-4 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3">
          <p className="mb-1 text-xs font-bold uppercase tracking-wider text-amber-700">Import Notices</p>
          <ul className="list-disc list-inside space-y-0.5">
            {importWarnings.map((w, i) => (
              <li key={i} className="text-xs text-amber-700">{w}</li>
            ))}
          </ul>
        </div>
      )}
      {/* Multi-designation notice + switcher */}
      {isImport && importedDesignations.length > 1 && (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3">
          <p className="text-xs font-semibold text-blue-700 flex-1">
            {importedDesignations.length} templates will be created — review each designation below before saving.
          </p>
          <div className="flex items-center gap-2">
            <label className="text-xs font-bold uppercase tracking-wider text-blue-600">Viewing:</label>
            <select
              value={importIdx}
              onChange={(e) => switchDesignation(Number(e.target.value))}
              className="rounded-lg border border-blue-300 bg-white px-3 py-1.5 text-sm font-semibold text-blue-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            >
              {importedDesignations.map((d, idx) => (
                <option key={idx} value={idx}>{d.designation_name || d.name || ('Designation ' + (idx + 1))}</option>
              ))}
            </select>
          </div>
        </div>
      )}
      {/* Meta */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField label="Name" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Engineering — Senior Engineer" />
        </FormField>
        <FormField label="Period" hint="e.g. FY2026-Q1">
          <Input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="FY2026" />
        </FormField>
        <FormField label="Department">
          <Select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
            <option value="">Any department</option>
            {(ref?.departments || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
        </FormField>
        <FormField label="Designation">
          <Select value={designationId} onChange={(e) => setDesignationId(e.target.value)}>
            <option value="">Any designation</option>
            {(ref?.designations || []).map((d) => <option key={d.id} value={d.id}>{d.name || d.title || d.id}</option>)}
          </Select>
        </FormField>
        <FormField label="Role">
          <Select value={roleId} onChange={(e) => setRoleId(e.target.value)}>
            <option value="">Any role</option>
            {(ref?.roles || []).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
        </FormField>
        <FormField label="Status">
          <Select value={isActive ? '1' : '0'} onChange={(e) => setIsActive(e.target.value === '1')}>
            <option value="1">Active</option>
            <option value="0">Inactive</option>
          </Select>
        </FormField>
      </div>
      <div className="mt-4">
        <FormField label="Description">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            placeholder="Optional context shared with managers and employees…"
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
          />
        </FormField>
      </div>

      {/* KRAs */}
      <SectionBlock
        title="Key Result Areas (KRAs)"
        meta={kras.length ? `${kras.length} KRA${kras.length === 1 ? '' : 's'} · Σ ${totalKraWeight}%` : 'No KRAs yet'}
        action={<AddButton onClick={addKra} label="Add KRA" />}
      >
        {kras.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-400">
            Add Key Result Areas to structure performance goals.
          </p>
        )}
        <div className="space-y-3">
          {kras.map((k, i) => (
            <div key={i} className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
              <div className="grid grid-cols-12 gap-2">
                <div className="col-span-12 sm:col-span-8">
                  <Input value={k.title} onChange={(e) => editKra(i, { title: e.target.value })} placeholder="KRA title (e.g. Deliver Q1 roadmap)" />
                </div>
                <div className="col-span-8 sm:col-span-3">
                  <div className="relative">
                    <Input type="number" value={k.weightage} onChange={(e) => editKra(i, { weightage: e.target.value })} placeholder="Weight" className="pr-7" />
                    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">%</span>
                  </div>
                </div>
                <div className="col-span-4 sm:col-span-1 flex justify-end">
                  <IconButton tone="danger" onClick={() => removeKra(i)} title="Remove KRA">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M6 6l1 14a2 2 0 002 2h6a2 2 0 002-2l1-14"/></svg>
                  </IconButton>
                </div>
              </div>
              <textarea
                value={k.description}
                onChange={(e) => editKra(i, { description: e.target.value })}
                rows={2}
                placeholder="Describe the outcome this KRA should achieve…"
                className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              />

              {/* KPIs */}
              <div className="mt-3">
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">KPIs</p>
                  <button type="button" onClick={() => addKpi(i)} className="text-xs font-semibold text-blue-700 hover:underline">+ Add KPI</button>
                </div>
                {k.kpis.length === 0 && (
                  <p className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-2 text-center text-xs text-slate-400">
                    No KPIs yet.
                  </p>
                )}
                <div className="space-y-2">
                  {k.kpis.map((p, j) => (
                    <div key={j} className="grid grid-cols-12 gap-2 rounded-lg bg-white p-2 ring-1 ring-slate-200">
                      <div className="col-span-12 sm:col-span-9"><Input value={p.title} onChange={(e) => editKpi(i, j, { title: e.target.value })} placeholder="KPI" /></div>
                      <div className="col-span-9 sm:col-span-2">
                        <div className="relative">
                          <Input type="number" value={p.weightage} onChange={(e) => editKpi(i, j, { weightage: e.target.value })} placeholder="Wt" className="pr-7" />
                          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">%</span>
                        </div>
                      </div>
                      <div className="col-span-3 sm:col-span-1 flex justify-end">
                        <IconButton tone="ghost" onClick={() => removeKpi(i, j)} title="Remove KPI">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </IconButton>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </SectionBlock>

      {/* Competencies */}
      <SectionBlock
        title="Competency Goals"
        meta={comps.length ? `${comps.length} item${comps.length === 1 ? '' : 's'} · Σ ${totalCompWeight}%` : 'No competencies yet'}
        action={<AddButton onClick={addComp} label="Add Competency" />}
      >
        {comps.length === 0 && (
          <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-400">
            Add competency goals (e.g. Collaboration, Ownership).
          </p>
        )}
        <div className="space-y-2">
          {comps.map((c, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 rounded-xl border border-slate-200 bg-slate-50/60 p-3">
              <div className="col-span-12 sm:col-span-3"><Input value={c.title} onChange={(e) => editComp(i, { title: e.target.value })} placeholder="Competency" /></div>
              <div className="col-span-12 sm:col-span-6"><Input value={c.description} onChange={(e) => editComp(i, { description: e.target.value })} placeholder="Description" /></div>
              <div className="col-span-9 sm:col-span-2">
                <div className="relative">
                  <Input type="number" value={c.weightage} onChange={(e) => editComp(i, { weightage: e.target.value })} placeholder="Weight" className="pr-7" />
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">%</span>
                </div>
              </div>
              <div className="col-span-3 sm:col-span-1 flex justify-end">
                <IconButton tone="danger" onClick={() => removeComp(i)} title="Remove competency">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </IconButton>
              </div>
            </div>
          ))}
        </div>
      </SectionBlock>

      {/* Footer */}
      <div className="-mx-6 -mb-5 mt-6 flex items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/60 px-6 py-4">
        <p className="text-xs text-slate-500">Weightage doesn't have to equal 100% — final weights are confirmed during discussion.</p>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50">Cancel</button>
          <button
            type="button"
            onClick={submit}
            disabled={saving}
            className="rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800 disabled:opacity-60"
          >
            {saving
              ? 'Saving…'
              : isImport
                ? `Create ${importedDesignations.length} Template${importedDesignations.length === 1 ? '' : 's'}`
                : (isEdit ? 'Save Changes' : 'Create Template')}
          </button>
        </div>
      </div>
      {editorToastEl}
    </Modal>
  );
}


// ── Assignments ────────────────────────────────────────────────────


function AssignmentsTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assignOpen, setAssignOpen] = useState(false);
  const [drawer, setDrawer] = useState(null);
  const [filter, setFilter] = useState('all');
  const [q, setQ] = useState('');

  const load = () => {
    setLoading(true);
    pmsApi.assignments({ scope: 'hr' })
      .then((data) => setRows(Array.isArray(data) ? data : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    let list = rows;
    if (filter === 'awaiting_hr') list = list.filter((r) => r.status === PMS_STATUS.MANAGER_APPROVED);
    else if (filter === 'in_progress') list = list.filter((r) => [
      PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION, PMS_STATUS.EMPLOYEE_CONFIRMED,
    ].includes(r.status));
    else if (filter === 'locked') list = list.filter((r) => r.status === PMS_STATUS.GOALS_LOCKED);
    const needle = q.trim().toLowerCase();
    if (needle) list = list.filter((r) => (r.employee_name || '').toLowerCase().includes(needle));
    return list;
  }, [rows, filter, q]);

  const tabs = [
    ['all',          'All',                 rows.length],
    ['in_progress',  'In Progress',         rows.filter((r) => [PMS_STATUS.GOALS_SENT, PMS_STATUS.UNDER_DISCUSSION, PMS_STATUS.EMPLOYEE_CONFIRMED].includes(r.status)).length],
    ['awaiting_hr',  'Awaiting HR Review',  rows.filter((r) => r.status === PMS_STATUS.MANAGER_APPROVED).length],
    ['locked',       'Locked',              rows.filter((r) => r.status === PMS_STATUS.GOALS_LOCKED).length],
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {tabs.map(([k, label, count]) => {
            const active = filter === k;
            return (
              <button
                key={k}
                type="button"
                onClick={() => setFilter(k)}
                className={
                  'inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-semibold transition ' +
                  (active
                    ? 'border-blue-700 bg-blue-700 text-white shadow-sm'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-blue-300 hover:text-blue-700')
                }
              >
                {label}
                <span className={'rounded-full px-1.5 py-0.5 text-[10px] font-bold ' + (active ? 'bg-white/20' : 'bg-slate-100 text-slate-500')}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2">
          <SearchInput value={q} onChange={setQ} placeholder="Search employee…" />
          <button
            type="button"
            onClick={() => setAssignOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
            Send Goal Sheet
          </button>
        </div>
      </div>

      {loading && <SkeletonTable rows={4} />}

      {!loading && filtered.length === 0 && (
        <EmptyState title="No assignments" description="Send a goal sheet to get started." />
      )}

      {!loading && filtered.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50">
              <tr className="text-left text-[10px] font-bold uppercase tracking-wider text-slate-500">
                <th className="px-5 py-3">Employee</th>
                <th className="px-5 py-3">Manager</th>
                <th className="px-5 py-3">Period</th>
                <th className="px-5 py-3">Structure</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((a) => (
                <tr key={a.id} className="cursor-pointer transition hover:bg-blue-50/40" onClick={() => setDrawer(a)}>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-3">
                      <Avatar name={a.employee_name} />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900">{a.employee_name}</p>
                        <p className="text-xs text-slate-400">ID #{a.employee_id}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-3.5 text-sm text-slate-600">{a.manager_name || <span className="text-slate-400">—</span>}</td>
                  <td className="px-5 py-3.5 text-sm text-slate-600">{a.period || <span className="text-slate-400">—</span>}</td>
                  <td className="px-5 py-3.5 text-xs text-slate-500">
                    {(a.kras || []).length} KRAs · {(a.competencies || []).length} comp.
                  </td>
                  <td className="px-5 py-3.5"><StatusPill status={a.status} /></td>
                  <td className="px-5 py-3.5 text-right">
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); setDrawer(a); }}
                      className="text-xs font-semibold text-blue-700 hover:underline"
                    >
                      Open →
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {assignOpen && <AssignSheetDialog onClose={() => setAssignOpen(false)} onDone={() => { setAssignOpen(false); load(); }} />}
      {drawer && (
        <GoalDetailDrawer
          assignment={drawer}
          viewerRole="hr"
          onClose={() => setDrawer(null)}
          onChanged={() => { load(); setDrawer(null); }}
        />
      )}
    </div>
  );
}


function AssignSheetDialog({ onClose, onDone }) {
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState('');
  const [period, setPeriod] = useState('');
  const [ref, setRef] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [filter, setFilter] = useState({ department_id: '', designation_id: '', role_id: '' });
  const [selectedIds, setSelectedIds] = useState([]);
  const [goalDeadline, setGoalDeadline] = useState('');  // CHANGE 3
  const [deadlineAutoCalc, setDeadlineAutoCalc] = useState(false);  // CHANGE 9
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');

  const [toast, toastEl] = usePmsToast();

  useEffect(() => {
    pmsApi.templates({ active_only: true }).then((d) => setTemplates(Array.isArray(d) ? d : []));
    employeesApi.reference().then(setRef);
    employeesApi.list({}).then((d) => setEmployees(Array.isArray(d) ? d : []));
    // CHANGE 9: auto-fetch computed deadline for goal_setting phase
    pmsApi.computeDeadline('goal_setting').then((d) => {
      if (d?.computed_deadline) {
        // datetime-local input expects "YYYY-MM-DDTHH:MM" format
        const iso = new Date(d.computed_deadline).toISOString().slice(0, 16);
        setGoalDeadline(iso);
        setDeadlineAutoCalc(true);
      }
    }).catch(() => {});
  }, []);

  const filtered = useMemo(() => employees.filter((e) => {
    if ((e.employment_status || '').toLowerCase() !== 'active') return false;
    if (filter.department_id && e.department_id !== filter.department_id) return false;
    if (filter.designation_id && e.designation_id !== filter.designation_id) return false;
    if (filter.role_id && String(e.role_id) !== String(filter.role_id)) return false;
    if (q.trim()) {
      const needle = q.trim().toLowerCase();
      const name = ((e.first_name || '') + ' ' + (e.last_name || '') + ' ' + (e.email || '')).toLowerCase();
      if (!name.includes(needle)) return false;
    }
    return true;
  }), [employees, filter, q]);

  const toggle = (id) => setSelectedIds((cur) => cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
  const toggleAll = () => {
    if (selectedIds.length === filtered.length) setSelectedIds([]);
    else setSelectedIds(filtered.map((e) => e.id));
  };

  const submit = async () => {
    if (!templateId) { toast('Pick a template.', 'error'); return; }
    const payload = {
      template_id: Number(templateId),
      period: period.trim() || null,
      department_id: selectedIds.length ? null : (filter.department_id || null),
      designation_id: selectedIds.length ? null : (filter.designation_id || null),
      role_id:        selectedIds.length ? null : (filter.role_id ? Number(filter.role_id) : null),
      employee_ids:   selectedIds.length ? selectedIds : null,
      deadline:       goalDeadline || null,  // CHANGE 3
    };
    setBusy(true);
    try {
      const created = await pmsApi.assign(payload);
      toast(`Goal sheet sent to ${created.length} employee(s).`);
      onDone();
    } catch (e) {
      toast(e?.data?.detail || e?.message || 'Assign failed.', 'error');
    } finally { setBusy(false); }
  };

  return (
    <Modal title="Send Goal Sheet" onClose={onClose} width="max-w-3xl">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField label="Template" required>
          <Select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
            <option value="">Choose a template…</option>
            {templates.map((t) => <option key={t.id} value={t.id}>{t.name}{t.period ? ` · ${t.period}` : ''}</option>)}
          </Select>
        </FormField>
        <FormField label="Period override" hint="Leave blank to use the template's period">
          <Input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="e.g. FY2026-Q1" />
        </FormField>
        {/* CHANGE 9: goal setting deadline — auto-calculated, HR can override */}
        <FormField
          label={<span>Goal Setting Deadline {deadlineAutoCalc && <span className="ml-1 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">auto-calculated</span>}</span>}
          hint="Pre-filled from PMS settings — modify to override"
        >
          <Input
            type="datetime-local"
            value={goalDeadline}
            onChange={(e) => { setGoalDeadline(e.target.value); setDeadlineAutoCalc(false); }}
          />
        </FormField>
      </div>

      <div className="mt-5">
        <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Target by cohort</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select value={filter.department_id} onChange={(e) => setFilter((f) => ({ ...f, department_id: e.target.value }))}>
            <option value="">Any department</option>
            {(ref?.departments || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </Select>
          <Select value={filter.designation_id} onChange={(e) => setFilter((f) => ({ ...f, designation_id: e.target.value }))}>
            <option value="">Any designation</option>
            {(ref?.designations || []).map((d) => <option key={d.id} value={d.id}>{d.name || d.title || d.id}</option>)}
          </Select>
          <Select value={filter.role_id} onChange={(e) => setFilter((f) => ({ ...f, role_id: e.target.value }))}>
            <option value="">Any role</option>
            {(ref?.roles || []).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
        </div>
      </div>

      <div className="mt-5">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Select employees</p>
          <SearchInput value={q} onChange={setQ} placeholder="Search…" small />
        </div>
        <div className="overflow-hidden rounded-xl border border-slate-200">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-4 py-2.5">
            <p className="text-xs font-semibold text-slate-600">
              {filtered.length} match{filtered.length === 1 ? '' : 'es'} · {selectedIds.length} selected
            </p>
            <button type="button" onClick={toggleAll} className="text-xs font-semibold text-blue-700 hover:underline">
              {selectedIds.length === filtered.length && filtered.length > 0 ? 'Clear all' : 'Select all'}
            </button>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {filtered.map((e) => (
              <label key={e.id} className="flex cursor-pointer items-center gap-3 border-t border-slate-100 px-4 py-2.5 transition hover:bg-blue-50/40">
                <input type="checkbox" checked={selectedIds.includes(e.id)} onChange={() => toggle(e.id)} className="h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-500" />
                <Avatar name={(e.first_name || '') + ' ' + (e.last_name || '')} size={28} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-slate-800">{(e.first_name || '') + ' ' + (e.last_name || '')}</p>
                  <p className="truncate text-xs text-slate-400">{e.email}</p>
                </div>
              </label>
            ))}
            {filtered.length === 0 && (
              <p className="px-4 py-8 text-center text-sm text-slate-400">No employees match the filters.</p>
            )}
          </div>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          With no selection, all employees matching the cohort filters above will receive the goal sheet.
        </p>
      </div>

      <div className="-mx-6 -mb-5 mt-6 flex justify-end gap-2 border-t border-slate-100 bg-slate-50/60 px-6 py-4">
        <button type="button" onClick={onClose} className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50">Cancel</button>
        <button type="button" onClick={submit} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-blue-700 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-800 disabled:opacity-60">
          {busy ? 'Sending…' : 'Send Goals'}
        </button>
      </div>
      {toastEl}
    </Modal>
  );
}


// ── Bulk Result Modal (CHANGE 8) ───────────────────────────────────


function BulkResultModal({ result, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <h3 className="mb-3 text-sm font-bold text-slate-800">Bulk Action Result</h3>
        <div className="mb-4 flex gap-3 text-center">
          <div className="flex-1 rounded-lg bg-slate-50 px-3 py-3">
            <p className="text-xl font-bold text-slate-900">{result.total}</p>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Total</p>
          </div>
          <div className="flex-1 rounded-lg bg-emerald-50 px-3 py-3">
            <p className="text-xl font-bold text-emerald-700">{result.success_count}</p>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-600">Succeeded</p>
          </div>
          <div className="flex-1 rounded-lg bg-rose-50 px-3 py-3">
            <p className="text-xl font-bold text-rose-700">{result.failure_count}</p>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-rose-600">Failed</p>
          </div>
        </div>
        {result.failure_count > 0 && (
          <div className="max-h-44 overflow-y-auto rounded-lg border border-rose-100 bg-rose-50 p-3">
            <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-rose-700">Failures</p>
            <div className="space-y-1">
              {result.results.filter((r) => !r.success).map((r, i) => (
                <div key={i} className="text-xs text-rose-800">
                  <span className="font-semibold">ID {r.id}{r.name ? ` (${r.name})` : ''}: </span>
                  {r.reason || 'Unknown error'}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="mt-4 flex justify-end">
          <button type="button" onClick={onClose}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-900">
            Done
          </button>
        </div>
      </div>
    </div>
  );
}


// ── Locking ────────────────────────────────────────────────────────


function LockingTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState(null);
  // CHANGE 8: bulk selection state
  const [selectedQueue, setSelectedQueue] = useState(new Set());
  const [selectedLocked, setSelectedLocked] = useState(new Set());
  const [bulkResult, setBulkResult] = useState(null);

  const [toast, toastEl] = usePmsToast();
  const [confirm, confirmEl] = useConfirm();

  const load = () => {
    setLoading(true);
    pmsApi.assignments({ scope: 'hr' })
      .then((d) => setRows(Array.isArray(d) ? d : []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const lockQueue  = rows.filter((r) => r.status === PMS_STATUS.HR_REVIEWED || r.status === PMS_STATUS.MANAGER_APPROVED);
  const locked     = rows.filter((r) => r.status === PMS_STATUS.GOALS_LOCKED);
  // Only manually-locked records can be bulk-unlocked.
  const manualLocked = locked.filter((r) => !isAutoLocked(r));

  // CHANGE 8: bulk helpers
  const toggleQueue    = (id) => setSelectedQueue((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAllQueue = () => setSelectedQueue(selectedQueue.size === lockQueue.length && lockQueue.length > 0 ? new Set() : new Set(lockQueue.map((a) => a.id)));
  const toggleLocked   = (id) => setSelectedLocked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAllLocked = () => setSelectedLocked(selectedLocked.size === manualLocked.length && manualLocked.length > 0 ? new Set() : new Set(manualLocked.map((a) => a.id)));

  const bulkHrReview = async () => {
    const ids = Array.from(selectedQueue);
    if (!ids.length) return;
    try { const r = await pmsApi.bulkHrReview(ids); setBulkResult(r); setSelectedQueue(new Set()); load(); }
    catch (e) { toast(e?.data?.detail || e?.message || 'Bulk HR review failed', 'error'); }
  };
  const bulkLockAction = () => {
    if (!selectedQueue.size) return;
    confirm('Lock selected goal sheets? Editing will be disabled for all selected employees.', async () => {
      try { const r = await pmsApi.bulkLock(Array.from(selectedQueue)); setBulkResult(r); setSelectedQueue(new Set()); load(); }
      catch (e) { toast(e?.data?.detail || e?.message || 'Bulk lock failed', 'error'); }
    });
  };
  const bulkUnlockAction = () => {
    if (!selectedLocked.size) return;
    confirm('Unlock selected goal sheets? Editing will be re-opened for all selected employees.', async () => {
      try { const r = await pmsApi.bulkUnlock(Array.from(selectedLocked)); setBulkResult(r); setSelectedLocked(new Set()); load(); }
      catch (e) { toast(e?.data?.detail || e?.message || 'Bulk unlock failed', 'error'); }
    });
  };

  const lockOne = (id) => {
    confirm('Lock these goals? Employee and manager cannot edit until HR unlocks.', async () => {
      try { await pmsApi.lock(id, {}); load(); toast('Goals locked successfully.'); }
      catch (e) { toast(e?.data?.detail || e?.message || 'Lock failed', 'error'); }
    });
  };
  const unlockOne = (id) => {
    confirm('Unlock these goals? Editing will be re-opened.', async () => {
      try { await pmsApi.unlock(id, {}); load(); toast('Goals unlocked.'); }
      catch (e) { toast(e?.data?.detail || e?.message || 'Unlock failed', 'error'); }
    });
  };
  const reviewOne = async (id) => {
    try { await pmsApi.hrReview(id, {}); load(); toast('Marked as HR reviewed.'); }
    catch (e) { toast(e?.data?.detail || e?.message || 'HR review failed', 'error'); }
  };

  return (
    <div className="space-y-6">
      {loading && <SkeletonTable rows={3} />}

      <LockSection title="Ready for HR review / lock" count={lockQueue.length} accent="bg-amber-50 text-amber-700">
        {lockQueue.length === 0 && (
          <p className="px-5 py-6 text-center text-sm text-slate-400">Nothing waiting on you right now.</p>
        )}
        {lockQueue.length > 0 && (
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-5 py-2.5">
            <div className="flex items-center gap-2">
              <input type="checkbox" checked={selectedQueue.size === lockQueue.length} onChange={toggleAllQueue}
                className="h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-500" />
              <span className="text-xs text-slate-500">{selectedQueue.size > 0 ? `${selectedQueue.size} selected` : 'Select all'}</span>
            </div>
            {selectedQueue.size > 0 && (
              <div className="flex gap-2">
                <button type="button" onClick={bulkHrReview} className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-cyan-700">Bulk HR Review</button>
                <button type="button" onClick={bulkLockAction} className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-rose-700">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                  Bulk Lock
                </button>
              </div>
            )}
          </div>
        )}
        <div className="divide-y divide-slate-100">
          {lockQueue.map((a) => (
            <div key={a.id} className="flex flex-wrap items-center gap-3 px-5 py-3.5">
              <input type="checkbox" checked={selectedQueue.has(a.id)} onChange={() => toggleQueue(a.id)}
                className="h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-500" />
              <Avatar name={a.employee_name} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-900">{a.employee_name}</p>
                <p className="truncate text-xs text-slate-500">{a.period || '—'} · Manager: {a.manager_name || '—'}</p>
              </div>
              <StatusPill status={a.status} />
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setDrawer(a)} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50">Review</button>
                {a.status === PMS_STATUS.MANAGER_APPROVED && (
                  <button type="button" onClick={() => reviewOne(a.id)} className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-cyan-700">Mark HR Reviewed</button>
                )}
                <button type="button" onClick={() => lockOne(a.id)} className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-rose-700">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                  Lock
                </button>
              </div>
            </div>
          ))}
        </div>
      </LockSection>

      <LockSection title="Locked" count={locked.length} accent="bg-rose-50 text-rose-700">
        {locked.length === 0 && (
          <p className="px-5 py-6 text-center text-sm text-slate-400">No locked goals yet.</p>
        )}
        {locked.length > 0 && (
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-5 py-2.5">
            <div className="flex items-center gap-2">
              <input type="checkbox"
                checked={manualLocked.length > 0 && selectedLocked.size === manualLocked.length}
                onChange={toggleAllLocked}
                disabled={manualLocked.length === 0}
                className="h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-500 disabled:opacity-40" />
              <span className="text-xs text-slate-500">{selectedLocked.size > 0 ? `${selectedLocked.size} selected` : 'Select all'}</span>
            </div>
            {selectedLocked.size > 0 && (
              <button type="button" onClick={bulkUnlockAction} className="inline-flex items-center gap-1 rounded-lg bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-800">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 019.9-1"/></svg>
                Bulk Unlock
              </button>
            )}
          </div>
        )}
        <div className="divide-y divide-slate-100">
          {locked.map((a) => {
            const autoLock = isAutoLocked(a);
            return (
              <div key={a.id} className="flex flex-wrap items-center gap-3 px-5 py-3.5">
                {/* Auto-locked records cannot be bulk-selected for unlock */}
                <input type="checkbox"
                  checked={selectedLocked.has(a.id)}
                  onChange={() => !autoLock && toggleLocked(a.id)}
                  disabled={autoLock}
                  className="h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-500 disabled:opacity-30" />
                <Avatar name={a.employee_name} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-slate-900">{a.employee_name}</p>
                  <p className="truncate text-xs text-slate-500">
                    {a.period || '—'} · Locked {a.locked_at ? new Date(a.locked_at).toLocaleDateString() : ''}
                  </p>
                </div>
                {/* Status pill — show "Auto Locked" badge when system-locked */}
                {autoLock
                  ? <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-100 px-2.5 py-1 text-[11px] font-semibold text-orange-700">
                      <span className="h-1.5 w-1.5 rounded-full bg-current" />Auto Locked
                    </span>
                  : <StatusPill status={a.status} />
                }
                <div className="flex gap-2">
                  <button type="button" onClick={() => setDrawer(a)} className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50">View</button>
                  {/* Unlock only available for manual locks */}
                  {!autoLock && (
                    <button type="button" onClick={() => unlockOne(a.id)} className="inline-flex items-center gap-1 rounded-lg bg-blue-700 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-blue-800">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 019.9-1"/></svg>
                      Unlock
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </LockSection>

      {drawer && (
        <GoalDetailDrawer
          assignment={drawer}
          viewerRole="hr"
          onClose={() => setDrawer(null)}
          onChanged={() => { load(); setDrawer(null); }}
        />
      )}
      {bulkResult && <BulkResultModal result={bulkResult} onClose={() => setBulkResult(null)} />}
      {toastEl}
      {confirmEl}
    </div>
  );
}


// ── Atomics (local to this hub) ────────────────────────────────────


export function Avatar({ name, size = 36 }) {
  const initials = (name || 'U').split(' ').filter(Boolean).map((s) => s[0]).slice(0, 2).join('').toUpperCase();
  // Stable hue from initials so each employee gets a consistent color.
  const hash = [...initials].reduce((n, ch) => n + ch.charCodeAt(0), 0);
  const palette = [
    'from-blue-500 to-indigo-500',
    'from-emerald-500 to-teal-500',
    'from-amber-500 to-orange-500',
    'from-rose-500 to-pink-500',
    'from-violet-500 to-purple-500',
    'from-cyan-500 to-sky-500',
  ];
  const grad = palette[hash % palette.length];
  return (
    <div
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br ${grad} font-semibold text-white shadow-sm`}
      style={{ width: size, height: size, fontSize: Math.max(10, size * 0.34) }}
    >
      {initials}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-sm font-bold text-slate-700">{value}</span>
      <span className="text-[11px] text-slate-400">{label}</span>
    </span>
  );
}

function FormField({ label, hint, required, children }) {
  return (
    <label className="block">
      <span className="mb-1 flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-slate-500">
        {label}
        {required && <span className="text-rose-500">*</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
    </label>
  );
}

function Input({ className = '', ...rest }) {
  return (
    <input
      {...rest}
      className={
        'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 placeholder-slate-400 transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 ' +
        className
      }
    />
  );
}

function Select({ className = '', children, ...rest }) {
  return (
    <select
      {...rest}
      className={
        'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 ' +
        className
      }
    >
      {children}
    </select>
  );
}

function SearchInput({ value, onChange, placeholder, small }) {
  return (
    <div className="relative">
      <svg className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={
          'rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-800 placeholder-slate-400 transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100 ' +
          (small ? 'py-1.5 w-44' : 'py-2 w-56')
        }
      />
    </div>
  );
}

function SectionBlock({ title, meta, action, children }) {
  return (
    <div className="mt-6 border-t border-slate-100 pt-5">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-slate-900">{title}</h3>
          {meta && <p className="mt-0.5 text-xs text-slate-400">{meta}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function AddButton({ onClick, label }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-blue-300 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 transition hover:bg-blue-100"
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      {label}
    </button>
  );
}

function IconButton({ children, onClick, tone = 'ghost', title }) {
  const toneClasses =
    tone === 'danger' ? 'bg-rose-50 text-rose-600 hover:bg-rose-100' :
    'bg-slate-100 text-slate-500 hover:bg-slate-200';
  return (
    <button type="button" onClick={onClick} title={title} className={`inline-flex h-9 w-9 items-center justify-center rounded-lg transition ${toneClasses}`}>
      {children}
    </button>
  );
}

function LockSection({ title, count, accent, children }) {
  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-sm font-bold text-slate-900">{title}</h2>
        <span className={'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold ' + accent}>{count}</span>
      </div>
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">{children}</div>
    </div>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-12 text-center">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-blue-600">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
      </div>
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      <p className="mt-1 text-xs text-slate-500">{description}</p>
    </div>
  );
}

// ── Mid-Cycle Review Tab (HR) ──────────────────────────────────────────────────

function MidCycleTab() {
  const [reviews, setReviews]       = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [drawer, setDrawer]         = useState(null);  // { review, assignment }
  const [statusFilter, setStatusFilter] = useState('');

  // Create review modal.
  const [showCreate, setShowCreate]             = useState(false);
  const [selectedAssignmentIds, setSelectedAssignmentIds] = useState([]);  // CHANGE 8: multi-select
  const [cyclePeriod, setCyclePeriod]           = useState('');
  const [allowMod, setAllowMod]                 = useState(false);
  const [mcrDeadline, setMcrDeadline]           = useState('');  // CHANGE 3
  const [mcrDeadlineAutoCalc, setMcrDeadlineAutoCalc] = useState(false);  // CHANGE 9
  const [creating, setCreating]                 = useState(false);
  const [createError, setCreateError]           = useState('');
  const [bulkResult, setBulkResult]             = useState(null);  // CHANGE 8

  // CHANGE 9: auto-fetch computed deadline when create modal opens.
  useEffect(() => {
    if (!showCreate) return;
    pmsApi.computeDeadline('mid_cycle').then((d) => {
      if (d?.computed_deadline && !mcrDeadline) {
        setMcrDeadline(new Date(d.computed_deadline).toISOString().slice(0, 16));
        setMcrDeadlineAutoCalc(true);
      }
    }).catch(() => {});
  }, [showCreate]);

  const load = () => {
    setLoading(true);
    Promise.all([
      pmsApi.midCycleReviews({ scope: 'hr' }),
      pmsApi.assignments({ scope: 'hr' }),
    ]).then(([revs, asns]) => {
      setReviews(Array.isArray(revs) ? revs : []);
      setAssignments(Array.isArray(asns) ? asns : []);
    }).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    if (!statusFilter) return reviews;
    return reviews.filter((r) => r.status === statusFilter);
  }, [reviews, statusFilter]);

  const assignmentMap = useMemo(() => {
    const m = {};
    assignments.forEach((a) => { m[a.id] = a; });
    return m;
  }, [assignments]);

  const handleCreate = async () => {
    // CHANGE 8: bulk create — at least one assignment must be selected
    if (!selectedAssignmentIds.length) { setCreateError('Select at least one assignment.'); return; }
    setCreating(true); setCreateError('');
    try {
      const result = await pmsApi.bulkCreateMidCycle({
        assignment_ids: selectedAssignmentIds,
        cycle_period: cyclePeriod.trim() || null,
        allow_goal_modification: allowMod,
        deadline: mcrDeadline || null,
      });
      setShowCreate(false); setSelectedAssignmentIds([]); setCyclePeriod(''); setAllowMod(false); setMcrDeadline(''); setMcrDeadlineAutoCalc(false);
      setBulkResult(result);
      load();
    } catch (e) {
      setCreateError(e?.message || 'Failed to create review.');
    } finally { setCreating(false); }
  };

  const MCR_STATUSES_LIST = [
    { value: '', label: 'All Statuses' },
    { value: 'draft', label: 'Draft' },
    { value: 'in_progress', label: 'In Progress' },
    { value: 'submitted', label: 'Submitted' },
    { value: 'manager_reviewed', label: 'Manager Reviewed' },
    { value: 'manager_approved', label: 'Manager Approved' },
    { value: 'hr_reviewed', label: 'HR Reviewed' },
    { value: 'mid_cycle_locked', label: 'Locked' },
  ];

  return (
    <div>
      {/* Toolbar */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 shadow-sm"
        >
          {MCR_STATUSES_LIST.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-blue-700"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Open Mid-Cycle Review
        </button>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h3 className="mb-4 text-sm font-bold text-slate-800">Open Mid-Cycle Review</h3>
            {createError && (
              <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{createError}</div>
            )}
            <div className="space-y-3">
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-600">Goal Assignments *</label>
                  {assignments.filter((a) => a.status === 'goals_locked').length > 0 && (
                    <button type="button" className="text-[10px] font-semibold text-blue-700 hover:underline"
                      onClick={() => {
                        const ids = assignments.filter((a) => a.status === 'goals_locked').map((a) => a.id);
                        setSelectedAssignmentIds(selectedAssignmentIds.length === ids.length ? [] : ids);
                      }}>
                      {selectedAssignmentIds.length === assignments.filter((a) => a.status === 'goals_locked').length ? 'Clear all' : 'Select all'}
                    </button>
                  )}
                </div>
                <div className="max-h-44 overflow-y-auto rounded-lg border border-slate-200 bg-white">
                  {assignments.filter((a) => a.status === 'goals_locked').length === 0 ? (
                    <p className="px-3 py-4 text-center text-xs text-slate-400">No locked assignments available.</p>
                  ) : (
                    assignments.filter((a) => a.status === 'goals_locked').map((a) => (
                      <label key={a.id} className="flex cursor-pointer items-center gap-3 border-b border-slate-100 px-3 py-2 last:border-b-0 hover:bg-blue-50">
                        <input type="checkbox" checked={selectedAssignmentIds.includes(a.id)}
                          onChange={() => setSelectedAssignmentIds((prev) => prev.includes(a.id) ? prev.filter((x) => x !== a.id) : [...prev, a.id])}
                          className="h-4 w-4 rounded border-slate-300 text-blue-700 focus:ring-blue-500" />
                        <span className="text-xs text-slate-800">{a.employee_name} — {a.period || 'No period'}</span>
                      </label>
                    ))
                  )}
                </div>
                <p className="mt-1 text-[10px] text-slate-400">Only locked goal assignments are shown. Select one or more.</p>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-600">Cycle Period</label>
                <input
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
                  placeholder="e.g. H1-2026"
                  value={cyclePeriod}
                  onChange={(e) => setCyclePeriod(e.target.value)}
                />
              </div>
              {/* CHANGE 9: deadline for mid-cycle phase — auto-calculated, HR can override */}
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-600">
                  Review Deadline
                  {mcrDeadlineAutoCalc && <span className="ml-1 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">auto-calculated</span>}
                </label>
                <input type="datetime-local"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
                  value={mcrDeadline} onChange={(e) => { setMcrDeadline(e.target.value); setMcrDeadlineAutoCalc(false); }} />
                <p className="mt-0.5 text-[10px] text-slate-400">Pre-filled from PMS settings — modify to override.</p>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={allowMod} onChange={(e) => setAllowMod(e.target.checked)}
                  className="rounded border-slate-300" />
                <span className="text-xs text-slate-700">Allow manager to modify goals during review</span>
              </label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)}
                className="rounded-lg px-4 py-2 text-xs text-slate-500 hover:text-slate-700">Cancel</button>
              <button type="button" onClick={handleCreate} disabled={creating}
                className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50">
                {creating ? 'Creating…' : 'Create Review'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <SkeletonTable rows={5} />
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white py-16">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-blue-500">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          </div>
          <p className="text-sm font-semibold text-slate-700">No mid-cycle reviews</p>
          <p className="mt-1 text-xs text-slate-400">Use the button above to open a review for a locked goal sheet.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-5 py-3 text-left">Employee</th>
                <th className="px-4 py-3 text-left">Period</th>
                <th className="px-4 py-3 text-left">Cycle</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Submitted</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((r) => {
                const tone     = MCR_STATUS_TONE[r.status] || { bg: '#F1F5F9', fg: '#475569' };
                const a        = assignmentMap[r.assignment_id];
                const autoLock = isAutoLocked(r);
                return (
                  <tr key={r.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-blue-50 text-xs font-bold text-blue-700">
                          {(r.employee_name || '?').slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-semibold text-slate-800">{r.employee_name || '—'}</p>
                          <p className="text-slate-400">{r.manager_name ? `Mgr: ${r.manager_name}` : ''}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-slate-600">{r.period || '—'}</td>
                    <td className="px-4 py-3.5 text-slate-600">{r.cycle_period || 'Mid-Cycle'}</td>
                    <td className="px-4 py-3.5">
                      {autoLock
                        ? <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-100 px-2.5 py-1 text-[11px] font-semibold text-orange-700">
                            <span className="h-1.5 w-1.5 rounded-full bg-current" />Auto Locked
                          </span>
                        : <span className="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold"
                            style={{ backgroundColor: tone.bg, color: tone.fg }}>
                            {MCR_STATUS_LABEL[r.status] || r.status}
                          </span>
                      }
                    </td>
                    <td className="px-4 py-3.5 text-slate-400">
                      {r.submitted_at ? new Date(r.submitted_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <button
                        type="button"
                        onClick={() => setDrawer({ review: r, assignment: a })}
                        className="rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-600 hover:bg-blue-100"
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {drawer && (
        <MidCycleReviewDrawer
          review={drawer.review}
          assignment={drawer.assignment}
          viewerRole="hr"
          onClose={() => setDrawer(null)}
          onChanged={() => { load(); setDrawer(null); }}
        />
      )}
      {bulkResult && <BulkResultModal result={bulkResult} onClose={() => setBulkResult(null)} />}
    </div>
  );
}

function SkeletonGrid({ count = 3 }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="h-48 animate-pulse rounded-xl bg-slate-100" />
      ))}
    </div>
  );
}
function SkeletonTable({ rows = 4 }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 border-t border-slate-100 px-5 py-4 first:border-t-0">
          <div className="h-9 w-9 animate-pulse rounded-full bg-slate-200" />
          <div className="flex-1 space-y-2">
            <div className="h-3 w-1/3 animate-pulse rounded bg-slate-200" />
            <div className="h-2.5 w-1/2 animate-pulse rounded bg-slate-100" />
          </div>
          <div className="h-6 w-20 animate-pulse rounded-full bg-slate-100" />
        </div>
      ))}
    </div>
  );
}


// ── Phase 3: End Cycle Assessment Tab ─────────────────────────────────────────

function EndCycleTab() {
  const [reviews, setReviews]         = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading]         = useState(true);
  const [drawer, setDrawer]           = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate]                   = useState(false);
  const [selectedAssignmentIds, setSelectedAssignmentIds] = useState([]);  // CHANGE 8
  const [cyclePeriod, setCyclePeriod]                 = useState('');
  const [ecaDeadline, setEcaDeadline]                 = useState('');  // CHANGE 3
  const [ecaDeadlineAutoCalc, setEcaDeadlineAutoCalc] = useState(false);  // CHANGE 9
  const [creating, setCreating]                       = useState(false);
  const [createError, setCreateError]                 = useState('');
  const [bulkResult, setBulkResult]                   = useState(null);  // CHANGE 8

  const load = () => {
    setLoading(true);
    Promise.all([
      pmsApi.assessments({ scope: 'hr' }),
      pmsApi.assignments({ scope: 'hr' }),
    ]).then(([revs, asns]) => {
      setReviews(Array.isArray(revs) ? revs : []);
      setAssignments(Array.isArray(asns) ? asns : []);
    }).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  // CHANGE 9: auto-fetch computed deadline when create modal opens.
  useEffect(() => {
    if (!showCreate) return;
    pmsApi.computeDeadline('end_cycle').then((d) => {
      if (d?.computed_deadline && !ecaDeadline) {
        setEcaDeadline(new Date(d.computed_deadline).toISOString().slice(0, 16));
        setEcaDeadlineAutoCalc(true);
      }
    }).catch(() => {});
  }, [showCreate]);

  const filtered = useMemo(() => {
    if (!statusFilter) return reviews;
    return reviews.filter((r) => r.status === statusFilter);
  }, [reviews, statusFilter]);

  const assignmentMap = useMemo(() => {
    const m = {};
    assignments.forEach((a) => { m[a.id] = a; });
    return m;
  }, [assignments]);

  const handleCreate = async () => {
    // CHANGE 8: bulk create — at least one assignment must be selected
    if (!selectedAssignmentIds.length) { setCreateError('Select at least one assignment.'); return; }
    setCreating(true); setCreateError('');
    try {
      const result = await pmsApi.bulkCreateECA({
        assignment_ids: selectedAssignmentIds,
        cycle_period: cyclePeriod.trim() || null,
        deadline: ecaDeadline || null,
      });
      setShowCreate(false); setSelectedAssignmentIds([]); setCyclePeriod(''); setEcaDeadline(''); setEcaDeadlineAutoCalc(false);
      setBulkResult(result);
      load();
    } catch (e) {
      setCreateError(e?.message || 'Failed to create assessment.');
    } finally { setCreating(false); }
  };

  const ECA_STATUSES_LIST = [
    { value: '', label: 'All Statuses' },
    { value: 'draft', label: 'Draft' },
    { value: 'self_assessed', label: 'Self Assessed' },
    { value: 'manager_assessed', label: 'Manager Assessed' },
    { value: 'submitted_to_hr', label: 'Submitted to HR' },
    { value: 'hr_received', label: 'HR Received' },
    { value: 'assessment_locked', label: 'Locked' },
  ];

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 shadow-sm">
          {ECA_STATUSES_LIST.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <div className="flex-1" />
        <button type="button" onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Open End-Cycle Assessment
        </button>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <h3 className="mb-4 text-sm font-bold text-slate-800">Open End-Cycle Assessment</h3>
            {createError && <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{createError}</div>}
            <div className="space-y-3">
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-600">Goal Assignments *</label>
                  {assignments.filter((a) => a.status === 'goals_locked').length > 0 && (
                    <button type="button" className="text-[10px] font-semibold text-indigo-700 hover:underline"
                      onClick={() => {
                        const ids = assignments.filter((a) => a.status === 'goals_locked').map((a) => a.id);
                        setSelectedAssignmentIds(selectedAssignmentIds.length === ids.length ? [] : ids);
                      }}>
                      {selectedAssignmentIds.length === assignments.filter((a) => a.status === 'goals_locked').length ? 'Clear all' : 'Select all'}
                    </button>
                  )}
                </div>
                <div className="max-h-44 overflow-y-auto rounded-lg border border-slate-200 bg-white">
                  {assignments.filter((a) => a.status === 'goals_locked').length === 0 ? (
                    <p className="px-3 py-4 text-center text-xs text-slate-400">No locked assignments available.</p>
                  ) : (
                    assignments.filter((a) => a.status === 'goals_locked').map((a) => (
                      <label key={a.id} className="flex cursor-pointer items-center gap-3 border-b border-slate-100 px-3 py-2 last:border-b-0 hover:bg-indigo-50">
                        <input type="checkbox" checked={selectedAssignmentIds.includes(a.id)}
                          onChange={() => setSelectedAssignmentIds((prev) => prev.includes(a.id) ? prev.filter((x) => x !== a.id) : [...prev, a.id])}
                          className="h-4 w-4 rounded border-slate-300 text-indigo-700 focus:ring-indigo-500" />
                        <span className="text-xs text-slate-800">{a.employee_name} — {a.period || 'No period'}</span>
                      </label>
                    ))
                  )}
                </div>
                <p className="mt-1 text-[10px] text-slate-400">Only locked goal assignments are shown. Select one or more.</p>
              </div>
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-600">Cycle Period</label>
                <input className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
                  placeholder="e.g. FY2026" value={cyclePeriod} onChange={(e) => setCyclePeriod(e.target.value)} />
              </div>
              {/* CHANGE 9: deadline for end-cycle phase — auto-calculated, HR can override */}
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-600">
                  Assessment Deadline
                  {ecaDeadlineAutoCalc && <span className="ml-1 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">auto-calculated</span>}
                </label>
                <input type="datetime-local"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
                  value={ecaDeadline} onChange={(e) => { setEcaDeadline(e.target.value); setEcaDeadlineAutoCalc(false); }} />
                <p className="mt-0.5 text-[10px] text-slate-400">Pre-filled from PMS settings — modify to override.</p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setShowCreate(false)}
                className="rounded-lg px-4 py-2 text-xs text-slate-500 hover:text-slate-700">Cancel</button>
              <button type="button" onClick={handleCreate} disabled={creating}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50">
                {creating ? 'Creating…' : 'Create Assessment'}
              </button>
            </div>
          </div>
        </div>
      )}

      {loading ? <SkeletonTable rows={4} /> : filtered.length === 0 ? (
        <EmptyState title="No end-cycle assessments" description="Open an end-cycle assessment for a locked goal sheet." />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-5 py-3 text-left">Employee</th>
                <th className="px-4 py-3 text-left">Period</th>
                <th className="px-4 py-3 text-left">Cycle</th>
                <th className="px-4 py-3 text-left">Self Rating</th>
                <th className="px-4 py-3 text-left">Mgr Rating</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((r) => {
                const tone     = ECA_STATUS_TONE[r.status] || { bg: '#F1F5F9', fg: '#475569' };
                const a        = assignmentMap[r.assignment_id];
                const autoLock = isAutoLocked(r);
                return (
                  <tr key={r.id} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-50 text-xs font-bold text-indigo-700">
                          {(r.employee_name || '?').slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-semibold text-slate-800">{r.employee_name || '—'}</p>
                          <p className="text-slate-400">{r.manager_name ? `Mgr: ${r.manager_name}` : ''}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-slate-600">{r.period || '—'}</td>
                    <td className="px-4 py-3.5 text-slate-600">{r.cycle_period || '—'}</td>
                    <td className="px-4 py-3.5">
                      {r.self_rating ? (
                        <span className="font-semibold text-amber-600">{r.self_rating.toFixed(1)} ★</span>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3.5">
                      {r.manager_rating ? (
                        <span className="font-semibold text-indigo-600">{r.manager_rating.toFixed(1)} ★</span>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="px-4 py-3.5">
                      {autoLock
                        ? <span className="inline-flex items-center gap-1.5 rounded-full bg-orange-100 px-2.5 py-1 text-[11px] font-semibold text-orange-700">
                            <span className="h-1.5 w-1.5 rounded-full bg-current" />Auto Locked
                          </span>
                        : <span className="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold"
                            style={{ backgroundColor: tone.bg, color: tone.fg }}>
                            {ECA_STATUS_LABEL[r.status] || r.status}
                          </span>
                      }
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <button type="button"
                        onClick={() => setDrawer({ assessment: r, assignment: a })}
                        className="rounded-lg bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-600 hover:bg-indigo-100">
                        Open
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {drawer && (
        <EndCycleAssessmentDrawer
          assessment={drawer.assessment}
          assignment={drawer.assignment}
          viewerRole="hr"
          onClose={() => setDrawer(null)}
          onChanged={() => { load(); setDrawer(null); }}
        />
      )}
      {bulkResult && <BulkResultModal result={bulkResult} onClose={() => setBulkResult(null)} />}
    </div>
  );
}


// ── Phase 4: Normalization Tab ────────────────────────────────────────────────

function NormalizationTab() {
  const [sessions, setSessions]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [selected, setSelected]   = useState(null);
  const [showCreate, setShowCreate] = useState(false);
  const [busy, setBusy]           = useState('');
  const [error, setError]         = useState('');

  const [confirm, confirmEl] = useConfirm();

  // ── Create-form state ──────────────────────────────────────────────────────
  const [availPeriods, setAvailPeriods]   = useState([]);  // from /eligible-periods
  const [periodsLoading, setPeriodsLoading] = useState(false);
  const [period, setPeriod]               = useState('');
  const [notes, setNotes]                 = useState('');
  const [normDeadline, setNormDeadline]   = useState('');   // CHANGE 3
  const [normDeadlineAutoCalc, setNormDeadlineAutoCalc] = useState(false);  // CHANGE 9
  const [preview, setPreview]             = useState([]);   // EligibleECAOut[]
  const [previewLoading, setPreviewLoading] = useState(false);
  const [creating, setCreating]           = useState(false);

  // ── Edit-session state (Issue 4) ───────────────────────────────────────────
  const [editing, setEditing]     = useState(false);
  const [editPeriod, setEditPeriod] = useState('');
  const [editNotes, setEditNotes] = useState('');
  const [saving, setSaving]       = useState(false);

  // ── Load session list ──────────────────────────────────────────────────────
  const load = () => {
    setLoading(true);
    pmsApi.normSessions()
      .then((d) => setSessions(Array.isArray(d) ? d : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const refreshSelected = async (id) => {
    const s = await pmsApi.normSession(id);
    setSelected(s);
    setSessions((prev) => prev.map((x) => x.id === s.id ? s : x));
  };

  // ── Open create form: load available periods + auto-compute deadline ──────────
  const openCreate = () => {
    setShowCreate(true);
    setPeriod('');
    setNotes('');
    setPreview([]);
    setError('');
    setPeriodsLoading(true);
    pmsApi.eligiblePeriods()
      .then((d) => setAvailPeriods(Array.isArray(d) ? d : []))
      .catch(() => setAvailPeriods([]))
      .finally(() => setPeriodsLoading(false));
    // CHANGE 9: auto-fetch computed deadline for normalization phase
    pmsApi.computeDeadline('normalization').then((d) => {
      if (d?.computed_deadline) {
        setNormDeadline(new Date(d.computed_deadline).toISOString().slice(0, 16));
        setNormDeadlineAutoCalc(true);
      }
    }).catch(() => {});
  };

  // ── When period changes, load employee preview ─────────────────────────────
  const handlePeriodChange = (p) => {
    setPeriod(p);
    if (!p) { setPreview([]); return; }
    setPreviewLoading(true);
    pmsApi.eligibleEmployees({ period: p })
      .then((d) => setPreview(Array.isArray(d) ? d : []))
      .catch(() => setPreview([]))
      .finally(() => setPreviewLoading(false));
  };

  // ── Create session ─────────────────────────────────────────────────────────
  const handleCreate = async () => {
    if (!period.trim()) { setError('Select a period first.'); return; }
    setCreating(true); setError('');
    try {
      const sess = await pmsApi.createNormSession({ period: period.trim(), notes: notes.trim() || null, deadline: normDeadline || null });
      setShowCreate(false);
      setPeriod(''); setNotes(''); setPreview([]); setNormDeadline(''); setNormDeadlineAutoCalc(false);
      load();
      // Auto-select the newly created session.
      if (sess?.id) setSelected(sess);
    } catch (e) {
      setError(e?.data?.detail || e?.message || 'Create failed.');
    } finally { setCreating(false); }
  };

  // ── Edit session (Issue 4) ─────────────────────────────────────────────────
  const handleEditOpen = () => {
    setEditPeriod(selected.period);
    setEditNotes(selected.notes || '');
    setEditing(true);
  };

  const handleEditSave = async () => {
    setSaving(true); setError('');
    try {
      await pmsApi.updateNormSession(selected.id, {
        period: editPeriod.trim() || undefined,
        notes: editNotes.trim() || null,
      });
      setEditing(false);
      await refreshSelected(selected.id);
    } catch (e) { setError(e?.data?.detail || e?.message || 'Edit failed.'); }
    finally { setSaving(false); }
  };

  // ── Delete session (Issue 4) ───────────────────────────────────────────────
  const handleDelete = () => {
    confirm(`Delete normalization session "${selected.period}"? This cannot be undone.`, async () => {
      setBusy('Delete'); setError('');
      try {
        await pmsApi.deleteNormSession(selected.id);
        setSelected(null);
        load();
      } catch (e) { setError(e?.data?.detail || e?.message || 'Delete failed.'); }
      finally { setBusy(''); }
    });
  };

  // ── Add employees to existing session ─────────────────────────────────────
  const handleAddRecords = async () => {
    setBusy('AddRecords'); setError('');
    try {
      await pmsApi.addNormRecords(selected.id);
      await refreshSelected(selected.id);
    } catch (e) { setError(e?.data?.detail || e?.message || 'Add employees failed.'); }
    finally { setBusy(''); }
  };

  const act = async (fn, label, sessId) => {
    setBusy(label); setError('');
    try { await fn(); await refreshSelected(sessId); }
    catch (e) { setError(e?.data?.detail || e?.message || `${label} failed.`); }
    finally { setBusy(''); }
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Session list */}
      <div className="lg:col-span-1">
        <div className="mb-3 flex items-center justify-between">
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Sessions</p>
          <button type="button" onClick={openCreate}
            className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700">
            + New
          </button>
        </div>

        {/* ── Create form with period dropdown + employee preview ── */}
        {showCreate && (
          <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-3">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-500">New Normalization Session</p>
            {error && <div className="rounded bg-red-50 px-3 py-2 text-xs text-red-600">{error}</div>}

            {/* Period selector */}
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-600">Period *</label>
              {periodsLoading ? (
                <div className="h-8 animate-pulse rounded-lg bg-slate-100" />
              ) : (
                <select
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 focus:border-blue-400 focus:outline-none"
                  value={period}
                  onChange={(e) => handlePeriodChange(e.target.value)}
                >
                  <option value="">— Select a period —</option>
                  {availPeriods.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              )}
              {!periodsLoading && availPeriods.length === 0 && (
                <p className="mt-1 text-[10px] text-amber-600">
                  No locked end-cycle assessments found. Lock assessments first.
                </p>
              )}
            </div>

            {/* Employee preview */}
            {period && (
              <div>
                <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Employees to be included
                </p>
                {previewLoading ? (
                  <div className="h-16 animate-pulse rounded-lg bg-slate-100" />
                ) : preview.length === 0 ? (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                    <p className="text-xs font-semibold text-amber-700">No eligible employees for "{period}".</p>
                    <p className="mt-0.5 text-[10px] text-amber-600">
                      All locked assessments for this period may already be in another session.
                    </p>
                  </div>
                ) : (
                  <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-200">
                    {preview.map((e) => (
                      <div key={e.eca_id}
                        className={`flex items-center justify-between border-b border-slate-100 px-3 py-2 last:border-0 ${
                          e.in_session_id ? 'bg-amber-50/60' : 'bg-white'
                        }`}>
                        <div className="min-w-0">
                          <p className="truncate text-xs font-semibold text-slate-800">{e.employee_name}</p>
                          <p className="text-[10px] text-slate-400">
                            Mgr: {e.manager_name || '—'}
                            {e.manager_rating != null && ` · Mgr rating: ${e.manager_rating.toFixed(1)}★`}
                          </p>
                        </div>
                        {e.in_session_id ? (
                          <span className="ml-2 shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[9px] font-bold text-amber-700">
                            In session #{e.in_session_id}
                          </span>
                        ) : (
                          <span className="ml-2 shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[9px] font-bold text-emerald-700">
                            Available
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                <p className="mt-1 text-[10px] text-slate-400">
                  {preview.filter((e) => !e.in_session_id).length} available ·{' '}
                  {preview.filter((e) => !!e.in_session_id).length} already in a session (will be skipped)
                </p>
              </div>
            )}

            {/* Notes */}
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-600">Notes (optional)</label>
              <textarea className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-xs" rows={2}
                placeholder="Any notes about this normalization run…"
                value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>

            {/* CHANGE 9: normalization phase deadline — auto-calculated, HR can override */}
            <div>
              <label className="mb-1 block text-xs font-semibold text-slate-600">
                Session Deadline
                {normDeadlineAutoCalc && <span className="ml-1 rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700">auto-calculated</span>}
              </label>
              <input type="datetime-local"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs focus:border-blue-400 focus:outline-none"
                value={normDeadline} onChange={(e) => { setNormDeadline(e.target.value); setNormDeadlineAutoCalc(false); }} />
              <p className="mt-0.5 text-[10px] text-slate-400">Pre-filled from PMS settings — modify to override.</p>
            </div>

            <div className="flex gap-2">
              <button type="button" onClick={() => setShowCreate(false)}
                className="flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700">
                Cancel
              </button>
              <button type="button" onClick={handleCreate}
                disabled={creating || !period || preview.filter((e) => !e.in_session_id).length === 0}
                className="flex-1 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700 disabled:opacity-50">
                {creating ? 'Creating…' : `Create (${preview.filter((e) => !e.in_session_id).length} employees)`}
              </button>
            </div>
          </div>
        )}

        {loading ? <SkeletonTable rows={3} /> : sessions.length === 0 ? (
          <p className="text-xs italic text-slate-400">No normalization sessions yet.</p>
        ) : (
          <div className="space-y-2">
            {sessions.map((s) => {
              const tone = NORM_STATUS_TONE[s.status] || { bg: '#F1F5F9', fg: '#475569' };
              return (
                <button key={s.id} type="button" onClick={() => { setSelected(s); setEditing(false); }}
                  className={`w-full rounded-xl border p-3 text-left transition ${
                    selected?.id === s.id ? 'border-blue-400 bg-blue-50' : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}>
                  <p className="text-sm font-semibold text-slate-800">{s.period}</p>
                  <div className="mt-1 flex items-center justify-between">
                    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold"
                      style={{ backgroundColor: tone.bg, color: tone.fg }}>
                      {NORM_STATUS_LABEL[s.status] || s.status}
                    </span>
                    <span className="text-[10px] text-slate-400">{s.records?.length || 0} employees</span>
                  </div>
                  {/* CHANGE 3: show deadline in session card */}
                  {s.deadline && (
                    <p className="mt-1 flex items-center gap-1 text-[10px] text-amber-600">
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                      Due: {new Date(s.deadline).toLocaleDateString()}
                    </p>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Session detail */}
      <div className="lg:col-span-2">
        {!selected ? (
          <div className="flex h-48 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white">
            <p className="text-sm text-slate-400">Select a session to manage records</p>
          </div>
        ) : (
          <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
            {/* ── Session header with Edit / Delete (Issue 4) ── */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
              <div>
                <p className="text-sm font-bold text-slate-800">Normalization — {selected.period}</p>
                <p className="text-xs text-slate-400">{selected.records?.length || 0} employees</p>
                {/* CHANGE 3: display session deadline in detail header */}
                {selected.deadline && (
                  <p className="mt-0.5 flex items-center gap-1 text-[11px] text-amber-600">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    Deadline: {new Date(selected.deadline).toLocaleString()}
                  </p>
                )}
              </div>
              {error && <p className="w-full text-xs text-red-600">{error}</p>}
              <div className="flex flex-wrap gap-2">
                {/* Add Employees button — scan for newly-locked ECAs */}
                {[NORM_STATUS.DRAFT, NORM_STATUS.NORMALIZED].includes(selected.status) && !editing && (
                  <button type="button" onClick={handleAddRecords} disabled={!!busy}
                    title="Scan for newly-locked end-cycle assessments and add them to this session"
                    className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100 disabled:opacity-50">
                    {busy === 'AddRecords' ? 'Scanning…' : '+ Add Employees'}
                  </button>
                )}
                {/* Edit button — only for draft / normalized sessions */}
                {[NORM_STATUS.DRAFT, NORM_STATUS.NORMALIZED].includes(selected.status) && !editing && (
                  <button type="button" onClick={handleEditOpen} disabled={!!busy}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                    ✏ Edit
                  </button>
                )}
                {/* Delete button — only for draft sessions */}
                {selected.status === NORM_STATUS.DRAFT && !editing && (
                  <button type="button" onClick={handleDelete} disabled={!!busy}
                    className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-600 hover:bg-red-100 disabled:opacity-50">
                    {busy === 'Delete' ? 'Deleting…' : '🗑 Delete'}
                  </button>
                )}
                {/* Normalize Ratings — optional step; HR can skip straight to Freeze */}
                {selected.status === NORM_STATUS.DRAFT && (
                  <button type="button" disabled={!!busy}
                    onClick={() => act(() => pmsApi.normalizeSession(selected.id, {}), 'Normalize', selected.id)}
                    title="Pre-compute weighted ratings (30% self + 70% manager). Optional — Freeze will auto-normalize if skipped."
                    className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-600 hover:bg-blue-100 disabled:opacity-50">
                    {busy === 'Normalize' ? 'Working…' : 'Normalize Ratings (optional)'}
                  </button>
                )}
                {/* Freeze Ratings — available from both DRAFT and NORMALIZED */}
                {[NORM_STATUS.DRAFT, NORM_STATUS.NORMALIZED].includes(selected.status) && (
                  <button type="button" disabled={!!busy}
                    onClick={() => act(() => pmsApi.freezeSession(selected.id, {}), 'Freeze', selected.id)}
                    className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-700 disabled:opacity-50">
                    {busy === 'Freeze' ? 'Working…' : 'Freeze Ratings'}
                  </button>
                )}
                {/* CHANGE 5: "Submit Hikes" replaces "Generate Hike". All hike_percent must be manually filled. */}
                {selected.status === NORM_STATUS.FROZEN && (
                  <button type="button" disabled={!!busy}
                    onClick={() => {
                      const missing = (selected.records || []).filter((r) => r.hike_percent == null);
                      if (missing.length > 0) {
                        setError(`Hike % must be entered for all employees before submitting. Missing: ${missing.map((r) => r.employee_name).join(', ')}.`);
                        return;
                      }
                      setError('');
                      act(() => pmsApi.generateHike(selected.id, {}), 'Submit Hikes', selected.id);
                    }}
                    className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50">
                    {busy === 'Submit Hikes' ? 'Working…' : 'Submit Hikes'}
                  </button>
                )}
                {selected.status === NORM_STATUS.HIKE_GENERATED && (
                  <button type="button" disabled={!!busy}
                    onClick={() => act(() => pmsApi.approveHike(selected.id, {}), 'Approve Hike', selected.id)}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50">
                    {busy === 'Approve Hike' ? 'Working…' : 'Approve Hike'}
                  </button>
                )}
              </div>
            </div>

            {/* Issue 4: Inline edit form */}
            {editing && (
              <div className="border-b border-slate-100 bg-slate-50/60 px-5 py-4 space-y-3">
                <p className="text-xs font-bold uppercase tracking-wider text-slate-500">Edit Session</p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-600">Period</label>
                    <input className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
                      value={editPeriod} onChange={(e) => setEditPeriod(e.target.value)} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-600">Notes</label>
                    <input className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs"
                      value={editNotes} onChange={(e) => setEditNotes(e.target.value)} />
                  </div>
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setEditing(false)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:text-slate-700">Cancel</button>
                  <button type="button" onClick={handleEditSave} disabled={saving}
                    className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50">
                    {saving ? 'Saving…' : 'Save Changes'}
                  </button>
                </div>
              </div>
            )}

            {/* Records table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-2.5 text-left">Employee</th>
                    <th className="px-4 py-2.5 text-center">Self</th>
                    <th className="px-4 py-2.5 text-center">Manager</th>
                    <th className="px-4 py-2.5 text-center">Normalized</th>
                    <th className="px-4 py-2.5 text-center">Override (+ Justification)</th>
                    <th className="px-4 py-2.5 text-center">Final</th>
                    <th className="px-4 py-2.5 text-center">Hike %</th>
                    <th className="px-4 py-2.5 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(selected.records || []).map((rec) => (
                    <NormRecordRow
                      key={rec.id}
                      rec={rec}
                      // frozen = ratings are locked (override_rating cannot change)
                      frozen={[NORM_STATUS.FROZEN, NORM_STATUS.HIKE_GENERATED, NORM_STATUS.HIKE_APPROVED].includes(selected.status)}
                      // hikeEditable = hike % can still be edited after freeze (until hike approved)
                      hikeEditable={[NORM_STATUS.FROZEN, NORM_STATUS.HIKE_GENERATED].includes(selected.status)}
                      sessionId={selected.id}
                      onUpdated={() => refreshSelected(selected.id)}
                    />
                  ))}
                  {(!selected.records || selected.records.length === 0) && (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center">
                        <p className="text-sm font-semibold text-slate-600">No employees in this session yet.</p>
                        <p className="mt-1 text-xs text-slate-400">
                          Make sure end-cycle assessments for period <strong>{selected.period}</strong> are locked,
                          then click <strong>"+ Add Employees"</strong> above.
                        </p>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
      {confirmEl}
    </div>
  );
}

function NormRecordRow({ rec, frozen, hikeEditable, sessionId, onUpdated }) {
  // editing modes: null = read, 'full' = override+hike+reason, 'hike' = hike % only
  const [editMode, setEditMode] = useState(null);
  const [override, setOverride] = useState(rec.override_rating != null ? String(rec.override_rating) : '');
  const [reason, setReason]     = useState(rec.override_reason || '');
  const [hike, setHike]         = useState(rec.hike_percent != null ? String(rec.hike_percent) : '');
  const [saving, setSaving]     = useState(false);
  const [rowToast, rowToastEl]  = usePmsToast();

  const openFull = () => {
    setOverride(rec.override_rating != null ? String(rec.override_rating) : '');
    setReason(rec.override_reason || '');
    setHike(rec.hike_percent != null ? String(rec.hike_percent) : '');
    setEditMode('full');
  };

  const openHikeOnly = () => {
    setHike(rec.hike_percent != null ? String(rec.hike_percent) : '');
    setEditMode('hike');
  };

  const cancel = () => setEditMode(null);

  const save = async (hikeOnly = false) => {
    const hikeVal = hike !== '' ? parseFloat(hike) : null;
    if (hikeVal !== null && (hikeVal < 0 || hikeVal > 100)) {
      rowToast('Hike % must be between 0 and 100.', 'error'); return;
    }

    const payload = { hike_percent: hikeVal };

    if (!hikeOnly) {
      const overrideVal = override !== '' ? parseFloat(override) : null;
      if (overrideVal !== null && (overrideVal < 1 || overrideVal > 5)) {
        rowToast('Override rating must be between 1.0 and 5.0.', 'error'); return;
      }
      // Override reason is OPTIONAL — no longer enforced
      payload.override_rating = overrideVal;
      payload.override_reason = reason.trim() || null;
    }

    setSaving(true);
    try {
      await pmsApi.updateNormRecord(sessionId, rec.id, payload);
      setEditMode(null);
      onUpdated();
    } catch (e) {
      rowToast(e?.data?.detail || e?.message || 'Save failed.', 'error');
    } finally { setSaving(false); }
  };

  const fmt = (v) => v != null ? v.toFixed(1) : '—';

  return (
    <>
      {rowToastEl}
      <tr className="hover:bg-slate-50/50">
        <td className="px-4 py-3 font-semibold text-slate-800">{rec.employee_name}</td>
        <td className="px-4 py-3 text-center text-slate-500">{fmt(rec.raw_self_rating)}</td>
        <td className="px-4 py-3 text-center text-slate-500">{fmt(rec.raw_manager_rating)}</td>
        <td className="px-4 py-3 text-center font-semibold text-blue-600">{fmt(rec.normalized_rating)}</td>

        {/* Override rating column */}
        <td className="px-4 py-3 text-center">
          {editMode === 'full' ? (
            <div className="space-y-1">
              <input type="number" min="1" max="5" step="0.1"
                className="w-16 rounded border border-violet-300 px-1.5 py-0.5 text-center text-xs focus:outline-none focus:ring-1 focus:ring-violet-400"
                placeholder="1–5"
                value={override} onChange={(e) => setOverride(e.target.value)} />
              <p className="text-[9px] text-slate-400 text-center">optional · 1.0–5.0</p>
            </div>
          ) : (
            <div>
              <span className={rec.override_rating != null ? 'font-semibold text-violet-600' : 'text-slate-300'}>
                {fmt(rec.override_rating)}
              </span>
              {rec.override_reason && (
                <p className="mt-0.5 truncate max-w-[100px] text-[9px] text-slate-400" title={rec.override_reason}>
                  {rec.override_reason}
                </p>
              )}
            </div>
          )}
        </td>

        {/* Final rating column */}
        <td className="px-4 py-3 text-center font-bold text-slate-800">{fmt(rec.final_rating)}</td>

        {/* Hike % column — editable in all modes */}
        <td className="px-4 py-3 text-center">
          {(editMode === 'full' || editMode === 'hike') ? (
            <div className="flex items-center gap-1 justify-center">
              <input type="number" min="0" max="100" step="0.5"
                className="w-14 rounded border border-emerald-300 px-1.5 py-0.5 text-center text-xs focus:outline-none focus:ring-1 focus:ring-emerald-400"
                value={hike} onChange={(e) => setHike(e.target.value)} />
              <span className="text-slate-400 text-xs">%</span>
            </div>
          ) : (
            <span className={rec.hike_percent != null ? 'font-semibold text-emerald-600' : 'text-slate-300'}>
              {rec.hike_percent != null ? `${rec.hike_percent.toFixed(1)}%` : '—'}
            </span>
          )}
        </td>

        {/* Actions column */}
        <td className="px-4 py-3 text-center">
          {editMode === 'full' ? (
            <div className="space-y-2 min-w-[160px]">
              {/* Override reason — optional */}
              <textarea rows={2}
                className="w-full resize-none rounded border border-slate-200 px-1.5 py-1 text-[10px] focus:outline-none focus:border-violet-300"
                placeholder="Reason for override (optional)…"
                value={reason} onChange={(e) => setReason(e.target.value)} />
              <div className="flex gap-1">
                <button type="button" onClick={() => save(false)} disabled={saving}
                  className="flex-1 rounded bg-emerald-500 px-2 py-0.5 text-[10px] font-bold text-white hover:bg-emerald-600 disabled:opacity-50">
                  {saving ? '…' : '✓ Save'}
                </button>
                <button type="button" onClick={cancel}
                  className="rounded bg-slate-200 px-2 py-0.5 text-[10px] text-slate-600 hover:bg-slate-300">✕</button>
              </div>
            </div>
          ) : editMode === 'hike' ? (
            <div className="flex gap-1 justify-center">
              <button type="button" onClick={() => save(true)} disabled={saving}
                className="rounded bg-emerald-500 px-2 py-0.5 text-[10px] font-bold text-white hover:bg-emerald-600 disabled:opacity-50">
                {saving ? '…' : '✓'}
              </button>
              <button type="button" onClick={cancel}
                className="rounded bg-slate-200 px-2 py-0.5 text-[10px] text-slate-600 hover:bg-slate-300">✕</button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-1">
              {/* Full edit — only when ratings are not frozen */}
              {!frozen && (
                <button type="button" onClick={openFull}
                  className="rounded border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-700">
                  ✏ Edit
                </button>
              )}
              {/* Hike-only edit — available after freeze until hike approved */}
              {frozen && hikeEditable && (
                <button type="button" onClick={openHikeOnly}
                  className="rounded border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-semibold text-emerald-700 hover:bg-emerald-100">
                  ✏ Hike%
                </button>
              )}
            </div>
          )}
        </td>
      </tr>
    </>
  );
}


// ── Phase 5: Compensation Tab ─────────────────────────────────────────────────

function CompensationTab() {
  const [sessions, setSessions]   = useState([]);
  const [selected, setSelected]   = useState(null);
  const [revisions, setRevisions] = useState([]);
  const [loading, setLoading]     = useState(true);
  const [effectiveFrom, setEffectiveFrom] = useState('');
  const [generating, setGenerating] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [error, setError]         = useState('');
  const [toast, toastEl] = usePmsToast();
  const [confirm, confirmEl] = useConfirm();

  const loadSessions = () => {
    setLoading(true);
    pmsApi.normSessions()
      .then((d) => setSessions((Array.isArray(d) ? d : []).filter((s) => s.status === NORM_STATUS.HIKE_APPROVED)))
      .catch(() => {}).finally(() => setLoading(false));
  };

  const loadRevisions = (sessId) => {
    pmsApi.revisions({ session_id: sessId })
      .then((d) => setRevisions(Array.isArray(d) ? d : []))
      .catch(() => setRevisions([]));
  };

  useEffect(() => { loadSessions(); }, []);
  useEffect(() => {
    // Clear stale revisions immediately when switching sessions so old
    // employee names don't flash while the new data loads.
    setRevisions([]);
    if (selected) loadRevisions(selected.id);
  }, [selected]);

  const handleGenerate = async () => {
    if (!effectiveFrom) { setError('Effective date is required.'); return; }
    setGenerating(true); setError('');
    try {
      await pmsApi.generateRevisions(selected.id, { effective_from: effectiveFrom });
      loadRevisions(selected.id);
    } catch (e) { setError(e?.data?.detail || e?.message || 'Generation failed.'); }
    finally { setGenerating(false); }
  };

  const handleArchive = () => {
    confirm('Archive this cycle? This action cannot be undone.', async () => {
      setArchiving(true); setError('');
      try {
        await pmsApi.archiveCycle(selected.id, {});
        toast('Cycle archived successfully.');
        loadSessions();
      } catch (e) { setError(e?.data?.detail || e?.message || 'Archive failed.'); }
      finally { setArchiving(false); }
    });
  };

  const acknowledged = revisions.filter((r) => !!r.employee_acknowledged_at).length;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Session picker */}
      <div className="lg:col-span-1">
        <p className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
          Approved Cycles
        </p>
        {loading ? <SkeletonTable rows={3} /> : sessions.length === 0 ? (
          <p className="text-xs text-slate-400 italic">No hike-approved sessions. Complete Phase 4 first.</p>
        ) : (
          <div className="space-y-2">
            {sessions.map((s) => (
              <button key={s.id} type="button" onClick={() => setSelected(s)}
                className={`w-full rounded-xl border p-3 text-left transition ${
                  selected?.id === s.id ? 'border-blue-400 bg-blue-50' : 'border-slate-200 bg-white hover:border-slate-300'
                }`}>
                <p className="text-sm font-semibold text-slate-800">{s.period}</p>
                <p className="mt-0.5 text-[10px] text-slate-400">
                  {s.records?.length || 0} employees · Hike Approved
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Compensation detail */}
      <div className="lg:col-span-2">
        {!selected ? (
          <div className="flex h-48 items-center justify-center rounded-2xl border border-dashed border-slate-200 bg-white">
            <p className="text-sm text-slate-400">Select a session to manage compensation</p>
          </div>
        ) : (
          <div className="space-y-4">
            {error && <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

            {/* Generate letters */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <p className="mb-3 text-sm font-bold text-slate-800">Generate Revision Letters</p>
              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-600">Effective From *</label>
                  <input type="date" className="rounded-lg border border-slate-200 px-3 py-2 text-xs"
                    value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} />
                </div>
                <button type="button" onClick={handleGenerate} disabled={generating || !effectiveFrom}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50">
                  {generating ? 'Generating…' : 'Generate Letters'}
                </button>
                {revisions.length > 0 && (
                  <button type="button" onClick={handleArchive} disabled={archiving}
                    className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50">
                    {archiving ? 'Archiving…' : 'Archive Cycle'}
                  </button>
                )}
              </div>
              {revisions.length > 0 && (
                <p className="mt-2 text-xs text-slate-500">
                  {acknowledged} / {revisions.length} employees acknowledged
                </p>
              )}
            </div>

            {/* Revisions table */}
            {revisions.length > 0 && (
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    <tr>
                      <th className="px-4 py-2.5 text-left">Employee</th>
                      <th className="px-4 py-2.5 text-right">Old CTC</th>
                      <th className="px-4 py-2.5 text-right">New CTC</th>
                      <th className="px-4 py-2.5 text-center">Hike %</th>
                      <th className="px-4 py-2.5 text-center">Acknowledged</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {revisions.map((rev) => (
                      <tr key={rev.id} className="hover:bg-slate-50/50">
                        <td className="px-4 py-3 font-semibold text-slate-800">{rev.employee_name}</td>
                        <td className="px-4 py-3 text-right text-slate-500">
                          {rev.old_ctc ? `₹${rev.old_ctc.toLocaleString('en-IN')}` : '—'}
                        </td>
                        <td className="px-4 py-3 text-right font-semibold text-emerald-600">
                          {rev.new_ctc ? `₹${rev.new_ctc.toLocaleString('en-IN')}` : '—'}
                        </td>
                        <td className="px-4 py-3 text-center font-bold text-amber-600">
                          {rev.hike_percent != null ? `${rev.hike_percent.toFixed(1)}%` : '—'}
                        </td>
                        <td className="px-4 py-3 text-center">
                          {rev.employee_acknowledged_at ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
                              ✓ {new Date(rev.employee_acknowledged_at).toLocaleDateString()}
                            </span>
                          ) : (
                            <span className="text-slate-300 text-[10px]">Pending</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
      {toastEl}
      {confirmEl}
    </div>
  );
}
