# -*- coding: utf-8 -*-
"""
官方利率快照拉取器（FRED + U.S. Treasury）

目标：
1) 2Y/10Y/3M 使用同源同日期口径
2) 提供 Treasury 对账信息
3) 失败时降级到 yfinance（仅兜底）
"""

from __future__ import annotations

import csv
import io
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

HTTP_TIMEOUT_SECONDS = float(os.getenv("RATE_HTTP_TIMEOUT_SECONDS", "8"))
HTTP_RETRIES = int(os.getenv("RATE_HTTP_RETRIES", "2"))

FRED_SERIES: dict[str, str] = {
    "3M": "DGS3MO",
    "2Y": "DGS2",
    "5Y": "DGS5",
    "10Y": "DGS10",
    "30Y": "DGS30",
}

TREASURY_COLUMN_MAP: dict[str, str] = {
    "3 Mo": "3M",
    "2 Yr": "2Y",
    "5 Yr": "5Y",
    "10 Yr": "10Y",
    "30 Yr": "30Y",
}

YF_FALLBACK_TICKERS: dict[str, str] = {
    "3M": "^IRX",
    "5Y": "^FVX",
    "10Y": "^TNX",
    "30Y": "^TYX",
}


@dataclass
class RatesSnapshot:
    source_primary: str
    source_secondary: str | None
    observation_date: str
    asof_utc: str
    rates: dict[str, float]
    spread_2y10y_bp: float | None
    spread_3m10y_bp: float | None
    curve_shape: str
    quality: str
    stale_days: int | None
    validation: dict[str, Any] = field(default_factory=dict)


def _http_get_text(url: str, timeout_seconds: float = HTTP_TIMEOUT_SECONDS, retries: int = HTTP_RETRIES) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (OpenClaw daily_stock_analysis)",
        "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.8",
    }
    for attempt in range(1, retries + 2):
        try:
            response = requests.get(url, timeout=timeout_seconds, headers=headers)
            if response.status_code == 200:
                return response.text
            raise RuntimeError(f"status={response.status_code}")
        except Exception as exc:
            if attempt >= retries + 1:
                logger.debug(f"HTTP GET failed after retries: url={url} error={exc}")
                return None
            time.sleep(0.4 * attempt)
    return None


def _parse_observation_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _fetch_fred_series_history(series_id: str) -> dict[str, float]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    body = _http_get_text(url)
    if not body:
        return {}

    reader = csv.DictReader(io.StringIO(body))
    result: dict[str, float] = {}
    for row in reader:
        date_str = (row.get("DATE") or "").strip()
        value_str = (row.get(series_id) or "").strip()
        if not date_str or not value_str or value_str in {".", "NaN", "nan"}:
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue
        result[date_str] = value
    return result


def _fetch_fred_snapshot() -> tuple[str, dict[str, float]] | None:
    series_history: dict[str, dict[str, float]] = {}

    with ThreadPoolExecutor(max_workers=len(FRED_SERIES)) as executor:
        futures = {
            executor.submit(_fetch_fred_series_history, series_id): tenor
            for tenor, series_id in FRED_SERIES.items()
        }
        for future in as_completed(futures):
            tenor = futures[future]
            try:
                series_history[tenor] = future.result()
            except Exception as exc:
                logger.debug(f"FRED pull failed: tenor={tenor} error={exc}")
                series_history[tenor] = {}

    required_tenors = ["3M", "2Y", "10Y"]
    if any(not series_history.get(tenor) for tenor in required_tenors):
        return None

    common_dates = set(series_history[required_tenors[0]].keys())
    for tenor in required_tenors[1:]:
        common_dates &= set(series_history[tenor].keys())

    if not common_dates:
        return None

    observation_date = max(common_dates)
    rates: dict[str, float] = {}
    for tenor, history in series_history.items():
        if observation_date in history:
            rates[tenor] = round(float(history[observation_date]), 3)

    if "2Y" not in rates or "10Y" not in rates:
        return None

    return observation_date, rates


def _build_treasury_year_urls(base_year: int) -> list[str]:
    template = (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
        "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&"
        "field_tdr_date_value={year}&page&_format=csv"
    )
    return [template.format(year=base_year), template.format(year=base_year - 1)]


def _fetch_treasury_snapshot() -> tuple[str, dict[str, float]] | None:
    year = datetime.now(timezone.utc).year
    rows: list[tuple[date, dict[str, float]]] = []

    for url in _build_treasury_year_urls(year):
        body = _http_get_text(url)
        if not body:
            continue

        reader = csv.DictReader(io.StringIO(body))
        for row in reader:
            date_text = (row.get("Date") or row.get("DATE") or "").strip()
            obs_date = _parse_observation_date(date_text)
            if obs_date is None:
                continue

            rates: dict[str, float] = {}
            for col_name, tenor in TREASURY_COLUMN_MAP.items():
                value_text = (row.get(col_name) or "").strip()
                if not value_text:
                    continue
                try:
                    rates[tenor] = round(float(value_text), 3)
                except ValueError:
                    continue

            if rates:
                rows.append((obs_date, rates))

        if rows:
            break

    if not rows:
        return None

    rows.sort(key=lambda item: item[0], reverse=True)
    for obs_date, rates in rows:
        if "2Y" in rates and "10Y" in rates:
            return obs_date.isoformat(), rates

    latest_date, latest_rates = rows[0]
    return latest_date.isoformat(), latest_rates


def _fetch_yfinance_fallback_snapshot() -> tuple[str, dict[str, float]] | None:
    rates: dict[str, float] = {}

    for tenor, ticker in YF_FALLBACK_TICKERS.items():
        for attempt in range(1, HTTP_RETRIES + 2):
            try:
                history = yf.Ticker(ticker).history(period="2d", interval="1d")
                if history.empty:
                    break
                rates[tenor] = round(float(history["Close"].iloc[-1]), 3)
                break
            except Exception as exc:
                if attempt >= HTTP_RETRIES + 1:
                    logger.debug(f"yfinance fallback failed: tenor={tenor} ticker={ticker} error={exc}")
                else:
                    time.sleep(0.25 * attempt)

    if not rates:
        return None

    return datetime.now(timezone.utc).date().isoformat(), rates


def _calculate_spread_bp(rates: dict[str, float], short_tenor: str, long_tenor: str) -> float | None:
    if short_tenor not in rates or long_tenor not in rates:
        return None
    return round((rates[long_tenor] - rates[short_tenor]) * 100, 1)


def _curve_shape(spread_3m10y_bp: float | None) -> str:
    if spread_3m10y_bp is None:
        return "未知"
    if spread_3m10y_bp < -50:
        return "🔴 深度倒挂"
    if spread_3m10y_bp < 0:
        return "🟠 倒挂"
    if spread_3m10y_bp < 30:
        return "🟡 平坦"
    if spread_3m10y_bp < 100:
        return "🟢 正常"
    return "🔵 陡峭"


def _calculate_stale_days(observation_date: str) -> int | None:
    obs = _parse_observation_date(observation_date)
    if obs is None:
        return None
    return (datetime.now(timezone.utc).date() - obs).days


def build_official_rates_snapshot() -> RatesSnapshot | None:
    """优先返回 FRED 同源快照，并附加 Treasury 对账。"""
    asof_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    fred_snapshot = _fetch_fred_snapshot()
    treasury_snapshot = _fetch_treasury_snapshot()

    if fred_snapshot:
        observation_date, rates = fred_snapshot
        spread_2y10y_bp = _calculate_spread_bp(rates, "2Y", "10Y")
        spread_3m10y_bp = _calculate_spread_bp(rates, "3M", "10Y")

        validation: dict[str, Any] = {
            "matched_date": False,
            "treasury_observation_date": None,
            "diff_2y_bp": None,
            "diff_10y_bp": None,
            "max_abs_diff_bp": None,
        }

        if treasury_snapshot:
            treasury_date, treasury_rates = treasury_snapshot
            validation["treasury_observation_date"] = treasury_date
            validation["matched_date"] = treasury_date == observation_date
            if validation["matched_date"]:
                diff_2y_bp = None
                diff_10y_bp = None
                if "2Y" in treasury_rates and "2Y" in rates:
                    diff_2y_bp = round((rates["2Y"] - treasury_rates["2Y"]) * 100, 1)
                if "10Y" in treasury_rates and "10Y" in rates:
                    diff_10y_bp = round((rates["10Y"] - treasury_rates["10Y"]) * 100, 1)
                validation["diff_2y_bp"] = diff_2y_bp
                validation["diff_10y_bp"] = diff_10y_bp
                diffs = [abs(v) for v in (diff_2y_bp, diff_10y_bp) if v is not None]
                validation["max_abs_diff_bp"] = max(diffs) if diffs else None

        return RatesSnapshot(
            source_primary="fred",
            source_secondary="treasury" if treasury_snapshot else None,
            observation_date=observation_date,
            asof_utc=asof_utc,
            rates=rates,
            spread_2y10y_bp=spread_2y10y_bp,
            spread_3m10y_bp=spread_3m10y_bp,
            curve_shape=_curve_shape(spread_3m10y_bp),
            quality="official",
            stale_days=_calculate_stale_days(observation_date),
            validation=validation,
        )

    if treasury_snapshot:
        observation_date, rates = treasury_snapshot
        spread_2y10y_bp = _calculate_spread_bp(rates, "2Y", "10Y")
        spread_3m10y_bp = _calculate_spread_bp(rates, "3M", "10Y")

        return RatesSnapshot(
            source_primary="treasury",
            source_secondary=None,
            observation_date=observation_date,
            asof_utc=asof_utc,
            rates=rates,
            spread_2y10y_bp=spread_2y10y_bp,
            spread_3m10y_bp=spread_3m10y_bp,
            curve_shape=_curve_shape(spread_3m10y_bp),
            quality="official",
            stale_days=_calculate_stale_days(observation_date),
            validation={"matched_date": False},
        )

    fallback = _fetch_yfinance_fallback_snapshot()
    if not fallback:
        return None

    observation_date, rates = fallback
    spread_2y10y_bp = _calculate_spread_bp(rates, "2Y", "10Y")
    spread_3m10y_bp = _calculate_spread_bp(rates, "3M", "10Y")

    return RatesSnapshot(
        source_primary="yfinance_fallback",
        source_secondary=None,
        observation_date=observation_date,
        asof_utc=asof_utc,
        rates=rates,
        spread_2y10y_bp=spread_2y10y_bp,
        spread_3m10y_bp=spread_3m10y_bp,
        curve_shape=_curve_shape(spread_3m10y_bp),
        quality="fallback",
        stale_days=_calculate_stale_days(observation_date),
        validation={"matched_date": False},
    )
