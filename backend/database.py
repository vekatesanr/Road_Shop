# backend/database.py

import logging
from datetime import datetime
from backend import Google_Sheet
from backend import config
from backend.utils import safe_float, safe_int, safe_str

log = logging.getLogger(__name__)

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
    if Google_Sheet.spreadsheet is None:
        Google_Sheet.connect_google_sheets()
    return Google_Sheet.spreadsheet is not None


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

def get_sales() -> list[dict]:
    """Retrieve all sales from Google Sheets."""
    _ensure_sheets()
    if Google_Sheet.sales_sheet is None:
        raise ConnectionError("Google Sheet is disconnected. Cannot retrieve sales.")
    
    try:
        records = Google_Sheet.sales_sheet.get_all_records()
        return [_cast_sale_record(r) for r in records]
    except Exception as e:
        log.error("Failed to get sales from Google Sheets: %s", e)
        raise


def get_max_sale_id() -> int:
    """Get the current maximum Sale_ID from the Google Sheet."""
    try:
        sales = get_sales()
        if not sales:
            return 0
        return max(s["Sale_ID"] for s in sales)
    except Exception:
        log.warning("Failed to get max sale ID from Google Sheet, default to 0")
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

def get_daily_summary(date_str: str) -> dict | None:
    """Retrieve the daily summary record for a specific date (YYYY-MM-DD)."""
    _ensure_sheets()
    if Google_Sheet.summary_sheet is None:
        raise ConnectionError("Google Sheet is disconnected. Cannot retrieve daily summary.")

    try:
        records = Google_Sheet.summary_sheet.get_all_records()
        for r in records:
            if safe_str(r.get("Date")) == date_str:
                return _cast_summary_record(r)
        return None
    except Exception as e:
        log.error("Failed to get daily summary from Google Sheets: %s", e)
        raise


def get_daily_summaries(days: int = 30) -> list[dict]:
    """Get the daily summaries for the last N records."""
    _ensure_sheets()
    if Google_Sheet.summary_sheet is None:
        raise ConnectionError("Google Sheet is disconnected. Cannot retrieve daily summaries.")

    try:
        records = Google_Sheet.summary_sheet.get_all_records()
        casted = [_cast_summary_record(r) for r in records]
        return casted[-days:] if len(casted) > days else casted
    except Exception as e:
        log.error("Failed to get daily summaries from Google Sheets: %s", e)
        raise


def create_daily_summary(record: dict) -> None:
    """Create a new daily summary row in Google Sheets."""
    _ensure_sheets()
    if Google_Sheet.summary_sheet is None:
        from backend.offline_sync import add_pending
        add_pending("summary", "create", record)
        return

    try:
        row = [record.get(col, "") for col in _SUMMARY_COLUMNS]
        sanitized = Google_Sheet._sanitize_row(row)
        Google_Sheet.summary_sheet.append_row(sanitized)
        log.info("Daily summary row created in Google Sheets for date %s", record.get("Date"))
    except Exception as e:
        log.error("Error creating daily summary row in Google Sheets: %s. Queueing.", e)
        from backend.offline_sync import add_pending
        add_pending("summary", "create", record)


def update_daily_summary(summary_record: dict) -> tuple[bool, str]:
    """
    Update or create a daily summary row in Google Sheets.
    Matches by 'Date' column.
    """
    date_str = summary_record.get("Date")
    _ensure_sheets()
    if Google_Sheet.summary_sheet is None:
        from backend.offline_sync import add_pending
        add_pending("summary", "update", summary_record)
        return True, "Offline. Summary update queued."

    try:
        records = Google_Sheet.summary_sheet.get_all_records()
        target_row = None
        for index, row in enumerate(records, start=2):
            if safe_str(row.get("Date")) == date_str:
                target_row = index
                break

        row_values = [summary_record.get(col, "") for col in _SUMMARY_COLUMNS]
        sanitized = Google_Sheet._sanitize_row(row_values)

        if target_row:
            Google_Sheet.summary_sheet.update(
                f"A{target_row}:T{target_row}",
                [sanitized]
            )
            log.info("Daily summary updated in Google Sheets for date %s", date_str)
        else:
            Google_Sheet.summary_sheet.append_row(sanitized)
            log.info("Daily summary appended in Google Sheets for date %s", date_str)

        return True, "Daily summary synced successfully"
    except Exception as e:
        log.error("Error updating daily summary in Google Sheets: %s. Queueing.", e)
        from backend.offline_sync import add_pending
        add_pending("summary", "update", summary_record)
        return True, "Connection lost. Summary update queued offline."
