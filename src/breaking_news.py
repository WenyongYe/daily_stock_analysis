# -*- coding: utf-8 -*-
"""
===================================
突发财经新闻监控模块
===================================

职责：
1. 从 FinancialJuice 获取实时市场快讯（需账号）
2. 备用 RSS 源：Reuters、MarketWatch、Yahoo Finance、CNBC
3. 去重防重推（本地 JSON 状态文件）
4. 定时推送到飞书 Webhook

使用方式：
    python news_watcher.py              # 启动定时监控（默认每 10 分钟）
    python news_watcher.py --once       # 仅执行一次
    python news_watcher.py --interval 5 # 每 5 分钟检查
"""

import hashlib
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Set
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

# ===== 配置 =====
STATE_FILE = Path(os.getenv("NEWS_STATE_FILE", "data/breaking_news_seen.json"))
MAX_SEEN_ITEMS = 500       # 最多记录多少条已推送（防文件膨胀）
NEWS_MAX_AGE_HOURS = int(os.getenv("NEWS_MAX_AGE_HOURS", "4"))   # 只推 N 小时内的新闻
DEFAULT_INTERVAL_MIN = int(os.getenv("NEWS_CHECK_INTERVAL", "10"))


@dataclass
class NewsItem:
    """单条新闻"""
    uid: str          # 唯一标识（hash）
    title: str
    source: str
    published: Optional[datetime] = None
    url: Optional[str] = None
    category: Optional[str] = None

    def format_push(self) -> str:
        """格式化飞书推送文本"""
        ts = self.published.strftime("%H:%M") if self.published else ""
        cat = f"[{self.category}] " if self.category else ""
        link = f"\n🔗 {self.url}" if self.url else ""
        return f"📰 {cat}{ts} **{self.source}**\n{self.title}{link}"


# ===== 新闻源 =====

class FinancialJuiceFetcher:
    """
    FinancialJuice 新闻获取（免费账号）
    环境变量：
        FJ_EMAIL    - 账号邮箱
        FJ_PASSWORD - 账号密码
    """
    BASE_URL = "https://www.financialjuice.com"
    LOGIN_URL = f"{BASE_URL}/account/login"
    FEED_URL = f"{BASE_URL}/api/newsitems"

    def __init__(self):
        self._email = os.getenv("FJ_EMAIL", "")
        self._password = os.getenv("FJ_PASSWORD", "")
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
        })
        self._logged_in = False

    @property
    def configured(self) -> bool:
        return bool(self._email and self._password)

    def _login(self) -> bool:
        """登录获取 session cookie"""
        if not self.configured:
            return False
        try:
            # 先获取首页拿 CSRF token（如有）
            home = self._session.get(self.BASE_URL, timeout=10)
            payload = {
                "Email": self._email,
                "Password": self._password,
                "RememberMe": "true",
            }
            resp = self._session.post(self.LOGIN_URL, data=payload, timeout=10, allow_redirects=True)
            if resp.status_code in (200, 302):
                self._logged_in = True
                logger.info("FinancialJuice 登录成功")
                return True
            logger.warning(f"FinancialJuice 登录失败: {resp.status_code}")
        except Exception as e:
            logger.warning(f"FinancialJuice 登录异常: {e}")
        return False

    def fetch(self, categories: List[str] = None, count: int = 20) -> List[NewsItem]:
        """拉取新闻"""
        if not self.configured:
            return []
        if not self._logged_in and not self._login():
            return []

        categories = categories or ["market-moving", "macro", "equities"]
        items: List[NewsItem] = []

        for cat in categories:
            try:
                resp = self._session.get(
                    self.FEED_URL,
                    params={"category": cat, "count": count},
                    timeout=10,
                )
                if resp.status_code == 401:
                    # session 过期，重新登录一次
                    self._logged_in = False
                    if self._login():
                        resp = self._session.get(
                            self.FEED_URL,
                            params={"category": cat, "count": count},
                            timeout=10,
                        )
                    else:
                        continue

                if resp.status_code != 200:
                    logger.debug(f"FinancialJuice {cat}: HTTP {resp.status_code}")
                    continue

                data = resp.json()
                news_list = data if isinstance(data, list) else data.get("items", data.get("news", []))
                for n in news_list:
                    title = n.get("headline") or n.get("title") or n.get("text", "")
                    if not title:
                        continue
                    url = n.get("url") or n.get("link", "")
                    if url and not url.startswith("http"):
                        url = urljoin(self.BASE_URL, url)
                    pub_str = n.get("date") or n.get("published") or n.get("timestamp", "")
                    published = _parse_dt(pub_str)
                    uid = _make_uid("fj", title)
                    items.append(NewsItem(
                        uid=uid,
                        title=title.strip(),
                        source="FinancialJuice",
                        published=published,
                        url=url or None,
                        category=cat,
                    ))
            except Exception as e:
                logger.warning(f"FinancialJuice fetch [{cat}] 异常: {e}")

        return items


class RssFetcher:
    """通用 RSS 拉取器"""

    FEEDS = [
        {
            "name": "MarketWatch",
            "url": "https://feeds.marketwatch.com/marketwatch/marketpulse/",
            "category": "Markets",
        },
        {
            "name": "Yahoo Finance",
            "url": "https://finance.yahoo.com/news/rssindex",
            "category": "Markets",
        },
        {
            "name": "CNBC Markets",
            "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
            "category": "Markets",
        },
        {
            "name": "Investing.com News",
            "url": "https://www.investing.com/rss/news_25.rss",
            "category": "Macro",
        },
        {
            "name": "FT Markets",
            "url": "https://www.ft.com/markets?format=rss",
            "category": "Markets",
        },
    ]

    def fetch(self) -> List[NewsItem]:
        items: List[NewsItem] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }
        ns_atom = "http://www.w3.org/2005/Atom"
        ns_dc = "http://purl.org/dc/elements/1.1/"

        for feed in self.FEEDS:
            try:
                resp = requests.get(feed["url"], headers=headers, timeout=10)
                if resp.status_code != 200:
                    logger.debug(f"RSS {feed['name']}: HTTP {resp.status_code}")
                    continue

                root = ET.fromstring(resp.content)

                # 支持 RSS 2.0（<item>）和 Atom（<entry>）
                entries = root.findall(".//item")
                if not entries:
                    entries = root.findall(f".//{{{ns_atom}}}entry")

                for entry in entries[:20]:
                    # 标题（兼容 RSS 和 Atom，用 is not None 避免 Element 真值警告）
                    title_el = entry.find("title")
                    if title_el is None:
                        title_el = entry.find(f"{{{ns_atom}}}title")
                    title = (title_el.text or "").strip() if title_el is not None else ""
                    if not title:
                        continue

                    # 链接
                    link_el = entry.find("link")
                    if link_el is None:
                        link_el = entry.find(f"{{{ns_atom}}}link")
                    url = ""
                    if link_el is not None:
                        url = (link_el.text or "").strip() or link_el.get("href", "")

                    # 发布时间
                    pub_el = entry.find("pubDate")
                    if pub_el is None:
                        pub_el = entry.find(f"{{{ns_dc}}}date")
                    if pub_el is None:
                        pub_el = entry.find(f"{{{ns_atom}}}published")
                    published = _parse_dt(pub_el.text if pub_el is not None else "")

                    uid = _make_uid(feed["name"], title)
                    items.append(NewsItem(
                        uid=uid,
                        title=title,
                        source=feed["name"],
                        published=published,
                        url=url or None,
                        category=feed["category"],
                    ))
            except Exception as e:
                logger.debug(f"RSS {feed['name']} 异常: {e}")

        return items


# ===== 状态管理 =====

class SeenTracker:
    """已推送条目追踪（本地 JSON）"""

    def __init__(self, state_file: Path = STATE_FILE):
        self._file = state_file
        self._seen: Set[str] = set()
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                self._seen = set(data.get("seen", []))
            except Exception:
                self._seen = set()

    def _save(self):
        self._file.parent.mkdir(parents=True, exist_ok=True)
        # 只保留最近 N 条，防膨胀
        seen_list = list(self._seen)[-MAX_SEEN_ITEMS:]
        self._file.write_text(json.dumps({"seen": seen_list, "updated": _now_str()}, ensure_ascii=False))

    def is_new(self, uid: str) -> bool:
        return uid not in self._seen

    def mark_seen(self, uid: str):
        self._seen.add(uid)
        self._save()

    def mark_seen_batch(self, uids: List[str]):
        self._seen.update(uids)
        self._save()


# ===== 主控 =====

class BreakingNewsWatcher:
    """
    突发新闻监控主控
    """

    def __init__(self, feishu_webhook_url: Optional[str] = None, notifier=None):
        self._webhook = feishu_webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")
        self._notifier = notifier  # 可传入 NotificationService 实例
        self._fj = FinancialJuiceFetcher()
        self._rss = RssFetcher()
        self._tracker = SeenTracker()
        self._max_age = timedelta(hours=NEWS_MAX_AGE_HOURS)

    def run_once(self) -> int:
        """执行一次检查，返回推送条数"""
        all_items: List[NewsItem] = []

        # 1. FinancialJuice（优先）
        if self._fj.configured:
            fj_items = self._fj.fetch()
            logger.info(f"FinancialJuice: 获取 {len(fj_items)} 条")
            all_items.extend(fj_items)

        # 2. RSS 备用源
        rss_items = self._rss.fetch()
        logger.info(f"RSS: 获取 {len(rss_items)} 条")
        all_items.extend(rss_items)

        # 3. 过滤：时效 + 去重
        now = datetime.now(timezone.utc)
        new_items: List[NewsItem] = []
        for item in all_items:
            if not self._tracker.is_new(item.uid):
                continue
            if item.published:
                age = now - item.published.replace(tzinfo=timezone.utc) if item.published.tzinfo is None else now - item.published
                if age > self._max_age:
                    # 老新闻：标记已见但不推送
                    self._tracker.mark_seen(item.uid)
                    continue
            new_items.append(item)

        if not new_items:
            logger.info("无新突发新闻")
            return 0

        # 4. 按来源分组去重（相同标题不同来源只推一次）
        deduped = _dedup_by_title(new_items)
        logger.info(f"新条目（去重后）: {len(deduped)} 条")

        # 5. 推送
        pushed = 0
        for item in deduped:
            if self._push_feishu(item):
                self._tracker.mark_seen(item.uid)
                pushed += 1
                time.sleep(0.5)  # 避免频率限制

        return pushed

    def _push(self, text: str) -> bool:
        """统一推送：优先用 NotificationService，回退到 Webhook"""
        # 优先使用项目自带多渠道通知
        if self._notifier is not None:
            return self._notifier.send(text, email_send_to_all=True)
        # 回退：直接 Feishu Webhook
        if not self._webhook:
            logger.warning("未配置 FEISHU_WEBHOOK_URL，跳过推送")
            return False
        payload = {"msg_type": "text", "content": {"text": text}}
        try:
            resp = requests.post(self._webhook, json=payload, timeout=10)
            ok = resp.status_code == 200 and resp.json().get("code") == 0
            if ok:
                logger.info("推送成功")
            else:
                logger.warning(f"推送失败: {resp.text[:200]}")
            return ok
        except Exception as e:
            logger.error(f"推送异常: {e}")
        return False

    def _push_feishu(self, item: NewsItem) -> bool:
        """推送单条新闻"""
        return self._push(item.format_push())

    def push_batch_summary(self, items: List[NewsItem]) -> bool:
        """将多条新闻合并为一条汇总消息推送"""
        if not items:
            return False
        lines = [f"📡 **突发财经快讯** ({datetime.now().strftime('%H:%M')})\n"]
        for item in items:
            ts = item.published.strftime("%H:%M") if item.published else ""
            cat = f"[{item.category}] " if item.category else ""
            lines.append(f"• {ts} {cat}{item.title}")
        return self._push("\n".join(lines))


# ===== 工具函数 =====

def _make_uid(source: str, title: str) -> str:
    raw = f"{source}:{title.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def _dedup_by_title(items: List[NewsItem]) -> List[NewsItem]:
    """按标题相似度简单去重（去掉完全相同的）"""
    seen_titles: Set[str] = set()
    result: List[NewsItem] = []
    for item in items:
        key = item.title.strip().lower()[:80]
        if key not in seen_titles:
            seen_titles.add(key)
            result.append(item)
    return result
