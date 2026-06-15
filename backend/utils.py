# backend/utils.py
# Shared utility functions for the Street Food Shop backend.
# Import from here — never duplicate logic across modules.

import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

# ── IST timezone constant ─────────────────────────────────────────────────────
# All modules MUST use ist_now() instead of datetime.now() for business records.
# Never use datetime.now() directly — it returns UTC on Render cloud servers.

IST = ZoneInfo("Asia/Kolkata")


def ist_now() -> datetime:
    """
    Return the current time as a timezone-aware datetime in Asia/Kolkata (IST).

    Use this everywhere a timestamp is needed for business records:
        sale time, open time, close time, date filters, day names.

    NEVER call datetime.now() directly in business logic — it returns UTC on
    cloud servers (Render, Railway, etc.) which is 5h 30m behind IST.
    """
    return datetime.now(IST)


def normalize_date(series):
    """
    Normalize a pandas Series of date strings with mixed formats to YYYY-MM-DD.

    Handles all known formats found in the Excel files:
        2026-06-10   (ISO — most common)
        2026/07/07   (slash-separated)
        07/07/2026   (DD/MM/YYYY legacy)

    Returns a Series of strings in the format YYYY-MM-DD.
    Unparseable values become NaN (coerced).

    IMPORTANT: dayfirst=False is used so ISO dates like 2026-06-12 are NOT
    misread as 2026-12-06. Pandas mixed-format parser handles DD/MM/YYYY
    correctly when the day value > 12 (unambiguous). For ambiguous dates like
    07/07/2026 the result is the same regardless of dayfirst.

    NOTE: This is for in-memory processing ONLY. It never modifies Excel files.
    """
    return pd.to_datetime(
        series,
        format="mixed",
        dayfirst=False,
        errors="coerce",
    ).dt.strftime("%Y-%m-%d")


def safe_int(value, default=0) -> int:
    """Safely convert a value to int, returning default on failure."""
    try:
        v = float(value)
        if pd.isna(v):
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0) -> float:
    """Safely convert a value to float, returning default on failure."""
    try:
        v = float(value)
        if pd.isna(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def safe_str(value, default="") -> str:
    """Safely convert a value to str, treating NaN/None as default."""
    if value is None:
        return default
    s = str(value).strip()
    if s.lower() in ("nan", "none", "nat"):
        return default
    return s
