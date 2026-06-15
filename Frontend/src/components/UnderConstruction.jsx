/**
 * UnderConstruction — "Work in Progress" placeholder used in pages
 * whose feature is on the roadmap but not yet built.
 *
 * Props:
 *   title       (string, required)  — large headline shown to the user
 *   description (string, optional)  — one or two sentences below the title
 *   features    (array,  optional)  — items shown in the "What's coming" grid:
 *                                     [{ label: string, icon: ReactNode }]
 *   accent      (string, optional)  — Tailwind color token base, default 'teal'
 *
 * Visual structure (top → bottom):
 *   - Soft glow + gradient icon medallion
 *   - "Under Construction" eyebrow
 *   - Headline + supporting copy
 *   - Optional 3-up feature grid ("What's coming")
 *   - Animated live-indicator strip
 */

const ACCENTS = {
  teal:   { dotBg: 'bg-teal-500',   dotPing: 'bg-teal-400',   eyebrow: 'text-teal-600',
            tile: 'bg-teal-50 text-teal-600',     glow: 'from-teal-300 to-blue-400',
            chip: 'from-teal-400 to-teal-600' },
  violet: { dotBg: 'bg-violet-500', dotPing: 'bg-violet-400', eyebrow: 'text-violet-600',
            tile: 'bg-violet-50 text-violet-600', glow: 'from-violet-300 to-pink-400',
            chip: 'from-violet-400 to-violet-600' },
  amber:  { dotBg: 'bg-amber-500',  dotPing: 'bg-amber-400',  eyebrow: 'text-amber-600',
            tile: 'bg-amber-50 text-amber-600',   glow: 'from-amber-300 to-orange-400',
            chip: 'from-amber-400 to-amber-600' },
};

export default function UnderConstruction({
  title,
  description,
  features = [],
  accent = 'teal',
}) {
  const a = ACCENTS[accent] || ACCENTS.teal;

  return (
    <div className="flex flex-col items-center justify-center min-h-[70vh] px-6 py-10">
      {/* Local keyframes scoped to this component. */}
      <style>{`
        @keyframes wip-medallion-float {
          0%, 100% { transform: translateY(0); }
          50%      { transform: translateY(-6px); }
        }
        @keyframes wip-medallion-glow {
          0%, 100% { opacity: 0.35; transform: scale(1); }
          50%      { opacity: 0.55; transform: scale(1.10); }
        }
        @keyframes wip-icon-spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes wip-eyebrow-shimmer {
          0%   { background-position: 0% 50%; }
          100% { background-position: 200% 50%; }
        }
      `}</style>

      {/* Icon medallion ─ gradient chip with soft glow behind it */}
      <div className="relative mb-8" style={{ animation: 'wip-medallion-float 3.6s ease-in-out infinite' }}>
        <div
          className={
            'absolute inset-0 rounded-full blur-2xl bg-gradient-to-br ' + a.glow
          }
          style={{ animation: 'wip-medallion-glow 3.6s ease-in-out infinite' }}
        />
        <div
          className={
            'relative w-28 h-28 rounded-3xl bg-gradient-to-br ' +
            a.chip +
            ' flex items-center justify-center shadow-lg'
          }
        >
          {/* Stylized "tools" mark — wrench + small accent gear */}
          <svg
            width="56"
            height="56"
            viewBox="0 0 48 48"
            fill="none"
            stroke="white"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
            style={{ animation: 'wip-icon-spin 18s linear infinite', transformOrigin: 'center' }}
          >
            {/* wrench */}
            <path d="M30 12.5a6 6 0 0 0 7.4 7.4l4.6-4.6a8 8 0 0 1-10.8 10.8L17 41.3a3 3 0 0 1-4.3-4.3l14.2-14.2A8 8 0 0 1 37.7 12L33 16.7l-3-4.2z" />
            {/* small gear in lower-right */}
            <circle cx="36.5" cy="35.5" r="3" />
            <path d="M36.5 30v2 M36.5 39v2 M31 35.5h2 M40 35.5h2 M32.7 31.7l1.4 1.4 M38.9 37.9l1.4 1.4 M32.7 39.3l1.4-1.4 M38.9 33.1l1.4-1.4" />
          </svg>
        </div>
      </div>

      {/* Eyebrow */}
      <span
        className={
          'text-[10px] font-bold uppercase tracking-[0.25em] mb-3 bg-clip-text text-transparent ' + a.eyebrow
        }
        style={{
          backgroundImage: 'linear-gradient(90deg, currentColor 0%, currentColor 40%, rgba(255,255,255,0.85) 50%, currentColor 60%, currentColor 100%)',
          backgroundSize: '200% 100%',
          WebkitBackgroundClip: 'text',
          animation: 'wip-eyebrow-shimmer 3.2s linear infinite',
        }}
      >
        Work in Progress
      </span>

      {/* Headline */}
      <h1 className="text-3xl font-bold text-slate-800 text-center">{title}</h1>

      {/* Supporting copy */}
      {description && (
        <p className="mt-3 text-sm text-slate-500 text-center max-w-md leading-relaxed">
          {description}
        </p>
      )}

      {/* Optional feature grid ─ "What's coming" */}
      {features.length > 0 && (
        <>
          <div className="my-8 h-px w-24 bg-slate-200" />
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-[0.2em] mb-4">
            What's coming
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-2xl w-full">
            {features.map((f, i) => (
              <div
                key={i}
                className="bg-white border border-slate-100 rounded-xl px-4 py-3 flex items-center gap-3 shadow-sm"
              >
                <span
                  className={
                    'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ' +
                    a.tile
                  }
                >
                  {f.icon}
                </span>
                <p className="text-xs font-semibold text-slate-700 leading-tight">
                  {f.label}
                </p>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Live indicator */}
      <div className="mt-10 flex items-center gap-2 text-xs text-slate-400">
        <span className="relative flex h-2 w-2">
          <span
            className={
              'animate-ping absolute inline-flex h-full w-full rounded-full opacity-60 ' +
              a.dotPing
            }
          />
          <span
            className={'relative inline-flex h-2 w-2 rounded-full ' + a.dotBg}
          />
        </span>
        <span>Our team is actively building this</span>
      </div>
    </div>
  );
}
