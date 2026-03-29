"""Configuration service for reading and writing .env.config files."""
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.path_utils import get_config_dir, get_project_root, is_frozen

logger = logging.getLogger(__name__)

def read_config(config_file: Path) -> Dict[str, str]:
    """
    Read configuration from .env.config file.

    Args:
        config_file: Path to .env.config file

    Returns:
        Dictionary of config key-value pairs (empty strings for unset values)
    """
    config = {}

    if not config_file.exists():
        logger.info(f"Config file not found: {config_file}, returning empty config")
        return config

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    config[key] = value
                else:
                    logger.warning(f"Invalid line {line_num} in {config_file}: {line}")

    except Exception as e:
        logger.error(f"Error reading config file {config_file}: {e}")
        raise

    return config

def write_config(config_file: Path, config: Dict[str, str], template_file: Optional[Path] = None) -> bool:
    """
    Write configuration to .env.config file, preserving comments and structure.

    Args:
        config_file: Path to .env.config file
        config: Dictionary of config key-value pairs
        template_file: Optional template file to preserve structure from

    Returns:
        True if successful, False otherwise
    """
    try:

        if template_file and template_file.exists():
            lines = []
            with open(template_file, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()

                    if not stripped or stripped.startswith("#"):
                        lines.append(line.rstrip())
                        continue

                    if "=" in stripped:
                        key = stripped.split("=", 1)[0].strip()
                        if key in config:
                            value = config[key]
                            lines.append(f"{key}={value}")

                            del config[key]
                        else:

                            lines.append(line.rstrip())

            if config:
                lines.append("")
                lines.append("# Additional configuration")
                for key, value in sorted(config.items()):
                    lines.append(f"{key}={value}")

            content = "\n".join(lines) + "\n"
        else:

            lines = []
            lines.append("# User Configuration")
            lines.append("# This file is auto-generated. Edit values as needed.")
            lines.append("")

            for key, value in sorted(config.items()):
                lines.append(f"{key}={value}")

            content = "\n".join(lines) + "\n"

        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Successfully wrote config to {config_file}")
        return True

    except Exception as e:
        logger.error(f"Error writing config file {config_file}: {e}")
        return False

def validate_config(config: Dict[str, str]) -> Dict[str, Any]:
    """
    Validate configuration values.

    Args:
        config: Dictionary of config key-value pairs

    Returns:
        Dictionary with 'valid' (bool) and 'errors' (list of error messages)
    """
    errors = []

    port_keys = ["SERVER_PORT", "AGENT_MANAGER_PORT", "CHROME_DEBUG_PORT"]
    for key in port_keys:
        if key in config and config[key]:
            try:
                port = int(config[key])
                if port < 1 or port > 65535:
                    errors.append(f"{key} must be between 1 and 65535")
            except ValueError:
                errors.append(f"{key} must be a valid integer")

    numeric_keys = [
        "AGENT_START_DELAY", "AGENT_STOP_TIMEOUT", "AGENT_STOP_POLL_INTERVAL",
        "AGENT_PROCESS_WAIT_TIMEOUT", "LOGIN_TYPE", "LOG_MAX_SIZE_MB"
    ]
    for key in numeric_keys:
        if key in config and config[key]:
            try:
                float(config[key])
            except ValueError:
                errors.append(f"{key} must be a valid number")

    boolean_keys = [
        "CHROME_AUTO_START", "CHROME_CLEANUP_ON_EXIT", "CHROME_REMOVE_USER_DATA",
        "FIREBASE_ANONYMOUS_AUTH", "FIREBASE_AUTH_ENABLED"
    ]
    for key in boolean_keys:
        if key in config and config[key]:
            value = config[key].lower()
            if value not in ["true", "false", "1", "0", "yes", "no", ""]:
                errors.append(f"{key} must be 'true' or 'false'")

    path_keys = ["PID_FILE_PATH", "CHROME_USER_DATA_DIR", "CHROME_EXECUTABLE_PATH", "AGENT_PROJECT_ROOT", "GOOGLE_SERVICE_ACCOUNT_PATH", "FIREBASE_SERVICE_ACCOUNT_KEY"]
    for key in path_keys:
        if key in config and config[key]:
            path_str = config[key].strip()
            if path_str:

                if not os.path.isabs(path_str) and "/" not in path_str and "\\" not in path_str:

                    pass

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }

def get_config_schema() -> List[Dict[str, Any]]:
    """
    Get configuration schema with field definitions.

    Returns:
        List of field definitions with name, type, default, description, category
    """
    return [

        {
            "name": "LOCAL_IP",
            "type": "string",
            "default": "",
            "description": "Local IP address of this machine (read-only, informational)",
            "category": "Server",
            "required": False,
            "readonly": True
        },
        {
            "name": "SERVER_HOST",
            "type": "string",
            "default": "0.0.0.0",
            "description": "Server host address (0.0.0.0 = all interfaces, 127.0.0.1 = localhost only)",
            "category": "Server",
            "required": False
        },
        {
            "name": "SERVER_PORT",
            "type": "integer",
            "default": "8000",
            "description": "Server port number (1-65535)",
            "category": "Server",
            "required": False,
            "validation": {"min": 1, "max": 65535}
        },
        {
            "name": "CORS_ORIGINS",
            "type": "string",
            "default": "*",
            "description": "Comma-separated list of allowed CORS origins, or '*' for all",
            "category": "Server",
            "required": False
        },
        {
            "name": "LOG_MAX_SIZE_MB",
            "type": "integer",
            "default": "500",
            "description": "Maximum total log size in MB. Logs will be cleaned up on startup if this limit is exceeded (oldest files deleted first)",
            "category": "Server",
            "required": False,
            "validation": {"min": 1, "max": 10000}
        },

        {
            "name": "PID_FILE_PATH",
            "type": "path",
            "default": "/tmp/agent.pid",
            "description": "PID file path (leave empty for system temp directory)",
            "category": "Process Management",
            "required": False
        },
        {
            "name": "AGENT_START_DELAY",
            "type": "float",
            "default": "1.0",
            "description": "Seconds to wait after starting agent process",
            "category": "Process Management",
            "required": False
        },
        {
            "name": "AGENT_STOP_TIMEOUT",
            "type": "integer",
            "default": "30",
            "description": "Timeout in seconds for graceful agent shutdown",
            "category": "Process Management",
            "required": False
        },
        {
            "name": "AGENT_STOP_POLL_INTERVAL",
            "type": "float",
            "default": "0.5",
            "description": "Interval in seconds for polling agent status during shutdown",
            "category": "Process Management",
            "required": False
        },
        {
            "name": "AGENT_PROCESS_WAIT_TIMEOUT",
            "type": "integer",
            "default": "5",
            "description": "Timeout in seconds for waiting for process to terminate",
            "category": "Process Management",
            "required": False
        },
        {
            "name": "LIVE_TRANSCRIPT_POLL_INTERVAL",
            "type": "integer",
            "default": "2000",
            "description": "Interval in milliseconds for polling live transcriptions (default: 2000ms = 2 seconds)",
            "category": "Process Management",
            "required": False,
            "validation": {"min": 500, "max": 10000}
        },
        {
            "name": "LIVE_TRANSCRIPT_AUTO_CLOSE_DELAY",
            "type": "integer",
            "default": "5000",
            "description": "Delay in milliseconds before auto-closing transcript dialog after call ends (default: 5000ms = 5 seconds)",
            "category": "Process Management",
            "required": False,
            "validation": {"min": 1000, "max": 60000}
        },

        {
            "name": "AGENT_PROJECT_ROOT",
            "type": "path",
            "default": "",
            "description": "Path to agent project root directory (leave empty for current directory)",
            "category": "Agent Paths",
            "required": False
        },
        {
            "name": "AGENT_ENTRYPOINT",
            "type": "string",
            "default": "myagent.py",
            "description": "Agent entrypoint filename (in agents/ directory)",
            "category": "Agent Paths",
            "required": False
        },
        {
            "name": "AGENT_LOG_DIR",
            "type": "string",
            "default": "logs",
            "description": "Agent log directory name (relative to agent project root)",
            "category": "Agent Paths",
            "required": False
        },
        {
            "name": "AGENT_TYPE",
            "type": "string",
            "default": "bundled",
            "description": "Agent type: 'bundled' for myagent.py, 'online' for dynamic agent from Firestore",
            "category": "Agent Paths",
            "required": False
        },

        {
            "name": "GOOGLE_SHEET_ID",
            "type": "string",
            "default": "1cqNMzjOCGrbTGqsi08FKZNW1IuClDKa3zPz2jfWRLVs",
            "description": "Google Sheets ID (from spreadsheet URL)",
            "category": "Google Sheets",
            "required": False
        },
        {
            "name": "GOOGLE_SHEET_NAME",
            "type": "string",
            "default": "0",
            "description": "Sheet name or range (e.g., '0' for first sheet, 'Sheet1')",
            "category": "Google Sheets",
            "required": False
        },
        {
            "name": "GOOGLE_SHEET_PHONE_COLUMN",
            "type": "string",
            "default": "phone",
            "description": "Column name for phone numbers",
            "category": "Google Sheets",
            "required": False
        },
        {
            "name": "GOOGLE_SHEET_ACCOUNT_CODE_COLUMN",
            "type": "string",
            "default": "Account Code",
            "description": "Column name for account codes",
            "category": "Google Sheets",
            "required": False
        },
        {
            "name": "GOOGLE_SHEET_ACCOUNT_NAME_COLUMN",
            "type": "string",
            "default": "Account Name",
            "description": "Column name for account names",
            "category": "Google Sheets",
            "required": False
        },
        {
            "name": "GOOGLE_SERVICE_ACCOUNT_PATH",
            "type": "path",
            "default": "/myagentagent-c481e1f52584.json",
            "description": "Path to Google Service Account JSON file (absolute or relative to project root). This file contains sensitive credentials - keep it secure!",
            "category": "Google Sheets",
            "required": False
        },

        {
            "name": "CHROME_DEBUG_PORT",
            "type": "integer",
            "default": "9222",
            "description": "Chrome remote debugging port",
            "category": "Chrome Launcher",
            "required": False,
            "validation": {"min": 1, "max": 65535}
        },
        {
            "name": "CHROME_USER_DATA_DIR",
            "type": "path",
            "default": "/tmp/chrome-playwright-clean",
            "description": "Chrome user data directory (leave empty for system temp directory)",
            "category": "Chrome Launcher",
            "required": False
        },
        {
            "name": "CHROME_EXECUTABLE_PATH",
            "type": "path",
            "default": "",
            "description": "Chrome executable path (leave empty for auto-detection)",
            "category": "Chrome Launcher",
            "required": False
        },
        {
            "name": "CHROME_AUTO_START",
            "type": "boolean",
            "default": "true",
            "description": "Auto-start Chrome when browser service connects",
            "category": "Chrome Launcher",
            "required": False
        },
        {
            "name": "CHROME_CLEANUP_ON_EXIT",
            "type": "boolean",
            "default": "false",
            "description": "Cleanup Chrome on application exit",
            "category": "Chrome Launcher",
            "required": False
        },
        {
            "name": "CHROME_REMOVE_USER_DATA",
            "type": "boolean",
            "default": "false",
            "description": "Remove Chrome user data directory on cleanup",
            "category": "Chrome Launcher",
            "required": False
        },

        {
            "name": "LOGIN_URL",
            "type": "string",
            "default": "https://backoffice/Login.aspx",
            "description": "Login URL for backoffice system",
            "category": "Browser Automation",
            "required": False
        },
        {
            "name": "LOGIN_TYPE",
            "type": "integer",
            "default": "15",
            "description": "Login type option value for backoffice system",
            "category": "Browser Automation",
            "required": False
        },

        {
            "name": "DEFAULT_AGENT_USE_CASE",
            "type": "string",
            "default": "myagent",
            "description": "Default agent use case when starting from webhook",
            "category": "Agent Configuration",
            "required": False
        },
        {
            "name": "END_CALL_WEBHOOK",
            "type": "string",
            "default": "http://localhost:5678/webhook/dd4b17ac-f49d-4971-a374-09a5fc3bb3aa",
            "description": "Webhook URL to call when a call ends (for n8n or other integrations)",
            "category": "Agent Configuration",
            "required": False
        },

        {
            "name": "AUDIO_INPUT_DEVICE_ID",
            "type": "select",
            "default": "",
            "description": "Audio input device name for console mode (leave empty for system default). Select from available devices in dropdown.",
            "category": "Audio Configuration",
            "required": False,
            "options_url": "/api/audio-devices",
            "options_key": "input_devices",
            "options_label": "name",
            "options_value": "name"
        },
        {
            "name": "AUDIO_OUTPUT_DEVICE_ID",
            "type": "select",
            "default": "",
            "description": "Audio output device name for console mode (leave empty for system default). Select from available devices in dropdown.",
            "category": "Audio Configuration",
            "required": False,
            "options_url": "/api/audio-devices",
            "options_key": "output_devices",
            "options_label": "name",
            "options_value": "name"
        },

        {
            "name": "PERFORMANCE_PROFILE",
            "type": "select",
            "default": "low",
            "description": "Performance profile: 'low' for low-end PCs (reduces CPU/memory), 'balanced' for normal use, 'high' for best quality",
            "category": "Performance",
            "required": False,
            "options": [
                {"label": "Low (Optimized for low-end PCs)", "value": "low"},
                {"label": "Balanced (Default)", "value": "balanced"},
                {"label": "High (Best quality)", "value": "high"}
            ]
        },
        {
            "name": "STT_MODEL",
            "type": "string",
            "default": "",
            "description": "Override STT model (e.g., 'nova-2', 'nova-3'). Leave empty to use profile default.",
            "category": "Performance",
            "required": False
        },
        {
            "name": "LLM_MAX_TOKENS",
            "type": "integer",
            "default": "",
            "description": "Override maximum LLM response tokens. Leave empty to use profile default (low: 100, balanced: 150, high: 200).",
            "category": "Performance",
            "required": False,
            "validation": {"min": 50, "max": 500}
        },
        {
            "name": "PREEMPTIVE_GENERATION",
            "type": "boolean",
            "default": "false",
            "description": "Override preemptive generation (true/false). Leave empty to use profile default.",
            "category": "Performance",
            "required": False
        },
        {
            "name": "NOISE_CANCELLATION_ENABLED",
            "type": "boolean",
            "default": "false",
            "description": "Override noise cancellation (true/false). Leave empty to use profile default.",
            "category": "Performance",
            "required": False
        },
        {
            "name": "TURN_DETECTION_ENABLED",
            "type": "boolean",
            "default": "false",
            "description": "Override turn detection (true/false). Leave empty to use profile default. Requires model files to be downloaded.",
            "category": "Performance",
            "required": False
        },

        {
            "name": "FIREBASE_API_KEY",
            "type": "string",
            "default": "AIzaSyAElpxxx",
            "description": "Firebase API key for client-side authentication",
            "category": "Firebase",
            "required": False
        },
        {
            "name": "FIREBASE_PROJECT_ID",
            "type": "string",
            "default": "voiceagents-xxx",
            "description": "Firebase project ID",
            "category": "Firebase",
            "required": False
        },
        {
            "name": "FIREBASE_STORAGE_BUCKET",
            "type": "string",
            "default": "voiceagents-xxx.firebasestorage.app",
            "description": "Firebase storage bucket name (e.g., project-id.firebasestorage.app)",
            "category": "Firebase",
            "required": False
        },
        {
            "name": "FIREBASE_SERVICE_ACCOUNT_KEY",
            "type": "path",
            "default": "/voiceagents-xxx-firebase-adminsdk-fbsvc-d56aec115c.json",
            "description": "Path to Firebase service account JSON key file (absolute or relative to project root)",
            "category": "Firebase",
            "required": False
        },
        {
            "name": "FIREBASE_ANONYMOUS_AUTH",
            "type": "boolean",
            "default": "true",
            "description": "Enable anonymous authentication for Firebase",
            "category": "Firebase",
            "required": False
        },
        {
            "name": "FIREBASE_AUTH_ENABLED",
            "type": "boolean",
            "default": "true",
            "description": "Enable Firebase authentication features",
            "category": "Firebase",
            "required": False
        },
        {
            "name": "FIREBASE_MESSAGING_SENDER_ID",
            "type": "string",
            "default": "xxx",
            "description": "Firebase messaging sender ID (also called App ID for web apps). Found in Firebase Console > Project Settings > Your apps > Web app config",
            "category": "Firebase",
            "required": False
        },
        {
            "name": "FIREBASE_APP_ID",
            "type": "string",
            "default": "1:xxx:web:xxx",
            "description": "Firebase App ID (optional, for some Firebase services). Format: 1:PROJECT_NUMBER:web:APP_ID",
            "category": "Firebase",
            "required": False
        },
    ]

def get_config_by_category() -> Dict[str, List[Dict[str, Any]]]:
    """
    Get configuration schema grouped by category.

    Returns:
        Dictionary mapping category names to lists of field definitions
    """
    schema = get_config_schema()
    categorized = {}

    for field in schema:
        category = field.get("category", "Other")
        if category not in categorized:
            categorized[category] = []
        categorized[category].append(field)

    return categorized
