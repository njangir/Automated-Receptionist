"""Configuration UI server for startup configuration and control panel."""
import json
import logging
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from services.config_service import (
    get_config_by_category,
    get_config_schema,
    read_config,
    validate_config,
    write_config,
)

logger = logging.getLogger(__name__)

_server_ready = threading.Event()
_config_saved = False
_main_server_running = False
_main_server_port = 8000
_main_server_host = "127.0.0.1"

def get_ui_dir() -> Path:
    """Get UI directory path, handling PyInstaller."""
    if getattr(sys, "frozen", False):

        base_path = Path(sys._MEIPASS)
    else:

        base_path = Path(__file__).parent.parent

    ui_dir = base_path / "ui"
    return ui_dir

def open_browser(url: str, delay: float = 1.0) -> None:
    """
    Open browser to the given URL (cross-platform).

    Args:
        url: URL to open
        delay: Delay in seconds before opening (to allow server to start)
    """
    def _open():
        time.sleep(delay)
        try:
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

app = FastAPI(title="Configuration UI", version="1.0.0")

from services.path_utils import get_config_dir, get_project_root, is_frozen

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

class ConfigRequest(BaseModel):
    config: dict

class StartServerRequest(BaseModel):
    config: dict

class AgentStartRequest(BaseModel):
    client_code: str
    phone_number: str
    name: str
    use_case: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve main UI HTML."""
    ui_dir = get_ui_dir()
    index_file = ui_dir / "index.html"

    if not index_file.exists():
        raise HTTPException(status_code=404, detail="UI files not found")

    return FileResponse(index_file)

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
            return JSONResponse({"success": True, "message": "Configuration saved successfully"})
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")

    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/start-server")
async def start_server(request: StartServerRequest):
    """Save configuration and signal ready to start main server."""
    global _config_saved, _main_server_running

    try:

        validation = validate_config(request.config)
        if not validation["valid"]:
            return JSONResponse(
                {"success": False, "errors": validation["errors"]},
                status_code=400
            )

        success = write_config(config_file, request.config, template_file)

        if success:
            _config_saved = True
            _server_ready.set()

            return JSONResponse({
                "success": True,
                "message": "Configuration saved. Starting main server..."
            })
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")

    except Exception as e:
        logger.error(f"Error starting server: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def set_main_server_running(running: bool, port: int = 8000, host: str = "127.0.0.1"):
    """Set main server running status (called by main.py)."""
    global _main_server_running, _main_server_port, _main_server_host
    _main_server_running = running
    _main_server_port = port
    _main_server_host = host

def get_main_server_url() -> str:
    """Get main server URL."""
    return f"http://{_main_server_host}:{_main_server_port}"

async def proxy_to_main_server(endpoint: str, method: str = "GET", data: Optional[dict] = None):
    """Proxy request to main server."""
    if not _main_server_running:
        raise HTTPException(status_code=503, detail="Main server is not running")

    url = f"{get_main_server_url()}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url, json=data)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported method: {method}")

            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=response.text)

            return response.json()
    except httpx.RequestError as e:
        logger.error(f"Error proxying to main server: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to connect to main server: {str(e)}")

@app.get("/api/main-server-status")
async def get_main_server_status():
    """Check if main server is running."""

    is_online = False
    if _main_server_running:
        try:
            url = f"{get_main_server_url()}/health"
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
                is_online = response.status_code == 200
        except Exception:
            is_online = False

    return JSONResponse({
        "running": _main_server_running and is_online,
        "port": _main_server_port,
        "host": _main_server_host
    })

@app.get("/api/agent-status")
async def get_agent_status():
    """Get agent status from main server."""
    return await proxy_to_main_server("/status", "GET")

@app.post("/api/agent-start")
async def start_agent(request: AgentStartRequest):
    """Start agent via main server."""
    data = {
        "client_code": request.client_code,
        "phone_number": request.phone_number,
        "name": request.name
    }
    if request.use_case:
        data["use_case"] = request.use_case

    return await proxy_to_main_server("/start", "POST", data)

@app.post("/api/agent-stop")
async def stop_agent():
    """Stop agent via main server."""
    return await proxy_to_main_server("/stop", "POST")

@app.post("/api/agent-overtake")
async def agent_overtake():
    """Manual overtake: stop agent but keep call alive."""
    try:

        stop_result = await proxy_to_main_server("/stop", "POST")

        return JSONResponse({
            "success": True,
            "message": "Agent stopped. Call should continue (manual mode).",
            "stop_result": stop_result
        })
    except Exception as e:
        logger.error(f"Error in agent overtake: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/call-history")
async def get_call_history():
    """Get call history (placeholder for future implementation)."""

    return JSONResponse({
        "calls": [],
        "message": "Call history feature coming soon"
    })

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

ui_dir = get_ui_dir()

if ui_dir.exists():

    static_dir = ui_dir
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    sections_dir = ui_dir / "sections"
    if sections_dir.exists():
        app.mount("/sections", StaticFiles(directory=str(sections_dir)), name="sections")

def wait_for_config() -> bool:
    """
    Wait for user to complete configuration.

    Returns:
        True if config was saved, False if timeout or error
    """
    global _config_saved
    _config_saved = False
    _server_ready.clear()

    timeout = 600
    if _server_ready.wait(timeout=timeout):
        return _config_saved
    else:
        logger.warning("Configuration timeout - proceeding with defaults")
        return False

def run_config_ui(port: int = 8001, open_browser_flag: bool = True) -> None:
    """
    Run the configuration UI server (blocking).

    Args:
        port: Port to run the UI server on
        open_browser_flag: Whether to automatically open browser
    """
    import uvicorn

    host = "127.0.0.1"
    url = f"http://{host}:{port}"

    logger.info(f"Starting configuration UI on {url}")

    if open_browser_flag:
        open_browser(url, delay=1.5)

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    server.run()
