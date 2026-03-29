"""FastAPI application and API endpoints."""
import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional, List

import httpx
import socket
import sounddevice as sd
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.agent_manager import (
    StartResponse,
    StopResponse,
    StatusResponse,
    start_agent_internal,
    stop_agent_internal,
    get_state,
)
from services.config_service import (
    get_config_by_category,
    get_config_schema,
    read_config,
    validate_config,
    write_config,
)
from services.google_sheets import find_contact_by_phone
from services.browser_automation.browser_service import BrowserService

try:
    from services.browser_automation.login_service import LoginService
except ImportError:

    from services.browser_automation.file_loader import load_login_service
    login_service_module = load_login_service()
    if login_service_module:
        LoginService = login_service_module.LoginService
    else:
        LoginService = None

root_dir = Path(__file__).parent.parent
from services.config_loader import load_config
load_config(root_dir)

logger = logging.getLogger("voice_agent_server")

app = FastAPI(title="Voice Agent Server", version="1.0.0")

_server_ready = threading.Event()
_config_saved = False

_webhook_listening = False
_webhook_lock = threading.Lock()

_browser_service = None
_browser_service_lock = threading.Lock()

def get_ui_dir() -> Path:
    """Get UI directory path, handling PyInstaller."""
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent.parent
    return base_path / "ui"

from services.path_utils import get_config_dir, get_project_root, is_frozen
from services.log_manager import get_log_dir

if is_frozen():
    root_dir = get_project_root()
    config_dir = get_config_dir()
    config_file = config_dir / ".env.config"

    template_file = root_dir / "env.config.example"
    if not template_file.exists() and hasattr(sys, "_MEIPASS"):
        template_file = Path(sys._MEIPASS) / "env.config.example"
else:
    root_dir = Path(__file__).parent.parent.resolve()
    config_file = root_dir / ".env.config"
    template_file = root_dir / "env.config.example"

cors_origins = os.getenv("CORS_ORIGINS", "*")
if cors_origins == "*":
    cors_origins_list = ["*"]
else:
    cors_origins_list = [origin.strip() for origin in cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WebhookData(BaseModel):
    phone: str

class StartRequest(BaseModel):
    client_code: str
    phone_number: str
    name: str
    use_case: Optional[str] = None

class ConfigRequest(BaseModel):
    config: dict

class StartServerRequest(BaseModel):
    config: dict

WEBHOOK_ID = os.getenv("WEBHOOK_ID", "db449163-84f3-479e-af09-9f599b4db256")
DEFAULT_AGENT_USE_CASE = os.getenv("DEFAULT_AGENT_USE_CASE", "myagent")
GOOGLE_SHEET_ACCOUNT_CODE_COLUMN = os.getenv("GOOGLE_SHEET_ACCOUNT_CODE_COLUMN", "Account Code")
GOOGLE_SHEET_ACCOUNT_NAME_COLUMN = os.getenv("GOOGLE_SHEET_ACCOUNT_NAME_COLUMN", "Account Name")

ui_dir = get_ui_dir()
if ui_dir.exists():
    app.mount("/static", StaticFiles(directory=str(ui_dir)), name="static")
    sections_dir = ui_dir / "sections"
    if sections_dir.exists():
        app.mount("/sections", StaticFiles(directory=str(sections_dir)), name="sections")

def open_browser(url: str, delay: float = 1.0, app_mode: bool = True) -> None:
    """Open browser to the given URL (cross-platform).

    Args:
        url: URL to open
        delay: Delay before opening (seconds)
        app_mode: If True, opens in Chrome app mode (no browser UI).
                  If False, opens in default browser normally.
    """
    def _open():
        time.sleep(delay)
        try:
            if app_mode:

                system = platform.system()
                chrome_path = None

                if system == "Darwin":
                    chrome_paths = [
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                        "/Applications/Chromium.app/Contents/MacOS/Chromium"
                    ]
                    for path in chrome_paths:
                        if os.path.exists(path):
                            chrome_path = path
                            break
                elif system == "Windows":
                    chrome_paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                        os.path.join(os.getenv("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe")
                    ]
                    for path in chrome_paths:
                        if os.path.exists(path):
                            chrome_path = path
                            break
                else:
                    chrome_path = shutil.which("google-chrome-stable") or \
                                 shutil.which("google-chrome") or \
                                 shutil.which("chromium-browser")

                if chrome_path:

                    if system == "Windows":
                        temp_dir = tempfile.gettempdir()
                        app_user_data = os.path.join(temp_dir, "chrome-app-ui")
                    else:
                        app_user_data = "/tmp/chrome-app-ui"

                    Path(app_user_data).mkdir(parents=True, exist_ok=True)

                    if system == "Darwin":
                        subprocess.Popen([
                            chrome_path,
                            f"--app={url}",
                            f"--user-data-dir={app_user_data}",
                            "--no-first-run",
                            "--no-default-browser-check"
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif system == "Windows":
                        subprocess.Popen([
                            chrome_path,
                            f"--app={url}",
                            f"--user-data-dir={app_user_data}",
                            "--no-first-run",
                            "--no-default-browser-check"
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        subprocess.Popen([
                            chrome_path,
                            f"--app={url}",
                            f"--user-data-dir={app_user_data}",
                            "--no-first-run",
                            "--no-default-browser-check"
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    logger.info(f"Opened Chrome in app mode to {url} (separate profile)")
                else:

                    logger.warning("Chrome not found, falling back to default browser")
                    if system == "Windows":
                        os.startfile(url)
                    elif system == "Darwin":
                        subprocess.run(["open", url], check=False)
                    else:
                        subprocess.run(["xdg-open", url], check=False)
                    logger.info(f"Opened browser to {url}")
            else:

                system = platform.system()
                if system == "Windows":
                    os.startfile(url)
                elif system == "Darwin":
                    subprocess.run(["open", url], check=False)
                else:
                    subprocess.run(["xdg-open", url], check=False)
                logger.info(f"Opened browser to {url}")
        except Exception as e:
            logger.warning(f"Failed to open browser: {e}")
            print(f"\nPlease open your browser and navigate to: {url}\n")

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()

@app.get("/")
async def root():
    """Serve main UI HTML or redirect to UI."""
    ui_dir = get_ui_dir()
    index_file = ui_dir / "index.html"

    if index_file.exists():
        return FileResponse(index_file)
    else:
        return {"status": "ok", "message": "Service is running"}

@app.get("/ui")
async def get_ui():
    """Serve main UI HTML."""
    ui_dir = get_ui_dir()
    index_file = ui_dir / "index.html"

    if not index_file.exists():
        raise HTTPException(status_code=404, detail="UI files not found")

    return FileResponse(index_file)

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

@app.get("/api/config")
async def get_config():
    """Get current configuration values."""
    try:
        config = read_config(config_file)
        schema = get_config_schema()

        result = {}
        for field in schema:
            key = field["name"]
            result[key] = config.get(key, field.get("default", ""))

        return JSONResponse({
            "config": result,
            "schema": schema,
            "categorized": get_config_by_category()
        })
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config")
async def save_config(request: ConfigRequest):
    """Save configuration values."""
    try:

        validation = validate_config(request.config)
        if not validation["valid"]:
            return JSONResponse(
                {"success": False, "errors": validation["errors"]},
                status_code=400
            )

        success = write_config(config_file, request.config, template_file)

        if success:

            load_config(root_dir)
            return JSONResponse({"success": True, "message": "Configuration saved successfully"})
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")

    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/start-server")
async def start_server_endpoint(request: StartServerRequest):
    """Save configuration and reload it (server already running)."""
    global _config_saved

    try:

        validation = validate_config(request.config)
        if not validation["valid"]:
            return JSONResponse(
                {"success": False, "errors": validation["errors"]},
                status_code=400
            )

        success = write_config(config_file, request.config, template_file)

        if success:

            load_config(root_dir)
            _config_saved = True
            _server_ready.set()
            return JSONResponse({
                "success": True,
                "message": "Configuration saved and server configuration reloaded successfully."
            })
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")

    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/local-ip")
async def get_local_ip():
    """Get the local IP address of the machine."""
    try:

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:

            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
        except Exception:

            local_ip = socket.gethostbyname(socket.gethostname())
        finally:
            s.close()

        return JSONResponse({
            "local_ip": local_ip,
            "hostname": socket.gethostname()
        })
    except Exception as e:
        logger.error(f"Error getting local IP: {e}", exc_info=True)
        return JSONResponse({
            "local_ip": "Unable to determine",
            "hostname": socket.gethostname() if hasattr(socket, 'gethostname') else "Unknown",
            "error": str(e)
        })

@app.get("/api/audio-devices")
async def get_audio_devices():
    """Get list of available audio input and output devices."""
    try:
        devices = sd.query_devices()
        input_devices = []
        output_devices = []

        for i, device in enumerate(devices):
            device_info = {
                "index": i,
                "name": device["name"],
                "channels_in": int(device["max_input_channels"]),
                "channels_out": int(device["max_output_channels"]),
                "default_samplerate": float(device["default_samplerate"])
            }

            if device_info["channels_in"] > 0:
                input_devices.append(device_info)

            if device_info["channels_out"] > 0:
                output_devices.append(device_info)

        try:
            default_input = sd.default.device[0] if sd.default.device[0] is not None else None
            default_output = sd.default.device[1] if sd.default.device[1] is not None else None
        except Exception:
            default_input = None
            default_output = None

        return JSONResponse({
            "input_devices": input_devices,
            "output_devices": output_devices,
            "default_input_index": default_input,
            "default_output_index": default_output
        })

    except ImportError:
        logger.warning("sounddevice library not available")
        return JSONResponse({
            "input_devices": [],
            "output_devices": [],
            "error": "sounddevice library not available"
        })
    except Exception as e:
        logger.error(f"Error querying audio devices: {e}", exc_info=True)
        return JSONResponse({
            "input_devices": [],
            "output_devices": [],
            "error": str(e)
        })

@app.get("/api/main-server-status")
async def get_main_server_status():
    """Check if main server is running (always true in single server mode)."""
    return JSONResponse({
        "running": True,
        "port": int(os.getenv("SERVER_PORT", os.getenv("AGENT_MANAGER_PORT", "8000"))),
        "host": os.getenv("SERVER_HOST", os.getenv("AGENT_MANAGER_HOST", "0.0.0.0"))
    })

@app.get("/api/agent-status")
async def get_agent_status_api():
    """Get agent status (direct call, no proxy needed)."""
    return await get_status()

@app.post("/api/agent-start")
async def start_agent_api(request: StartRequest):
    """Start agent (direct call, no proxy needed)."""
    return await start_agent(request)

@app.post("/api/agent-stop")
async def stop_agent_api():
    """Stop agent (direct call, no proxy needed)."""
    return await stop_agent()

@app.post("/api/agent-overtake")
async def agent_overtake():
    """Manual overtake: stop agent but keep call alive."""
    try:

        stop_result = await stop_agent_internal()

        return JSONResponse({
            "success": True,
            "message": "Agent stopped. Call should continue (manual mode).",
            "stop_result": stop_result.dict() if hasattr(stop_result, 'dict') else str(stop_result)
        })
    except Exception as e:
        logger.error(f"Error in agent overtake: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/call-history")
async def get_call_history(limit: int = 50, offset: int = 0, sync: bool = True):
    """Get call history from daily summaries, syncing missing days if needed."""
    try:
        from services.daily_summary_service import get_daily_summary_service

        summary_service = get_daily_summary_service()
        all_calls = summary_service.get_all_calls(limit=limit + offset, restore_missing=sync)

        paginated_calls = all_calls[offset:offset + limit]

        formatted_calls = []
        for call_data in paginated_calls:
            duration = call_data.get("duration_seconds", 0)
            transcriptions = call_data.get("transcriptions", [])

            transcript_preview = ""
            if transcriptions:
                first_transcript = transcriptions[0] if transcriptions else None
                if first_transcript:
                    transcript_preview = first_transcript.get("text", "")[:100]

            call_summary = {
                "call_id": call_data.get("call_id", ""),
                "start_time": call_data.get("start_time", ""),
                "end_time": call_data.get("end_time"),
                "duration": duration,
                "client_name": call_data.get("client", {}).get("name", ""),
                "phone_number": call_data.get("client", {}).get("phone_number", ""),
                "client_code": call_data.get("client", {}).get("client_code", ""),
                "summary": call_data.get("summary", ""),
                "mood": call_data.get("mood", ""),
                "rating": call_data.get("rating", {"numeric": 3, "text": "Neutral"}),
                "status": call_data.get("status", "completed"),
                "transcript_preview": transcript_preview,
                "transcription_count": len(transcriptions)
            }
            formatted_calls.append(call_summary)

        return JSONResponse({
            "calls": formatted_calls,
            "total": len(all_calls),
            "limit": limit,
            "offset": offset
        })

    except Exception as e:
        logger.error(f"Error getting call history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/live-transcript")
async def get_live_transcript():
    """Get live transcriptions for the current active call."""
    try:

        log_dir = get_log_dir()

        if not log_dir.exists():
            return JSONResponse({
                "active": False,
                "message": "Log directory not found"
            })

        call_files = sorted(
            log_dir.glob("call_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if not call_files:
            return JSONResponse({
                "active": False,
                "message": "No calls found"
            })

        try:
            with open(call_files[0], "r", encoding="utf-8") as f:
                call_data = json.load(f)

            status = call_data.get("status", "unknown")
            is_active = status == "in_progress"

            return JSONResponse({
                "active": is_active,
                "call_id": call_data.get("call_id"),
                "phone_number": call_data.get("client", {}).get("phone_number", ""),
                "name": call_data.get("client", {}).get("name", ""),
                "client_code": call_data.get("client", {}).get("client_code", ""),
                "transcriptions": call_data.get("transcriptions", []),
                "status": status,
                "start_time": call_data.get("start_time")
            })
        except Exception as e:
            logger.error(f"Error reading call file: {e}", exc_info=True)
            return JSONResponse({
                "active": False,
                "message": f"Error reading call data: {str(e)}"
            })

    except Exception as e:
        logger.error(f"Error getting live transcript: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/call-history/{call_id}")
async def get_call_details(call_id: str):
    """Get full call details including complete transcript."""
    try:
        from services.daily_summary_service import get_daily_summary_service

        summary_service = get_daily_summary_service()
        all_calls = summary_service.get_all_calls(limit=10000, restore_missing=True)

        call_data = None
        for call in all_calls:
            if call.get("call_id") == call_id:
                call_data = call
                break

        if not call_data:
            raise HTTPException(status_code=404, detail=f"Call with ID {call_id} not found")

        return JSONResponse(call_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/version")
async def get_version():
    """Get version information."""
    try:
        version_file = root_dir / "version.json"
        if version_file.exists():
            with open(version_file, "r", encoding="utf-8") as f:
                version_data = json.load(f)
            return JSONResponse(version_data)
        else:
            return JSONResponse({
                "version": "1.0.0",
                "build_date": "Unknown",
                "build_number": "0"
            })
    except Exception as e:
        logger.error(f"Error getting version: {e}")
        return JSONResponse({
            "version": "1.0.0",
            "build_date": "Unknown",
            "build_number": "0"
        })

@app.post("/api/validate")
async def validate_config_endpoint(request: ConfigRequest):
    """Validate configuration values."""
    try:
        validation = validate_config(request.config)
        return JSONResponse(validation)
    except Exception as e:
        logger.error(f"Error validating config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
async def get_stats():
    """Get aggregated statistics from daily summaries."""
    try:
        from services.daily_summary_service import get_daily_summary_service

        summary_service = get_daily_summary_service()
        stats = summary_service.calculate_stats()

        total_duration_seconds = stats.get("total_duration_seconds", 0)
        hours = int(total_duration_seconds // 3600)
        minutes = int((total_duration_seconds % 3600) // 60)
        uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        return JSONResponse({
            "total_calls": stats.get("total_calls", 0),
            "total_duration_seconds": total_duration_seconds,
            "uptime": uptime_str,
            "uptime_seconds": total_duration_seconds,
            "average_rating": stats.get("average_rating"),
            "rating_count": stats.get("rating_count", 0)
        })
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sync-summaries")
async def sync_summaries(limit: int = 30):
    """Manually trigger sync of missing daily summaries from Firebase."""
    try:
        from services.daily_summary_service import get_daily_summary_service

        summary_service = get_daily_summary_service()
        synced_count = summary_service.sync_missing_summaries_from_firebase(limit=limit)

        return JSONResponse({
            "success": True,
            "synced_count": synced_count,
            "message": f"Synced {synced_count} daily summaries"
        })
    except Exception as e:
        logger.error(f"Error syncing summaries: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/webhook-status")
async def get_webhook_status(request: Request):
    """Get current webhook listening status."""
    with _webhook_lock:
        is_listening = _webhook_listening

    base_url = str(request.base_url).rstrip('/')
    webhook_url = f"{base_url}/webhook/{WEBHOOK_ID}"

    return JSONResponse({
        "listening": is_listening,
        "status": "listening" if is_listening else "disabled",
        "webhook_url": webhook_url
    })

@app.post("/api/webhook-enable")
async def enable_webhook():
    """Enable webhook listening."""
    global _webhook_listening
    with _webhook_lock:
        _webhook_listening = True
        logger.info("Webhook listening enabled")
    return JSONResponse({
        "success": True,
        "message": "Webhook listening enabled",
        "listening": True
    })

@app.post("/api/webhook-disable")
async def disable_webhook():
    """Disable webhook listening."""
    global _webhook_listening
    with _webhook_lock:
        _webhook_listening = False
        logger.info("Webhook listening disabled")
    return JSONResponse({
        "success": True,
        "message": "Webhook listening disabled",
        "listening": False
    })

@app.post("/api/webhook-toggle")
async def toggle_webhook(background_tasks: BackgroundTasks):
    """Toggle webhook listening state and manage browser/agent lifecycle."""
    global _webhook_listening, _browser_service

    with _webhook_lock:
        current_state = _webhook_listening
        new_state = not current_state
        _webhook_listening = new_state
        logger.info(f"Webhook listening toggled to: {new_state}")

    try:
        if new_state:

            logger.info("Starting browser automation (toggle ON)")

            agent_type = os.getenv("AGENT_TYPE", "bundled")
            if agent_type == "online":
                try:
                    from services.agent_code_service import ensure_agent_code_ready, get_installer_id
                    from services.file_registry import get_installer_id as get_registry_installer_id

                    agent_name = os.getenv("ONLINE_AGENT_NAME", "online_agent")
                    installer_id = get_registry_installer_id()

                    logger.info(f"Prefetching online agent: {agent_name} for installer: {installer_id}")

                    async def prefetch_agent():
                        try:
                            agent_path = ensure_agent_code_ready(agent_name, installer_id)
                            if agent_path:
                                logger.info(f"Successfully prefetched agent {agent_name}")
                            else:
                                logger.warning(f"Failed to prefetch agent {agent_name}, will fallback to bundled")
                        except Exception as e:
                            logger.error(f"Error prefetching agent: {e}")

                    background_tasks.add_task(prefetch_agent)
                except Exception as e:
                    logger.warning(f"Failed to prefetch agent code: {e}, will use cached or bundled")

            launcher = get_chrome_launcher()

            try:
                launcher.start_chrome()
                logger.info("Chrome browser started successfully")
            except Exception as e:
                logger.error(f"Failed to start Chrome: {e}", exc_info=True)

                with _webhook_lock:
                    _webhook_listening = False
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to start Chrome browser: {str(e)}"
                )

            try:
                chrome_debug_port = int(os.getenv("CHROME_DEBUG_PORT", "9222"))
                chrome_user_data_dir = os.getenv("CHROME_USER_DATA_DIR")
                chrome_executable_path = os.getenv("CHROME_EXECUTABLE_PATH")

                with _browser_service_lock:
                    browser_service = BrowserService(
                        chrome_debug_port=chrome_debug_port,
                        auto_start_chrome=False,
                        chrome_user_data_dir=chrome_user_data_dir,
                        chrome_executable_path=chrome_executable_path
                    )
                    _browser_service = browser_service

                    async def connect_and_login(bs=browser_service):
                        try:
                            page = await bs.ensure_connected()
                            logger.info("BrowserService connected to Chrome via CDP")

                            if LoginService is None:
                                logger.warning("LoginService not available - skipping login")
                                return

                            login_service = LoginService(page)
                            login_success = await login_service.login()

                            if login_success:
                                logger.info("Login service executed successfully")
                            else:
                                logger.warning("Login service execution completed but may have failed")
                        except Exception as e:
                            logger.error(f"Error during browser connection/login: {e}", exc_info=True)

                    background_tasks.add_task(connect_and_login)

            except Exception as e:
                logger.error(f"Failed to create/connect BrowserService: {e}", exc_info=True)

                try:
                    launcher.stop_chrome()
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup Chrome after error: {cleanup_error}")

                with _webhook_lock:
                    _webhook_listening = False
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to connect browser service: {str(e)}"
                )

            return JSONResponse({
                "success": True,
                "message": "Webhook listening enabled, browser started",
                "listening": True
            })

        else:

            logger.info("Stopping browser automation (toggle OFF)")

            try:
                stop_result = await stop_agent_internal()
                logger.info(f"Agent stop result: {stop_result.message}")
            except Exception as e:
                logger.warning(f"Error stopping agent (may not be running): {e}")

            with _browser_service_lock:
                if _browser_service is not None:
                    try:
                        await _browser_service.close(stop_chrome=False)
                        logger.info("BrowserService connection closed")
                    except Exception as e:
                        logger.warning(f"Error closing BrowserService: {e}")
                    finally:
                        _browser_service = None

            try:
                launcher = get_chrome_launcher()
                stopped = launcher.stop_chrome_by_port(launcher.chrome_debug_port)
                if stopped:
                    logger.info("Chrome browser stopped successfully")
                else:
                    logger.info("Chrome browser was not running")
            except Exception as e:
                logger.warning(f"Error stopping Chrome: {e}")

            return JSONResponse({
                "success": True,
                "message": "Webhook listening disabled, browser stopped",
                "listening": False
            })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in toggle_webhook: {e}", exc_info=True)

        with _webhook_lock:
            _webhook_listening = current_state
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle webhook: {str(e)}"
        )

@app.post(f"/webhook/{WEBHOOK_ID}", name="webhook_handler")
async def webhook_handler(phone_data: WebhookData):
    """Main webhook endpoint that replaces the n8n workflow"""

    with _webhook_lock:
        is_listening = _webhook_listening

    if not is_listening:
        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": "Webhook listening is disabled"}
        )

    try:
        phone = phone_data.phone
        if not phone:
            raise HTTPException(status_code=400, detail="Phone number is required")

        contact = await find_contact_by_phone(phone)
        if not contact:
            return {"status": "error", "message": "Contact not found"}

        pick_service_url = os.getenv("PICK_SERVICE_URL", "")
        if not pick_service_url:
            return {"status": "error", "message": "PICK_SERVICE_URL not configured"}

        async with httpx.AsyncClient() as client:
            pick_response = await client.post(
                pick_service_url,
                json={}
            )

            if pick_response.status_code != 200 or pick_response.json().get('data') != 'OK':
                return {"status": "error", "message": "Failed to process request"}

            try:

                agent_type = os.getenv("AGENT_TYPE", "bundled")

                result = await start_agent_internal(
                    client_code=contact.get(GOOGLE_SHEET_ACCOUNT_CODE_COLUMN, ''),
                    phone_number=phone,
                    name=contact.get(GOOGLE_SHEET_ACCOUNT_NAME_COLUMN, ''),
                    use_case=DEFAULT_AGENT_USE_CASE,
                    agent_type=agent_type
                )

                return {
                    "status": "success",
                    "data": {
                        "status": result.status,
                        "pid": result.pid,
                        "message": result.message
                    }
                }
            except Exception as e:
                logger.error(f"Failed to start agent: {e}")
                return {"status": "error", "message": f"Failed to start voice agent: {str(e)}"}

    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/start", response_model=StartResponse)
async def start_agent(request: StartRequest):
    """Start the LiveKit agent process (HTTP endpoint)."""
    try:

        agent_type = os.getenv("AGENT_TYPE", "bundled")

        return await start_agent_internal(
            client_code=request.client_code,
            phone_number=request.phone_number,
            name=request.name,
            use_case=request.use_case,
            agent_type=agent_type
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start agent: {str(e)}"
        )

@app.post("/stop", response_model=StopResponse)
async def stop_agent():
    """
    Stop the LiveKit agent process gracefully (HTTP endpoint).

    This endpoint properly terminates the agent process by:
    1. Sending graceful termination signal (SIGTERM)
    2. Waiting for process to terminate with timeout
    3. Force killing if graceful termination fails (SIGKILL)
    4. Cleaning up all process state (PID file, log files, temp env file)

    Called by end_call_and_disconnect tool to stop agent after call ends.
    """
    try:
        logger.info("Received stop request via /stop endpoint")
        result = await stop_agent_internal()
        logger.info(f"Stop request completed: {result.status}")
        return result
    except Exception as e:
        logger.error(f"Stop request failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to stop agent: {str(e)}"
        )

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get the current status of the agent process."""
    logger.info("Received status request")
    state = get_state()
    is_running = state.is_running()
    uptime = state.get_uptime()

    if is_running:
        logger.info(f"Agent status: running - PID: {state.pid}, Uptime: {uptime:.2f}s")
        return StatusResponse(
            status="running",
            pid=state.pid,
            uptime_seconds=uptime,
            message=f"Agent is running with PID {state.pid}",
        )
    else:
        logger.info("Agent status: stopped")
        return StatusResponse(
            status="stopped",
            pid=None,
            uptime_seconds=None,
            message="Agent is not currently running",
        )

_chrome_launcher = None

def get_chrome_launcher():
    """Get or create Chrome launcher instance."""
    global _chrome_launcher
    if _chrome_launcher is None:
        chrome_debug_port = int(os.getenv("CHROME_DEBUG_PORT", "9222"))
        chrome_user_data_dir = os.getenv("CHROME_USER_DATA_DIR")
        chrome_executable_path = os.getenv("CHROME_EXECUTABLE_PATH")

        from services.browser_automation.chrome_launcher import ChromeLauncher
        _chrome_launcher = ChromeLauncher(
            chrome_debug_port=chrome_debug_port,
            user_data_dir=chrome_user_data_dir,
            chrome_executable_path=chrome_executable_path
        )
    return _chrome_launcher

class ChromeStatusResponse(BaseModel):
    status: str
    port: int
    message: str

@app.post("/chrome/start", response_model=ChromeStatusResponse)
async def start_chrome():
    """Start Chrome browser with remote debugging."""
    try:
        launcher = get_chrome_launcher()
        launcher.start_chrome()
        return ChromeStatusResponse(
            status="started",
            port=launcher.chrome_debug_port,
            message=f"Chrome started on port {launcher.chrome_debug_port}"
        )
    except Exception as e:
        logger.error(f"Failed to start Chrome: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start Chrome: {str(e)}")

@app.post("/chrome/stop", response_model=ChromeStatusResponse)
async def stop_chrome():
    """Stop Chrome browser."""
    try:
        launcher = get_chrome_launcher()
        stopped = launcher.stop_chrome_by_port(launcher.chrome_debug_port)
        if stopped:
            return ChromeStatusResponse(
                status="stopped",
                port=launcher.chrome_debug_port,
                message=f"Chrome stopped on port {launcher.chrome_debug_port}"
            )
        else:
            return ChromeStatusResponse(
                status="not_running",
                port=launcher.chrome_debug_port,
                message="Chrome was not running"
            )
    except Exception as e:
        logger.error(f"Failed to stop Chrome: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop Chrome: {str(e)}")

@app.get("/chrome/status", response_model=ChromeStatusResponse)
async def chrome_status():
    """Get Chrome browser status."""
    try:
        launcher = get_chrome_launcher()
        is_running = launcher.is_chrome_running_on_port(launcher.chrome_debug_port)
        return ChromeStatusResponse(
            status="running" if is_running else "stopped",
            port=launcher.chrome_debug_port,
            message=f"Chrome is {'running' if is_running else 'not running'} on port {launcher.chrome_debug_port}"
        )
    except Exception as e:
        logger.error(f"Failed to get Chrome status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get Chrome status: {str(e)}")

class LoginRequest(BaseModel):
    email: str
    password: str

class InstallFilesRequest(BaseModel):
    files: List[str]

class AgentTypeRequest(BaseModel):
    agent_type: str

@app.post("/api/auth/login")
async def firebase_login(request: LoginRequest):
    """Authenticate with Firebase (sign in only, no sign up)."""
    try:
        from services.firebase_service import (
            sign_in_with_email_password,
            initialize_firebase,
        )

        if not initialize_firebase():
            raise HTTPException(status_code=500, detail="Firebase not configured")

        if not request.email or not request.password:
            raise HTTPException(status_code=400, detail="Email and password required")

        user = sign_in_with_email_password(request.email, request.password)

        if not user:
            raise HTTPException(status_code=401, detail="Authentication failed. Invalid credentials or user does not exist.")

        return JSONResponse({
            "success": True,
            "user_id": user.get("localId"),
            "email": user.get("email"),
            "expiry_timestamp": user.get("expiry_timestamp"),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Firebase login error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/logout")
async def firebase_logout():
    """Sign out from Firebase."""
    try:
        from services.firebase_service import sign_out

        success = sign_out()
        return JSONResponse({"success": success})
    except Exception as e:
        logger.error(f"Firebase logout error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/status")
async def firebase_auth_status():
    """Check Firebase authentication status and token validity."""
    try:
        from services.firebase_service import (
            is_authenticated,
            get_firebase_user_id,
            load_auth_tokens,
            check_token_validity,
        )

        authenticated = is_authenticated()
        token_data = load_auth_tokens() if authenticated else None
        user_id = get_firebase_user_id() if authenticated else None

        expiry_timestamp = token_data.get("expiry_timestamp") if token_data else None
        time_until_expiry = expiry_timestamp - int(time.time()) if expiry_timestamp else None

        return JSONResponse({
            "authenticated": authenticated,
            "user_id": user_id,
            "email": token_data.get("email") if token_data else None,
            "expiry_timestamp": expiry_timestamp,
            "time_until_expiry": time_until_expiry,
            "token_valid": check_token_validity(),
        })
    except Exception as e:
        logger.error(f"Firebase auth status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/refresh")
async def firebase_refresh_token():
    """Refresh authentication token."""
    try:
        from services.firebase_service import refresh_auth_token, initialize_firebase

        if not initialize_firebase():
            raise HTTPException(status_code=500, detail="Firebase not configured")

        token_data = refresh_auth_token()

        if not token_data:
            raise HTTPException(status_code=401, detail="Token refresh failed. Please sign in again.")

        return JSONResponse({
            "success": True,
            "expiry_timestamp": token_data.get("expiry_timestamp"),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/verify")
async def firebase_verify_token():
    """Verify token validity."""
    try:
        from services.firebase_service import check_token_validity, load_auth_tokens

        is_valid = check_token_validity()
        token_data = load_auth_tokens() if is_valid else None

        return JSONResponse({
            "valid": is_valid,
            "user_id": token_data.get("user_id") if token_data else None,
            "email": token_data.get("email") if token_data else None,
        })
    except Exception as e:
        logger.error(f"Token verification error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files/available")
async def get_available_files():
    """Get list of available files for installation."""
    try:
        from services.firebase_service import (
            get_available_files,
            get_installer_id_from_bundle,
            initialize_firebase,
            is_authenticated,
        )

        if not initialize_firebase():
            return JSONResponse({"available_files": [], "message": "Firebase not configured"})

        if not is_authenticated():
            return JSONResponse({
                "available_files": [],
                "message": "Authentication required. Please sign in to view available files.",
                "requires_auth": True
            })

        installer_id = get_installer_id_from_bundle()

        files = get_available_files(installer_id)

        return JSONResponse({
            "available_files": files,
            "installer_id": installer_id,
        })
    except Exception as e:
        logger.error(f"Get available files error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files/installed")
async def get_installed_files():
    """Get list of installed files."""
    try:
        from services.file_registry import get_installed_files

        installed = get_installed_files()

        return JSONResponse({
            "installed_files": list(installed.keys()),
            "files": installed,
        })
    except Exception as e:
        logger.error(f"Get installed files error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/files/install")
async def install_files(request: InstallFilesRequest):
    """Install selected files from Firebase."""
    try:
        from services.firebase_service import (
            get_available_files,
            install_file,
            get_installer_id_from_bundle,
            initialize_firebase,
            is_authenticated,
        )

        if not initialize_firebase():
            raise HTTPException(status_code=500, detail="Firebase not configured")

        if not is_authenticated():
            raise HTTPException(status_code=401, detail="Authentication required. Please sign in to install files.")

        installer_id = get_installer_id_from_bundle()
        available_files = get_available_files(installer_id)

        file_metadata = {f.get("name"): f for f in available_files}

        results = []
        for file_name in request.files:
            if file_name not in file_metadata:
                results.append({
                    "file": file_name,
                    "success": False,
                    "error": "File not available"
                })
                continue

            metadata = file_metadata[file_name]
            success, error_msg = install_file(
                file_name,
                metadata.get("version", "1.0.0"),
                metadata.get("checksum", ""),
                installer_id
            )

            results.append({
                "file": file_name,
                "success": success,
                "version": metadata.get("version", "1.0.0"),
                "error": error_msg if not success else None,
            })

        from services.browser_automation.file_loader import _loaded_modules
        _loaded_modules.clear()

        return JSONResponse({
            "success": True,
            "results": results,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Install files error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/files/status/{file_name}")
async def get_file_status(file_name: str):
    """Get status of a specific file."""
    try:
        from services.file_registry import is_file_installed, get_file_info
        from services.path_utils import get_browser_automation_dir, is_frozen, get_project_root

        installed = is_file_installed(file_name)
        file_info = get_file_info(file_name) if installed else None

        if is_frozen():
            file_path = get_browser_automation_dir() / file_name
        else:
            file_path = get_project_root() / "services" / "browser_automation" / file_name

        exists_on_disk = file_path.exists()

        return JSONResponse({
            "file": file_name,
            "installed": installed,
            "exists_on_disk": exists_on_disk,
            "info": file_info,
        })
    except Exception as e:
        logger.error(f"Get file status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/installer-id")
async def get_installer_id_endpoint():
    """Get current installer ID."""
    try:
        from services.firebase_service import get_installer_id_from_bundle

        installer_id = get_installer_id_from_bundle()
        return JSONResponse({"installer_id": installer_id})
    except Exception as e:
        logger.error(f"Get installer ID error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/agent-type")
async def get_agent_type():
    """Get current agent type preference."""
    try:
        agent_type = os.getenv("AGENT_TYPE", "bundled")
        return JSONResponse({"agent_type": agent_type})
    except Exception as e:
        logger.error(f"Get agent type error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/agent-type")
async def set_agent_type(request: AgentTypeRequest):
    """Set agent type preference."""
    try:
        if request.agent_type not in ["bundled", "online"]:
            raise HTTPException(status_code=400, detail="agent_type must be 'bundled' or 'online'")

        config = read_config(config_file)
        config["AGENT_TYPE"] = request.agent_type
        write_config(config_file, config, template_file)

        os.environ["AGENT_TYPE"] = request.agent_type

        return JSONResponse({"success": True, "agent_type": request.agent_type})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set agent type error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/available-agents")
async def get_available_agents():
    """Get list of available agents for current installer."""
    try:
        from services.agent_code_service import get_available_agents
        from services.file_registry import get_installer_id

        installer_id = get_installer_id()
        agents = get_available_agents(installer_id)

        return JSONResponse({"agents": agents})
    except Exception as e:
        logger.error(f"Get available agents error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fetch-agent-code")
async def fetch_agent_code_endpoint(background_tasks: BackgroundTasks):
    """Manually trigger agent code fetch."""
    try:
        from services.agent_code_service import ensure_agent_code_ready, get_installer_id
        from services.file_registry import get_installer_id as get_registry_installer_id

        agent_name = os.getenv("ONLINE_AGENT_NAME", "online_agent")
        installer_id = get_registry_installer_id()

        async def fetch_agent():
            try:
                agent_path = ensure_agent_code_ready(agent_name, installer_id)
                if agent_path:
                    logger.info(f"Successfully fetched agent {agent_name}")
                else:
                    logger.warning(f"Failed to fetch agent {agent_name}")
            except Exception as e:
                logger.error(f"Error fetching agent: {e}")

        background_tasks.add_task(fetch_agent)

        return JSONResponse({"success": True, "message": "Agent code fetch initiated"})
    except Exception as e:
        logger.error(f"Fetch agent code error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/shutdown")
async def shutdown_app(background_tasks: BackgroundTasks):
    """Shutdown the entire application: stop agent, close browser services, and exit."""
    global _browser_service
    logger.info("Shutdown requested via API")

    try:

        try:
            stop_result = await stop_agent_internal()
            logger.info(f"Agent stop result: {stop_result.message}")
        except Exception as e:
            logger.warning(f"Error stopping agent (may not be running): {e}")

        with _browser_service_lock:
            if _browser_service is not None:
                try:
                    await _browser_service.close(stop_chrome=False)
                    logger.info("BrowserService connection closed")
                except Exception as e:
                    logger.warning(f"Error closing BrowserService: {e}")
                finally:
                    _browser_service = None

        try:
            launcher = get_chrome_launcher()
            stopped = launcher.stop_chrome_by_port(launcher.chrome_debug_port)
            if stopped:
                logger.info("Chrome browser stopped successfully")
            else:
                logger.info("Chrome browser was not running")
        except Exception as e:
            logger.warning(f"Error stopping Chrome: {e}")

        async def exit_process():
            """Exit the process after a short delay to allow response to be sent."""
            await asyncio.sleep(0.5)
            logger.info("Exiting application...")
            os._exit(0)

        background_tasks.add_task(exit_process)

        return JSONResponse({
            "success": True,
            "message": "Application shutdown initiated"
        })
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)

        background_tasks.add_task(lambda: os._exit(1))
        raise HTTPException(status_code=500, detail=f"Error during shutdown: {str(e)}")

import atexit

def cleanup_on_exit():
    """Cleanup function called on application exit."""
    try:

        global _browser_service
        with _browser_service_lock:
            if _browser_service is not None:
                try:

                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():

                            logger.info("BrowserService cleanup skipped (event loop running)")
                        else:
                            loop.run_until_complete(_browser_service.close(stop_chrome=False))
                            logger.info("BrowserService connection closed on exit")
                    except RuntimeError:

                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            loop.run_until_complete(_browser_service.close(stop_chrome=False))
                            logger.info("BrowserService connection closed on exit")
                        finally:
                            loop.close()
                except Exception as e:
                    logger.warning(f"Error closing BrowserService on exit: {e}")
                finally:
                    _browser_service = None

        cleanup_chrome = os.getenv("CHROME_CLEANUP_ON_EXIT", "false").lower() == "true"
        if cleanup_chrome and _chrome_launcher:
            logger.info("Cleaning up Chrome on exit")
            remove_user_data = os.getenv("CHROME_REMOVE_USER_DATA", "false").lower() == "true"
            _chrome_launcher.cleanup(remove_user_data=remove_user_data)
    except Exception as e:
        logger.warning(f"Error during cleanup: {e}")

atexit.register(cleanup_on_exit)
