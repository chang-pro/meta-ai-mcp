"""Browser-level Fetch interception across ALL meta.ai tabs (create + vibes).

Fix vs v1: attach at the browser endpoint, auto-attach to every page target,
enable Fetch on each, and route continueRequest back with the right sessionId.
Verifies Fetch.enable succeeds (prints errors) so we know interception is live.

Run, generate ONE video in EITHER tab. Prompt-carrying request is flagged.
Output -> capture_fetch.jsonl
"""
import json
import time
import urllib.request
import websocket

CDP_PORT = 19343
OUT = r"C:\Users\User\Documents\code\meta-ai-api\capture_fetch.jsonl"
RUN_SECONDS = 150

with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json/version") as r:
    browser_ws = json.load(r)["webSocketDebuggerUrl"]
print("Browser endpoint:", browser_ws, flush=True)

ws = websocket.create_connection(browser_ws, suppress_origin=True, max_size=None)
mid = 0
def send(method, params=None, session_id=None):
    global mid
    mid += 1
    msg = {"id": mid, "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    ws.send(json.dumps(msg))
    return mid

PATTERNS = [
    {"urlPattern": "*meta.ai/api/graphql*", "requestStage": "Request"},
    {"urlPattern": "*rupload.meta.ai/*", "requestStage": "Request"},
]

# Auto-attach to all current + future targets (incl. workers), flattened
send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False,
                              "flatten": True})

out = open(OUT, "w", encoding="utf-8")
deadline = time.time() + RUN_SECONDS
sessions = {}   # sessionId -> targetInfo url
enabled_ids = {}  # msg id of Fetch.enable -> sessionId (to check success)
print(f"Recording {RUN_SECONDS}s (ALL tabs) -- GENERATE ONE VIDEO NOW", flush=True)

def flag(txt):
    t = txt.lower()
    return "subtle" in t or "cinematic" in t or "animat" in t or "handshake" in t

while time.time() < deadline:
    try:
        ws.settimeout(2)
        raw = ws.recv()
    except websocket.WebSocketTimeoutException:
        continue
    except Exception as e:
        print("recv err:", e, flush=True)
        break
    ev = json.loads(raw)
    m = ev.get("method", "")
    p = ev.get("params", {})
    sid = ev.get("sessionId")

    if m == "Target.attachedToTarget":
        ti = p.get("targetInfo", {})
        s = p.get("sessionId")
        if ti.get("type") in ("page", "service_worker", "worker"):
            sessions[s] = ti.get("url", "")
            i = send("Fetch.enable", {"patterns": PATTERNS}, session_id=s)
            enabled_ids[i] = (s, ti.get("url", ""))
            send("Network.enable", session_id=s)
            print(f"  attached {ti.get('type')} {ti.get('url','')[:45]} -> Fetch+Network", flush=True)

    elif ev.get("id") in enabled_ids:
        s, url = enabled_ids.pop(ev["id"])
        if "error" in ev:
            print(f"  !! Fetch.enable FAILED for {url[:40]}: {ev['error']}", flush=True)
        else:
            print(f"  Fetch LIVE on {url[:45]}", flush=True)

    elif m == "Fetch.requestPaused":
        fetch_id = p["requestId"]
        req = p.get("request", {})
        url = req.get("url", "")
        pd = req.get("postData", "")
        docid = ""
        try:
            docid = json.loads(pd).get("doc_id", "") if pd.startswith("{") else ""
        except Exception:
            pass
        is_flag = flag(pd)
        rec = {"type": "paused", "url": url, "doc_id": docid,
               "postDataLen": len(pd), "flagged": is_flag,
               "postData": pd if "graphql" in url else "<binary upload>",
               "headers": {k: v for k, v in req.get("headers", {}).items()
                           if k.lower() in ("authorization", "content-type",
                                            "x-entity-name", "x-entity-type",
                                            "desired_upload_handler")}}
        out.write(json.dumps(rec) + "\n"); out.flush()
        tag = "graphql" if "graphql" in url else "rupload"
        print(f"  PAUSED {tag} doc_id={docid[:12]} len={len(pd)} {'<<<< PROMPT!' if is_flag else ''}", flush=True)
        send("Fetch.continueRequest", {"requestId": fetch_id}, session_id=sid)

    elif m == "Network.requestWillBeSent":
        req = p.get("request", {})
        url = req.get("url", "")
        if "graphql" in url or "rupload" in url:
            pd = req.get("postData", "")
            rec = {"type": "net", "url": url, "postDataLen": len(pd),
                   "flagged": flag(pd), "postData": pd[:6000],
                   "hasPostData": req.get("hasPostData", False)}
            out.write(json.dumps(rec) + "\n"); out.flush()
            if flag(pd):
                print(f"  NET CARRIES PROMPT: {url[:60]}", flush=True)

for s in sessions:
    send("Fetch.disable", session_id=s)
out.close(); ws.close()
print(f"\nDone -> {OUT}", flush=True)
