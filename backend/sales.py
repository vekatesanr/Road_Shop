# backend/sales.py

import pandas as pd
from datetime import datetime
import os
from backend.utils import normalize_date, safe_float
from backend.products import get_product, get_unit_price, calc_weight_grams, VALID_CUSTOMER_TYPES
from backend import config

_SALE_COLUMNS = [
    "Sale_ID", "Date", "Time", "Day_Name",
    "Product_Name", "Sale_Type", "Variant",
    "Quantity", "Quantity_Unit", "Unit_Price",
    "Total_Amount", "Customer_Type", "Status",
]


def generate_sale_id() -> int:
    """Generate the next Sale_ID by finding the current max in Google Sheets and adding 1."""
    from backend.database import get_max_sale_id
    return get_max_sale_id() + 1


def create_sale_record(
        product_name: str,
        sale_type: str,
        variant: str,
        quantity: float,
        quantity_unit: str,
        unit_price: float,
        total_amount: float,
        customer_type: str) -> dict:
    """
    Build a validated sale record dict ready for database insertion.

    unit_price semantics:
      - weight products: ₹ per 100g  (e.g. 50 for Chicken Pakoda)
      - piece products:  ₹ per piece  (e.g. 50 for Leg Piece)
      - variant products: ₹ per bowl/unit for the selected variant
    """
    sale_id = generate_sale_id()
    now = datetime.now()

    # Sanitize customer type
    if customer_type not in VALID_CUSTOMER_TYPES:
        customer_type = "Unknown"

    return {
        "Sale_ID": sale_id,
        "Date": now.strftime("%Y-%m-%d"),
        "Time": now.strftime("%H:%M:%S"),
        "Day_Name": now.strftime("%A"),
        "Product_Name": product_name,
        "Sale_Type": sale_type,
        "Variant": variant or "",
        "Quantity": quantity,
        "Quantity_Unit": quantity_unit,
        "Unit_Price": unit_price,
        "Total_Amount": total_amount,
        "Customer_Type": customer_type,
        "Status": "Active",
    }


def save_sale(sale_record: dict) -> None:
    """Append a sale record to Google Sheets and refresh the daily summary."""
    from backend.database import save_sale as db_save_sale
    db_save_sale(sale_record)

    # Optional Excel Backup Sync
    if config.EXCEL_BACKUP_ENABLED:
        try:
            from backend.excel_backup import backup_sales_to_excel
            backup_sales_to_excel([sale_record])
        except Exception as e:
            print(f"Excel backup failed during save_sale: {e}")

    from backend.summary import update_daily_summary
    update_daily_summary()

    print(f"Sale saved: ID={sale_record['Sale_ID']} "
          f"product={sale_record['Product_Name']} "
          f"amount=Rs{sale_record['Total_Amount']}")


def get_today_sales() -> pd.DataFrame:
    """Return a DataFrame of today's Active sales from Google Sheets."""
    from backend.database import get_sales
    try:
        sales = get_sales()
    except Exception as e:
        print(f"Failed to fetch live sales: {e}. Falling back to Excel.")
        if os.path.exists(config.SALES_FILE):
            df = pd.read_excel(config.SALES_FILE)
            if not df.empty:
                df["Date"] = normalize_date(df["Date"].astype(str))
                today = datetime.now().strftime("%Y-%m-%d")
                return df[(df["Date"] == today) & (df["Status"] == "Active")].copy()
        return pd.DataFrame(columns=_SALE_COLUMNS)

    if not sales:
        return pd.DataFrame(columns=_SALE_COLUMNS)

    df = pd.DataFrame(sales)
    today = datetime.now().strftime("%Y-%m-%d")
    df["Date"] = normalize_date(df["Date"].astype(str))

    today_df = df[
        (df["Date"] == today) &
        (df["Status"] == "Active")
    ].copy()

    return today_df


def delete_sale(sale_id: int) -> tuple[bool, str]:
    """
    Soft-delete a sale by setting Status = 'Deleted' in Google Sheets.
    Summary is refreshed AFTER the write.
    """
    from backend.database import get_sales, delete_sale as db_delete_sale
    try:
        sales = get_sales()
    except Exception as e:
        return False, f"Failed to access database: {e}"

    target_sale = None
    for s in sales:
        if s["Sale_ID"] == sale_id:
            target_sale = s
            break

    if not target_sale:
        return False, "Sale ID not found"

    sale_date = normalize_date(pd.Series([str(target_sale["Date"])]))[0]
    today = datetime.now().strftime("%Y-%m-%d")

    if sale_date != today:
        return False, "Cannot delete past-day transactions"

    success, msg = db_delete_sale(sale_id)
    if not success:
        return False, msg

    # Optional Excel Backup Sync
    if config.EXCEL_BACKUP_ENABLED and os.path.exists(config.SALES_FILE):
        try:
            df = pd.read_excel(config.SALES_FILE)
            sale_idx = df[df["Sale_ID"] == sale_id].index
            if len(sale_idx) > 0:
                df.at[sale_idx[0], "Status"] = "Deleted"
                df.to_excel(config.SALES_FILE, index=False)
        except Exception as e:
            print(f"Excel backup update failed during delete_sale: {e}")

    from backend.summary import update_daily_summary
    update_daily_summary()

    return True, f"Sale {sale_id} deleted successfully"


def edit_sale(
        sale_id: int,
        new_quantity: float = None,
        new_total_amount: float = None,
        new_customer_type: str = None,
        new_variant: str = None) -> tuple[bool, str]:
    """
    Edit a sale record in Google Sheets.
    Summary is refreshed AFTER the write.
    """
    from backend.database import get_sales, update_sale as db_update_sale
    try:
        sales = get_sales()
    except Exception as e:
        return False, f"Failed to access database: {e}"

    target_sale = None
    for s in sales:
        if s["Sale_ID"] == sale_id:
            target_sale = s
            break

    if not target_sale:
        return False, "Sale ID not found"

    sale_date = normalize_date(pd.Series([str(target_sale["Date"])]))[0]
    today = datetime.now().strftime("%Y-%m-%d")

    if sale_date != today:
        return False, "Cannot edit past-day transactions"

    updates = {}

    if new_customer_type is not None:
        if new_customer_type not in VALID_CUSTOMER_TYPES:
            return False, f"Invalid customer type: {new_customer_type}"
        updates["Customer_Type"] = new_customer_type

    if new_quantity is not None:
        unit_price = safe_float(target_sale.get("Unit_Price"))
        updates["Quantity"] = new_quantity
        updates["Total_Amount"] = round(new_quantity * unit_price / 100, 2) \
            if str(target_sale.get("Sale_Type")) == "weight" \
            else round(new_quantity * unit_price, 2)

    if new_total_amount is not None:
        unit_price = safe_float(target_sale.get("Unit_Price"))
        sale_type = str(target_sale.get("Sale_Type"))
        updates["Total_Amount"] = new_total_amount
        if unit_price > 0:
            if sale_type == "weight":
                prod_name = str(target_sale.get("Product_Name"))
                updates["Quantity"] = calc_weight_grams(prod_name, new_total_amount)
            else:
                updates["Quantity"] = round(new_total_amount / unit_price, 2)

    if new_variant is not None:
        updates["Variant"] = new_variant

    if not updates:
        return True, "No edits requested"

    success, msg = db_update_sale(sale_id, updates)
    if not success:
        return False, msg

    # Optional Excel Backup Sync
    if config.EXCEL_BACKUP_ENABLED and os.path.exists(config.SALES_FILE):
        try:
            df = pd.read_excel(config.SALES_FILE)
            sale_idx = df[df["Sale_ID"] == sale_id].index
            if len(sale_idx) > 0:
                for key, val in updates.items():
                    df.at[sale_idx[0], key] = val
                df.to_excel(config.SALES_FILE, index=False)
        except Exception as e:
            print(f"Excel backup update failed during edit_sale: {e}")

    from backend.summary import update_daily_summary
    update_daily_summary()

    return True, f"Sale {sale_id} updated successfully"