# -*- coding: utf-8 -*-
"""
新闻数据 Provider
多源聚合：RSS（复用 src.breaking_news.RssFetcher）+ Tavily/Brave 搜索 + FT 回退
并做“重要性评分 + 去重 + 限额”，聚焦突发财经/宏观/地缘政治新闻
"""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except Exception:
    pass

# 确保能 import src 模块
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _make_service():
    """构造搜索 Provider（优先 Tavily，次选 Brave）"""
    tavily_keys = [
        k.strip() for k in os.getenv("TAVILY_API_KEYS", "").split(",")
        if k.strip() and k.strip() != "your_tavily_key_here"
    ]
    brave_keys = [
        k.strip() for k in os.getenv("BRAVE_API_KEYS", "").split(",")
        if k.strip() and k.strip() != "your_brave_key_here"
    ]

    try:
        if tavily_keys:
            from src.search_service import TavilySearchProvider
            return TavilySearchProvider(tavily_keys)
        if brave_keys:
            from src.search_service import BraveSearchProvider
            return BraveSearchProvider(brave_keys)
    except ImportError as e:
        print(f"  [NewsProvider] import 失败: {e}", file=sys.stderr)
    return None


# 搜索查询词（每组: 查询词, 默认分类）
SEARCH_QUERIES: list[tuple[str, str]] = [
    ("breaking US stock market news Wall Street today", "美股动态"),
    ("Federal Reserve FOMC inflation CPI payroll macro news today", "央行政策"),
    ("geopolitical risk sanctions trade war conflict oil shipping disruption", "地缘风险"),
    ("oil gold commodity prices OPEC supply shock today", "大宗商品"),
    ("AI semiconductor NVIDIA Apple Microsoft earnings surprise today", "科技行业"),
]

# 主题分类关键词（小写匹配）
CATEGORY_RULES = {
    "美股动态": [
        "s&p", "nasdaq", "dow", "wall street", "stock", "rally", "sell-off",
        "selloff", "equit", "bull", "bear market", "futures", "volatility"
    ],
    "央行政策": [
        "fed", "ecb", "boj", "rate", "fomc", "inflation", "cpi", "pce", "gdp",
        "monetary", "central bank", "powell", "lagarde", "payroll", "jobless"
    ],
    "地缘风险": [
        "tariff", "sanction", "war", "geopolitical", "trade war", "china", "russia",
        "ukraine", "middle east", "conflict", "tension", "missile", "shipping lane"
    ],
    "大宗商品": [
        "oil", "gold", "copper", "commodity", "opec", "crude", "energy", "silver",
        "natural gas", "brent", "wti", "supply"
    ],
    "科技行业": [
        "ai", "tech", "nvidia", "apple", "microsoft", "tesla", "semiconductor", "chip",
        "google", "amazon", "meta", "openai"
    ],
}

# 分类展示顺序和 emoji
CATEGORY_ORDER = [
    ("地缘风险", "🌍"),
    ("央行政策", "🏦"),
    ("美股动态", "📈"),
    ("大宗商品", "⛽"),
    ("科技行业", "💻"),
    ("其他", "📌"),
]

# 过滤掉导航/首页类 URL（正则匹配 url）
_SKIP_URL_PATTERNS = [
    r"\.com/?$",                 # 纯域名首页
    r"\.com/markets/?$",
    r"\.com/news/?$",
    r"\.com/economy/?$",
    r"federalreserve\.gov/monetarypolicy/implementation",
    r"schwab\.com/learn",
    r"tradingeconomics\.com/united-states/?$",
]

# 来源/站点权重（可信度+时效）
SOURCE_WEIGHTS = {
    "FinancialJuice": 3.2,
    "Reuters": 2.8,
    "FT": 2.6,
    "FT Markets": 2.6,
    "CNBC Markets": 2.4,
    "MarketWatch": 2.0,
    "Yahoo Finance": 1.8,
    "Investing.com News": 1.6,
    "Tavily": 1.2,
    "Brave": 1.2,
}

DOMAIN_WEIGHTS = {
    "reuters.com": 2.2,
    "ft.com": 2.0,
    "cnbc.com": 1.8,
    "bloomberg.com": 1.8,
    "wsj.com": 1.8,
    "marketwatch.com": 1.3,
    "finance.yahoo.com": 1.2,
    "investing.com": 1.0,
    "tradingeconomics.com": 0.5,
}

CATEGORY_WEIGHTS = {
    "地缘风险": 2.8,
    "央行政策": 2.6,
    "美股动态": 2.0,
    "大宗商品": 1.8,
    "科技行业": 1.4,
    "其他": 0.8,
}

BREAKING_KEYWORDS = [
    "breaking", "urgent", "shock", "surge", "plunge", "warning", "escalate",
    "attack", "strike", "ceasefire", "emergency", "defaults", "collapse",
]

MACRO_KEYWORDS = [
    "fed", "fomc", "cpi", "pce", "inflation", "payroll", "jobless", "yield",
    "interest rate", "treasury", "central bank",
]

GEO_KEYWORDS = [
    "war", "sanction", "tariff", "middle east", "ukraine", "russia", "china",
    "shipping", "strait", "conflict", "geopolitical",
]

# 最终条数控制
MAX_TOTAL_NEWS = int(os.getenv("MARKET_NEWS_MAX_ITEMS", "15"))
MAX_PER_SOURCE = int(os.getenv("MARKET_NEWS_MAX_PER_SOURCE", "4"))
MAX_PER_CATEGORY = {
    "地缘风险": 4,
    "央行政策": 4,
    "美股动态": 4,
    "大宗商品": 3,
    "科技行业": 2,
    "其他": 2,
}
MIN_IMPORTANCE_SCORE = float(os.getenv("MARKET_NEWS_MIN_SCORE", "2.2"))

FT_URL = "https://r.jina.ai/https://www.ft.com/markets"
JINA_HEADERS = {"Accept": "text/markdown", "X-No-Cache": "true"}


def _classify(title: str, snippet: str = "") -> str:
    """根据标题/摘要关键词匹配分类"""
    lower = f"{title} {snippet}".lower()
    for cat, keywords in CATEGORY_RULES.items():
        if any(kw in lower for kw in keywords):
            return cat
    return "其他"


def _title_fingerprint(title: str) -> str:
    """生成标题指纹用于模糊去重"""
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", title.lower())
    return t[:72]


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        d = urlparse(url).netloc.lower()
        if d.startswith("www."):
            d = d[4:]
        return d
    except Exception:
        return ""


def _compute_recency_score(item: dict) -> float:
    """时间新鲜度评分（仅 RSS/可解析时间生效）"""
    published = item.get("published")
    if not published:
        return 0.0
    try:
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
        if age_hours <= 2:
            return 2.0
        if age_hours <= 6:
            return 1.2
        if age_hours <= 24:
            return 0.6
        if age_hours <= 48:
            return 0.2
        return -0.8
    except Exception:
        return 0.0


def _score_item(item: dict) -> float:
    """重要性评分：分类+来源+域名+关键词+时效"""
    title = item.get("title", "")
    snippet = item.get("snippet", "")
    text = f"{title} {snippet}".lower()
    source = item.get("source", "")
    category = item.get("category", "其他")
    domain = _extract_domain(item.get("url", ""))

    score = 0.0
    score += CATEGORY_WEIGHTS.get(category, 0.8)
    score += SOURCE_WEIGHTS.get(source, 0.9)
    score += DOMAIN_WEIGHTS.get(domain, 0.0)
    score += _compute_recency_score(item)

    # 关键词增强
    if any(k in text for k in BREAKING_KEYWORDS):
        score += 1.6
    if any(k in text for k in MACRO_KEYWORDS):
        score += 1.2
    if any(k in text for k in GEO_KEYWORDS):
        score += 1.4

    # 标题过短通常是导航页/噪音
    if len(title.strip()) < 24:
        score -= 0.6

    return round(score, 3)


def _fetch_rss() -> list[dict]:
    """通过 RssFetcher 拉取 RSS 新闻"""
    try:
        from src.breaking_news import RssFetcher
        fetcher = RssFetcher()
        items = fetcher.fetch()
        results = []
        for item in items:
            results.append({
                "title": item.title,
                "url": item.url or "",
                "snippet": "",
                "source": item.source,
                "published": item.published,
                "_default_cat": item.category if item.category in CATEGORY_RULES else None,
            })
        return results
    except Exception as e:
        print(f"  [NewsProvider] RSS 拉取失败: {e}", file=sys.stderr)
        return []


def _search_via_service(queries: list[tuple[str, str]], max_per_query: int = 3) -> list[dict]:
    """通过 SearchProvider 搜索新闻，每条带默认分类"""
    results = []
    service = _make_service()
    if not service:
        return []

    try:
        for q, default_cat in queries:
            resp = service.search(q, max_results=max_per_query, days=1)
            for item in resp.results:
                url = getattr(item, "url", "")
                if any(re.search(p, url) for p in _SKIP_URL_PATTERNS):
                    continue
                results.append({
                    "title": item.title,
                    "url": url,
                    "snippet": (item.snippet[:220] if hasattr(item, "snippet") and item.snippet else ""),
                    "source": "Tavily",
                    "published": None,
                    "_default_cat": default_cat,
                })
    except Exception as e:
        print(f"  [NewsProvider] search 错误: {e}", file=sys.stderr)
    return results


def _fetch_ft_headlines() -> list[dict]:
    """兜底：从 FT 抓取 Most Read 标题"""
    try:
        r = requests.get(FT_URL, headers=JINA_HEADERS, timeout=20)
        raw = re.findall(r'\*\s+\[([^\]]{20,})\]\(https://www\.ft\.com/content/([^\)]+)\)', r.text)
        seen = set()
        results = []
        for title, slug in raw:
            if title in seen or title.endswith("?"):
                continue
            seen.add(title)
            results.append({
                "title": title,
                "url": f"https://www.ft.com/content/{slug}",
                "snippet": "",
                "source": "FT",
                "published": None,
            })
        return results[:10]
    except Exception as e:
        print(f"  [NewsProvider] FT 抓取失败: {e}", file=sys.stderr)
        return []


def _dedup_classify_score(items: list[dict]) -> list[dict]:
    """去重 + 分类 + 打分"""
    seen_fp = set()
    seen_url = set()
    unique = []

    for item in items:
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        if not title:
            continue

        fp = _title_fingerprint(title)
        if not fp:
            continue
        if fp in seen_fp:
            continue

        norm_url = re.sub(r"[?#].*$", "", url)
        if norm_url and norm_url in seen_url:
            continue

        seen_fp.add(fp)
        if norm_url:
            seen_url.add(norm_url)

        # 分类：关键词优先，其次默认分类
        cat = _classify(title, item.get("snippet", ""))
        if cat == "其他" and item.get("_default_cat"):
            cat = item.get("_default_cat")
        item["category"] = cat
        item.pop("_default_cat", None)

        # 打分
        item["importance_score"] = _score_item(item)
        unique.append(item)

    return unique


def _select_focus_items(items: list[dict], limit: int = MAX_TOTAL_NEWS) -> list[dict]:
    """
    选择最终新闻：
    - 按重要性降序
    - 每个来源/分类限额
    - 阈值过滤
    """
    if not items:
        return []

    ranked = sorted(items, key=lambda x: x.get("importance_score", 0.0), reverse=True)

    selected = []
    source_count: dict[str, int] = {}
    cat_count: dict[str, int] = {}

    for item in ranked:
        score = item.get("importance_score", 0.0)
        if score < MIN_IMPORTANCE_SCORE:
            continue

        src = item.get("source", "Unknown")
        cat = item.get("category", "其他")

        if source_count.get(src, 0) >= MAX_PER_SOURCE:
            continue
        if cat_count.get(cat, 0) >= MAX_PER_CATEGORY.get(cat, 2):
            continue

        selected.append(item)
        source_count[src] = source_count.get(src, 0) + 1
        cat_count[cat] = cat_count.get(cat, 0) + 1

        if len(selected) >= limit:
            break

    # 如果阈值太严导致条数不足，补齐（不再看阈值，但保留来源/分类限额）
    if len(selected) < min(8, limit):
        for item in ranked:
            if item in selected:
                continue
            src = item.get("source", "Unknown")
            cat = item.get("category", "其他")
            if source_count.get(src, 0) >= MAX_PER_SOURCE:
                continue
            if cat_count.get(cat, 0) >= MAX_PER_CATEGORY.get(cat, 2):
                continue
            selected.append(item)
            source_count[src] = source_count.get(src, 0) + 1
            cat_count[cat] = cat_count.get(cat, 0) + 1
            if len(selected) >= limit:
                break

    return selected


class NewsProvider:
    """市场新闻拉取器：RSS + 搜索多源聚合（突发/宏观/地缘优先）"""

    def __init__(self, queries: list[tuple[str, str]] | None = None, max_per_query: int = 3):
        self.queries = queries or SEARCH_QUERIES
        self.max_per_query = max_per_query

    def fetch(self) -> list[dict]:
        """
        拉取新闻列表

        Returns:
            list[dict]: [{title, url, snippet, source, category, importance_score}, ...]
        """
        all_items = []

        # 1) RSS 主源
        rss_items = _fetch_rss()
        if rss_items:
            print(f"  [NewsProvider] RSS 获取 {len(rss_items)} 条", file=sys.stderr)
        all_items.extend(rss_items)

        # 2) 搜索补充（Tavily/Brave）
        search_items = _search_via_service(self.queries, self.max_per_query)
        if search_items:
            print(f"  [NewsProvider] Search 获取 {len(search_items)} 条", file=sys.stderr)
        all_items.extend(search_items)

        # 3) 都失败才回退 FT
        if not all_items:
            ft_items = _fetch_ft_headlines()
            if ft_items:
                print(f"  [NewsProvider] FT 回退获取 {len(ft_items)} 条", file=sys.stderr)
            all_items.extend(ft_items)

        # 去重 + 分类 + 打分 + 聚焦筛选
        enriched = _dedup_classify_score(all_items)
        selected = _select_focus_items(enriched, limit=MAX_TOTAL_NEWS)

        sources = sorted(set(item.get("source", "") for item in selected)) or ["none"]
        avg_score = (sum(i.get("importance_score", 0) for i in selected) / len(selected)) if selected else 0.0
        print(
            f"  [NewsProvider] 最终 {len(selected)} 条新闻（来源: {', '.join(sources)}，平均分: {avg_score:.2f}）",
            file=sys.stderr,
        )

        return selected
