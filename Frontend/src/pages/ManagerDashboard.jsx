import DashboardLayout from '../components/DashboardLayout'

const STATS = [
  { label: 'Team Members', value: '14' },
  { label: 'Pending Leave Requests', value: '3' },
  { label: 'Reviews Due', value: '5' },
  { label: 'Open Tasks', value: '22' },
]

const REQUESTS = [
  { who: 'Aisha K.',   what: 'PTO – 3 days', when: 'May 4 – May 6' },
  { who: 'Daniel M.',  what: 'Work from home', when: 'Tomorrow' },
  { who: 'Sara L.',    what: 'Comp time',     when: 'May 12' },
]

export default function ManagerDashboard() {
  return (
    <DashboardLayout
      title="Manager Dashboard"
      subtitle="Approve requests, track team performance, and plan upcoming reviews."
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
          <h3 className="text-sm font-semibold text-slate-900">Pending Requests</h3>
          <table className="mt-4 w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                <th className="pb-2">Employee</th>
                <th className="pb-2">Type</th>
                <th className="pb-2">When</th>
                <th className="pb-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {REQUESTS.map((r) => (
                <tr key={r.who}>
                  <td className="py-3 font-medium text-slate-800">{r.who}</td>
                  <td className="py-3 text-slate-600">{r.what}</td>
                  <td className="py-3 text-slate-600">{r.when}</td>
                  <td className="py-3 text-right">
                    <button className="rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-100">
                      Approve
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900">Team Pulse</h3>
          <p className="mt-2 text-sm text-slate-600">
            14 active team members. 92% on-time check-ins this week.
          </p>
          <div className="mt-4 h-2 w-full rounded-full bg-slate-100">
            <div className="h-2 w-[92%] rounded-full bg-emerald-500" />
          </div>
          <p className="mt-2 text-xs text-slate-500">Engagement score is trending up.</p>
        </div>
      </section>
    </DashboardLayout>
  )
}
