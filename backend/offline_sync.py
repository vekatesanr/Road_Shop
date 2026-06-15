# backend/offline_sync.py

import os
import json
import time
import logging
import threading
from datetime import datetime
from backend import config
from backend import Google_Sheet
from backend import database
from backend.utils import safe_int, safe_str

log = logging.getLogger(__name__)

# Sale columns in Google Sheet order — must match sales.py _SALE_COLUMNS
_SALE_COLUMNS = [
    "Sale_ID", "Date", "Time", "Day_Name",
    "Product_Name", "Sale_Type", "Variant",
    "Quantity", "Quantity_Unit", "Unit_Price",
    "Total_Amount", "Customer_Type", "Status",
]

# Lock for protecting file writes and thread-safety
_sync_lock = threading.Lock()
_worker_thread = None
_should_run = True


def load_pending() -> list:
    """Load the list of pending operations from pending_sync.json."""
    if not os.path.exists(config.PENDING_SYNC_FILE):
        return []
    try:
        with open(config.PENDING_SYNC_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except Exception as e:
        log.error("Failed to load pending sync file: %s", e)
        return []


def save_pending(pending_list: list) -> None:
    """Save the list of pending operations to pending_sync.json."""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(config.PENDING_SYNC_FILE), exist_ok=True)
        with open(config.PENDING_SYNC_FILE, "w") as f:
            json.dump(pending_list, f, indent=2)
    except Exception as e:
        log.error("Failed to save pending sync file: %s", e)


def add_pending(op_type: str, action: str, data: dict) -> None:
    """
    Queue a failed write operation to pending_sync.json.
    op_type: "sale" | "summary"
    action: "save" | "update" | "create"
    """
    with _sync_lock:
        pending = load_pending()
        
        # Check if we can consolidate/deduplicate updates to avoid redundant requests
        # (e.g. if the same sale is updated multiple times, we can update the cached values)
        # However, to preserve exact sequence of user actions, simple appending is safest.
        
        new_entry = {
            "type": op_type,
            "action": action,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        pending.append(new_entry)
        save_pending(pending)
        log.warning("Added operation to offline queue. Total pending: %d", len(pending))


def get_pending_count() -> int:
    """Return the number of pending operations in the queue."""
    with _sync_lock:
        return len(load_pending())


def _process_single_item(item: dict) -> bool:
    """
    Process a single sync item against Google Sheets.
    Returns True if successfully processed, False if it failed.
    """
    op_type = item.get("type")
    action = item.get("action")
    data = item.get("data", {})

    try:
        if op_type == "sale":
            if Google_Sheet.sales_sheet is None:
                return False
                
            if action == "save":
                row = [data.get(col, "") for col in _SALE_COLUMNS]
                sanitized = Google_Sheet._sanitize_row(row)
                Google_Sheet.sales_sheet.append_row(sanitized)
                log.info("Offline sync: Saved sale ID %s", data.get("Sale_ID"))
                return True
                
            elif action == "update":
                sale_id = data.get("Sale_ID")
                updates = data.get("updates", {})
                records = Google_Sheet.sales_sheet.get_all_records()
                target_row = None
                for index, r in enumerate(records, start=2):
                    if safe_int(r.get("Sale_ID")) == sale_id:
                        target_row = index
                        break
                
                if target_row:
                    target_record = database._cast_sale_record(records[target_row - 2])
                    for key, val in updates.items():
                        if key in target_record:
                            target_record[key] = val
                    row_values = [target_record.get(col, "") for col in _SALE_COLUMNS]
                    sanitized = Google_Sheet._sanitize_row(row_values)
                    Google_Sheet.sales_sheet.update(f"A{target_row}:M{target_row}", [sanitized])
                    log.info("Offline sync: Updated sale ID %s", sale_id)
                else:
                    log.warning("Offline sync: Sale ID %s for update not found in Sheet", sale_id)
                return True # Treat as success so it is removed, or could skip

        elif op_type == "summary":
            if Google_Sheet.summary_sheet is None:
                return False

            if action == "create" or action == "update":
                date_str = data.get("Date")
                records = Google_Sheet.summary_sheet.get_all_records()
                target_row = None
                for index, r in enumerate(records, start=2):
                    if safe_str(r.get("Date")) == date_str:
                        target_row = index
                        break
                
                row_values = [data.get(col, "") for col in database._SUMMARY_COLUMNS]
                sanitized = Google_Sheet._sanitize_row(row_values)
                
                if target_row:
                    Google_Sheet.summary_sheet.update(f"A{target_row}:T{target_row}", [sanitized])
                    log.info("Offline sync: Updated summary for date %s", date_str)
                else:
                    Google_Sheet.summary_sheet.append_row(sanitized)
                    log.info("Offline sync: Created summary for date %s", date_str)
                return True

        return False
    except Exception as e:
        log.error("Failed to process sync item %s: %s", item, e)
        return False


def process_pending() -> int:
    """
    Attempt to replay all queued operations in order.
    Stops at the first failure.
    Returns the number of successfully synced operations.
    """
    if not database.is_connected():
        return 0

    with _sync_lock:
        pending = load_pending()
        if not pending:
            return 0

        log.info("Starting processing of %d pending sync operations...", len(pending))
        
        # Re-resolve sheets if needed
        database._ensure_sheets()

        synced_count = 0
        failed_index = None

        for index, item in enumerate(pending):
            success = _process_single_item(item)
            if success:
                synced_count += 1
            else:
                log.warning("Offline sync failed at item index %d. Aborting replay.", index)
                failed_index = index
                break

        # Update the pending list with remaining items
        if failed_index is not None:
            remaining = pending[failed_index:]
        else:
            remaining = []
        
        save_pending(remaining)
        
        if synced_count > 0:
            log.info("Offline sync complete: successfully processed %d items. Remaining in queue: %d", 
                     synced_count, len(remaining))
            
            # Since sales or summaries changed, refresh Excel backups if enabled
            if config.EXCEL_BACKUP_ENABLED:
                try:
                    from backend.excel_backup import sync_google_to_excel
                    sync_google_to_excel()
                except Exception as e:
                    log.warning("Post-sync Excel backup failed: %s", e)

        return synced_count


def _sync_worker_loop():
    """Background worker target function."""
    global _should_run
    log.info("Background sync worker started.")
    while _should_run:
        try:
            # Check if there are pending items and try to process them
            if get_pending_count() > 0:
                process_pending()
        except Exception as e:
            log.error("Error in sync worker loop: %s", e)
        
        # Sleep for the configured interval
        for _ in range(config.SYNC_INTERVAL_SECONDS):
            if not _should_run:
                break
            time.sleep(1)


def start_sync_worker():
    """Start the background thread for auto-sync retry."""
    global _worker_thread, _should_run
    with _sync_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _should_run = True
        _worker_thread = threading.Thread(target=_sync_worker_loop, daemon=True)
        _worker_thread.start()


def stop_sync_worker():
    """Stop the background sync worker thread."""
    global _should_run, _worker_thread
    _should_run = False
    if _worker_thread is not None:
        _worker_thread.join(timeout=2)
        log.info("Background sync worker stopped.")
