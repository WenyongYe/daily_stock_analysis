# -*- coding: utf-8 -*-
"""
FirstSquawk / LiveSquawk 实时金融快讯抓取器
双源采集：Jina Reader (livesquawk.com) + Grok X Search (@FirstSquawk)

数据源1: https://www.livesquawk.com/latest-news （Jina Reader 抓取）
数据源2: @FirstSquawk X/Twitter 推文 （Grok x-ai/grok-4.1-fast:online via OpenRouter）
"""

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import requests

# ─── 通用配置 ────────────────────────────────────────────────
MAX_AGE_HOURS = int(os.getenv("FIRSTSQUAWK_MAX_HOURS", "24"))

# ─── Jina 配置 ──────────────────────────────────────────────
LIVESQUAWK_URL = "https://r.jina.ai/https://www.livesquawk.com/latest-news"
JINA_HEADERS = {"Accept": "text/markdown", "X-No-Cache": "true"}
JINA_TIMEOUT = 20

# ─── Grok X Search 配置 ─────────────────────────────────────
GROK_ENABLED = os.getenv("GROK_FIRSTSQUAWK_ENABLED", "false").lower() == "true"
GROK_MODEL = os.getenv("GROK_MODEL", "x-ai/grok-4.1-fast:online")
GROK_TIMEOUT = 90
GROK_PROMPT = (
    "List the 20 most important @FirstSquawk tweets from the past 24 hours. "
    "One line per tweet: time UTC - headline. "
    "Merge related tweets. No other text."
)

# Grok 响应行解析：
#   完整格式: "2026-03-01 05:23:47 UTC - headline"
#   纯时间格式: "05:23:47 UTC - headline" 或 "05:23 UTC - headline"
_GROK_LINE_FULL = re.compile(
    r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)\s*UTC\s*[-–—]\s*(.+)"
)
_GROK_LINE_TIME = re.compile(
    r"(\d{2}:\d{2}(?::\d{2})?)\s*UTC\s*[-–—]\s*(.+)"
)


# ─── Jina / LiveSquawk 解析 ─────────────────────────────────

def _parse_relative_time(text: str) -> datetime | None:
    """
    解析 livesquawk 的相对时间格式：
    - "19 hours ago"
    - "1 days 7 hours ago"
    - "2 days ago"
    - "5 mins ago"
    """
    now = datetime.now(timezone.utc)

    # "X days Y hours ago"
    m = re.match(r'(\d+)\s*days?\s+(\d+)\s*hours?\s+ago', text)
    if m:
        return now - timedelta(days=int(m.group(1)), hours=int(m.group(2)))

    # "X days ago"
    m = re.match(r'(\d+)\s*days?\s+ago', text)
    if m:
        return now - timedelta(days=int(m.group(1)))

    # "X hours ago"
    m = re.match(r'(\d+)\s*hours?\s+ago', text)
    if m:
        return now - timedelta(hours=int(m.group(1)))

    # "X mins ago" / "X minutes ago"
    m = re.match(r'(\d+)\s*min(?:ute)?s?\s+ago', text)
    if m:
        return now - timedelta(minutes=int(m.group(1)))

    return None


def _parse_livesquawk(markdown: str) -> list[dict]:
    """
    从 Jina Reader 返回的 Markdown 中提取快讯条目。

    格式规律（正向扫描）：
    - 标题行（纯文本，非 "Show Detail"/链接/空行/子弹点/日期）
    - 可选 "Show Detail"
    - 可选子弹点详情（- "xxx"）
    - 可选链接行
    - 可选日期行（28 Feb 2026）
    - 时间行（19 hours ago / 1 days 7 hours ago）
    """
    lines = markdown.split("\n")
    items = []

    # 只处理 NEWSFEED HIGHLIGHTS 到 FEATURED STORIES 之间的内容
    start_idx = 0
    end_idx = len(lines)
    for i, line in enumerate(lines):
        if "NEWSFEED HIGHLIGHTS" in line:
            start_idx = i + 1
        if "FEATURED STORIES" in line:
            end_idx = i
            break

    # 收集有效内容行（去空行）
    content_lines = []
    for i in range(start_idx, end_idx):
        stripped = lines[i].strip()
        if stripped:
            content_lines.append(stripped)

    # 跳过的行模式
    _SKIP = re.compile(
        r'^(Show Detail|View some.*|---+|\[.*\]\(.*\)|!\[.*\]|'
        r'\d{1,2}\s+\w{3}\s+\d{4}|for all the headlines.*|'
        r'NEWSFEED.*|FEATURED.*|LATEST.*|REPORTS.*)$',
        re.IGNORECASE,
    )
    _TIME = re.compile(
        r'^(\d+\s+(?:days?\s+)?(?:\d+\s+)?(?:hours?|mins?|minutes?)\s+ago)'
    )

    # 正向扫描：标题 → 详情 → 时间
    current_title = ""
    current_details = []

    for line in content_lines:
        # 时间行 → 保存当前条目
        time_match = _TIME.match(line)
        if time_match:
            dt = _parse_relative_time(time_match.group(1))
            if current_title and dt:
                items.append({
                    "title": current_title,
                    "snippet": "; ".join(current_details[:2])[:220],
                    "published": dt,
                })
            current_title = ""
            current_details = []
            continue

        # 子弹点详情
        if line.startswith("- "):
            current_details.append(line[2:].strip().strip('"'))
            continue

        # 跳过无用行
        if _SKIP.match(line):
            continue

        # 链接行单独处理（可能嵌在标题之间）
        if line.startswith("[") and line.endswith(")"):
            continue
        if line.startswith("[!["):
            continue

        # 否则是新标题（如果已有标题但还没遇到时间行，当前行可能是子标题/补充，合并）
        if not current_title:
            current_title = line
        else:
            # 已有标题，当前行是补充内容 → 保持原标题不变，把当前行当详情
            current_details.append(line)
            continue
        current_title = line
        # 清理 Markdown
        current_title = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', current_title)
        current_title = re.sub(r'\*\*(.+?)\*\*', r'\1', current_title)
        current_title = current_title.strip("# ").strip()
        current_details = []

    return items


def _fetch_jina_firstsquawk() -> list[dict]:
    """
    通过 Jina Reader 抓取 LiveSquawk 网页快讯。
    """
    try:
        resp = requests.get(LIVESQUAWK_URL, headers=JINA_HEADERS, timeout=JINA_TIMEOUT)
        if resp.status_code != 200:
            print(f"  [FirstSquawk/Jina] HTTP {resp.status_code}", file=sys.stderr)
            return []
    except Exception as e:
        print(f"  [FirstSquawk/Jina] 请求失败: {e}", file=sys.stderr)
        return []

    raw = _parse_livesquawk(resp.text)
    if not raw:
        print("  [FirstSquawk/Jina] 未解析到快讯", file=sys.stderr)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    results = []
    for item in raw:
        if item["published"] and item["published"] >= cutoff:
            results.append({
                "title": item["title"],
                "url": "",
                "snippet": item.get("snippet", ""),
                "source": "FirstSquawk",
                "published": item["published"],
                "_default_cat": None,
            })

    print(f"  [FirstSquawk/Jina] 解析 {len(raw)} 条，{len(results)} 条在 "
          f"{MAX_AGE_HOURS}h 窗口内", file=sys.stderr)
    return results


# ─── Grok X Search ──────────────────────────────────────────

def _parse_grok_response(text: str) -> list[dict]:
    """
    解析 Grok 返回的文本，提取时间+标题。
    支持格式：
      2026-03-01 05:23:47 UTC - headline text
      2026-03-01 05:23 UTC - headline text
    以及带编号前缀：1. 2026-03-01 ...  或  1) 2026-03-01 ...
    """
    # 清理 Grok reasoning 泄漏（偶尔出现的 <parameter> 标签）
    cleaned = re.sub(r'<parameter[^>]*>.*?</parameter>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'</?xai:[^>]*>', '', cleaned)

    today = datetime.now(timezone.utc).date()
    items = []
    for line in cleaned.strip().splitlines():
        line = line.strip()
        # 去掉编号前缀: "1. ", "1) ", "- ", "* "
        line = re.sub(r'^[\d]+[.)]\s*', '', line)
        line = re.sub(r'^[-*]\s+', '', line)
        # 去掉 Markdown 链接引用 [[1]](url)
        line = re.sub(r'\[\[\d+\]\]\([^)]*\)', '', line).strip()

        # 尝试完整格式: "2026-03-01 05:23:47 UTC - ..."
        m = _GROK_LINE_FULL.match(line)
        if m:
            time_str = m.group(1).strip()
            headline = m.group(2).strip()
            dt = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(time_str, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            if dt and headline:
                items.append({"title": headline, "published": dt, "snippet": ""})
            continue

        # 尝试纯时间格式: "05:23:47 UTC - ..." 或 "05:23 UTC - ..."
        m = _GROK_LINE_TIME.match(line)
        if m:
            time_str = m.group(1).strip()
            headline = m.group(2).strip()
            dt = None
            for fmt in ("%H:%M:%S", "%H:%M"):
                try:
                    t = datetime.strptime(time_str, fmt).time()
                    dt = datetime.combine(today, t, tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
            if dt and headline:
                items.append({"title": headline, "published": dt, "snippet": ""})

    return items


def _fetch_grok_firstsquawk() -> list[dict]:
    """
    通过 OpenRouter 调用 Grok X Search 搜索 @FirstSquawk 推文。
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

    if not api_key:
        print("  [FirstSquawk/X] 无 API key，跳过", file=sys.stderr)
        return []

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROK_MODEL,
                "messages": [{"role": "user", "content": GROK_PROMPT}],
                "temperature": 0.1,
                "max_tokens": 2500,
            },
            timeout=GROK_TIMEOUT,
        )
        if resp.status_code != 200:
            print(f"  [FirstSquawk/X] HTTP {resp.status_code}: "
                  f"{resp.text[:200]}", file=sys.stderr)
            return []
    except Exception as e:
        print(f"  [FirstSquawk/X] 请求失败: {e}", file=sys.stderr)
        return []

    data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    raw = _parse_grok_response(content)

    if not raw:
        print("  [FirstSquawk/X] 未解析到推文", file=sys.stderr)
        return []

    # 过滤时间窗口
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)
    results = []
    for item in raw:
        if item["published"] >= cutoff:
            results.append({
                "title": item["title"],
                "url": "",
                "snippet": "",
                "source": "FirstSquawk/X",
                "published": item["published"],
                "_default_cat": None,
            })

    # 日志：含成本信息
    cost = data.get("usage", {}).get("cost", 0)
    cost_str = f"，cost ${cost:.4f}" if cost else ""
    print(f"  [FirstSquawk/X] 解析 {len(raw)} 条，{len(results)} 条在 "
          f"{MAX_AGE_HOURS}h 窗口内{cost_str}", file=sys.stderr)
    return results


# ─── 统一入口 ────────────────────────────────────────────────

def fetch_firstsquawk_tweets() -> list[dict]:
    """
    抓取 FirstSquawk 快讯，双源并发：Jina (LiveSquawk网页) + Grok (X推文搜索)。
    Grok 默认关闭，通过 GROK_FIRSTSQUAWK_ENABLED=true 开启。
    任一源失败不影响另一源。

    Returns:
        list[dict]: [{title, url, snippet, source, published, _default_cat}, ...]
    """
    tasks = {"Jina": _fetch_jina_firstsquawk}
    if GROK_ENABLED:
        tasks["Grok"] = _fetch_grok_firstsquawk

    all_items = []
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(fn): name for name, fn in tasks.items()}
        for f in as_completed(futs):
            name = futs[f]
            try:
                items = f.result(timeout=95)
                all_items.extend(items)
            except Exception as e:
                print(f"  [FirstSquawk/{name}] 异常: {e}", file=sys.stderr)

    return all_items
