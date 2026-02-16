"""Maine sports betting scraper — GCU PDF revenue reports.

Downloads operator-level PDF reports from the Maine Gambling Control Unit.
Each PDF contains monthly revenue data (2024/2025 format: monthly columns,
2023 format: daily rows with monthly totals).

Operators: DraftKings (via Passamaquoddy), Caesars (via Penobscot/Maliseet/Micmac),
Oddfellahs (First Tracks Investments retail), Oxford Sportsbook (retail).

GGR = Wagers − Voided/Cancelled Wagers − Payouts.
Tax is 10% on Adjusted Gross Receipts (AGR = GGR − Federal Excise Tax).
"""

import io
import re
from collections import defaultdict

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper

PAGE_URL = "https://www.maine.gov/dps/gcu/sports-wagering/sports-wagering-revenue"
BASE_URL = "https://www.maine.gov"

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_NUM = {name: i + 1 for i, name in enumerate(MONTH_NAMES)}

# Map PDF operator names → consumer-facing brand names
OPERATOR_BRAND_MAP = {
    "Passamaquoddy": "DraftKings",
    "Penobscot Maliseet Micmac": "Caesars",
    "First Tracks Investments": "Oddfellahs",
    # Oxford Sportsbook stays as-is
}

# Map 2023-era PDF names to the same canonical names (via brand)
OPERATOR_ALIASES = {
    "DraftKings": "DraftKings",
    "American Wagering": "Caesars",
}


class MEScraper(BaseScraper):
    STATE_CODE = "me"
    STATE_NAME = "Maine"
    TAX_RATE = 0.10
    TAX_RATE_NOTE = "10% on adjusted gross receipts (AGR)"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2023-12-01"
    GGR_DEFINITION = "Wagers \u2212 Voided/Cancelled Wagers \u2212 Payouts"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._agr_data = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        pdf_urls = self._find_pdf_urls()
        if not pdf_urls:
            print("  No PDF URLs found.")
            return {}

        print(f"  Found {len(pdf_urls)} PDFs.")

        operator_data = defaultdict(list)

        for url in pdf_urls:
            try:
                records = self._download_and_parse(url)
                for rec in records:
                    operator_data[rec["operator"]].append(rec)
            except Exception as e:
                print(f"    Error parsing {url.split('/')[-1][:60]}: {e}")

        if not operator_data:
            print("  No data parsed.")
            return {}

        result = {}
        agr_result = {}
        for operator, records in sorted(operator_data.items()):
            df = pd.DataFrame(records)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").drop_duplicates(subset="date", keep="last")
            df = df.reset_index(drop=True)
            result[operator] = df[["date", "handle", "ggr"]]
            agr_result[operator] = df[["date", "agr"]].rename(columns={"agr": "handle"})
            print(f"    {operator}: {len(df)} months")

        self._agr_data = agr_result
        return result

    def run(self):
        """Override run to compute tax on AGR instead of GGR."""
        result = super().run()

        if self._agr_data and not result.ggr_pivot.empty:
            agr_pivot = self.build_pivot(self._agr_data, "handle")
            tax_revenue = agr_pivot * self.TAX_RATE

            path = self.state_dir / "tax_revenue.csv"
            tax_revenue.to_csv(path, index=True, date_format="%Y-%m-%d")
            print(f"  Rewrote tax_revenue.csv (based on AGR)")

            latest_date = result.handle_pivot.index.max()
            latest_agr = agr_pivot.loc[latest_date, "Total"] if pd.notna(agr_pivot.loc[latest_date, "Total"]) else None
            if latest_agr and result.metadata:
                result.metadata["latestData"]["taxRevenue"] = round(latest_agr * self.TAX_RATE, 2)

            result = result.__class__(
                state_code=result.state_code,
                state_name=result.state_name,
                handle_pivot=result.handle_pivot,
                ggr_pivot=result.ggr_pivot,
                hold_pivot=result.hold_pivot,
                yoy_handle=result.yoy_handle,
                yoy_ggr=result.yoy_ggr,
                tax_revenue=tax_revenue,
                sports_handle=result.sports_handle,
                metadata=result.metadata,
            )

        return result

    def _find_pdf_urls(self) -> list[str]:
        """Scrape the revenue page for all PDF download links."""
        urls = []
        try:
            resp = requests.get(PAGE_URL, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.lower().endswith(".pdf"):
                    continue
                full_url = href if href.startswith("http") else BASE_URL + href
                urls.append(full_url)

        except Exception as e:
            print(f"  Error fetching page: {e}")

        return urls

    def _download_and_parse(self, url: str) -> list[dict]:
        """Download a PDF and parse operator monthly data from it."""
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code} for {url.split('/')[-1][:50]}")
            return []

        pdf = pdfplumber.open(io.BytesIO(resp.content))
        text = pdf.pages[0].extract_text()
        if not text:
            return []

        if "MONTHLY TOTALS" in text.upper():
            return self._parse_daily_format(text)
        else:
            return self._parse_monthly_format(text)

    def _parse_monthly_format(self, text: str) -> list[dict]:
        """Parse 2024/2025 format: monthly columns with operator totals."""
        op_match = re.search(
            r"SPORTS WAGERING\s*[-\u2013\u2014]\s*(.+?)"
            r"(?:\s+(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December|Y-T-D))",
            text,
        )
        if not op_match:
            return []
        operator = self._clean_operator_name(op_match.group(1).strip())

        month_year_pairs = re.findall(
            r"(" + "|".join(MONTH_NAMES) + r")\s+(\d{4})", text
        )

        all_months_in_text = [m for m in MONTH_NAMES if m in text]

        if month_year_pairs:
            dominant_year = month_year_pairs[0][1]
        else:
            year_match = re.search(r"(?<!\d)(20\d{2})(?!\d)", text)
            dominant_year = year_match.group(1) if year_match else None

        if not dominant_year:
            return []

        paired_months = {m for m, _ in month_year_pairs}
        month_year_pairs_complete = []
        for m in all_months_in_text:
            if m in paired_months:
                year = next(y for mn, y in month_year_pairs if mn == m)
                month_year_pairs_complete.append((m, year))
            else:
                month_year_pairs_complete.append((m, dominant_year))

        if not month_year_pairs_complete:
            return []

        month_year_pairs = month_year_pairs_complete

        dates = []
        for month_name, year in month_year_pairs:
            month_num = MONTH_NUM[month_name]
            dates.append(f"{year}-{month_num:02d}-01")

        n_months = len(dates)

        handle_amounts = self._extract_row_amounts(text, "Gross Event Wagering Receipts")
        voided_amounts = self._extract_row_amounts(text, "Voided and Cancelled Wagers")
        payout_amounts = self._extract_row_amounts(text, "Winnings Paid to Players")
        excise_amounts = self._extract_row_amounts(text, "Federal Excise Tax - 0.25")

        if not handle_amounts or not payout_amounts:
            return []

        handle_amounts = handle_amounts[:n_months]
        voided_amounts = voided_amounts[:n_months] if voided_amounts else [0] * n_months
        payout_amounts = payout_amounts[:n_months]
        excise_amounts = excise_amounts[:n_months] if excise_amounts else [0] * n_months

        while len(voided_amounts) < n_months:
            voided_amounts.append(0)
        while len(excise_amounts) < n_months:
            excise_amounts.append(0)

        n = min(len(dates), len(handle_amounts), len(payout_amounts))

        records = []
        for i in range(n):
            handle = handle_amounts[i]
            voided = voided_amounts[i] if i < len(voided_amounts) else 0
            payout = payout_amounts[i]
            excise = excise_amounts[i] if i < len(excise_amounts) else 0
            ggr = handle - voided - payout
            agr = ggr - excise
            if handle > 0:
                records.append({
                    "operator": operator,
                    "date": dates[i],
                    "handle": handle,
                    "ggr": ggr,
                    "agr": agr,
                })

        return records

    def _parse_daily_format(self, text: str) -> list[dict]:
        """Parse 2023 format: daily rows with MONTHLY TOTALS at bottom."""
        operator = None
        for alias in OPERATOR_ALIASES:
            if alias in text:
                operator = OPERATOR_ALIASES[alias]
                break

        if not operator:
            lic_match = re.search(r"Licensee:\s*(.+?)(?:\s+Month:)", text)
            if lic_match:
                operator = self._clean_operator_name(lic_match.group(1).strip())
            else:
                return []

        month_match = re.search(r"Month:\s*(\w+)", text)
        year_match = re.search(r"Year:\s*(\d{4})", text)
        if not month_match or not year_match:
            return []

        month_name = month_match.group(1)
        year = year_match.group(1)
        if month_name not in MONTH_NUM:
            return []
        date_str = f"{year}-{MONTH_NUM[month_name]:02d}-01"

        for line in text.split("\n"):
            if "MONTHLY TOTALS" in line.upper():
                amounts = self._extract_amounts(line)
                if len(amounts) >= 5:
                    handle = amounts[0]
                    voided = amounts[1]
                    payouts = amounts[2]
                    excise = amounts[3]
                    ggr = handle - voided - payouts
                    agr = ggr - excise
                    if handle > 0:
                        return [{
                            "operator": operator,
                            "date": date_str,
                            "handle": handle,
                            "ggr": ggr,
                            "agr": agr,
                        }]
        return []

    def _extract_row_amounts(self, text: str, label: str) -> list[float]:
        """Find a row by label and extract all dollar amounts after the label."""
        for line in text.split("\n"):
            idx = line.find(label)
            if idx >= 0:
                after_label = line[idx + len(label):]
                return self._extract_amounts(after_label)
        return []

    def _extract_amounts(self, text: str) -> list[float]:
        """Extract all dollar amounts from text, handling space-separated digits."""
        raw_amounts = re.findall(r"[\d][\d ,]*\.\d{2}", text)
        results = []
        for raw in raw_amounts:
            cleaned = raw.replace(",", "").replace(" ", "")
            try:
                val = float(cleaned)
            except ValueError:
                continue

            idx = text.find(raw)
            if idx > 0:
                prefix = text[:idx].rstrip()
                if prefix.endswith("("):
                    val = -val
            results.append(val)
        return results

    def _clean_operator_name(self, name: str) -> str:
        """Normalize operator name to consumer-facing brand."""
        name = re.sub(r",?\s*LLC\.?$", "", name, flags=re.IGNORECASE).strip()
        for alias, canonical in OPERATOR_ALIASES.items():
            if alias.lower() in name.lower():
                return canonical
        for corp_name, brand in OPERATOR_BRAND_MAP.items():
            if corp_name.lower() in name.lower():
                return brand
        return name
