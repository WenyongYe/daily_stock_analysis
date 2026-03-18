# -*- coding: utf-8 -*-
"""
US Trading Scanner — Entry Point

AI-assisted US stock trading scanner that identifies high-probability
trading setups using volume-price analysis, pattern recognition,
anomaly detection, and options analysis.

Usage:
    python us_trading_scanner.py --pre-market          # Pre-market scan
    python us_trading_scanner.py --post-market         # Post-market review
    python us_trading_scanner.py --both                # Both scans
    python us_trading_scanner.py --schedule            # Scheduled mode
    python us_trading_scanner.py --stocks NVDA,TSLA    # Override stock pool
    python us_trading_scanner.py --top 5               # Top N results
    python us_trading_scanner.py --no-notify           # Skip notifications
    python us_trading_scanner.py --no-llm              # Skip LLM report generation
    python us_trading_scanner.py --no-options           # Skip options analysis
"""

import os
from src.config import setup_env
setup_env()

if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "10809")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

import argparse
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import schedule

from src.config import get_config
from src.logging_config import setup_logging
from src.scanner.us_stock_pool import USStockPool
from src.scanner.volume_price_engine import VolumePriceEngine, VolumePriceSignal
from src.scanner.pattern_detector import PatternDetector, PatternSignal
from src.scanner.anomaly_detector import AnomalyDetector, AnomalyAlert
from src.scanner.options_analyzer import OptionsAnalyzer, OptionsSignal
from src.scanner.signal_scorer import SignalScorer, ScoredSignal
from src.scanner.scan_reporter import ScanReporter

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="US Stock Trading Scanner")
    parser.add_argument("--pre-market", action="store_true", help="Run pre-market scan")
    parser.add_argument("--post-market", action="store_true", help="Run post-market review")
    parser.add_argument("--both", action="store_true", help="Run both pre-market and post-market")
    parser.add_argument("--schedule", action="store_true", help="Enable scheduled mode")
    parser.add_argument("--stocks", type=str, help="Override stock pool (comma-separated)")
    parser.add_argument("--top", type=int, help="Number of top stocks to report")
    parser.add_argument("--no-notify", action="store_true", help="Skip push notifications")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM report generation")
    parser.add_argument("--no-options", action="store_true", help="Skip options analysis")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    return parser.parse_args()


def fetch_stock_data(symbol: str, lookback_days: int = 60) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data for a US stock using yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=f"{lookback_days}d")
        if df.empty:
            logger.warning(f"{symbol}: no data returned from yfinance")
            return None

        # Normalize column names to match system convention
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        if "date" not in df.columns and "datetime" in df.columns:
            df = df.rename(columns={"datetime": "date"})

        # Ensure date column is string format
        if hasattr(df["date"].dtype, "tz"):
            df["date"] = df["date"].dt.tz_localize(None)
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")

        required = ["date", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                logger.warning(f"{symbol}: missing column {col}")
                return None

        return df[required]
    except Exception as e:
        logger.warning(f"{symbol}: failed to fetch data: {e}")
        return None


def analyze_stock(
    symbol: str,
    df: pd.DataFrame,
    vp_engine: VolumePriceEngine,
    pattern_detector: PatternDetector,
    anomaly_detector: AnomalyDetector,
    options_analyzer: Optional[OptionsAnalyzer],
) -> Tuple[str, Optional[VolumePriceSignal], List[PatternSignal], List[AnomalyAlert], Optional[OptionsSignal]]:
    """Run all analyses on a single stock."""
    vp_signal = vp_engine.analyze(df, symbol)
    patterns = pattern_detector.analyze(df)
    anomalies = anomaly_detector.analyze(df, symbol)

    options_signal = None
    if options_analyzer:
        options_signal = options_analyzer.analyze(symbol, vp_signal.current_price)

    return symbol, vp_signal, patterns, anomalies, options_signal


def run_scan(mode: str = "pre_market", stocks_override: Optional[List[str]] = None,
             top_n: Optional[int] = None, notify: bool = True, use_llm: bool = True,
             use_options: bool = True):
    """
    Run the full scanning pipeline.

    Args:
        mode: "pre_market" or "post_market"
        stocks_override: Override the default stock pool
        top_n: Override top N
        notify: Whether to send notifications
        use_llm: Whether to use LLM for report generation
        use_options: Whether to analyze options
    """
    config = get_config()
    start_time = time.time()
    mode_label = "盘前扫描" if mode == "pre_market" else "盘后复盘"
    logger.info(f"=== 开始美股{mode_label} ===")

    # 1. Get stock pool
    pool = USStockPool()
    if stocks_override:
        symbols = stocks_override
    else:
        symbols = pool.get_tradable_stocks()

    top_n = top_n or config.us_scanner_top_n
    min_score = config.us_scanner_min_score
    lookback = config.us_scanner_lookback_days

    logger.info(f"标的池: {len(symbols)} 只 | Top N: {top_n} | 最低分: {min_score}")

    # 2. Fetch data
    logger.info("获取历史数据...")
    stock_data: Dict[str, pd.DataFrame] = {}
    max_workers = min(config.max_workers, 5)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_stock_data, sym, lookback): sym for sym in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                df = future.result()
                if df is not None and len(df) >= 20:
                    stock_data[sym] = df
            except Exception as e:
                logger.warning(f"{sym}: data fetch error: {e}")

    logger.info(f"成功获取 {len(stock_data)}/{len(symbols)} 只股票数据")

    if not stock_data:
        logger.error("未获取到任何股票数据，退出")
        return

    # 3. Run analyses
    logger.info("运行分析引擎...")
    vp_engine = VolumePriceEngine(heavy_vol_ratio=config.us_scanner_volume_heavy_ratio)
    pattern_detector = PatternDetector()
    anomaly_detector = AnomalyDetector()
    options_analyzer = OptionsAnalyzer() if use_options else None

    all_results: Dict[str, Tuple] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for sym, df in stock_data.items():
            future = executor.submit(
                analyze_stock, sym, df, vp_engine, pattern_detector,
                anomaly_detector, options_analyzer
            )
            futures[future] = sym

        for future in as_completed(futures):
            sym = futures[future]
            try:
                result = future.result()
                all_results[sym] = result
            except Exception as e:
                logger.warning(f"{sym}: analysis error: {e}")

    logger.info(f"分析完成: {len(all_results)} 只股票")

    # 4. Score and rank
    logger.info("评分排序...")
    scorer = SignalScorer(min_score=min_score, top_n=top_n)
    scored_signals: List[ScoredSignal] = []

    for sym, (_, vp_signal, patterns, anomalies, options_signal) in all_results.items():
        trend_strength = vp_signal.signal_strength if vp_signal else 50
        scored = scorer.score(
            code=sym,
            vp_signal=vp_signal,
            patterns=patterns,
            anomalies=anomalies,
            options=options_signal,
            trend_strength=trend_strength,
        )
        scored_signals.append(scored)

    ranked = scorer.rank_signals(scored_signals, mode=mode)

    if not ranked:
        logger.info(f"没有标的达到最低评分 {min_score}，降低阈值到 {min_score - 10}")
        scorer.min_score = max(40, min_score - 10)
        ranked = scorer.rank_signals(scored_signals, mode=mode)

    logger.info(f"筛选出 {len(ranked)} 只标的")

    # 5. Generate report
    logger.info("生成报告...")
    reporter = ScanReporter()
    report = reporter.generate_report(ranked, mode=mode, use_llm=use_llm)

    # Print to console
    print("\n" + report)

    # 6. Push notification
    if notify and ranked:
        try:
            from src.notification import NotificationService
            notifier = NotificationService()
            notifier.send(report)
            logger.info("通知已推送")
        except Exception as e:
            logger.warning(f"通知推送失败: {e}")

    elapsed = time.time() - start_time
    logger.info(f"=== 美股{mode_label}完成，耗时 {elapsed:.1f}s ===")

    return ranked


def main():
    args = parse_args()
    log_level = "DEBUG" if args.debug else get_config().log_level
    setup_logging(log_level)

    # Determine stocks override
    stocks_override = None
    if args.stocks:
        stocks_override = [s.strip().upper() for s in args.stocks.split(",") if s.strip()]

    use_options = not args.no_options
    use_llm = not args.no_llm
    notify = not args.no_notify

    if args.schedule:
        config = get_config()
        pre_time = config.us_scanner_pre_market_time
        post_time = config.us_scanner_post_market_time

        logger.info(f"定时模式启动: 盘前={pre_time} 盘后={post_time} (北京时间)")

        schedule.every().day.at(pre_time).do(
            run_scan, mode="pre_market", stocks_override=stocks_override,
            top_n=args.top, notify=notify, use_llm=use_llm, use_options=use_options
        )
        schedule.every().day.at(post_time).do(
            run_scan, mode="post_market", stocks_override=stocks_override,
            top_n=args.top, notify=notify, use_llm=use_llm, use_options=use_options
        )

        # Run once immediately
        run_scan(mode="pre_market", stocks_override=stocks_override,
                 top_n=args.top, notify=notify, use_llm=use_llm, use_options=use_options)

        while True:
            schedule.run_pending()
            time.sleep(60)

    elif args.both:
        run_scan(mode="pre_market", stocks_override=stocks_override,
                 top_n=args.top, notify=notify, use_llm=use_llm, use_options=use_options)
        run_scan(mode="post_market", stocks_override=stocks_override,
                 top_n=args.top, notify=notify, use_llm=use_llm, use_options=use_options)

    elif args.post_market:
        run_scan(mode="post_market", stocks_override=stocks_override,
                 top_n=args.top, notify=notify, use_llm=use_llm, use_options=use_options)

    else:
        # Default: pre-market
        run_scan(mode="pre_market", stocks_override=stocks_override,
                 top_n=args.top, notify=notify, use_llm=use_llm, use_options=use_options)


if __name__ == "__main__":
    main()
