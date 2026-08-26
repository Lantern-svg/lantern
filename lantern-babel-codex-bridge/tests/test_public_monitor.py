"""Regression tests for the public endpoint monitor.

These exist because of a real incident: a monitor reported "ok" for eleven
days while the advertised public tunnel URL had rotated to a dead hostname,
and only the local node's own health was ever checked. Every test here
targets a specific way that failure mode could recur.
"""

from __future__ import annotations

from lantern import public_monitor as pm


HEALTHY_INTERNAL = {
    "status": "ok",
    "node_id": "lantern-field-experiment-1",
    "identity_public": {"public_key": "abc123"},
    "rendezvous": {"pending": 0, "total": 0},
}


def test_stale_advertised_endpoint_cannot_produce_overall_healthy():
    """The exact regression: node is fine, public ingress is fine, but the
    advertised URL (e.g. in the GitHub post) still points at an old,
    rotated hostname. overall_healthy must be False."""
    node = pm.evaluate_node(HEALTHY_INTERNAL, None)
    public_health = {**HEALTHY_INTERNAL}
    public_ingress = pm.evaluate_public_ingress(
        "https://current-live.trycloudflare.com",
        public_health,
        None,
        expected_node_id="lantern-field-experiment-1",
        expected_public_key="abc123",
    )
    advertised = pm.evaluate_advertised_endpoint(
        "https://survive-guest-farmers-correspondence.trycloudflare.com",
        "https://current-live.trycloudflare.com",
    )
    rendezvous = pm.evaluate_rendezvous(HEALTHY_INTERNAL["rendezvous"])

    result = pm.evaluate(node, public_ingress, advertised, rendezvous)

    assert node["healthy"] is True
    assert public_ingress["healthy"] is True
    assert advertised["stale"] is True
    assert result["overall_healthy"] is False
    assert "advertised_endpoint" in result["failed_layers"]


def test_healthy_node_behind_dead_tunnel_is_not_overall_healthy():
    """Internal node health must never substitute for public ingress
    health. A live local process behind a dead/unreachable tunnel is the
    exact scenario an external interop tester would hit."""
    node = pm.evaluate_node(HEALTHY_INTERNAL, None)
    public_ingress = pm.evaluate_public_ingress(
        "https://dead-tunnel.trycloudflare.com",
        None,
        "connection failed: Name or service not known",
        expected_node_id="lantern-field-experiment-1",
        expected_public_key="abc123",
    )
    advertised = pm.evaluate_advertised_endpoint(
        "https://dead-tunnel.trycloudflare.com", "https://dead-tunnel.trycloudflare.com"
    )
    rendezvous = pm.evaluate_rendezvous(HEALTHY_INTERNAL["rendezvous"])

    result = pm.evaluate(node, public_ingress, advertised, rendezvous)

    assert node["healthy"] is True
    assert public_ingress["healthy"] is False
    assert result["overall_healthy"] is False
    assert "public_ingress" in result["failed_layers"]
    assert result["monitor_status"] == "stale_or_unreachable_endpoint"


def test_public_health_failure_is_surfaced_not_swallowed():
    """A /health failure on the public path must be visible in the
    result, not merged away or hidden behind a generic ok."""
    public_ingress = pm.evaluate_public_ingress(
        "https://current-live.trycloudflare.com",
        {"status": "degraded", "node_id": "lantern-field-experiment-1"},
        None,
        expected_node_id="lantern-field-experiment-1",
        expected_public_key="abc123",
    )
    assert public_ingress["healthy"] is False
    assert public_ingress["health_ok"] is False
    assert "status='degraded'" in public_ingress["last_error"]


def test_endpoint_rotation_is_detected_even_when_both_urls_are_reachable():
    """If the tunnel rotated (old URL retired, new URL live) but nobody
    updated the advertised URL, that must be flagged even though the
    *current* live endpoint itself is perfectly healthy."""
    node = pm.evaluate_node(HEALTHY_INTERNAL, None)
    public_ingress = pm.evaluate_public_ingress(
        "https://new-rotated-url.trycloudflare.com",
        HEALTHY_INTERNAL,
        None,
        expected_node_id="lantern-field-experiment-1",
        expected_public_key="abc123",
    )
    advertised = pm.evaluate_advertised_endpoint(
        "https://old-retired-url.trycloudflare.com",
        "https://new-rotated-url.trycloudflare.com",
    )
    rendezvous = pm.evaluate_rendezvous(HEALTHY_INTERNAL["rendezvous"])

    result = pm.evaluate(node, public_ingress, advertised, rendezvous)

    assert public_ingress["healthy"] is True
    assert advertised["stale"] is True
    assert result["overall_healthy"] is False
    assert result["failed_layers"] == ["advertised_endpoint"]


def test_no_live_url_discovered_fails_public_ingress_not_node():
    """If the tunnel log has no announced URL at all (log rotated away,
    tunnel never started, etc.), public_ingress must fail explicitly
    rather than being silently skipped or defaulting to healthy."""
    node = pm.evaluate_node(HEALTHY_INTERNAL, None)
    public_ingress = pm.evaluate_public_ingress(
        None, None, None, expected_node_id="lantern-field-experiment-1", expected_public_key="abc123"
    )
    assert public_ingress["healthy"] is False
    assert node["healthy"] is True
    assert public_ingress["current_live_url"] is None


def test_identity_mismatch_on_public_endpoint_is_not_healthy():
    """A /health 200 from *something* at the public URL is not sufficient
    -- if the identity in the response doesn't match this node's own
    node_id/public_key, it must not be trusted as this node's endpoint
    (guards against an unrelated service answering on a reused/similar
    hostname)."""
    public_ingress = pm.evaluate_public_ingress(
        "https://current-live.trycloudflare.com",
        {"status": "ok", "node_id": "some-other-node", "identity_public": {"public_key": "zzz"}},
        None,
        expected_node_id="lantern-field-experiment-1",
        expected_public_key="abc123",
    )
    assert public_ingress["health_ok"] is True
    assert public_ingress["identity_matches_node"] is False
    assert public_ingress["healthy"] is False


def test_failed_layer_naming_distinguishes_which_layer_broke():
    """The result must name exactly which layer(s) failed, not just an
    opaque overall boolean, so an operator/monitor consumer never has to
    guess whether it was the node, the tunnel, or the advertised URL."""
    node = {"healthy": False}
    public_ingress = {"healthy": True}
    advertised = {"stale": False}
    rendezvous = {"healthy": True}
    result = pm.evaluate(node, public_ingress, advertised, rendezvous)
    assert result["failed_layers"] == ["node"]

    node_ok = {"healthy": True}
    result2 = pm.evaluate(node_ok, {"healthy": False}, {"stale": True}, {"healthy": True})
    assert set(result2["failed_layers"]) == {"public_ingress", "advertised_endpoint"}


def test_fully_healthy_path_reports_overall_healthy_true():
    """Sanity check on the positive path: when every layer genuinely
    checks out (matching URLs, matching identity, rendezvous readable),
    overall_healthy is True and no layer is listed as failed."""
    node = pm.evaluate_node(HEALTHY_INTERNAL, None)
    public_ingress = pm.evaluate_public_ingress(
        "https://current-live.trycloudflare.com",
        HEALTHY_INTERNAL,
        None,
        expected_node_id="lantern-field-experiment-1",
        expected_public_key="abc123",
    )
    advertised = pm.evaluate_advertised_endpoint(
        "https://current-live.trycloudflare.com", "https://current-live.trycloudflare.com"
    )
    rendezvous = pm.evaluate_rendezvous(HEALTHY_INTERNAL["rendezvous"])

    result = pm.evaluate(node, public_ingress, advertised, rendezvous)

    assert result["overall_healthy"] is True
    assert result["failed_layers"] == []
    assert result["monitor_status"] == "ok"


def test_discover_live_tunnel_url_reads_most_recent_announcement(tmp_path):
    """The live URL must come from the tunnel process's own log output
    (most recent announcement wins on rotation), never from a stored
    config value passed in separately."""
    log = tmp_path / "tunnel.log"
    log.write_text(
        "2026-08-11T05:45:48Z INF Your quick Tunnel has been created! "
        "https://old-one.trycloudflare.com\n"
        "2026-08-15T05:45:56Z INF Your quick Tunnel has been created! "
        "https://newest-one.trycloudflare.com\n"
    )
    assert pm.discover_live_tunnel_url(log) == "https://newest-one.trycloudflare.com"


def test_discover_live_tunnel_url_missing_log_returns_none(tmp_path):
    assert pm.discover_live_tunnel_url(tmp_path / "does-not-exist.log") is None
