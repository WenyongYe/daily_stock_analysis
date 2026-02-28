# -*- coding: utf-8 -*-
"""
===================================
宏观指标监控模块
===================================

监控内容：
1. VIX 恐慌指数 - 变化幅度 + 阈值预警
2. 美债收益率曲线 - 2Y/5Y/10Y/30Y + 关键利差
3. 曲线形态判断（倒挂/正常/牛陡/熊陡）

数据源：Yahoo Finance（yfinance，免费）
推送：飞书 Webhook

环境变量：
    VIX_ALERT_LEVEL     - VIX 预警阈值（默认 20，多个用逗号：20,30,40）
    VIX_CHANGE_PCT      - VIX 单次变动预警幅度（默认 10%）
    YIELD_CHANGE_BP     - 收益率单次变动预警（基点，默认 10bp）
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# ===== 配置 =====
STATE_FILE = Path(os.getenv("MACRO_STATE_FILE", "data/macro_state.json"))

# VIX 阈值（越过时提醒）
_vix_levels_raw = os.getenv("VIX_ALERT_LEVEL", "20,30,40")
VIX_ALERT_LEVELS = [float(x.strip()) for x in _vix_levels_raw.split(",") if x.strip()]

# VIX 单次变动预警幅度（%）
VIX_CHANGE_PCT_THRESH = float(os.getenv("VIX_CHANGE_PCT", "10"))

# 收益率变动预警（基点）
YIELD_CHANGE_BP_THRESH = float(os.getenv("YIELD_CHANGE_BP", "10"))

# 美债 Ticker 映射
YIELD_TICKERS: Dict[str, str] = {
    "3M":  "^IRX",
    "2Y":  "^IRX",   # Yahoo 没有独立2Y ticker，用 FRED 的 DGS2 如果配了
    "5Y":  "^FVX",
    "10Y": "^TNX",
    "30Y": "^TYX",
}

# 实际使用的 ticker（Yahoo Finance 有的）
ACTIVE_TICKERS: Dict[str, str] = {
    "3M":  "^IRX",
    "5Y":  "^FVX",
    "10Y": "^TNX",
    "30Y": "^TYX",
}

# 尝试用 US Treasury API 补充 2Y（更准确）
TREASURY_API = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/202502?type=daily_treasury_yield_curve&field_tdr_date_value_month=202502&page&_format=csv"


@dataclass
class YieldCurve:
    """收益率曲线快照"""
    timestamp: datetime
    rates: Dict[str, float]   # {"3M": 5.23, "2Y": 4.71, "5Y": 4.45, "10Y": 4.32, "30Y": 4.55}

    @property
    def spread_2y10y(self) -> Optional[float]:
        """2Y-10Y 利差（bp）= 10Y - 2Y，负值为倒挂"""
        if "2Y" in self.rates and "10Y" in self.rates:
            return round((self.rates["10Y"] - self.rates["2Y"]) * 100, 1)
        return None

    @property
    def spread_3m10y(self) -> Optional[float]:
        """3M-10Y 利差（bp），最常用的倒挂指标"""
        if "3M" in self.rates and "10Y" in self.rates:
            return round((self.rates["10Y"] - self.rates["3M"]) * 100, 1)
        return None

    @property
    def spread_5y30y(self) -> Optional[float]:
        """5Y-30Y 利差（bp），牛陡/熊陡判断"""
        if "5Y" in self.rates and "30Y" in self.rates:
            return round((self.rates["30Y"] - self.rates["5Y"]) * 100, 1)
        return None

    @property
    def curve_shape(self) -> str:
        """曲线形态判断"""
        s = self.spread_3m10y
        if s is None:
            return "未知"
        if s < -50:
            return "🔴 深度倒挂"
        if s < 0:
            return "🟠 倒挂"
        if s < 30:
            return "🟡 平坦"
        if s < 100:
            return "🟢 正常"
        return "🔵 陡峭"

    def format_display(self) -> str:
        lines = ["**美债收益率**"]
        order = ["3M", "2Y", "5Y", "10Y", "30Y"]
        for k in order:
            if k in self.rates:
                lines.append(f"  {k:>3s}: {self.rates[k]:.3f}%")
        if self.spread_3m10y is not None:
            inv = "⚠️ 倒挂" if self.spread_3m10y < 0 else ""
            lines.append(f"  3M-10Y 利差: {self.spread_3m10y:+.0f}bp {inv}")
        if self.spread_2y10y is not None:
            inv = "⚠️ 倒挂" if self.spread_2y10y < 0 else ""
            lines.append(f"  2Y-10Y 利差: {self.spread_2y10y:+.0f}bp {inv}")
        lines.append(f"  形态: {self.curve_shape}")
        return "\n".join(lines)


@dataclass
class VixSnapshot:
    """VIX 快照"""
    timestamp: datetime
    value: float
    prev_value: Optional[float] = None

    @property
    def change_pct(self) -> Optional[float]:
        if self.prev_value and self.prev_value > 0:
            return round((self.value - self.prev_value) / self.prev_value * 100, 1)
        return None

    @property
    def level_label(self) -> str:
        if self.value >= 40:
            return "🔴 极度恐慌"
        if self.value >= 30:
            return "🟠 恐慌"
        if self.value >= 20:
            return "🟡 警觉"
        if self.value >= 15:
            return "🟢 正常"
        return "🔵 低波动"

    def format_display(self) -> str:
        chg = f" ({self.change_pct:+.1f}%)" if self.change_pct is not None else ""
        return f"**VIX** {self.value:.2f}{chg}  {self.level_label}"


# ===== 数据获取 =====

def fetch_vix() -> Optional[float]:
    """获取当前 VIX"""
    try:
        ticker = yf.Ticker("^VIX")
        hist = ticker.history(period="1d", interval="1m")
        if hist.empty:
            hist = ticker.history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning(f"VIX 获取失败: {e}")
    return None


def fetch_yield_curve() -> Optional[YieldCurve]:
    """获取美债收益率曲线"""
    rates: Dict[str, float] = {}

    # 1. 从 Yahoo Finance 拉取主要期限
    for tenor, ticker_sym in ACTIVE_TICKERS.items():
        try:
            t = yf.Ticker(ticker_sym)
            hist = t.history(period="1d", interval="1m")
            if hist.empty:
                hist = t.history(period="2d")
            if not hist.empty:
                # Yahoo Finance IRX/FVX/TNX/TYX 单位是 % (已×10 or ×100?)
                # ^IRX = 13-week T-Bill × 10 → 需要 /10
                # ^TNX = 10-year × 10 → /10
                val = float(hist["Close"].iloc[-1])
                # Yahoo 财经的债券指数直接是 yield × 10（如 TNX=43.2 代表 4.32%）
                # 实际上 ^TNX 的 Close 是直接的百分比值（如 4.32 = 4.32%）
                rates[tenor] = round(val, 3)
        except Exception as e:
            logger.debug(f"Yahoo Finance {tenor}({ticker_sym}) 失败: {e}")

    # 2. 尝试从 US Treasury 补充 2Y（如网络可达）
    try:
        resp = requests.get(
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            lines = resp.text.strip().split("\n")
            if len(lines) >= 2:
                headers = [h.strip().strip('"') for h in lines[0].split(",")]
                last_row = [v.strip().strip('"') for v in lines[-1].split(",")]
                row = dict(zip(headers, last_row))
                # 常见列名："2 Yr", "5 Yr", "10 Yr", "30 Yr", "1 Mo"
                mapping = {
                    "1 Mo": "3M", "2 Mo": "3M",
                    "3 Mo": "3M", "6 Mo": "6M",
                    "1 Yr": "1Y", "2 Yr": "2Y",
                    "3 Yr": "3Y", "5 Yr": "5Y",
                    "7 Yr": "7Y", "10 Yr": "10Y",
                    "20 Yr": "20Y", "30 Yr": "30Y",
                }
                for col, tenor in mapping.items():
                    if col in row and row[col]:
                        try:
                            rates[tenor] = float(row[col])
                        except ValueError:
                            pass
    except Exception as e:
        logger.debug(f"Treasury CSV 获取失败: {e}")

    if not rates:
        return None

    return YieldCurve(timestamp=datetime.now(timezone.utc), rates=rates)


# ===== 状态持久化 =====

class MacroState:
    """宏观指标历史状态（用于变化对比）"""

    def __init__(self, state_file: Path = STATE_FILE):
        self._file = state_file
        self._data: Dict = {}
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                self._data = json.loads(self._file.read_text())
            except Exception:
                self._data = {}

    def _save(self):
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(self._data, ensure_ascii=False, indent=2))

    def get_prev_vix(self) -> Optional[float]:
        return self._data.get("vix")

    def set_vix(self, val: float):
        self._data["vix"] = val
        self._data["vix_ts"] = datetime.now().isoformat()
        self._save()

    def get_prev_yields(self) -> Dict[str, float]:
        return self._data.get("yields", {})

    def set_yields(self, rates: Dict[str, float]):
        self._data["yields"] = rates
        self._data["yields_ts"] = datetime.now().isoformat()
        self._save()

    def get_crossed_vix_levels(self) -> List[float]:
        """已触发过的 VIX 阈值（防重复报警）"""
        return self._data.get("vix_alerted_levels", [])

    def set_crossed_vix_levels(self, levels: List[float]):
        self._data["vix_alerted_levels"] = levels
        self._save()


# ===== 报警判断 =====

@dataclass
class MacroAlert:
    """宏观预警条目"""
    level: str   # "WARN" / "INFO"
    message: str


def check_vix_alerts(vix: VixSnapshot, state: MacroState) -> List[MacroAlert]:
    alerts: List[MacroAlert] = []
    alerted = set(state.get_crossed_vix_levels())

    # 阈值穿越报警
    for lvl in VIX_ALERT_LEVELS:
        crossed = vix.value >= lvl
        was_crossed = lvl in alerted
        if crossed and not was_crossed:
            alerts.append(MacroAlert("WARN", f"⚡ VIX 突破 {lvl:.0f}！当前 {vix.value:.2f} {vix.level_label}"))
            alerted.add(lvl)
        elif not crossed and was_crossed:
            # 回落时清除（允许下次再触发）
            alerted.discard(lvl)

    state.set_crossed_vix_levels(list(alerted))

    # 单次变动预警
    if vix.change_pct is not None and abs(vix.change_pct) >= VIX_CHANGE_PCT_THRESH:
        direction = "上涨" if vix.change_pct > 0 else "下跌"
        alerts.append(MacroAlert(
            "WARN",
            f"⚡ VIX 急{direction} {abs(vix.change_pct):.1f}%！{vix.prev_value:.2f} → {vix.value:.2f}",
        ))

    return alerts


def check_yield_alerts(curve: YieldCurve, state: MacroState) -> List[MacroAlert]:
    alerts: List[MacroAlert] = []
    prev = state.get_prev_yields()
    if not prev:
        return alerts

    for tenor, rate in curve.rates.items():
        if tenor not in prev:
            continue
        change_bp = (rate - prev[tenor]) * 100
        if abs(change_bp) >= YIELD_CHANGE_BP_THRESH:
            direction = "上行" if change_bp > 0 else "下行"
            alerts.append(MacroAlert(
                "INFO",
                f"📈 美债 {tenor} {direction} {abs(change_bp):.1f}bp → {rate:.3f}%",
            ))

    # 曲线倒挂状态变化提醒
    s = curve.spread_3m10y
    ps_val = (prev.get("10Y", 0) - prev.get("3M", 0)) * 100 if "10Y" in prev and "3M" in prev else None
    if s is not None and ps_val is not None:
        if ps_val >= 0 > s:
            alerts.append(MacroAlert("WARN", f"⚠️ 美债收益率曲线倒挂！3M-10Y = {s:+.0f}bp"))
        elif ps_val < 0 <= s:
            alerts.append(MacroAlert("INFO", f"✅ 美债收益率曲线恢复正常，3M-10Y = {s:+.0f}bp"))

    return alerts


# ===== 主控 =====

class MacroMonitor:
    """
    宏观指标监控主控
    """

    def __init__(self, feishu_webhook_url: Optional[str] = None, notifier=None):
        self._webhook = feishu_webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")
        self._notifier = notifier  # 可传入 NotificationService 实例
        self._state = MacroState()

    def run_once(self, force_report: bool = False) -> str:
        """
        执行一次监控检查。
        force_report=True 强制推送完整快照（用于日报）
        返回格式化的摘要文本（可用于集成进日报）
        """
        alerts: List[MacroAlert] = []
        lines: List[str] = []

        # ---- VIX ----
        vix_val = fetch_vix()
        if vix_val is not None:
            prev_vix = self._state.get_prev_vix()
            vix = VixSnapshot(
                timestamp=datetime.now(timezone.utc),
                value=vix_val,
                prev_value=prev_vix,
            )
            lines.append(vix.format_display())
            alerts.extend(check_vix_alerts(vix, self._state))
            self._state.set_vix(vix_val)
        else:
            lines.append("VIX: 获取失败")

        # ---- 收益率曲线 ----
        curve = fetch_yield_curve()
        if curve is not None:
            lines.append("")
            lines.append(curve.format_display())
            alerts.extend(check_yield_alerts(curve, self._state))
            self._state.set_yields(curve.rates)
        else:
            lines.append("收益率曲线: 获取失败")

        summary = "\n".join(lines)

        # 推送预警
        if alerts:
            alert_text = "\n".join(f"{'🚨' if a.level == 'WARN' else 'ℹ️'} {a.message}" for a in alerts)
            push_text = f"📡 **宏观预警** ({datetime.now().strftime('%H:%M')})\n{alert_text}\n\n{summary}"
            self._push_feishu(push_text)
        elif force_report:
            push_text = f"📊 **宏观日报** ({datetime.now().strftime('%m-%d %H:%M')})\n\n{summary}"
            self._push_feishu(push_text)

        return summary

    def _push_feishu(self, text: str) -> bool:
        # 优先用项目 NotificationService（支持多渠道）
        if self._notifier is not None:
            return self._notifier.send(text, email_send_to_all=True)
        # 回退：直接 Feishu Webhook
        if not self._webhook:
            logger.warning("未配置 FEISHU_WEBHOOK_URL")
            return False
        payload = {"msg_type": "text", "content": {"text": text}}
        try:
            resp = requests.post(self._webhook, json=payload, timeout=10)
            ok = resp.status_code == 200 and resp.json().get("code") == 0
            if ok:
                logger.info("宏观指标推送成功")
            else:
                logger.warning(f"宏观指标推送失败: {resp.text[:200]}")
            return ok
        except Exception as e:
            logger.error(f"推送异常: {e}")
        return False
