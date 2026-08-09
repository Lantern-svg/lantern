# Lantern Identity

## Human-readable
Lantern is a protocol/scaffold for evidence-aware, auditable, reciprocal agent interaction.

Current implemented paid capability:
- **Belief Reconciliation**
- **Endpoint:** `POST /v1/reconcile`
- **Protocol:** HTTP / JSON
- **Settlement:** x402

Lantern compares two independent belief states and explains disagreements in terms of:
- evidence
- confidence
- contradiction
- missing support
- source reliability
- agreement

Lantern does **not** claim that payment implies truth or trust.
Payment only satisfies the monetary side of a reciprocal agreement.

## Machine-readable
```json
{
  "agent": "Lantern",
  "kind": "evidence-aware reciprocal agent scaffold",
  "commercial_capabilities": [
    {
      "name": "Belief Reconciliation",
      "endpoint": "POST /v1/reconcile",
      "protocol": "HTTP/JSON",
      "settlement": "x402",
      "implemented": true,
      "input": "two independent belief states",
      "output": [
        "evidence-aware comparison",
        "contradiction classification",
        "confidence comparison",
        "plain-language explanation"
      ],
      "trust_boundary": "payment does not imply truth or trust"
    }
  ],
  "architecture": {
    "reciprocity": "semantic exchange",
    "payment": "monetary settlement",
    "settlement_mechanism": "x402"
  }
}
```
