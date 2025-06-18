import os

from utils.logging_config import get_logger

logger = get_logger(__name__)


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
