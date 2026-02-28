#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===================================
突发财经新闻监控 - 独立运行入口
===================================

使用方式：
    python news_watcher.py              # 定时模式（默认每 10 分钟）
    python news_watcher.py --once       # 仅执行一次
    python news_watcher.py --interval 5 # 每 5 分钟检查
    python news_watcher.py --batch      # 批量汇总模式（N条合并为一条）

环境变量（.env 中配置）：
    FEISHU_WEBHOOK_URL      - 飞书 Webhook（必填）
    FJ_EMAIL                - FinancialJuice 账号邮箱（可选）
    FJ_PASSWORD             - FinancialJuice 账号密码（可选）
    NEWS_CHECK_INTERVAL     - 检查间隔分钟（默认 10）
    NEWS_MAX_AGE_HOURS      - 只推多少小时内的新闻（默认 4）
    NEWS_STATE_FILE         - 状态文件路径（默认 data/breaking_news_seen.json）
"""

import argparse
import logging
import time
import os
import sys
from datetime import datetime

# 加载 .env
from src.config import setup_env
setup_env()

from src.breaking_news import BreakingNewsWatcher, DEFAULT_INTERVAL_MIN
from src.logging_config import setup_logging


def parse_args():
    parser = argparse.ArgumentParser(description="突发财经新闻监控")
    parser.add_argument("--once", action="store_true", help="只执行一次后退出")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_MIN,
                        help=f"检查间隔（分钟，默认 {DEFAULT_INTERVAL_MIN}）")
    parser.add_argument("--batch", action="store_true",
                        help="批量汇总模式：N 条合并为一条推送")
    parser.add_argument("--debug", action="store_true", help="开启 DEBUG 日志")
    return parser.parse_args()


def run_check(watcher: BreakingNewsWatcher, batch_mode: bool = False) -> int:
    try:
        if batch_mode:
            # 批量模式：先收集所有新条目，再一次推送
            from src.breaking_news import (
                FinancialJuiceFetcher, RssFetcher, SeenTracker,
                _dedup_by_title, NEWS_MAX_AGE_HOURS
            )
            from datetime import timezone, timedelta
            import time as _time

            all_items = []
            if watcher._fj.configured:
                all_items.extend(watcher._fj.fetch())
            all_items.extend(watcher._rss.fetch())

            now = datetime.now(timezone.utc)
            max_age = timedelta(hours=NEWS_MAX_AGE_HOURS)
            new_items = []
            for item in all_items:
                if not watcher._tracker.is_new(item.uid):
                    continue
                if item.published:
                    pub = item.published
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=timezone.utc)
                    if (now - pub) > max_age:
                        watcher._tracker.mark_seen(item.uid)
                        continue
                new_items.append(item)

            deduped = _dedup_by_title(new_items)
            if deduped:
                if watcher.push_batch_summary(deduped):
                    watcher._tracker.mark_seen_batch([i.uid for i in deduped])
                    return len(deduped)
            return 0
        else:
            return watcher.run_once()
    except Exception as e:
        logging.getLogger(__name__).error(f"检查异常: {e}", exc_info=True)
        return 0


def main():
    args = parse_args()
    setup_logging(debug=args.debug)
    logger = logging.getLogger(__name__)

    webhook = os.getenv("FEISHU_WEBHOOK_URL", "")
    if not webhook:
        logger.error("未配置 FEISHU_WEBHOOK_URL，请在 .env 中设置")
        sys.exit(1)

    watcher = BreakingNewsWatcher(feishu_webhook_url=webhook)

    fj_configured = watcher._fj.configured
    logger.info(f"新闻监控启动 | FinancialJuice={'✓' if fj_configured else '✗（未配置账号）'} | RSS=✓")
    logger.info(f"模式={'单次' if args.once else f'定时 {args.interval} 分钟'} | 推送={'批量' if args.batch else '逐条'}")

    if args.once:
        count = run_check(watcher, batch_mode=args.batch)
        logger.info(f"执行完成，推送 {count} 条")
        return

    # 定时循环
    interval_sec = args.interval * 60
    while True:
        logger.info(f"[{datetime.now().strftime('%H:%M:%S')}] 开始检查...")
        count = run_check(watcher, batch_mode=args.batch)
        logger.info(f"本次推送 {count} 条，下次检查在 {args.interval} 分钟后")
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
