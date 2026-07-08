"""Ensure the Meta AI Vibes Chrome (CDP 19343, profile Chrome-MetaAI-Vibes) is
running and logged in. Idempotent: safe to run repeatedly.

Cookies live in cookies.json (gitignored). Regenerate by exporting fresh
datr + ecto_1_sess from a logged-in meta.ai browser session.
Registry: browser-registry.md port 19343.
"""
import json
import os
import subprocess
import time
import urllib.request

CDP_PORT = int(os.environ.get("META_CDP_PORT", "19343"))
PROFILE = os.environ.get(
    "META_CHROME_PROFILE",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Chrome-MetaAI-Vibes"))
def _find_chrome():
    candidates = [
        os.environ.get("META_CHROME_EXE", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return "chrome"  # fall back to PATH

CHROME = _find_chrome()
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.json")


def cdp_alive():
    try:
        with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version", timeout=3):
            return True
    except Exception:
        return False


def launch():
    """Ensure Chrome 19343 is up. Returns 'already running', 'launched', or 'failed'.
    On a fresh start, (re)injects cookies from cookies.json so an expired
    profile session self-heals (setCookie is idempotent; cookies.json is kept
    fresh by save_cookies.py)."""
    if cdp_alive():
        return "already running"
    subprocess.Popen([CHROME, f"--remote-debugging-port={CDP_PORT}",
                      f"--user-data-dir={PROFILE}", "--no-first-run",
                      "--no-default-browser-check", "https://www.meta.ai/create"])
    for _ in range(20):
        if cdp_alive():
            # fresh start -> refresh cookies from backup, regardless of profile age
            try:
                inject_cookies()
            except Exception:
                pass
            return "launched"
        time.sleep(1)
    return "failed"


def inject_cookies():
    """Inject cookies from cookies.json into the running browser (first boot)."""
    if not os.path.exists(COOKIES_FILE):
        return "no cookies.json - assuming profile already logged in"
    import websocket
    cookies = json.load(open(COOKIES_FILE))
    with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version") as r:
        ws_url = json.load(r)["webSocketDebuggerUrl"]
    ws = websocket.create_connection(ws_url, suppress_origin=True)
    mid = 0
    def send(method, params):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == mid:
                return r
    for name, value in cookies.items():
        send("Network.setCookie", {"name": name, "value": value,
                                   "domain": ".meta.ai", "path": "/"})
    ws.close()
    return f"injected {len(cookies)} cookies"


if __name__ == "__main__":
    print(launch())   # launch() now injects cookies itself on a fresh start
    print("CDP 19343 ready:", cdp_alive())
