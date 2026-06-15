from flask import Flask, render_template, request, jsonify
from backend.dashboard import get_dashboard_data
from backend.sales import save_sale, create_sale_record, get_today_sales, delete_sale, edit_sale
from backend.summary import open_shop, close_shop, create_day_record
from backend.products import get_product, get_unit_price, calc_weight_grams, VALID_CUSTOMER_TYPES, PRODUCTS
from backend.utils import normalize_date
from backend.weather import get_weather_data
from backend.holidays import get_day_info
from backend import config
from backend.offline_sync import start_sync_worker
from backend.excel_backup import sync_google_to_excel
import pandas as pd
import os

app = Flask(__name__)

# Start offline synchronization background worker
start_sync_worker()

# Run a startup backup sync from Google Sheets to local Excel
try:
    sync_google_to_excel()
except Exception as e:
    print(f"Startup Google-to-Excel sync failed: {e}")

# Ensure today's daily_summary row exists at startup
create_day_record()


# ── PAGE ROUTES ────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    data = get_dashboard_data()
    return render_template("dashboard.html", data=data)


@app.route("/sales")
def sales():
    data = get_dashboard_data()
    return render_template("sales_entry.html", data=data)


@app.route("/today-sales")
def today_sales_page():
    data = get_dashboard_data()
    sales_df = get_today_sales()

    sales_list = []
    if not sales_df.empty:
        sales_list = sales_df.to_dict("records")
        image_map = {name: info["image"] for name, info in PRODUCTS.items()}
        for s in sales_list:
            s["image_file"] = image_map.get(s.get("Product_Name", ""), "chicken_pakoda.jpg")

    return render_template("today_sales.html", sales=sales_list, summary=data)


# ── API: SUMMARY ───────────────────────────────────────────────────────────────

@app.route("/api/summary", methods=["GET"])
def api_summary():
    """Live dashboard totals — called by JS after each sale action."""
    return jsonify(get_dashboard_data())


@app.route("/api/products", methods=["GET"])
def api_products():
    """Return PRODUCTS dict as JSON for frontend price lookups."""
    return jsonify(PRODUCTS)


@app.route("/api/weather", methods=["GET"])
def api_weather():
    """Return live weather data for Saidapet, Chennai."""
    return jsonify(get_weather_data())


@app.route("/api/day-info", methods=["GET"])
def api_day_info():
    """Return today's holiday and weekend status."""
    return jsonify(get_day_info())


# ── API: ADD SALE ──────────────────────────────────────────────────────────────

@app.route("/api/add-sale", methods=["POST"])
def api_add_sale():
    """
    Expected payload:
    {
        "product_name": "Chicken Pakoda",
        "sale_type":    "weight" | "piece" | "variant",
        "variant":      "Dine-In" | "Parcel" | "",
        "quantity":     <number>,        # grams for weight, pieces for piece/variant
        "unit":         "g" | "pc" | "bowl",
        "amount":       <rupees>,
        "customer_type": "Regular" | "New" | "Unknown"
    }
    """
    try:
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"status": "error", "message": "JSON body required"}), 400

        product_name = body.get("product_name", "").strip()
        sale_type    = body.get("sale_type", "").strip()
        variant      = body.get("variant", "") or ""
        quantity     = body.get("quantity")
        unit         = body.get("unit", "")
        amount       = body.get("amount")
        customer_type = body.get("customer_type", "Unknown")

        # ── Validate required fields ──
        if not product_name:
            return jsonify({"status": "error", "message": "product_name is required"}), 400

        product = get_product(product_name)
        if product is None:
            return jsonify({"status": "error", "message": f"Unknown product: {product_name}"}), 400

        if quantity is None or float(quantity) <= 0:
            return jsonify({"status": "error", "message": "quantity must be > 0"}), 400

        if amount is None or float(amount) <= 0:
            return jsonify({"status": "error", "message": "amount must be > 0"}), 400

        quantity = float(quantity)
        amount   = float(amount)

        if customer_type not in VALID_CUSTOMER_TYPES:
            customer_type = "Unknown"

        # ── Validate variant for variant products ──
        if product["type"] == "variant":
            if variant not in product["variants"]:
                return jsonify({"status": "error",
                                "message": f"Invalid variant '{variant}'. Valid: {list(product['variants'].keys())}"}), 400

        # ── Derive canonical unit_price for Excel storage ──
        # weight: ₹/100g  |  piece: ₹/pc  |  variant: ₹/bowl
        unit_price = get_unit_price(product_name, variant)

        record = create_sale_record(
            product_name=product_name,
            sale_type=sale_type,
            variant=variant,
            quantity=quantity,
            quantity_unit=unit or product.get("unit", ""),
            unit_price=unit_price,
            total_amount=amount,
            customer_type=customer_type,
        )

        save_sale(record)
        return jsonify({"status": "success", "sale_id": record["Sale_ID"]})

    except Exception as e:
        print(f"[add-sale] error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ── API: DELETE SALE ───────────────────────────────────────────────────────────

@app.route("/api/delete-sale", methods=["POST"])
def api_delete_sale():
    try:
        body = request.get_json(silent=True)
        if not body or "sale_id" not in body:
            return jsonify({"status": "error", "message": "sale_id is required"}), 400

        sale_id = int(body["sale_id"])
        success, msg = delete_sale(sale_id)

        if success:
            return jsonify({"status": "success", "message": msg})
        return jsonify({"status": "error", "message": msg}), 400

    except Exception as e:
        print(f"[delete-sale] error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ── API: EDIT SALE ─────────────────────────────────────────────────────────────

@app.route("/api/edit-sale", methods=["POST"])
def api_edit_sale():
    """
    Adapter: frontend sends { sale_id, amount }.
    Passes new_total_amount directly to edit_sale() which handles
    quantity recalculation using the stored unit_price.

    Also accepts optional customer_type update.
    """
    try:
        body = request.get_json(silent=True)
        if not body or "sale_id" not in body:
            return jsonify({"status": "error", "message": "sale_id is required"}), 400

        sale_id = int(body["sale_id"])

        new_amount = None
        if "amount" in body:
            new_amount = float(body["amount"])
            if new_amount <= 0:
                return jsonify({"status": "error", "message": "amount must be > 0"}), 400

        new_customer_type = body.get("customer_type")
        if new_customer_type and new_customer_type not in VALID_CUSTOMER_TYPES:
            return jsonify({"status": "error",
                            "message": f"Invalid customer_type: {new_customer_type}"}), 400

        success, msg = edit_sale(
            sale_id=sale_id,
            new_total_amount=new_amount,
            new_customer_type=new_customer_type,
        )

        if success:
            return jsonify({"status": "success", "message": msg})
        return jsonify({"status": "error", "message": msg}), 400

    except Exception as e:
        print(f"[edit-sale] error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ── API: SHOP CONTROL ──────────────────────────────────────────────────────────

@app.route("/api/open-shop", methods=["POST"])
def api_open_shop():
    success, msg = open_shop()
    if success:
        return jsonify({"status": "success", "message": msg})
    if "already" in msg.lower():
        return jsonify({"status": "success", "message": "Shop was already open"})
    return jsonify({"status": "error", "message": msg}), 400


@app.route("/api/close-shop", methods=["POST"])
def api_close_shop():
    success, msg = close_shop()
    if success:
        return jsonify({"status": "success", "message": msg})
    return jsonify({"status": "error", "message": msg}), 400


# ── HEALTH CHECK ───────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint indicating connection status of sheets."""
    from backend.database import is_connected
    from backend import Google_Sheet
    
    gs_connected = is_connected()
    
    return jsonify({
        "status": "healthy" if (gs_connected and Google_Sheet.sales_sheet and Google_Sheet.summary_sheet) else "unhealthy",
        "google_sheet": "connected" if gs_connected else "disconnected",
        "sales": "ok" if Google_Sheet.sales_sheet else "error",
        "daily_summary": "ok" if Google_Sheet.summary_sheet else "error"
    })


# ── API: EXCEL BACKUP ──────────────────────────────────────────────────────────

@app.route("/api/backup-excel", methods=["POST"])
def api_backup_excel():
    """Trigger a manual sync of data from Google Sheets to Excel backups."""
    from backend.excel_backup import sync_google_to_excel
    success = sync_google_to_excel()
    if success:
        return jsonify({"status": "success", "message": "Google Sheets synced to Excel backup successfully."})
    else:
        return jsonify({"status": "error", "message": "Failed to sync Google Sheets to Excel backup."}), 500


# ── RUN ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=config.PORT,
        debug=config.DEBUG
    )
