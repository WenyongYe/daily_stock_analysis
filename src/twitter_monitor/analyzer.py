# -*- coding: utf-8 -*-
"""AI 筛选与解读：将原始推文转化为结构化中文金融简报"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.config import setup_env, get_config
from src.twitter_monitor.config import get_fetch_interval_hours

logger = logging.getLogger(__name__)

# Skill references 目录（优先从此加载 prompt）
SKILL_REFS_DIR = Path("/root/.openclaw/workspace/skills/twitter-news-briefing/references")

# 内置 fallback prompt（当 skill 文件不可用时使用）
_FALLBACK_PROMPT = """你是一位资深金融分析师，负责将 Twitter 金融快讯整理为结构化中文简报。

## 输入
你将收到过去 {hours} 小时内来自多个 Twitter 金融快讯账号的推文原文（英文）。

## 任务
1. **去重合并**：多个账号报道同一事件时，合并为一条，标注所有来源
2. **分级分类**：
   - 🔴 **重大事件**：可能导致主要资产（美股/美债/黄金/原油/汇率）波动 >1% 的事件
   - 🟡 **重要动态**：值得关注但非突发的市场动态
   - 🔵 **市场观点**：分析师评论、市场情绪观察
3. **中文解读**：每条新闻翻译为中文，附加简明的市场影响分析
4. **过滤噪音**：忽略广告、个人观点争论、与金融无关的内容

## 输出格式
🔴 重大事件
• [事件标题]
  [中文解读 + 影响分析]
  来源：@账号1 @账号2 | 时间

🟡 重要动态
• [动态内容]
  来源：@账号 | 时间

🔵 市场观点
• @账号：[观点摘要]

## 规则
- 如果某个级别没有内容，省略该级别
- 每条新闻控制在 2-3 行
- 如果所有推文都无重要价值，直接输出：「过去 {hours} 小时无重大金融事件」
"""


def _load_skill_prompt(hours: int) -> str:
    """从 skill references 文件加载 prompt，失败则 fallback。"""
    try:
        if not SKILL_REFS_DIR.exists():
            raise FileNotFoundError(f"Skill references 目录不存在: {SKILL_REFS_DIR}")

        parts = []
        parts.append("你是一位资深金融分析师，负责将 Twitter 金融快讯整理为结构化中文简报。")
        parts.append(f"\n你将收到过去 {hours} 小时内来自多个 Twitter 金融快讯账号的推文原文（英文）。\n")

        # 加载分析框架
        framework_file = SKILL_REFS_DIR / "analysis_framework.md"
        if framework_file.exists():
            parts.append(framework_file.read_text(encoding="utf-8"))

        # 加载账号画像
        profiles_file = SKILL_REFS_DIR / "account_profiles.md"
        if profiles_file.exists():
            parts.append(profiles_file.read_text(encoding="utf-8"))

        # 加载模板和示例
        templates_file = SKILL_REFS_DIR / "prompt_templates.md"
        if templates_file.exists():
            parts.append(templates_file.read_text(encoding="utf-8"))

        parts.append(f"\n如果所有推文都无重要价值，直接输出：「过去 {hours} 小时无重大金融事件」")

        prompt = "\n\n".join(parts)
        logger.info(f"已从 skill references 加载 prompt（{len(prompt)} 字符）")
        return prompt

    except Exception as e:
        logger.warning(f"加载 skill references 失败，使用 fallback prompt: {e}")
        return _FALLBACK_PROMPT.format(hours=hours)


def analyze_tweets(tweets: list[dict], hours: int | None = None) -> str:
    """调用 LLM 分析推文，返回结构化简报文本。"""
    hours = hours or get_fetch_interval_hours()

    if not tweets:
        return f"过去 {hours} 小时无重大金融事件"

    # 拼接推文文本
    lines = []
    for t in tweets:
        lines.append(f"@{t['author']} ({t['createdAt']}): {t['text']}")
    raw_text = "\n\n".join(lines)

    # token 保护：截断超长输入（约 15000 字符 ≈ 4000 tokens）
    max_chars = 15000
    if len(raw_text) > max_chars:
        raw_text = raw_text[:max_chars] + "\n\n...(已截断)"
        logger.warning(f"推文内容过长，已截断至 {max_chars} 字符")

    setup_env()
    config = get_config()

    result = _call_llm(config, raw_text, hours)
    return result


def _call_llm(config, raw_text: str, hours: int) -> str:
    """调用 LLM 生成简报。"""
    system = _load_skill_prompt(hours)
    user_msg = f"以下是过去 {hours} 小时的推文：\n\n{raw_text}"

    # 优先 Gemini
    gemini_key = config.gemini_api_key
    if gemini_key and not gemini_key.startswith("your_") and len(gemini_key) > 10:
        try:
            return _call_gemini(gemini_key, config, system, user_msg)
        except Exception as e:
            logger.warning(f"Gemini 调用失败，回退: {e}")

    # OpenAI 兼容
    openai_key = config.openai_api_key
    if openai_key and not openai_key.startswith("your_") and len(openai_key) >= 8:
        try:
            return _call_openai(config, system, user_msg)
        except Exception as e:
            logger.warning(f"OpenAI 调用失败: {e}")

    logger.error("无可用 LLM 提供商")
    return f"过去 {hours} 小时获取到 {len(raw_text)} 字符推文，但 LLM 不可用，无法生成简报"


def _call_gemini(api_key: str, config, system: str, user_msg: str) -> str:
    from google import genai as google_genai
    client = google_genai.Client(api_key=api_key)
    model = getattr(config, "gemini_model", None) or "gemini-2.5-flash"
    response = client.models.generate_content(
        model=model,
        contents=[{"role": "user", "parts": [{"text": f"{system}\n\n{user_msg}"}]}],
    )
    return response.text


def _call_openai(config, system: str, user_msg: str) -> str:
    from openai import OpenAI
    client_kwargs = {"api_key": config.openai_api_key}
    if config.openai_base_url:
        client_kwargs["base_url"] = config.openai_base_url
    client = OpenAI(**client_kwargs)
    model = getattr(config, "openai_model", None) or "gpt-4o-mini"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=4000,
    )
    return resp.choices[0].message.content


def format_briefing(analysis: str, since: str, until: str) -> str:
    """将 AI 分析结果包装为完整简报格式。"""
    now = datetime.now(timezone.utc)
    bj_hour = (now.hour + 8) % 24
    interval = get_fetch_interval_hours()
    next_hours = [0, 8, 16]
    next_push = None
    for h in next_hours:
        if h > bj_hour:
            next_push = f"{h:02d}:00"
            break
    if not next_push:
        next_push = f"{next_hours[0]:02d}:00"

    header = f"📌 推特金融快讯 | 北京时间 {bj_hour:02d}:00（过去{interval}小时）"
    separator = "━" * 25
    footer = f"⏰ 下次推送：北京时间 {next_push}"

    return f"{header}\n{separator}\n\n{analysis}\n\n{separator}\n{footer}"
