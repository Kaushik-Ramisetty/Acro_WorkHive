/**
 * Export timesheet entries to Excel (.xlsx) using SheetJS.
 * Requires: npm install xlsx
 *
 * Falls back to a CSV download if the xlsx package is not installed.
 */
export async function exportToXlsx(entries, filename) {
  try {
    const XLSX = await import('xlsx');
    const rows = [
      ['Day', 'Date', 'Client', 'Project', 'Task', 'Type', 'Hours', 'Status'],
      ...entries.map((e) => [
        e.day, e.date, e.client, e.project, e.task, e.type, e.hours, e.status,
      ]),
    ];
    const ws = XLSX.utils.aoa_to_sheet(rows);
    // Auto-width columns
    ws['!cols'] = [8, 12, 16, 20, 24, 14, 8, 12].map((w) => ({ wch: w }));
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Timesheet');
    XLSX.writeFile(wb, filename);
    return { ok: true };
  } catch {
    // xlsx not installed — fall back to CSV
    const escape = (v) => (String(v).includes(',') ? `"${v}"` : String(v));
    const csv = [
      ['Day', 'Date', 'Client', 'Project', 'Task', 'Type', 'Hours', 'Status']
        .map(escape)
        .join(','),
      ...entries.map((e) =>
        [e.day, e.date, e.client, e.project, e.task, e.type, e.hours, e.status]
          .map(escape)
          .join(',')
      ),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename.replace('.xlsx', '.csv');
    a.click();
    URL.revokeObjectURL(url);
    return {
      ok: false,
      note: 'Downloaded as CSV — run npm install xlsx to enable Excel export',
    };
  }
}
