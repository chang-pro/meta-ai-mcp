"""Snapshot the current meta.ai cookies from the live logged-in Chrome (CDP 19343)
into cookies.json. Run this whenever the browser is freshly logged in so the
bootstrap backup stays current. Answers "do we make cookies": we EXPORT them
from the real session rather than hand-copying from devtools.

Usage:  venv/Scripts/python save_cookies.py
"""
import json
import os
import urllib.request
import websocket

CDP_PORT = int(os.environ.get("META_CDP_PORT", "19343"))
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.json")
# the cookies that actually matter for auth + the challenge handshake
WANT = ("datr", "ecto_1_sess", "dpr", "wd", "rd_challenge")


def main():
    with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version") as r:
        ws_url = json.load(r)["webSocketDebuggerUrl"]
    ws = websocket.create_connection(ws_url, suppress_origin=True, max_size=None)
    ws.settimeout(10)
    ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
    while True:
        resp = json.loads(ws.recv())
        if resp.get("id") == 1:
            break
    ws.close()

    cookies = resp.get("result", {}).get("cookies", [])
    meta = {c["name"]: c["value"] for c in cookies
            if c["name"] in WANT and c.get("domain", "").endswith("meta.ai")}

    if "ecto_1_sess" not in meta or "datr" not in meta:
        print("WARNING: core cookies (datr/ecto_1_sess) not found — is the browser "
              "logged into meta.ai? Not overwriting cookies.json.")
        print("Found:", list(meta.keys()))
        return

    # keep only the two the bootstrap injector needs, but log all found
    save = {k: meta[k] for k in ("datr", "ecto_1_sess") if k in meta}
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        json.dump(save, f, indent=2)
    print(f"Saved {list(save.keys())} to cookies.json (also saw: {list(meta.keys())})")


if __name__ == "__main__":
    main()
