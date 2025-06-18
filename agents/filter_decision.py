from typing import Any, Dict

from utils.llm_provider import create_llm
from utils.logging_config import get_logger

logger = get_logger()


class FilterDecisionAgent:
    """LLM agent to decide if new filtering is warranted"""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = create_llm(model=model, temperature=0.1)
        logger.info(f"Filter Decision Agent initialized with {model}")

    def should_create_new_filter(
        self,
        most_recent_filter: Dict[str, Any],
        fed_summary: Dict[str, Any],
        movement_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Determine if new filtering is warranted based on recent filter and current conditions

        Returns:
            Dict with 'create_new_filter': bool and 'reasoning': str
        """

        try:
            prompt = self._create_filter_decision_prompt(
                most_recent_filter, fed_summary, movement_analysis
            )
            response = self.llm.invoke(prompt)

            if hasattr(response, "content"):
                response_text = response.content.strip()
            else:
                response_text = str(response).strip()

            # Parse response (expect YES/NO at start)
            decision = response_text.upper().startswith("YES")

            return {
                "create_new_filter": decision,
                "reasoning": response_text,
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error in filter decision: {e}")
            return {
                "create_new_filter": True,  # Default to creating filter on error
                "reasoning": f"Error in decision process: {e}",
                "success": False,
            }

    def _create_filter_decision_prompt(
        self,
        most_recent_filter: Dict[str, Any],
        fed_summary: Dict[str, Any],
        movement_analysis: Dict[str, Any],
    ) -> str:
        """Create prompt for filter decision"""

        # Extract recent filter info
        recent_timestamp = most_recent_filter.get("timestamp", "Unknown")
        recent_fed_count = most_recent_filter.get("fed_item_count", 0)
        recent_sentiment = most_recent_filter.get("fed_sentiment", "UNKNOWN")
        recent_market_condition = most_recent_filter.get("market_condition", "UNKNOWN")

        # Current conditions
        current_fed_count = fed_summary.get("item_count", 0)
        current_sentiment = fed_summary.get("overall_sentiment", "NEUTRAL")
        current_market_commentary = movement_analysis.get("commentary", "No analysis")[
            :300
        ]

        prompt = f"""
You are a financial screening decision agent. Determine if a NEW stock screening filter is warranted based on the comparison below.

MOST RECENT FILTER (Last Run):
- Timestamp: {recent_timestamp}
- Fed Communications Analyzed: {recent_fed_count}
- Fed Sentiment: {recent_sentiment}
- Market Condition: {recent_market_condition}

CURRENT CONDITIONS:
- Fed Communications: {current_fed_count}
- Fed Sentiment: {current_sentiment}
- Market Analysis: {current_market_commentary}

DECISION CRITERIA:
Create a new filter ONLY if there are SIGNIFICANT changes that warrant different screening criteria:
1. Sentiment shift (POSITIVE ↔ NEGATIVE)
2. New Fed communications 
3. Significant market condition changes
4. Last filter is older than 7 days

Otherwise, the recent filter is still relevant and no new screening is needed.

Start your response with either "YES" or "NO" followed by your reasoning.

RESPONSE:"""

        return prompt
