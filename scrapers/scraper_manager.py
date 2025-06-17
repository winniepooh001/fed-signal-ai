# scrapers/scraper_manager.py
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from scrapers.base_scraper import BaseScraper
from agents.fed_scraper import FedScraper
from scrapers.reddit_scraper import RedditWSBScraper
from database import DatabaseManager
from utils.logging_config import get_logger

logger = get_logger()


class ScraperManager:
    """Manages multiple scrapers with coordinated execution and monitoring"""

    def __init__(self, database_url: str):
        self.db_manager = DatabaseManager(database_url)
        self.db_manager.create_tables()

        # Initialize scrapers
        self.scrapers: Dict[str, BaseScraper] = {
            'fed_reserve': FedScraper(self.db_manager),
            'reddit_wsb': RedditWSBScraper(self.db_manager)
        }

        self.lock = threading.Lock()

        logger.info(f"ScraperManager initialized with {len(self.scrapers)} scrapers")

    def run_all_scrapers(self,
                         force_update: bool = False,
                         parallel: bool = True,
                         timeout: int = 300) -> Dict[str, Any]:
        """Run all scrapers and return consolidated results"""

        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("STARTING MULTI-SCRAPER EXECUTION")
        logger.info("=" * 60)
        logger.info(f"Force update: {force_update}")
        logger.info(f"Parallel execution: {parallel}")
        logger.info(f"Timeout: {timeout}s")

        results = {}

        if parallel:
            results = self._run_scrapers_parallel(force_update, timeout)
        else:
            results = self._run_scrapers_sequential(force_update)

        # Generate summary
        summary = self._generate_execution_summary(results, start_time)

        logger.info("=" * 60)
        logger.info("MULTI-SCRAPER EXECUTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total execution time: {summary['total_execution_time_ms']:.0f}ms")
        logger.info(f"Successful scrapers: {summary['successful_scrapers']}/{summary['total_scrapers']}")
        logger.info(f"Total new content: {summary['total_new_content']}")

        return {
            'success': summary['successful_scrapers'] > 0,
            'summary': summary,
            'scraper_results': results,
            'execution_timestamp': start_time.isoformat()
        }

    def _run_scrapers_parallel(self, force_update: bool, timeout: int) -> Dict[str, Any]:
        """Run scrapers in parallel using ThreadPoolExecutor"""
        results = {}

        with ThreadPoolExecutor(max_workers=len(self.scrapers)) as executor:
            # Submit all scraper tasks
            future_to_scraper = {
                executor.submit(scraper.run_scraping, force_update): name
                for name, scraper in self.scrapers.items()
            }

            # Collect results as they complete
            for future in as_completed(future_to_scraper, timeout=timeout):
                scraper_name = future_to_scraper[future]

                try:
                    result = future.result(timeout=30)  # Individual scraper timeout
                    results[scraper_name] = result

                    status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
                    content_info = ""
                    if result['success']:
                        content_info = f" - {result.get('new_content_count', 0)} new items"

                    logger.info(f"{scraper_name}: {status}{content_info}")

                except Exception as e:
                    logger.error(f"{scraper_name}: ❌ CRASHED - {str(e)}")
                    results[scraper_name] = {
                        'success': False,
                        'scraper_name': scraper_name,
                        'error': f"Execution failed: {str(e)}",
                        'execution_time_ms': 0
                    }

        return results

    def _run_scrapers_sequential(self, force_update: bool) -> Dict[str, Any]:
        """Run scrapers sequentially"""
        results = {}

        for name, scraper in self.scrapers.items():
            logger.info(f"Running scraper: {name}")

            try:
                result = scraper.run_scraping(force_update)
                results[name] = result

                status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
                content_info = ""
                if result['success']:
                    content_info = f" - {result.get('new_content_count', 0)} new items"

                logger.info(f"{name}: {status}{content_info}")

            except Exception as e:
                logger.error(f"{name}: ❌ CRASHED - {str(e)}")
                results[name] = {
                    'success': False,
                    'scraper_name': name,
                    'error': f"Execution failed: {str(e)}",
                    'execution_time_ms': 0
                }

        return results

    def _generate_execution_summary(self, results: Dict[str, Any], start_time: datetime) -> Dict[str, Any]:
        """Generate execution summary from scraper results"""

        total_execution_time = (datetime.now() - start_time).total_seconds() * 1000

        summary = {
            'total_scrapers': len(self.scrapers),
            'successful_scrapers': sum(1 for r in results.values() if r.get('success', False)),
            'failed_scrapers': sum(1 for r in results.values() if not r.get('success', False)),
            'total_new_content': sum(r.get('new_content_count', 0) for r in results.values()),
            'total_content_found': sum(r.get('total_content_found', 0) for r in results.values()),
            'total_execution_time_ms': total_execution_time,
            'average_scraper_time_ms': sum(r.get('execution_time_ms', 0) for r in results.values()) / len(
                results) if results else 0,
            'execution_start': start_time.isoformat(),
            'execution_end': datetime.now().isoformat()
        }

        # Per-scraper breakdown
        summary['scraper_breakdown'] = {}
        for name, result in results.items():
            summary['scraper_breakdown'][name] = {
                'success': result.get('success', False),
                'new_content': result.get('new_content_count', 0),
                'total_found': result.get('total_content_found', 0),
                'execution_time_ms': result.get('execution_time_ms', 0),
                'message': result.get('message', 'No message'),
                'error': result.get('error')
            }

        return summary

    def run_single_scraper(self, scraper_name: str, force_update: bool = False) -> Dict[str, Any]:
        """Run a specific scraper by name"""

        if scraper_name not in self.scrapers:
            return {
                'success': False,
                'error': f"Scraper '{scraper_name}' not found. Available: {list(self.scrapers.keys())}"
            }

        logger.info(f"Running single scraper: {scraper_name}")

        try:
            scraper = self.scrapers[scraper_name]
            result = scraper.run_scraping(force_update)

            logger.info(f"{scraper_name}: {'✅ SUCCESS' if result['success'] else '❌ FAILED'}")
            return result

        except Exception as e:
            logger.error(f"{scraper_name}: ❌ CRASHED - {str(e)}")
            return {
                'success': False,
                'scraper_name': scraper_name,
                'error': f"Execution failed: {str(e)}"
            }

    def get_scraper_status(self) -> Dict[str, Any]:
        """Get status of all scrapers"""

        status = {
            'scrapers': {},
            'system': {
                'total_scrapers': len(self.scrapers),
                'status_checked_at': datetime.now().isoformat()
            }
        }

        for name, scraper in self.scrapers.items():
            try:
                with self.db_manager.get_session() as session:
                    from database.models import ScraperState

                    state = session.query(ScraperState).filter_by(scraper_name=name).first()

                    if state:
                        last_run_meta = json.loads(state.last_run_metadata or '{}')

                        status['scrapers'][name] = {
                            'last_check_time': state.last_check_time.isoformat() if state.last_check_time else None,
                            'total_runs': state.total_runs,
                            'successful_runs': state.successful_runs,
                            'success_rate': (
                                        state.successful_runs / state.total_runs * 100) if state.total_runs > 0 else 0,
                            'last_run_successful': last_run_meta.get('successful', False),
                            'created_at': state.created_at.isoformat(),
                            'updated_at': state.updated_at.isoformat()
                        }
                    else:
                        status['scrapers'][name] = {
                            'last_check_time': None,
                            'total_runs': 0,
                            'successful_runs': 0,
                            'success_rate': 0,
                            'last_run_successful': None,
                            'status': 'Never run'
                        }

            except Exception as e:
                status['scrapers'][name] = {
                    'error': f"Could not get status: {str(e)}"
                }

        return status

    def get_recent_content(self,
                           scraper_name: Optional[str] = None,
                           hours: int = 24,
                           limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent content from scrapers"""

        try:
            with self.db_manager.get_session() as session:
                from database.models import ScrapedData

                query = session.query(ScrapedData)

                # Filter by scraper if specified
                if scraper_name:
                    query = query.filter(ScrapedData.source == scraper_name)

                # Filter by time range
                cutoff_time = datetime.now() - timedelta(hours=hours)
                query = query.filter(ScrapedData.created_at >= cutoff_time)

                # Order by recency and limit
                results = query.order_by(ScrapedData.created_at.desc()).limit(limit).all()

                content_list = []
                for result in results:
                    metadata = json.loads(result.extra_metadata or '{}')

                    content_list.append({
                        'id': result.id,
                        'external_id': result.external_id,
                        'source': result.source,
                        'title': result.target_content,
                        'url': result.url,
                        'created_at': result.created_at.isoformat(),
                        'content_preview': result.raw_content[:200] + '...' if len(
                            result.raw_content) > 200 else result.raw_content,
                        'metadata': metadata
                    })

                return content_list

        except Exception as e:
            logger.error(f"Error getting recent content: {e}")
            return []

    def get_trending_analysis(self, hours: int = 6) -> Dict[str, Any]:
        """Get trending analysis across all scrapers"""

        try:
            recent_content = self.get_recent_content(hours=hours, limit=100)

            # Analyze trending topics
            analysis = {
                'time_range_hours': hours,
                'total_content_items': len(recent_content),
                'content_by_source': {},
                'trending_keywords': {},
                'analysis_timestamp': datetime.now().isoformat()
            }

            # Group by source
            for content in recent_content:
                source = content['source']
                if source not in analysis['content_by_source']:
                    analysis['content_by_source'][source] = {
                        'count': 0,
                        'recent_titles': []
                    }

                analysis['content_by_source'][source]['count'] += 1
                analysis['content_by_source'][source]['recent_titles'].append(content['title'])

            # Extract trending keywords (simple approach)
            all_text = ' '.join([content['title'] + ' ' + content['content_preview']
                                 for content in recent_content]).lower()

            # Simple keyword extraction
            import re
            words = re.findall(r'\b[a-z]{4,}\b', all_text)
            word_counts = {}

            # Filter relevant financial terms
            financial_keywords = [
                'rate', 'inflation', 'fed', 'powell', 'earnings', 'market',
                'stock', 'trading', 'investment', 'economy', 'gdp', 'fomc',
                'monetary', 'policy', 'bank', 'finance', 'bull', 'bear'
            ]

            for word in words:
                if word in financial_keywords:
                    word_counts[word] = word_counts.get(word, 0) + 1

            # Get top keywords
            analysis['trending_keywords'] = dict(
                sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            )

            return analysis

        except Exception as e:
            logger.error(f"Error generating trending analysis: {e}")
            return {
                'error': str(e),
                'analysis_timestamp': datetime.now().isoformat()
            }

    def cleanup_old_content(self, days: int = 30) -> Dict[str, Any]:
        """Clean up old scraped content to manage database size"""

        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            with self.db_manager.get_session() as session:
                from database.models import ScrapedData

                # Count records to be deleted
                old_records = session.query(ScrapedData).filter(
                    ScrapedData.created_at < cutoff_date
                ).count()

                if old_records > 0:
                    # Delete old records
                    deleted = session.query(ScrapedData).filter(
                        ScrapedData.created_at < cutoff_date
                    ).delete()

                    session.commit()

                    logger.info(f"Cleaned up {deleted} old content records (older than {days} days)")

                    return {
                        'success': True,
                        'deleted_records': deleted,
                        'cutoff_date': cutoff_date.isoformat(),
                        'cleanup_timestamp': datetime.now().isoformat()
                    }
                else:
                    return {
                        'success': True,
                        'deleted_records': 0,
                        'message': f'No records older than {days} days found',
                        'cleanup_timestamp': datetime.now().isoformat()
                    }

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return {
                'success': False,
                'error': str(e),
                'cleanup_timestamp': datetime.now().isoformat()
            }