import os
from typing import Any, Dict, List

from market_data.data_model import MarketDataPoint
from utils.logging_config import get_logger

logger = get_logger(__name__)

import time


class MarketDataProvider:
    """Abstract base class for market data providers"""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.rate_limit_delay = config.get("rate_limit_delay", 0.1)
        self.max_retries = config.get("max_retries", 3)

    def get_data(self, symbols: List[str]) -> List[MarketDataPoint]:
        """Override in subclasses"""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if provider is available and configured"""
        raise NotImplementedError


class TiingoProvider(MarketDataProvider):
    """Tiingo API provider - high quality, requires API key"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("tiingo", config)
        self.api_key = config.get("api_key") or os.getenv("TIINGO_API_KEY")
        self.base_url = "https://api.tiingo.com/tiingo/daily"

        if self.api_key:
            self.client = self._init_client()
        else:
            self.client = None
            logger.warning("Tiingo API key not found - provider disabled")

    def _init_client(self):
        """Initialize Tiingo client"""
        try:
            from tiingo import TiingoClient

            config = {
                "api_key": self.api_key,
                "session": True,  # Reuse HTTP session for better performance
            }
            return TiingoClient(config)
        except ImportError:
            logger.error("Tiingo library not installed. Run: pip install tiingo")
            return None
        except Exception as e:
            logger.error(f"Error initializing Tiingo client: {e}")
            return None

    def is_available(self) -> bool:
        return self.client is not None and self.api_key is not None

    def get_data(self, symbols: List[str]) -> List[MarketDataPoint]:
        """Get real-time data from Tiingo"""
        if not self.is_available():
            return []

        data_points = []

        for symbol in symbols:
            try:
                # Get latest price data
                price_data = self.client.get_ticker_price(
                    symbol,
                    frequency="1min",  # Get most recent data
                    columns="open,close,high,low,volume",
                )

                if price_data and len(price_data) > 0:
                    latest = price_data[-1]  # Most recent data point

                    # Get metadata for additional info
                    try:
                        metadata = self.client.get_ticker_metadata(symbol)
                        market_cap = metadata.get("marketCap")
                        pe_ratio = metadata.get("peRatio")
                    except:
                        market_cap = None
                        pe_ratio = None

                    # Calculate change (approximate from OHLC)
                    price = latest.get("close", latest.get("open", 0))
                    prev_close = latest.get("open", price)
                    change = price - prev_close
                    change_percent = (
                        (change / prev_close * 100) if prev_close != 0 else 0
                    )

                    data_point = MarketDataPoint(
                        symbol=symbol.upper(),
                        price=price,
                        change=change,
                        change_percent=change_percent,
                        volume=int(latest.get("volume", 0)),
                        market_cap=market_cap,
                        pe_ratio=pe_ratio,
                        source="tiingo",
                    )

                    data_points.append(data_point)
                    logger.debug(f"Tiingo: Got data for {symbol}: ${price:.2f}")

                # Rate limiting
                time.sleep(self.rate_limit_delay)

            except Exception as e:
                logger.warning(f"Tiingo error for {symbol}: {e}")
                continue

        return data_points


class YFinanceProvider(MarketDataProvider):
    """yfinance provider - free backup option"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__("yfinance", config)
        self.yf = self._init_yfinance()

    def _init_yfinance(self):
        """Initialize yfinance"""
        try:
            import yfinance as yf

            return yf
        except ImportError:
            logger.error("yfinance library not installed. Run: pip install yfinance")
            return None

    def is_available(self) -> bool:
        return self.yf is not None

    def get_data(self, symbols: List[str]) -> List[MarketDataPoint]:
        """Get data from yfinance"""
        if not self.is_available():
            return []

        data_points = []

        # Batch request for better performance
        try:
            tickers = self.yf.Tickers(" ".join(symbols))

            for symbol in symbols:
                try:
                    ticker = getattr(tickers.tickers, symbol.upper(), None)
                    if not ticker:
                        ticker = self.yf.Ticker(symbol)

                    # Get current data
                    info = ticker.info
                    hist = ticker.history(
                        period="1D", interval="1m"
                    )  # Get last 2 days for change calc

                    if not hist.empty:
                        current_price = hist["Close"].iloc[-1]
                        volume = int(hist["Volume"].iloc[-1])

                        # Calculate change
                        if len(hist) > 1:
                            prev_close = hist["Close"].iloc[-2]
                            change = current_price - prev_close
                            change_percent = (
                                (change / prev_close * 100) if prev_close != 0 else 0
                            )
                        else:
                            change = 0
                            change_percent = 0

                        data_point = MarketDataPoint(
                            symbol=symbol.upper(),
                            price=float(current_price),
                            change=float(change),
                            change_percent=float(change_percent),
                            volume=volume,
                            market_cap=info.get("marketCap"),
                            pe_ratio=info.get("trailingPE"),
                            source="yfinance",
                        )

                        data_points.append(data_point)
                        logger.debug(
                            f"yfinance: Got data for {symbol}: ${current_price:.2f}"
                        )

                except Exception as e:
                    logger.warning(f"yfinance error for {symbol}: {e}")
                    continue

                # Rate limiting to avoid being blocked
                time.sleep(self.rate_limit_delay)

        except Exception as e:
            logger.error(f"yfinance batch error: {e}")

        return data_points
