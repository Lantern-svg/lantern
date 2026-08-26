"""Public endpoint monitor for an externally-exposed Lantern bootstrap node.

This module exists because of a real incident: a monitor reported the
system "ok" for eleven days by checking only that the local `bootstrap_node`
process was alive, while the Cloudflare Quick Tunnel URL it advertised
publicly (in a GitHub discussion) had silently rotated to a dead hostname.
Nobody trying to reach the advertised URL from outside the host could have
connected, and nothing detected it.

The core correctness rule this module enforces: **node health is not public
reachability, and public reachability is not "the URL we happen to have
written down somewhere."** Those are three distinct claims, and each one is
checked and reported independently:

  1. node        -- is the local process alive and does its own /health
                     endpoint respond? (never sufficient on its own)
  2. public_ingress -- does the CURRENTLY LIVE tunnel URL (discovered from
                     the running cloudflared process/log, not from any
                     previously-recorded config) actually resolve over DNS
                     and return a healthy /health response, from THIS node
                     (identity-matched, not an unrelated service)?
  3. advertised_endpoint -- does the URL that is publicly advertised
                     (e.g. in a GitHub discussion) match the current live
                     ingress URL? A quick tunnel's public hostname is not a
                     durable identity -- it can and does rotate -- so this
                     check exists specifically to catch that rotation
                     instead of silently trusting a hardcoded string.

`overall_healthy` is only true when every layer that was checked is
healthy. A dead public_ingress or a stale advertised_endpoint always makes
`overall_healthy` False even when node.healthy is True, and `failed_layers`
names exactly which layer(s) failed so a human/monitor consumer never has
to reverse-engineer that from a single boolean.

Network/subprocess access is isolated in small functions
(`fetch_public_health`, `fetch_advertised_endpoint`, `discover_live_tunnel_url`,
`run`) so the pure evaluation logic (`evaluate`, `evaluate_public_ingress`,
`evaluate_advertised_endpoint`) can be exercised in tests without a live
tunnel, a live GitHub discussion, or a live node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import re
import subprocess
import urllib.error
import urllib.request


TUNNEL_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# I/O boundary functions. Each one does exactly one external call and
# returns plain data (or raises/returns None on failure) -- no evaluation
# logic lives here, so tests never need to hit a real network or process.
# ---------------------------------------------------------------------------


def discover_live_tunnel_url(tunnel_log_path: str | Path) -> str | None:
    """Return the most recently announced quick-tunnel URL from a
    cloudflared log file.

    This is the source of truth for "what is the live public URL right
    now" -- it is read from the tunnel process's own output, never from a
    previously stored config value, because a stored value is exactly what
    goes stale on rotation.
    """
    path = Path(tunnel_log_path)
    if not path.exists():
        return None
    text = path.read_text(errors="replace")
    matches = TUNNEL_URL_RE.findall(text)
    return matches[-1] if matches else None


def fetch_json(url: str, timeout: float = 10.0) -> tuple[dict[str, Any] | None, str | None]:
    """GET url, return (parsed_json, None) on success or (None, error) on
    failure. DNS failures, connection failures, timeouts, non-200 status,
    and non-JSON bodies are all folded into the error string rather than
    raised, because for this monitor a failed check is data, not an
    exception to propagate."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return None, f"connection failed: {exc.reason}"
    except OSError as exc:
        return None, f"connection failed: {exc}"
    if status != 200:
        return None, f"HTTP {status}"
    try:
        return json.loads(body), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON response: {exc}"


def fetch_advertised_endpoint(owner: str, repo: str, discussion_number: int) -> tuple[str | None, int, str | None]:
    """Read the currently-advertised public endpoint and comment count
    directly from the GitHub discussion via `gh api graphql`.

    Returns (advertised_url_or_None, comment_count, error_or_None).

    "Currently advertised" means what an external reader would actually
    see as the latest word on the endpoint: the most recent comment that
    contains a tunnel URL, if any, otherwise the original discussion body.
    A correction comment posted after the original body must take
    precedence -- the original post is a historical record and is
    intentionally never rewritten, so this function has to look past it
    once a newer comment supersedes it.
    """
    query = (
        "{ repository(owner: \"%s\", name: \"%s\") { discussion(number: %d) "
        "{ body comments(first: 100) { totalCount nodes { body createdAt } } } } }"
        % (owner, repo, discussion_number)
    )
    try:
        result = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={query}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, 0, f"gh api call failed: {exc}"
    if result.returncode != 0:
        return None, 0, f"gh api call failed: {result.stderr.strip()}"
    try:
        payload = json.loads(result.stdout)
        discussion = payload["data"]["repository"]["discussion"]
        body = discussion["body"]
        comments = discussion["comments"]["nodes"]
        comment_count = discussion["comments"]["totalCount"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return None, 0, f"unexpected gh api response shape: {exc}"

    advertised = None
    for comment in sorted(comments, key=lambda c: c.get("createdAt", "")):
        matches = TUNNEL_URL_RE.findall(comment.get("body", ""))
        if matches:
            advertised = matches[-1]
    if advertised is None:
        matches = TUNNEL_URL_RE.findall(body)
        advertised = matches[-1] if matches else None
    return advertised, comment_count, None


def count_lines(path: str | Path) -> int:
    p = Path(path)
    if not p.exists():
        return 0
    with p.open("r", errors="replace") as handle:
        return sum(1 for _ in handle)


def process_alive(pid: int) -> bool:
    try:
        subprocess.run(["kill", "-0", str(pid)], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


# ---------------------------------------------------------------------------
# Pure evaluation logic. No network/process access below this line -- every
# function takes already-fetched data and returns a verdict, so this half
# of the module is exactly what the regression tests exercise.
# ---------------------------------------------------------------------------


def evaluate_node(internal_health: dict[str, Any] | None, internal_error: str | None) -> dict[str, Any]:
    healthy = internal_health is not None and internal_health.get("status") == "ok"
    return {
        "healthy": healthy,
        "internal_health_ok": healthy,
        "node_id": (internal_health or {}).get("node_id"),
        "public_key": ((internal_health or {}).get("identity_public") or {}).get("public_key"),
        "last_error": internal_error,
    }


def evaluate_public_ingress(
    current_live_url: str | None,
    public_health: dict[str, Any] | None,
    public_error: str | None,
    expected_node_id: str | None,
    expected_public_key: str | None,
) -> dict[str, Any]:
    """A public endpoint is healthy only if all of the following hold:
    a live URL was discovered, that URL's /health responded 200 with
    parseable JSON, the response says status "ok", AND the identity in
    that response matches the local node's own identity (so a stray
    unrelated service on the same hostname can't be mistaken for this
    node). Internal node health is NOT part of this function's inputs by
    design -- public ingress health must never be satisfied merely because
    the local node is fine.
    """
    if current_live_url is None:
        return {
            "current_live_url": None,
            "url_resolves": False,
            "health_ok": False,
            "identity_matches_node": False,
            "healthy": False,
            "last_error": "no live public URL could be discovered",
        }

    if public_health is None:
        url_resolves = public_error is not None and "connection failed" not in public_error
        return {
            "current_live_url": current_live_url,
            "url_resolves": url_resolves,
            "health_ok": False,
            "identity_matches_node": False,
            "healthy": False,
            "last_error": public_error or "no response",
        }

    health_ok = public_health.get("status") == "ok"
    identity_matches = (
        expected_node_id is not None
        and expected_public_key is not None
        and public_health.get("node_id") == expected_node_id
        and ((public_health.get("identity_public") or {}).get("public_key")) == expected_public_key
    )
    healthy = health_ok and identity_matches
    last_error = None
    if not health_ok:
        last_error = f"public /health reported status={public_health.get('status')!r}"
    elif not identity_matches:
        last_error = "public endpoint responded but identity does not match this node (possible unrelated service)"
    return {
        "current_live_url": current_live_url,
        "url_resolves": True,
        "health_ok": health_ok,
        "identity_matches_node": identity_matches,
        "healthy": healthy,
        "last_error": last_error,
    }


def evaluate_advertised_endpoint(
    advertised_url: str | None, current_live_url: str | None
) -> dict[str, Any]:
    """Compare what is publicly advertised (e.g. in the GitHub discussion)
    against the current live ingress URL. `stale` is true whenever they
    differ, including when advertised_url is None (nothing to compare, so
    it cannot be assumed correct) -- there is no code path here that
    reports "not stale" just because the comparison could not be made.
    """
    matches = advertised_url is not None and current_live_url is not None and advertised_url == current_live_url
    return {
        "url": advertised_url,
        "matches_current_live_url": matches,
        "stale": not matches,
    }


def evaluate_rendezvous(rendezvous_health: dict[str, Any] | None) -> dict[str, Any]:
    if rendezvous_health is None:
        return {"pending": None, "total": None, "healthy": False}
    return {
        "pending": rendezvous_health.get("pending"),
        "total": rendezvous_health.get("total"),
        "healthy": "pending" in rendezvous_health and "total" in rendezvous_health,
    }


def evaluate(
    node: dict[str, Any],
    public_ingress: dict[str, Any],
    advertised_endpoint: dict[str, Any],
    rendezvous: dict[str, Any],
    previous_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine layer verdicts into one overall result.

    `overall_healthy` requires node, public_ingress, advertised_endpoint,
    and rendezvous all healthy/non-stale. A healthy node behind a dead or
    stale tunnel must never produce overall_healthy=True -- that is
    precisely the bug this module exists to fix, so this function's return
    value is what the regression tests assert against directly.
    """
    failed_layers: list[str] = []
    if not node.get("healthy"):
        failed_layers.append("node")
    if not public_ingress.get("healthy"):
        failed_layers.append("public_ingress")
    if advertised_endpoint.get("stale"):
        failed_layers.append("advertised_endpoint")
    if not rendezvous.get("healthy"):
        failed_layers.append("rendezvous")

    overall_healthy = not failed_layers

    checked_at = _now_iso()
    previous_verification = (previous_state or {}).get("last_successful_external_verification")
    last_successful_external_verification = (
        checked_at if public_ingress.get("healthy") else previous_verification
    )

    if overall_healthy:
        status = "ok"
    elif "public_ingress" in failed_layers or "advertised_endpoint" in failed_layers:
        status = "stale_or_unreachable_endpoint"
    else:
        status = "degraded"

    return {
        "schema_version": 2,
        "checked_at": checked_at,
        "node": node,
        "public_ingress": public_ingress,
        "advertised_endpoint": advertised_endpoint,
        "rendezvous": rendezvous,
        "overall_healthy": overall_healthy,
        "failed_layers": failed_layers,
        "monitor_status": status,
        "last_successful_external_verification": last_successful_external_verification,
    }


@dataclass
class MonitorConfig:
    node_health_url: str
    tunnel_log_path: str
    github_owner: str
    github_repo: str
    discussion_number: int
    monitor_state_path: str
    fetch_public_health: Callable[[str], tuple[dict[str, Any] | None, str | None]] = field(
        default=lambda url: fetch_json(url)
    )


def run_check(config: MonitorConfig) -> dict[str, Any]:
    """Perform one full monitor pass using real I/O and return the
    combined result. This is the only function in the module that wires
    the I/O boundary functions to the pure evaluation functions -- keep it
    thin; any new logic belongs in `evaluate*`, not here."""
    internal_health, internal_error = fetch_json(config.node_health_url)
    node = evaluate_node(internal_health, internal_error)

    current_live_url = discover_live_tunnel_url(config.tunnel_log_path)
    public_health, public_error = (
        config.fetch_public_health(current_live_url + "/health") if current_live_url else (None, None)
    )
    public_ingress = evaluate_public_ingress(
        current_live_url,
        public_health,
        public_error,
        node.get("node_id"),
        node.get("public_key"),
    )

    advertised_url, comment_count, gh_error = fetch_advertised_endpoint(
        config.github_owner, config.github_repo, config.discussion_number
    )
    advertised_endpoint = evaluate_advertised_endpoint(advertised_url, current_live_url)
    if gh_error:
        advertised_endpoint["last_error"] = gh_error

    rendezvous_health = (internal_health or {}).get("rendezvous")
    rendezvous = evaluate_rendezvous(rendezvous_health)

    previous_state = None
    state_path = Path(config.monitor_state_path)
    if state_path.exists():
        try:
            previous_state = json.loads(state_path.read_text())
        except json.JSONDecodeError:
            previous_state = None

    result = evaluate(node, public_ingress, advertised_endpoint, rendezvous, previous_state)
    result["github"] = {
        "discussion_number": config.discussion_number,
        "comment_count": comment_count,
        "previous_comment_count": (previous_state or {}).get("github", {}).get("comment_count"),
    }
    return result


def write_state(result: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Lantern public endpoint monitor")
    parser.add_argument("--node-health-url", default="http://127.0.0.1:8765/health")
    parser.add_argument("--tunnel-log", required=True)
    parser.add_argument("--github-owner", default="agent-network-protocol")
    parser.add_argument("--github-repo", default="AgentNetworkProtocol")
    parser.add_argument("--discussion-number", type=int, default=93)
    parser.add_argument("--state-path", required=True)
    args = parser.parse_args()

    config = MonitorConfig(
        node_health_url=args.node_health_url,
        tunnel_log_path=args.tunnel_log,
        github_owner=args.github_owner,
        github_repo=args.github_repo,
        discussion_number=args.discussion_number,
        monitor_state_path=args.state_path,
    )
    result = run_check(config)
    write_state(result, args.state_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["overall_healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
