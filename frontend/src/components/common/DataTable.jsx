import { useState, useMemo } from "react";
import styles from "./DataTable.module.css";

export default function DataTable({ data, columns, formatCell, dateColumn, maxRows = 50 }) {
  const [sortCol, setSortCol] = useState(null);
  const [sortAsc, setSortAsc] = useState(false);

  const allColumns = useMemo(() => {
    if (columns) return columns;
    if (!data || data.length === 0) return [];
    return Object.keys(data[0]);
  }, [data, columns]);

  const sorted = useMemo(() => {
    if (!data) return [];
    let rows = [...data];
    if (sortCol) {
      rows.sort((a, b) => {
        const av = parseFloat(a[sortCol]) || a[sortCol];
        const bv = parseFloat(b[sortCol]) || b[sortCol];
        if (av < bv) return sortAsc ? -1 : 1;
        if (av > bv) return sortAsc ? 1 : -1;
        return 0;
      });
    }
    return rows.slice(0, maxRows);
  }, [data, sortCol, sortAsc, maxRows]);

  function handleSort(col) {
    if (sortCol === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(col);
      setSortAsc(false);
    }
  }

  if (!data || data.length === 0) {
    return <div className={styles.empty}>No data available</div>;
  }

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            {allColumns.map((col) => (
              <th key={col} onClick={() => handleSort(col)} className={styles.th}>
                {col}
                {sortCol === col && <span className={styles.sortArrow}>{sortAsc ? " \u25B2" : " \u25BC"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={i} className={styles.row}>
              {allColumns.map((col) => (
                <td key={col} className={styles.td}>
                  {formatCell ? formatCell(row[col], col, row) : row[col]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {data.length > maxRows && (
        <div className={styles.truncated}>Showing {maxRows} of {data.length} rows</div>
      )}
    </div>
  );
}
