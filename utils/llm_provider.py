import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from utils.logging_config import get_logger

logger = get_logger()


class AbstractLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(self, model: str, temperature: float = 0.1, **kwargs):
        self.model = model
        self.temperature = temperature
        self.provider_name = self.__class__.__name__.replace("Provider", "").lower()
        self.kwargs = kwargs

    @abstractmethod
    def create_llm(self):
        """Create and return the LLM instance"""
        pass

    @abstractmethod
    def get_model_list(self) -> Dict[str, str]:
        """Return available models for this provider"""
        pass

    @abstractmethod
    def normalize_model_name(self, model: str) -> str:
        """Normalize model name to provider's format"""
        pass

    @abstractmethod
    def get_pricing_info(self) -> Dict[str, Dict[str, float]]:
        """Return pricing information for models"""
        pass


class OpenAIProvider(AbstractLLMProvider):
    """OpenAI provider implementation"""

    def create_llm(self):
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=self.normalize_model_name(self.model),
                temperature=self.temperature,
                **self.kwargs,
            )
        except ImportError:
            raise ImportError(
                "langchain_openai not installed. Run: pip install langchain-openai"
            )

    def get_model_list(self) -> Dict[str, str]:
        return {
            "gpt-4o": "gpt-4o",
            "gpt-4o-mini": "gpt-4o-mini",
            "gpt-4-turbo": "gpt-4-turbo-preview",
            "gpt-4": "gpt-4",
            "gpt-3.5-turbo": "gpt-3.5-turbo",
            "o1-preview": "o1-preview",
            "o1-mini": "o1-mini",
        }

    def normalize_model_name(self, model: str) -> str:
        """Normalize model name for OpenAI"""
        # Handle common aliases
        aliases = {
            "gpt4": "gpt-4",
            "gpt4o": "gpt-4o",
            "gpt4-mini": "gpt-4o-mini",
            "gpt35": "gpt-3.5-turbo",
            "chatgpt": "gpt-3.5-turbo",
        }
        return aliases.get(model.lower(), model)

    def get_pricing_info(self) -> Dict[str, Dict[str, float]]:
        return {
            "gpt-4o": {"input": 0.005, "output": 0.015},
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-4-turbo-preview": {"input": 0.01, "output": 0.03},
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
            "o1-preview": {"input": 0.015, "output": 0.06},
            "o1-mini": {"input": 0.003, "output": 0.012},
        }


class GoogleProvider(AbstractLLMProvider):
    """Google Gemini provider implementation"""

    def create_llm(self):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=self.normalize_model_name(self.model),
                temperature=self.temperature,
                **self.kwargs,
            )
        except ImportError:
            raise ImportError(
                "langchain_google_genai not installed. Run: pip install langchain-google-genai"
            )

    def get_model_list(self) -> Dict[str, str]:
        return {
            "gemini-pro": "gemini-pro",
            "gemini-1.5-pro": "gemini-1.5-pro",
            "gemini-1.5-flash": "gemini-1.5-flash",
            "gemini-ultra": "gemini-ultra",
        }

    def normalize_model_name(self, model: str) -> str:
        """Normalize model name for Google"""
        aliases = {
            "gemini": "gemini-pro",
            "gemini-pro-latest": "gemini-1.5-pro",
            "gemini-flash": "gemini-1.5-flash",
        }
        return aliases.get(model.lower(), model)

    def get_pricing_info(self) -> Dict[str, Dict[str, float]]:
        return {
            "gemini-pro": {"input": 0.0005, "output": 0.0015},
            "gemini-1.5-pro": {"input": 0.0035, "output": 0.0105},
            "gemini-1.5-flash": {"input": 0.00035, "output": 0.00105},
            "gemini-ultra": {"input": 0.01, "output": 0.03},  # Estimated
        }


class AnthropicProvider(AbstractLLMProvider):
    """Anthropic Claude provider implementation"""

    def create_llm(self):
        try:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=self.normalize_model_name(self.model),
                temperature=self.temperature,
                **self.kwargs,
            )
        except ImportError:
            raise ImportError(
                "langchain_anthropic not installed. Run: pip install langchain-anthropic"
            )

    def get_model_list(self) -> Dict[str, str]:
        return {
            "claude-3-opus": "claude-3-opus-20240229",
            "claude-3-sonnet": "claude-3-sonnet-20240229",
            "claude-3-haiku": "claude-3-haiku-20240307",
            "claude-3.5-sonnet": "claude-3-5-sonnet-20241022",
        }

    def normalize_model_name(self, model: str) -> str:
        """Normalize model name for Anthropic"""
        aliases = {
            "claude": "claude-3-sonnet-20240229",
            "claude-opus": "claude-3-opus-20240229",
            "claude-sonnet": "claude-3-sonnet-20240229",
            "claude-haiku": "claude-3-haiku-20240307",
        }
        return aliases.get(model.lower(), model)

    def get_pricing_info(self) -> Dict[str, Dict[str, float]]:
        return {
            "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
            "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
            "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
        }


class DeepSeekProvider(AbstractLLMProvider):
    """DeepSeek provider implementation"""

    def create_llm(self):
        try:
            from langchain_deepseek import (
                ChatDeepSeek,
            )  # DeepSeek uses OpenAI-compatible API

            return ChatDeepSeek(
                model=self.normalize_model_name(self.model),
                temperature=self.temperature,
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                **self.kwargs,
            )
        except ImportError:
            raise ImportError(
                "langchain_openai not installed. Run: pip install langchain-openai"
            )

    def get_model_list(self) -> Dict[str, str]:
        return {
            "deepseek-chat": "deepseek-chat",
            "deepseek-coder": "deepseek-coder",
            "deepseek-v2.5": "deepseek-v2.5",
        }

    def normalize_model_name(self, model: str) -> str:
        """Normalize model name for DeepSeek"""
        aliases = {"deepseek": "deepseek-chat", "deepseek-latest": "deepseek-v2.5"}
        return aliases.get(model.lower(), model)

    def get_pricing_info(self) -> Dict[str, Dict[str, float]]:
        return {
            "deepseek-chat": {"input": 0.00014, "output": 0.00028},
            "deepseek-coder": {"input": 0.00014, "output": 0.00028},
            "deepseek-v2.5": {"input": 0.00014, "output": 0.00028},
        }


class LLMFactory:
    """Factory class to create LLM instances from different providers"""

    _providers = {
        "openai": OpenAIProvider,
        "google": GoogleProvider,
        "anthropic": AnthropicProvider,
        "deepseek": DeepSeekProvider,
    }

    @classmethod
    def create_llm(
        cls,
        model: str,
        provider: Optional[str] = None,
        temperature: float = 0.1,
        **kwargs,
    ):
        """
        Create an LLM instance from any provider

        Args:
            model: Model name (can include provider prefix like 'openai/gpt-4o')
            provider: Explicit provider name, if not in model string
            temperature: Model temperature
            **kwargs: Additional provider-specific arguments

        Returns:
            LLM instance ready for use with LangChain
        """

        # Parse provider from model string if present
        if "/" in model:
            provider_from_model, model = model.split("/", 1)
            if not provider:
                provider = provider_from_model

        # Auto-detect provider if not specified
        if not provider:
            provider = cls._detect_provider_from_model(model)

        provider = provider.lower()

        if provider not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(f"Unknown provider '{provider}'. Available: {available}")

        logger.info(f"Creating LLM: {provider}/{model}")

        # Create provider instance
        provider_class = cls._providers[provider]
        provider_instance = provider_class(
            model=model, temperature=temperature, **kwargs
        )

        # Return the actual LLM instance
        return provider_instance.create_llm()

    @classmethod
    def _detect_provider_from_model(cls, model: str) -> str:
        """Auto-detect provider based on model name patterns"""
        model_lower = model.lower()

        if any(x in model_lower for x in ["gpt", "chatgpt", "o1"]):
            return "openai"
        elif any(x in model_lower for x in ["gemini", "bard"]):
            return "google"
        elif any(x in model_lower for x in ["claude"]):
            return "anthropic"
        elif any(x in model_lower for x in ["deepseek"]):
            return "deepseek"
        else:
            # Default to OpenAI for unknown models
            logger.warning(
                f"Could not detect provider for model '{model}', defaulting to OpenAI"
            )
            return "openai"

    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of available providers"""
        return list(cls._providers.keys())

    @classmethod
    def get_provider_models(cls, provider: str) -> Dict[str, str]:
        """Get available models for a specific provider"""
        if provider not in cls._providers:
            raise ValueError(f"Unknown provider '{provider}'")

        provider_instance = cls._providers[provider]("dummy", 0.1)
        return provider_instance.get_model_list()

    @classmethod
    def get_all_models(cls) -> Dict[str, Dict[str, str]]:
        """Get all available models across all providers"""
        all_models = {}
        for provider_name in cls._providers:
            try:
                all_models[provider_name] = cls.get_provider_models(provider_name)
            except Exception as e:
                logger.warning(f"Could not get models for {provider_name}: {e}")
                all_models[provider_name] = {}
        return all_models


# Convenience function for easy usage
def create_llm(
    model: str, provider: Optional[str] = None, temperature: float = 0.1, **kwargs
):
    """
    Convenience function to create LLM instances

    Examples:
        # Auto-detect provider
        llm = create_llm('gpt-4o', temperature=0.1)
        llm = create_llm('gemini-pro', temperature=0.2)
        llm = create_llm('claude-3-sonnet', temperature=0.0)

        # Explicit provider
        llm = create_llm('gpt-4o-mini', provider='openai')
        llm = create_llm('deepseek-chat', provider='deepseek')

        # Provider prefix notation
        llm = create_llm('openai/gpt-4o')
        llm = create_llm('google/gemini-1.5-pro')
        llm = create_llm('anthropic/claude-3-opus')
        llm = create_llm('deepseek/deepseek-v2.5')
    """
    return LLMFactory.create_llm(model, provider, temperature, **kwargs)
