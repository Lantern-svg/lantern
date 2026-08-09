"""Explicit, verified persistence operations for memory records.

This is a small persistence boundary for callers that manage durable memory
files. It deliberately does not infer whether a replacement was intended:
APPEND, UPDATE, REPLACE, and DELETE are separate operations, and replacing an
existing record requires an explicit authorization flag.

The boundary stages content in the target directory, verifies the staged
bytes, atomically replaces the target, then independently re-reads the target.
If the final read or comparison fails, it attempts to restore the original
bytes before returning UNVERIFIED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import tempfile


_UNREADABLE = object()


class MemoryOperation(str, Enum):
    APPEND = "APPEND"
    UPDATE = "UPDATE"
    REPLACE = "REPLACE"
    DELETE = "DELETE"


class MemoryWriteStatus(str, Enum):
    BLOCKED = "BLOCKED"
    WRITTEN = "WRITTEN"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class MemoryWriteResult:
    status: MemoryWriteStatus
    operation: MemoryOperation
    path: str
    reason: str | None = None

    @property
    def persisted(self) -> bool:
        return self.status == MemoryWriteStatus.WRITTEN

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "status": self.status.value,
            "operation": self.operation.value,
            "path": self.path,
            "persisted": self.persisted,
            "reason": self.reason,
        }


class MemoryBoundary:
    """Perform explicit, non-silent operations on a persistent text record."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root).resolve() if root is not None else None

    def append(self, path: str | Path, content: str) -> MemoryWriteResult:
        target = self._target(path)
        existing = self._read_existing(target)
        if existing is _UNREADABLE:
            return self._blocked(target, MemoryOperation.APPEND, "EXISTING_STATE_NOT_VERIFIED")
        if existing is None:
            original = None
            combined = content
        else:
            original = existing
            combined = existing + content
        return self._commit(target, combined, original, MemoryOperation.APPEND)

    def update(
        self,
        path: str | Path,
        old_text: str,
        new_text: str,
    ) -> MemoryWriteResult:
        target = self._target(path)
        existing = self._read_existing(target)
        if existing is _UNREADABLE:
            return self._blocked(target, MemoryOperation.UPDATE, "EXISTING_STATE_NOT_VERIFIED")
        if existing is None:
            return self._blocked(target, MemoryOperation.UPDATE, "EXISTING_STATE_NOT_VERIFIED")
        if existing.count(old_text) != 1:
            return self._blocked(
                target,
                MemoryOperation.UPDATE,
                "UPDATE_TARGET_MUST_MATCH_EXACTLY_ONCE",
            )
        updated = existing.replace(old_text, new_text, 1)
        return self._commit(target, updated, existing, MemoryOperation.UPDATE)

    def replace(
        self,
        path: str | Path,
        content: str,
        *,
        authorize: bool = False,
    ) -> MemoryWriteResult:
        target = self._target(path)
        existing = self._read_existing(target)
        if existing is _UNREADABLE:
            return self._blocked(target, MemoryOperation.REPLACE, "EXISTING_STATE_NOT_VERIFIED")
        if existing is None and target.exists():
            return self._blocked(target, MemoryOperation.REPLACE, "EXISTING_STATE_NOT_VERIFIED")
        if target.exists() and not authorize:
            return self._blocked(target, MemoryOperation.REPLACE, "EXPLICIT_REPLACE_REQUIRED")
        return self._commit(target, content, existing, MemoryOperation.REPLACE)

    def delete(
        self,
        path: str | Path,
        *,
        authorize: bool = False,
    ) -> MemoryWriteResult:
        target = self._target(path)
        existing = self._read_existing(target)
        if existing is _UNREADABLE:
            return self._blocked(target, MemoryOperation.DELETE, "EXISTING_STATE_NOT_VERIFIED")
        if existing is None:
            if target.exists():
                return self._blocked(target, MemoryOperation.DELETE, "EXISTING_STATE_NOT_VERIFIED")
            return MemoryWriteResult(MemoryWriteStatus.WRITTEN, MemoryOperation.DELETE, str(target))
        if not authorize:
            return self._blocked(target, MemoryOperation.DELETE, "EXPLICIT_DELETE_REQUIRED")

        backup = target.with_name(target.name + ".deleted")
        try:
            os.replace(target, backup)
            if target.exists() or not backup.exists():
                if backup.exists() and not target.exists():
                    os.replace(backup, target)
                return self._unverified(target, MemoryOperation.DELETE, "DELETE_VERIFICATION_FAILED")
            return MemoryWriteResult(
                MemoryWriteStatus.WRITTEN,
                MemoryOperation.DELETE,
                str(target),
                reason=f"backup={backup}",
            )
        except OSError as exc:
            return self._unverified(target, MemoryOperation.DELETE, str(exc))

    def _target(self, path: str | Path) -> Path:
        target = Path(path).resolve()
        if self.root is not None:
            try:
                target.relative_to(self.root)
            except ValueError as exc:
                raise ValueError("memory path is outside the configured root") from exc
        return target

    @staticmethod
    def _read_existing(target: Path) -> str | object | None:
        if not target.exists():
            return None
        try:
            return target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return _UNREADABLE

    @staticmethod
    def _blocked(target: Path, operation: MemoryOperation, reason: str) -> MemoryWriteResult:
        return MemoryWriteResult(MemoryWriteStatus.BLOCKED, operation, str(target), reason)

    @staticmethod
    def _unverified(target: Path, operation: MemoryOperation, reason: str) -> MemoryWriteResult:
        return MemoryWriteResult(MemoryWriteStatus.UNVERIFIED, operation, str(target), reason)

    @staticmethod
    def _stage(content: str, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        )
        staged = Path(handle.name)
        try:
            with handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            return staged
        except BaseException:
            staged.unlink(missing_ok=True)
            raise

    def _commit(
        self,
        target: Path,
        content: str,
        original: str | None,
        operation: MemoryOperation,
    ) -> MemoryWriteResult:
        try:
            staged = self._stage(content, target)
            if staged.read_text(encoding="utf-8") != content:
                staged.unlink(missing_ok=True)
                return self._unverified(target, operation, "STAGED_CONTENT_VERIFICATION_FAILED")

            os.replace(staged, target)
            try:
                observed = target.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                return self._rollback_result(target, original, operation, str(exc))
            if observed != content:
                return self._rollback_result(
                    target,
                    original,
                    operation,
                    "FINAL_CONTENT_VERIFICATION_FAILED",
                )
            return MemoryWriteResult(MemoryWriteStatus.WRITTEN, operation, str(target))
        except OSError as exc:
            if "staged" in locals():
                staged.unlink(missing_ok=True)
            return self._unverified(target, operation, str(exc))

    def _rollback_result(
        self,
        target: Path,
        original: str | None,
        operation: MemoryOperation,
        reason: str,
    ) -> MemoryWriteResult:
        try:
            self._restore(target, original)
        except OSError as exc:
            reason = f"{reason}; RESTORE_FAILED: {exc}"
        return self._unverified(target, operation, reason)

    def _restore(self, target: Path, original: str | None) -> None:
        if original is None:
            target.unlink(missing_ok=True)
            return
        staged = self._stage(original, target)
        os.replace(staged, target)
