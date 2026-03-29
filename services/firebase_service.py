"""Firebase service for authentication, file storage, and Firestore operations."""
import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

import httpx
from firebase_admin import credentials, initialize_app, storage, firestore, get_app
from firebase_admin.exceptions import FirebaseError

logger = logging.getLogger(__name__)

try:
    import pyrebase
    PYREBASE4_AVAILABLE = True
except ImportError:
    PYREBASE4_AVAILABLE = False

    import sys
    print("WARNING: pyrebase not installed. Firebase authentication features will be unavailable.", file=sys.stderr)
    print("WARNING: Install it with: pip install pyrebase4", file=sys.stderr)

from services.path_utils import get_browser_automation_dir, get_app_data_dir
from services.file_registry import (
    register_file,
    get_installed_files,
    get_installer_id,
    set_installer_id,
    set_firebase_user_id,
    get_firebase_user_id,
    calculate_file_checksum,
    verify_file_checksum,
    update_last_check,
)

_firebase_app = None
_firebase_auth = None
_firebase_db = None
_firebase_storage = None
_pyrebase = None

TOKEN_FILE = "auth_tokens.json"
TOKEN_EXPIRY_DAYS = 7

def initialize_firebase() -> bool:
    """
    Initialize Firebase Admin SDK and Pyrebase.

    Returns:
        True if initialization successful, False otherwise
    """
    global _firebase_app, _firebase_db, _firebase_storage, _pyrebase

    if _firebase_app is not None and _pyrebase is not None:
        return True

    try:

        api_key = os.getenv("FIREBASE_API_KEY")
        project_id = os.getenv("FIREBASE_PROJECT_ID")
        storage_bucket = os.getenv("FIREBASE_STORAGE_BUCKET")
        messaging_sender_id = os.getenv("FIREBASE_MESSAGING_SENDER_ID", "")
        app_id = os.getenv("FIREBASE_APP_ID", "")

        if not all([api_key, project_id, storage_bucket]):
            logger.warning("Firebase configuration incomplete. Some features may be unavailable.")
            return False

        try:

            _firebase_app = get_app()
        except ValueError:

            if _firebase_app is None:

                service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")

                if service_account_path:
                    service_account_path_obj = Path(service_account_path)

                    if not service_account_path_obj.exists():

                        from services.path_utils import get_project_root
                        project_root = get_project_root()

                        if service_account_path.startswith('/'):
                            relative_path = service_account_path.lstrip('/')
                        else:
                            relative_path = service_account_path
                        resolved_path = project_root / relative_path
                        if resolved_path.exists():
                            service_account_path = str(resolved_path)
                        elif not service_account_path_obj.is_absolute():

                            service_account_path = str(project_root / service_account_path)

                if service_account_path and Path(service_account_path).exists():
                    cred = credentials.Certificate(service_account_path)
                    _firebase_app = initialize_app(cred, {
                        "storageBucket": storage_bucket
                    })
                else:

                    try:
                        _firebase_app = initialize_app(options={
                            "storageBucket": storage_bucket
                        })
                    except Exception as e:

                        try:
                            existing_app = get_app()
                            _firebase_app = existing_app
                        except ValueError:

                            pass
                        logger.warning(f"Could not initialize Firebase Admin SDK: {e}")
                        logger.info("Continuing with client-side Firebase only")

        if _firebase_app:
            try:
                _firebase_db = firestore.client()
                _firebase_storage = storage.bucket()
            except Exception as e:

                logger.debug(f"Firestore/Storage clients not available (Admin SDK credentials missing): {type(e).__name__}")
                logger.info("Using client-side Firebase (Pyrebase) only - Admin SDK features unavailable")

                _firebase_app = None

        if _pyrebase is None:
            if not PYREBASE4_AVAILABLE:
                logger.error("pyrebase4 is not installed. Cannot initialize Firebase authentication.")
                logger.error("Please install it with: pip install pyrebase4")
                return False

            firebase_config = {
                "apiKey": api_key,
                "authDomain": f"{project_id}.firebaseapp.com",
                "projectId": project_id,
                "storageBucket": storage_bucket,
                "databaseURL": f"https://{project_id}.firebaseio.com"
            }

            if messaging_sender_id:
                firebase_config["messagingSenderId"] = messaging_sender_id
            if app_id:
                firebase_config["appId"] = app_id

            _pyrebase = pyrebase.initialize_app(firebase_config)

        if _pyrebase is not None:
            logger.info("Firebase initialized successfully (Pyrebase ready)")
            return True
        else:
            logger.error("Failed to initialize Firebase: Pyrebase not available")
            return False

    except Exception as e:

        logger.error(f"Unexpected error during Firebase initialization: {e}")
        return False

def get_token_file_path() -> Path:
    """Get path to token storage file."""
    return get_app_data_dir() / TOKEN_FILE

def save_auth_tokens(
    id_token: str,
    refresh_token: str,
    user_id: str,
    email: str
) -> bool:
    """
    Save authentication tokens to file.

    Args:
        id_token: Firebase ID token
        refresh_token: Firebase refresh token
        user_id: Firebase user ID
        email: User email

    Returns:
        True if successful, False otherwise
    """
    try:
        token_file = get_token_file_path()
        expiry_timestamp = int(time.time()) + (TOKEN_EXPIRY_DAYS * 24 * 60 * 60)

        token_data = {
            "id_token": id_token,
            "refresh_token": refresh_token,
            "expiry_timestamp": expiry_timestamp,
            "user_id": user_id,
            "email": email,
            "created_at": datetime.utcnow().isoformat()
        }

        token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)

        logger.info(f"Auth tokens saved (expires in {TOKEN_EXPIRY_DAYS} days)")
        return True
    except Exception as e:
        logger.error(f"Failed to save auth tokens: {e}")
        return False

def load_auth_tokens() -> Optional[Dict[str, Any]]:
    """
    Load authentication tokens from file.

    Returns:
        Token data dictionary, or None if not found/invalid
    """
    try:
        token_file = get_token_file_path()
        if not token_file.exists():
            return None

        with open(token_file, "r", encoding="utf-8") as f:
            token_data = json.load(f)

        expiry_timestamp = token_data.get("expiry_timestamp", 0)
        if time.time() >= expiry_timestamp:
            logger.info("Stored tokens have expired")
            return None

        return token_data
    except Exception as e:
        logger.error(f"Failed to load auth tokens: {e}")
        return None

def clear_auth_tokens() -> bool:
    """
    Clear stored authentication tokens.

    Returns:
        True if successful, False otherwise
    """
    try:
        token_file = get_token_file_path()
        if token_file.exists():
            token_file.unlink()
        return True
    except Exception as e:
        logger.error(f"Failed to clear auth tokens: {e}")
        return False

def check_token_validity() -> bool:
    """
    Check if stored token is valid and not expired.

    Returns:
        True if token is valid, False otherwise
    """
    token_data = load_auth_tokens()
    if not token_data:
        return False

    expiry_timestamp = token_data.get("expiry_timestamp", 0)
    return time.time() < expiry_timestamp

def get_firebase_auth():
    """Get Firebase auth instance."""
    global _pyrebase
    if not PYREBASE4_AVAILABLE:
        logger.error("pyrebase4 is not installed. Cannot use Firebase authentication.")
        return None
    if _pyrebase is None:
        initialize_firebase()
    return _pyrebase.auth() if _pyrebase else None

def get_firebase_storage():
    """Get Firebase storage instance."""
    global _pyrebase
    if not PYREBASE4_AVAILABLE:
        logger.error("pyrebase4 is not installed. Cannot use Firebase storage.")
        return None
    if _pyrebase is None:
        initialize_firebase()
    return _pyrebase.storage() if _pyrebase else None

def get_firestore_db():
    """Get Firestore database instance."""
    global _firebase_db
    if _firebase_db is None:
        initialize_firebase()
    return _firebase_db

def sign_in_with_email_password(email: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Sign in with email and password (sign up disabled).

    Args:
        email: User email
        password: User password

    Returns:
        User info dictionary with tokens, or None if failed
    """
    try:
        auth = get_firebase_auth()
        if not auth:
            logger.error("Firebase auth not initialized")
            return None

        user = auth.sign_in_with_email_and_password(email, password)

        id_token = user.get("idToken")
        refresh_token = user.get("refreshToken")
        user_id = user.get("localId")

        if not all([id_token, refresh_token, user_id]):
            logger.error("Failed to get tokens from sign in")
            return None

        save_auth_tokens(id_token, refresh_token, user_id, email)
        set_firebase_user_id(user_id)

        logger.info(f"Signed in with email: {email}")

        return {
            **user,
            "id_token": id_token,
            "refresh_token": refresh_token,
            "expiry_timestamp": int(time.time()) + (TOKEN_EXPIRY_DAYS * 24 * 60 * 60)
        }
    except Exception as e:
        error_msg = str(e)
        if "USER_NOT_FOUND" in error_msg or "INVALID_PASSWORD" in error_msg:
            logger.warning(f"Authentication failed: Invalid credentials")
        else:
            logger.error(f"Failed to sign in with email/password: {e}")
        return None

def refresh_auth_token() -> Optional[Dict[str, Any]]:
    """
    Refresh authentication token using stored refresh token.

    Returns:
        Updated token data, or None if failed
    """
    try:
        token_data = load_auth_tokens()
        if not token_data:
            logger.warning("No stored tokens to refresh")
            return None

        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            logger.warning("No refresh token available")
            return None

        api_key = os.getenv("FIREBASE_API_KEY")
        if not api_key:
            logger.error("Firebase API key not configured")
            return None

        url = f"https://securetoken.googleapis.com/v1/token?key={api_key}"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }

        response = httpx.post(url, json=payload, timeout=10.0)
        response.raise_for_status()

        data = response.json()
        new_id_token = data.get("id_token")
        new_refresh_token = data.get("refresh_token", refresh_token)

        if not new_id_token:
            logger.error("Failed to get new ID token")
            return None

        user_id = token_data.get("user_id")
        email = token_data.get("email", "")
        save_auth_tokens(new_id_token, new_refresh_token, user_id, email)

        logger.info("Auth token refreshed successfully")
        return {
            "id_token": new_id_token,
            "refresh_token": new_refresh_token,
            "user_id": user_id,
            "email": email,
            "expiry_timestamp": int(time.time()) + (TOKEN_EXPIRY_DAYS * 24 * 60 * 60)
        }
    except Exception as e:
        logger.error(f"Failed to refresh auth token: {e}")
        return None

def load_stored_token() -> Optional[Dict[str, Any]]:
    """
    Load and validate stored token for app startup.

    Returns:
        Token data if valid, None otherwise
    """
    token_data = load_auth_tokens()
    if not token_data:
        return None

    if not check_token_validity():
        logger.info("Stored token has expired")
        return None

    user_id = token_data.get("user_id")
    if user_id:
        set_firebase_user_id(user_id)

    return token_data

def sign_out() -> bool:
    """
    Sign out from Firebase and clear stored tokens.

    Returns:
        True if successful, False otherwise
    """
    try:
        clear_auth_tokens()
        set_firebase_user_id(None)
        logger.info("Signed out from Firebase")
        return True
    except Exception as e:
        logger.error(f"Failed to sign out: {e}")
        return False

def get_auth_token() -> Optional[str]:
    """
    Get current authentication token.

    Returns:
        Auth token, or None if not authenticated
    """
    try:
        auth = get_firebase_auth()
        if not auth:
            return None

        return None
    except Exception as e:
        logger.error(f"Failed to get auth token: {e}")
        return None

def get_available_files(installer_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get list of available files for the installer.

    Args:
        installer_id: Installer ID (if None, uses registry)

    Returns:
        List of available file metadata
    """
    try:
        db = get_firestore_db()
        if not db:

            logger.debug("Firestore not available (Admin SDK not configured). File listing requires Admin SDK.")
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
        available_files = installer_data.get("available_files", [])

        files_list = []
        for file_info in available_files:
            file_name = file_info.get("name") if isinstance(file_info, dict) else file_info
            file_ref = db.collection("files").document(file_name)
            file_doc = file_ref.get()

            if file_doc.exists:
                file_data = file_doc.to_dict()
                files_list.append({
                    "name": file_name,
                    "version": file_data.get("version", "1.0.0"),
                    "description": file_data.get("description", ""),
                    "checksum": file_data.get("checksum", ""),
                    "size": file_data.get("size", 0),
                    "required": file_data.get("required", False),
                    "category": file_data.get("category", "browser_automation")
                })

        update_last_check()
        return files_list

    except Exception as e:
        logger.error(f"Failed to get available files: {e}")
        return []

def download_file(
    file_name: str,
    installer_id: Optional[str] = None,
    version: Optional[str] = None
) -> Optional[Path]:
    """
    Download a file from Firebase Storage.

    Args:
        file_name: Name of the file to download
        installer_id: Installer ID (for Firestore queries, not used in storage path)
        version: File version (for metadata, not used in storage path)

    Returns:
        Path to downloaded file, or None if failed
    """
    try:
        storage_client = get_firebase_storage()
        if not storage_client:

            logger.debug("Firebase storage not available (Admin SDK not configured). File download requires Admin SDK.")
            return None

        storage_path = f"files/{file_name}"

        temp_dir = Path(tempfile.gettempdir()) / "voice-agent-downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / file_name

        logger.info(f"Downloading {file_name} from Firebase Storage...")

        token_data = load_auth_tokens()
        auth_token = token_data.get("id_token") if token_data else None

        storage_bucket = os.getenv("FIREBASE_STORAGE_BUCKET", "")
        if not storage_bucket:
            logger.error("FIREBASE_STORAGE_BUCKET not configured")
            return None

        import urllib.parse
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
            raise
        if temp_file.exists():
            logger.info(f"Downloaded {file_name} to {temp_file}")
            return temp_file
        else:
            logger.error(f"Downloaded file not found: {temp_file}")
            return None

    except Exception as e:
        logger.error(f"Failed to download file {file_name}: {e}")
        return None

def install_file(
    file_name: str,
    version: str,
    checksum: str,
    installer_id: Optional[str] = None
) -> tuple[bool, Optional[str]]:
    """
    Install a downloaded file to the app data directory.

    Args:
        file_name: Name of the file
        version: File version
        checksum: Expected file checksum
        installer_id: Installer ID

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:

        downloaded_file = download_file(file_name, installer_id, version)
        if not downloaded_file or not downloaded_file.exists():
            error_msg = f"Failed to download {file_name}"
            logger.error(error_msg)
            return False, error_msg

        from services.file_registry import calculate_file_checksum
        if checksum and not verify_file_checksum(downloaded_file, checksum):
            actual_checksum = calculate_file_checksum(downloaded_file) if downloaded_file.exists() else None
            error_msg = f"Checksum verification failed for {file_name}. Expected: {checksum[:16]}..., Got: {actual_checksum[:16] if actual_checksum else 'None'}..."
            logger.error(error_msg)
            downloaded_file.unlink()
            return False, error_msg

        target_dir = get_browser_automation_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / file_name

        if target_file.exists():
            target_file.unlink()

        downloaded_file.rename(target_file)

        actual_checksum = calculate_file_checksum(target_file)

        register_file(file_name, version, actual_checksum, "remote", installer_id)

        logger.info(f"Successfully installed {file_name} v{version}")
        return True, None

    except Exception as e:
        error_msg = f"Failed to install file {file_name}: {e}"
        logger.error(error_msg)
        return False, error_msg

def get_installer_id_from_bundle() -> Optional[str]:
    """
    Get installer ID from bundled file or generate new one.

    Returns:
        Installer ID
    """
    import sys
    import uuid

    installer_id = os.getenv("INSTALLER_ID")
    if installer_id:
        return installer_id

    installer_id = get_installer_id()
    if installer_id:
        return installer_id

    if hasattr(sys, "_MEIPASS"):
        installer_id_file = Path(sys._MEIPASS) / "installer_id.txt"
        if installer_id_file.exists():
            try:
                installer_id = installer_id_file.read_text().strip()
                if installer_id:
                    set_installer_id(installer_id)
                    return installer_id
            except Exception as e:
                logger.warning(f"Failed to read installer ID from bundle: {e}")

    installer_id = str(uuid.uuid4())
    set_installer_id(installer_id)
    logger.info(f"Generated new installer ID: {installer_id}")
    return installer_id

def is_authenticated() -> bool:
    """
    Check if user is authenticated with valid token.

    Returns:
        True if authenticated with valid token, False otherwise
    """
    return check_token_validity() and get_firebase_user_id() is not None

def save_call_log_to_firestore(call_data: Dict[str, Any]) -> bool:
    """
    Save call log data to Firestore database.

    Args:
        call_data: Dictionary containing call log data (from CallLogger.call_data)

    Returns:
        True if successful, False otherwise
    """
    try:
        db = get_firestore_db()
        if not db:
            logger.debug("Firestore not available (Admin SDK not configured). Call log not saved to Firebase.")
            return False

        if not call_data:
            logger.warning("No call data provided to save to Firestore")
            return False

        call_id = call_data.get("call_id")
        if not call_id:
            logger.warning("Call ID missing from call data, cannot save to Firestore")
            return False

        calls_ref = db.collection("calls").document(call_id)

        firestore_data = {
            "call_id": call_id,
            "start_time": call_data.get("start_time"),
            "end_time": call_data.get("end_time"),
            "duration_seconds": call_data.get("duration_seconds"),
            "client": call_data.get("client", {}),
            "transcriptions": call_data.get("transcriptions", []),
            "summary": call_data.get("summary"),
            "mood": call_data.get("mood"),
            "rating": call_data.get("rating"),
            "status": call_data.get("status", "completed"),
            "created_at": datetime.utcnow().isoformat()
        }

        calls_ref.set(firestore_data, merge=True)

        logger.info(f"Call log saved to Firestore: call_id={call_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to save call log to Firestore: {e}", exc_info=True)
        return False
