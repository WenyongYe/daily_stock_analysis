# -*- coding: utf-8 -*-
"""LLM helpers for options flow pipeline."""

from __future__ import annotations

import logging
from typing import Optional

from src.config import get_config

logger = logging.getLogger(__name__)


def _is_key_valid(key: Optional[str]) -> bool:
    return bool(key and not key.startswith("your_") and len(key) >= 8)


def call_text_llm(system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 2000) -> str:
    cfg = get_config()

    if _is_key_valid(cfg.gemini_api_key):
        try:
            from google import genai as google_genai

            client = google_genai.Client(api_key=cfg.gemini_api_key)
            model = getattr(cfg, "gemini_model", None) or "gemini-2.5-flash"
            response = client.models.generate_content(
                model=model,
                contents=[{"role": "user", "parts": [{"text": f"{system}\n\n{user}"}]}],
            )
            if response and response.text:
                return response.text
        except Exception as exc:
            logger.warning("Gemini 文本调用失败，回退 OpenAI: %s", exc)

    if _is_key_valid(cfg.openai_api_key):
        try:
            from openai import OpenAI

            client_kwargs = {"api_key": cfg.openai_api_key}
            if cfg.openai_base_url:
                client_kwargs["base_url"] = cfg.openai_base_url
            client = OpenAI(**client_kwargs)
            model = getattr(cfg, "openai_model", None) or "gpt-4o-mini"
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if resp.choices and resp.choices[0].message.content:
                return resp.choices[0].message.content
        except Exception as exc:
            logger.warning("OpenAI 文本调用失败: %s", exc)

    raise RuntimeError("无可用 LLM 提供商")
