# backend/config.py
# Centralized configuration for the Street Food Shop Management System.
# Reads from environment variables (Railway / production) with fallback
# defaults for local development.
#
# NEVER hardcode secrets here — use environment variables.

import os
import json
import base64
import tempfile
import logging

log = logging.getLogger(__name__)

# ── Google Sheets ─────────────────────────────────────────────────────────────

GOOGLE_SHEET_ID = os.environ.get(
    "GOOGLE_SHEET_ID",
    "1cRME2GvgKLGff-J-SXVOVfuLa6Yy58tP3rRDdGLY9rc"
)

# Local development: path to credentials.json file
CREDENTIALS_PATH = os.environ.get("CREDENTIALS_PATH", "credentials.json")

# Railway / production: base64-encoded credentials JSON in env var.
# When set, a temporary file is created and CREDENTIALS_PATH is updated.
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

if GOOGLE_CREDENTIALS_JSON:
    try:
        decoded = base64.b64decode(GOOGLE_CREDENTIALS_JSON)
        # Validate it's valid JSON
        json.loads(decoded)
        # Write to a secure temp file
        _tmp = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".json", delete=False, prefix="gsheet_creds_"
        )
        _tmp.write(decoded)
        _tmp.close()
        CREDENTIALS_PATH = _tmp.name
        log.info("Google credentials loaded from GOOGLE_CREDENTIALS_JSON env var")
    except Exception as e:
        log.warning("Failed to decode GOOGLE_CREDENTIALS_JSON: %s", e)


# ── Google Sheets API scope ──────────────────────────────────────────────────

GOOGLE_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# ── Worksheet names ──────────────────────────────────────────────────────────

SALES_SHEET_NAME = os.environ.get("SALES_SHEET_NAME", "Sales")
SUMMARY_SHEET_NAME = os.environ.get("SUMMARY_SHEET_NAME", "DailySummary")

# ── Excel backup file paths ─────────────────────────────────────────────────

SALES_FILE = os.environ.get("SALES_FILE", "data/sales.xlsx")
SUMMARY_FILE = os.environ.get("SUMMARY_FILE", "data/daily_summary.xlsx")

# ── Offline sync ─────────────────────────────────────────────────────────────

PENDING_SYNC_FILE = os.environ.get("PENDING_SYNC_FILE", "data/pending_sync.json")
SYNC_INTERVAL_SECONDS = int(os.environ.get("SYNC_INTERVAL_SECONDS", "60"))

# ── Feature toggles ─────────────────────────────────────────────────────────

EXCEL_BACKUP_ENABLED = os.environ.get("EXCEL_BACKUP_ENABLED", "true").lower() == "true"
WEATHER_ENABLED = os.environ.get("WEATHER_ENABLED", "true").lower() == "true"

# ── Server ───────────────────────────────────────────────────────────────────

FLASK_ENV = os.environ.get("FLASK_ENV", "development")
PORT = int(os.environ.get("PORT", "5000"))
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
