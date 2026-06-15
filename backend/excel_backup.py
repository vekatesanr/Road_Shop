# backend/excel_backup.py

import os
import shutil
import logging
import tempfile
import pandas as pd
from backend import config
from backend import database
from backend.utils import normalize_date

log = logging.getLogger(__name__)


def _write_df_atomically(df: pd.DataFrame, target_path: str) -> None:
    """Write a DataFrame to a target Excel file path atomically."""
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    # Write to a temporary file first
    temp_dir = os.path.dirname(target_path) or "."
    fd, temp_file_path = tempfile.mkstemp(suffix=".xlsx", dir=temp_dir)
    os.close(fd)
    
    try:
        df.to_excel(temp_file_path, index=False)
        # Move the temp file to the target path (atomic overwrite)
        shutil.move(temp_file_path, target_path)
        log.info("Wrote Excel file atomically to %s", target_path)
    except Exception as e:
        log.error("Atomic write failed for %s: %s", target_path, e)
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise


def sync_google_to_excel() -> bool:
    """
    Pull all sales and daily summaries from Google Sheets and overwrite local Excel files.
    Includes validation to prevent overwriting valid data with empty sheets.
    """
    log.info("Starting Google Sheets to Excel backup synchronization...")

    if not database.is_connected():
        log.warning("Google Sheet not connected. Sync aborted.")
        return False

    try:
        # ── Backup Sales ──
        sales = database.get_sales()
        if not sales:
            log.warning("Google Sheets Sales sheet returned no records. Skipping Sales sync to prevent data loss.")
        else:
            sales_df = pd.DataFrame(sales)
            _write_df_atomically(sales_df, config.SALES_FILE)
            log.info("Successfully synced %d sales records from Google Sheets to local Excel.", len(sales_df))

        # ── Backup Summaries ──
        # Grab a large number of days or all records to sync the entire sheet
        from backend import Google_Sheet
        database._ensure_sheets()
        if Google_Sheet.summary_sheet is not None:
            records = Google_Sheet.summary_sheet.get_all_records()
            if not records:
                log.warning("Google Sheets DailySummary sheet returned no records. Skipping Summary sync.")
            else:
                casted_records = [database._cast_summary_record(r) for r in records]
                summary_df = pd.DataFrame(casted_records)
                _write_df_atomically(summary_df, config.SUMMARY_FILE)
                log.info("Successfully synced %d summary records from Google Sheets to local Excel.", len(summary_df))

        return True
    except Exception as e:
        log.error("Error during Google Sheets to Excel sync: %s", e)
        return False


def backup_sales_to_excel(records: list[dict]) -> None:
    """Merge specific sales records into the local Excel sales file."""
    if not records:
        return

    try:
        new_df = pd.DataFrame(records)
        
        if os.path.exists(config.SALES_FILE):
            existing_df = pd.read_excel(config.SALES_FILE)
            # Combine existing and new records
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            # Deduplicate by Sale_ID, keeping the latest update
            combined_df = combined_df.drop_duplicates(subset=["Sale_ID"], keep="last")
        else:
            combined_df = new_df
            
        _write_df_atomically(combined_df, config.SALES_FILE)
        log.info("Merged %d sale records into local Excel backup.", len(records))
    except Exception as e:
        log.error("Failed to backup sales records to local Excel: %s", e)


def backup_summary_to_excel(records: list[dict]) -> None:
    """Merge specific daily summary records into the local Excel summary file."""
    if not records:
        return

    try:
        new_df = pd.DataFrame(records)
        new_df["Date"] = normalize_date(new_df["Date"].astype(str))

        if os.path.exists(config.SUMMARY_FILE):
            existing_df = pd.read_excel(config.SUMMARY_FILE)
            existing_df["Date"] = normalize_date(existing_df["Date"].astype(str))
            
            # Combine existing and new records
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            # Deduplicate by Date, keeping the latest update
            combined_df = combined_df.drop_duplicates(subset=["Date"], keep="last")
        else:
            combined_df = new_df
            
        _write_df_atomically(combined_df, config.SUMMARY_FILE)
        log.info("Merged %d summary records into local Excel backup.", len(records))
    except Exception as e:
        log.error("Failed to backup daily summary records to local Excel: %s", e)
