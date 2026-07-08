"""Definitive prompt-submit capture using the CDP Fetch domain (per Codex).

Network.requestWillBeSent misses bodies for streamed/keepalive requests.
Fetch.enable pauses each graphql request so we see the ACTUAL postData bytes,
then we continueRequest so the page keeps working.

Run, generate ONE image->video. The request carrying your prompt is flagged.
Output -> capture_fetch.jsonl
"""
import json
import time
import urllib.request
import websocket

CDP_PORT = 19343
OUT = r"C:\Users\User\Documents\code\meta-ai-api\capture_fetch.jsonl"
RUN_SECONDS = 150

with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json") as r:
    tabs = json.load(r)
target = next(t for t in tabs if "meta.ai" in t.get("url", ""))
print("Attached:", target["url"], flush=True)

ws = websocket.create_connection(target["webSocketDebuggerUrl"],
                                 suppress_origin=True, max_size=None)
mid = 0
def send(method, params=None):
    global mid
    mid += 1
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    return mid

# Intercept every graphql + rupload request at the Request stage
send("Fetch.enable", {"patterns": [
    {"urlPattern": "*meta.ai/api/graphql*", "requestStage": "Request"},
    {"urlPattern": "*rupload.meta.ai/*", "requestStage": "Request"},
]})

out = open(OUT, "w", encoding="utf-8")
deadline = time.time() + RUN_SECONDS
print(f"Recording {RUN_SECONDS}s via Fetch interception -- GENERATE ONE VIDEO NOW", flush=True)

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
    if ev.get("method") == "Fetch.requestPaused":
        p = ev["params"]
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
               "hasPostData": req.get("hasPostData", False),
               "postDataLen": len(pd), "flagged": is_flag,
               "postData": pd if ("graphql" in url) else "<binary upload>",
               "headers": {k: v for k, v in req.get("headers", {}).items()
                           if k.lower() in ("authorization", "content-type", "x-entity-name",
                                            "x-entity-type", "desired_upload_handler")}}
        out.write(json.dumps(rec) + "\n"); out.flush()
        tag = "graphql" if "graphql" in url else "rupload"
        print(f"  PAUSED {tag} doc_id={docid[:12]} len={len(pd)} {'<<<< PROMPT!' if is_flag else ''}", flush=True)
        # MUST continue or the tab hangs
        send("Fetch.continueRequest", {"requestId": fetch_id})

# disable interception cleanly so the tab isn't left paused
send("Fetch.disable")
out.close(); ws.close()
print(f"\nDone -> {OUT}", flush=True)
