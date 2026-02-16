"""Arizona sports betting scraper — AZ Dept of Gaming monthly PDF reports."""

import io
import re
from collections import defaultdict

import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

from .base import BaseScraper

try:
    import cloudscraper
except ImportError:
    cloudscraper = None

REPORTS_INDEX = "https://gaming.az.gov/blog-terms/event-wagering-revenue-reports"
BASE_URL = "https://gaming.az.gov"

# Map PDF operator names to canonical names
OPERATOR_NAME_MAP = {
    "BetMGM": "BetMGM",
    "Caesars (American Wagering)": "Caesars",
    "Draft Kings/Crown Gaming": "DraftKings",
    "Fan Duel": "FanDuel",
    "FanDuel": "FanDuel",
    "Bally Interactive, LLC": "Bally Bet",
    "Bally Interactive": "Bally Bet",
    "Bet365": "Bet365",
    "BetFred": "BetFred",
    "Churchill Downs/Twin Spires": "TwinSpires",
    "Churchill Downs/TwinSpires": "TwinSpires",
    "Desert Diamond Mobile": "Desert Diamond",
    "Digital Gaming USA (Betway)": "Betway",
    "Digital Gaming USA": "Betway",
    "Fanatics Sports Book": "Fanatics",
    "Fanatics Sportsbook": "Fanatics",
    "Golden Nugget Online Gaming": "Golden Nugget",
    "PENN / ESPN Bet": "ESPN Bet",
    "PENN/ESPN Bet": "ESPN Bet",
    "Penn Sports (Barstool Sports)": "ESPN Bet",
    "Plannatech": "Plannatech",
    "RSI (Rush Street Interactive)": "Rush Street Interactive",
    "Sahara Bets": "Sahara Bets",
    "SBOpco, LLC (SuperBook)": "SuperBook",
    "SBOpco (SuperBook)": "SuperBook",
    "Seminole Hard Rock Digital": "Seminole Hard Rock",
    "Sporttrade": "Sporttrade",
    "Unibet AZ (Kindred)": "Unibet",
    "WSI US (WynnBet)": "WynnBet",
}


class AZScraper(BaseScraper):
    STATE_CODE = "az"
    STATE_NAME = "Arizona"
    TAX_RATE = 0.10
    TAX_RATE_NOTE = "8% retail, 10% mobile (blended ~10%)"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = "https://gaming.az.gov/resources/reports"
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2021-09-09"
    GGR_DEFINITION = "Adjusted Gross Event Wagering Receipts from ADG reports (Handle − Payouts, pre-deductions)"

    def scrape(self) -> dict[str, pd.DataFrame]:
        if cloudscraper is None:
            print("  cloudscraper not installed, using fallback.")
            return self._fallback_data()

        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "darwin", "mobile": False}
        )
        print("  Fetching AZ report index pages...")

        # Collect all individual report page URLs
        report_pages = []
        for page_num in range(7):
            url = f"{REPORTS_INDEX}?page={page_num}"
            try:
                resp = scraper.get(url, timeout=30)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, "lxml")
                found = False
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if "event-wagering-revenue-report" in href and "blog-terms" not in href:
                        full = href if href.startswith("http") else BASE_URL + href
                        m = re.search(r"report-(\w+)-(\d{4})", full)
                        if m and full not in [r[2] for r in report_pages]:
                            report_pages.append((m.group(1), m.group(2), full))
                            found = True
                if not found:
                    break
            except Exception as e:
                print(f"  Error fetching page {page_num}: {e}")
                break

        if not report_pages:
            print("  Could not find report pages, using fallback.")
            return self._fallback_data()

        print(f"  Found {len(report_pages)} report pages. Downloading PDFs...")

        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }

        # Accumulate per-operator data across all months
        operator_rows = defaultdict(list)
        total_rows = []

        for month_name, year, page_url in report_pages:
            month_num = month_map.get(month_name.lower())
            if not month_num:
                continue
            date_str = f"{year}-{month_num:02d}-01"
            date_ts = pd.Timestamp(date_str)

            try:
                resp = scraper.get(page_url, timeout=30)
                soup = BeautifulSoup(resp.text, "lxml")
                pdf_url = None
                for a in soup.find_all("a", href=True):
                    if ".pdf" in a["href"].lower():
                        pdf_url = a["href"] if a["href"].startswith("http") else BASE_URL + a["href"]
                        break

                if not pdf_url:
                    continue

                pdf_resp = scraper.get(pdf_url, timeout=60)
                if pdf_resp.status_code != 200:
                    continue

                operators = self._parse_pdf_operators(pdf_resp.content, date_str)

                if operators:
                    month_handle = 0.0
                    month_ggr = 0.0
                    for name, (handle, ggr) in operators.items():
                        operator_rows[name].append({
                            "date": date_ts,
                            "handle": handle,
                            "ggr": ggr,
                        })
                        month_handle += handle
                        month_ggr += ggr
                    total_rows.append({"date": date_ts, "handle": month_handle, "ggr": month_ggr})
                else:
                    # Fall back to aggregate parsing if operator parsing fails
                    handle, ggr = self._parse_pdf_totals(pdf_resp.content, date_str)
                    if handle > 0:
                        total_rows.append({"date": date_ts, "handle": handle, "ggr": ggr})

            except Exception as e:
                print(f"    Error on {date_str}: {e}")

        if not operator_rows and not total_rows:
            print("  No data parsed from PDFs, using fallback.")
            return self._fallback_data()

        # If we have operator-level data, return it
        if operator_rows:
            result = {}
            for name, rows in operator_rows.items():
                df = pd.DataFrame(rows)
                df = df.sort_values("date").reset_index(drop=True)
                result[name] = df
            print(f"  Parsed {len(total_rows)} months, {len(result)} operators.")
            return result

        # Otherwise return just the total
        print(f"  Parsed {len(total_rows)} months (aggregate only).")
        df = pd.DataFrame(total_rows)
        return {"Total": df}

    def _parse_pdf_operators(self, content: bytes, date_str: str) -> dict[str, tuple[float, float]]:
        """Parse operator-level handle and GGR from an AZ event wagering PDF.

        Returns dict of canonical_operator_name -> (handle, ggr_pre_deductions).
        """
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = pdf.pages[0].extract_text()
            if not text:
                return {}

        operators = {}
        lines = text.split("\n")
        in_operator_section = False

        for line in lines:
            stripped = line.strip()

            # Detect operator section start
            if "Operator:" in stripped and ("Retail" in stripped or "Mobile" in stripped):
                in_operator_section = True
                continue

            if not in_operator_section:
                continue

            # Stop at subtotal line (starts with $, no operator name)
            # or Limited Event Wagering section
            if stripped.startswith("$"):
                break
            if "Limited" in stripped or "Total" in stripped:
                break
            if not stripped or "$" not in stripped:
                continue

            # Split line at $ signs to separate operator name from values
            parts = stripped.split("$")
            name_raw = parts[0].strip()
            if not name_raw:
                continue

            # Parse dollar values
            values = []
            for part in parts[1:]:
                cleaned = part.replace(" ", "").replace(",", "").strip()
                if cleaned == "-" or cleaned == "":
                    values.append(0.0)
                else:
                    try:
                        values.append(float(cleaned))
                    except ValueError:
                        values.append(0.0)

            # 12 values = retail + mobile (6 metrics x 2 channels)
            # 6 values = mobile only (6 metrics x 1 channel)
            if len(values) == 12:
                handle = values[0] + values[1]   # retail + mobile gross wagers
                ggr = values[4] + values[5]       # retail + mobile adj GGR pre-deductions
            elif len(values) >= 6:
                handle = values[0]                # mobile gross wagers
                ggr = values[2]                   # mobile adj GGR pre-deductions
            else:
                continue

            # Normalize operator name
            canonical = OPERATOR_NAME_MAP.get(name_raw, name_raw)
            # Merge if same canonical name (e.g., ESPN Bet appears as both Penn Sports and PENN/ESPN Bet)
            if canonical in operators:
                prev_h, prev_g = operators[canonical]
                operators[canonical] = (prev_h + handle, prev_g + ggr)
            else:
                operators[canonical] = (handle, ggr)

        return operators

    def _parse_pdf_totals(self, content: bytes, date_str: str) -> tuple[float, float]:
        """Parse aggregate handle and GGR from an AZ event wagering PDF (fallback)."""
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"

            # Try table extraction from first page
            handle, ggr = 0.0, 0.0
            tables = pdf.pages[0].extract_tables()

            if tables and len(tables[0]) > 2:
                last_row = tables[0][-1]
                vals = [self._clean_money(c) for c in last_row]

                if len(vals) >= 12:
                    handle = vals[0] + vals[1]
                    ggr = vals[4] + vals[5]

            # Fallback: parse from summary text
            if handle == 0 or ggr == 0:
                h_text, g_text = self._parse_from_text(full_text)
                if handle == 0:
                    handle = h_text
                if ggr == 0:
                    ggr = g_text

            return handle, ggr

    def _parse_from_text(self, text: str) -> tuple[float, float]:
        """Parse handle and GGR from the summary text at bottom of PDF."""
        handle, ggr = 0.0, 0.0
        for line in text.split("\n"):
            ll = line.lower().strip()
            amounts = re.findall(r"\$\s*[\d, ]+(?:\.\d+)?", line)
            if not amounts:
                continue
            val = self._clean_money(amounts[-1])

            if "gross event wagering receipts" in ll and "adjusted" not in ll and "net" not in ll:
                handle = val
            elif ("net" in ll and "adj" in ll and "prior" in ll) or \
                 ("adjusted gross" in ll and "prior" in ll and "free" in ll):
                ggr = val
        return handle, ggr

    @staticmethod
    def _clean_money(s) -> float:
        if not s:
            return 0.0
        s = re.sub(r"[$,]", "", str(s)).strip()
        s = re.sub(r"\s+", "", s)
        if s == "-" or s == "":
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _fallback_data(self) -> dict[str, pd.DataFrame]:
        """AZ monthly estimates from public reporting."""
        data = [
            ("2024-01-01", 704329706, 69198016), ("2024-02-01", 635892228, 52967301),
            ("2024-03-01", 757698399, 57406693), ("2024-04-01", 654950708, 63206770),
            ("2024-05-01", 567314323, 60986742), ("2024-06-01", 454047879, 46202630),
            ("2024-07-01", 410140440, 41519312), ("2024-08-01", 496602562, 37353079),
            ("2024-09-01", 732099544, 77417680), ("2024-10-01", 791243694, 53758417),
            ("2024-11-01", 897635847, 84105254), ("2024-12-01", 849316636, 49338308),
            ("2025-01-01", 864241496, 83609019), ("2025-02-01", 699732379, 64694939),
            ("2025-03-01", 887363830, 48272323), ("2025-04-01", 746436864, 64784986),
            ("2025-05-01", 707103199, 73395113), ("2025-06-01", 542954635, 67250739),
            ("2025-07-01", 463686016, 53436248), ("2025-08-01", 610663049, 59948652),
            ("2025-09-01", 851331639, 54967404), ("2025-10-01", 967141269, 82958097),
            ("2025-11-01", 965233845, 80854981),
        ]
        rows = [{"date": pd.Timestamp(d), "handle": h, "ggr": g} for d, h, g in data]
        df = pd.DataFrame(rows)
        return {"Total": df}
