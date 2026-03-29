@echo off

echo ========================================
echo Installing build dependencies...
echo ========================================

pip install fastapi>=0.104.0
pip install "uvicorn[standard]>=0.24.0"
pip install python-dotenv>=0.19.0
pip install httpx>=0.25.0

pip install google-auth>=2.3.0
pip install google-api-python-client>=2.0.0
pip install google-auth-oauthlib>=0.4.6

pip install sounddevice

pip install firebase-admin>=6.0.0
pip install pyrebase4>=4.7.0

pip install playwright>=1.40.0


pip install pyinstaller>=6.0.0

echo ========================================
echo Installation complete!
echo ========================================
echo.
echo You can now run: pyinstaller voice-agent-server.spec
pause
