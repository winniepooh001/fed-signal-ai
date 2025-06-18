from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain.callbacks.base import BaseCallbackHandler

from utils.logging_config import get_logger

logger = get_logger()


class UniversalLLMUsageTracker(BaseCallbackHandler):
    """Universal LLM usage tracker that works with any provider"""

    def __init__(self, db_manager, agent_execution_id: Optional[str] = None):
        self.db_manager = db_manager
        self.agent_execution_id = agent_execution_id
        self.current_call_data = {}

        # Universal pricing database - will be extended as we add providers
        self.pricing_db = self._load_pricing_database()

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs
    ) -> None:
        """Called when LLM starts running"""
        model_info = self._extract_model_info(serialized, kwargs)

        self.current_call_data = {
            "model_name": model_info["model"],
            "provider": model_info["provider"],
            "prompts": prompts,
            "start_time": datetime.utcnow(),
            "prompt_length": sum(len(p) for p in prompts),
        }

        logger.debug(
            f"LLM call started: {model_info['provider']}/{model_info['model']}"
        )

    def on_llm_end(self, response, **kwargs) -> None:
        """Called when LLM ends running"""
        try:
            model_name = self.current_call_data.get("model_name", "unknown")
            provider = self.current_call_data.get("provider", "unknown")

            # Extract token usage using universal strategies
            usage_info = self._extract_token_usage_universal(response, provider)

            prompt_tokens = usage_info["prompt_tokens"]
            completion_tokens = usage_info["completion_tokens"]
            total_tokens = usage_info["total_tokens"]

            logger.debug(
                f"Token usage: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}"
            )

            # Calculate cost using universal pricing
            cost_estimate = self._calculate_cost_universal(
                provider, model_name, prompt_tokens, completion_tokens
            )

            # Save to database
            if self.db_manager:
                self.db_manager.save_llm_usage(
                    agent_execution_id=self.agent_execution_id,
                    model_name=f"{provider}/{model_name}",  # Store with provider prefix
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    call_type="agent_execution",
                    request_data={"prompts": self.current_call_data.get("prompts", [])},
                    response_data={
                        "provider": provider,
                        "generations": self._count_generations(response),
                    },
                    cost_estimate=cost_estimate,
                )

            logger.info(
                f"LLM call completed: {provider}/{model_name} - {total_tokens} tokens, ${cost_estimate:.4f}"
            )

        except Exception as e:
            logger.error(f"Error tracking LLM usage: {e}", exc_info=True)

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        """Called when LLM errors"""
        model_name = self.current_call_data.get("model_name", "unknown")
        provider = self.current_call_data.get("provider", "unknown")
        logger.error(f"LLM call error ({provider}/{model_name}): {error}")

    def _extract_model_info(
        self, serialized: Dict[str, Any], kwargs: Dict[str, Any]
    ) -> Dict[str, str]:
        """Extract model name and provider from various sources"""

        # Try to get model name from multiple locations
        model_sources = [
            serialized.get("model_name"),
            serialized.get("model"),
            kwargs.get("invocation_params", {}).get("model"),
            kwargs.get("model"),
            serialized.get("kwargs", {}).get("model"),
            serialized.get("kwargs", {}).get("model_name"),
            (
                getattr(kwargs.get("run_manager"), "name", None)
                if kwargs.get("run_manager")
                else None
            ),
        ]

        model_name = "unknown"
        for model in model_sources:
            if model:
                model_name = str(model)
                break

        # Detect provider from model name or class name
        provider = self._detect_provider(model_name, serialized)

        return {"model": model_name, "provider": provider}

    def _detect_provider(self, model_name: str, serialized: Dict[str, Any]) -> str:
        """Detect provider from model name or class information"""

        model_lower = model_name.lower()
        class_name = serialized.get("_type", "").lower()

        # Check for provider in model name
        if "/" in model_name:
            return model_name.split("/")[0]

        # Provider detection based on model patterns
        if any(x in model_lower for x in ["gpt", "o1", "chatgpt"]):
            return "openai"
        elif any(x in model_lower for x in ["gemini", "bard"]):
            return "google"
        elif any(x in model_lower for x in ["claude"]):
            return "anthropic"
        elif any(x in model_lower for x in ["deepseek"]):
            return "deepseek"

        # Provider detection based on class name
        if any(x in class_name for x in ["openai", "chatopenai"]):
            return "openai"
        elif any(x in class_name for x in ["google", "gemini"]):
            return "google"
        elif any(x in class_name for x in ["anthropic", "claude"]):
            return "anthropic"
        elif "deepseek" in class_name:
            return "deepseek"

        # Check base_url for provider hints
        base_url = serialized.get("kwargs", {}).get("base_url", "")
        if "deepseek" in base_url:
            return "deepseek"
        elif "anthropic" in base_url:
            return "anthropic"
        elif "google" in base_url or "googleapis" in base_url:
            return "google"

        # Default fallback
        logger.warning(
            f"Could not detect provider for model '{model_name}', defaulting to 'unknown'"
        )
        return "unknown"

    def _extract_token_usage_universal(self, response, provider: str) -> Dict[str, int]:
        """Universal token extraction that works across all providers"""

        strategies = [
            self._strategy_response_metadata,
            self._strategy_llm_output,
            self._strategy_usage_metadata,
            self._strategy_generations,
            self._strategy_provider_specific,
            self._strategy_estimate_fallback,
        ]

        for strategy in strategies:
            try:
                result = strategy(response, provider)
                if result and result.get("total_tokens", 0) > 0:
                    logger.debug(
                        f"Token extraction successful using {strategy.__name__}"
                    )
                    return result
            except Exception as e:
                logger.debug(f"{strategy.__name__} failed: {e}")
                continue

        # Final fallback
        logger.warning("All token extraction strategies failed, using zero counts")
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _strategy_response_metadata(
        self, response, provider: str
    ) -> Optional[Dict[str, int]]:
        """Extract from response.response_metadata (common in newer LangChain)"""
        if hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage", {})
            if usage:
                return self._normalize_token_fields(usage)
        return None

    def _strategy_llm_output(self, response, provider: str) -> Optional[Dict[str, int]]:
        """Extract from response.llm_output.token_usage (traditional location)"""
        if hasattr(response, "llm_output") and response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            if usage:
                return self._normalize_token_fields(usage)
        return None

    def _strategy_usage_metadata(
        self, response, provider: str
    ) -> Optional[Dict[str, int]]:
        """Extract from response.usage_metadata (newest LangChain versions)"""
        if hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            if usage:
                # Handle both dict and object formats
                if hasattr(usage, "__dict__"):
                    usage_dict = usage.__dict__
                else:
                    usage_dict = usage
                return self._normalize_token_fields(usage_dict)
        return None

    def _strategy_generations(
        self, response, provider: str
    ) -> Optional[Dict[str, int]]:
        """Extract from response.generations (some providers)"""
        if hasattr(response, "generations") and response.generations:
            for generation in response.generations:
                if (
                    hasattr(generation, "generation_info")
                    and generation.generation_info
                ):
                    usage = generation.generation_info.get("token_usage", {})
                    if usage:
                        return self._normalize_token_fields(usage)
        return None

    def _strategy_provider_specific(
        self, response, provider: str
    ) -> Optional[Dict[str, int]]:
        """Provider-specific extraction methods"""

        if provider == "anthropic":
            # Anthropic sometimes stores usage in different locations
            if hasattr(response, "response_metadata"):
                usage = response.response_metadata.get("usage", {})
                if usage:
                    return {
                        "prompt_tokens": usage.get("input_tokens", 0),
                        "completion_tokens": usage.get("output_tokens", 0),
                        "total_tokens": usage.get("input_tokens", 0)
                        + usage.get("output_tokens", 0),
                    }

        elif provider == "google":
            # Google Gemini specific extraction
            if hasattr(response, "response_metadata"):
                usage = response.response_metadata.get("usage_metadata", {})
                if usage:
                    return self._normalize_token_fields(usage)

        return None

    def _strategy_estimate_fallback(
        self, response, provider: str
    ) -> Optional[Dict[str, int]]:
        """Estimate tokens based on content length (last resort)"""
        try:
            # Rough estimation: ~4 characters per token for English text
            prompt_length = self.current_call_data.get("prompt_length", 0)
            estimated_prompt_tokens = max(1, prompt_length // 4)

            # Estimate completion tokens from response content
            completion_text = self._extract_completion_text(response)
            estimated_completion_tokens = max(1, len(completion_text) // 4)

            logger.warning(
                f"Using token estimation fallback: ~{estimated_prompt_tokens + estimated_completion_tokens} tokens"
            )

            return {
                "prompt_tokens": estimated_prompt_tokens,
                "completion_tokens": estimated_completion_tokens,
                "total_tokens": estimated_prompt_tokens + estimated_completion_tokens,
            }
        except:
            return None

    def _normalize_token_fields(self, usage: Dict[str, Any]) -> Dict[str, int]:
        """Normalize different token field names across providers"""

        # Common field name variations
        prompt_fields = ["prompt_tokens", "input_tokens", "prompt_token_count"]
        completion_fields = [
            "completion_tokens",
            "output_tokens",
            "completion_token_count",
            "generated_tokens",
        ]
        total_fields = ["total_tokens", "total_token_count"]

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        # Extract prompt tokens
        for field in prompt_fields:
            if field in usage and usage[field] is not None:
                prompt_tokens = int(usage[field])
                break

        # Extract completion tokens
        for field in completion_fields:
            if field in usage and usage[field] is not None:
                completion_tokens = int(usage[field])
                break

        # Extract total tokens (or calculate)
        for field in total_fields:
            if field in usage and usage[field] is not None:
                total_tokens = int(usage[field])
                break

        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def _extract_completion_text(self, response) -> str:
        """Extract completion text for estimation purposes"""
        try:
            if hasattr(response, "content"):
                return str(response.content)
            elif hasattr(response, "generations") and response.generations:
                texts = []
                for gen in response.generations:
                    if hasattr(gen, "text"):
                        texts.append(gen.text)
                    elif hasattr(gen, "message") and hasattr(gen.message, "content"):
                        texts.append(gen.message.content)
                return " ".join(texts)
            return ""
        except:
            return ""

    def _count_generations(self, response) -> int:
        """Count number of generations in response"""
        try:
            if hasattr(response, "generations"):
                return len(response.generations)
            return 1
        except:
            return 1

    def _load_pricing_database(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        """Load pricing information for all providers"""
        return {
            "openai": {
                "gpt-4o": {"input": 0.005, "output": 0.015},
                "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
                "gpt-4-turbo-preview": {"input": 0.01, "output": 0.03},
                "gpt-4": {"input": 0.03, "output": 0.06},
                "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
                "o1-preview": {"input": 0.015, "output": 0.06},
                "o1-mini": {"input": 0.003, "output": 0.012},
            },
            "google": {
                "gemini-pro": {"input": 0.0005, "output": 0.0015},
                "gemini-1.5-pro": {"input": 0.0035, "output": 0.0105},
                "gemini-1.5-flash": {"input": 0.00035, "output": 0.00105},
                "gemini-ultra": {"input": 0.01, "output": 0.03},
            },
            "anthropic": {
                "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
                "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
                "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
                "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
            },
            "deepseek": {
                "deepseek-chat": {"input": 0.00014, "output": 0.00028},
                "deepseek-coder": {"input": 0.00014, "output": 0.00028},
                "deepseek-v2.5": {"input": 0.00014, "output": 0.00028},
            },
            "unknown": {"default": {"input": 0.01, "output": 0.03}},
        }

    def _calculate_cost_universal(
        self, provider: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        """Calculate cost using universal pricing database"""

        provider_pricing = self.pricing_db.get(provider, self.pricing_db["unknown"])

        # Try exact model match first
        model_pricing = provider_pricing.get(model)

        # If no exact match, try partial matching
        if not model_pricing:
            for pricing_model, pricing in provider_pricing.items():
                if pricing_model in model or model in pricing_model:
                    model_pricing = pricing
                    break

        # Fallback to default for provider or unknown
        if not model_pricing:
            if "default" in provider_pricing:
                model_pricing = provider_pricing["default"]
            else:
                model_pricing = self.pricing_db["unknown"]["default"]
                logger.warning(
                    f"No pricing found for {provider}/{model}, using default rates"
                )

        input_cost = (prompt_tokens / 1000) * model_pricing["input"]
        output_cost = (completion_tokens / 1000) * model_pricing["output"]

        return input_cost + output_cost


# Convenience alias for backwards compatibility
LLMUsageTracker = UniversalLLMUsageTracker
