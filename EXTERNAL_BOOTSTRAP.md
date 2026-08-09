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

Pick a `--node-id` that identifies you or your machine (not the person
you're connecting to). Pick a `--data-dir` that's just for this node — don't
point two different nodes at the same folder.

These two things never change, no matter what flags you pass or what a peer
claims:

- Your node will always reject `CODEX_UPDATE` messages.
- Nothing a remote peer sends can directly become belief on your node.
  Only your own local evaluation can do that.

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
  "heartbeat": {"uptime_seconds": ..., ...}
}
```

If `status` is `"ok"`, your node is alive and reachable. `watermark` is your
node's position in its own history — a fresh node starts at `step: 0` and
`chain: "GENESIS"`.

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
public internet. This transport has no authentication, no TLS, and no
replay protection yet — see section 12.

Once you have the peer's address, confirm you can reach it before trying to
exchange anything:

```bash
curl http://PEER_ADDRESS:PEER_PORT/health
curl http://PEER_ADDRESS:PEER_PORT/handshake
```

The handshake response should show a `protocol_version` that matches yours
(`0.82`) and `codex_update: false`.

## 8. Send Your First Observation

This is the actual exchange. From your machine, send one observation to
your peer:

```bash
.venv/bin/python -m lantern.bootstrap_client \
  --node-id alice-lantern-client \
  --peer http://PEER_ADDRESS:PEER_PORT \
  --source alice \
  --content "water freezes near 0 C at sea level" \
  --reliability 0.95 \
  --data-dir ./lantern-client-data
```

Behind the scenes this does four things, in order: checks the peer is
healthy, performs a handshake, checks version/capability compatibility, and
then sends the observation. You'll see the full JSON result printed,
including your peer's response and their updated watermark.

A successful send shows `"accepted": true` and
`"action": "OBSERVATION_CREATED"` inside the `exchange` section of the
output.

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

## 12. Security Warning

This transport is intentionally minimal: plain HTTP, no authentication, no
TLS, no replay protection. That's fine for a private network or a VPN/tunnel
you control, because you're already restricting who can reach the port at
all. It is **not** safe to expose directly to the public internet. If you
bind `--host 0.0.0.0` on a machine with a public IP and no firewall, anyone
who finds the port can call `/health`, `/handshake`, and `/message` on your
node.

None of that changes what a peer can actually do to you, though: a remote
node can send you observations, but it cannot make your Lantern believe
anything, cannot update your Codex, and cannot mutate your local evidence or
belief state. The worst a malicious or careless peer can do over this
transport is fill your Chronicle with observations you never asked for —
which you can always choose to ignore, since receiving is not trusting.

Adding real authentication, TLS, and replay protection is expected before
anyone runs this on a public network, and is intentionally left to the
operator rather than assumed.
