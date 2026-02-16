import styles from "./FreshnessIndicator.module.css";

export default function FreshnessIndicator({ latestDate, frequency }) {
  if (!latestDate) return null;

  const latest = new Date(latestDate + "T12:00:00");
  const now = new Date();
  const daysSince = Math.floor((now - latest) / (1000 * 60 * 60 * 24));

  const threshold = frequency === "weekly" ? 14 : 45;
  const status = daysSince <= threshold ? "fresh" : daysSince <= threshold * 2 ? "stale" : "old";

  return (
    <div className={`${styles.indicator} ${styles[status]}`}>
      <span className={styles.dot} />
      <span className={styles.text}>
        {status === "fresh" ? "Current" : status === "stale" ? "Updating" : "Outdated"}
        {" \u2022 "}
        {daysSince}d ago
      </span>
    </div>
  );
}
