#!/usr/bin/env python3
"""
市场深度解读 - market_deep.py
通过分层 LLM 分析生成深度市场解读报告（事实→因果→推演→关联）

用法:
  python market_deep.py                  # 打印到终端
  python market_deep.py --output report  # 保存到 reports/market_deep_YYYYMMDD.md
  python market_deep.py --feishu         # 推送到飞书 Webhook
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="市场深度解读生成器")
    parser.add_argument("--output", choices=["print", "report"], default="print")
    parser.add_argument("--feishu", action="store_true", help="推送到飞书")
    args = parser.parse_args()

    from market_daily.core_deep import run
    run(output=args.output, feishu=args.feishu)


if __name__ == "__main__":
    main()
