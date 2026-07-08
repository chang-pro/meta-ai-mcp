"""Direct-attach capture on BOTH meta.ai tabs via two websockets.
Uses the proven direct-page-attach method (not browser-endpoint auto-attach).
Network + Fetch on each. Whatever carries the prompt gets flagged.
Output -> capture_fetch.jsonl
"""
import json
import time
import threading
import urllib.request
import websocket

CDP_PORT = 19343
OUT = r"C:\Users\User\Documents\code\meta-ai-api\capture_fetch.jsonl"
RUN_SECONDS = 150

with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json") as r:
    tabs = [t for t in json.load(r) if t.get("type") == "page" and "meta.ai" in t.get("url", "")]

out = open(OUT, "w", encoding="utf-8")
lock = threading.Lock()
def write(rec):
    with lock:
        out.write(json.dumps(rec) + "\n"); out.flush()

def flag(txt):
    t = txt.lower()
    return "subtle" in t or "cinematic" in t or "animat" in t or "handshake" in t or "old wom" in t

PATTERNS = [
    {"urlPattern": "*meta.ai/api/graphql*", "requestStage": "Request"},
    {"urlPattern": "*rupload.meta.ai/*", "requestStage": "Request"},
]

def watch(tab):
    url_tab = tab["url"]
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"],
                                     suppress_origin=True, max_size=None)
    mid = [0]
    def send(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
    send("Network.enable")
    send("Fetch.enable", {"patterns": PATTERNS})
    print(f"  watching {url_tab[:45]}", flush=True)
    deadline = time.time() + RUN_SECONDS
    while time.time() < deadline:
        try:
            ws.settimeout(2)
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            continue
        except Exception:
            break
        ev = json.loads(raw)
        m = ev.get("method", "")
        p = ev.get("params", {})
        if m == "Fetch.requestPaused":
            req = p.get("request", {})
            u = req.get("url", "")
            pd = req.get("postData", "")
            docid = ""
            try:
                docid = json.loads(pd).get("doc_id", "") if pd.startswith("{") else ""
            except Exception:
                pass
            write({"type": "paused", "tab": url_tab, "url": u, "doc_id": docid,
                   "postDataLen": len(pd), "flagged": flag(pd),
                   "postData": pd if "graphql" in u else "<binary>",
                   "headers": {k: v for k, v in req.get("headers", {}).items()
                               if k.lower() in ("authorization", "x-entity-name",
                                                "x-entity-type", "desired_upload_handler")}})
            fl = "<<<< PROMPT!" if flag(pd) else ""
            print(f"  [{url_tab[-6:]}] PAUSED doc={docid[:12]} len={len(pd)} {fl}", flush=True)
            send("Fetch.continueRequest", {"requestId": p["requestId"]})
        elif m == "Network.requestWillBeSent":
            req = p.get("request", {})
            u = req.get("url", "")
            if "graphql" in u or "rupload" in u:
                pd = req.get("postData", "")
                write({"type": "net", "tab": url_tab, "url": u, "postDataLen": len(pd),
                       "flagged": flag(pd), "postData": pd[:6000]})
                if flag(pd):
                    print(f"  [{url_tab[-6:]}] NET PROMPT {u[:50]}", flush=True)
    try:
        send("Fetch.disable")
    except Exception:
        pass
    ws.close()

print(f"Recording {RUN_SECONDS}s on {len(tabs)} tabs -- GENERATE IN VIBES NOW", flush=True)
threads = [threading.Thread(target=watch, args=(t,)) for t in tabs]
for th in threads:
    th.start()
for th in threads:
    th.join()
out.close()
print(f"\nDone -> {OUT}", flush=True)
