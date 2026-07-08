"""Capture ALL POST requests (full body, every host) from the live meta.ai tab.
Also grabs graphql RESPONSE bodies via Fetch domain so we see the video URL + card ids.
Run, then generate ONE video. Everything lands in capture_all.jsonl.
"""
import json
import time
import urllib.request
import websocket

CDP_PORT = 19343
OUT = r"C:\Users\User\Documents\code\meta-ai-api\capture_all.jsonl"
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

send("Network.enable")
out = open(OUT, "w", encoding="utf-8")
bodies_wanted = {}   # requestId -> url for graphql responses we want bodies of
deadline = time.time() + RUN_SECONDS
print(f"Recording {RUN_SECONDS}s -- GENERATE A VIDEO NOW", flush=True)
npost = 0
pending = {}  # id -> requestId, for getResponseBody replies

while time.time() < deadline:
    try:
        ws.settimeout(2)
        raw = ws.recv()
    except websocket.WebSocketTimeoutException:
        continue
    except Exception:
        break
    ev = json.loads(raw)
    m = ev.get("method")
    p = ev.get("params", {})

    if m == "Network.requestWillBeSent":
        req = p.get("request", {})
        if req.get("method") == "POST":
            npost += 1
            url = req.get("url", "")
            rec = {"type": "post", "requestId": p.get("requestId"),
                   "url": url, "postData": req.get("postData", ""),
                   "hasPostData": req.get("hasPostData", False),
                   "headers": req.get("headers", {})}
            out.write(json.dumps(rec) + "\n"); out.flush()
            tag = url.split("meta.ai")[-1][:50] if "meta.ai" in url else url[:50]
            print(f"  POST {tag} bodylen={len(req.get('postData',''))}", flush=True)

    elif m == "Network.responseReceived":
        resp = p.get("response", {})
        url = resp.get("url", "")
        if "graphql" in url or url.endswith(".mp4") or "video" in resp.get("mimeType",""):
            bodies_wanted[p.get("requestId")] = url
            rec = {"type": "resp", "requestId": p.get("requestId"), "url": url,
                   "status": resp.get("status"), "mime": resp.get("mimeType")}
            out.write(json.dumps(rec) + "\n"); out.flush()
            if url.endswith(".mp4"):
                print(f"  >>> MP4 {url[:110]}", flush=True)

    elif m == "Network.loadingFinished":
        rid = p.get("requestId")
        if rid in bodies_wanted:
            i = send("Network.getResponseBody", {"requestId": rid})
            pending[i] = bodies_wanted.pop(rid)

    elif ev.get("id") in pending:
        url = pending.pop(ev["id"])
        body = ev.get("result", {}).get("body", "")
        rec = {"type": "respbody", "url": url, "body": body[:60000]}
        out.write(json.dumps(rec) + "\n"); out.flush()

out.close(); ws.close()
print(f"\nDone. {npost} POSTs captured -> {OUT}", flush=True)
