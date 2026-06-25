# backend/products.py
# Single source of truth for all product definitions, types, and pricing.
# All calculations in frontend and backend must derive from PRODUCTS.
# DO NOT hardcode prices anywhere else.

PRODUCTS = {
    "Chicken Pakoda": {
        "type": "weight",
        "display": "Chicken Pakoda",
        "image": "chicken_pakoda.jpg",
        # Fixed-rate tiers: amount paid → grams received
        "rates": {
            50: 100,
            120: 250,
            240: 500,
        },
        # Fallback: ₹50 per 100g for non-tier amounts
        "rate_per_100g": 50,
        "unit": "g",
    },
    "Liver": {
        "type": "weight",
        "display": "Liver",
        "image": "liver.jpg",
        "rate_per_100g": 40,
        "unit": "g",
    },
    "Leg Piece": {
        "type": "piece",
        "display": "Leg Piece",
        "image": "leg.jpg",
        "unit_price": 50,
        "unit": "pc",
    },
    "Wings": {
        "type": "piece",
        "display": "Wings",
        "image": "wings.jpg",
        "unit_price": 20,
        "unit": "pc",
    },
    "Fish1": {
        "type": "piece",
        "display": "Fish 1",
        "image": "fish1.jpg",
        "unit_price": 40,
        "unit": "pc",
    },
    "Fish2": {
        "type": "piece",
        "display": "Fish 2",
        "image": "fish2.jpg",
        "unit_price": 20,
        "unit": "pc",
    },
    "Fish3": {
        "type": "piece",
        "display": "Fish 3",
        "image": "fish3.jpg",
        "unit_price": 30,
        "unit": "pc",
    },
    "Gravy": {
        "type": "piece",
        "display": "Gravy",
        "image": "gravy.jpg",
        "unit_price": 70,
        "unit": "pc",
    },
    "Soup": {
        "type": "variant",
        "display": "Soup",
        "image": "soup.jpg",
        "variants": {
            "Dine-In": 30,
            "Parcel": 35,
        },
        "unit": "bowl",
    },
}

VALID_CUSTOMER_TYPES = {"Regular", "New", "Unknown"}


def get_product(product_name: str) -> dict | None:
    """Return the product definition dict or None if not found."""
    return PRODUCTS.get(product_name)


def get_unit_price(product_name: str, variant: str = None) -> float:
    """
    Return the canonical unit price for a product, used for Excel storage.

    For weight products: returns rate_per_100g (so unit_price in Excel = ₹/100g).
    For piece products: returns unit_price per piece.
    For variant products: returns price for the given variant.
    """
    p = PRODUCTS.get(product_name)
    if p is None:
        return 0.0

    if p["type"] == "weight":
        return float(p["rate_per_100g"])

    if p["type"] == "piece":
        return float(p["unit_price"])

    if p["type"] == "variant":
        return float(p["variants"].get(variant, 0))

    return 0.0


def calc_weight_grams(product_name: str, amount: float) -> int:
    """
    Given the rupee amount paid, return how many grams the customer receives.

    For Chicken Pakoda, uses tier pricing (₹50=100g, ₹120=250g, ₹240=500g).
    For all other weight products, uses linear rate_per_100g.
    """
    p = PRODUCTS.get(product_name)
    if p is None or p["type"] != "weight":
        return 0

    # Check tier pricing first (Chicken Pakoda only)
    # Convert amount to int for key lookup — JS may send 50.0 instead of 50
    if "rates" in p:
        tier_key = int(amount)
        if tier_key in p["rates"]:
            return p["rates"][tier_key]

    # Linear fallback: (amount / rate_per_100g) * 100
    rate = p["rate_per_100g"]
    return round((amount / rate) * 100)


def get_all_products() -> dict:
    """Return the full PRODUCTS dict."""
    return PRODUCTS
