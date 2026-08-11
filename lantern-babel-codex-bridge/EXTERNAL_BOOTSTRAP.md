# Running Your Own Lantern Node

This guide walks you through installing Lantern, starting your own node, and
connecting it to another Lantern so the two can exchange information. It
assumes you're comfortable with a terminal but have never seen the Lantern
code before.

## 1. What Lantern Is

Lantern is a small program that keeps an auditable record of things it's
told ("observations"), and separately keeps track of what it actually
believes, with evidence and confidence attached. Those two things are kept
deliberately apart:

- An **observation** is just "someone told me X." Anyone can send you one.
- **Belief** is what your own Lantern has decided to trust, based on your
  own local evaluation.

Receiving an observation from another Lantern never automatically becomes a
belief on your node. Your Lantern decides that for itself, locally. This is
true even if the sender claims very high confidence.

Every Lantern node keeps its own history (called the **Chronicle**) as a
hash-chained log file, so its record can be checked for tampering later.

## 2. What You Need

- Python 3.10 or newer
- A terminal
- Network access to whichever machine is running the other Lantern (see
  section 7 for what "network access" should mean here)
- No accounts, no API keys, no cloud services

## 3. Install

```bash
git clone <the Lantern repository URL> lantern-babel-codex-bridge
cd lantern-babel-codex-bridge
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

This creates a private Python environment (`.venv`) inside the project
folder and installs Lantern into it, along with the test tools. It does not
touch anything outside this folder, and it does not require `sudo`.

You'll know it worked if the install command finishes without an error and
you can run:

```bash
.venv/bin/python -c "import lantern; print(lantern.__version__ if hasattr(lantern, '__version__') else 'installed')"
```

## 4. Configure Your Node

You don't need a configuration file. Everything is passed as command-line
flags when you start your node:

| Flag | Meaning | Example |
|---|---|---|
| `--node-id` | A name for your node. Yours. | `alice-lantern` |
| `--host` | Which network interface to listen on | `127.0.0.1` or `0.0.0.0` |
| `--port` | Which port to listen on | `8765` |
| `--data-dir` | Where your Chronicle and snapshot files are stored | `./lantern-data` |
| `--authorize` | Explicitly grant a capability to an *already cryptographically verified* peer node id, e.g. `alice-client:evidence_exchange`. Repeatable. Default: no one is authorized for anything. | `--authorize alice-client:evidence_exchange` |
| `--session-ttl-seconds` | How long a verified session stays valid before the peer must re-verify. | `300` (default) |
| `--allow-legacy-message-ingestion` | Opt-in only. Re-enables the old unauthenticated `/message` path with no identity proof and no session. Default: off. See section 7a before using this. | (flag, no value) |

Pick a `--node-id` that identifies you or your machine (not the person
you're connecting to). Pick a `--data-dir` that's just for this node — don't
point two different nodes at the same folder.

These things never change, no matter what flags you pass or what a peer
claims:

- Your node will always reject `CODEX_UPDATE` messages. There is no flag,
  capability, or authorization grant that makes `CODEX_UPDATE` reachable —
  it is structurally blocked in the code, not just policy-blocked.
- Nothing a remote peer sends can directly become belief on your node.
  Only your own local evaluation can do that.
- By default (no `--allow-legacy-message-ingestion`), a peer must prove its
  cryptographic identity and hold an explicit `--authorize` grant from you
  before it can send you anything at all. Self-declared capabilities in a
  request are never sufficient on their own.

## 5. Start Your Node

```bash
.venv/bin/python -m lantern.bootstrap_node \
  --node-id alice-lantern \
  --host 127.0.0.1 \
  --port 8765 \
  --data-dir ./lantern-data
```

Leave this running in its own terminal (or run it in the background). It
will create `./lantern-data` if it doesn't exist yet.

Use `--host 127.0.0.1` if you're only testing on your own machine.
Use `--host 0.0.0.0` if another machine on your private network needs to
reach you — see section 7 before doing this.

## 6. Check Health

In a second terminal, confirm your node is actually running and answering:

```bash
curl http://127.0.0.1:8765/health
```

You should get back something like:

```json
{
  "node_id": "alice-lantern",
  "protocol_version": "0.82",
  "status": "ok",
  "capabilities": {"handshake": true, "evidence_exchange": true, "codex_update": false, ...},
  "watermark": {"step": 0, "chain": "GENESIS"},
  "heartbeat": {"uptime_seconds": ..., ...},
  "legacy_message_ingestion": false,
  "identity_public": {"node_id": "alice-lantern", "public_key_hex": "..."}
}
```

If `status` is `"ok"`, your node is alive and reachable. `watermark` is your
node's position in its own history — a fresh node starts at `step: 0` and
`chain: "GENESIS"`. `legacy_message_ingestion: false` confirms your node is
running in its secure default mode (see section 7a). `identity_public`
is your node's public key — safe to share, never a secret.

## 7. Connect to Another Lantern

To exchange anything with another Lantern, you need the address it's
actually reachable at. Do not guess this — find it directly. In order of
preference:

1. **Same machine** — use `127.0.0.1` and the peer's port. Safest, no
   network configuration needed.
2. **Private LAN** — if you and your peer are on the same private network
   (home, office, private cloud), find your machine's private address
   (`ip -4 addr show` or `hostname -I` on Linux) and share that, not
   `127.0.0.1`.
3. **Private VPN / tunnel** — if you're on different networks, use
   something like Tailscale, WireGuard, or an SSH tunnel, and connect
   through the address that tunnel gives you.

**Do not** put port 8765 (or whatever port you choose) directly on the
public internet. This transport has no TLS and no built-in transport
encryption — see section 12.

Once you have the peer's address, confirm you can reach it before trying to
exchange anything:

```bash
curl http://PEER_ADDRESS:PEER_PORT/health
curl http://PEER_ADDRESS:PEER_PORT/handshake
```

The handshake response should show a `protocol_version` that matches yours
(`0.82`) and `codex_update: false`.

## 7a. Identity, Sessions, and Authorization (secure default)

As of this release, a peer cannot send you an observation just by claiming
it supports `evidence_exchange`. Three separate things all have to be true
first, and they mean different things — don't conflate them:

1. **Cryptographic identity verification** (`/identity/challenge` →
   `/identity/respond` → `/identity/verify`). This proves the peer holds
   the private key matching the public key it claims, using Ed25519
   signatures. It proves *who is talking to you*. It does **not** mean you
   trust them, and it does not grant them anything by itself.
2. **A verified session** (`POST /session/open`). Once a `node_id` has
   passed step 1, it can request a short-lived session token
   (`--session-ttl-seconds`, default 300s). The session proves *this
   specific connection* is still the same verified identity. A session by
   itself still grants zero capabilities.
3. **Explicit authorization** (`--authorize node_id:capability` at node
   startup). Only the operator running the node decides which verified
   node ids may use which capabilities. There is no default grant, and a
   peer cannot request or negotiate its way into a capability it wasn't
   explicitly given.

All three have to line up — verified identity, live session, explicit
authorization — before `/message` will accept anything. `bootstrap_client`
performs steps 1 and 2 automatically as its default workflow; step 3 only
happens if you (the node operator) pass `--authorize` for that client's
node id when you start your node.

### Legacy mode (opt-in only, weaker)

If you pass `--allow-legacy-message-ingestion` when starting your node, it
will also accept the old, pre-verification workflow: a client can send
`/message` with a self-declared `peer_capabilities` block and no identity
proof, no session, and no operator authorization at all. This exists only
for backward compatibility with older deployments and local testing. It is
off by default, must be turned on explicitly, and an operator turning it on
is explicitly choosing to accept unauthenticated observations from anyone
who can reach the port. `bootstrap_client --legacy` is the matching client
flag; without it, the client always uses the secure workflow.

Concretely, this flag reactivates the original, pre-v0.83 acceptance path
verbatim: `lantern.bridge.LanternAgentBridge` and `lantern.router`, gating
acceptance on nothing but negotiated (self-declared) capabilities. It is
**not** a relaxed version of the new identity/session/authorization
pipeline — it is a second, independent code path that predates that
pipeline and never gained any of its checks. Turning on legacy mode does
not weaken the secure pipeline (a session-holding caller is always routed
through the secure path regardless of this flag), but it does mean the
port is, in parallel, running the old unauthenticated implementation for
anyone who doesn't present a session.

### Full HTTP surface

For completeness, every route your node exposes once it's running:

```
GET  /health                        node status, identity, watermark, legacy mode flag
GET  /heartbeat                     uptime/liveness only
GET  /handshake                     protocol/capability advertisement
GET  /participants                  read-only: recorded rendezvous/join claims as-is,
                                     never re-verified here, never authorization
GET  /participants/<id>/next-step   read-only advisory text for a given claim;
                                     does not contact the participant
POST /identity/challenge            issue a fresh identity challenge
POST /identity/respond              respond to a challenge (signed proof)
POST /identity/verify               verify a proof, returns identity_status
POST /session/open                  open a short-lived verified session
POST /join                          rendezvous/announcement (untrusted claim only)
POST /message                       secure path if session_id present; legacy path
                                     only if --allow-legacy-message-ingestion
POST /connection-state              connection/negotiation status
```

`/participants` and `/participants/<id>/next-step` are read-only and never
mutate state or contact a peer — see `src/lantern/participants.py`. They
exist to let you inspect what's been claimed via rendezvous/`/join` without
treating any of it as verified.

## 8. Send Your First Observation

This is the actual exchange. From your machine, send one observation to
your peer. By default this uses the secure workflow described in section
7a — your peer's operator must have already run their node with
`--authorize your-client-node-id:evidence_exchange` or this will be
correctly rejected.

```bash
.venv/bin/python -m lantern.bootstrap_client \
  --node-id alice-lantern-client \
  --peer http://PEER_ADDRESS:PEER_PORT \
  --source alice \
  --content "water freezes near 0 C at sea level" \
  --reliability 0.95 \
  --data-dir ./lantern-client-data
```

Behind the scenes this does five things, in order: checks the peer is
healthy, performs a handshake, verifies your client's identity to the peer
(challenge/respond/verify), opens a verified session, and then sends the
observation over that session. You'll see the full JSON result printed,
including `"mode": "secure"`, the `identity` and `session` outcome, your
peer's response, and their updated watermark.

A successful send shows `"accepted": true` inside the `exchange` section of
the output. If your peer hasn't authorized your node id, you'll instead see
`"accepted": false` with a reason naming the missing capability — that's
the node operator's decision, not something you can talk your way around.

If you need the old unauthenticated behavior against a peer that has opted
into it, add `--legacy` to the command above. Against a peer running with
secure defaults, `--legacy` will be rejected with `LEGACY_MODE_DISABLED`.

## 9. Verify Your Chronicle

If you're the one *receiving* an observation, check that your own node
actually recorded it — don't just trust the network response:

```bash
cat ./lantern-data/YOUR-NODE-ID.jsonl
```

Each line is one event. Right after receiving an observation you should see
exactly one `OBSERVATION_CREATED` entry with the sender's claimed content,
source, and reliability. You will **not** see any evidence or belief event
from this alone — that only happens if you explicitly run your own local
evaluation and call `add_evidence(...)` yourself. Receiving information is
not the same as trusting it, and Lantern keeps that boundary strict on
purpose.

You can also re-check your health endpoint — the `watermark.step` should
have advanced by one for each event recorded.

## 10. Restart / Recovery

Your Chronicle and snapshot files live entirely in `--data-dir`. If you stop
your node and start it again pointed at the same `--data-dir`, it picks up
exactly where it left off — same watermark, same history, same node
identity. Nothing needs to be re-synced or re-negotiated with your peer.

```bash
# stop the node (Ctrl+C, or kill the process)
.venv/bin/python -m lantern.bootstrap_node \
  --node-id alice-lantern \
  --host 127.0.0.1 \
  --port 8765 \
  --data-dir ./lantern-data
curl http://127.0.0.1:8765/health   # watermark should match what it was before you stopped it
```

## 11. Troubleshooting

- **"Connection refused"** — your node (or your peer's) isn't running, or
  you have the wrong port. Confirm with `ps` / `curl .../health` on the
  machine running the node itself first.
- **`/health` works on `127.0.0.1` but not on your private IP** — the node
  was started with `--host 127.0.0.1`. Restart it with `--host 0.0.0.0` to
  listen on all interfaces, then re-check.
- **Peer unreachable from another machine but reachable locally** — this is
  almost always a firewall or security-group rule on the network between
  the two machines, not a Lantern problem. Confirm the port is open between
  the two machines before assuming Lantern is broken.
- **Handshake shows a different `protocol_version`** — the two installs are
  different versions of Lantern. Update whichever one is behind.
- **"Did my observation actually arrive?"** — check the JSON your client
  printed for `"accepted": true`, then independently confirm by reading the
  receiving node's own Chronicle file (section 9). Don't rely on one side's
  word alone.
- **"Where did my observation go?"** — it's an observation, not a belief.
  It's sitting in the receiving node's Chronicle as a record of "someone
  told me this." It stays there until that node's operator decides,
  locally, to evaluate and promote it. Nothing happens to it automatically.
- **"My client got `accepted: false` with a reason mentioning a missing
  capability" (secure mode)** — the peer's operator hasn't run `--authorize
  your-node-id:evidence_exchange` on their node. That's their decision to
  make, not something the client can negotiate around. Ask them to add it,
  or confirm your `--node-id` matches exactly what they authorized.
- **"My client got `LEGACY_MODE_DISABLED`"** — you passed `--legacy`, but
  the peer is running with secure defaults (no
  `--allow-legacy-message-ingestion`). Drop `--legacy` and use the normal
  secure workflow instead.

## 12. Security Warning

Even in the secure default mode, this transport is intentionally minimal:
plain HTTP, no TLS, no transport-layer encryption of any kind. Be precise
about what this does and does not mean:

- **Cryptographic identity verification (section 7a) proves who signed a
  message. It does not encrypt anything.** Ed25519 signatures prove the
  peer controls a specific private key; they say nothing about whether
  anyone else can read the bytes going over the wire.
- **A session ID is an opaque bearer credential, not a signature.** Once
  `/session/open` issues one, presenting that exact string is what proves
  "this request belongs to the same verified session" for the rest of its
  TTL (`--session-ttl-seconds`, default 300s) — the request itself is not
  re-signed or re-proven each time.
- **Anyone who can observe your network path can read a session ID in
  transit**, because the transport is unencrypted HTTP. If they capture it
  within its validity window, they can reuse it to make requests that look
  like they came from the verified session — subject to the existing
  source-binding (`expected_source` must still match), expiry, and replay
  controls (a message replayed via its `message_id` is still rejected by
  the observation ledger), but **not** subject to any check that would
  detect the request came from a different physical sender than the one
  who originally opened the session. Identity verification and session
  issuance do not, by themselves, prevent this — they were never designed
  to provide transport confidentiality, only proof-of-key-control at the
  moment of verification.
- That's an acceptable risk on a private network or a VPN/tunnel you
  control, because you're already restricting who can observe traffic on
  the wire in the first place. It is **not** safe to expose directly to
  the public internet without adding your own transport encryption in
  front of it.

If you bind `--host 0.0.0.0` on a machine with a public IP and no
firewall, anyone who finds the port can call `/health`, `/handshake`, and
the read-only `/participants` routes, and can attempt `/message`,
`/identity/*`, and `/session/open` — though without a private key
matching a node id you've explicitly authorized, they still can't get an
observation accepted unless you've turned on
`--allow-legacy-message-ingestion`.

If you do turn on `--allow-legacy-message-ingestion`, you are explicitly
opting back into the old, weaker model: any peer who can reach the port can
send you an observation with zero identity proof, whatever
`peer_capabilities` it claims for itself. Only turn this on for a trusted,
private network, or for local testing, never on a public-facing port.

None of the above changes what a peer can actually do to you at the belief
layer, in either mode: a remote node can send you observations, but it
cannot make your Lantern believe anything, cannot update your Codex
(`CODEX_UPDATE` is structurally blocked, not just policy-blocked — no
authorization grant can reach it), and cannot mutate your local evidence or
belief state. The worst a peer can do, even one you've explicitly
authorized for `evidence_exchange`, is add entries to your Chronicle that
you can always choose to ignore — receiving is not trusting.

Adding real transport encryption (TLS) is expected before anyone runs this
on a public network, and is intentionally left to the operator (e.g. a
reverse proxy or VPN/tunnel terminating TLS in front of the node) rather
than assumed by Lantern itself. TLS is what would actually close the
session-ID-observation gap described above; identity verification alone
does not and cannot.
