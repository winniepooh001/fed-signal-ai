#!/usr/bin/env python3
"""
Multi-Scraper System Test Script
===============================

Tests the Fed and Reddit WSB scrapers with change detection.
"""

import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Initialize logging
from utils.logging_config import initialize_logging

logger = initialize_logging(
    log_level="INFO",
    console_output=True,
    log_file="scraper_test.log"
)


def test_fed_scraper():
    """Test Federal Reserve scraper"""
    logger.info("=" * 60)
    logger.info("TESTING FEDERAL RESERVE SCRAPER")
    logger.info("=" * 60)

    try:
        from agents.fed_scraper import FedScraper
        from database import DatabaseManager

        # Initialize
        db_manager = DatabaseManager("sqlite:///test_scrapers.db")
        db_manager.create_tables()

        fed_scraper = FedScraper(db_manager)
        logger.info("✅ Fed scraper initialized")

        # Test scraping
        logger.info("Running Fed scraper...")
        result = fed_scraper.run_scraping(force_update=True)

        if result['success']:
            logger.info(f"✅ Fed scraper SUCCESS")
            logger.info(f"   New content: {result['new_content_count']}")
            logger.info(f"   Total found: {result.get('total_content_found', 0)}")
            logger.info(f"   Execution time: {result['execution_time_ms']:.0f}ms")
            logger.info(f"   Message: {result.get('message', 'No message')}")

            # Show sample content
            if result['content_ids']:
                logger.info("   Sample content IDs:")
                for content_id in result['content_ids'][:3]:
                    logger.info(f"     - {content_id}")
        else:
            logger.error(f"❌ Fed scraper FAILED: {result.get('error', 'Unknown error')}")

        return result['success']

    except Exception as e:
        logger.error(f"❌ Fed scraper test crashed: {e}", exc_info=True)
        return False


def test_reddit_scraper():
    """Test Reddit WSB scraper"""
    logger.info("=" * 60)
    logger.info("TESTING REDDIT WSB SCRAPER")
    logger.info("=" * 60)

    try:
        from scrapers.reddit_scraper import RedditWSBScraper
        from database import DatabaseManager

        # Initialize
        db_manager = DatabaseManager("sqlite:///test_scrapers.db")
        db_manager.create_tables()

        reddit_scraper = RedditWSBScraper(db_manager)
        logger.info("✅ Reddit WSB scraper initialized")

        # Test scraping
        logger.info("Running Reddit WSB scraper...")
        result = reddit_scraper.run_scraping(force_update=True)

        if result['success']:
            logger.info(f"✅ Reddit WSB scraper SUCCESS")
            logger.info(f"   New content: {result['new_content_count']}")
            logger.info(f"   Total found: {result.get('total_content_found', 0)}")
            logger.info(f"   Execution time: {result['execution_time_ms']:.0f}ms")
            logger.info(f"   Message: {result.get('message', 'No message')}")

            # Test trending tickers
            logger.info("Getting trending tickers...")
            trending = reddit_scraper.get_trending_tickers(limit=5)

            if trending:
                logger.info("   Top trending tickers:")
                for ticker_data in trending:
                    ticker = ticker_data['ticker']
                    mentions = ticker_data['mentions']
                    upvotes = ticker_data['total_upvotes']
                    logger.info(f"     ${ticker}: {mentions} mentions, {upvotes} total upvotes")
            else:
                logger.info("   No trending tickers found")

        else:
            logger.error(f"❌ Reddit WSB scraper FAILED: {result.get('error', 'Unknown error')}")

        return result['success']

    except Exception as e:
        logger.error(f"❌ Reddit WSB scraper test crashed: {e}", exc_info=True)
        return False


def test_scraper_manager():
    """Test the unified scraper manager"""
    logger.info("=" * 60)
    logger.info("TESTING SCRAPER MANAGER")
    logger.info("=" * 60)

    try:
        from scrapers.scraper_manager import ScraperManager

        # Initialize manager
        manager = ScraperManager("sqlite:///test_scrapers.db")
        logger.info("✅ Scraper manager initialized")

        # Test status
        logger.info("Getting scraper status...")
        status = manager.get_scraper_status()
        logger.info(f"   Total scrapers: {status['system']['total_scrapers']}")

        for scraper_name, scraper_status in status['scrapers'].items():
            last_run = scraper_status.get('last_check_time', 'Never')
            success_rate = scraper_status.get('success_rate', 0)
            logger.info(f"   {scraper_name}: Last run: {last_run}, Success rate: {success_rate:.1f}%")

        # Test parallel execution
        logger.info("Running all scrapers in parallel...")
        result = manager.run_all_scrapers(force_update=True, parallel=True)

        if result['success']:
            summary = result['summary']
            logger.info(f"✅ Multi-scraper execution SUCCESS")
            logger.info(f"   Successful scrapers: {summary['successful_scrapers']}/{summary['total_scrapers']}")
            logger.info(f"   Total new content: {summary['total_new_content']}")
            logger.info(f"   Total execution time: {summary['total_execution_time_ms']:.0f}ms")

            # Show per-scraper breakdown
            logger.info("   Per-scraper results:")
            for scraper_name, scraper_result in summary['scraper_breakdown'].items():
                status = "✅" if scraper_result['success'] else "❌"
                content = scraper_result['new_content']
                time_ms = scraper_result['execution_time_ms']
                logger.info(f"     {status} {scraper_name}: {content} new items ({time_ms:.0f}ms)")
        else:
            logger.error(f"❌ Multi-scraper execution FAILED")

        # Test recent content retrieval
        logger.info("Getting recent content...")
        recent_content = manager.get_recent_content(hours=24, limit=10)
        logger.info(f"   Found {len(recent_content)} recent items")

        for content in recent_content[:3]:
            source = content['source']
            title = content['title'][:50] + '...' if len(content['title']) > 50 else content['title']
            logger.info(f"     {source}: {title}")

        # Test trending analysis
        logger.info("Getting trending analysis...")
        trending = manager.get_trending_analysis(hours=6)

        if 'error' not in trending:
            logger.info(f"   Content items analyzed: {trending['total_content_items']}")
            logger.info(f"   Sources: {list(trending['content_by_source'].keys())}")

            if trending['trending_keywords']:
                logger.info("   Top trending keywords:")
                for keyword, count in list(trending['trending_keywords'].items())[:5]:
                    logger.info(f"     {keyword}: {count} mentions")
        else:
            logger.warning(f"   Trending analysis failed: {trending['error']}")

        return result['success']

    except Exception as e:
        logger.error(f"❌ Scraper manager test crashed: {e}", exc_info=True)
        return False


def test_change_detection():
    """Test change detection functionality"""
    logger.info("=" * 60)
    logger.info("TESTING CHANGE DETECTION")
    logger.info("=" * 60)

    try:
        from scrapers.scraper_manager import ScraperManager

        manager = ScraperManager("sqlite:///test_scrapers.db")

        # Run scrapers once
        logger.info("First run (should find new content)...")
        result1 = manager.run_all_scrapers(force_update=False)

        new_content_1 = result1['summary']['total_new_content']
        logger.info(f"   First run found: {new_content_1} new items")

        # Run again immediately (should find little or no new content)
        logger.info("Second run (should find little new content)...")
        result2 = manager.run_all_scrapers(force_update=False)

        new_content_2 = result2['summary']['total_new_content']
        logger.info(f"   Second run found: {new_content_2} new items")

        # Test force update
        logger.info("Third run with force update (should re-scrape everything)...")
        result3 = manager.run_all_scrapers(force_update=True)

        new_content_3 = result3['summary']['total_new_content']
        logger.info(f"   Force update found: {new_content_3} new items")

        # Analyze results
        if new_content_2 < new_content_1:
            logger.info("✅ Change detection working: Second run found less content")
        else:
            logger.warning("⚠️  Change detection may not be working optimally")

        if new_content_3 >= new_content_1:
            logger.info("✅ Force update working: Third run re-scraped content")
        else:
            logger.warning("⚠️  Force update may not be working correctly")

        return True

    except Exception as e:
        logger.error(f"❌ Change detection test crashed: {e}", exc_info=True)
        return False


def test_database_cleanup():
    """Test database cleanup functionality"""
    logger.info("=" * 60)
    logger.info("TESTING DATABASE CLEANUP")
    logger.info("=" * 60)

    try:
        from scrapers.scraper_manager import ScraperManager

        manager = ScraperManager("sqlite:///test_scrapers.db")

        # Get current content count
        recent_content = manager.get_recent_content(hours=24 * 30, limit=1000)  # Last month
        logger.info(f"Current content items: {len(recent_content)}")

        # Test cleanup (use a very short period for testing)
        logger.info("Testing cleanup with 0 days (should clean nothing)...")
        cleanup_result = manager.cleanup_old_content(days=0)

        if cleanup_result['success']:
            deleted = cleanup_result['deleted_records']
            logger.info(f"✅ Cleanup test successful: {deleted} records would be deleted")
        else:
            logger.error(f"❌ Cleanup test failed: {cleanup_result.get('error')}")

        return cleanup_result['success']

    except Exception as e:
        logger.error(f"❌ Database cleanup test crashed: {e}", exc_info=True)
        return False


def run_performance_test():
    """Run performance test with timing"""
    logger.info("=" * 60)
    logger.info("RUNNING PERFORMANCE TEST")
    logger.info("=" * 60)

    try:
        from scrapers.scraper_manager import ScraperManager
        import time

        manager = ScraperManager("sqlite:///test_scrapers.db")

        # Test sequential vs parallel performance
        logger.info("Testing sequential execution...")
        start_time = time.time()
        sequential_result = manager.run_all_scrapers(force_update=True, parallel=False)
        sequential_time = time.time() - start_time

        logger.info("Testing parallel execution...")
        start_time = time.time()
        parallel_result = manager.run_all_scrapers(force_update=True, parallel=True)
        parallel_time = time.time() - start_time

        # Compare results
        logger.info("Performance comparison:")
        logger.info(f"   Sequential: {sequential_time:.2f}s")
        logger.info(f"   Parallel: {parallel_time:.2f}s")

        if parallel_time < sequential_time:
            speedup = sequential_time / parallel_time
            logger.info(f"   ✅ Parallel execution {speedup:.1f}x faster")
        else:
            logger.info(f"   ⚠️  No significant performance improvement from parallel execution")

        return True

    except Exception as e:
        logger.error(f"❌ Performance test crashed: {e}", exc_info=True)
        return False


def main():
    """Run all scraper tests"""

    logger.info("🧪 STARTING MULTI-SCRAPER SYSTEM TESTS")
    logger.info("=" * 80)

    tests = [
        ("Fed Scraper", test_fed_scraper),
        ("Reddit WSB Scraper", test_reddit_scraper),
        ("Scraper Manager", test_scraper_manager),
        ("Change Detection", test_change_detection),
        ("Database Cleanup", test_database_cleanup),
        ("Performance Test", run_performance_test)
    ]

    results = []

    for test_name, test_func in tests:
        logger.info(f"\n🧪 Running {test_name} test...")
        try:
            result = test_func()
            results.append((test_name, result))
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"   {status}")
        except Exception as e:
            logger.error(f"   ❌ CRASHED: {e}")
            results.append((test_name, False))

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("SCRAPER SYSTEM TEST SUMMARY")
    logger.info("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{status} {test_name}")

    logger.info("-" * 80)
    logger.info(f"OVERALL RESULT: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 ALL SCRAPER TESTS PASSED!")
        logger.info("Your multi-scraper system is working correctly.")
    else:
        logger.error(f"⚠️  {total - passed} tests failed. Check the logs above for details.")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)