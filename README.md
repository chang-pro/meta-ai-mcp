# meta-ai-mcp — Free Meta AI image generation + prompting

Generate images and run AI prompts for free using a real logged-in Meta AI browser session.
No API key. No subscription. No credits.

Exposes two live tools via Claude Code MCP:

| Tool | What it does |
|---|---|
| `generate_image` | Free image generation via meta.ai/create |
| `ask_meta` | Free AI chat/prompting (Meta AI = Llama 4) |
| `meta_browser_status` | Check if the Chrome session is alive |

> **Note:** Meta AI Vibes (video generation at meta.ai/vibes) was discontinued. The
> `generate_video` tool is kept for reference but will likely not work.

## Why browser automation

Meta's image and chat APIs are either private, protobuf-encoded over a WebSocket, or
schema-stale. The only reliable approach is driving the real browser session:
- Survives Meta UI changes better than a reverse-engineered HTTP client
- Uses your real logged-in account (no token dance, no auth headers to reverse-engineer)
- The same pattern as [linkedin-mcp](https://github.com/chang-pro/linkedin-mcp)

## Setup

### 1. Install prerequisites

- Python 3.10+
- Node.js + `npm install -g agent-browser`
- Google Chrome
- `pip install mcp websocket-client` (inside a venv)

### 2. Start a dedicated Chrome with CDP

```bash
# Windows
chrome.exe --remote-debugging-port=19343 ^
  --user-data-dir="%LOCALAPPDATA%\Google\Chrome\Chrome-MetaAI" ^
  https://www.meta.ai/

# Mac / Linux
google-chrome --remote-debugging-port=19343 \
  --user-data-dir="$HOME/.chrome-meta-ai" \
  https://www.meta.ai/
```

Log into meta.ai in that browser window. Then save cookies as a backup:

```bash
venv/Scripts/python save_cookies.py   # Windows
# or
venv/bin/python save_cookies.py       # Mac/Linux
```

### 3. Register in Claude Code (`~/.claude.json`)

```json
"mcpServers": {
  "meta-ai": {
    "type": "stdio",
    "command": "/absolute/path/to/meta-ai-api/venv/Scripts/python.exe",
    "args": ["/absolute/path/to/meta-ai-api/mcp_server.py"]
  }
}
```

Restart Claude Code. The `generate_image`, `ask_meta`, and `meta_browser_status` tools appear.

## Usage

### Free image generation

```
generate_image("a photorealistic Jamaican yard, banana trees, golden hour")
→ { success: true, out_path: "~/Documents/meta_images/a_photorealistic_ja.jpg", bytes: 184320 }
```

From Python directly:
```python
from meta_image import generate_image
generate_image("a futuristic cityscape at night, neon reflections", "city.jpg")
```

### Free AI prompting

```
ask_meta("What are the best strategies for viral short-form video content?")
→ { success: true, response: "Here are the top strategies...", chars: 1240 }
```

No token limits, no API cost — runs through your real Meta AI session (Llama 4).

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `META_CDP_PORT` | `19343` | CDP port for the Meta AI Chrome |
| `META_IMG_DIR` | `~/Documents/meta_images` | Output folder for generated images |
| `META_OUT_DIR` | `~/Documents/meta_clips` | Output folder for video (deprecated) |
| `META_CHROME_PROFILE` | `%LOCALAPPDATA%\Google\Chrome\Chrome-MetaAI` | Chrome profile dir |
| `META_ABW_JS` | auto-detected | Path to agent-browser.js |
| `META_ABW_SESSION` | `metaai-vibes` | agent-browser session name |

## Files

| File | Purpose |
|---|---|
| `mcp_server.py` | FastMCP server — `generate_image`, `ask_meta`, `meta_browser_status`, `generate_video` (deprecated) |
| `meta_image.py` | Free image gen — drives meta.ai/create, captures from Meta's AI image CDN |
| `meta_chat.py` | Free chat prompting — drives meta.ai chat, captures the AI response |
| `meta_video.py` | Video gen driver (deprecated — meta.ai/vibes shut down) |
| `launch_meta_browser.py` | Start Chrome on CDP port + inject cookies (idempotent) |
| `save_cookies.py` | Export live cookies from running browser to `cookies.json` |
| `test_edge_cases.py` | Offline edge-case suite (mocked browser) — `venv/Scripts/python test_edge_cases.py` |

## Gotchas

- **Image quality**: Meta AI image generation is great for B-roll and scenery but loose
  on specifics (e.g. "generic banknotes" when asked for a particular currency). Judge
  results with a vision model if accuracy matters.
- **Rate limits**: Meta has no published cap but rate-limits under rapid use. Don't spam it.
- **Session expiry**: If tools start failing auth, re-log into meta.ai in the Chrome profile
  and run `save_cookies.py` again.
- **React inputs**: Meta's composer is a React controlled input. The agent-browser fill
  is required to enable the Send button. Raw CDP `Runtime.evaluate` leaves it disabled.

## Credits

Built by [chang-pro](https://github.com/chang-pro).
If you use this, please credit the repo. See [LICENSE](LICENSE) for terms.

## License

Source-available — all rights reserved. See [LICENSE](LICENSE).
You may view and study this code. Use, redistribution, and derivative works require
explicit written permission from the author.
