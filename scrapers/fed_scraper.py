# tools/comprehensive_fed_scraper.py
from langchain.tools import BaseTool
from typing import Type, Optional, Dict, Any, List
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import re
import hashlib
from utils.logging_config import get_logger
from scrapers.model_object import FedContent

from schema.tool_schemas import FedWebScraperInput

logger = get_logger(__name__)


class FedScraper:
    """Fed data scraper based on working ComprehensiveFedScraper implementation"""

    def __init__(self, request_timeout: int = 15):
        self.request_timeout = request_timeout
        self.session = self._get_session()

        # Define Fed document sources with correct patterns
        self.fed_sources = {
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
            },
            'economic_research': {
                'url': 'https://www.federalreserve.gov/econres.htm',
                'doc_type': 'Research Paper',
                'pattern': r'/econres/\w+/\w+\.htm',
                'special_handler': 'research'  # Flag for special processing
            },
            'working_papers': {
                'url': 'https://www.federalreserve.gov/econres/feds/index.htm',
                'doc_type': 'Working Paper',
                'pattern': r'/econres/feds/\d+/\d+\.htm',
                'special_handler': 'working_papers'
            },
            'discussion_papers': {
                'url': 'https://www.federalreserve.gov/econres/ifdp/index.htm',
                'doc_type': 'Discussion Paper',
                'pattern': r'/econres/ifdp/\d+/\d+\.htm',
                'special_handler': 'discussion_papers'
            }
        }

    def _get_session(self):
        """Create session with proper headers"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        return session

    def scrape_new_content(self, since_date: datetime) -> List[FedContent]:
        """Scrape new Fed content since the given date using proven working method"""
        all_content = []

        for source_name, source_info in self.fed_sources.items():
            logger.info(f"Checking {source_name} for new documents since {since_date.strftime('%Y-%m-%d')}")

            try:
                new_docs = self._check_source_for_new_documents(
                    source_name, source_info, since_date
                )

                # Convert to FedContent objects
                for doc in new_docs:
                    content_item = FedContent(
                        url=doc['url'],
                        title=doc['title'],
                        content=doc['content'],
                        published_date=doc['date'],
                        content_hash=doc['content_hash'],
                        file_type=source_name
                    )
                    all_content.append(content_item)

                logger.info(f"Found {len(new_docs)} new documents in {source_name}")

            except Exception as e:
                logger.error(f"Error checking {source_name}: {e}")
                continue

        # Sort by date (newest first)
        all_content.sort(key=lambda x: x.published_date, reverse=True)

        return all_content

    def _check_source_for_new_documents(self, source_name: str, source_info: dict, cutoff_date: datetime) -> List[dict]:
        """Check a specific Fed source for new documents"""
        new_documents = []

        # Check if this source needs special handling
        if source_info.get('special_handler') == 'research':
            return self._scrape_research_papers(source_info, cutoff_date)
        elif source_info.get('special_handler') == 'working_papers':
            return self._scrape_working_papers(source_info, cutoff_date)
        elif source_info.get('special_handler') == 'discussion_papers':
            return self._scrape_discussion_papers(source_info, cutoff_date)

        try:
            # Get the source page
            response = self.session.get(source_info['url'], timeout=self.request_timeout)
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

                    # Get the full document content
                    doc_content = self._get_document_content(doc_link['url'])
                    if not doc_content or len(doc_content.strip()) < 200:
                        continue  # Skip documents with insufficient content

                    # Filter for relevance (Fed-specific content)
                    if self._is_content_relevant(doc_content):
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

    def _extract_date_from_document(self, doc_link: dict) -> Optional[datetime]:
        """Extract date from document URL or title using proven method"""
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

    def _get_document_content(self, url: str) -> str:
        """Get full content from a Fed document using proven method"""
        try:
            response = self.session.get(url, timeout=self.request_timeout)
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

    def _is_content_relevant(self, content: str) -> bool:
        """Check if content is relevant Fed content"""
        if not content:
            return False

        content_lower = content.lower()

        # Check for Fed-specific terms
        fed_terms = [
            'federal reserve', 'fomc', 'monetary policy', 'interest rate',
            'economic outlook', 'inflation', 'employment', 'federal funds',
            'committee', 'board of governors', 'financial stability'
        ]

        fed_matches = sum(1 for term in fed_terms if term in content_lower)

        # Content is relevant if it has multiple Fed terms
        return fed_matches >= 2

    def _scrape_research_papers(self, source_info: dict, cutoff_date: datetime) -> List[dict]:
        """Scrape recent research papers from Fed economic research page with strict date filtering"""
        new_documents = []

        try:
            response = self.session.get(source_info['url'], timeout=self.request_timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for research paper sections - Fed research page has different layouts
            research_sections = [
                'div.panel',  # Panel sections
                'div.col-md-4',  # Column sections
                'div.highlight-box',  # Highlight boxes
                'ul.list-unstyled li',  # List items
            ]

            for section_selector in research_sections:
                sections = soup.select(section_selector)

                for section in sections[:3]:  # Only check top 3 sections
                    try:
                        # Find links within this section
                        links = section.find_all('a', href=True)

                        for link in links:
                            href = link.get('href', '')

                            # Look for research paper patterns
                            if any(pattern in href for pattern in ['/econres/', '/feds/', '/ifdp/', '/notes/']):
                                if href.startswith('/'):
                                    href = 'https://www.federalreserve.gov' + href

                                title = link.get_text(strip=True)
                                if len(title) > 10:  # Filter out short navigation text

                                    # STRICT DATE CHECK: Only process if we can find a valid recent date
                                    date_context = section.get_text()
                                    doc_date = self._extract_recent_date(date_context, href, cutoff_date)

                                    if not doc_date:
                                        logger.debug(f"No recent date found for {title[:30]}, skipping")
                                        continue

                                    # Get document content
                                    doc_content = self._get_document_content(href)
                                    if doc_content and len(doc_content.strip()) > 300:

                                        # Research papers often have economic/financial relevance
                                        if self._is_research_relevant(doc_content, title):
                                            new_documents.append({
                                                'url': href,
                                                'title': title,
                                                'content': doc_content,
                                                'date': doc_date,
                                                'content_hash': hashlib.md5(doc_content.encode()).hexdigest(),
                                                'doc_type': source_info['doc_type'],
                                                'source': 'economic_research'
                                            })

                                            logger.info(
                                                f"Found recent research paper: {title[:50]} ({doc_date.strftime('%Y-%m-%d')})")

                    except Exception as e:
                        logger.debug(f"Error processing research section: {e}")
                        continue

        except Exception as e:
            logger.error(f"Error scraping research papers: {e}")

        return new_documents

    def _extract_recent_date(self, text: str, url: str, cutoff_date: datetime) -> Optional[datetime]:
        """Extract date only if it's recent enough (after cutoff)"""

        # First try URL patterns
        url_date_patterns = [
            r'/(\d{4})/(\d{2})/(\d{2})/',  # /2025/06/17/
            r'/(\d{4})-(\d{2})-(\d{2})/',  # /2025-06-17/
            r'(\d{8})',  # 20250617
            r'(\d{6})',  # 202506
        ]

        for pattern in url_date_patterns:
            match = re.search(pattern, url)
            if match:
                try:
                    if len(match.groups()) == 3:
                        year, month, day = match.groups()
                        doc_date = datetime(int(year), int(month), int(day))
                    elif len(match.groups()) == 1:
                        date_str = match.group(1)
                        if len(date_str) == 8:  # YYYYMMDD
                            doc_date = datetime.strptime(date_str, '%Y%m%d')
                        elif len(date_str) == 6:  # YYYYMM
                            doc_date = datetime.strptime(date_str, '%Y%m')
                        else:
                            continue

                    # Only return if recent enough
                    if doc_date >= cutoff_date:
                        return doc_date
                except (ValueError, IndexError):
                    continue

        # Look for recent dates in text (must be after cutoff)
        text_lower = text.lower()
        current_year = datetime.now().year

        # Look for current year and month patterns
        month_patterns = [
            rf'(january|february|march|april|may|june|july|august|september|october|november|december)\s+{current_year}',
            rf'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+{current_year}',
            rf'{current_year}[-/](\d{{1,2}})[-/](\d{{1,2}})',
            rf'(\d{{1,2}})[-/](\d{{1,2}})[-/]{current_year}',
        ]

        for pattern in month_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                try:
                    if isinstance(match, str):  # Month name
                        month_names = {
                            'january': 1, 'february': 2, 'march': 3, 'april': 4,
                            'may': 5, 'june': 6, 'july': 7, 'august': 8,
                            'september': 9, 'october': 10, 'november': 11, 'december': 12,
                            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
                            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                        }
                        month_num = month_names.get(match)
                        if month_num:
                            doc_date = datetime(current_year, month_num, 1)
                            if doc_date >= cutoff_date:
                                return doc_date
                    elif len(match) == 2:  # Month/day numbers
                        month, day = match
                        doc_date = datetime(current_year, int(month), int(day))
                        if doc_date >= cutoff_date:
                            return doc_date
                except (ValueError, KeyError):
                    continue

        # No recent date found
        return None

    def _scrape_working_papers(self, source_info: dict, cutoff_date: datetime) -> List[dict]:
        """Scrape FEDS working papers"""
        new_documents = []

        try:
            response = self.session.get(source_info['url'], timeout=self.request_timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # FEDS papers are typically listed in tables or lists
            paper_rows = soup.find_all(['tr', 'li'])

            for row in paper_rows[:15]:  # Check recent papers
                try:
                    # Find paper link
                    link = row.find('a', href=True)
                    if not link:
                        continue

                    href = link.get('href', '')
                    if '/econres/feds/' not in href:
                        continue

                    if href.startswith('/'):
                        href = 'https://www.federalreserve.gov' + href

                    title = link.get_text(strip=True)
                    if len(title) < 10:
                        continue

                    # Extract date from row text or URL
                    row_text = row.get_text()
                    doc_date = self._extract_date_from_context(row_text, href)

                    if doc_date and doc_date < cutoff_date:
                        continue

                    # Get paper content
                    doc_content = self._get_document_content(href)
                    if doc_content and len(doc_content.strip()) > 500:

                        if self._is_research_relevant(doc_content, title):
                            new_documents.append({
                                'url': href,
                                'title': title,
                                'content': doc_content,
                                'date': doc_date or datetime.now(),
                                'content_hash': hashlib.md5(doc_content.encode()).hexdigest(),
                                'doc_type': source_info['doc_type'],
                                'source': 'working_papers'
                            })

                            logger.info(f"Found working paper: {title[:50]}...")

                except Exception as e:
                    logger.debug(f"Error processing working paper: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping working papers: {e}")

        return new_documents

    def _scrape_discussion_papers(self, source_info: dict, cutoff_date: datetime) -> List[dict]:
        """Scrape IFDP discussion papers"""
        new_documents = []

        try:
            response = self.session.get(source_info['url'], timeout=self.request_timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # IFDP papers are typically in tables
            paper_rows = soup.find_all(['tr', 'li'])

            for row in paper_rows[:15]:  # Check recent papers
                try:
                    link = row.find('a', href=True)
                    if not link:
                        continue

                    href = link.get('href', '')
                    if '/econres/ifdp/' not in href:
                        continue

                    if href.startswith('/'):
                        href = 'https://www.federalreserve.gov' + href

                    title = link.get_text(strip=True)
                    if len(title) < 10:
                        continue

                    # Extract date from row
                    row_text = row.get_text()
                    doc_date = self._extract_date_from_context(row_text, href)

                    if doc_date and doc_date < cutoff_date:
                        continue

                    # Get paper content
                    doc_content = self._get_document_content(href)
                    if doc_content and len(doc_content.strip()) > 500:

                        if self._is_research_relevant(doc_content, title):
                            new_documents.append({
                                'url': href,
                                'title': title,
                                'content': doc_content,
                                'date': doc_date or datetime.now(),
                                'content_hash': hashlib.md5(doc_content.encode()).hexdigest(),
                                'doc_type': source_info['doc_type'],
                                'source': 'discussion_papers'
                            })

                            logger.info(f"Found discussion paper: {title[:50]}...")

                except Exception as e:
                    logger.debug(f"Error processing discussion paper: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping discussion papers: {e}")

        return new_documents

    def _extract_date_from_context(self, text: str, url: str) -> Optional[datetime]:
        """Extract date from surrounding text or URL for research papers"""

        # First try the existing URL-based extraction
        doc_date = self._extract_date_from_document({'url': url, 'title': text})
        if doc_date and doc_date.year >= 2020:  # Reasonable date check
            return doc_date

        # Look for dates in the context text
        date_patterns = [
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # 2025-06-17
            r'(\d{1,2})/(\d{1,2})/(\d{4})',  # 6/17/2025
            r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',  # June 17, 2025
            r'(\d{4})-(\d{2})',  # 2025-06 (year-month)
            r'(\d{4})',  # Just year
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    if len(match) == 3:
                        if pattern.startswith(r'(\d{4})'):  # Year first
                            year, month, day = match
                            return datetime(int(year), int(month), int(day))
                        elif pattern.startswith(r'(\d{1,2})'):  # Month first
                            month, day, year = match
                            return datetime(int(year), int(month), int(day))
                        else:  # Month name
                            month_name, day, year = match
                            month_names = {
                                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                                'september': 9, 'october': 10, 'november': 11, 'december': 12
                            }
                            month_num = month_names.get(month_name.lower())
                            if month_num:
                                return datetime(int(year), month_num, int(day))
                    elif len(match) == 2:  # Year-month
                        year, month = match
                        return datetime(int(year), int(month), 1)
                    elif len(match) == 1:  # Just year
                        year = match[0]
                        return datetime(int(year), 1, 1)
                except (ValueError, IndexError):
                    continue

        # Default to recent if no date found
        return datetime.now()

    def _is_research_relevant(self, content: str, title: str) -> bool:
        """Check if research content is relevant for financial analysis"""
        content_lower = content.lower()
        title_lower = title.lower()

        # Research-specific terms that indicate financial/economic relevance
        research_terms = [
            'monetary policy', 'financial markets', 'banking', 'credit', 'inflation',
            'economic growth', 'recession', 'financial stability', 'systemic risk',
            'asset prices', 'yield curve', 'interest rates', 'unemployment',
            'gdp', 'productivity', 'financial institutions', 'regulation',
            'stress test', 'capital requirements', 'liquidity', 'market volatility',
            'financial crisis', 'macroeconomic', 'fiscal policy'
        ]

        # Count matches in both title and content
        title_matches = sum(1 for term in research_terms if term in title_lower)
        content_matches = sum(1 for term in research_terms if term in content_lower)

        # Research is relevant if it has strong keyword presence
        return title_matches >= 1 or content_matches >= 3