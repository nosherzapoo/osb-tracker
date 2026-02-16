import { useMemo } from "react";
import { useData } from "../context/DataContext";
import KPICard from "../components/common/KPICard";
import BarChart from "../components/common/BarChart";
import USMapSelector from "../components/common/USMapSelector";
import DataTable from "../components/common/DataTable";
import FreshnessIndicator from "../components/common/FreshnessIndicator";
import { KPISkeleton, ChartSkeleton } from "../components/common/Skeleton";
import { STATE_COLORS } from "../lib/colors";
import { formatCompact, formatPercent, formatCurrency } from "../lib/format";
import styles from "./NationalOverview.module.css";

export default function NationalOverview() {
  const { manifest, loading } = useData();

  const states = manifest?.states || [];
  const stateMap = useMemo(() => {
    const m = {};
    states.forEach((s) => { m[s.code] = s; });
    return m;
  }, [states]);

  // Aggregate KPIs from manifest latestData
  const kpis = useMemo(() => {
    let totalHandle = 0, totalGgr = 0, totalTax = 0;
    let stateCount = 0;

    states.forEach((s) => {
      const ld = s.latestData;
      if (ld?.handle) totalHandle += ld.handle;
      if (ld?.ggr) totalGgr += ld.ggr;
      if (ld?.taxRevenue) totalTax += ld.taxRevenue;
      stateCount++;
    });

    const avgHold = totalHandle > 0 ? totalGgr / totalHandle : null;
    return { totalHandle, totalGgr, totalTax, avgHold, stateCount };
  }, [states]);

  // Bar chart: latest handle by state
  const barData = useMemo(() => {
    const labels = states.map((s) => s.abbreviation);
    const handles = states.map((s) => s.latestData?.handle || 0);
    const colors = states.map((s) => STATE_COLORS[s.code] || "#4f8ff7");
    return {
      labels,
      datasets: [
        {
          label: "Latest Period Handle",
          data: handles,
          backgroundColor: colors,
          borderRadius: 4,
        },
      ],
    };
  }, [states]);

  // Table data
  const tableData = useMemo(
    () =>
      states.map((s) => ({
        State: s.name,
        Handle: s.latestData?.handle,
        GGR: s.latestData?.ggr,
        "Hold %": s.latestData?.holdPct,
        "Tax Rate": s.taxRate,
        "Tax Revenue": s.latestData?.taxRevenue,
        Frequency: s.frequency,
        Periods: s.periodCount,
      })),
    [states]
  );

  if (loading) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>National Overview</h1>
        <KPISkeleton />
        <ChartSkeleton />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>National Overview</h1>
        <div className={styles.badges}>
          {states.map((s) => (
            <FreshnessIndicator key={s.code} latestDate={s.latestDate} frequency={s.frequency} />
          ))}
        </div>
      </div>

      <div className={styles.kpiGrid}>
        <KPICard label="Total Handle (Latest)" value={formatCompact(kpis.totalHandle)} color="var(--accent)" />
        <KPICard label="Total GGR (Latest)" value={formatCompact(kpis.totalGgr)} color="var(--green)" />
        <KPICard label="Avg Hold %" value={formatPercent(kpis.avgHold)} color="var(--yellow)" />
        <KPICard label="Total Tax Revenue" value={formatCompact(kpis.totalTax)} color="var(--purple)" />
      </div>

      <div className={styles.grid2}>
        <div className={styles.card}>
          <h3 className={styles.cardTitle}>State Comparison — Latest Handle</h3>
          <BarChart labels={barData.labels} datasets={barData.datasets} height={280} />
        </div>
        <div className={styles.card}>
          <h3 className={styles.cardTitle}>Tracked States</h3>
          <USMapSelector activeStates={states.map((s) => s.code)} stateData={stateMap} />
        </div>
      </div>

      <div className={styles.card}>
        <h3 className={styles.cardTitle}>State Summary Table</h3>
        <DataTable
          data={tableData}
          formatCell={(val, col) => {
            if (col === "Handle" || col === "GGR" || col === "Tax Revenue") return formatCompact(val);
            if (col === "Hold %" || col === "Tax Rate") return formatPercent(val);
            return val;
          }}
        />
      </div>
    </div>
  );
}
