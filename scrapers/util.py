import json
import os
import platform
from datetime import datetime
from typing import List

from scrapers.model_object import FedContent
from utils.logging_config import get_logger

logger = get_logger(__name__)


def write_relevant_content_with_scraped_ids(
    content_items: List[FedContent], output_file: str
):
    """Write relevant content with scraped_data_ids included"""

    if not content_items:
        logger.info("No relevant content found - no output file written")
        return

    lock_file = f"{output_file}.lock"

    try:
        with FileLocker(lock_file):
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)

            # Prepare output data
            output_data = {
                "timestamp": datetime.now().isoformat(),
                "content_count": len(content_items),
                "items": [],
            }

            for content in content_items:
                item_data = {
                    "scraped_data_id": getattr(
                        content, "scraped_data_id", None
                    ),  # Include database ID
                    "url": content.url,
                    "title": content.title,
                    "published_date": content.published_date.isoformat(),
                    "sentiment_score": (
                        content.sentiment["sentiment_analysis"]["scores"]
                        if content.sentiment
                        else {}
                    ),
                    "sentiment": (
                        content.sentiment["sentiment_analysis"]["sentiment"]
                        if content.sentiment
                        else "UNKNOWN"
                    ),
                    "model_name": (
                        content.sentiment["model"] if content.sentiment else "unknown"
                    ),
                    "full_content": content.content,
                    "summary": getattr(content, "summary", "No summary available"),
                }
                output_data["items"].append(item_data)

            # Write to output file
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            logger.info(
                f"✅ Wrote {len(content_items)} relevant items with scraped_data_ids to {output_file}"
            )

    except RuntimeError as e:
        logger.error(f"Could not write to output file (file locked): {e}")
    except Exception as e:
        logger.error(f"Error writing output file: {e}")


class FileLocker:
    """Cross-platform file-based locking mechanism"""

    def __init__(self, lock_file: str):
        self.lock_file = lock_file
        self.lock_handle = None
        self.is_windows = platform.system().lower() == "windows"

    def __enter__(self):
        try:
            # Check if lock file already exists
            if os.path.exists(self.lock_file):
                # Check if the process that created the lock is still running
                if self._is_lock_stale():
                    self._remove_stale_lock()
                else:
                    raise RuntimeError(
                        f"Lock file exists and process is still running: {self.lock_file}"
                    )

            # Create lock file
            self.lock_handle = open(self.lock_file, "w")

            if self.is_windows:
                # Windows file locking
                try:
                    import msvcrt

                    msvcrt.locking(self.lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
                except ImportError:
                    # Fallback for Windows without msvcrt (shouldn't happen)
                    pass
                except OSError:
                    self.lock_handle.close()
                    raise RuntimeError(
                        f"Could not acquire Windows lock: {self.lock_file}"
                    )
            else:
                # Unix file locking
                try:
                    import fcntl

                    fcntl.flock(
                        self.lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
                    )
                except ImportError:
                    # Fallback if fcntl not available
                    pass
                except (IOError, OSError):
                    self.lock_handle.close()
                    raise RuntimeError(f"Could not acquire Unix lock: {self.lock_file}")

            # Write lock info
            lock_info = {
                "pid": os.getpid(),
                "started": datetime.now().isoformat(),
                "platform": platform.system(),
            }
            self.lock_handle.write(json.dumps(lock_info, indent=2))
            self.lock_handle.flush()

            return self

        except Exception as e:
            if self.lock_handle:
                try:
                    self.lock_handle.close()
                except:
                    pass
            raise RuntimeError(f"Could not acquire lock: {self.lock_file} - {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_handle:
            try:
                if self.is_windows:
                    try:
                        import msvcrt

                        msvcrt.locking(self.lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                    except ImportError:
                        pass
                else:
                    try:
                        import fcntl

                        fcntl.flock(self.lock_handle.fileno(), fcntl.LOCK_UN)
                    except ImportError:
                        pass

                self.lock_handle.close()
            except:
                pass

        # Remove lock file
        try:
            if os.path.exists(self.lock_file):
                os.unlink(self.lock_file)
        except:
            pass

    def _is_lock_stale(self) -> bool:
        """Check if lock file is stale (process no longer running)"""
        try:
            with open(self.lock_file, "r") as f:
                lock_data = json.load(f)

            pid = lock_data.get("pid")
            if not pid:
                return True

            # Check if process is still running
            if self.is_windows:
                return not self._is_process_running_windows(pid)
            else:
                return not self._is_process_running_unix(pid)

        except Exception:
            # If we can't read the lock file, consider it stale
            return True

    def _is_process_running_windows(self, pid: int) -> bool:
        """Check if process is running on Windows"""
        try:
            import subprocess

            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return str(pid) in result.stdout
        except Exception:
            return False

    def _is_process_running_unix(self, pid: int) -> bool:
        """Check if process is running on Unix"""
        try:
            # Send signal 0 to check if process exists
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception:
            return False

    def _remove_stale_lock(self):
        """Remove a stale lock file"""
        try:
            os.unlink(self.lock_file)
            logger.info(f"Removed stale lock file: {self.lock_file}")
        except Exception as e:
            logger.warning(f"Could not remove stale lock file {self.lock_file}: {e}")
