# -*- coding: utf-8 -*-
"""
Volume-Price Analysis Engine (SRxTrades Style)

Core philosophy: Volume tells the TRUTH that price alone cannot.
- Context-aware volume analysis (not just high/low, but WHERE it happens)
- Support/Resistance identification from price structure
- Breakout/Pullback quality assessment with volume confirmation
- Volume-price divergence detection
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class KeyLevel:
    """A support or resistance price level."""
    price: float
    level_type: str  # "support" | "resistance"
    source: str  # "swing_high", "swing_low", "ma20", "ma50", "ma200", "volume_cluster", "round_number"
    strength: float = 0.0  # 0-100


@dataclass
class VolumePriceSignal:
    """Result of volume-price analysis."""
    code: str
    current_price: float = 0.0

    # Volume context
    volume_ratio_5d: float = 0.0  # today vol / 5d avg
    volume_ratio_20d: float = 0.0  # today vol / 20d avg
    volume_context: str = ""  # human-readable volume context
    is_volume_breakout: bool = False  # heavy vol at key level
    is_shrink_pullback: bool = False  # healthy pullback on low vol
    is_volume_divergence: bool = False  # price up but vol down (warning)
    volume_trend_5d: str = ""  # "increasing", "decreasing", "stable"

    # Key levels
    support_levels: List[KeyLevel] = field(default_factory=list)
    resistance_levels: List[KeyLevel] = field(default_factory=list)
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0

    # Breakout/Pullback status
    breakout_signal: str = ""  # "breakout_confirmed", "breakout_attempt", "false_breakout", ""
    pullback_signal: str = ""  # "pullback_to_support", "healthy_pullback", "breakdown", ""
    breakout_level: float = 0.0
    pullback_level: float = 0.0

    # Moving averages
    ma20: float = 0.0
    ma50: float = 0.0
    ma200: float = 0.0
    above_ma20: bool = False
    above_ma50: bool = False
    above_ma200: bool = False

    # Signal strength
    signal_strength: float = 0.0  # 0-100 composite score
    signal_direction: str = ""  # "bullish", "bearish", "neutral"
    signal_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "current_price": self.current_price,
            "volume_ratio_5d": round(self.volume_ratio_5d, 2),
            "volume_ratio_20d": round(self.volume_ratio_20d, 2),
            "volume_context": self.volume_context,
            "is_volume_breakout": self.is_volume_breakout,
            "is_shrink_pullback": self.is_shrink_pullback,
            "is_volume_divergence": self.is_volume_divergence,
            "volume_trend_5d": self.volume_trend_5d,
            "support_levels": [{"price": l.price, "type": l.source, "strength": l.strength} for l in self.support_levels],
            "resistance_levels": [{"price": l.price, "type": l.source, "strength": l.strength} for l in self.resistance_levels],
            "nearest_support": self.nearest_support,
            "nearest_resistance": self.nearest_resistance,
            "breakout_signal": self.breakout_signal,
            "pullback_signal": self.pullback_signal,
            "ma20": self.ma20, "ma50": self.ma50, "ma200": self.ma200,
            "above_ma20": self.above_ma20, "above_ma50": self.above_ma50, "above_ma200": self.above_ma200,
            "signal_strength": round(self.signal_strength, 1),
            "signal_direction": self.signal_direction,
            "signal_reasons": self.signal_reasons,
        }


class VolumePriceEngine:
    """
    SRxTrades-style volume-price analysis engine.

    Key principles:
    1. Volume at key levels matters more than volume in isolation
    2. Breakouts need volume confirmation; pullbacks should be on low volume
    3. Divergence between price and volume is a warning sign
    """

    # Thresholds
    HEAVY_VOL_RATIO = 2.0  # > 2x avg = heavy
    HIGH_VOL_RATIO = 1.5  # > 1.5x avg = elevated
    LOW_VOL_RATIO = 0.7  # < 0.7x avg = low
    SHRINK_VOL_RATIO = 0.5  # < 0.5x avg = shrink
    SWING_LOOKBACK = 5  # bars for swing high/low detection
    NEAR_LEVEL_PCT = 0.02  # within 2% of a level = "near"

    def __init__(self, heavy_vol_ratio: float = 2.0):
        self.HEAVY_VOL_RATIO = heavy_vol_ratio

    def analyze(self, df: pd.DataFrame, code: str) -> VolumePriceSignal:
        """
        Run full volume-price analysis on OHLCV data.

        Args:
            df: DataFrame with columns [date, open, high, low, close, volume]
            code: Stock symbol
        """
        signal = VolumePriceSignal(code=code)

        if df is None or df.empty or len(df) < 20:
            logger.warning(f"{code}: insufficient data for volume-price analysis")
            return signal

        df = df.sort_values("date").reset_index(drop=True)
        latest = df.iloc[-1]
        signal.current_price = float(latest["close"])

        # Calculate MAs
        self._calc_moving_averages(df, signal)

        # Volume analysis
        self._analyze_volume_context(df, signal)

        # Identify key support/resistance levels
        self._identify_key_levels(df, signal)

        # Breakout/pullback detection
        self._detect_breakout_pullback(df, signal)

        # Volume-price divergence
        self._detect_divergence(df, signal)

        # Generate composite signal
        self._score_signal(signal)

        return signal

    def _calc_moving_averages(self, df: pd.DataFrame, signal: VolumePriceSignal):
        """Calculate key moving averages."""
        close = df["close"]
        price = signal.current_price

        if len(df) >= 20:
            signal.ma20 = float(close.rolling(20).mean().iloc[-1])
            signal.above_ma20 = price > signal.ma20
        if len(df) >= 50:
            signal.ma50 = float(close.rolling(50).mean().iloc[-1])
            signal.above_ma50 = price > signal.ma50
        if len(df) >= 200:
            signal.ma200 = float(close.rolling(200).mean().iloc[-1])
            signal.above_ma200 = price > signal.ma200

    def _analyze_volume_context(self, df: pd.DataFrame, signal: VolumePriceSignal):
        """Analyze volume in the context of price action."""
        vol = df["volume"].values
        close = df["close"].values
        latest_vol = float(vol[-1])
        latest_close = float(close[-1])
        prev_close = float(close[-2]) if len(close) > 1 else latest_close
        price_change_pct = (latest_close - prev_close) / prev_close * 100 if prev_close else 0

        # Volume ratios
        avg_5d = float(np.mean(vol[-6:-1])) if len(vol) >= 6 else float(np.mean(vol))
        avg_20d = float(np.mean(vol[-21:-1])) if len(vol) >= 21 else float(np.mean(vol))

        signal.volume_ratio_5d = latest_vol / avg_5d if avg_5d > 0 else 0
        signal.volume_ratio_20d = latest_vol / avg_20d if avg_20d > 0 else 0

        # Volume trend (last 5 days)
        if len(vol) >= 5:
            recent_vols = vol[-5:]
            if all(recent_vols[i] <= recent_vols[i + 1] for i in range(len(recent_vols) - 1)):
                signal.volume_trend_5d = "increasing"
            elif all(recent_vols[i] >= recent_vols[i + 1] for i in range(len(recent_vols) - 1)):
                signal.volume_trend_5d = "decreasing"
            else:
                vol_slope = np.polyfit(range(5), recent_vols, 1)[0]
                if vol_slope > avg_5d * 0.05:
                    signal.volume_trend_5d = "increasing"
                elif vol_slope < -avg_5d * 0.05:
                    signal.volume_trend_5d = "decreasing"
                else:
                    signal.volume_trend_5d = "stable"

        # Context-aware interpretation
        contexts = []
        if signal.volume_ratio_5d >= self.HEAVY_VOL_RATIO:
            if price_change_pct > 1.0:
                contexts.append("heavy volume rally - strong buying pressure")
                signal.is_volume_breakout = True
            elif price_change_pct < -1.0:
                contexts.append("heavy volume selloff - strong selling pressure")
            else:
                contexts.append("heavy volume churn - battle between buyers and sellers")
        elif signal.volume_ratio_5d >= self.HIGH_VOL_RATIO:
            if price_change_pct > 0.5:
                contexts.append("elevated volume on green day - moderate buying interest")
            elif price_change_pct < -0.5:
                contexts.append("elevated volume on red day - distribution")
        elif signal.volume_ratio_5d <= self.SHRINK_VOL_RATIO:
            if price_change_pct < -0.5:
                contexts.append("shrink volume pullback - healthy consolidation")
                signal.is_shrink_pullback = True
            elif price_change_pct > 0.5:
                contexts.append("low volume rally - lack of conviction")
        elif signal.volume_ratio_5d <= self.LOW_VOL_RATIO:
            contexts.append("below-average volume - quiet session")

        signal.volume_context = "; ".join(contexts) if contexts else "normal volume activity"

    def _identify_key_levels(self, df: pd.DataFrame, signal: VolumePriceSignal):
        """Identify support and resistance levels."""
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        volume = df["volume"].values
        price = signal.current_price

        supports: List[KeyLevel] = []
        resistances: List[KeyLevel] = []

        # 1. Swing highs and lows
        lb = self.SWING_LOOKBACK
        for i in range(lb, len(df) - lb):
            # Swing high
            if high[i] == max(high[i - lb:i + lb + 1]):
                level = float(high[i])
                if level > price:
                    resistances.append(KeyLevel(level, "resistance", "swing_high", 70))
                else:
                    supports.append(KeyLevel(level, "support", "swing_high", 60))
            # Swing low
            if low[i] == min(low[i - lb:i + lb + 1]):
                level = float(low[i])
                if level < price:
                    supports.append(KeyLevel(level, "support", "swing_low", 70))
                else:
                    resistances.append(KeyLevel(level, "resistance", "swing_low", 60))

        # 2. Moving average levels
        for ma_val, ma_name in [(signal.ma20, "ma20"), (signal.ma50, "ma50"), (signal.ma200, "ma200")]:
            if ma_val > 0:
                strength = 60 if ma_name == "ma20" else (75 if ma_name == "ma50" else 85)
                if ma_val < price:
                    supports.append(KeyLevel(ma_val, "support", ma_name, strength))
                else:
                    resistances.append(KeyLevel(ma_val, "resistance", ma_name, strength))

        # 3. Volume-weighted price clusters (simplified volume profile)
        if len(df) >= 20:
            recent_df = df.tail(20)
            price_bins = np.linspace(recent_df["low"].min(), recent_df["high"].max(), 20)
            vol_profile = np.zeros(len(price_bins) - 1)
            for _, row in recent_df.iterrows():
                for j in range(len(price_bins) - 1):
                    if price_bins[j] <= row["close"] <= price_bins[j + 1]:
                        vol_profile[j] += row["volume"]
            # Find high-volume nodes
            if vol_profile.max() > 0:
                threshold = np.percentile(vol_profile[vol_profile > 0], 75)
                for j in range(len(vol_profile)):
                    if vol_profile[j] >= threshold:
                        cluster_price = (price_bins[j] + price_bins[j + 1]) / 2
                        if cluster_price < price:
                            supports.append(KeyLevel(round(cluster_price, 2), "support", "volume_cluster", 65))
                        else:
                            resistances.append(KeyLevel(round(cluster_price, 2), "resistance", "volume_cluster", 65))

        # 4. Round numbers
        base = round(price, -1)  # nearest 10
        for rn in [base - 10, base, base + 10]:
            if rn > 0:
                if rn < price:
                    supports.append(KeyLevel(rn, "support", "round_number", 40))
                elif rn > price:
                    resistances.append(KeyLevel(rn, "resistance", "round_number", 40))

        # Deduplicate and sort
        supports = self._dedupe_levels(supports, price, is_support=True)
        resistances = self._dedupe_levels(resistances, price, is_support=False)

        signal.support_levels = sorted(supports, key=lambda l: l.price, reverse=True)[:5]
        signal.resistance_levels = sorted(resistances, key=lambda l: l.price)[:5]

        if signal.support_levels:
            signal.nearest_support = signal.support_levels[0].price
        if signal.resistance_levels:
            signal.nearest_resistance = signal.resistance_levels[0].price

    def _dedupe_levels(self, levels: List[KeyLevel], price: float, is_support: bool) -> List[KeyLevel]:
        """Merge levels that are within 1% of each other, keeping the strongest."""
        if not levels:
            return levels
        levels.sort(key=lambda l: l.price, reverse=not is_support)
        merged: List[KeyLevel] = [levels[0]]
        for lv in levels[1:]:
            if abs(lv.price - merged[-1].price) / price < 0.01:
                if lv.strength > merged[-1].strength:
                    merged[-1] = lv
            else:
                merged.append(lv)
        return merged

    def _detect_breakout_pullback(self, df: pd.DataFrame, signal: VolumePriceSignal):
        """Detect breakout attempts and pullback patterns."""
        if len(df) < 10:
            return

        price = signal.current_price
        close = df["close"].values
        high = df["high"].values
        prev_close = float(close[-2])

        # Check for breakout above recent highs
        recent_high = float(np.max(high[-21:-1])) if len(df) >= 21 else float(np.max(high[:-1]))
        if price > recent_high:
            if signal.volume_ratio_5d >= self.HIGH_VOL_RATIO:
                signal.breakout_signal = "breakout_confirmed"
                signal.breakout_level = recent_high
                signal.signal_reasons.append(
                    f"Confirmed breakout above ${recent_high:.2f} on {signal.volume_ratio_5d:.1f}x volume"
                )
            else:
                signal.breakout_signal = "breakout_attempt"
                signal.breakout_level = recent_high
                signal.signal_reasons.append(
                    f"Breakout attempt above ${recent_high:.2f} but volume weak ({signal.volume_ratio_5d:.1f}x)"
                )

        # Check for false breakout (broke out yesterday but reversed today)
        if len(df) >= 22:
            prev_recent_high = float(np.max(high[-22:-2]))
            if prev_close > prev_recent_high and price < prev_recent_high:
                signal.breakout_signal = "false_breakout"
                signal.signal_reasons.append(f"False breakout: reversed below ${prev_recent_high:.2f}")

        # Pullback detection
        if signal.nearest_support > 0:
            dist_to_support = (price - signal.nearest_support) / price
            if dist_to_support < self.NEAR_LEVEL_PCT:
                if signal.volume_ratio_5d <= self.LOW_VOL_RATIO:
                    signal.pullback_signal = "healthy_pullback"
                    signal.pullback_level = signal.nearest_support
                    signal.signal_reasons.append(
                        f"Healthy pullback to support ${signal.nearest_support:.2f} on low volume"
                    )
                else:
                    signal.pullback_signal = "pullback_to_support"
                    signal.pullback_level = signal.nearest_support

        # Check for breakdown below support
        if signal.support_levels:
            for sl in signal.support_levels:
                if price < sl.price and prev_close >= sl.price:
                    if signal.volume_ratio_5d >= self.HIGH_VOL_RATIO:
                        signal.pullback_signal = "breakdown"
                        signal.signal_reasons.append(
                            f"Breakdown below ${sl.price:.2f} ({sl.source}) on heavy volume"
                        )
                    break

    def _detect_divergence(self, df: pd.DataFrame, signal: VolumePriceSignal):
        """Detect volume-price divergence."""
        if len(df) < 10:
            return

        close = df["close"].values
        volume = df["volume"].values

        # Look at last 10 bars for divergence
        recent_close = close[-10:]
        recent_vol = volume[-10:]

        # Price making higher highs but volume declining
        price_highs = []
        vol_at_highs = []
        for i in range(2, len(recent_close)):
            if recent_close[i] > recent_close[i - 1] and recent_close[i] > recent_close[i - 2]:
                price_highs.append(recent_close[i])
                vol_at_highs.append(recent_vol[i])

        if len(price_highs) >= 2:
            if price_highs[-1] > price_highs[0] and vol_at_highs[-1] < vol_at_highs[0] * 0.8:
                signal.is_volume_divergence = True
                signal.signal_reasons.append(
                    "Bearish divergence: price making higher highs but volume declining"
                )

        # Price making lower lows but volume declining (bullish divergence)
        price_lows = []
        vol_at_lows = []
        for i in range(2, len(recent_close)):
            if recent_close[i] < recent_close[i - 1] and recent_close[i] < recent_close[i - 2]:
                price_lows.append(recent_close[i])
                vol_at_lows.append(recent_vol[i])

        if len(price_lows) >= 2:
            if price_lows[-1] < price_lows[0] and vol_at_lows[-1] < vol_at_lows[0] * 0.8:
                signal.signal_reasons.append(
                    "Bullish divergence: price making lower lows but selling volume drying up"
                )

    def _score_signal(self, signal: VolumePriceSignal):
        """Generate composite signal strength score (0-100)."""
        score = 50.0  # neutral baseline

        # Volume breakout at key level
        if signal.is_volume_breakout and signal.breakout_signal == "breakout_confirmed":
            score += 25
        elif signal.breakout_signal == "breakout_attempt":
            score += 10
        elif signal.breakout_signal == "false_breakout":
            score -= 15

        # Healthy pullback to support
        if signal.pullback_signal == "healthy_pullback":
            score += 20
        elif signal.pullback_signal == "pullback_to_support":
            score += 10
        elif signal.pullback_signal == "breakdown":
            score -= 20

        # Volume-price divergence
        if signal.is_volume_divergence:
            score -= 10

        # Shrink volume pullback (bullish)
        if signal.is_shrink_pullback and signal.above_ma20:
            score += 15

        # MA alignment
        if signal.above_ma20 and signal.above_ma50:
            score += 10
            if signal.above_ma200:
                score += 5
        elif not signal.above_ma20 and not signal.above_ma50:
            score -= 10

        signal.signal_strength = max(0, min(100, score))

        if signal.signal_strength >= 65:
            signal.signal_direction = "bullish"
        elif signal.signal_strength <= 35:
            signal.signal_direction = "bearish"
        else:
            signal.signal_direction = "neutral"
