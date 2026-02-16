/**
 * Chart.js annotation builder from annotations.json.
 */

export function buildChartAnnotations(annotationData, dateRange) {
  // Handle both array format and {annotations: [...]} wrapper
  const annotations = Array.isArray(annotationData)
    ? annotationData
    : annotationData?.annotations;

  if (!annotations || !Array.isArray(annotations)) return {};

  const result = {};
  annotations.forEach((ann, i) => {
    if (ann.type === "point") {
      const d = new Date(ann.date);
      if (dateRange && (d < dateRange.min || d > dateRange.max)) return;
      result[`ann_${i}`] = {
        type: "line",
        xMin: ann.date,
        xMax: ann.date,
        borderColor: ann.color || "rgba(255,255,255,0.3)",
        borderWidth: 1,
        borderDash: [4, 4],
        label: {
          display: true,
          content: ann.label,
          position: "start",
          backgroundColor: "rgba(0,0,0,0.7)",
          color: "#fff",
          font: { size: 10 },
        },
      };
    } else if (ann.type === "range") {
      result[`ann_${i}`] = {
        type: "box",
        xMin: ann.startDate || ann.start,
        xMax: ann.endDate || ann.end,
        backgroundColor: ann.color || "rgba(79,143,247,0.08)",
        borderWidth: 0,
        label: {
          display: true,
          content: ann.label,
          position: { x: "center", y: "start" },
          color: "rgba(255,255,255,0.5)",
          font: { size: 9 },
        },
      };
    }
  });
  return result;
}
