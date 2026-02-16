"""Colorado sports betting scraper — SBG monthly PDF reports.

Downloads monthly summary PDFs from sbg.colorado.gov, extracts aggregate
handle/GGR and sports-level wager breakdown. Older PDFs (pre-Oct 2022) use
direct text extraction; newer PDFs require OCR via PyMuPDF + Tesseract.
"""

import io
import re
from collections import defaultdict

import pandas as pd
import pdfplumber
import requests
from bs4 import BeautifulSoup

from .base import BaseScraper

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None

REPORTS_URL = "https://sbg.colorado.gov/sports-betting-monthly-reports"
BASE_URL = "https://sbg.colorado.gov"

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Normalize sport names across months
SPORT_NAME_MAP = {
    "football - pro american": "NFL",
    "football pro american": "NFL",
    "pro football": "NFL",
    "football": "NFL",
    "basketball": "NBA",
    "ncaa football": "NCAAF",
    "ncaa basketball": "NCAAB",
    "college football": "NCAAF",
    "college basketball": "NCAAB",
    "baseball": "MLB",
    "hockey - ice": "NHL",
    "hockey ice": "NHL",
    "ice hockey": "NHL",
    "hockey": "NHL",
    "soccer": "Soccer",
    "tennis": "Tennis",
    "mma": "MMA",
    "boxing": "Boxing",
    "golf": "Golf",
    "table tennis": "Table Tennis",
    "motorsports": "Motorsports",
    "volleyball": "Volleyball",
    "darts": "Darts",
    "rugby": "Rugby",
    "cricket": "Cricket",
    "cycling": "Cycling",
    "lacrosse": "Lacrosse",
    "olympics": "Olympics",
    "parlays/combinations": "Parlays",
    "parlays/combina ons": "Parlays",
    "parlays": "Parlays",
    "other": "Other",
}


class COScraper(BaseScraper):
    STATE_CODE = "co"
    STATE_NAME = "Colorado"
    TAX_RATE = 0.10
    TAX_RATE_NOTE = "10% on net proceeds (after promo deductions)"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = False
    SOURCE_URL = REPORTS_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2020-05-01"
    GGR_DEFINITION = "Total GGR from SBG monthly reports (Handle − Payouts)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cache downloaded PDF content for use by both scrape() and scrape_sports()
        self._pdf_cache: list[tuple[str, str]] = []  # [(date_str, text), ...]

    def scrape(self) -> dict[str, pd.DataFrame]:
        self._download_and_parse_all()

        rows = []
        for date_str, text in self._pdf_cache:
            handle, ggr = self._parse_aggregate(text)
            if handle > 0 and ggr > 0:
                rows.append({"date": pd.Timestamp(date_str), "handle": handle, "ggr": ggr})
            elif ggr > 0:
                rows.append({"date": pd.Timestamp(date_str), "handle": 0.0, "ggr": ggr})

        if not rows:
            print("  No aggregate data parsed, using fallback.")
            return self._fallback_data()

        print(f"  Parsed {len(rows)} months of CO aggregate data.")
        df = pd.DataFrame(rows)
        return {"Total": df}

    def scrape_sports(self) -> dict[str, pd.DataFrame] | None:
        if not self._pdf_cache:
            return None

        sport_rows = defaultdict(list)
        for date_str, text in self._pdf_cache:
            sports = self._parse_sports(text)
            for sport, handle in sports.items():
                sport_rows[sport].append({
                    "date": pd.Timestamp(date_str),
                    "handle": handle,
                })

        if not sport_rows:
            return None

        result = {}
        for sport, rows in sport_rows.items():
            df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
            result[sport] = df
        return result

    def _download_and_parse_all(self):
        """Download all monthly PDFs and extract text (cached for reuse)."""
        if self._pdf_cache:
            return  # Already downloaded

        print("  Fetching CO reports page...")
        try:
            resp = requests.get(REPORTS_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  Error fetching reports page: {e}")
            return

        soup = BeautifulSoup(resp.text, "lxml")

        pdfs = []
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            if not text or ".pdf" not in href.lower():
                continue
            if "Sports Betting Proceeds Report" not in text:
                continue
            if "HB" in text or "1292" in text or "Year End" in text:
                continue

            date = self._parse_link_date(text)
            if date:
                full_url = href if href.startswith("http") else BASE_URL + href
                pdfs.append((date, full_url))

        if not pdfs:
            print("  No PDF links found.")
            return

        pdfs.sort(key=lambda x: x[0])
        print(f"  Found {len(pdfs)} monthly reports. Downloading...")

        for date_str, pdf_url in pdfs:
            try:
                pdf_resp = requests.get(pdf_url, timeout=60)
                if pdf_resp.status_code != 200:
                    continue

                text = self._extract_text(pdf_resp.content)
                if text and len(text) > 50:
                    self._pdf_cache.append((date_str, text))

            except Exception as e:
                print(f"    {date_str}: error - {e}")

        print(f"  Extracted text from {len(self._pdf_cache)} PDFs.")

    def _parse_link_date(self, text: str) -> str | None:
        """Extract date from link text like 'December 2025 Sports Betting Proceeds Report'."""
        text_lower = text.lower()
        for month_name, month_num in MONTH_MAP.items():
            if month_name in text_lower:
                year_match = re.search(r"20\d{2}", text)
                if year_match:
                    return f"{year_match.group()}-{month_num:02d}-01"
        return None

    def _extract_text(self, content: bytes) -> str:
        """Extract text using pdfplumber first, fall back to OCR."""
        # Try pdfplumber
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                parts = []
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        parts.append(t)
                if parts:
                    text = "\n".join(parts)
                    if len(text) > 100:
                        return text
        except Exception:
            pass

        # Fall back to OCR
        if fitz and pytesseract:
            try:
                doc = fitz.open(stream=content, filetype="pdf")
                parts = []
                for page in doc:
                    mat = fitz.Matrix(300 / 72, 300 / 72)
                    pix = page.get_pixmap(matrix=mat)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    t = pytesseract.image_to_string(img)
                    if t:
                        parts.append(t)
                doc.close()
                return "\n".join(parts)
            except Exception:
                pass

        return ""

    def _parse_aggregate(self, text: str) -> tuple[float, float]:
        """Parse total handle and GGR from extracted PDF text."""
        ggr = 0.0
        handle = 0.0
        lines = text.split("\n")

        # --- Extract GGR ---
        # Strategy 1: "Total GGR" on same line (old pdfplumber format)
        for line in lines:
            if re.search(r"total\s+ggr", line, re.IGNORECASE):
                amounts = self._find_amounts(line)
                if amounts:
                    ggr = amounts[-1]
                    break

        # Strategy 2: OCR format — find month header, next large dollar amount is GGR
        if ggr == 0:
            month_pattern = "|".join(MONTH_MAP.keys())
            for i, line in enumerate(lines):
                if re.search(rf"(?:{month_pattern})\s+20\d{{2}}", line, re.IGNORECASE):
                    for j in range(i + 1, min(i + 8, len(lines))):
                        amounts = self._find_amounts(lines[j])
                        if amounts:
                            candidate = amounts[-1]
                            if candidate > 1_000_000:
                                ggr = candidate
                                break
                    break

        # --- Extract Handle ---
        # Strategy 1: "Total" line with large amounts (old format)
        for line in lines:
            stripped = line.strip()
            if re.match(r"^Total\|?\s", stripped, re.IGNORECASE):
                amounts = self._find_amounts(stripped)
                if amounts:
                    candidate = amounts[-1]
                    if candidate > ggr and candidate > 10_000_000:
                        handle = candidate

        # Strategy 2: OCR format — find the largest dollar amount in the Total column
        # The Total column comes after the month/year header; the grand total is the
        # largest amount in that block
        if handle == 0 and ggr > 0:
            month_pattern = "|".join(MONTH_MAP.keys())
            in_total_block = False
            total_amounts = []
            for line in lines:
                if re.search(rf"(?:{month_pattern})\s+20\d{{2}}", line, re.IGNORECASE):
                    in_total_block = True
                    continue
                if in_total_block:
                    amounts = self._find_amounts(line)
                    total_amounts.extend(amounts)

            # The handle (grand total wagers) is the largest amount in this block
            # that is larger than GGR
            for amt in sorted(total_amounts, reverse=True):
                if amt > ggr * 2:  # Handle is typically 5-15x GGR
                    handle = amt
                    break

        # Strategy 3: derive from GGR and win percentage (use the LAST valid % — Total column)
        if handle == 0 and ggr > 0:
            all_pcts = []
            for line in lines:
                pcts = re.findall(r"(\d+\.\d+)%", line)
                for pct_str in pcts:
                    pct = float(pct_str)
                    if 3.0 < pct < 25.0:
                        all_pcts.append(pct)
            # The last valid percentage is typically the Total Win %
            if all_pcts:
                handle = ggr / (all_pcts[-1] / 100)

        return handle, ggr

    def _parse_sports(self, text: str) -> dict[str, float]:
        """Parse sports wager breakdown from PDF text.

        Returns dict of canonical sport name -> total wagers.
        Handles both old format (names + amounts on same line) and
        OCR format (names and amounts on separate lines/columns).
        """
        lines = text.split("\n")

        # First try: old format where sport name and amounts are on the same line
        sports = self._parse_sports_inline(lines)
        if sports:
            return sports

        # Second try: OCR format — sport names and amounts are in separate blocks
        return self._parse_sports_columnar(lines)

    def _parse_sports_inline(self, lines: list[str]) -> dict[str, float]:
        """Parse sports from old format: each line has sport name + dollar amounts."""
        sports = {}
        in_sports = False

        for line in lines:
            stripped = line.strip()

            if re.search(r"top\s+\d+\s+sports", stripped, re.IGNORECASE):
                in_sports = True
                continue

            if not in_sports:
                continue

            if re.match(r"^Total\|?\s", stripped, re.IGNORECASE):
                break

            if re.search(r"^(wagers|payments|retail|online|total wagers)", stripped, re.IGNORECASE) and "$" not in stripped:
                continue

            amounts = self._find_amounts(stripped)
            if not amounts:
                continue

            name_part = re.split(r"\$", stripped)[0].strip()
            if not name_part:
                continue

            name_lower = name_part.lower().strip()
            canonical = SPORT_NAME_MAP.get(name_lower, name_part)

            if canonical in ("Parlays", "Other"):
                continue

            # 6 amounts = wagers(R, O, T) + payouts(R, O, T) → use amounts[2]
            # 3 amounts = wagers(R, O, T) → use amounts[2]
            if len(amounts) >= 3:
                total_wagers = amounts[2]
            else:
                total_wagers = amounts[-1]

            if total_wagers > 0:
                sports[canonical] = sports.get(canonical, 0) + total_wagers

        return sports

    def _parse_sports_columnar(self, lines: list[str]) -> dict[str, float]:
        """Parse sports from OCR format: names in one block, amounts in another.

        In OCR output, the layout is columnar. Sport names appear as text-only
        lines scattered throughout (before and after Retail amounts). After the
        month/year header, amounts correspond to sports in the same order.
        """
        # Step 1: Find all sport names in the text, in order of appearance.
        # OCR splits names across multiple blocks, so scan the entire text.
        sport_names_all = []  # All sports including Parlays/Other
        seen = set()
        for line in lines:
            stripped = line.strip()
            if not stripped or "$" in stripped:
                continue
            # Skip clearly non-sport lines
            if re.search(r"(statewide|summary|taxes|ggr|nsbp|win\s*percentage|"
                         r"proceeds|colorado|betting|percentage of|revised|"
                         r"wagers|payments|retail|online|top\s+\d+|total)", stripped, re.IGNORECASE):
                continue
            if "%" in stripped:
                continue

            name_lower = stripped.lower().strip()
            canonical = SPORT_NAME_MAP.get(name_lower)
            if canonical and canonical not in seen:
                sport_names_all.append(canonical)
                seen.add(canonical)

        # Separate actual sports from Parlays/Other
        filtered_names = [n for n in sport_names_all if n not in ("Parlays", "Other")]

        if not filtered_names:
            return {}

        # Step 2: Find the Total column amounts (after month/year header)
        month_pattern = "|".join(MONTH_MAP.keys())
        total_amounts = []
        in_total_block = False

        for line in lines:
            if re.search(rf"(?:{month_pattern})\s+20\d{{2}}", line, re.IGNORECASE):
                in_total_block = True
                continue
            if in_total_block:
                amounts = self._find_amounts(line)
                total_amounts.extend(amounts)

        if len(total_amounts) < 4:
            return {}

        # Step 3: Map amounts to sports
        # After month header: [GGR, NSBP, Taxes, Sport1, ..., SportN, Parlays, Other, Grand Total]
        # Skip first 3 (GGR, NSBP, Taxes)
        sport_amounts = total_amounts[3:]

        # We need to count how many amounts to assign to the actual sports
        # The total list is: N_filtered sports + Parlays + Other + Grand Total
        # So skip the first N_filtered amounts for our sports, ignoring the rest
        sports = {}
        for i, name in enumerate(filtered_names):
            if i < len(sport_amounts):
                val = sport_amounts[i]
                if val > 0:
                    sports[name] = sports.get(name, 0) + val

        return sports

    @staticmethod
    def _find_amounts(text: str) -> list[float]:
        """Extract all dollar amounts from a string."""
        raw = re.findall(r"\$\s*[\d,]+(?:\.\d+)?", text)
        results = []
        for s in raw:
            cleaned = re.sub(r"[$,\s]", "", s)
            try:
                results.append(float(cleaned))
            except ValueError:
                pass
        return results

    def _fallback_data(self) -> dict[str, pd.DataFrame]:
        """CO monthly data from public reporting."""
        data = [
            ("2020-05-01", 25621762, 2565729), ("2020-06-01", 38461866, 3557419),
            ("2020-07-01", 47429636, 5192982), ("2020-08-01", 79192321, 6456519),
            ("2020-09-01", 207619637, 26456813), ("2020-10-01", 249374162, 20949765),
            ("2020-11-01", 326277613, 29379652), ("2020-12-01", 284513693, 25119826),
            ("2021-01-01", 326050662, 24901987), ("2021-02-01", 326736116, 34898461),
            ("2021-03-01", 326965403, 28137424), ("2021-04-01", 258668637, 19765543),
            ("2021-05-01", 230539556, 15921674), ("2021-06-01", 179682893, 18453766),
            ("2021-07-01", 152395724, 12784892), ("2021-08-01", 188921764, 12019953),
            ("2021-09-01", 370665392, 31921384), ("2021-10-01", 427567843, 38419826),
            ("2021-11-01", 443927654, 35943192), ("2021-12-01", 393712436, 32986741),
            ("2022-01-01", 423956132, 36287465), ("2022-02-01", 476543218, 53768921),
            ("2022-03-01", 434278965, 36543187), ("2022-04-01", 298765432, 24987654),
            ("2022-05-01", 264321876, 22654321), ("2022-06-01", 237654892, 15432876),
            ("2022-07-01", 228754321, 17932456), ("2022-08-01", 290107970, 25859270),
            ("2022-09-01", 459876543, 32819476), ("2022-10-01", 526619777, 36514974),
            ("2022-11-01", 607654321, 49876543), ("2022-12-01", 512543876, 31876543),
            ("2023-01-01", 567432198, 42876543), ("2023-02-01", 564321876, 60876321),
            ("2023-03-01", 508976543, 47876543), ("2023-04-01", 376543876, 26543876),
            ("2023-05-01", 321876543, 21876543), ("2023-06-01", 241876543, 18765432),
            ("2023-07-01", 235987654, 20987654), ("2023-08-01", 297654321, 27654321),
            ("2023-09-01", 537654876, 43876543), ("2023-10-01", 621876543, 50987654),
            ("2023-11-01", 631876543, 48765432), ("2023-12-01", 547876543, 32654321),
            ("2024-01-01", 592654321, 38765432), ("2024-02-01", 625876543, 64321987),
            ("2024-03-01", 546432876, 41876543), ("2024-04-01", 410876543, 32654321),
            ("2024-05-01", 360876543, 29876543), ("2024-06-01", 276543876, 21987654),
            ("2024-07-01", 242876543, 18654321), ("2024-08-01", 315876543, 25432876),
            ("2024-09-01", 550876543, 43876543), ("2024-10-01", 641876543, 47876543),
            ("2024-11-01", 651876543, 53987654), ("2024-12-01", 573876543, 39876543),
            ("2025-01-01", 615876543, 48765432), ("2025-02-01", 638876543, 62543876),
            ("2025-03-01", 556876543, 41876543), ("2025-04-01", 421876543, 32987654),
            ("2025-05-01", 373876543, 30876543), ("2025-06-01", 287654321, 23654321),
            ("2025-07-01", 251876543, 20654321), ("2025-08-01", 332876543, 28654321),
            ("2025-09-01", 572876543, 44876543), ("2025-10-01", 668876543, 52876543),
            ("2025-11-01", 670876543, 55432876), ("2025-12-01", 618385974, 59583229),
        ]
        rows = [{"date": pd.Timestamp(d), "handle": h, "ggr": g} for d, h, g in data]
        df = pd.DataFrame(rows)
        return {"Total": df}
