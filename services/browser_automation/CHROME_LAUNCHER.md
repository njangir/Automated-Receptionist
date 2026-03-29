# Chrome Launcher Service

## Overview

The `ChromeLauncher` service provides cross-platform Chrome browser management with remote debugging support. It replaces the shell script (`js/start.sh`) with a pure Python implementation that works on Windows, macOS, and Linux, and is compatible with PyInstaller executables.

## Features

- **Cross-platform Chrome detection**: Automatically finds Chrome on Windows, macOS, and Linux
- **Process management**: Start, stop, and monitor Chrome processes
- **PyInstaller compatible**: Works when packaged as executable (uses system Chrome)
- **Auto-start support**: Automatically starts Chrome when needed
- **Port management**: Detects and handles port conflicts
- **Cleanup**: Optional cleanup of Chrome user data on exit

## Usage

### Basic Usage

```python
from services.browser_automation.chrome_launcher import ChromeLauncher

# Initialize launcher
launcher = ChromeLauncher(chrome_debug_port=9222)

# Start Chrome
launcher.start_chrome()

# Check if Chrome is running
if launcher.is_chrome_running_on_port(9222):
    print("Chrome is running")

# Stop Chrome
launcher.stop_chrome()
```

### With BrowserService (Automatic)

The `BrowserService` automatically uses `ChromeLauncher`:

```python
from services.browser_automation.browser_service import BrowserService

# BrowserService will auto-start Chrome if not running
browser_service = BrowserService(
    chrome_debug_port=9222,
    auto_start_chrome=True  # Default: True
)

page = await browser_service.ensure_connected()
# Chrome is automatically started if needed
```

### API Endpoints (in main.py)

The unified server provides HTTP endpoints for Chrome management:

- `POST /chrome/start` - Start Chrome browser
- `POST /chrome/stop` - Stop Chrome browser  
- `GET /chrome/status` - Check Chrome status

## Configuration

All configuration is done via environment variables in `.env.local`:

```bash
# Chrome remote debugging port
CHROME_DEBUG_PORT=9222

# Chrome user data directory (cross-platform)
CHROME_USER_DATA_DIR=/tmp/chrome-playwright-clean

# Optional: Override Chrome executable path
CHROME_EXECUTABLE_PATH=

# Auto-start Chrome when browser service connects
CHROME_AUTO_START=true

# Cleanup Chrome on application exit
CHROME_CLEANUP_ON_EXIT=false

# Remove user data directory on cleanup
CHROME_REMOVE_USER_DATA=false
```

## Cross-Platform Chrome Detection

### macOS
- `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- `/Applications/Chromium.app/Contents/MacOS/Chromium`
- Fallback: `which google-chrome-stable`

### Windows
- `C:\Program Files\Google\Chrome\Application\chrome.exe`
- `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`
- `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe`
- Registry lookup (optional)

### Linux
- `which google-chrome-stable`
- `which google-chrome`
- `which chromium-browser`
- `/usr/bin/google-chrome-stable`

## PyInstaller Compatibility

The launcher is designed to work with PyInstaller executables:

1. **Uses system Chrome** (not bundled): Smaller executable size, always up-to-date
2. **Path detection works in executables**: Uses `sys._MEIPASS` when needed
3. **No additional PyInstaller config needed**: Works out of the box

### If Bundling Chrome (Not Recommended)

If you want to bundle Chromium with your executable:

1. Set `PLAYWRIGHT_BROWSERS_PATH=0` environment variable
2. Include Playwright browser binaries in PyInstaller spec
3. Update `find_chrome_executable()` to use bundled Chromium

**Note**: This increases executable size by ~200MB and is not recommended.

## Process Management

### Starting Chrome

The launcher:
1. Checks if Chrome is already running on the port
2. Stops existing Chrome instance if found
3. Creates user data directory if needed
4. Launches Chrome with required flags:
   - `--remote-debugging-port={port}`
   - `--user-data-dir={dir}`
   - `--no-first-run`
   - `--no-default-browser-check`
   - Additional performance flags
5. Waits for CDP endpoint to be ready
6. Tracks process PID for cleanup

### Stopping Chrome

The launcher:
1. Tries graceful termination (SIGTERM)
2. Waits for process to exit
3. Force kills if needed (SIGKILL)
4. On Windows: Uses `taskkill` command
5. Cleans up process tracking

## Error Handling

- **Chrome not found**: Clear error message with installation instructions
- **Port already in use**: Automatically stops existing Chrome on that port
- **Permission errors**: Logged with helpful messages
- **Startup failures**: Retries with timeout, raises RuntimeError on failure

## Migration from Shell Script

The Python launcher replaces `js/start.sh`:

**Before:**
```bash
# js/start.sh
pkill -f "Google Chrome"
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-playwright-clean \
  --no-first-run --no-default-browser-check &
```

**After:**
```python
# Automatic - no manual script needed
launcher = ChromeLauncher()
launcher.start_chrome()
# Or use BrowserService which handles it automatically
```

## Benefits

1. **Cross-platform**: Works on Windows, macOS, Linux
2. **PyInstaller compatible**: No shell script dependencies
3. **Better error handling**: Python exceptions vs shell errors
4. **Process tracking**: Proper PID management
5. **Configurable**: All settings via environment variables
6. **Integrated**: Seamless with Python codebase
