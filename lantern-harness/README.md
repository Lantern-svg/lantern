# Lantern Harness

## What Lantern is

Lantern (`lantern-babel-codex-bridge`) is an auditable evidence/belief
engine and inter-instance exchange protocol. It gives an AI system
persistent, hash-chained evidence tracking, contradiction detection,
cryptographic node identity, and a capability-authorization boundary.
Lantern by itself is a Python **library** — it has no chat interface,
no reasoning engine, and no `main.py`.

## What this harness is

This harness (`lantern-harness`) is the missing human-facing layer: a
small, provider-agnostic conversation loop that connects a reasoning
engine of your choice (Ollama, OpenAI, Anthropic, Google, or a custom
adapter) to Lantern's evidence/identity/memory layer through a thin
`LanternBridge` adapter. It does not duplicate or reimplement any of
Lantern's internals.

## How they relate

```
USER -> LANTERN INTERFACE (this harness) -> REASONING ENGINE -> LANTERN CORE (real lantern package)
```

The harness never asserts model output as verified external fact, and
it never treats reasoning-engine availability as evidence about
Lantern's own state.

## Install

Requires Python >= 3.10.

```bash
git clone <this-repo>
cd lantern-babel-codex-bridge
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd ../lantern-harness
../lantern-babel-codex-bridge/.venv/bin/python -m pytest tests/ -q
```

If `lantern` is not importable, `main.py` will report exactly that and
stop — it will not fabricate a working session.

## Choose a model

Edit `config/config.json`:

```json
{
  "reasoning_engine": {
    "provider": "ollama",
    "model": "llama3.1",
    "ollama_host": "http://localhost:11434"
  }
}
```

Supported `provider` values: `ollama`, `openai`, `anthropic`, `google`,
or `none` (default — the harness runs with no reasoning engine and
tells you so at every message).

For API providers, set the corresponding environment variable before
running (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`). Keys
are read directly from the environment at call time and are never
written to Lantern's Chronicle, evidence, witness ledger, or any file
in this repo.

## Start

```bash
../lantern-babel-codex-bridge/.venv/bin/python main.py
```

## Inspect status

Type `/status` at the `You:` prompt, or run the same check
non-interactively:

```bash
../lantern-babel-codex-bridge/.venv/bin/python -c "
from lantern_harness.bootstrap import bootstrap, format_bootstrap_report
print(format_bootstrap_report(bootstrap()))
"
```

## Commands

`/status` `/memory` `/identity` `/tools` `/branches` `/exit`

(`/history`, `/beliefs`, `/evidence`, `/projects` are recognized but
not yet implemented as formatted views in this version — see
`KNOWN_LIMITATIONS` in the harness status report.)

## Configure tools

Tools are registered programmatically via
`lantern_harness.tools.boundary.ToolBoundary` — none are registered by
default. Tool discovery never implies authorization; call
`boundary.authorize(name)` explicitly before a tool can execute.

## Create a project

`projects/` is a plain workspace directory for your own files. It is
not a replacement for Lantern's evidence history — it holds no
epistemic state of its own.

## Understand evidence / validation

- **Observation** -> **Evidence** -> **belief()** is real and
  implemented (`lantern.core.EvidenceKernel`), reachable through
  `LanternBridge.observe()` / `.add_evidence()` / `.belief()`.
- **Witness Integrity** reports the real Chronicle hash-chain
  verification (`Chronicle.verify()`). `VALID` means the recorded
  sequence has not been silently altered — it does **not** mean the
  underlying claims are true.
- **Branches / Spine / Commitment**, a **Perspective Differential
  engine**, and a dedicated **RealityBoundary** class do not exist in
  Lantern v0.84. This harness reports them as `NOT_IMPLEMENTED` rather
  than simulating them.

## Known limitations

See `KNOWN_LIMITATIONS` in the mission report delivered alongside this
harness for the full, honest list.
