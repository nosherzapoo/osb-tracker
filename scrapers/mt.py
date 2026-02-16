"""Montana sports betting scraper — sportsbetmontana.com weekly + monthly PDFs.

Montana Lottery operates sports betting through Intralot retailers.
Reports available from January 2025 in both weekly and monthly formats.

Weekly PDFs: Sports_Bet_Montana_Activity_WE_{M.D.YY}.pdf (Saturdays)
Monthly PDFs: Sports_Bet_Montana_Activity_{MonthName}_{YYYY}.pdf

Each PDF (1 page): Project-to-date totals, period activity (Handle, Payout,
GGR, Retailer Commissions), and Activity by Sport Detail table.

Montana is lottery-operated — no traditional tax. State revenue = GGR minus
retailer commissions (~13% of GGR).
"""

import io
import re
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import pdfplumber
import requests

from .base import BaseScraper, ScraperResult

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

SPORT_MAP = {
    "FOOTBALL": "Football",
    "BASKETBALL": "Basketball",
    "ICE HOCKEY": "Ice Hockey",
    "SOCCER": "Soccer",
    "SPECIALS": "Specials",
    "MMA": "MMA",
    "TENNIS": "Tennis",
    "GOLF": "Golf",
    "TABLE TENNIS": "Table Tennis",
    "BOXING": "Boxing",
    "OTHER": "Other",
}

BASE_URL = "https://sportsbetmontana.com/static/assets"


class MTScraper(BaseScraper):
    STATE_CODE = "mt"
    STATE_NAME = "Montana"
    TAX_RATE = 0.0
    TAX_RATE_NOTE = "Lottery-operated; state revenue = GGR minus retailer commissions"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = False
    SOURCE_URL = "https://sportsbetmontana.com/en/view/news"
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2020-03-11"
    GGR_DEFINITION = "Handle minus Payouts"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._monthly_cache = None  # list of {date, handle, ggr, commissions, sports}
        self._weekly_cache = None
        self._monthly_sports = None
        self._weekly_sports = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        """Scrape monthly PDFs — returns {"total": df}."""
        self._monthly_cache = self._scrape_pdfs("monthly")
        if not self._monthly_cache:
            return {}

        self._monthly_sports = self._build_sports_dict(self._monthly_cache)

        df = pd.DataFrame(self._monthly_cache)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates(subset="date", keep="last")

        print(f"  Monthly: {len(df)} months, "
              f"${df['handle'].iloc[-1]:,.0f} handle latest, "
              f"{len(self._monthly_sports)} sports tracked")

        return {"total": df[["date", "handle", "ggr"]].reset_index(drop=True)}

    def scrape_sports(self) -> dict[str, pd.DataFrame] | None:
        return self._monthly_sports

    def run(self) -> ScraperResult:
        """Full pipeline: monthly (standard) + weekly (supplemental) data."""
        # ── Monthly ───────────────────────────────────────────────
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

        # Tax = GGR - Retailer Commissions (from cached data)
        tax_revenue = self._build_tax_from_cache(self._monthly_cache, ggr_pivot)
        self.write_csvs(handle_pivot, ggr_pivot, hold_pivot, yoy_handle, yoy_ggr, tax_revenue)

        # Monthly sports
        sports_handle = pd.DataFrame()
        if self._monthly_sports:
            sports_handle = self.build_pivot(self._monthly_sports, "handle")
            path = self.state_dir / "sports_handle.csv"
            sports_handle.to_csv(path, index=True, date_format="%Y-%m-%d")
            print(f"  Wrote sports_handle.csv ({len(sports_handle)} periods, "
                  f"{len(self._monthly_sports)} sports)")

        # ── Weekly ────────────────────────────────────────────────
        has_weekly = False
        self._weekly_cache = self._scrape_pdfs("weekly")
        if self._weekly_cache:
            has_weekly = True
            self._weekly_sports = self._build_sports_dict(self._weekly_cache)
            self._write_weekly_csvs()

        metadata = self.build_metadata(handle_pivot, ggr_pivot, sports_handle)
        metadata["hasWeeklyData"] = has_weekly
        # Fix latestData.taxRevenue (base uses TAX_RATE=0, we need actual value)
        if self._monthly_cache:
            latest = sorted(self._monthly_cache, key=lambda x: x["date"])[-1]
            metadata["latestData"]["taxRevenue"] = round(
                latest["ggr"] - latest["commissions"], 2
            )

        return ScraperResult(
            state_code=self.STATE_CODE, state_name=self.STATE_NAME,
            handle_pivot=handle_pivot, ggr_pivot=ggr_pivot,
            hold_pivot=hold_pivot, yoy_handle=yoy_handle,
            yoy_ggr=yoy_ggr, tax_revenue=tax_revenue,
            sports_handle=sports_handle, metadata=metadata,
        )

    # ── Helpers ────────────────────────────────────────────────────

    def _scrape_pdfs(self, freq: str) -> list[dict]:
        """Download and parse all PDFs of given frequency. Returns list of records."""
        if freq == "monthly":
            urls = self._find_monthly_urls()
        else:
            urls = self._find_weekly_urls()

        if not urls:
            print(f"  No {freq} PDF URLs found.")
            return []

        print(f"  Found {len(urls)} {freq} PDFs.")
        records = []
        for url, date_str in urls:
            result = _download_and_parse(url)
            if result is None:
                continue
            handle, ggr, commissions, sports = result
            records.append({
                "date": date_str,
                "handle": handle,
                "ggr": ggr,
                "commissions": commissions,
                "sports": sports,
            })

        print(f"  {freq.title()}: parsed {len(records)}/{len(urls)} reports.")
        return records

    @staticmethod
    def _build_sports_dict(cache: list[dict]) -> dict[str, pd.DataFrame]:
        """Build sport -> DataFrame from cached records."""
        sports_by_type = defaultdict(list)
        for rec in cache:
            for sport, sport_handle in rec["sports"].items():
                sports_by_type[sport].append({"date": rec["date"], "handle": sport_handle})

        result = {}
        for sport, recs in sorted(sports_by_type.items()):
            df = pd.DataFrame(recs)
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
            result[sport] = df
        return result

    def _build_tax_from_cache(self, cache: list[dict], ggr_pivot: pd.DataFrame) -> pd.DataFrame:
        """Build tax revenue = GGR - commissions from cached data."""
        commission_map = {}
        for rec in cache:
            dt = pd.Timestamp(rec["date"])
            commission_map[dt] = rec["ggr"] - rec["commissions"]

        tax = pd.DataFrame(index=ggr_pivot.index, columns=ggr_pivot.columns, dtype=float)
        tax.index.name = self.DATE_COLUMN
        for dt in tax.index:
            if dt in commission_map:
                tax.loc[dt, "total"] = commission_map[dt]
                tax.loc[dt, "Total"] = commission_map[dt]
        return tax

    def _write_weekly_csvs(self):
        """Write weekly CSVs with _weekly suffix."""
        if not self._weekly_cache:
            return

        df = pd.DataFrame(self._weekly_cache)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates(subset="date", keep="last")

        raw = {"total": df[["date", "handle", "ggr"]].reset_index(drop=True)}
        handle_pivot = self.build_pivot(raw, "handle")
        ggr_pivot = self.build_pivot(raw, "ggr")
        hold_pivot = self.build_hold_pct(handle_pivot, ggr_pivot)

        # YoY with weekly lookback
        orig_freq = self.FREQUENCY
        self.FREQUENCY = "weekly"
        yoy_handle = self.build_yoy_change(handle_pivot)
        yoy_ggr = self.build_yoy_change(ggr_pivot)
        self.FREQUENCY = orig_freq

        # Weekly tax from cache
        tax = self._build_tax_from_cache(self._weekly_cache, ggr_pivot)

        # Set index name to "Week Ending"
        for frame in [handle_pivot, ggr_pivot, hold_pivot, yoy_handle, yoy_ggr, tax]:
            frame.index.name = "Week Ending"

        for name, frame in [
            ("handle_weekly", handle_pivot), ("ggr_weekly", ggr_pivot),
            ("hold_pct_weekly", hold_pivot), ("yoy_handle_weekly", yoy_handle),
            ("yoy_ggr_weekly", yoy_ggr), ("tax_revenue_weekly", tax),
        ]:
            path = self.state_dir / f"{name}.csv"
            frame.to_csv(path, index=True, date_format="%Y-%m-%d")

        # Weekly sports
        if self._weekly_sports:
            sports_handle = self.build_pivot(self._weekly_sports, "handle")
            sports_handle.index.name = "Week Ending"
            path = self.state_dir / "sports_handle_weekly.csv"
            sports_handle.to_csv(path, index=True, date_format="%Y-%m-%d")
            print(f"  Wrote sports_handle_weekly.csv ({len(sports_handle)} weeks, "
                  f"{len(self._weekly_sports)} sports)")

        print(f"  Wrote 6 weekly CSVs to {self.state_dir}/")

    # ── URL discovery ─────────────────────────────────────────────

    @staticmethod
    def _find_monthly_urls() -> list[tuple[str, str]]:
        """Probe monthly PDF URLs by known pattern."""
        urls = []
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

        today = date.today()
        for year in range(2024, today.year + 1):
            for month_idx in range(12):
                month_name = MONTH_NAMES[month_idx]
                month_num = month_idx + 1
                if date(year, month_num, 1) > today:
                    break
                url = f"{BASE_URL}/Sports_Bet_Montana_Activity_{month_name}_{year}.pdf"
                try:
                    r = session.head(url, allow_redirects=False, timeout=10)
                    if r.status_code == 200:
                        urls.append((url, f"{year}-{month_num:02d}-01"))
                except requests.RequestException:
                    pass

        return sorted(urls, key=lambda x: x[1])

    @staticmethod
    def _find_weekly_urls() -> list[tuple[str, str]]:
        """Probe weekly PDF URLs for every Saturday from Jan 2025."""
        urls = []
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

        current = date(2025, 1, 4)  # First Saturday of 2025
        while current.weekday() != 5:
            current += timedelta(days=1)

        today = date.today()
        while current <= today:
            date_part = f"{current.month}.{current.day}.{str(current.year)[2:]}"
            url = f"{BASE_URL}/Sports_Bet_Montana_Activity_WE_{date_part}.pdf"
            try:
                r = session.head(url, allow_redirects=False, timeout=10)
                if r.status_code == 200:
                    urls.append((url, current.strftime("%Y-%m-%d")))
            except requests.RequestException:
                pass
            current += timedelta(days=7)

        return sorted(urls, key=lambda x: x[1])


# ── PDF parsing (module-level) ────────────────────────────────────

def _download_and_parse(url: str) -> tuple[float, float, float, dict[str, float]] | None:
    """Download and parse a Montana activity PDF.

    Returns (handle, ggr, retailer_commissions, sports_dict) or None.
    """
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return None
    except requests.RequestException:
        return None

    return _parse_pdf(r.content)


def _parse_pdf(pdf_bytes: bytes) -> tuple[float, float, float, dict[str, float]] | None:
    """Parse a Montana activity PDF (single page).

    Format:
      ➢ Project To Date Activity ...    ➢ [Weekly/Monthly] Activity ...
      Handle: $251.38M                  Handle: $5,750,903
      Payout: $218.56M                  Payout: $4,461,520
      GGR: $32.82M                      GGR: $1,289,383
      Retailer Commissions: $10.00M     Retailer Commissions: $172,527

      ➢ [Weekly/Monthly] Activity by Sport Detail:
      Sport | Handle ($) | Handle (%) | Payout ($) | GGR ($)
      ...
    """
    try:
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception:
        return None

    if not pdf.pages:
        return None

    text = pdf.pages[0].extract_text() or ""
    if not text:
        return None

    handle = None
    ggr = None
    commissions = None

    lines = text.split("\n")
    for line in lines:
        # Each line has cumulative + period values (two of each metric)
        # We want the LAST (period) value for each metric

        handle_matches = re.findall(r"Handle:\s*\$([\d,.]+[MBK]?)", line)
        if handle_matches:
            handle = _parse_amount(handle_matches[-1])

        ggr_matches = re.findall(r"GGR:\s*\$([\d,.]+[MBK]?)", line)
        if ggr_matches:
            ggr = _parse_amount(ggr_matches[-1])

        comm_matches = re.findall(r"Retailer Commissions:\s*\$([\d,.]+[MBK]?)", line)
        if comm_matches:
            commissions = _parse_amount(comm_matches[-1])

    if handle is None:
        return None

    sports = _parse_sports(lines)
    return handle, ggr or 0.0, commissions or 0.0, sports


def _parse_amount(s: str) -> float:
    """Parse dollar amount like '5,750,903' or '251.38M'."""
    s = s.strip().replace(",", "")
    multiplier = 1
    if s.endswith("M"):
        s = s[:-1]
        multiplier = 1_000_000
    elif s.endswith("B"):
        s = s[:-1]
        multiplier = 1_000_000_000
    elif s.endswith("K"):
        s = s[:-1]
        multiplier = 1_000
    return float(s) * multiplier


def _parse_sports(lines: list[str]) -> dict[str, float]:
    """Parse Activity by Sport Detail table from PDF lines."""
    sports = defaultdict(float)
    in_detail = False

    for line in lines:
        if "Activity by Sport Detail" in line:
            in_detail = True
            continue

        if not in_detail:
            continue

        if "Sport" in line and "Handle" in line:
            continue

        stripped = line.strip()
        if stripped.startswith("Total") or stripped.startswith("Note:"):
            break

        if not stripped:
            continue

        amounts = re.findall(r"\$\(?([\d,]+\.?\d*)\)?", stripped)
        if not amounts:
            continue

        name_end = stripped.find("$")
        if name_end < 0:
            continue
        sport_name = stripped[:name_end].strip()
        if not sport_name:
            continue

        handle_val = float(amounts[0].replace(",", ""))
        if handle_val == 0:
            continue

        canonical = SPORT_MAP.get(sport_name.upper(), sport_name)
        sports[canonical] += handle_val

    return dict(sports)
