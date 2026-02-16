import { useMemo } from "react";
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from "chart.js";
import { formatCompact } from "../../lib/format";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

export default function BarChart({ labels, datasets, height = 300, horizontal = false }) {
  const data = useMemo(() => ({ labels, datasets }), [labels, datasets]);

  const options = useMemo(
    () => ({
      indexAxis: horizontal ? "y" : "x",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { color: "rgba(42, 46, 62, 0.4)" },
          ticks: { color: "#8b8fa3" },
        },
        y: {
          grid: { color: "rgba(42, 46, 62, 0.4)" },
          ticks: {
            color: "#8b8fa3",
            callback: (v) => formatCompact(v),
          },
        },
      },
      plugins: {
        legend: { display: datasets.length > 1, labels: { color: "#e4e6eb" } },
        tooltip: {
          backgroundColor: "#1a1d27",
          borderColor: "#2a2e3e",
          borderWidth: 1,
          titleColor: "#e4e6eb",
          bodyColor: "#e4e6eb",
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${formatCompact(ctx.parsed[horizontal ? "x" : "y"])}`,
          },
        },
      },
    }),
    [horizontal, datasets.length]
  );

  return (
    <div style={{ height }}>
      <Bar data={data} options={options} />
    </div>
  );
}
