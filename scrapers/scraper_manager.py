import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent.absolute()

# Add the project root to Python path so it can find utils, database, etc.
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# Also add parent directory in case project structure is nested
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logging_config import ScreenerLogger

logger = ScreenerLogger.initialize(
    "INFO", log_file="fed_scraper.log", log_dir="../logs"
)

import time

from dotenv import load_dotenv

from database import DatabaseManager
from market_data.data_fetch import fetch_and_save_market_data_to_table
from scrapers.fed_scraper import FedScraper
from scrapers.file_handler import SimpleFileManager
from scrapers.sentimental_analyzer import FinancialSentimentAnalyzer
from scrapers.summarizer import enhance_relevant_content_with_summaries
from scrapers.util import FileLocker, write_relevant_content_with_scraped_ids
from utils.file_and_folder import delete_all_files_in_directory

load_dotenv()

in_debug = True
DATABASE_AVAILABLE = True
MARKET_DATA_AVAILABLE = True


def main():
    """Main execution function"""
    cur_dir = os.getcwd()
    # Configuration
    config = {
        "data_dir": f"{cur_dir}/data",
        "output_file": os.getenv("OUTPUT_FILE", "{cur_dir}/output/{execution_id}.json"),
        "market_data_output": os.getenv(
            "MARKET_DATA_OUTPUT", "{cur_dir}/output/{execution_id}.json"
        ),
        "log_file": os.getenv("LOG_FILE", f"{cur_dir}/logs/fed_scraper.log"),
        "lock_file": os.getenv("LOCK_FILE", f"{cur_dir}/data/fed_scraper.lock"),
        "database_url": os.getenv("DATABASE_URL", "sqlite:///screener_data.db"),
    }

    start_time = time.time()

    if in_debug:
        delete_all_files_in_directory(f"{cur_dir}/data")
        delete_all_files_in_directory(f"{cur_dir}/output")

    try:
        # Check if another instance is running
        with FileLocker(config["lock_file"]):
            logger.info("=" * 60)
            logger.info("STARTING FED SCRAPER WITH MARKET DATA INTEGRATION")
            logger.info("=" * 60)

            # Initialize database manager
            db_manager = None
            execution_id = None
            if DATABASE_AVAILABLE:
                try:
                    db_manager = DatabaseManager(config["database_url"])
                    db_manager.create_tables()

                    # Start agent execution tracking
                    execution_id = db_manager.start_agent_execution(
                        user_prompt="Fed scraper with market data collection",
                        execution_type="fed_scraper_with_market_data",
                    )
                    logger.info(f"Database initialized, execution ID: {execution_id}")
                except Exception as e:
                    logger.error(f"Database initialization failed: {e}")
                    db_manager = None
            if execution_id is None:
                raise KeyError("No Execution ID provided")

            # Initialize components
            file_manager = SimpleFileManager(config["data_dir"])
            scraper = FedScraper()
            sentiment_config = {
                "provider": os.getenv(
                    "SENTIMENT_PROVIDER", "vader_finance"
                )  # Default to lightweight
            }
            sentiment_analyzer = FinancialSentimentAnalyzer(sentiment_config)

            # Determine cutoff time for new content
            last_run = file_manager.get_last_run_time()
            if last_run:
                cutoff_time = last_run
                logger.info(
                    f"Last run: {last_run}, checking for new content since then"
                )
            else:
                # First run - look back 14 days
                cutoff_time = datetime.now() - timedelta(days=14)
                logger.info("First run - checking content from last 14 days")

            # Scrape new content
            logger.info("Starting content scraping...")
            all_content = scraper.scrape_new_content(cutoff_time)
            logger.info(f"Found {len(all_content)} total content items")

            # Filter for truly new content
            new_content = []
            for content in all_content:
                if file_manager.is_content_new(content.content_hash):
                    new_content.append(content)
                    # Track this content hash
                    file_manager.add_content_hash(content.content_hash)

            logger.info(f"Found {len(new_content)} new content items")

            if new_content:
                # Analyze sentiment for new content
                relevant_items = []

                for content in new_content:
                    try:
                        sentiment = sentiment_analyzer.is_relevant_for_trading(
                            content.content, content.title, 0.5
                        )
                        content.sentiment = sentiment

                        if sentiment["relevant"]:
                            relevant_items.append(content)
                            content = enhance_relevant_content_with_summaries(content)

                    except Exception as e:
                        logger.error(f"Error analyzing content {content.url}: {e}")
                        continue

                logger.info(f"Found {len(relevant_items)} relevant items")

                # Collect raw market data when relevant Fed content is found
                if relevant_items and MARKET_DATA_AVAILABLE and DATABASE_AVAILABLE:
                    logger.info("Collecting raw market data and saving to database...")
                    try:
                        # Simple market data configuration
                        market_config = {
                            "yfinance": {"rate_limit_delay": 0.2, "max_retries": 2}
                        }

                        # Fetch raw market data and save to database
                        market_result = fetch_and_save_market_data_to_table(
                            relevant_items,
                            config["database_url"],
                            agent_execution_id=execution_id,
                            config=market_config,
                        )

                        # Log simple results
                        market_data_id = market_result.get("database_records", {}).get(
                            "market_snapshot_id"
                        )
                        symbols_fetched = market_result.get("market_data", {}).get(
                            "symbols_fetched", 0
                        )

                        logger.info("✅ Raw market data saved to database")
                        logger.info(f"   Market data ID: {market_data_id}")
                        logger.info(f"   Symbols collected: {symbols_fetched}")

                    except Exception as e:
                        logger.error(f"Error in raw market data collection: {e}")

                elif relevant_items:
                    logger.info("No Relevant Feeds")

                # Write relevant content directly to output file (preserve original functionality)
                if relevant_items:
                    write_relevant_content_with_scraped_ids(
                        relevant_items,
                        config["output_file"].format(
                            cur_dir=cur_dir, execution_id=execution_id
                        ),
                    )
                else:
                    logger.info("No relevant content found")

                # Log successful run
                execution_time = int((time.time() - start_time) * 1000)
                file_manager.log_run(
                    len(new_content), len(relevant_items), execution_time
                )

                # Complete execution tracking
                if db_manager and execution_id:
                    try:
                        summary = f"Processed {len(new_content)} new items, {len(relevant_items)} relevant. Market data: {'✅' if MARKET_DATA_AVAILABLE else '❌'}"
                        db_manager.complete_agent_execution(
                            execution_id=execution_id,
                            agent_reasoning=summary,
                            success=True,
                        )
                    except Exception as e:
                        logger.error(f"Error completing execution tracking: {e}")

                # Update last run time
                file_manager.update_last_run_time()

                logger.info("Scraper completed successfully")
                logger.info(f"   New items: {len(new_content)}")
                logger.info(f"   Relevant items: {len(relevant_items)}")
                logger.info(
                    f"   Database integration: {'✅' if DATABASE_AVAILABLE else '❌'}"
                )
                logger.info(
                    f"   Market data: {'✅' if MARKET_DATA_AVAILABLE else '❌'}"
                )
                logger.info(f"   Execution time: {execution_time}ms")

            else:
                # No new content found - just update the run time
                execution_time = int((time.time() - start_time) * 1000)
                file_manager.log_run(0, 0, execution_time)
                file_manager.update_last_run_time()

                # Complete execution tracking
                if db_manager and execution_id:
                    try:
                        db_manager.complete_agent_execution(
                            execution_id=execution_id,
                            agent_reasoning="No new content found",
                            success=True,
                        )
                    except Exception as e:
                        logger.error(f"Error completing execution tracking: {e}")

                logger.info("No new content found")

            # Periodic cleanup
            file_manager.cleanup_old_hashes()

    except RuntimeError as e:
        logger.error(f"Could not acquire lock: {e}")
        return 1

    except Exception as e:
        execution_time = int((time.time() - start_time) * 1000)
        try:
            file_manager = SimpleFileManager(config["data_dir"])
            file_manager.log_run(0, 0, execution_time, "error")
        except:
            pass
        logger.error(f"Scraper failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
