"""Attach to the live meta.ai CDP tab and record all GraphQL/video requests.

Run this, THEN generate a video in the browser. It records every graphql
request (url, headers, postData) + media/video responses to capture.jsonl
so we can rebuild a working web-API client from the CURRENT schema.
"""
import json
import time
import urllib.request
import websocket

CDP_PORT = 19343
OUT = r"C:\Users\User\Documents\code\meta-ai-api\capture.jsonl"
RUN_SECONDS = 150

with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json") as r:
    tabs = json.load(r)
target = next(t for t in tabs if "meta.ai" in t.get("url", ""))
print("Attached to:", target["url"])

ws = websocket.create_connection(target["webSocketDebuggerUrl"],
                                 suppress_origin=True, max_size=None)

msg_id = 0
def send(method, params=None):
    global msg_id
    msg_id += 1
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))

send("Network.enable")

requests_seen = {}
out = open(OUT, "w", encoding="utf-8")
deadline = time.time() + RUN_SECONDS
print(f"Recording for {RUN_SECONDS}s. GENERATE A VIDEO NOW...")

interesting = ("graphql", "/api/", "video", "media", "imagine", "vibe", "generate")

while time.time() < deadline:
    try:
        ws.settimeout(2)
        raw = ws.recv()
    except websocket.WebSocketTimeoutException:
        continue
    except Exception:
        break
    ev = json.loads(raw)
    method = ev.get("method")
    p = ev.get("params", {})

    if method == "Network.requestWillBeSent":
        req = p.get("request", {})
        url = req.get("url", "")
        if any(k in url.lower() for k in interesting):
            rid = p.get("requestId")
            friendly = ""
            pd = req.get("postData", "")
            if "fb_api_req_friendly_name=" in pd:
                friendly = pd.split("fb_api_req_friendly_name=")[1].split("&")[0]
            rec = {
                "type": "request", "requestId": rid, "url": url,
                "method": req.get("method"), "friendly_name": friendly,
                "headers": req.get("headers", {}),
                "postData": pd[:20000],
                "hasPostData": req.get("hasPostData", False),
            }
            requests_seen[rid] = friendly or url
            out.write(json.dumps(rec) + "\n"); out.flush()
            print(f"  REQ {friendly or url[:80]}")

    elif method == "Network.responseReceived":
        resp = p.get("response", {})
        url = resp.get("url", "")
        if any(k in url.lower() for k in interesting) or url.endswith(".mp4"):
            rec = {"type": "response", "requestId": p.get("requestId"),
                   "url": url, "status": resp.get("status"),
                   "mimeType": resp.get("mimeType")}
            out.write(json.dumps(rec) + "\n"); out.flush()
            if url.endswith(".mp4") or "video" in resp.get("mimeType", ""):
                print(f"  VIDEO RESP {url[:100]}")

out.close()
ws.close()
print(f"\nDone. {len(requests_seen)} interesting requests captured to {OUT}")
