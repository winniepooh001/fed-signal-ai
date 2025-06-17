#!/usr/bin/env python3
"""
Real-Time Market Data Fetcher Module

Modular market data fetcher supporting multiple providers:
- Tiingo (primary) - requires API key, high quality data
- yfinance (backup) - free but rate limited

Usage:
    from market_data.fetcher import MarketDataFetcher

    fetcher = MarketDataFetcher()
    data = fetcher.get_market_snapshot(['SPY', 'QQQ', 'VIX'])
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict
from pathlib import Path
import asyncio
import logging

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class MarketDataPoint:
    """Standardized market data point"""
    symbol: str
    price: float
    change: float
    change_percent: float
    volume: int
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    timestamp: str = ""
    source: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class MarketSnapshot:
    """Complete market snapshot with multiple data points"""
    timestamp: str
    data_points: List[MarketDataPoint]
    market_indicators: Dict[str, Any]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'data_points': [asdict(dp) for dp in self.data_points],
            'market_indicators': self.market_indicators,
            'metadata': self.metadata
        }

