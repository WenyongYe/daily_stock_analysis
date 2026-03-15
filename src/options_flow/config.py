# -*- coding: utf-8 -*-
"""Options flow configuration and time window helpers."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from typing import Tuple

try:
    import exchange_calendars as xcals
    _XCALS_AVAILABLE = True
except Exception:
    _XCALS_AVAILABLE = False

from zoneinfo import ZoneInfo

DEFAULT_ACCOUNTS = ["FL0WG0D"]
US_MARKET_TZ = "America/New_York"


def get_monitor_accounts() -> list[str]:
    env_val = os.getenv("OPTIONS_FLOW_ACCOUNTS", "").strip()
    if env_val:
        return [a.strip().lstrip("@") for a in env_val.split(",") if a.strip()]
    return DEFAULT_ACCOUNTS


def get_use_images() -> bool:
    return os.getenv("OPTIONS_FLOW_USE_IMAGES", "true").lower() == "true"


def get_vision_model() -> str:
    return os.getenv("OPTIONS_FLOW_VISION_MODEL", "gemini-2.5-flash")


def get_vision_fallback_model() -> str:
    return os.getenv("OPTIONS_FLOW_VISION_FALLBACK_MODEL", "gemini-2.5-pro")


def get_top_n() -> int:
    return int(os.getenv("OPTIONS_FLOW_TOP_N", "10"))


def get_news_max_age_days() -> int:
    return int(os.getenv("OPTIONS_FLOW_NEWS_MAX_AGE_DAYS", "2"))


def get_min_volume() -> int:
    return int(os.getenv("OPTIONS_FLOW_MIN_VOLUME", "500"))


def get_min_premium() -> float:
    return float(os.getenv("OPTIONS_FLOW_MIN_PREMIUM", "200000"))


def get_min_volume_oi_ratio() -> float:
    return float(os.getenv("OPTIONS_FLOW_MIN_VOLUME_OI_RATIO", "3.0"))


def _last_us_trading_date(now_ny: datetime) -> datetime.date:
    if _XCALS_AVAILABLE:
        cal = xcals.get_calendar("XNYS")
        today = now_ny.date()
        if now_ny.time() < time(16, 0):
            session = cal.previous_session(today)
            return session.date() if hasattr(session, "date") else session
        if cal.is_session(today):
            return today
        session = cal.previous_session(today)
        return session.date() if hasattr(session, "date") else session

    # Fallback: weekend logic only
    date_val = now_ny.date()
    if now_ny.time() < time(16, 0):
        date_val = date_val - timedelta(days=1)
    while date_val.weekday() >= 5:
        date_val = date_val - timedelta(days=1)
    return date_val


def get_last_us_session_window() -> Tuple[str, str, str]:
    """Return (since_utc, until_utc, session_date_str) for last completed US session."""
    tz = ZoneInfo(US_MARKET_TZ)
    now_ny = datetime.now(tz)
    session_date = _last_us_trading_date(now_ny)
    start_ny = datetime.combine(session_date, time(9, 30), tzinfo=tz)
    end_ny = datetime.combine(session_date, time(16, 0), tzinfo=tz)
    since = start_ny.astimezone(timezone.utc).strftime("%Y-%m-%d_%H:%M:%S_UTC")
    until = end_ny.astimezone(timezone.utc).strftime("%Y-%m-%d_%H:%M:%S_UTC")
    return since, until, session_date.strftime("%Y-%m-%d")
