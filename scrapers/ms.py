"""Mississippi sports betting scraper — MSG Commission Sports Wagering PDFs.

Downloads monthly Sports Wagering Report PDFs from the Mississippi Gaming Commission.
Each PDF has 3 pages (Central, Coastal, Northern regions) with sport-type breakdowns.
The "Overall for State" row on the last page provides state-level totals.

Mississippi is retail-only (no online sports wagering). Casinos with sportsbooks
are located in three regions along the Mississippi River and Gulf Coast.

Tax: 8% state + 4% local = 12% on taxable (adjusted gross) sports wagering revenue.
Data available from November 2018 (sports betting launched August 2018).
"""

import io
import re
from collections import defaultdict
from datetime import date

import pandas as pd
import pdfplumber

from .base import BaseScraper
from .utils import get_session, clean_dollar_value

PAGE_URL = "https://www.msgamingcommission.com/reports/monthly_reports"
PDF_BASE = "https://www.msgamingcommission.com/files/monthly_reports/"

# First month with a valid PDF (Aug-Oct 2018 are not available as PDFs)
FIRST_MONTH = date(2018, 11, 1)


class MSScraper(BaseScraper):
    STATE_CODE = "ms"
    STATE_NAME = "Mississippi"
    TAX_RATE = 0.12
    TAX_RATE_NOTE = "8% state + 4% local on taxable sports wagering revenue"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = False
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2018-08-01"
    GGR_DEFINITION = "Taxable Revenue (modified accrual basis; Write − Payouts)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sports_data = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        session = get_session()

        month_urls = self._generate_pdf_urls()
        print(f"  Checking {len(month_urls)} monthly PDFs (Nov 2018 – present)...")

        totals = []
        sports_by_type = defaultdict(list)
        success = 0

        for date_obj, url_variants in month_urls:
            content = None
            for url in url_variants:
                try:
                    resp = session.get(url, timeout=30)
                    if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                        content = resp.content
                        break
                except Exception:
                    continue

            if not content:
                continue

            try:
                state_total, sports = self._parse_pdf(content, date_obj)
                if state_total:
                    totals.append(state_total)
                    success += 1
                for sport, handle in sports.items():
                    sports_by_type[sport].append({"date": date_obj, "handle": handle})
            except Exception as e:
                print(f"    Error parsing {date_obj}: {e}")

        print(f"  Parsed {success} monthly reports.")

        if not totals:
            return {}

        # Cache sports data for scrape_sports()
        self._sports_data = {}
        for sport, records in sorted(sports_by_type.items()):
            df = pd.DataFrame(records)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
            self._sports_data[sport] = df

        df = pd.DataFrame(totals)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        return {"total": df[["date", "handle", "ggr"]]}

    def scrape_sports(self) -> dict[str, pd.DataFrame] | None:
        return self._sports_data

    # ── URL generation ─────────────────────────────────────────────

    @staticmethod
    def _generate_pdf_urls() -> list[tuple[date, list[str]]]:
        """Generate (date, [url_variants]) pairs from Nov 2018 to current month.

        Some months use inconsistent naming:
          - Standard: {MMYY}_sports_wagering.pdf
          - No underscore: {MMYY}sports_wagering.pdf
          - Capitalized: {MMYY}_Sports_Wagering.pdf
        """
        urls = []
        current = FIRST_MONTH
        today = date.today().replace(day=1)
        while current <= today:
            mmyy = f"{current.month:02d}{current.year % 100:02d}"
            variants = [
                f"{PDF_BASE}{mmyy}_sports_wagering.pdf",
                f"{PDF_BASE}{mmyy}sports_wagering.pdf",
                f"{PDF_BASE}{mmyy}_Sports_Wagering.pdf",
            ]
            urls.append((current, variants))
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)
        return urls

    # ── PDF parsing ────────────────────────────────────────────────

    @staticmethod
    def _parse_pdf(content: bytes, date_obj: date) -> tuple[dict | None, dict]:
        """Parse a Sports Wagering Report PDF.

        Returns:
            (state_total, sports_dict)
            state_total: {"date": date, "handle": float, "ggr": float} or None
            sports_dict: {"Football": handle, "Basketball": handle, ...}
        """
        pdf = pdfplumber.open(io.BytesIO(content))

        state_total = None
        sports = defaultdict(float)

        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue
            table = tables[0]

            for row in table:
                if not row or not row[0]:
                    continue
                label = str(row[0]).strip()

                # State-level totals (appears on last page only)
                if label == "Overall for State":
                    write = clean_dollar_value(row[1])
                    revenue = clean_dollar_value(row[2])
                    if write is not None:
                        state_total = {
                            "date": date_obj,
                            "handle": write,
                            "ggr": revenue if revenue is not None else 0.0,
                        }

                # Sport-type data (aggregate across all 3 regions)
                if label.startswith("Sports -"):
                    sport = label.replace("Sports - ", "").strip()
                    write = clean_dollar_value(row[1])
                    if write is not None:
                        sports[sport] += write
                elif label == "Sports Parlay Cards":
                    write = clean_dollar_value(row[1])
                    if write is not None:
                        sports["Parlay Cards"] += write
                elif label == "Other":
                    write = clean_dollar_value(row[1])
                    if write is not None:
                        sports["Other"] += write

        return state_total, dict(sports)
