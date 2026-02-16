"""Wyoming sports betting scraper — gaming.wyo.gov Combined Wagering Activity Reports.

Monthly Combined Wagering Activity PDFs hosted on Google Drive, linked from
yearly archive pages on the Wyoming Gaming Commission website (Google Sites).

The Online Sports Wagering (OSW) section is near the end of each PDF and
includes operator-level data: Handle (Monthly Wagers), GGR (Gross Gaming Revenue),
Taxable Gaming Revenue, and Tax Due.

Three PDF format variants:
  Format 1 (Jan–Jul 2023): single table, operators in rows, 6 amount columns
  Format 2 (Aug 2023–Dec 2024): split into 2 sub-tables, operators in rows
  Format 3 (Jan 2025+): transposed — operators as columns, metrics as rows

Operators: BetMGM, Caesars, DraftKings, FanDuel; +Fanatics from ~Jun 2024.
Tax: 10% on Taxable Gaming Revenue (GGR minus promotional deductions).
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

# Canonical operator names
OPERATOR_MAP = {
    "BETMGM": "BetMGM",
    "CAESARS": "Caesars",
    "DRAFTKINGS": "DraftKings",
    "FANATICS": "Fanatics",
    "FANDUEL": "FanDuel",
    "WYNNBET": "WynnBet",
}

KNOWN_OPERATORS = set(OPERATOR_MAP.values())

# Yearly archive page paths (combined wagering reports)
ARCHIVE_PAGES = {
    2023: "/historical-revenue-reports/archive-combined-wagering-activity-2023",
    2024: "/historical-revenue-reports/archive-combined-wagering-activity-2024",
    2025: "/historical-revenue-reports/archive-combined-wagering-activity-reports-2025",
}

BASE_URL = "https://gaming.wyo.gov"
MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


class WYScraper(BaseScraper):
    STATE_CODE = "wy"
    STATE_NAME = "Wyoming"
    TAX_RATE = 0.10
    TAX_RATE_NOTE = "10% on taxable gaming revenue (GGR minus promo deductions)"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = "https://gaming.wyo.gov/revenue-reports/financial-reports/combined-wagering-activity-reports"
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2021-09-01"
    GGR_DEFINITION = "Gross Gaming Revenue (Handle minus Cash and Non-Cash Payouts)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tax_cache = {}  # date -> {operator: tax_amount}

    def scrape(self) -> dict[str, pd.DataFrame]:
        """Scrape all monthly Combined Wagering Activity PDFs."""
        file_map = self._find_pdf_file_ids()
        if not file_map:
            print("  No PDF file IDs found.")
            return {}

        print(f"  Found {len(file_map)} monthly report file IDs.")

        all_data = defaultdict(list)  # operator -> list of {date, handle, ggr}
        success = 0

        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

        for date_str, file_id in sorted(file_map.items()):
            result = _download_and_parse(session, file_id)
            if result is None:
                print(f"    Failed: {date_str}")
                continue

            operators_data, tax_data = result
            for op_name, (handle, ggr) in operators_data.items():
                all_data[op_name].append({
                    "date": date_str,
                    "handle": handle,
                    "ggr": ggr,
                })

            self._tax_cache[date_str] = tax_data
            success += 1

        print(f"  Parsed {success}/{len(file_map)} reports, "
              f"{len(all_data)} operators found.")

        if not all_data:
            return {}

        result = {}
        for op_name, records in all_data.items():
            df = pd.DataFrame(records)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").drop_duplicates(subset="date", keep="last")
            result[op_name] = df

        return result

    def run(self) -> "ScraperResult":
        """Override to use actual tax values from reports."""
        from .base import ScraperResult

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

        # Use actual tax values from reports
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
        """Build tax revenue from actual report values."""
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

    # ── URL discovery ─────────────────────────────────────────────

    def _find_pdf_file_ids(self) -> dict[str, str]:
        """Discover Google Drive file IDs from yearly archive pages.

        Returns dict of date_str -> file_id.
        """
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

        file_map = {}

        for year, path in ARCHIVE_PAGES.items():
            url = f"{BASE_URL}{path}"
            try:
                r = session.get(url, timeout=30)
                if r.status_code != 200:
                    continue
            except requests.RequestException:
                continue

            soup = BeautifulSoup(r.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)

                if "drive.google.com/file" not in href:
                    continue

                # Extract file ID
                fid_match = re.search(r"/d/([a-zA-Z0-9_-]+)", href)
                if not fid_match:
                    continue
                file_id = fid_match.group(1)

                # Match "MonthName YYYY" pattern
                month_match = re.match(
                    r"^(january|february|march|april|may|june|july|august|"
                    r"september|october|november|december)\s+(\d{4})$",
                    text, re.IGNORECASE,
                )
                if not month_match:
                    continue

                month_name = month_match.group(1).lower()
                yr = int(month_match.group(2))
                month_num = MONTH_NAMES[month_name]
                date_str = f"{yr}-{month_num:02d}-01"
                file_map[date_str] = file_id

        return file_map


# ── PDF parsing (module-level) ────────────────────────────────────

def _download_and_parse(
    session: requests.Session, file_id: str,
) -> tuple[dict[str, tuple[float, float]], dict[str, float]] | None:
    """Download PDF from Google Drive and parse the OSW section.

    Returns (operators_data, tax_data) or None.
    operators_data: {operator_name: (handle, ggr)}
    tax_data: {operator_name: tax_amount}
    """
    url = f"https://drive.google.com/uc?id={file_id}&export=download&confirm=t"
    try:
        r = session.get(url, timeout=60, allow_redirects=True)
        if r.status_code != 200 or r.content[:5] != b"%PDF-":
            return None
    except requests.RequestException:
        return None

    return _parse_pdf(r.content)


def _parse_pdf(
    pdf_bytes: bytes,
) -> tuple[dict[str, tuple[float, float]], dict[str, float]] | None:
    """Parse a WY Combined Wagering Activity PDF for OSW data.

    Returns (operators_data, tax_data) or None.
    """
    try:
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception:
        return None

    # Find the OSW page
    for page in pdf.pages:
        text = page.extract_text() or ""
        if "ONLINE SPORTS WAGERING" not in text:
            continue

        # Try table extraction first (Format 3: Jan 2025+)
        tables = page.extract_tables()
        if tables and len(tables[0]) >= 3 and len(tables[0][0]) >= 3:
            result = _parse_format3_table(tables[0])
            if result:
                return result

        # Fall back to text parsing (Formats 1 & 2)
        return _parse_text_format(text)

    return None


def _parse_format3_table(
    table: list[list[str]],
) -> tuple[dict[str, tuple[float, float]], dict[str, float]] | None:
    """Parse Format 3 (Jan 2025+): operators as columns, metrics as rows."""
    header = table[0]
    # Header may have leading empty cols: ['', '', 'BetMGM', ...] or ['', 'BetMGM', ...]
    operators = []
    for col_idx, h in enumerate(header):
        if h and h.strip() and h.strip() != "Total":
            canonical = OPERATOR_MAP.get(h.strip().upper())
            if canonical:
                operators.append((col_idx, canonical))

    if not operators:
        return None

    handle_row = None
    ggr_row = None
    tax_row = None

    for row in table[1:]:
        # Join all cells to find the label (may be in any column)
        label = " ".join((c or "") for c in row).strip()
        if "Monthly Wagers" in label:
            handle_row = row
        elif "Gross Gaming Revenue" in label and "Taxable" not in label:
            ggr_row = row
        elif "Tax Due" in label:
            tax_row = row

    if not handle_row or not ggr_row:
        return None

    operators_data = {}
    tax_data = {}

    for col_idx, op_name in operators:
        handle = _clean_amount(handle_row[col_idx]) if col_idx < len(handle_row) else 0.0
        ggr = _clean_amount(ggr_row[col_idx]) if col_idx < len(ggr_row) else 0.0
        tax = _clean_amount(tax_row[col_idx]) if tax_row and col_idx < len(tax_row) else 0.0
        operators_data[op_name] = (handle, ggr)
        tax_data[op_name] = tax

    return operators_data, tax_data


def _parse_text_format(
    text: str,
) -> tuple[dict[str, tuple[float, float]], dict[str, float]] | None:
    """Parse Formats 1 & 2 from text: operators in rows."""
    lines = text.split("\n")
    osw_started = False
    sections = []  # list of (operator_name, [amounts])
    current_section = 0

    for line in lines:
        if "ONLINE SPORTS WAGERING" in line:
            osw_started = True
            continue

        if not osw_started:
            continue

        # Stop at next major section or footnote
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("*"):
            break

        # Skip header lines
        if stripped.startswith("Operator") or stripped.startswith("Non-Cash"):
            # If we see "Operator" again, we're in section 2
            if sections:
                current_section = 1
            continue

        if stripped.startswith("Taxable"):
            continue

        # Skip Total line but mark end of section
        if stripped.startswith("Total"):
            continue

        # Try to match an operator line
        op_match = None
        for op_key, op_name in OPERATOR_MAP.items():
            if stripped.upper().startswith(op_key):
                op_match = op_name
                break

        if not op_match:
            continue

        # Extract all dollar amounts from the line
        amounts = _extract_amounts(stripped)
        if amounts:
            sections.append((op_match, current_section, amounts))

    if not sections:
        return None

    # Determine format based on section structure
    # Format 1: all in section 0, 6 amounts per operator
    # Format 2: split across sections 0 and 1, 3 amounts each
    max_section = max(s for _, s, _ in sections)

    operators_data = {}
    tax_data = {}

    if max_section == 0:
        # Format 1: single section
        for op_name, _, amounts in sections:
            if len(amounts) >= 4:
                handle = amounts[0]
                # Amounts: [Handle, CashPayouts, NonCashPayouts, GGR, TaxableGGR, Tax]
                ggr = amounts[3] if len(amounts) >= 4 else 0.0
                tax = amounts[5] if len(amounts) >= 6 else 0.0
                operators_data[op_name] = (handle, ggr)
                tax_data[op_name] = tax
    else:
        # Format 2: two sections
        section0 = {op: amounts for op, sec, amounts in sections if sec == 0}
        section1 = {op: amounts for op, sec, amounts in sections if sec == 1}

        for op_name in set(list(section0.keys()) + list(section1.keys())):
            handle = section0.get(op_name, [0.0])[0]
            ggr_amounts = section1.get(op_name, [0.0, 0.0, 0.0])
            ggr = ggr_amounts[0] if ggr_amounts else 0.0
            tax = ggr_amounts[2] if len(ggr_amounts) >= 3 else 0.0
            operators_data[op_name] = (handle, ggr)
            tax_data[op_name] = tax

    return operators_data, tax_data if operators_data else None


def _extract_amounts(line: str) -> list[float]:
    """Extract all dollar amounts from a line, handling negatives in parens."""
    amounts = []
    # Match: $ 1,234.56 or $ (1,234.56) or $ - (with possible spaces in numbers)
    for m in re.finditer(r"\$\s*(\([\d,\s]+\.?\d*\)|[\d,\s]+\.?\d*|-)", line):
        val_str = m.group(1).strip()
        if val_str == "-":
            amounts.append(0.0)
        elif val_str.startswith("("):
            amounts.append(-float(val_str.strip("()").replace(",", "").replace(" ", "")))
        else:
            amounts.append(float(val_str.replace(",", "").replace(" ", "")))
    return amounts


def _clean_amount(s: str | None) -> float:
    """Clean a dollar amount string from a table cell."""
    if not s:
        return 0.0
    s = s.strip()
    if s == "-" or s == "$ -" or not s:
        return 0.0
    # Remove $ sign
    s = s.replace("$", "").strip()
    # Handle negative (parenthesized)
    neg = False
    if s.startswith("("):
        neg = True
        s = s.strip("()")
    # Remove commas and spaces within numbers (PDF artifact)
    s = s.replace(",", "").replace(" ", "").strip()
    if not s or s == "-":
        return 0.0
    val = float(s)
    return -val if neg else val
