"""Michigan sports betting scraper — MGCB Excel revenue reports.

Downloads Internet Sports Betting (XLSX) and Retail Sports Betting (XLS) files
from the Michigan Gaming Control Board.

Internet SB (online): 15-16 platform providers across commercial and tribal casinos.
  - Commercial (5.88% tax on AGSWR): MGM Grand Detroit, MotorCity Casino, Greektown Casino
  - Tribal (8.4% payment on AGSWR): 12+ tribal casino partnerships
Retail SB: 3 Detroit casinos (MGM Grand, MotorCity, Greektown), 3.78% tax on QAGR.

Internal tracking: Each record is tagged as 'online' or 'retail' source.
Eventually we may need to strip out online-only data.

Platform provider → consumer brand mapping:
  BetMGM (MGM Grand) → BetMGM
  FanDuel (MotorCity) → FanDuel
  Penn/Barstool (Greektown) → ESPN Bet
  DraftKings (Bay Mills) → DraftKings
  William Hill (Grand Traverse) → Caesars
  PointsBet (Lac Vieux Desert) → Fanatics
  Rush Street (Little River) → Rush Street Interactive
  Others: NYX Digital, Parx, TwinSpires/Hard Rock, Golden Nugget, FoxBet, Pala, GAN, Wynn
"""

import io
import re
from collections import defaultdict

import pandas as pd

from .base import BaseScraper
from .utils import get_session, clean_dollar_value

PAGE_URL = "https://www.michigan.gov/mgcb/detroit-casinos/resources/revenues-and-wagering-tax-information"
BASE_URL = "https://www.michigan.gov"

MONTH_NUM = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}

# Map platform provider names → consumer-facing brand names.
# Partial match is used (key.lower() in name.lower()).
PLATFORM_TO_BRAND = {
    "BetMGM": "BetMGM",
    "FanDuel": "FanDuel",
    "Penn Sports Interactive": "ESPN Bet",
    "Barstool": "ESPN Bet",
    "DraftKings": "DraftKings",
    "William Hill": "Caesars",
    "PointsBet": "Fanatics",
    "Rush Street": "Rush Street Interactive",
    "NYX Digital": "Others",
    "Parx Interactive": "Others",
    "TwinSpires": "Others",
    "Hard Rock": "Others",
    "Golden Nugget": "Others",
    "FoxBet": "Others",
    "Pala Interactive": "Others",
    "GAN": "Others",
    "Wynn": "Others",
}

RETAIL_BRAND = "Retail (Detroit)"


class MIScraper(BaseScraper):
    STATE_CODE = "mi"
    STATE_NAME = "Michigan"
    TAX_RATE = 0.0588
    TAX_RATE_NOTE = "5.88% commercial online, 8.4% tribal online, 3.78% retail on AGSWR/QAGR"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = PAGE_URL
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2021-01-22"
    GGR_DEFINITION = "Gross Sports Betting Receipts (Handle − Payouts)"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tax_data = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        session = get_session()

        isb_urls, rsb_urls = self._find_file_urls(session)
        if not isb_urls and not rsb_urls:
            print("  No file URLs found.")
            return {}

        print(f"  Found {len(isb_urls)} Internet SB + {len(rsb_urls)} Retail SB files.")

        brand_records = defaultdict(list)
        tax_records = defaultdict(list)

        # Parse Internet SB files (newest first so newer revisions win)
        years_seen_isb = set()
        for url in self._sort_urls_by_year(isb_urls):
            try:
                recs = self._parse_isb_file(session, url, years_seen_isb)
                for rec in recs:
                    brand_records[rec["brand"]].append(rec)
                    tax_records[rec["brand"]].append({"date": rec["date"], "tax": rec["tax"]})
            except Exception as e:
                fname = url.split("/")[-1].split("?")[0][:50]
                print(f"    Error parsing ISB {fname}: {e}")

        # Parse Retail SB files (newest first; older files may be encrypted/protected)
        years_seen_rsb = set()
        for url in self._sort_urls_by_year(rsb_urls):
            try:
                recs = self._parse_rsb_file(session, url, years_seen_rsb)
                for rec in recs:
                    brand_records[rec["brand"]].append(rec)
                    tax_records[rec["brand"]].append({"date": rec["date"], "tax": rec["tax"]})
            except Exception as e:
                err_msg = str(e)
                if "encrypt" in err_msg.lower():
                    fname = url.split("/")[-1].split("?")[0][:50]
                    print(f"    Skipping encrypted RSB file: {fname}")
                else:
                    fname = url.split("/")[-1].split("?")[0][:50]
                    print(f"    Error parsing RSB {fname}: {e}")

        if not brand_records:
            print("  No data parsed.")
            return {}

        # Cap retail data at the max ISB date to avoid incomplete months
        # (RSB files may be published before new ISB data is available)
        isb_dates = set()
        for brand, recs in brand_records.items():
            if brand != RETAIL_BRAND:
                for rec in recs:
                    isb_dates.add(rec["date"])

        if isb_dates and RETAIL_BRAND in brand_records:
            max_isb = max(isb_dates)
            brand_records[RETAIL_BRAND] = [
                r for r in brand_records[RETAIL_BRAND] if r["date"] <= max_isb
            ]
            tax_records[RETAIL_BRAND] = [
                r for r in tax_records[RETAIL_BRAND] if r["date"] <= max_isb
            ]

        result = {}
        tax_result = {}
        for brand, records in sorted(brand_records.items()):
            df = pd.DataFrame(records)
            df["date"] = pd.to_datetime(df["date"])
            # Sum by date: multiple platforms may map to same brand (e.g. "Others")
            df = df.groupby("date").agg({"handle": "sum", "ggr": "sum"}).reset_index()
            df = df.sort_values("date")
            result[brand] = df[["date", "handle", "ggr"]]

            tdf = pd.DataFrame(tax_records[brand])
            tdf["date"] = pd.to_datetime(tdf["date"])
            tdf = tdf.groupby("date").agg({"tax": "sum"}).reset_index()
            tdf = tdf.sort_values("date")
            tdf = tdf.rename(columns={"tax": "handle"})
            tax_result[brand] = tdf[["date", "handle"]]

            print(f"    {brand}: {len(df)} months")

        self._tax_data = tax_result
        return result

    def run(self):
        """Override run to use actual tax values from Excel files."""
        result = super().run()

        if self._tax_data and not result.ggr_pivot.empty:
            tax_pivot = self.build_pivot(self._tax_data, "handle")

            path = self.state_dir / "tax_revenue.csv"
            tax_pivot.to_csv(path, index=True, date_format="%Y-%m-%d")
            print(f"  Rewrote tax_revenue.csv (actual tax from Excel files)")

            latest_date = result.handle_pivot.index.max()
            if latest_date in tax_pivot.index:
                latest_tax = tax_pivot.loc[latest_date, "Total"]
                if pd.notna(latest_tax) and result.metadata:
                    result.metadata["latestData"]["taxRevenue"] = round(float(latest_tax), 2)

            result = result.__class__(
                state_code=result.state_code,
                state_name=result.state_name,
                handle_pivot=result.handle_pivot,
                ggr_pivot=result.ggr_pivot,
                hold_pivot=result.hold_pivot,
                yoy_handle=result.yoy_handle,
                yoy_ggr=result.yoy_ggr,
                tax_revenue=tax_pivot,
                sports_handle=result.sports_handle,
                metadata=result.metadata,
            )

        return result

    # ── URL discovery ──────────────────────────────────────────────

    def _find_file_urls(self, session):
        """Scrape the MGCB page for ISB (XLSX) and RSB (XLS) download URLs."""
        isb_urls = []
        rsb_urls = []

        try:
            resp = session.get(PAGE_URL, timeout=30)
            resp.raise_for_status()
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")

            for a in soup.find_all("a", href=True):
                href = a["href"]
                href_lower = href.lower()

                # Internet Sports Betting XLSX files
                if ("internet-sports-betting" in href_lower
                        or "internet_sports_betting" in href_lower):
                    if ".xlsx" in href_lower:
                        full = href if href.startswith("http") else BASE_URL + href
                        isb_urls.append(full)

                # Retail Sports Betting XLS files
                elif "rsb" in href_lower or "retail" in href_lower.replace("-", " "):
                    if ".xls" in href_lower and ".xlsx" not in href_lower:
                        full = href if href.startswith("http") else BASE_URL + href
                        rsb_urls.append(full)

        except Exception as e:
            print(f"  Error fetching page: {e}")

        return isb_urls, rsb_urls

    @staticmethod
    def _sort_urls_by_year(urls: list[str]) -> list[str]:
        """Sort URLs from newest to oldest based on year in filename."""
        def max_year(url):
            fname = url.split("/")[-1].split("?")[0]
            years = re.findall(r"20\d{2}", fname)
            return max(int(y) for y in years) if years else 0
        return sorted(urls, key=max_year, reverse=True)

    # ── Platform → brand mapping ──────────────────────────────────

    @staticmethod
    def _map_platform(name: str) -> str:
        """Map a platform provider name to consumer brand."""
        name = name.strip()
        for key, brand in PLATFORM_TO_BRAND.items():
            if key.lower() in name.lower():
                return brand
        return "Others"

    # ── Internet Sports Betting (XLSX) parser ─────────────────────

    def _parse_isb_file(self, session, url: str, years_seen: set) -> list[dict]:
        """Parse an Internet Sports Betting XLSX file (may contain 1-2 year sheets)."""
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        content = io.BytesIO(resp.content)

        xls = pd.ExcelFile(content, engine="openpyxl")
        records = []

        for sheet_name in xls.sheet_names:
            year_match = re.search(r"(\d{4})", sheet_name)
            if not year_match:
                continue
            year = int(year_match.group(1))

            if year in years_seen:
                continue  # A newer file already provided this year
            years_seen.add(year)

            df = pd.read_excel(content, sheet_name=sheet_name, header=None, engine="openpyxl")

            # Row 3: Platform providers at their start columns
            providers = []
            for col_idx in range(1, df.shape[1]):
                val = df.iloc[3, col_idx] if col_idx < df.shape[1] else None
                if pd.notna(val):
                    name = str(val).strip()
                    if name and name.lower() != "platform providers":
                        providers.append((col_idx, name))

            if not providers:
                continue

            # Rows 6–17: monthly data (Jan–Dec)
            for row_idx in range(6, min(18, len(df))):
                month_val = df.iloc[row_idx, 0]
                if pd.isna(month_val):
                    continue
                month_str = str(month_val).strip()
                if month_str.upper() in ("TOTAL", ""):
                    continue

                month_num = MONTH_NUM.get(month_str)
                if not month_num:
                    continue

                date_str = f"{year}-{month_num:02d}-01"

                for col_start, platform_name in providers:
                    handle = clean_dollar_value(df.iloc[row_idx, col_start])
                    ggr = clean_dollar_value(df.iloc[row_idx, col_start + 1])
                    tax = clean_dollar_value(df.iloc[row_idx, col_start + 3])

                    if not handle or handle == 0:
                        continue

                    records.append({
                        "brand": self._map_platform(platform_name),
                        "date": date_str,
                        "handle": handle,
                        "ggr": ggr if ggr is not None else 0.0,
                        "tax": tax if tax is not None else 0.0,
                        "source": "online",
                    })

            fname = url.split("/")[-1].split("?")[0][:50]
            print(f"    Parsed ISB {year} from {fname}")

        return records

    # ── Retail Sports Betting (XLS) parser ────────────────────────

    def _parse_rsb_file(self, session, url: str, years_seen: set) -> list[dict]:
        """Parse a Retail Sports Betting XLS file (may contain 1-2 year sheets)."""
        resp = session.get(url, timeout=60)
        resp.raise_for_status()

        import xlrd
        workbook = xlrd.open_workbook(file_contents=resp.content)
        records = []

        for sheet_name in workbook.sheet_names():
            year_match = re.search(r"(\d{4})", sheet_name)
            if not year_match:
                continue
            year = int(year_match.group(1))

            if year in years_seen:
                continue
            years_seen.add(year)

            sheet = workbook.sheet_by_name(sheet_name)

            # Find "All Detroit Casinos" total column in row 1
            total_col = self._find_rsb_total_col(sheet)

            # Data rows start at row 3 (after title row 0, casino names row 1, headers row 2)
            for row_idx in range(3, min(15, sheet.nrows)):
                month_val = sheet.cell_value(row_idx, 0)
                if not month_val:
                    continue
                month_str = str(month_val).strip()
                if month_str.upper() in ("TOTAL", ""):
                    continue

                month_num = MONTH_NUM.get(month_str)
                if not month_num:
                    continue

                date_str = f"{year}-{month_num:02d}-01"

                if total_col is not None:
                    handle = clean_dollar_value(sheet.cell_value(row_idx, total_col))
                    ggr = clean_dollar_value(sheet.cell_value(row_idx, total_col + 1))
                    tax = clean_dollar_value(sheet.cell_value(row_idx, total_col + 3))
                else:
                    # Fallback: sum individual casinos at cols 1, 5, 9
                    handle, ggr, tax = 0.0, 0.0, 0.0
                    for c in (1, 5, 9):
                        h = clean_dollar_value(sheet.cell_value(row_idx, c))
                        g = clean_dollar_value(sheet.cell_value(row_idx, c + 1))
                        t = clean_dollar_value(sheet.cell_value(row_idx, c + 3))
                        if h:
                            handle += h
                        if g:
                            ggr += g
                        if t:
                            tax += t

                if not handle or handle == 0:
                    continue

                records.append({
                    "brand": RETAIL_BRAND,
                    "date": date_str,
                    "handle": handle,
                    "ggr": ggr if ggr is not None else 0.0,
                    "tax": tax if tax is not None else 0.0,
                    "source": "retail",
                })

            print(f"    Parsed RSB {year}")

        return records

    @staticmethod
    def _find_rsb_total_col(sheet) -> int | None:
        """Find the 'All Detroit Casinos' total column in row 1."""
        for col_idx in range(sheet.ncols):
            val = sheet.cell_value(1, col_idx)
            if val and "all detroit" in str(val).lower():
                return col_idx
        return None
