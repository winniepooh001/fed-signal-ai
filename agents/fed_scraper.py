# tools/comprehensive_fed_scraper.py
from langchain.tools import BaseTool
from typing import Type, Optional, Dict, Any, List
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import re
import hashlib
import logging

from schema.tool_schemas import FedWebScraperInput

logger = logging.getLogger(__name__)


class ComprehensiveFedScraper(BaseTool):
    """Production-ready comprehensive Fed scraper for FOMC minutes, statements, speeches, and press releases"""

    name: str = "comprehensive_fed_scraper"
    description: str = """
    Scrapes Federal Reserve for latest FOMC minutes, statements, speeches, and press releases.
    Only pulls new documents that haven't been scraped before.
    Returns scraped content and database IDs for tracking.
    """
    args_schema: Type[FedWebScraperInput] = FedWebScraperInput

    # Use class variables to avoid Pydantic issues
    _db_manager = None
    _embedding_manager = None
    _request_timeout = 15

    def __init__(self, db_manager=None, embedding_manager=None, request_timeout: int = 15):
        super().__init__()
        ComprehensiveFedScraper._db_manager = db_manager
        ComprehensiveFedScraper._embedding_manager = embedding_manager
        ComprehensiveFedScraper._request_timeout = request_timeout

    def _get_session(self):
        """Create session with proper headers"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        return session

    def _run(self, url: str = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
             target_content: str = "FOMC interest rates monetary policy") -> str:
        """Scrape latest Fed documents and return new content"""

        try:
            session = self._get_session()

            # Get last run time from database to determine cutoff date
            last_run_time = self._get_last_scraper_run_time()
            if last_run_time:
                cutoff_date = last_run_time
                logger.info(f"Using last run time as cutoff: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                # First run - look back 30 days
                cutoff_date = datetime.now() - timedelta(days=30)
                logger.info(f"First run - using 30-day lookback: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")

            # Define Fed document sources with correct patterns
            fed_sources = {
                'fomc_minutes': {
                    'url': 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
                    'doc_type': 'FOMC Minutes',
                    'pattern': r'/monetarypolicy/fomcminutes\d+\.htm'
                },
                'fomc_statements': {
                    'url': 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
                    'doc_type': 'FOMC Statement',
                    'pattern': r'/newsevents/pressreleases/monetary\d+[a-z]?\.htm'
                },
                'recent_press_releases': {
                    'url': 'https://www.federalreserve.gov/newsevents/pressreleases/2025-press.htm',
                    'doc_type': 'Press Release',
                    'pattern': r'/newsevents/pressreleases/\w+\d+[a-z]?\.htm'
                },
                'recent_speeches': {
                    'url': 'https://www.federalreserve.gov/newsevents/speech/2025-speeches.htm',
                    'doc_type': 'Speech',
                    'pattern': r'/newsevents/speech/\w+\d+[a-z]?\.htm'
                }
            }

            all_new_documents = []
            scraped_data_ids = []
            embeddings_created = 0

            for source_name, source_info in fed_sources.items():
                logger.info(f"Checking {source_name} for new documents since {cutoff_date.strftime('%Y-%m-%d')}")

                try:
                    new_docs = self._check_source_for_new_documents(
                        session, source_name, source_info, target_content, cutoff_date
                    )

                    for doc in new_docs:
                        # Save each document to database
                        if self._db_manager:
                            scraped_data_id = self._db_manager.save_scraped_data(
                                source=f"fed_{source_name}",
                                url=doc['url'],
                                target_content=target_content,
                                raw_content=doc['content'],
                                metadata={
                                    'title': doc['title'],
                                    'doc_type': source_info['doc_type'],
                                    'date_extracted': doc['date'].isoformat() if isinstance(doc['date'],
                                                                                            datetime) else str(
                                        doc['date']),
                                    'content_hash': doc['content_hash'],
                                    'scraped_at': datetime.now().isoformat()
                                }
                            )
                            scraped_data_ids.append(scraped_data_id)
                            doc['scraped_data_id'] = scraped_data_id

                            # Create and save embeddings if available
                            if self._embedding_manager and doc['content'].strip():
                                try:
                                    embeddings = self._embedding_manager.create_embeddings(doc['content'])
                                    if embeddings:
                                        self._db_manager.save_embeddings(scraped_data_id, embeddings)
                                        embeddings_created += len(embeddings)
                                except Exception as e:
                                    logger.warning(f"Could not create embeddings for {doc['title']}: {e}")

                    all_new_documents.extend(new_docs)
                    logger.info(f"Found {len(new_docs)} new documents in {source_name}")

                except Exception as e:
                    logger.error(f"Error checking {source_name}: {e}")
                    continue

            # Update the last run time in database
            self._update_last_scraper_run_time()

            # Sort by date (newest first)
            all_new_documents.sort(key=lambda x: x['date'], reverse=True)

            # Prepare summary
            summary = self._create_comprehensive_summary(all_new_documents, target_content)

            # Return structured result matching your existing Fed scraper format
            result = {
                'scraped_data_ids': scraped_data_ids,
                'url': url,
                'target_content': target_content,
                'relevant_content': [doc['content'][:1000] for doc in all_new_documents[:3]],  # First 3 previews
                'content_summary': summary,
                'total_documents_found': len(all_new_documents),
                'new_documents_found': len(all_new_documents),
                'sources_checked': list(fed_sources.keys()),
                'embeddings_created': embeddings_created,
                'cutoff_date_used': cutoff_date.isoformat(),
                'scraped_at': datetime.now().isoformat()
            }

            logger.info(
                f"Fed comprehensive scraper: found {len(all_new_documents)} new documents, created {embeddings_created} embeddings")
            return json.dumps(result, indent=2, default=str)

        except Exception as e:
            logger.error(f"Fed comprehensive scraper error: {str(e)}")
            error_result = {
                'error': str(e),
                'url': url,
                'scraped_at': datetime.now().isoformat()
            }
            return json.dumps(error_result)

    def _check_source_for_new_documents(self, session, source_name: str, source_info: Dict,
                                        target_content: str, cutoff_date: datetime) -> List[Dict]:
        """Check a specific Fed source for new documents"""
        new_documents = []

        try:
            # Get the source page
            response = session.get(source_info['url'], timeout=self._request_timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find document links using the pattern
            pattern = source_info['pattern']
            document_links = []

            # Find all links matching the pattern
            all_links = soup.find_all('a', href=True)

            for link in all_links:
                href = link.get('href', '')
                if re.search(pattern, href):
                    if href.startswith('/'):
                        href = 'https://www.federalreserve.gov' + href

                    title = link.get_text(strip=True)
                    if len(title) > 5:  # Filter out navigation links
                        document_links.append({
                            'url': href,
                            'title': title,
                            'link_element': link
                        })

            logger.debug(f"Found {len(document_links)} documents matching pattern in {source_name}")

            for doc_link in document_links[:20]:  # Check top 20 recent documents
                try:
                    # Extract date from URL or title
                    doc_date = self._extract_date_from_document(doc_link)

                    # Skip documents older than cutoff date
                    if doc_date and doc_date < cutoff_date:
                        continue

                    # Check if we've already scraped this document
                    if self._is_document_already_scraped(doc_link['url']):
                        continue  # Skip already scraped documents

                    # Get the full document content
                    doc_content = self._get_document_content(session, doc_link['url'])
                    if not doc_content or len(doc_content.strip()) < 200:
                        continue  # Skip documents with insufficient content

                    # Filter for relevance
                    if self._is_content_relevant(doc_content, target_content):
                        new_documents.append({
                            'url': doc_link['url'],
                            'title': doc_link['title'],
                            'content': doc_content,
                            'date': doc_date or datetime.now(),
                            'content_hash': hashlib.md5(doc_content.encode()).hexdigest(),
                            'doc_type': source_info['doc_type'],
                            'source': source_name
                        })

                        logger.info(f"Found new relevant document: {doc_link['title'][:50]}...")

                except Exception as e:
                    logger.debug(f"Error processing document {doc_link.get('url', 'unknown')}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error checking source {source_name}: {e}")

        return new_documents

    def _extract_date_from_document(self, doc_link: Dict) -> Optional[datetime]:
        """Extract date from document URL or title"""
        url = doc_link['url']
        title = doc_link['title']

        # Try to extract date from URL (e.g., fomcminutes20250507.htm)
        url_date_match = re.search(r'(\d{8})', url)
        if url_date_match:
            try:
                date_str = url_date_match.group(1)
                return datetime.strptime(date_str, '%Y%m%d')
            except ValueError:
                pass

        # Try shorter date format (e.g., monetary20250129a.htm)
        url_date_match = re.search(r'(\d{6})', url)
        if url_date_match:
            try:
                date_str = url_date_match.group(1)
                # Assume 20XX format
                if len(date_str) == 6:
                    year = 2000 + int(date_str[:2])
                    month = int(date_str[2:4])
                    day = int(date_str[4:6])
                    return datetime(year, month, day)
            except (ValueError, IndexError):
                pass

        # Try to extract date from title
        date_patterns = [
            r'(\w+\s+\d{1,2}(?:–|-)\d{1,2},?\s+\d{4})',  # "May 6-7, 2025"
            r'(\w+\s+\d{1,2},?\s+\d{4})',  # "May 7, 2025"
            r'(\d{1,2}/\d{1,2}/\d{4})',  # "5/7/2025"
        ]

        for pattern in date_patterns:
            match = re.search(pattern, title)
            if match:
                try:
                    date_str = match.group(1)
                    # Handle range dates by taking the end date
                    if '–' in date_str or '-' in date_str:
                        date_str = re.sub(r'.*[–-](\d{1,2})', r'\1', date_str)

                    # Try different date formats
                    for fmt in ['%B %d, %Y', '%B %d %Y', '%m/%d/%Y']:
                        try:
                            return datetime.strptime(date_str.strip(), fmt)
                        except ValueError:
                            continue
                except Exception:
                    continue

        # Default to recent if no date found
        return datetime.now()

    def _is_document_already_scraped(self, url: str) -> bool:
        """Check if document has already been scraped"""
        if not self._db_manager:
            return False

        try:
            with self._db_manager.get_session() as session:
                from database.models import ScrapedData

                existing = session.query(ScrapedData).filter(
                    ScrapedData.url == url
                ).first()

                return existing is not None
        except Exception:
            return False

    def _get_document_content(self, session, url: str) -> str:
        """Get full content from a Fed document"""
        try:
            response = session.get(url, timeout=self._request_timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Remove unwanted elements
            for elem in soup.find_all(['script', 'style', 'nav', 'header', 'footer']):
                elem.decompose()

            # Try to find main content area
            content_selectors = [
                'div[id="content"]',
                'main',
                'article',
                'div.content',
                'div#article'
            ]

            content_text = ""
            for selector in content_selectors:
                content_area = soup.select_one(selector)
                if content_area:
                    content_text = content_area.get_text(separator='\n', strip=True)
                    break

            # Fallback to body if no main content found
            if not content_text:
                body = soup.find('body')
                if body:
                    content_text = body.get_text(separator='\n', strip=True)

            # Clean up the content
            content_text = re.sub(r'\n\s*\n', '\n\n', content_text)
            content_text = re.sub(r'[ \t]+', ' ', content_text)

            # Remove common navigation text
            nav_patterns = [
                r'Skip to main content.*?Menu',
                r'Board of Governors.*?System',
                r'Back to Home.*?flexible',
                r'Main Menu.*?Search'
            ]

            for pattern in nav_patterns:
                content_text = re.sub(pattern, '', content_text, flags=re.IGNORECASE | re.DOTALL)

            return content_text.strip()[:15000]  # Limit content size

        except Exception as e:
            logger.warning(f"Could not get content from {url}: {e}")
            return ""

    def _is_content_relevant(self, content: str, target_content: str) -> bool:
        """Check if content is relevant to target keywords"""
        if not content or not target_content:
            return True

        content_lower = content.lower()
        target_keywords = target_content.lower().split()

        # Count keyword matches
        keyword_matches = sum(1 for keyword in target_keywords if keyword in content_lower)

        # Check for Fed-specific terms
        fed_terms = ['federal reserve', 'fomc', 'monetary policy', 'interest rate', 'economic outlook', 'inflation',
                     'employment']
        fed_matches = sum(1 for term in fed_terms if term in content_lower)

        # Content is relevant if has target keywords OR multiple Fed terms
        return keyword_matches >= 1 or fed_matches >= 2

    def _create_comprehensive_summary(self, documents: List[Dict], target_content: str) -> str:
        """Create summary of all new documents found"""
        if not documents:
            return "No new Federal Reserve documents found matching the criteria."

        summary_parts = []

        # Group by document type
        by_type = {}
        for doc in documents:
            doc_type = doc['doc_type']
            if doc_type not in by_type:
                by_type[doc_type] = []
            by_type[doc_type].append(doc)

        for doc_type, docs in by_type.items():
            summary_parts.append(f"{doc_type}s ({len(docs)} new):")
            for doc in docs[:3]:  # Top 3 per type
                title = doc['title'][:80] + "..." if len(doc['title']) > 80 else doc['title']
                date_str = doc['date'].strftime('%Y-%m-%d') if isinstance(doc['date'], datetime) else str(doc['date'])
                summary_parts.append(f"  • {title} ({date_str})")

        # Add content preview from most recent document
        if documents:
            latest_doc = documents[0]
            content_preview = latest_doc['content'][:300] + "..."
            summary_parts.append(f"\nLatest content preview:\n{content_preview}")

        return "\n".join(summary_parts)

    def _get_last_scraper_run_time(self) -> Optional[datetime]:
        """Get the last time this scraper was run from database"""
        if not self._db_manager:
            return None

        try:
            with self._db_manager.get_session() as session:
                from database.models import ScrapedData

                # Get the most recent scraped Fed document
                last_scraped = session.query(ScrapedData).filter(
                    ScrapedData.source.like('fed_%')
                ).order_by(ScrapedData.created_at.desc()).first()

                if last_scraped:
                    return last_scraped.created_at

        except Exception as e:
            logger.debug(f"Error getting last scraper run time: {e}")

        return None

    def _update_last_scraper_run_time(self):
        """Update the last scraper run time in database"""
        # This is automatically handled by saving scraped data with created_at timestamps
        # The _get_last_scraper_run_time method will pick up the latest timestamp
        pass