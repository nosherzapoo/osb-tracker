import { useState, useMemo } from "react";
import { useData } from "../context/DataContext";
import { useStateData } from "../hooks/useStateData";
import DataTable from "../components/common/DataTable";
import { TABS } from "../lib/constants";
import { formatCompact, formatPercent, formatDate } from "../lib/format";
import { showToast } from "../components/common/Toast";
import styles from "./DataLab.module.css";

export default function DataLab() {
  const { manifest } = useData();
  const states = manifest?.states || [];
  const [selectedState, setSelectedState] = useState("ny");
  const [selectedMetric, setSelectedMetric] = useState("handle");

  const { data, loading } = useStateData(selectedState);

  const meta = data?.meta;
  const tableData = data?.[selectedMetric] || [];
  const dateCol = meta?.dateColumn || "Month";
  const isPercent = selectedMetric === "hold_pct" || selectedMetric === "yoy_handle" || selectedMetric === "yoy_ggr";

  function handleExportCSV() {
    if (!tableData || tableData.length === 0) return;
    const cols = Object.keys(tableData[0]);
    const rows = [cols.join(",")];
    tableData.forEach((row) => {
      rows.push(cols.map((c) => row[c] ?? "").join(","));
    });
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selectedState}_${selectedMetric}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("CSV exported", "success");
  }

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>Data Lab</h1>
      <p className={styles.subtitle}>Select a state and metric to explore and export data.</p>

      <div className={styles.controls}>
        <div className={styles.control}>
          <label className={styles.label}>State</label>
          <select value={selectedState} onChange={(e) => setSelectedState(e.target.value)}>
            {states.map((s) => (
              <option key={s.code} value={s.code}>{s.name}</option>
            ))}
          </select>
        </div>

        <div className={styles.control}>
          <label className={styles.label}>Metric</label>
          <select value={selectedMetric} onChange={(e) => setSelectedMetric(e.target.value)}>
            {TABS.map((t) => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>
        </div>

        <button className={styles.exportBtn} onClick={handleExportCSV}>
          Export CSV
        </button>
      </div>

      {loading ? (
        <div className={styles.loading}>Loading data...</div>
      ) : (
        <div className={styles.card}>
          <h3 className={styles.cardTitle}>
            {states.find((s) => s.code === selectedState)?.name} — {TABS.find((t) => t.id === selectedMetric)?.label}
          </h3>
          <DataTable
            data={tableData}
            formatCell={(val, col) => {
              if (col === dateCol) return formatDate(val, meta?.frequency);
              if (isPercent) return formatPercent(parseFloat(val));
              return formatCompact(parseFloat(val));
            }}
            maxRows={100}
          />
        </div>
      )}
    </div>
  );
}
