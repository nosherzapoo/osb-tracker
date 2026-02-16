"""Shared utilities for all state scrapers."""

import re
import requests
import pandas as pd


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


def clean_dollar_value(val) -> float | None:
    """Parse a dollar string like '$1,234,567.89' or '-$500.00' into a float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if pd.isna(val):
            return None
        return float(val)
    s = str(val).strip()
    if s in ("", "-", "\u2014", "\u2013", "N/A", "n/a"):
        return None
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


def parse_date_flex(val):
    """Parse a date value from various formats. Returns a date object or None."""
    if val is None:
        return None
    if isinstance(val, pd.Timestamp):
        return val.date()
    if hasattr(val, "date"):
        return val.date()
    if hasattr(val, "year"):
        return val
    date_str = str(val).strip()
    if not date_str or date_str in ("-", "\u2014"):
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y", "%B %Y", "%b %Y"):
        try:
            return pd.to_datetime(date_str, format=fmt).date()
        except (ValueError, TypeError):
            continue
    try:
        return pd.to_datetime(date_str).date()
    except (ValueError, TypeError):
        return None


def download_file(session: requests.Session, url: str, dest) -> bool:
    """Download a file to the given path."""
    try:
        resp = session.get(url, timeout=60, allow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except requests.RequestException as e:
        print(f"  Error downloading {url}: {e}")
        return False
