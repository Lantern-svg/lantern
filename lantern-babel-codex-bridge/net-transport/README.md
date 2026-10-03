# net-transport — lantern-net close network, Phase 3

Two transports, one protocol core (Ed25519 over DOMAIN `lantern-net/v1/`,
fail-closed allowlist, replay nonces, hash-chained local ledgers,
producer + independent-recompute confirmation):

1. `lantern_net.py` — original build (Claw, 2026-10-03): TLS hub + rendezvous +
   relay + worker + submit, challenge-response registration, rate bucket,
   cert pinning, selftest. Reviewed and selftest-verified in sandbox on both
   crypto backends (pynacl + cryptography).
2. `lantern_net_http.py` + `lanternNetHub_base44.ts` — Phase 3 transport
   fallback (B, 2026-10-03): the VPS container boundary never served TLS
   (port maps, handshake resets; `-p 443:443` live, hub behind it not). The
   Base44 function host is the only verified inbound surface, so the hub
   runs there as signed HTTP POST (register/post/fetch/mark/info) with the
   SAME protocol core imported from lantern_net.py (HttpNode subclasses
   Node). Nodes need zero inbound; VPS joins with outbound HTTPS only.

Hub design: server-side allowlist (fail-closed; redeploy = operator
ceremony), WebCrypto Ed25519 verification of every write and read,
(from_node, nonce) replay gate, presence expiry 300s, UA gate, client-
canonized envelopes stored VERBATIM (env_json — v1.0.0 re-serialized and
ms-truncated ts, breaking reader signature checks; fixed v1.0.1).

Live evidence 2026-10-03 (unit 133b1456a6373a70, collatz 27): sbx submitted,
t1 computed, sbx independently recomputed, CONFIRMED, result_hash
f6e0a1e2ac41945a (= sha256 canon(111)); both ledgers chain-VALID. Live
attacks all held: rogue key NOT_ALLOWLISTED, exact replay 409, forged
signature SIGNATURE_INVALID, default UA UA_BLOCKED.

Limits (unchanged from lantern_net plus transport): keys != operators
(R8: sbx+t1 same operator for the live test); envelopes signed, not
encrypted; hub sees metadata by design; single function host = SPOF; HTTP
polling, not raw TCP.
