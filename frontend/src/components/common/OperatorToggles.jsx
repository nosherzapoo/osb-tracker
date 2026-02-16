import { getSeriesColor } from "../../lib/colors";
import styles from "./OperatorToggles.module.css";

export default function OperatorToggles({ operators, active, onToggle, onToggleAll, isSportsTab = false }) {
  const allActive = operators.every((op) => active.includes(op));

  return (
    <div className={styles.container}>
      <button
        className={`${styles.toggle} ${allActive ? styles.active : ""}`}
        onClick={onToggleAll}
        style={{ borderColor: "var(--text-muted)" }}
      >
        All
      </button>
      {operators.map((op) => {
        const isActive = active.includes(op);
        const color = getSeriesColor(op, isSportsTab);
        return (
          <button
            key={op}
            className={`${styles.toggle} ${isActive ? styles.active : ""}`}
            onClick={() => onToggle(op)}
            style={{
              borderColor: isActive ? color : "var(--border)",
              color: isActive ? color : "var(--text-muted)",
            }}
          >
            <span className={styles.dot} style={{ backgroundColor: isActive ? color : "transparent" }} />
            {op}
          </button>
        );
      })}
    </div>
  );
}
