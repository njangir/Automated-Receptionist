"""Chrome browser launcher service with cross-platform support."""
import logging
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

class ChromeLauncher:
    """Service for launching and managing Chrome browser with remote debugging."""

    def __init__(
        self,
        chrome_debug_port: int = 9222,
        user_data_dir: Optional[str] = None,
        chrome_executable_path: Optional[str] = None
    ):
        """
        Initialize Chrome launcher.

        Args:
            chrome_debug_port: Port for remote debugging
            user_data_dir: Directory for Chrome user data (default: temp directory)
            chrome_executable_path: Optional path to Chrome executable (overrides auto-detection)
        """
        self.chrome_debug_port = chrome_debug_port
        self.chrome_executable_path = chrome_executable_path
        self.user_data_dir = user_data_dir or self._get_default_user_data_dir()
        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None

    @staticmethod
    def _get_default_user_data_dir() -> str:
        """Get default user data directory based on platform."""
        system = platform.system()
        if system == "Windows":

            import tempfile
            temp_dir = tempfile.gettempdir()
            return os.path.join(temp_dir, "chrome-playwright-clean")
        else:

            return "/tmp/chrome-playwright-clean"

    def find_chrome_executable(self) -> Optional[Path]:
        """
        Find Chrome executable path on the current platform.

        Returns:
            Path to Chrome executable, or None if not found
        """

        if self.chrome_executable_path:
            chrome_path = Path(self.chrome_executable_path)
            if chrome_path.exists():
                return chrome_path.resolve()
            logger.warning(f"Provided Chrome path does not exist: {chrome_path}")

        system = platform.system()

        if system == "Darwin":
            chrome_paths = [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                Path("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
            ]
            for path in chrome_paths:
                if path.exists():
                    return path.resolve()

            try:
                which_result = shutil.which("google-chrome-stable")
                if which_result:
                    return Path(which_result).resolve()
            except Exception:
                pass

        elif system == "Windows":
            chrome_paths = [
                Path(os.getenv("ProgramFiles", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(os.getenv("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
                Path(os.getenv("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            ]
            for path in chrome_paths:
                if path.exists():
                    return path.resolve()

            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Google\Chrome\BLBeacon"
                )
                version = winreg.QueryValueEx(key, "version")[0]
                winreg.CloseKey(key)

                local_appdata = os.getenv("LOCALAPPDATA", "")
                if local_appdata:
                    chrome_path = Path(local_appdata) / "Google" / "Chrome" / "Application" / "chrome.exe"
                    if chrome_path.exists():
                        return chrome_path.resolve()
            except Exception:
                pass

        else:
            chrome_commands = [
                "google-chrome-stable",
                "google-chrome",
                "chromium-browser",
                "chromium",
            ]
            for cmd in chrome_commands:
                try:
                    which_result = shutil.which(cmd)
                    if which_result:
                        return Path(which_result).resolve()
                except Exception:
                    continue

            linux_paths = [
                Path("/usr/bin/google-chrome-stable"),
                Path("/usr/bin/google-chrome"),
                Path("/usr/bin/chromium-browser"),
                Path("/usr/bin/chromium"),
            ]
            for path in linux_paths:
                if path.exists():
                    return path.resolve()

        return None

    def is_chrome_running_on_port(self, port: int) -> bool:
        """
        Check if Chrome is already running on the specified port.

        Args:
            port: Port to check

        Returns:
            True if Chrome is running on the port
        """
        try:

            response = httpx.get(f"http://localhost:{port}/json/version", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False

    def stop_chrome_by_port(self, port: int) -> bool:
        """
        Stop Chrome process running on the specified port.

        Args:
            port: Port where Chrome is running

        Returns:
            True if Chrome was stopped, False otherwise
        """
        try:
            system = platform.system()

            if system == "Windows":

                try:
                    result = subprocess.run(
                        ["netstat", "-ano"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        shell=True
                    )
                    for line in result.stdout.splitlines():
                        if f":{port}" in line and "LISTENING" in line:
                            parts = line.split()
                            if len(parts) >= 5:
                                try:
                                    pid = int(parts[-1])
                                    try:

                                        subprocess.run(
                                            ["taskkill", "/PID", str(pid), "/T"],
                                            capture_output=True,
                                            timeout=5
                                        )
                                        time.sleep(1)

                                        subprocess.run(
                                            ["taskkill", "/PID", str(pid), "/F", "/T"],
                                            capture_output=True,
                                            timeout=5
                                        )
                                        logger.info(f"Stopped Chrome process with PID {pid}")
                                        return True
                                    except (OSError, ProcessLookupError, subprocess.TimeoutExpired) as e:
                                        logger.warning(f"Failed to kill process {pid}: {e}")
                                except (ValueError, IndexError):
                                    continue
                except Exception as e:
                    logger.warning(f"Failed to find Chrome process on Windows: {e}")
            else:

                try:
                    result = subprocess.run(
                        ["lsof", "-ti", f":{port}"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        pids = [int(pid) for pid in result.stdout.strip().split() if pid]
                        for pid in pids:
                            try:
                                os.kill(pid, signal.SIGTERM)
                                time.sleep(1)

                                try:
                                    os.kill(pid, 0)
                                    os.kill(pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
                                logger.info(f"Stopped Chrome process with PID {pid}")
                            except (OSError, ProcessLookupError) as e:
                                logger.warning(f"Failed to kill process {pid}: {e}")
                        return len(pids) > 0
                except FileNotFoundError:

                    try:
                        subprocess.run(
                            ["pkill", "-f", "Google Chrome"],
                            timeout=5
                        )
                        logger.info("Stopped Chrome using pkill")
                        return True
                    except Exception as e:
                        logger.warning(f"Failed to stop Chrome with pkill: {e}")
                except Exception as e:
                    logger.warning(f"Failed to find Chrome process: {e}")

            return False
        except Exception as e:
            logger.error(f"Error stopping Chrome: {e}")
            return False

    def stop_chrome(self) -> bool:
        """
        Stop the Chrome process launched by this instance.

        Returns:
            True if Chrome was stopped, False otherwise
        """
        if self.process is None and self.pid is None:
            return False

        try:

            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
                except Exception as e:
                    logger.warning(f"Error terminating process: {e}")

            pid = self.pid or (self.process.pid if self.process else None)
            if pid:
                system = platform.system()
                try:
                    if system == "Windows":

                        subprocess.run(
                            ["taskkill", "/PID", str(pid), "/F", "/T"],
                            capture_output=True,
                            timeout=5
                        )
                    else:

                        os.kill(pid, signal.SIGTERM)
                        time.sleep(1)
                        try:
                            os.kill(pid, 0)
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    logger.info(f"Stopped Chrome process with PID {pid}")
                except (OSError, ProcessLookupError, subprocess.TimeoutExpired) as e:
                    logger.warning(f"Failed to kill Chrome process {pid}: {e}")

            self.process = None
            self.pid = None
            return True
        except Exception as e:
            logger.error(f"Error stopping Chrome: {e}")
            return False

    def start_chrome(
        self,
        port: Optional[int] = None,
        user_data_dir: Optional[str] = None,
        wait_for_ready: bool = True,
        timeout: int = 30
    ) -> subprocess.Popen:
        """
        Start Chrome with remote debugging enabled.

        Args:
            port: Remote debugging port (default: self.chrome_debug_port)
            user_data_dir: User data directory (default: self.user_data_dir)
            wait_for_ready: Wait for CDP endpoint to be ready
            timeout: Timeout in seconds for waiting for Chrome to be ready

        Returns:
            Popen object for the Chrome process

        Raises:
            FileNotFoundError: If Chrome executable is not found
            RuntimeError: If Chrome fails to start
        """
        port = port or self.chrome_debug_port
        user_data_dir = user_data_dir or self.user_data_dir

        chrome_path = self.find_chrome_executable()
        if not chrome_path:
            raise FileNotFoundError(
                "Chrome executable not found. Please install Google Chrome or Chromium, "
                "or set CHROME_EXECUTABLE_PATH environment variable."
            )

        logger.info(f"Found Chrome at: {chrome_path}")

        if self.is_chrome_running_on_port(port):
            logger.info(f"Chrome already running on port {port}, stopping it...")
            self.stop_chrome_by_port(port)
            time.sleep(1)

        user_data_path = Path(user_data_dir)
        user_data_path.mkdir(parents=True, exist_ok=True)

        chrome_args = [
            str(chrome_path),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ]

        logger.info(f"Starting Chrome with args: {' '.join(chrome_args)}")
        try:
            process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,

            )

            self.process = process
            self.pid = process.pid
            logger.info(f"Chrome started with PID {self.pid}")

            if wait_for_ready:
                logger.info(f"Waiting for Chrome CDP endpoint to be ready on port {port}...")
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if self.is_chrome_running_on_port(port):
                        logger.info("Chrome CDP endpoint is ready")
                        return process
                    time.sleep(0.5)

                if process.poll() is not None:
                    raise RuntimeError(f"Chrome process exited immediately with code {process.returncode}")

                raise RuntimeError(f"Chrome started but CDP endpoint not ready after {timeout} seconds")

            return process

        except Exception as e:
            logger.error(f"Failed to start Chrome: {e}")
            raise

    def ensure_chrome_running(
        self,
        port: Optional[int] = None,
        auto_start: bool = True
    ) -> bool:
        """
        Ensure Chrome is running on the specified port.

        Args:
            port: Remote debugging port (default: self.chrome_debug_port)
            auto_start: Automatically start Chrome if not running

        Returns:
            True if Chrome is running, False otherwise
        """
        port = port or self.chrome_debug_port

        if self.is_chrome_running_on_port(port):
            logger.info(f"Chrome is already running on port {port}")
            return True

        if not auto_start:
            logger.warning(f"Chrome is not running on port {port} and auto_start is disabled")
            return False

        try:
            self.start_chrome(port=port)
            return True
        except Exception as e:
            logger.error(f"Failed to ensure Chrome is running: {e}")
            return False

    def cleanup(self, remove_user_data: bool = False):
        """
        Clean up Chrome launcher resources.

        Args:
            remove_user_data: If True, remove the user data directory
        """
        self.stop_chrome()

        if remove_user_data and self.user_data_dir:
            try:
                user_data_path = Path(self.user_data_dir)
                if user_data_path.exists():
                    shutil.rmtree(user_data_path)
                    logger.info(f"Removed user data directory: {user_data_path}")
            except Exception as e:
                logger.warning(f"Failed to remove user data directory: {e}")
