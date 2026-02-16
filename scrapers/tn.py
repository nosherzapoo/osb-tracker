"""Tennessee sports betting scraper — TN Sports Wagering Council reports.

Downloads monthly PDF and CSV reports from the TN SWAC reports page.
Tennessee is online-only (no retail sportsbooks). The tax regime changed:
  - Nov 2020 – Jun 2023: 20% privilege tax on Adjusted Gross Income (GGR)
  - Jul 2023 – present: 1.85% privilege tax on gross handle (no GGR reported)

Reports contain: Handle, Tax, and GGR (pre-Jul 2023 only).
2020–2021 PDFs report values rounded to "$X.X Million".
2022+ PDFs/CSVs report exact dollar amounts.
"""

import io
import re
import time
from collections import defaultdict

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import BaseScraper

PAGE_URL = "https://www.tn.gov/swac/reports.html"
BASE_URL = "https://www.tn.gov"

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Tax regime change date
TAX_CHANGE_DATE = "2023-07-01"


class TNScraper(BaseScraper):
    STATE_CODE = "tn"
    STATE_NAME = "Tennessee"
    TAX_RATE = 0.0185
    TAX_RATE_NOTE = "1.85% on handle since Jul 2023; was 20% on AGI before"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = False
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2020-11-01"
    GGR_DEFINITION = "Adjusted Gross Income (pre-Jul 2023 only; not reported after)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tax_data = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        session = self._get_session()
        report_urls = self._find_report_urls(session)
        if not report_urls:
            print("  No report URLs found.")
            return {}

        print(f"  Found {len(report_urls)} monthly reports.")

        all_records = []
        tax_records = []
        success = 0

        for date_str, csv_url, pdf_url in report_urls:
            record = None

            # Prefer CSV (cleaner, no PDF parsing issues)
            if csv_url:
                record = self._parse_csv(session, csv_url, date_str)

            # Fall back to PDF
            if record is None and pdf_url:
                record = self._parse_pdf(session, pdf_url, date_str)

            if record:
                all_records.append({
                    "date": date_str,
                    "handle": record["handle"],
                    "ggr": record.get("ggr"),
                })
                if record.get("tax") is not None:
                    tax_records.append({
                        "date": date_str,
                        "handle": record["tax"],
                    })
                success += 1

            # Small delay to avoid hammering tn.gov
            time.sleep(0.3)

        print(f"  Parsed {success}/{len(report_urls)} reports.")

        if not all_records:
            return {}

        # Cache tax data for run() override
        tax_df = pd.DataFrame(tax_records)
        tax_df["date"] = pd.to_datetime(tax_df["date"])
        tax_df = tax_df.sort_values("date")
        self._tax_data = {"total": tax_df[["date", "handle"]].reset_index(drop=True)}

        df = pd.DataFrame(all_records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates(subset="date", keep="last")

        print(f"  Total: {len(df)} months, "
              f"${df['handle'].iloc[-1]:,.0f} handle latest")

        return {"total": df[["date", "handle", "ggr"]].reset_index(drop=True)}

    def run(self):
        """Override run to use actual tax values from reports."""
        result = super().run()

        if self._tax_data and not result.handle_pivot.empty:
            tax_pivot = self.build_pivot(self._tax_data, "handle")

            path = self.state_dir / "tax_revenue.csv"
            tax_pivot.to_csv(path, index=True, date_format="%Y-%m-%d")
            print(f"  Rewrote tax_revenue.csv (actual privilege tax values)")

            # Fix metadata with actual latest tax
            latest_date = result.handle_pivot.index.max()
            if latest_date in tax_pivot.index:
                latest_tax = tax_pivot.loc[latest_date, "Total"]
                if pd.notna(latest_tax) and result.metadata:
                    result.metadata["latestData"]["taxRevenue"] = round(latest_tax, 2)

            result = result.__class__(
                state_code=result.state_code,
                state_name=result.state_name,
                handle_pivot=result.handle_pivot,
                ggr_pivot=result.ggr_pivot,
                hold_pivot=result.hold_pivot,
                yoy_handle=result.yoy_handle,
                yoy_ggr=result.yoy_ggr,
                tax_revenue=tax_pivot,
                sports_handle=result.sports_handle,
                metadata=result.metadata,
            )

        return result

    # ── Session ───────────────────────────────────────────────────

    @staticmethod
    def _get_session() -> requests.Session:
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1,
                        status_forcelist=[500, 502, 503, 504])
        session.mount("https://", HTTPAdapter(max_retries=retries))
        session.headers["User-Agent"] = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko)"
        )
        return session

    # ── URL discovery ─────────────────────────────────────────────

    def _find_report_urls(
        self, session: requests.Session,
    ) -> list[tuple[str, str | None, str | None]]:
        """Find all monthly report URLs from the SWAC reports page.

        Returns list of (date_str, csv_url, pdf_url) sorted by date.
        """
        try:
            resp = session.get(PAGE_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  Error fetching page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        reports: dict[str, dict] = {}

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/content/dam/tn/swac/documents/report/" not in href:
                continue

            is_csv = href.lower().endswith(".csv")
            is_pdf = href.lower().endswith(".pdf")
            if not (is_csv or is_pdf):
                continue

            year_match = re.search(r"/report/(\d{4})/", href)
            if not year_match:
                continue
            year = int(year_match.group(1))

            filename = href.split("/")[-1].lower()
            month_num = None
            for mname, mnum in MONTH_NAMES.items():
                if mname in filename:
                    month_num = mnum
                    break

            if month_num is None:
                continue

            date_str = f"{year}-{month_num:02d}-01"
            full_url = href if href.startswith("http") else BASE_URL + href

            if date_str not in reports:
                reports[date_str] = {"csv": None, "pdf": None}

            if is_csv:
                reports[date_str]["csv"] = full_url
            elif is_pdf:
                reports[date_str]["pdf"] = full_url

        result = []
        for date_str in sorted(reports.keys()):
            r = reports[date_str]
            result.append((date_str, r["csv"], r["pdf"]))

        return result

    # ── CSV parsing ───────────────────────────────────────────────

    @staticmethod
    def _parse_csv(
        session: requests.Session, url: str, date_str: str,
    ) -> dict | None:
        """Parse a TN SWAC monthly CSV report.

        Format (Jul 2023+):
            o   Gross Wagers," $540,424,861 "
            o   Adjustments," $4,267,858 "
            o   Gross Handle," $536,157,003 "
            o   Privilege Tax Assessed," $9,918,905 "
        """
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        text = resp.text
        handle = None
        tax = None

        for line in text.split("\n"):
            val = _extract_dollar_value(line)
            if val is None:
                continue

            lower = line.lower()
            if "gross handle" in lower:
                handle = val
            elif "gross wager" in lower and handle is None:
                handle = val
            elif "privilege tax" in lower:
                tax = val

        if handle is None:
            return None

        return {"handle": handle, "tax": tax, "ggr": None}

    # ── PDF parsing ───────────────────────────────────────────────

    @staticmethod
    def _parse_pdf(
        session: requests.Session, url: str, date_str: str,
    ) -> dict | None:
        """Parse a TN SWAC monthly PDF report.

        Handles four format variants:
        1. Nov-Dec 2020: exact amounts, Gross Wagers/Payouts/Tax
        2. 2021: "$X.X Million" format with AGI
        3. Jan 2022 - Jun 2023: exact amounts with AGI
        4. Jul 2023+: exact amounts, no AGI/Payouts
        """
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                return None
            # Verify it's a PDF
            if not resp.content[:5].startswith(b"%PDF"):
                return None
        except Exception:
            return None

        try:
            pdf = pdfplumber.open(io.BytesIO(resp.content))
        except Exception:
            return None

        text = pdf.pages[0].extract_text() or ""
        if not text:
            return None

        handle = None
        payouts = None
        agi = None
        tax = None

        for line in text.split("\n"):
            val = _extract_value_from_line(line)
            if val is None:
                continue

            lower = line.lower()
            if "gross handle" in lower:
                handle = val
            elif "gross wager" in lower and handle is None:
                handle = val
            elif "payout" in lower:
                payouts = val
            elif "adjusted gross income" in lower:
                agi = val
            elif "privilege tax" in lower:
                tax = val

        if handle is None:
            return None

        # Compute GGR: use AGI if available, else Wagers - Payouts
        ggr = None
        if agi is not None:
            ggr = agi
        elif payouts is not None:
            ggr = handle - payouts

        return {"handle": handle, "ggr": ggr, "tax": tax}


# ── Helpers ───────────────────────────────────────────────────

def _extract_dollar_value(text: str) -> float | None:
    """Extract a dollar amount from CSV/text line.

    Handles: "$540,424,861", "$ 536,157,003", "$4,267,858 "
    """
    match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _extract_value_from_line(line: str) -> float | None:
    """Extract a dollar value from a PDF text line.

    Handles multiple formats:
    - "$211.3 Million" → 211300000
    - "$ 386,059,756" → 386059756
    - "$ 5 40,424,861" → 540424861 (split number)
    - "$180,900,000" → 180900000
    """
    # Check for "Million" format first
    million_match = re.search(
        r"\$\s*([\d,.]+)\s*Million", line, re.IGNORECASE,
    )
    if million_match:
        val_str = million_match.group(1).replace(",", "")
        try:
            return float(val_str) * 1_000_000
        except ValueError:
            return None

    # Standard dollar amount (may have spaces from PDF layout)
    # First, try clean extraction
    match = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", line)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            pass

    # Handle split numbers like "$ 5 40,424,861"
    # Find $ sign, then collect all digit/comma fragments after it
    dollar_idx = line.find("$")
    if dollar_idx >= 0:
        after = line[dollar_idx + 1:].strip()
        # Remove spaces within numbers: "5 40,424,861" → "540,424,861"
        cleaned = re.sub(r"(\d)\s+(\d)", r"\1\2", after)
        cleaned = re.sub(r"(\d)\s+,", r"\1,", cleaned)
        match2 = re.match(r"([\d,]+(?:\.\d+)?)", cleaned)
        if match2:
            try:
                return float(match2.group(1).replace(",", ""))
            except ValueError:
                pass

    return None
