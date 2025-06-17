#!/usr/bin/env python3
"""
Standalone Fed Scraper with Sentiment Analysis
Designed to run as a cron job every 30 minutes during business hours (9-5 M-F)

Usage:
    python fed_scraper_standalone.py

Cron Setup (every 30 minutes, 9-5 M-F):
    */30 9-17 * * 1-5 /usr/bin/python3 /path/to/fed_scraper_standalone.py
"""

import os
import sys
import json
import time
import hashlib
from utils.logging_config import get_logger
import platform
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

logger = get_logger(__name__)

class SimpleFileManager:
    """Simple file-based tracking for scraper runs and content hashes"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.last_run_file = self.data_dir / "last_run.txt"
        self.content_hashes_file = self.data_dir / "content_hashes.txt"
        self.run_log_file = self.data_dir / "run_log.txt"

    def get_last_run_time(self) -> Optional[datetime]:
        """Get the timestamp of the last successful run"""
        try:
            if self.last_run_file.exists():
                with open(self.last_run_file, 'r') as f:
                    timestamp_str = f.read().strip()
                    return datetime.fromisoformat(timestamp_str)
        except Exception as e:
            logger.warning(f"Could not read last run time: {e}")
        return None

    def update_last_run_time(self):
        """Update the last run timestamp"""
        try:
            with open(self.last_run_file, 'w') as f:
                f.write(datetime.now().isoformat())
        except Exception as e:
            logger.error(f"Could not update last run time: {e}")

    def is_content_new(self, content_hash: str) -> bool:
        """Check if content is new based on hash"""
        try:
            if self.content_hashes_file.exists():
                with open(self.content_hashes_file, 'r') as f:
                    existing_hashes = set(line.strip() for line in f)
                    return content_hash not in existing_hashes
        except Exception as e:
            logger.warning(f"Could not read content hashes: {e}")
        return True  # Assume new if we can't read the file

    def add_content_hash(self, content_hash: str):
        """Add a content hash to the tracking file"""
        try:
            with open(self.content_hashes_file, 'a') as f:
                f.write(f"{content_hash}\n")
        except Exception as e:
            logger.error(f"Could not save content hash: {e}")

    def log_run(self, new_items: int, relevant_items: int, execution_time_ms: int, status: str = 'success'):
        """Log scraper run to file"""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'new_items': new_items,
                'relevant_items': relevant_items,
                'execution_time_ms': execution_time_ms,
                'status': status
            }

            with open(self.run_log_file, 'a') as f:
                f.write(f"{json.dumps(log_entry)}\n")
        except Exception as e:
            logger.error(f"Could not log run: {e}")

    def cleanup_old_hashes(self, days: int = 30):
        """Clean up old content hashes to prevent file from growing too large"""
        try:
            if self.content_hashes_file.exists():
                # For simplicity, just keep the last 10000 hashes
                with open(self.content_hashes_file, 'r') as f:
                    lines = f.readlines()

                if len(lines) > 10000:
                    with open(self.content_hashes_file, 'w') as f:
                        f.writelines(lines[-10000:])
                    logger.info(f"Cleaned up content hashes, kept last 10000 entries")
        except Exception as e:
            logger.warning(f"Could not cleanup old hashes: {e}")
