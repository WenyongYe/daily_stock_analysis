# -*- coding: utf-8 -*-
"""Format options flow report."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Optional

from src.options_flow.config import get_top_n, get_min_volume, get_min_premium, get_min_volume_oi_ratio
from src.options_flow.llm import call_text_llm
from src.options_flow.parser import OptionFlowItem, volume_oi_ratio


def _fmt_num(value: Optional[float]) -> str:
    if value is None:
        return "-"
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value/1_000:.2f}K"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _fmt_volume_oi(item: OptionFlowItem) -> str:
    ratio = volume_oi_ratio(item)
    if ratio is None:
        return "-"
    return str(ratio)


def _is_unusual(item: OptionFlowItem) -> bool:
    min_volume = get_min_volume()
    min_premium = get_min_premium()
    min_ratio = get_min_volume_oi_ratio()
    if item.volume and item.volume >= min_volume:
        return True
    if item.premium and item.premium >= min_premium:
        return True
    ratio = volume_oi_ratio(item)
    if ratio and ratio >= min_ratio:
        return True
    return False


def build_symbol_stats(items: list[OptionFlowItem]) -> dict[str, dict]:
    stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "premium": 0.0, "volume": 0})
    for item in items:
        stat = stats[item.symbol]
        stat["count"] += 1
        if item.premium:
            stat["premium"] += item.premium
        if item.volume:
            stat["volume"] += item.volume
    return stats


def _rank_key(item: OptionFlowItem) -> tuple:
    return (
        item.premium or 0.0,
        item.volume or 0,
        volume_oi_ratio(item) or 0.0,
    )


def _select_items_for_summary(items: list[OptionFlowItem], max_items: int) -> list[OptionFlowItem]:
    rich = [
        i for i in items
        if i.expiry or i.strike or i.volume or i.open_interest
    ]
    if len(rich) < max_items:
        for item in items:
            if item in rich:
                continue
            rich.append(item)
            if len(rich) >= max_items:
                break
    rich_sorted = sorted(rich, key=_rank_key, reverse=True)
    return rich_sorted[:max_items]


def _build_llm_summary(
    session_date: str,
    items: list[OptionFlowItem],
    news_summaries: dict[str, list[str]],
    warnings: list[str],
) -> str:
    top_n = get_top_n()
    selected = _select_items_for_summary(items, top_n)
    payload = {
        "session_date": session_date,
        "warnings": warnings,
        "flows": [
            {
                "symbol": i.symbol,
                "type": i.option_type,
                "expiry": i.expiry,
                "strike": i.strike,
                "volume": i.volume,
                "open_interest": i.open_interest,
                "premium": i.premium,
                "volume_oi_ratio": volume_oi_ratio(i),
            }
            for i in selected
        ],
        "news_summaries": news_summaries,
    }

    system = (
        "你是美股期权异动分析师。请用 Gemini 3.0 简报模板输出 Markdown。"
        "模板要求：\n"
        "1) 标题：## 交易日 {date} 期权异动简报\n"
        "2) Top 异动表（不超过 {top_n} 条）：包含 symbol, call/put, expiry, strike, volume, OI, premium, V/OI\n"
        "3) 新闻关联性分析：每个标的 2-3 条要点，说明与异动的可能关联；无新闻写‘无明确关联’\n"
        "4) 最后给 2-3 句简短结论\n"
        "5) 不输出冗长明细列表，不超过 40 行。"
    ).format(date=session_date, top_n=top_n)

    user = json.dumps(payload, ensure_ascii=False)
    return call_text_llm(system=system, user=user, temperature=0.2, max_tokens=2000)


def format_report(
    session_date: str,
    items: list[OptionFlowItem],
    news_summaries: dict[str, list[str]] | None = None,
    warnings: list[str] | None = None,
) -> str:
    news_summaries = news_summaries or {}
    warnings = warnings or []

    if not items:
        return f"📌 美股期权异动简报 | 交易日 {session_date}\n------------------------------\n本交易日未解析到有效期权异动记录。"

    try:
        return _build_llm_summary(session_date, items, news_summaries, warnings)
    except Exception:
        lines: list[str] = []
        lines.append(f"📌 美股期权异动简报 | 交易日 {session_date}")
        lines.append("------------------------------")
        if warnings:
            lines.append("⚠️ 备注")
            for w in warnings:
                lines.append(f"- {w}")
            lines.append("")

        unusual_items = [i for i in items if _is_unusual(i)]
        lines.append(f"本次解析 {len(items)} 条记录，筛出异动 {len(unusual_items)} 条。")

        stats = build_symbol_stats(unusual_items or items)
        top_n = get_top_n()
        sorted_symbols = sorted(
            stats.items(),
            key=lambda kv: (kv[1]["premium"], kv[1]["volume"], kv[1]["count"]),
            reverse=True,
        )
        lines.append("\n## Top 异动标的")
        for symbol, stat in sorted_symbols[:top_n]:
            lines.append(
                f"- {symbol}: premium {_fmt_num(stat['premium'])}, volume {_fmt_num(stat['volume'])}, 次数 {stat['count']}"
            )

        if news_summaries:
            lines.append("\n## 新闻关联性分析")
            for symbol, _ in sorted_symbols[:top_n]:
                points = news_summaries.get(symbol)
                if not points:
                    lines.append(f"- {symbol}: 无明确关联")
                    continue
                lines.append(f"- {symbol}:")
                for p in points[:2]:
                    lines.append(f"  - {p}")

        return "\n".join(lines)
