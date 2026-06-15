import DashboardLayout from '../components/DashboardLayout'

const STATS = [
  { label: 'PTO Balance', value: '12 days' },
  { label: 'Next Payday', value: 'May 15' },
  { label: 'Open Tasks',  value: '4' },
  { label: 'Hours This Week', value: '32.5' },
]

const ANNOUNCEMENTS = [
  'Q2 town hall on May 8 at 11:00 AM. Calendar invites sent.',
  'New benefits portal goes live next Monday — review your selections.',
  'Office closed on May 27 for the public holiday.',
]

export default function EmployeeDashboard() {
  return (
    <DashboardLayout
      title="Employee Dashboard"
      subtitle="View your pay, manage time off, and stay on top of company updates."
      accent="#1e3acb"
    >
      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {STATS.map((s) => (
          <div key={s.label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{s.label}</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">{s.value}</p>
          </div>
        ))}
      </section>

      <section className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
          <h3 className="text-sm font-semibold text-slate-900">Announcements</h3>
          <ul className="mt-4 space-y-3 text-sm text-slate-700">
            {ANNOUNCEMENTS.map((a, i) => (
              <li key={i} className="flex gap-3">
                <span className="mt-1.5 inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full bg-brand-600" />
                <span>{a}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900">Quick Links</h3>
          <div className="mt-4 flex flex-col gap-2">
            {['Submit Time Off', 'View Payslip', 'Benefits Portal', 'Update Profile'].map((a) => (
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
