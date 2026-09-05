# REPRODUCE.md — Independent Reproduction Guide

This document lets an independent operator obtain, verify, and exercise the
public Lantern implementation from a clean checkout, without any private
credentials, and without needing access to this session's specific running
processes.

## 1. Obtain the public repository

```bash
git clone https://github.com/Lantern-svg/lantern.git
cd lantern/lantern-babel-codex-bridge
```

The repository is public; this clone requires no authentication.

## 2. Check out the verified commit

```bash
git fetch origin
git checkout f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9   # protocol/capability implementation under test
# or, for the latest documentation on top of it:
git checkout 59335e64728a02f696a26445f883f5058199702a   # deploy/candidate-229756e-reproduction HEAD
```

`master` (`28d12c853eafdab9aeb2f443648b5c0bd0d240df` at time of writing) is
the stable baseline; the commits above live on
`deploy/candidate-229756e-reproduction` and have not yet been merged.

## 3. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Runtime dependency is minimal: `PyNaCl>=1.5.0` (Ed25519/X25519/SecretBox —
all cryptography is audited-library primitives, no homemade crypto). `[dev]`
adds `pytest` and friends for the test suite.

## 4. Create a new Lantern identity and start a node

```bash
python -m lantern.bootstrap_node \
  --host 127.0.0.1 --port 8765 \
  --node-id my-first-lantern-node \
  --data-dir /tmp/my_lantern_data \
  --session-ttl-seconds 900
```

On first run this generates a fresh Ed25519 keypair under
`/tmp/my_lantern_data/identity/my-first-lantern-node/` and persists it —
subsequent restarts with the same `--node-id`/`--data-dir` reload the same
identity rather than generating a new one (`lantern.identity.load_or_create`).

Check it came up:

```bash
curl -s http://127.0.0.1:8765/health | python3 -m json.tool
```

## 5. Understand authorization

The **only** authorization mechanism wired into the running server in this
version is the operator-supplied `--authorize` CLI flag:

```bash
--authorize <peer-node-id>:<capability>[,<capability>...]
```

There is no dynamic or self-issued grant API — a peer can prove its
identity via the Ed25519 challenge/response flow, but it cannot grant
itself any capability. Changing a grant requires restarting the node with
an updated `--authorize` argument (the same mechanism used to create the
grant in the first place).

Real capabilities implemented and enforced in current source:
`evidence_exchange`, `belief_query`, `handshake`, `identity_proof`,
`secret_transfer`. `contradiction_tracking` and `snapshot_exchange` are
advertised in `/health` but have no enforcement endpoint yet.
`codex_update` is architecturally disabled regardless of any grant (see
`bootstrap_node.py`'s secure `/message` handler).

`lantern.peer_authorization` implements a fuller signed-grant/delegation/
recovery ceremony (root authority → bootstrap grant → delegation →
admission), fully tested, but is **not** wired into `bootstrap_node.py`'s
runtime as of this commit — it is a standalone, usable library, not yet
the live authorization source for a running node.

## 6. Run the automated tests

```bash
python -m pytest -q
```

Expected (OBSERVED at commit `f0d3e2976b44d7d1f1c5df86c33dbbd61145cfa9`,
this session): **1102 passed, 3 skipped, 0 failed**, ~90 seconds.

## 7. Reproduce the identity → session → message path locally (two nodes, one machine)

Start a second node in another terminal:

```bash
python -m lantern.bootstrap_node \
  --host 127.0.0.1 --port 8766 \
  --node-id my-second-lantern-node \
  --data-dir /tmp/my_lantern_data_2 \
  --session-ttl-seconds 900 \
  --authorize my-first-lantern-node:evidence_exchange,belief_query
```

Restart the first node too, granting it back:

```bash
--authorize my-second-lantern-node:evidence_exchange,belief_query
```

Then, from Python (or adapt `lantern.connector.LanternConnector` directly):

```python
from lantern.connector import ConnectorConfig, LanternConnector
from lantern.protocol import create_observation_share
from dataclasses import asdict
import json, urllib.request

cfg = ConnectorConfig(remote_url="http://127.0.0.1:8766",
                       node_id="my-first-lantern-node",
                       data_dir="/tmp/my_lantern_data")
conn = LanternConnector(cfg)
conn.health_check()
print(conn.verify_identity(remote_node_id_hint="my-second-lantern-node"))
session = conn.open_session()
print(session)

msg = create_observation_share("my-first-lantern-node",
                                {"content": "hello from a clean checkout",
                                 "source": "my-first-lantern-node",
                                 "reliability": 0.5})
req = urllib.request.Request(
    "http://127.0.0.1:8766/message",
    data=json.dumps({"message": asdict(msg), "session_id": session["session_id"]}).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
print(json.load(urllib.request.urlopen(req)))
```

Expected: `identity_status: CRYPTOGRAPHICALLY_VERIFIED`, a real
`session_id`, and `accepted: true` with a real `observation_id`.

## 8. Reproduce capability enforcement (negative test)

Send a `CODEX_UPDATE` message over the same valid session (see
`lantern.protocol.create_codex_update`) — expect `accepted: false`,
`reason: "secure /message currently only accepts OBSERVATION_SHARE; got 'CODEX_UPDATE'"`,
regardless of any capability grant.

## 9. Reproduce synthetic secret transfer (safe, no real credentials)

```python
import secrets, uuid
from lantern import secret_transfer, identity as identity_module
from pathlib import Path

# Both nodes must be launched with each other's node_id granted
# "secret_transfer" in --authorize for this to succeed.

disposable_secret = ("TEST-" + secrets.token_hex(16)).encode()
transfer_id = str(uuid.uuid4())

# 1. Receiver offers (call /secret/offer on the receiver over a valid session)
# 2. Sender seals against the receiver's returned ephemeral bundle:
identity_dir = identity_module.default_identity_dir(Path("/tmp/my_lantern_data"), "my-first-lantern-node")
sender_identity = identity_module.load_or_create("my-first-lantern-node", identity_dir)
my_ephemeral_private, my_bundle = secret_transfer.create_ephemeral_bundle(
    transfer_id=transfer_id, session_id="<session_id from step 1>",
    from_node_id="my-first-lantern-node", to_node_id="my-second-lantern-node",
    identity=sender_identity)
sealed = secret_transfer.seal_secret(
    my_ephemeral_private=my_ephemeral_private,
    their_ephemeral_public_hex="<receiver's ephemeral_public_key from offer response>",
    session_id="<session_id>", transfer_id=transfer_id, secret=disposable_secret)
# 3. POST {"session_id", "node_id", "transfer_id", "bundle": my_bundle.to_dict(), "sealed": sealed} to /secret/send
```

Compare the receiver's returned `secret_sha256`/`secret_length` against
`hashlib.sha256(disposable_secret).hexdigest()` / `len(disposable_secret)`
computed locally — a match proves correct end-to-end authenticated
decryption without ever transmitting the plaintext back or logging it.

**Never use a real password, credential, API key, cookie, or token as the
test value — always generate a fresh disposable value locally, as shown.**

## No credentials required

Every step above works from a clean checkout with zero external
credentials. The only case requiring infrastructure beyond your own
machine is testing against someone else's already-running node over a
network — that dependency is explicit (you need their real, reachable
endpoint and a real `--authorize` grant from them), not hidden.
