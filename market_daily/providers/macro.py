# -*- coding: utf-8 -*-
"""
宏观数据 Provider
复用 src/macro_monitor.py 的 VIX + 美债收益率曲线拉取
并补充 VIX 的日变化/周变化（相对上周收盘）
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# 确保能 import src 模块
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from src.macro_monitor import fetch_vix, fetch_yield_curve
    _MACRO_AVAILABLE = True
except ImportError as e:
    print(f"  [MacroProvider] src.macro_monitor 不可用: {e}，降级到 yfinance", file=sys.stderr)
    _MACRO_AVAILABLE = False


def _fallback_vix() -> Optional[float]:
    """yfinance 降级拉 VIX"""
    try:
        import yfinance as yf
        t = yf.Ticker("^VIX")
        return float(t.fast_info.last_price)
    except Exception:
        return None


def _fallback_yields() -> dict:
    """yfinance 降级拉收益率（不再把 ^IRX 误当 2Y）"""
    try:
        import yfinance as yf
        result = {}
        # 注意：^IRX 是 13-week bill，不等于 2Y
        for sym, key in [("^TNX", "10Y"), ("^FVX", "5Y"), ("^TYX", "30Y"), ("^IRX", "3M")]:
            try:
                result[key] = float(yf.Ticker(sym).fast_info.last_price)
            except Exception:
                pass
        return result
    except Exception:
        return {}


def _vix_level_label(vix: float, day_chg: Optional[float], week_chg: Optional[float]) -> str:
    """VIX 风险标签：水平 + 变化率联合判断"""
    # 绝对水平
    if vix >= 35:
        return "🚨 极度恐慌"
    if vix >= 25:
        return "⚠️ 高位恐慌"
    if vix >= 20:
        return "🟡 警戒区"

    # 低于 20 时，变化率仍可能表示“升温异常”
    if day_chg is not None and day_chg >= 8:
        return "⚠️ 快速升温"
    if week_chg is not None and week_chg >= 15:
        return "⚠️ 周度升温"
    if day_chg is not None and day_chg >= 5:
        return "🟠 偏紧张"

    if vix < 15:
        return "🔵 低波动"
    return "🟢 常态"


def _calc_vix_changes() -> dict:
    """
    计算 VIX 日/周变化

    Returns:
        {
          "vix_close": float | None,
          "day_change_pct": float | None,      # 对比上个交易日收盘
          "week_change_pct": float | None,     # 对比上周最后一个交易日收盘
          "last_week_close": float | None,
          "last_date": "YYYY-MM-DD" | None,
        }
    """
    out = {
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

        # 周变化（相对上周最后一个交易日收盘）
        start_current_week = last_date - timedelta(days=last_date.weekday())  # 周一
        prev_week = closes[closes.index.date < start_current_week]
        if not prev_week.empty:
            last_week_close = float(prev_week.iloc[-1])
            out["last_week_close"] = last_week_close
            if last_week_close > 0:
                out["week_change_pct"] = round((last_close - last_week_close) / last_week_close * 100, 2)

    except Exception as e:
        print(f"  [MacroProvider] VIX 日/周变化计算失败: {e}", file=sys.stderr)

    return out


class MacroProvider:
    """宏观指标数据拉取器（VIX + 收益率曲线）"""

    def fetch(self) -> dict:
        """
        Returns:
            dict: {
                "vix": float | None,
                "vix_label": str,
                "vix_day_change_pct": float | None,
                "vix_week_change_pct": float | None,
                "vix_last_week_close": float | None,
                "yield_curve": {
                    "rates": {tenors: rates},
                    "spread_2y10y_bp": float | None,
                    "spread_3m10y_bp": float | None,
                    "curve_shape": str,
                    "display": str,
                },
                "source": "macro_monitor" | "yfinance_fallback"
            }
        """
        result = {
            "vix": None,
            "vix_label": "N/A",
            "vix_day_change_pct": None,
            "vix_week_change_pct": None,
            "vix_last_week_close": None,
            "yield_curve": {},
            "source": "unknown",
        }

        # 先算 VIX 日/周变化（无论是否有 macro_monitor 都可算）
        vix_ref = _calc_vix_changes()
        result["vix_day_change_pct"] = vix_ref.get("day_change_pct")
        result["vix_week_change_pct"] = vix_ref.get("week_change_pct")
        result["vix_last_week_close"] = vix_ref.get("last_week_close")

        if _MACRO_AVAILABLE:
            try:
                vix_val = fetch_vix()
                yc = fetch_yield_curve()
                result["source"] = "macro_monitor"

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

                if yc is not None:
                    # macro_monitor 的 spread_* 单位是 bp
                    result["yield_curve"] = {
                        "rates": yc.rates if hasattr(yc, "rates") else {},
                        "spread_2y10y_bp": yc.spread_2y10y,
                        "spread_3m10y_bp": yc.spread_3m10y,
                        "curve_shape": yc.curve_shape,
                        "display": yc.format_display() if hasattr(yc, "format_display") else "",
                    }

                print(
                    f"  [MacroProvider] macro_monitor 成功，VIX={result['vix']}，"
                    f"日变化={result['vix_day_change_pct']}%，周变化={result['vix_week_change_pct']}%",
                    file=sys.stderr,
                )
                return result
            except Exception as e:
                print(f"  [MacroProvider] macro_monitor 异常: {e}，降级", file=sys.stderr)

        # 降级：直接 yfinance
        vix_val = _fallback_vix()
        yields = _fallback_yields()
        result["source"] = "yfinance_fallback"
        result["vix"] = float(vix_val) if vix_val is not None else vix_ref.get("vix_close")

        if result["vix"] is not None:
            result["vix_label"] = _vix_level_label(
                result["vix"],
                result.get("vix_day_change_pct"),
                result.get("vix_week_change_pct"),
            )

        if yields:
            y10 = yields.get("10Y")
            y5 = yields.get("5Y")
            spread_5y10y_bp = ((y10 - y5) * 100) if (y10 is not None and y5 is not None) else None
            result["yield_curve"] = {
                "rates": yields,
                "spread_2y10y_bp": None,
                "spread_3m10y_bp": None,
                "spread_5y10y_bp": spread_5y10y_bp,
                "curve_shape": "unknown",
                "display": "",
            }

        print(
            f"  [MacroProvider] yfinance fallback，VIX={result['vix']}，"
            f"日变化={result['vix_day_change_pct']}%，周变化={result['vix_week_change_pct']}%",
            file=sys.stderr,
        )
        return result
