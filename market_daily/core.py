# -*- coding: utf-8 -*-
"""
market_daily 核心调度器
并发调用所有 Provider，组装报告，可选推送
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .providers  import PriceProvider, MacroProvider, CalendarProvider
from .providers.news_digest import NewsDigestPipeline
from .report     import ReportBuilder
from .report.narrative import generate_narrative, generate_annotations
from .delivery   import FeishuDelivery


def run(
    output:  str  = "print",   # "print" | "report"
    feishu:  bool = False,
    verbose: bool = True,
) -> str:
    """
    运行完整日报流程

    Args:
        output:  "print"（控制台）或 "report"（保存文件）
        feishu:  是否推送到飞书
        verbose: 是否打印进度

    Returns:
        str: 生成的报告 Markdown 文本
    """
    if verbose:
        print("🔄 正在并发拉取数据...", file=sys.stderr)

    # 并发拉取四路数据（新闻使用 NewsDigest pipeline：50-100条→LLM精选~10条）
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
                results[key] = {} if key in ("prices", "macro") else ([] if key != "news" else "")

    # LLM 综合叙事（行情+新闻关联分析）
    from .report.theme import analyze_theme
    prices_data = results.get("prices", {})
    macro_data = results.get("macro", {})
    news_data = results.get("news", "")
    calendar_data = results.get("calendar", [])

    theme = analyze_theme(prices_data, macro_data, calendar_data)

    # LLM 叙事 + AI 注释并发生成
    narrative = None
    annotations = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_narr = ex.submit(
            generate_narrative, prices_data, news_data, theme.label, theme.themes
        )
        fut_ann = ex.submit(
            generate_annotations, prices_data, calendar_data, news_data
        )
        narrative = fut_narr.result()
        annotations = fut_ann.result()

    # 生成报告
    report = ReportBuilder().build(
        prices      = prices_data,
        macro       = macro_data,
        news        = news_data,
        calendar    = calendar_data,
        narrative   = narrative,
        annotations = annotations,
    )

    # 输出
    if output == "report":
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        # 保存到 daily_stock_analysis/reports/ 目录
        out_dir  = Path(__file__).parent.parent / "reports"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / f"market_daily_{date_str}.md"
        out_file.write_text(report, encoding="utf-8")
        if verbose:
            print(f"✅ 报告已保存: {out_file}", file=sys.stderr)
    else:
        print(report)

    # 推送
    if feishu:
        FeishuDelivery().send(report)

    return report
