from langchain.callbacks.base import BaseCallbackHandler
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
logger = logging.getLogger(__name__)


class LLMUsageTracker(BaseCallbackHandler):
    """Callback handler to track LLM usage and costs"""

    def __init__(self, db_manager, agent_execution_id: Optional[str] = None):
        self.db_manager = db_manager
        self.agent_execution_id = agent_execution_id
        self.current_call_data = {}

        # OpenAI pricing (as of 2024 - update as needed)
        self.pricing = {
            # GPT-4 family
            'gpt-4': {'input': 0.03, 'output': 0.06},
            'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
            'gpt-4-turbo-preview': {'input': 0.01, 'output': 0.03},
            'gpt-4-1106-preview': {'input': 0.01, 'output': 0.03},
            'gpt-4-0125-preview': {'input': 0.01, 'output': 0.03},

            # GPT-3.5 family
            'gpt-3.5-turbo': {'input': 0.001, 'output': 0.002},
            'gpt-3.5-turbo-1106': {'input': 0.001, 'output': 0.002},
            'gpt-3.5-turbo-0125': {'input': 0.001, 'output': 0.002},

            # O1 family (if exists)
            'o1': {'input': 0.015, 'output': 0.06},
            'o1-preview': {'input': 0.015, 'output': 0.06},
            'o1-mini': {'input': 0.003, 'output': 0.012},

            # Common variations and aliases
            'gpt-4o': {'input': 0.01, 'output': 0.03},
            'gpt-4o-mini': {'input': 0.003, 'output': 0.012},

            # Default fallback for unknown models
            'unknown': {'input': 0.01, 'output': 0.03}
        }

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """Called when LLM starts running"""
        self.current_call_data = {
            'model_name': serialized.get('model_name', kwargs.get('invocation_params', {}).get('model', 'unknown')),
            'prompts': prompts,
            'start_time': datetime.utcnow()
        }
        logger.info(f"LLM call started: {self.current_call_data['model_name']}")

    def on_llm_end(self, response, **kwargs) -> None:
        """Called when LLM ends running"""
        try:
            # Extract token usage
            usage = response.llm_output.get('token_usage', {}) if response.llm_output else {}

            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)

            model_name = self.current_call_data.get('model_name', 'unknown')

            # Calculate cost estimate
            cost_estimate = self._calculate_cost(model_name, prompt_tokens, completion_tokens)

            # Save to database
            if self.db_manager:
                self.db_manager.save_llm_usage(
                    agent_execution_id=self.agent_execution_id,
                    model_name=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    call_type='agent_execution',
                    request_data={'prompts': self.current_call_data.get('prompts', [])},
                    response_data={'generations': len(response.generations)},
                    cost_estimate=cost_estimate
                )

            logger.info(f"LLM call completed: {model_name} - {total_tokens} tokens, ${cost_estimate:.4f}")

        except Exception as e:
            logger.error(f"Error tracking LLM usage: {e}")

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        """Called when LLM errors"""
        logger.error(f"LLM call error: {error}")

    def _calculate_cost(self, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate estimated cost based on token usage"""
        if model_name not in self.pricing:
            logger.warning(f"Unknown model for pricing: {model_name}")
            return 0.0

        pricing = self.pricing[model_name]
        input_cost = (prompt_tokens / 1000) * pricing['input']
        output_cost = (completion_tokens / 1000) * pricing['output']

        return input_cost + output_cost