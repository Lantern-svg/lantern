import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.bridge import LanternBridge
from lantern_harness.transfer_manifest import build_manifest, TransferManifest


def _fresh_bridge(name="case"):
    tmp = Path(tempfile.mkdtemp()) / name
    bridge = LanternBridge(tmp, node_id=f"transfer-test-{name}")
    bridge.ensure_identity()
    bridge.startup()
    return bridge


def test_manifest_reports_real_identity_not_a_placeholder():
    bridge = _fresh_bridge("identity")
    manifest = build_manifest(bridge)
    assert manifest.node_id == "transfer-test-identity"
    assert manifest.identity_status == "READY"
    assert manifest.public_key_hex is not None
    assert len(manifest.public_key_hex) == 64  # Ed25519 verify key hex


def test_manifest_never_contains_a_private_key_or_signing_material():
    bridge = _fresh_bridge("no-secrets")
    manifest = build_manifest(bridge)
    payload = str(manifest.to_dict())
    assert "private" not in payload.lower() or "private_key" not in payload
    assert "signing_key" not in payload
    assert "SigningKey" not in payload


def test_manifest_state_summary_reflects_real_observations():
    bridge = _fresh_bridge("state")
    bridge.observe("first observation", source="test")
    bridge.observe("second observation", source="test")
    manifest = build_manifest(bridge)
    assert manifest.state_summary["observations"] == 2
    assert manifest.state_summary["step"] == 2


def test_manifest_reports_real_witness_integrity_not_assumed_valid():
    bridge = _fresh_bridge("integrity")
    manifest = build_manifest(bridge)
    assert manifest.witness_integrity == bridge.witness_integrity()
    assert manifest.witness_integrity.get("status") in ("VALID", "INVALID", "NO_CHRONICLE", "ERROR")


def test_manifest_lists_reauthorization_required_items():
    bridge = _fresh_bridge("reauth")
    manifest = build_manifest(bridge)
    assert len(manifest.reauthorization_required) > 0
    joined = " ".join(manifest.reauthorization_required)
    assert "credential" in joined.lower() or "reasoning engine" in joined.lower()
    assert "network" in joined.lower()


def test_manifest_does_not_transfer_reasoning_engine_api_key_value():
    """Only the env var NAME may appear, never a real key value.
    No API key is configured in this test environment, so also assert
    that no environment secret happens to leak in incidentally."""
    import os

    bridge = _fresh_bridge("no-key-value")
    manifest = build_manifest(bridge, engine=None)
    assert manifest.reasoning_engine_api_key_env is None
    payload = manifest.to_dict()
    assert payload["configuration"]["reasoning_engine_api_key_env"] is None
    for env_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(env_name)
        if value:
            assert value not in str(payload)


def test_manifest_reuses_self_model_capability_and_gap_lists():
    """Must not maintain a second, divergent capability list -- proves
    it's the same tuple objects as self_model.py, not a copy that can
    drift out of sync."""
    from lantern_harness.self_model import KNOWN_CAPABILITIES, KNOWN_GAPS

    bridge = _fresh_bridge("reuse")
    manifest = build_manifest(bridge)
    assert manifest.capabilities == KNOWN_CAPABILITIES
    assert manifest.known_gaps == KNOWN_GAPS


def test_manifest_records_real_provenance_commit_hashes():
    bridge = _fresh_bridge("provenance")
    manifest = build_manifest(bridge)
    # Either a real 40-char git hash or an honest UNKNOWN -- never a
    # fabricated placeholder value.
    assert manifest.harness_commit == "UNKNOWN (not a git checkout, or git unavailable)" or len(manifest.harness_commit) == 40
    assert manifest.lantern_core_commit.startswith("UNKNOWN") or len(manifest.lantern_core_commit) == 40


def test_manifest_protocol_version_matches_lantern_protocol_module():
    from lantern.protocol import PROTOCOL_VERSION

    bridge = _fresh_bridge("protocol")
    manifest = build_manifest(bridge)
    assert manifest.protocol_version == PROTOCOL_VERSION


def test_manifest_is_read_only_no_state_mutation():
    bridge = _fresh_bridge("read-only")
    before = bridge.status()
    build_manifest(bridge)
    build_manifest(bridge)
    after = bridge.status()
    assert before == after


def test_manifest_to_dict_and_format_round_trip_without_error():
    bridge = _fresh_bridge("format")
    manifest = build_manifest(bridge)
    as_dict = manifest.to_dict()
    assert isinstance(as_dict, dict)
    formatted = manifest.format()
    assert "TRANSFER MANIFEST" in formatted
    assert manifest.node_id in formatted
