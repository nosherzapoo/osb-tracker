/**
 * Formatting utilities for currency, percentages, and compact numbers.
 */

export function formatCurrency(value) {
  if (value == null || isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatCompact(value) {
  if (value == null || isNaN(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

export function formatPercent(value, decimals = 1) {
  if (value == null || isNaN(value)) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

export function formatDate(dateStr, frequency = "weekly") {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  if (frequency === "weekly") {
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    });
  }
  return d.toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function formatNumber(value) {
  if (value == null || isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US").format(Math.round(value));
}
