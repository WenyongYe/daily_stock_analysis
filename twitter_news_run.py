#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推特金融快讯监控 CLI 入口

用法:
  python twitter_news_run.py                        # 拉取+分析，打印到终端
  python twitter_news_run.py --output report        # 保存到 reports/
  python twitter_news_run.py --output report --feishu  # 保存并推送飞书
  python twitter_news_run.py --dry-run              # 仅拉取推文，不分析不推送
"""

import argparse
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import setup_env
from src.twitter_monitor.config import get_monitor_accounts, get_time_window
from src.twitter_monitor.client import TwitterAPIClient
from src.twitter_monitor.analyzer import analyze_tweets, format_briefing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _normalize_feishu_text(text: str) -> str:
    """把 markdown-heavy 文本转成更稳的飞书文本格式"""
    normalized = text.replace("\r\n", "\n").strip()
    normalized = re.sub(r"\*\*(.*?)\*\*", r"\1", normalized)  # 去掉 markdown 粗体
    normalized = normalized.replace("━━━━━━━━━━━━━━━━━━━━━━━━━", "--------------------")
    return normalized


def _chunk_line(line: str, max_len: int = 900) -> list[str]:
    """按长度切分单行，避免飞书 post 段落过长"""
    line = line.strip()
    if not line:
        return []

    chunks: list[str] = []
    remain = line
    while len(remain) > max_len:
        split_at = remain.rfind(" ", 0, max_len)
        if split_at < max_len // 2:
            split_at = max_len
        chunks.append(remain[:split_at].rstrip())
        remain = remain[split_at:].lstrip()

    if remain:
        chunks.append(remain)
    return chunks


def _build_feishu_post_payload(text: str) -> dict:
    normalized = _normalize_feishu_text(text)
    lines = normalized.splitlines()

    content: list[list[dict]] = []
    for line in lines:
        if not line.strip():
            content.append([{"tag": "text", "text": " "}])
            continue
        for part in _chunk_line(line):
            content.append([{"tag": "text", "text": part}])

    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": "📌 推特金融快讯",
                    "content": content,
                }
            }
        },
    }


def _build_feishu_text_payload(text: str) -> dict:
    normalized = _normalize_feishu_text(text)
    max_len = 9000
    if len(normalized) > max_len:
        normalized = normalized[:max_len] + "\n\n(内容过长，已截断)"

    return {
        "msg_type": "text",
        "content": {"text": normalized},
    }


def _post_to_feishu(webhook: str, payload: dict) -> tuple[bool, str]:
    import requests

    try:
        response = requests.post(webhook, json=payload, timeout=30)
        if response.status_code != 200:
            return False, f"HTTP {response.status_code}"

        result = response.json()
        code = result.get("code", result.get("StatusCode"))
        if code == 0:
            return True, "ok"
        return False, f"返回错误: {result}"
    except Exception as exc:
        return False, str(exc)


def push_feishu(text: str):
    """推送简报到飞书 Webhook（post 模板优先，text 兜底）"""
    setup_env()
    webhook = os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook:
        print("[飞书] 未配置 FEISHU_WEBHOOK_URL，跳过", file=sys.stderr)
        return

    # 1) 先用兼容性更高的 post 模板
    post_payload = _build_feishu_post_payload(text)
    ok, detail = _post_to_feishu(webhook, post_payload)
    if ok:
        print("[飞书] 推送成功（post 模板）")
        return

    print(f"[飞书] post 模板失败: {detail}，尝试 text 兜底", file=sys.stderr)

    # 2) 失败则降级到最稳妥的 text 模板
    text_payload = _build_feishu_text_payload(text)
    ok, detail = _post_to_feishu(webhook, text_payload)
    if ok:
        print("[飞书] 推送成功（text 兜底）")
    else:
        print(f"[飞书] 推送失败: {detail}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="推特金融快讯监控")
    parser.add_argument(
        "--output",
        choices=["print", "report"],
        default="print",
        help="输出方式: print(终端) 或 report(保存到 reports/)",
    )
    parser.add_argument("--feishu", action="store_true", help="推送到飞书")
    parser.add_argument("--dry-run", action="store_true", help="仅拉取推文，不分析不推送")
    parser.add_argument("--hours", type=int, default=None, help="回溯小时数（默认8）")
    args = parser.parse_args()

    setup_env()

    accounts = get_monitor_accounts()
    since, until = get_time_window(args.hours)
    logger.info(f"监控账号: {accounts}")
    logger.info(f"时间窗口: {since} ~ {until}")

    # 1. 拉取推文
    client = TwitterAPIClient()
    tweets = client.fetch_all_tweets(accounts, since, until)

    if args.dry_run:
        print(f"\n=== Dry Run: {len(tweets)} 条推文 ===\n")
        for t in tweets:
            print(f"@{t['author']} ({t['createdAt']}):")
            print(f"  {t['text'][:200]}")
            print()
        return

    # 2. AI 分析
    logger.info("正在 AI 分析推文...")
    analysis = analyze_tweets(tweets, args.hours)

    # 3. 格式化简报
    briefing = format_briefing(analysis, since, until)

    # 4. 输出
    if args.output == "report":
        reports_dir = Path(__file__).parent / "reports"
        reports_dir.mkdir(exist_ok=True)
        filename = f"twitter_news_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        filepath = reports_dir / filename
        filepath.write_text(briefing, encoding="utf-8")
        print(f"[报告] 已保存: {filepath}")
    else:
        print(briefing)

    # 5. 飞书推送
    if args.feishu:
        push_feishu(briefing)


if __name__ == "__main__":
    main()
