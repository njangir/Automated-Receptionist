# Browser Automation Services

This package contains Python Playwright services that replace the TypeScript/JavaScript Playwright tests.

## Services

### BrowserService
Manages connection to Chrome via Chrome DevTools Protocol (CDP).

**Usage:**
```python
from services.browser_automation.browser_service import BrowserService

browser_service = BrowserService(chrome_debug_port=9222)
page = await browser_service.ensure_connected()
```

### ProfileService
Retrieves user profile and bank details from the backoffice system.

**Usage:**
```python
from services.browser_automation.profile_service import ProfileService

profile_service = ProfileService(page)
bank_details = await profile_service.get_user_bank_details(client_code="12345")
```

### PortfolioService
Retrieves user portfolio details and converts them to markdown format.

**Usage:**
```python
from services.browser_automation.portfolio_service import PortfolioService

portfolio_service = PortfolioService(page)
portfolio = await portfolio_service.get_user_portfolio(client_code="12345")
```

### LoginService
Handles login to the backoffice system.

**Usage:**
```python
from services.browser_automation.login_service import LoginService

login_service = LoginService(page)
success = await login_service.login(
    username="user",
    password="pass",
    login_type="15"
)
```

## Configuration

All services use environment variables from `.env.local`:

### Chrome Launcher
- `CHROME_DEBUG_PORT`: Port where Chrome is running with remote debugging (default: 9222)
- `CHROME_USER_DATA_DIR`: Chrome user data directory (cross-platform temp)
- `CHROME_EXECUTABLE_PATH`: Optional path to Chrome executable (auto-detected if not set)
- `CHROME_AUTO_START`: Auto-start Chrome when needed (default: true)
- `CHROME_CLEANUP_ON_EXIT`: Cleanup Chrome on application exit (default: false)
- `CHROME_REMOVE_USER_DATA`: Remove user data directory on cleanup (default: false)

### Login Service
- `LOGIN_URL`: URL of the login page
- `LOGIN_USERNAME`: Username for backoffice login
- `LOGIN_PASSWORD`: Password for backoffice login
- `LOGIN_TYPE`: Login type option value

## Migration from TypeScript Tests

The Python services replace the following TypeScript test files:

- `js/banya/user_profile.spec.ts` → `ProfileService.get_user_bank_details()`
- `js/banya/user_portfolio.spec.ts` → `PortfolioService.get_user_portfolio()`
- `js/banya/connect.spec.ts` → `LoginService.login()`
- `js/start.sh` → `ChromeLauncher.start_chrome()` (Python Chrome launcher)

## Benefits

1. **No subprocess overhead**: Direct Python API calls instead of spawning Node.js processes
2. **Better error handling**: Native Python exceptions instead of parsing stdout/stderr
3. **Type safety**: Python type hints for better IDE support
4. **Easier debugging**: Direct access to Playwright objects
5. **Single language stack**: Everything in Python

## Requirements

- `playwright>=1.40.0` (already in pyproject.toml)
- Chrome browser installed on the system (auto-detected)
- Chrome will be automatically started with remote debugging if `CHROME_AUTO_START=true`

## Chrome Launcher

The `ChromeLauncher` service automatically:
- Detects Chrome executable on Windows, macOS, and Linux
- Starts Chrome with remote debugging enabled
- Manages Chrome process lifecycle
- Works with PyInstaller executables (uses system Chrome, not bundled)

**Usage:**
```python
from browser_automation.chrome_launcher import ChromeLauncher

launcher = ChromeLauncher(chrome_debug_port=9222)
launcher.start_chrome()
# Chrome is now running with remote debugging on port 9222
```

**API Endpoints (in main.py):**
- `POST /chrome/start` - Start Chrome browser
- `POST /chrome/stop` - Stop Chrome browser
- `GET /chrome/status` - Check Chrome status