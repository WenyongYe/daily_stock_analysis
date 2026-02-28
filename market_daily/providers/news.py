# -*- coding: utf-8 -*-
"""
新闻数据 Provider
多源聚合：RSS（复用 src.breaking_news.RssFetcher）+ Tavily/Brave 搜索 + FT 回退
按主题分类返回 15-20 条新闻
"""

import re
import sys
from pathlib import Path

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
    import os
    tavily_keys = [k.strip() for k in os.getenv("TAVILY_API_KEYS", "").split(",")
                   if k.strip() and k.strip() != "your_tavily_key_here"]
    brave_keys  = [k.strip() for k in os.getenv("BRAVE_API_KEYS", "").split(",")
                   if k.strip() and k.strip() != "your_brave_key_here"]
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

_SEARCH_AVAILABLE = True  # 运行时动态检测

# 搜索查询词（每组: 查询词, 默认分类）
SEARCH_QUERIES = [
    ("US stock market Wall Street today",              "美股动态"),
    ("Federal Reserve interest rate monetary policy",   "央行政策"),
    ("geopolitical risk trade war tariff sanctions",    "地缘风险"),
    ("oil gold commodity prices OPEC",                  "大宗商品"),
    ("AI tech earnings NVIDIA Apple Tesla",             "科技行业"),
]

# 主题分类关键词（小写匹配）
CATEGORY_RULES = {
    "美股动态": ["s&p", "nasdaq", "dow", "wall street", "stock", "rally", "sell-off",
                "selloff", "equit", "bull", "bear market"],
    "央行政策": ["fed", "ecb", "boj", "rate", "fomc", "inflation", "cpi", "gdp",
                "monetary", "central bank", "powell", "lagarde"],
    "地缘风险": ["tariff", "sanction", "war", "geopolitical", "trade war", "china",
                "russia", "ukraine", "middle east", "conflict", "tension"],
    "大宗商品": ["oil", "gold", "copper", "commodity", "opec", "crude", "energy",
                "silver", "natural gas", "brent", "wti"],
    "科技行业": ["ai", "tech", "nvidia", "apple", "microsoft", "tesla", "semiconductor",
                "chip", "google", "amazon", "meta", "openai"],
}

# 分类展示顺序和 emoji
CATEGORY_ORDER = [
    ("美股动态", "📈"),
    ("央行政策", "🏦"),
    ("地缘风险", "🌍"),
    ("大宗商品", "⛽"),
    ("科技行业", "💻"),
    ("其他",     "📌"),
]

# 过滤掉导航/首页类 URL（正则匹配 url）
_SKIP_URL_PATTERNS = [
    r"\.com/?$",               # 纯域名首页
    r"\.com/markets/?$",
    r"\.com/news/?$",
    r"federalreserve\.gov/monetarypolicy/implementation",
    r"schwab\.com/learn",
    r"tradingeconomics\.com/united-states/?$",
]

FT_URL = "https://r.jina.ai/https://www.ft.com/markets"
JINA_HEADERS = {"Accept": "text/markdown", "X-No-Cache": "true"}


def _classify(title: str) -> str:
    """根据标题关键词匹配分类"""
    lower = title.lower()
    for cat, keywords in CATEGORY_RULES.items():
        if any(kw in lower for kw in keywords):
            return cat
    return "其他"


def _title_fingerprint(title: str) -> str:
    """生成标题指纹用于模糊去重：去除标点、空格、转小写，取前60字符"""
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", title.lower())
    return t[:60]


def _fetch_rss() -> list[dict]:
    """通过 RssFetcher 拉取 RSS 新闻"""
    try:
        from src.breaking_news import RssFetcher
        fetcher = RssFetcher()
        items = fetcher.fetch()
        results = []
        for item in items:
            results.append({
                "title":   item.title,
                "url":     item.url or "",
                "snippet": "",
                "source":  item.source,
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
                # 过滤导航首页类链接
                if any(re.search(p, url) for p in _SKIP_URL_PATTERNS):
                    continue
                results.append({
                    "title":   item.title,
                    "url":     url,
                    "snippet": (item.snippet[:200] if hasattr(item, "snippet") and item.snippet else ""),
                    "source":  "Tavily",
                    "_default_cat": default_cat,
                })
    except Exception as e:
        print(f"  [NewsProvider] search 错误: {e}", file=sys.stderr)
    return results


def _fetch_ft_headlines() -> list[dict]:
    """降级：从 FT 抓取 Most Read 标题"""
    try:
        r = requests.get(FT_URL, headers=JINA_HEADERS, timeout=20)
        raw = re.findall(r'\*\s+\[([^\]]{20,})\]\(https://www\.ft\.com/content/([^\)]+)\)', r.text)
        seen = set()
        results = []
        for title, slug in raw:
            if title not in seen and not title.endswith("?"):
                seen.add(title)
                results.append({
                    "title":   title,
                    "url":     f"https://www.ft.com/content/{slug}",
                    "snippet": "",
                    "source":  "FT",
                })
        return results[:8]
    except Exception as e:
        print(f"  [NewsProvider] FT 抓取失败: {e}", file=sys.stderr)
        return []


def _dedup_and_classify(items: list[dict]) -> list[dict]:
    """去重（标题指纹相似度）并分类"""
    seen_fps = set()
    unique = []
    for item in items:
        fp = _title_fingerprint(item["title"])
        if fp in seen_fps or not fp:
            continue
        seen_fps.add(fp)
        # 分类：优先关键词匹配，回退到搜索查询的默认分类
        cat = _classify(item["title"])
        if cat == "其他" and "_default_cat" in item:
            cat = item.pop("_default_cat")
        else:
            item.pop("_default_cat", None)
        item["category"] = cat
        unique.append(item)
    return unique


class NewsProvider:
    """市场新闻拉取器：RSS + 搜索多源聚合"""

    def __init__(self, queries: list[tuple[str, str]] | None = None, max_per_query: int = 3):
        self.queries       = queries or SEARCH_QUERIES
        self.max_per_query = max_per_query

    def fetch(self) -> list[dict]:
        """
        拉取新闻列表

        Returns:
            list[dict]: [{title, url, snippet, source, category}, ...]
        """
        all_items = []

        # 1. RSS 源（主力）
        rss_items = _fetch_rss()
        if rss_items:
            print(f"  [NewsProvider] RSS 获取 {len(rss_items)} 条", file=sys.stderr)
        all_items.extend(rss_items)

        # 2. Tavily/Brave 搜索（补充）
        if _SEARCH_AVAILABLE:
            search_items = _search_via_service(self.queries, self.max_per_query)
            if search_items:
                print(f"  [NewsProvider] Search 获取 {len(search_items)} 条", file=sys.stderr)
            all_items.extend(search_items)

        # 3. 如果两个源都没数据，降级到 FT
        if not all_items:
            ft_items = _fetch_ft_headlines()
            if ft_items:
                print(f"  [NewsProvider] FT 回退获取 {len(ft_items)} 条", file=sys.stderr)
            all_items.extend(ft_items)

        # 去重 + 分类
        unique = _dedup_and_classify(all_items)

        sources = set(item["source"] for item in unique) if unique else {"none"}
        print(f"  [NewsProvider] 最终 {len(unique)} 条新闻（来源: {', '.join(sources)}）", file=sys.stderr)
        return unique[:20]
