from datetime import datetime
from typing import Any, Dict, List

from utils.llm_provider import create_llm
from utils.logging_config import get_logger

logger = get_logger(__name__)


class MarketMovementAnalyzer:
    """Separate class for analyzing market movements between two snapshots"""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = create_llm(model=model, temperature=0.1)
        logger.info(f"Market Movement Analyzer initialized with {model}")

    def analyze_market_movement(
        self, historical_data: List[Dict[str, Any]], current_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze market movement between historical and current snapshots

        Args:
            historical_data: Market data from when Fed content was scraped
            current_data: Current market data snapshot

        Returns:
            Dict with analysis results and commentary
        """

        try:
            prompt = self._create_movement_analysis_prompt(
                historical_data, current_data
            )
            response = self.llm.invoke(prompt)

            if hasattr(response, "content"):
                commentary = response.content.strip()
            else:
                commentary = str(response).strip()

            return {
                "success": True,
                "commentary": commentary,
                "historical_data_points": len(historical_data),
                "current_data_points": len(current_data),
                "analysis_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error analyzing market movement: {e}")
            return {
                "success": False,
                "error": str(e),
                "commentary": "Market movement analysis unavailable due to technical error.",
            }

    def _create_movement_analysis_prompt(
        self, historical_data: List[Dict[str, Any]], current_data: List[Dict[str, Any]]
    ) -> str:
        """Create prompt for market movement analysis"""

        historical_summary = self._summarize_market_data(historical_data, "Historical")
        current_summary = self._summarize_market_data(current_data, "Current")

        prompt = f"""
Analyze the market movement between these two snapshots and provide investment-focused commentary.

{historical_summary}

{current_summary}

Please provide a concise 2-3 paragraph analysis that:
1. Identifies the most significant price movements and trends
2. Highlights any notable sector rotations or shifts
3. Assesses overall market sentiment change (risk-on vs risk-off)
4. Provides actionable insights for stock screening strategy

Focus on practical implications for investment decisions rather than general market observations.
Be specific about which sectors or asset classes show strength or weakness.
        """

        return prompt

    def _summarize_market_data(
        self, market_data: List[Dict[str, Any]], label: str
    ) -> str:
        """Summarize market data for prompt"""

        if not market_data:
            return f"{label} Market Data: No data available"

        # Group by data type
        indicators = [
            md for md in market_data if md.get("data_type") == "market_indicators"
        ]
        sectors = [md for md in market_data if md.get("data_type") == "sector_rotation"]
        stocks = [md for md in market_data if md.get("data_type") == "individual_stock"]

        summary = f"{label} Market Data:\n"

        if indicators:
            summary += "  Market Indicators:\n"
            for md in indicators[:10]:  # Top 10
                ticker = md.get("ticker", "N/A")
                price = md.get("price", 0)
                change_pct = md.get("change_percent", 0)
                summary += f"    {ticker}: ${price:.2f} ({change_pct:+.1f}%)\n"

        if sectors:
            summary += "  Sector Performance:\n"
            for md in sectors[:10]:  # Top 10
                ticker = md.get("ticker", "N/A")
                price = md.get("price", 0)
                change_pct = md.get("change_percent", 0)
                summary += f"    {ticker}: ${price:.2f} ({change_pct:+.1f}%)\n"

        if stocks:
            summary += "  Individual Stocks:\n"
            for md in stocks[:5]:  # Top 5
                ticker = md.get("ticker", "N/A")
                price = md.get("price", 0)
                change_pct = md.get("change_percent", 0)
                summary += f"    {ticker}: ${price:.2f} ({change_pct:+.1f}%)\n"

        return summary
