# Lantern Packaging / Distribution Status

Status document only, like `RELEASE.md` and `REVENUE.md`. Building and
testing a package locally is fully reversible -- nothing here uploads
anything to a public index.

## PyPI

- **Package name `lantern` is taken** by an unrelated project (owner
  contact `cameron.lonsdale@gmail.com`, confirmed via the PyPI JSON API).
- **Confirmed available** (HTTP 404 on the PyPI JSON API, checked
  2026-08-12): `lantern-protocol`, `lantern-babel`, `lantern-evidence`,
  `lantern-kernel`, `lantern-agent-protocol`, `babel-codex-bridge`,
  `lantern-babel-codex-bridge`.
- **Build verified real, this session:** using `python -m build` against
  a disposable copy of the repo (candidate name `lantern-protocol`,
  never committed to the tracked repo), both an sdist and a wheel built
  successfully. The wheel was then installed into a completely fresh,
  unrelated throwaway venv (`pip install lantern_protocol-0.84-py3-none-any.whl`)
  and its core API was exercised for real:
  `Lantern()` / `LanternAgent(l)` / `agent.observe(...)` all worked,
  producing a real observation id. This confirms the package is
  genuinely `pip install`-able under a renamed distribution name, not
  just importable from a development checkout.
- **What's still missing:** a decision on which available name to use
  (this document does not choose one -- the mission's own boundary
  rules treat naming/identity decisions as the operator's to make,
  since the name becomes a public, hard-to-reverse identity), and PyPI
  publishing credentials (no `TWINE_*`/`PYPI_*` environment variables
  exist in this environment; none were fabricated).
- **PACKAGE_READY:** YES (build+install verified). **PUBLISH_READY:**
  NO -- blocked on name decision + credentials, both operator-owned
  decisions.

## `lantern-harness`

- Already has its own `pyproject.toml` (added this session) with a
  console entry point (`lantern-harness`). Verified installable via
  `pip install -e .` into a fresh venv, with the entry-point script
  actually running and all 132 harness tests passing from that fresh
  install (see harness `README.md` "Install" section).
- Depends on `lantern` core by import name (`from lantern.core import
  Lantern`, etc.) -- if `lantern` core is ever published to PyPI under
  a different distribution name (e.g. `lantern-protocol`), the harness's
  `pyproject.toml` dependency line would need to reference that
  distribution name explicitly. Not yet needed since neither package is
  published.
