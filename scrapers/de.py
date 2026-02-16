"""Delaware sports betting scraper — delottery.com sportsbook monthly data.

Delaware Lottery operates sports betting through three casino sportsbooks
(Delaware Park, Bally's Dover, Harrington) plus retail sports lottery locations.

Data sources:
  FY 2023–2026: Monthly Proceeds & Distribution pages (full data: handle, GGR, tax)
    /Sports-Lottery/Sportsbooks/Monthly-Proceeds-And-Distribution-Financial-Year/{year}
  2018–2022: Track Data pages (handle + net proceeds per operator)
    /Sports-Lottery/Sportsbooks/Track-Data/{year}

Sportsbook operators: Delaware Park, Bally's Dover (fka Dover Downs),
Harrington (fka Harrington Raceway), Retailers (online/retail sports lottery).

Key metrics:
  Handle = Sports Sales (FY pages) / Amount Played (Track Data)
  GGR = Net Proceeds (handle minus payouts minus vendor fees)
  Tax = State Share (~50% of Net Proceeds)

Full-scale sports betting started June 5, 2018.
"""

import re
from collections import defaultdict
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper, ScraperResult
from .utils import clean_dollar_value

BASE_URL = "https://www.delottery.com"

# Canonical operator names
OPERATOR_MAP = {
    "delaware park": "Delaware Park",
    "bally's dover": "Bally's Dover",
    "bally\u2019s dover": "Bally's Dover",
    "dover downs": "Bally's Dover",
    "harrington": "Harrington",
    "harrington raceway": "Harrington",
    "retailers": "Retailers",
}

# FY pages (Jul–Jun fiscal years)
FY_PAGES = {
    2023: "/Sports-Lottery/Sportsbooks/Monthly-Proceeds-And-Distribution-Financial-Year/2023",
    2024: "/Sports-Lottery/Sportsbooks/Monthly-Proceeds-And-Distribution-Financial-Year/2024",
    2025: "/Sports-Lottery/Sportsbooks/Monthly-Proceeds-And-Distribution-Financial-Year/2025",
    2026: "/Sports-Lottery/Sportsbooks/Monthly-Proceeds-And-Distribution-Financial-Year/2026",
}

# Track Data pages (calendar years, pre-FY format)
TRACK_DATA_PAGES = {
    2018: "/Sports-Lottery/Sportsbooks/Track-Data/2018",
    2019: "/Sports-Lottery/Sportsbooks/Track-Data/2019",
    2020: "/Sports-Lottery/Sportsbooks/Track-Data/2020",
    2021: "/Sports-Lottery/Sportsbooks/Track-Data/2021",
    2022: "/Sports-Lottery/Sportsbooks/Track-Data/2022",
}

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


class DEScraper(BaseScraper):
    STATE_CODE = "de"
    STATE_NAME = "Delaware"
    TAX_RATE = 0.50
    TAX_RATE_NOTE = "~50% of net proceeds (State Share); before operating expenses"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = "https://www.delottery.com/Sports-Lottery/Monthly-Net-Proceeds"
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2018-06-01"
    GGR_DEFINITION = "Net Proceeds (Sports Sales minus Amount Won minus Vendor Fees)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tax_cache = {}  # date_str -> {operator: tax_amount}

    def scrape(self) -> dict[str, pd.DataFrame]:
        """Scrape all sportsbook data from FY pages and Track Data pages."""
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

        all_records = defaultdict(list)  # operator -> [{date, handle, ggr}]

        # Track Data pages (2018-2022) — handle + net proceeds per operator
        for year, path in sorted(TRACK_DATA_PAGES.items()):
            records = _parse_track_data_page(session, f"{BASE_URL}{path}")
            for op, date_str, handle, ggr in records:
                all_records[op].append({"date": date_str, "handle": handle, "ggr": ggr})
                # Tax = 50% of net proceeds for track data periods
                if date_str not in self._tax_cache:
                    self._tax_cache[date_str] = {}
                self._tax_cache[date_str][op] = ggr * 0.50
            if records:
                print(f"  Track Data {year}: {len(records)} operator-months")

        # FY pages (2023-2026) — full data with actual State Share
        for fy, path in sorted(FY_PAGES.items()):
            records = _parse_fy_page(session, f"{BASE_URL}{path}")
            for op, date_str, handle, ggr, tax in records:
                all_records[op].append({"date": date_str, "handle": handle, "ggr": ggr})
                if tax is not None:
                    if date_str not in self._tax_cache:
                        self._tax_cache[date_str] = {}
                    self._tax_cache[date_str][op] = tax
            if records:
                print(f"  FY {fy}: {len(records)} operator-months")

        if not all_records:
            print("  No data found.")
            return {}

        result = {}
        for op_name, records in all_records.items():
            df = pd.DataFrame(records)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").drop_duplicates(subset="date", keep="last")
            result[op_name] = df

        total_months = max(len(df) for df in result.values()) if result else 0
        print(f"  {len(result)} operators, {total_months} months max.")
        return result

    def run(self) -> "ScraperResult":
        """Override to use actual tax values from reports."""
        raw = self.scrape()
        if not raw:
            print(f"  No data scraped for {self.STATE_NAME}")
            return ScraperResult(
                state_code=self.STATE_CODE, state_name=self.STATE_NAME,
                handle_pivot=pd.DataFrame(), ggr_pivot=pd.DataFrame(),
                hold_pivot=pd.DataFrame(), yoy_handle=pd.DataFrame(),
                yoy_ggr=pd.DataFrame(), tax_revenue=pd.DataFrame(),
            )

        handle_pivot = self.build_pivot(raw, "handle")
        ggr_pivot = self.build_pivot(raw, "ggr")
        hold_pivot = self.build_hold_pct(handle_pivot, ggr_pivot)
        yoy_handle = self.build_yoy_change(handle_pivot)
        yoy_ggr = self.build_yoy_change(ggr_pivot)
        tax_revenue = self._build_actual_tax(handle_pivot)
        self.write_csvs(handle_pivot, ggr_pivot, hold_pivot, yoy_handle, yoy_ggr, tax_revenue)

        metadata = self.build_metadata(handle_pivot, ggr_pivot)
        # Fix latestData.taxRevenue with actual value
        latest_date = handle_pivot.index.max().strftime("%Y-%m-%d")
        if latest_date in self._tax_cache:
            actual_total = sum(self._tax_cache[latest_date].values())
            metadata["latestData"]["taxRevenue"] = round(actual_total, 2)

        return ScraperResult(
            state_code=self.STATE_CODE, state_name=self.STATE_NAME,
            handle_pivot=handle_pivot, ggr_pivot=ggr_pivot,
            hold_pivot=hold_pivot, yoy_handle=yoy_handle,
            yoy_ggr=yoy_ggr, tax_revenue=tax_revenue,
            metadata=metadata,
        )

    def _build_actual_tax(self, handle_pivot: pd.DataFrame) -> pd.DataFrame:
        """Build tax revenue from actual State Share values."""
        tax = pd.DataFrame(index=handle_pivot.index, columns=handle_pivot.columns, dtype=float)
        tax.index.name = self.DATE_COLUMN

        for dt in tax.index:
            date_str = dt.strftime("%Y-%m-%d")
            if date_str not in self._tax_cache:
                continue
            tax_map = self._tax_cache[date_str]
            for op_name, tax_val in tax_map.items():
                if op_name in tax.columns:
                    tax.loc[dt, op_name] = tax_val
            tax.loc[dt, "Total"] = sum(tax_map.values())

        return tax


# ── Page parsing (module-level) ─────────────────────────────────────

def _parse_fy_page(
    session: requests.Session, url: str,
) -> list[tuple[str, str, float, float, float | None]]:
    """Parse a FY page. Returns [(operator, date_str, handle, ggr, tax), ...]."""
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            return []
    except requests.RequestException:
        return []

    soup = BeautifulSoup(r.text, "lxml")
    tables = soup.find_all("table")
    if not tables:
        return []

    table = tables[0]
    rows = table.find_all("tr")
    if not rows:
        return []

    # Parse header to find operator columns
    header_cells = rows[0].find_all(["th", "td"])
    header = [c.get_text(strip=True).lower() for c in header_cells]

    # Map column index -> canonical operator name
    op_columns = {}
    for idx, h in enumerate(header):
        if not h:
            continue
        canonical = OPERATOR_MAP.get(h)
        if canonical:
            op_columns[idx] = canonical

    if not op_columns:
        return []

    # Parse data rows in blocks (each period = ~9 rows)
    results = []
    current_date = None

    for row in rows[1:]:
        cells = row.find_all(["th", "td"])
        texts = [c.get_text(strip=True) for c in cells]

        if not any(texts):
            continue

        # Check if first cell has a date
        first = texts[0] if texts else ""
        if first and not first.lower().startswith("fiscal") and not first.lower().startswith("total"):
            parsed_date = _parse_period_date(first)
            if parsed_date:
                current_date = parsed_date

        if current_date is None:
            continue

        # Skip fiscal year totals
        if first.lower().startswith("fiscal") or first.lower().startswith("total"):
            current_date = None
            continue

        # Identify metric type
        metric = texts[1].lower() if len(texts) > 1 else ""

        if "sports sales" in metric or "amount played" in metric:
            for idx, op in op_columns.items():
                if idx < len(texts):
                    val = clean_dollar_value(texts[idx])
                    if val is not None:
                        _upsert_record(results, op, current_date, handle=val)

        elif "net proceeds" in metric:
            for idx, op in op_columns.items():
                if idx < len(texts):
                    val = clean_dollar_value(texts[idx])
                    if val is not None:
                        _upsert_record(results, op, current_date, ggr=val)

        elif "state share" in metric:
            for idx, op in op_columns.items():
                if idx < len(texts):
                    val = clean_dollar_value(texts[idx])
                    if val is not None:
                        _upsert_record(results, op, current_date, tax=val)

    return results


def _parse_track_data_page(
    session: requests.Session, url: str,
) -> list[tuple[str, str, float, float]]:
    """Parse a Track Data page. Returns [(operator, date_str, handle, ggr), ...]."""
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            return []
    except requests.RequestException:
        return []

    soup = BeautifulSoup(r.text, "lxml")
    tables = soup.find_all("table")
    if not tables:
        return []

    # Track Data pages may have multiple tables; parse all
    all_results = []

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Find header to get operator columns
        op_columns = {}
        for row in rows[:3]:
            cells = row.find_all(["th", "td"])
            texts = [c.get_text(strip=True).lower() for c in cells]
            for idx, h in enumerate(texts):
                if not h:
                    continue
                canonical = OPERATOR_MAP.get(h)
                if canonical:
                    op_columns[idx] = canonical

        if not op_columns:
            continue

        current_date = None

        for row in rows:
            cells = row.find_all(["th", "td"])
            texts = [c.get_text(strip=True) for c in cells]

            if not any(texts):
                continue

            first = texts[0] if texts else ""

            # Check for date in first cell
            if first and not first.lower().startswith("calendar") and not first.lower().startswith("month"):
                parsed = _parse_period_date(first)
                if parsed:
                    current_date = parsed

            if current_date is None:
                continue

            # Skip calendar year totals
            if first.lower().startswith("calendar"):
                current_date = None
                continue

            # Find metric label (may be in any of the first few cells)
            metric = ""
            for t in texts[:4]:
                if "amount played" in t.lower():
                    metric = "handle"
                    break
                elif "net proceeds" in t.lower():
                    metric = "ggr"
                    break

            if metric == "handle":
                for idx, op in op_columns.items():
                    if idx < len(texts):
                        val = clean_dollar_value(texts[idx])
                        if val is not None:
                            _upsert_track(all_results, op, current_date, handle=val)
            elif metric == "ggr":
                for idx, op in op_columns.items():
                    if idx < len(texts):
                        val = clean_dollar_value(texts[idx])
                        if val is not None:
                            _upsert_track(all_results, op, current_date, ggr=val)

    # Convert accumulated data to flat list
    results = []
    for (op, date_str), data in all_results:
        if data.get("handle") is not None and data.get("ggr") is not None:
            results.append((op, date_str, data["handle"], data["ggr"]))

    return results


# ── Helpers ──────────────────────────────────────────────────────────

# Accumulator for FY page records: (op, date, handle, ggr, tax)
def _upsert_record(
    results: list, op: str, date_str: str,
    handle: float | None = None, ggr: float | None = None, tax: float | None = None,
):
    """Add or update a record in the results list."""
    for i, (o, d, h, g, t) in enumerate(results):
        if o == op and d == date_str:
            results[i] = (
                op, date_str,
                handle if handle is not None else h,
                ggr if ggr is not None else g,
                tax if tax is not None else t,
            )
            return
    results.append((op, date_str, handle or 0.0, ggr or 0.0, tax))


# Accumulator for Track Data records
_track_data = {}

def _upsert_track(
    results: list, op: str, date_str: str,
    handle: float | None = None, ggr: float | None = None,
):
    """Add or update a track data record."""
    key = (op, date_str)
    for i, (k, data) in enumerate(results):
        if k == key:
            if handle is not None:
                data["handle"] = handle
            if ggr is not None:
                data["ggr"] = ggr
            return
    data = {"handle": handle, "ggr": ggr}
    results.append((key, data))


def _parse_period_date(text: str) -> str | None:
    """Parse various date formats into YYYY-MM-01 string.

    Handles:
      "07/01/25 - 07/27/25" → use end date, normalize to first of month
      "07/28/25 - 08/31/25" → 2025-08-01
      "July 2024" → 2024-07-01
      "7/30/2023" → 2023-07-01
      "1/31/22" → 2022-01-01
      "6/24/18" → 2018-06-01
    """
    text = text.strip()
    if not text:
        return None

    # Date range: "MM/DD/YY - MM/DD/YY"
    range_match = re.match(
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})", text,
    )
    if range_match:
        end_str = range_match.group(2)
        return _parse_single_date(end_str)

    # "Month YYYY"
    month_year = re.match(r"^([a-zA-Z]+)\s+(\d{4})$", text)
    if month_year:
        month_name = month_year.group(1).lower()
        year = int(month_year.group(2))
        month_num = MONTH_NAMES.get(month_name)
        if month_num:
            return f"{year}-{month_num:02d}-01"
        return None

    # Single date: "M/DD/YYYY" or "M/DD/YY"
    return _parse_single_date(text)


def _parse_single_date(text: str) -> str | None:
    """Parse a single date string and normalize to first of month."""
    text = text.strip()

    # M/DD/YYYY or M/DD/YY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", text)
    if not m:
        return None

    month = int(m.group(1))
    year = int(m.group(3))
    if year < 100:
        year += 2000

    if 1 <= month <= 12:
        return f"{year}-{month:02d}-01"
    return None
