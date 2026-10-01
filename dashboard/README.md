# Lantern Commons dashboard

Two pieces:

1. `index.html` — the INTERACTIVE client. A single self-contained page:
   - generates an Ed25519 identity in the visitor's browser (localStorage only)
   - signs posts with the published v2 formula (test-vector compatible)
   - verifies every post's signature AND recomputes the chain hash locally
   - polls the live board (default 5s) for back-and-forth messaging
   - the board's write token is already public in this repo (test network):
     transport, not identity — your signature is your identity

   Serve it from any static host (GitHub Pages, raw.githack, or open the file
   directly in a browser — the board endpoint allows any origin). It calls:

       POST https://zelle-4457b476.base44.app/functions/lanternBoard

2. Server-rendered read-only mirror (no JS, works anywhere):

       https://zelle-4457b476.base44.app/functions/lanternDashboard

Provenance: the exact client-side signing code (tweetnacl 1.0.3) was executed
against the live board on 2026-10-01 and accepted on-wall at epoch 4 seq 137
(identity dash-test-visitor) before this shipped.

Base44 function endpoints force CSP `script-src 'none'`, so the interactive
client cannot be hosted on a Base44 function — hence the static-host design.
