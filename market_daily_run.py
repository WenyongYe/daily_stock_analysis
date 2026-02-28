#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融市场日报 CLI 入口
替代原 market_daily.py，调用模块化的 market_daily 包

用法:
  python market_daily_run.py                  # 打印到终端
  python market_daily_run.py --output report  # 保存到 reports/market_daily_YYYYMMDD.md
  python market_daily_run.py --feishu         # 推送到飞书
  python market_daily_run.py --output report --feishu  # 保存并推送
"""

import argparse

from market_daily import run


def main():
    parser = argparse.ArgumentParser(description="金融市场日报生成器（模块化版）")
    parser.add_argument(
        "--output",
        choices=["print", "report"],
        default="print",
        help="输出方式: print(打印到终端) 或 report(保存到 reports/ 目录)",
    )
    parser.add_argument(
        "--feishu",
        action="store_true",
        help="推送到飞书",
    )
    args = parser.parse_args()

    run(output=args.output, feishu=args.feishu)


if __name__ == "__main__":
    main()
