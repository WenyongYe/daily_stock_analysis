# -*- coding: utf-8 -*-
"""Vision OCR for option flow images."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Optional, Tuple

import requests

from src.config import get_config
from src.options_flow.config import get_vision_model, get_vision_fallback_model

logger = logging.getLogger(__name__)

VISION_TIMEOUT = 60
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE_BYTES = 6 * 1024 * 1024

PROMPT = """
你是期权异动 OCR 助手。请从图片中提取所有可见的期权异动记录。

输出格式：仅返回 JSON 数组（不要 markdown），数组元素为对象，字段：
- symbol: 美股代码（如 AAPL）
- option_type: call/put
- expiry: 到期日（YYYY-MM-DD）
- strike: 执行价（数字）
- volume: 成交量（整数）
- open_interest: OI（整数）
- premium: 成交金额（可选，数字，美元）

如果图片无法识别出期权记录，返回 []。
""".strip()


def _is_key_valid(key: Optional[str]) -> bool:
    return bool(key and not key.startswith("your_") and len(key) >= 8)


def _download_image(url: str) -> Tuple[bytes, str]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    content_type = (resp.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
    if content_type not in ALLOWED_MIME:
        raise ValueError(f"Unsupported image type: {content_type}")
    data = resp.content
    if len(data) > MAX_SIZE_BYTES:
        raise ValueError("Image too large")
    return data, content_type


def _parse_json_list(text: str) -> list[dict[str, Any]]:
    cleaned = text.strip()
    if "```" in cleaned:
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except Exception:
        pass
    return []


def _has_key_fields(items: list[dict[str, Any]]) -> bool:
    for item in items:
        if item.get("volume") and item.get("open_interest") and item.get("expiry"):
            return True
    return False


def _call_gemini(image_bytes: bytes, mime_type: str, model_name: str) -> str:
    import google.generativeai as genai

    cfg = get_config()
    genai.configure(api_key=cfg.gemini_api_key)
    model = genai.GenerativeModel(model_name)
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    part = {"inline_data": {"mime_type": mime_type, "data": b64}}
    response = model.generate_content([part, PROMPT], request_options={"timeout": VISION_TIMEOUT})
    if response and response.text:
        return response.text
    raise ValueError("Gemini returned empty response")


def _call_openai(image_bytes: bytes, mime_type: str, model_name: str) -> str:
    from openai import OpenAI

    cfg = get_config()
    client_kwargs = {"api_key": cfg.openai_api_key, "timeout": VISION_TIMEOUT}
    if cfg.openai_base_url:
        client_kwargs["base_url"] = cfg.openai_base_url
    client = OpenAI(**client_kwargs)
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a precise OCR assistant."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        max_tokens=1200,
    )
    if resp.choices and resp.choices[0].message.content:
        return resp.choices[0].message.content
    raise ValueError("OpenAI returned empty response")


def extract_option_items_from_image(image_url: str) -> list[dict[str, Any]]:
    image_bytes, mime_type = _download_image(image_url)
    cfg = get_config()

    items: list[dict[str, Any]] = []
    raw_text = ""

    if _is_key_valid(cfg.gemini_api_key):
        model = get_vision_model()
        try:
            raw_text = _call_gemini(image_bytes, mime_type, model)
            items = _parse_json_list(raw_text)
            if items and _has_key_fields(items):
                return items
        except Exception as exc:
            logger.warning("Gemini vision 失败: %s", exc)

        fallback = get_vision_fallback_model()
        if fallback and fallback != model:
            try:
                raw_text = _call_gemini(image_bytes, mime_type, fallback)
                items = _parse_json_list(raw_text)
                if items:
                    return items
            except Exception as exc:
                logger.warning("Gemini fallback 失败: %s", exc)

    if _is_key_valid(cfg.openai_api_key):
        model = cfg.openai_vision_model or cfg.openai_model
        if model:
            try:
                raw_text = _call_openai(image_bytes, mime_type, model)
                items = _parse_json_list(raw_text)
                if items:
                    return items
            except Exception as exc:
                logger.warning("OpenAI vision 失败: %s", exc)

    logger.warning("图片 OCR 未能解析: %s", image_url)
    return []
