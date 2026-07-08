import json
import base64
import urllib.request
import websocket

CDP_PORT = 19343
OUT = r"C:\Users\User\AppData\Local\Temp\claude\C--Users-User\a96aa43c-4731-4cc0-84e0-65cd1764f68e\scratchpad\metaai_page.png"

with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json") as r:
    tabs = json.load(r)

target = next(t for t in tabs if "meta.ai" in t.get("url", ""))
ws = websocket.create_connection(target["webSocketDebuggerUrl"], suppress_origin=True)

msg_id = 1
ws.send(json.dumps({"id": msg_id, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
while True:
    resp = json.loads(ws.recv())
    if resp.get("id") == msg_id:
        break

data = base64.b64decode(resp["result"]["data"])
with open(OUT, "wb") as f:
    f.write(data)
print("saved", OUT, "url:", target["url"], "title:", target.get("title"))
ws.close()
