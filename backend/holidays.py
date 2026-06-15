# backend/holidays.py
# Indian national holidays + Tamil Nadu state holidays for 2026.
# Used to auto-detect Is_Holiday when the shop is opened each day.
# No external API required — static calendar data.
#
# Enhanced: Extended festival list + any-date lookup helpers.

from datetime import date, datetime

# ── 2026 Holiday Calendar ─────────────────────────────────────────────────────
# Format: "YYYY-MM-DD": "Holiday Name"
# Includes: Indian national holidays + Tamil Nadu public holidays + festivals

_HOLIDAYS_2026 = {
    # January
    "2026-01-01": "New Year's Day",
    "2026-01-14": "Pongal",
    "2026-01-15": "Thiruvalluvar Day",
    "2026-01-16": "Uzhavar Thirunal",
    "2026-01-26": "Republic Day",

    # February
    "2026-02-12": "Masi Magam",
    "2026-02-19": "Chhatrapati Shivaji Maharaj Jayanti",
    "2026-02-26": "Maha Shivaratri",

    # March
    "2026-03-14": "Karadaiyan Nombu",
    "2026-03-19": "Holi",

    # April
    "2026-04-02": "Good Friday",
    "2026-04-06": "Tamil New Year / Ugadi",
    "2026-04-10": "Good Friday (Tamil Nadu)",
    "2026-04-14": "Dr. Ambedkar Jayanti / Tamil New Year",

    # May
    "2026-05-01": "International Labour Day / May Day",
    "2026-05-07": "Buddha Purnima",

    # June
    "2026-06-06": "Id-ul-Adha (Bakrid)",

    # July
    "2026-07-05": "Muharram",
    "2026-07-07": "Rath Yatra",

    # August
    "2026-08-15": "Independence Day",
    "2026-08-18": "Varalakshmi Vratham",
    "2026-08-27": "Onam",

    # September
    "2026-09-05": "Teachers Day",
    "2026-09-14": "Milad-un-Nabi (Prophet's Birthday)",

    # October
    "2026-10-02": "Gandhi Jayanti",
    "2026-10-12": "Ayudha Pooja",
    "2026-10-13": "Saraswathi Pooja",
    "2026-10-14": "Vijaya Dasami (Dussehra)",
    "2026-10-20": "Diwali",

    # November
    "2026-11-01": "Tamil Nadu Day",
    "2026-11-04": "Diwali (Tamil Nadu)",
    "2026-11-14": "Children's Day",
    "2026-11-30": "Karthigai Deepam",

    # December
    "2026-12-25": "Christmas Day",
}

# ── Festival names (subset of holidays that drive higher footfall) ─────────
_FESTIVAL_NAMES = {
    "Pongal", "Diwali", "Diwali (Tamil Nadu)", "Holi",
    "Vijaya Dasami (Dussehra)", "Ayudha Pooja", "Karthigai Deepam",
    "Tamil New Year / Ugadi", "Dr. Ambedkar Jayanti / Tamil New Year",
    "Christmas Day", "New Year's Day", "Onam",
}


def is_holiday_today() -> tuple[bool, str]:
    """
    Check if today is a recognized Indian / Tamil Nadu holiday.

    Returns:
        (True,  "Holiday Name")  if today is a holiday
        (False, "")              if today is a normal working day
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    name = _HOLIDAYS_2026.get(today_str, "")
    return (bool(name), name)


def is_weekend_today() -> bool:
    """Return True if today is Saturday (5) or Sunday (6)."""
    return datetime.now().weekday() >= 5


def get_day_info() -> dict:
    """
    Return a dict with Is_Holiday and Is_Weekend for today.
    Convenience wrapper used by summary.open_shop().
    """
    holiday, holiday_name = is_holiday_today()
    weekend = is_weekend_today()
    return {
        "is_holiday":   holiday,
        "holiday_name": holiday_name,
        "is_weekend":   weekend,
    }


# ── Any-date helpers (for historical lookups by sales_analyzer) ───────────────

def is_holiday_on(date_str: str) -> tuple[bool, str]:
    """
    Check if a given date (YYYY-MM-DD) is a holiday.

    Returns:
        (True, "Holiday Name")  if it's a holiday
        (False, "")             otherwise
    """
    name = _HOLIDAYS_2026.get(date_str, "")
    return (bool(name), name)


def is_weekend_on(date_str: str) -> bool:
    """Return True if a given date (YYYY-MM-DD) is Saturday or Sunday."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.weekday() >= 5
    except (ValueError, TypeError):
        return False


def is_festival_on(date_str: str) -> bool:
    """Return True if a given date is a major festival (drives high footfall)."""
    name = _HOLIDAYS_2026.get(date_str, "")
    return name in _FESTIVAL_NAMES
