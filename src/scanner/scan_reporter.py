# -*- coding: utf-8 -*-
"""
Scan Reporter — LLM-Powered Report Generation

Takes scored signals and generates human-readable trading reports
with price range + condition-based suggestions using the existing
GeminiAnalyzer (or fallback LLM).
"""

import logging
from datetime import datetime
from typing import List, Optional

from src.scanner.signal_scorer import ScoredSignal

logger = logging.getLogger(__name__)


# Prompt template for LLM report generation
PRE_MARKET_PROMPT = """You are an expert US stock trading analyst. Based on the following technical analysis data,
generate a concise pre-market trading watchlist report in Chinese.

For each stock, provide:
1. 一句话信号总结
2. 条件买入建议（给出具体价格区间和触发条件）
3. 目标价区间
4. 止损位
5. 风险提示

Format each stock like this:
📊 {SYMBOL} (${price}) | 综合评分: {score}/100
信号: {one-line signal summary}
📈 期权: {options summary if available}
✅ 条件买入: {entry conditions with price range}
🎯 目标: {target range with reasoning}
⛔ 止损: {stop-loss with reasoning}
⚠️ 风险: {key risks}

Analysis data:
{data}

Important rules:
- Give SPECIFIC price levels, not vague suggestions
- Explain WHY each level matters (e.g., "MA50 support", "high OI put strike", "前高阻力")
- If the setup is not actionable, say "暂不出手，等待更好时机"
- Use Chinese for the report content
- Be concise but precise
"""

POST_MARKET_PROMPT = """You are an expert US stock trading analyst. Based on today's market data,
generate a post-market review report in Chinese.

For each stock, provide:
1. 今日走势回顾（关键事件和量价变化）
2. 技术面变化（形态/信号变化）
3. 明日展望和操作建议

Format each stock like this:
📊 {SYMBOL} (${price}) | 综合评分: {score}/100
📋 今日: {today's action summary}
📈 期权: {options changes}
🔮 展望: {outlook and conditions for tomorrow}

Analysis data:
{data}

Important rules:
- Focus on what CHANGED today (breakout? breakdown? volume spike?)
- Provide forward-looking conditions for tomorrow
- Use Chinese for the report content
"""


class ScanReporter:
    """Generates LLM-powered trading reports from scored signals."""

    def __init__(self):
        self._analyzer = None

    def _get_analyzer(self):
        """Lazy-init the LLM analyzer."""
        if self._analyzer is None:
            from src.analyzer import GeminiAnalyzer
            self._analyzer = GeminiAnalyzer()
        return self._analyzer

    def generate_report(
        self,
        signals: List[ScoredSignal],
        mode: str = "pre_market",
        use_llm: bool = True,
    ) -> str:
        """
        Generate a trading report.

        Args:
            signals: Ranked ScoredSignal list.
            mode: "pre_market" or "post_market".
            use_llm: If True, use LLM to enhance the report. If False, use template only.

        Returns:
            Formatted report string (Markdown).
        """
        if not signals:
            return "📭 本次扫描未发现符合条件的交易机会。"

        # Build data summary for each signal
        data_blocks = []
        for s in signals:
            block = self._build_signal_data(s)
            data_blocks.append(block)

        data_text = "\n\n---\n\n".join(data_blocks)

        if use_llm:
            try:
                return self._generate_llm_report(data_text, signals, mode)
            except Exception as e:
                logger.warning(f"LLM report generation failed, falling back to template: {e}")
                return self._generate_template_report(signals, mode)
        else:
            return self._generate_template_report(signals, mode)

    def _build_signal_data(self, s: ScoredSignal) -> str:
        """Build a structured data block for one signal."""
        lines = [
            f"## {s.code} | Price: ${s.current_price:.2f} | Score: {s.composite_score:.0f}/100 | Direction: {s.direction}",
            f"Sub-scores: Trend={s.trend_score:.0f} VP={s.volume_price_score:.0f} Pattern={s.pattern_score:.0f} "
            f"Anomaly={s.anomaly_score:.0f} Options={s.options_score:.0f} Position={s.position_score:.0f}",
        ]

        # Volume-Price details
        if s.vp_signal:
            vp = s.vp_signal
            lines.append(f"Volume: {vp.volume_ratio_5d:.1f}x 5d avg | Context: {vp.volume_context}")
            lines.append(f"Volume trend (5d): {vp.volume_trend_5d}")
            if vp.breakout_signal:
                lines.append(f"Breakout: {vp.breakout_signal} at ${vp.breakout_level:.2f}")
            if vp.pullback_signal:
                lines.append(f"Pullback: {vp.pullback_signal} at ${vp.pullback_level:.2f}")
            lines.append(f"MA20=${vp.ma20:.2f} MA50=${vp.ma50:.2f} MA200=${vp.ma200:.2f}")
            if vp.support_levels:
                supports = ", ".join(f"${l.price:.2f}({l.source})" for l in vp.support_levels[:3])
                lines.append(f"Support: {supports}")
            if vp.resistance_levels:
                resistances = ", ".join(f"${l.price:.2f}({l.source})" for l in vp.resistance_levels[:3])
                lines.append(f"Resistance: {resistances}")
            if vp.is_volume_divergence:
                lines.append("⚠️ Volume-price divergence detected")

        # Patterns
        if s.patterns:
            pats = ", ".join(f"{p.name_cn}({p.direction},{p.score:.0f})" for p in s.patterns[:3])
            lines.append(f"Patterns: {pats}")

        # Anomalies
        if s.anomalies:
            for a in s.anomalies[:3]:
                lines.append(f"Anomaly: [{a.severity.value}] {a.description}")

        # Options
        if s.options:
            opt = s.options
            lines.append(f"PCR: {opt.pcr_volume:.2f} ({opt.pcr_signal})")
            lines.append(f"Max Pain: ${opt.max_pain:.0f} (distance: {opt.max_pain_distance_pct:+.1f}%)")
            lines.append(f"GEX: {opt.gex_direction} — {opt.gex_description}")
            if opt.high_oi_call_strikes:
                lines.append(f"Call walls: {', '.join(f'${x:.0f}' for x in opt.high_oi_call_strikes[:3])}")
            if opt.high_oi_put_strikes:
                lines.append(f"Put floors: {', '.join(f'${x:.0f}' for x in opt.high_oi_put_strikes[:3])}")
            if opt.has_unusual_activity:
                lines.append("🔥 Unusual options activity detected")

        # Reasons
        if s.signal_reasons:
            lines.append(f"Key signals: {'; '.join(s.signal_reasons[:5])}")

        return "\n".join(lines)

    def _generate_llm_report(self, data_text: str, signals: List[ScoredSignal], mode: str) -> str:
        """Generate report using LLM."""
        analyzer = self._get_analyzer()

        prompt_template = PRE_MARKET_PROMPT if mode == "pre_market" else POST_MARKET_PROMPT
        prompt = prompt_template.replace("{data}", data_text)

        # Use the analyzer's internal API call method
        generation_config = {"temperature": 0.7, "max_output_tokens": 8192}
        result = analyzer._call_api_with_retry(prompt, generation_config)

        if result:
            # Add header
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            title = "🇺🇸 美股盘前扫描报告" if mode == "pre_market" else "🇺🇸 美股盘后复盘报告"
            header = f"# {title}\n⏰ {now} | 共 {len(signals)} 只标的\n\n---\n\n"
            return header + result

        raise RuntimeError("LLM returned empty result")

    def _generate_template_report(self, signals: List[ScoredSignal], mode: str) -> str:
        """Generate report using template (fallback when LLM unavailable)."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = "🇺🇸 美股盘前扫描报告" if mode == "pre_market" else "🇺🇸 美股盘后复盘报告"
        lines = [f"# {title}", f"⏰ {now} | 共 {len(signals)} 只标的\n"]

        for s in signals:
            lines.append(f"---\n")
            lines.append(f"### #{s.rank} {s.code} (${s.current_price:.2f}) | 评分: {s.composite_score:.0f}/100 | {s.direction}")
            lines.append(f"趋势={s.trend_score:.0f} 量价={s.volume_price_score:.0f} 形态={s.pattern_score:.0f} "
                         f"异动={s.anomaly_score:.0f} 期权={s.options_score:.0f} 位置={s.position_score:.0f}")

            if s.top_patterns:
                lines.append(f"**形态**: {', '.join(s.top_patterns)}")
            if s.top_anomalies:
                lines.append(f"**异动**: {'; '.join(s.top_anomalies[:2])}")

            # Key levels
            if s.nearest_support > 0:
                lines.append(f"**支撑**: ${s.nearest_support:.2f}")
            if s.nearest_resistance > 0:
                lines.append(f"**阻力**: ${s.nearest_resistance:.2f}")
            if s.max_pain > 0:
                lines.append(f"**Max Pain**: ${s.max_pain:.0f}")

            # Options
            if s.options and s.options.pcr_signal:
                lines.append(f"**期权**: PCR {s.options.pcr_volume:.2f} ({s.options.pcr_signal}), "
                             f"GEX {s.options.gex_direction}")

            if s.signal_reasons:
                lines.append(f"**信号**: {'; '.join(s.signal_reasons[:3])}")

            lines.append("")

        return "\n".join(lines)
