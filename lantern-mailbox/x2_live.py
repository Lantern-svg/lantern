"""Live X2: expired fetch challenge against the deployed service.
Binds a fresh mailbox, gets a challenge, waits the real TTL, then fetches."""
import json, time, os, sys
os.environ["MAILBOX_LIVE_URL"] = "https://vesper-f402303b.base44.app/functions/lanternMailbox"
from mailbox_client import Rpc, Instance, _now
tag = sys.argv[1]
rpc = Rpc()
inst = Instance(f"x2-probe-{tag}")
b = inst.bind(rpc)
fb = inst.fetch_begin(rpc)
print(json.dumps({"stage": "bound+challenge", "bind": b["body"], "challenge_expires": fb["body"]["expires_ms"]}), flush=True)
time.sleep(605)
r = inst.fetch(rpc, fb["body"]["challenge_id"])
print(json.dumps({"stage": "expired_fetch", "status": r["status"], "body": r["body"]}), flush=True)
