#!/usr/bin/env python3
"""
Download all weekly mobile sports wagering data from the NY Gaming Commission
and compile it into a single Excel workbook.
"""

import re
import shutil
from datetime import timedelta
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

BASE_URL = "https://gaming.ny.gov"
REVENUE_PAGE = f"{BASE_URL}/revenue-reports"
DOWNLOADS_DIR = Path("downloads")
DATA_DIR = Path("data")
OUTPUT_FILE = "ny_sports_betting_data.xlsx"

# Sportsbook slug → link suffix on the revenue reports page
SPORTSBOOK_LINKS = {
    "fanduel": "/fanduel-weekly-report-excel",
    "draftkings": "/draftkings-sport-book-weekly-report-excel",
    "betmgm": "/betmgm-weekly-report-excel",
    "caesars": "/caesars-sport-book-weekly-report-excel",
    "wynn-interactive": "/wynn-interactive-weekly-report-excel",
    "ballybet": "/ballybet-weekly-report-excel",
    "fanatics": "/fanatics-weekly-report-excel",
    "resorts-world-bet": "/resorts-world-bet-weekly-report-excel",
    "rush-street-interactive": "/rush-street-interactive-weekly-report-excel",
}

NAME_MAP = {
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
    "betmgm": "BetMGM",
    "caesars": "Caesars",
    "wynn-interactive": "ESPN Bet",
    "ballybet": "Bally Bet",
    "fanatics": "Fanatics",
    "resorts-world-bet": "Resorts World Bet",
    "rush-street-interactive": "Rush Street Interactive",
}


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    })
    return session


def find_xlsx_download_url(session: requests.Session, page_url: str) -> str | None:
    """Fetch a sportsbook's weekly-report-excel page and find the .xlsx download URL."""
    try:
        resp = session.get(page_url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  Error fetching page {page_url}: {e}")
        return None

    # If the response itself is an xlsx file (direct download / redirect), return the final URL
    content_type = resp.headers.get("Content-Type", "")
    if "spreadsheet" in content_type or "octet-stream" in content_type:
        return resp.url

    # Otherwise parse the HTML to find the xlsx link
    soup = BeautifulSoup(resp.text, "lxml")

    # Look for a direct link to an .xlsx file
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.endswith(".xlsx"):
            if href.startswith("http"):
                return href
            return BASE_URL + href

    # Look for links containing "system/files" which is how Drupal serves files
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "system/files" in href:
            if href.startswith("http"):
                return href
            return BASE_URL + href

    return None


def download_file(session: requests.Session, url: str, dest: Path) -> bool:
    """Download a file to the given path."""
    try:
        resp = session.get(url, timeout=60, allow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except requests.RequestException as e:
        print(f"  Error downloading {url}: {e}")
        return False


def resolve_sportsbook_url(session: requests.Session, slug: str, link_path: str) -> str | None:
    """
    Try multiple strategies to get the xlsx download URL for a sportsbook.
    Strategy 1: Visit the link page and look for xlsx URL in the HTML.
    Strategy 2: The link itself may redirect to the file.
    """
    page_url = BASE_URL + link_path
    return find_xlsx_download_url(session, page_url)


def clean_dollar_value(val) -> float | None:
    """Parse a dollar string like '$1,234,567.89' or '-$500.00' into a float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if pd.isna(val):
            return None
        return float(val)
    s = str(val).strip()
    if s in ("", "-", "—", "–", "N/A", "n/a"):
        return None
    # Handle negative values: could be -$X or ($X) or $-X
    negative = False
    if s.startswith("-") or s.startswith("("):
        negative = True
    s = re.sub(r"[$()\s,]", "", s)
    if s.startswith("-"):
        negative = True
        s = s[1:]
    elif s.endswith("-"):
        negative = True
        s = s[:-1]
    try:
        result = float(s)
        return -result if negative else result
    except ValueError:
        return None


def parse_xlsx(filepath: Path) -> pd.DataFrame:
    """
    Parse a downloaded sportsbook xlsx file.
    Returns a DataFrame with columns: week_ending (date), handle (float), ggr (float).
    Reads ALL sheets (fiscal years).
    """
    wb = load_workbook(filepath, read_only=True, data_only=True)
    all_rows = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        # Find header row — look for a row containing "Week" or "Week-Ending"
        header_idx = None
        for i, row in enumerate(rows):
            row_strs = [str(c).lower().strip() if c else "" for c in row]
            for cell_str in row_strs:
                if "week" in cell_str:
                    header_idx = i
                    break
            if header_idx is not None:
                break

        if header_idx is None:
            # Assume first row is header
            header_idx = 0

        # Identify column indices for date, handle, GGR
        header = rows[header_idx]
        date_col = None
        handle_col = None
        ggr_col = None

        for j, cell in enumerate(header):
            if cell is None:
                continue
            cell_str = str(cell).lower().strip()
            if "week" in cell_str or "date" in cell_str:
                date_col = j
            elif "handle" in cell_str:
                handle_col = j
            elif "ggr" in cell_str or "gross" in cell_str or "revenue" in cell_str:
                ggr_col = j

        # Fallback: assume columns A=date, B=handle, C=ggr
        if date_col is None:
            date_col = 0
        if handle_col is None:
            handle_col = 1
        if ggr_col is None:
            ggr_col = 2

        for row in rows[header_idx + 1:]:
            if len(row) <= max(date_col, handle_col, ggr_col):
                continue

            date_val = row[date_col]
            handle_val = row[handle_col]
            ggr_val = row[ggr_col]

            # Skip total rows
            if date_val is not None and "total" in str(date_val).lower():
                continue
            if date_val is None:
                continue

            # Parse date
            week_ending = None
            if isinstance(date_val, (pd.Timestamp,)):
                week_ending = date_val.date()
            elif hasattr(date_val, "date"):
                # datetime object
                week_ending = date_val.date()
            elif hasattr(date_val, "year"):
                # date object
                week_ending = date_val
            else:
                # Try parsing string
                date_str = str(date_val).strip()
                if not date_str or date_str in ("-", "—"):
                    continue
                for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y"):
                    try:
                        week_ending = pd.to_datetime(date_str, format=fmt).date()
                        break
                    except (ValueError, TypeError):
                        continue
                if week_ending is None:
                    try:
                        week_ending = pd.to_datetime(date_str).date()
                    except (ValueError, TypeError):
                        continue

            handle = clean_dollar_value(handle_val)
            ggr = clean_dollar_value(ggr_val)

            if handle is None and ggr is None:
                continue

            all_rows.append({
                "week_ending": week_ending,
                "handle": handle,
                "ggr": ggr,
            })

    wb.close()

    if not all_rows:
        return pd.DataFrame(columns=["week_ending", "handle", "ggr"])

    df = pd.DataFrame(all_rows)
    df["week_ending"] = pd.to_datetime(df["week_ending"])
    df = df.drop_duplicates(subset=["week_ending"], keep="first")
    df = df.sort_values("week_ending").reset_index(drop=True)
    return df


def build_pivot(all_data: dict[str, pd.DataFrame], value_col: str) -> pd.DataFrame:
    """
    Build a pivot table with Week Ending as rows and sportsbook names as columns.
    value_col is 'handle' or 'ggr'.
    """
    frames = []
    for slug, df in all_data.items():
        name = NAME_MAP.get(slug, slug)
        subset = df[["week_ending", value_col]].copy()
        subset = subset.rename(columns={value_col: name})
        subset = subset.set_index("week_ending")
        frames.append(subset)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, axis=1)
    # Sort columns alphabetically
    sorted_cols = sorted(combined.columns)
    combined = combined[sorted_cols]
    # Add total column
    combined["Total"] = combined.sum(axis=1, skipna=True)
    # Where ALL sportsbooks are NaN for a row, total should also be NaN
    all_nan_mask = combined[sorted_cols].isna().all(axis=1)
    combined.loc[all_nan_mask, "Total"] = None
    # Sort by date descending (most recent first)
    combined = combined.sort_index(ascending=False)
    combined.index.name = "Week Ending"
    return combined


def build_hold_pct(handle_pivot: pd.DataFrame, ggr_pivot: pd.DataFrame) -> pd.DataFrame:
    """Calculate Hold % = GGR / Handle."""
    sportsbook_cols = [c for c in handle_pivot.columns if c != "Total"]
    hold = pd.DataFrame(index=handle_pivot.index)
    hold.index.name = "Week Ending"

    for col in sportsbook_cols:
        h = handle_pivot[col]
        g = ggr_pivot[col]
        hold[col] = g / h.where(h != 0)

    # Total hold %
    h_total = handle_pivot["Total"]
    g_total = ggr_pivot["Total"]
    hold["Total"] = g_total / h_total.where(h_total != 0)

    return hold


def build_yoy_change(pivot: pd.DataFrame) -> pd.DataFrame:
    """
    Compute year-over-year percentage change by matching each week to the closest
    date approximately 52 weeks (364 days) prior, within ±3 days tolerance.
    Returns values as decimals (e.g. 0.15 = 15% increase).
    """
    yoy = pd.DataFrame(index=pivot.index, columns=pivot.columns, dtype=float)
    yoy.index.name = "Week Ending"
    dates = pivot.index.to_series()

    for i, current_date in enumerate(pivot.index):
        target_date = current_date - timedelta(days=364)
        # Find closest date within ±3 days
        diffs = (dates - target_date).abs()
        min_diff = diffs.min()
        if min_diff <= timedelta(days=3):
            prior_date = diffs.idxmin()
            for col in pivot.columns:
                curr_val = pivot.loc[current_date, col]
                prior_val = pivot.loc[prior_date, col]
                if pd.notna(curr_val) and pd.notna(prior_val) and prior_val != 0:
                    yoy.loc[current_date, col] = (curr_val - prior_val) / abs(prior_val)

    return yoy


def format_worksheet(ws, fmt_type: str, num_data_cols: int):
    """
    Apply formatting to a worksheet.
    fmt_type: 'currency', 'percentage', or 'currency_yoy'
    """
    bold_font = Font(bold=True)

    # Bold headers
    for cell in ws[1]:
        cell.font = bold_font

    # Freeze top row
    ws.freeze_panes = "A2"

    # Format date column (column A)
    for row in ws.iter_rows(min_row=2, max_col=1):
        for cell in row:
            cell.number_format = "MM/DD/YYYY"

    # Format data columns
    if fmt_type in ("currency", "currency_yoy"):
        num_fmt = '#,##0.00'
    elif fmt_type == "percentage":
        num_fmt = '0.00%'
    else:
        num_fmt = "General"

    for row in ws.iter_rows(min_row=2, min_col=2, max_col=num_data_cols + 1):
        for cell in row:
            cell.number_format = num_fmt

    # Set column widths
    ws.column_dimensions["A"].width = 14
    for col_idx in range(2, num_data_cols + 2):
        col_letter = get_column_letter(col_idx)
        if fmt_type == "percentage":
            ws.column_dimensions[col_letter].width = 14
        else:
            ws.column_dimensions[col_letter].width = 22


def write_output(
    handle_pivot: pd.DataFrame,
    ggr_pivot: pd.DataFrame,
    hold_pivot: pd.DataFrame,
    yoy_handle: pd.DataFrame,
    yoy_ggr: pd.DataFrame,
):
    """Write all sheets to the output Excel file."""
    print(f"Writing output to {OUTPUT_FILE}...")

    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        handle_pivot.to_excel(writer, sheet_name="Handle")
        ggr_pivot.to_excel(writer, sheet_name="GGR")
        hold_pivot.to_excel(writer, sheet_name="Hold %")
        yoy_handle.to_excel(writer, sheet_name="YoY Handle Change")
        yoy_ggr.to_excel(writer, sheet_name="YoY GGR Change")

    # Now apply formatting
    wb = load_workbook(OUTPUT_FILE)
    num_data_cols = len(handle_pivot.columns)

    format_worksheet(wb["Handle"], "currency", num_data_cols)
    format_worksheet(wb["GGR"], "currency", num_data_cols)
    format_worksheet(wb["Hold %"], "percentage", num_data_cols)
    format_worksheet(wb["YoY Handle Change"], "percentage", num_data_cols)
    format_worksheet(wb["YoY GGR Change"], "percentage", num_data_cols)

    wb.save(OUTPUT_FILE)
    wb.close()
    print(f"Done! Output saved to {OUTPUT_FILE}")


def write_csvs(
    handle_pivot: pd.DataFrame,
    ggr_pivot: pd.DataFrame,
    hold_pivot: pd.DataFrame,
    yoy_handle: pd.DataFrame,
    yoy_ggr: pd.DataFrame,
):
    """Write all pivot tables as CSVs to the data/ directory for the web dashboard."""
    print(f"Writing CSVs to {DATA_DIR}/...")
    for name, df in [
        ("handle", handle_pivot),
        ("ggr", ggr_pivot),
        ("hold_pct", hold_pivot),
        ("yoy_handle", yoy_handle),
        ("yoy_ggr", yoy_ggr),
    ]:
        out_path = DATA_DIR / f"{name}.csv"
        df.to_csv(out_path, index=True, date_format="%Y-%m-%d")
        print(f"  Wrote {out_path}")


def write_tax_revenue_csv(ggr_pivot: pd.DataFrame):
    """Compute NY tax revenue (51% of GGR) and write to CSV."""
    tax = ggr_pivot * 0.51
    out_path = DATA_DIR / "tax_revenue.csv"
    tax.to_csv(out_path, index=True, date_format="%Y-%m-%d")
    print(f"  Wrote {out_path}")


def main():
    # Setup
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    session = get_session()

    # Download and parse each sportsbook
    all_data: dict[str, pd.DataFrame] = {}

    for slug, link_path in SPORTSBOOK_LINKS.items():
        display_name = NAME_MAP.get(slug, slug)
        print(f"Downloading {display_name} weekly data...")

        xlsx_url = resolve_sportsbook_url(session, slug, link_path)
        if xlsx_url is None:
            print(f"  Could not find download URL for {display_name}, skipping.")
            continue

        dest = DOWNLOADS_DIR / f"{slug}.xlsx"
        if not download_file(session, xlsx_url, dest):
            print(f"  Failed to download {display_name}, skipping.")
            continue

        print(f"  Parsing {display_name} data...")
        try:
            df = parse_xlsx(dest)
            if df.empty:
                print(f"  No data found for {display_name}.")
            else:
                num_weeks = len(df)
                date_min = df["week_ending"].min().strftime("%m/%d/%Y")
                date_max = df["week_ending"].max().strftime("%m/%d/%Y")
                print(f"  Parsed {num_weeks} weeks ({date_min} - {date_max})")
                all_data[slug] = df
        except Exception as e:
            print(f"  Error parsing {display_name}: {e}")
            continue

    if not all_data:
        print("No data was successfully downloaded. Exiting.")
        return

    # Build pivot tables
    print(f"\nBuilding pivot tables from {len(all_data)} sportsbooks...")
    handle_pivot = build_pivot(all_data, "handle")
    ggr_pivot = build_pivot(all_data, "ggr")

    print("Calculating Hold %...")
    hold_pivot = build_hold_pct(handle_pivot, ggr_pivot)

    print("Calculating YoY Handle Change...")
    yoy_handle = build_yoy_change(handle_pivot)

    print("Calculating YoY GGR Change...")
    yoy_ggr = build_yoy_change(ggr_pivot)

    # Write output
    write_output(handle_pivot, ggr_pivot, hold_pivot, yoy_handle, yoy_ggr)
    write_csvs(handle_pivot, ggr_pivot, hold_pivot, yoy_handle, yoy_ggr)
    write_tax_revenue_csv(ggr_pivot)

    # Cleanup downloads
    print("Cleaning up temporary files...")
    shutil.rmtree(DOWNLOADS_DIR, ignore_errors=True)

    total_weeks = len(handle_pivot)
    total_books = len(handle_pivot.columns) - 1  # exclude Total
    print(f"\nSummary: {total_weeks} weeks across {total_books} sportsbooks")


if __name__ == "__main__":
    main()
