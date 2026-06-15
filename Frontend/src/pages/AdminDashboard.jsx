import DashboardLayout from '../components/DashboardLayout'

const STATS = [
  { label: 'Total Employees', value: '248', delta: '+12 this month' },
  { label: 'Open Positions',  value: '18',  delta: '4 in interview' },
  { label: 'Pending Approvals', value: '7',  delta: 'Awaiting review' },
  { label: 'System Health',  value: '99.9%', delta: 'All services up' },
]

const QUICK_ACTIONS = [
  'Manage Users & Roles',
  'Configure Pay Cycles',
  'Audit Logs',
  'Org-wide Announcements',
]

export default function AdminDashboard() {
  return (
    <DashboardLayout
      title="Admin Dashboard"
      subtitle="Configure the organization, manage users, and oversee global HR operations."
      accent="#1e3acb"
    >
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STATS.map((s) => (
          <div key={s.label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{s.label}</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">{s.value}</p>
            <p className="mt-1 text-xs text-slate-500">{s.delta}</p>
          </div>
        ))}
      </section>

      <section className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
          <h3 className="text-sm font-semibold text-slate-900">Recent Activity</h3>
          <ul className="mt-4 divide-y divide-slate-100 text-sm">
            <li className="flex items-center justify-between py-3">
              <span className="text-slate-700">New manager invited — Priya R.</span>
              <span className="text-xs text-slate-500">2h ago</span>
            </li>
            <li className="flex items-center justify-between py-3">
              <span className="text-slate-700">Payroll cycle #042 closed</span>
              <span className="text-xs text-slate-500">Yesterday</span>
            </li>
            <li className="flex items-center justify-between py-3">
              <span className="text-slate-700">Compliance audit exported</span>
              <span className="text-xs text-slate-500">3 days ago</span>
            </li>
          </ul>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900">Quick Actions</h3>
          <div className="mt-4 flex flex-col gap-2">
            {QUICK_ACTIONS.map((a) => (
              <button
                key={a}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm font-medium text-slate-700 transition hover:border-brand-500 hover:text-brand-600"
              >
                {a}
              </button>
            ))}
          </div>
        </div>
      </section>
    </DashboardLayout>
  )
}
