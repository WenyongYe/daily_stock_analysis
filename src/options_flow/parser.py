# -*- coding: utf-8 -*-
"""Parse option flow items from tweet text and OCR output."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class OptionFlowItem:
    symbol: str
    option_type: str
    expiry: Optional[str]
    strike: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    premium: Optional[float]
    source: str
    tweet_url: str
    tweet_time: str
    image_url: Optional[str] = None
    raw_text: Optional[str] = None


def _normalize_symbol(value: str) -> Optional[str]:
    if not value:
        return None
    val = value.strip().upper().lstrip("$")
    if re.match(r"^[A-Z]{1,6}$", val):
        return val
    return None


def _normalize_option_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).lower()
    if "call" in v or v == "c":
        return "call"
    if "put" in v or v == "p":
        return "put"
    return None


def _parse_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().upper().replace(",", "")
    if not text:
        return None
    match = re.match(r"^\$?([0-9]*\.?[0-9]+)\s*([KMB])?$", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "K":
        number *= 1_000
    elif unit == "M":
        number *= 1_000_000
    elif unit == "B":
        number *= 1_000_000_000
    return number


def _parse_int(value: Any) -> Optional[int]:
    num = _parse_number(value)
    if num is None:
        return None
    return int(num)


def _parse_expiry(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


def _parse_strike(value: Any) -> Optional[float]:
    num = _parse_number(value)
    if num is None:
        return None
    return float(num)


def extract_from_text(text: str, tweet_url: str, tweet_time: str) -> Optional[OptionFlowItem]:
    if not text:
        return None
    tickers = re.findall(r"\$[A-Z]{1,6}", text)
    if not tickers:
        return None
    symbol = _normalize_symbol(tickers[0])
    if not symbol:
        return None

    lower = text.lower()
    option_type = "call" if "call" in lower else ("put" if "put" in lower else "call")

    premium_match = re.search(r"\$\s*([0-9]*\.?[0-9]+)\s*([KMB])", text, re.IGNORECASE)
    premium = _parse_number("".join(premium_match.groups())) if premium_match else None

    return OptionFlowItem(
        symbol=symbol,
        option_type=option_type,
        expiry=None,
        strike=None,
        volume=None,
        open_interest=None,
        premium=premium,
        source="text",
        tweet_url=tweet_url,
        tweet_time=tweet_time,
        raw_text=text.strip(),
    )


def extract_from_ocr(data: dict[str, Any], tweet_url: str, tweet_time: str, image_url: str) -> Optional[OptionFlowItem]:
    symbol = _normalize_symbol(data.get("symbol") or data.get("ticker") or "")
    if not symbol:
        return None

    option_type = _normalize_option_type(data.get("option_type") or data.get("type")) or "call"
    expiry = _parse_expiry(data.get("expiry") or data.get("expiration"))
    strike = _parse_strike(data.get("strike"))
    volume = _parse_int(data.get("volume"))
    open_interest = _parse_int(data.get("open_interest") or data.get("oi"))
    premium = _parse_number(data.get("premium"))

    return OptionFlowItem(
        symbol=symbol,
        option_type=option_type,
        expiry=expiry,
        strike=strike,
        volume=volume,
        open_interest=open_interest,
        premium=premium,
        source="image",
        tweet_url=tweet_url,
        tweet_time=tweet_time,
        image_url=image_url,
    )


def deduplicate_items(items: list[OptionFlowItem]) -> list[OptionFlowItem]:
    merged: dict[tuple, OptionFlowItem] = {}
    for item in items:
        key = (
            item.symbol,
            item.option_type,
            item.expiry or "",
            item.strike or 0.0,
        )
        if key not in merged:
            merged[key] = item
            continue
        exist = merged[key]
        if exist.volume is None and item.volume is not None:
            exist.volume = item.volume
        elif exist.volume is not None and item.volume is not None:
            exist.volume = max(exist.volume, item.volume)
        if exist.open_interest is None and item.open_interest is not None:
            exist.open_interest = item.open_interest
        elif exist.open_interest is not None and item.open_interest is not None:
            exist.open_interest = max(exist.open_interest, item.open_interest)
        if exist.premium is None and item.premium is not None:
            exist.premium = item.premium
        elif exist.premium is not None and item.premium is not None:
            exist.premium = max(exist.premium, item.premium)
        if not exist.expiry and item.expiry:
            exist.expiry = item.expiry
        if not exist.strike and item.strike:
            exist.strike = item.strike
        merged[key] = exist

    return list(merged.values())


def volume_oi_ratio(item: OptionFlowItem) -> Optional[float]:
    if item.volume is None or item.open_interest in (None, 0):
        return None
    return round(item.volume / item.open_interest, 2)
