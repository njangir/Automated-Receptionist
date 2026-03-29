"""Log management service for centralized log directory and automatic cleanup."""
import logging
import os
from pathlib import Path
from typing import List, Tuple

from services.path_utils import get_app_data_dir

logger = logging.getLogger(__name__)

def get_log_dir() -> Path:
    """
    Get the log directory (always uses app data directory).

    Returns:
        Path to log directory in app data directory
    """
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir

def get_total_log_size(log_dir: Path) -> int:
    """
    Calculate total size of all log files in the directory.

    Args:
        log_dir: Directory containing log files

    Returns:
        Total size in bytes
    """
    total_size = 0
    try:
        for file_path in log_dir.iterdir():
            if file_path.is_file():
                try:
                    total_size += file_path.stat().st_size
                except (OSError, PermissionError) as e:
                    logger.warning(f"Could not get size for {file_path}: {e}")
    except (OSError, PermissionError) as e:
        logger.warning(f"Could not read log directory {log_dir}: {e}")

    return total_size

def get_log_files_sorted(log_dir: Path) -> List[Tuple[Path, float]]:
    """
    Get all log files sorted by modification time (oldest first).

    Args:
        log_dir: Directory containing log files

    Returns:
        List of tuples (file_path, modification_time) sorted by modification time
    """
    log_files = []
    try:
        for file_path in log_dir.iterdir():
            if file_path.is_file():
                try:
                    mtime = file_path.stat().st_mtime
                    log_files.append((file_path, mtime))
                except (OSError, PermissionError) as e:
                    logger.warning(f"Could not get modification time for {file_path}: {e}")
    except (OSError, PermissionError) as e:
        logger.warning(f"Could not read log directory {log_dir}: {e}")

    log_files.sort(key=lambda x: x[1])
    return log_files

def cleanup_logs(max_size_mb: int = 500, exclude_files: List[Path] = None) -> dict:
    """
    Clean up log files to keep total size under the specified limit.
    Deletes oldest files first until total size is under limit.

    Args:
        max_size_mb: Maximum total log size in MB (default: 500)
        exclude_files: List of file paths to exclude from deletion
                       (e.g., currently open log files)

    Returns:
        Dictionary with cleanup results:
        {
            'deleted_count': int,
            'space_freed_mb': float,
            'remaining_size_mb': float,
            'success': bool
        }
    """
    if exclude_files is None:
        exclude_files = []

    exclude_set = {Path(f).resolve() for f in exclude_files}

    log_dir = get_log_dir()
    max_size_bytes = max_size_mb * 1024 * 1024

    result = {
        'deleted_count': 0,
        'space_freed_mb': 0.0,
        'remaining_size_mb': 0.0,
        'success': False
    }

    try:

        log_files = get_log_files_sorted(log_dir)

        log_files = [(path, mtime) for path, mtime in log_files if path.resolve() not in exclude_set]

        total_size = get_total_log_size(log_dir)

        if total_size <= max_size_bytes:

            result['remaining_size_mb'] = total_size / (1024 * 1024)
            result['success'] = True
            logger.info(f"Log cleanup: No cleanup needed. Current size: {result['remaining_size_mb']:.2f} MB (limit: {max_size_mb} MB)")
            return result

        space_freed = 0
        deleted_count = 0

        for file_path, _ in log_files:
            if total_size <= max_size_bytes:
                break

            try:
                file_size = file_path.stat().st_size
                file_path.unlink()
                total_size -= file_size
                space_freed += file_size
                deleted_count += 1
                logger.debug(f"Deleted log file: {file_path} ({file_size / (1024 * 1024):.2f} MB)")
            except (OSError, PermissionError) as e:
                logger.warning(f"Could not delete log file {file_path}: {e}")

        result['deleted_count'] = deleted_count
        result['space_freed_mb'] = space_freed / (1024 * 1024)
        result['remaining_size_mb'] = total_size / (1024 * 1024)
        result['success'] = True

        logger.info(
            f"Log cleanup completed: Deleted {deleted_count} files, "
            f"freed {result['space_freed_mb']:.2f} MB, "
            f"remaining size: {result['remaining_size_mb']:.2f} MB (limit: {max_size_mb} MB)"
        )

    except Exception as e:
        logger.error(f"Error during log cleanup: {e}", exc_info=True)
        result['success'] = False

    return result
