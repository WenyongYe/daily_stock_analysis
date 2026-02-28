# -*- coding: utf-8 -*-
"""
market_daily 核心调度器
并发调用所有 Provider，组装报告，可选推送
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .providers  import PriceProvider, MacroProvider, NewsProvider, CalendarProvider
from .report     import ReportBuilder
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

    # 并发拉取四路数据
    providers = {
        "prices":   PriceProvider().fetch,
        "macro":    MacroProvider().fetch,
        "news":     NewsProvider().fetch,
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
                results[key] = {} if key in ("prices", "macro") else []

    # 生成报告
    report = ReportBuilder().build(
        prices   = results.get("prices",   {}),
        macro    = results.get("macro",    {}),
        news     = results.get("news",     []),
        calendar = results.get("calendar", []),
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
