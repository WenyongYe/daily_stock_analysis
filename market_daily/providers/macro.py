# -*- coding: utf-8 -*-
"""
宏观数据 Provider

- VIX：yfinance + 日/周变化
- 收益率曲线：official 同源快照（FRED 主源 + Treasury 校验，失败时 fallback）
- 历史追踪：将每日利率快照写入 SQLite（data/macro_rates.db）
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

# 确保能 import src 模块
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from src.macro_monitor import fetch_vix, fetch_yield_curve

    _MACRO_AVAILABLE = True
except ImportError as exc:
    print(f"  [MacroProvider] src.macro_monitor 不可用: {exc}", file=sys.stderr)
    _MACRO_AVAILABLE = False


_MACRO_DB_PATH = _ROOT / "data" / "macro_rates.db"


def _vix_level_label(vix: float, day_chg: float | None, week_chg: float | None) -> str:
    if vix >= 35:
        return "🚨 极度恐慌"
    if vix >= 25:
        return "⚠️ 高位恐慌"
    if vix >= 20:
        return "🟡 警戒区"

    if day_chg is not None and day_chg >= 8:
        return "⚠️ 快速升温"
    if week_chg is not None and week_chg >= 15:
        return "⚠️ 周度升温"
    if day_chg is not None and day_chg >= 5:
        return "🟠 偏紧张"

    if vix < 15:
        return "🔵 低波动"
    return "🟢 常态"


def _calc_vix_changes() -> dict[str, Any]:
    """计算 VIX 日/周变化（以日线收盘为准）"""
    out: dict[str, Any] = {
        "vix_close": None,
        "day_change_pct": None,
        "week_change_pct": None,
        "last_week_close": None,
        "last_date": None,
    }
    try:
        import yfinance as yf

        hist = yf.Ticker("^VIX").history(period="3mo", interval="1d")
        if hist is None or hist.empty:
            return out

        closes = hist["Close"].dropna()
        if closes.empty:
            return out

        last_close = float(closes.iloc[-1])
        last_ts = closes.index[-1].to_pydatetime()
        last_date = last_ts.date()

        out["vix_close"] = last_close
        out["last_date"] = str(last_date)

        # 日变化（相对前一个交易日）
        if len(closes) >= 2:
            prev_close = float(closes.iloc[-2])
            if prev_close > 0:
                out["day_change_pct"] = round((last_close - prev_close) / prev_close * 100, 2)

        # 周变化（相对上周最后一个交易日）
        start_current_week = last_date - timedelta(days=last_date.weekday())
        prev_week = closes[closes.index.date < start_current_week]
        if not prev_week.empty:
            last_week_close = float(prev_week.iloc[-1])
            out["last_week_close"] = last_week_close
            if last_week_close > 0:
                out["week_change_pct"] = round((last_close - last_week_close) / last_week_close * 100, 2)

    except Exception as exc:
        print(f"  [MacroProvider] VIX 日/周变化计算失败: {exc}", file=sys.stderr)

    return out


def _ensure_history_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS yield_curve_daily (
            observation_date TEXT PRIMARY KEY,
            source_primary TEXT NOT NULL,
            source_secondary TEXT,
            quality TEXT,
            asof_utc TEXT,
            stale_days INTEGER,
            y3m REAL,
            y2y REAL,
            y5y REAL,
            y10y REAL,
            y30y REAL,
            spread_2y10y_bp REAL,
            spread_3m10y_bp REAL,
            curve_shape TEXT,
            validation_json TEXT,
            raw_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _persist_yield_curve(payload: dict[str, Any]) -> None:
    observation_date = payload.get("observation_date")
    if not observation_date:
        return

    rates = payload.get("rates") or {}
    _MACRO_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(_MACRO_DB_PATH) as conn:
        _ensure_history_schema(conn)
        conn.execute(
            """
            INSERT INTO yield_curve_daily (
                observation_date, source_primary, source_secondary, quality, asof_utc,
                stale_days, y3m, y2y, y5y, y10y, y30y,
                spread_2y10y_bp, spread_3m10y_bp, curve_shape,
                validation_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(observation_date) DO UPDATE SET
                source_primary=excluded.source_primary,
                source_secondary=excluded.source_secondary,
                quality=excluded.quality,
                asof_utc=excluded.asof_utc,
                stale_days=excluded.stale_days,
                y3m=excluded.y3m,
                y2y=excluded.y2y,
                y5y=excluded.y5y,
                y10y=excluded.y10y,
                y30y=excluded.y30y,
                spread_2y10y_bp=excluded.spread_2y10y_bp,
                spread_3m10y_bp=excluded.spread_3m10y_bp,
                curve_shape=excluded.curve_shape,
                validation_json=excluded.validation_json,
                raw_json=excluded.raw_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                observation_date,
                payload.get("source") or "unknown",
                payload.get("secondary_source"),
                payload.get("quality"),
                payload.get("asof_utc"),
                payload.get("stale_days"),
                rates.get("3M"),
                rates.get("2Y"),
                rates.get("5Y"),
                rates.get("10Y"),
                rates.get("30Y"),
                payload.get("spread_2y10y_bp"),
                payload.get("spread_3m10y_bp"),
                payload.get("curve_shape"),
                json.dumps(payload.get("validation") or {}, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
            ),
        )


class MacroProvider:
    """宏观指标数据拉取器（VIX + 收益率曲线）"""

    def fetch(self) -> dict[str, Any]:
        """
        Returns:
            {
              "vix": float | None,
              "vix_label": str,
              "vix_day_change_pct": float | None,
              "vix_week_change_pct": float | None,
              "vix_last_week_close": float | None,
              "yield_curve": {
                    "source": str,
                    "secondary_source": str | None,
                    "observation_date": str,
                    "asof_utc": str,
                    "quality": str,
                    "stale_days": int | None,
                    "rates": {tenor: rate},
                    "spread_2y10y_bp": float | None,
                    "spread_3m10y_bp": float | None,
                    "curve_shape": str,
                    "validation": dict,
                    "consistency": dict,
              },
              "source": str,
            }
        """
        result: dict[str, Any] = {
            "vix": None,
            "vix_label": "N/A",
            "vix_day_change_pct": None,
            "vix_week_change_pct": None,
            "vix_last_week_close": None,
            "yield_curve": {},
            "source": "unknown",
        }

        vix_ref = _calc_vix_changes()
        result["vix_day_change_pct"] = vix_ref.get("day_change_pct")
        result["vix_week_change_pct"] = vix_ref.get("week_change_pct")
        result["vix_last_week_close"] = vix_ref.get("last_week_close")

        if not _MACRO_AVAILABLE:
            print("  [MacroProvider] macro_monitor 不可用", file=sys.stderr)
            return result

        try:
            vix_val = fetch_vix()
            if vix_val is not None:
                result["vix"] = float(vix_val)
            elif vix_ref.get("vix_close") is not None:
                result["vix"] = float(vix_ref["vix_close"])

            if result["vix"] is not None:
                result["vix_label"] = _vix_level_label(
                    result["vix"],
                    result.get("vix_day_change_pct"),
                    result.get("vix_week_change_pct"),
                )

            curve = fetch_yield_curve()
            if curve is not None:
                spread_2y10y_bp = curve.spread_2y10y
                rates = curve.rates or {}
                calc_spread_bp = None
                diff_bp = None
                if "2Y" in rates and "10Y" in rates:
                    calc_spread_bp = round((rates["10Y"] - rates["2Y"]) * 100, 1)
                    if spread_2y10y_bp is not None:
                        diff_bp = round(calc_spread_bp - spread_2y10y_bp, 2)

                yield_payload = {
                    "source": curve.source_primary,
                    "secondary_source": curve.source_secondary,
                    "observation_date": curve.observation_date,
                    "asof_utc": curve.asof_utc,
                    "quality": curve.quality,
                    "stale_days": curve.stale_days,
                    "rates": rates,
                    "spread_2y10y_bp": spread_2y10y_bp,
                    "spread_3m10y_bp": curve.spread_3m10y,
                    "curve_shape": curve.curve_shape,
                    "validation": curve.validation or {},
                    "consistency": {
                        "calc_10y_minus_2y_bp": calc_spread_bp,
                        "reported_spread_2y10y_bp": spread_2y10y_bp,
                        "diff_bp": diff_bp,
                        "passed": diff_bp is None or abs(diff_bp) <= 1.0,
                    },
                }

                result["yield_curve"] = yield_payload
                result["source"] = curve.source_primary

                try:
                    _persist_yield_curve(yield_payload)
                except Exception as exc:
                    print(f"  [MacroProvider] 入库失败: {exc}", file=sys.stderr)

                print(
                    "  [MacroProvider] curve source={} date={} 2Y={} 10Y={} spread={}bp".format(
                        yield_payload.get("source"),
                        yield_payload.get("observation_date"),
                        rates.get("2Y"),
                        rates.get("10Y"),
                        yield_payload.get("spread_2y10y_bp"),
                    ),
                    file=sys.stderr,
                )

            return result

        except Exception as exc:
            print(f"  [MacroProvider] 异常: {exc}", file=sys.stderr)
            return result
