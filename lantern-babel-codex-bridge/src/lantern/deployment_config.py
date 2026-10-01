"""Deployment-safe configuration resolution for a Lantern receiver.

Every externally visible value (public base URL, bind address, ports,
identity and evidence locations, authorization) comes from explicit
operator configuration. Nothing here ever embeds a tunnel URL, an
endpoint, or an identity: the module only resolves what the operator
supplied.

Precedence, highest first:
  1. explicit CLI argument
  2. environment variable (LANTERN_*)
  3. built-in safe default

Fail-closed rules enforced at resolution time:
  - node_id must be provided (CLI or env) -- there is no default node.
  - public_base_url, when set, must be a clean http:// or https:// URL
    with no path or query -- it identifies where THIS node is reachable,
    never a peer.
  - allow_legacy_message_ingestion is opt-in via the exact strings
    true/1/yes/on only; anything else means False.
  - bind port must be in 1-65535.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from . import verified_session

_TRUE_STRINGS = {"true", "1", "yes", "on"}


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in _TRUE_STRINGS


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_authorize_entries(raw: str) -> list[str]:
    """LANTERN_AUTHORIZE format: "node:cap[,cap];other:cap" -- the same
    node:capability entries as repeated --authorize arguments, joined
    with ';'. Parsing into an AuthorizationPolicy happens only in
    bootstrap_node._parse_authorize_args, never here."""
    return [item.strip() for item in raw.split(";") if item.strip()]


@dataclass
class DeploymentConfig:
    """Resolved, validated receiver configuration. Every field carries
    `source` provenance (cli/env/default) for startup diagnostics."""

    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    node_id: str | None = None
    data_dir: str = ".lantern"
    chronicle_path: str | None = None
    witness_registry: str | None = None
    public_base_url: str | None = None
    authorize: tuple[str, ...] = ()
    session_ttl_seconds: float = verified_session.DEFAULT_SESSION_TTL_SECONDS
    allowed_protocol_versions: tuple[str, ...] = ()
    allow_legacy_message_ingestion: bool = False
    source: dict[str, str] = field(default_factory=dict)


ENV_SPEC = {
    "bind_host": ("LANTERN_BIND_HOST", str, "127.0.0.1"),
    "bind_port": ("LANTERN_BIND_PORT", int, 8765),
    "node_id": ("LANTERN_NODE_ID", str, None),
    "data_dir": ("LANTERN_DATA_DIR", str, ".lantern"),
    "chronicle_path": ("LANTERN_CHRONICLE", str, None),
    "witness_registry": ("LANTERN_WITNESS_REGISTRY", str, None),
    "public_base_url": ("LANTERN_PUBLIC_URL", str, None),
    "authorize": ("LANTERN_AUTHORIZE", _parse_authorize_entries, ()),
    "session_ttl_seconds": ("LANTERN_SESSION_TTL_SECONDS", float, None),
    "allowed_protocol_versions": (
        "LANTERN_ALLOWED_PROTOCOL_VERSIONS",
        _parse_csv,
        (),
    ),
    "allow_legacy_message_ingestion": (
        "LANTERN_ALLOW_LEGACY_MESSAGE_INGESTION",
        _parse_bool,
        False,
    ),
}


def _validate_public_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError(
            "public_base_url must start with http:// or https:// "
            f"(got {value!r})"
        )
    rest = value.split("://", 1)[1]
    if not rest or any(ch in rest for ch in "/?#"):
        raise ValueError(
            "public_base_url must be scheme://host[:port] only -- no path, "
            f"query, or fragment (got {value!r})"
        )
    return value


def resolve_config(
    cli: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> DeploymentConfig:
    """Merge CLI overrides > environment > defaults, then validate."""
    cli_values = {k: v for k, v in (cli or {}).items() if v is not None}
    env = os.environ if environ is None else environ

    resolved: dict[str, Any] = {}
    sources: dict[str, str] = {}

    for key, (env_name, cast, default) in ENV_SPEC.items():
        if key in cli_values:
            value = cli_values[key]
            # --authorize is repeatable: accept a list of raw entries
            if key == "authorize" and isinstance(value, str):
                value = _parse_authorize_entries(value)
            if key == "allowed_protocol_versions" and isinstance(value, str):
                value = _parse_csv(value)
            if key == "allow_legacy_message_ingestion":
                value = bool(value)
            resolved[key] = value
            sources[key] = "cli"
            continue
        raw = env.get(env_name)
        if raw is not None and raw.strip() != "":
            resolved[key] = cast(raw)
            sources[key] = "env"
            continue
        resolved[key] = default
        sources[key] = "default"

    if not resolved["node_id"] or not str(resolved["node_id"]).strip():
        raise ValueError(
            "node_id is required and has no default: pass --node-id or "
            "set LANTERN_NODE_ID"
        )
    resolved["node_id"] = str(resolved["node_id"]).strip()

    port = int(resolved["bind_port"])
    if not 1 <= port <= 65535:
        raise ValueError(f"bind_port must be in 1..65535 (got {port})")
    resolved["bind_port"] = port

    if resolved["public_base_url"]:
        resolved["public_base_url"] = _validate_public_url(
            str(resolved["public_base_url"])
        )

    ttl = float(resolved["session_ttl_seconds"] or 0)
    if ttl <= 0:
        ttl = verified_session.DEFAULT_SESSION_TTL_SECONDS
    resolved["session_ttl_seconds"] = ttl

    authorize = resolved["authorize"]
    if isinstance(authorize, (list, tuple)):
        authorize = tuple(str(entry) for entry in authorize)
    else:
        authorize = ()
    resolved["authorize"] = authorize
    sources.setdefault("authorize", "default")

    versions = resolved["allowed_protocol_versions"]
    if isinstance(versions, (list, tuple)):
        versions = tuple(str(v) for v in versions)
    else:
        versions = ()
    resolved["allowed_protocol_versions"] = versions

    resolved["allow_legacy_message_ingestion"] = bool(
        resolved["allow_legacy_message_ingestion"]
    )

    cfg = DeploymentConfig(**resolved, source=sources)

    if not cfg.chronicle_path:
        cfg.chronicle_path = str(
            Path(cfg.data_dir) / f"{cfg.node_id}.jsonl"
        )
    return cfg
