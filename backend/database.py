# backend/database.py

import logging
import threading
from backend import Google_Sheet
from backend import config
from backend.utils import safe_float, safe_int, safe_str
from datetime import datetime

log = logging.getLogger(__name__)

# Lock for protecting Sale ID generation from race conditions
_sale_id_lock = threading.Lock()

# Column names in DailySummary sheet in order
_SUMMARY_COLUMNS = [
    "Date", "Day_Name", "Open_Time", "Close_Time",
    "Weather", "Temperature", "Rain_Level",
    "Is_Weekend", "Is_Holiday", "Special_Event",
    "Total_Sales_Amount", "Total_Items_Sold", "Total_Transactions",
    "Best_Selling_Product", "Worst_Selling_Product",
    "Regular_Customer_Count", "New_Customer_Count", "Unknown_Customer_Count",
    "Notes", "Expected_Revenue"
]


def is_connected() -> bool:
    """Return True if connected to Google Sheets, False otherwise."""
    return Google_Sheet.ensure_connection()


def _ensure_sheets():
    """Ensure sales_sheet and summary_sheet are resolved."""
    if Google_Sheet.sales_sheet is None or Google_Sheet.summary_sheet is None:
        Google_Sheet.connect_google_sheets()


def _cast_sale_record(row_dict: dict) -> dict:
    """
    Cast a sale record read from Google Sheets to proper types.
    Maps legacy/spelled Google Sheet columns to standard Excel schema names:
      - 'Sales_ID' / 'Sale_ID' -> 'Sale_ID'
      - 'Sales_Type' / 'Sale_Type' -> 'Sale_Type'
      - 'Quanity' / 'Quantity' -> 'Quantity'
      - 'Quanity_Unit' / 'Quantity_Unit' -> 'Quantity_Unit'
    """
    sale_id = row_dict.get("Sales_ID") if "Sales_ID" in row_dict else row_dict.get("Sale_ID")
    sale_type = row_dict.get("Sales_Type") if "Sales_Type" in row_dict else row_dict.get("Sale_Type")
    quantity = row_dict.get("Quanity") if "Quanity" in row_dict else row_dict.get("Quantity")
    quantity_unit = row_dict.get("Quanity_Unit") if "Quanity_Unit" in row_dict else row_dict.get("Quantity_Unit")

    return {
        "Sale_ID": safe_int(sale_id),
        "Date": safe_str(row_dict.get("Date")),
        "Time": safe_str(row_dict.get("Time")),
        "Day_Name": safe_str(row_dict.get("Day_Name")),
        "Product_Name": safe_str(row_dict.get("Product_Name")),
        "Sale_Type": safe_str(sale_type),
        "Variant": safe_str(row_dict.get("Variant")),
        "Quantity": safe_float(quantity),
        "Quantity_Unit": safe_str(quantity_unit),
        "Unit_Price": safe_float(row_dict.get("Unit_Price")),
        "Total_Amount": safe_float(row_dict.get("Total_Amount")),
        "Customer_Type": safe_str(row_dict.get("Customer_Type"), "Unknown"),
        "Status": safe_str(row_dict.get("Status"), "Active"),
    }


def _cast_summary_record(row_dict: dict) -> dict:
    """Cast a daily summary record read from Google Sheets to proper types."""
    is_weekend_val = row_dict.get("Is_Weekend")
    if isinstance(is_weekend_val, str):
        is_weekend = is_weekend_val.upper() == "TRUE"
    else:
        is_weekend = bool(is_weekend_val)

    is_holiday_val = row_dict.get("Is_Holiday")
    if isinstance(is_holiday_val, str):
        is_holiday = is_holiday_val.upper() == "TRUE"
    else:
        is_holiday = bool(is_holiday_val)

    return {
        "Date": safe_str(row_dict.get("Date")),
        "Day_Name": safe_str(row_dict.get("Day_Name")),
        "Open_Time": safe_str(row_dict.get("Open_Time")),
        "Close_Time": safe_str(row_dict.get("Close_Time")),
        "Weather": safe_str(row_dict.get("Weather"), "N/A"),
        "Temperature": safe_str(row_dict.get("Temperature"), "N/A"),
        "Rain_Level": safe_str(row_dict.get("Rain_Level"), "N/A"),
        "Is_Weekend": is_weekend,
        "Is_Holiday": is_holiday,
        "Special_Event": safe_str(row_dict.get("Special_Event")),
        "Total_Sales_Amount": safe_float(row_dict.get("Total_Sales_Amount")),
        "Total_Items_Sold": safe_float(row_dict.get("Total_Items_Sold")),
        "Total_Transactions": safe_int(row_dict.get("Total_Transactions")),
        "Best_Selling_Product": safe_str(row_dict.get("Best_Selling_Product")),
        "Worst_Selling_Product": safe_str(row_dict.get("Worst_Selling_Product")),
        "Regular_Customer_Count": safe_int(row_dict.get("Regular_Customer_Count")),
        "New_Customer_Count": safe_int(row_dict.get("New_Customer_Count")),
        "Unknown_Customer_Count": safe_int(row_dict.get("Unknown_Customer_Count")),
        "Notes": safe_str(row_dict.get("Notes")),
        "Expected_Revenue": safe_float(row_dict.get("Expected_Revenue")),
    }


# ── SALES ACCESSORS ───────────────────────────────────────────────────────────

@Google_Sheet.with_retry
def get_sales() -> list[dict]:
    """Retrieve all sales from Google Sheets."""
    _ensure_sheets()
    if Google_Sheet.sales_sheet is None:
        raise ConnectionError("Google Sheet is disconnected. Cannot retrieve sales.")

    records = Google_Sheet.sales_sheet.get_all_records()
    return [_cast_sale_record(r) for r in records]


def get_max_sale_id() -> int:
    """
    Get the current maximum Sale_ID from the Google Sheet.

    Uses col_values(1) to read only the Sale_ID column — much faster than
    get_all_records() which reads every cell.  Thread-safe via _sale_id_lock.
    """
    with _sale_id_lock:
        try:
            _ensure_sheets()
            if Google_Sheet.sales_sheet is None:
                log.warning("Cannot read max Sale ID — sheet not connected, defaulting to 0")
                return 0

            # col_values(1) returns all values in column A (Sale_ID) as strings
            col_vals = Google_Sheet.sales_sheet.col_values(1)

            # Skip header row, filter to numeric values only
            max_id = 0
            for val in col_vals[1:]:  # skip header
                parsed = safe_int(val, default=0)
                if parsed > max_id:
                    max_id = parsed

            log.info("Max Sale ID from Google Sheet: %d", max_id)
            return max_id

        except Exception as e:
            log.warning("Failed to get max sale ID from Google Sheet: %s. Retrying after reconnect...", e)
            # Single retry after reconnect
            try:
                Google_Sheet.connect_google_sheets()
                if Google_Sheet.sales_sheet is None:
                    return 0
                col_vals = Google_Sheet.sales_sheet.col_values(1)
                max_id = 0
                for val in col_vals[1:]:
                    parsed = safe_int(val, default=0)
                    if parsed > max_id:
                        max_id = parsed
                log.info("Max Sale ID after reconnect: %d", max_id)
                return max_id
            except Exception as retry_err:
                log.error("Retry also failed for max sale ID: %s, defaulting to 0", retry_err)
                return 0


def _build_gs_sale_row(sale_record: dict) -> list:
    """Build a list matching the Google Sheet columns schema."""
    return [
        sale_record.get("Sale_ID"),
        sale_record.get("Date"),
        sale_record.get("Time"),
        sale_record.get("Day_Name"),
        sale_record.get("Product_Name"),
        sale_record.get("Sale_Type"),
        sale_record.get("Variant"),
        sale_record.get("Quantity"),
        sale_record.get("Quantity_Unit"),
        sale_record.get("Unit_Price"),
        sale_record.get("Total_Amount"),
        sale_record.get("Customer_Type"),
        sale_record.get("Status")
    ]


@Google_Sheet.with_retry
def save_sale(sale_record: dict) -> None:
    """
    Save a new sale record to Google Sheets.
    If offline, delegates to pending sync.
    """
    _ensure_sheets()
    if Google_Sheet.sales_sheet is None:
        from backend.offline_sync import add_pending
        log.warning("Google Sheets offline. Saving sale locally to pending sync.")
        add_pending("sale", "save", sale_record)
        return

    try:
        row = _build_gs_sale_row(sale_record)
        sanitized = Google_Sheet._sanitize_row(row)
        Google_Sheet.sales_sheet.append_row(sanitized)
        log.info("Sale ID %s saved to Google Sheets successfully.", sale_record.get("Sale_ID"))
    except Exception as e:
        log.error("Error saving sale to Google Sheets: %s. Queueing offline.", e)
        from backend.offline_sync import add_pending
        add_pending("sale", "save", sale_record)


@Google_Sheet.with_retry
def update_sale(sale_id: int, updates: dict) -> tuple[bool, str]:
    """
    Update field values of an existing sale by Sale_ID.
    If offline, queue to offline sync.
    """
    _ensure_sheets()
    if Google_Sheet.sales_sheet is None:
        from backend.offline_sync import add_pending
        add_pending("sale", "update", {"Sale_ID": sale_id, "updates": updates})
        return True, "Offline. Update queued."

    try:
        records = Google_Sheet.sales_sheet.get_all_records()
        target_row = None
        for index, row in enumerate(records, start=2):
            val = row.get("Sales_ID") if "Sales_ID" in row else row.get("Sale_ID")
            if safe_int(val) == sale_id:
                target_row = index
                break

        if not target_row:
            return False, f"Sale ID {sale_id} not found."

        # Fetch current record to build updated row
        target_record = _cast_sale_record(records[target_row - 2])
        for key, val in updates.items():
            if key in target_record:
                target_record[key] = val

        row_values = _build_gs_sale_row(target_record)
        sanitized = Google_Sheet._sanitize_row(row_values)

        Google_Sheet.sales_sheet.update(
            f"A{target_row}:M{target_row}",
            [sanitized]
        )
        log.info("Sale ID %s updated in Google Sheets.", sale_id)
        return True, "Sale updated successfully"
    except Exception as e:
        log.error("Error updating sale ID %s in Google Sheets: %s. Queueing.", sale_id, e)
        from backend.offline_sync import add_pending
        add_pending("sale", "update", {"Sale_ID": sale_id, "updates": updates})
        return True, "Connection lost. Update queued offline."


def delete_sale(sale_id: int) -> tuple[bool, str]:
    """Soft delete a sale by setting Status = 'Deleted'."""
    return update_sale(sale_id, {"Status": "Deleted"})


# ── DAILY SUMMARY ACCESSORS ───────────────────────────────────────────────────

@Google_Sheet.with_retry
def get_daily_summary(date_str: str) -> dict | None:
    """Retrieve the daily summary record for a specific date (YYYY-MM-DD)."""
    _ensure_sheets()
    if Google_Sheet.summary_sheet is None:
        raise ConnectionError("Google Sheet is disconnected. Cannot retrieve daily summary.")

    records = Google_Sheet.summary_sheet.get_all_records()
    for r in records:
        if safe_str(r.get("Date")) == date_str:
            return _cast_summary_record(r)
    return None


@Google_Sheet.with_retry
def get_daily_summaries(days: int = 30) -> list[dict]:
    """Get the daily summaries for the last N records."""
    _ensure_sheets()
    if Google_Sheet.summary_sheet is None:
        raise ConnectionError("Google Sheet is disconnected. Cannot retrieve daily summaries.")

    records = Google_Sheet.summary_sheet.get_all_records()
    casted = [_cast_summary_record(r) for r in records]
    return casted[-days:] if len(casted) > days else casted


@Google_Sheet.with_retry
def create_daily_summary(record: dict) -> None:
    """Create a new daily summary row in Google Sheets."""
    log.info("[SUMMARY] create_daily_summary entered for date=%s", record.get("Date"))
    _ensure_sheets()
    if Google_Sheet.summary_sheet is None:
        log.warning("[SUMMARY] summary_sheet is None — queuing offline (create)")
        from backend.offline_sync import add_pending
        add_pending("summary", "create", record)
        return

    try:
        log.info("[SUMMARY] data prepared, writing new row to Google Sheet")
        row = [record.get(col, "") for col in _SUMMARY_COLUMNS]
        sanitized = Google_Sheet._sanitize_row(row)
        Google_Sheet.summary_sheet.append_row(sanitized)
        log.info("[SUMMARY] success — daily summary row created for date %s", record.get("Date"))
    except Exception as e:
        log.error("[SUMMARY] failed to create daily summary row: %s. Queuing offline.", e)
        from backend.offline_sync import add_pending
        add_pending("summary", "create", record)


@Google_Sheet.with_retry
def update_daily_summary(summary_record: dict) -> tuple[bool, str]:
    """
    Update or create a daily summary row in Google Sheets.
    Matches by 'Date' column.
    """
    date_str = summary_record.get("Date")
    log.info("[SUMMARY] update_daily_summary entered for date=%s", date_str)
    _ensure_sheets()
    if Google_Sheet.summary_sheet is None:
        log.warning("[SUMMARY] summary_sheet is None — queuing offline (update)")
        from backend.offline_sync import add_pending
        add_pending("summary", "update", summary_record)
        return True, "Offline. Summary update queued."

    try:
        log.info("[SUMMARY] reading existing rows from DailySummary sheet")
        records = Google_Sheet.summary_sheet.get_all_records()
        target_row = None
        for index, row in enumerate(records, start=2):
            if safe_str(row.get("Date")) == date_str:
                target_row = index
                break

        log.info("[SUMMARY] data prepared — %s row for date %s",
                 "updating existing" if target_row else "appending new", date_str)
        row_values = [summary_record.get(col, "") for col in _SUMMARY_COLUMNS]
        sanitized = Google_Sheet._sanitize_row(row_values)

        if target_row:
            log.info("[SUMMARY] writing to Google Sheet row %d", target_row)
            Google_Sheet.summary_sheet.update(
                f"A{target_row}:T{target_row}",
                [sanitized]
            )
            log.info("[SUMMARY] success — daily summary updated for date %s", date_str)
        else:
            log.info("[SUMMARY] writing new append row to Google Sheet")
            Google_Sheet.summary_sheet.append_row(sanitized)
            log.info("[SUMMARY] success — daily summary appended for date %s", date_str)

        return True, "Daily summary synced successfully"
    except Exception as e:
        log.error("[SUMMARY] failed — error updating daily summary: %s. Queuing offline.", e)
        from backend.offline_sync import add_pending
        add_pending("summary", "update", summary_record)
        return True, "Connection lost. Summary update queued offline."
