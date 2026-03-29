"""Dynamic file loader for browser automation modules.

This module provides infrastructure for dynamically loading excluded browser automation
files that are not bundled with PyInstaller. Files can be loaded from:
1. App data directory (when running from PyInstaller)
2. Project directory (development mode)
3. Remote download (stub - to be implemented)
"""
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Optional, Any

from services.path_utils import (
    get_browser_automation_dir,
    is_frozen,
    get_project_root,
)

logger = logging.getLogger(__name__)

_loaded_modules: dict[str, Any] = {}

def load_module_dynamically(module_name: str, file_name: str) -> Optional[Any]:
    """
    Dynamically load a Python module from file system.

    This function attempts to load a module from:
    1. App data directory (frozen mode) or project directory (dev mode)
    2. If not found, attempts to download it (stub - to be implemented)
    3. Falls back to bundled module if available

    Args:
        module_name: Full module name (e.g., 'services.browser_automation.login_service')
        file_name: Name of the Python file (e.g., 'login_service.py')

    Returns:
        Loaded module object, or None if loading failed
    """

    if module_name in _loaded_modules:
        return _loaded_modules[module_name]

    if is_frozen():

        file_path = get_browser_automation_dir() / file_name
    else:

        file_path = get_project_root() / "services" / "browser_automation" / file_name

    if file_path.exists():
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to create spec for {module_name} from {file_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            _loaded_modules[module_name] = module
            logger.info(f"Successfully loaded {module_name} from {file_path}")
            return module
        except Exception as e:
            logger.error(f"Failed to load {module_name} from {file_path}: {e}")
            return None

    logger.warning(f"Module file not found: {file_path}")
    logger.info(f"Attempting to download {file_name}...")

    downloaded = download_module_file(file_name)
    if downloaded and downloaded.exists():

        try:
            spec = importlib.util.spec_from_file_location(module_name, downloaded)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to create spec for {module_name} from {downloaded}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            _loaded_modules[module_name] = module
            logger.info(f"Successfully loaded {module_name} from downloaded file: {downloaded}")
            return module
        except Exception as e:
            logger.error(f"Failed to load {module_name} from downloaded file: {e}")
            return None

    try:
        module = __import__(module_name, fromlist=[""])
        _loaded_modules[module_name] = module
        logger.info(f"Loaded {module_name} from bundled modules")
        return module
    except ImportError:
        logger.error(f"Module {module_name} not found in bundle and could not be loaded dynamically")
        return None

def download_module_file(file_name: str) -> Optional[Path]:
    """
    Download a module file from Firebase Storage.

    Args:
        file_name: Name of the file to download (e.g., 'login_service.py')

    Returns:
        Path to downloaded file, or None if download failed
    """
    try:
        from services.firebase_service import (
            get_available_files,
            install_file,
            get_installer_id,
            is_authenticated,
        )
        from services.file_registry import is_file_installed, get_file_info

        import os
        if not os.getenv("FIREBASE_API_KEY"):
            logger.warning("Firebase not configured. Cannot download files.")
            return None

        if not is_authenticated():
            logger.error("Not authenticated. Please sign in to download files.")
            return None

        if is_file_installed(file_name):
            file_info = get_file_info(file_name)
            logger.info(f"File {file_name} is already installed (version: {file_info.get('version', 'unknown')})")

            if is_frozen():
                installed_path = get_browser_automation_dir() / file_name
            else:
                installed_path = get_project_root() / "services" / "browser_automation" / file_name

            if installed_path.exists():
                return installed_path

        available_files = get_available_files()
        file_metadata = None

        for file_info in available_files:
            if file_info.get("name") == file_name:
                file_metadata = file_info
                break

        if not file_metadata:
            logger.warning(f"File {file_name} not found in available files")
            return None

        installer_id = get_installer_id()
        success, error_msg = install_file(
            file_name,
            file_metadata.get("version", "1.0.0"),
            file_metadata.get("checksum", ""),
            installer_id
        )

        if success:

            if is_frozen():
                installed_path = get_browser_automation_dir() / file_name
            else:
                installed_path = get_project_root() / "services" / "browser_automation" / file_name

            if installed_path.exists():
                return installed_path

        return None

    except ImportError as e:
        logger.error(f"Firebase service not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to download file {file_name}: {e}")
        return None

def ensure_module_available(module_name: str, file_name: str) -> bool:
    """
    Ensure a module is available, downloading if necessary.

    Args:
        module_name: Full module name
        file_name: Name of the Python file

    Returns:
        True if module is available, False otherwise
    """
    module = load_module_dynamically(module_name, file_name)
    return module is not None

def load_login_service():
    """Load login_service module dynamically."""
    return load_module_dynamically(
        "services.browser_automation.login_service",
        "login_service.py"
    )

def load_portfolio_service():
    """Load portfolio_service module dynamically."""
    return load_module_dynamically(
        "services.browser_automation.portfolio_service",
        "portfolio_service.py"
    )

def load_profile_service():
    """Load profile_service module dynamically."""
    return load_module_dynamically(
        "services.browser_automation.profile_service",
        "profile_service.py"
    )
