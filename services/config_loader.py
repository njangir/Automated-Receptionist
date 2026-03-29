"""Configuration loader for secrets and user config."""
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from services.path_utils import (
    get_config_dir,
    get_bundled_secrets_path,
    is_frozen,
    get_project_root,
)

logger = logging.getLogger(__name__)

def load_config(root_dir: Optional[Path] = None) -> None:
    """
    Load environment variables from .env.secrets and .env.config files.

    Loads secrets first (bundled, protected), then user config (editable).
    User config can override defaults but not secrets.

    In PyInstaller mode:
    - .env.secrets is loaded from bundle (_MEIPASS)
    - .env.config is loaded from app data directory
    - .env.temp is loaded from app data directory

    In development mode:
    - All files are loaded from project root

    Args:
        root_dir: Root directory to search for config files. If None, uses current directory.
                  In frozen mode, this is ignored and app data directory is used for config.
    """

    if is_frozen():

        config_dir = get_config_dir()

        secrets_file = get_bundled_secrets_path()
        if secrets_file and secrets_file.exists():
            load_dotenv(str(secrets_file), override=False)
            logger.info(f"Loaded secrets from bundle: {secrets_file}")
        else:
            logger.warning("Secrets file not found in bundle")
            logger.warning("Application may not work correctly without secrets configured.")

        config_file = config_dir / ".env.config"
        if config_file.exists():
            load_dotenv(str(config_file), override=True)
            logger.info(f"Loaded user config from: {config_file}")
        else:
            logger.info(f"User config file not found: {config_file}")
            logger.info("Using default configuration values.")

        temp_file = config_dir / ".env.temp"
        if temp_file.exists():
            load_dotenv(str(temp_file), override=True)
            logger.debug(f"Loaded runtime variables from: {temp_file}")
    else:

        if root_dir is None:
            root_dir = Path.cwd()
        else:
            root_dir = Path(root_dir).resolve()

        secrets_file = root_dir / ".env.secrets"
        if secrets_file.exists():
            load_dotenv(str(secrets_file), override=False)
            logger.info(f"Loaded secrets from: {secrets_file}")
        else:
            logger.warning(f"Secrets file not found: {secrets_file}")
            logger.warning("Application may not work correctly without secrets configured.")

        config_file = root_dir / ".env.config"
        if config_file.exists():
            load_dotenv(str(config_file), override=True)
            logger.info(f"Loaded user config from: {config_file}")
        else:
            logger.info(f"User config file not found: {config_file}")
            logger.info("Using default configuration values.")

        temp_file = root_dir / ".env.temp"
        if temp_file.exists():
            load_dotenv(str(temp_file), override=True)
            logger.debug(f"Loaded runtime variables from: {temp_file}")

def create_config_from_template(config_file: Path, template_file: Optional[Path] = None) -> bool:
    """
    Create .env.config from template if it doesn't exist.

    Args:
        config_file: Path to .env.config file to create
        template_file: Path to template file. If None, uses env.config.example

    Returns:
        True if file was created, False otherwise
    """
    if config_file.exists():
        return False

    if template_file is None:
        template_file = config_file.parent / "env.config.example"

    if not template_file.exists():
        logger.warning(f"Template file not found: {template_file}")
        return False

    try:

        import shutil
        shutil.copy(template_file, config_file)
        logger.info(f"Created config file from template: {config_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to create config file: {e}")
        return False

def get_config_path(root_dir: Optional[Path] = None) -> dict:
    """
    Get paths to config files.

    In PyInstaller mode, returns paths to app data directory for config files.
    In development mode, returns paths relative to project root.

    Args:
        root_dir: Root directory. If None, uses current directory (dev mode) or app data (frozen).

    Returns:
        Dictionary with paths to secrets, config, and local files
    """
    if is_frozen():
        config_dir = get_config_dir()
        secrets_file = get_bundled_secrets_path()
        return {
            "root": config_dir,
            "secrets": secrets_file or Path(),
            "config": config_dir / ".env.config",
            "local": config_dir / ".env.local",
            "temp": config_dir / ".env.temp",
        }
    else:
        if root_dir is None:
            root_dir = Path.cwd()
        else:
            root_dir = Path(root_dir).resolve()

        return {
            "root": root_dir,
            "secrets": root_dir / ".env.secrets",
            "config": root_dir / ".env.config",
            "local": root_dir / ".env.local",
            "temp": root_dir / ".env.temp",
        }
