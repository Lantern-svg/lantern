# Lantern Revenue Investigation

Status document only, like `RELEASE.md`. Nothing in this file starts a
service, moves funds, or creates a financial account. It records what
was actually investigated, what was actually built, and exactly which
external credential/identity/financial step remains before each path
could produce a real dollar.

## Capability 1: Paid belief reconciliation service (`service.py`, x402)

**What exists and is tested:** `POST /v1/reconcile` wraps the real
`codex_compare`/`codex_explanation` modules behind x402 payment
middleware. `tests/test_service_integration.py` (10/10 passing) verifies:
no-payment returns 402, invalid-payment returns 402, and a
mocked-valid payment authorizes exactly one real (non-fabricated)
reconciliation call, with the reciprocity outcome recorded to a real
Chronicle. The mocking is scoped to the facilitator's HTTP boundary
(`verify`/`settle`) only -- the reconciliation business logic itself is
never mocked.

**Real defect found and fixed this session:** the historical default
facilitator (`https://x402.org/facilitator`, `x402` SDK's own
hardcoded default) returns HTTP 404 -- verified live via GET and POST.
`service.py` previously would have silently pointed a production
deployment at a dead endpoint. It has been changed to:
1. Use the real Coinbase CDP Facilitator
   (`cdp.x402.create_facilitator_config`, per
   https://docs.cdp.coinbase.com/x402/seller/facilitator) if
   `CDP_API_KEY_ID`/`CDP_API_KEY_SECRET` are set, or
2. Use a caller-supplied `LANTERN_FACILITATOR_URL`, or
3. Refuse to start with an explicit `CAPABILITY_REQUIRED` error if
   neither is configured -- no silent dead default, no fabricated
   value.

**What is genuinely missing (named, not invented):**
- A real EVM wallet address the operator controls
  (`LANTERN_PAYMENT_RECIPIENT_EVM`) to receive funds. Not present in
  this environment. This harness will not generate one and claim it as
  the operator's -- receiving funds requires the operator's own key
  custody.
- Either CDP API credentials (`CDP_API_KEY_ID` / `CDP_API_KEY_SECRET`,
  requires a Coinbase Developer Platform account) or a genuinely live
  facilitator URL. Neither exists in this environment.
- The `cdp-sdk` Python package is not installed (only needed if the
  CDP credential path is chosen).
- Running the service at all (even against Base Sepolia testnet, i.e.
  no real money) means starting a network-exposed process, which this
  session is holding pending explicit operator authorization to
  install/run services.

**REVENUE_READY:** NO. **BLOCKED on:** operator-supplied wallet address
+ operator-supplied facilitator credentials + explicit authorization to
run the service. **CAPABILITY_REQUIRED:** `LANTERN_PAYMENT_RECIPIENT_EVM`,
one of (`CDP_API_KEY_ID`+`CDP_API_KEY_SECRET`) or a live
`LANTERN_FACILITATOR_URL`, and operator go-ahead to start the process.

This is the **smallest real monetizable capability** already built:
everything up to the financial/identity boundary is done and tested.

**Update, 2026-08-30 (mission: prepare production path):** the operator
supplied a real receiving wallet address
(`0xD062a97d1Bc9D7CE42B2bD1E4BD7f9d3aa4E2683`) and authorized preparing
(not executing) the full production path. Re-inspected `service.py`
directly (not from this document) and re-ran tests fresh: still 10/10
on `tests/test_service_integration.py`, still 862 passed (now 871 with
a new ledger test file) on the full suite. Confirmed via the real
`cdp-sdk` package source (downloaded and read, not assumed from docs)
that `service.py`'s existing CDP integration code is already correct.
Built three new artifacts, none of which touch financial state:
- `CDP_INTEGRATION.md` — exact CDP account/credential/package
  requirements and how the payment/settlement flow actually works,
  verified against real source.
- `DEPLOYMENT_CHECKLIST.md` — three explicit gates (testnet /
  production-prep / mainnet-authorization), with mainnet, real-money
  acceptance, public exposure, and fund movement all requiring separate
  explicit operator authorization under Gate 3.
- `src/lantern/revenue_ledger.py` (+ `tests/test_revenue_ledger.py`,
  9/9 passing) — reads the service's own Chronicle and classifies
  outcomes honestly: testnet settlements, unpaid/failed calls, and the
  service's own "verified_pending_settlement" intermediate state are
  all explicitly excluded from `gross_revenue_usd`; only
  `settlement_status == "settled"` on the configured mainnet network
  counts. A real accounting bug (stale `net_contribution_usd` field)
  was caught by this test suite and fixed before merge.

Still not done, deliberately: no `cdp-sdk` install, no CDP account/key
creation or request, no env vars set, no mainnet network change, no
service process started, no funds received or moved. Base Sepolia
(`eip155:84532`) remains the only configured network.

## Capability 2: Paid prompt compilation (investigated, not yet built)

The mission asks about "paid prompt compilation" as a revenue path.
`lantern_harness.prompt_compiler.PromptCompiler` already exists and is
useful standalone (turns an ordinary request into a structured,
non-fabricating investigation prompt). It could be exposed as its own
priced endpoint using the same `service.py` x402 pattern, without
needing Lantern's evidence/Chronicle state at all for the lightest
tier. **Not built this session** because it depends on the same missing
wallet/facilitator credentials as Capability 1 -- building a second
paid endpoint before the first can be tested end-to-end would not
create additional REVENUE_READY-ness, only additional BLOCKED surface.
**NEXT_BUILD** once Capability 1's credentials exist: add
`POST /v1/compile` alongside `/v1/reconcile` in `service.py`.

## Capability 3: Hosted Lantern-as-a-service / subscriptions

Investigated conceptually only. Would require the same payment
infrastructure as Capability 1 (or a fiat processor such as Stripe,
which introduces its own separate operator-identity/KYB requirement)
plus multi-tenant deployment concerns (per-tenant Chronicle isolation)
that do not exist yet. **Not started.** Premature relative to
Capability 1: build one working paid endpoint before generalizing to
multi-tenant hosting.

## Capability 4: Agent-to-agent / MCP-mediated payment (Linq/Natural signal)

Investigated per the mission's explicit prompt. The user-cited
Linq/Natural agent-payment model was **not assumed to be the answer**;
instead the broader ecosystem was checked directly. Finding: the x402
protocol (already integrated into `service.py`) is itself the
general-purpose "agent pays for a capability mid-conversation" rail --
an x402-protected HTTP endpoint is already callable by any x402-aware
agent client, human or automated, with no separate agent-specific
integration required. The blocking dependency is identical to
Capability 1 (wallet + facilitator credentials), not a missing
agent-specific integration. `AGENT_DISTRIBUTION_POLICY.md` and
`agent_distribution_funnel.json` already define the discovery/
introduction/pricing/settlement funnel for when a real endpoint exists
to advertise -- currently all-zero, honestly, because there is nothing
live to discover yet.

## Capability 6: MCP server distribution (free, adoption channel -- not itself revenue)

Built this session: `lantern_harness.mcp_server` exposes 9 real
Lantern harness tools (observe, add_evidence, confidence, decide,
compile, self_model, branch_open, spine_read, witness_integrity) over
the standard MCP stdio transport, `pip install lantern-harness[mcp]`,
verified against a real independent MCP client
(`tests/test_mcp_server_live_stdio.py`, launched as a genuine
subprocess). This is **not a revenue path by itself** -- it is free,
local-only, and deliberately excludes any tool that could execute an
external action or accept payment. It matters for revenue only
indirectly: it is the lowest-friction way for another agent developer
to actually try Lantern (`pip install` + one JSON config entry, no
server to run, no account, no payment), which is a prerequisite for
any future paid capability having real users to reach. Recorded here
so it isn't conflated with an actual monetizable capability -- it has
no `settlement` field and never will while it stays scoped to
epistemic primitives.

## Capability 5: GitHub Sponsors / other funding platforms

Considered. Requires the operator to personally enroll in a funding
platform (real-world identity/financial/tax step) -- this harness has
no path to do that on the operator's behalf, and doing so would be a
`REQUIRES_OPERATOR_IDENTITY` action by definition, not an engineering
one. Not pursued further; named here so it isn't silently dropped from
consideration.

## Summary

| Capability | Built | Tested | Blocked on |
|---|---|---|---|
| Paid `/v1/reconcile` (x402) | YES | YES (10/10) | wallet + facilitator credential + run authorization |
| Paid `/v1/compile` (x402) | NO | -- | same as above, deprioritized until #1 is live |
| Hosted multi-tenant service | NO | -- | #1's infra + multi-tenant isolation design |
| Agent-to-agent via x402 | Same infra as #1 | -- | same as #1 |
| GitHub Sponsors / funding platforms | N/A | -- | operator identity/financial enrollment |
| MCP server (free distribution, not revenue) | YES | YES (14/14 across both mcp_server test files) | none -- already usable today |

No revenue has occurred. No user has paid. No partnership exists. This
document will be updated with real, dated entries only as real events
occur -- not projected or assumed ones.
