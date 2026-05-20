// Lightweight inline SVG icon set. Stroke-based, follows currentColor.

const baseProps = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
};

const PATHS = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M3 20c.8-3 3-5 6-5s5.2 2 6 5" />
      <path d="M14 20c.5-2 2-3.2 3.5-3.2S20.5 18 21 20" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 9h17M8 3v4M16 3v4" />
    </>
  ),
  leave: (
    <>
      <path d="M4 7h16v12H4z" />
      <path d="M4 7l8 6 8-6" />
    </>
  ),
  money: (
    <>
      <rect x="3" y="6" width="18" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M6 10v.01M18 14v.01" />
    </>
  ),
  doc: (
    <>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4" />
    </>
  ),
  chart: (
    <>
      <path d="M4 20V8M10 20v-6M16 20V4M22 20H2" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="1" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  briefcase: (
    <>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2" />
    </>
  ),
  graduation: (
    <>
      <path d="M3 9l9-4 9 4-9 4-9-4z" />
      <path d="M7 11v4c0 1.7 2.2 3 5 3s5-1.3 5-3v-4" />
    </>
  ),
  building: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="1.5" />
      <path d="M9 8h2M13 8h2M9 12h2M13 12h2M9 16h2M13 16h2" />
    </>
  ),
  megaphone: (
    <>
      <path d="M3 11v2a2 2 0 002 2h1l3 5h2l-1-5h2l8 3V6l-8 3H6a3 3 0 00-3 3z" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 00.34 1.87l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.7 1.7 0 00-1.87-.34 1.7 1.7 0 00-1.03 1.55V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.11-1.55 1.7 1.7 0 00-1.87.34l-.06.06A2 2 0 113.13 16.92l.06-.06a1.7 1.7 0 00.34-1.87 1.7 1.7 0 00-1.55-1.03H1.5a2 2 0 110-4h.1a1.7 1.7 0 001.55-1.11 1.7 1.7 0 00-.34-1.87l-.06-.06A2 2 0 015.58 4l.06.06a1.7 1.7 0 001.87.34h.04A1.7 1.7 0 008.5 2.85V2.5a2 2 0 014 0v.1a1.7 1.7 0 001.03 1.55 1.7 1.7 0 001.87-.34l.06-.06A2 2 0 0119.42 6l-.06.06a1.7 1.7 0 00-.34 1.87v.04a1.7 1.7 0 001.55 1.03H21a2 2 0 010 4h-.1a1.7 1.7 0 00-1.55 1.03z" />
    </>
  ),
  logout: (
    <>
      <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </>
  ),
  bell: (
    <>
      <path d="M6 8a6 6 0 0112 0c0 7 3 7 3 9H3c0-2 3-2 3-9z" />
      <path d="M10 21a2 2 0 004 0" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" />
    </>
  ),
  approve: (
    <>
      <path d="M20 6L9 17l-5-5" />
    </>
  ),
  reject: (
    <>
      <path d="M6 6l12 12M18 6L6 18" />
    </>
  ),
  plug: (
    <>
      <path d="M9 7V3M15 7V3M6 7h12v5a6 6 0 01-12 0V7zM12 18v3" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l8 3v5c0 4.5-3 8-8 10-5-2-8-5.5-8-10V6l8-3z" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9 9a3 3 0 015 2c0 1.5-2 2-2 3.5M12 17v.01" />
    </>
  ),
  chevronDown: <path d="M6 9l6 6 6-6" />,
  chevronLeft: <path d="M15 6l-6 6 6 6" />,
  chevronRight: <path d="M9 6l6 6-6 6" />,
  menu: <path d="M3 6h18M3 12h18M3 18h18" />,
  download: (
    <>
      <path d="M12 4v12M6 12l6 6 6-6M4 20h16" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  arrowRight: <path d="M5 12h14M13 6l6 6-6 6" />,
  arrowUp: <path d="M12 19V5M5 12l7-7 7 7" />,
  arrowDown: <path d="M12 5v14M5 12l7 7 7-7" />,
  send: <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />,
  folder: <path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />,
  chat: (
    <>
      <path d="M21 15a2 2 0 01-2 2H8l-5 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
    </>
  ),
  star: <path d="M12 3l2.7 6 6.3.6-4.8 4.4 1.5 6.4L12 17l-5.7 3.4 1.5-6.4L3 9.6l6.3-.6L12 3z" />,
  warning: (
    <>
      <path d="M12 3l10 18H2L12 3z" />
      <path d="M12 10v5M12 18v.01" />
    </>
  ),
};

export default function Icon({ name, className = 'h-5 w-5' }) {
  const path = PATHS[name];
  if (!path) return null;
  return (
    <svg viewBox="0 0 24 24" className={className} {...baseProps} aria-hidden>
      {path}
    </svg>
  );
}
