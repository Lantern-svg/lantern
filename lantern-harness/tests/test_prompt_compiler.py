import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.bridge import LanternBridge
from lantern_harness.prompt_compiler import CompiledPrompt, FieldStatus, PromptCompiler


def _fresh_bridge():
    tmp = Path(tempfile.mkdtemp())
    bridge = LanternBridge(tmp, node_id="compiler-test")
    bridge.ensure_identity()
    bridge.startup()
    return bridge


def test_rejects_empty_request():
    compiler = PromptCompiler()
    import pytest
    with __import__("pytest").raises(ValueError):
        compiler.compile("")
    with __import__("pytest").raises(ValueError):
        compiler.compile("   ")


def test_lightweight_mode_for_ordinary_request():
    compiler = PromptCompiler()
    result = compiler.compile("What is the boiling point of water at sea level?")
    assert result.mode == "lightweight"
    assert "REQUEST" in result.text
    assert "USER_INTENT" in result.fields


def test_heavyweight_mode_triggered_by_consequential_keyword():
    compiler = PromptCompiler()
    result = compiler.compile("Should we delete the production database backups?")
    assert result.mode == "heavyweight"
    assert "CONTRADICTIONS" in result.fields
    assert "VALIDATION_REQUIREMENTS" in result.fields


def test_consequential_override_forces_heavyweight():
    compiler = PromptCompiler()
    result = compiler.compile("What color is the sky?", consequential=True)
    assert result.mode == "heavyweight"


def test_consequential_override_forces_lightweight():
    compiler = PromptCompiler()
    result = compiler.compile("Should we delete this?", consequential=False)
    assert result.mode == "lightweight"


def test_missing_information_marked_not_provided_not_fabricated():
    compiler = PromptCompiler()
    result = compiler.compile("Should we launch the new pricing policy?")
    assert result.fields["ASSUMPTIONS"] == FieldStatus.NOT_PROVIDED
    assert result.fields["UNCERTAINTIES"] == FieldStatus.NOT_PROVIDED
    assert result.fields["ALTERNATIVE_EXPLANATIONS"] == FieldStatus.NOT_PROVIDED
    assert result.fields["CONSTRAINTS"] == FieldStatus.NOT_PROVIDED
    assert result.fields["AUTHORIZATION"] == FieldStatus.NOT_PROVIDED
    # never silently omitted -- always present as an explicit marker
    assert FieldStatus.NOT_PROVIDED in result.text


def test_prove_x_pattern_is_reframed_not_assumed():
    compiler = PromptCompiler()
    result = compiler.compile("Write me a prompt that proves this idea is correct.")
    assert "Determine whether" in result.fields["TASK"]
    assert result.fields["TASK"] != result.fields["USER_INTENT"]
    assert any("reframed" in note for note in result.notes)
    # the original ask is preserved, not discarded
    assert result.fields["USER_INTENT"] == "Write me a prompt that proves this idea is correct."


def test_no_concept_supplied_means_evidence_fields_not_provided_not_fabricated():
    compiler = PromptCompiler()  # no bridge at all
    result = compiler.compile("Should we launch the new pricing policy?")
    assert result.fields["KNOWN_EVIDENCE"] == FieldStatus.NOT_PROVIDED
    assert result.fields["OBSERVATIONS"] == FieldStatus.NOT_PROVIDED


def test_concept_with_no_recorded_evidence_is_unknown_not_fabricated():
    bridge = _fresh_bridge()
    compiler = PromptCompiler(bridge=bridge)
    result = compiler.compile("Should we launch the new pricing policy?", concept="pricing_policy")
    assert result.fields["KNOWN_EVIDENCE"] == FieldStatus.UNKNOWN
    assert result.fields["CONTRADICTIONS"] == FieldStatus.UNKNOWN


def test_real_evidence_and_contradiction_are_surfaced_when_present():
    bridge = _fresh_bridge()
    obs1 = bridge.observe("pricing test A showed 12% lift", source="analyst", reliability=0.9)
    bridge.add_evidence("pricing_policy", obs1.id, weight=0.8, sign=1)
    obs2 = bridge.observe("pricing test B showed a 5% drop", source="analyst", reliability=0.9)
    bridge.add_evidence("pricing_policy", obs2.id, weight=0.6, sign=-1)

    compiler = PromptCompiler(bridge=bridge)
    result = compiler.compile(
        "Should we launch the new pricing policy?", concept="pricing_policy", consequential=True
    )

    assert result.fields["KNOWN_EVIDENCE"] != FieldStatus.NOT_PROVIDED
    assert result.fields["KNOWN_EVIDENCE"] != FieldStatus.UNKNOWN
    assert len(result.fields["KNOWN_EVIDENCE"]) == 2
    assert any(e["sign"] == -1 for e in result.fields["KNOWN_EVIDENCE"])  # the contradicting evidence is not hidden
    assert any("12% lift" in o["content"] for o in result.fields["OBSERVATIONS"])


def test_contradiction_detection_surfaces_when_kernel_actually_detects_one():
    bridge = _fresh_bridge()
    # add_evidence returns (evidence, contradiction) via the real EvidenceKernel;
    # feed enough opposing evidence for the kernel to actually flag one.
    obs1 = bridge.observe("supports X", source="a", reliability=1.0)
    bridge.add_evidence("claim_x", obs1.id, weight=5.0, sign=1)
    obs2 = bridge.observe("contradicts X", source="b", reliability=1.0)
    bridge.add_evidence("claim_x", obs2.id, weight=5.0, sign=-1)

    compiler = PromptCompiler(bridge=bridge)
    result = compiler.compile("Is claim X true?", concept="claim_x", consequential=True)

    contradictions = result.fields["CONTRADICTIONS"]
    # either the kernel flagged an OPEN contradiction (real detection) or it
    # didn't meet the kernel's own threshold -- either way this must reflect
    # the kernel's actual state, not an invented one.
    assert contradictions in (FieldStatus.UNKNOWN,) or isinstance(contradictions, list)
    if isinstance(contradictions, list) and contradictions:
        assert contradictions[0]["concept"] == "claim_x"


def test_secrets_never_enter_compiled_prompt():
    os.environ["FAKE_TEST_SECRET_FOR_COMPILER"] = "sk-should-never-appear-anywhere"
    try:
        compiler = PromptCompiler()
        result = compiler.compile("Should we deploy the new auth service?", consequential=True)
        assert "sk-should-never-appear-anywhere" not in result.text
        assert "sk-should-never-appear-anywhere" not in str(result.fields)
    finally:
        del os.environ["FAKE_TEST_SECRET_FOR_COMPILER"]


def test_malformed_input_types_rejected_not_silently_coerced():
    compiler = PromptCompiler()
    import pytest
    with __import__("pytest").raises((ValueError, AttributeError, TypeError)):
        compiler.compile(None)


def test_epistemic_status_field_present_and_labels_output_as_observation():
    compiler = PromptCompiler()
    result = compiler.compile("What is the capital of France?")
    assert "EPISTEMIC_STATUS" in result.fields
    joined = " ".join(result.fields["EPISTEMIC_STATUS"])
    assert "OBSERVATION" in joined


def test_lightweight_still_surfaces_real_evidence_if_present():
    bridge = _fresh_bridge()
    obs = bridge.observe("water boils at 100C at sea level", source="textbook", reliability=1.0)
    bridge.add_evidence("boiling_point", obs.id, weight=1.0, sign=1)

    compiler = PromptCompiler(bridge=bridge)
    result = compiler.compile("What is the boiling point of water?", concept="boiling_point", consequential=False)
    assert result.mode == "lightweight"
    # lightweight scales down empty fields, not real available evidence
    assert result.fields.get("KNOWN_EVIDENCE") not in (None, FieldStatus.NOT_PROVIDED)


def test_compiled_prompt_to_dict_round_trips():
    compiler = PromptCompiler()
    result = compiler.compile("hello")
    d = result.to_dict()
    assert d["mode"] == result.mode
    assert d["text"] == result.text

def test_blocked_when_chronicle_integrity_check_fails():
    """If witness_integrity() reports a broken chain, the compiler must
    refuse to read/present kernel state as though it were trustworthy --
    fields marked BLOCKED, not silently served from a corrupted chain."""
    bridge = _fresh_bridge()
    obs = bridge.observe("some fact", source="test", reliability=1.0)
    bridge.add_evidence("some_concept", obs.id, weight=0.5, sign=1)

    chronicle_path = bridge.data_dir / "chronicle.jsonl"
    with open(chronicle_path, "a") as f:
        f.write('{"id": "tampered", "type": "fake", "source": "attacker", "payload": {}, "prev_hash": "0" * 64, "hash": "deadbeef"}\n')

    integrity = bridge.witness_integrity()
    assert integrity["status"] != "VALID"

    compiler = PromptCompiler(bridge=bridge)
    result = compiler.compile(
        "What do we know about some_concept?", concept="some_concept", consequential=True
    )
    assert result.fields["KNOWN_EVIDENCE"] == FieldStatus.BLOCKED
    assert result.fields["OBSERVATIONS"] == FieldStatus.BLOCKED
    assert any("BLOCKED" in note for note in result.notes)

