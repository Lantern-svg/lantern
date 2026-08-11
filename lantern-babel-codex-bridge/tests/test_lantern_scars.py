"""Lantern Scar persistence tests."""

from pathlib import Path

import pytest

from lantern.core import Lantern
from lantern.scars import (
    ACTIVE,
    SCAR_EVENT_TYPE,
    ScarPersistenceStatus,
    create_network_scar,
    create_scar,
    describe_scar_claim,
    scar_persistence_status,
    should_record_network_scar,
)


def test_scar_persistence_status_reports_active_durable_mechanism():
    status = scar_persistence_status()
    assert isinstance(status, ScarPersistenceStatus)
    assert status.status == ACTIVE
    assert "chronicle" in status.reason.lower()


def test_describe_scar_claim_is_still_not_marked_persisted():
    claim = describe_scar_claim("SCAR-001", "constructed only")
    assert claim["scar_id"] == "SCAR-001"
    assert claim["persisted"] is False
    assert claim["persistence_status"]["status"] == ACTIVE


def test_scar_can_be_constructed_without_being_persisted():
    record = create_scar(
        source="network",
        trigger="handshake_attempt",
        observation="peer rejected capability",
        outcome="REJECTED_CAPABILITY",
        severity="medium",
    )

    assert record.constructed is True
    assert record.persisted is False
    assert record.verified is False
    assert record.replayed is False
    assert record.scar.outcome == "REJECTED_CAPABILITY"


def test_persist_scar_writes_to_chronicle_and_verifies(tmp_path):
    lantern = Lantern(chronicle_filename=tmp_path / "chronicle.jsonl")
    record = lantern.create_scar(
        source="network",
        trigger="handshake_attempt",
        observation="peer protocol mismatch",
        outcome="INCOMPATIBLE_PROTOCOL",
        severity="high",
        lesson="version negotiation required before exchange",
    )

    persisted = lantern.persist_scar(record)

    assert persisted.persisted is True
    assert persisted.verified is True
    assert lantern.verify_scar(record.scar.id) is True
    chronicle_text = (tmp_path / "chronicle.jsonl").read_text(encoding="utf-8")
    assert SCAR_EVENT_TYPE in chronicle_text
    assert record.scar.id in chronicle_text


def test_scar_survives_restart_and_replays_from_public_state(tmp_path):
    chronicle_path = tmp_path / "chronicle.jsonl"

    writer = Lantern(chronicle_filename=chronicle_path)
    record = writer.create_scar(
        source="integration",
        trigger="experiment_result",
        observation="adapter rollback preserved sovereignty",
        outcome="INTEGRATION_ROLLBACK",
        severity="medium",
        lesson="reversible boundaries matter",
    )
    persisted = writer.persist_scar(record)
    assert persisted.persisted is True

    reader = Lantern(chronicle_filename=chronicle_path)
    reader.startup()

    recovered = reader.load_scar(record.scar.id)
    assert recovered is not None
    assert recovered.persisted is True
    assert reader.verify_scar(record.scar.id) is True
    replayed_ids = [item.scar.id for item in reader.replay_scars()]
    assert record.scar.id in replayed_ids


def test_snapshot_restore_preserves_scars(tmp_path):
    chronicle_path = tmp_path / "chronicle.jsonl"
    writer = Lantern(chronicle_filename=chronicle_path)
    record = writer.create_scar(
        source="network",
        trigger="verification_outcome",
        observation="peer provenance invalid",
        outcome="INVALID_PROVENANCE",
        severity="high",
    )
    writer.persist_scar(record)
    writer.save_snapshot()

    reader = Lantern(chronicle_filename=chronicle_path)
    reader.startup()

    recovered = reader.load_scar(record.scar.id)
    assert recovered is not None
    assert recovered.scar.observation == "peer provenance invalid"


def test_corrupted_chronicle_is_detected_before_replay(tmp_path):
    chronicle_path = tmp_path / "chronicle.jsonl"
    lantern = Lantern(chronicle_filename=chronicle_path)
    record = lantern.create_scar(
        source="network",
        trigger="failed_handshake",
        observation="peer sent malformed watermark",
        outcome="FAILED_HANDSHAKE",
        severity="medium",
    )
    lantern.persist_scar(record)

    path = Path(chronicle_path)
    data = path.read_text(encoding="utf-8")
    path.write_text(data.replace("FAILED_HANDSHAKE", "TAMPERED_HANDSHAKE"), encoding="utf-8")

    reader = Lantern(chronicle_filename=chronicle_path)
    with pytest.raises(RuntimeError, match="Chronicle verification failed"):
        reader.startup()


def test_failed_persistence_does_not_report_persisted_true(tmp_path, monkeypatch):
    lantern = Lantern(chronicle_filename=tmp_path / "chronicle.jsonl")
    record = lantern.create_scar(
        source="network",
        trigger="failed_write",
        observation="chronicle append interrupted",
        outcome="FAILED_HANDSHAKE",
        severity="high",
    )

    def fail_append(event):
        raise OSError("append failed")

    monkeypatch.setattr(lantern.bus.chronicle, "append", fail_append)

    with pytest.raises(OSError, match="append failed"):
        lantern.persist_scar(record)

    assert record.persisted is False
    assert lantern.load_scar(record.scar.id) is None


def test_network_scar_requires_meaningful_outcome():
    assert should_record_network_scar(outcome="FAILED_HANDSHAKE", meaningful=True) is True
    assert should_record_network_scar(outcome="FAILED_HANDSHAKE", meaningful=False) is False
    assert should_record_network_scar(outcome="TRIVIAL_PING", meaningful=True) is False


def test_network_integration_can_create_durable_scar(tmp_path):
    lantern = Lantern(chronicle_filename=tmp_path / "chronicle.jsonl")
    record = create_network_scar(
        source="federation",
        trigger="remote_observation_verification",
        observation="remote claim contradicted local evidence and failed provenance review",
        outcome="CONTRADICTORY_OBSERVATION",
        severity="high",
        provenance={"remote_instance": "peer-1"},
    )

    persisted = lantern.persist_scar(record)

    assert persisted.persisted is True
    assert persisted.verified is True
    assert lantern.load_scar(record.scar.id).scar.provenance["remote_instance"] == "peer-1"
