# -*- coding: utf-8 -*-
"""
飞书推送 Delivery
优先复用 src/notification.py 的 NotificationService
降级到 FEISHU_WEBHOOK_URL 直接 POST
"""

import os
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
        # 方式一：通过 NotificationService（支持 bot 推送）
        if _NOTIF_AVAILABLE:
            try:
                svc = NotificationService()
                if svc.is_available():
                    ok = svc.send_to_context(text)
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
                    json={"msg_type": "text", "content": {"text": text}},
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
