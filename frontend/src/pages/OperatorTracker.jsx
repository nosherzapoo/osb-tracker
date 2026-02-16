import { useState, useMemo, useEffect, useCallback } from "react";
import { useData } from "../context/DataContext";
import { fetchCSV } from "../lib/csv";
import KPICard from "../components/common/KPICard";
import BarChart from "../components/common/BarChart";
import TimeSeriesChart from "../components/common/TimeSeriesChart";
import DoughnutChart from "../components/common/DoughnutChart";
import DataTable from "../components/common/DataTable";
import OperatorToggles from "../components/common/OperatorToggles";
import DateRangeFilter from "../components/common/DateRangeFilter";
import { KPISkeleton, ChartSkeleton } from "../components/common/Skeleton";
import { getOperatorColor } from "../lib/colors";
import { formatCompact, formatPercent, formatDate } from "../lib/format";
import styles from "./OperatorTracker.module.css";

const MAJOR_OPS = ["FanDuel", "DraftKings", "BetMGM", "Caesars", "ESPN Bet", "Fanatics"];
const ALL_OPS = [...MAJOR_OPS, "Others"];

const METRIC_TABS = [
  { id: "handle", label: "Handle" },
  { id: "ggr", label: "GGR" },
  { id: "hold_pct", label: "Hold %" },
  { id: "yoy_handle", label: "YoY Handle" },
  { id: "yoy_ggr", label: "YoY GGR" },
];

/**
 * Aggregate weekly CSV rows to monthly, summing each operator column.
 */
function aggregateWeeklyToMonthly(rows, dateCol) {
  const months = {};
  for (const row of rows) {
    const d = new Date(row[dateCol]);
    const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-01`;
    if (!months[key]) months[key] = { [dateCol]: key };
    for (const [col, val] of Object.entries(row)) {
      if (col === dateCol) continue;
      const num = parseFloat(val);
      if (!isNaN(num)) {
        months[key][col] = (months[key][col] || 0) + num;
      }
    }
  }
  return Object.values(months);
}

/**
 * Build cross-state monthly aggregation for a given metric (handle or ggr).
 * Buckets non-major operators into "Others".
 */
function aggregateAcrossStates(allCSVs, majorOps) {
  const monthly = {}; // { "2025-12-01": { FanDuel: X, DraftKings: Y, ..., Others: Z } }

  for (const rows of allCSVs) {
    for (const row of rows) {
      const date = row.Month || row["Week Ending"];
      if (!date) continue;
      // Normalize to first-of-month
      const d = new Date(date);
      const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-01`;

      if (!monthly[key]) monthly[key] = {};

      for (const [col, val] of Object.entries(row)) {
        if (col === "Month" || col === "Week Ending" || col === "Total") continue;
        const num = parseFloat(val);
        if (isNaN(num)) continue;

        const bucket = majorOps.includes(col) ? col : "Others";
        monthly[key][bucket] = (monthly[key][bucket] || 0) + num;
      }
    }
  }

  // Convert to sorted array
  const allOps = [...majorOps, "Others"];
  return Object.entries(monthly)
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([date, ops]) => {
      const row = { Month: date };
      let total = 0;
      for (const op of allOps) {
        const v = ops[op] || 0;
        row[op] = v || null;
        total += v;
      }
      row.Total = total || null;
      return row;
    });
}

/**
 * Compute hold % = ggr / handle per operator per month.
 */
function computeHoldPct(handleData, ggrData) {
  const ggrMap = {};
  for (const row of ggrData) {
    ggrMap[row.Month] = row;
  }

  return handleData.map((hRow) => {
    const gRow = ggrMap[hRow.Month] || {};
    const row = { Month: hRow.Month };
    for (const col of [...MAJOR_OPS, "Others", "Total"]) {
      const h = parseFloat(hRow[col]);
      const g = parseFloat(gRow[col]);
      if (h > 0 && !isNaN(g)) {
        row[col] = g / h;
      } else {
        row[col] = null;
      }
    }
    return row;
  });
}

/**
 * Compute year-over-year % change for each operator column.
 */
function computeYoY(data) {
  const dateMap = {};
  for (const row of data) {
    dateMap[row.Month] = row;
  }

  return data.map((row) => {
    const d = new Date(row.Month);
    const priorDate = new Date(Date.UTC(d.getUTCFullYear() - 1, d.getUTCMonth(), 1));
    const priorKey = `${priorDate.getUTCFullYear()}-${String(priorDate.getUTCMonth() + 1).padStart(2, "0")}-01`;
    const priorRow = dateMap[priorKey];

    const result = { Month: row.Month };
    for (const col of [...MAJOR_OPS, "Others", "Total"]) {
      const curr = parseFloat(row[col]);
      const prior = priorRow ? parseFloat(priorRow[col]) : NaN;
      if (!isNaN(curr) && !isNaN(prior) && prior !== 0) {
        result[col] = (curr - prior) / Math.abs(prior);
      } else {
        result[col] = null;
      }
    }
    return result;
  });
}

export default function OperatorTracker() {
  const { manifest } = useData();

  const [rawData, setRawData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("handle");
  const [selectedOp, setSelectedOp] = useState("DraftKings");
  const [activeOps, setActiveOps] = useState([...ALL_OPS]);
  const [rangeMonths, setRangeMonths] = useState(null);

  const operatorStates = useMemo(
    () => (manifest?.states || []).filter((s) => s.hasOperatorData && s.operators?.length > 1),
    [manifest]
  );

  // Load handle.csv and ggr.csv for every operator state
  useEffect(() => {
    if (!operatorStates.length) return;

    async function loadAll() {
      const allHandle = [];
      const allGgr = [];

      await Promise.all(
        operatorStates.map(async (state) => {
          try {
            const [handle, ggr] = await Promise.all([
              fetchCSV(`${state.code}/handle.csv`),
              fetchCSV(`${state.code}/ggr.csv`),
            ]);
            // Aggregate weekly → monthly for NY
            const dateCol = state.dateColumn || "Month";
            const hRows = state.frequency === "weekly" ? aggregateWeeklyToMonthly(handle, dateCol) : handle;
            const gRows = state.frequency === "weekly" ? aggregateWeeklyToMonthly(ggr, dateCol) : ggr;
            // Normalize date column to "Month"
            const normalize = (rows) =>
              rows.map((r) => {
                if (r.Month) return r;
                const copy = { ...r };
                copy.Month = copy[dateCol];
                delete copy[dateCol];
                return copy;
              });
            allHandle.push(normalize(hRows));
            allGgr.push(normalize(gRows));
          } catch (e) {
            console.warn(`Failed to load ${state.code}:`, e);
          }
        })
      );

      setRawData({ allHandle, allGgr });
      setLoading(false);
    }

    loadAll();
  }, [operatorStates]);

  // Build aggregated datasets
  const { handleData, ggrData, holdData, yoyHandle, yoyGgr } = useMemo(() => {
    if (!rawData) return { handleData: [], ggrData: [], holdData: [], yoyHandle: [], yoyGgr: [] };

    const handleData = aggregateAcrossStates(rawData.allHandle, MAJOR_OPS);
    const ggrData = aggregateAcrossStates(rawData.allGgr, MAJOR_OPS);
    const holdData = computeHoldPct(handleData, ggrData);
    const yoyHandle = computeYoY(handleData);
    const yoyGgr = computeYoY(ggrData);

    return { handleData, ggrData, holdData, yoyHandle, yoyGgr };
  }, [rawData]);

  const dataForTab = useMemo(() => {
    const map = { handle: handleData, ggr: ggrData, hold_pct: holdData, yoy_handle: yoyHandle, yoy_ggr: yoyGgr };
    return map[activeTab] || [];
  }, [activeTab, handleData, ggrData, holdData, yoyHandle, yoyGgr]);

  // Date range filter
  const filteredData = useMemo(() => {
    if (!rangeMonths) return dataForTab;
    const cutoff = new Date();
    cutoff.setMonth(cutoff.getMonth() - rangeMonths);
    return dataForTab.filter((r) => new Date(r.Month + "T12:00:00") >= cutoff);
  }, [dataForTab, rangeMonths]);

  const isPercent = activeTab === "hold_pct" || activeTab === "yoy_handle" || activeTab === "yoy_ggr";

  // Chart columns
  const chartColumns = useMemo(() => {
    if (activeOps.length === 0) return ["Total"];
    return [...activeOps, "Total"];
  }, [activeOps]);

  // KPIs for selected operator (latest month)
  const kpis = useMemo(() => {
    if (!handleData.length) return null;
    const latestH = handleData[0];
    const latestG = ggrData[0];
    const handle = parseFloat(latestH?.[selectedOp]) || 0;
    const ggr = parseFloat(latestG?.[selectedOp]) || 0;
    const totalHandle = parseFloat(latestH?.Total) || 0;
    const share = totalHandle > 0 ? handle / totalHandle : 0;
    const hold = handle > 0 ? ggr / handle : 0;
    const stateCount = operatorStates.filter((s) => s.operators?.includes(selectedOp)).length;
    return { handle, ggr, share, hold, stateCount };
  }, [handleData, ggrData, selectedOp, operatorStates]);

  // Market share doughnut for latest period
  const marketShare = useMemo(() => {
    if (!handleData.length) return null;
    const latest = handleData[0];
    const labels = [];
    const values = [];
    const colors = [];
    for (const op of ALL_OPS) {
      const val = parseFloat(latest[op]);
      if (val > 0) {
        labels.push(op);
        values.push(val);
        colors.push(getOperatorColor(op));
      }
    }
    return labels.length ? { labels, values, colors } : null;
  }, [handleData]);

  const handleToggle = useCallback((op) => {
    setActiveOps((prev) => (prev.includes(op) ? prev.filter((o) => o !== op) : [...prev, op]));
  }, []);

  const handleToggleAll = useCallback(() => {
    setActiveOps((prev) => (prev.length === ALL_OPS.length ? [] : [...ALL_OPS]));
  }, []);

  if (loading) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>Operator Tracker</h1>
        <KPISkeleton />
        <ChartSkeleton />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Operator Tracker</h1>
          <p className={styles.subtitle}>
            Cross-state monthly aggregated data across {operatorStates.length} states with operator breakdowns.
          </p>
        </div>
        <DateRangeFilter value={rangeMonths} onChange={setRangeMonths} />
      </div>

      {/* Operator selector for KPIs */}
      <div className={styles.opSelector}>
        {MAJOR_OPS.map((op) => (
          <button
            key={op}
            className={`${styles.opBtn} ${selectedOp === op ? styles.opActive : ""}`}
            style={selectedOp === op ? { borderColor: getOperatorColor(op), color: getOperatorColor(op) } : {}}
            onClick={() => setSelectedOp(op)}
          >
            {op}
          </button>
        ))}
        <button
          className={`${styles.opBtn} ${selectedOp === "Others" ? styles.opActive : ""}`}
          style={selectedOp === "Others" ? { borderColor: getOperatorColor("Others"), color: getOperatorColor("Others") } : {}}
          onClick={() => setSelectedOp("Others")}
        >
          Others
        </button>
      </div>

      {/* KPIs */}
      {kpis && (
        <div className={styles.kpiGrid}>
          <KPICard
            label={`${selectedOp} Handle`}
            value={formatCompact(kpis.handle)}
            color={getOperatorColor(selectedOp)}
          />
          <KPICard label={`${selectedOp} GGR`} value={formatCompact(kpis.ggr)} color="var(--green)" />
          <KPICard label="Market Share" value={formatPercent(kpis.share)} color="var(--yellow)" />
          <KPICard label="Hold %" value={formatPercent(kpis.hold)} color="var(--purple)" />
        </div>
      )}

      {/* Metric tabs */}
      <div className={styles.tabs}>
        {METRIC_TABS.map((tab) => (
          <button
            key={tab.id}
            className={`${styles.tab} ${activeTab === tab.id ? styles.activeTab : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Operator toggles for chart */}
      <OperatorToggles
        operators={ALL_OPS}
        active={activeOps}
        onToggle={handleToggle}
        onToggleAll={handleToggleAll}
      />

      {/* Chart + Market Share */}
      <div className={styles.chartArea}>
        <div className={styles.mainChart}>
          <TimeSeriesChart
            data={filteredData}
            dateColumn="Month"
            columns={chartColumns}
            title={METRIC_TABS.find((t) => t.id === activeTab)?.label}
            isPercent={isPercent}
            frequency="monthly"
            height={360}
          />
        </div>
        {marketShare && activeTab === "handle" && (
          <div className={styles.sideChart}>
            <h3 className={styles.cardTitle}>Market Share (Latest)</h3>
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
        <h3 className={styles.cardTitle}>
          Monthly Data — {METRIC_TABS.find((t) => t.id === activeTab)?.label}
        </h3>
        <DataTable
          data={filteredData}
          formatCell={(val, col) => {
            if (col === "Month") return formatDate(val, "monthly");
            if (isPercent) return formatPercent(parseFloat(val));
            return formatCompact(parseFloat(val));
          }}
          maxRows={60}
        />
      </div>
    </div>
  );
}
