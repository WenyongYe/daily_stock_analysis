# -*- coding: utf-8 -*-
"""
LLM 市场综合叙事生成器
1. 生成 2-3 句核心叙事（行情+新闻关联）
2. 为价格异动和宏观事件生成 AI 简短解读
"""

import json
import os
import re
import sys

import requests


_NARRATIVE_PROMPT = (
    "你是资深金融市场分析师。请根据以下今日市场数据和新闻摘要，用 2-3 句简洁中文"
    "总结今日市场全貌，重点将行情异动与新闻事件关联解读。\n\n"
    "要求：\n"
    "- 只写 2-3 句话，不要用列表或分点\n"
    "- 必须关联行情数据和新闻事件（如\"受XX事件影响，油价大涨X%\"）\n"
    "- 点明核心驱动因素和市场情绪\n"
    "- 不要说\"今日\"开头，直接描述\n\n"
)


def _summarize_prices(prices: dict) -> str:
    """将价格数据压缩为摘要文本"""
    lines = []
    key_assets = [
        ("sp500", "S&P 500"), ("nasdaq", "NASDAQ"), ("dji", "道琼斯"),
        ("vix", "VIX"), ("gold", "黄金"), ("brent", "布伦特原油"),
        ("dxy", "美元指数"), ("us10y", "10Y美债"), ("btc", "BTC"),
    ]
    for key, label in key_assets:
        d = prices.get(key, {})
        if d and "error" not in d:
            chg = d.get("chg", 0)
            price = d.get("price", 0)
            lines.append(f"{label}: {price:,.2f} ({chg:+.2f}%)")
    return " | ".join(lines)


def generate_narrative(
    prices: dict,
    news_summary,
    theme_label: str,
    theme_themes: list[str],
) -> str | None:
    """
    调用 LLM 生成市场综合叙事

    Args:
        prices: 行情数据
        news_summary: 新闻摘要（str 或 list）
        theme_label: 主题判断标签
        theme_themes: 主题列表

    Returns:
        str: 2-3 句综合叙事，失败返回 None
    """
    api_key = os.getenv("AIHUBMIX_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        return None

    price_summary = _summarize_prices(prices)
    news_text = news_summary if isinstance(news_summary, str) else "\n".join(news_summary[:10]) if news_summary else "无新闻数据"
    themes_text = "、".join(theme_themes) if theme_themes else "无显著异动"

    prompt = (
        _NARRATIVE_PROMPT
        + f"## 市场判断\n{theme_label}：{themes_text}\n\n"
        + f"## 行情数据\n{price_summary}\n\n"
        + f"## 新闻摘要\n{news_text}\n"
    )

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 300,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content:
                print(f"  [Narrative] LLM 叙事生成完成（{len(content)} 字符）",
                      file=sys.stderr)
                return content
        else:
            print(f"  [Narrative] LLM API 返回 {resp.status_code}",
                  file=sys.stderr)
    except Exception as e:
        print(f"  [Narrative] LLM 调用失败: {e}", file=sys.stderr)

    return None


# ─── AI 数据点注释 ─────────────────────────────────────────

_ANNOTATION_PROMPT = (
    "你是资深金融分析师。请为以下数据点各写一句简短中文解读（8-15字），说明其市场含义。\n\n"
    "规则：\n"
    "- 价格异动：解释驱动因素（如\"中东局势推升油价\"\"避险资金涌入\"）\n"
    "- 宏观数据：说明实际值vs预期的经济含义，注意指标方向性：\n"
    "  - CPI/通胀类：高于预期=通胀升温（鹰派信号），低于预期=通胀降温（鸽派信号）\n"
    "  - 就业/消费/GDP类：高于预期=经济强劲，低于预期=经济放缓\n"
    "  - 失业率/初请类：高于预期=就业恶化，低于预期=就业强劲\n"
    "- 央行发言类事件：简述可能的政策倾向\n"
    "- 每条解读不超过15个字\n\n"
    "严格按 JSON 格式返回，key 为数据点编号，value 为解读文本：\n"
    '{"1": "中东冲突推升油价", "2": "通胀降温，利好降息预期"}\n\n'
    "数据点列表：\n"
)


def _collect_annotation_items(prices: dict, calendar: list[dict]) -> list[dict]:
    """收集需要注释的数据点"""
    items = []

    # 价格异动（涨跌幅超过阈值的资产）
    thresholds = {
        "gold": 1.0, "silver": 2.0, "brent": 1.5, "crude": 1.5,
        "copper": 1.5, "natgas": 2.0,
        "sp500": 0.8, "nasdaq": 1.0, "dji": 0.8, "russell": 1.5,
        "vix": 3.0,
        "btc": 3.0, "eth": 3.0,
        "dxy": 0.3, "us10y": 0.5,
        "eurusd": 0.3, "usdjpy": 0.5,
    }
    labels = {
        "gold": "黄金", "silver": "白银", "brent": "布伦特原油", "crude": "WTI原油",
        "copper": "铜", "natgas": "天然气",
        "sp500": "S&P 500", "nasdaq": "NASDAQ", "dji": "道琼斯", "russell": "Russell 2000",
        "vix": "VIX恐慌指数",
        "btc": "BTC", "eth": "ETH",
        "dxy": "美元指数", "us10y": "10Y美债收益率",
        "eurusd": "EUR/USD", "usdjpy": "USD/JPY",
    }
    for key, threshold in thresholds.items():
        d = prices.get(key, {})
        if not d or "error" in d:
            continue
        chg = d.get("chg", 0)
        price = d.get("price", 0)
        if abs(chg) >= threshold:
            label = labels.get(key, key)
            items.append({
                "type": "price",
                "key": key,
                "text": f"{label}: {price:,.2f} ({chg:+.2f}%)",
            })

    # 宏观事件（有actual数据的）
    for e in (calendar or []):
        actual = e.get("actual", "").strip()
        if not actual or actual == "****":
            continue
        forecast = e.get("forecast", "").strip()
        event = e.get("event", "")
        cur = e.get("currency", "")
        text = f"[{cur}] {event}: 实际 {actual}"
        if forecast:
            text += f" vs 预期 {forecast}"
        items.append({
            "type": "calendar",
            "key": f"{cur}_{event}",
            "text": text,
        })

    return items


def generate_annotations(
    prices: dict,
    calendar: list[dict],
    news_summary=None,
) -> dict[str, str]:
    """
    调用 LLM 为价格异动和宏观事件生成简短解读

    Returns:
        dict: {key: "解读文本"} — key 是资产 key 或 "货币_事件名"
    """
    items = _collect_annotation_items(prices, calendar)
    if not items:
        return {}

    api_key = os.getenv("AIHUBMIX_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        return {}

    # 构建 prompt
    prompt = _ANNOTATION_PROMPT
    if news_summary:
        news_text = news_summary if isinstance(news_summary, str) else "\n".join(news_summary[:5])
        prompt += f"\n参考今日新闻（用于关联解读）：\n{news_text}\n\n"
    for i, item in enumerate(items, 1):
        prompt += f"{i}. {item['text']}\n"

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # 提取 JSON
            json_match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                # 映射回原始 key
                result = {}
                for i, item in enumerate(items, 1):
                    ann = parsed.get(str(i), "")
                    if ann:
                        result[item["key"]] = ann
                print(f"  [Annotations] LLM 生成 {len(result)} 条注释",
                      file=sys.stderr)
                return result
        else:
            print(f"  [Annotations] LLM API 返回 {resp.status_code}",
                  file=sys.stderr)
    except Exception as e:
        print(f"  [Annotations] LLM 调用失败: {e}", file=sys.stderr)

    return {}
