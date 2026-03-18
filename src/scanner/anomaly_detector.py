# -*- coding: utf-8 -*-
"""
Anomaly Detector

Multi-dimensional anomaly detection for US stocks:
- Volume anomalies (spike, consecutive heavy, unusual shrink)
- Price breakouts (N-day high/low, key MA cross)
- Momentum anomalies (RSI extremes, MACD cross, consecutive moves)
- Sector correlation (multiple stocks in same sector moving together)
- News catalysts (via existing SearchService)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    VOLUME_SPIKE = "volume_spike"
    VOLUME_CONSECUTIVE = "volume_consecutive"
    PRICE_NEW_HIGH = "price_new_high"
    PRICE_NEW_LOW = "price_new_low"
    MA_CROSS = "ma_cross"
    RSI_EXTREME = "rsi_extreme"
    MACD_CROSS = "macd_cross"
    CONSECUTIVE_MOVE = "consecutive_move"
    GAP = "gap"
    SECTOR_CORRELATION = "sector_correlation"
    NEWS_CATALYST = "news_catalyst"


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AnomalyAlert:
    """A detected anomaly."""
    code: str
    anomaly_type: AnomalyType
    severity: Severity
    direction: str  # "bullish", "bearish", "neutral"
    description: str
    score: float = 0.0  # 0-100 significance

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "type": self.anomaly_type.value,
            "severity": self.severity.value,
            "direction": self.direction,
            "description": self.description,
            "score": self.score,
        }


class AnomalyDetector:
    """Detects multi-dimensional anomalies in stock data."""

    def analyze(self, df: pd.DataFrame, code: str) -> List[AnomalyAlert]:
        """
        Detect all anomalies for a single stock.

        Args:
            df: OHLCV DataFrame sorted by date ascending.
            code: Stock symbol.
        """
        if df is None or df.empty or len(df) < 10:
            return []

        df = df.sort_values("date").reset_index(drop=True)
        alerts: List[AnomalyAlert] = []

        alerts.extend(self._detect_volume_anomalies(df, code))
        alerts.extend(self._detect_price_anomalies(df, code))
        alerts.extend(self._detect_momentum_anomalies(df, code))
        alerts.extend(self._detect_gap(df, code))

        return sorted(alerts, key=lambda a: a.score, reverse=True)

    def detect_sector_correlation(
        self, stock_alerts: Dict[str, List[AnomalyAlert]], sector_map: Dict[str, str]
    ) -> List[AnomalyAlert]:
        """
        Detect when multiple stocks in the same sector show anomalies.

        Args:
            stock_alerts: {symbol: [alerts]} for all scanned stocks.
            sector_map: {symbol: sector_name} mapping.
        """
        sector_alert_counts: Dict[str, List[str]] = {}
        for symbol, alerts in stock_alerts.items():
            if not alerts:
                continue
            sector = sector_map.get(symbol, "unknown")
            if sector == "unknown":
                continue
            significant = [a for a in alerts if a.score >= 60]
            if significant:
                sector_alert_counts.setdefault(sector, []).append(symbol)

        results = []
        for sector, symbols in sector_alert_counts.items():
            if len(symbols) >= 3:
                results.append(AnomalyAlert(
                    code=sector,
                    anomaly_type=AnomalyType.SECTOR_CORRELATION,
                    severity=Severity.HIGH if len(symbols) >= 5 else Severity.MEDIUM,
                    direction="neutral",
                    description=f"Sector [{sector}]: {len(symbols)} stocks showing anomalies ({', '.join(symbols[:5])})",
                    score=min(90, 50 + len(symbols) * 8),
                ))

        return results

    # ============================
    # Volume Anomalies
    # ============================

    def _detect_volume_anomalies(self, df: pd.DataFrame, code: str) -> List[AnomalyAlert]:
        alerts = []
        vol = df["volume"].values
        close = df["close"].values
        latest_vol = float(vol[-1])
        avg_5d = float(np.mean(vol[-6:-1])) if len(vol) >= 6 else float(np.mean(vol[:-1]))
        avg_20d = float(np.mean(vol[-21:-1])) if len(vol) >= 21 else avg_5d

        ratio_5d = latest_vol / avg_5d if avg_5d > 0 else 0
        ratio_20d = latest_vol / avg_20d if avg_20d > 0 else 0

        price_chg = (close[-1] - close[-2]) / close[-2] * 100 if len(close) > 1 else 0

        # Single-day volume spike
        if ratio_20d >= 3.0:
            direction = "bullish" if price_chg > 1 else ("bearish" if price_chg < -1 else "neutral")
            severity = Severity.CRITICAL if ratio_20d >= 5.0 else Severity.HIGH
            alerts.append(AnomalyAlert(
                code=code, anomaly_type=AnomalyType.VOLUME_SPIKE,
                severity=severity, direction=direction,
                description=f"Volume spike: {ratio_20d:.1f}x 20d avg, price {price_chg:+.1f}%",
                score=min(95, 60 + (ratio_20d - 3) * 10),
            ))
        elif ratio_5d >= 2.0:
            direction = "bullish" if price_chg > 0.5 else ("bearish" if price_chg < -0.5 else "neutral")
            alerts.append(AnomalyAlert(
                code=code, anomaly_type=AnomalyType.VOLUME_SPIKE,
                severity=Severity.MEDIUM, direction=direction,
                description=f"Elevated volume: {ratio_5d:.1f}x 5d avg, price {price_chg:+.1f}%",
                score=55,
            ))

        # Consecutive heavy volume (3+ days)
        if len(vol) >= 4:
            consecutive = 0
            for i in range(-1, -4, -1):
                day_avg = float(np.mean(vol[max(0, i - 5):i])) if abs(i) < len(vol) - 5 else avg_5d
                if day_avg > 0 and vol[i] / day_avg >= 1.5:
                    consecutive += 1
                else:
                    break
            if consecutive >= 3:
                alerts.append(AnomalyAlert(
                    code=code, anomaly_type=AnomalyType.VOLUME_CONSECUTIVE,
                    severity=Severity.HIGH, direction="neutral",
                    description=f"{consecutive} consecutive days of heavy volume",
                    score=70,
                ))

        return alerts

    # ============================
    # Price Anomalies
    # ============================

    def _detect_price_anomalies(self, df: pd.DataFrame, code: str) -> List[AnomalyAlert]:
        alerts = []
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        current = float(close[-1])

        # New N-day high/low
        for n in [20, 50]:
            if len(df) > n:
                n_high = float(np.max(high[-n - 1:-1]))
                n_low = float(np.min(low[-n - 1:-1]))
                if current > n_high:
                    alerts.append(AnomalyAlert(
                        code=code, anomaly_type=AnomalyType.PRICE_NEW_HIGH,
                        severity=Severity.HIGH if n == 50 else Severity.MEDIUM,
                        direction="bullish",
                        description=f"New {n}-day high: ${current:.2f} (prev: ${n_high:.2f})",
                        score=75 if n == 50 else 65,
                    ))
                    break  # Only report highest significance
                elif current < n_low:
                    alerts.append(AnomalyAlert(
                        code=code, anomaly_type=AnomalyType.PRICE_NEW_LOW,
                        severity=Severity.HIGH if n == 50 else Severity.MEDIUM,
                        direction="bearish",
                        description=f"New {n}-day low: ${current:.2f} (prev: ${n_low:.2f})",
                        score=75 if n == 50 else 65,
                    ))
                    break

        # MA cross events
        if len(df) >= 50:
            ma20 = df["close"].rolling(20).mean().values
            ma50 = df["close"].rolling(50).mean().values
            if not (np.isnan(ma20[-1]) or np.isnan(ma20[-2]) or np.isnan(ma50[-1]) or np.isnan(ma50[-2])):
                # MA20 crossing MA50
                if ma20[-2] < ma50[-2] and ma20[-1] >= ma50[-1]:
                    alerts.append(AnomalyAlert(
                        code=code, anomaly_type=AnomalyType.MA_CROSS,
                        severity=Severity.MEDIUM, direction="bullish",
                        description="MA20 golden cross above MA50",
                        score=70,
                    ))
                elif ma20[-2] > ma50[-2] and ma20[-1] <= ma50[-1]:
                    alerts.append(AnomalyAlert(
                        code=code, anomaly_type=AnomalyType.MA_CROSS,
                        severity=Severity.MEDIUM, direction="bearish",
                        description="MA20 death cross below MA50",
                        score=70,
                    ))

        return alerts

    # ============================
    # Momentum Anomalies
    # ============================

    def _detect_momentum_anomalies(self, df: pd.DataFrame, code: str) -> List[AnomalyAlert]:
        alerts = []
        close = df["close"].values

        # RSI extremes
        if len(df) >= 14:
            rsi = self._calc_rsi(close, 14)
            if rsi is not None:
                if rsi > 80:
                    alerts.append(AnomalyAlert(
                        code=code, anomaly_type=AnomalyType.RSI_EXTREME,
                        severity=Severity.MEDIUM, direction="bearish",
                        description=f"RSI(14) extremely overbought: {rsi:.1f}",
                        score=60,
                    ))
                elif rsi < 20:
                    alerts.append(AnomalyAlert(
                        code=code, anomaly_type=AnomalyType.RSI_EXTREME,
                        severity=Severity.MEDIUM, direction="bullish",
                        description=f"RSI(14) extremely oversold: {rsi:.1f}",
                        score=60,
                    ))

        # MACD cross
        if len(df) >= 26:
            ema12 = pd.Series(close).ewm(span=12, adjust=False).mean().values
            ema26 = pd.Series(close).ewm(span=26, adjust=False).mean().values
            dif = ema12 - ema26
            dea = pd.Series(dif).ewm(span=9, adjust=False).mean().values
            if len(dif) >= 2:
                if dif[-2] < dea[-2] and dif[-1] >= dea[-1]:
                    above_zero = dif[-1] > 0
                    alerts.append(AnomalyAlert(
                        code=code, anomaly_type=AnomalyType.MACD_CROSS,
                        severity=Severity.HIGH if above_zero else Severity.MEDIUM,
                        direction="bullish",
                        description=f"MACD golden cross{' above zero axis' if above_zero else ''}",
                        score=75 if above_zero else 60,
                    ))
                elif dif[-2] > dea[-2] and dif[-1] <= dea[-1]:
                    alerts.append(AnomalyAlert(
                        code=code, anomaly_type=AnomalyType.MACD_CROSS,
                        severity=Severity.MEDIUM, direction="bearish",
                        description="MACD death cross",
                        score=65,
                    ))

        # Consecutive green/red days
        if len(close) >= 4:
            consecutive_up = 0
            consecutive_down = 0
            for i in range(-1, -min(10, len(close)), -1):
                if close[i] > close[i - 1]:
                    if consecutive_down > 0:
                        break
                    consecutive_up += 1
                elif close[i] < close[i - 1]:
                    if consecutive_up > 0:
                        break
                    consecutive_down += 1
                else:
                    break

            if consecutive_up >= 5:
                alerts.append(AnomalyAlert(
                    code=code, anomaly_type=AnomalyType.CONSECUTIVE_MOVE,
                    severity=Severity.MEDIUM, direction="bullish",
                    description=f"{consecutive_up} consecutive green days",
                    score=55 + consecutive_up * 3,
                ))
            elif consecutive_down >= 5:
                alerts.append(AnomalyAlert(
                    code=code, anomaly_type=AnomalyType.CONSECUTIVE_MOVE,
                    severity=Severity.MEDIUM, direction="bearish",
                    description=f"{consecutive_down} consecutive red days",
                    score=55 + consecutive_down * 3,
                ))

        return alerts

    # ============================
    # Gap Detection
    # ============================

    def _detect_gap(self, df: pd.DataFrame, code: str) -> List[AnomalyAlert]:
        """Detect gap up/down."""
        alerts = []
        if len(df) < 2:
            return alerts

        prev = df.iloc[-2]
        curr = df.iloc[-1]
        prev_high = float(prev["high"])
        prev_low = float(prev["low"])
        curr_open = float(curr["open"])
        curr_close = float(curr["close"])
        prev_close = float(prev["close"])

        gap_pct = (curr_open - prev_close) / prev_close * 100

        # Gap up: today's low > yesterday's high
        if float(curr["low"]) > prev_high:
            alerts.append(AnomalyAlert(
                code=code, anomaly_type=AnomalyType.GAP,
                severity=Severity.HIGH if abs(gap_pct) > 3 else Severity.MEDIUM,
                direction="bullish",
                description=f"Gap up {gap_pct:+.1f}%: opened ${curr_open:.2f} above prev high ${prev_high:.2f}",
                score=min(85, 55 + abs(gap_pct) * 5),
            ))
        # Gap down: today's high < yesterday's low
        elif float(curr["high"]) < prev_low:
            alerts.append(AnomalyAlert(
                code=code, anomaly_type=AnomalyType.GAP,
                severity=Severity.HIGH if abs(gap_pct) > 3 else Severity.MEDIUM,
                direction="bearish",
                description=f"Gap down {gap_pct:+.1f}%: opened ${curr_open:.2f} below prev low ${prev_low:.2f}",
                score=min(85, 55 + abs(gap_pct) * 5),
            ))

        return alerts

    # ============================
    # Helpers
    # ============================

    @staticmethod
    def _calc_rsi(close: np.ndarray, period: int = 14) -> Optional[float]:
        """Calculate RSI for the last bar."""
        if len(close) < period + 1:
            return None
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
