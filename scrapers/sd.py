"""South Dakota sports betting scraper — SD Commission on Gaming monthly PDFs.

Downloads monthly Gaming Statistics PDFs from the SD Department of Revenue.
Page 1 has summary totals for Sports Wagering (Handle, Statistical Win).
Page 2 has Sports Wagering Detail with sport-by-sport breakdown.

SD sports wagering is retail-only (no online), operated through ~7 casinos
in Deadwood. Monthly PDF reports available from January 2023.

GGR = Statistical Win = Handle − Payouts.
Tax: 9% on adjusted gross revenue (all gaming categories combined).
"""

import io
import re
from collections import defaultdict

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper
from .utils import clean_dollar_value

PAGE_URL = "https://dor.sd.gov/businesses/gaming/"
BASE_URL = "https://dor.sd.gov"

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Map PDF sport names → canonical sport names for the dashboard
# Keys are UPPERCASE for case-insensitive matching
SPORT_MAP = {
    "NFL": "NFL",
    "NBA": "NBA",
    "WNBA": "NBA",
    "MLB": "MLB",
    "NHL": "NHL",
    "NCAA FB": "NCAAF",
    "NCAA MENS BB": "NCAAB",
    "NCAA WOMENS BB": "NCAAB",
    "NCAA BASEBALL": "MLB",
    "NCAA HOCKEY": "NHL",
    "MMA/UFC": "MMA",
    "BOXING": "Boxing",
    "PGA": "Golf",
    "SOCCER": "Soccer",
    "MLS": "Soccer",
    "TENNIS": "Tennis",
    "NASCAR": "Motorsports",
    "FORMULA 1": "Motorsports",
    "INDYCAR": "Motorsports",
    "INDY CAR": "Motorsports",
    "CFL": "NFL",
    "USFL": "NFL",
    "OLYMPICS": "Olympics",
    "LPGA": "Golf",
    "RUGBY": "Rugby",
}


class SDScraper(BaseScraper):
    STATE_CODE = "sd"
    STATE_NAME = "South Dakota"
    TAX_RATE = 0.09
    TAX_RATE_NOTE = "9% on adjusted gross revenue (all gaming combined)"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = False
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2021-09-01"
    GGR_DEFINITION = "Statistical Win (Handle − Payouts)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sports_data = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        pdf_urls = self._find_pdf_urls()
        if not pdf_urls:
            print("  No monthly PDF URLs found.")
            return {}

        print(f"  Found {len(pdf_urls)} monthly PDFs.")

        totals = []
        sports_by_type = defaultdict(list)
        success = 0

        for url, date_str in pdf_urls:
            try:
                resp = requests.get(url, timeout=60)
                if resp.status_code != 200:
                    continue

                result = self._parse_pdf(resp.content, date_str)
                if result is None:
                    continue

                handle, ggr, sports = result
                totals.append({"date": date_str, "handle": handle, "ggr": ggr})
                success += 1

                for sport, sport_handle in sports.items():
                    sports_by_type[sport].append({
                        "date": date_str, "handle": sport_handle,
                    })
            except Exception as e:
                print(f"    Error {date_str}: {e}")

        print(f"  Parsed {success}/{len(pdf_urls)} reports.")

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
        df = df.sort_values("date").drop_duplicates(subset="date", keep="last")

        print(f"  Total: {len(df)} months, "
              f"${df['handle'].iloc[-1]:,.0f} handle latest, "
              f"{len(sports_by_type)} sports tracked")

        return {"total": df[["date", "handle", "ggr"]].reset_index(drop=True)}

    def scrape_sports(self) -> dict[str, pd.DataFrame] | None:
        return self._sports_data

    # ── URL discovery ─────────────────────────────────────────────

    def _find_pdf_urls(self) -> list[tuple[str, str]]:
        """Find monthly gaming stats PDF links from the gaming page.

        Returns list of (url, date_str) tuples sorted by date.
        Link text is like "December 2025", "January 2023".
        """
        try:
            resp = requests.get(PAGE_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  Error fetching page: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        urls = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)

            # Only PDFs in /media/ paths
            if "/media/" not in href or ".pdf" not in href.lower():
                continue

            # Match "MonthName Year" pattern (e.g., "December 2025")
            match = re.match(
                r"^(january|february|march|april|may|june|july|august|"
                r"september|october|november|december)\s+(\d{4})$",
                text, re.IGNORECASE,
            )
            if not match:
                continue

            month_name = match.group(1).lower()
            year = int(match.group(2))
            month_num = MONTH_NAMES[month_name]
            date_str = f"{year}-{month_num:02d}-01"

            full_url = href if href.startswith("http") else BASE_URL + href
            urls.append((full_url, date_str))

        return sorted(urls, key=lambda x: x[1])

    # ── PDF parsing ───────────────────────────────────────────────

    @staticmethod
    def _parse_pdf(
        pdf_bytes: bytes, date_str: str,
    ) -> tuple[float, float, dict[str, float]] | None:
        """Parse a monthly gaming stats PDF.

        Returns (handle, ggr, sports_dict) or None.
        Page 1: Sports Wagering summary totals.
        Page 2: Sports Wagering Detail by sport.
        """
        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception:
            return None

        handle = None
        ggr = None
        sports = {}

        # Page 1: Extract Sports Wagering totals
        if len(pdf.pages) >= 1:
            text = pdf.pages[0].extract_text() or ""
            handle, ggr = SDScraper._parse_page1_totals(text)

        # Page 2: Extract Sports Wagering Detail
        if len(pdf.pages) >= 2:
            text = pdf.pages[1].extract_text() or ""
            sports = SDScraper._parse_page2_sports(text)

        if handle is None:
            return None

        return handle, ggr or 0.0, sports

    @staticmethod
    def _parse_page1_totals(text: str) -> tuple[float | None, float | None]:
        """Extract Sports Wagering totals from page 1.

        Looks for section "Sports Wagering" followed by a "Totals" line:
        Totals {N} ${handle} ${ggr} {pct}%
        """
        lines = text.split("\n")
        in_sports_section = False

        for line in lines:
            if "Sports Wagering" in line and "Detail" not in line:
                in_sports_section = True
                continue

            if in_sports_section and line.strip().startswith("Totals"):
                # Extract dollar amounts from the Totals line
                amounts = re.findall(
                    r"\$\(?([\d,]+\.?\d*)\)?", line,
                )
                if len(amounts) >= 2:
                    handle = float(amounts[0].replace(",", ""))
                    ggr_str = amounts[1].replace(",", "")
                    ggr = float(ggr_str)

                    # Check for negative GGR (parenthesized)
                    if "(" in line and ")" in line:
                        # Find position of second dollar amount
                        second_dollar = line.find("$", line.find("$") + 1)
                        if second_dollar >= 0:
                            after = line[second_dollar:]
                            if "(" in after.split("%")[0]:
                                ggr = -ggr

                    return handle, ggr

                # If the line has Handle as non-dollar format
                break

        return None, None

    @staticmethod
    def _parse_page2_sports(text: str) -> dict[str, float]:
        """Extract sport-by-sport handle from Sports Wagering Detail (page 2).

        Each line: {SPORT_NAME} ${handle} ${stat_win} {pct}%
        """
        sports = defaultdict(float)
        lines = text.split("\n")
        in_detail = False

        for line in lines:
            if "Sports Wagering Detail" in line:
                in_detail = True
                continue

            if not in_detail:
                continue

            # Skip header lines
            if "Sporting Event" in line or "Handle" in line:
                continue

            # Stop at Totals line
            if line.strip().startswith("Totals"):
                break

            # Parse sport row: SPORT_NAME followed by dollar amounts
            # Handle negative values in parentheses
            line = line.strip()
            if not line:
                continue

            # Extract amounts (including negative in parens)
            amounts = re.findall(
                r"\$\(?([\d,]+\.?\d*)\)?|\(\$([\d,]+\.?\d*)\)", line,
            )
            if not amounts:
                continue

            # Sport name is everything before the first $ or (
            name_end = line.find("$")
            if name_end < 0:
                name_end = line.find("(")
            if name_end < 0:
                continue

            sport_name = line[:name_end].strip()
            if not sport_name:
                continue

            # First amount is handle
            handle_str = amounts[0][0] or amounts[0][1]
            if not handle_str:
                continue
            handle_val = float(handle_str.replace(",", ""))
            if handle_val == 0:
                continue

            # Map to canonical sport name (case-insensitive)
            canonical = SPORT_MAP.get(sport_name.upper(), sport_name)
            sports[canonical] += handle_val

        return dict(sports)
