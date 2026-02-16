"""Connecticut sports betting scraper — data.ct.gov Socrata API.

Fetches operator-level monthly data from CT's open data portal (Socrata/SODA API).
Three operators: DraftKings (MPI), FanDuel (Mohegan), CT Lottery.
Data available from October 2021.

GGR = Wagers - Patron Winnings - Cancelled Wagers (raw operator win)
Adjusted GGR = Total Gross Gaming Revenue (after federal excise tax & promo deductions)
Tax is computed on Adjusted GGR at 13.75%.
"""

import pandas as pd
import requests

from .base import BaseScraper

# Socrata SODA API endpoint for CT online sports wagering data
API_URL = "https://data.ct.gov/resource/xf6g-659c.json"

# Map CT licensee names → canonical operator names
LICENSEE_MAP = {
    "MPI Master Wagering License CT, LLC": "DraftKings",
    "Mohegan Digital, LLC": "FanDuel",
    "CT Lottery Corp": "CT Lottery",
}


class CTScraper(BaseScraper):
    STATE_CODE = "ct"
    STATE_NAME = "Connecticut"
    TAX_RATE = 0.1375
    TAX_RATE_NOTE = "13.75% on adjusted gross gaming revenue"
    FREQUENCY = "monthly"
    HAS_OPERATOR_DATA = True
    SOURCE_URL = "https://data.ct.gov/Government/Selected-Online-Sport-Wagering-Data/xf6g-659c"
    DATE_COLUMN = "Month"
    LAUNCH_DATE = "2021-10-12"
    GGR_DEFINITION = "Handle − Patron Winnings − Cancelled Wagers"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._raw_cache = None

    def scrape(self) -> dict[str, pd.DataFrame]:
        if self._raw_cache is not None:
            return self._raw_cache

        print("  Fetching CT data from Socrata API...")
        rows = self._fetch_all()

        if not rows:
            print("  No data returned from API.")
            self._raw_cache = {}
            return {}

        all_data = {}
        for row in rows:
            licensee = row.get("licensee", "").strip()
            canonical = LICENSEE_MAP.get(licensee)
            if not canonical:
                canonical = self._fuzzy_match(licensee)
                if not canonical:
                    print(f"    Unknown licensee: {licensee}")
                    continue

            date_str = row.get("month_ending", "")
            if not date_str:
                continue

            # Socrata returns ISO dates like "2025-12-31T00:00:00.000"
            date = pd.Timestamp(date_str).normalize()
            # Normalize to first-of-month for consistency
            date = date.replace(day=1)

            # Raw GGR = Handle - Patron Winnings - Cancelled Wagers
            handle = self._safe_float(row.get("wagers"))
            patron_winnings = self._safe_float(row.get("patron_winnings"))
            cancelled = self._safe_float(row.get("cancelled_wagers"))
            ggr = handle - patron_winnings - cancelled

            # Adjusted GGR = after federal excise tax & promotional deductions
            adj_ggr = self._safe_float(row.get("total_gross_gaming"))

            if canonical not in all_data:
                all_data[canonical] = []

            all_data[canonical].append({
                "date": date,
                "handle": handle,
                "ggr": ggr,
                "adj_ggr": adj_ggr,
            })

        # Convert lists to DataFrames
        result = {}
        for name, records in all_data.items():
            df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
            result[name] = df
            print(f"    {name}: {len(df)} months")

        print(f"  Parsed {sum(len(df) for df in result.values())} total records across {len(result)} operators.")
        self._raw_cache = result
        return result

    def run(self):
        """Override to also write adj_ggr.csv."""
        result = super().run()

        # Build adjusted GGR pivot from cached raw data
        raw = self._raw_cache
        if raw:
            adj_ggr_pivot = self.build_pivot(raw, "adj_ggr")
            path = self.state_dir / "adj_ggr.csv"
            adj_ggr_pivot.to_csv(path, index=True, date_format="%Y-%m-%d")
            print(f"  Wrote adj_ggr.csv ({len(adj_ggr_pivot)} periods)")

        return result

    def _fetch_all(self) -> list[dict]:
        """Fetch all rows from Socrata API with pagination."""
        all_rows = []
        limit = 5000
        offset = 0

        while True:
            params = {
                "$limit": limit,
                "$offset": offset,
                "$order": "month_ending DESC",
            }

            try:
                resp = requests.get(API_URL, params=params, timeout=30)
                resp.raise_for_status()
                batch = resp.json()
            except Exception as e:
                print(f"    API error at offset {offset}: {e}")
                break

            if not batch:
                break

            all_rows.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        print(f"  Fetched {len(all_rows)} rows from API.")
        return all_rows

    @staticmethod
    def _fuzzy_match(licensee: str) -> str | None:
        """Partial matching fallback for licensee names."""
        lower = licensee.lower()
        if "mpi" in lower or "mashantucket" in lower or "foxwoods" in lower:
            return "DraftKings"
        if "mohegan" in lower:
            return "FanDuel"
        if "lottery" in lower:
            return "CT Lottery"
        return None

    @staticmethod
    def _safe_float(val) -> float:
        """Safely convert API value to float."""
        if val is None:
            return 0.0
        try:
            return float(str(val).replace(",", ""))
        except (ValueError, TypeError):
            return 0.0
