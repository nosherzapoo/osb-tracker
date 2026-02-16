import styles from "./DateRangeFilter.module.css";

const PRESETS = [
  { label: "3M", months: 3 },
  { label: "6M", months: 6 },
  { label: "1Y", months: 12 },
  { label: "2Y", months: 24 },
  { label: "All", months: null },
];

export default function DateRangeFilter({ value, onChange }) {
  return (
    <div className={styles.container}>
      {PRESETS.map((p) => (
        <button
          key={p.label}
          className={`${styles.btn} ${value === p.months ? styles.active : ""}`}
          onClick={() => onChange(p.months)}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
