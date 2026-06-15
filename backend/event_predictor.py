# backend/event_predictor.py
# Special Event Prediction Engine.
#
# Combines weather + holiday + weekend data to generate predictive event tags
# for the Special_Event field in daily_summary.xlsx.
#
# Rules-based — no ML. Deterministic output from current-day inputs.
# Does NOT modify UI. Does NOT change any existing logic.

import logging

log = logging.getLogger(__name__)


def predict_special_event(weather_data: dict, day_info: dict) -> str:
    """
    Generate a comma-separated Special_Event string based on conditions.

    Args:
        weather_data: dict from get_weather_data() with keys:
            weather, temperature, rain_level, rain_mm, humidity, wind_speed
        day_info: dict from get_day_info() with keys:
            is_holiday, holiday_name, is_weekend

    Returns:
        Comma-separated event tags string, e.g. "Festival Crowd, Weekend Rush"
        Returns "" if no special conditions detected.

    Rules (per spec):
        Sunday/Saturday  → Weekend Rush
        Rainy weather    → Rain Impact
        Holiday          → Festival Crowd
        Festival day     → Festival Sales Peak
        Temp ≥ 38°C      → Summer Demand
        High/Extreme rain→ Low Footfall Risk
    """
    tags = []

    try:
        # ── Weekend detection ─────────────────────────────────────────────
        if day_info.get("is_weekend", False):
            tags.append("Weekend Rush")

        # ── Holiday detection ─────────────────────────────────────────────
        holiday_name = day_info.get("holiday_name", "")
        is_holiday = day_info.get("is_holiday", False)

        if is_holiday and holiday_name:
            # Check if it's a major festival
            from backend.holidays import is_festival_on
            from datetime import datetime
            today_str = datetime.now().strftime("%Y-%m-%d")

            if is_festival_on(today_str):
                tags.append("Festival Sales Peak")
            else:
                tags.append("Festival Crowd")

            # Include the holiday name for context
            if holiday_name not in tags:
                tags.append(holiday_name)

        # ── Weather-based events ──────────────────────────────────────────
        weather_condition = weather_data.get("weather", "Unknown")
        rain_level = weather_data.get("rain_level", "None")
        temp_str = weather_data.get("temperature", "0C")

        # Parse temperature number
        try:
            temp_num = float(temp_str.replace("C", "").replace("°", "").strip())
        except (ValueError, AttributeError):
            temp_num = 0

        # Rain impact
        if weather_condition in ("Rainy", "Storm", "Light Rain"):
            tags.append("Rain Impact")

        # Low footfall risk for heavy/extreme rain
        if rain_level in ("High", "Extreme"):
            tags.append("Low Footfall Risk")

        # Summer demand
        if temp_num >= 38:
            tags.append("Summer Demand")

    except Exception as e:
        log.warning("Event prediction error: %s", e)

    # Deduplicate while preserving order
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    result = ", ".join(unique_tags)
    log.info("Event prediction: %s", result or "(none)")
    return result
