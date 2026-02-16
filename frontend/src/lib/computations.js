/**
 * Computation utilities for KPIs and aggregations.
 */

export function computeLatestKPIs(stateData, metric = "handle") {
  if (!stateData || stateData.length === 0) return null;
  const latest = stateData[0]; // Data sorted descending by date
  const total = parseFloat(latest.Total);
  return isNaN(total) ? null : total;
}

export function computeAllTimeTotal(stateData, column = "Total") {
  if (!stateData) return 0;
  return stateData.reduce((sum, row) => {
    const val = parseFloat(row[column]);
    return sum + (isNaN(val) ? 0 : val);
  }, 0);
}

export function computeAvgHold(handleData, ggrData) {
  const totalHandle = computeAllTimeTotal(handleData);
  const totalGgr = computeAllTimeTotal(ggrData);
  if (totalHandle === 0) return null;
  return totalGgr / totalHandle;
}

export function getOperators(data) {
  if (!data || data.length === 0) return [];
  return Object.keys(data[0]).filter((k) => k !== "Total" && !k.includes("Month") && !k.includes("Week"));
}

export function aggregateMonthly(weeklyData, dateCol) {
  const months = {};
  for (const row of weeklyData) {
    const d = new Date(row[dateCol]);
    const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
    if (!months[key]) months[key] = { date: key + "-01", total: 0, count: 0 };
    const val = parseFloat(row.Total);
    if (!isNaN(val)) {
      months[key].total += val;
      months[key].count++;
    }
  }
  return Object.values(months).sort((a, b) => b.date.localeCompare(a.date));
}
