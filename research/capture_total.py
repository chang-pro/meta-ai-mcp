"""TOTAL net capture on both tabs: every request URL + all websocket frames.
Finds where the prompt actually goes. Trigger uses a unique marker word.
Output -> capture_total.jsonl
"""
import json
import time
import threading
import urllib.request
import websocket

CDP_PORT = 19343
OUT = r"C:\Users\User\Documents\code\meta-ai-api\capture_total.jsonl"
RUN_SECONDS = 120
MARKER = "zebrafish"  # unique word we'll put in the prompt

with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json") as r:
    tabs = [t for t in json.load(r) if t.get("type") == "page" and "meta.ai" in t.get("url", "")]

out = open(OUT, "w", encoding="utf-8")
lock = threading.Lock()
def write(rec):
    with lock:
        out.write(json.dumps(rec) + "\n"); out.flush()

def watch(tab):
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"],
                                     suppress_origin=True, max_size=None)
    mid = [0]
    def send(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
    send("Network.enable")
    print(f"  watching {tab['webSocketDebuggerUrl'][-12:]}", flush=True)
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

        if m == "Network.requestWillBeSent":
            req = p.get("request", {})
            u = req.get("url", "")
            pd = req.get("postData", "")
            # log any POST that isn't a static asset, plus anything w/ the marker
            is_asset = any(u.endswith(e) for e in (".js",".css",".png",".jpg",".woff",".woff2",".svg",".ico"))
            if (req.get("method") == "POST" and not is_asset) or MARKER in pd.lower():
                write({"type":"req","url":u,"method":req.get("method"),
                       "postData":pd[:8000],"marker": MARKER in pd.lower()})
                if MARKER in pd.lower():
                    print(f"  >>> MARKER in REQUEST {u[:60]}", flush=True)

        elif m == "Network.webSocketCreated":
            write({"type":"ws_created","url":p.get("url","")})
            print(f"  WS created {p.get('url','')[:60]}", flush=True)

        elif m == "Network.webSocketFrameSent":
            payload = p.get("response",{}).get("payloadData","")
            if MARKER in payload.lower() or len(payload) > 40:
                write({"type":"ws_sent","len":len(payload),"data":payload[:8000],
                       "marker": MARKER in payload.lower()})
                if MARKER in payload.lower():
                    print(f"  >>> MARKER in WS FRAME", flush=True)

    ws.close()

print(f"Recording {RUN_SECONDS}s TOTAL net on {len(tabs)} tabs", flush=True)
threads=[threading.Thread(target=watch,args=(t,)) for t in tabs]
for th in threads: th.start()
for th in threads: th.join()
out.close()
print("Done", flush=True)
