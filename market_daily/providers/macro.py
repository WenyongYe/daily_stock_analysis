# -*- coding: utf-8 -*-
"""
宏观数据 Provider
复用 src/macro_monitor.py 的 VIX + 美债收益率曲线拉取
"""

import sys
from pathlib import Path
from typing import Optional

# 确保能 import src 模块
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from src.macro_monitor import fetch_vix, fetch_yield_curve, VixSnapshot, YieldCurve
    _MACRO_AVAILABLE = True
except ImportError as e:
    print(f"  [MacroProvider] src.macro_monitor 不可用: {e}，降级到 yfinance", file=sys.stderr)
    _MACRO_AVAILABLE = False


def _fallback_vix() -> Optional[float]:
    """yfinance 降级拉 VIX"""
    try:
        import yfinance as yf
        t = yf.Ticker("^VIX")
        return t.fast_info.last_price
    except:
        return None


def _fallback_yields() -> dict:
    """yfinance 降级拉收益率"""
    try:
        import yfinance as yf
        result = {}
        for sym, key in [("^TNX", "10y"), ("^IRX", "2y"), ("^TYX", "30y")]:
            try:
                result[key] = yf.Ticker(sym).fast_info.last_price
            except:
                pass
        return result
    except:
        return {}


class MacroProvider:
    """宏观指标数据拉取器（VIX + 收益率曲线）"""

    def fetch(self) -> dict:
        """
        拉取宏观数据

        Returns:
            dict: {
                "vix": float | None,
                "vix_label": str,
                "yield_curve": {
                    "rates": {tenors: rates},
                    "spread_2y10y": float,
                    "spread_3m10y": float,
                    "curve_shape": str,   # "normal" | "inverted" | "flat"
                    "display": str,       # 格式化文本
                },
                "source": "macro_monitor" | "yfinance_fallback"
            }
        """
        result = {
            "vix": None,
            "vix_label": "N/A",
            "yield_curve": {},
            "source": "unknown",
        }

        if _MACRO_AVAILABLE:
            try:
                vix_val = fetch_vix()
                yc = fetch_yield_curve()
                result["source"] = "macro_monitor"

                if vix_val is not None:
                    result["vix"] = vix_val
                    try:
                        snap = VixSnapshot(current=vix_val, previous=None)
                        result["vix_label"] = snap.level_label()
                    except TypeError:
                        # 不同版本构造函数参数不同，直接计算
                        if vix_val >= 30:   result["vix_label"] = "🚨 极度恐慌"
                        elif vix_val >= 25: result["vix_label"] = "⚠️ 恐慌区间"
                        elif vix_val >= 20: result["vix_label"] = "⚠️ 警戒线"
                        else:               result["vix_label"] = "✅ 正常"

                if yc is not None:
                    result["yield_curve"] = {
                        "rates":        yc.rates if hasattr(yc, 'rates') else {},
                        "spread_2y10y": yc.spread_2y10y,
                        "spread_3m10y": yc.spread_3m10y,
                        "curve_shape":  yc.curve_shape,
                        "display":      yc.format_display() if hasattr(yc, 'format_display') else "",
                    }
                print(f"  [MacroProvider] macro_monitor 成功，VIX={vix_val}", file=sys.stderr)
                return result
            except Exception as e:
                print(f"  [MacroProvider] macro_monitor 异常: {e}，降级", file=sys.stderr)

        # 降级：直接用 yfinance
        vix_val = _fallback_vix()
        yields = _fallback_yields()
        result["source"] = "yfinance_fallback"
        result["vix"] = vix_val

        if vix_val is not None:
            if vix_val >= 30:   result["vix_label"] = "🚨 极度恐慌"
            elif vix_val >= 25: result["vix_label"] = "⚠️ 恐慌区间"
            elif vix_val >= 20: result["vix_label"] = "⚠️ 警戒线"
            else:               result["vix_label"] = "✅ 正常"

        if yields:
            y10 = yields.get("10y", 0)
            y2  = yields.get("2y", 0)
            spread = (y10 - y2) if (y10 and y2) else None
            result["yield_curve"] = {
                "rates":        yields,
                "spread_2y10y": spread,
                "spread_3m10y": None,
                "curve_shape":  "inverted" if (spread is not None and spread < 0) else "normal",
                "display":      "",
            }

        print(f"  [MacroProvider] yfinance fallback，VIX={vix_val}", file=sys.stderr)
        return result
