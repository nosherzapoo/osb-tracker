"""Iowa sports betting scraper — IRGC monthly PDF reports.

Downloads fiscal-year and monthly PDF reports from irgc.iowa.gov.
FY PDFs (FY2020-FY2025) contain all 12 months; current-FY monthly
PDFs cover the ongoing fiscal year. Operator-level data available
from FY2022 onwards.

GGR = Handle − Payouts (reported as "Sports Wagering Net Receipts").
"""

import io
import re
from collections import defaultdict

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper

BASE_URL = "https://irgc.iowa.gov"
CURRENT_URL = "https://irgc.iowa.gov/publications-reports/sports-wagering-revenue"
ARCHIVE_URL = "https://irgc.iowa.gov/publications-reports/sports-wagering-revenue/archived-sports-revenue"

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Map Iowa licensee names → canonical operator names.
# Keys are lowercase first-word patterns matched against individual header lines.
# Using short, unambiguous patterns to avoid multi-line name issues.
LICENSEE_MAP = {
    "american": "Caesars",
    "william hill": "Caesars",
    "bally": "Bally Bet",
    "betfair": "FanDuel",
    "betmgm": "BetMGM",
    "circa": "Circa Sports",
    "crown": "DraftKings",
    "dubuque": "Dubuque Racing",
    "fbg": "Fanatics",
    "pointsbet": "Fanatics",
    "hillside": "Bet365",
    "penn sports": "ESPN Bet",
    "rush street": "Rush Street Interactive",
    "sce partners": "SCE Partners",
    "sporttrade": "Sporttrade",
    "betfred": "BetFred",
    "bluebet": "BlueBet",
    "digital gaming": "Betway",
    "elite": "Elite Hospitality",
}


class IAScraper(BaseScraper):
    STATE_CODE = "ia"
    STATE_NAME = "Iowa"
    TAX_RATE = 0.0675
    TAX_RATE_NOTE = "6.75% on net receipts"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = CURRENT_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2019-08-15"
    GGR_DEFINITION = "Sports Wagering Net Receipts (Handle − Payouts)"

    def scrape(self) -> dict[str, pd.DataFrame]:
        pdf_urls = self._gather_pdf_urls()
        if not pdf_urls:
            print("  No PDF URLs found.")
            return {}

        # Parse all PDFs for monthly data
        all_months = {}  # date_str -> {operator -> {handle, ggr}}

        for label, url in pdf_urls:
            try:
                resp = requests.get(url, timeout=60)
                if resp.status_code != 200:
                    print(f"    {label}: HTTP {resp.status_code}")
                    continue

                months = self._parse_pdf(resp.content, label)
                for date_str, operators in months.items():
                    if date_str not in all_months:
                        all_months[date_str] = {}
                    # Merge operator data (later PDFs may have corrections)
                    all_months[date_str].update(operators)

            except Exception as e:
                print(f"    {label}: error - {e}")

        if not all_months:
            print("  No monthly data parsed.")
            return {}

        # Build per-operator DataFrames
        op_data = defaultdict(list)
        for date_str in sorted(all_months.keys()):
            operators = all_months[date_str]
            for op_name, vals in operators.items():
                op_data[op_name].append({
                    "date": pd.Timestamp(date_str),
                    "handle": vals["handle"],
                    "ggr": vals["ggr"],
                })

        result = {}
        for name, records in op_data.items():
            df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
            result[name] = df

        total_months = len(all_months)
        total_ops = len(result)
        print(f"  Parsed {total_months} months, {total_ops} operators.")
        for name, df in sorted(result.items()):
            print(f"    {name}: {len(df)} months")

        return result

    def _gather_pdf_urls(self) -> list[tuple[str, str]]:
        """Collect all PDF URLs from both current and archived pages."""
        urls = []

        for page_url in [ARCHIVE_URL, CURRENT_URL]:
            try:
                resp = requests.get(page_url, timeout=30)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True)
                    href = a["href"]
                    if not href or "download" not in href:
                        continue

                    # Skip non-revenue PDFs
                    lower = text.lower()
                    if "amendment" in lower or "approved" in lower or "wagers list" in lower:
                        continue
                    if "revenue" not in lower:
                        continue

                    full_url = href if href.startswith("http") else BASE_URL + href
                    urls.append((text.strip(), full_url))

            except Exception as e:
                print(f"  Error fetching {page_url}: {e}")

        print(f"  Found {len(urls)} PDF links.")
        return urls

    def _parse_pdf(self, content: bytes, label: str) -> dict[str, dict]:
        """Parse a PDF and return monthly data.

        Returns: {date_str: {operator_name: {handle: float, ggr: float}}}
        """
        months = {}

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = pdf.pages
            i = 0
            while i < len(pages):
                text = pages[i].extract_text() or ""
                first_line = text.split("\n")[0] if text else ""

                # Skip FYTD summary pages and amendment pages
                if "FYTD" in first_line or "Amendments" in first_line or "Amendment" in first_line:
                    i += 1
                    continue

                # Check for monthly report page
                date_str = self._parse_month_from_header(first_line)
                if not date_str:
                    i += 1
                    continue

                # Parse aggregate data from this page (page 1 of month)
                agg = self._parse_aggregate_page(text)

                # Check if next page has operator data
                op_data = {}
                if i + 1 < len(pages):
                    next_text = pages[i + 1].extract_text() or ""
                    if "BY OPERATOR" in next_text:
                        op_data = self._parse_operator_page(next_text)
                        i += 1  # Skip operator page

                # Build month entry
                month_operators = {}

                if op_data:
                    # Use operator-level data
                    for op_name, vals in op_data.items():
                        month_operators[op_name] = vals

                    # Add retail-only total to capture retail handle not in online operators
                    if agg:
                        retail_handle = agg["handle"] - sum(v["handle"] for v in op_data.values())
                        retail_ggr = agg["ggr"] - sum(v["ggr"] for v in op_data.values())
                        if retail_handle > 100000:  # Only if meaningful retail component
                            month_operators["Retail (All Properties)"] = {
                                "handle": retail_handle,
                                "ggr": retail_ggr,
                            }
                elif agg:
                    # No operator data — use aggregate total
                    month_operators["Total"] = agg

                if month_operators:
                    months[date_str] = month_operators

                i += 1

        if months:
            print(f"    {label}: {len(months)} months parsed")

        return months

    def _parse_month_from_header(self, header: str) -> str | None:
        """Extract date from header like 'SPORTS WAGERING REVENUE REPORT -- JANUARY 2026'."""
        lower = header.lower()
        for month_name, month_num in MONTH_MAP.items():
            if month_name in lower:
                year_match = re.search(r"20\d{2}", header)
                if year_match:
                    return f"{year_match.group()}-{month_num:02d}-01"
        return None

    def _parse_aggregate_page(self, text: str) -> dict | None:
        """Extract state-wide totals from a property-level page.

        Returns {handle: float, ggr: float} from the Totals column (last amounts).
        """
        handle = 0.0
        ggr = 0.0

        for line in text.split("\n"):
            amounts = self._extract_amounts(line)
            if not amounts:
                continue

            if re.match(r"SPORTS WAGERING HANDLE", line, re.IGNORECASE):
                handle = amounts[-1]  # Last amount = Totals column
            elif re.match(r"SPORTS WAGERING NET RECEIPTS", line, re.IGNORECASE):
                ggr = amounts[-1]

        if handle > 0:
            return {"handle": handle, "ggr": ggr}
        return None

    def _parse_operator_page(self, text: str) -> dict[str, dict]:
        """Parse online operator data from page 2.

        The page has 1-2 blocks of operators. Each block has:
        - Header line(s) with operator names (first line has all first-words)
        - INTERNET NET RECEIPTS row
        - INTERNET HANDLE row
        - INTERNET PAYOUTS row

        Returns {canonical_name: {handle: float, ggr: float}}
        """
        lines = text.split("\n")
        operators = {}

        # Find all INTERNET data blocks by scanning for the data row patterns
        # and collecting the header line that precedes each block
        blocks = []
        current_header_line = ""  # First header line before data (has operator first-words)
        current_data = {}
        awaiting_header = True

        for line in lines:
            upper = line.upper().strip()

            if "BY OPERATOR" in upper:
                awaiting_header = True
                continue

            is_data_row = bool(re.match(
                r"INTERNET\s+(NET\s+RECEIPTS|HANDLE|PAYOUTS)", upper
            ))

            if is_data_row:
                awaiting_header = False
                amounts = self._extract_amounts(line)
                if "NET RECEIPTS" in upper:
                    current_data["ggr"] = amounts
                elif "HANDLE" in upper and "PAYOUTS" not in upper:
                    current_data["handle"] = amounts
                elif "PAYOUTS" in upper:
                    # Block complete — save it
                    if "ggr" in current_data and "handle" in current_data:
                        blocks.append({
                            "header": current_header_line,
                            "ggr": current_data["ggr"],
                            "handle": current_data["handle"],
                        })
                    current_data = {}
                    awaiting_header = True
                    current_header_line = ""
            elif awaiting_header and line.strip() and "$" not in line:
                # First non-empty, non-data line after a block boundary = header
                if not current_header_line:
                    current_header_line = line.strip()

        # Handle last block if PAYOUTS line was missing
        if "ggr" in current_data and "handle" in current_data:
            blocks.append({
                "header": current_header_line,
                "ggr": current_data["ggr"],
                "handle": current_data["handle"],
            })

        # Process each block: match operators to amounts
        for block in blocks:
            op_names = self._extract_operator_names(block["header"])
            ggr_amounts = block["ggr"]
            handle_amounts = block["handle"]

            n = min(len(op_names), len(ggr_amounts), len(handle_amounts))
            if n == 0 and len(ggr_amounts) > 0:
                # Fallback: if no names matched, skip this block
                continue

            for j in range(n):
                name = op_names[j]
                if name in operators:
                    operators[name]["handle"] += handle_amounts[j]
                    operators[name]["ggr"] += ggr_amounts[j]
                else:
                    operators[name] = {
                        "handle": handle_amounts[j],
                        "ggr": ggr_amounts[j],
                    }

        return operators

    def _extract_operator_names(self, header_text: str) -> list[str]:
        """Extract ordered canonical operator names from header text.

        Searches the FIRST header line only (all operator first-words
        appear on line 1), so column order is preserved left-to-right.
        """
        # Normalize smart quotes and other unicode
        normalized = header_text.replace("\u2019", "'").replace("\u2018", "'")
        # Use only the first line of the header (operator first-words are always on line 1)
        first_line = normalized.split("\n")[0] if "\n" in normalized else normalized
        lower = first_line.lower()

        matches = []
        for pattern, canonical in LICENSEE_MAP.items():
            idx = lower.find(pattern)
            if idx >= 0:
                matches.append((idx, canonical))

        # Sort by position (left-to-right = column order)
        matches.sort(key=lambda x: x[0])

        # Deduplicate (e.g., "Fanatics" from both "FBG" and "PointsBet")
        seen = set()
        result = []
        for _, name in matches:
            if name not in seen:
                result.append(name)
                seen.add(name)

        return result

    @staticmethod
    def _extract_amounts(text: str) -> list[float]:
        """Extract all dollar amounts (including negative/parenthetical) from text."""
        # Match $1,234.56, ($1,234.56), -$1,234.56
        raw = re.findall(r"[(-]?\$[\d,]+(?:\.\d+)?\)?", text)
        results = []
        for s in raw:
            negative = "(" in s or s.startswith("-")
            cleaned = re.sub(r"[$,() \-]", "", s)
            try:
                val = float(cleaned)
                if negative:
                    val = -val
                results.append(val)
            except ValueError:
                pass
        return results
