import { useMemo } from "react";
import { Scatter } from "react-chartjs-2";
import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  Tooltip,
  Legend,
} from "chart.js";
import { formatCompact, formatPercent } from "../../lib/format";

ChartJS.register(LinearScale, PointElement, Tooltip, Legend);

export default function ScatterChart({ datasets, xLabel, yLabel, height = 300, isPercentX = false, isPercentY = false }) {
  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          title: { display: true, text: xLabel, color: "#8b8fa3" },
          grid: { color: "rgba(42, 46, 62, 0.4)" },
          ticks: {
            color: "#8b8fa3",
            callback: (v) => (isPercentX ? formatPercent(v) : formatCompact(v)),
          },
        },
        y: {
          title: { display: true, text: yLabel, color: "#8b8fa3" },
          grid: { color: "rgba(42, 46, 62, 0.4)" },
          ticks: {
            color: "#8b8fa3",
            callback: (v) => (isPercentY ? formatPercent(v) : formatCompact(v)),
          },
        },
      },
      plugins: {
        legend: { display: true, labels: { color: "#e4e6eb", usePointStyle: true } },
        tooltip: {
          backgroundColor: "#1a1d27",
          borderColor: "#2a2e3e",
          borderWidth: 1,
          titleColor: "#e4e6eb",
          bodyColor: "#e4e6eb",
        },
      },
    }),
    [xLabel, yLabel, isPercentX, isPercentY]
  );

  return (
    <div style={{ height }}>
      <Scatter data={{ datasets }} options={options} />
    </div>
  );
}
