"""Kentucky sports betting scraper — KHRC monthly PDF reports.

Downloads the cumulative Sports Wagering Market Report PDF from khrc.ky.gov.
Each page covers one month with Online and Retail sections.
Operator-level data is extracted from the Online section.

GGR = Wagers − Winnings (handle less payouts to players).
Kentucky also reports AGR = Wagers − Winnings − Federal Excise Tax.
"""

import io
import re
from collections import defaultdict

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper

BASE_URL = "https://khrc.ky.gov"
PAGE_URL = "https://khrc.ky.gov/newstatic_info.aspx?static_ID=694"

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


class KYScraper(BaseScraper):
    STATE_CODE = "ky"
    STATE_NAME = "Kentucky"
    TAX_RATE = 0.1425
    TAX_RATE_NOTE = "14.25% online, 9.75% retail on AGR"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2023-09-28"
    GGR_DEFINITION = "Handle − Winnings (Wagers less payouts to players)"

    def scrape(self) -> dict[str, pd.DataFrame]:
        pdf_url = self._get_pdf_url()
        if not pdf_url:
            print("  No PDF URL found.")
            return {}

        print(f"  Downloading: {pdf_url}")
        resp = requests.get(pdf_url, timeout=60)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}")
            return {}

        all_months = {}
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            for page in pdf.pages:
                date_str, operators = self._parse_page(page)
                if date_str and operators:
                    all_months[date_str] = operators

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

    def _get_pdf_url(self) -> str | None:
        """Find the sports wagering report PDF URL from the KHRC page."""
        try:
            resp = requests.get(PAGE_URL, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True).lower()
                href = a["href"]
                if "wagering" in text and "report" in text and ".pdf" in href.lower():
                    full_url = href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")
                    return full_url

        except Exception as e:
            print(f"  Error fetching page: {e}")
        return None

    def _parse_page(self, page) -> tuple[str | None, dict]:
        """Parse a single page. Returns (date_str, {operator: {handle, ggr}})."""
        text = page.extract_text() or ""
        lines = text.split("\n")

        # Find date from header
        date_str = self._extract_date(lines)
        if not date_str:
            return None, {}

        # Find Online and Retail wagers/winnings rows
        wagers_lines = []
        winnings_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Wagers") and "$" in stripped:
                wagers_lines.append(stripped)
            elif stripped.startswith("Winnings") and "$" in stripped:
                winnings_lines.append(stripped)

        if len(wagers_lines) < 2 or len(winnings_lines) < 2:
            return None, {}

        # Online = first pair, Retail = second pair
        online_wagers = self._extract_amounts(wagers_lines[0])
        online_winnings = self._extract_amounts(winnings_lines[0])
        retail_wagers = self._extract_amounts(wagers_lines[1])
        retail_winnings = self._extract_amounts(winnings_lines[1])

        if not online_wagers or not online_winnings:
            return None, {}

        # Per-operator amounts (all except last = Grand Total)
        op_wagers = online_wagers[:-1]
        op_winnings = online_winnings[:-1]

        # Detect operators using word positions
        operators_list = self._detect_operators(page, text)

        n_ops = len(op_wagers)
        if len(operators_list) != n_ops:
            # Fallback: infer operators from count
            operators_list = self._infer_operators(n_ops)

        if len(operators_list) != n_ops:
            print(f"    Warning: {date_str}: {len(operators_list)} operators vs {n_ops} amounts")
            return None, {}

        # Build operator data
        month_ops = {}
        for j, name in enumerate(operators_list):
            handle = op_wagers[j]
            ggr = op_wagers[j] - (op_winnings[j] if j < len(op_winnings) else 0)
            if name in month_ops:
                month_ops[name]["handle"] += handle
                month_ops[name]["ggr"] += ggr
            else:
                month_ops[name] = {"handle": handle, "ggr": ggr}

        # Retail aggregate
        if retail_wagers and retail_winnings:
            retail_handle = retail_wagers[-1]
            retail_ggr = retail_wagers[-1] - retail_winnings[-1]
            if retail_handle > 0:
                month_ops["Retail (All Properties)"] = {
                    "handle": retail_handle,
                    "ggr": retail_ggr,
                }

        return date_str, month_ops

    def _extract_date(self, lines: list[str]) -> str | None:
        """Extract date from page header lines."""
        for line in lines[:5]:
            lower = line.lower().strip()
            # Skip cumulative "All" pages
            if "all" in lower and ("online" in lower or "retail" in lower):
                return None
            for month_name, month_num in MONTH_MAP.items():
                if month_name in lower:
                    year_match = re.search(r"20\d{2}", line)
                    if year_match:
                        return f"{year_match.group()}-{month_num:02d}-01"
        return None

    def _detect_operators(self, page, text: str) -> list[str]:
        """Detect online operators from word positions in the header area."""
        words = page.extract_words()

        # Find the y-position of the first Wagers data line
        wagers_y = None
        for w in sorted(words, key=lambda w: w["top"]):
            if w["text"] == "Wagers":
                # Verify it's a data row (has $ nearby on same line)
                has_dollar = any(
                    ww["text"].startswith("$")
                    for ww in words
                    if abs(ww["top"] - w["top"]) < 5 and ww["x0"] > w["x0"]
                )
                if has_dollar:
                    wagers_y = w["top"]
                    break

        if wagers_y is None:
            return []

        # Find "Online" header y-position
        online_y = None
        for w in sorted(words, key=lambda w: w["top"]):
            if w["text"].lower() == "online" and w["top"] < wagers_y:
                online_y = w["top"]
                break

        if online_y is None:
            return []

        # Collect words between Online header and Wagers line
        header_words = [
            w for w in words
            if online_y < w["top"] < wagers_y
        ]

        # Find operator patterns with x-positions
        matches = []
        seen_espn = False

        for w in header_words:
            text_lower = w["text"].lower().rstrip(".,")
            x = w["x0"]

            # DraftKings (possibly concatenated with Penn/Interactive)
            if "draftkings" in text_lower:
                matches.append((x, "DraftKings"))
                if "penn" in text_lower or "interactive" in text_lower:
                    matches.append((x + 0.1, "ESPN Bet"))
                    seen_espn = True
            # Penn Sports (standalone word)
            elif text_lower.startswith("penn") and not seen_espn:
                matches.append((x, "ESPN Bet"))
                seen_espn = True
            # Other known operators
            elif text_lower == "prime":
                matches.append((x, "Prime"))
            elif text_lower == "circa":
                matches.append((x, "Circa Sports"))
            elif text_lower == "fanatics":
                matches.append((x, "Fanatics"))
            elif text_lower == "caesars":
                matches.append((x, "Caesars"))
            elif text_lower == "bet365":
                matches.append((x, "Bet365"))
            elif text_lower == "betmgm":
                matches.append((x, "BetMGM"))
            elif text_lower.startswith("fanduel") or text_lower.startswith("fandue"):
                matches.append((x, "FanDuel"))

        # Sort by x-position, deduplicate
        matches.sort(key=lambda m: m[0])
        seen = set()
        result = []
        for _, name in matches:
            if name not in seen:
                result.append(name)
                seen.add(name)

        return result

    @staticmethod
    def _infer_operators(n_ops: int) -> list[str]:
        """Fallback: infer operator set from count."""
        if n_ops == 9:
            return ["Prime", "DraftKings", "ESPN Bet", "Circa Sports",
                    "Fanatics", "Caesars", "Bet365", "BetMGM", "FanDuel"]
        elif n_ops == 8:
            return ["DraftKings", "ESPN Bet", "Circa Sports",
                    "Fanatics", "Caesars", "Bet365", "BetMGM", "FanDuel"]
        elif n_ops == 7:
            return ["DraftKings", "ESPN Bet", "Fanatics",
                    "Caesars", "Bet365", "BetMGM", "FanDuel"]
        elif n_ops == 6:
            return ["DraftKings", "ESPN Bet", "Fanatics",
                    "Caesars", "BetMGM", "FanDuel"]
        return []

    @staticmethod
    def _extract_amounts(text: str) -> list[float]:
        """Extract all dollar amounts (including negative/parenthetical) from text."""
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
