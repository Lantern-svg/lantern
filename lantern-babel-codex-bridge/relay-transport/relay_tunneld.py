import json, time, urllib.request

RELAY = "https://zelle-4457b476.base44.app/functions/lanternRelay"
TOKEN = "lantern-relay-test-2026-09-05"
CHANNEL = "claw-ingress"
NODE = "http://127.0.0.1:8767"

def relay(payload):
    req = urllib.request.Request(
        RELAY, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "lantern-relay/1.0"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def call_node(method, path, body):
    req = urllib.request.Request(
        NODE + path, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

print("tunneld up: relay ->", NODE, "channel", CHANNEL, flush=True)
while True:
    try:
        nxt = relay({"action": "next", "token": TOKEN, "channel": CHANNEL})
        req = nxt.get("request")
        if req is None:
            time.sleep(2.0)
            continue
        code, resp = call_node(req["method"], req["path"], req.get("body"))
        meta = {
            "sender_node_id": req.get("sender_node_id", ""),
            "recipient_node_id": req.get("recipient_node_id", ""),
        }
        if req["path"] == "/authorization/request":
            meta["authorization_status"] = str(resp.get("status", ""))
        if req["path"] == "/message":
            meta["message_status"] = str(resp.get("status", resp.get("received", "")))
        relay({"action": "respond", "token": TOKEN, "id": req["id"],
               "code": code, "body": resp, **meta})
        print("forwarded", req["method"], req["path"], "->", code, flush=True)
    except Exception as exc:
        print("tunneld error:", exc, flush=True)
        time.sleep(5)
