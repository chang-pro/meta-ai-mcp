# SETUP.md — Agent-Executable Setup Guide

This file is written for AI agents. If you are an agent setting up this repo
for a user, follow every step in order. Each step is unambiguous and verifiable.

---

## What this repo does

Generates short AI videos (5.2s mp4 clips, text→video or image→video) for free
using Meta AI Vibes. Exposed as a Claude Code MCP tool and a Python CLI.
No paid API needed. Requires a logged-in Meta AI account.

---

## Prerequisites — check these first

Run these checks. If any fail, install the missing dependency before continuing.

```powershell
# Python 3.10+
python --version

# Node.js (for agent-browser)
node --version

# npm (comes with Node)
npm --version

# ffmpeg on PATH (needed for chained video)
ffmpeg -version

# Google Chrome installed
Test-Path "C:\Program Files\Google\Chrome\Application\chrome.exe"
# If false, check: Test-Path "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
```

---

## Step 1 — Clone or locate the repo

```powershell
# The repo should live at:
$REPO = "C:\Users\$env:USERNAME\Documents\code\meta-ai-api"
Set-Location $REPO
```

---

## Step 2 — Create Python virtual environment and install deps

```powershell
python -m venv venv
venv\Scripts\pip install --upgrade pip
venv\Scripts\pip install mcp websocket-client
```

Verify:
```powershell
venv\Scripts\python -c "import mcp, websocket; print('deps ok')"
```
Expected output: `deps ok`

---

## Step 3 — Install agent-browser globally

```powershell
npm install -g agent-browser
```

Verify:
```powershell
node "$env:APPDATA\npm\node_modules\agent-browser\bin\agent-browser.js" --version
```

---

## Step 4 — Configure environment variables (optional overrides)

Create a `.env` file in the repo root to override defaults. All variables are
optional — the defaults work on a standard Windows + Chrome install.

```env
# .env (gitignored — safe to put real paths here)
META_CDP_PORT=19343
META_CHROME_PROFILE=C:\Users\<YOUR_USERNAME>\AppData\Local\Google\Chrome\Chrome-MetaAI-Vibes
META_CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe
META_ABW_JS=C:\Users\<YOUR_USERNAME>\AppData\Roaming\npm\node_modules\agent-browser\bin\agent-browser.js
META_OUT_DIR=C:\Users\<YOUR_USERNAME>\Documents\meta_clips
```

Replace `<YOUR_USERNAME>` with your Windows username, or omit lines to use defaults.

---

## Step 5 — Log into Meta AI in a dedicated Chrome profile

This step requires a human to log in once. After that, the session persists.

```powershell
# Launch Chrome with a dedicated profile on the CDP port
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$profileDir = "$env:LOCALAPPDATA\Google\Chrome\Chrome-MetaAI-Vibes"
& $chromePath --remote-debugging-port=19343 --user-data-dir="$profileDir" "https://www.meta.ai/create"
```

In the browser that opens:
1. Log into meta.ai with a Meta/Facebook account
2. Confirm you can see the "Create" composer (a text input)
3. Leave the browser open

---

## Step 6 — Save cookies (backup for session recovery)

With Chrome running from Step 5:

```powershell
venv\Scripts\python save_cookies.py
```

Expected output: `Saved ['datr', 'ecto_1_sess'] to cookies.json ...`

If it prints a WARNING about missing cookies, make sure you are fully logged in
to meta.ai in the Chrome window from Step 5.

---

## Step 7 — Verify the setup works

```powershell
# Check the browser is reachable
venv\Scripts\python -c "import launch_meta_browser; print(launch_meta_browser.cdp_alive())"
```
Expected: `True`

```powershell
# Generate a test video (~30-90s)
venv\Scripts\python meta_video.py "a red kite soaring over green hills, cinematic"
```

Expected: JSON output with `"success": true` and an `out_path` pointing to an mp4 file.
Verify the file exists and is > 100KB.

---

## Step 8 — Register as a Claude Code MCP tool

Add this to `~/.claude.json` under `mcpServers` (adjust the path to where you
cloned this repo):

```json
"meta-video": {
  "type": "stdio",
  "command": "C:\\Users\\<YOUR_USERNAME>\\Documents\\code\\meta-ai-api\\venv\\Scripts\\python.exe",
  "args": ["C:\\Users\\<YOUR_USERNAME>\\Documents\\code\\meta-ai-api\\mcp_server.py"]
}
```

Then restart Claude Code. Two new MCP tools will appear:
- `generate_video(prompt, image_path, out_path, timeout)` — generate a video
- `meta_browser_status()` — check if the browser is running

---

## Ongoing maintenance

- **If video generation fails auth:** Re-log into meta.ai in the Chrome profile,
  then run `venv\Scripts\python save_cookies.py` again.
- **If Chrome closes:** Run `venv\Scripts\python launch_meta_browser.py` to restart it.
- **Rate limits:** Don't generate more than ~10 videos/hour. Meta's free tier
  rate-limits heavy use but doesn't publish exact caps.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `cdp_alive()` returns `False` | Run `python launch_meta_browser.py` |
| `agent-browser connect failed` | Check `node` is on PATH; verify `META_ABW_JS` points to the right file |
| `composer textarea never appeared` | meta.ai may have changed its layout; open Chrome manually and confirm the Create page loads |
| `download failed` | The CDN URL expired (Meta clips expire quickly); re-generate |
| `ffmpeg not found` | Install ffmpeg and add it to PATH; required for `generate_chained()` only |
