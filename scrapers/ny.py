"""New York sports betting scraper — gaming.ny.gov weekly operator-level data."""

import shutil
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from openpyxl import load_workbook

from .base import BaseScraper
from .utils import get_session, clean_dollar_value, parse_date_flex, download_file

DOWNLOADS_DIR = Path("downloads")

SPORTSBOOK_LINKS = {
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

    def scrape(self) -> dict[str, pd.DataFrame]:
        DOWNLOADS_DIR.mkdir(exist_ok=True)
        session = get_session()
        all_data = {}

        for slug, link_path in SPORTSBOOK_LINKS.items():
            display_name = NAME_MAP.get(slug, slug)
            print(f"  Downloading {display_name}...")

            xlsx_url = self._find_xlsx_url(session, BASE_URL + link_path)
            if not xlsx_url:
                print(f"    Could not find download URL, skipping.")
                continue

            dest = DOWNLOADS_DIR / f"{slug}.xlsx"
            if not download_file(session, xlsx_url, dest):
                print(f"    Failed to download, skipping.")
                continue

            try:
                df = self._parse_xlsx(dest)
                if df.empty:
                    print(f"    No data found.")
                else:
                    print(f"    Parsed {len(df)} weeks")
                    all_data[display_name] = df
            except Exception as e:
                print(f"    Error parsing: {e}")

        # Cleanup downloads
        shutil.rmtree(DOWNLOADS_DIR, ignore_errors=True)
        return all_data

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

    def _parse_xlsx(self, filepath: Path) -> pd.DataFrame:
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
