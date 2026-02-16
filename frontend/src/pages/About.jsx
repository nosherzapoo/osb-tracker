import { useData } from "../context/DataContext";
import { formatPercent } from "../lib/format";
import styles from "./About.module.css";

export default function About() {
  const { manifest } = useData();
  const states = manifest?.states || [];

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>About</h1>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Data Sources</h2>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>State</th>
                <th>Source</th>
                <th>Frequency</th>
                <th>Tax Rate</th>
                <th>Launch Date</th>
                <th>Operators</th>
              </tr>
            </thead>
            <tbody>
              {states.map((s) => (
                <tr key={s.code}>
                  <td><strong>{s.name}</strong></td>
                  <td>
                    <a href={s.sourceUrl} target="_blank" rel="noopener noreferrer">
                      {new URL(s.sourceUrl).hostname.replace("www.", "")}
                    </a>
                  </td>
                  <td>{s.frequency}</td>
                  <td>{formatPercent(s.taxRate)} {s.taxRateNote && <span className={styles.note}>({s.taxRateNote})</span>}</td>
                  <td>{s.launchDate}</td>
                  <td>{s.operators?.length || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Methodology</h2>
        <div className={styles.prose}>
          <p>
            <strong>Handle</strong> is the total dollar amount wagered by bettors in a given period.
            <strong> Gross Gaming Revenue (GGR)</strong> is the sportsbook's net win after paying out bets.
            <strong> Hold %</strong> = GGR / Handle, representing the operator's margin.
          </p>
          <p>
            <strong>Year-over-Year (YoY) Change</strong> compares each period to the same period one year prior.
            For weekly data, this looks back 364 days (52 weeks); for monthly data, 365 days.
          </p>
          <p>
            <strong>Tax Revenue</strong> is estimated as GGR multiplied by each state's headline tax rate. Actual
            tax collection may differ due to deductions, credits, promotional allowances, and graduated rate
            structures (e.g., Illinois).
          </p>
          <p>
            New York is the only state currently providing operator-level weekly breakdowns. Other states
            publish aggregate monthly totals. When live scraping fails, the system falls back to estimated
            data from public reporting.
          </p>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Tax Rate Comparison</h2>
        <div className={styles.taxBars}>
          {states
            .sort((a, b) => b.taxRate - a.taxRate)
            .map((s) => (
              <div key={s.code} className={styles.taxRow}>
                <span className={styles.taxLabel}>{s.abbreviation}</span>
                <div className={styles.taxBarBg}>
                  <div
                    className={styles.taxBarFill}
                    style={{ width: `${s.taxRate * 100 * 2}%` }}
                  />
                </div>
                <span className={styles.taxValue}>{formatPercent(s.taxRate)}</span>
              </div>
            ))}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Keyboard Shortcuts</h2>
        <div className={styles.shortcuts}>
          {[
            ["1-5", "Navigate pages"],
            ["j / k", "Previous / next operator (State Deep Dive)"],
            ["e", "Export data"],
            ["?", "Show help"],
          ].map(([key, desc]) => (
            <div key={key} className={styles.shortcutRow}>
              <kbd className={styles.kbd}>{key}</kbd>
              <span>{desc}</span>
            </div>
          ))}
        </div>
      </section>

      <footer className={styles.footer}>
        <p>
          Last updated: {manifest?.lastUpdated ? new Date(manifest.lastUpdated).toLocaleString() : "—"}
        </p>
      </footer>
    </div>
  );
}
