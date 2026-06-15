# backend/dashboard.py

import os
import pandas as pd
from datetime import datetime
from backend.utils import normalize_date, safe_int, safe_str, ist_now
from backend import config
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


def get_dashboard_data() -> dict:
    """
    Read today's row from Google Sheets daily summary and return a dict for templates.

    Keys:
        date, day, weather, temperature — display info
        revenue, orders, items           — today's aggregate totals
        best_product                     — top-selling product name
        shop_status                      — NOT_OPENED | OPEN | CLOSED

    Never returns None. Returns safe zero-state dict on any error.
    """
    today = ist_now().strftime("%Y-%m-%d")
    base = {**_EMPTY_DATA, "date": today, "day": ist_now().strftime("%A")}

    try:
        from backend.database import get_daily_summary
        row = get_daily_summary(today)
    except Exception as e:
        print(f"[dashboard] Live database access failed: {e}. Falling back to Excel.")
        try:
            if os.path.exists(config.SUMMARY_FILE):
                df = pd.read_excel(config.SUMMARY_FILE)
                if not df.empty:
                    df["Date"] = normalize_date(df["Date"].astype(str))
                    df_row = df[df["Date"] == today]
                    if len(df_row) > 0:
                        row = df_row.iloc[0].to_dict()
                    else:
                        row = None
                else:
                    row = None
            else:
                row = None
        except Exception as ex:
            print(f"[dashboard] Excel fallback failed: {ex}")
            return base

    if not row:
        return base

    # Derive shop status from stored times
    open_time = safe_str(row.get("Open_Time", ""))
    close_time = safe_str(row.get("Close_Time", ""))

    if open_time in ("", "00:00:00"):
        shop_status = "NOT_OPENED"
    elif close_time not in ("", "00:00:00"):
        shop_status = "CLOSED"
    else:
        shop_status = "OPEN"

    return {
        "date": ist_now().strftime("%Y-%m-%d"),
        "day": ist_now().strftime("%A"),
        "weather": safe_str(row.get("Weather", ""), "N/A") or "N/A",
        "temperature": safe_str(row.get("Temperature", ""), "N/A") or "N/A",
        "revenue": safe_int(row.get("Total_Sales_Amount", 0)),
        "orders": safe_int(row.get("Total_Transactions", 0)),
        "items": safe_int(row.get("Total_Items_Sold", 0)),
        "best_product": safe_str(row.get("Best_Selling_Product", ""), "N/A") or "N/A",
        "shop_status": shop_status,
    }