import styles from "./KPICard.module.css";

export default function KPICard({ label, value, subValue, trend, color, tooltip }) {
  const trendClass = trend > 0 ? styles.up : trend < 0 ? styles.down : "";
  const trendIcon = trend > 0 ? "\u25B2" : trend < 0 ? "\u25BC" : "";

  return (
    <div className={styles.card} style={color ? { borderTopColor: color } : undefined} title={tooltip}>
      <div className={styles.label}>{label}</div>
      <div className={styles.value}>{value}</div>
      {(subValue || trend != null) && (
        <div className={`${styles.sub} ${trendClass}`}>
          {trendIcon && <span className={styles.trendIcon}>{trendIcon}</span>}
          {subValue}
        </div>
      )}
    </div>
  );
}
