# -*- coding: utf-8 -*-
"""
US Stock Pool Manager

Manages the universe of US stocks to scan. Combines a curated core list
of tech/hot-sector large-caps (>$20B market cap) with optional dynamic
discovery from sector ETF holdings.
"""

import logging
from typing import List, Optional

from src.config import get_config

logger = logging.getLogger(__name__)

# Pre-defined core pool: tech + hot sectors, market cap > $20B (~70 stocks)
DEFAULT_US_TECH_STOCKS: List[str] = [
    # === Mega-Cap Tech ===
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    # === Semiconductors ===
    "AMD", "AVGO", "QCOM", "INTC", "MU", "MRVL", "LRCX", "KLAC", "AMAT",
    "TXN", "ADI", "ON", "NXPI",
    # === AI / Data Center ===
    "SMCI", "ARM", "DELL", "ORCL", "IBM", "PLTR", "SNOW",
    # === SaaS / Cloud ===
    "CRM", "NOW", "ADBE", "INTU", "PANW", "CRWD", "DDOG", "NET", "ZS",
    # === Consumer Tech / Internet ===
    "NFLX", "UBER", "ABNB", "BKNG", "SHOP", "MELI", "SE", "PDD",
    # === Fintech ===
    "SQ", "PYPL", "COIN", "HOOD", "AFRM",
    # === EV / New Energy ===
    "RIVN", "LCID", "ENPH", "FSLR",
    # === Biotech / Med-Tech (large-cap) ===
    "LLY", "NVO", "ISRG", "DXCM",
    # === Financials (trading-relevant) ===
    "V", "MA", "JPM", "GS", "MS",
    # === Major Indices / ETFs for sector correlation ===
    "SPY", "QQQ", "SMH", "XLK", "SOXX",
]

# Sector ETFs used for dynamic discovery and sector correlation
SECTOR_ETFS = {
    "tech": "XLK",
    "semiconductor": "SMH",
    "software": "IGV",
    "internet": "FDN",
    "clean_energy": "ICLN",
}


class USStockPool:
    """Manages the stock universe for scanning."""

    def __init__(self):
        self.config = get_config()
        self._cached_stocks: Optional[List[str]] = None

    def get_stocks(self) -> List[str]:
        """
        Return the list of stock symbols to scan.

        Priority:
        1. US_SCANNER_STOCKS from .env (if configured)
        2. Default curated list
        """
        if self._cached_stocks is not None:
            return self._cached_stocks

        custom = self.config.us_scanner_stocks
        if custom:
            self._cached_stocks = custom
            logger.info(f"Using custom US scanner stock pool: {len(custom)} stocks")
        else:
            self._cached_stocks = list(DEFAULT_US_TECH_STOCKS)
            logger.info(f"Using default US scanner stock pool: {len(self._cached_stocks)} stocks")

        return self._cached_stocks

    def get_tradable_stocks(self) -> List[str]:
        """Return only individual stocks (exclude ETFs/indices)."""
        etf_set = set(SECTOR_ETFS.values()) | {"SPY", "QQQ"}
        return [s for s in self.get_stocks() if s not in etf_set]

    def get_sector_etfs(self) -> List[str]:
        """Return sector ETF symbols for correlation analysis."""
        return list(SECTOR_ETFS.values())

    def refresh(self):
        """Force refresh the cached stock list."""
        self._cached_stocks = None
