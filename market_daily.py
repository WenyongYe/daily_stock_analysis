#!/usr/bin/env python3
"""
金融市场日报生成器 - market_daily.py
按标准模板生成完整日报：行情 + 宏观事件 + 新闻 + 主题分析 + 后续关注

用法:
  python market_daily.py                  # 打印到终端
  python market_daily.py --output report  # 保存到 reports/market_daily_YYYYMMDD.md
  python market_daily.py --feishu         # 推送到飞书 Webhook
"""

import argparse
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
import yfinance as yf

# ─── 标的配置 ────────────────────────────────────────────────
SYMBOLS = {
    # 美股
    "sp500":   ("^GSPC",    "S&P 500"),
    "nasdaq":  ("^IXIC",    "NASDAQ"),
    "dji":     ("^DJI",     "Dow Jones"),
    "russell": ("^RUT",     "Russell 2000"),
    "vix":     ("^VIX",     "VIX 恐慌指数"),
    # 欧亚
    "stoxx":   ("^STOXX",   "Euro STOXX 600"),
    "dax":     ("^GDAXI",   "DAX"),
    "ftse":    ("^FTSE",    "FTSE 100"),
    "nikkei":  ("^N225",    "Nikkei 225"),
    "hsi":     ("^HSI",     "恒生指数"),
    # 商品
    "gold":    ("GC=F",     "黄金 Gold"),
    "silver":  ("SI=F",     "白银 Silver"),
    "brent":   ("BZ=F",     "布伦特原油"),
    "crude":   ("CL=F",     "WTI 原油"),
    "copper":  ("HG=F",     "铜 Copper"),
    "natgas":  ("NG=F",     "天然气"),
    # 外汇
    "eurusd":  ("EURUSD=X", "EUR/USD"),
    "gbpusd":  ("GBPUSD=X", "GBP/USD"),
    "usdjpy":  ("USDJPY=X", "USD/JPY"),
    "dxy":     ("DX=F",     "美元指数 DXY"),
    # 债券（^IRX = 13周T-Bill短端利率；2Y yfinance 无直接 ticker）
    "us10y":   ("^TNX",     "美国10Y"),
    "us3m":    ("^IRX",     "美国3M（短端利率）"),
}

FOREXFACTORY_URL = "https://r.jina.ai/https://www.forexfactory.com/calendar"
FT_URL           = "https://r.jina.ai/https://www.ft.com/markets"
REUTERS_URL      = "https://r.jina.ai/https://www.reuters.com/markets/us/"
JINA_HEADERS     = {"Accept": "text/markdown", "X-No-Cache": "true"}
TIMEOUT          = 20


# ─── 数据拉取 ────────────────────────────────────────────────

def _fetch_ticker(key: str, symbol: str) -> tuple[str, dict]:
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        price = info.last_price
        prev  = info.previous_close
        chg   = (price - prev) / prev * 100 if prev else 0
        return key, {"price": price, "prev": prev, "chg": chg}
    except Exception as e:
        return key, {"error": str(e)}


def fetch_all_tickers() -> dict:
    results = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_fetch_ticker, k, sym): k for k, (sym, _) in SYMBOLS.items()}
        for f in as_completed(futs):
            k, data = f.result()
            results[k] = data
    return results


def fetch_text(url: str, max_chars: int = 8000) -> str:
    try:
        r = requests.get(url, headers=JINA_HEADERS, timeout=TIMEOUT)
        return r.text[:max_chars]
    except Exception as e:
        print(f"[fetch] {url[:60]} 失败: {e}", file=sys.stderr)
        return ""


def parse_ff_events(text: str) -> list[dict]:
    """解析 ForexFactory 高影响事件（橙色 ora）"""
    events = []
    cur_date = ""
    # 先找日期行
    date_pat = re.compile(r'\|\s*((?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+\w+\s+\d+)\s*\|')
    # 高影响行（含 ora）
    event_pat = re.compile(
        r'\|\s*([\d:apm]+|All Day)\s*\|'
        r'\s*(USD|EUR|GBP|CNY|JPY|AUD|CAD|CHF|NZD)\s*\|'
        r'[^|]*ora[^|]*\|'
        r'\s*([^|]+?)\s*\|'
        r'[^|]*\|[^|]*\|'
        r'\s*([^|]*?)\s*\|'
        r'\s*([^|]*?)\s*\|'
        r'\s*([^|]*?)\s*\|'
    )
    for line in text.split('\n'):
        dm = date_pat.search(line)
        if dm:
            cur_date = dm.group(1).strip()
        em = event_pat.search(line)
        if em:
            time_, cur, event, actual, forecast, prev = em.groups()
            events.append({
                "date":     cur_date,
                "time":     time_.strip(),
                "currency": cur.strip(),
                "event":    event.strip(),
                "actual":   actual.strip(),
                "forecast": forecast.strip(),
                "previous": prev.strip(),
            })
    return events


def extract_headlines(text: str, domain_pattern: str) -> list[str]:
    """从 Jina 抓取的 Markdown 中提取文章标题（纯文本，无链接）"""
    raw = re.findall(rf'\[([^\]]{{15,}})\]\(https://(?:www\.)?{domain_pattern}[^\)]*\)', text)
    seen = set()
    headlines = []
    for h in raw:
        h = h.strip()
        if h not in seen and len(h) > 20:
            seen.add(h)
            headlines.append(h)
    return headlines[:15]


def summarize_news_zh(ft_text: str, reuters_text: str) -> str:
    """用 LLM 将英文新闻分类总结为中文摘要；无 API 时回退到原始标题"""
    # 提取原始标题作为回退
    ft_headlines = extract_headlines(ft_text, r"ft\.com/")
    reuters_headlines = extract_headlines(reuters_text, r"reuters\.com/")
    all_headlines = ft_headlines + reuters_headlines

    # 尝试调用 OpenAI 兼容 API 做中文总结
    api_key = os.getenv("AIHUBMIX_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key or not all_headlines:
        # 无 API 或无新闻 → 回退到原始英文标题
        return all_headlines

    prompt = (
        "你是金融新闻编辑。请从以下英文新闻标题中筛选出最重要的 8-10 条，分类汇总为简洁的中文摘要。\n"
        "筛选标准：优先选择对全球金融市场有直接影响的新闻（地缘冲突、央行政策、重大经济数据、大型并购等），忽略软新闻和评论文章。\n"
        "要求：\n"
        "1. 按主题分类，使用 emoji 标注类别（如 🌍 地缘风险、📈 市场走势、🏢 企业动态、💰 货币政策、🛢️ 大宗商品 等）\n"
        "2. 每条新闻用一句简洁中文概括核心信息\n"
        "3. 不要输出英文原文、链接或来源标注\n"
        "4. 直接输出分类结果，不要加标题或前言\n\n"
        "新闻标题列表：\n"
    )
    for h in all_headlines:
        prompt += f"- {h}\n"

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1024,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content:
                return content
    except Exception as e:
        print(f"[新闻摘要] LLM 调用失败: {e}", file=sys.stderr)

    # LLM 失败 → 回退
    return all_headlines


# ─── 报告格式 ────────────────────────────────────────────────

def sign_icon(chg: float) -> str:
    return "🟢" if chg >= 0 else "🔴"


def fmt_row(data: dict, decimals: int = 2, unit: str = "") -> str:
    if not data or "error" in data:
        return "N/A"
    p = data["price"]
    c = data["chg"]
    return f"{p:,.{decimals}f}{unit}  {sign_icon(c)} {c:+.2f}%"


def vix_label(price: float) -> str:
    if price >= 30: return "🚨 极度恐慌"
    if price >= 25: return "⚠️ 恐慌区间"
    if price >= 20: return "⚠️ 警戒线"
    return "✅ 正常"


def event_signal(actual: str, forecast: str) -> str:
    try:
        a = float(re.sub(r'[^\d.\-]', '', actual))
        f = float(re.sub(r'[^\d.\-]', '', forecast))
        return " ✅超预期" if a > f else " ❌不及预期" if a < f else " 符合预期"
    except (ValueError, TypeError):
        return ""


def macro_theme_summary(mkt: dict, ff_events: list[dict]) -> str:
    """基于数据自动生成宏观主题判断"""
    themes = []

    # 美股趋势
    sp_chg = mkt.get("sp500", {}).get("chg", 0)
    nd_chg = mkt.get("nasdaq", {}).get("chg", 0)
    if sp_chg < -0.5:
        themes.append("美股回调")
    elif sp_chg > 0.5:
        themes.append("美股上涨")

    # VIX
    vix_p = mkt.get("vix", {}).get("price", 0)
    vix_c = mkt.get("vix", {}).get("chg", 0)
    if vix_p >= 25:
        themes.append("市场恐慌情绪高涨")
    elif vix_c > 5:
        themes.append("恐慌指数上升")

    # 黄金
    gold_chg = mkt.get("gold", {}).get("chg", 0)
    if gold_chg > 1.0:
        themes.append(f"黄金大涨 {gold_chg:+.1f}%（避险需求强烈）")

    # 油价
    brent_chg = mkt.get("brent", {}).get("chg", 0)
    if abs(brent_chg) > 1.5:
        dir_ = "上涨" if brent_chg > 0 else "下跌"
        themes.append(f"油价{dir_} {brent_chg:+.1f}%")

    # 美元
    dxy_chg = mkt.get("dxy", {}).get("chg", 0)
    if dxy_chg < -0.3:
        themes.append("美元走弱")
    elif dxy_chg > 0.3:
        themes.append("美元走强")

    # 债券
    us10y_chg = mkt.get("us10y", {}).get("chg", 0)
    if us10y_chg < -0.5:
        themes.append("美债收益率下行（避险买盘）")
    elif us10y_chg > 0.5:
        themes.append("美债收益率上升（通胀预期/紧缩预期）")

    # 欧亚vs美股分化
    stoxx_chg = mkt.get("stoxx", {}).get("chg", 0)
    if sp_chg < -0.3 and stoxx_chg > 0.1:
        themes.append("美欧股市分化（资金轮动）")

    # Risk-Off / Risk-On 判断（美元走强 = 避险信号，非走弱）
    risk_off_signals = sum([
        gold_chg > 0.5,
        us10y_chg < -0.3,
        vix_p > 20 or vix_c > 3,
        sp_chg < -0.3,
        dxy_chg > 0.3,
    ])
    regime = "⚠️ Risk-Off（避险为主）" if risk_off_signals >= 3 else "✅ Risk-On（风险偏好）" if risk_off_signals <= 1 else "➡️ 中性混合"

    return regime, themes


def build_report(mkt: dict, ff_events: list[dict], news_summary) -> str:
    now = datetime.now(timezone.utc)
    date_str  = now.strftime("%Y-%m-%d")
    time_str  = now.strftime("%H:%M UTC")

    regime, themes = macro_theme_summary(mkt, ff_events)

    lines = [
        f"# 📊 金融市场日报 · {date_str}",
        f"**{time_str}** | 数据源: yfinance · ForexFactory · FT",
        "",
        "---",
        "",
        f"## 🎯 今日主题：{regime}",
    ]

    if themes:
        for t in themes:
            lines.append(f"- {t}")
    else:
        lines.append("- 市场整体平稳，无显著信号")

    # ── 一、美股 ──
    lines += ["", "---", "", "## 一、美股指数"]
    for key, label in [("sp500","S&P 500"),("nasdaq","NASDAQ"),("dji","Dow Jones"),("russell","Russell 2000")]:
        lines.append(f"- **{label}**: {fmt_row(mkt.get(key,{}))}")

    vix_d = mkt.get("vix", {})
    if vix_d and "error" not in vix_d:
        vix_p = vix_d["price"]
        vix_c = vix_d["chg"]
        lines.append(f"- **VIX 恐慌指数**: {vix_p:.2f}  {sign_icon(vix_c)} {vix_c:+.2f}%  {vix_label(vix_p)}")

    # ── 二、欧亚 ──
    lines += ["", "## 二、欧亚股市"]
    for key, label in [("stoxx","Euro STOXX 600"),("dax","DAX"),("ftse","FTSE 100"),("nikkei","Nikkei 225"),("hsi","恒生指数")]:
        d = mkt.get(key, {})
        if d and "error" not in d:
            lines.append(f"- **{label}**: {fmt_row(d)}")

    # ── 三、商品 ──
    lines += ["", "## 三、大宗商品"]
    commodity_notes = {
        "gold":   lambda c: "  ⚠️ 避险大幅买入" if c > 1.5 else ("  ⚠️ 大幅下跌" if c < -1.5 else ""),
        "brent":  lambda c: "  ⚠️ 油价大涨（地缘/OPEC）" if c > 2 else ("  ⚠️ 油价大跌" if c < -2 else ""),
        "copper": lambda c: "  （需求预期走强）" if c > 1 else ("  （需求预期走弱）" if c < -1 else ""),
    }
    for key, label in [("gold","黄金 Gold"),("silver","白银 Silver"),("brent","布伦特原油"),("crude","WTI 原油"),("copper","铜 Copper"),("natgas","天然气")]:
        d = mkt.get(key, {})
        if d and "error" not in d:
            note = commodity_notes.get(key, lambda c: "")(d["chg"])
            p_unit = "$" if key in ("brent","crude") else ""
            lines.append(f"- **{label}**: {p_unit}{fmt_row(d, decimals=2 if key not in ('copper',) else 4)}{note}")

    # ── 四、外汇 ──
    lines += ["", "## 四、外汇"]
    for key, label in [("eurusd","EUR/USD"),("gbpusd","GBP/USD"),("usdjpy","USD/JPY"),("dxy","美元指数 DXY")]:
        d = mkt.get(key, {})
        if d and "error" not in d:
            lines.append(f"- **{label}**: {fmt_row(d, decimals=4 if 'usd' in key.lower() else 2)}")

    # ── 五、债券 ──
    lines += ["", "## 五、美债收益率"]
    for key, label in [("us10y","10年期"), ("us3m","3个月（短端）")]:
        d = mkt.get(key, {})
        if d and "error" not in d:
            p, c = d["price"], d["chg"]
            direction = "↓ 避险买盘" if c < -0.5 else ("↑ 通胀预期" if c > 0.5 else "")
            lines.append(f"- **{label}国债**: {p:.3f}%  {sign_icon(c)} {c:+.2f}%  {direction}")

    # 收益率曲线（3M-10Y，注：^IRX 为13周T-Bill）
    us3m_p  = mkt.get("us3m",  {}).get("price", 0)
    us10y_p = mkt.get("us10y", {}).get("price", 0)
    if us3m_p and us10y_p:
        spread = us10y_p - us3m_p
        invert_tag = "  🚨 倒挂（衰退信号）" if spread < 0 else ""
        lines.append(f"- **3M-10Y 利差**: {spread:+.3f}%{invert_tag}")

    # ── 六、宏观事件 ──
    lines += ["", "---", "", "## 六、未来一周重要宏观事件（高影响）"]
    if ff_events:
        lines.append("")
        lines.append("| 日期 | 时间 | 货币 | 事件 | 实际 | 预期 | 前值 | 解读 |")
        lines.append("|------|------|------|------|------|------|------|------|")
        for e in ff_events[:12]:
            sig = event_signal(e["actual"], e["forecast"])
            lines.append(
                f"| {e['date']} | {e['time']} | {e['currency']} "
                f"| {e['event']} | **{e['actual']}** | {e['forecast']} | {e['previous']} | {sig} |"
            )
    else:
        lines.append("*数据加载中或本周暂无高影响事件*")

    # ── 七、重要新闻（中文分类总结） ──
    lines += ["", "---", "", "## 七、重要市场新闻"]
    if news_summary:
        if isinstance(news_summary, str):
            # LLM 中文总结（已分类带 emoji）
            lines.append(news_summary)
        elif isinstance(news_summary, list):
            # 回退模式：原始英文标题列表
            for i, h in enumerate(news_summary, 1):
                lines.append(f"{i}. {h}")
    else:
        lines.append("*新闻源暂时无法访问*")

    # ── 八、后续关注 ──
    lines += ["", "---", "", "## 八、后续关注"]
    watch_items = []

    vix_p2 = mkt.get("vix", {}).get("price", 0)
    if vix_p2 > 20:
        watch_items.append("🔍 VIX 是否持续高位 → 观察市场是否触底")

    gold_chg2 = mkt.get("gold", {}).get("chg", 0)
    if gold_chg2 > 1:
        watch_items.append("🔍 黄金后续走势 → 确认避险还是技术性回调")

    brent_chg2 = mkt.get("brent", {}).get("chg", 0)
    if abs(brent_chg2) > 1.5:
        watch_items.append("🔍 油价驱动因素 → OPEC 决策 / 地缘局势 / 需求数据")

    sp_chg2 = mkt.get("sp500", {}).get("chg", 0)
    if sp_chg2 < -0.5:
        watch_items.append("🔍 美股关键支撑位 → S&P 500 技术面是否破位")

    us10y_p2 = mkt.get("us10y", {}).get("price", 0)
    if us10y_p2:
        watch_items.append(f"🔍 美联储下步动作 → 当前10Y: {us10y_p2:.3f}%，关注FOMC委员发言")

    watch_items.append("🔍 本周重要数据：NFP 就业报告（如当周）、CPI 通胀数据")
    watch_items.append("🔍 美元走势 → DXY 是否持续弱势，影响新兴市场资金流向")

    for w in watch_items:
        lines.append(f"- {w}")

    # ── 尾部 ──
    lines += [
        "",
        "---",
        f"*📅 {date_str} {time_str} · market_daily.py · 数据来源: yfinance / ForexFactory / FT*",
        "*⚠️ 仅供参考，不构成投资建议*"
    ]

    return "\n".join(lines)


# ─── 推送飞书 ────────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    """去除常见 Markdown 标记，使飞书纯文本模式正常显示"""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # # 标题
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)                # **粗体**
    text = re.sub(r'\*(.+?)\*', r'\1', text)                    # *斜体*
    text = re.sub(r'^---+$', '─' * 30, text, flags=re.MULTILINE)  # 分隔线
    return text


def push_feishu(text: str):
    webhook = os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook:
        print("[飞书] 未配置 FEISHU_WEBHOOK_URL，跳过", file=sys.stderr)
        return
    payload = {"msg_type": "text", "content": {"text": _strip_markdown(text)}}
    try:
        r = requests.post(webhook, json=payload, timeout=10)
        print(f"[飞书] {'推送成功' if r.status_code == 200 else f'失败 {r.status_code}'}")
    except Exception as e:
        print(f"[飞书] 错误: {e}", file=sys.stderr)


# ─── 主流程 ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="金融市场日报生成器")
    parser.add_argument("--output", choices=["print", "report"], default="print")
    parser.add_argument("--feishu", action="store_true")
    args = parser.parse_args()

    print("🔄 拉取市场数据...", file=sys.stderr)

    # 导入新闻精选 pipeline
    try:
        from market_daily.providers.news_digest import NewsDigestPipeline
        _use_digest = True
    except ImportError:
        _use_digest = False

    with ThreadPoolExecutor(max_workers=4) as ex:
        fut_mkt     = ex.submit(fetch_all_tickers)
        fut_ff      = ex.submit(fetch_text, FOREXFACTORY_URL)
        # 新闻：优先使用 NewsDigest pipeline（50-100条→LLM精选~10条）
        if _use_digest:
            fut_news = ex.submit(NewsDigestPipeline().run)
        else:
            fut_ft      = ex.submit(fetch_text, FT_URL, 6000)
            fut_reuters = ex.submit(fetch_text, REUTERS_URL, 6000)

        mkt    = fut_mkt.result()
        ff_raw = fut_ff.result()

        if _use_digest:
            news_summary = fut_news.result()
        else:
            ft_raw      = fut_ft.result()
            reuters_raw = fut_reuters.result()
            news_summary = summarize_news_zh(ft_raw, reuters_raw)

    ff_events = parse_ff_events(ff_raw)

    news_count = len(news_summary) if isinstance(news_summary, list) else (1 if news_summary else 0)
    ok = sum(1 for v in mkt.values() if "error" not in v)
    news_label = 'NewsDigest' if _use_digest and isinstance(news_summary, str) else ('LLM总结' if isinstance(news_summary, str) else f'{news_count} 条')
    print(f"✅ yfinance: {ok}/{len(mkt)} 成功 | ForexFactory: {len(ff_events)} 事件 | 新闻: {news_label}", file=sys.stderr)

    report = build_report(mkt, ff_events, news_summary)

    if args.output == "report":
        date_str = datetime.now().strftime("%Y%m%d")
        out_dir  = Path(__file__).parent / "reports"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / f"market_daily_{date_str}.md"
        out_file.write_text(report, encoding="utf-8")
        print(f"✅ 保存: {out_file}", file=sys.stderr)
    else:
        print(report)

    if args.feishu:
        push_feishu(report)


if __name__ == "__main__":
    main()
