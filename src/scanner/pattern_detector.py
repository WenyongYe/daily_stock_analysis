# -*- coding: utf-8 -*-
"""
K-Line Pattern Detector

Identifies candlestick patterns and chart formations from OHLCV data.
Covers single/multi-bar patterns and classic chart formations.
All implemented with pure pandas/numpy — no external TA library dependency.
"""

import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PatternSignal:
    """A detected pattern."""
    name: str  # pattern name (English)
    name_cn: str  # Chinese name
    direction: str  # "bullish", "bearish", "neutral"
    pattern_type: str  # "candlestick", "chart_formation"
    completeness: float = 0.0  # 0-100, how well-formed the pattern is
    score: float = 0.0  # 0-100 quality score
    description: str = ""


class PatternDetector:
    """Detects candlestick patterns and chart formations."""

    def analyze(self, df: pd.DataFrame) -> List[PatternSignal]:
        """
        Detect all patterns in the given OHLCV data.

        Args:
            df: DataFrame with [date, open, high, low, close, volume] sorted by date ascending.

        Returns:
            List of detected PatternSignal, sorted by score descending.
        """
        if df is None or df.empty or len(df) < 5:
            return []

        df = df.sort_values("date").reset_index(drop=True)
        patterns: List[PatternSignal] = []

        # Single/multi-bar candlestick patterns
        patterns.extend(self._detect_hammer(df))
        patterns.extend(self._detect_engulfing(df))
        patterns.extend(self._detect_doji(df))
        patterns.extend(self._detect_morning_evening_star(df))
        patterns.extend(self._detect_three_soldiers_crows(df))

        # Chart formations (need more data)
        if len(df) >= 20:
            patterns.extend(self._detect_double_bottom_top(df))
        if len(df) >= 30:
            patterns.extend(self._detect_triangle(df))
            patterns.extend(self._detect_cup_handle(df))
        if len(df) >= 15:
            patterns.extend(self._detect_flag(df))
            patterns.extend(self._detect_box_breakout(df))

        return sorted(patterns, key=lambda p: p.score, reverse=True)

    # ============================
    # Candlestick Patterns
    # ============================

    def _detect_hammer(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect hammer and inverted hammer (last bar)."""
        results = []
        row = df.iloc[-1]
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        body = abs(c - o)
        total_range = h - l
        if total_range == 0:
            return results

        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l
        body_ratio = body / total_range

        # Hammer: small body at top, long lower shadow
        if body_ratio < 0.35 and lower_shadow > body * 2 and upper_shadow < body * 0.5:
            # Check if in downtrend (last 5 bars)
            if len(df) >= 5 and float(df.iloc[-5]["close"]) > c:
                results.append(PatternSignal(
                    name="hammer", name_cn="锤子线",
                    direction="bullish", pattern_type="candlestick",
                    completeness=min(100, lower_shadow / body * 25) if body > 0 else 70,
                    score=75 if lower_shadow > body * 3 else 60,
                    description="Hammer at potential bottom — bullish reversal signal"
                ))

        # Inverted hammer: small body at bottom, long upper shadow
        if body_ratio < 0.35 and upper_shadow > body * 2 and lower_shadow < body * 0.5:
            if len(df) >= 5 and float(df.iloc[-5]["close"]) > c:
                results.append(PatternSignal(
                    name="inverted_hammer", name_cn="倒锤子",
                    direction="bullish", pattern_type="candlestick",
                    completeness=min(100, upper_shadow / body * 25) if body > 0 else 70,
                    score=65,
                    description="Inverted hammer — potential bullish reversal"
                ))

        # Shooting star (bearish): inverted hammer at top
        if body_ratio < 0.35 and upper_shadow > body * 2 and lower_shadow < body * 0.5:
            if len(df) >= 5 and float(df.iloc[-5]["close"]) < c:
                results.append(PatternSignal(
                    name="shooting_star", name_cn="射击之星",
                    direction="bearish", pattern_type="candlestick",
                    completeness=min(100, upper_shadow / body * 25) if body > 0 else 70,
                    score=70,
                    description="Shooting star at top — bearish reversal signal"
                ))

        return results

    def _detect_engulfing(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect bullish/bearish engulfing patterns."""
        results = []
        if len(df) < 2:
            return results

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        co, cc = float(curr["open"]), float(curr["close"])
        po, pc = float(prev["open"]), float(prev["close"])

        # Bullish engulfing: prev red, current green body fully covers prev
        if pc < po and cc > co and cc > po and co < pc:
            body_ratio = abs(cc - co) / abs(po - pc) if abs(po - pc) > 0 else 2
            results.append(PatternSignal(
                name="bullish_engulfing", name_cn="看涨吞没",
                direction="bullish", pattern_type="candlestick",
                completeness=min(100, body_ratio * 50),
                score=80 if body_ratio > 1.5 else 65,
                description="Bullish engulfing — strong reversal signal"
            ))

        # Bearish engulfing
        if pc > po and cc < co and cc < po and co > pc:
            body_ratio = abs(co - cc) / abs(pc - po) if abs(pc - po) > 0 else 2
            results.append(PatternSignal(
                name="bearish_engulfing", name_cn="看跌吞没",
                direction="bearish", pattern_type="candlestick",
                completeness=min(100, body_ratio * 50),
                score=80 if body_ratio > 1.5 else 65,
                description="Bearish engulfing — strong reversal signal"
            ))

        return results

    def _detect_doji(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect doji (indecision) patterns."""
        results = []
        row = df.iloc[-1]
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        body = abs(c - o)
        total_range = h - l
        if total_range == 0:
            return results

        if body / total_range < 0.1:
            results.append(PatternSignal(
                name="doji", name_cn="十字星",
                direction="neutral", pattern_type="candlestick",
                completeness=90,
                score=55,
                description="Doji — indecision, potential trend change"
            ))

        return results

    def _detect_morning_evening_star(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect morning star (bullish) and evening star (bearish)."""
        results = []
        if len(df) < 3:
            return results

        d1, d2, d3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
        o1, c1 = float(d1["open"]), float(d1["close"])
        o2, c2 = float(d2["open"]), float(d2["close"])
        o3, c3 = float(d3["open"]), float(d3["close"])
        body2 = abs(c2 - o2)
        range1 = abs(c1 - o1)
        range3 = abs(c3 - o3)

        # Morning star: big red, small body, big green
        if (c1 < o1 and range1 > 0 and  # day1 bearish
                body2 < range1 * 0.3 and  # day2 small body
                c3 > o3 and range3 > range1 * 0.5 and  # day3 bullish
                c3 > (o1 + c1) / 2):  # day3 closes above midpoint of day1
            results.append(PatternSignal(
                name="morning_star", name_cn="早晨之星",
                direction="bullish", pattern_type="candlestick",
                completeness=85, score=80,
                description="Morning star — strong bullish reversal"
            ))

        # Evening star: big green, small body, big red
        if (c1 > o1 and range1 > 0 and
                body2 < range1 * 0.3 and
                c3 < o3 and range3 > range1 * 0.5 and
                c3 < (o1 + c1) / 2):
            results.append(PatternSignal(
                name="evening_star", name_cn="黄昏之星",
                direction="bearish", pattern_type="candlestick",
                completeness=85, score=80,
                description="Evening star — strong bearish reversal"
            ))

        return results

    def _detect_three_soldiers_crows(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect three white soldiers and three black crows."""
        results = []
        if len(df) < 3:
            return results

        bars = [df.iloc[-3], df.iloc[-2], df.iloc[-1]]
        opens = [float(b["open"]) for b in bars]
        closes = [float(b["close"]) for b in bars]
        bodies = [abs(c - o) for o, c in zip(opens, closes)]

        # Three white soldiers: three consecutive green candles with higher closes
        if all(c > o for o, c in zip(opens, closes)):
            if closes[0] < closes[1] < closes[2] and all(b > 0 for b in bodies):
                avg_body = np.mean(bodies)
                if all(b > avg_body * 0.5 for b in bodies):  # all bodies meaningful
                    results.append(PatternSignal(
                        name="three_white_soldiers", name_cn="三个白兵",
                        direction="bullish", pattern_type="candlestick",
                        completeness=90, score=75,
                        description="Three white soldiers — bullish continuation"
                    ))

        # Three black crows
        if all(c < o for o, c in zip(opens, closes)):
            if closes[0] > closes[1] > closes[2] and all(b > 0 for b in bodies):
                avg_body = np.mean(bodies)
                if all(b > avg_body * 0.5 for b in bodies):
                    results.append(PatternSignal(
                        name="three_black_crows", name_cn="三只乌鸦",
                        direction="bearish", pattern_type="candlestick",
                        completeness=90, score=75,
                        description="Three black crows — bearish continuation"
                    ))

        return results

    # ============================
    # Chart Formations
    # ============================

    def _detect_double_bottom_top(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect W-bottom and M-top formations."""
        results = []
        low = df["low"].values
        high = df["high"].values
        close = df["close"].values

        # Look for double bottom in last 20 bars
        window = min(len(df), 40)
        recent_low = low[-window:]
        recent_high = high[-window:]

        # Find two lowest points
        lows_idx = []
        for i in range(2, len(recent_low) - 2):
            if recent_low[i] <= recent_low[i - 1] and recent_low[i] <= recent_low[i - 2] and \
               recent_low[i] <= recent_low[i + 1] and recent_low[i] <= recent_low[i + 2]:
                lows_idx.append((i, recent_low[i]))

        if len(lows_idx) >= 2:
            # Check if two lows are within 3% of each other
            l1_idx, l1_val = lows_idx[-2]
            l2_idx, l2_val = lows_idx[-1]
            if abs(l1_val - l2_val) / l1_val < 0.03 and l2_idx - l1_idx >= 5:
                # Neckline = highest point between the two lows
                neckline = float(np.max(recent_high[l1_idx:l2_idx + 1]))
                current = float(close[-1])
                if current > neckline:
                    results.append(PatternSignal(
                        name="double_bottom_breakout", name_cn="双底突破",
                        direction="bullish", pattern_type="chart_formation",
                        completeness=95, score=85,
                        description=f"W-bottom breakout above neckline ${neckline:.2f}"
                    ))
                elif current > (l1_val + l2_val) / 2:
                    results.append(PatternSignal(
                        name="double_bottom_forming", name_cn="双底形成中",
                        direction="bullish", pattern_type="chart_formation",
                        completeness=70, score=60,
                        description=f"W-bottom forming, neckline at ${neckline:.2f}"
                    ))

        # Find two highest points for double top
        highs_idx = []
        for i in range(2, len(recent_high) - 2):
            if recent_high[i] >= recent_high[i - 1] and recent_high[i] >= recent_high[i - 2] and \
               recent_high[i] >= recent_high[i + 1] and recent_high[i] >= recent_high[i + 2]:
                highs_idx.append((i, recent_high[i]))

        if len(highs_idx) >= 2:
            h1_idx, h1_val = highs_idx[-2]
            h2_idx, h2_val = highs_idx[-1]
            if abs(h1_val - h2_val) / h1_val < 0.03 and h2_idx - h1_idx >= 5:
                neckline = float(np.min(recent_low[h1_idx:h2_idx + 1]))
                current = float(close[-1])
                if current < neckline:
                    results.append(PatternSignal(
                        name="double_top_breakdown", name_cn="双顶跌破",
                        direction="bearish", pattern_type="chart_formation",
                        completeness=95, score=85,
                        description=f"M-top breakdown below neckline ${neckline:.2f}"
                    ))
                elif current < (h1_val + h2_val) / 2:
                    results.append(PatternSignal(
                        name="double_top_forming", name_cn="双顶形成中",
                        direction="bearish", pattern_type="chart_formation",
                        completeness=70, score=60,
                        description=f"M-top forming, neckline at ${neckline:.2f}"
                    ))

        return results

    def _detect_triangle(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect ascending/descending/symmetrical triangle patterns."""
        results = []
        window = min(len(df), 30)
        recent = df.tail(window)
        highs = recent["high"].values
        lows = recent["low"].values
        close_val = float(recent.iloc[-1]["close"])

        x = np.arange(window)
        if window < 10:
            return results

        # Fit trendlines to highs and lows
        high_slope, high_intercept = np.polyfit(x, highs, 1)
        low_slope, low_intercept = np.polyfit(x, lows, 1)

        # Ascending triangle: flat top, rising bottom
        if abs(high_slope) < np.std(highs) * 0.02 and low_slope > np.std(lows) * 0.01:
            resistance = float(np.mean(highs[-5:]))
            if close_val > resistance:
                results.append(PatternSignal(
                    name="ascending_triangle_breakout", name_cn="上升三角形突破",
                    direction="bullish", pattern_type="chart_formation",
                    completeness=90, score=80,
                    description=f"Ascending triangle breakout above ${resistance:.2f}"
                ))
            else:
                results.append(PatternSignal(
                    name="ascending_triangle", name_cn="上升三角形",
                    direction="bullish", pattern_type="chart_formation",
                    completeness=75, score=60,
                    description=f"Ascending triangle, resistance at ${resistance:.2f}"
                ))

        # Descending triangle: flat bottom, falling top
        if abs(low_slope) < np.std(lows) * 0.02 and high_slope < -np.std(highs) * 0.01:
            support = float(np.mean(lows[-5:]))
            if close_val < support:
                results.append(PatternSignal(
                    name="descending_triangle_breakdown", name_cn="下降三角形跌破",
                    direction="bearish", pattern_type="chart_formation",
                    completeness=90, score=80,
                    description=f"Descending triangle breakdown below ${support:.2f}"
                ))
            else:
                results.append(PatternSignal(
                    name="descending_triangle", name_cn="下降三角形",
                    direction="bearish", pattern_type="chart_formation",
                    completeness=75, score=60,
                    description=f"Descending triangle, support at ${support:.2f}"
                ))

        return results

    def _detect_cup_handle(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect cup-and-handle pattern."""
        results = []
        window = min(len(df), 40)
        recent = df.tail(window)
        close = recent["close"].values

        if len(close) < 20:
            return results

        # Find cup: U-shape in the first 2/3 of the window
        cup_end = int(len(close) * 0.7)
        cup_data = close[:cup_end]

        if len(cup_data) < 15:
            return results

        cup_min_idx = np.argmin(cup_data)
        left_rim = float(cup_data[0])
        right_rim = float(cup_data[-1])
        cup_bottom = float(cup_data[cup_min_idx])

        # Cup should be U-shaped: min in middle, rims roughly equal
        if (cup_min_idx > len(cup_data) * 0.2 and cup_min_idx < len(cup_data) * 0.8 and
                abs(left_rim - right_rim) / left_rim < 0.05 and
                (left_rim - cup_bottom) / left_rim > 0.05):

            # Handle: slight decline in the last portion
            handle_data = close[cup_end:]
            if len(handle_data) >= 3:
                handle_low = float(np.min(handle_data))
                current = float(close[-1])

                # Handle shouldn't retrace more than 50% of the cup depth
                cup_depth = left_rim - cup_bottom
                handle_retrace = right_rim - handle_low
                if handle_retrace < cup_depth * 0.5:
                    if current > right_rim:
                        results.append(PatternSignal(
                            name="cup_handle_breakout", name_cn="杯柄突破",
                            direction="bullish", pattern_type="chart_formation",
                            completeness=90, score=85,
                            description=f"Cup & handle breakout above rim ${right_rim:.2f}"
                        ))
                    else:
                        results.append(PatternSignal(
                            name="cup_handle_forming", name_cn="杯柄形成中",
                            direction="bullish", pattern_type="chart_formation",
                            completeness=70, score=65,
                            description=f"Cup & handle forming, breakout level ${right_rim:.2f}"
                        ))

        return results

    def _detect_flag(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect bull/bear flag patterns."""
        results = []
        if len(df) < 15:
            return results

        close = df["close"].values
        volume = df["volume"].values

        # Bull flag: strong uptrend (pole) followed by slight downtrend (flag)
        pole_end = len(close) - 8
        pole_start = max(0, pole_end - 7)
        pole_data = close[pole_start:pole_end]
        flag_data = close[pole_end:]

        if len(pole_data) < 3 or len(flag_data) < 3:
            return results

        pole_return = (pole_data[-1] - pole_data[0]) / pole_data[0]
        flag_return = (flag_data[-1] - flag_data[0]) / flag_data[0]

        # Bull flag: pole up >5%, flag down <-1% and >-5%
        if pole_return > 0.05 and -0.05 < flag_return < -0.01:
            # Volume should decrease during flag
            pole_vol = float(np.mean(volume[pole_start:pole_end]))
            flag_vol = float(np.mean(volume[pole_end:]))
            if flag_vol < pole_vol * 0.8:
                results.append(PatternSignal(
                    name="bull_flag", name_cn="牛旗",
                    direction="bullish", pattern_type="chart_formation",
                    completeness=80, score=70,
                    description="Bull flag — consolidation after strong rally"
                ))

        # Bear flag
        if pole_return < -0.05 and 0.01 < flag_return < 0.05:
            pole_vol = float(np.mean(volume[pole_start:pole_end]))
            flag_vol = float(np.mean(volume[pole_end:]))
            if flag_vol < pole_vol * 0.8:
                results.append(PatternSignal(
                    name="bear_flag", name_cn="熊旗",
                    direction="bearish", pattern_type="chart_formation",
                    completeness=80, score=70,
                    description="Bear flag — consolidation after sharp decline"
                ))

        return results

    def _detect_box_breakout(self, df: pd.DataFrame) -> List[PatternSignal]:
        """Detect trading range (box) and breakout."""
        results = []
        window = min(len(df), 20)
        recent = df.tail(window)
        highs = recent["high"].values
        lows = recent["low"].values
        close_val = float(recent.iloc[-1]["close"])

        box_high = float(np.max(highs[:-1]))
        box_low = float(np.min(lows[:-1]))
        box_range = box_high - box_low

        if box_range == 0 or box_range / box_low > 0.15:
            return results  # Range too wide to be a box

        # Check if price stayed within range for most of the period
        in_range = sum(1 for i in range(len(highs) - 1) if lows[i] >= box_low * 0.99 and highs[i] <= box_high * 1.01)
        if in_range < window * 0.6:
            return results

        if close_val > box_high:
            results.append(PatternSignal(
                name="box_breakout_up", name_cn="箱体向上突破",
                direction="bullish", pattern_type="chart_formation",
                completeness=85, score=75,
                description=f"Breakout above box range ${box_low:.2f}-${box_high:.2f}"
            ))
        elif close_val < box_low:
            results.append(PatternSignal(
                name="box_breakout_down", name_cn="箱体向下跌破",
                direction="bearish", pattern_type="chart_formation",
                completeness=85, score=75,
                description=f"Breakdown below box range ${box_low:.2f}-${box_high:.2f}"
            ))
        else:
            results.append(PatternSignal(
                name="box_range", name_cn="箱体震荡",
                direction="neutral", pattern_type="chart_formation",
                completeness=80, score=45,
                description=f"Trading in box range ${box_low:.2f}-${box_high:.2f}"
            ))

        return results
