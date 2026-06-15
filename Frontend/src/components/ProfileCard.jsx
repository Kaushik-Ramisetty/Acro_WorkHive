import AvatarUpload from './AvatarUpload';

const ROLE_TONE = {
  admin:    { gradient: 'from-rose-500 to-orange-500',    badge: 'bg-rose-100 text-rose-700 ring-rose-200' },
  manager:  { gradient: 'from-amber-500 to-rose-500',     badge: 'bg-amber-100 text-amber-800 ring-amber-200' },
  employee: { gradient: 'from-emerald-500 to-teal-500',   badge: 'bg-emerald-100 text-emerald-700 ring-emerald-200' },
};

export default function ProfileCard({
  name, role, email, phone, position, department, location, joined,
  status = 'Active',
  cover = 'linear-gradient(135deg, #1E3A8A 0%, #2D4FC0 60%, #3B5BDB 100%)',
  onEdit,
  editing,
}) {
  const initials = (name || 'U').split(' ').map((s) => s[0]).slice(0, 2).join('').toUpperCase();
  const t = ROLE_TONE[role] || ROLE_TONE.employee;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      {/* Cover */}
      <div className="relative h-36 w-full" style={{ background: cover }}>
        <div className="pointer-events-none absolute -right-10 -top-10 h-44 w-44 rounded-full bg-white/10 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-10 -left-10 h-44 w-44 rounded-full bg-white/5 blur-2xl" />
      </div>

      {/* Header row: avatar overlaps cover; name block sits BELOW the cover edge */}
      <div className="px-6 pt-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:gap-6">
          {/* Avatar — pulled up into the cover, ringed so it reads as a separate element */}
          <div className="-mt-20 flex-shrink-0 rounded-full bg-white p-1.5 shadow-md ring-1 ring-slate-200">
            <AvatarUpload initials={initials} size={104} gradient={t.gradient} />
          </div>

          {/* Identity block */}
          <div className="min-w-0 flex-1 pt-1">
            <h2 className="truncate text-2xl font-bold tracking-tight text-slate-900">
              {name || 'Unnamed user'}
            </h2>
            {(position || department) && (
              <p className="mt-0.5 truncate text-sm text-slate-600">
                {position}
                {position && department ? ' · ' : ''}
                {department}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className={'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold capitalize ring-1 ' + t.badge}>
                <span className="h-1.5 w-1.5 rounded-full bg-current" /> {role}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> {status}
              </span>
              {joined && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
                  <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
                  Joined {joined}
                </span>
              )}
            </div>
          </div>

          {/* Edit slot — keeps the action visible at top-right on wide screens */}
          {onEdit && (
            <div className="sm:pt-1">
              <button
                onClick={onEdit}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
              >
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 1 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>
                {editing ? 'Done' : 'Edit'}
              </button>
            </div>
          )}
        </div>

        {/* Quick contact strip */}
        <div className="mt-5 grid grid-cols-1 gap-3 border-t border-slate-100 pt-4 pb-6 sm:grid-cols-3">
          {email && (
            <div className="flex items-center gap-2.5 text-sm text-slate-700">
              <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600 ring-1 ring-blue-100">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>
              </span>
              <span className="min-w-0 truncate" title={email}>{email}</span>
            </div>
          )}
          {phone && (
            <div className="flex items-center gap-2.5 text-sm text-slate-700">
              <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 16.92V21a1 1 0 0 1-1.1 1A19.86 19.86 0 0 1 2 4.1 1 1 0 0 1 3 3h4.09a1 1 0 0 1 1 .75l1 4a1 1 0 0 1-.27 1L7 10.5a16 16 0 0 0 6.5 6.5l1.74-1.79a1 1 0 0 1 1-.27l4 1a1 1 0 0 1 .76 1z"/></svg>
              </span>
              <span className="truncate">{phone}</span>
            </div>
          )}
          {location && (
            <div className="flex items-center gap-2.5 text-sm text-slate-700">
              <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600 ring-1 ring-amber-100">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
              </span>
              <span className="truncate">{location}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
