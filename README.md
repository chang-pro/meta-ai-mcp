# meta-ai-api — Meta AI Vibes video generation MCP

Free AI video generation via [Meta AI Vibes](https://www.meta.ai/create), driven
through a real logged-in Chrome and exposed as a Claude Code MCP tool.

Both **text → video** and **image → video** work. ~30–90s per 5.2s clip, no
subscription cost.

## Why browser automation (not a pure-HTTP client)

A pure-HTTP cookie client is not achievable. Meta sends the prompt over its `dgw`
data-gateway **WebSocket as protobuf** (`PROTO_INSIDE_JSON`), invisible to CDP
Network + Fetch interception. Confirmed with a unique-marker capture test and by
independent audit. The old `mir-ashiq/metaai-api` PyPI package is also dead
(GraphQL schema drift).

Browser automation uses the real session, survives Meta schema changes, and carries
the lowest account-flag risk.

## Setup

### 1. Prerequisites

- Python 3.10+
- Node.js (for agent-browser)
- `npm install -g agent-browser`
- Google Chrome installed
- `ffmpeg` on PATH (for chained video concat)

### 2. Install Python deps

```
python -m venv venv
venv/Scripts/pip install mcp websocket-client
```

### 3. Log into Meta AI in a dedicated Chrome profile

```
chrome.exe --remote-debugging-port=19343 \
  --user-data-dir="<some-profile-dir>" \
  https://www.meta.ai/create
```

Log into meta.ai in that browser, then run:

```
venv/Scripts/python save_cookies.py
```

This saves `datr` + `ecto_1_sess` to `cookies.json` (gitignored) as a
recovery backup.

### 4. Environment variables (optional overrides)

| Variable | Default | Purpose |
|---|---|---|
| `META_CDP_PORT` | `19343` | CDP port for the Meta AI Chrome |
| `META_CHROME_PROFILE` | `%LOCALAPPDATA%\Google\Chrome\Chrome-MetaAI-Vibes` | Chrome profile dir |
| `META_CHROME_EXE` | `C:\Program Files\Google\Chrome\Application\chrome.exe` | Chrome executable |
| `META_ABW_JS` | `%APPDATA%\npm\node_modules\agent-browser\bin\agent-browser.js` | agent-browser path |
| `META_OUT_DIR` | `~/Documents/meta_clips` | Output folder for generated mp4s |
| `META_ABW_SESSION` | `metaai-vibes` | agent-browser session name |

### 5. Register as an MCP tool (Claude Code)

Add to `~/.claude.json` under `mcpServers` (adjust paths to your install):

```json
"meta-video": {
  "type": "stdio",
  "command": "/path/to/meta-ai-api/venv/Scripts/python.exe",
  "args": ["/path/to/meta-ai-api/mcp_server.py"]
}
```

Restart Claude Code. The `generate_video`, `generate_image`, and `meta_browser_status` tools will appear.

## Usage

### CLI

```
venv/Scripts/python meta_video.py "prompt text"
venv/Scripts/python meta_video.py "animate this, keep characters consistent" image.png
```

### MCP tools (from Claude Code)

```
generate_video(prompt, image_path="", out_path="", timeout=300)  → {success, out_path, video_url, bytes}
generate_image(prompt, out_path="", timeout=180)                 → {success, out_path, bytes}
meta_browser_status()                                             → {cdp_alive, port, hint}
```

### Images (free)

Meta's reverse-engineered HTTP image API is schema-stale, so `generate_image` drives the same
logged-in `meta.ai/create` browser, waits for the generated image on Meta's AI image CDN
(`t39.105495`), and downloads it **in-page** (fetch → dataURL — no cookie/auth dance):

```python
from meta_image import generate_image
generate_image("a photorealistic Jamaican yard, banana trees, board house, no text", "yard.jpg")
```

> Free image gen is great for scenery/B-roll but can be **loose on specifics** (it renders "generic
> banknotes" when asked for a particular currency). If accuracy matters, judge the result with a
> vision model and fall back to a paid generator — don't assume the first image is right.

### Chained video (beat the 5.2s cap)

```python
from meta_video import MetaVibes
gen = MetaVibes()
res = gen.generate_chained("a red kite soaring over mountains", target_seconds=15, style="cinematic")
```

Each segment is seeded from the last frame of the previous clip for continuous motion.
Styles: `cinematic`, `anime`, `claymation`, `pixar`, `comic`, `realistic`, `flat2d`.

## Files

| File | Purpose |
|---|---|
| `meta_video.py` | Core driver — `MetaVibes` class, text/image→video, chained video, account rotation |
| `meta_image.py` | Free image gen via the browser (reliable capture from Meta's AI image CDN) |
| `mcp_server.py` | FastMCP server exposing `generate_video` + `generate_image` + `meta_browser_status` |
| `launch_meta_browser.py` | Start Chrome on CDP port + inject cookies (idempotent) |
| `save_cookies.py` | Export live cookies from running browser to `cookies.json` |
| `research/` | Reverse-engineering capture scripts (kept for reference) |

## Gotchas

- Clips are 5.2s, ~464×832 or 832×464, h264, with a small **Meta AI watermark** top-right (crop with ffmpeg if needed).
- The composer is a React controlled input — only agent-browser's value-tracker-aware fill enables the Send button. Raw CDP `Runtime.evaluate` leaves it disabled.
- Free tier has no published cap but rate-limits under rapid use. Don't spam it.
- If generation starts failing auth: relog meta.ai in the Chrome profile, then re-run `save_cookies.py`.

## License

See [LICENSE](LICENSE). Source-available, all rights reserved.
Viewing for study/portfolio review is permitted. Use, copying, and derivative works are not.
