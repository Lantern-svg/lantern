"""Regression tests for the serialization boundary between immutable
internal Lantern structures (MappingProxyType, tuple) and JSON-serializable
external representations.

These tests verify the architectural rule:
  Internal Lantern state -> immutable structures -> serialization boundary
  -> ordinary JSON-compatible structures

The specific failure these guard against:
  asdict(observation) on a frozen dataclass with MappingProxyType metadata
  triggers copy.deepcopy internally, which fails with
  "cannot pickle 'mappingproxy' object" when the HTTP handler tries to
  serialize the response.
"""

import copy
import dataclasses
import json
from types import MappingProxyType

import pytest

from lantern.core import (
    Evidence,
    Observation,
    Contradiction,
    ResolutionEvent,
    EvidenceKernel,
)


def _serializable_dict(obj):
    """Local copy of the bootstrap_node serialization boundary helper."""
    result = {}
    for key, value in obj.__dict__.items():
        if isinstance(value, MappingProxyType):
            result[key] = dict(value)
        elif isinstance(value, tuple):
            result[key] = list(value)
        else:
            result[key] = value
    return result


# 1. Observation with metadata serializes successfully

def test_observation_with_metadata_serializes_to_json():
    obs = Observation(
        content="test fact", source="sensor_a", reliability=0.9,
        step=1, owner_instance="node-x", id="obs-1",
        metadata={"layer": "physical", "priority": "high"},
    )
    serializable = _serializable_dict(obs)
    result = json.dumps(serializable, sort_keys=True)
    assert json.loads(result)["metadata"] == {"layer": "physical", "priority": "high"}


def test_observation_with_empty_metadata_serializes():
    obs = Observation(
        content="x", source="s", reliability=0.5, step=0,
        owner_instance="n", id="o1", metadata={},
    )
    serializable = _serializable_dict(obs)
    assert json.dumps(serializable)


def test_observation_with_nested_metadata_serializes():
    obs = Observation(
        content="nested", source="s", reliability=0.7, step=1,
        owner_instance="n", id="o2",
        metadata={"outer": {"inner": [1, 2, 3], "flag": True}},
    )
    serializable = _serializable_dict(obs)
    result = json.loads(json.dumps(serializable))
    assert result["metadata"]["outer"]["inner"] == [1, 2, 3]


# 2. MappingProxyType never reaches the JSON serializer

def test_mappingproxy_never_reaches_json_serializer():
    obs = Observation(
        content="x", source="s", reliability=0.5, step=0,
        owner_instance="n", id="o3", metadata={"k": "v"},
    )
    serializable = _serializable_dict(obs)

    def _check(obj):
        if isinstance(obj, MappingProxyType):
            pytest.fail("MappingProxyType reached serialization boundary")
        elif isinstance(obj, dict):
            for v in obj.values():
                _check(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _check(item)

    _check(serializable)
    json.dumps(serializable)


# 3. Serialized metadata is an ordinary dictionary

def test_serialized_metadata_is_ordinary_dict():
    obs = Observation(
        content="x", source="s", reliability=0.5, step=0,
        owner_instance="n", id="o4", metadata={"key": "value"},
    )
    serializable = _serializable_dict(obs)
    assert isinstance(serializable["metadata"], dict)
    assert not isinstance(serializable["metadata"], MappingProxyType)
    assert serializable["metadata"] == {"key": "value"}


# 4. Nested metadata survives serialization/deserialization correctly

def test_nested_metadata_roundtrip():
    original_metadata = {"a": {"b": {"c": [1, 2]}}, "d": "string"}
    obs = Observation(
        content="x", source="s", reliability=0.5, step=0,
        owner_instance="n", id="o5", metadata=original_metadata,
    )
    serializable = _serializable_dict(obs)
    wire = json.dumps(serializable, sort_keys=True)
    decoded = json.loads(wire)
    assert decoded["metadata"] == original_metadata


# 5. Frozen dataclasses remain frozen

def test_observation_remains_frozen():
    obs = Observation(
        content="x", source="s", reliability=0.5, step=0,
        owner_instance="n", id="o6", metadata={},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.content = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        obs.metadata = {"new": "value"}


def test_evidence_remains_frozen():
    ev = Evidence(
        concept="c", observation_id="o", weight=1.0, sign=1,
        step=1, owner_instance="n", id="e1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.concept = "changed"


def test_contradiction_remains_frozen():
    c = Contradiction(
        concept="c", evidence_snapshot=("e1", "e2"),
        historical_severity=0.5, current_severity=0.5,
        created_step=1, owner_instance="n", id="c1",
        status="OPEN", resolution_id=None,
        supersedes=None, superseded_by=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.status = "RESOLVED"


def test_resolution_event_remains_frozen():
    r = ResolutionEvent(
        contradiction_id="c1", decision="resolved",
        reasoning="test", confidence=0.9,
        evidence_snapshot=("e1", "e2"),
        owner_instance="n", id="r1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.confidence = 0.5


# 6. Immutability guarantees from Finding 1 remain intact

def test_observation_metadata_is_immutable_mappingproxy():
    obs = Observation(
        content="x", source="s", reliability=0.5, step=0,
        owner_instance="n", id="o7", metadata={"k": "v"},
    )
    assert isinstance(obs.metadata, MappingProxyType)
    with pytest.raises(TypeError):
        obs.metadata["new"] = "value"


def test_contradiction_evidence_snapshot_is_tuple():
    c = Contradiction(
        concept="c", evidence_snapshot=("e1", "e2"),
        historical_severity=0.5, current_severity=0.5,
        created_step=1, owner_instance="n", id="c2",
        status="OPEN", resolution_id=None,
        supersedes=None, superseded_by=None,
    )
    assert isinstance(c.evidence_snapshot, tuple)


def test_deepcopy_preserves_immutability():
    obs = Observation(
        content="x", source="s", reliability=0.5, step=0,
        owner_instance="n", id="o8", metadata={"k": "v"},
    )
    clone = copy.deepcopy(obs)
    assert isinstance(clone.metadata, MappingProxyType)
    with pytest.raises(dataclasses.FrozenInstanceError):
        clone.content = "changed"
    with pytest.raises(TypeError):
        clone.metadata["x"] = "y"


def test_no_shared_mutable_metadata_across_copies():
    original = {"key": "value"}
    obs = Observation(
        content="x", source="s", reliability=0.5, step=0,
        owner_instance="n", id="o9", metadata=original,
    )
    original["key"] = "changed"
    assert obs.metadata["key"] == "value"


# 7. Bootstrap HTTP endpoint returns observation data

def test_serializable_dict_matches_bootstrap_node_helper():
    obs = Observation(
        content="hello", source="remote", reliability=0.5, step=1,
        owner_instance="node-a", id="obs-uuid",
        metadata={"claimed_reliability": 0.99, "origin": "exchange"},
    )
    from lantern.bootstrap_node import _serializable_dict as bs_serializable
    result = bs_serializable(obs)
    assert isinstance(result["metadata"], dict)
    assert result["metadata"] == {"claimed_reliability": 0.99, "origin": "exchange"}
    assert result["content"] == "hello"
    assert result["id"] == "obs-uuid"
    json.dumps(result)


# 8. Fix does not break Chronicle or portable-instance serialization

def test_chronicle_serialization_with_frozen_observations(tmp_path):
    from lantern.core import Lantern
    lantern = Lantern(
        owner_instance="test-node",
        chronicle_filename=str(tmp_path / "chronicle.jsonl"),
    )
    lantern.observe("test fact", "local", 0.9, metadata={"tag": "value"})
    chronicle_file = tmp_path / "chronicle.jsonl"
    assert chronicle_file.exists()
    lines = chronicle_file.read_text().strip().split("\n")
    assert len(lines) >= 1
    record = json.loads(lines[-1])
    assert record["type"] == "OBSERVATION_CREATED"
    assert record["payload"]["metadata"] == {"tag": "value"}
    assert lantern.bus.chronicle.verify()


def test_portable_instance_export_with_frozen_observations(tmp_path):
    """PortableInstance export must serialize frozen Observation objects
    with MappingProxyType metadata through its _state_payload() method."""
    from lantern.portable_instance import PortableInstance
    from lantern import instance_lifecycle as lc
    from lantern import ownership as own
    from lantern import instance_permissions as perms
    from lantern.core import EvidenceKernel

    state = lc.install(node_id="test-node", data_dir=tmp_path / "node")
    state = lc.initialize(state)
    state, identity = lc.create_identity(state)
    state, ownership = lc.authorize_owner(state, identity, owner_id="alice", owner_token="token-a")

    kernel = EvidenceKernel(owner_instance=identity.public_key_hex)
    obs = kernel.observe("fact", "local", 0.9, metadata={"source_type": "sensor"})
    kernel.add_evidence("concept_a", obs.id, 1.0, 1)

    grant = perms.create_capability_grant(
        identity, ownership, owner_token="token-a",
        capabilities=[perms.EXPORT_STATE],
    )
    history = own.OwnershipHistory([ownership])
    instance = PortableInstance(
        identity=identity,
        ownership_history=history,
        kernel=kernel,
        configuration={"mode": "portable"},
        capability_grant=grant,
    )
    payload = instance._state_payload()
    observations = payload["kernel"]["observations"]
    assert len(observations) >= 1
    assert observations[0]["metadata"] == {"source_type": "sensor"}
    # Full payload must be JSON-serializable
    json.dumps(payload, sort_keys=True)


def test_kernel_snapshot_restore_roundtrip(tmp_path):
    kernel = EvidenceKernel(owner_instance="test-node")
    obs = kernel.observe("fact", "local", 0.9, metadata={"k": "v"})
    kernel.add_evidence("concept", obs.id, 1.0, 1)

    snapshot = kernel.snapshot()
    wire = json.dumps(snapshot, sort_keys=True)
    decoded = json.loads(wire)
    assert decoded["observations"][0]["metadata"] == {"k": "v"}

    restored = EvidenceKernel.restore(decoded)
    assert restored.owner_instance == "test-node"
    assert obs.id in restored.observations
    assert restored.observations[obs.id].metadata == {"k": "v"}
    assert isinstance(restored.observations[obs.id].metadata, MappingProxyType)
