"""File registry management for tracking installed files."""
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from services.path_utils import get_app_data_dir

logger = logging.getLogger(__name__)

REGISTRY_FILE = "files_registry.json"

def get_registry_path() -> Path:
    """Get path to file registry."""
    return get_app_data_dir() / REGISTRY_FILE

def load_registry() -> Dict:
    """
    Load file registry from disk.

    Returns:
        Dictionary containing registry data
    """
    registry_path = get_registry_path()

    if not registry_path.exists():
        return {
            "installed_files": {},
            "installer_id": None,
            "firebase_user_id": None,
            "last_check": None,
            "version": "1.0"
        }

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)

        if "installed_files" not in registry:
            registry["installed_files"] = {}
        if "installer_id" not in registry:
            registry["installer_id"] = None
        if "firebase_user_id" not in registry:
            registry["firebase_user_id"] = None
        if "last_check" not in registry:
            registry["last_check"] = None

        return registry
    except Exception as e:
        logger.error(f"Failed to load registry: {e}")
        return {
            "installed_files": {},
            "installer_id": None,
            "firebase_user_id": None,
            "last_check": None,
            "version": "1.0"
        }

def save_registry(registry: Dict) -> bool:
    """
    Save file registry to disk.

    Args:
        registry: Registry dictionary to save

    Returns:
        True if successful, False otherwise
    """
    registry_path = get_registry_path()

    try:

        registry_path.parent.mkdir(parents=True, exist_ok=True)

        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)

        logger.debug(f"Registry saved to {registry_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save registry: {e}")
        return False

def get_installed_files() -> Dict[str, Dict]:
    """
    Get dictionary of installed files.

    Returns:
        Dictionary mapping file names to their metadata
    """
    registry = load_registry()
    return registry.get("installed_files", {})

def register_file(
    file_name: str,
    version: str,
    checksum: str,
    source: str = "remote",
    installer_id: Optional[str] = None
) -> bool:
    """
    Register an installed file in the registry.

    Args:
        file_name: Name of the file
        version: Version of the file
        checksum: SHA256 checksum of the file
        source: Source of the file (e.g., "remote", "local")
        installer_id: Optional installer ID

    Returns:
        True if successful, False otherwise
    """
    registry = load_registry()

    if "installed_files" not in registry:
        registry["installed_files"] = {}

    registry["installed_files"][file_name] = {
        "version": version,
        "installed_date": datetime.utcnow().isoformat(),
        "checksum": checksum,
        "source": source
    }

    if installer_id:
        registry["installer_id"] = installer_id

    return save_registry(registry)

def unregister_file(file_name: str) -> bool:
    """
    Remove a file from the registry.

    Args:
        file_name: Name of the file to remove

    Returns:
        True if successful, False otherwise
    """
    registry = load_registry()

    if "installed_files" in registry and file_name in registry["installed_files"]:
        del registry["installed_files"][file_name]
        return save_registry(registry)

    return True

def get_file_info(file_name: str) -> Optional[Dict]:
    """
    Get information about an installed file.

    Args:
        file_name: Name of the file

    Returns:
        Dictionary with file info, or None if not found
    """
    installed_files = get_installed_files()
    return installed_files.get(file_name)

def is_file_installed(file_name: str) -> bool:
    """
    Check if a file is registered as installed.

    Args:
        file_name: Name of the file

    Returns:
        True if file is installed, False otherwise
    """
    return file_name in get_installed_files()

def calculate_file_checksum(file_path: Path) -> str:
    """
    Calculate SHA256 checksum of a file.

    Args:
        file_path: Path to the file

    Returns:
        SHA256 checksum as hex string
    """
    sha256_hash = hashlib.sha256()

    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate checksum for {file_path}: {e}")
        return ""

def verify_file_checksum(file_path: Path, expected_checksum: str) -> bool:
    """
    Verify file checksum matches expected value.

    Args:
        file_path: Path to the file
        expected_checksum: Expected SHA256 checksum

    Returns:
        True if checksum matches, False otherwise
    """
    if not file_path.exists():
        return False

    actual_checksum = calculate_file_checksum(file_path)
    return actual_checksum == expected_checksum.lower()

def set_installer_id(installer_id: str) -> bool:
    """
    Set installer ID in registry.

    Args:
        installer_id: Installer ID to set

    Returns:
        True if successful, False otherwise
    """
    registry = load_registry()
    registry["installer_id"] = installer_id
    return save_registry(registry)

def get_installer_id() -> Optional[str]:
    """
    Get installer ID from registry.

    Returns:
        Installer ID, or None if not set
    """
    registry = load_registry()
    return registry.get("installer_id")

def set_firebase_user_id(user_id: str) -> bool:
    """
    Set Firebase user ID in registry.

    Args:
        user_id: Firebase user ID to set

    Returns:
        True if successful, False otherwise
    """
    registry = load_registry()
    registry["firebase_user_id"] = user_id
    return save_registry(registry)

def get_firebase_user_id() -> Optional[str]:
    """
    Get Firebase user ID from registry.

    Returns:
        Firebase user ID, or None if not set
    """
    registry = load_registry()
    return registry.get("firebase_user_id")

def update_last_check() -> bool:
    """
    Update last check timestamp in registry.

    Returns:
        True if successful, False otherwise
    """
    registry = load_registry()
    registry["last_check"] = datetime.utcnow().isoformat()
    return save_registry(registry)
