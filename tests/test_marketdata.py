
from market_data.data_fetch import DatabaseIntegratedMarketDataFetcher

print("Testing Market Data Fetcher...")

fetcher = MarketDataFetcher()

# # Test basic functionality
snapshot = fetcher.get_market_snapshot()
print(f"Fetched data for {len(snapshot.data_points)} symbols")

# # Test market regime assessment
# regime = fetcher.assess_market_regime(snapshot)
# print(f"Market regime: {regime}")
#
# # Test sector data
# sector_data = fetcher.get_sector_rotation_data()
# print(f"Sector data: {len(sector_data.get('sectors', {}))} sectors")

