# -*- coding: utf-8 -*-
"""
深度解读调度器
并发拉取数据 → 深度分析 → 组装报告 → 输出/推送
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .providers import PriceProvider, MacroProvider, CalendarProvider
from .providers.news_digest import NewsDigestPipeline
from .report.theme import analyze_theme
from .report.deep_analysis import DeepAnalysisGenerator, build_deep_report, polish_report_markdown
from .delivery import FeishuDelivery


def _validate_report_sections(report: str) -> list[str]:
    required_tokens = [
        "## 📈 大盘与科技表现",
        "### 🟡 黄金（Gold）",
        "### ⚪ 白银（Silver）",
        "### ⚫ 原油（Crude/Brent）",
    ]
    missing = [token for token in required_tokens if token not in report]
    return missing


def _build_confidence_note(prices: dict, macro: dict, news_data, report: str, missing: list[str]) -> str:
    score = 100
    remarks: list[str] = []

    available_assets = 0
    for key in ("sp500", "nasdaq", "dji", "gold", "silver", "brent", "dxy", "us10y"):
        item = prices.get(key, {})
        if item and "error" not in item:
            available_assets += 1
    if available_assets < 6:
        score -= 15
        remarks.append(f"关键行情覆盖偏低（{available_assets}/8）")

    if not macro.get("vix"):
        score -= 10
        remarks.append("VIX 宏观指标缺失")

    has_news = bool(news_data and (isinstance(news_data, str) and news_data.strip() or isinstance(news_data, list) and len(news_data) > 0))
    if not has_news:
        score -= 25
        remarks.append("新闻输入不足")

    if missing:
        score -= min(60, 20 * len(missing))
        remarks.append("关键版块缺失: " + "；".join(missing))

    if "可信度" not in report:
        score -= 10
        remarks.append("商品段缺少可信度字段")

    score = max(0, min(100, score))
    if score >= 85:
        level = "高"
    elif score >= 70:
        level = "中"
    else:
        level = "低"

    lines = [f"- 置信度评分：**{score}/100（{level}）**"]
    if remarks:
        lines.append("- 备注：" + "；".join(remarks))
    else:
        lines.append("- 备注：关键版块完整，数据覆盖正常")
    return "\n".join(lines)


def _build_weekly_compare_note(reports_dir: Path) -> str:
    files = sorted(reports_dir.glob("market_deep_*.md"))
    if len(files) < 2:
        return "- 近一周历史样本不足，暂不生成对比。"

    recent = files[-7:]

    def _extract_value(text: str, label: str) -> float | None:
        import re
        for line in text.splitlines():
            if line.startswith(f"- {label}:"):
                m = re.search(r"([+-]\d+(?:\.\d+)?)%", line)
                if not m:
                    continue
                try:
                    return float(m.group(1))
                except Exception:
                    return None
        return None

    def _extract_theme(text: str) -> str:
        for line in text.splitlines():
            if line.startswith("## 🎯 今日主线："):
                return line.replace("## 🎯 今日主线：", "").strip()
        return ""

    first_text = recent[0].read_text(encoding="utf-8", errors="ignore")
    last_text = recent[-1].read_text(encoding="utf-8", errors="ignore")

    sp_first = _extract_value(first_text, "S&P 500")
    sp_last = _extract_value(last_text, "S&P 500")
    gold_first = _extract_value(first_text, "黄金")
    gold_last = _extract_value(last_text, "黄金")
    brent_first = _extract_value(first_text, "布伦特")
    brent_last = _extract_value(last_text, "布伦特")

    themes = []
    for f in recent:
        t = _extract_theme(f.read_text(encoding="utf-8", errors="ignore"))
        if t:
            themes.append(t)

    lines = [f"- 对比区间：{recent[0].stem[-8:]} ~ {recent[-1].stem[-8:]}"]
    if sp_first is not None and sp_last is not None:
        lines.append(f"- 大盘（S&P日涨跌幅口径）：{sp_first:+.2f}% → {sp_last:+.2f}%")
    if gold_first is not None and gold_last is not None:
        lines.append(f"- 黄金（日涨跌幅口径）：{gold_first:+.2f}% → {gold_last:+.2f}%")
    if brent_first is not None and brent_last is not None:
        lines.append(f"- 布伦特（日涨跌幅口径）：{brent_first:+.2f}% → {brent_last:+.2f}%")

    if themes:
        lines.append(f"- 事件驱动主线：{themes[0]} → {themes[-1]}")

    lines.append("- 结论：近一周市场主导因素以地缘与风险偏好切换为主，商品与大盘呈明显联动。")
    return "\n".join(lines)


def _extract_commodity_news(news_data) -> str:
    if isinstance(news_data, str):
        lines = [line.strip() for line in news_data.splitlines() if line.strip()]
    elif isinstance(news_data, list):
        lines = [str(item).strip() for item in news_data if str(item).strip()]
    else:
        lines = []

    keywords = [
        "gold", "xau", "黄金",
        "silver", "xag", "白银",
        "oil", "crude", "brent", "wti", "原油",
        "opec", "eia", "inventory", "库存",
        "real yield", "us10y", "美元", "dxy",
    ]

    picked: list[str] = []
    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in keywords):
            picked.append(line)

    picked = picked[:12]
    return "\n".join(f"- {item}" for item in picked) if picked else "无明确商品新闻"


def run(
    output:  str  = "print",   # "print" | "report"
    feishu:  bool = False,
    verbose: bool = True,
) -> str:
    """
    运行深度解读流程

    Args:
        output:  "print"（控制台）或 "report"（保存文件）
        feishu:  是否推送到飞书
        verbose: 是否打印进度

    Returns:
        str: 生成的报告 Markdown 文本
    """
    if verbose:
        print("🔄 [DeepMode] 正在并发拉取数据...", file=sys.stderr)

    # 并发拉取四路数据
    providers = {
        "prices":   PriceProvider().fetch,
        "macro":    MacroProvider().fetch,
        "news":     NewsDigestPipeline().run,
        "calendar": CalendarProvider().fetch,
    }

    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fn): key for key, fn in providers.items()}
        for f in as_completed(futs):
            key = futs[f]
            try:
                results[key] = f.result()
            except Exception as e:
                print(f"  [{key}] 异常: {e}", file=sys.stderr)
                results[key] = (
                    {} if key in ("prices", "macro")
                    else ([] if key == "calendar" else "")
                )

    prices_data = results.get("prices", {})
    macro_data = results.get("macro", {})
    news_data = results.get("news", "")
    calendar_data = results.get("calendar", [])

    # 主题分析
    theme = analyze_theme(prices_data, macro_data, calendar_data)

    if verbose:
        print(f"  [DeepMode] 主题: {theme.label}", file=sys.stderr)
        print("  [DeepMode] 开始深度分析...", file=sys.stderr)

    commodity_news_text = _extract_commodity_news(news_data)

    # 深度解读生成
    generator = DeepAnalysisGenerator()
    deep_result = generator.generate(
        prices=prices_data,
        news_summary=news_data,
        macro=macro_data,
        calendar=calendar_data,
        theme_label=theme.label,
        theme_themes=theme.themes,
        commodity_news_text=commodity_news_text,
    )

    if not deep_result:
        print("  [DeepMode] 深度分析失败，生成精简报告", file=sys.stderr)
        deep_result = {
            "analysis": "深度分析暂不可用（LLM 未配置或调用失败）",
            "summary": "",
        }

    # 组装报告
    report = build_deep_report(
        prices=prices_data,
        macro=macro_data,
        deep_result=deep_result,
        theme_label=theme.label,
        theme_watch=theme.watch,
        confidence_note="",
        weekly_compare_note="",
    )

    missing_sections = _validate_report_sections(report)
    confidence_note = _build_confidence_note(
        prices=prices_data,
        macro=macro_data,
        news_data=news_data,
        report=report,
        missing=missing_sections,
    )
    weekly_compare_note = _build_weekly_compare_note(Path(__file__).parent.parent / "reports")

    report = build_deep_report(
        prices=prices_data,
        macro=macro_data,
        deep_result=deep_result,
        theme_label=theme.label,
        theme_watch=theme.watch,
        confidence_note=confidence_note,
        weekly_compare_note=weekly_compare_note,
    )

    raw_report = report
    report = polish_report_markdown(report)

    missing_sections = _validate_report_sections(report)
    if missing_sections:
        warn_lines = ["---", "", "## ⚠️ 报告完整性告警"]
        for item in missing_sections:
            warn_lines.append(f"- 缺少必要版块: {item}")
        report = report + "\n\n" + "\n".join(warn_lines)
        print(f"  [DeepMode] 报告完整性告警: {missing_sections}", file=sys.stderr)

    # 输出
    if output == "report":
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        out_dir = Path(__file__).parent.parent / "reports"
        out_dir.mkdir(exist_ok=True)
        raw_file = out_dir / f"market_deep_raw_{date_str}.md"
        out_file = out_dir / f"market_deep_{date_str}.md"
        raw_file.write_text(raw_report, encoding="utf-8")
        out_file.write_text(report, encoding="utf-8")
        if verbose:
            print(f"✅ [DeepMode] 原始报告已保存: {raw_file}", file=sys.stderr)
            print(f"✅ [DeepMode] 润色终稿已保存: {out_file}", file=sys.stderr)
    else:
        print(report)

    # 推送
    if feishu:
        FeishuDelivery().send(report)

    return report
