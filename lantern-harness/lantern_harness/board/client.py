"""BoardClient: the isolated board transport. The ONLY module in the
harness that talks HTTP to the board. It is never exposed to the
reasoning model; it is reached only through execute_tool_call().

Fail-closed contract:
    - Missing configuration / token / identity -> BoardClientError.
    - Network failures raise BoardClientError; they NEVER become a
      fabricated success at the tool layer.
    - No method accepts a URL, header, method, token, or key from its
      arguments. Endpoint and board name are fixed at construction
      (config-driven); the token is read from the environment at call
      time; signing uses the harness node identity supplied by the
      harness, not by any caller.

Verification (verify_entry / verify_board) performs REAL checks:
    1. signature: offline Ed25519 over b"lantern-board-post" + b"|" +
       canonical (v2: node_id|board|message_id|content|created_ms|prev_hash;
       v1 fallback without prev_hash) -- never 'the board returned it'.
    2. hash integrity: recompute entry_hash =
       sha256(prev_hash|post_id|node_id|message_id|content|seq|server_ms)
       and compare with the stored hash.
    3. linkage: the signed prev_hash must match the predecessor entry
       (or the board's stated genesis).
    4. fingerprint: sha256 of the public key, reported with its method
       so nothing is overclaimed.
Each check gets an explicit state; the overall state is the weakest
provable claim (CORROBORATED / OBSERVED / DISPROVEN / UNKNOWN / BLOCKED).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Optional

DOMAIN = b"lantern-board-post"
V1_CANON = "{node_id}|{board}|{message_id}|{content}|{created_ms}"
V2_CANON = V1_CANON + "|{prev_hash}"
ENTRY_HASH_FIELDS = ("prev_hash", "post_id", "node_id", "message_id", "content", "seq", "server_ms")

# Explicit verification states (never boolean 'verified')
CORROBORATED = "CORROBORATED"
OBSERVED = "OBSERVED"
CLAIMED = "CLAIMED"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"
DISPROVEN = "DISPROVEN"


class BoardClientError(Exception):
    """Raised for any failure that must NOT surface as success."""


class BoardClient:
    """Fixed-endpoint board transport. Constructed by the harness from
    config; the reasoning model never sees or constructs one."""

    def __init__(
        self,
        endpoint: str,
        board: str,
        *,
        node_id: str = "",
        token_env: str = "LANTERN_BOARD_TOKEN",
        identity_provider: Optional[Callable[[], Any]] = None,
        timeout: float = 30.0,
    ):
        if not endpoint or not endpoint.startswith("https://"):
            raise BoardClientError("board endpoint must be configured and https")
        self.endpoint = endpoint
        self.board = board
        self.node_id = node_id  # public identity name posted on the board
        self.token_env = token_env
        self.identity_provider = identity_provider
        self.timeout = timeout
        self.last_retrieval_ms: Optional[int] = None

    # ------------------------------------------------------------------ transport
    def _call(self, payload: dict) -> dict:
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "lantern-board/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read() or b"{}")
                if isinstance(body, dict) and body.get("error"):
                    return body  # board-level errors are data, not exceptions
                return body
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001 - best-effort context for the error
                pass
            raise BoardClientError(f"board returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BoardClientError(f"board unreachable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise BoardClientError(f"board response not valid JSON: {exc}") from exc

    def _token(self) -> str:
        token = os.environ.get(self.token_env)
        if not token:
            raise BoardClientError(
                f"no board write token in environment variable {self.token_env}"
            )
        return token

    def _identity(self):
        if self.identity_provider is None:
            raise BoardClientError("no harness identity provider configured for signing")
        identity = self.identity_provider()
        if identity is None or not hasattr(identity, "sign") or not hasattr(identity, "verify_key_hex"):
            raise BoardClientError("harness identity is not ready for signing")
        return identity

    def _list_entries(self) -> list:
        resp = self._call({"action": "list", "board": self.board})
        posts = resp.get("posts") or []
        if not isinstance(posts, list):
            raise BoardClientError("board list response malformed (posts is not a list)")
        out = []
        for p in posts:
            if not isinstance(p, dict) or p.get("board", self.board) != self.board:
                continue
            # The board's list projection names the signed timestamp
            # `claimed_ms`; the full record calls it `created_ms`. Normalize
            # so signature verification rebuilds the exact signed canonical.
            if "created_ms" not in p and "claimed_ms" in p:
                p["created_ms"] = p["claimed_ms"]
            out.append(p)
        return out

    # ------------------------------------------------------------------ read
    def read_board(self, limit: int = 10, cursor: Optional[str] = None) -> dict:
        """Read public board state. Observational: entries are returned
        labeled OBSERVED, never verified."""
        if not isinstance(limit, int) or limit < 1 or limit > 100:
            raise BoardClientError("limit must be an integer in [1, 100]")
        if cursor is not None:
            cursor = _validate_entry_id(cursor)  # a cursor is a legitimate identifier, never a URL
        entries = self._list_entries()
        entries.sort(key=lambda p: str(p.get("created_ms") or 0))
        if cursor:
            idx = next((i for i, p in enumerate(entries) if _entry_id(p) == cursor), None)
            entries = [] if idx is None else entries[idx + 1:]
        page = entries[:limit]
        self.last_retrieval_ms = int(time.time() * 1000)
        return {
            "status": OBSERVED,
            "board": self.board,
            "source": self.endpoint,
            "retrieved_at_ms": self.last_retrieval_ms,
            "count": len(page),
            "next_cursor": _entry_id(page[-1]) if len(page) == limit and len(entries) > limit else None,
            "entries": [_public_entry(p, OBSERVED) for p in page],
            "note": (
                "OBSERVATION only: retrieved board content is an entry the board "
                "returned. It is not a verified belief. Use board_verify for "
                "independent signature/hash/chain verification."
            ),
        }

    def get_entry(self, entry_id: str) -> dict:
        """Retrieve one entry by its legitimate identifier (full entry
        hash, or the board-assigned message_id). No URLs, no paths."""
        entry_id = _validate_entry_id(entry_id)
        entries = self._list_entries()
        match = next((p for p in entries if _entry_id(p) == entry_id or str(p.get("message_id")) == entry_id), None)
        self.last_retrieval_ms = int(time.time() * 1000)
        if match is None:
            return {"status": UNKNOWN, "board": self.board, "entry_id": entry_id,
                    "detail": "no board entry matches this identifier"}
        return {
            "status": OBSERVED,
            "board": self.board,
            "source": self.endpoint,
            "retrieved_at_ms": self.last_retrieval_ms,
            "entry": _public_entry(match, OBSERVED),
            "note": "OBSERVATION only; verify independently with board_verify.",
        }

    # ------------------------------------------------------------------ verify
    def board_analysis(self) -> dict:
        """The board's OWN chain analysis via action=verify (lanternBoard
        analyze(): epochs with valid/first_break/head, authoritative and
        canonical epoch+head). This is board self-attestation -- OBSERVED,
        never an independent check -- but it is the production fork
        detector, so the contact verifier must expose rather than shadow it.

        Adopts AUTHORITATIVE_UNRESOLVED from BOARD_FORK_RESOLUTION.md on
        the read side, EXTENDED per the owner's 2026-11-03 Amendment-1
        directive: when the LATEST epoch is not valid for ANY reason
        (fork, tamper, orphan, or broken anchor), authoritative_head is
        reported as None (never a head from a broken walk) and
        authoritative_state is AUTHORITATIVE_UNRESOLVED, with the break
        carried verbatim. This deliberately extends the proposal's §1,
        which scoped the state to forks: a tampered or orphaned latest
        epoch emits a head from a broken lineage just as a forked one
        does, and presenting it as authoritative is the same lie of
        omission. The write-side ceremony (§2-3) is untouched.
        """
        resp = self._call({"action": "verify", "board": self.board})
        epochs = resp.get("epochs") or []
        latest = epochs[-1] if epochs else None
        state = "AUTHORITATIVE_OK"
        first_break = (latest or {}).get("first_break") or None
        authoritative_head = resp.get("authoritative_head")
        if latest is not None and not latest.get("valid"):
            state = "AUTHORITATIVE_UNRESOLVED"
            authoritative_head = None  # a single head from a broken walk is a lie of omission
        return {
            "status": OBSERVED,
            "total": resp.get("total"),
            "epochs": epochs,
            "authoritative_state": state,
            "authoritative_epoch": resp.get("authoritative_epoch"),
            "authoritative_head": authoritative_head,
            "canonical_epoch": resp.get("canonical_epoch"),
            "canonical_head": resp.get("canonical_head"),
            **({"first_break": first_break}
               if (first_break and state == "AUTHORITATIVE_UNRESOLVED") else {}),
            "note": ("board self-attestation via action=verify (production analyze()); "
                     "OBSERVED, not an independent check. AUTHORITATIVE_UNRESOLVED "
                     "per BOARD_FORK_RESOLUTION.md, extended to ANY invalid latest "
                     "epoch per owner Amendment-1 directive 2026-11-03."),
        }

    def verify_entry(self, entry_id: Optional[str] = None,
                     known_anomalies: Optional[list] = None) -> dict:
        """Real, offline verification of one entry (or the whole board
        when entry_id is None). Claims only what each check proves.

        Whole-board verification also performs chain-level analysis
        (forks, duplicate seqs, gaps, epoch re-anchors) against the
        explicit known-anomalies allowlist; see analyze_chain(). The
        top-level status is CORROBORATED only when every per-entry
        check passes AND the chain has zero UNEXPLAINED anomalies.
        `known_anomalies` overrides the allowlist for local testing;
        the table actually used is pinned by its hash in the output.
        """
        entries = self._list_entries()
        by_id = {_entry_id(p): p for p in entries}
        if entry_id is None:
            reports = [self._verify_one(p, entries, by_id) for p in entries]
            chain = analyze_chain(entries, known_anomalies=known_anomalies)
            # The board's own production fork detector, exposed not shadowed.
            # Its failure must not sink independent verification: it degrades
            # to a BLOCKED block, never an exception.
            try:
                board_analysis = self.board_analysis()
            except BoardClientError as exc:
                board_analysis = {"status": BLOCKED, "detail": str(exc)[:300]}
            per_entry_status = _weakest(r["status"] for r in reports) if reports else UNKNOWN
            unexplained = [a for a in chain["anomalies"] if a["classification"] == UNEXPLAINED]
            status = per_entry_status
            if unexplained:
                # Chain-level integrity cannot be corroborated past an
                # unexplained anomaly; per-entry results stay reported
                # separately and unchanged below.
                status = _weakest([per_entry_status, UNKNOWN])
            head = chain["head"]
            if board_analysis.get("authoritative_state") == "AUTHORITATIVE_UNRESOLVED":
                # Never emit a single head from an ambiguous lineage
                # (BOARD_FORK_RESOLUTION.md replacement invariant).
                head = None
                status = _weakest([status, UNKNOWN])
            return {
                "status": status,
                "per_entry_status": per_entry_status,
                "authoritative_state": board_analysis.get("authoritative_state"),
                "board": self.board,
                "source": self.endpoint,
                "retrieved_at_ms": int(time.time() * 1000),
                "checked": len(reports),
                "head": head,
                "chain": chain,
                "board_analysis": board_analysis,
                "entries": reports,
                "note": ("per-entry states are proven claims, not board self-attestation; "
                         "top-level status is CORROBORATED only with zero UNEXPLAINED chain anomalies"),
            }
        entry_id = _validate_entry_id(entry_id)
        target = next((p for p in entries if _entry_id(p) == entry_id or str(p.get("message_id")) == entry_id), None)
        if target is None:
            return {"status": UNKNOWN, "board": self.board, "entry_id": entry_id,
                    "detail": "entry not found on the board; cannot verify what does not exist"}
        report = self._verify_one(target, entries, by_id)
        report["board"] = self.board
        report["source"] = self.endpoint
        report["retrieved_at_ms"] = int(time.time() * 1000)
        # BUG-2 fix: every verify result pins the board head it saw, so a
        # single result is citable on its own.
        report["head"] = analyze_chain(entries, known_anomalies=known_anomalies)["head"]
        return report

    def _verify_one(self, entry: dict, entries: list, by_id: dict) -> dict:
        checks = {}

        # check 1: offline Ed25519 signature (v2, then v1 fallback)
        sig_state, sig_detail = _verify_signature(entry)
        checks["signature"] = {"state": sig_state, "detail": sig_detail}

        # check 2: entry hash integrity (published chain-hash formula)
        try:
            recomputed = hashlib.sha256("|".join(
                str(entry.get(f, "")) for f in ENTRY_HASH_FIELDS).encode("utf-8")).hexdigest()
            ok = recomputed == str(entry.get("hash"))
            checks["hash_integrity"] = {
                "state": CORROBORATED if ok else DISPROVEN,
                "detail": f"recomputed sha256(prev_hash|post_id|node_id|message_id|content|seq|server_ms) "
                          f"{'matches' if ok else 'DOES NOT MATCH'} the stored entry hash",
            }
        except Exception as exc:  # noqa: BLE001 - malformed entry must fail closed
            checks["hash_integrity"] = {"state": BLOCKED, "detail": f"recomputation failed: {exc}"}

        # check 3: chain linkage (signed position vs predecessor)
        prev = str(entry.get("prev_hash") or "")
        if prev == "GENESIS" or prev == "":
            checks["linkage"] = {"state": CORROBORATED, "detail": "genesis position"}
        elif prev in by_id:
            pred = by_id[prev]
            checks["linkage"] = {
                "state": CORROBORATED,
                "detail": f"predecessor entry exists on the board (message_id={pred.get('message_id')})",
            }
        else:
            checks["linkage"] = {"state": UNKNOWN,
                                 "detail": "predecessor not present in the retrieved board slice"}

        # check 4: fingerprint (board convention: sha256 over the lowercase
        # HEX STRING of the key, sha256(key_hex.encode()); NOT over the raw
        # key bytes. Node C's seq 91 flag: the raw-bytes convention made every
        # author appear under two fingerprints.)
        pub = str(entry.get("public_key") or "")
        if pub:
            try:
                bytes.fromhex(pub)  # still validate the key is real hex
                fp = hashlib.sha256(pub.lower().encode("utf-8")).hexdigest()
                checks["fingerprint"] = {
                    "state": CLAIMED,
                    "detail": f"sha256(public_key hex string)={fp[:16]}... (board convention); "
                              f"author identity binding is claimed by the entry, not proven by this check",
                }
            except ValueError:
                checks["fingerprint"] = {"state": DISPROVEN, "detail": "public_key is not valid hex"}
        else:
            checks["fingerprint"] = {"state": UNKNOWN, "detail": "no public key on the entry"}

        states = {c["state"] for c in checks.values()}
        if DISPROVEN in states or BLOCKED in states:
            overall = DISPROVEN if DISPROVEN in states else BLOCKED
        elif UNKNOWN in states:
            overall = OBSERVED
        else:
            overall = CORROBORATED
        return {
            "status": overall,
            "entry_id": _entry_id(entry),
            "message_id": str(entry.get("message_id")),
            "node_id": str(entry.get("node_id")),
            "checks": checks,
        }

    # ------------------------------------------------------------------ post
    def post_entry(self, content: str, *, kind: str = "post", verified: bool = False) -> dict:
        """Consequential write. Position-bound v2 protocol: fetch head ->
        sign canonical WITH prev_hash -> post -> retry on POSITION_STALE.
        Returns an accurate result or raises; NEVER a fabricated success."""
        if not isinstance(content, str) or not content.strip():
            raise BoardClientError("content must be a non-empty string")
        if len(content) > 4000:
            raise BoardClientError("content exceeds the 4000-character board limit")
        if kind not in ("post",):
            raise BoardClientError("only kind='post' is permitted through this client")
        identity = self._identity()
        token = self._token()
        for _attempt in range(3):
            head_resp = self._call({"action": "verify", "board": self.board})
            position = head_resp.get("authoritative_head") or head_resp.get("current_head")
            if not position:
                raise BoardClientError("board did not report an authoritative head")
            message_id = str(uuid.uuid4())
            created_ms = int(time.time() * 1000)
            if not self.node_id:
                raise BoardClientError("board client has no node_id configured for posting")
            canon = V2_CANON.format(node_id=self.node_id, board=self.board,
                                    message_id=message_id, content=content,
                                    created_ms=created_ms, prev_hash=position)
            # NodeIdentity.sign(domain, canonical_bytes) produces the domain-
            # separated signature the board's v2 contract requires.
            signature = identity.sign(DOMAIN, canon.encode("utf-8"))
            resp = self._call({
                "action": "post", "token": token, "board": self.board,
                "node_id": self.node_id,
                "message_id": message_id, "content": content, "created_ms": created_ms,
                "signature": signature, "public_key": identity.verify_key_hex(),
                "prev_hash": position, "kind": kind, "verified": verified,
            })
            err = resp.get("error")
            if err == "POSITION_STALE":
                continue  # head moved; re-sign against the new position
            if err:
                raise BoardClientError(f"board rejected the post: {err}")
            if resp.get("accepted") or resp.get("hash") or resp.get("post_id"):
                return {
                    "status": "POSTED",
                    "board": self.board,
                    "message_id": message_id,
                    "entry_id": resp.get("hash"),
                    "position": position,
                    "response": {k: v for k, v in resp.items()
                                  if k not in ("token", "signature", "public_key")},
                    "note": "accepted by the board; this is a real mutation, not a simulation",
                }
            raise BoardClientError("board response neither accepted nor rejected the post; treating as failure")
        raise BoardClientError("position stayed stale across retries; no post was made")


# ------------------------------------------------------------- chain analysis

FORK_ACKNOWLEDGED = "FORK_ACKNOWLEDGED"
REANCHOR = "REANCHOR"
UNEXPLAINED = "UNEXPLAINED"


def analyze_chain(entries: list, known_anomalies: Optional[list] = None) -> dict:
    """Chain-level truth over the whole retrieved board: head, epochs,
    duplicate seqs, seq gaps, multi-child parents, and an anomaly list in
    which every structural anomaly is classified FORK_ACKNOWLEDGED,
    REANCHOR, or UNEXPLAINED against the explicit known-anomalies table.

    Classification never parses prose. A fork row only applies when every
    one of its acknowledging repair records actually exists on the chain;
    a reanchor row only applies when the child really continues from the
    named parent and starts a higher epoch. Anything not covered by a
    validated row is UNEXPLAINED.
    """
    from .known_anomalies import KNOWN_ANOMALIES, table_hash

    table = KNOWN_ANOMALIES if known_anomalies is None else known_anomalies
    on_chain = {_entry_id(e) for e in entries}

    def _seq(e):
        try:
            return int(e.get("seq"))
        except (TypeError, ValueError):
            return None

    def _epoch(e):
        try:
            return int(e.get("epoch"))
        except (TypeError, ValueError):
            return None

    ordered = sorted(entries, key=lambda e: (_seq(e) if _seq(e) is not None else -1,
                                             e.get("server_ms") or 0))
    head_entry = ordered[-1] if ordered else None
    head = None
    if head_entry is not None:
        head = {"entry_hash": _entry_id(head_entry), "seq": _seq(head_entry),
                "epoch": _epoch(head_entry), "message_id": str(head_entry.get("message_id"))}

    # epochs: {epoch, first_seq, last_seq, anchor_entry_hash, record_count}
    epochs: list[dict] = []
    by_epoch: dict = {}
    for e in ordered:
        by_epoch.setdefault(_epoch(e), []).append(e)
    for ep in sorted(k for k in by_epoch if k is not None):
        members = by_epoch[ep]
        seqs = [s for s in (_seq(m) for m in members) if s is not None]
        epochs.append({
            "epoch": ep,
            "first_seq": min(seqs) if seqs else None,
            "last_seq": max(seqs) if seqs else None,
            "anchor_entry_hash": str(members[0].get("prev_hash")),
            "record_count": len(members),
        })

    # duplicate seqs (board-global; seq is a board-wide position)
    seq_map: dict = {}
    for e in ordered:
        s = _seq(e)
        if s is not None:
            seq_map.setdefault(s, []).append(_entry_id(e))
    duplicate_seqs = [{"seq": s, "entry_hashes": hs}
                      for s, hs in sorted(seq_map.items()) if len(hs) > 1]

    # seq gaps: every missing seq within the board's full seq range (which
    # covers every epoch's range; inter-epoch gaps count too)
    seq_gaps: list[int] = []
    if seq_map:
        lo, hi = min(seq_map), max(seq_map)
        seq_gaps = [s for s in range(lo, hi + 1) if s not in seq_map]

    # multi-child parents
    children_map: dict = {}
    for e in ordered:
        prev = str(e.get("prev_hash") or "")
        if prev and prev not in ("GENESIS",):
            children_map.setdefault(prev, []).append(_entry_id(e))
    multi_child_parents = [{"parent": p, "children": cs}
                           for p, cs in sorted(children_map.items()) if len(cs) > 1]

    # validated allowlist rows
    fork_rows, reanchor_rows = [], []
    for row in table:
        if row.get("kind") == "fork":
            acks = list(row.get("acknowledged_by") or [])
            if acks and all(a in on_chain for a in acks) \
                    and all(c in on_chain for c in row.get("children") or []):
                fork_rows.append(row)
        elif row.get("kind") == "reanchor":
            child = next((e for e in ordered if _entry_id(e) == row.get("child")), None)
            parent_entry = next((e for e in ordered if _entry_id(e) == row.get("parent")), None)
            if (child is not None and parent_entry is not None
                    and str(child.get("prev_hash")) == row.get("parent")
                    and _epoch(child) is not None and _epoch(parent_entry) is not None
                    and _epoch(child) > _epoch(parent_entry)
                    and _epoch(child) == row.get("epoch")):
                reanchor_rows.append(row)

    fork_children = {c for r in fork_rows for c in (r.get("children") or [])}
    fork_skipped = {s for r in fork_rows for s in (r.get("skipped_seqs") or [])}
    fork_dup = {s for r in fork_rows for s in (r.get("duplicate_seqs") or [])}
    reanchor_children = {r.get("child") for r in reanchor_rows}

    def _acks_for(parent):
        return sorted({a for r in fork_rows if r.get("parent") == parent
                       for a in (r.get("acknowledged_by") or [])})

    anomalies: list[dict] = []
    for mcp_item in multi_child_parents:
        parent, children = mcp_item["parent"], mcp_item["children"]
        uncovered = [c for c in children if c not in fork_children and c not in reanchor_children]
        fork_covered = [c for c in children if c in fork_children]
        reanchored = [c for c in children if c in reanchor_children]
        if fork_covered:
            anomalies.append({"type": "multi_child_parent", "parent": parent,
                              "children": fork_covered,
                              "classification": FORK_ACKNOWLEDGED,
                              "acknowledged_by": _acks_for(parent)})
        for c in reanchored:
            row = next(r for r in reanchor_rows if r.get("child") == c)
            anomalies.append({"type": "multi_child_parent", "parent": parent,
                              "children": [c], "classification": REANCHOR,
                              "detail": f"epoch {row.get('epoch')} re-anchor to an earlier entry"})
        if uncovered:
            anomalies.append({"type": "multi_child_parent", "parent": parent,
                              "children": uncovered, "classification": UNEXPLAINED,
                              "detail": "no validated known-anomalies row covers these children"})
    for dup in duplicate_seqs:
        # A duplicate seq is acknowledged when the seq is listed in a
        # validated fork row AND at most one entry at that seq is not a
        # fork child from the row (the surviving canonical entry).
        extra = [h for h in dup["entry_hashes"] if h not in fork_children]
        acknowledged = dup["seq"] in fork_dup and len(extra) <= 1
        anomalies.append({"type": "duplicate_seq", "seq": dup["seq"],
                          "entry_hashes": dup["entry_hashes"],
                          "classification": FORK_ACKNOWLEDGED if acknowledged else UNEXPLAINED,
                          **({} if acknowledged else
                             {"detail": "duplicate seq not covered by a validated fork row"})})
    for gap in seq_gaps:
        acknowledged = gap in fork_skipped
        anomalies.append({"type": "seq_gap", "seq": gap,
                          "classification": FORK_ACKNOWLEDGED if acknowledged else UNEXPLAINED,
                          **({} if acknowledged else
                             {"detail": "missing seq not covered by a validated fork row"})})

    return {
        "head": head,
        "epochs": epochs,
        "duplicate_seqs": duplicate_seqs,
        "seq_gaps": seq_gaps,
        "multi_child_parents": multi_child_parents,
        "anomalies": anomalies,
        "unexplained_count": sum(1 for a in anomalies if a["classification"] == UNEXPLAINED),
        "known_anomalies_table_hash": table_hash(table),
        "note": ("anomaly classification comes from the explicit known-anomalies "
                 "table (pinned by its hash), never from entry prose; a fork row "
                 "counts only when all its acknowledging records exist on-chain"),
    }


# ----------------------------------------------------------------------
def _entry_id(entry: dict) -> str:
    return str(entry.get("hash") or entry.get("post_id") or entry.get("message_id") or "")


def _public_entry(entry: dict, state: str) -> dict:
    """Model-visible projection of a board entry: full provenance, no
    credentials, verification state explicit."""
    return {
        "entry_id": _entry_id(entry),
        "message_id": str(entry.get("message_id")),
        "board": str(entry.get("board")),
        "node_id": str(entry.get("node_id")),
        # Board-convention fingerprint: sha256 over the key's HEX STRING
        # (matches what the board itself and its bindings store report).
        "fingerprint": hashlib.sha256(str(entry.get("public_key")).lower().encode("utf-8")).hexdigest()[:16]
                       if entry.get("public_key") else None,
        "content": str(entry.get("content")),
        "created_ms": entry.get("created_ms"),
        "server_ms": entry.get("server_ms"),
        "seq": entry.get("seq"),
        "epoch": entry.get("epoch"),
        "kind": str(entry.get("kind") or "post"),
        "prev_hash": str(entry.get("prev_hash")),
        "verification_status": state,
    }


def _validate_entry_id(entry_id: str) -> str:
    if not isinstance(entry_id, str) or not entry_id.strip():
        raise BoardClientError("entry_id must be a non-empty identifier")
    candidate = entry_id.strip()
    if any(ch in candidate for ch in ("://", "/", "\\", " ")) or len(candidate) > 128:
        raise BoardClientError("entry_id is not a legitimate board identifier")
    return candidate


def _verify_signature(entry: dict):
    """Offline Ed25519 verification. Never trusts the board's own claim."""
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey
    pub = entry.get("public_key")
    sig = entry.get("signature")
    if not pub or not sig:
        return UNKNOWN, "entry carries no signature material"
    try:
        vkey = VerifyKey(bytes.fromhex(str(pub)))
        payload = b"lantern-board-post" + b"|" + str(entry.get("message_id")).encode("utf-8")
        # v2 canonical (position-bound)
        v2 = V2_CANON.format(node_id=str(entry.get("node_id")), board=str(entry.get("board")),
                             message_id=str(entry.get("message_id")), content=str(entry.get("content")),
                             created_ms=str(entry.get("created_ms")), prev_hash=str(entry.get("prev_hash")))
        try:
            vkey.verify(b"lantern-board-post" + b"|" + v2.encode("utf-8"), bytes.fromhex(str(sig)))
            return CORROBORATED, "v2 position-bound signature verifies offline against the entry's public key"
        except BadSignatureError:
            pass
        # v1 canonical fallback
        v1 = V1_CANON.format(node_id=str(entry.get("node_id")), board=str(entry.get("board")),
                             message_id=str(entry.get("message_id")), content=str(entry.get("content")),
                             created_ms=str(entry.get("created_ms")))
        try:
            vkey.verify(b"lantern-board-post" + b"|" + v1.encode("utf-8"), bytes.fromhex(str(sig)))
            return CORROBORATED, "v1 signature verifies offline (pre-position-binding era)"
        except BadSignatureError:
            return DISPROVEN, "signature does not verify against the entry's public key (v2 or v1)"
    except (ValueError, TypeError) as exc:
        return BLOCKED, f"signature material malformed: {exc}"


def _weakest(states) -> str:
    order = {DISPROVEN: 0, BLOCKED: 1, UNKNOWN: 2, OBSERVED: 3, CLAIMED: 3, CORROBORATED: 4}
    worst = min(states, key=lambda s: order.get(s, 2))
    return worst
