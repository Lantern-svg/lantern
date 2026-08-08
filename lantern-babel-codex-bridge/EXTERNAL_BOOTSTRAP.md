# External Lantern Bootstrap

This is the smallest runnable process boundary for the current Basic Lantern
Protocol. It adds HTTP transport only. The protocol message, compatibility
rules, handshake, capability registry, boundary, router, bridge, agent, core,
Chronicle, and snapshot behavior remain the existing implementation.

The first transport is intentionally development-grade HTTP:

- `ProtocolMessage` is sent as its existing JSON object.
- The HTTP request envelope carries `peer_capabilities`, because capabilities
  are negotiated during handshake and are not part of the message schema.
- The receiver validates message shape, then delegates version policy to
  `compatibility.negotiate()`.
- The receiver stores an observation but does not create Evidence from a remote
  confidence claim. Evidence promotion remains a local decision.
- Chronicle and snapshots belong to the receiving node's `--data-dir`.

Do not expose this adapter directly to the public internet without the
operator's TLS, authentication, firewall, and rate-limit controls. It binds to
`127.0.0.1` by default. `--host 0.0.0.0` is for a controlled development
network or a private tunnel.

## Install

Each operator uses a fresh checkout and virtual environment:

```bash
git clone <LANtern-repository-url> lantern-babel-codex-bridge
cd lantern-babel-codex-bridge
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The bootstrap adapter uses only the Python standard library in addition to the
installed Lantern package.

## Start Lantern B

On the external operator's machine:

```bash
cd lantern-babel-codex-bridge
.venv/bin/python -m lantern.bootstrap_node \
  --node-id lantern-b \
  --host 0.0.0.0 \
  --port 8766 \
  --data-dir .lantern
```

The node prints its protocol version, capabilities, and current continuity
watermark. Its identity and history persist in `.lantern/lantern-b.jsonl` and
`.lantern/lantern-b.jsonl.snapshot.json`.

For a same-machine smoke test, use `--host 127.0.0.1`.

## Verify B Identity

From Lantern A's machine, replace the hostname with the reachable address of B:\n\n```bash\ncurl http://B_HOST:8766/health
curl http://B_HOST:8766/handshake
```

The response must show protocol `0.82`, `evidence_exchange: true`, and
`codex_update: false`.

## Send One Observation From Lantern A

Lantern A is an independently operated client process with its own node ID and
local Chronicle directory:

```bash
cd lantern-babel-codex-bridge
.venv/bin/python -m lantern.bootstrap_client \
  --node-id lantern-a \
  --peer http://B_HOST:8766 \
  --source operator-a \
  --content "water freezes near 0 C at sea level" \
  --reliability 0.95 \
  --data-dir .lantern-a
```

The client performs, in order:

1. B identity discovery.
2. A handshake request to B.
3. Compatibility and capability negotiation.
4. An `OBSERVATION_SHARE` using the existing `ProtocolMessage`.
5. Receipt of B's result, including source, protocol, message type, and B's
   updated watermark.

A successful exchange returns `accepted: true` and
`action: "OBSERVATION_CREATED"`.

## Local Evaluation On B

Receiving an observation does not create Evidence. That is deliberate:

```python
from lantern.agent import LanternAgent
from lantern.core import Lantern

agent = LanternAgent(Lantern(chronicle_filename=".lantern/lantern-b.jsonl"))
```

The operator may inspect the received observation, apply local evaluation, and
only then call `agent.add_evidence(concept, observation_id, weight, sign)`.
Remote reliability/confidence is not automatically promoted to local belief.
`CODEX_UPDATE` is disabled and rejected by the receiver's capability policy.

## Rejection Checks

The transport tests cover:

- different major protocol version: rejected by compatibility
- missing `evidence_exchange`: rejected by the router before the agent
- malformed message shape: HTTP 400, no kernel mutation
- `CODEX_UPDATE`: rejected because `codex_update` is false
- remote confidence/reliability: observation only, zero Evidence created

Run the full verification suite:

```bash
.venv/bin/python -m pytest -q
```

## Current Boundary

This is ready for the first controlled external participant over a private
network or tunnel. It is not a production public service: TLS, authentication,
peer authorization, replay protection at the HTTP transport layer, and a
multi-hop deployment policy are still operator responsibilities. No core
rewrite is required to validate the first external Lantern connection.
