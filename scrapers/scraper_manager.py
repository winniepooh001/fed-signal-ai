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

logger = ScreenerLogger.initialize("INFO", log_file="fed_scraper.log", log_dir="../logs")

import time
from scrapers.util import FileLocker, write_relevant_content

from scrapers.fed_scraper import FedScraper
from scrapers.file_handler import SimpleFileManager
from scrapers.sentimental_analyzer import FinancialSentimentAnalyzer
from scrapers.summarizer import enhance_relevant_content_with_summaries
from dotenv import load_dotenv
load_dotenv()

in_debug = False

def delete_all_files_in_directory(directory_path):
    logger.info(f"clear {directory_path}")
    for filename in os.listdir(directory_path):
        file_path = os.path.join(directory_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)  # Delete file or symlink
            elif os.path.isdir(file_path):
                # Skip subdirectories (or handle them if needed)
                continue
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")


def main():
    """Main execution function"""
    cur_dir = os.getcwd()
    # Configuration
    config = {
        'data_dir': f'{cur_dir}/data',
        'output_file': os.getenv('OUTPUT_FILE', f'{cur_dir}/output/relevant_fed_content.json'),
        'log_file': os.getenv('LOG_FILE', f'{cur_dir}/logs/fed_scraper.log'),
        'lock_file': os.getenv('LOCK_FILE', f'{cur_dir}/data/fed_scraper.lock')
    }

    # Setup logging

    start_time = time.time()

    if in_debug:
        delete_all_files_in_directory(f"{cur_dir}/data")
        delete_all_files_in_directory(f"{cur_dir}/output")
    try:
        # Check if another instance is running
        with FileLocker(config['lock_file']):
            logger.info("=" * 60)
            logger.info("STARTING FED SCRAPER CRON JOB")
            logger.info("=" * 60)

            # Initialize components
            file_manager = SimpleFileManager(config['data_dir'])
            scraper = FedScraper()
            sentiment_config = {
                'provider': os.getenv('SENTIMENT_PROVIDER', 'vader_finance')  # Default to lightweight
            }
            sentiment_analyzer = FinancialSentimentAnalyzer(sentiment_config)

            # Determine cutoff time for new content
            last_run = file_manager.get_last_run_time()
            if last_run:
                cutoff_time = last_run
                logger.info(f"Last run: {last_run}, checking for new content since then")
            else:
                # First run - look back 1 day
                cutoff_time = datetime.now() - timedelta(days=14)
                logger.info(f"First run - checking content from last 7 days")

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
                        sentiment = sentiment_analyzer.is_relevant_for_trading(content.content, content.title, 0.5)
                        content.sentiment = sentiment

                        if sentiment["relevant"]:
                            relevant_items.append(content)
                            content = enhance_relevant_content_with_summaries(content)

                    except Exception as e:
                        logger.error(f"Error analyzing content {content.url}: {e}")
                        continue

                logger.info(f"Found {len(relevant_items)} relevant items")

                # Write relevant content directly to output file
                if relevant_items:
                    write_relevant_content(relevant_items, config['output_file'])
                else:
                    logger.info("No relevant content found")

                # Log successful run
                execution_time = int((time.time() - start_time) * 1000)
                file_manager.log_run(len(new_content), len(relevant_items), execution_time)

                # Update last run time
                file_manager.update_last_run_time()

                logger.info(f"Scraper completed successfully")
                logger.info(f"   New items: {len(new_content)}")
                logger.info(f"   Relevant items: {len(relevant_items)}")
                logger.info(f"   Execution time: {execution_time}ms")

            else:
                # No new content found - just update the run time
                execution_time = int((time.time() - start_time) * 1000)
                file_manager.log_run(0, 0, execution_time)
                file_manager.update_last_run_time()
                logger.info("No new content found")

            # Periodic cleanup
            file_manager.cleanup_old_hashes()

    except RuntimeError as e:
        logger.error(f"Could not acquire lock: {e}")
        return 1

    except Exception as e:
        execution_time = int((time.time() - start_time) * 1000)
        try:
            file_manager = SimpleFileManager(config['data_dir'])
            file_manager.log_run(0, 0, execution_time, 'error')
        except:
            pass
        logger.error(f" Scraper failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())