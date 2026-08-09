"""Lantern Scar persistence honesty tests.

Locks in Principle 1 (claim != state) and Principle 6 (no fabricated
Scar persistence) from the v0.94 revision: describing a Scar in a
Python dict or a chat response must never be reported as, or
mistaken for, a durable write.
"""

from lantern.scars import (
    NOT_IMPLEMENTED,
    ScarPersistenceStatus,
    describe_scar_claim,
    scar_persistence_status,
)


def test_scar_persistence_status_is_not_implemented():
    status = scar_persistence_status()
    assert isinstance(status, ScarPersistenceStatus)
    assert status.status == NOT_IMPLEMENTED
    assert "no scar-specific durable store" in status.reason.lower()


def test_scar_persistence_status_to_dict_matches_fields():
    status = scar_persistence_status()
    assert status.to_dict() == {"status": NOT_IMPLEMENTED, "reason": status.reason}


def test_describe_scar_claim_is_never_marked_persisted():
    """A Scar-shaped dict is category C (generated data), not category D
    (persisted state) -- persisted must always be False, and the
    persistence_status must always be surfaced alongside it so a
    caller cannot accidentally drop the disclaimer.
    """
    claim = describe_scar_claim("SCAR-001", "remote reliability reaches Evidence weight unmediated")

    assert claim["scar_id"] == "SCAR-001"
    assert claim["persisted"] is False
    assert claim["persistence_status"]["status"] == NOT_IMPLEMENTED


def test_describe_scar_claim_does_not_write_any_file(tmp_path, monkeypatch):
    """Building a Scar description must not touch the filesystem at all --
    there is no real persistence mechanism to accidentally invoke.
    """
    import pathlib

    original_open = pathlib.Path.open

    def _guard(self, *args, **kwargs):
        raise AssertionError(f"describe_scar_claim must not touch the filesystem, tried: {self}")

    monkeypatch.setattr(pathlib.Path, "open", _guard)
    try:
        describe_scar_claim("SCAR-002", "no write should happen")
    finally:
        monkeypatch.setattr(pathlib.Path, "open", original_open)
