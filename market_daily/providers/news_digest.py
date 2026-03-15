# -*- coding: utf-8 -*-
"""
新闻精选 Pipeline — NewsDigestPipeline
两阶段筛选：多源聚合 50-100 条 → 本地粗筛 ~25 条 → LLM 精选 ~10 条中文分类摘要

用法:
  # 独立运行（调试）
  python -m market_daily.providers.news_digest

  # 在 market_daily.py 中调用
  from market_daily.providers.news_digest import NewsDigestPipeline
  result = NewsDigestPipeline().run()
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except Exception:
    pass

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from market_daily.providers.news import (
    SEARCH_QUERIES_EXTENDED,
    CATEGORY_ORDER,
    _fetch_rss,
    _fetch_ft_headlines,
    _fetch_reuters_headlines,
    _search_via_service,
    _dedup_classify_score,
    _select_focus_items,
    _title_fingerprint,
)

try:
    from market_daily.providers.twitter_firstsquawk import fetch_firstsquawk_tweets
except ImportError:
    def fetch_firstsquawk_tweets():
        return []

# ─── 配置 ────────────────────────────────────────────────────
CACHE_FILE = Path(os.getenv("NEWS_DIGEST_CACHE", "data/news_digest_cache.json"))
CACHE_MAX_ITEMS = 500
CACHE_MAX_AGE_HOURS = 24
STAGE1_LIMIT = 25          # 阶段一粗筛输出数
DIGEST_TARGET = 10          # 阶段二 LLM 目标输出数
MAX_PER_QUERY = 8           # Tavily 每组查询返回数


# ─── 24h 缓存 ────────────────────────────────────────────────

def _load_cache() -> dict:
    """加载缓存，返回 {fingerprint: {title, url, source, fetched_at, ...}}"""
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        print("  [NewsDigest] 缓存文件损坏，忽略", file=sys.stderr)
        return {}


def _save_cache(cache: dict):
    """保存缓存，自动清理过期条目"""
    now = datetime.now(timezone.utc).isoformat()
    cutoff = (datetime.now(timezone.utc).timestamp()
              - CACHE_MAX_AGE_HOURS * 3600)

    # 清理过期
    cleaned = {}
    for fp, item in cache.items():
        fetched_at = item.get("fetched_at", "")
        try:
            ts = datetime.fromisoformat(fetched_at).timestamp()
            if ts >= cutoff:
                cleaned[fp] = item
        except (ValueError, TypeError):
            cleaned[fp] = item  # 无法解析时间的保留

    # 限额：保留最新的 CACHE_MAX_ITEMS 条
    if len(cleaned) > CACHE_MAX_ITEMS:
        sorted_items = sorted(
            cleaned.items(),
            key=lambda x: x[1].get("fetched_at", ""),
            reverse=True,
        )
        cleaned = dict(sorted_items[:CACHE_MAX_ITEMS])

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def _cleanup_expired(cache: dict) -> dict:
    """清理超过 24h 的旧条目"""
    cutoff = (datetime.now(timezone.utc).timestamp()
              - CACHE_MAX_AGE_HOURS * 3600)
    return {
        fp: item for fp, item in cache.items()
        if _parse_ts(item.get("fetched_at", "")) >= cutoff
    }


def _parse_ts(iso_str: str) -> float:
    try:
        return datetime.fromisoformat(iso_str).timestamp()
    except (ValueError, TypeError):
        return 0.0


# ─── 聚合器 ──────────────────────────────────────────────────

class NewsAggregator:
    """多源并发新闻抓取，目标 50-100 条"""

    def __init__(self, queries=None, max_per_query: int = MAX_PER_QUERY):
        self.queries = queries or SEARCH_QUERIES_EXTENDED
        self.max_per_query = max_per_query

    def fetch_all(self) -> list[dict]:
        """并发抓取所有源，返回去重后的原始新闻列表"""
        all_items = []
        stats = {}

        with ThreadPoolExecutor(max_workers=5) as ex:
            fut_rss = ex.submit(_fetch_rss)
            fut_search = ex.submit(
                _search_via_service, self.queries, self.max_per_query
            )
            fut_ft = ex.submit(_fetch_ft_headlines)
            fut_reuters = ex.submit(_fetch_reuters_headlines)
            fut_firstsquawk = ex.submit(fetch_firstsquawk_tweets)

            for name, fut in [
                ("RSS", fut_rss),
                ("Search", fut_search),
                ("FT", fut_ft),
                ("Reuters", fut_reuters),
                ("FirstSquawk", fut_firstsquawk),
            ]:
                try:
                    # FirstSquawk 内部并发 Jina+Grok，Grok 可能需要 60-90s
                    t = 100 if name == "FirstSquawk" else 35
                    items = fut.result(timeout=t)
                    stats[name] = len(items)
                    all_items.extend(items)
                except Exception as e:
                    stats[name] = f"失败: {e}"
                    print(f"  [NewsAggregator] {name} 错误: {e}",
                          file=sys.stderr)

        # 统计日志
        for name, count in stats.items():
            print(f"  [NewsAggregator] {name}: {count} 条", file=sys.stderr)
        print(f"  [NewsAggregator] 原始总计: {len(all_items)} 条",
              file=sys.stderr)

        # 去重 + 分类 + 打分
        enriched = _dedup_classify_score(all_items)
        print(f"  [NewsAggregator] 去重后: {len(enriched)} 条",
              file=sys.stderr)
        return enriched


# ─── LLM 精选 ────────────────────────────────────────────────

_DIGEST_PROMPT = (
    "你是资深金融新闻编辑。请从以下候选新闻中精选最重要的 8-12 条，生成中文分类摘要。\n\n"
    "## 筛选标准\n"
    "1. 优先选择对全球金融市场有直接影响的新闻（央行决策、重大经济数据、地缘冲突、大型并购、市场剧烈波动）\n"
    "2. 忽略软新闻、评论文章、市场噪音和广告\n"
    "3. 如果多条新闻报道同一事件，合并为一条综合摘要\n\n"
    "## 输出格式\n"
    "按主题分类，使用 emoji 标注类别：\n"
    "🌍 地缘风险 | 🏦 央行政策 | 📈 市场走势 | ⛽ 大宗商品 | 💻 科技行业 | 🏢 企业动态 | 🌏 欧亚市场 | ₿ 加密货币 | 💵 债券外汇\n\n"
    "## 要求\n"
    "- 每条用一句简洁中文概括核心信息（不超过 30 字）\n"
    "- 不要输出英文原文、链接或来源标注\n"
    "- 直接输出分类结果，不要加标题、前言或总结\n"
    "- 同类别的新闻放在一起\n\n"
    "## 候选新闻\n"
)


def _build_llm_prompt(candidates: list[dict]) -> str:
    """构建 LLM 精选 prompt"""
    prompt = _DIGEST_PROMPT
    for i, item in enumerate(candidates, 1):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        cat = item.get("category", "其他")
        score = item.get("importance_score", 0)
        line = f"{i}. [{cat}] {title}"
        if snippet:
            line += f" — {snippet[:100]}"
        prompt += line + "\n"
    return prompt


def _call_llm(prompt: str) -> str | None:
    """调用 LLM API，优先 AIHUBMIX_KEY，次选 OPENAI_API_KEY"""
    api_key = os.getenv("AIHUBMIX_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        print("  [NewsDigest] 无 LLM API key，跳过阶段二", file=sys.stderr)
        return None

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1200,
            },
            timeout=45,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content:
                print(f"  [NewsDigest] LLM 精选完成（{len(content)} 字符）",
                      file=sys.stderr)
                return content
        else:
            print(f"  [NewsDigest] LLM API 返回 {resp.status_code}: "
                  f"{resp.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"  [NewsDigest] LLM 调用失败: {e}", file=sys.stderr)

    return None


# ─── Pipeline 编排 ───────────────────────────────────────────

class NewsDigestPipeline:
    """
    新闻精选 Pipeline：
    1. 多源聚合抓取 50-100 条
    2. 阶段一：本地评分粗筛 ~25 条
    3. 阶段二：LLM 精选总结 ~10 条中文摘要

    返回值兼容 market_daily.py 的 news_summary 参数：
    - str：LLM 中文分类摘要
    - list[str]：回退时的英文标题列表
    """

    def __init__(self, queries=None, max_per_query: int = MAX_PER_QUERY,
                 stage1_limit: int = STAGE1_LIMIT,
                 digest_target: int = DIGEST_TARGET,
                 use_cache: bool = True):
        self.aggregator = NewsAggregator(queries, max_per_query)
        self.stage1_limit = stage1_limit
        self.digest_target = digest_target
        self.use_cache = use_cache

    def run(self) -> str | list[str]:
        """执行完整 pipeline，返回中文摘要(str)或英文标题列表(list)"""
        t0 = time.time()

        # 加载缓存
        cache = _load_cache() if self.use_cache else {}
        cache_before = len(cache)

        # 1. 多源聚合
        all_news = self.aggregator.fetch_all()

        # 合并缓存中的新闻（不重复抓取，但参与筛选）
        now_iso = datetime.now(timezone.utc).isoformat()
        new_count = 0
        for item in all_news:
            fp = _title_fingerprint(item.get("title", ""))
            if fp and fp not in cache:
                cache[fp] = {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                    "category": item.get("category", ""),
                    "importance_score": item.get("importance_score", 0),
                    "fetched_at": now_iso,
                }
                new_count += 1

        print(f"  [NewsDigest] 缓存: {cache_before} 已有 + {new_count} 新增",
              file=sys.stderr)

        # 保存缓存
        if self.use_cache:
            _save_cache(cache)

        # 2. 阶段一：本地粗筛
        if len(all_news) <= 20:
            # 新闻不足，跳过粗筛直接全部送 LLM
            candidates = sorted(
                all_news,
                key=lambda x: x.get("importance_score", 0),
                reverse=True,
            )
            print(f"  [NewsDigest] 新闻不足 20 条，跳过粗筛，"
                  f"直接送 LLM {len(candidates)} 条", file=sys.stderr)
        else:
            candidates = _select_focus_items(all_news, limit=self.stage1_limit)
            print(f"  [NewsDigest] 阶段一粗筛: {len(all_news)} → "
                  f"{len(candidates)} 条", file=sys.stderr)

        if not candidates:
            print("  [NewsDigest] 无候选新闻", file=sys.stderr)
            return []

        # 3. 阶段二：LLM 精选
        prompt = _build_llm_prompt(candidates)
        result = _call_llm(prompt)

        elapsed = time.time() - t0
        if result:
            print(f"  [NewsDigest] 完成 ({elapsed:.1f}s): "
                  f"{len(all_news)} 原始 → {len(candidates)} 粗筛 → LLM 精选",
                  file=sys.stderr)
            return result
        else:
            # 回退：返回前 N 条英文标题
            fallback = [item["title"] for item in candidates[:self.digest_target]]
            print(f"  [NewsDigest] LLM 回退 ({elapsed:.1f}s): "
                  f"返回前 {len(fallback)} 条英文标题", file=sys.stderr)
            return fallback


# ─── CLI 入口 ────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60, file=sys.stderr)
    print("  NewsDigest Pipeline — 独立运行模式", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    pipeline = NewsDigestPipeline()
    result = pipeline.run()

    print("\n" + "=" * 60)
    print("  最终输出")
    print("=" * 60)

    if isinstance(result, str):
        print(result)
    elif isinstance(result, list):
        print(f"[回退模式] {len(result)} 条英文标题:")
        for i, title in enumerate(result, 1):
            print(f"  {i}. {title}")
    else:
        print("无结果")
