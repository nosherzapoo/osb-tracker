import { useMemo } from "react";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  TimeScale,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import "chartjs-adapter-date-fns";
import annotationPlugin from "chartjs-plugin-annotation";
import { getOperatorColor, getSeriesColor } from "../../lib/colors";
import { formatCompact, formatPercent } from "../../lib/format";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  TimeScale,
  Tooltip,
  Legend,
  Filler,
  annotationPlugin
);

export default function TimeSeriesChart({
  data,
  dateColumn,
  columns,
  title,
  isPercent = false,
  isSportsTab = false,
  annotations,
  height = 320,
  frequency = "monthly",
}) {
  const chartData = useMemo(() => {
    if (!data || data.length === 0) return null;

    const colorFn = (name) => getSeriesColor(name, isSportsTab);
    // Append T12:00:00 to date-only strings to avoid UTC→local timezone shift
    const labels = data.map((r) => {
      const d = r[dateColumn];
      return d && d.length === 10 ? d + "T12:00:00" : d;
    }).reverse();
    const datasets = columns.map((col) => ({
      label: col,
      data: data.map((r) => parseFloat(r[col]) || null).reverse(),
      borderColor: colorFn(col),
      backgroundColor: colorFn(col) + "20",
      borderWidth: col === "Total" ? 2.5 : 1.5,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.3,
      fill: col === "Total",
    }));

    return { labels, datasets };
  }, [data, dateColumn, columns, isSportsTab]);

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          type: "time",
          time: frequency === "weekly"
            ? { displayFormats: { week: "MMM d", month: "MMM yyyy" } }
            : { unit: "month", displayFormats: { month: "MMM yyyy" } },
          grid: { color: "rgba(42, 46, 62, 0.4)" },
          ticks: { color: "#8b8fa3", maxTicksLimit: 12 },
        },
        y: {
          grid: { color: "rgba(42, 46, 62, 0.4)" },
          ticks: {
            color: "#8b8fa3",
            callback: (v) => (isPercent ? formatPercent(v) : formatCompact(v)),
          },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1a1d27",
          borderColor: "#2a2e3e",
          borderWidth: 1,
          titleColor: "#e4e6eb",
          bodyColor: "#e4e6eb",
          callbacks: {
            title: (items) => {
              if (!items.length) return "";
              const d = new Date(items[0].parsed.x);
              if (frequency === "weekly") {
                return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
              }
              return d.toLocaleDateString("en-US", { month: "long", year: "numeric", timeZone: "UTC" });
            },
            label: (ctx) => {
              const val = ctx.parsed.y;
              return `${ctx.dataset.label}: ${isPercent ? formatPercent(val) : formatCompact(val)}`;
            },
          },
        },
        annotation: annotations ? { annotations } : undefined,
      },
    }),
    [isPercent, annotations, frequency]
  );

  if (!chartData) return <div style={{ height, display: "grid", placeItems: "center", color: "var(--text-muted)" }}>No chart data</div>;

  return (
    <div style={{ height }}>
      <Line data={chartData} options={options} />
    </div>
  );
}
