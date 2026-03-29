"""Main entry point for the Voice Agent Server."""
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from services.path_utils import get_project_root, is_frozen, get_app_data_dir
from services.log_manager import get_log_dir

def setup_logging():
    """Configure logging to write to both console and file."""

    log_dir = get_log_dir()

    log_file = log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured. Log file: {log_file}")
    return log_file

log_file = setup_logging()

import uvicorn
from server.api import app, open_browser
from services.config_loader import load_config
from services.log_manager import cleanup_logs

logger = logging.getLogger(__name__)

if is_frozen():

    load_config()
else:

    root_dir = Path(__file__).parent.resolve()
    load_config(root_dir)

try:

    max_size_mb_str = os.getenv("LOG_MAX_SIZE_MB", "500")

    if max_size_mb_str == "500":
        try:
            from services.config_service import read_config
            from services.path_utils import get_config_dir
            if is_frozen():
                config_file = get_config_dir() / ".env.config"
            else:
                config_file = Path(__file__).parent.resolve() / ".env.config"
            if config_file.exists():
                config = read_config(config_file)
                if "LOG_MAX_SIZE_MB" in config and config["LOG_MAX_SIZE_MB"]:
                    max_size_mb_str = config["LOG_MAX_SIZE_MB"]
        except Exception:
            pass

    max_size_mb = int(max_size_mb_str)

    cleanup_result = cleanup_logs(max_size_mb=max_size_mb, exclude_files=[log_file])

    if cleanup_result['success']:
        if cleanup_result['deleted_count'] > 0:
            logger.info(
                f"Log cleanup: Deleted {cleanup_result['deleted_count']} files, "
                f"freed {cleanup_result['space_freed_mb']:.2f} MB"
            )
    else:
        logger.warning("Log cleanup failed, but continuing with startup")
except Exception as e:
    logger.warning(f"Error during log cleanup on startup: {e}, but continuing with startup")

try:
    from services.firebase_service import (
        initialize_firebase,
        get_installer_id_from_bundle,
        load_stored_token,
    )

    if initialize_firebase():
        logger.info("Firebase initialized successfully")

        installer_id = get_installer_id_from_bundle()
        if installer_id:
            logger.info(f"Installer ID: {installer_id}")

        from services.firebase_service import TOKEN_EXPIRY_DAYS
        token_data = load_stored_token()
        if token_data:
            logger.info(f"Loaded stored authentication token (expires in {TOKEN_EXPIRY_DAYS} days)")
        else:
            logger.info("No valid stored authentication token found")
    else:
        logger.info("Firebase not configured or initialization failed")
except Exception as e:
    logger.warning(f"Firebase initialization error: {e}")
    logger.info("Continuing without Firebase (file download features will be unavailable)")

def start_server():
    """Start the unified FastAPI server."""

    if is_frozen():
        load_config()
    else:
        root_dir = Path(__file__).parent.resolve()
        load_config(root_dir)

    port = int(os.getenv("SERVER_PORT", os.getenv("AGENT_MANAGER_PORT", "8000")))
    host = os.getenv("SERVER_HOST", os.getenv("AGENT_MANAGER_HOST", "0.0.0.0"))

    logger.info(f"Starting unified server on {host}:{port}")

    import threading

    def run_server():
        uvicorn.run(app, host=host, port=port)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    time.sleep(2)

    url = f"http://127.0.0.1:{port}/ui" if host == "0.0.0.0" else f"http://{host}:{port}/ui"
    open_browser(url, delay=0.5, app_mode=True)

    logger.info("Server is ready. Configuration can be managed through the web UI.")

    try:
        server_thread.join()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")

if __name__ == "__main__":

    start_server()