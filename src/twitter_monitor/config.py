# -*- coding: utf-8 -*-
"""Twitter 监控配置"""

import os
from datetime import datetime, timedelta, timezone


TWITTER_API_BASE = "https://api.twitterapi.io/twitter"

# 默认监控账号，可通过环境变量 TWITTER_MONITOR_ACCOUNTS 覆盖（逗号分隔）
DEFAULT_ACCOUNTS = ["FirstSquawk", "DeItaone", "KobeissiLetter", "financialjuice"]


def get_api_key() -> str:
    return os.getenv("TWITTER_API_KEY", "")


def get_fetch_interval_hours() -> int:
    return int(os.getenv("TWITTER_FETCH_INTERVAL_HOURS", "8"))


def get_monitor_accounts() -> list[str]:
    env_val = os.getenv("TWITTER_MONITOR_ACCOUNTS", "")
    if env_val.strip():
        return [a.strip().lstrip("@") for a in env_val.split(",") if a.strip()]
    return DEFAULT_ACCOUNTS


def get_time_window(hours: int | None = None) -> tuple[str, str]:
    """返回 (since, until) UTC 时间字符串，格式: YYYY-MM-DD_HH:MM:SS_UTC"""
    hours = hours or get_fetch_interval_hours()
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    fmt = "%Y-%m-%d_%H:%M:%S_UTC"
    return since.strftime(fmt), now.strftime(fmt)
