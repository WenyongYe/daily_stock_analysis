# -*- coding: utf-8 -*-
"""News enrichment for options flow."""

from __future__ import annotations

import json
import logging
from typing import Any

from src.config import get_config
from src.search_service import SearchService, SearchResponse
from src.options_flow.config import get_news_max_age_days
from src.options_flow.llm import call_text_llm

logger = logging.getLogger(__name__)


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if "```" in cleaned:
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def build_search_service() -> SearchService:
    cfg = get_config()
    return SearchService(
        bocha_keys=cfg.bocha_api_keys,
        tavily_keys=cfg.tavily_api_keys,
        brave_keys=cfg.brave_api_keys,
        serpapi_keys=cfg.serpapi_keys,
        news_max_age_days=get_news_max_age_days(),
    )


def fetch_news_context(tickers: list[str], max_results: int = 3) -> dict[str, SearchResponse]:
    service = build_search_service()
    results: dict[str, SearchResponse] = {}
    if not service.is_available:
        return results

    for ticker in tickers:
        query = f"{ticker} unusual options activity"
        resp = service.search_stock_news(
            stock_code=ticker,
            stock_name=ticker,
            max_results=max_results,
            focus_keywords=[query],
        )
        results[ticker] = resp
    return results


def summarize_drivers(news_results: dict[str, SearchResponse]) -> dict[str, list[str]]:
    if not news_results:
        return {}

    context_lines = []
    for ticker, resp in news_results.items():
        context_lines.append(resp.to_context(max_results=3))

    system = (
        "你是美股期权异动分析师。"
        "请根据搜索结果总结每个标的可能的异动驱动，"
        "每个标的输出 2-3 条要点。"
        "输出严格 JSON：{\"TICKER\": [\"要点1\", \"要点2\"]}，不要额外文本。"
    )
    user = "\n\n".join(context_lines)

    try:
        text = call_text_llm(system=system, user=user, temperature=0.2, max_tokens=2000)
        data = _parse_json(text)
        if data:
            return {
                k.upper(): [str(i).strip() for i in v if str(i).strip()]
                for k, v in data.items()
                if isinstance(v, list)
            }
    except Exception as exc:
        logger.warning("LLM 异动原因摘要失败: %s", exc)

    return {}
