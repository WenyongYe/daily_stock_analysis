# -*- coding: utf-8 -*-
"""
深度新闻解读生成器
通过分层 LLM prompt（事实→因果→推演→关联）生成 3-5 个主题的深度市场解读报告
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests


# ─── 分层深度分析 Prompt ──────────────────────────────────────

_DEEP_ANALYSIS_PROMPT = """\
你是资深宏观策略分析师，为专业投资者撰写每日市场深度解读。

## 输入数据
你将收到：今日行情数据、精选新闻摘要、宏观指标（VIX/收益率曲线）、经济日历。

## 输出要求

请先输出 3-5 个最重要的市场主题，按影响力排序。每个主题严格按以下结构：

### [emoji] 主题标题（一句话概括）

**事件**：客观描述发生了什么（1-2句）

**驱动因素**：为什么发生，背景是什么（1-2句）

**市场影响**：
- 哪些资产受影响、方向、幅度
- 与行情数据是否吻合（交叉验证）

**前瞻推演**：
- 短期（1-2周）最可能的走向
- 关键变量：什么条件会改变判断
- 需关注的后续事件/数据

---


## 强制商品解读（必须单独输出）
在上述主题后，必须追加以下固定版块，不得省略：

### 🟡 黄金（Gold）
- 事件：
- 驱动因素：
- 市场影响（需交叉验证 DXY / US10Y / Gold 价格）：
- 定价状态（已定价/部分定价/未定价）：
- 前瞻推演（1-2周）：
- 可信度（高/中/低 + 原因）：

### ⚪ 白银（Silver）
- 事件：
- 驱动因素：
- 市场影响（需交叉验证 DXY / US10Y / Silver 价格）：
- 定价状态（已定价/部分定价/未定价）：
- 前瞻推演（1-2周）：
- 可信度（高/中/低 + 原因）：

### ⚫ 原油（Crude/Brent）
- 事件：
- 驱动因素：
- 市场影响（需交叉验证 DXY / US10Y / Oil 价格）：
- 定价状态（已定价/部分定价/未定价）：
- 前瞻推演（1-2周）：
- 可信度（高/中/低 + 原因）：

商品三段要求：每段保持 5-6 行、每行一句，避免冗长；尤其原油部分须更精炼。

输出完所有主题后，添加一段跨事件关联分析：

### 🔗 关联信号

分析多个主题之间的内在联系，归纳它们共同指向的宏观叙事。如果存在矛盾信号，明确指出。

## 分析规则
1. 必须用行情数据交叉验证新闻叙事（如新闻说利好但股市下跌，需指出矛盾并分析原因）
2. 区分"市场已定价"和"尚未定价"的信息
3. 明确标注不确定性，不做绝对判断
4. 使用中文，语言简练专业
5. 不要输出前言、总结段落或免责声明
6. 若商品数据不足，必须明确写出“数据不足”，并将可信度降为低
"""

_EXECUTIVE_SUMMARY_PROMPT = """\
基于以下深度市场分析，写一段 3-5 句的执行摘要。

要求：
- 第一句：今日市场核心主线（一句话定性，不要以"今日"开头）
- 第二句：最重要的驱动事件及其影响
- 第三句：资产联动逻辑（XX涨因为YY，同时ZZ下跌印证了…）
- 第四句（可选）：与近期趋势的延续或转折
- 最后一句：未来 1-2 天最值得关注的事

直接输出摘要文本，不要加标题或前言。

## 深度分析内容
"""

_REPORT_POLISH_PROMPT = """\
你是卖方宏观策略团队的审校编辑。请对下面的 Markdown 报告做“最终校正+润色”，输出仍为 Markdown。

目标风格（偏机构）：
1. 语气克制、专业、可验证，避免情绪化表达。
2. 逻辑链条清晰：现象 → 驱动 → 资产定价 → 风险点。
3. 保留原有结构与标题层级，不删除固定板块。

硬性约束：
1. 不得新增输入中不存在的事实、数字、日期、事件。
2. 若发现结论与数据明显冲突，优先改写结论措辞（例如“部分定价”“仍待验证”），不要编造新数据。
3. 保留 emoji 标题和风险提示页脚。
4. 输出仅包含最终 Markdown 正文，不要解释你的修改过程。

请处理以下报告：
"""


# ─── 数据预处理 ──────────────────────────────────────────────

_KEY_ASSETS = [
    ("sp500", "S&P 500"), ("nasdaq", "NASDAQ"), ("dji", "道琼斯"),
    ("russell", "Russell 2000"),
    ("vix", "VIX"), ("gold", "黄金"), ("silver", "白银"),
    ("brent", "布伦特原油"), ("crude", "WTI原油"),
    ("copper", "铜"), ("natgas", "天然气"),
    ("dxy", "美元指数"), ("us10y", "10Y美债"),
    ("eurusd", "EUR/USD"), ("usdjpy", "USD/JPY"),
    ("btc", "BTC"), ("eth", "ETH"),
    ("stoxx", "Euro STOXX"), ("dax", "DAX"), ("nikkei", "日经225"), ("hsi", "恒生"),
]


def _summarize_prices(prices: dict) -> str:
    """将价格数据压缩为结构化文本"""
    lines = []
    for key, label in _KEY_ASSETS:
        d = prices.get(key, {})
        if d and "error" not in d:
            chg = d.get("chg", 0)
            price = d.get("price", 0)
            lines.append(f"- {label}: {price:,.2f} ({chg:+.2f}%)")
    return "\n".join(lines) if lines else "无行情数据"


def _summarize_macro(macro: dict) -> str:
    """将宏观指标压缩为文本"""
    parts = []

    vix = macro.get("vix")
    vix_label = macro.get("vix_label", "")
    if vix:
        week_chg = macro.get("vix_week_change_pct")
        week_part = f"，周变化 {week_chg:+.1f}%" if week_chg is not None else ""
        parts.append(f"- VIX: {vix:.2f} {vix_label}{week_part}")

    yc = macro.get("yield_curve", {}) or {}
    source = yc.get("source") or "unknown"
    obs_date = yc.get("observation_date") or "N/A"
    stale_days = yc.get("stale_days")

    spread = yc.get("spread_2y10y_bp")
    shape = yc.get("curve_shape", "")
    if spread is not None:
        parts.append(f"- 2Y-10Y利差: {float(spread):+.1f}bp {shape}")

    rates = yc.get("rates") or {}
    if "2Y" in rates and "10Y" in rates:
        parts.append(f"- 2Y收益率: {float(rates['2Y']):.3f}%  10Y: {float(rates['10Y']):.3f}%")

    stale_part = f" | stale={stale_days}d" if stale_days is not None else ""
    parts.append(f"- 利率口径: source={source} | observation_date={obs_date}{stale_part}")

    validation = yc.get("validation") or {}
    if validation.get("matched_date"):
        max_abs_diff = validation.get("max_abs_diff_bp")
        if max_abs_diff is not None:
            parts.append(f"- 官方对账: Treasury 同日最大偏差 {float(max_abs_diff):.1f}bp")
    elif validation.get("treasury_observation_date"):
        parts.append(
            f"- 官方对账: 日期未对齐（Treasury={validation.get('treasury_observation_date')}）"
        )

    return "\n".join(parts) if parts else "无宏观指标数据"


def _summarize_calendar(calendar: list[dict]) -> str:
    """将经济日历压缩为文本"""
    if not calendar:
        return "无经济日历数据"

    lines = []
    for e in calendar:
        actual = e.get("actual", "").strip()
        if not actual or actual == "****":
            # 待公布事件
            forecast = e.get("forecast", "N/A")
            lines.append(
                f"- [待公布] {e.get('date','')} [{e.get('currency','')}] "
                f"{e.get('event','')}"
                f"（预期: {forecast}）"
            )
        else:
            forecast = e.get("forecast", "")
            previous = e.get("previous", "")
            lines.append(
                f"- [已公布] [{e.get('currency','')}] {e.get('event','')}: "
                f"实际 {actual} vs 预期 {forecast}（前值 {previous}）"
            )

    return "\n".join(lines[:15]) if lines else "无经济日历数据"


def _build_deep_prompt(prices: dict, news_summary, macro: dict,
                       calendar: list[dict], theme_label: str,
                       commodity_news_text: str = "") -> str:
    """构建完整的深度分析 prompt"""
    price_text = _summarize_prices(prices)
    macro_text = _summarize_macro(macro)
    calendar_text = _summarize_calendar(calendar)

    news_text = (
        news_summary if isinstance(news_summary, str)
        else "\n".join(news_summary[:12]) if news_summary
        else "无新闻数据"
    )

    return (
        _DEEP_ANALYSIS_PROMPT
        + f"\n## 市场状态判断\n{theme_label}\n"
        + f"\n## 今日行情数据\n{price_text}\n"
        + f"\n## 宏观指标\n{macro_text}\n"
        + f"\n## 经济日历\n{calendar_text}\n"
        + f"\n## 精选新闻\n{news_text}\n"
    )


# ─── LLM 调用 ────────────────────────────────────────────────

def _call_llm(prompt: str, max_tokens: int = 2000,
              temperature: float = 0.2, stage: str = "DeepAnalysis") -> str | None:
    """调用 LLM API"""
    api_key = os.getenv("AIHUBMIX_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        print(f"  [{stage}] 无 LLM API key，跳过", file=sys.stderr)
        return None

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
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content:
                print(f"  [{stage}] LLM 生成完成（{len(content)} 字符）",
                      file=sys.stderr)
                return content
        else:
            print(f"  [{stage}] LLM API 返回 {resp.status_code}: "
                  f"{resp.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"  [{stage}] LLM 调用失败: {e}", file=sys.stderr)

    return None


# ─── 深度解读生成器 ──────────────────────────────────────────

class DeepAnalysisGenerator:
    """深度市场解读生成器"""

    def generate(
        self,
        prices: dict,
        news_summary,
        macro: dict,
        calendar: list[dict],
        theme_label: str,
        theme_themes: list[str],
        commodity_news_text: str = "",
    ) -> dict | None:
        """
        生成深度解读

        Returns:
            dict: {"analysis": str, "summary": str} 或 None（LLM 失败时）
        """
        # 数据不完整时调整提示
        has_news = bool(news_summary and (
            (isinstance(news_summary, str) and news_summary.strip()) or
            (isinstance(news_summary, list) and len(news_summary) > 0)
        ))

        prompt = _build_deep_prompt(
            prices, news_summary, macro, calendar, theme_label,
            commodity_news_text=commodity_news_text,
        )

        if not has_news:
            prompt += (
                "\n注意：今日新闻数据缺失，请基于行情+宏观+日历数据分析，"
                "主题数量可减少至 2-3 个。\n"
            )

        # Stage 1: 深度分析
        analysis = _call_llm(prompt, max_tokens=2000, temperature=0.2, stage="DeepAnalysis")
        if not analysis:
            return None

        # Stage 2: 执行摘要
        summary_prompt = _EXECUTIVE_SUMMARY_PROMPT + analysis
        summary = _call_llm(summary_prompt, max_tokens=400, temperature=0.3, stage="DeepSummary")

        return {
            "analysis": analysis,
            "summary": summary or "",
        }


def polish_report_markdown(report_markdown: str) -> str:
    """对完整报告做最终校正和机构风格润色（失败时回退原文）"""
    if not report_markdown.strip():
        return report_markdown

    prompt = _REPORT_POLISH_PROMPT + "\n\n" + report_markdown
    polished = _call_llm(
        prompt,
        max_tokens=2600,
        temperature=0.15,
        stage="DeepPolish",
    )
    if not polished:
        return report_markdown

    # 防止模型返回代码块包裹
    text = polished.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip() or report_markdown


# ─── 报告组装 ────────────────────────────────────────────────

def _sign(chg: float) -> str:
    return "🟢" if chg >= 0 else "🔴"


def _price_brief(prices: dict) -> str:
    """生成精简行情速览"""
    brief_assets = [
        ("sp500", "S&P 500", 2), ("nasdaq", "NASDAQ", 2),
        ("vix", "VIX", 2),
        ("gold", "黄金", 2), ("brent", "布伦特", 2),
        ("dxy", "美元", 2), ("us10y", "10Y美债", 3),
        ("btc", "BTC", 0),
    ]

    lines = []
    for key, label, dec in brief_assets:
        d = prices.get(key, {})
        if d and "error" not in d:
            p = d["price"]
            chg = d["chg"]
            lines.append(f"- {label}: {p:,.{dec}f}  {_sign(chg)} {chg:+.2f}%")

    return "\n".join(lines) if lines else "行情数据不可用"


def _market_tech_brief(prices: dict) -> str:
    def get_item(key: str) -> tuple[float, float] | None:
        data = prices.get(key, {})
        if not data or "error" in data:
            return None
        return float(data.get("price", 0.0)), float(data.get("chg", 0.0))

    sp = get_item("sp500")
    nd = get_item("nasdaq")
    dj = get_item("dji")
    if not (sp and nd and dj):
        return "- 大盘或科技指数数据不完整"

    style_diff = nd[1] - sp[1]
    if style_diff > 0.4:
        style_text = "科技跑赢大盘"
    elif style_diff < -0.4:
        style_text = "科技跑输大盘"
    else:
        style_text = "科技与大盘表现接近"

    return "\n".join([
        f"- S&P 500: {sp[0]:,.2f} ({sp[1]:+.2f}%)",
        f"- NASDAQ: {nd[0]:,.2f} ({nd[1]:+.2f}%)",
        f"- Dow Jones: {dj[0]:,.2f} ({dj[1]:+.2f}%)",
        f"- 风格差(NASDAQ - S&P): {style_diff:+.2f}% → {style_text}",
    ])


def build_deep_report(
    prices: dict,
    macro: dict,
    deep_result: dict,
    theme_label: str,
    theme_watch: list[str],
    confidence_note: str = "",
    weekly_compare_note: str = "",
) -> str:
    """
    组装深度解读 Markdown 报告

    Args:
        prices:      行情数据
        macro:       宏观数据
        deep_result: DeepAnalysisGenerator.generate() 的返回值
        theme_label: 主题判断标签
        theme_watch: 后续关注列表

    Returns:
        str: 完整 Markdown 报告
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M UTC")

    analysis = deep_result.get("analysis", "")
    summary = deep_result.get("summary", "")

    sections = []

    # 标题
    sections.append(
        f"# 📰 市场深度解读 · {date_str}\n"
        f"**{time_str}** | 深度分析模式\n\n"
        "---"
    )

    # 今日主线
    sections.append(f"## 🎯 今日主线：{theme_label}")

    # 执行摘要
    if summary:
        sections.append(f"> 💡 {summary}")

    # 大盘与科技表现（固定输出，避免主题被挤占）
    sections.append("---\n\n## 📈 大盘与科技表现")
    sections.append(_market_tech_brief(prices))

    # 深度主题解读
    sections.append("---\n\n## 📰 深度主题解读")
    sections.append(analysis)

    # 行情速览
    sections.append("---\n\n## 📊 行情速览")
    sections.append(_price_brief(prices))

    # 后续关注
    sections.append("---\n\n## 👀 后续关注")
    if theme_watch:
        for w in theme_watch:
            sections.append(f"- {w}")
    else:
        sections.append("- 关注本周剩余宏观数据公布及央行官员发言")

    if confidence_note:
        sections.append("---\n\n## ✅ 报告质量与置信度")
        sections.append(confidence_note)

    if weekly_compare_note:
        sections.append("---\n\n## 🗓️ 近一周对比（简版）")
        sections.append(weekly_compare_note)

    # 页脚
    sections.append(
        "---\n"
        f"*📅 {date_str} {time_str} · market_deep · 深度解读模式*\n"
        "*⚠️ 仅供参考，不构成投资建议*"
    )

    return "\n\n".join(sections)
