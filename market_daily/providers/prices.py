# -*- coding: utf-8 -*-
"""
行情数据 Provider
使用 yfinance 并发拉取全球主要指数、商品、外汇、债券
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

# 标的配置：key -> (symbol, label, category)
SYMBOLS: dict[str, tuple[str, str, str]] = {
    # 美股
    "sp500":   ("^GSPC",    "S&P 500",         "us_equity"),
    "nasdaq":  ("^IXIC",    "NASDAQ",           "us_equity"),
    "dji":     ("^DJI",     "Dow Jones",        "us_equity"),
    "russell": ("^RUT",     "Russell 2000",     "us_equity"),
    "vix":     ("^VIX",     "VIX 恐慌指数",     "risk"),
    # 欧亚
    "stoxx":   ("^STOXX",   "Euro STOXX 600",   "intl_equity"),
    "dax":     ("^GDAXI",   "DAX",              "intl_equity"),
    "ftse":    ("^FTSE",    "FTSE 100",         "intl_equity"),
    "nikkei":  ("^N225",    "Nikkei 225",       "intl_equity"),
    "hsi":     ("^HSI",     "恒生指数",          "intl_equity"),
    # 商品
    "gold":    ("GC=F",     "黄金 Gold",        "commodity"),
    "silver":  ("SI=F",     "白银 Silver",      "commodity"),
    "brent":   ("BZ=F",     "布伦特原油",        "commodity"),
    "crude":   ("CL=F",     "WTI 原油",         "commodity"),
    "copper":  ("HG=F",     "铜 Copper",        "commodity"),
    "natgas":  ("NG=F",     "天然气",            "commodity"),
    # 外汇
    "eurusd":  ("EURUSD=X", "EUR/USD",          "fx"),
    "gbpusd":  ("GBPUSD=X", "GBP/USD",          "fx"),
    "usdjpy":  ("USDJPY=X", "USD/JPY",          "fx"),
    "dxy":     ("DX=F",     "美元指数 DXY",     "fx"),
    # 债券
    "us10y":   ("^TNX",     "美国10Y",          "bond"),
    "us2y":    ("^IRX",     "美国2Y",           "bond"),
}


def _fetch_one(key: str, symbol: str) -> tuple[str, dict]:
    """拉取单个标的数据"""
    try:
        t = yf.Ticker(symbol)
        info = t.fast_info
        price = info.last_price
        prev  = info.previous_close
        chg   = (price - prev) / prev * 100 if prev else 0.0
        return key, {
            "price":    price,
            "prev":     prev,
            "chg":      chg,
            "label":    SYMBOLS[key][1],
            "category": SYMBOLS[key][2],
        }
    except Exception as e:
        return key, {"error": str(e), "label": SYMBOLS.get(key, ("", key, ""))[1]}


class PriceProvider:
    """全球行情数据拉取器"""

    def __init__(self, workers: int = 12):
        self.workers = workers

    def fetch(self, keys: list[str] | None = None) -> dict:
        """
        并发拉取行情数据

        Args:
            keys: 要拉取的标的 key 列表，None 则拉取全部

        Returns:
            dict: {key: {price, prev, chg, label, category}} 或 {key: {error}}
        """
        targets = {k: v for k, v in SYMBOLS.items() if keys is None or k in keys}
        results = {}
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futs = {ex.submit(_fetch_one, k, sym): k for k, (sym, _, _) in targets.items()}
            for f in as_completed(futs):
                k, data = f.result()
                results[k] = data
        ok = sum(1 for v in results.values() if "error" not in v)
        print(f"  [PriceProvider] {ok}/{len(results)} 成功", file=sys.stderr)
        return results

    @property
    def symbols(self) -> dict:
        return SYMBOLS
