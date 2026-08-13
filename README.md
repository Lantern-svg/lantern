# Lantern

Lantern (Lantern Babel Codex Bridge) is an auditable evidence/belief engine
and inter-instance exchange protocol for AI systems: it tracks *why* a
belief is held, *how strongly*, and *what would change it* — without
collapsing observation into trust.

**The core library lives in [`lantern-babel-codex-bridge/`](./lantern-babel-codex-bridge/).**
**A human-facing conversation harness that wraps it lives in [`lantern-harness/`](./lantern-harness/).**

- Start here: [`lantern-babel-codex-bridge/README.md`](./lantern-babel-codex-bridge/README.md)
- Install and run your own node: [`lantern-babel-codex-bridge/EXTERNAL_BOOTSTRAP.md`](./lantern-babel-codex-bridge/EXTERNAL_BOOTSTRAP.md)
- Architecture and module map: [`lantern-babel-codex-bridge/ARCHITECTURE.md`](./lantern-babel-codex-bridge/ARCHITECTURE.md)
- Want a chat interface instead of using the library directly? See [`lantern-harness/README.md`](./lantern-harness/README.md) — a small, provider-agnostic conversation loop (Ollama, OpenAI, Anthropic, Google, or a custom adapter) that connects to Lantern's evidence/identity/memory layer through a thin adapter, without duplicating any of Lantern's internals.

Quick start (core library):

```bash
git clone https://github.com/Lantern-svg/lantern.git
cd lantern/lantern-babel-codex-bridge
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
```

Then follow `EXTERNAL_BOOTSTRAP.md` to start a node and connect a peer.

License: MIT. See [`LICENSE`](./LICENSE) (repo root; `lantern-harness`'s `pyproject.toml` also declares MIT).
