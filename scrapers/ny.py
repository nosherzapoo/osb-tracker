"""New York sports betting scraper — gaming.ny.gov weekly + monthly operator-level data.

Weekly Excel reports per operator: handle + GGR per week.
Monthly Excel reports per operator: handle, GGR, tax (Net Revenue to Education)
per month, organized by fiscal year sheets (FY starts April).

Weekly is the primary frequency; monthly data stored as *_monthly.csv files.
"""

import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from openpyxl import load_workbook

from .base import BaseScraper, ScraperResult
from .utils import get_session, clean_dollar_value, parse_date_flex, download_file

DOWNLOADS_DIR = Path("downloads")

WEEKLY_LINKS = {
    "fanduel": "/fanduel-weekly-report-excel",
    "draftkings": "/draftkings-sport-book-weekly-report-excel",
    "betmgm": "/betmgm-weekly-report-excel",
    "caesars": "/caesars-sport-book-weekly-report-excel",
    "wynn-interactive": "/wynn-interactive-weekly-report-excel",
    "ballybet": "/ballybet-weekly-report-excel",
    "fanatics": "/fanatics-weekly-report-excel",
    "resorts-world-bet": "/resorts-world-bet-weekly-report-excel",
    "rush-street-interactive": "/rush-street-interactive-weekly-report-excel",
}

MONTHLY_LINKS = {
    "fanduel": "/fanduel-monthly-report-excel",
    "draftkings": "/draftkings-sport-book-monthly-report-excel",
    "betmgm": "/betmgm-monthly-report-excel",
    "caesars": "/caesars-sport-book-monthly-report-excel",
    "wynn-interactive": "/wynn-interactive-monthly-report-excel",
    "ballybet": "/ballybet-monthly-report-excel",
    "fanatics": "/fanatics-monthly-report-excel",
    "resorts-world-bet": "/resorts-world-bet-monthly-report-excel",
    "rush-street-interactive": "/rush-street-interactive-monthly-report-excel",
}

NAME_MAP = {
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
    "betmgm": "BetMGM",
    "caesars": "Caesars",
    "wynn-interactive": "ESPN Bet",
    "ballybet": "Bally Bet",
    "fanatics": "Fanatics",
    "resorts-world-bet": "Resorts World Bet",
    "rush-street-interactive": "Rush Street Interactive",
}

BASE_URL = "https://gaming.ny.gov"


class NYScraper(BaseScraper):
    STATE_CODE = "ny"
    STATE_NAME = "New York"
    TAX_RATE = 0.51
    TAX_RATE_NOTE = "Flat 51% on GGR"
    FREQUENCY = "weekly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = "https://gaming.ny.gov/revenue-reports"
    DATE_COLUMN = "Week Ending"
    LAUNCH_DATE = "2022-01-08"
    GGR_DEFINITION = "Gross Gaming Revenue as reported per operator (Handle − Payouts); no promo deductions allowed"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._monthly_tax_cache = {}  # date -> {operator: tax_amount}

    def scrape(self) -> dict[str, pd.DataFrame]:
        """Scrape weekly operator Excel reports (primary frequency)."""
        DOWNLOADS_DIR.mkdir(exist_ok=True)
        session = get_session()
        all_data = {}

        for slug, link_path in WEEKLY_LINKS.items():
            display_name = NAME_MAP.get(slug, slug)
            print(f"  Downloading {display_name} weekly...")

            xlsx_url = self._find_xlsx_url(session, BASE_URL + link_path)
            if not xlsx_url:
                print(f"    Could not find download URL, skipping.")
                continue

            dest = DOWNLOADS_DIR / f"{slug}_weekly.xlsx"
            if not download_file(session, xlsx_url, dest):
                print(f"    Failed to download, skipping.")
                continue

            try:
                df = self._parse_weekly_xlsx(dest)
                if df.empty:
                    print(f"    No data found.")
                else:
                    print(f"    Parsed {len(df)} weeks")
                    all_data[display_name] = df
            except Exception as e:
                print(f"    Error parsing: {e}")

        shutil.rmtree(DOWNLOADS_DIR, ignore_errors=True)
        return all_data

    def run(self) -> "ScraperResult":
        """Override to also scrape monthly data and write monthly CSVs."""
        # Weekly (primary)
        raw = self.scrape()
        if not raw:
            print(f"  No weekly data scraped for {self.STATE_NAME}")
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
        tax_revenue = ggr_pivot * self.TAX_RATE
        self.write_csvs(handle_pivot, ggr_pivot, hold_pivot, yoy_handle, yoy_ggr, tax_revenue)

        # Monthly (supplemental)
        has_monthly = False
        monthly_raw = self._scrape_monthly()
        if monthly_raw:
            has_monthly = True
            self._write_monthly_csvs(monthly_raw)

        metadata = self.build_metadata(handle_pivot, ggr_pivot)
        metadata["hasMonthlyData"] = has_monthly

        return ScraperResult(
            state_code=self.STATE_CODE, state_name=self.STATE_NAME,
            handle_pivot=handle_pivot, ggr_pivot=ggr_pivot,
            hold_pivot=hold_pivot, yoy_handle=yoy_handle,
            yoy_ggr=yoy_ggr, tax_revenue=tax_revenue,
            metadata=metadata,
        )

    # ── Monthly scraping ───────────────────────────────────────────

    def _scrape_monthly(self) -> dict[str, pd.DataFrame]:
        """Scrape monthly operator Excel reports. Returns {operator: DataFrame}."""
        DOWNLOADS_DIR.mkdir(exist_ok=True)
        session = get_session()
        all_data = {}

        for slug, link_path in MONTHLY_LINKS.items():
            display_name = NAME_MAP.get(slug, slug)
            print(f"  Downloading {display_name} monthly...")

            xlsx_url = self._find_xlsx_url(session, BASE_URL + link_path)
            if not xlsx_url:
                print(f"    Could not find download URL, skipping.")
                continue

            dest = DOWNLOADS_DIR / f"{slug}_monthly.xlsx"
            if not download_file(session, xlsx_url, dest):
                print(f"    Failed to download, skipping.")
                continue

            try:
                df = self._parse_monthly_xlsx(dest, display_name)
                if df.empty:
                    print(f"    No monthly data found.")
                else:
                    print(f"    Parsed {len(df)} months")
                    all_data[display_name] = df
            except Exception as e:
                print(f"    Error parsing monthly: {e}")

        shutil.rmtree(DOWNLOADS_DIR, ignore_errors=True)
        if all_data:
            print(f"  Monthly: {len(all_data)} operators, "
                  f"{sum(len(df) for df in all_data.values())} total month-operator rows.")
        return all_data

    def _parse_monthly_xlsx(self, filepath: Path, operator: str) -> pd.DataFrame:
        """Parse a monthly operator Excel with fiscal year sheets.

        Each sheet has: Month | (blank) | Handle | GGR | (blank) | Net Revenue
        to Platform Provider | [Unclaimed Funds] | Adjustments/Fines | Net Revenue
        to Education.
        """
        wb = load_workbook(filepath, read_only=True, data_only=True)
        all_rows = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue

            # Find header row (contains "Month" and "Handle")
            header_idx = None
            for i, row in enumerate(rows):
                row_strs = [str(c).lower().strip() if c else "" for c in row]
                if "month" in row_strs and any("handle" in s for s in row_strs):
                    header_idx = i
                    break
            if header_idx is None:
                continue

            header = rows[header_idx]

            # Find column indices
            date_col = handle_col = ggr_col = tax_col = None
            for j, cell in enumerate(header):
                if cell is None:
                    continue
                cell_str = str(cell).lower().strip()
                if cell_str == "month":
                    date_col = j
                elif "handle" in cell_str:
                    handle_col = j
                elif "ggr" in cell_str:
                    ggr_col = j
                elif "to education" in cell_str:
                    tax_col = j

            if date_col is None or handle_col is None or ggr_col is None:
                continue

            for row in rows[header_idx + 1:]:
                if len(row) <= max(date_col, handle_col, ggr_col):
                    continue

                date_val = row[date_col]
                if date_val is None:
                    continue
                date_str = str(date_val).lower().strip()
                if date_str.startswith("total") or date_str.startswith("fiscal") or not date_str:
                    continue

                # Parse date — normalize to first of month
                if isinstance(date_val, datetime):
                    month_date = date_val.replace(day=1)
                else:
                    parsed = parse_date_flex(date_val)
                    if parsed is None:
                        continue
                    month_date = pd.Timestamp(parsed).replace(day=1)

                handle = clean_dollar_value(row[handle_col])
                ggr = clean_dollar_value(row[ggr_col])
                if handle is None and ggr is None:
                    continue

                # Extract tax (Net Revenue to Education)
                tax = None
                if tax_col is not None and tax_col < len(row):
                    tax = clean_dollar_value(row[tax_col])

                date_key = month_date.strftime("%Y-%m-%d")
                if tax is not None:
                    if date_key not in self._monthly_tax_cache:
                        self._monthly_tax_cache[date_key] = {}
                    self._monthly_tax_cache[date_key][operator] = tax

                all_rows.append({
                    "date": month_date,
                    "handle": handle or 0.0,
                    "ggr": ggr or 0.0,
                })

        wb.close()

        if not all_rows:
            return pd.DataFrame(columns=["date", "handle", "ggr"])

        df = pd.DataFrame(all_rows)
        df["date"] = pd.to_datetime(df["date"])
        # Combine duplicate months (e.g. ESPN Bet has two FY 24-25 sheets)
        df = df.groupby("date", as_index=False).sum()
        df = df.sort_values("date").reset_index(drop=True)
        return df

    def _write_monthly_csvs(self, monthly_raw: dict[str, pd.DataFrame]):
        """Write monthly pivot CSVs with _monthly suffix."""
        handle_pivot = self.build_pivot(monthly_raw, "handle")
        ggr_pivot = self.build_pivot(monthly_raw, "ggr")
        hold_pivot = self.build_hold_pct(handle_pivot, ggr_pivot)

        # YoY with monthly lookback
        orig_freq = self.FREQUENCY
        self.FREQUENCY = "monthly"
        yoy_handle = self.build_yoy_change(handle_pivot)
        yoy_ggr = self.build_yoy_change(ggr_pivot)
        self.FREQUENCY = orig_freq

        # Actual tax from reports
        tax = self._build_monthly_tax(handle_pivot)

        # Set index name to "Month"
        for frame in [handle_pivot, ggr_pivot, hold_pivot, yoy_handle, yoy_ggr, tax]:
            frame.index.name = "Month"

        for name, frame in [
            ("handle_monthly", handle_pivot), ("ggr_monthly", ggr_pivot),
            ("hold_pct_monthly", hold_pivot), ("yoy_handle_monthly", yoy_handle),
            ("yoy_ggr_monthly", yoy_ggr), ("tax_revenue_monthly", tax),
        ]:
            path = self.state_dir / f"{name}.csv"
            frame.to_csv(path, index=True, date_format="%Y-%m-%d")

        print(f"  Wrote 6 monthly CSVs to {self.state_dir}/ "
              f"({len(handle_pivot)} months, {len(monthly_raw)} operators)")

    def _build_monthly_tax(self, handle_pivot: pd.DataFrame) -> pd.DataFrame:
        """Build tax revenue from actual 'Net Revenue to Education' values."""
        tax = pd.DataFrame(index=handle_pivot.index, columns=handle_pivot.columns, dtype=float)
        tax.index.name = "Month"

        for dt in tax.index:
            date_str = dt.strftime("%Y-%m-%d")
            if date_str not in self._monthly_tax_cache:
                continue
            tax_map = self._monthly_tax_cache[date_str]
            for op_name, tax_val in tax_map.items():
                if op_name in tax.columns:
                    tax.loc[dt, op_name] = tax_val
            tax.loc[dt, "Total"] = sum(tax_map.values())

        return tax

    # ── Weekly parsing ─────────────────────────────────────────────

    def _find_xlsx_url(self, session, page_url) -> str | None:
        try:
            resp = session.get(page_url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            print(f"    Error fetching {page_url}: {e}")
            return None

        content_type = resp.headers.get("Content-Type", "")
        if "spreadsheet" in content_type or "octet-stream" in content_type:
            return resp.url

        soup = BeautifulSoup(resp.text, "lxml")
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href.endswith(".xlsx"):
                return href if href.startswith("http") else BASE_URL + href

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if "system/files" in href:
                return href if href.startswith("http") else BASE_URL + href

        return None

    def _parse_weekly_xlsx(self, filepath: Path) -> pd.DataFrame:
        """Parse a weekly operator Excel report."""
        wb = load_workbook(filepath, read_only=True, data_only=True)
        all_rows = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue

            header_idx = None
            for i, row in enumerate(rows):
                row_strs = [str(c).lower().strip() if c else "" for c in row]
                if any("week" in s for s in row_strs):
                    header_idx = i
                    break
            if header_idx is None:
                header_idx = 0

            header = rows[header_idx]
            date_col = handle_col = ggr_col = None
            for j, cell in enumerate(header):
                if cell is None:
                    continue
                cell_str = str(cell).lower().strip()
                if "week" in cell_str or "date" in cell_str:
                    date_col = j
                elif "handle" in cell_str:
                    handle_col = j
                elif "ggr" in cell_str or "gross" in cell_str or "revenue" in cell_str:
                    ggr_col = j
            date_col = date_col if date_col is not None else 0
            handle_col = handle_col if handle_col is not None else 1
            ggr_col = ggr_col if ggr_col is not None else 2

            for row in rows[header_idx + 1:]:
                if len(row) <= max(date_col, handle_col, ggr_col):
                    continue
                date_val = row[date_col]
                if date_val is not None and "total" in str(date_val).lower():
                    continue
                if date_val is None:
                    continue

                week_ending = parse_date_flex(date_val)
                if week_ending is None:
                    continue

                handle = clean_dollar_value(row[handle_col])
                ggr = clean_dollar_value(row[ggr_col])
                if handle is None and ggr is None:
                    continue

                all_rows.append({"date": week_ending, "handle": handle, "ggr": ggr})

        wb.close()

        if not all_rows:
            return pd.DataFrame(columns=["date", "handle", "ggr"])

        df = pd.DataFrame(all_rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.drop_duplicates(subset=["date"], keep="first")
        df = df.sort_values("date").reset_index(drop=True)
        return df
