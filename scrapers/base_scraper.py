# scrapers/base_scraper.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import hashlib
import json
from dataclasses import dataclass
from utils.logging_config import get_logger

logger = get_logger()


@dataclass
class ScrapedContent:
    """Standard format for scraped content"""
    id: str  # Unique identifier
    title: str
    content: str
    url: str
    published_date: datetime
    source: str
    metadata: Dict[str, Any]
    content_hash: str  # For change detection


class BaseScraper(ABC):
    """Base class for all scrapers with change detection"""

    def __init__(self, db_manager, name: str):
        self.db_manager = db_manager
        self.name = name
        self.last_check_time = None
        self._load_last_check_time()

    def _load_last_check_time(self):
        """Load the last check time from database"""
        try:
            with self.db_manager.get_session() as session:
                from database.models import ScraperState

                state = session.query(ScraperState).filter_by(scraper_name=self.name).first()
                if state:
                    self.last_check_time = state.last_check_time
                    logger.debug(f"{self.name}: Last check time loaded: {self.last_check_time}")
                else:
                    logger.debug(f"{self.name}: No previous check time found")
        except Exception as e:
            logger.warning(f"{self.name}: Could not load last check time: {e}")

    def _save_check_time(self, check_time: datetime):
        """Save the current check time to database"""
        try:
            with self.db_manager.get_session() as session:
                from database.models import ScraperState

                state = session.query(ScraperState).filter_by(scraper_name=self.name).first()
                if state:
                    state.last_check_time = check_time
                    state.last_run_metadata = json.dumps({
                        'successful': True,
                        'timestamp': check_time.isoformat()
                    })
                else:
                    state = ScraperState(
                        scraper_name=self.name,
                        last_check_time=check_time,
                        last_run_metadata=json.dumps({
                            'successful': True,
                            'timestamp': check_time.isoformat()
                        })
                    )
                    session.add(state)

                self.last_check_time = check_time
                logger.debug(f"{self.name}: Check time saved: {check_time}")
        except Exception as e:
            logger.error(f"{self.name}: Could not save check time: {e}")

    def _content_hash(self, content: str) -> str:
        """Generate hash for content change detection"""
        return hashlib.md5(content.encode()).hexdigest()

    def _is_content_new(self, content_id: str, content_hash: str) -> bool:
        """Check if content is new based on hash"""
        try:
            with self.db_manager.get_session() as session:
                from database.models import ScrapedData

                existing = session.query(ScrapedData).filter_by(
                    source=self.name,
                    external_id=content_id
                ).first()

                if not existing:
                    return True  # Completely new content

                # Check if content has changed
                existing_metadata = json.loads(existing.extra_metadata or '{}')
                existing_hash = existing_metadata.get('content_hash', '')

                return content_hash != existing_hash

        except Exception as e:
            logger.warning(f"{self.name}: Could not check content freshness: {e}")
            return True  # Assume new if we can't check

    def _save_content(self, content: ScrapedContent) -> str:
        """Save scraped content to database"""
        try:
            metadata = {
                'content_hash': content.content_hash,
                'published_date': content.published_date.isoformat(),
                'scraped_at': datetime.now().isoformat(),
                **content.metadata
            }

            return self.db_manager.save_scraped_data(
                source=self.name,
                url=content.url,
                target_content=content.title,
                raw_content=content.content,
                metadata=metadata,
                external_id=content.id
            )
        except Exception as e:
            logger.error(f"{self.name}: Failed to save content: {e}")
            return None

    @abstractmethod
    def scrape_new_content(self) -> List[ScrapedContent]:
        """Scrape and return only new content since last check"""
        pass

    def run_scraping(self, force_update: bool = False) -> Dict[str, Any]:
        """Run the scraping process and return results"""
        start_time = datetime.now()

        logger.info(f"{self.name}: Starting scraping run")
        logger.info(f"{self.name}: Last check: {self.last_check_time or 'Never'}")
        logger.info(f"{self.name}: Force update: {force_update}")

        try:
            # Get new content
            new_content = self.scrape_new_content()

            if not new_content and not force_update:
                logger.info(f"{self.name}: No new content found")
                return {
                    'success': True,
                    'scraper_name': self.name,
                    'new_content_count': 0,
                    'content_ids': [],
                    'message': 'No new content since last check',
                    'last_check': self.last_check_time.isoformat() if self.last_check_time else None,
                    'execution_time_ms': (datetime.now() - start_time).total_seconds() * 1000
                }

            # Filter for truly new content
            saved_content_ids = []

            for content in new_content:
                if force_update or self._is_content_new(content.id, content.content_hash):
                    content_id = self._save_content(content)
                    if content_id:
                        saved_content_ids.append(content_id)
                        logger.info(f"{self.name}: Saved new content: {content.title[:50]}...")
                else:
                    logger.debug(f"{self.name}: Content unchanged: {content.title[:50]}...")

            # Update check time
            self._save_check_time(start_time)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            result = {
                'success': True,
                'scraper_name': self.name,
                'new_content_count': len(saved_content_ids),
                'total_content_found': len(new_content),
                'content_ids': saved_content_ids,
                'message': f'Found {len(new_content)} items, saved {len(saved_content_ids)} new',
                'last_check': start_time.isoformat(),
                'execution_time_ms': execution_time
            }

            logger.info(f"{self.name}: Scraping completed successfully")
            logger.info(f"{self.name}: {result['message']}")

            return result

        except Exception as e:
            logger.error(f"{self.name}: Scraping failed: {str(e)}", exc_info=True)

            return {
                'success': False,
                'scraper_name': self.name,
                'error': str(e),
                'last_check': self.last_check_time.isoformat() if self.last_check_time else None,
                'execution_time_ms': (datetime.now() - start_time).total_seconds() * 1000
            }