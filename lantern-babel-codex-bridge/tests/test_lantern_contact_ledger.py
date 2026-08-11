from lantern.contact_ledger import (
    CONTACT_STATES,
    EVIDENCE_BACKED_STATES,
    FIRST_CONTACT_MESSAGE,
    ContactAttempt,
    ContactEvidence,
    ContactLedger,
    build_contact_report,
)


def test_contact_attempted_is_not_message_received():
    ledger = ContactLedger()
    attempt = ContactAttempt(destination="https://example-peer.test", state="CONTACT_ATTEMPTED")
    ledger.record(attempt)

    latest = ledger.latest_for("https://example-peer.test")
    assert latest.state == "CONTACT_ATTEMPTED"
    assert latest.is_evidence_backed is False


def test_sent_is_not_acknowledged():
    ledger = ContactLedger()
    attempt = ledger.record(ContactAttempt(destination="peer-a", state="CONTACT_ATTEMPTED"))
    sent = ledger.record(attempt.advance("MESSAGE_SENT", evidence=ContactEvidence(
        destination="peer-a", transport="https", request_id="req-1",
    )))

    assert sent.state == "MESSAGE_SENT"
    assert sent.is_evidence_backed is False
    assert "ACKNOWLEDGED" not in {e.state for e in ledger.history_for("peer-a")}


def test_acknowledged_is_not_identity_verified():
    ledger = ContactLedger()
    attempt = ledger.record(ContactAttempt(destination="peer-b", state="CONTACT_ATTEMPTED"))
    attempt = ledger.record(attempt.advance("MESSAGE_SENT"))
    acked = ledger.record(attempt.advance("ACKNOWLEDGED", evidence=ContactEvidence(
        acknowledgment_evidence="peer replied referencing our request_id",
    )))

    assert acked.state == "ACKNOWLEDGED"
    assert acked.is_evidence_backed is True
    # identity_verified must be a SEPARATE, later, explicitly recorded step
    assert ledger.latest_for("peer-b").state != "IDENTITY_VERIFIED"


def test_identity_verified_is_not_collaboration_authorized():
    ledger = ContactLedger()
    attempt = ledger.record(ContactAttempt(destination="peer-c", state="CONTACT_ATTEMPTED"))
    attempt = ledger.record(attempt.advance("MESSAGE_SENT"))
    attempt = ledger.record(attempt.advance("ACKNOWLEDGED"))
    verified = ledger.record(attempt.advance("IDENTITY_VERIFIED", evidence=ContactEvidence(
        peer_identity_claim="claims to be lantern-peer-1",
        provenance="cryptographic challenge/response result",
    )))

    assert verified.state == "IDENTITY_VERIFIED"
    assert ledger.latest_for("peer-c").state != "COLLABORATION_NEGOTIATED"
    assert ledger.latest_for("peer-c").state != "COLLABORATION_ACTIVE"


def test_cannot_record_message_received_with_no_prior_history():
    ledger = ContactLedger()
    try:
        ledger.record(ContactAttempt(destination="peer-d", state="MESSAGE_RECEIVED"))
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "no prior contact history" in str(exc)


def test_no_contact_path_and_discovery_in_progress_do_not_require_prior_history():
    ledger = ContactLedger()
    ledger.record(ContactAttempt(destination="candidate-x", state="NO_CONTACT_PATH"))
    ledger.record(ContactAttempt(destination="candidate-y", state="DISCOVERY_IN_PROGRESS"))
    ledger.record(ContactAttempt(destination="candidate-z", state="CONTACT_PATH_FOUND"))
    # no exception


def test_local_simulation_is_never_counted_as_real_peer_contact():
    ledger = ContactLedger()
    local = ledger.record(ContactAttempt(
        destination="local-second-instance",
        state="CONTACT_ATTEMPTED",
        contact_type="LOCAL_SIMULATION",
    ))
    active = ledger.record(local.advance("MESSAGE_SENT").advance("ACKNOWLEDGED").advance(
        "COLLABORATION_ACTIVE"
    ))

    assert active.is_local_simulation is True
    assert ledger.real_peer_contacts() == []
    summary = ledger.summary()
    assert summary["peer_contact_status"] == "NOT_ESTABLISHED"


def test_real_peer_collaboration_active_flips_peer_contact_status():
    ledger = ContactLedger()
    attempt = ledger.record(ContactAttempt(
        destination="real-peer-1",
        state="CONTACT_ATTEMPTED",
        contact_type="REAL_INDEPENDENT_PEER",
    ))
    attempt = ledger.record(attempt.advance("MESSAGE_SENT"))
    attempt = ledger.record(attempt.advance("ACKNOWLEDGED"))
    attempt = ledger.record(attempt.advance("IDENTITY_VERIFIED"))
    attempt = ledger.record(attempt.advance("COLLABORATION_NEGOTIATED"))
    active = ledger.record(attempt.advance("COLLABORATION_ACTIVE"))

    assert active.contact_type == "REAL_INDEPENDENT_PEER"
    summary = ledger.summary()
    assert summary["peer_contact_status"] == "ESTABLISHED"


def test_unknown_contact_state_is_rejected():
    try:
        ContactAttempt(destination="x", state="TOTALLY_MADE_UP")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unknown contact state" in str(exc)


def test_unknown_contact_type_is_rejected():
    try:
        ContactAttempt(destination="x", state="NO_CONTACT_PATH", contact_type="MADE_UP_TYPE")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "unknown contact type" in str(exc)


def test_build_contact_report_reports_not_established_when_no_peer_exists():
    ledger = ContactLedger()
    ledger.record(ContactAttempt(destination="candidate-1", state="CONTACT_PATH_FOUND"))

    report = build_contact_report(ledger)
    assert report["PEER_CONTACT_STATUS"] == "NOT_ESTABLISHED"
    assert report["PEER_FOUND"] is False
    assert report["INTEROPERABILITY_TEST"] == "NOT_STARTED"


def test_build_contact_report_never_upgrades_uncertainty_into_success():
    ledger = ContactLedger()
    attempt = ledger.record(ContactAttempt(
        destination="candidate-2",
        state="CONTACT_ATTEMPTED",
        contact_type="REAL_INDEPENDENT_PEER",
    ))
    ledger.record(attempt.advance("MESSAGE_SENT"))
    ledger.record(attempt.advance("DELIVERY_UNKNOWN", evidence=ContactEvidence(
        failure_reason="no response yet, delivery cannot be confirmed",
    )))

    report = build_contact_report(ledger)
    assert report["ACKNOWLEDGMENTS"] == 0
    assert report["IDENTITY_VERIFIED"] == 0
    assert report["PEER_CONTACT_STATUS"] == "NOT_ESTABLISHED"


def test_first_contact_message_requests_no_authority_transfer():
    assert "no authority" in FIRST_CONTACT_MESSAGE.lower() or "authority transfer" in FIRST_CONTACT_MESSAGE.lower()
    assert "no code execution" in FIRST_CONTACT_MESSAGE.lower()
    assert "bounded" in FIRST_CONTACT_MESSAGE.lower()


def test_contact_states_include_the_full_requested_vocabulary():
    expected = {
        "NO_CONTACT_PATH",
        "DISCOVERY_IN_PROGRESS",
        "CONTACT_PATH_FOUND",
        "CONTACT_ATTEMPTED",
        "MESSAGE_SENT",
        "DELIVERY_UNKNOWN",
        "MESSAGE_RECEIVED",
        "ACKNOWLEDGED",
        "IDENTITY_VERIFIED",
        "COLLABORATION_NEGOTIATED",
        "COLLABORATION_ACTIVE",
        "CONTACT_FAILED",
    }
    assert set(CONTACT_STATES) == expected


def test_evidence_backed_states_exclude_pure_intent_states():
    assert "CONTACT_ATTEMPTED" not in EVIDENCE_BACKED_STATES
    assert "MESSAGE_SENT" not in EVIDENCE_BACKED_STATES
    assert "MESSAGE_RECEIVED" in EVIDENCE_BACKED_STATES
