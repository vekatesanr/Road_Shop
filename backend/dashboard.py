# backend/dashboard.py

import os
import logging
import pandas as pd
from datetime import datetime
from backend.utils import normalize_date, safe_int, safe_float, safe_str, ist_now
from backend import config

log = logging.getLogger(__name__)

_EMPTY_DATA = {
    "date": "",
    "day": "",
    "weather": "N/A",
    "temperature": "N/A",
    "revenue": 0,
    "orders": 0,
    "items": 0,
    "best_product": "N/A",
    "shop_status": "NOT_OPENED",
}


def _compute_live_totals(today: str) -> dict | None:
    """
    Compute today's revenue, orders, items, and best_product directly
    from the Sales worksheet.

    This bypasses DailySummary entirely and gives the most up-to-date
    numbers.  Returns None if the Sales sheet is unavailable.
    """
    try:
        from backend.database import get_sales
        sales = get_sales()
    except Exception as e:
        log.warning("[dashboard] Failed to fetch live sales for totals: %s", e)
        return None

    if not sales:
        return {"revenue": 0, "orders": 0, "items": 0, "best_product": "N/A"}

    # Filter to today's active sales
    active = [
        s for s in sales
        if s.get("Date") == today and s.get("Status") == "Active"
    ]

    if not active:
        return {"revenue": 0, "orders": 0, "items": 0, "best_product": "N/A"}

    df = pd.DataFrame(active)
    revenue = safe_float(df["Total_Amount"].sum())
    orders = len(df)
    items = safe_float(df["Quantity"].sum())

    # Best product by quantity sold
    product_totals = df.groupby("Product_Name")["Quantity"].sum()
    best_product = product_totals.idxmax() if not product_totals.empty else "N/A"

    return {
        "revenue": int(revenue),
        "orders": orders,
        "items": int(items),
        "best_product": best_product,
    }


def get_dashboard_data() -> dict:
    """
    Read today's row from Google Sheets daily summary and return a dict for templates.

    Keys:
        date, day, weather, temperature — display info
        revenue, orders, items           — today's aggregate totals
        best_product                     — top-selling product name
        shop_status                      — NOT_OPENED | OPEN | CLOSED

    Never returns None. Returns safe zero-state dict on any error.

    IMPORTANT: After reading DailySummary, this function validates the
    totals against live Sales data. If DailySummary has stale/zero values
    but live sales exist, the live values are used instead. This ensures
    the dashboard always reflects the latest state.
    """
    today = ist_now().strftime("%Y-%m-%d")
    base = {**_EMPTY_DATA, "date": today, "day": ist_now().strftime("%A")}

    # ── Step 1: Read from DailySummary (primary source for weather/status) ──
    row = None
    try:
        from backend.database import get_daily_summary
        row = get_daily_summary(today)
    except Exception as e:
        log.warning("[dashboard] Live database access failed: %s. Falling back to Excel.", e)
        try:
            if os.path.exists(config.SUMMARY_FILE):
                df = pd.read_excel(config.SUMMARY_FILE)
                if not df.empty:
                    df["Date"] = normalize_date(df["Date"].astype(str))
                    df_row = df[df["Date"] == today]
                    if len(df_row) > 0:
                        row = df_row.iloc[0].to_dict()
        except Exception as ex:
            log.warning("[dashboard] Excel fallback also failed: %s", ex)

    # ── Step 2: Derive shop status and display info from summary row ──
    if row:
        open_time = safe_str(row.get("Open_Time", ""))
        close_time = safe_str(row.get("Close_Time", ""))

        if open_time in ("", "00:00:00"):
            shop_status = "NOT_OPENED"
        elif close_time not in ("", "00:00:00"):
            shop_status = "CLOSED"
        else:
            shop_status = "OPEN"

        base["weather"] = safe_str(row.get("Weather", ""), "N/A") or "N/A"
        base["temperature"] = safe_str(row.get("Temperature", ""), "N/A") or "N/A"
        base["shop_status"] = shop_status

    # ── Step 3: Compute LIVE totals directly from Sales sheet ──
    # This ensures revenue/orders/items are always fresh, regardless of
    # whether update_daily_summary() has run or succeeded.
    live = _compute_live_totals(today)
    if live is not None:
        base["revenue"] = live["revenue"]
        base["orders"] = live["orders"]
        base["items"] = live["items"]
        base["best_product"] = live["best_product"]
    elif row:
        # Fallback to DailySummary values if live computation failed
        base["revenue"] = safe_int(row.get("Total_Sales_Amount", 0))
        base["orders"] = safe_int(row.get("Total_Transactions", 0))
        base["items"] = safe_int(row.get("Total_Items_Sold", 0))
        base["best_product"] = safe_str(row.get("Best_Selling_Product", ""), "N/A") or "N/A"

    return base