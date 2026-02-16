import { useState, useMemo, useCallback, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useData } from "../context/DataContext";
import { useStateData } from "../hooks/useStateData";
import { useURLState } from "../hooks/useURLState";
import KPICard from "../components/common/KPICard";
import TimeSeriesChart from "../components/common/TimeSeriesChart";
import DataTable from "../components/common/DataTable";
import OperatorToggles from "../components/common/OperatorToggles";
import DateRangeFilter from "../components/common/DateRangeFilter";
import DoughnutChart from "../components/common/DoughnutChart";
import FreshnessIndicator from "../components/common/FreshnessIndicator";
import { KPISkeleton, ChartSkeleton } from "../components/common/Skeleton";
import { TABS } from "../lib/constants";
import { formatCompact, formatPercent, formatCurrency, formatDate } from "../lib/format";
import { getSeriesColor } from "../lib/colors";
import { buildChartAnnotations } from "../lib/annotations";
import { generatePDF } from "../components/pdf/PDFReport";
import styles from "./StateDeepDive.module.css";

export default function StateDeepDive() {
  const { stateCode } = useParams();
  const navigate = useNavigate();
  const { manifest } = useData();

  const code = stateCode || "ny";
  const { data, loading } = useStateData(code);
  const [activeTab, setActiveTab] = useURLState("tab", "handle");
  const [rangeMonths, setRangeMonths] = useState(null);

  const states = manifest?.states || [];
  const meta = data?.meta;

  // Determine which operators are available
  const operators = useMemo(() => {
    if (!data || !data[activeTab] || data[activeTab].length === 0) return [];
    const row = data[activeTab][0];
    return Object.keys(row).filter(
      (k) => k !== "Total" && !k.includes("Month") && !k.includes("Week")
    );
  }, [data, activeTab]);

  const [activeOps, setActiveOps] = useState([]);

  // Reset active operators when state changes
  useEffect(() => {
    setActiveOps(operators);
  }, [operators.join(",")]);

  const handleToggle = useCallback((op) => {
    setActiveOps((prev) =>
      prev.includes(op) ? prev.filter((o) => o !== op) : [...prev, op]
    );
  }, []);

  const handleToggleAll = useCallback(() => {
    setActiveOps((prev) => (prev.length === operators.length ? [] : [...operators]));
  }, [operators]);

  // Filter data by date range
  const filteredData = useMemo(() => {
    if (!data || !data[activeTab]) return [];
    let rows = data[activeTab];
    if (rangeMonths) {
      const cutoff = new Date();
      cutoff.setMonth(cutoff.getMonth() - rangeMonths);
      const dateCol = meta?.dateColumn || "Month";
      rows = rows.filter((r) => new Date(r[dateCol] + "T12:00:00") >= cutoff);
    }
    return rows;
  }, [data, activeTab, rangeMonths, meta]);

  // Chart columns
  const chartColumns = useMemo(() => {
    if (activeOps.length === 0 || operators.length <= 1) return ["Total"];
    return [...activeOps, "Total"];
  }, [activeOps, operators]);

  // KPIs
  const kpis = useMemo(() => {
    if (!meta?.latestData) return {};
    return meta.latestData;
  }, [meta]);

  const isSportsTab = activeTab === "sports_handle";
  const isPercent = activeTab === "hold_pct" || activeTab === "yoy_handle" || activeTab === "yoy_ggr";

  // Market share (doughnut) for latest period — shows operator or sport share
  const marketShare = useMemo(() => {
    const sourceKey = isSportsTab ? "sports_handle" : "handle";
    if (!data || !data[sourceKey] || data[sourceKey].length === 0 || operators.length <= 1) return null;
    const latest = data[sourceKey][0];
    const labels = [];
    const values = [];
    const colors = [];
    operators.forEach((op) => {
      const val = parseFloat(latest[op]);
      if (val > 0) {
        labels.push(op);
        values.push(val);
        colors.push(getSeriesColor(op, isSportsTab));
      }
    });
    return { labels, values, colors };
  }, [data, operators, isSportsTab]);

  // Annotations
  const annotations = useMemo(() => {
    if (!data?.annotations) return undefined;
    return buildChartAnnotations(data.annotations);
  }, [data]);

  // Filter tabs: only show "By Sport" tab if state has sports data
  const visibleTabs = useMemo(() => {
    const hasSports = meta?.hasSportsData || (data?.sports_handle && data.sports_handle.length > 0);
    return TABS.filter((tab) => tab.id !== "sports_handle" || hasSports);
  }, [meta, data]);
  const dateCol = meta?.dateColumn || "Month";

  // PDF export via keyboard shortcut 'e'
  useEffect(() => {
    function handleExport() {
      if (manifest && data) generatePDF(manifest, code, data);
    }
    window.addEventListener("osb:export", handleExport);
    return () => window.removeEventListener("osb:export", handleExport);
  }, [manifest, data, code]);

  // j/k keyboard shortcuts for operator toggling
  useEffect(() => {
    function handler(e) {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
      if (operators.length <= 1) return;
      if (e.key === "j" || e.key === "k") {
        e.preventDefault();
        setActiveOps((prev) => {
          if (prev.length === 0) return [operators[0]];
          // Find the "current" single operator or cycle
          const currentIdx = operators.indexOf(prev[prev.length - 1]);
          const dir = e.key === "j" ? 1 : -1;
          const nextIdx = (currentIdx + dir + operators.length) % operators.length;
          return [operators[nextIdx]];
        });
      }
      // 'a' to toggle all
      if (e.key === "a") {
        e.preventDefault();
        setActiveOps((prev) => (prev.length === operators.length ? [] : [...operators]));
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [operators]);

  if (loading) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>Loading...</h1>
        <KPISkeleton />
        <ChartSkeleton />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      {/* Header with state selector */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <select
            className={styles.stateSelect}
            value={code}
            onChange={(e) => navigate(`/state/${e.target.value}`)}
          >
            {states.map((s) => (
              <option key={s.code} value={s.code}>{s.name}</option>
            ))}
          </select>
          {meta && <FreshnessIndicator latestDate={meta.latestDate} frequency={meta.frequency} />}
        </div>
        <div className={styles.headerRight}>
          <DateRangeFilter value={rangeMonths} onChange={setRangeMonths} />
          <button
            className={styles.exportBtn}
            onClick={() => manifest && data && generatePDF(manifest, code, data)}
            title="Export PDF (e)"
          >
            Export PDF
          </button>
        </div>
      </div>

      {/* Tax info bar */}
      {meta && (
        <div className={styles.taxBar}>
          Tax Rate: {formatPercent(meta.taxRate)} {meta.taxRateNote && `(${meta.taxRateNote})`}
          {" | "}Frequency: {meta.frequency} | Since: {meta.launchDate}
          {meta.ggrDefinition && <>{" | "}GGR: {meta.ggrDefinition}</>}
        </div>
      )}

      {/* KPIs */}
      <div className={styles.kpiGrid}>
        <KPICard label="Latest Handle" value={formatCompact(kpis.handle)} color="var(--accent)" />
        <KPICard label="Latest GGR" value={formatCompact(kpis.ggr)} color="var(--green)" tooltip={meta?.ggrDefinition} />
        <KPICard label="Hold %" value={formatPercent(kpis.holdPct)} color="var(--yellow)" />
        <KPICard label="Tax Revenue" value={formatCompact(kpis.taxRevenue)} color="var(--purple)" />
      </div>

      {/* Tab bar */}
      <div className={styles.tabs}>
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            className={`${styles.tab} ${activeTab === tab.id ? styles.activeTab : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Operator toggles (only if multi-operator) */}
      {operators.length > 1 && (
        <OperatorToggles
          operators={operators}
          active={activeOps}
          onToggle={handleToggle}
          onToggleAll={handleToggleAll}
          isSportsTab={isSportsTab}
        />
      )}

      {/* Chart + Market Share side by side */}
      <div className={styles.chartArea}>
        <div className={styles.mainChart}>
          <TimeSeriesChart
            data={filteredData}
            dateColumn={dateCol}
            columns={chartColumns}
            title={visibleTabs.find((t) => t.id === activeTab)?.label}
            isPercent={isPercent}
            isSportsTab={isSportsTab}
            annotations={annotations}
            height={360}
            frequency={meta?.frequency}
          />
        </div>
        {marketShare && (activeTab === "handle" || isSportsTab) && (
          <div className={styles.sideChart}>
            <h3 className={styles.sideTitle}>Market Share (Latest)</h3>
            <DoughnutChart
              labels={marketShare.labels}
              values={marketShare.values}
              colors={marketShare.colors}
              height={280}
            />
          </div>
        )}
      </div>

      {/* Data table */}
      <div className={styles.card}>
        <h3 className={styles.cardTitle}>Data Table</h3>
        <DataTable
          data={filteredData}
          formatCell={(val, col) => {
            if (col === dateCol) return formatDate(val, meta?.frequency);
            if (isPercent) return formatPercent(parseFloat(val));
            return formatCompact(parseFloat(val));
          }}
          maxRows={52}
        />
      </div>
    </div>
  );
}
