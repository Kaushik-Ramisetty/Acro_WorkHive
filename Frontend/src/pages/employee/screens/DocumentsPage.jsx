import { useState } from "react";
import { PageTitle, Card, Pill } from "../parts/UI";

const CATEGORIES = ["All", "Joining", "Payroll", "ID & Tax", "Personal"];

const DOCS = [
  { name: "Offer Letter",        cat: "Joining", size: "1.2 MB", type: "PDF", date: "Mar 15, 2023", icon: "🗒️", tone: "rose"   },
  { name: "Appointment Letter",  cat: "Joining", size: "0.9 MB", type: "PDF", date: "Apr 02, 2023", icon: "🗂️", tone: "blue"   },
  { name: "Salary Slips (Jan-Oct)", cat: "Payroll", size: "12 files",     type: "PDF", date: "Updated Oct 30, 2023", icon: "💰", tone: "green" },
  { name: "Form 16 (FY 2022-23)", cat: "ID & Tax", size: "0.6 MB",       type: "PDF", date: "Jul 10, 2023", icon: "📄", tone: "amber" },
  { name: "Employee ID Card",    cat: "ID & Tax", size: "0.3 MB",       type: "Image", date: "Apr 02, 2023", icon: "🪪", tone: "violet" },
  { name: "PAN Card",            cat: "Personal", size: "0.2 MB",       type: "Image", date: "Apr 02, 2023", icon: "🆔", tone: "slate" },
  { name: "Aadhaar Card",        cat: "Personal", size: "0.4 MB",       type: "Image", date: "Apr 02, 2023", icon: "🆔", tone: "slate" },
  { name: "Bank Account Details", cat: "Personal", size: "0.1 MB",       type: "PDF", date: "Apr 02, 2023", icon: "🏦", tone: "blue"   },
  { name: "Insurance Policy",    cat: "Personal", size: "1.5 MB",       type: "PDF", date: "Sep 12, 2023", icon: "🛡️", tone: "green" },
];

const DocumentsPage = () => {
  const [cat, setCat] = useState("All");
  const visible = cat === "All" ? DOCS : DOCS.filter(d => d.cat === cat);

  return (
    <div className="space-y-5">
      <PageTitle
        title="Documents"
        sub="Your offer letter, payslips, and other personal documents."
        right={
          <button className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold text-white" style={{ background: "#14b8a6" }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Upload
          </button>
        }
      />

      <Card padding="p-3">
        <div className="flex flex-wrap gap-1">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              onClick={() => setCat(c)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${cat === c ? "bg-teal-50 text-teal-600 border border-teal-200" : "text-slate-500 hover:bg-slate-50 border border-transparent"}`}
            >
              {c}
            </button>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {visible.map((d) => (
          <Card key={d.name} padding="p-4" className="flex items-center gap-3 hover:border-teal-200 transition-colors">
            <div className="w-12 h-12 rounded-xl bg-slate-50 flex items-center justify-center text-2xl flex-shrink-0">{d.icon}</div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-800 truncate">{d.name}</p>
              <p className="text-[11px] text-slate-400">{d.size} · {d.type}</p>
              <p className="text-[10px] text-slate-400">{d.date}</p>
            </div>
            <div className="flex flex-col gap-2">
              <button className="w-8 h-8 rounded-md border border-slate-200 flex items-center justify-center text-slate-500 hover:text-teal-600 hover:border-teal-300" aria-label="View">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
              </button>
              <button className="w-8 h-8 rounded-md border border-slate-200 flex items-center justify-center text-slate-500 hover:text-teal-600 hover:border-teal-300" aria-label="Download">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              </button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default DocumentsPage;
