"""Rhode Island sports betting scraper — RI Lottery sportsbook PDFs.

Downloads FY sportsbook revenue PDFs from rilot.com financials page.
Each PDF has facility-level data (Twin River, Tiverton Casino, Online, Combined).
We parse the Combined column using word x-positions for robust number extraction
(the PDFs have layout artifacts that split numbers across column boundaries).

RI's sportsbook is state-operated through the RI Lottery (no private operators).
Revenue split: 51% state, 32.5% vendor (IGT), 16.5% facilities.

GGR = Book Revenue = Write (Handle) − Payouts.
Tax: 51% of book revenue to state.
Data from Nov 2018 (Twin River) through present. Online launched Sep 2019.
"""

import io
import re
from collections import defaultdict

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper

PAGE_URL = "https://www.rilot.com/en-us/about-us/financials.html"
BASE_URL = "https://www.rilot.com"

MONTH_ABBREVS = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}
MONTH_NUM = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
             "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}

# Word x-position gap threshold: fragments within a number have gap < 10,
# while separate numbers have gap >= 10. Calibrated across all FY PDFs.
GAP_THRESHOLD = 10


class RIScraper(BaseScraper):
    STATE_CODE = "ri"
    STATE_NAME = "Rhode Island"
    TAX_RATE = 0.51
    TAX_RATE_NOTE = "51% of book revenue to state (lottery-operated)"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = False
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2018-11-01"
    GGR_DEFINITION = "Book Revenue (Write − Payouts)"

    def scrape(self) -> dict[str, pd.DataFrame]:
        pdf_urls = self._find_pdf_urls()
        if not pdf_urls:
            print("  No PDF URLs found.")
            return {}

        print(f"  Found {len(pdf_urls)} FY PDFs.")

        all_records = []
        for url, fy_year in pdf_urls:
            try:
                resp = requests.get(url, timeout=60)
                if resp.status_code != 200:
                    print(f"    FY{fy_year}: HTTP {resp.status_code}")
                    continue

                records = self._parse_pdf(resp.content, fy_year)
                all_records.extend(records)
                print(f"    FY{fy_year}: {len(records)} months")
            except Exception as e:
                print(f"    FY{fy_year} error: {e}")

        if not all_records:
            return {}

        df = pd.DataFrame(all_records)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates(subset="date", keep="last")
        df = df.reset_index(drop=True)

        print(f"  Total: {len(df)} months, "
              f"${df['handle'].iloc[-1]:,.0f} handle latest")

        return {"total": df[["date", "handle", "ggr"]]}

    # ── URL discovery ─────────────────────────────────────────────

    def _find_pdf_urls(self) -> list[tuple[str, int]]:
        """Find sportsbook PDF links from the financials page.

        The links are inside a <script type="text/template"> tag
        with id="SportsBookRevenueModalContent".
        """
        try:
            resp = requests.get(PAGE_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  Error fetching page: {e}")
            return []

        html = resp.text

        # Extract the modal template content
        match = re.search(
            r'<script[^>]*id="SportsBookRevenueModalContent"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        if not match:
            print("  Could not find SportsBookRevenueModalContent template.")
            return []

        content = match.group(1)

        # Find PDF links with FY labels
        links = re.findall(
            r'href=["\']([^"\']*\.pdf)["\'][^>]*>([^<]*)',
            content, re.IGNORECASE,
        )

        urls = []
        for href, text in links:
            fy_match = re.search(r"(?:Fiscal\s+Year|FY)\s*(\d{4})", text, re.IGNORECASE)
            if not fy_match:
                fy_match = re.search(r"FY(\d{4})", href, re.IGNORECASE)
            if not fy_match:
                continue

            fy_year = int(fy_match.group(1))
            full_url = href if href.startswith("http") else BASE_URL + href
            urls.append((full_url, fy_year))

        return sorted(urls, key=lambda x: x[1])

    # ── PDF parsing ───────────────────────────────────────────────

    def _parse_pdf(self, pdf_bytes: bytes, fy_year: int) -> list[dict]:
        """Parse a FY PDF using word x-positions for robust number extraction.

        Strategy:
        1. Extract words with positions from the PDF page
        2. Group words into rows by y-position
        3. For each data row, find the last month marker (Combined section)
        4. Group number fragments by x-proximity (gap > 10 = new number)
        5. Extract 3 numbers: Handle, Payout, GGR
        """
        try:
            pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
        except Exception:
            return []

        page = pdf.pages[0]
        words = page.extract_words(x_tolerance=3, y_tolerance=3)
        if not words:
            return []

        # Group words by row (y-position, snapped to grid)
        rows_by_y = defaultdict(list)
        for w in words:
            y_key = round(w["top"] / 2) * 2
            rows_by_y[y_key].append(w)

        records = []
        for y_key in sorted(rows_by_y.keys()):
            row = sorted(rows_by_y[y_key], key=lambda w: w["x0"])
            if not row:
                continue

            # Skip non-data rows
            first_text = row[0]["text"]
            if first_text not in MONTH_ABBREVS:
                continue
            if any(w["text"] == "Total" for w in row):
                continue

            # Find all month marker positions in this row
            month_indices = [
                i for i, w in enumerate(row) if w["text"] in MONTH_ABBREVS
            ]
            if len(month_indices) < 2:
                continue

            # Combined section starts at the last month marker
            start_idx = month_indices[-1]
            combined_words = row[start_idx:]

            # Determine date from the Combined month marker
            month_abbrev = combined_words[0]["text"]
            month_num = MONTH_NUM[month_abbrev]

            # Check for year suffix (e.g., "19" in "Jul 19")
            year_suffix = None
            if (len(combined_words) > 1
                    and re.match(r"^\d{2}$", combined_words[1]["text"])):
                year_suffix = int(combined_words[1]["text"])

            if year_suffix is not None:
                cal_year = 2000 + year_suffix
            else:
                # FY format: FY2019 = Jul 2018 – Jun 2019
                cal_year = fy_year - 1 if month_num >= 7 else fy_year

            date_str = f"{cal_year}-{month_num:02d}-01"

            # Extract numbers from Combined section words
            numbers = self._extract_numbers_from_words(combined_words)
            if numbers is None:
                continue

            handle, payout, ggr = numbers
            if handle == 0 and payout == 0 and ggr == 0:
                continue

            records.append({
                "date": date_str,
                "handle": handle,
                "ggr": ggr,
            })

        return records

    @staticmethod
    def _extract_numbers_from_words(words: list[dict]) -> tuple[float, float, float] | None:
        """Extract 3 numbers (Handle, Payout, GGR) from Combined section words.

        Filters out month names, year suffixes, $ signs, and dashes.
        Groups remaining number fragments by x-position gap:
        - Gap <= GAP_THRESHOLD: same number (merge fragments)
        - Gap > GAP_THRESHOLD: different number
        """
        # Filter to numeric-like words
        num_words = []
        saw_month = False
        for w in words:
            text = w["text"].strip()
            if text in MONTH_ABBREVS:
                saw_month = True
                continue
            # Skip year suffix immediately after month
            if saw_month and re.match(r"^\d{2}$", text) and not num_words:
                saw_month = False
                continue
            saw_month = False
            if text in ("$", "-"):
                continue
            num_words.append(w)

        if not num_words:
            return None

        # Group by x-position proximity
        groups = [[num_words[0]]]
        for w in num_words[1:]:
            gap = w["x0"] - groups[-1][-1]["x1"]
            if gap > GAP_THRESHOLD:
                groups.append([w])
            else:
                groups[-1].append(w)

        # Convert each group to a number
        numbers = []
        for group in groups:
            text = "".join(w["text"] for w in group)
            text = text.replace("$", "").replace(" ", "")
            is_neg = "(" in text and ")" in text
            text = text.replace("(", "").replace(")", "")
            text = text.replace(",", "")
            try:
                val = float(text)
                if is_neg:
                    val = -val
                numbers.append(val)
            except ValueError:
                pass

        if len(numbers) != 3:
            return None

        return numbers[0], numbers[1], numbers[2]
