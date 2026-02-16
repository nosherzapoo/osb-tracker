import styles from "./Skeleton.module.css";

export default function Skeleton({ width, height = 20, variant = "rect", count = 1 }) {
  const items = Array.from({ length: count }, (_, i) => (
    <div
      key={i}
      className={`${styles.skeleton} ${styles[variant]}`}
      style={{ width, height }}
    />
  ));

  return count === 1 ? items[0] : <div className={styles.group}>{items}</div>;
}

export function KPISkeleton() {
  return (
    <div className={styles.kpiRow}>
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className={styles.kpiCard}>
          <Skeleton width="60%" height={12} />
          <Skeleton width="80%" height={28} />
          <Skeleton width="40%" height={12} />
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 320 }) {
  return <Skeleton width="100%" height={height} />;
}
