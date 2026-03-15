# -*- coding: utf-8 -*-
"""
飞书推送 Delivery
优先复用 src/notification.py 的 NotificationService
降级到 FEISHU_WEBHOOK_URL 直接 POST
"""

import os
import re
import sys
from pathlib import Path

import requests

# 确保能 import src 模块
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_NOTIF_AVAILABLE = False
try:
    from src.notification import NotificationService
    _NOTIF_AVAILABLE = True
except ImportError as e:
    print(f"  [FeishuDelivery] src.notification 不可用: {e}，降级到 Webhook", file=sys.stderr)

FEISHU_MAX_CHARS = int(os.getenv("FEISHU_MAX_BYTES", "15000"))


def _md_to_feishu_text(md: str) -> str:
    """将 Markdown 日报转为飞书友好的纯文本格式"""
    text = md

    # Markdown 表格 → 纯文本列表
    lines = text.split("\n")
    out = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        # 跳过表格分隔行
        if re.match(r'^\|[-:\s|]+\|$', stripped):
            in_table = True
            continue
        # 表格表头行
        if in_table and stripped.startswith("|") and stripped.endswith("|"):
            # 跳过表头（紧跟在分隔行之前的行已输出）
            pass
        if not in_table and stripped.startswith("|") and stripped.endswith("|"):
            # 表头行，跳过（下一行是分隔行）
            in_table = True
            continue
        if in_table and stripped.startswith("|") and stripped.endswith("|"):
            # 数据行 → 转文本
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            # 格式：事件相关字段拼接
            if len(cells) >= 6:
                # 日期 | 货币 | 事件 | 实际 | 预期 | 前值 | 解读
                date, cur, event = cells[0], cells[1], cells[2]
                actual = cells[3].replace("**", "")
                forecast = cells[4] if len(cells) > 4 else ""
                signal = cells[-1] if len(cells) > 5 else ""
                line_text = f"  {date} [{cur}] {event}: {actual}"
                if forecast:
                    line_text += f"（预期 {forecast}）"
                if signal:
                    line_text += f" {signal}"
                out.append(line_text)
            else:
                out.append("  " + " | ".join(cells))
            continue
        if in_table and not stripped.startswith("|"):
            in_table = False

        out.append(line)

    text = "\n".join(out)

    # 去除 Markdown 标记
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # 标题
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)                # 粗体
    text = re.sub(r'\*(.+?)\*', r'\1', text)                    # 斜体
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)       # 链接
    text = re.sub(r'^---+$', '─' * 30, text, flags=re.MULTILINE)

    # 压缩连续空行
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


class FeishuDelivery:
    """飞书推送器"""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL")

    def send(self, text: str) -> bool:
        """
        推送文本到飞书

        Args:
            text: 报告内容（Markdown）

        Returns:
            bool: 是否成功
        """
        # 转为飞书友好的纯文本
        feishu_text = _md_to_feishu_text(text)

        # 长度控制
        if len(feishu_text.encode("utf-8")) > FEISHU_MAX_CHARS:
            feishu_text = feishu_text[:FEISHU_MAX_CHARS - 100]
            feishu_text += "\n\n⋯⋯（内容过长已截断，完整版已保存到文件）"

        # 方式一：通过 NotificationService（支持 bot 推送）
        if _NOTIF_AVAILABLE:
            try:
                svc = NotificationService()
                if svc.is_available():
                    ok = svc.send_to_context(feishu_text)
                    if ok:
                        print("  [FeishuDelivery] NotificationService 推送成功", file=sys.stderr)
                        return True
            except Exception as e:
                print(f"  [FeishuDelivery] NotificationService 失败: {e}，降级 Webhook", file=sys.stderr)

        # 方式二：Webhook 直接 POST
        if self.webhook_url:
            try:
                r = requests.post(
                    self.webhook_url,
                    json={"msg_type": "text", "content": {"text": feishu_text}},
                    timeout=10,
                )
                ok = r.status_code == 200
                status = "成功" if ok else f"失败 {r.status_code}"
                print(f"  [FeishuDelivery] Webhook 推送{status}", file=sys.stderr)
                return ok
            except Exception as e:
                print(f"  [FeishuDelivery] Webhook 错误: {e}", file=sys.stderr)

        print("  [FeishuDelivery] 无可用推送渠道（未配置 FEISHU_WEBHOOK_URL）", file=sys.stderr)
        return False
