"""Agent code service for fetching and managing dynamic agent code with installer restrictions."""
import json
import logging
import os
import tempfile
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import httpx

from services.firebase_service import (
    get_firestore_db,
    get_firebase_storage,
    load_auth_tokens,
    is_authenticated,
)
from services.path_utils import get_dynamic_agents_dir, is_frozen
from services.file_registry import (
    calculate_file_checksum,
    verify_file_checksum,
    get_installer_id,
)

logger = logging.getLogger(__name__)

AGENT_CACHE_REGISTRY = "agent_cache_registry.json"

def get_agent_cache_registry_path() -> Path:
    """Get path to agent cache registry file."""
    from services.path_utils import get_app_data_dir
    return get_app_data_dir() / AGENT_CACHE_REGISTRY

def load_agent_cache_registry() -> Dict[str, Any]:
    """Load agent cache registry from disk."""
    registry_path = get_agent_cache_registry_path()

    if not registry_path.exists():
        return {"agents": {}}

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load agent cache registry: {e}")
        return {"agents": {}}

def save_agent_cache_registry(registry: Dict[str, Any]) -> bool:
    """Save agent cache registry to disk."""
    registry_path = get_agent_cache_registry_path()

    try:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Failed to save agent cache registry: {e}")
        return False

def get_available_agents(installer_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get list of agents available to the installer.

    Args:
        installer_id: Installer ID (if None, uses registry)

    Returns:
        List of available agent metadata
    """
    try:
        db = get_firestore_db()
        if not db:
            logger.debug("Firestore not available. Agent listing requires Admin SDK.")
            return []

        if not installer_id:
            installer_id = get_installer_id()

        if not installer_id:
            logger.warning("No installer ID available")
            return []

        installer_ref = db.collection("installers").document(installer_id)
        installer_doc = installer_ref.get()

        if not installer_doc.exists:
            logger.warning(f"Installer {installer_id} not found in Firestore")
            return []

        installer_data = installer_doc.to_dict()
        available_agents = installer_data.get("available_agents", [])

        agents_list = []
        for agent_info in available_agents:
            agent_name = agent_info.get("name") if isinstance(agent_info, dict) else agent_info
            agent_ref = db.collection("dynamic_agents").document(agent_name)
            agent_doc = agent_ref.get()

            if agent_doc.exists:
                agent_data = agent_doc.to_dict()
                agents_list.append({
                    "name": agent_name,
                    "version": agent_data.get("version", "1.0.0"),
                    "description": agent_data.get("description", ""),
                    "checksum": agent_data.get("checksum", ""),
                })

        return agents_list

    except Exception as e:
        logger.error(f"Failed to get available agents: {e}")
        return []

def is_agent_available(agent_name: str, installer_id: Optional[str] = None) -> bool:
    """
    Check if installer has access to the specified agent.

    Args:
        agent_name: Name of the agent
        installer_id: Installer ID (if None, uses registry)

    Returns:
        True if agent is available, False otherwise
    """
    try:
        available_agents = get_available_agents(installer_id)
        return any(agent.get("name") == agent_name for agent in available_agents)
    except Exception as e:
        logger.error(f"Failed to check agent availability: {e}")
        return False

def get_cached_version(agent_name: str) -> Optional[str]:
    """
    Get version of cached agent code.

    Args:
        agent_name: Name of the agent

    Returns:
        Version string, or None if not cached
    """
    registry = load_agent_cache_registry()
    agent_info = registry.get("agents", {}).get(agent_name)
    if agent_info:
        return agent_info.get("version")
    return None

def get_cached_agent_path(agent_name: str, version: Optional[str] = None) -> Optional[Path]:
    """
    Get path to cached agent code.

    Args:
        agent_name: Name of the agent
        version: Optional version (if None, uses latest cached version)

    Returns:
        Path to cached agent file, or None if not found
    """
    registry = load_agent_cache_registry()
    agent_info = registry.get("agents", {}).get(agent_name)

    if not agent_info:
        return None

    if version and agent_info.get("version") != version:
        return None

    cached_version = agent_info.get("version")
    if not cached_version:
        return None

    cache_dir = get_dynamic_agents_dir()
    cache_file = cache_dir / f"{agent_name}_{cached_version}.py"

    if cache_file.exists():
        return cache_file

    return None

def cache_agent_code(agent_name: str, code: str, version: str, checksum: str) -> Optional[Path]:
    """
    Save agent code to local cache.

    Args:
        agent_name: Name of the agent
        code: Agent code content
        version: Version of the agent
        checksum: Checksum of the code

    Returns:
        Path to cached file, or None if failed
    """
    try:
        cache_dir = get_dynamic_agents_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_file = cache_dir / f"{agent_name}_{version}.py"

        cache_file.write_text(code, encoding="utf-8")

        if not verify_file_checksum(cache_file, checksum):
            logger.error(f"Checksum verification failed for cached agent {agent_name}")
            cache_file.unlink()
            return None

        registry = load_agent_cache_registry()
        if "agents" not in registry:
            registry["agents"] = {}

        registry["agents"][agent_name] = {
            "version": version,
            "checksum": checksum,
            "cached_at": datetime.utcnow().isoformat(),
        }

        save_agent_cache_registry(registry)

        logger.info(f"Cached agent {agent_name} v{version} to {cache_file}")
        return cache_file

    except Exception as e:
        logger.error(f"Failed to cache agent code: {e}")
        return None

def load_cached_agent(agent_name: str, version: Optional[str] = None) -> Optional[Path]:
    """
    Load cached agent code.

    Args:
        agent_name: Name of the agent
        version: Optional version (if None, uses latest cached)

    Returns:
        Path to cached agent file, or None if not found
    """
    return get_cached_agent_path(agent_name, version)

def download_agent_code(agent_name: str, installer_id: Optional[str] = None) -> Optional[str]:
    """
    Download agent code from Firebase Storage.

    Args:
        agent_name: Name of the agent
        installer_id: Installer ID (for validation, not used in storage path)

    Returns:
        Agent code content as string, or None if failed
    """
    try:
        storage_client = get_firebase_storage()
        if not storage_client:
            logger.debug("Firebase storage not available. Agent download requires Admin SDK.")
            return None

        if not is_agent_available(agent_name, installer_id):
            logger.warning(f"Agent {agent_name} is not available to installer {installer_id}")
            return None

        storage_path = f"agents/{agent_name}.py"

        temp_dir = Path(tempfile.gettempdir()) / "voice-agent-downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f"{agent_name}.py"

        logger.info(f"Downloading {agent_name} from Firebase Storage...")

        token_data = load_auth_tokens()
        auth_token = token_data.get("id_token") if token_data else None

        storage_bucket = os.getenv("FIREBASE_STORAGE_BUCKET", "")
        if not storage_bucket:
            logger.error("FIREBASE_STORAGE_BUCKET not configured")
            return None

        encoded_path = urllib.parse.quote(storage_path, safe='')
        download_url = f"https://firebasestorage.googleapis.com/v0/b/{storage_bucket}/o/{encoded_path}?alt=media"
        if auth_token:
            download_url += f"&token={auth_token}"

        try:
            with httpx.stream("GET", download_url, timeout=30.0) as response:
                response.raise_for_status()
                with open(temp_file, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
        except Exception as download_err:
            logger.error(f"Failed to download agent code: {download_err}")
            return None

        if temp_file.exists():

            code_content = temp_file.read_text(encoding="utf-8")
            temp_file.unlink()
            logger.info(f"Downloaded {agent_name} successfully")
            return code_content
        else:
            logger.error(f"Downloaded file not found: {temp_file}")
            return None

    except Exception as e:
        logger.error(f"Failed to download agent code {agent_name}: {e}")
        return None

def fetch_agent_code(agent_name: str, installer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetch agent code from Firestore with installer validation.

    Args:
        agent_name: Name of the agent
        installer_id: Installer ID (if None, uses registry)

    Returns:
        Dictionary with agent metadata and code, or None if failed
        Format: {"code": str, "version": str, "checksum": str, "description": str}
    """
    try:
        db = get_firestore_db()
        if not db:
            logger.debug("Firestore not available. Agent fetch requires Admin SDK.")
            return None

        if not installer_id:
            installer_id = get_installer_id()

        if not installer_id:
            logger.warning("No installer ID available")
            return None

        if not is_agent_available(agent_name, installer_id):
            logger.warning(f"Agent {agent_name} is not available to installer {installer_id}")
            return None

        agent_ref = db.collection("dynamic_agents").document(agent_name)
        agent_doc = agent_ref.get()

        if not agent_doc.exists:
            logger.warning(f"Agent {agent_name} not found in Firestore")
            return None

        agent_data = agent_doc.to_dict()

        code = agent_data.get("code")
        if not code:

            logger.info(f"Code not in Firestore document, downloading from Storage...")
            code = download_agent_code(agent_name, installer_id)
            if not code:
                logger.error(f"Failed to download agent code from Storage")
                return None

        return {
            "code": code,
            "version": agent_data.get("version", "1.0.0"),
            "checksum": agent_data.get("checksum", ""),
            "description": agent_data.get("description", ""),
        }

    except Exception as e:
        logger.error(f"Failed to fetch agent code: {e}")
        return None

def ensure_agent_code_ready(agent_name: str, installer_id: Optional[str] = None) -> Optional[Path]:
    """
    Ensure agent code is ready (cached or fetched).

    Args:
        agent_name: Name of the agent
        installer_id: Installer ID (if None, uses registry)

    Returns:
        Path to agent code file (cached or newly fetched), or None if failed
    """
    try:

        cached_path = load_cached_agent(agent_name)
        if cached_path:
            logger.info(f"Using cached agent {agent_name} from {cached_path}")
            return cached_path

        if not is_authenticated():
            logger.warning("Not authenticated. Cannot fetch agent code.")
            return None

        logger.info(f"Fetching agent {agent_name} from Firestore...")
        agent_data = fetch_agent_code(agent_name, installer_id)

        if not agent_data:
            logger.error(f"Failed to fetch agent {agent_name}")
            return None

        cached_path = cache_agent_code(
            agent_name,
            agent_data["code"],
            agent_data["version"],
            agent_data["checksum"]
        )

        if cached_path:
            logger.info(f"Successfully fetched and cached agent {agent_name} v{agent_data['version']}")
            return cached_path
        else:
            logger.error(f"Failed to cache agent {agent_name}")
            return None

    except Exception as e:
        logger.error(f"Failed to ensure agent code ready: {e}")
        return None
