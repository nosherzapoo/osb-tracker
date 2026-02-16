"""Abstract base class for state sports betting scrapers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pandas as pd


@dataclass
class ScraperResult:
    state_code: str
    state_name: str
    handle_pivot: pd.DataFrame
    ggr_pivot: pd.DataFrame
    hold_pivot: pd.DataFrame
    yoy_handle: pd.DataFrame
    yoy_ggr: pd.DataFrame
    tax_revenue: pd.DataFrame
    sports_handle: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata: dict = field(default_factory=dict)


class BaseScraper(ABC):
    STATE_CODE: str = ""
    STATE_NAME: str = ""
    TAX_RATE: float = 0.0
    TAX_RATE_NOTE: str = ""
    FREQUENCY: str = "monthly"  # "weekly" or "monthly"
    HAS_OPERATOR_DATA: bool = True
    SOURCE_URL: str = ""
    DATE_COLUMN: str = "Month"
    LAUNCH_DATE: str = ""
    GGR_DEFINITION: str = "Handle − Payouts"  # Override per state with specifics

    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = data_dir
        self.state_dir = data_dir / self.STATE_CODE
        self.state_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def scrape(self) -> dict[str, pd.DataFrame]:
        """Download and parse raw data.
        Returns dict of operator_slug -> DataFrame with columns:
            [date_col, handle, ggr]
        For aggregate-only states, return {"total": df}.
        """
        pass

    def run(self) -> ScraperResult:
        """Full pipeline: scrape, pivot, compute derived metrics, write CSVs."""
        raw = self.scrape()
        if not raw:
            print(f"  No data scraped for {self.STATE_NAME}")
            return ScraperResult(
                state_code=self.STATE_CODE,
                state_name=self.STATE_NAME,
                handle_pivot=pd.DataFrame(),
                ggr_pivot=pd.DataFrame(),
                hold_pivot=pd.DataFrame(),
                yoy_handle=pd.DataFrame(),
                yoy_ggr=pd.DataFrame(),
                tax_revenue=pd.DataFrame(),
            )

        handle_pivot = self.build_pivot(raw, "handle")
        ggr_pivot = self.build_pivot(raw, "ggr")
        hold_pivot = self.build_hold_pct(handle_pivot, ggr_pivot)
        yoy_handle = self.build_yoy_change(handle_pivot)
        yoy_ggr = self.build_yoy_change(ggr_pivot)
        tax_revenue = ggr_pivot * self.TAX_RATE

        self.write_csvs(handle_pivot, ggr_pivot, hold_pivot, yoy_handle, yoy_ggr, tax_revenue)

        # Sports breakdown (optional)
        sports_handle = pd.DataFrame()
        sports_raw = self.scrape_sports()
        if sports_raw:
            sports_handle = self.build_pivot(sports_raw, "handle")
            path = self.state_dir / "sports_handle.csv"
            sports_handle.to_csv(path, index=True, date_format="%Y-%m-%d")
            print(f"  Wrote sports_handle.csv ({len(sports_handle)} periods, {len(sports_raw)} sports)")

        metadata = self.build_metadata(handle_pivot, ggr_pivot, sports_handle)

        return ScraperResult(
            state_code=self.STATE_CODE,
            state_name=self.STATE_NAME,
            handle_pivot=handle_pivot,
            ggr_pivot=ggr_pivot,
            hold_pivot=hold_pivot,
            yoy_handle=yoy_handle,
            yoy_ggr=yoy_ggr,
            tax_revenue=tax_revenue,
            sports_handle=sports_handle,
            metadata=metadata,
        )

    def scrape_sports(self) -> dict[str, pd.DataFrame] | None:
        """Optional: download and parse sports breakdown data.
        Returns dict of sport_name -> DataFrame with columns [date, handle].
        Override in state scrapers that report sports-level data.
        """
        return None

    def build_pivot(self, all_data: dict[str, pd.DataFrame], value_col: str) -> pd.DataFrame:
        """Build a pivot table: dates as rows, operators as columns."""
        frames = []
        for name, df in all_data.items():
            subset = df[["date", value_col]].copy()
            subset = subset.rename(columns={value_col: name})
            subset = subset.set_index("date")
            frames.append(subset)

        if not frames:
            return pd.DataFrame()

        combined = pd.concat(frames, axis=1)
        sorted_cols = sorted(combined.columns)
        combined = combined[sorted_cols]
        combined["Total"] = combined.sum(axis=1, skipna=True)
        all_nan_mask = combined[sorted_cols].isna().all(axis=1)
        combined.loc[all_nan_mask, "Total"] = None
        combined = combined.sort_index(ascending=False)
        combined.index.name = self.DATE_COLUMN
        return combined

    def build_hold_pct(self, handle_pivot: pd.DataFrame, ggr_pivot: pd.DataFrame) -> pd.DataFrame:
        """Calculate Hold % = GGR / Handle."""
        sportsbook_cols = [c for c in handle_pivot.columns if c != "Total"]
        hold = pd.DataFrame(index=handle_pivot.index)
        hold.index.name = self.DATE_COLUMN

        for col in sportsbook_cols:
            h = handle_pivot[col]
            g = ggr_pivot[col]
            hold[col] = g / h.where(h != 0)

        h_total = handle_pivot["Total"]
        g_total = ggr_pivot["Total"]
        hold["Total"] = g_total / h_total.where(h_total != 0)
        return hold

    def build_yoy_change(self, pivot: pd.DataFrame) -> pd.DataFrame:
        """Compute year-over-year percentage change."""
        yoy = pd.DataFrame(index=pivot.index, columns=pivot.columns, dtype=float)
        yoy.index.name = self.DATE_COLUMN
        dates = pivot.index.to_series()

        # For weekly data, look back 364 days. For monthly, 365 days.
        lookback = 364 if self.FREQUENCY == "weekly" else 365
        tolerance = 3 if self.FREQUENCY == "weekly" else 15

        for current_date in pivot.index:
            target_date = current_date - timedelta(days=lookback)
            diffs = (dates - target_date).abs()
            min_diff = diffs.min()
            if min_diff <= timedelta(days=tolerance):
                prior_date = diffs.idxmin()
                for col in pivot.columns:
                    curr_val = pivot.loc[current_date, col]
                    prior_val = pivot.loc[prior_date, col]
                    if pd.notna(curr_val) and pd.notna(prior_val) and prior_val != 0:
                        yoy.loc[current_date, col] = (curr_val - prior_val) / abs(prior_val)

        return yoy

    def write_csvs(self, handle, ggr, hold, yoy_h, yoy_g, tax):
        """Write 6 CSVs to the state's data directory."""
        for name, df in [
            ("handle", handle), ("ggr", ggr), ("hold_pct", hold),
            ("yoy_handle", yoy_h), ("yoy_ggr", yoy_g), ("tax_revenue", tax),
        ]:
            path = self.state_dir / f"{name}.csv"
            df.to_csv(path, index=True, date_format="%Y-%m-%d")
        print(f"  Wrote 6 CSVs to {self.state_dir}/")

    def build_metadata(self, handle_pivot: pd.DataFrame, ggr_pivot: pd.DataFrame, sports_handle: pd.DataFrame = None) -> dict:
        """Build metadata dict for states.json manifest."""
        operators = [c for c in handle_pivot.columns if c != "Total"]
        latest_date = handle_pivot.index.max()
        latest_handle = handle_pivot.loc[latest_date, "Total"] if pd.notna(handle_pivot.loc[latest_date, "Total"]) else None
        latest_ggr = ggr_pivot.loc[latest_date, "Total"] if pd.notna(ggr_pivot.loc[latest_date, "Total"]) else None
        latest_hold = (latest_ggr / latest_handle) if latest_handle and latest_ggr and latest_handle != 0 else None
        latest_tax = (latest_ggr * self.TAX_RATE) if latest_ggr else None

        return {
            "code": self.STATE_CODE,
            "name": self.STATE_NAME,
            "abbreviation": self.STATE_CODE.upper(),
            "taxRate": self.TAX_RATE,
            "taxRateNote": self.TAX_RATE_NOTE,
            "launchDate": self.LAUNCH_DATE,
            "frequency": self.FREQUENCY,
            "hasOperatorData": self.HAS_OPERATOR_DATA and len(operators) > 1,
            "operators": operators,
            "sourceUrl": self.SOURCE_URL,
            "dataPath": f"data/{self.STATE_CODE}/",
            "dateColumn": self.DATE_COLUMN,
            "latestDate": latest_date.strftime("%Y-%m-%d") if latest_date else None,
            "periodCount": len(handle_pivot),
            "latestData": {
                "handle": round(latest_handle, 2) if latest_handle else None,
                "ggr": round(latest_ggr, 2) if latest_ggr else None,
                "holdPct": round(latest_hold, 4) if latest_hold else None,
                "taxRevenue": round(latest_tax, 2) if latest_tax else None,
            },
            "hasAnnotations": (self.state_dir / "annotations.json").exists(),
            "hasSportsData": sports_handle is not None and not sports_handle.empty,
            "sports": [c for c in (sports_handle.columns if sports_handle is not None and not sports_handle.empty else []) if c != "Total"],
            "ggrDefinition": self.GGR_DEFINITION,
        }
