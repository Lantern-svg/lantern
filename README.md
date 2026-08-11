# Lantern

Lantern (Lantern Babel Codex Bridge) is an auditable evidence/belief engine
and inter-instance exchange protocol for AI systems: it tracks *why* a
belief is held, *how strongly*, and *what would change it* — without
collapsing observation into trust.

**The project lives in [`lantern-babel-codex-bridge/`](./lantern-babel-codex-bridge/).**

- Start here: [`lantern-babel-codex-bridge/README.md`](./lantern-babel-codex-bridge/README.md)
- Install and run your own node: [`lantern-babel-codex-bridge/EXTERNAL_BOOTSTRAP.md`](./lantern-babel-codex-bridge/EXTERNAL_BOOTSTRAP.md)
- Architecture and module map: [`lantern-babel-codex-bridge/ARCHITECTURE.md`](./lantern-babel-codex-bridge/ARCHITECTURE.md)

Quick start:

```bash
git clone https://github.com/Lantern-svg/lantern.git
cd lantern/lantern-babel-codex-bridge
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
```

Then follow `EXTERNAL_BOOTSTRAP.md` to start a node and connect a peer.

License: MIT. See [`lantern-babel-codex-bridge/LICENSE`](./lantern-babel-codex-bridge/LICENSE).
