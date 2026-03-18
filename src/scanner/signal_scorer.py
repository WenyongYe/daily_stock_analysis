# -*- coding: utf-8 -*-
"""
Multi-Factor Signal Scorer

Combines outputs from all analysis engines into a composite score (0-100)
and ranks stocks by trading opportunity quality.

Factor weights:
- Trend (15%): MA alignment, trend strength
- Volume-Price (25%): Volume-price engine signal strength
- Pattern (15%): Pattern completeness and quality
- Anomaly (15%): Anomaly severity and significance
- Options (15%): Options flow signals
- Position (15%): Distance to key S/R levels
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.scanner.volume_price_engine import VolumePriceSignal
from src.scanner.pattern_detector import PatternSignal
from src.scanner.anomaly_detector import AnomalyAlert
from src.scanner.options_analyzer import OptionsSignal

logger = logging.getLogger(__name__)


@dataclass
class ScoredSignal:
    """A scored and ranked trading signal."""
    code: str
    rank: int = 0
    composite_score: float = 0.0  # 0-100
    direction: str = ""  # "bullish", "bearish", "neutral"

    # Sub-scores (each 0-100)
    trend_score: float = 0.0
    volume_price_score: float = 0.0
    pattern_score: float = 0.0
    anomaly_score: float = 0.0
    options_score: float = 0.0
    position_score: float = 0.0

    # Key data references
    current_price: float = 0.0
    nearest_support: float = 0.0
    nearest_resistance: float = 0.0
    max_pain: float = 0.0

    # Top signals summary
    top_patterns: List[str] = field(default_factory=list)
    top_anomalies: List[str] = field(default_factory=list)
    signal_reasons: List[str] = field(default_factory=list)

    # Raw data for reporter
    vp_signal: Optional[VolumePriceSignal] = None
    patterns: List[PatternSignal] = field(default_factory=list)
    anomalies: List[AnomalyAlert] = field(default_factory=list)
    options: Optional[OptionsSignal] = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "rank": self.rank,
            "composite_score": round(self.composite_score, 1),
            "direction": self.direction,
            "trend_score": round(self.trend_score, 1),
            "volume_price_score": round(self.volume_price_score, 1),
            "pattern_score": round(self.pattern_score, 1),
            "anomaly_score": round(self.anomaly_score, 1),
            "options_score": round(self.options_score, 1),
            "position_score": round(self.position_score, 1),
            "current_price": self.current_price,
            "nearest_support": self.nearest_support,
            "nearest_resistance": self.nearest_resistance,
            "max_pain": self.max_pain,
            "top_patterns": self.top_patterns,
            "top_anomalies": self.top_anomalies,
            "signal_reasons": self.signal_reasons,
        }


# Factor weights
WEIGHTS = {
    "trend": 0.15,
    "volume_price": 0.25,
    "pattern": 0.15,
    "anomaly": 0.15,
    "options": 0.15,
    "position": 0.15,
}


class SignalScorer:
    """Scores and ranks stock signals from multiple analysis engines."""

    def __init__(self, min_score: int = 60, top_n: int = 10):
        self.min_score = min_score
        self.top_n = top_n

    def score(
        self,
        code: str,
        vp_signal: Optional[VolumePriceSignal] = None,
        patterns: Optional[List[PatternSignal]] = None,
        anomalies: Optional[List[AnomalyAlert]] = None,
        options: Optional[OptionsSignal] = None,
        trend_strength: float = 50.0,
    ) -> ScoredSignal:
        """Score a single stock based on all analysis results."""
        scored = ScoredSignal(code=code)
        patterns = patterns or []
        anomalies = anomalies or []

        # 1. Trend score
        scored.trend_score = max(0, min(100, trend_strength))

        # 2. Volume-Price score
        if vp_signal:
            scored.volume_price_score = vp_signal.signal_strength
            scored.current_price = vp_signal.current_price
            scored.nearest_support = vp_signal.nearest_support
            scored.nearest_resistance = vp_signal.nearest_resistance
            scored.signal_reasons.extend(vp_signal.signal_reasons)
            scored.vp_signal = vp_signal

        # 3. Pattern score (best pattern's score, boosted if multiple patterns agree)
        if patterns:
            best_pattern = max(patterns, key=lambda p: p.score)
            scored.pattern_score = best_pattern.score
            # Boost if multiple bullish or bearish patterns
            bullish_count = sum(1 for p in patterns if p.direction == "bullish" and p.score >= 60)
            bearish_count = sum(1 for p in patterns if p.direction == "bearish" and p.score >= 60)
            if bullish_count >= 2:
                scored.pattern_score = min(100, scored.pattern_score + 10)
            elif bearish_count >= 2:
                scored.pattern_score = min(100, scored.pattern_score + 10)
            scored.top_patterns = [f"{p.name_cn}({p.score:.0f})" for p in patterns[:3]]
            scored.patterns = patterns

        # 4. Anomaly score
        if anomalies:
            best_anomaly = max(anomalies, key=lambda a: a.score)
            scored.anomaly_score = best_anomaly.score
            # Boost if multiple significant anomalies
            sig_count = sum(1 for a in anomalies if a.score >= 60)
            if sig_count >= 2:
                scored.anomaly_score = min(100, scored.anomaly_score + 8)
            scored.top_anomalies = [a.description for a in anomalies[:3]]
            scored.anomalies = anomalies

        # 5. Options score
        if options:
            scored.options_score = options.options_score
            scored.max_pain = options.max_pain
            scored.signal_reasons.extend(options.signal_reasons)
            scored.options = options

        # 6. Position score — how favorable is the current price location?
        scored.position_score = self._calc_position_score(vp_signal, options)

        # Composite score
        scored.composite_score = (
            scored.trend_score * WEIGHTS["trend"] +
            scored.volume_price_score * WEIGHTS["volume_price"] +
            scored.pattern_score * WEIGHTS["pattern"] +
            scored.anomaly_score * WEIGHTS["anomaly"] +
            scored.options_score * WEIGHTS["options"] +
            scored.position_score * WEIGHTS["position"]
        )

        # Direction
        bullish_factors = 0
        bearish_factors = 0
        if vp_signal and vp_signal.signal_direction == "bullish":
            bullish_factors += 2
        elif vp_signal and vp_signal.signal_direction == "bearish":
            bearish_factors += 2
        for p in patterns:
            if p.direction == "bullish" and p.score >= 60:
                bullish_factors += 1
            elif p.direction == "bearish" and p.score >= 60:
                bearish_factors += 1
        for a in anomalies:
            if a.direction == "bullish" and a.score >= 60:
                bullish_factors += 1
            elif a.direction == "bearish" and a.score >= 60:
                bearish_factors += 1

        if bullish_factors > bearish_factors + 1:
            scored.direction = "bullish"
        elif bearish_factors > bullish_factors + 1:
            scored.direction = "bearish"
        else:
            scored.direction = "neutral"

        return scored

    def rank_signals(self, signals: List[ScoredSignal], mode: str = "pre_market") -> List[ScoredSignal]:
        """
        Rank and filter signals.

        Args:
            signals: List of scored signals.
            mode: "pre_market" (focus on actionable setups) or "post_market" (focus on notable moves).
        """
        # Filter by minimum score
        filtered = [s for s in signals if s.composite_score >= self.min_score]

        if mode == "pre_market":
            # Pre-market: prioritize bullish setups near support with good volume patterns
            filtered.sort(key=lambda s: (
                s.direction == "bullish",  # bullish first
                s.composite_score,
            ), reverse=True)
        else:
            # Post-market: prioritize biggest movers and anomalies
            filtered.sort(key=lambda s: (
                s.anomaly_score,
                s.composite_score,
            ), reverse=True)

        # Assign ranks and limit
        for i, s in enumerate(filtered[:self.top_n]):
            s.rank = i + 1

        return filtered[:self.top_n]

    def _calc_position_score(
        self, vp: Optional[VolumePriceSignal], options: Optional[OptionsSignal]
    ) -> float:
        """Score based on price position relative to key levels."""
        if not vp or vp.current_price <= 0:
            return 50.0

        score = 50.0
        price = vp.current_price

        # Near support = favorable for long entries
        if vp.nearest_support > 0:
            dist_to_support = (price - vp.nearest_support) / price
            if dist_to_support < 0.02:
                score += 20  # Very close to support
            elif dist_to_support < 0.05:
                score += 10

        # Near resistance = less favorable
        if vp.nearest_resistance > 0:
            dist_to_resistance = (vp.nearest_resistance - price) / price
            if dist_to_resistance < 0.01:
                score -= 10  # Right at resistance
            elif dist_to_resistance > 0.10:
                score += 5  # Lots of room to run

        # Options key levels
        if options and options.high_oi_put_strikes:
            nearest_put_support = options.high_oi_put_strikes[0]
            if abs(price - nearest_put_support) / price < 0.03:
                score += 10  # Options-defined support nearby

        return max(0, min(100, score))
