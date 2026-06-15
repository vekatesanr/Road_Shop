# backend/Google_Sheet.py

import gspread
import logging
import math
from datetime import datetime, date
from oauth2client.service_account import ServiceAccountCredentials
from backend import config

log = logging.getLogger(__name__)

scope = config.GOOGLE_SCOPES

# ── Safe module-level initialization ──────────────────────────────────────────
# Wrapped in try/except so the app never crashes on import even if
# Google Sheets is unreachable, credentials are expired, or worksheet
# names have trailing spaces.

spreadsheet = None
sales_sheet = None
summary_sheet = None

def connect_google_sheets():
    global spreadsheet, sales_sheet, summary_sheet
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            config.CREDENTIALS_PATH,
            scope
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(config.GOOGLE_SHEET_ID)
        log.info("Google Sheet connected successfully")
        
        sales_sheet = get_worksheet_safe(config.SALES_SHEET_NAME)
        summary_sheet = get_worksheet_safe(config.SUMMARY_SHEET_NAME)

        if sales_sheet:
            log.info("Sales Sheet: %s", sales_sheet.title)
        else:
            log.warning("Sales worksheet NOT FOUND")

        if summary_sheet:
            log.info("Summary Sheet: %s", summary_sheet.title)
        else:
            log.warning("DailySummary worksheet NOT FOUND")
    except Exception as e:
        log.warning("Google Sheet init failed: %s", e)

# ── Safe worksheet finder ─────────────────────────────────────────────────────

def get_worksheet_safe(name):
    """
    Find a worksheet by name with whitespace-trimming and case-insensitive
    matching.  Returns the worksheet object or None.

    This handles the known issue where worksheet titles contain trailing
    spaces (e.g. 'DailySummary ' instead of 'DailySummary').

    Never raises an exception — returns None on any failure.
    """
    if spreadsheet is None:
        log.warning("get_worksheet_safe('%s'): spreadsheet not connected", name)
        return None

    try:
        target = name.strip().lower()
        for ws in spreadsheet.worksheets():
            if ws.title.strip().lower() == target:
                log.info("Worksheet '%s' matched → '%s'", name, ws.title)
                return ws
        log.warning("Worksheet '%s' not found (available: %s)",
                     name,
                     [ws.title for ws in spreadsheet.worksheets()])
        return None
    except Exception as e:
        log.warning("get_worksheet_safe('%s') error: %s", name, e)
        return None

# Initial connection attempt
connect_google_sheets()

# ── Row sanitizer ─────────────────────────────────────────────────────────────

def _sanitize_value(v):
    """
    Convert a single value to a Google-Sheets-safe type.

    - NaN / None → ""
    - pandas Timestamp / datetime / date → "YYYY-MM-DD" or "HH:MM:SS"
    - float with no fractional part → int
    - bool → TRUE/FALSE string
    - Everything else → str
    """
    import pandas as pd

    if v is None:
        return ""

    # Check NaN (works for float nan and numpy nan)
    if isinstance(v, float) and math.isnan(v):
        return ""

    # pandas NaT
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass

    # pandas Timestamp
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")

    # Python datetime / date
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")

    # Boolean → string
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"

    # Float → int if no fractional part, else round
    if isinstance(v, float):
        if v == int(v):
            return int(v)
        return round(v, 2)

    return str(v) if not isinstance(v, str) else v


def _sanitize_row(row):
    """Sanitize every value in a list for Google Sheets."""
    return [_sanitize_value(v) for v in row]


# ── Keep compatibility functions for transition phase ────────────────────────

def save_sale_to_google_sheet(sale_record):
    """Append a single sale record row to the Sales worksheet."""
    if sales_sheet is None:
        log.warning("save_sale_to_google_sheet: Sales sheet not available, skipping")
        return

    try:
        row = [
            sale_record["Sale_ID"],
            sale_record["Date"],
            sale_record["Time"],
            sale_record["Day_Name"],
            sale_record["Product_Name"],
            sale_record["Sale_Type"],
            sale_record["Variant"],
            sale_record["Quantity"],
            sale_record["Quantity_Unit"],
            sale_record["Unit_Price"],
            sale_record["Total_Amount"],
            sale_record["Customer_Type"],
            sale_record["Status"]
        ]
        sales_sheet.append_row(_sanitize_row(row))
        log.info("Sale %s synced to Google Sheet", sale_record["Sale_ID"])
    except Exception as e:
        log.warning("save_sale_to_google_sheet error: %s", e)


def update_daily_summary_sheet(summary_record):
    """Update or append today's summary row in the DailySummary worksheet."""
    if summary_sheet is None:
        log.warning("update_daily_summary_sheet: Summary sheet not available, skipping")
        return

    try:
        records = summary_sheet.get_all_records()

        target_row = None
        for index, row in enumerate(records, start=2):
            if str(row.get("Date")) == str(summary_record["Date"]):
                target_row = index
                break

        values = [
            summary_record["Date"],
            summary_record["Day_Name"],
            summary_record["Open_Time"],
            summary_record["Close_Time"],
            summary_record["Weather"],
            summary_record["Temperature"],
            summary_record["Rain_Level"],
            summary_record["Is_Weekend"],
            summary_record["Is_Holiday"],
            summary_record["Special_Event"],
            summary_record["Total_Sales_Amount"],
            summary_record["Total_Items_Sold"],
            summary_record["Total_Transactions"],
            summary_record["Best_Selling_Product"],
            summary_record["Worst_Selling_Product"],
            summary_record["Regular_Customer_Count"],
            summary_record["New_Customer_Count"],
            summary_record["Unknown_Customer_Count"],
            summary_record["Notes"],
            summary_record.get("Expected_Revenue", 0)
        ]

        safe_values = _sanitize_row(values)

        if target_row:
            summary_sheet.update(
                f"A{target_row}:T{target_row}",
                [safe_values]
            )
        else:
            summary_sheet.append_row(safe_values)

        log.info("Daily summary synced for %s", summary_record["Date"])
    except Exception as e:
        log.warning("update_daily_summary_sheet error: %s", e)


def sync_daily_summary_to_google():
    """
    Full sync: read daily_summary.xlsx and overwrite the DailySummary
    worksheet.  Headers are preserved.
    """
    if summary_sheet is None:
        log.warning("sync_daily_summary_to_google: Summary sheet not available, skipping")
        return

    try:
        import pandas as pd

        log.info("SYNC STARTED")

        summary_df = pd.read_excel(config.SUMMARY_FILE)

        summary_sheet.clear()

        headers = summary_df.columns.tolist()
        summary_sheet.append_row(headers)

        for row in summary_df.values.tolist():
            summary_sheet.append_row(_sanitize_row(row))

        log.info("SYNC COMPLETED — %d rows written", len(summary_df))

    except Exception as e:
        log.warning("sync_daily_summary_to_google error: %s", e)