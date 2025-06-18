# Add this to your Fed scraper file

from typing import Any, Dict, List

from scrapers.model_object import FedContent
from utils.logging_config import get_logger

logger = get_logger(__name__)


class DocumentSummarizer:
    """Summarize Fed documents using existing LLM library"""

    def __init__(self, llm_config: Dict[str, Any] = None):
        self.llm_config = llm_config or {
            "model": "gpt-4.1-mini",
            "temperature": 0,
            "max_tokens": 8000,
            "provider": "openai",
        }
        self.llm = self._initialize_llm()

    def _initialize_llm(self):
        """Initialize LLM using your existing library"""
        try:
            # Import your existing LLM provider
            from utils.llm_provider import create_llm

            llm = create_llm(
                model=self.llm_config["model"],
                temperature=self.llm_config["temperature"],
                max_tokens=self.llm_config["max_tokens"],
                provider=self.llm_config["provider"],
            )

            logger.info(
                f"Initialized document summarizer with {self.llm_config['model']}"
            )
            return llm

        except ImportError as e:
            logger.error(f"Could not import LLM provider: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            return None

    def summarize_document(
        self, title: str, content: str, doc_type: str = "Fed Document"
    ) -> str:
        """Summarize a single document into one sentence"""

        if not self.llm:
            return f"Summary unavailable - {title[:100]}..."

        try:
            # Create focused prompt for Fed content
            prompt = f"""Analyze this {doc_type} in exactly 3  clear, concise sentences.
             First sentence captures the key financial/economic insight. 
             Second sentence rationalize about policy implication.
             Third sentence hypothesize on potential market impact. 

Title: {title}

Content: {content[:5000]}...

Three Sentence summary:"""

            # Call LLM
            response = self.llm.invoke(prompt)

            # Extract text from response (handle different response formats)
            if hasattr(response, "content"):
                summary = response.content.strip()
            elif isinstance(response, str):
                summary = response.strip()
            else:
                summary = str(response).strip()

            # Clean up the summary
            summary = self._clean_summary(summary)

            # Ensure it's actually one sentence
            sentences = summary.split(".")
            if len(sentences) > 1 and len(sentences[0]) > 20:
                summary = sentences[0] + "."

            return summary

        except Exception as e:
            logger.error(f"Failed to summarize document {title[:50]}: {e}")
            return f"Summary error - {title[:100]}..."

    def _clean_summary(self, summary: str) -> str:
        """Clean and validate the summary"""
        # Remove common prefixes
        prefixes_to_remove = [
            "this document",
            "the paper",
            "this research",
            "this study",
            "this report",
            "the fed",
            "the federal reserve",
        ]

        summary_lower = summary.lower()
        for prefix in prefixes_to_remove:
            if summary_lower.startswith(prefix):
                summary = summary[len(prefix) :].strip()
                # Capitalize first letter
                if summary:
                    summary = summary[0].upper() + summary[1:]
                break

        return summary

    def batch_summarize(self, content_items: List[FedContent]) -> Dict[str, str]:
        """Summarize multiple documents efficiently"""
        summaries = {}

        for content in content_items:
            try:
                summary = self.summarize_document(
                    content.title,
                    content.content,
                    getattr(content, "doc_type", "Fed Document"),
                )
                summaries[content.url] = summary

                logger.debug(f"Summarized: {content.title[:50]} -> {summary[:100]}...")

            except Exception as e:
                logger.error(f"Failed to summarize {content.url}: {e}")
                summaries[content.url] = (
                    f"Summary unavailable - {content.title[:100]}..."
                )

        return summaries


# Integration function - add this to your main scraper logic
def enhance_relevant_content_with_summaries(
    relevant_items: FedContent, llm_config: Dict[str, Any] = None
) -> FedContent:
    """Add summaries to relevant content items"""

    if not relevant_items:
        return relevant_items

    try:
        # Initialize summarizer
        summarizer = DocumentSummarizer(llm_config)

        # Generate summaries
        relevant_items.summary = summarizer.summarize_document(
            relevant_items.title, relevant_items.content, relevant_items.file_type
        )

        logger.info(
            f"Generated summaries for {relevant_items.title[:100]} relevant documents"
        )

    except Exception as e:
        logger.error(f"Failed to generate summaries: {e}")
        # Add fallback summaries

    return relevant_items
