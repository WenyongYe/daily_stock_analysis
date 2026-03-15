#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
期权异动简报 CLI

用法:
  python options_flow_run.py --output report --feishu
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List

# ensure project root
sys.path.insert(0, str(Path(__file__).parent))

from src.config import setup_env
from src.notification import NotificationService
from src.options_flow.config import (
    get_last_us_session_window,
    get_monitor_accounts,
    get_use_images,
)
from src.options_flow.client import OptionsFlowTwitterClient
from src.options_flow.vision import extract_option_items_from_image
from src.options_flow.parser import (
    OptionFlowItem,
    deduplicate_items,
    extract_from_ocr,
    extract_from_text,
)
from src.options_flow.enricher import fetch_news_context, summarize_drivers
from src.options_flow.formatter import format_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _collect_items(tweets: list[dict]) -> list[OptionFlowItem]:
    items: list[OptionFlowItem] = []

    for t in tweets:
        text_item = extract_from_text(t.get("text", ""), t.get("url", ""), t.get("createdAt", ""))
        if text_item:
            items.append(text_item)

        if not t.get("media_urls"):
            continue
        for url in t.get("media_urls"):
            ocr_items = []
            try:
                ocr_items = extract_option_items_from_image(url)
            except Exception as exc:
                logger.warning("OCR 失败: %s", exc)
            for raw in ocr_items:
                item = extract_from_ocr(raw, t.get("url", ""), t.get("createdAt", ""), url)
                if item:
                    items.append(item)

    return items


def main():
    parser = argparse.ArgumentParser(description="Options flow briefing")
    parser.add_argument(
        "--output",
        choices=["print", "report"],
        default="print",
        help="输出方式: print 或 report",
    )
    parser.add_argument("--feishu", action="store_true", help="推送到飞书")
    args = parser.parse_args()

    setup_env()

    since, until, session_date = get_last_us_session_window()
    accounts = get_monitor_accounts()
    logger.info("监控账号: %s", accounts)
    logger.info("时间窗口: %s ~ %s", since, until)

    client = OptionsFlowTwitterClient()
    tweets = client.fetch_all_tweets(accounts, since, until)

    items = _collect_items(tweets)
    items = deduplicate_items(items)

    warnings: List[str] = []
    if not get_use_images():
        warnings.append("未启用图片 OCR，仅解析文本")
    if not items:
        warnings.append("未解析到有效记录")

    tickers = sorted({i.symbol for i in items})[:10]
    news_results = fetch_news_context(tickers)
    news_summary = summarize_drivers(news_results)

    report = format_report(session_date, items, news_summary, warnings)

    if args.output == "report":
        reports_dir = Path(__file__).parent / "reports"
        reports_dir.mkdir(exist_ok=True)
        filename = f"options_flow_{session_date.replace('-', '')}.md"
        path = reports_dir / filename
        path.write_text(report, encoding="utf-8")
        logger.info("报告已保存: %s", path)
    else:
        print(report)

    if args.feishu:
        notifier = NotificationService()
        notifier.send(report, email_send_to_all=True)


if __name__ == "__main__":
    main()
