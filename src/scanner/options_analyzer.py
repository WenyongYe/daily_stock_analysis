# -*- coding: utf-8 -*-
"""
Options Analyzer

Analyzes options chain data for trading signals:
- Put/Call Ratio (PCR) for sentiment
- Unusual options activity detection
- Max Pain calculation
- Simplified Gamma Exposure (GEX) direction
- High-OI strike levels as support/resistance
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OptionsSignal:
    """Options analysis result for a stock."""
    code: str
    current_price: float = 0.0

    # Put/Call Ratio
    pcr_volume: float = 0.0  # Volume-based PCR
    pcr_oi: float = 0.0  # Open Interest-based PCR
    pcr_signal: str = ""  # "bullish", "bearish", "neutral", "extreme_bullish", "extreme_bearish"

    # Unusual activity
    has_unusual_activity: bool = False
    unusual_calls: List[Dict] = field(default_factory=list)  # [{strike, volume, oi, ratio}]
    unusual_puts: List[Dict] = field(default_factory=list)

    # Max Pain
    max_pain: float = 0.0
    max_pain_expiry: str = ""
    max_pain_distance_pct: float = 0.0  # % distance from current price

    # GEX direction (simplified)
    gex_direction: str = ""  # "positive" (vol compression) | "negative" (vol expansion)
    gex_description: str = ""

    # Key strike levels
    high_oi_call_strikes: List[float] = field(default_factory=list)  # Resistance from options
    high_oi_put_strikes: List[float] = field(default_factory=list)  # Support from options

    # Overall
    options_score: float = 0.0  # 0-100
    signal_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "current_price": self.current_price,
            "pcr_volume": round(self.pcr_volume, 2),
            "pcr_oi": round(self.pcr_oi, 2),
            "pcr_signal": self.pcr_signal,
            "has_unusual_activity": self.has_unusual_activity,
            "unusual_calls_count": len(self.unusual_calls),
            "unusual_puts_count": len(self.unusual_puts),
            "max_pain": self.max_pain,
            "max_pain_expiry": self.max_pain_expiry,
            "max_pain_distance_pct": round(self.max_pain_distance_pct, 2),
            "gex_direction": self.gex_direction,
            "gex_description": self.gex_description,
            "high_oi_call_strikes": self.high_oi_call_strikes[:3],
            "high_oi_put_strikes": self.high_oi_put_strikes[:3],
            "options_score": round(self.options_score, 1),
            "signal_reasons": self.signal_reasons,
        }


class OptionsAnalyzer:
    """
    Analyzes options chain data using yfinance.

    Note: yfinance options data is delayed, suitable for pre-market/post-market
    analysis, not real-time trading decisions.
    """

    # PCR thresholds
    PCR_EXTREME_BEARISH = 1.5  # Very high puts = extreme fear
    PCR_BEARISH = 1.0
    PCR_NEUTRAL_HIGH = 0.8
    PCR_NEUTRAL_LOW = 0.5
    PCR_BULLISH = 0.3  # Very low puts = complacency

    # Unusual activity: volume > N * open interest
    UNUSUAL_VOL_OI_RATIO = 3.0

    def analyze(self, code: str, current_price: float = 0.0) -> OptionsSignal:
        """
        Analyze options for a stock symbol.

        Args:
            code: Stock symbol (e.g. "NVDA")
            current_price: Current stock price for reference
        """
        signal = OptionsSignal(code=code, current_price=current_price)

        try:
            import yfinance as yf
            ticker = yf.Ticker(code)

            # Get available expiry dates
            expiries = ticker.options
            if not expiries:
                logger.debug(f"{code}: no options data available")
                return signal

            # Use nearest expiry for short-term analysis
            nearest_expiry = expiries[0]
            signal.max_pain_expiry = nearest_expiry

            chain = ticker.option_chain(nearest_expiry)
            calls = chain.calls
            puts = chain.puts

            if calls.empty and puts.empty:
                return signal

            # Get current price if not provided
            if current_price <= 0:
                info = ticker.fast_info
                current_price = float(getattr(info, 'last_price', 0) or 0)
                if current_price <= 0:
                    current_price = float(calls.iloc[0]["lastPrice"]) if not calls.empty else 0
                signal.current_price = current_price

            # 1. Put/Call Ratio
            self._calc_pcr(calls, puts, signal)

            # 2. Unusual activity
            self._detect_unusual_activity(calls, puts, signal)

            # 3. Max Pain
            self._calc_max_pain(calls, puts, signal, current_price)

            # 4. GEX direction (simplified)
            self._estimate_gex(calls, puts, signal, current_price)

            # 5. High-OI strike levels
            self._find_high_oi_strikes(calls, puts, signal, current_price)

            # Also check next expiry for larger OI (if available)
            if len(expiries) >= 2:
                try:
                    chain2 = ticker.option_chain(expiries[1])
                    self._find_high_oi_strikes(chain2.calls, chain2.puts, signal, current_price)
                except Exception:
                    pass

            # Score
            self._score_signal(signal)

        except ImportError:
            logger.warning("yfinance not installed, options analysis unavailable")
        except Exception as e:
            logger.warning(f"{code}: options analysis failed: {e}")

        return signal

    def _calc_pcr(self, calls, puts, signal: OptionsSignal):
        """Calculate Put/Call ratio."""
        total_call_vol = calls["volume"].sum() if "volume" in calls.columns else 0
        total_put_vol = puts["volume"].sum() if "volume" in puts.columns else 0
        total_call_oi = calls["openInterest"].sum() if "openInterest" in calls.columns else 0
        total_put_oi = puts["openInterest"].sum() if "openInterest" in puts.columns else 0

        if total_call_vol > 0:
            signal.pcr_volume = float(total_put_vol / total_call_vol)
        if total_call_oi > 0:
            signal.pcr_oi = float(total_put_oi / total_call_oi)

        pcr = signal.pcr_volume if signal.pcr_volume > 0 else signal.pcr_oi

        if pcr >= self.PCR_EXTREME_BEARISH:
            signal.pcr_signal = "extreme_bearish"
            signal.signal_reasons.append(f"PCR {pcr:.2f} — extreme fear, possible contrarian bullish")
        elif pcr >= self.PCR_BEARISH:
            signal.pcr_signal = "bearish"
            signal.signal_reasons.append(f"PCR {pcr:.2f} — elevated put buying, bearish sentiment")
        elif pcr >= self.PCR_NEUTRAL_LOW:
            signal.pcr_signal = "neutral"
        elif pcr >= self.PCR_BULLISH:
            signal.pcr_signal = "bullish"
            signal.signal_reasons.append(f"PCR {pcr:.2f} — low put activity, bullish sentiment")
        elif pcr > 0:
            signal.pcr_signal = "extreme_bullish"
            signal.signal_reasons.append(f"PCR {pcr:.2f} — extreme complacency, possible contrarian bearish")

    def _detect_unusual_activity(self, calls, puts, signal: OptionsSignal):
        """Find strikes with unusually high volume relative to OI."""
        for _, row in calls.iterrows():
            vol = float(row.get("volume", 0) or 0)
            oi = float(row.get("openInterest", 0) or 0)
            if oi > 0 and vol / oi >= self.UNUSUAL_VOL_OI_RATIO and vol >= 100:
                signal.unusual_calls.append({
                    "strike": float(row["strike"]),
                    "volume": int(vol),
                    "oi": int(oi),
                    "ratio": round(vol / oi, 1),
                })

        for _, row in puts.iterrows():
            vol = float(row.get("volume", 0) or 0)
            oi = float(row.get("openInterest", 0) or 0)
            if oi > 0 and vol / oi >= self.UNUSUAL_VOL_OI_RATIO and vol >= 100:
                signal.unusual_puts.append({
                    "strike": float(row["strike"]),
                    "volume": int(vol),
                    "oi": int(oi),
                    "ratio": round(vol / oi, 1),
                })

        signal.unusual_calls.sort(key=lambda x: x["volume"], reverse=True)
        signal.unusual_puts.sort(key=lambda x: x["volume"], reverse=True)
        signal.unusual_calls = signal.unusual_calls[:5]
        signal.unusual_puts = signal.unusual_puts[:5]

        if signal.unusual_calls or signal.unusual_puts:
            signal.has_unusual_activity = True
            if signal.unusual_calls:
                top = signal.unusual_calls[0]
                signal.signal_reasons.append(
                    f"Unusual call activity: ${top['strike']:.0f} strike, {top['volume']} vol ({top['ratio']}x OI)"
                )
            if signal.unusual_puts:
                top = signal.unusual_puts[0]
                signal.signal_reasons.append(
                    f"Unusual put activity: ${top['strike']:.0f} strike, {top['volume']} vol ({top['ratio']}x OI)"
                )

    def _calc_max_pain(self, calls, puts, signal: OptionsSignal, current_price: float):
        """
        Calculate max pain — the strike where total options value is minimized.
        At this price, the maximum number of options expire worthless.
        """
        all_strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))
        if not all_strikes:
            return

        min_pain = float("inf")
        max_pain_strike = 0.0

        for strike in all_strikes:
            total_pain = 0.0
            # Pain from calls (call buyers lose when price < strike)
            for _, row in calls.iterrows():
                oi = float(row.get("openInterest", 0) or 0)
                if strike > row["strike"]:
                    total_pain += (strike - row["strike"]) * oi
            # Pain from puts (put buyers lose when price > strike)
            for _, row in puts.iterrows():
                oi = float(row.get("openInterest", 0) or 0)
                if strike < row["strike"]:
                    total_pain += (row["strike"] - strike) * oi

            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = strike

        signal.max_pain = float(max_pain_strike)
        if current_price > 0:
            signal.max_pain_distance_pct = (current_price - max_pain_strike) / current_price * 100
            if abs(signal.max_pain_distance_pct) > 3:
                direction = "above" if signal.max_pain_distance_pct > 0 else "below"
                signal.signal_reasons.append(
                    f"Max Pain ${max_pain_strike:.0f} — price {abs(signal.max_pain_distance_pct):.1f}% {direction}, "
                    f"may gravitate toward max pain near expiry"
                )

    def _estimate_gex(self, calls, puts, signal: OptionsSignal, current_price: float):
        """
        Simplified Gamma Exposure estimation.
        Positive GEX = market makers sell high/buy low → volatility compression.
        Negative GEX = market makers chase → volatility expansion.
        """
        if current_price <= 0:
            return

        net_gamma = 0.0
        for _, row in calls.iterrows():
            oi = float(row.get("openInterest", 0) or 0)
            strike = float(row["strike"])
            # Simplified: gamma peaks ATM, decays with distance
            distance = abs(strike - current_price) / current_price
            gamma_proxy = oi * max(0, 1 - distance * 5)
            net_gamma += gamma_proxy  # Calls: MM short calls → positive gamma effect

        for _, row in puts.iterrows():
            oi = float(row.get("openInterest", 0) or 0)
            strike = float(row["strike"])
            distance = abs(strike - current_price) / current_price
            gamma_proxy = oi * max(0, 1 - distance * 5)
            net_gamma -= gamma_proxy  # Puts: MM short puts → negative gamma effect

        if net_gamma > 0:
            signal.gex_direction = "positive"
            signal.gex_description = "Positive GEX — market makers dampen volatility (sell rallies, buy dips)"
        elif net_gamma < 0:
            signal.gex_direction = "negative"
            signal.gex_description = "Negative GEX — market makers amplify moves (chase momentum)"
        else:
            signal.gex_direction = "neutral"
            signal.gex_description = "Neutral GEX"

    def _find_high_oi_strikes(self, calls, puts, signal: OptionsSignal, current_price: float):
        """Find strikes with highest OI as potential S/R levels."""
        if current_price <= 0:
            return

        # Top call OI strikes above current price = resistance
        if not calls.empty and "openInterest" in calls.columns:
            above = calls[calls["strike"] > current_price].nlargest(5, "openInterest")
            for _, row in above.iterrows():
                strike = float(row["strike"])
                if strike not in signal.high_oi_call_strikes:
                    signal.high_oi_call_strikes.append(strike)

        # Top put OI strikes below current price = support
        if not puts.empty and "openInterest" in puts.columns:
            below = puts[puts["strike"] < current_price].nlargest(5, "openInterest")
            for _, row in below.iterrows():
                strike = float(row["strike"])
                if strike not in signal.high_oi_put_strikes:
                    signal.high_oi_put_strikes.append(strike)

        signal.high_oi_call_strikes = sorted(set(signal.high_oi_call_strikes))[:5]
        signal.high_oi_put_strikes = sorted(set(signal.high_oi_put_strikes), reverse=True)[:5]

    def _score_signal(self, signal: OptionsSignal):
        """Generate options signal score."""
        score = 50.0

        # PCR signal
        if signal.pcr_signal == "extreme_bearish":
            score += 10  # Contrarian bullish
        elif signal.pcr_signal == "bullish":
            score += 8
        elif signal.pcr_signal == "bearish":
            score -= 5
        elif signal.pcr_signal == "extreme_bullish":
            score -= 10  # Contrarian bearish (complacency)

        # Unusual activity
        if signal.has_unusual_activity:
            if signal.unusual_calls and not signal.unusual_puts:
                score += 12  # Bullish unusual calls
            elif signal.unusual_puts and not signal.unusual_calls:
                score -= 8  # Bearish unusual puts
            else:
                score += 5  # Mixed activity = attention

        # GEX
        if signal.gex_direction == "positive":
            score += 5  # Lower vol = better for planned entries
        elif signal.gex_direction == "negative":
            score -= 3  # Higher vol = riskier

        # Max Pain proximity (closer = more magnetic)
        if abs(signal.max_pain_distance_pct) < 2:
            score += 3  # Near max pain, likely to stay

        signal.options_score = max(0, min(100, score))
