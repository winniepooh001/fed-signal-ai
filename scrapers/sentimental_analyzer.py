from datetime import datetime
from typing import Any, Dict

from utils.logging_config import get_logger

logger = get_logger(__name__)


class FinancialSentimentAnalyzer:
    """Unified interface for multiple financial sentiment analysis models"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.provider = self.config.get(
            "provider", "vader_finance"
        )  # Default to lightweight VADER
        self.model = None
        self.tokenizer = None
        self.pipeline = None

        # Initialize the selected provider
        self._initialize_provider()

    def _initialize_provider(self):
        """Initialize the selected sentiment analysis provider"""
        try:
            if self.provider == "finbert":
                self._initialize_finbert()
            elif self.provider == "finbert_tone":
                self._initialize_finbert_tone()
            elif self.provider == "vader_finance":
                self._initialize_vader_finance()
            elif self.provider == "textblob":
                self._initialize_textblob()
            else:
                # Fallback to lightweight option
                self.provider = "vader_finance"
                self._initialize_vader_finance()

            logger.info(f"Initialized financial sentiment analyzer: {self.provider}")

        except Exception as e:
            logger.error(
                f"Failed to initialize sentiment provider {self.provider}: {e}"
            )
            # Final fallback to textblob
            self.provider = "textblob"
            self._initialize_textblob()

    def _initialize_finbert(self):
        """Initialize FinBERT model (ProsusAI/finbert)"""
        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
                pipeline,
            )

            model_name = "ProsusAI/finbert"

            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)

            # Create pipeline for easier inference
            self.pipeline = pipeline(
                "sentiment-analysis",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if torch.cuda.is_available() else -1,
            )
        except ImportError:
            logger.warning(
                "FinBERT requires transformers and torch. Falling back to VADER."
            )
            raise

    def _initialize_finbert_tone(self):
        """Initialize FinBERT-Tone model (yiyanghkust/finbert-tone)"""
        try:
            import torch
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
                pipeline,
            )

            model_name = "yiyanghkust/finbert-tone"

            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)

            self.pipeline = pipeline(
                "sentiment-analysis",
                model=self.model,
                tokenizer=self.tokenizer,
                device=0 if torch.cuda.is_available() else -1,
            )
        except ImportError:
            logger.warning(
                "FinBERT-Tone requires transformers and torch. Falling back to VADER."
            )
            raise

    def _initialize_vader_finance(self):
        """Initialize VADER sentiment (enhanced for finance)"""
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            self.vader_analyzer = SentimentIntensityAnalyzer()

            # Load financial lexicon enhancements
            financial_lexicon = {
                "bullish": 2.0,
                "bearish": -2.0,
                "rally": 1.5,
                "crash": -2.5,
                "moon": 2.0,
                "dump": -2.0,
                "pump": 1.5,
                "hodl": 1.0,
                "diamond hands": 2.0,
                "paper hands": -1.5,
                "to the moon": 2.5,
                "buy the dip": 1.5,
                "sell off": -1.5,
                "breakout": 1.5,
                "support": 1.0,
                "resistance": -0.5,
                "oversold": 1.0,
                "overbought": -1.0,
                "bounce": 1.0,
                "rejection": -1.5,
                "hawkish": -1.5,
                "dovish": 1.5,
                "tightening": -1.0,
                "accommodative": 1.0,
                "easing": 1.5,
                "aggressive": -1.0,
            }

            # Update VADER lexicon with financial terms
            self.vader_analyzer.lexicon.update(financial_lexicon)

        except ImportError:
            logger.warning(
                "VADER sentiment package not available. Falling back to TextBlob."
            )
            raise

    def _initialize_textblob(self):
        """Initialize TextBlob as final fallback"""
        try:
            from textblob import TextBlob

            self.textblob = TextBlob
        except ImportError:
            logger.error("TextBlob not available. Cannot perform sentiment analysis.")
            raise

    def analyze_sentiment(self, text: str, title: str = None) -> Dict[str, Any]:
        """Analyze sentiment of financial text"""
        try:
            if self.provider in ["finbert", "finbert_tone"]:
                return self._analyze_with_transformer(text, title)
            elif self.provider == "vader_finance":
                return self._analyze_with_vader(text, title)
            elif self.provider == "textblob":
                return self._analyze_with_textblob(text, title)
            else:
                raise ValueError(f"Unknown provider: {self.provider}")

        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return {
                "sentiment": "NEUTRAL",
                "confidence": 0.0,
                "scores": {"positive": 0.33, "negative": 0.33, "neutral": 0.34},
                "error": str(e),
                "provider": self.provider,
            }

    def _analyze_with_transformer(self, text: str, title: str = None) -> Dict[str, Any]:
        """Analyze sentiment using transformer models (FinBERT, etc.)"""
        try:
            import torch

            # Combine title and text
            full_text = f"{title}. {text}" if title else text

            # Truncate to model's max length
            max_length = 512
            if len(full_text) > max_length:
                full_text = full_text[:max_length]

            # Get prediction
            result = self.pipeline(full_text)[0]

            # Standardize output format
            label = result["label"].upper()
            confidence = result["score"]

            # Map different model outputs to standard format
            if label in ["POSITIVE", "BULLISH"]:
                sentiment = "POSITIVE"
            elif label in ["NEGATIVE", "BEARISH"]:
                sentiment = "NEGATIVE"
            else:
                sentiment = "NEUTRAL"

            # Get detailed scores if possible
            try:
                with torch.no_grad():
                    inputs = self.tokenizer(
                        full_text, return_tensors="pt", truncation=True, max_length=512
                    )
                    outputs = self.model(**inputs)
                    probabilities = torch.nn.functional.softmax(outputs.logits, dim=-1)

                scores = {}
                for i, prob in enumerate(probabilities[0]):
                    label_name = self.pipeline.model.config.id2label[i].lower()
                    scores[label_name] = float(prob)
            except:
                # Simple confidence mapping
                scores = {sentiment.lower(): confidence}
                for s in ["positive", "negative", "neutral"]:
                    if s not in scores:
                        scores[s] = (1.0 - confidence) / 2

            return {
                "sentiment": sentiment,
                "confidence": confidence,
                "scores": scores,
                "provider": self.provider,
                "analyzed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Transformer sentiment analysis error: {e}")
            raise

    def _analyze_with_vader(self, text: str, title: str = None) -> Dict[str, Any]:
        """Analyze sentiment using enhanced VADER"""
        try:
            # Combine title and text
            full_text = f"{title}. {text}" if title else text

            # Get VADER scores
            scores = self.vader_analyzer.polarity_scores(full_text)

            # Determine overall sentiment
            compound = scores["compound"]
            if compound >= 0.05:
                sentiment = "POSITIVE"
                confidence = min(compound * 2, 1.0)  # Scale to 0-1
            elif compound <= -0.05:
                sentiment = "NEGATIVE"
                confidence = min(abs(compound) * 2, 1.0)
            else:
                sentiment = "NEUTRAL"
                confidence = 1.0 - abs(compound)

            return {
                "sentiment": sentiment,
                "confidence": confidence,
                "scores": {
                    "positive": scores["pos"],
                    "negative": scores["neg"],
                    "neutral": scores["neu"],
                    "compound": scores["compound"],
                },
                "provider": self.provider,
                "analyzed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"VADER sentiment analysis error: {e}")
            raise

    def _analyze_with_textblob(self, text: str, title: str = None) -> Dict[str, Any]:
        """Analyze sentiment using TextBlob as fallback"""
        try:
            full_text = f"{title}. {text}" if title else text
            blob = self.textblob(full_text)

            polarity = blob.sentiment.polarity

            if polarity > 0.1:
                sentiment = "POSITIVE"
                confidence = min(polarity * 2, 1.0)
            elif polarity < -0.1:
                sentiment = "NEGATIVE"
                confidence = min(abs(polarity) * 2, 1.0)
            else:
                sentiment = "NEUTRAL"
                confidence = 1.0 - abs(polarity)

            return {
                "sentiment": sentiment,
                "confidence": confidence,
                "scores": {
                    "polarity": polarity,
                    "subjectivity": blob.sentiment.subjectivity,
                },
                "provider": self.provider,
                "analyzed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"TextBlob sentiment analysis error: {e}")
            raise

    def is_relevant_for_trading(
        self, text: str, title: str = None, threshold: float = 0.6
    ) -> Dict[str, Any]:
        """Determine if content is relevant for trading based on sentiment confidence"""
        sentiment_result = self.analyze_sentiment(text, title)

        # Content is relevant if:
        # 1. High confidence sentiment (positive or negative)
        # 2. Contains financial keywords
        # 3. Strong emotional language

        confidence = sentiment_result.get("confidence", 0.0)
        sentiment = sentiment_result.get("sentiment", "NEUTRAL")

        # Check for financial keywords
        financial_keywords = [
            "fed",
            "federal reserve",
            "fomc",
            "interest rate",
            "inflation",
            "monetary policy",
            "economic growth",
            "recession",
            "gdp",
            "employment",
            "unemployment",
            "labor market",
            "wages",
            "financial stability",
            "banking",
            "credit",
            "liquidity",
            "asset prices",
            "yield curve",
            "bonds",
            "treasury",
            "market volatility",
            "financial conditions",
            "stress test",
        ]

        full_text = f"{title} {text}".lower() if title else text.lower()
        keyword_matches = sum(
            1 for keyword in financial_keywords if keyword in full_text
        )

        # Relevance scoring
        relevance_score = 0.0

        # Sentiment confidence contributes to relevance
        if sentiment != "NEUTRAL":
            relevance_score += confidence * 0.6

        # Financial keywords contribute
        keyword_score = min(keyword_matches / 5.0, 1.0)  # Normalize to 0-1
        relevance_score += keyword_score * 0.4

        is_relevant = relevance_score >= threshold

        return {
            "relevant": is_relevant,
            "model": self.provider,
            "relevance_score": relevance_score,
            "sentiment_analysis": sentiment_result,
            "keyword_matches": keyword_matches,
            "reasoning": f"Sentiment: {sentiment} ({confidence:.2f}), Keywords: {keyword_matches}",
        }
