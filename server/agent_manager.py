"""Agent process management."""
import logging
import os
import platform
import signal
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

root_dir = Path(__file__).parent.parent
from services.config_loader import load_config
from services.path_utils import get_config_dir, is_frozen
from services.log_manager import get_log_dir
load_config(root_dir)

logger = logging.getLogger(__name__)

class ProcessState:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.start_time: Optional[datetime] = None

        default_pid = os.path.join(tempfile.gettempdir(), "agent.pid")
        pid_file_path = os.getenv("PID_FILE_PATH", default_pid)
        self.pid_file = Path(pid_file_path)
        self.stdout_file: Optional[object] = None
        self.stderr_file: Optional[object] = None

    def is_running(self) -> bool:
        """Check if the process is still running."""
        if self.pid is None:
            return False

        if self.process is not None:
            return_code = self.process.poll()
            if return_code is not None:

                self._cleanup_state()
                return False
            return True

        try:
            os.kill(self.pid, 0)
            return True
        except (OSError, ProcessLookupError):

            self._cleanup_state()
            return False

    def _cleanup_state(self):
        """Clean up process state."""
        self.pid = None
        self.process = None
        self.start_time = None

    def get_uptime(self) -> Optional[float]:
        """Get uptime in seconds if process is running."""
        if self.start_time and self.is_running():
            return (datetime.now() - self.start_time).total_seconds()
        return None

state = ProcessState()

def _check_process_tree_dead(pid: int) -> bool:
    """
    Check if a process and all its children are actually dead (Windows-specific).

    On Windows, we need to verify that the entire process tree is terminated,
    not just the parent process.

    Args:
        pid: Process ID to check

    Returns:
        True if process and all children are dead, False otherwise
    """
    if platform.system() != "Windows":

        try:
            os.kill(pid, 0)
            return False
        except (OSError, ProcessLookupError):
            return True

    try:

        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
            capture_output=True,
            timeout=5,
            check=False
        )

        output = result.stdout.decode('utf-8', errors='ignore')
        if str(pid) in output and "INFO:" not in output:
            return False

        try:
            result2 = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
                capture_output=True,
                timeout=5,
                check=False
            )

        except Exception:
            pass

        return True
    except Exception as e:
        logger.warning(f"Failed to check if process tree is dead: {e}")

        return False

def _terminate_process(process: Optional[subprocess.Popen], pid: int, force: bool = False) -> bool:
    """
    Terminate process cross-platform.

    On Windows, this ensures the entire process tree is killed, including child processes
    spawned by uv run python (which creates a process tree: uv -> python -> agent).

    Args:
        process: Subprocess.Popen object (preferred method)
        pid: Process ID (fallback if process is None)
        force: If True, force kill; if False, graceful termination

    Returns:
        True if termination was attempted
    """
    system = platform.system()

    if system == "Windows":

        try:
            if force:

                cmd = ["taskkill", "/PID", str(pid), "/F", "/T"]
            else:

                cmd = ["taskkill", "/PID", str(pid), "/T"]

            result = subprocess.run(cmd, capture_output=True, timeout=10, check=False)
            if result.returncode == 0:
                logger.info(f"Terminated process tree {pid} using taskkill (force={force})")
            else:

                if "not found" in result.stderr.decode('utf-8', errors='ignore').lower():
                    logger.info(f"Process {pid} not found (already terminated)")
                else:
                    logger.warning(f"taskkill returned code {result.returncode} for PID {pid}: {result.stderr.decode('utf-8', errors='ignore')}")
            return True
        except subprocess.TimeoutExpired:
            logger.warning(f"taskkill timed out for process {pid}")
            return False
        except Exception as e:
            logger.warning(f"Failed to terminate process {pid} with taskkill: {e}")

            if process is not None:
                try:
                    if force:
                        process.kill()
                    else:
                        process.terminate()
                    logger.info(f"Terminated process {pid} using subprocess method (force={force}) as fallback")
                    return True
                except Exception as e2:
                    logger.warning(f"Failed to terminate process using subprocess method: {e2}")
            return False
    else:

        try:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)
            logger.info(f"Sent {sig.name} to process {pid}")
            return True
        except (OSError, ProcessLookupError) as e:
            logger.warning(f"Failed to send signal to process {pid}: {e}")
            return False

class StartResponse(BaseModel):
    status: str
    pid: Optional[int] = None
    message: str

class StopResponse(BaseModel):
    status: str
    message: str

class StatusResponse(BaseModel):
    status: str
    pid: Optional[int] = None
    uptime_seconds: Optional[float] = None
    message: str

async def start_agent_internal(
    client_code: str,
    phone_number: str,
    name: str,
    use_case: Optional[str] = None,
    agent_type: Optional[str] = None
) -> StartResponse:
    """Internal method to start the LiveKit agent process."""
    logger.info(
        f"Starting agent internally - CLIENT_CODE: {client_code}, "
        f"PHONE_NUMBER: {phone_number}, NAME: {name}"
    )

    if state.is_running():
        logger.warning(f"Agent is already running with PID {state.pid}, returning existing status")
        return StartResponse(
            status="already_running",
            pid=state.pid,
            message=f"Agent is already running with PID {state.pid}",
        )

    if state.pid is not None and state.process is not None:
        return_code = state.process.poll()
        if return_code is not None:

            defunct_pid = state.pid
            logger.warning(f"Found defunct process with PID {defunct_pid}, cleaning up")
            state._cleanup_state()

            if platform.system() != "Windows":
                try:
                    os.waitpid(defunct_pid, os.WNOHANG)
                except (OSError, ProcessLookupError, ChildProcessError):
                    pass

    try:

        root_dir = Path(__file__).parent.parent.resolve()

        agent_project_root_str = os.getenv("AGENT_PROJECT_ROOT", str(root_dir))
        agent_project_root = Path(agent_project_root_str).resolve()

        if not agent_type:
            agent_type = os.getenv("AGENT_TYPE", "bundled")

        agent_entrypoint_name = os.getenv("AGENT_ENTRYPOINT", "myagent.py")

        if agent_type == "online":
            try:
                from services.agent_code_service import ensure_agent_code_ready, get_installer_id
                from services.file_registry import get_installer_id as get_registry_installer_id

                agent_name = os.getenv("ONLINE_AGENT_NAME", "online_agent")
                installer_id = get_registry_installer_id()

                logger.info(f"Loading online agent: {agent_name} for installer: {installer_id}")
                agent_path = ensure_agent_code_ready(agent_name, installer_id)

                if agent_path and agent_path.exists():

                    agents_dir = agent_project_root / "agents"
                    agents_dir.mkdir(exist_ok=True)
                    dynamic_entrypoint = agents_dir / "dynamic_agent.py"

                    import shutil
                    shutil.copy2(agent_path, dynamic_entrypoint)

                    agent_entrypoint_name = "dynamic_agent.py"
                    logger.info(f"Using online agent from {agent_path}")
                else:
                    logger.warning(f"Failed to load online agent, falling back to bundled agent")
                    agent_type = "bundled"
            except Exception as e:
                logger.error(f"Error loading online agent: {e}, falling back to bundled agent")
                agent_type = "bundled"

        agent_entrypoint = agent_project_root / "agents" / agent_entrypoint_name

        logger.info(f"Root directory: {root_dir}")
        logger.info(f"Agent project root: {agent_project_root}")
        logger.info(f"Agent type: {agent_type}")
        logger.info(f"Agent entrypoint: {agent_entrypoint}")

        if not agent_entrypoint.exists():
            raise FileNotFoundError(f"Agent entrypoint not found: {agent_entrypoint}")

        os.chdir(str(agent_project_root))
        logger.info(f"Changed working directory to: {os.getcwd()}")

        env = os.environ.copy()

        env["CLIENT_CODE"] = client_code
        env["PHONE_NUMBER"] = phone_number
        env["NAME"] = name
        if use_case:
            env["AGENT_USE_CASE"] = use_case

        logger.info(
            f"Setting environment variables - CLIENT_CODE: {client_code}, "
            f"PHONE_NUMBER: {phone_number}, NAME: {name}"
        )

        if is_frozen():
            temp_env_file = get_config_dir() / ".env.temp"
        else:
            temp_env_file = agent_project_root / ".env.temp"
        logger.info(f"Writing environment variables to temporary file: {temp_env_file}")
        with open(temp_env_file, "w") as f:
            f.write(f"CLIENT_CODE={client_code}\n")
            f.write(f"PHONE_NUMBER={phone_number}\n")
            f.write(f"NAME={name}\n")
        logger.info(f"Successfully wrote environment variables to {temp_env_file}")

        log_dir = get_log_dir()
        stdout_log = log_dir / f"agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        stderr_log = log_dir / f"agent_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logger.info(f"Creating log files - stdout: {stdout_log}, stderr: {stderr_log}")

        stdout_file = open(stdout_log, "a")
        stderr_file = open(stderr_log, "a")

        state.stdout_file = stdout_file
        state.stderr_file = stderr_file

        agent_entrypoint_relative = f"agents/{agent_entrypoint_name}"
        logger.info(f"Starting agent process in directory: {agent_project_root}")
        logger.info(f"Command: uv run python {agent_entrypoint_relative} console")
        logger.info(f"Environment variables in env dict: CLIENT_CODE={env.get('CLIENT_CODE')}, PHONE_NUMBER={env.get('PHONE_NUMBER')}, NAME={env.get('NAME')}")

        process = subprocess.Popen(
            ["uv", "run", "python", agent_entrypoint_relative, "console"],
            cwd=str(agent_project_root),
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,

        )

        state.process = process
        state.pid = process.pid
        state.start_time = datetime.now()

        state.pid_file.parent.mkdir(parents=True, exist_ok=True)
        state.pid_file.write_text(str(state.pid))

        logger.info(f"✅ Started agent process with PID {state.pid} at {state.start_time}")

        start_delay = float(os.getenv("AGENT_START_DELAY", "1.0"))
        time.sleep(start_delay)

        if not state.is_running():
            logger.error(f"❌ Process {state.pid} died immediately after starting")
            raise RuntimeError("Process died immediately after starting")

        logger.info(f"✅ Process {state.pid} is running successfully")

        return StartResponse(
            status="started",
            pid=state.pid,
            message=f"Agent started successfully with PID {state.pid}",
        )

    except Exception as e:
        logger.error(f"❌ Failed to start agent: {e}", exc_info=True)

        state.process = None
        state.pid = None
        state.start_time = None

        logger.info("Cleaning up log file handles on failure")
        if state.stdout_file:
            try:
                state.stdout_file.close()
            except Exception:
                pass
        if state.stderr_file:
            try:
                state.stderr_file.close()
            except Exception:
                pass
        state.stdout_file = None
        state.stderr_file = None

        root_dir = Path(__file__).parent.parent.resolve()
        agent_project_root_str = os.getenv("AGENT_PROJECT_ROOT", str(root_dir))
        agent_project_root = Path(agent_project_root_str).resolve()

        if is_frozen():
            temp_env_file = get_config_dir() / ".env.temp"
        else:
            temp_env_file = agent_project_root / ".env.temp"
        if temp_env_file.exists():
            logger.info(f"Removing temporary .env file: {temp_env_file}")
            try:
                temp_env_file.unlink()
            except Exception as cleanup_error:
                logger.warning(f"Failed to remove temp env file: {cleanup_error}")

        if state.pid_file.exists():
            logger.info(f"Removing PID file: {state.pid_file}")
            state.pid_file.unlink()

        raise

async def stop_agent_internal() -> StopResponse:
    """Internal method to stop the LiveKit agent process gracefully."""
    logger.info("Stopping agent internally")

    if not state.is_running():
        logger.info("Agent is not currently running, nothing to stop")
        return StopResponse(
            status="not_running", message="Agent is not currently running"
        )

    try:
        pid = state.pid
        uptime = state.get_uptime()
        logger.info(f"Stopping agent process with PID {pid} (uptime: {uptime:.2f}s)")

        logger.info(f"Attempting graceful termination of process {pid}")
        _terminate_process(state.process, pid, force=False)

        if state.process is not None:
            process_wait_timeout = int(os.getenv("AGENT_PROCESS_WAIT_TIMEOUT", "5"))
            logger.info(f"Waiting for process to terminate (timeout: {process_wait_timeout}s)")
            try:
                state.process.wait(timeout=process_wait_timeout)
                logger.info(f"Process terminated within {process_wait_timeout} seconds")
            except subprocess.TimeoutExpired:
                logger.warning(f"Process did not terminate within {process_wait_timeout} seconds, continuing wait")

        stop_timeout = int(os.getenv("AGENT_STOP_TIMEOUT", "30"))
        stop_poll_interval = float(os.getenv("AGENT_STOP_POLL_INTERVAL", "0.5"))
        start_wait = time.time()
        logger.info(f"Waiting up to {stop_timeout}s for process to terminate")
        while state.is_running() and (time.time() - start_wait) < stop_timeout:
            time.sleep(stop_poll_interval)

        if state.is_running():
            logger.warning(f"Process {pid} did not terminate gracefully after {stop_timeout}s, forcing kill")
            _terminate_process(state.process, pid, force=True)

            time.sleep(2)

        if platform.system() == "Windows" and pid is not None:
            if not _check_process_tree_dead(pid):
                logger.warning(f"Process tree for PID {pid} still appears to be running, attempting additional cleanup")

                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F", "/T"],
                        capture_output=True,
                        timeout=10,
                        check=False
                    )
                    time.sleep(1)
                except Exception as e:
                    logger.warning(f"Additional cleanup attempt failed: {e}")

        final_check_timeout = 3
        final_check_start = time.time()
        while state.is_running() and (time.time() - final_check_start) < final_check_timeout:
            time.sleep(0.2)

        if state.is_running():
            logger.error(f"WARNING: Process {pid} is still running after all termination attempts!")
            logger.error("Process state will be cleaned up, but process may continue running in background")
        else:
            logger.info(f"Verified that process {pid} and all children are terminated")

        logger.info("Cleaning up process state")
        state.process = None
        state.pid = None
        state.start_time = None

        root_dir = Path(__file__).parent.parent.resolve()
        agent_project_root_str = os.getenv("AGENT_PROJECT_ROOT", str(root_dir))
        agent_project_root = Path(agent_project_root_str).resolve()

        if is_frozen():
            temp_env_file = get_config_dir() / ".env.temp"
        else:
            temp_env_file = agent_project_root / ".env.temp"
        if temp_env_file.exists():
            logger.info(f"Removing temporary .env file: {temp_env_file}")
            try:
                temp_env_file.unlink()
                logger.info("Temporary .env file removed successfully")
            except Exception as e:
                logger.warning(f"Failed to remove temp env file: {e}")

        logger.info("Closing log file handles")
        if state.stdout_file:
            try:
                state.stdout_file.close()
            except Exception as e:
                logger.warning(f"Failed to close stdout file: {e}")
        if state.stderr_file:
            try:
                state.stderr_file.close()
            except Exception as e:
                logger.warning(f"Failed to close stderr file: {e}")
        state.stdout_file = None
        state.stderr_file = None

        if state.pid_file.exists():
            logger.info(f"Removing PID file: {state.pid_file}")
            state.pid_file.unlink()

        logger.info(f"✅ Agent process {pid} stopped successfully")

        return StopResponse(
            status="stopped", message=f"Agent stopped successfully (was PID {pid})"
        )

    except Exception as e:
        logger.error(f"❌ Failed to stop agent: {e}", exc_info=True)
        raise

def get_state() -> ProcessState:
    """Get the process state instance."""
    return state
