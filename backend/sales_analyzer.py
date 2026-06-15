# backend/sales_analyzer.py
# Sales Intelligence & Revenue Prediction Engine.
#
# Read-only analysis of sales and daily_summary worksheets in Google Sheets.

import pandas as pd
import os
import logging
from datetime import datetime, timedelta
from backend.utils import normalize_date
from backend import config

log = logging.getLogger(__name__)


def _get_last_n_days_summary(days: int = 30) -> pd.DataFrame:
    """
    Read daily summary worksheet from Google Sheets and return the last N days of data.
    Returns empty DataFrame on any error.
    """
    try:
        from backend.database import get_daily_summaries
        records = get_daily_summaries(days + 2) # Grab slightly more to ensure filtering works
        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        df["Date"] = normalize_date(df["Date"].astype(str))

        # Filter to last N days and exclude today
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        df = df[(df["Date"] >= cutoff) & (df["Date"] < today)].copy()

        return df

    except Exception as e:
        log.warning("_get_last_n_days_summary error: %s. Falling back to Excel.", e)
        try:
            if os.path.exists(config.SUMMARY_FILE):
                df = pd.read_excel(config.SUMMARY_FILE)
                if not df.empty or "Date" in df.columns:
                    df["Date"] = normalize_date(df["Date"].astype(str))
                    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                    today = datetime.now().strftime("%Y-%m-%d")
                    df = df[(df["Date"] >= cutoff) & (df["Date"] < today)].copy()
                    return df
        except Exception:
            pass
        return pd.DataFrame()


def _get_last_n_days_sales(days: int = 30) -> pd.DataFrame:
    """
    Read sales worksheet from Google Sheets and return the last N days of Active sales.
    Returns empty DataFrame on any error.
    """
    try:
        from backend.database import get_sales
        sales = get_sales()
        if not sales:
            return pd.DataFrame()

        df = pd.DataFrame(sales)
        df["Date"] = normalize_date(df["Date"].astype(str))

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        df = df[
            (df["Date"] >= cutoff) &
            (df["Date"] < today) &
            (df["Status"] == "Active")
        ].copy()

        return df

    except Exception as e:
        log.warning("_get_last_n_days_sales error: %s. Falling back to Excel.", e)
        try:
            if os.path.exists(config.SALES_FILE):
                df = pd.read_excel(config.SALES_FILE)
                if not df.empty or "Date" in df.columns:
                    df["Date"] = normalize_date(df["Date"].astype(str))
                    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                    today = datetime.now().strftime("%Y-%m-%d")
                    df = df[
                        (df["Date"] >= cutoff) &
                        (df["Date"] < today) &
                        (df["Status"] == "Active")
                    ].copy()
                    return df
        except Exception:
            pass
        return pd.DataFrame()


def analyze_last_30_days() -> dict:
    """
    Analyze the last 30 days of sales data.

    Returns:
        {
            "avg_daily_revenue": float,
            "best_day": {"date": str, "revenue": float},
            "worst_day": {"date": str, "revenue": float},
            "highest_footfall_day": {"date": str, "transactions": int},
            "total_days": int,
        }
    """
    result = {
        "avg_daily_revenue": 0.0,
        "best_day": {"date": "", "revenue": 0},
        "worst_day": {"date": "", "revenue": 0},
        "highest_footfall_day": {"date": "", "transactions": 0},
        "total_days": 0,
    }

    try:
        summary_df = _get_last_n_days_summary(30)

        if summary_df.empty or "Total_Sales_Amount" not in summary_df.columns:
            return result

        # Filter to days with actual sales
        with_sales = summary_df[summary_df["Total_Sales_Amount"] > 0].copy()

        if with_sales.empty:
            return result

        result["total_days"] = len(with_sales)
        result["avg_daily_revenue"] = round(with_sales["Total_Sales_Amount"].mean(), 2)

        # Best day (highest revenue)
        best_idx = with_sales["Total_Sales_Amount"].idxmax()
        result["best_day"] = {
            "date": str(with_sales.at[best_idx, "Date"]),
            "revenue": float(with_sales.at[best_idx, "Total_Sales_Amount"]),
        }

        # Worst day (lowest revenue)
        worst_idx = with_sales["Total_Sales_Amount"].idxmin()
        result["worst_day"] = {
            "date": str(with_sales.at[worst_idx, "Date"]),
            "revenue": float(with_sales.at[worst_idx, "Total_Sales_Amount"]),
        }

        # Highest footfall day (most transactions)
        if "Total_Transactions" in with_sales.columns:
            foot_idx = with_sales["Total_Transactions"].idxmax()
            result["highest_footfall_day"] = {
                "date": str(with_sales.at[foot_idx, "Date"]),
                "transactions": int(with_sales.at[foot_idx, "Total_Transactions"]),
            }

    except Exception as e:
        log.warning("analyze_last_30_days error: %s", e)

    return result


def _compute_weather_impact_score(summary_df: pd.DataFrame) -> dict:
    """
    Correlate weather conditions with revenue from historical data.

    Returns a dict of weather_condition → average revenue.
    Internal use only — NOT exposed in UI.
    """
    impact = {}

    try:
        if summary_df.empty:
            return impact

        if "Weather" not in summary_df.columns or "Total_Sales_Amount" not in summary_df.columns:
            return impact

        with_sales = summary_df[summary_df["Total_Sales_Amount"] > 0].copy()

        if with_sales.empty:
            return impact

        grouped = with_sales.groupby("Weather")["Total_Sales_Amount"].mean()
        impact = grouped.to_dict()

        log.info("Weather impact scores: %s", impact)

    except Exception as e:
        log.warning("_compute_weather_impact_score error: %s", e)

    return impact


def get_sales_prediction(weather_data: dict, day_info: dict) -> dict:
    """
    Predict expected revenue and demand level for today.

    Uses:
        - Historical average revenue
        - Day type weighting (weekend, holiday, normal)
        - Weather condition weighting
        - Rain impact adjustment

    Returns:
        {
            "expected_revenue": int,
            "demand_tag": "Expected High Demand" | "Expected Low Demand" | "Normal Business Day",
            "weather_impact_score": float  (internal)
        }

    Gracefully returns 0 if insufficient data.
    """
    result = {
        "expected_revenue": 0,
        "demand_tag": "Normal Business Day",
        "weather_impact_score": 0.0,
    }

    try:
        summary_df = _get_last_n_days_summary(30)

        if summary_df.empty or "Total_Sales_Amount" not in summary_df.columns:
            log.info("Insufficient historical data for prediction")
            return result

        with_sales = summary_df[summary_df["Total_Sales_Amount"] > 0].copy()

        if len(with_sales) < 3:
            log.info("Need at least 3 days of sales data for prediction")
            return result

        # ── Base: overall average ─────────────────────────────────────────
        avg_revenue = with_sales["Total_Sales_Amount"].mean()

        # ── Weekend multiplier ────────────────────────────────────────────
        is_weekend = day_info.get("is_weekend", False)
        weekend_multiplier = 1.0

        if "Is_Weekend" in with_sales.columns:
            weekend_days = with_sales[with_sales["Is_Weekend"] == True]
            weekday_days = with_sales[with_sales["Is_Weekend"] == False]

            if len(weekend_days) >= 2 and len(weekday_days) >= 2:
                weekend_avg = weekend_days["Total_Sales_Amount"].mean()
                weekday_avg = weekday_days["Total_Sales_Amount"].mean()

                if weekday_avg > 0:
                    weekend_multiplier = weekend_avg / weekday_avg

        # ── Holiday multiplier ────────────────────────────────────────────
        is_holiday = day_info.get("is_holiday", False)
        holiday_multiplier = 1.0

        if is_holiday:
            if "Is_Holiday" in with_sales.columns:
                holiday_days = with_sales[with_sales["Is_Holiday"] == True]
                if len(holiday_days) >= 1:
                    holiday_avg = holiday_days["Total_Sales_Amount"].mean()
                    if avg_revenue > 0:
                        holiday_multiplier = holiday_avg / avg_revenue
                else:
                    holiday_multiplier = 1.2

        # ── Weather impact ────────────────────────────────────────────────
        weather_impact = _compute_weather_impact_score(summary_df)
        weather_condition = weather_data.get("weather", "Unknown")
        weather_multiplier = 1.0

        if weather_condition in weather_impact and avg_revenue > 0:
            weather_multiplier = weather_impact[weather_condition] / avg_revenue
            result["weather_impact_score"] = round(weather_multiplier, 3)

        # ── Rain penalty ──────────────────────────────────────────────────
        rain_level = weather_data.get("rain_level", "None")
        rain_penalty = {
            "None": 1.0,
            "Low": 0.95,
            "Medium": 0.85,
            "High": 0.7,
            "Extreme": 0.5,
            "Unknown": 0.9,
        }.get(rain_level, 1.0)

        # ── Calculate predicted revenue ───────────────────────────────────
        predicted = avg_revenue

        if is_weekend:
            predicted *= weekend_multiplier
        if is_holiday:
            predicted *= holiday_multiplier
        if weather_multiplier != 1.0:
            predicted *= weather_multiplier

        predicted *= rain_penalty

        result["expected_revenue"] = round(predicted)

        # ── Demand classification ─────────────────────────────────────────
        if predicted >= avg_revenue * 1.3:
            result["demand_tag"] = "Expected High Demand"
        elif predicted <= avg_revenue * 0.7:
            result["demand_tag"] = "Expected Low Demand"
        else:
            result["demand_tag"] = "Normal Business Day"

        log.info("Sales prediction: revenue=%d, demand=%s",
                 result["expected_revenue"], result["demand_tag"])

    except Exception as e:
        log.warning("get_sales_prediction error: %s", e)

    return result
