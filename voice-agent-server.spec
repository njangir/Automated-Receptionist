
"""
PyInstaller spec file for voice-agent-server.

This spec file:
- Excludes runtime-modifiable config files (.env.config, .env.temp)
- Excludes specific browser automation files for dynamic loading
- Includes UI files and necessary resources
- Configures hidden imports for dependencies
"""

import os
import sys
from pathlib import Path

REQUIRED_PACKAGES = {
    "uvicorn": "uvicorn[standard]",
    "httpx": "httpx",
    "fastapi": "fastapi",
    "pydantic": "pydantic",
    "sounddevice": "sounddevice",
    "google.auth": "google-auth",
    "google.oauth2": "google-auth-oauthlib",
    "googleapiclient": "google-api-python-client",
    "firebase_admin": "firebase-admin",
    "pyrebase": "pyrebase4",
    "playwright": "playwright",
    "dotenv": "python-dotenv",
}

print("=" * 60)
print("Checking required packages...")
print("=" * 60)
missing_packages = []
for module_name, package_name in REQUIRED_PACKAGES.items():
    try:
        __import__(module_name)
        print(f"✓ {package_name} (provides {module_name})")
    except ImportError:
        print(f"✗ MISSING: {package_name} (provides {module_name})")
        missing_packages.append(package_name)

if missing_packages:
    print("\n" + "=" * 60)
    print("ERROR: Missing required packages!")
    print("=" * 60)
    print("Please install the following packages before building:")
    print(f"\npip install {' '.join(missing_packages)}")
    print("\nOr install all dependencies from requirements.txt:")
    print("pip install -r requirements.txt")
    print("=" * 60)
    sys.exit(1)

print("=" * 60)
print("All required packages are installed. Proceeding with build...")
print("=" * 60)

try:
    from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_all
    COLLECT_HOOKS_AVAILABLE = True
except ImportError:
    COLLECT_HOOKS_AVAILABLE = False
    collect_all = None

block_cipher = None

project_root = Path(SPECPATH)

datas = [

    (str(project_root / "ui"), "ui"),
]

if (project_root / ".env.secrets").exists():
    datas.append((str(project_root / ".env.secrets"), "."))
if (project_root / "installer_id.txt").exists():
    datas.append((str(project_root / "installer_id.txt"), "."))
if (project_root / "env.config.example").exists():
    datas.append((str(project_root / "env.config.example"), "."))
if (project_root / "assets" / "icon.ico").exists():
    datas.append((str(project_root / "assets" / "icon.ico"), "."))

icon_path = str(project_root / "assets" / "icon.ico") if (project_root / "assets" / "icon.ico").exists() else None

hiddenimports = [

    "fastapi",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    "fastapi.responses",
    "fastapi.staticfiles",
    "pydantic",

    "uvicorn",
    "uvicorn.main",
    "uvicorn.server",
    "uvicorn.config",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.uvloop",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",

    "h11",
    "httptools",
    "websockets",
    "websockets.legacy",
    "websockets.legacy.server",
    "click",
    "watchfiles",
]

binaries_to_add = []

if COLLECT_HOOKS_AVAILABLE:

    packages_to_collect = [
        "uvicorn",
        "httpx",
        "fastapi",
        "pydantic",
        "sounddevice",

        "google_auth",
        "google_auth_oauthlib",
        "googleapiclient",
    ]

    try:
        google_submodules = collect_submodules("google")
        hiddenimports.extend(google_submodules)
        print(f"✓ Collected {len(google_submodules)} google submodules")
    except Exception as e:
        print(f"⚠ Warning: Could not collect google submodules: {e}")
    for package in packages_to_collect:
        try:
            pkg_binaries, pkg_datas, pkg_hiddenimports = collect_all(package)
            hiddenimports.extend(pkg_hiddenimports)

            if pkg_datas:
                datas.extend(pkg_datas)

            if pkg_binaries:
                binaries_to_add.extend(pkg_binaries)
            print(f"✓ Collected {package}: {len(pkg_hiddenimports)} hidden imports, {len(pkg_binaries)} binaries")
        except Exception as e:
            print(f"⚠ Warning: Could not collect {package}: {e}")

optional_packages = [

    ("livekit", "livekit-agents"),
    ("livekit.agents", "livekit-agents"),
    ("livekit.plugins", "livekit-agents"),
    ("livekit.plugins.noise_cancellation", "livekit-plugins-noise-cancellation"),
    ("livekit.plugins.silero", "livekit-agents"),
    ("livekit.plugins.openai", "livekit-agents"),
    ("livekit.plugins.elevenlabs", "livekit-agents"),
    ("livekit.plugins.deepgram", "livekit-agents"),
    ("livekit.plugins.turn_detector", "livekit-agents"),
    ("livekit.plugins.turn_detector.multilingual", "livekit-agents"),

    ("pyrebase", "pyrebase4"),
]

print("\n=== Checking optional packages ===")
optional_imports = []
for module_name, package_name in optional_packages:
    try:
        __import__(module_name)
        optional_imports.append(module_name)
        print(f"✓ {package_name} (provides {module_name}) - will be included")
    except ImportError:
        print(f"⚠ {package_name} (provides {module_name}) - not installed, skipping")

hiddenimports.extend([

        "services.browser_automation.browser_service",
        "services.browser_automation.chrome_launcher",
        "services.browser_automation.file_loader",

        "services.config_loader",
        "services.config_service",
        "services.path_utils",
        "services.google_sheets",
        "services.call_logger",

        "playwright",
        "playwright.async_api",

        "firebase_admin",
        "firebase_admin.credentials",
        "firebase_admin.storage",
        "firebase_admin.firestore",
        "firebase_admin.exceptions",

        "google",
        "google.auth",
        "google.auth.transport",
        "google.auth.transport.requests",
        "google.auth.transport.urllib3",
        "google.oauth2",
        "google.oauth2.credentials",
        "google.oauth2.service_account",
        "googleapiclient",
        "googleapiclient.discovery",
        "googleapiclient.errors",
        "googleapiclient.http",
        "google_auth_oauthlib",
        "google_auth_httplib2",
        "httplib2",

    "httpx",
    "httpx._client",
    "httpx._transports",
    "httpx._transports.default",

    "httpx._models",
    "httpx._types",
    "httpx._utils",
    "httpcore",
    "httpcore._async",
    "httpcore._sync",
    "h2",
    "certifi",

    "dotenv",
    "sounddevice",
])

hiddenimports.extend(optional_imports)

critical_packages = {
    "uvicorn": ["uvicorn.main", "uvicorn.server", "uvicorn.config", "uvicorn.loops", "uvicorn.protocols", "uvicorn.lifespan"],
    "httpx": ["httpx._client", "httpx._transports", "httpx._models"],
    "fastapi": ["fastapi.middleware", "fastapi.responses", "fastapi.staticfiles"],
    "pydantic": ["pydantic.fields", "pydantic.validators"],
    "sounddevice": [],
}

google_packages = [
    "google.auth",
    "google.oauth2",
    "google.oauth2.service_account",
    "googleapiclient",
    "googleapiclient.discovery",
]

print("\n=== Verifying package installations ===")
for package_name, submodules in critical_packages.items():
    try:
        package = __import__(package_name)
        print(f"✓ {package_name} found at: {package.__file__}")

        for submodule in submodules:
            try:
                __import__(submodule)
            except ImportError:
                pass
    except ImportError as e:
        print(f"✗ ERROR: {package_name} not found: {e}")
        print(f"  Install with: pip install {package_name}")
        raise

print("\n=== Verifying Google API packages ===")
for google_pkg in google_packages:
    try:
        __import__(google_pkg)
        print(f"✓ {google_pkg} found")
    except ImportError as e:
        print(f"✗ ERROR: {google_pkg} not found: {e}")
        if "google.auth" in google_pkg:
            print("  Install with: pip install google-auth")
        elif "google.oauth2" in google_pkg:
            print("  Install with: pip install google-auth-oauthlib")
        elif "googleapiclient" in google_pkg:
            print("  Install with: pip install google-api-python-client")
        else:
            print(f"  Install required Google packages: pip install google-auth google-api-python-client google-auth-oauthlib")
        raise

print("\n=== All packages verified ===\n")

import site
pathex = []

if hasattr(site, 'getsitepackages'):
    for site_packages in site.getsitepackages():
        if os.path.exists(site_packages):
            pathex.append(site_packages)

user_site = site.getusersitepackages()
if user_site and os.path.exists(user_site):
    pathex.append(user_site)

a = Analysis(
    [str(project_root / "main.py")],
    pathex=pathex,
    binaries=binaries_to_add,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[

        ".env.config",
        ".env.temp",

        "services.browser_automation.login_service",
        "services.browser_automation.portfolio_service",
        "services.browser_automation.profile_service",

        "pytest",
        "tests",

        "ruff",

    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="voice-agent-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=os.name != 'nt',
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
