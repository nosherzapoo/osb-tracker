"""Pennsylvania sports betting scraper — PA Gaming Control Board monthly data.

Downloads fiscal-year Sports Wagering Report Excel files from the PGCB revenue
page. Each file covers one PA fiscal year (July–June) with monthly columns.
Data is broken down by casino license holder with Total / Retail / Online
sub-sections.

Casino license holders are mapped to consumer-facing sportsbook brands:
  VALLEY FORGE CASINO → FanDuel, HOLLYWOOD CASINO AT THE MEADOWS → DraftKings,
  RIVERS → Rush Street Interactive, PARX → Parx, HARRAH'S → Caesars,
  HOLLYWOOD CASINO → ESPN Bet, MOUNT AIRY → Fanatics, etc.

Tax: 34% state + 2% local share = 36% on taxable gross revenue.
Data available from November 2018 (sports betting launched May 2019 online,
Nov 2018 retail).
"""

import io
from collections import defaultdict
from datetime import datetime

import openpyxl
import pandas as pd
from bs4 import BeautifulSoup

from .base import BaseScraper
from .utils import get_session

PAGE_URL = "https://gamingcontrolboard.pa.gov/news-and-transparency/revenue"
BASE_URL = "https://gamingcontrolboard.pa.gov"

# Casino license holder → consumer-facing brand
CASINO_TO_BRAND = {
    "VALLEY FORGE CASINO": "FanDuel",
    "HOLLYWOOD CASINO AT THE MEADOWS": "DraftKings",
    "MEADOWS": "DraftKings",
    "HOLLYWOOD CASINO MORGANTOWN": "ESPN Bet",
    "HOLLYWOOD CASINO YORK": "ESPN Bet",
    "HOLLYWOOD CASINO": "ESPN Bet",
    "RIVERS - PITTSBURGH": "Rush Street Interactive",
    "RIVERS - PHILADELPHIA": "Rush Street Interactive",
    "SUGARHOUSE CASINO": "Rush Street Interactive",
    "RIVERS": "Rush Street Interactive",
    "PARX CASINO": "Parx",
    "PARX SHIPPENSBURG": "Parx",
    "HARRAH'S": "Caesars",
    "MOUNT AIRY": "Fanatics",
    "LIVE! CASINO PITTSBURGH": "BetMGM",
    "LIVE! CASINO PHILADELPHIA": "BetMGM",
    "WIND CREEK": "Betway",
    "MOHEGAN": "Others",
    "MOHEGAN - LEHIGH VALLEY": "Others",
    "PRESQUE ISLE": "Others",
    "SOUTH PHILADELPHIA RACE AND SPORTSBOOK": "Others",
    "OAKS RACE AND SPORTSBOOK": "Others",
}

# Metric row labels in the Total Sports Wagering block
SKIP_LABELS = frozenset([
    "Handle*", "Revenue", "Promotional Credits", "Gross Revenue (Taxable)",
    "Total Sports Wagering", "Retail Sports Wagering", "Online Sports Wagering",
])

# First PA fiscal year with sports wagering data
FIRST_FY_START = 2018


class PAScraper(BaseScraper):
    STATE_CODE = "pa"
    STATE_NAME = "Pennsylvania"
    TAX_RATE = 0.36
    TAX_RATE_NOTE = "34% state + 2% local share on taxable gross revenue"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2018-11-01"
    GGR_DEFINITION = "Taxable Gross Revenue (Revenue − Promotional Credits)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tax_data = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        session = get_session()

        fy_urls = self._discover_fy_urls(session)
        if not fy_urls:
            print("  No fiscal year Excel files found.")
            return {}

        print(f"  Found {len(fy_urls)} fiscal year files.")

        brand_records = defaultdict(list)
        tax_records = defaultdict(list)

        for fy_label, url in fy_urls:
            try:
                recs = self._parse_fy_file(session, url, fy_label)
                for rec in recs:
                    brand_records[rec["brand"]].append(rec)
                    tax_records[rec["brand"]].append(
                        {"date": rec["date"], "tax": rec["tax"]}
                    )
            except Exception as e:
                print(f"    Error parsing {fy_label}: {e}")

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
        """Override run to use actual tax (State Tax + Local Share) from Excel."""
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
    def _discover_fy_urls(session) -> list[tuple[str, str]]:
        """Discover fiscal year Excel URLs via the PGCB revenue page dropdown."""
        try:
            resp = session.get(PAGE_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  Error fetching revenue page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        # Parse the FY dropdown to get tid → FY label
        select = soup.find("select", {"name": "field_gaming_revenue_fiscal_year_target_id"})
        if not select:
            print("  Could not find FY dropdown on page.")
            return []

        fy_options = []
        for opt in select.find_all("option"):
            tid = opt.get("value", "")
            text = opt.get_text(strip=True)
            if not tid or tid == "All":
                continue
            # Extract start year from "FY 2025/2026" → 2025
            try:
                start_year = int(text.split("/")[0].split()[-1])
            except (ValueError, IndexError):
                continue
            if start_year >= FIRST_FY_START:
                fy_options.append((tid, text, start_year))

        # Sort by start year ascending
        fy_options.sort(key=lambda x: x[2])

        # For each FY, fetch the page with the tid param and find the Excel URL
        found = []
        for tid, fy_label, _ in fy_options:
            try:
                fy_resp = session.get(
                    PAGE_URL,
                    params={"field_gaming_revenue_fiscal_year_target_id": tid},
                    timeout=30,
                )
                fy_soup = BeautifulSoup(fy_resp.text, "lxml")

                xlsx_url = None
                for a in fy_soup.find_all("a", href=True):
                    href = a["href"]
                    if ".xlsx" in href.lower() and "sport" in href.lower():
                        xlsx_url = href if href.startswith("http") else BASE_URL + href
                        break

                if xlsx_url:
                    print(f"    {fy_label}: {xlsx_url.split('/')[-1][:60]}")
                    found.append((fy_label, xlsx_url))
                else:
                    print(f"    {fy_label}: no Sports Wagering xlsx found")

            except Exception as e:
                print(f"    Error discovering {fy_label}: {e}")

        return found

    # ── Excel parsing ─────────────────────────────────────────────

    def _parse_fy_file(self, session, url: str, fy_label: str) -> list[dict]:
        """Parse a fiscal year Sports Wagering Report Excel file."""
        resp = session.get(url, timeout=60)
        resp.raise_for_status()

        wb = openpyxl.load_workbook(io.BytesIO(resp.content), data_only=True)

        # Use first sheet (skip Footnotes)
        ws = None
        for name in wb.sheetnames:
            if "footnote" not in name.lower():
                ws = wb[name]
                break
        if ws is None:
            ws = wb[wb.sheetnames[0]]

        # Parse month columns from row 4
        months = self._parse_month_headers(ws)
        if not months:
            print(f"    No month headers found in {fy_label}")
            wb.close()
            return []

        # Find casino blocks and parse
        records = []
        casinos_found = 0
        row = 1
        while row <= ws.max_row:
            casino_name = self._detect_casino_row(ws, row)
            if casino_name and casino_name != "GRAND TOTAL":
                block_recs = self._parse_casino_block(ws, row, casino_name, months)
                if block_recs:
                    records.extend(block_recs)
                    casinos_found += 1
                row += 20  # Skip past this casino's block
            else:
                row += 1

        wb.close()
        print(f"    Parsed {fy_label}: {len(months)} months, {casinos_found} casinos")
        return records

    @staticmethod
    def _parse_month_headers(ws) -> dict[int, str]:
        """Parse month column headers from row 4.

        Returns {col_index: 'YYYY-MM-01'} for each month column.
        """
        months = {}
        for c in range(3, ws.max_column + 1, 2):
            val = ws.cell(row=4, column=c).value
            if not val:
                continue
            val = str(val).strip()
            if "Total" in val or "Grand" in val:
                continue
            try:
                dt = datetime.strptime(val, "%B %Y")
                months[c] = dt.strftime("%Y-%m-01")
            except ValueError:
                continue
        return months

    @staticmethod
    def _detect_casino_row(ws, row: int) -> str | None:
        """Check if this row is a casino name header.

        Casino name rows have text in col A and no numeric data in other columns.
        The next row should say 'Total Sports Wagering'.
        """
        val = ws.cell(row=row, column=1).value
        if not val:
            return None

        name = str(val).strip()
        if not name:
            return None

        # Skip known metric/section labels
        lower = name.lower()
        if any(kw in lower for kw in [
            "handle", "revenue", "promotional", "gross revenue", "state tax",
            "local share", "total sports", "retail sports", "online sports",
            "monthly", "footnote", "*sport",
        ]):
            return None

        # Verify next row says "Total Sports Wagering"
        next_val = ws.cell(row=row + 1, column=1).value
        if next_val and "Total Sports Wagering" in str(next_val):
            return name

        return None

    def _parse_casino_block(
        self, ws, name_row: int, casino_name: str, months: dict[int, str]
    ) -> list[dict]:
        """Parse the Total Sports Wagering section of a casino block."""
        handle_row = None
        ggr_row = None
        tax_row = None
        local_row = None

        # Scan rows after casino name, stopping at "Retail Sports Wagering"
        for r in range(name_row + 2, min(name_row + 10, ws.max_row + 1)):
            label = str(ws.cell(row=r, column=1).value or "").strip()
            if label.startswith("Handle"):
                handle_row = r
            elif label.startswith("Gross Revenue"):
                ggr_row = r
            elif label.startswith("State Tax"):
                tax_row = r
            elif label.startswith("Local Share"):
                local_row = r
            elif "Retail Sports Wagering" in label:
                break

        if not handle_row:
            return []

        brand = self._map_casino(casino_name)
        records = []

        for col, date_str in months.items():
            handle_val = ws.cell(row=handle_row, column=col).value
            if not isinstance(handle_val, (int, float)) or handle_val == 0:
                continue

            ggr_val = ws.cell(row=ggr_row, column=col).value if ggr_row else 0
            tax_val = ws.cell(row=tax_row, column=col).value if tax_row else 0
            local_val = ws.cell(row=local_row, column=col).value if local_row else 0

            ggr = float(ggr_val) if isinstance(ggr_val, (int, float)) else 0.0
            state_tax = float(tax_val) if isinstance(tax_val, (int, float)) else 0.0
            local_tax = float(local_val) if isinstance(local_val, (int, float)) else 0.0

            records.append({
                "brand": brand,
                "date": date_str,
                "handle": float(handle_val),
                "ggr": ggr,
                "tax": state_tax + local_tax,
            })

        return records

    # ── Casino → brand mapping ────────────────────────────────────

    @staticmethod
    def _map_casino(casino_name: str) -> str:
        """Map casino license holder name to consumer-facing brand."""
        name = casino_name.strip().upper()

        # Remove common suffixes for matching
        for suffix in [" (FORMERLY SUGARHOUSE)", " CASINO RESORT"]:
            name = name.replace(suffix, "")

        # Exact match first
        for key, brand in CASINO_TO_BRAND.items():
            if name == key.upper():
                return brand

        # Partial match (for name variations across years)
        for key, brand in CASINO_TO_BRAND.items():
            if key.upper() in name or name in key.upper():
                return brand

        return "Others"
