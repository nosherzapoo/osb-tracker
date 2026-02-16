import { useNavigate } from "react-router-dom";
import { STATE_COLORS } from "../../lib/colors";
import styles from "./USMapSelector.module.css";

// Simplified US state SVG paths for the 5 tracked states + outlines for context
// Positions are approximate centroids for label placement
const STATES = {
  ny: { name: "New York", cx: 810, cy: 185, path: "M780,140 L830,140 840,160 830,180 840,200 820,220 790,210 770,190 770,160 Z" },
  nj: { name: "New Jersey", cx: 830, cy: 230, path: "M820,215 L840,210 845,230 840,250 825,255 815,240 Z" },
  pa: { name: "Pennsylvania", cx: 780, cy: 220, path: "M730,200 L815,195 820,215 815,240 730,245 725,220 Z" },
  il: { name: "Illinois", cx: 570, cy: 270, path: "M555,200 L585,200 590,230 595,270 585,310 570,320 555,310 545,270 550,230 Z" },
  oh: { name: "Ohio", cx: 670, cy: 240, path: "M645,200 L700,195 710,220 705,260 680,270 650,260 640,230 Z" },
  az: { name: "Arizona", cx: 280, cy: 310, path: "M240,260 L310,260 320,290 320,350 250,350 240,310 Z" },
  co: { name: "Colorado", cx: 340, cy: 260, path: "M310,235 L380,235 380,280 310,280 Z" },
  ct: { name: "Connecticut", cx: 855, cy: 195, path: "M840,185 L870,183 872,195 868,205 842,207 840,195 Z" },
  ia: { name: "Iowa", cx: 490, cy: 220, path: "M465,200 L520,200 522,218 520,240 465,240 462,218 Z" },
  ky: { name: "Kentucky", cx: 650, cy: 280, path: "M610,270 L700,265 710,275 700,290 615,295 610,280 Z" },
  la: { name: "Louisiana", cx: 545, cy: 350, path: "M520,330 L570,330 575,345 570,365 530,365 520,345 Z" },
  me: { name: "Maine", cx: 880, cy: 140, path: "M865,110 L890,105 900,125 895,155 880,170 865,155 860,130 Z" },
  ma: { name: "Massachusetts", cx: 870, cy: 178, path: "M845,172 L885,170 888,178 882,186 845,186 843,178 Z" },
  mi: { name: "Michigan", cx: 620, cy: 190, path: "M600,160 L640,155 650,175 645,200 630,210 610,205 595,190 Z" },
  ms: { name: "Mississippi", cx: 575, cy: 325, path: "M565,295 L585,295 588,320 585,350 570,355 565,330 Z" },
};

export default function USMapSelector({ activeStates, stateData }) {
  const navigate = useNavigate();

  return (
    <div className={styles.container}>
      <svg viewBox="200 100 700 300" className={styles.map}>
        {/* Background US outline (simplified) */}
        <rect x="200" y="100" width="700" height="300" fill="transparent" />

        {/* Tracked states */}
        {Object.entries(STATES).map(([code, state]) => {
          const isActive = activeStates?.includes(code);
          const color = STATE_COLORS[code] || "#4f8ff7";
          return (
            <g
              key={code}
              className={styles.state}
              onClick={() => navigate(`/state/${code}`)}
            >
              <path
                d={state.path}
                fill={isActive ? color + "40" : color + "20"}
                stroke={color}
                strokeWidth="2"
                className={styles.statePath}
              />
              <text
                x={state.cx}
                y={state.cy}
                textAnchor="middle"
                dominantBaseline="middle"
                className={styles.stateLabel}
                fill={color}
              >
                {code.toUpperCase()}
              </text>
            </g>
          );
        })}
      </svg>

      {/* State cards below the map */}
      <div className={styles.stateCards}>
        {Object.entries(STATES).map(([code, state]) => {
          const data = stateData?.[code];
          const color = STATE_COLORS[code];
          return (
            <button
              key={code}
              className={styles.stateCard}
              style={{ borderColor: color }}
              onClick={() => navigate(`/state/${code}`)}
            >
              <span className={styles.cardCode} style={{ color }}>{code.toUpperCase()}</span>
              <span className={styles.cardName}>{state.name}</span>
              {data?.latestData?.handle && (
                <span className={styles.cardValue}>
                  ${(data.latestData.handle / 1e9).toFixed(2)}B
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
