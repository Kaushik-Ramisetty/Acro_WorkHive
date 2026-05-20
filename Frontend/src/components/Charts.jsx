// Lightweight inline-SVG charts: Donut, MiniBars, SparkLine, ProgressBar.

export function Donut({ value = 0, max = 100, size = 110, stroke = 12, color = '#1e3acb', track = '#e2e8f0', children }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.min(value / max, 1);
  const dash = c * pct;
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke={track} strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - dash}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">{children}</div>
    </div>
  );
}

export function DonutMulti({ segments, size = 160, stroke = 22, gap = 0.01 }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  let offset = 0;
  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} stroke="#e2e8f0" strokeWidth={stroke} fill="none" />
      {segments.map((s, i) => {
        const frac = s.value / total;
        const dash = Math.max(c * (frac - gap), 0);
        const space = c - dash;
        const el = (
          <circle
            key={i}
            cx={size / 2}
            cy={size / 2}
            r={r}
            stroke={s.color}
            strokeWidth={stroke}
            fill="none"
            strokeDasharray={dash + ' ' + space}
            strokeDashoffset={-offset}
          />
        );
        offset += c * frac;
        return el;
      })}
    </svg>
  );
}

export function MiniBars({ data = [], height = 130, color = '#10b981', highlight }) {
  if (!data.length) return null;
  const max = Math.max(...data.map((d) => d.value));
  const w = 100 / data.length;
  return (
    <div className="w-full">
      <div className="flex items-end gap-1.5" style={{ height }}>
        {data.map((d, i) => {
          const h = (d.value / max) * (height - 24);
          const isHi = highlight === i;
          return (
            <div key={i} className="flex flex-1 flex-col items-center justify-end">
              <div
                className="w-full rounded-t-md"
                style={{
                  height: h,
                  background: isHi ? '#0d9488' : color,
                  opacity: isHi ? 1 : 0.85,
                }}
                title={d.value}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex">
        {data.map((d, i) => (
          <div key={i} className="flex-1 text-center text-[11px] text-slate-500">
            {d.label}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SparkLine({ data = [], width = 480, height = 200, color = '#10b981', showPoints = true, showAxis = true }) {
  if (!data.length) return null;
  const max = Math.max(...data.map((d) => d.value));
  const min = Math.min(...data.map((d) => d.value));
  const range = max - min || 1;
  const padX = 36;
  const padY = 18;
  const W = width - padX * 2;
  const H = height - padY * 2;
  const points = data.map((d, i) => {
    const x = padX + (i / (data.length - 1)) * W;
    const y = padY + H - ((d.value - min) / range) * H;
    return [x, y];
  });
  const pathD = points.map((p, i) => (i === 0 ? 'M' : 'L') + p[0] + ',' + p[1]).join(' ');
  const areaD = pathD + ' L' + points[points.length - 1][0] + ',' + (padY + H) + ' L' + padX + ',' + (padY + H) + ' Z';

  // Y-axis ticks (4 lines)
  const ticks = [0, 0.33, 0.66, 1].map((t) => Math.round(min + t * range));

  return (
    <svg viewBox={'0 0 ' + width + ' ' + height} className="w-full">
      {showAxis &&
        ticks.map((t, i) => {
          const y = padY + H - (i / 3) * H;
          return (
            <g key={i}>
              <line x1={padX} x2={padX + W} y1={y} y2={y} stroke="#e2e8f0" strokeDasharray="2 4" />
              <text x={padX - 8} y={y + 3} textAnchor="end" className="fill-slate-400 text-[10px]">
                {t.toLocaleString()}
              </text>
            </g>
          );
        })}
      <path d={areaD} fill={color} opacity="0.12" />
      <path d={pathD} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {showPoints &&
        points.map(([x, y], i) => (
          <g key={i}>
            <circle cx={x} cy={y} r="4" fill="white" stroke={color} strokeWidth="2" />
            <text x={x} y={y - 10} textAnchor="middle" className="fill-slate-700 text-[10px] font-semibold">
              {data[i].value.toLocaleString()}
            </text>
          </g>
        ))}
      {showAxis &&
        data.map((d, i) => {
          const x = padX + (i / (data.length - 1)) * W;
          return (
            <text key={i} x={x} y={height - 4} textAnchor="middle" className="fill-slate-500 text-[10px]">
              {d.label}
            </text>
          );
        })}
    </svg>
  );
}

export function ProgressBar({ value = 0, max = 100, color = '#10b981', track = 'bg-slate-100', height = 8 }) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div className={'w-full overflow-hidden rounded-full ' + track} style={{ height }}>
      <div className="h-full rounded-full transition-all" style={{ width: pct + '%', background: color }} />
    </div>
  );
}

export function Funnel({ data = [] }) {
  const max = Math.max(...data.map((d) => d.value));
  return (
    <div className="space-y-2">
      {data.map((d, i) => {
        const pct = (d.value / max) * 100;
        return (
          <div key={d.label} className="flex items-center gap-3">
            <div className="w-24 text-right text-xs text-slate-600">{d.label}</div>
            <div className="relative flex-1 overflow-hidden rounded-md bg-slate-100" style={{ height: 28 }}>
              <div
                className="h-full rounded-md transition-all"
                style={{
                  width: pct + '%',
                  background: 'linear-gradient(90deg, ' + (d.color || '#1e3acb') + ', ' + (d.color2 || '#3b82f6') + ')',
                }}
              />
            </div>
            <div className="w-14 text-right text-xs font-semibold text-slate-700">{d.value.toLocaleString()}</div>
          </div>
        );
      })}
    </div>
  );
}

export function Heatmap({ rows = 4, cols = 7, scale = [], cellSize = 14, gap = 3 }) {
  // scale: array of {value} length rows*cols. Color from light to dark blue.
  const palette = ['#dbeafe', '#bfdbfe', '#93c5fd', '#60a5fa', '#3b82f6', '#1d4ed8'];
  return (
    <div className="inline-grid" style={{ gridTemplateColumns: 'repeat(' + cols + ', ' + cellSize + 'px)', gap }}>
      {Array.from({ length: rows * cols }).map((_, i) => {
        const v = scale[i] ?? Math.random();
        const idx = Math.min(Math.floor(v * palette.length), palette.length - 1);
        return <div key={i} style={{ width: cellSize, height: cellSize, background: palette[idx], borderRadius: 3 }} />;
      })}
    </div>
  );
}
