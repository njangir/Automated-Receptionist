# Voice Agent Server

A **FastAPI** app that hosts a web UI to configure and run a **LiveKit Agents** voice assistant, with optional **browser automation** (Playwright), **Google Sheets** contact lookup, and **Firebase** extras. Use it as a template: swap the bundled agent (`agents/`), point env vars at your own services, or rely on **mock data** for a quick local demo.

## How it fits together

- **`main.py`** starts **Uvicorn**, loads `.env.secrets` + `.env.config`, then opens the UI at `http://127.0.0.1:<port>/ui` (default port **8000**).
- The **UI** drives settings, agent start/stop, webhooks, and related features via **`server/api.py`** and **`server/agent_manager.py`**.
- The **voice agent** lives under **`agents/`** (e.g. `myagent.py`). It uses LiveKit, STT/LLM/TTS providers, and tools that can call browser services when not in mock mode.
- **Demo defaults** in `env.config.example` use **`USE_MOCK_CONTACT_LOOKUP`** and **`BROWSER_USE_MOCK_DATA`** so you can run without real Sheets or a live backoffice portal. Data samples are under **`demo/`**.

## First run

1. **Python 3.9+** and **`uv`** or **`pip`**.
2. Clone the repo and create a venv:

   ```bash
   cd "Automated Receptionist - Demo"
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   uv sync
   ```

   or with pip:

   ```bash
   pip install -r requirements.txt
   ```

4. Install **Playwright** browsers if you use automation:

   ```bash
   playwright install chromium
   ```

5. **Config files** (not committed; loaded at startup):

   - Copy **`env.config.example`** → **`.env.config`** and adjust if needed.
   - Copy **`.env.secrets.example`** → **`.env.secrets`** and set at least **LiveKit** and provider keys (`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, plus e.g. `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY` as you use them).

6. Start the server:

   ```bash
   python main.py
   ```

   Open the URL shown in the logs (typically **`http://127.0.0.1:8000/ui`**) and complete setup in the UI.

## Customizing

- Change **`AGENT_ENTRYPOINT`** / **`DEFAULT_AGENT_USE_CASE`** in `.env.config` to your file under **`agents/`**.
- For real **Sheets** lookup: set **`GOOGLE_SHEET_ID`**, **`GOOGLE_SERVICE_ACCOUNT_PATH`**, and set **`USE_MOCK_CONTACT_LOOKUP=false`**.
- For real **browser** tools: set **`BROWSER_USE_MOCK_DATA=false`** and configure **`LOGIN_URL`** and credentials as required by your target site.

## Building a desktop binary

See **`voice-agent-server.spec`** (PyInstaller). Install PyInstaller and project deps, then build per your platform’s PyInstaller workflow.
