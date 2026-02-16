import jsPDF from "jspdf";
import { formatCompact, formatPercent } from "../../lib/format";
import { showToast } from "../common/Toast";

export async function generatePDF(manifest, stateCode, stateData) {
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const state = manifest?.states?.find((s) => s.code === stateCode);
  if (!state) {
    showToast("No state data for PDF", "error");
    return;
  }

  const W = doc.internal.pageSize.getWidth();
  const margin = 15;
  let y = 20;

  // Title
  doc.setFontSize(18);
  doc.setFont("helvetica", "bold");
  doc.text(`${state.name} Sports Betting Report`, margin, y);
  y += 8;

  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(120);
  doc.text(`Generated ${new Date().toLocaleDateString()} | Source: ${state.sourceUrl}`, margin, y);
  y += 12;

  doc.setTextColor(0);

  // KPI section
  doc.setFontSize(12);
  doc.setFont("helvetica", "bold");
  doc.text("Key Metrics (Latest Period)", margin, y);
  y += 7;

  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");

  const ld = state.latestData || {};
  const kpis = [
    ["Handle", formatCompact(ld.handle)],
    ["GGR", formatCompact(ld.ggr)],
    ["Hold %", formatPercent(ld.holdPct)],
    ["Tax Revenue", formatCompact(ld.taxRevenue)],
    ["Tax Rate", `${formatPercent(state.taxRate)} ${state.taxRateNote ? `(${state.taxRateNote})` : ""}`],
    ["Frequency", state.frequency],
    ["Data Periods", String(state.periodCount)],
    ["Launch Date", state.launchDate],
  ];

  for (const [label, value] of kpis) {
    doc.setFont("helvetica", "bold");
    doc.text(`${label}:`, margin, y);
    doc.setFont("helvetica", "normal");
    doc.text(value, margin + 40, y);
    y += 5;
  }
  y += 5;

  // Data table (handle)
  const handleData = stateData?.handle;
  if (handleData && handleData.length > 0) {
    doc.setFontSize(12);
    doc.setFont("helvetica", "bold");
    doc.text("Handle Data (Recent)", margin, y);
    y += 7;

    doc.setFontSize(8);
    const dateCol = state.dateColumn || "Month";
    const cols = Object.keys(handleData[0]);
    const colW = (W - 2 * margin) / Math.min(cols.length, 5);
    const displayCols = cols.slice(0, 5);

    // Header
    doc.setFont("helvetica", "bold");
    displayCols.forEach((col, i) => {
      doc.text(col.substring(0, 12), margin + i * colW, y);
    });
    y += 1;
    doc.setDrawColor(200);
    doc.line(margin, y, W - margin, y);
    y += 4;

    // Rows (first 20)
    doc.setFont("helvetica", "normal");
    const rowCount = Math.min(handleData.length, 20);
    for (let r = 0; r < rowCount; r++) {
      if (y > 270) {
        doc.addPage();
        y = 20;
      }
      const row = handleData[r];
      displayCols.forEach((col, i) => {
        let val = row[col];
        if (col !== dateCol) {
          const num = parseFloat(val);
          val = isNaN(num) ? (val || "") : formatCompact(num);
        }
        doc.text(String(val).substring(0, 14), margin + i * colW, y);
      });
      y += 4;
    }
  }

  // Footer
  y = doc.internal.pageSize.getHeight() - 10;
  doc.setFontSize(7);
  doc.setTextColor(150);
  doc.text("US Sports Betting Intelligence Platform", margin, y);
  doc.text(new Date().toISOString(), W - margin - 40, y);

  doc.save(`${stateCode}_sports_betting_report.pdf`);
  showToast("PDF exported", "success");
}
