import { useState } from "react";
import { PageTitle, Card, Pill } from "../parts/UI";

const GOALS = [
  { id: 1, title: "Launch new design system v2",          owner: "Self",         due: "Oct 31, 2023", progress: 92, priority: "High",     category: "Design" },
  { id: 2, title: "Complete React 19 migration",          owner: "Marcus Chen",  due: "Nov 15, 2023", progress: 78, priority: "High",     category: "Engineering" },
  { id: 3, title: "User research report Q4",              owner: "Lucia F.",     due: "Nov 30, 2023", progress: 45, priority: "Medium",   category: "Research" },
  { id: 4, title: "Implement CI/CD pipeline",             owner: "Arjun Gupta",  due: "Nov 20, 2023", progress: 60, priority: "High",     category: "DevOps" },
  { id: 5, title: "Mentor 2 junior designers",            owner: "Self",         due: "Dec 31, 2023", progress: 35, priority: "Medium",   category: "Leadership" },
  { id: 6, title: "Achieve AWS certification",            owner: "Self",         due: "Dec 10, 2023", progress: 20, priority: "Low",      category: "Learning" },
];

const PRIORITY_TONE = { High: "rose", Medium: "amber", Low: "slate", Critical: "rose" };

const progressTone = (n) => n >= 80 ? "#14b8a6" : n >= 50 ? "#3b82f6" : n >= 30 ? "#f59e0b" : "#ef4444";

const GoalsPage = () => {
  const [filter, setFilter] = useState("All");
  const tabs = ["All", "On Track", "At Risk"];
  const visible = GOALS.filter((g) => {
    if (filter === "All") return true;
    if (filter === "On Track") return g.progress >= 50;
    if (filter === "At Risk") return g.progress < 50;
    return true;
  });

  return (
    <div className="space-y-5">
      <PageTitle
        title="Goals"
        sub="Track your goals and progress for this cycle."
        right={
          <button className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold text-white" style={{ background: "#14b8a6" }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            New Goal
          </button>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { l: "Total Goals",   v: GOALS.length, c: "text-slate-700" },
          { l: "On Track",      v: GOALS.filter(g => g.progress >= 50).length, c: "text-emerald-600" },
          { l: "At Risk",       v: GOALS.filter(g => g.progress < 50 && g.progress >= 30).length, c: "text-amber-600" },
          { l: "Behind",        v: GOALS.filter(g => g.progress < 30).length, c: "text-rose-600" },
        ].map((s) => (
          <Card key={s.l} padding="p-4">
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{s.l}</p>
            <p className={`text-2xl font-bold ${s.c}`}>{s.v}</p>
          </Card>
        ))}
      </div>

      <Card padding="p-0">
        <div className="px-5 pt-4 border-b border-slate-100 flex flex-wrap gap-1">
          {tabs.map((t) => (
            <button
              key={t}
              onClick={() => setFilter(t)}
              className={`px-4 py-2 text-xs font-semibold border-b-2 ${filter === t ? "text-teal-600 border-teal-500" : "text-slate-500 border-transparent hover:text-slate-700"}`}
            >
              {t}
            </button>
          ))}
        </div>
        <div className="p-5 space-y-3">
          {visible.map((g) => {
            const c = progressTone(g.progress);
            return (
              <div key={g.id} className="border border-slate-100 rounded-xl p-4 hover:border-teal-200 transition-colors">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h4 className="text-sm font-semibold text-slate-800">{g.title}</h4>
                    <p className="text-[11px] text-slate-400 mt-0.5">{g.category} · Owner: {g.owner} · Due {g.due}</p>
                  </div>
                  <Pill tone={PRIORITY_TONE[g.priority] || "slate"}>{g.priority}</Pill>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${g.progress}%`, background: c }} />
                  </div>
                  <span className="text-xs font-bold tabular-nums" style={{ color: c }}>{g.progress}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
};

export default GoalsPage;
