# backend/weather.py
# Enhanced weather engine using Open-Meteo (free, no API key required).
# Location: Saidapet, Chennai, Tamil Nadu 600015
#
# Features:
#   - Daily cache: max 1 API call per day
#   - Rain mm precipitation data + classified rain level
#   - Humidity, wind speed
#   - WMO code → human label mapping
#   - Never crashes — safe fallback on any error
#
# Called automatically by create_day_record() and open_shop().

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

current_time = datetime.now(ZoneInfo("Asia/Kolkata"))   

log = logging.getLogger(__name__)

# Saidapet, Chennai coordinates (per user spec)
_LAT = 13.0230
_LON = 80.2209

# ── Daily cache ───────────────────────────────────────────────────────────────
# Stores today's weather result so we never make more than 1 API call per day.

_cache = {"date": None, "data": None}


# ── Rain level classification (mm-based) ──────────────────────────────────────

def _classify_rain(rain_mm: float) -> str:
    """
    Classify rainfall in mm to a human-readable level.

    0 mm        → None
    0.1 - 2 mm  → Low
    2 - 10 mm   → Medium
    10 - 30 mm  → High
    30+ mm      → Extreme
    """
    if rain_mm <= 0:
        return "None"
    elif rain_mm <= 2:
        return "Low"
    elif rain_mm <= 10:
        return "Medium"
    elif rain_mm <= 30:
        return "High"
    else:
        return "Extreme"


# ── WMO Weather Code → Human Label ───────────────────────────────────────────
# https://open-meteo.com/en/docs#weathervariables

_WMO_MAP = {
    0:  "Sunny",
    1:  "Sunny",
    2:  "Cloudy",
    3:  "Cloudy",
    45: "Cloudy",
    48: "Cloudy",
    51: "Light Rain",
    53: "Light Rain",
    55: "Light Rain",
    61: "Rainy",
    63: "Rainy",
    65: "Rainy",
    71: "Cloudy",
    73: "Cloudy",
    75: "Cloudy",
    77: "Cloudy",
    80: "Rainy",
    81: "Rainy",
    82: "Rainy",
    85: "Cloudy",
    86: "Cloudy",
    95: "Storm",
    96: "Storm",
    99: "Storm",
}


# ── Fallback data ─────────────────────────────────────────────────────────────

_FALLBACK = {
    "weather":     "Unknown",
    "temperature": "0C",
    "humidity":    0,
    "wind_speed":  0.0,
    "rain_mm":     0.0,
    "rain_level":  "Unknown",
}


# ── Main API ──────────────────────────────────────────────────────────────────

def get_weather_data() -> dict:
    """
    Fetch current weather for Saidapet, Chennai using Open-Meteo.

    Returns a dict with keys:
        weather      — "Sunny" | "Cloudy" | "Rainy" | "Storm" | "Light Rain"
        temperature  — "32C"
        humidity     — 75
        wind_speed   — 12.5
        rain_mm      — 0.0
        rain_level   — "None" | "Low" | "Medium" | "High" | "Extreme"

    Cached per day: max 1 API call per day.
    Always returns a safe dict even on network failure.
    """
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Return cached result if already fetched today
    if _cache["date"] == today_str and _cache["data"] is not None:
        log.info("Weather cache HIT for %s", today_str)
        return _cache["data"].copy()

    try:
        import requests

        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={_LAT}"
            f"&longitude={_LON}"
            "&current_weather=true"
            "&hourly=relativehumidity_2m,precipitation,windspeed_10m"
            "&timezone=Asia%2FKolkata"
            "&forecast_days=1"
        )

        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()

        # ── Current weather ───────────────────────────────────────────────
        cw = data["current_weather"]
        temp = cw["temperature"]              # float, °C
        code = int(cw["weathercode"])
        wind = cw.get("windspeed", 0.0)

        label = _WMO_MAP.get(code, "Cloudy")

        # ── Hourly data for humidity and precipitation ────────────────────
        hourly = data.get("hourly", {})
        current_hour = datetime.now().hour

        # Get humidity for current hour
        humidity_list = hourly.get("relativehumidity_2m", [])
        humidity = humidity_list[current_hour] if current_hour < len(humidity_list) else 0

        # Get precipitation (rain) in mm for current hour
        precip_list = hourly.get("precipitation", [])
        rain_mm = precip_list[current_hour] if current_hour < len(precip_list) else 0.0

        # Sum today's total precipitation for a daily rain level
        total_rain_mm = sum(p for p in precip_list if isinstance(p, (int, float)))

        rain_level = _classify_rain(total_rain_mm)

        result = {
            "weather":     label,
            "temperature": f"{temp:.0f}C",
            "humidity":    int(humidity),
            "wind_speed":  round(float(wind), 1),
            "rain_mm":     round(total_rain_mm, 1),
            "rain_level":  rain_level,
        }

        # Cache for today
        _cache["date"] = today_str
        _cache["data"] = result.copy()

        log.info("Weather fetched and cached: %s", result)
        return result

    except Exception as exc:
        log.warning("Weather fetch failed: %s", exc)
        return _FALLBACK.copy()