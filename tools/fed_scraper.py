from langchain.tools import BaseTool
from typing import Type, Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import logging

from schema.tool_schemas import FedWebScraperInput

logger = logging.getLogger(__name__)


class FedWebScraperTool(BaseTool):
    """Enhanced Fed scraper with database persistence and embeddings"""

    name: str = "fed_web_scraper"
    description: str = """
    Scrapes Federal Reserve website and saves data with embeddings to database.
    Returns scraped content and database ID for future reference.
    """
    args_schema: Type[FedWebScraperInput] = FedWebScraperInput

    # Use class variables instead of instance variables to avoid Pydantic issues
    _db_manager = None
    _embedding_manager = None
    _request_timeout = 10

    def __init__(self, db_manager=None, embedding_manager=None, request_timeout: int = 10):
        super().__init__()
        # Store in class variables to avoid Pydantic validation
        FedWebScraperTool._db_manager = db_manager
        FedWebScraperTool._embedding_manager = embedding_manager
        FedWebScraperTool._request_timeout = request_timeout

    def _get_session(self):
        """Create session on-demand to avoid Pydantic issues"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        return session

    def _run(self, url: str, target_content: str = "interest rates economic outlook") -> str:
        """Scrape Fed website and save to database with embeddings"""
        try:
            # Create session on-demand
            session = self._get_session()

            # Scrape content
            response = session.get(url, timeout=self._request_timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            content_blocks = self._extract_content_blocks(soup)
            relevant_content = self._filter_relevant_content(content_blocks, target_content)

            # Prepare full content for storage
            full_content = "\n\n".join(relevant_content)

            # Save to database if available
            scraped_data_id = None
            embeddings_count = 0

            if self._db_manager:
                scraped_data_id = self._db_manager.save_scraped_data(
                    source="fed_website",
                    url=url,
                    target_content=target_content,
                    raw_content=full_content,
                    metadata={
                        'total_blocks_found': len(content_blocks),
                        'relevant_blocks_found': len(relevant_content),
                        'scraped_at': datetime.now().isoformat()
                    }
                )

                # Create and save embeddings if available
                if self._embedding_manager and full_content.strip():
                    embeddings = self._embedding_manager.create_embeddings(full_content)
                    if embeddings:
                        self._db_manager.save_embeddings(scraped_data_id, embeddings)
                        embeddings_count = len(embeddings)

            # Return structured result
            result = {
                'scraped_data_id': scraped_data_id,
                'url': url,
                'target_content': target_content,
                'relevant_content': relevant_content[:3],  # First 3 for immediate analysis
                'content_summary': self._create_summary(relevant_content),
                'total_blocks_found': len(content_blocks),
                'relevant_blocks_found': len(relevant_content),
                'embeddings_created': embeddings_count,
                'scraped_at': datetime.now().isoformat()
            }

            logger.info(f"Fed scraper: saved data with ID {scraped_data_id}, created {embeddings_count} embeddings")
            return json.dumps(result, indent=2)

        except Exception as e:
            error_result = {
                'error': str(e),
                'url': url,
                'scraped_at': datetime.now().isoformat()
            }
            logger.error(f"Fed scraper error: {str(e)}")
            return json.dumps(error_result)

    def _extract_content_blocks(self, soup: BeautifulSoup) -> list:
        """Extract content blocks from Fed website"""
        content_blocks = []

        # Enhanced selectors for Fed website
        selectors = [
            {'class_': lambda x: x and any(
                term in x.lower() for term in ['release', 'statement', 'content', 'article'])},
            {'id': lambda x: x and any(term in x.lower() for term in ['content', 'article', 'main'])},
            {'tag': 'article'},
            {'tag': 'main'}
        ]

        for selector in selectors:
            if 'tag' in selector:
                elements = soup.find_all(selector['tag'])
            else:
                elements = soup.find_all(['div', 'p', 'article', 'main'],
                                         **{k: v for k, v in selector.items() if k != 'tag'})

            for element in elements:
                text = element.get_text().strip()
                if text and len(text) > 100:
                    content_blocks.append(text)

        # Fallback: get all meaningful paragraphs
        if not content_blocks:
            for p in soup.find_all('p'):
                text = p.get_text().strip()
                if text and len(text) > 50:
                    content_blocks.append(text)

        return list(set(content_blocks))[:20]  # Remove duplicates and limit

    def _filter_relevant_content(self, content_blocks: list, target_content: str) -> list:
        """Filter content blocks for target keywords"""
        target_keywords = target_content.lower().split()
        relevant_content = []

        for block in content_blocks:
            block_lower = block.lower()
            keyword_matches = sum(1 for keyword in target_keywords if keyword in block_lower)

            # Include blocks with multiple keyword matches or specific financial terms
            financial_terms = ['federal reserve', 'fomc', 'monetary policy', 'interest rate', 'economic']
            has_financial_terms = any(term in block_lower for term in financial_terms)

            if keyword_matches >= 2 or (keyword_matches >= 1 and has_financial_terms):
                relevant_content.append(block)

        return relevant_content

    def _create_summary(self, relevant_content: list) -> str:
        """Create a brief summary of the relevant content"""
        if not relevant_content:
            return "No relevant content found"

        summary_parts = []
        for content in relevant_content[:3]:
            summary_parts.append(content[:150] + "..." if len(content) > 150 else content)

        return " | ".join(summary_parts)