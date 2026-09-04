"""Identity Witness Ledger (LAR-1, Phase 1).

An out-of-directory, host-scoped, append-only JSONL ledger that
witnesses node_id -> public_key registrations so that TOTAL loss of an
identity directory can no longer masquerade as first-time creation.

The witness is a WITNESS, NOT AN AUTHORITY:

- It can REFUSE an unsafe state.
- It can never create, rotate, resurrect, or authorize a
  cryptographic identity.
- It stores PUBLIC material only: node_ids, public keys, signatures,
  nonces, timestamps, operator notes. No private keys. No secrets.

The invariant is absolute:

    A node_id maps to at most one public key for its entire lifetime.
    Same node_id + different public key is a FORK -- never rotation,
    never recovery.

Event types (exactly five; there is deliberately no ROTATE):

- GENESIS       establishes the chain (previous_hash="GENESIS")
- REGISTER      binds node_id permanently to public_key, with binding
                signature + fresh proof-of-possession
- RECOVER       the SAME previously registered key material was
                restored; proves possession of the REGISTERED key
                with a nonce challenge; never permits a new key
- RETIRE        authenticated by proof of possession; the node_id is
                permanently dead afterwards
- FORCE_RETIRE  the sole unauthenticated event: an explicit operator
                ceremony, recorded with acknowledged_fork_risk=true.
                It authorizes nothing: a replacement identity needs
                a NEW node_id.

Hash-chain construction is the EXACT Chronicle pattern from core.py:

    body   = record fields minus (timestamp, previous_hash, current_hash)
    digest = sha256(previous_hash + json.dumps(body, sort_keys=True))

File writes use the Chronicle's proven staged-append pattern
(NamedTemporaryFile in the same directory + fsync + os.replace),
guarded by a sidecar flock to serialize cross-process appends.

Default path: ~/.lantern/registry.jsonl (operator-configurable).
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from nacl import secret
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from .identity import (
    FORK_DETECTED,
    NODE_ID_RETIRED,
    NOT_REGISTERED,
    RECOVER_KEY_MISMATCH,
    REGISTRY_CORRUPTED,
    WitnessError,
    load_or_create,
    verify_binding,
)

DEFAULT_WITNESS_REGISTRY_PATH = Path.home() / ".lantern" / "registry.jsonl"

# Domain-separated signing namespaces, mirroring the identity module's
# binding/challenge domains. A signature over one domain can never be
# replayed as another event type.
_DOMAIN_REGISTER = b"lantern.witness.register.v1"
_DOMAIN_RECOVER = b"lantern.witness.recover.v1"
_DOMAIN_RETIRE = b"lantern.witness.retire.v1"

_HASH_EXCLUDED = ("timestamp", "previous_hash", "current_hash")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pop_payload(event_type: str, node_id: str, public_key_hex: str, nonce: str) -> bytes:
    return f"{event_type}|{node_id}|{public_key_hex}|{nonce}".encode("utf-8")


def _verify_pop(domain: bytes, payload: bytes, public_key_hex: str, signature_hex: str) -> bool:
    try:
        verify_key = VerifyKey(public_key_hex.encode("ascii"), encoder=HexEncoder)
        verify_key.verify(domain + b"|" + payload, bytes.fromhex(signature_hex))
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False


def _canonical_digest(previous_hash: str, body: dict) -> str:
    # Exact Chronicle construction (core.py): hash previous chain link
    # plus the canonical JSON of the non-meta fields.
    return hashlib.sha256(
        (previous_hash + json.dumps(body, sort_keys=True)).encode()
    ).hexdigest()


def _event_body(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in _HASH_EXCLUDED}


class IdentityWitness:
    """Append-only witness ledger for node_id -> public_key bindings.

    Public material only. One ledger per host, decoupled from every
    node's data/identity/chronicle directories. It refuses forks; it
    never grants anything.
    """

    def __init__(self, registry_path: str | Path | None = None):
        self.path = Path(registry_path) if registry_path else DEFAULT_WITNESS_REGISTRY_PATH
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    # ------------------------------------------------------------
    # Chain integrity
    # ------------------------------------------------------------

    def verify_chain(self) -> bool:
        """True iff the on-disk ledger is absent (trivially valid) or its
        hash chain and index sequence are intact."""
        if not self.path.exists():
            return True
        try:
            self._load_verified_events()
            return True
        except WitnessError:
            return False

    def _read_lines(self) -> list:
        records = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                records.append(json.loads(line))  # malformed JSON -> corrupted
        return records

    def _load_verified_events(self) -> list:
        """Parse + verify the chain + semantic invariants. Raises
        WitnessError(REGISTRY_CORRUPTED) on any tampering."""
        if not self.path.exists():
            return []
        try:
            records = self._read_lines()
        except (ValueError, OSError) as exc:
            raise WitnessError(
                REGISTRY_CORRUPTED, f"witness ledger at {self.path} is unreadable: {exc}"
            ) from exc

        previous = "GENESIS"
        registered: dict = {}
        for position, record in enumerate(records):
            try:
                if record["previous_hash"] != previous:
                    raise WitnessError(
                        REGISTRY_CORRUPTED,
                        f"chain break at record {position}: previous_hash mismatch",
                    )
                body = _event_body(record)
                digest = _canonical_digest(previous, body)
                if digest != record["current_hash"]:
                    raise WitnessError(
                        REGISTRY_CORRUPTED,
                        f"hash mismatch at record {position}",
                    )
                if record.get("index") != position:
                    raise WitnessError(
                        REGISTRY_CORRUPTED,
                        f"index discontinuity at record {position}",
                    )
            except KeyError as exc:
                raise WitnessError(
                    REGISTRY_CORRUPTED, f"missing field {exc} at record {position}"
                ) from exc
            previous = digest

            # Semantic invariant: a node_id may never appear REGISTERed
            # to two different public keys, even in a hash-intact
            # hand-crafted ledger.
            if record["type"] == "REGISTER":
                seen = registered.get(record["node_id"])
                if seen is not None and seen != record["public_key"]:
                    raise WitnessError(
                        REGISTRY_CORRUPTED,
                        f"semantic fork in ledger: node_id {record['node_id']!r} "
                        "registered to two different public keys",
                    )
                registered[record["node_id"]] = record["public_key"]

        if records and records[0]["type"] != "GENESIS":
            raise WitnessError(REGISTRY_CORRUPTED, "first ledger record is not GENESIS")
        return records

    # ------------------------------------------------------------
    # State derivation
    # ------------------------------------------------------------

    def lookup(self, node_id: str):
        """Return (status, public_key) for node_id.

        status in {"absent", "active", "retired"}.
        Raises WitnessError(REGISTRY_CORRUPTED) on a tampered ledger.
        """
        status = "absent"
        public_key = None
        for record in self._load_verified_events():
            if record.get("node_id") != node_id:
                continue
            if record["type"] in ("REGISTER", "RECOVER"):
                status = "active"
                public_key = record["public_key"]
            elif record["type"] in ("RETIRE", "FORCE_RETIRE"):
                status = "retired"
        return status, public_key

    # ------------------------------------------------------------
    # Append machinery (Chronicle staged-write pattern + flock)
    # ------------------------------------------------------------

    def _append_event(self, event: dict) -> dict:
        """Append one event under the sidecar lock, extending the chain."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "a+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                events = self._load_verified_events()
                previous = events[-1]["current_hash"] if events else "GENESIS"
                event["index"] = len(events)
                event["previous_hash"] = previous
                event["current_hash"] = _canonical_digest(previous, _event_body(event))
                record = {
                    "timestamp": _now(),
                    "previous_hash": event["previous_hash"],
                    "current_hash": event["current_hash"],
                    **_event_body(event),
                }
                serialized = json.dumps(record, sort_keys=True)
                staged = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="w",
                        encoding="utf-8",
                        dir=self.path.parent,
                        prefix="." + self.path.name + ".",
                        suffix=".tmp",
                        delete=False,
                    ) as out:
                        staged = Path(out.name)
                        if self.path.exists():
                            with self.path.open(encoding="utf-8") as existing:
                                out.write(existing.read())
                        out.write(serialized)
                        out.write("\n")
                        out.flush()
                        os.fsync(out.fileno())
                    with staged.open(encoding="utf-8") as verify_handle:
                        lines = [line for line in verify_handle if line.strip()]
                    if not lines or lines[-1].strip() != serialized:
                        raise OSError("witness staging verification failed")
                    os.replace(staged, self.path)
                    staged = None
                except BaseException:
                    if staged is not None:
                        staged.unlink(missing_ok=True)
                    raise
                return record
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _ensure_genesis(self) -> None:
        if not self.path.exists():
            self._append_event({"type": "GENESIS", "note": "lantern identity witness ledger"})

    @staticmethod
    def _pop(identity, domain: bytes, event_type: str) -> dict:
        nonce = secrets.token_hex(16)
        payload = _pop_payload(event_type, identity.node_id, identity.public_key_hex, nonce)
        return {
            "nonce": nonce,
            "signature": identity.sign(domain, payload),
            "signed_at": _now(),
        }

    @staticmethod
    def _binding_signature(identity) -> str:
        binding = json.loads(
            (Path(identity.identity_dir) / "binding.json").read_text(encoding="utf-8")
        )
        signature = binding.get("signature", "")
        if not verify_binding(identity.node_id, identity.public_key_hex, signature):
            raise WitnessError(
                REGISTRY_CORRUPTED,
                "binding.json signature for node_id {!r} is invalid; "
                "refusing to witness a broken identity".format(identity.node_id),
            )
        return signature

    # ------------------------------------------------------------
    # Ceremonies
    # ------------------------------------------------------------

    def register(self, node_id: str, identity, backfill: bool = False) -> dict:
        """Bind node_id permanently to identity.public_key_hex.

        Idempotent for an identical re-registration; refuses any
        conflicting key (fork) and any retired node_id.
        """
        if identity.node_id != node_id:
            raise WitnessError(
                FORK_DETECTED,
                "identity node_id {!r} does not match requested node_id {!r}".format(
                    identity.node_id, node_id
                ),
            )
        self._ensure_genesis()
        status, public_key = self.lookup(node_id)
        if status == "retired":
            raise WitnessError(
                NODE_ID_RETIRED,
                "node_id {!r} is retired and permanently dead; "
                "a retired node_id can never be associated with another key".format(node_id),
            )
        if status == "active":
            if public_key == identity.public_key_hex:
                return {"status": "already_registered", "public_key": public_key}
            raise WitnessError(
                FORK_DETECTED,
                "node_id {!r} is already registered to public key {}; "
                "a second key under the same node_id is a fork".format(node_id, public_key),
            )
        return self._append_event(
            {
                "type": "REGISTER",
                "node_id": node_id,
                "public_key": identity.public_key_hex,
                "binding_signature": self._binding_signature(identity),
                "pop": self._pop(identity, _DOMAIN_REGISTER, "REGISTER"),
                "backfill": bool(backfill),
            }
        )

    def recover(self, node_id: str, identity, provenance: str = "operator backup") -> dict:
        """Record that the SAME registered key material was restored.

        Proves possession of the already-registered public key with a
        fresh nonce challenge. NEVER permits a new public key.
        """
        self._ensure_genesis()
        status, public_key = self.lookup(node_id)
        if status == "absent":
            raise WitnessError(
                NOT_REGISTERED,
                "node_id {!r} has no active registration to recover".format(node_id),
            )
        if status == "retired":
            raise WitnessError(
                NODE_ID_RETIRED, "node_id {!r} is retired; recovery is impossible".format(node_id)
            )
        if public_key != identity.public_key_hex:
            raise WitnessError(
                RECOVER_KEY_MISMATCH,
                "node_id {!r} is registered to public key {}; "
                "recovery with a different key is a fork, never recovery".format(
                    node_id, public_key
                ),
            )
        return self._append_event(
            {
                "type": "RECOVER",
                "node_id": node_id,
                "public_key": public_key,
                "pop": self._pop(identity, _DOMAIN_RECOVER, "RECOVER"),
                "provenance": provenance,
            }
        )

    def retire(self, node_id: str, identity, reason: str = "") -> dict:
        """Authenticated retirement. The node_id is permanently dead."""
        self._ensure_genesis()
        status, public_key = self.lookup(node_id)
        if status == "absent":
            raise WitnessError(NOT_REGISTERED, "node_id {!r} is not registered".format(node_id))
        if status == "retired":
            return {"status": "already_retired"}
        if public_key != identity.public_key_hex:
            raise WitnessError(
                FORK_DETECTED,
                "refusing to retire node_id {!r} with a key that is not "
                "the registered one".format(node_id),
            )
        return self._append_event(
            {
                "type": "RETIRE",
                "node_id": node_id,
                "public_key": public_key,
                "pop": self._pop(identity, _DOMAIN_RETIRE, "RETIRE"),
                "reason": reason,
            }
        )

    def force_retire(
        self, node_id: str, note: str = "", *, acknowledged_fork_risk: bool = False
    ) -> dict:
        """The sole UNAUTHENTICATED event. Explicit operator ceremony.

        Requires acknowledged_fork_risk=True. It authorizes nothing:
        after a FORCE_RETIRE the node_id is permanently dead and a
        replacement identity must use a NEW node_id.
        """
        if not acknowledged_fork_risk:
            raise WitnessError(
                "FORK_RISK_NOT_ACKNOWLEDGED",
                "force retirement is an explicit, audited operator action; "
                "pass acknowledged_fork_risk=true and an operator note",
            )
        self._ensure_genesis()
        status, _ = self.lookup(node_id)
        if status == "absent":
            raise WitnessError(NOT_REGISTERED, "node_id {!r} is not registered".format(node_id))
        if status == "retired":
            return {"status": "already_retired"}
        return self._append_event(
            {
                "type": "FORCE_RETIRE",
                "node_id": node_id,
                "operator_note": note,
                "acknowledged_fork_risk": True,
            }
        )

    # ------------------------------------------------------------
    # Registry export/import (tamper mitigation, operator custody)
    # ------------------------------------------------------------

    def export_snapshot(self, destination) -> dict:
        """Copy the verified ledger to an operator-held location."""
        events = self._load_verified_events()  # refuse to export a corrupt ledger
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = self.path.read_bytes()
        destination.write_bytes(data)
        os.chmod(destination, stat.S_IRUSR | stat.S_IWUSR)
        return {"records": len(events), "sha256": hashlib.sha256(data).hexdigest()}

    def import_snapshot(self, source) -> dict:
        """Install an operator-held export over the local ledger, but
        only after verifying the source chain independently."""
        source = Path(source)
        data = source.read_bytes()
        try:
            lines = [json.loads(l) for l in data.decode("utf-8").splitlines() if l.strip()]
        except (ValueError, UnicodeDecodeError) as exc:
            raise WitnessError(
                REGISTRY_CORRUPTED, f"source snapshot is unreadable: {exc}"
            ) from exc
        previous = "GENESIS"
        for position, record in enumerate(lines):
            if record["previous_hash"] != previous:
                raise WitnessError(
                    REGISTRY_CORRUPTED, "source snapshot chain break at record {}".format(position)
                )
            digest = _canonical_digest(previous, _event_body(record))
            if digest != record["current_hash"]:
                raise WitnessError(
                    REGISTRY_CORRUPTED, "source snapshot hash mismatch at record {}".format(position)
                )
            previous = digest
        staged = self.path.with_suffix(self.path.suffix + ".import.tmp")
        staged.write_bytes(data)
        os.replace(staged, self.path)
        return {"installed_records": len(lines)}


# ============================================================
# Operator custody: encrypted identity export (NO auto-escrow)
# ============================================================


def export_identity_encrypted(identity, passphrase: str, out_path) -> dict:
    """Encrypt the FULL identity (public material + private key) with a
    passphrase (scrypt) into an operator-held backup file. Explicit,
    opt-in, initiated by the operator -- never automatic."""
    private_bytes = (Path(identity.identity_dir) / "private_key.bin").read_bytes()
    public_bytes = (Path(identity.identity_dir) / "public_key.bin").read_bytes()
    binding_bytes = (Path(identity.identity_dir) / "binding.json").read_bytes()
    plaintext = json.dumps(
        {
            "node_id": identity.node_id,
            "public_key_hex": identity.public_key_hex,
            "private_key_hex": private_bytes.hex(),
            "public_key_bin_hex": public_bytes.hex(),
            "binding": binding_bytes.decode("utf-8"),
        },
        sort_keys=True,
    ).encode("utf-8")

    salt = os.urandom(16)
    box_nonce = os.urandom(secret.SecretBox.NONCE_SIZE)
    key = hashlib.scrypt(
        passphrase.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024
    )
    box = secret.SecretBox(key)
    # SecretBox.encrypt(message, nonce) returns nonce||ciphertext||mac
    # combined; store ONLY the ciphertext||mac part -- the nonce is a
    # separate envelope field, never duplicated.
    encrypted = box.encrypt(plaintext, box_nonce)
    ciphertext = encrypted.ciphertext

    envelope = {
        "format": "lantern.identity.export.v1",
        "kdf": "scrypt",
        "kdf_params": {"n": 32768, "r": 8, "p": 1, "salt": salt.hex(), "dklen": 32},
        "node_id": identity.node_id,
        "public_key_hex": identity.public_key_hex,
        "nonce": box_nonce.hex(),
        "ciphertext": ciphertext.hex(),
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(envelope, indent=2, sort_keys=True))
    os.chmod(out_path, stat.S_IRUSR | stat.S_IWUSR)
    return {"node_id": identity.node_id, "public_key_hex": identity.public_key_hex, "path": str(out_path)}


def restore_identity_from_backup(backup_path, passphrase: str, identity_dir):
    """Decrypt an operator-held backup and restore the identity files.

    Refuses to overwrite ANY existing identity material. Returns the
    restored NodeIdentity. The restored key must match the envelope's
    recorded public key and a valid binding signature, or nothing is
    written.
    """
    envelope = json.loads(Path(backup_path).read_text(encoding="utf-8"))
    if envelope.get("format") != "lantern.identity.export.v1":
        raise WitnessError("UNSUPPORTED_BACKUP", "unknown backup format {!r}".format(envelope.get("format")))
    params = envelope["kdf_params"]
    key = hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=bytes.fromhex(params["salt"]),
        n=params["n"],
        r=params["r"],
        p=params["p"],
        dklen=params["dklen"],
        maxmem=64 * 1024 * 1024,
    )
    box = secret.SecretBox(key)
    try:
        plaintext = box.decrypt(bytes.fromhex(envelope["ciphertext"]), bytes.fromhex(envelope["nonce"]))
    except Exception as exc:
        raise WitnessError("BACKUP_DECRYPT_FAILED", "wrong passphrase or corrupted backup") from exc
    payload = json.loads(plaintext.decode("utf-8"))

    node_id = payload["node_id"]
    private_bytes = bytes.fromhex(payload["private_key_hex"])
    signing_key = SigningKey(private_bytes)
    public_key_hex = signing_key.verify_key.encode(encoder=HexEncoder).decode("ascii")
    if public_key_hex != payload["public_key_hex"] or public_key_hex != envelope["public_key_hex"]:
        raise WitnessError(
            "BACKUP_KEY_MISMATCH", "restored private key does not match the recorded public key"
        )
    binding = json.loads(payload["binding"])
    if not verify_binding(node_id, public_key_hex, binding.get("signature", "")):
        raise WitnessError("BACKUP_BINDING_INVALID", "backup binding signature is invalid")

    from .identity import _identity_paths as _paths

    identity_dir = Path(identity_dir)
    paths = _paths(identity_dir)
    existing = [k for k in ("binding", "public_key", "private_key") if paths[k].exists()]
    if existing:
        raise WitnessError(
            "REFUSING_OVERWRITE",
            "identity material already present at {}; "
            "restoration must never overwrite".format(str(identity_dir)),
        )
    identity_dir.mkdir(parents=True, exist_ok=True)
    paths["private_key"].write_bytes(private_bytes)
    os.chmod(paths["private_key"], stat.S_IRUSR | stat.S_IWUSR)
    paths["public_key"].write_bytes(bytes(signing_key.verify_key))
    paths["binding"].write_text(json.dumps(binding, indent=2, sort_keys=True))
    return load_or_create(node_id, identity_dir)


# ============================================================
# Operator CLI
# ============================================================


def main(argv=None):  # pragma: no cover - thin operator surface
    import argparse

    parser = argparse.ArgumentParser(description="Lantern Identity Witness Ledger (LAR-1 Phase 1)")
    parser.add_argument("--registry", default=str(DEFAULT_WITNESS_REGISTRY_PATH))
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("--node-id", default=None)

    sub.add_parser("verify-chain")

    p_export = sub.add_parser("export")
    p_export.add_argument("--node-id", required=True)
    p_export.add_argument("--identity-dir", required=True)
    p_export.add_argument("--out", required=True)

    p_restore = sub.add_parser("restore")
    p_restore.add_argument("--backup", required=True)
    p_restore.add_argument("--identity-dir", required=True)

    p_recover = sub.add_parser("recover")
    p_recover.add_argument("--node-id", required=True)
    p_recover.add_argument("--identity-dir", required=True)

    p_retire = sub.add_parser("retire")
    p_retire.add_argument("--node-id", required=True)
    p_retire.add_argument("--identity-dir", required=True)
    p_retire.add_argument("--reason", default="")

    p_force = sub.add_parser("force-retire")
    p_force.add_argument("--node-id", required=True)
    p_force.add_argument("--note", required=True)
    p_force.add_argument("--acknowledge-fork-risk", action="store_true")

    p_reg_export = sub.add_parser("export-registry")
    p_reg_export.add_argument("--out", required=True)

    p_reg_import = sub.add_parser("import-registry")
    p_reg_import.add_argument("--src", required=True)

    args = parser.parse_args(argv)
    witness = IdentityWitness(args.registry)

    if args.command == "status":
        if args.node_id:
            status, pk = witness.lookup(args.node_id)
            print(json.dumps({"node_id": args.node_id, "status": status, "public_key": pk}))
        else:
            print(json.dumps({"chain_valid": witness.verify_chain(), "path": str(witness.path)}))
        return 0
    if args.command == "verify-chain":
        print(json.dumps({"chain_valid": witness.verify_chain(), "path": str(witness.path)}))
        return 0
    if args.command == "export":
        import getpass

        identity = load_or_create(args.node_id, args.identity_dir)
        result = export_identity_encrypted(
            identity, getpass.getpass("Backup passphrase: "), args.out
        )
        print(json.dumps(result))
        return 0
    if args.command == "restore":
        import getpass

        identity = restore_identity_from_backup(
            args.backup, getpass.getpass("Backup passphrase: "), args.identity_dir
        )
        print(json.dumps({"restored": identity.node_id, "public_key": identity.public_key_hex}))
        return 0
    if args.command == "recover":
        identity = load_or_create(args.node_id, args.identity_dir)
        print(json.dumps(witness.recover(args.node_id, identity)))
        return 0
    if args.command == "retire":
        identity = load_or_create(args.node_id, args.identity_dir)
        print(json.dumps(witness.retire(args.node_id, identity, reason=args.reason)))
        return 0
    if args.command == "force-retire":
        print(
            json.dumps(
                witness.force_retire(
                    args.node_id,
                    args.note,
                    acknowledged_fork_risk=args.acknowledge_fork_risk,
                )
            )
        )
        return 0
    if args.command == "export-registry":
        print(json.dumps(witness.export_snapshot(args.out)))
        return 0
    if args.command == "import-registry":
        print(json.dumps(witness.import_snapshot(args.src)))
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
