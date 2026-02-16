"""Ohio sports betting scraper — OCCC Sports Gaming Revenue Excel reports.

Downloads yearly Sports Gaming Revenue XLSX files from the Ohio Casino Control
Commission. Each file has 12 month sheets with TYPE A (online) and TYPE B
(retail) operator-level data.

Columns: Total Gross Receipts (Handle), (-) Winnings Paid, (-) Voided Wagers,
         Promotional*, Revenue (GGR), Taxable Revenue.

Tax: 20% on taxable sports gaming revenue (floors at 0 when GGR is negative).
Data available from January 2023.
"""

import io
import re
from collections import defaultdict
from datetime import date

import openpyxl
import pandas as pd

from .base import BaseScraper
from .utils import get_session

PAGE_URL = "https://casinocontrol.ohio.gov/about/revenue-reports"
DAM_BASE = "https://dam.assets.ohio.gov/raw/upload/casinocontrol.ohio.gov/revenue-reports"

# Brand keyword → consumer-facing name (matched against the brand portion of proprietor name)
BRAND_MAP = {
    "FANDUEL": "FanDuel",
    "DRAFTKINGS": "DraftKings",
    "BETMGM": "BetMGM",
    "CAESARS": "Caesars",
    "PENN INTERACTIVE": "ESPN Bet",
    "ESPN BET": "ESPN Bet",
    "FANATICS": "Fanatics",
    "POINTSBET": "Fanatics",
    "BET365": "Bet365",
    "BALLY": "Bally Bet",
    "RSI": "Rush Street Interactive",
    "SEMINOLE HARD ROCK": "Seminole Hard Rock",
    "SUPERBOOK": "SuperBook",
    "BETWAY": "Betway",
    "BETFRED": "BetFred",
}

MONTH_SHEETS = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
]

# Rows with these prefixes are not operator data
SKIP_PREFIXES = (
    "Subtotal", "Total", "Online Proprietor", "Retail Proprietor",
    "All Proprietors", "TYPE", "*",
)


class OHScraper(BaseScraper):
    STATE_CODE = "oh"
    STATE_NAME = "Ohio"
    TAX_RATE = 0.20
    TAX_RATE_NOTE = "20% on taxable sports gaming revenue"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2023-01-01"
    GGR_DEFINITION = "Sports Gaming Revenue (Handle − Payouts − Voided − Promos)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tax_data = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        session = get_session()

        file_urls = self._discover_urls(session)
        if not file_urls:
            print("  No Excel files found.")
            return {}

        print(f"  Found {len(file_urls)} yearly Excel files.")

        brand_records = defaultdict(list)
        tax_records = defaultdict(list)

        for year, url in file_urls:
            try:
                recs = self._parse_yearly_file(session, url, year)
                for rec in recs:
                    brand_records[rec["brand"]].append(rec)
                    tax_records[rec["brand"]].append(
                        {"date": rec["date"], "tax": rec["tax"]}
                    )
            except Exception as e:
                print(f"    Error parsing {year}: {e}")

        if not brand_records:
            print("  No data parsed.")
            return {}

        result = {}
        tax_result = {}
        for brand, records in sorted(brand_records.items()):
            df = pd.DataFrame(records)
            df["date"] = pd.to_datetime(df["date"])
            df = df.groupby("date").agg({"handle": "sum", "ggr": "sum"}).reset_index()
            df = df.sort_values("date")
            result[brand] = df[["date", "handle", "ggr"]]

            tdf = pd.DataFrame(tax_records[brand])
            tdf["date"] = pd.to_datetime(tdf["date"])
            tdf = tdf.groupby("date").agg({"tax": "sum"}).reset_index()
            tdf = tdf.sort_values("date")
            tdf = tdf.rename(columns={"tax": "handle"})
            tax_result[brand] = tdf[["date", "handle"]]

            print(f"    {brand}: {len(df)} months")

        self._tax_data = tax_result
        return result

    def run(self):
        """Override run to use actual tax (Taxable Revenue × 20%) from Excel."""
        result = super().run()

        if self._tax_data and not result.ggr_pivot.empty:
            tax_pivot = self.build_pivot(self._tax_data, "handle")

            path = self.state_dir / "tax_revenue.csv"
            tax_pivot.to_csv(path, index=True, date_format="%Y-%m-%d")
            print(f"  Rewrote tax_revenue.csv (actual tax from Excel)")

            latest_date = result.handle_pivot.index.max()
            if latest_date in tax_pivot.index:
                latest_tax = tax_pivot.loc[latest_date, "Total"]
                if pd.notna(latest_tax) and result.metadata:
                    result.metadata["latestData"]["taxRevenue"] = round(
                        float(latest_tax), 2
                    )

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

    # ── URL discovery ─────────────────────────────────────────────

    @staticmethod
    def _discover_urls(session) -> list[tuple[int, str]]:
        """Probe known URL patterns to find yearly Excel files."""
        found = []
        current_year = date.today().year

        for year in range(2023, current_year + 1):
            url = OHScraper._find_best_url(session, year)
            if url:
                fname = url.split("/")[-1]
                print(f"    {year}: {fname}")
                found.append((year, url))

        return found

    @staticmethod
    def _find_best_url(session, year: int) -> str | None:
        """Find the most complete URL for a given year (highest month suffix wins)."""
        candidates = []

        # Pattern 1: {year}/Sports/{year}_Sports_Gaming_Revenue_Report{N}.xlsx
        for n in range(12, 0, -1):
            candidates.append(
                f"{DAM_BASE}/{year}/Sports/{year}_Sports_Gaming_Revenue_Report{n}.xlsx"
            )

        # Pattern 2: {year}/Sports/{year}_Sports_Gaming_Revenue_Report.xlsx (no suffix)
        candidates.append(
            f"{DAM_BASE}/{year}/Sports/{year}_Sports_Gaming_Revenue_Report.xlsx"
        )

        # Pattern 3: {year}/{year}_Sports_Gaming_Revenue_Report.xlsx
        candidates.append(
            f"{DAM_BASE}/{year}/{year}_Sports_Gaming_Revenue_Report.xlsx"
        )

        # Pattern 4: 2023 had a special root-level path
        if year == 2023:
            candidates.append(
                f"{DAM_BASE}/December_{year}_Sports_Gaming_Revenue_Report.xlsx"
            )

        for url in candidates:
            try:
                resp = session.head(url, timeout=10, allow_redirects=True)
                if resp.status_code == 200:
                    return url
            except Exception:
                continue

        return None

    # ── Excel parsing ─────────────────────────────────────────────

    def _parse_yearly_file(self, session, url: str, year: int) -> list[dict]:
        """Parse a yearly Sports Gaming Revenue Excel file."""
        resp = session.get(url, timeout=60)
        resp.raise_for_status()

        wb = openpyxl.load_workbook(io.BytesIO(resp.content), data_only=True)
        records = []
        months_parsed = 0

        for month_idx, sheet_name in enumerate(MONTH_SHEETS):
            if sheet_name not in wb.sheetnames:
                continue

            month_num = month_idx + 1
            date_str = f"{year}-{month_num:02d}-01"

            try:
                month_recs = self._parse_month_sheet(wb[sheet_name], date_str)
                if month_recs:
                    records.extend(month_recs)
                    months_parsed += 1
            except Exception as e:
                print(f"      Error parsing {sheet_name} {year}: {e}")

        wb.close()
        print(f"    Parsed {year}: {months_parsed} months")
        return records

    @staticmethod
    def _parse_month_sheet(ws, date_str: str) -> list[dict]:
        """Parse a single month sheet for online + retail operator data."""
        records = []

        for row_idx in range(1, ws.max_row + 1):
            cell_val = ws.cell(row=row_idx, column=1).value
            if not cell_val:
                continue

            label = str(cell_val).strip()

            # Skip non-data rows
            if any(label.startswith(p) for p in SKIP_PREFIXES):
                continue
            if "OHIO SPORTS GAMING" in label:
                continue

            # Column 2 = Total Gross Receipts (Handle)
            handle_raw = ws.cell(row=row_idx, column=2).value
            if not isinstance(handle_raw, (int, float)):
                continue

            handle = float(handle_raw)
            if handle == 0:
                continue

            # Column 6 = Revenue (GGR), Column 7 = Taxable Revenue
            ggr_raw = ws.cell(row=row_idx, column=6).value
            taxable_raw = ws.cell(row=row_idx, column=7).value

            ggr = float(ggr_raw) if isinstance(ggr_raw, (int, float)) else 0.0
            taxable = float(taxable_raw) if isinstance(taxable_raw, (int, float)) else 0.0
            tax = taxable * 0.20

            brand = OHScraper._map_brand(label)

            records.append({
                "brand": brand,
                "date": date_str,
                "handle": handle,
                "ggr": ggr,
                "tax": tax,
            })

        return records

    # ── Brand mapping ─────────────────────────────────────────────

    @staticmethod
    def _map_brand(proprietor_name: str) -> str:
        """Map proprietor/provider name to consumer-facing brand.

        Names come in formats like:
          "BELTERRA PARK - FANDUEL"
          "JACK CLEVELAND (BETJACK)"
          "HOLLYWOOD COLUMBUS"  (standalone retail)
        """
        name_upper = proprietor_name.upper()

        # Extract brand portion from "CASINO - BRAND" or "CASINO (BRAND)" format
        brand_part = name_upper
        if " - " in name_upper:
            brand_part = name_upper.split(" - ", 1)[1]
        elif "(" in name_upper:
            match = re.search(r"\(([^)]+)\)", name_upper)
            if match:
                brand_part = match.group(1)

        # Match against known brand keywords
        for keyword, brand in BRAND_MAP.items():
            if keyword in brand_part:
                return brand

        # Fallback: check the full name
        for keyword, brand in BRAND_MAP.items():
            if keyword in name_upper:
                return brand

        return "Others"
