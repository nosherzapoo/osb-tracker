"""Massachusetts sports betting scraper — MGC PDF revenue reports.

Downloads operator-level PDF reports from the Massachusetts Gaming Commission.
Each PDF contains all monthly data from launch to the current month.

Cat. 1 (retail, 15% tax): Encore Boston Harbor, MGM Springfield, Plainridge Park Casino
Cat. 3 (online, 20% tax): DraftKings, FanDuel, BetMGM, Caesars, Fanatics, Bally Bet, theScore Bet

GGR = Monthly Win (accrual basis).
Tax is on AGSWR (Adjusted Gross Sports Wagering Revenue = Win − Federal Excise Tax).
Cat. 1 operators may carry forward losses across months.
"""

import io
import re
from collections import defaultdict

import pandas as pd
import pdfplumber

from .base import BaseScraper
from .utils import get_session, clean_dollar_value

PAGE_URL = "https://massgaming.com/regulations/revenue/"

MONTH_NUM = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

# Map PDF title operator names → consumer-facing names
OPERATOR_NAME_MAP = {
    "DraftKings": "DraftKings",
    "FanDuel": "FanDuel",
    "BetMGM": "BetMGM",
    "Caesars": "Caesars",
    "Fanatics": "Fanatics",
    "Bally's": "Bally Bet",
    "Ballys": "Bally Bet",
    "theScore Bet": "theScore Bet",
    "theScore": "theScore Bet",
    "Encore": "Encore Boston Harbor",
    "MGM Springfield": "MGM Springfield",
    "Plainridge Park Casino": "Plainridge Park Casino",
    "Plainridge Park": "Plainridge Park Casino",
    "Plainridge": "Plainridge Park Casino",
}


class MAScraper(BaseScraper):
    STATE_CODE = "ma"
    STATE_NAME = "Massachusetts"
    TAX_RATE = 0.20
    TAX_RATE_NOTE = "20% online (Cat. 3), 15% retail (Cat. 1) on AGSWR"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2023-01-01"
    GGR_DEFINITION = "Monthly Win (accrual basis)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tax_data = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        session = get_session()
        session.headers["Referer"] = PAGE_URL

        pdf_urls = self._find_pdf_urls(session)
        if not pdf_urls:
            print("  No PDF URLs found.")
            return {}

        print(f"  Found {len(pdf_urls)} Sports Wagering PDFs.")

        operator_data = defaultdict(list)
        tax_data = defaultdict(list)

        for url in pdf_urls:
            try:
                records = self._download_and_parse(session, url)
                for rec in records:
                    op = rec["operator"]
                    operator_data[op].append(rec)
                    tax_data[op].append({
                        "date": rec["date"],
                        "tax": rec["tax_collected"],
                    })
            except Exception as e:
                fname = url.split("/")[-1][:60]
                print(f"    Error parsing {fname}: {e}")

        if not operator_data:
            print("  No data parsed.")
            return {}

        result = {}
        tax_result = {}
        for operator, records in sorted(operator_data.items()):
            df = pd.DataFrame(records)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").drop_duplicates(subset="date", keep="last")
            df = df.reset_index(drop=True)
            result[operator] = df[["date", "handle", "ggr"]]

            tdf = pd.DataFrame(tax_data[operator])
            tdf["date"] = pd.to_datetime(tdf["date"])
            tdf = tdf.sort_values("date").drop_duplicates(subset="date", keep="last")
            tdf = tdf.reset_index(drop=True)
            tdf = tdf.rename(columns={"tax": "handle"})
            tax_result[operator] = tdf[["date", "handle"]]

            print(f"    {operator}: {len(df)} months")

        self._tax_data = tax_result
        return result

    def run(self):
        """Override run to use actual Tax Collected from PDFs."""
        result = super().run()

        if self._tax_data and not result.ggr_pivot.empty:
            tax_pivot = self.build_pivot(self._tax_data, "handle")

            path = self.state_dir / "tax_revenue.csv"
            tax_pivot.to_csv(path, index=True, date_format="%Y-%m-%d")
            print(f"  Rewrote tax_revenue.csv (actual Tax Collected from PDFs)")

            latest_date = result.handle_pivot.index.max()
            if latest_date in tax_pivot.index:
                latest_tax = tax_pivot.loc[latest_date, "Total"]
                if pd.notna(latest_tax) and result.metadata:
                    result.metadata["latestData"]["taxRevenue"] = round(float(latest_tax), 2)

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

    def _find_pdf_urls(self, session) -> list[str]:
        """Scrape the revenue page for Sports Wagering Revenue Report PDF links."""
        urls = []
        try:
            resp = session.get(PAGE_URL, timeout=30)
            resp.raise_for_status()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")

            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.lower().endswith(".pdf"):
                    continue
                if "sports-wagering-revenue-report" not in href.lower():
                    continue
                urls.append(href)

        except Exception as e:
            print(f"  Error fetching page: {e}")

        return urls

    def _download_and_parse(self, session, url: str) -> list[dict]:
        """Download a PDF and parse monthly revenue data from its table."""
        resp = session.get(url, timeout=60)
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code} for {url.split('/')[-1][:50]}")
            return []

        pdf = pdfplumber.open(io.BytesIO(resp.content))
        page = pdf.pages[0]

        # Extract operator name and category from title text
        text = page.extract_text() or ""
        operator, category = self._extract_operator_info(text)
        if not operator:
            return []

        tables = page.extract_tables()
        if not tables:
            return []

        table = tables[0]
        records = []

        for row in table[1:]:  # Skip header row
            if not row or not row[0]:
                continue

            month_str = row[0].strip()
            if month_str.upper() == "TOTAL":
                break

            date = self._parse_month(month_str)
            if not date:
                continue

            # Parse handle (col 2) and win/GGR (col 3)
            handle = clean_dollar_value(row[2])
            win = clean_dollar_value(row[3])

            # Handle merged handle+win in one cell (happens on some first rows)
            if win is None and row[2] and " $" in str(row[2]):
                parts = str(row[2]).split(" $", 1)
                handle = clean_dollar_value(parts[0])
                win = clean_dollar_value("$" + parts[1])

            if handle is None or handle == 0:
                continue  # Skip pre-launch months (e.g. Bally Bet before Jul 2024)

            ggr = win if win is not None else 0.0

            # Tax Collected is column 7
            tax_collected = clean_dollar_value(row[7]) or 0.0

            records.append({
                "operator": operator,
                "date": date,
                "handle": handle,
                "ggr": ggr,
                "tax_collected": tax_collected,
            })

        return records

    def _extract_operator_info(self, text: str) -> tuple:
        """Extract operator name and category (1 or 3) from PDF title text."""
        match = re.search(
            r"Sports Wagering Tax Revenue\s+(.+?)\s+Category\s+(\d)",
            text,
        )
        if not match:
            return None, None

        raw_name = match.group(1).strip()
        category = int(match.group(2))

        # Map to consumer-facing name
        operator = None
        for key, brand in OPERATOR_NAME_MAP.items():
            if key.lower() in raw_name.lower():
                operator = brand
                break
        if not operator:
            operator = raw_name

        return operator, category

    def _parse_month(self, month_str: str) -> str | None:
        """Parse 'March 2023' or 'July 2025 FY26' into '2023-03-01'."""
        month_str = re.sub(r"\s+FY\d+", "", month_str).strip()
        match = re.match(r"(\w+)\s+(\d{4})", month_str)
        if not match:
            return None
        month_name = match.group(1)
        year = match.group(2)
        if month_name not in MONTH_NUM:
            return None
        return f"{year}-{MONTH_NUM[month_name]:02d}-01"
