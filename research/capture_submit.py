"""Definitive capture of the meta.ai prompt-SUBMIT step.

Records THREE things the earlier POST-only capture missed:
  1. WebSocket frames sent/received (Network.webSocketFrameSent/Received)
  2. EventSource / streaming responses
  3. Full request bodies for EVERY graphql + realtime request (not just POSTs)

Run this, generate ONE image->video, then we find which channel carries the prompt.
Everything -> capture_submit.jsonl
"""
import json
import time
import urllib.request
import websocket

CDP_PORT = 19343
OUT = r"C:\Users\User\Documents\code\meta-ai-api\capture_submit.jsonl"
RUN_SECONDS = 150
PROMPT_HINT = ""  # optional substring of your prompt to flag the carrying frame

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

send("Network.enable")
send("Page.enable")

out = open(OUT, "w", encoding="utf-8")
deadline = time.time() + RUN_SECONDS
print(f"Recording {RUN_SECONDS}s (WS frames + all bodies) -- GENERATE ONE VIDEO NOW", flush=True)

def flag(txt):
    return "subtle" in txt.lower() or "cinematic" in txt.lower() or "prompt" in txt.lower() or (PROMPT_HINT and PROMPT_HINT.lower() in txt.lower())

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

    if m == "Network.webSocketFrameSent":
        payload = p.get("response", {}).get("payloadData", "")
        rec = {"type": "ws_sent", "len": len(payload), "data": payload[:8000]}
        out.write(json.dumps(rec) + "\n"); out.flush()
        print(f"  WS_SENT len={len(payload)} {'<<PROMPT?' if flag(payload) else ''}", flush=True)

    elif m == "Network.webSocketFrameReceived":
        payload = p.get("response", {}).get("payloadData", "")
        if flag(payload) or "video" in payload.lower():
            rec = {"type": "ws_recv", "len": len(payload), "data": payload[:8000]}
            out.write(json.dumps(rec) + "\n"); out.flush()
            print(f"  WS_RECV len={len(payload)} {'<<PROMPT?' if flag(payload) else ''}", flush=True)

    elif m == "Network.webSocketCreated":
        rec = {"type": "ws_created", "url": p.get("url", "")}
        out.write(json.dumps(rec) + "\n"); out.flush()
        print(f"  WS_CREATED {p.get('url','')[:80]}", flush=True)

    elif m == "Network.requestWillBeSent":
        req = p.get("request", {})
        url = req.get("url", "")
        pd = req.get("postData", "")
        if "graphql" in url or "rupload" in url or flag(pd):
            rec = {"type": "req", "url": url, "method": req.get("method"),
                   "postData": pd, "flagged": flag(pd)}
            out.write(json.dumps(rec) + "\n"); out.flush()
            if flag(pd):
                print(f"  REQ CARRIES PROMPT: {url[:70]}", flush=True)

    elif m == "Network.eventSourceMessageReceived":
        data = p.get("data", "")
        if flag(data) or "video" in data.lower():
            rec = {"type": "sse", "eventName": p.get("eventName"), "data": data[:8000]}
            out.write(json.dumps(rec) + "\n"); out.flush()
            print(f"  SSE {p.get('eventName')} {'<<PROMPT?' if flag(data) else ''}", flush=True)

out.close(); ws.close()
print(f"\nDone -> {OUT}", flush=True)
