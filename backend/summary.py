# backend/summary.py

import pandas as pd
import os
import logging
from datetime import datetime
from backend.utils import normalize_date, ist_now
from backend.weather import get_weather_data
from backend.holidays import get_day_info
from backend.event_predictor import predict_special_event
from backend.sales_analyzer import get_sales_prediction
from backend import config

log = logging.getLogger(__name__)


def create_day_record():
    """Create today's record in Google Sheets if it does not already exist.

    Automatically populates:
        Weather, Temperature, Rain_Level  — from weather engine (cached)
        Is_Weekend, Is_Holiday            — from holiday engine
        Special_Event                     — from event predictor
        Expected_Revenue                  — from sales analyzer

    No manual input required.
    """
    today = ist_now().strftime("%Y-%m-%d")

    try:
        from backend.database import get_daily_summary, create_daily_summary
        record = get_daily_summary(today)
        if record is not None:
            return  # Record already exists for today
    except Exception as e:
        log.warning("Failed to check daily summary in database: %s. Falling back to Excel check.", e)
        if os.path.exists(config.SUMMARY_FILE):
            try:
                df = pd.read_excel(config.SUMMARY_FILE)
                df["Date"] = normalize_date(df["Date"].astype(str))
                if today in df["Date"].values:
                    return
            except Exception:
                pass

    # ── Auto-fetch weather (cached, max 1 API call per day) ───────────────
    weather_data = get_weather_data()
    log.info("Weather auto-populated on day create: %s", weather_data)

    # ── Auto-detect holiday/weekend ───────────────────────────────────────
    day_info = get_day_info()

    # ── Auto-predict special events ───────────────────────────────────────
    special_event = predict_special_event(weather_data, day_info)

    # ── Auto-predict expected revenue ─────────────────────────────────────
    prediction = get_sales_prediction(weather_data, day_info)

    new_row = {
        "Date": today,
        "Day_Name": ist_now().strftime("%A"),
        "Open_Time": "",
        "Close_Time": "",
        "Weather": weather_data["weather"],
        "Temperature": weather_data["temperature"],
        "Rain_Level": weather_data["rain_level"],
        "Is_Weekend": day_info["is_weekend"],
        "Is_Holiday": day_info["is_holiday"],
        "Special_Event": special_event,
        "Total_Sales_Amount": 0,
        "Total_Items_Sold": 0,
        "Total_Transactions": 0,
        "Best_Selling_Product": "",
        "Worst_Selling_Product": "",
        "Regular_Customer_Count": 0,
        "New_Customer_Count": 0,
        "Unknown_Customer_Count": 0,
        "Notes": "",
        "Expected_Revenue": prediction["expected_revenue"],
    }

    # Append demand tag to Special_Event if available
    demand_tag = prediction.get("demand_tag", "")
    if demand_tag and demand_tag != "Normal Business Day":
        if new_row["Special_Event"]:
            new_row["Special_Event"] += ", " + demand_tag
        else:
            new_row["Special_Event"] = demand_tag

    try:
        from backend.database import create_daily_summary
        create_daily_summary(new_row)
    except Exception as e:
        log.warning("Database write failed in create_day_record: %s", e)

    # Optional Excel Backup Sync
    if config.EXCEL_BACKUP_ENABLED:
        try:
            from backend.excel_backup import backup_summary_to_excel
            backup_summary_to_excel([new_row])
        except Exception as e:
            log.warning("Excel backup failed in create_day_record: %s", e)

    log.info("Daily record created with auto-populated intelligence")


def update_daily_summary():
    """
    Recalculate today's aggregates from sales database and write them to
    Google Sheets.
    """
    today = ist_now().strftime("%Y-%m-%d")

    from backend.database import get_sales, get_daily_summary, update_daily_summary as db_update_summary
    try:
        sales = get_sales()
        active_sales = [
            s for s in sales
            if s["Date"] == today and s["Status"] == "Active"
        ]

        summary = get_daily_summary(today)
        if not summary:
            log.warning("Daily summary record for today does not exist yet. Cannot update.")
            return
    except Exception as e:
        log.error("Failed to access database during update_daily_summary: %s", e)
        return

    if not active_sales:
        summary["Total_Sales_Amount"] = 0
        summary["Total_Items_Sold"] = 0
        summary["Total_Transactions"] = 0
        summary["Best_Selling_Product"] = ""
        summary["Worst_Selling_Product"] = ""
        summary["Regular_Customer_Count"] = 0
        summary["New_Customer_Count"] = 0
        summary["Unknown_Customer_Count"] = 0
    else:
        sales_df = pd.DataFrame(active_sales)
        total_sales_amount = sales_df["Total_Amount"].sum()
        total_items_sold = sales_df["Quantity"].sum()
        total_transactions = len(sales_df)

        product_sales = sales_df.groupby("Product_Name")["Quantity"].sum()
        best_product = product_sales.idxmax()
        worst_product = product_sales.idxmin()

        regular_count = len(sales_df[sales_df["Customer_Type"] == "Regular"])
        new_count = len(sales_df[sales_df["Customer_Type"] == "New"])
        unknown_count = len(sales_df[sales_df["Customer_Type"] == "Unknown"])

        summary["Total_Sales_Amount"] = total_sales_amount
        summary["Total_Items_Sold"] = total_items_sold
        summary["Total_Transactions"] = total_transactions
        summary["Best_Selling_Product"] = best_product
        summary["Worst_Selling_Product"] = worst_product
        summary["Regular_Customer_Count"] = regular_count
        summary["New_Customer_Count"] = new_count
        summary["Unknown_Customer_Count"] = unknown_count

    # Save update
    db_update_summary(summary)

    # Optional Excel Backup Sync
    if config.EXCEL_BACKUP_ENABLED:
        try:
            from backend.excel_backup import backup_summary_to_excel
            backup_summary_to_excel([summary])
        except Exception as e:
            log.warning("Excel backup failed in update_daily_summary: %s", e)

    print("Daily summary updated")


def open_shop(is_holiday=None, special_event=None, notes=""):
    """
    Record the shop open time for today in Google Sheets.
    Automatically fetches weather data and detects holidays/weekends.
    """
    today = ist_now().strftime("%Y-%m-%d")

    from backend.database import get_daily_summary, update_daily_summary as db_update_summary
    try:
        summary = get_daily_summary(today)
    except Exception as e:
        return False, f"Failed to access database: {e}"

    if not summary:
        return False, "Today's record not found in database"

    current_open_time = str(summary.get("Open_Time", "")).strip()
    if current_open_time and \
            current_open_time != "00:00:00" and \
            current_open_time.lower() != "nan" and \
            current_open_time != "":
        return False, "Shop already opened"

    # ── Auto-fetch weather ────────────────────────────────────────────────
    weather_data = get_weather_data()
    log.info("Weather fetched on open: %s", weather_data)

    # ── Auto-detect holiday/weekend ───────────────────────────────────────
    day_info = get_day_info()
    auto_holiday = day_info["is_holiday"]
    auto_event   = day_info["holiday_name"]
    auto_weekend = day_info["is_weekend"]

    # Caller can override is_holiday / special_event if desired
    final_holiday = is_holiday if is_holiday is not None else auto_holiday
    final_event   = special_event if special_event is not None else auto_event

    # ── Write to summary row ──────────────────────────────────────────────
    summary["Open_Time"]    = ist_now().strftime("%H:%M:%S")  # IST — critical fix
    summary["Weather"]      = weather_data["weather"]
    summary["Temperature"]  = weather_data["temperature"]
    summary["Rain_Level"]   = weather_data["rain_level"]
    summary["Is_Holiday"]   = final_holiday
    summary["Is_Weekend"]   = auto_weekend
    summary["Special_Event"]= final_event
    summary["Notes"]        = notes

    db_update_summary(summary)

    # Optional Excel Backup Sync
    if config.EXCEL_BACKUP_ENABLED:
        try:
            from backend.excel_backup import backup_summary_to_excel
            backup_summary_to_excel([summary])
        except Exception as e:
            log.warning("Excel backup failed in open_shop: %s", e)

    return True, "Shop opened successfully"


def close_shop():
    """Record the shop close time for today in Google Sheets."""
    today = ist_now().strftime("%Y-%m-%d")

    from backend.database import get_daily_summary, update_daily_summary as db_update_summary
    try:
        summary = get_daily_summary(today)
    except Exception as e:
        return False, f"Failed to access database: {e}"

    if not summary:
        return False, "Today's record not found in database"

    summary["Close_Time"] = ist_now().strftime("%H:%M:%S")  # IST — critical fix

    db_update_summary(summary)

    # Optional Excel Backup Sync
    if config.EXCEL_BACKUP_ENABLED:
        try:
            from backend.excel_backup import backup_summary_to_excel
            backup_summary_to_excel([summary])
        except Exception as e:
            log.warning("Excel backup failed in close_shop: %s", e)

    return True, "Shop closed successfully"


def get_shop_status():
    """
    Return the current shop status for today.

    Returns one of:
        "NOT_OPENED"  — today's record exists but Open_Time is blank
        "OPEN"        — shop has been opened, not yet closed
        "CLOSED"      — shop has been opened and closed
        "NO_RECORD"   — no record found for today
    """
    today = ist_now().strftime("%Y-%m-%d")

    from backend.database import get_daily_summary
    try:
        summary = get_daily_summary(today)
    except Exception as e:
        print(f"Failed to fetch live shop status: {e}. Falling back to Excel.")
        if os.path.exists(config.SUMMARY_FILE):
            try:
                df = pd.read_excel(config.SUMMARY_FILE)
                df["Date"] = normalize_date(df["Date"].astype(str))
                row = df[df["Date"] == today]
                if len(row) > 0:
                    open_time = str(row.iloc[0].get("Open_Time", "")).strip()
                    close_time = str(row.iloc[0].get("Close_Time", "")).strip()
                    if open_time in ["", "nan", "00:00:00"]:
                        return "NOT_OPENED"
                    if close_time not in ["", "nan", "00:00:00"]:
                        return "CLOSED"
                    return "OPEN"
            except Exception:
                pass
        return "NO_RECORD"

    if not summary:
        return "NO_RECORD"

    open_time = str(summary.get("Open_Time", "")).strip()
    close_time = str(summary.get("Close_Time", "")).strip()

    if open_time in ["", "nan", "00:00:00"]:
        return "NOT_OPENED"

    if close_time not in ["", "nan", "00:00:00"]:
        return "CLOSED"

    return "OPEN"