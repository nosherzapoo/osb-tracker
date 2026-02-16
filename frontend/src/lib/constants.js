/**
 * Application constants: tab config, canonical operator names.
 */

export const TABS = [
  { id: "handle", label: "Handle", key: "handle" },
  { id: "ggr", label: "GGR", key: "ggr" },
  { id: "hold_pct", label: "Hold %", key: "hold_pct" },
  { id: "yoy_handle", label: "YoY Handle", key: "yoy_handle" },
  { id: "yoy_ggr", label: "YoY GGR", key: "yoy_ggr" },
  { id: "tax_revenue", label: "Tax Revenue", key: "tax_revenue" },
  { id: "sports_handle", label: "By Sport", key: "sports_handle" },
];

export const CANONICAL_OPERATORS = {
  FanDuel: "FanDuel",
  DraftKings: "DraftKings",
  BetMGM: "BetMGM",
  Caesars: "Caesars",
  "ESPN Bet": "ESPN Bet",
  "Bally Bet": "Bally Bet",
  Fanatics: "Fanatics",
  "Resorts World Bet": "Resorts World Bet",
  "Rush Street Interactive": "Rush Street Interactive",
  PointsBet: "Fanatics", // Rebranded
  "WynnBET": "ESPN Bet", // Rebranded
};

export const PAGES = [
  { path: "/", label: "National Overview", shortcut: "1", icon: "globe" },
  { path: "/state", label: "State Deep Dive", shortcut: "2", icon: "chart" },
  { path: "/operator", label: "Operator Tracker", shortcut: "3", icon: "users" },
  { path: "/data-lab", label: "Data Lab", shortcut: "4", icon: "table" },
  { path: "/about", label: "About", shortcut: "5", icon: "info" },
];

export const DATA_BASE_URL = "/data";
