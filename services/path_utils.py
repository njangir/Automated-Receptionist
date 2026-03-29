"""Path utilities for handling platform-specific directories and PyInstaller compatibility."""
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def is_frozen() -> bool:
    """
    Check if running from PyInstaller bundle.

    Returns:
        True if running from PyInstaller, False otherwise
    """
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

def get_app_data_dir() -> Path:
    """
    Get platform-specific application data directory.

    Returns:
        Path to app data directory:
        - macOS/Linux: ~/.config/voice-agent-server/
        - Windows: %APPDATA%/voice-agent-server/
    """
    system = os.name

    if system == "nt":
        appdata = os.getenv("APPDATA", "")
        if appdata:
            app_data_dir = Path(appdata) / "voice-agent-server"
        else:

            app_data_dir = Path.home() / "AppData" / "Roaming" / "voice-agent-server"
    else:
        app_data_dir = Path.home() / ".config" / "voice-agent-server"

    app_data_dir.mkdir(parents=True, exist_ok=True)

    return app_data_dir

def get_config_dir() -> Path:
    """
    Get directory for configuration files.

    Returns:
        Path to config directory (app data dir when frozen, project root in dev)
    """
    if is_frozen():
        return get_app_data_dir()
    else:

        return Path(__file__).parent.parent.resolve()

def get_browser_automation_dir() -> Path:
    """
    Get directory for dynamically loaded browser automation files.

    Returns:
        Path to browser_automation directory in app data when frozen,
        or project services/browser_automation in dev
    """
    if is_frozen():
        return get_app_data_dir() / "browser_automation"
    else:
        return Path(__file__).parent / "browser_automation"

def get_dynamic_agents_dir() -> Path:
    """
    Get directory for dynamically loaded agent code.

    Returns:
        Path to dynamic_agents directory in app data when frozen,
        or project dynamic_agents in dev
    """
    if is_frozen():
        return get_app_data_dir() / "dynamic_agents"
    else:
        return get_project_root() / "dynamic_agents"

def get_project_root() -> Path:
    """
    Get project root directory.

    In frozen mode, returns the directory containing the executable.
    In development mode, returns the project root.

    Returns:
        Path to project root
    """
    if is_frozen():

        if hasattr(sys, "_MEIPASS"):

            return Path(sys.executable).parent.resolve()
        else:
            return Path(sys.executable).parent.resolve()
    else:
        return Path(__file__).parent.parent.resolve()

def get_bundled_secrets_path() -> Optional[Path]:
    """
    Get path to bundled .env.secrets file (only in frozen mode).

    Returns:
        Path to bundled secrets file, or None if not found
    """
    if is_frozen():

        secrets_path = Path(sys._MEIPASS) / ".env.secrets"
        if secrets_path.exists():
            return secrets_path
    return None
