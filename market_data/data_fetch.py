from typing import Dict, Any, Optional, List
from datetime import datetime

from market_data.dataproviders import TiingoProvider, YFinanceProvider

from database.database import DatabaseManager


from utils.logging_config import get_logger

logger = get_logger(__name__)


class DatabaseIntegratedMarketDataFetcher:
    """Market data fetcher that saves to dedicated MarketData table"""

    def __init__(self,
                 database_url: str,
                 config: Optional[Dict[str, Any]] = None):
        """Initialize with database integration"""
        self.config = config or self._get_default_config()

        # Initialize database manager
        self.db_manager = DatabaseManager(database_url)
        self.db_manager.create_tables()

        # Initialize providers
        self.providers = []

        # Add yfinance provider
        yfinance_config = self.config.get('yfinance', {})
        yfinance_provider = YFinanceProvider(yfinance_config)
        if yfinance_provider.is_available():
            self.providers.append(yfinance_provider)
            logger.info("yfinance provider initialized")

        if not self.providers:
            logger.error("No market data providers available!")

        # Market indicators
        self.market_indicators = [
            "SPY", "QQQ", "IWM", "DIA",  # Equities
            "^VIX",  # Volatility
            "TLT", "IEF", "HYG", "LQD", "^TNX",  # Bonds and yields
            "GLD", "USO", "DBA", "DBC",  # Inflation proxies
            "UUP", "BTC-USD",  # Dollar and crypto
            "EFA", "EEM", "FXI",  # International
        ]

        # Sector ETFs
        self.sector_etfs = [
            'XLK',  # Technology
            'XLF',  # Financial
            'XLV',  # Healthcare
            'XLE',  # Energy
            'XLI',  # Industrial
            'XLY',  # Consumer Discretionary
            'XLP',  # Consumer Staples
            'XLU',  # Utilities
            'XLRE',  # Real Estate
            'XLB',  # Materials
            'XLC'  # Communication
        ]

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'yfinance': {
                'rate_limit_delay': 0.2,
                'max_retries': 2
            }
        }

    def collect_and_save_market_data(self,
                                     scraped_data_id: Optional[str] = None,
                                     additional_symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Collect market data and save to MarketData table"""

        logger.info("Collecting market data and saving to MarketData table")

        results = {
            'market_indicators': [],
            'sector_rotation': [],
            'individual_stocks': [],
            'scraped_data_id': scraped_data_id,
            'timestamp': datetime.now().isoformat()
        }

        # Collect market indicators
        logger.info("Collecting market indicators...")
        market_data_ids = self._collect_and_save_symbols(
            symbols=self.market_indicators,
            data_type='market_indicators',
            scraped_data_id=scraped_data_id
        )
        results['market_indicators'] = market_data_ids

        # Collect sector rotation data
        logger.info("Collecting sector rotation data...")
        sector_data_ids = self._collect_and_save_symbols(
            symbols=self.sector_etfs,
            data_type='sector_rotation',
            scraped_data_id=scraped_data_id
        )
        results['sector_rotation'] = sector_data_ids

        # Collect additional individual stocks if provided
        if additional_symbols:
            logger.info(f"Collecting individual stocks: {additional_symbols}")
            individual_data_ids = self._collect_and_save_symbols(
                symbols=additional_symbols,
                data_type='individual_stock',
                scraped_data_id=scraped_data_id
            )
            results['individual_stocks'] = individual_data_ids

        total_saved = len(results['market_indicators']) + len(results['sector_rotation']) + len(
            results['individual_stocks'])
        logger.info(f"Saved {total_saved} market data points to database")

        return results

    def collect_and_save_market_data_with_batch(self,
                                                scraped_data_id: Optional[str] = None,
                                                additional_symbols: Optional[List[str]] = None,
                                                batch_timestamp: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Collect market data and save with consistent batch timestamp

        Args:
            scraped_data_id: Optional link to scraped data (None for independent collection)
            additional_symbols: Additional symbols to collect
            batch_timestamp: Consistent timestamp for this batch (defaults to now)

        Returns:
            Results with batch timestamp and IDs
        """

        if batch_timestamp is None:
            batch_timestamp = datetime.utcnow()

        logger.info(f"Collecting market data with batch timestamp: {batch_timestamp}")

        all_market_data = []

        # Collect market indicators
        for provider in self.providers:
            try:
                # Market indicators
                indicator_data = provider.get_data(self.market_indicators)
                for dp in indicator_data:
                    all_market_data.append({
                        'ticker': dp.symbol,
                        'price': dp.price,
                        'change_percent': dp.change_percent,
                        'volume': dp.volume,
                        'market_cap': dp.market_cap,
                        'data_type': 'market_indicators',
                        'data_source': dp.source,
                        'provider_timestamp': getattr(dp, 'timestamp', None)
                    })

                # Sector data
                sector_data = provider.get_data(self.sector_etfs)
                for dp in sector_data:
                    all_market_data.append({
                        'ticker': dp.symbol,
                        'price': dp.price,
                        'change_percent': dp.change_percent,
                        'volume': dp.volume,
                        'market_cap': dp.market_cap,
                        'data_type': 'sector_rotation',
                        'data_source': dp.source,
                        'provider_timestamp': getattr(dp, 'timestamp', None)
                    })

                # Additional symbols
                if additional_symbols:
                    additional_data = provider.get_data(additional_symbols)
                    for dp in additional_data:
                        all_market_data.append({
                            'ticker': dp.symbol,
                            'price': dp.price,
                            'change_percent': dp.change_percent,
                            'volume': dp.volume,
                            'market_cap': dp.market_cap,
                            'data_type': 'individual_stock',
                            'data_source': dp.source,
                            'provider_timestamp': getattr(dp, 'timestamp', None)
                        })

                # If we got data, don't try other providers
                if all_market_data:
                    break

            except Exception as e:
                logger.error(f"Provider {provider.name} failed: {e}")
                continue

        # Save as batch
        market_data_ids = self.db_manager.save_market_data_batch(
            market_data_points=all_market_data,
            batch_timestamp=batch_timestamp,
            scraped_data_id=scraped_data_id
        )

        return {
            'success': True,
            'batch_timestamp': batch_timestamp.isoformat(),
            'market_data_ids': market_data_ids,
            'total_points': len(all_market_data),
            'scraped_data_id': scraped_data_id,
            'summary': {
                'market_indicators': len([d for d in all_market_data if d['data_type'] == 'market_indicators']),
                'sector_rotation': len([d for d in all_market_data if d['data_type'] == 'sector_rotation']),
                'individual_stocks': len([d for d in all_market_data if d['data_type'] == 'individual_stock'])
            }
        }

    def _collect_and_save_symbols(self,
                                  symbols: List[str],
                                  data_type: str,
                                  scraped_data_id: Optional[str] = None) -> List[str]:
        """Collect data for symbols and save to MarketData table"""

        market_data_ids = []

        for provider in self.providers:
            try:
                data_points = provider.get_data(symbols)

                for dp in data_points:
                    try:
                        # Parse provider timestamp if available
                        provider_timestamp = None
                        if hasattr(dp, 'timestamp') and dp.timestamp:
                            try:
                                provider_timestamp = datetime.fromisoformat(dp.timestamp.replace('Z', '+00:00'))
                            except:
                                provider_timestamp = None

                        # Save to MarketData table
                        market_data_id = self.db_manager.save_market_data_point(
                            ticker=dp.symbol,
                            price=dp.price,
                            data_type=data_type,
                            data_source=dp.source,
                            scraped_data_id=scraped_data_id,
                            change_percent=dp.change_percent,
                            volume=dp.volume,
                            market_cap=dp.market_cap,
                            provider_timestamp=provider_timestamp
                        )

                        market_data_ids.append(market_data_id)

                        logger.debug(f"Saved {dp.symbol}: ${dp.price:.2f} from {dp.source}")

                    except Exception as e:
                        logger.error(f"Error saving market data for {dp.symbol}: {e}")
                        continue

                # If we got data, don't try other providers
                if data_points:
                    break

            except Exception as e:
                logger.error(f"Provider {provider.name} failed: {e}")
                continue

        return market_data_ids


def fetch_and_save_market_data_to_table(
        fed_content_items: List[Any],
        database_url: str,
        agent_execution_id: Optional[str] = None,
        additional_symbols: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Fetch market data and save to dedicated MarketData table

    Args:
        fed_content_items: List of Fed content items
        database_url: Database connection string
        agent_execution_id: Agent execution ID
        additional_symbols: Additional symbols to collect
        config: Market data configuration

    Returns:
        Dict with results and database IDs
    """

    logger.info(f"Collecting market data for {len(fed_content_items)} Fed content items")

    try:
        # Initialize fetcher
        fetcher = DatabaseIntegratedMarketDataFetcher(database_url, config)

        # Get Fed content scraped_data_id (use first one if multiple)
        scraped_data_id = None
        if fed_content_items:
            for item in fed_content_items:
                if hasattr(item, 'scraped_data_id'):
                    scraped_data_id = item.scraped_data_id
                    break

        # Collect and save market data
        results = fetcher.collect_and_save_market_data(
            scraped_data_id=agent_execution_id,
            additional_symbols=additional_symbols
        )

        # Create summary
        total_points = len(results['market_indicators']) + len(results['sector_rotation']) + len(
            results['individual_stocks'])

        return {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'market_data_results': results,
            'summary': {
                'total_data_points': total_points,
                'market_indicators': len(results['market_indicators']),
                'sector_rotation': len(results['sector_rotation']),
                'individual_stocks': len(results['individual_stocks']),
                'linked_to_scraped_id': scraped_data_id
            },
            'metadata': {
                'agent_execution_id': agent_execution_id,
                'fed_content_count': len(fed_content_items)
            }
        }

    except Exception as e:
        logger.error(f"Error collecting market data: {e}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat(),
            'metadata': {'agent_execution_id': agent_execution_id}
        }
