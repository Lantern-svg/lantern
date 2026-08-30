# CDP Facilitator Integration — Exact Requirements

Status document. Nothing in this file installs a package, creates an
account, or configures a secret. It records exactly what is required so
the operator can complete the remaining steps deliberately.

Verified against `service.py` (as of 2026-08-30) and the real `cdp-sdk`
package source (`cdp/x402/x402.py`, version 1.48.1, downloaded and
inspected directly — not assumed from documentation alone).

## What `service.py` already does today

```python
CDP_API_KEY_ID = os.getenv("CDP_API_KEY_ID", "")
CDP_API_KEY_SECRET = os.getenv("CDP_API_KEY_SECRET", "")
...
if CDP_API_KEY_ID and CDP_API_KEY_SECRET:
    from cdp.x402 import create_facilitator_config
    facilitator = HTTPFacilitatorClient(create_facilitator_config())
```

`create_facilitator_config()` (real source, `cdp/x402/x402.py`):
- Reads `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` from the environment
  itself if not passed as arguments (`service.py` doesn't pass them
  explicitly — it relies on the SDK's own `os.getenv` fallback, which
  reads the same two variable names, so this is consistent, not a bug).
- Builds a `FacilitatorConfig` pointing at
  `https://api.cdp.coinbase.com/platform/v2/x402`.
- If credentials are present, wires up CDP's authenticated JWT header
  generation for the `verify`, `settle`, and `supported` operations
  (`create_cdp_auth_headers`).
- If credentials are absent, falls back to unauthenticated headers that
  only support the `list` (discovery) operation — `verify`/`settle`
  will not work without credentials. This matches `service.py`'s own
  explicit refusal to start without credentials or a fallback URL.

**Conclusion: `service.py`'s CDP integration code is already correct
and matches the real SDK's actual interface.** Nothing needs to change
in the integration logic itself for Gate 2. What's missing is purely
credentials + the `cdp-sdk` package + explicit run authorization.

## Required CDP account

1. An account at the **Coinbase Developer Platform**
   (https://www.coinbase.com/developer-platform / portal at
   https://portal.cdp.coinbase.com). This is a real, human-operated
   account — it cannot be created by an agent on the operator's behalf,
   and this project will not attempt to.
2. Inside that account, an **API key** (key ID + secret pair) with
   permission to use the x402 Facilitator (`verify`/`settle`
   endpoints). CDP's own docs describe this as part of standard API key
   creation in the CDP Portal — no separate "x402 product" enrollment
   was found to be required beyond having a CDP account and API key,
   based on the docs reviewed; if the CDP Portal UI shows an explicit
   separate x402/Facilitator enablement step at account-creation time,
   the operator should follow whatever that live UI states, since this
   document cannot see the current portal UI.

## Required credentials (the operator must generate and hold these — this project never will)

| Variable | What it is | Where it comes from |
|---|---|---|
| `CDP_API_KEY_ID` | CDP API key identifier | CDP Portal, after account creation |
| `CDP_API_KEY_SECRET` | CDP API key secret | CDP Portal, shown once at key creation |
| `LANTERN_PAYMENT_RECIPIENT_EVM` | Payout address | Already provided by operator: `0xD062a97d1Bc9D7CE42B2bD1E4BD7f9d3aa4E2683` — this is a **public receiving address only**; no private key or seed phrase is needed or wanted for this integration. The facilitator settles payment *to* this address; it does not need to sign anything on the recipient's behalf. |

Optional / not required for the CDP path (only relevant to the
alternate, non-CDP facilitator path):
- `LANTERN_FACILITATOR_URL` — only used if CDP credentials are absent.
  Not needed once CDP credentials exist; the code prefers CDP when both
  are present.

## Required Python package

- `cdp-sdk` (verified on PyPI: latest is `1.48.1` as of this check).
  **Not currently installed** in `.venv`
  (`pip show cdp-sdk` → "Package(s) not found").
  Installing it is a reversible, side-effect-free `pip install cdp-sdk`
  into the existing project virtualenv — it does not itself create any
  account, spend money, or expose secrets. This project has **not**
  installed it yet, pending explicit authorization, since the mission
  instructions asked for the complete *path* to be prepared, not
  necessarily every dependency pre-installed without a checkpoint.

## Exact facilitator configuration (target end-state, Gate 2)

Environment variables to be set by the operator at deploy time (never
committed to source):

```
LANTERN_PAYMENT_RECIPIENT_EVM=0xD062a97d1Bc9D7CE42B2bD1E4BD7f9d3aa4E2683
CDP_API_KEY_ID=<operator-generated, secret>
CDP_API_KEY_SECRET=<operator-generated, secret>
LANTERN_RECONCILIATION_PRICE=$0.001   # or operator-chosen price
```

No code change is required in `service.py` to consume these — the
CDP branch (`if CDP_API_KEY_ID and CDP_API_KEY_SECRET:`) already exists
and already prefers CDP over any fallback URL.

## How the x402 middleware uses the facilitator (verified from real source)

1. `service.py` builds an `x402ResourceServer(facilitator)` and
   registers `ExactEvmScheme()` for `TESTNET_NETWORK` only
   (`eip155:84532`). **This means: even with valid CDP credentials
   configured, the service as currently written will only ever accept
   payment on Base Sepolia, because that is the only network registered
   with `payment_server.register(...)`.** Switching to mainnet requires
   both changing `TESTNET_NETWORK` to `eip155:8453` AND this remains the
   explicit Gate 3 action, not something CDP credentials alone trigger.
2. Every request to `POST /v1/reconcile` passes through
   `x402_payment_middleware`, which calls the real
   `x402.http.middleware.fastapi.payment_middleware(routes_config,
   payment_server)` (verified by reading the installed package source,
   not just its docstring).
3. That middleware (real control flow, read directly from
   `x402/http/middleware/fastapi.py`):
   - No `X-PAYMENT` header → returns HTTP 402 immediately, route handler
     never runs.
   - Header present → calls `http_server.process_http_request(...)`,
     which calls the facilitator's `verify` endpoint (this is the first
     live network call to CDP, and the first point CDP credentials are
     actually exercised).
   - If verify fails → 402, handler never runs.
   - If verify succeeds → the actual `/v1/reconcile` route handler runs
     (the real reconciliation logic — unchanged, un-mockable at this
     point).
   - After the handler returns successfully (status < 400) → the
     middleware calls `process_settlement(...)`, which calls the
     facilitator's `settle` endpoint (the second live CDP call — this
     is what actually moves funds on-chain).
   - If settlement fails → the response is downgraded to 402 with a
     `PAYMENT-RESPONSE` header carrying `success: false`, even though
     the handler already ran. (`service.py`'s own Chronicle record was
     already written at `settlement_status="verified_pending_settlement"`
     by that point — this is the exact reason the revenue ledger
     (`lantern.revenue_ledger`) refuses to count that status as
     revenue: verified is not the same as settled.)
   - If settlement succeeds → the real response is returned with
     settlement headers attached.

## What must remain secret

- `CDP_API_KEY_SECRET` — never logged, never committed, never placed in
  `service.py` or any tracked file. Must be supplied only via
  environment variable or a secret manager at deploy time.
- `CDP_API_KEY_ID` — not as sensitive as the secret, but still an
  account-linked identifier; treat as secret by default (no reason to
  publish it).
- Any wallet **private key or Secret Recovery Phrase** — not applicable
  here at all. This integration never needs, requests, or stores a
  private key. The recipient address is a public destination for
  incoming funds only; CDP's Facilitator (not this service) handles the
  on-chain settlement transaction using the *payer's* signed
  authorization, not the recipient's key.

## What can safely be committed to the repository

- `service.py` itself (already committed) — contains no secrets, only
  `os.getenv(...)` reads.
- This document.
- The deployment checklist (`DEPLOYMENT_CHECKLIST.md`).
- `src/lantern/revenue_ledger.py` and its tests.
- A `.env.example` file (not yet created) listing variable *names*
  only, with placeholder/empty values — useful for operators, contains
  no real secret.

## How to test the integration on Base Sepolia before mainnet

1. Install `cdp-sdk` in the project venv (`pip install cdp-sdk`) —
   reversible, no account/spend implication by itself.
2. Operator creates a CDP account + API key (human step, outside this
   project's ability to perform).
3. Set `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` /
   `LANTERN_PAYMENT_RECIPIENT_EVM` as environment variables (not
   committed).
4. Start `service.py` locally (`uvicorn service:app`). It will now use
   the real CDP Facilitator, but still only for `eip155:84532` (Base
   Sepolia) per current code — no mainnet exposure yet even with real
   CDP credentials configured, because the network registration itself
   is still testnet-only.
5. Obtain Base Sepolia testnet USDC from a public faucet (e.g. Circle's
   or Coinbase's testnet faucet — free, no real money) into a test
   wallet the operator controls.
6. Make a real `POST /v1/reconcile` call from an x402-aware client using
   that test wallet. Confirm:
   - First call without payment → 402.
   - Call with a real signed Base Sepolia payment → 200, with a
     genuine `settlement_status: "settled"` Chronicle record.
7. Run `python -m lantern.revenue_ledger reciprocity_chronicle.jsonl`
   and confirm it reports the testnet call under
   `testnet_settlements`, **not** `gross_revenue_usd` — this is the
   live proof that the accounting rule holds against a real (not
   simulated) CDP-verified transaction.

This full sequence proves the entire path — CDP auth, verify, execute,
settle, Chronicle record, honest ledger classification — end-to-end
with zero real money at risk, before Gate 3 is ever considered.
