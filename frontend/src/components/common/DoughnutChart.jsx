import { useMemo } from "react";
import { Doughnut } from "react-chartjs-2";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import { formatCompact, formatPercent } from "../../lib/format";

ChartJS.register(ArcElement, Tooltip, Legend);

export default function DoughnutChart({ labels, values, colors, height = 280 }) {
  const data = useMemo(
    () => ({
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: colors,
          borderColor: "var(--bg)",
          borderWidth: 2,
        },
      ],
    }),
    [labels, values, colors]
  );

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      cutout: "65%",
      plugins: {
        legend: {
          position: "right",
          labels: {
            color: "#e4e6eb",
            padding: 12,
            usePointStyle: true,
            pointStyleWidth: 10,
            font: { size: 11 },
          },
        },
        tooltip: {
          backgroundColor: "#1a1d27",
          borderColor: "#2a2e3e",
          borderWidth: 1,
          titleColor: "#e4e6eb",
          bodyColor: "#e4e6eb",
          callbacks: {
            label: (ctx) => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct = total > 0 ? ctx.raw / total : 0;
              return `${ctx.label}: ${formatCompact(ctx.raw)} (${formatPercent(pct)})`;
            },
          },
        },
      },
    }),
    []
  );

  return (
    <div style={{ height }}>
      <Doughnut data={data} options={options} />
    </div>
  );
}
