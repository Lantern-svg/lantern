"""Lantern relay tunnel daemon v2 — transport only, explicit opt-in.

v2 (2026-09-08, B relay-boundary repair; landed 2026-10-01):
  1. IMPORT-SAFE: importing this module performs NO network activity and
     starts NO loop. Execution requires explicit operator opt-in:
         python relay_tunneld.py --run --credential-file /path/to/cred
     or  RELAY_TUNNEL_CREDENTIAL=... python relay_tunneld.py --run
  2. The shared hardcoded relay token is REMOVED. Tunnel authentication
     now uses a per-node scoped relay credential (sha256-verified by the
     relay, revocable). The credential authenticates TRANSPORT SCOPE
     ONLY — it is NOT Lantern cryptographic identity, NOT node
     authorization, and grants nothing the local node would not grant a
     stranger. The local node remains the sole authority layer.
  3. Advertised-route allowlist: only the routes below are forwarded;
     everything else is rejected before any node contact.
  4. Operator visibility: one log line per slot (reject/forward/result),
     no payloads, secrets, or response bodies are ever logged.

Stop: Ctrl-C (SIGINT) or kill the process. Nothing is spawned in the
background; a dead tunnel means no transport, and that fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request

RELAY = "https://zelle-4457b476.base44.app/functions/lanternRelay"
CHANNEL = "claw-ingress"
NODE = "http://127.0.0.1:8767"
POLL_SECONDS = 2.0

# Advertised routes ONLY — (method, exact path). Exact match, case-sensitive;
# query strings, traversal, and encodings all fail the membership test. The
# local node's own session/authorization still applies to every forwarded
# call; this list is a transport boundary, NOT an authority grant.
ALLOWED_ROUTES = {
    ("GET", "/health"),
    ("POST", "/handshake"),
    ("POST", "/session/open"),
    ("POST", "/message"),
    ("POST", "/observation/retrieve"),
    ("POST", "/authorization/request"),
    ("POST", "/secret/offer"),
    ("POST", "/secret/seal"),
    ("POST", "/secret/receipt"),
}


def route_allowed(method, path):
    """Return (allowed, reason). Fail-closed for anything not advertised."""
    method = str(method or "").upper()
    path = str(path or "")
    if (method, path) in ALLOWED_ROUTES:
        return True, ""
    if "?" in path or "#" in path or ".." in path or "%" in path or "\\" in path or path != path.strip():
        return False, "malformed path"
    return False, "route not advertised for relay transport"


def relay(payload, relay_url=RELAY):
    req = urllib.request.Request(
        relay_url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "lantern-relay/1.0"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def call_node(method, path, body, node_url=NODE):
    req = urllib.request.Request(
        node_url + path, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def handle_request(req, credential, relay_url=RELAY, node_url=NODE, log=print):
    """Process one relay slot. Rejections happen BEFORE any node contact."""
    rid = str(req.get("id", ""))
    method = str(req.get("method", ""))
    path = str(req.get("path", ""))
    ok, reason = route_allowed(method, path)
    if not ok:
        log(f"{_now()} REJECT slot={rid} method={method} path={path} reason={reason}")
        relay({"action": "respond", "credential": credential, "id": rid,
               "code": 403, "body": {"error": "RELAY_ROUTE_NOT_ADVERTISED", "reason": reason}})
        return False
    log(f"{_now()} FORWARD slot={rid} method={method} path={path}")
    code, resp = call_node(method, path, req.get("body"), node_url=node_url)
    meta = {
        "sender_node_id": str(req.get("sender_node_id", "")),
        "recipient_node_id": str(req.get("recipient_node_id", "")),
    }
    if path == "/authorization/request":
        meta["authorization_status"] = str(resp.get("status", ""))
    if path == "/message":
        meta["message_status"] = str(resp.get("status", resp.get("received", "")))
    relay({"action": "respond", "credential": credential, "id": rid,
           "code": code, "body": resp, **meta})
    log(f"{_now()} RESULT slot={rid} method={method} path={path} status={code}")
    return True


def poll_once(credential, channel=CHANNEL, relay_url=RELAY, node_url=NODE, log=print):
    nxt = relay({"action": "next", "credential": credential, "channel": channel})
    req = nxt.get("request")
    if req is None:
        return False
    handle_request(req, credential, relay_url=relay_url, node_url=node_url, log=log)
    return True


def _load_credential(args):
    if args.credential:
        return args.credential
    if args.credential_file:
        with open(args.credential_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    env = os.environ.get("RELAY_TUNNEL_CREDENTIAL", "")
    if env:
        return env
    return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lantern relay tunnel (transport only; requires explicit opt-in)")
    ap.add_argument("--run", action="store_true",
                    help="EXPLICIT OPERATOR OPT-IN: actually run the network-active tunnel loop")
    ap.add_argument("--credential", default="", help="per-node relay credential (prefer --credential-file)")
    ap.add_argument("--credential-file", default="", help="file containing the per-node relay credential")
    ap.add_argument("--relay", default=RELAY)
    ap.add_argument("--node", default=NODE)
    ap.add_argument("--channel", default=CHANNEL)
    ap.add_argument("--once", action="store_true", help="poll a single request and exit (test/ops mode)")
    args = ap.parse_args(argv)

    if not args.run:
        print("refusing to start: no --run flag. The relay tunnel is network-active "
              "code; it only runs with an explicit operator opt-in.", file=sys.stderr)
        return 2
    credential = _load_credential(args)
    if not credential:
        print("refusing to start: no relay credential. Provide --credential-file, "
              "--credential, or RELAY_TUNNEL_CREDENTIAL.", file=sys.stderr)
        return 2
    print(f"tunneld up (explicit opt-in): relay={args.relay} node={args.node} channel={args.channel} "
          f"credential_fingerprint={hashlib.sha256(credential.encode()).hexdigest()[:16]}", flush=True)
    try:
        while True:
            try:
                if not poll_once(credential, channel=args.channel, relay_url=args.relay, node_url=args.node):
                    if args.once:
                        break
                    time.sleep(POLL_SECONDS)
                elif args.once:
                    break
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"tunneld error: {exc}", flush=True)
                if args.once:
                    return 1
                time.sleep(5)
    except KeyboardInterrupt:
        print("tunneld stopped by operator (SIGINT).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
