/**
 * Color palettes for operators and states.
 */

export const OPERATOR_COLORS = {
  FanDuel: "#1a6dff",
  DraftKings: "#4bc44b",
  BetMGM: "#d4a017",
  Caesars: "#1a8f5c",
  "ESPN Bet": "#ff4444",
  "Bally Bet": "#ff6600",
  Fanatics: "#8b5cf6",
  "Resorts World Bet": "#e91e63",
  "Rush Street Interactive": "#00bcd4",
  Bet365: "#006b3f",
  "Desert Diamond": "#c2185b",
  "Seminole Hard Rock": "#ff8f00",
  "Golden Nugget": "#ffd600",
  SuperBook: "#5c6bc0",
  Betway: "#00a5cf",
  WynnBet: "#b71c1c",
  TwinSpires: "#2e7d32",
  BetFred: "#1565c0",
  "Sahara Bets": "#d4a017",
  Unibet: "#388e3c",
  "Fubo.TV": "#f4511e",
  Sporttrade: "#7e57c2",
  Plannatech: "#546e7a",
  "CT Lottery": "#0d47a1",
  "Circa Sports": "#b45309",
  "Dubuque Racing": "#78716c",
  "Elite Hospitality": "#a3a3a3",
  "SCE Partners": "#737373",
  BlueBet: "#2563eb",
  Prime: "#8d6e63",
  Oddfellahs: "#e65100",
  "Oxford Sportsbook": "#6d4c41",
  "theScore Bet": "#e53935",
  "Encore Boston Harbor": "#b8860b",
  "MGM Springfield": "#c0ca33",
  "Plainridge Park Casino": "#795548",
  "Retail (Detroit)": "#ef6c00",
  Parx: "#0288d1",
  Others: "#9ca3af",
  Total: "#ffffff",
};

export const STATE_COLORS = {
  ny: "#4f8ff7",
  nj: "#0277bd",
  pa: "#a855f7",
  il: "#ff6b35",
  oh: "#22c55e",
  az: "#e74c3c",
  co: "#f59e0b",
  ct: "#06b6d4",
  ia: "#dc2626",
  ky: "#3b82f6",
  la: "#9333ea",
  me: "#10b981",
  ma: "#7c3aed",
  mi: "#0d5cab",
  ms: "#854d0e",
  ri: "#d32f2f",
  sd: "#4a752c",
  tn: "#ff8c00",
  mt: "#4a6741",
  wy: "#a0522d",
  de: "#004b87",
};

export const STATE_COLORS_LIGHT = {
  ny: "rgba(79, 143, 247, 0.15)",
  nj: "rgba(2, 119, 189, 0.15)",
  pa: "rgba(168, 85, 247, 0.15)",
  il: "rgba(255, 107, 53, 0.15)",
  oh: "rgba(34, 197, 94, 0.15)",
  az: "rgba(231, 76, 60, 0.15)",
  co: "rgba(245, 158, 11, 0.15)",
  ct: "rgba(6, 182, 212, 0.15)",
  ia: "rgba(220, 38, 38, 0.15)",
  ky: "rgba(59, 130, 246, 0.15)",
  la: "rgba(147, 51, 234, 0.15)",
  me: "rgba(16, 185, 129, 0.15)",
  ma: "rgba(124, 58, 237, 0.15)",
  mi: "rgba(13, 92, 171, 0.15)",
  ms: "rgba(133, 77, 14, 0.15)",
  ri: "rgba(211, 47, 47, 0.15)",
  sd: "rgba(74, 117, 44, 0.15)",
  tn: "rgba(255, 140, 0, 0.15)",
  mt: "rgba(74, 103, 65, 0.15)",
  wy: "rgba(160, 82, 45, 0.15)",
  de: "rgba(0, 75, 135, 0.15)",
};

export const SPORT_COLORS = {
  NFL: "#013369",
  NBA: "#c9082a",
  MLB: "#002d72",
  NHL: "#000000",
  NCAAF: "#1a5276",
  NCAAB: "#7d3c98",
  Soccer: "#27ae60",
  Tennis: "#f39c12",
  MMA: "#e74c3c",
  Boxing: "#8b0000",
  Golf: "#2ecc71",
  "Table Tennis": "#3498db",
  Motorsports: "#e67e22",
  Volleyball: "#9b59b6",
  Cricket: "#16a085",
  Darts: "#d35400",
  Cycling: "#2980b9",
  Rugby: "#1abc9c",
  Olympics: "#f1c40f",
  Lacrosse: "#6c3483",
  Football: "#013369",
  Basketball: "#c9082a",
  "Ice Hockey": "#000000",
  Baseball: "#002d72",
  Specials: "#7f8c8d",
  NASCAR: "#e67e22",
  Other: "#95a5a6",
};

const PALETTE = [
  "#4f8ff7", "#22c55e", "#eab308", "#ef4444", "#a855f7",
  "#f97316", "#06b6d4", "#ec4899", "#84cc16", "#6366f1",
];

export function getOperatorColor(name) {
  return OPERATOR_COLORS[name] || PALETTE[Math.abs(hashCode(name)) % PALETTE.length];
}

export function getSportColor(name) {
  return SPORT_COLORS[name] || PALETTE[Math.abs(hashCode(name)) % PALETTE.length];
}

export function getSeriesColor(name, isSportsTab) {
  if (isSportsTab) return getSportColor(name);
  return getOperatorColor(name);
}

function hashCode(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
  }
  return hash;
}
