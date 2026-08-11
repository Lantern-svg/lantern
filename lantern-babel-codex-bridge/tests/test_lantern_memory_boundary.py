from lantern.memory_boundary import MemoryBoundary, MemoryOperation, MemoryWriteStatus


def test_a_existing_memory_unsafe_overwrite_is_blocked(tmp_path):
    path = tmp_path / "memory.md"
    path.write_text("original\n", encoding="utf-8")
    boundary = MemoryBoundary(tmp_path)

    result = boundary.replace(path, "replacement\n")

    assert result.status == MemoryWriteStatus.BLOCKED
    assert result.reason == "EXPLICIT_REPLACE_REQUIRED"
    assert path.read_text(encoding="utf-8") == "original\n"


def test_b_existing_memory_explicit_replacement_succeeds(tmp_path):
    path = tmp_path / "memory.md"
    path.write_text("original\n", encoding="utf-8")

    result = MemoryBoundary(tmp_path).replace(path, "replacement\n", authorize=True)

    assert result.status == MemoryWriteStatus.WRITTEN
    assert path.read_text(encoding="utf-8") == "replacement\n"


def test_c_append_and_update_preserve_other_information(tmp_path):
    path = tmp_path / "memory.md"
    path.write_text("first\nsecond\n", encoding="utf-8")
    boundary = MemoryBoundary(tmp_path)

    append_result = boundary.append(path, "third\n")
    update_result = boundary.update(path, "second\n", "second updated\n")

    assert append_result.status == MemoryWriteStatus.WRITTEN
    assert update_result.status == MemoryWriteStatus.WRITTEN
    assert path.read_text(encoding="utf-8") == "first\nsecond updated\nthird\n"


def test_d_write_failure_leaves_original_memory_intact(tmp_path, monkeypatch):
    path = tmp_path / "memory.md"
    original = "original\n"
    path.write_text(original, encoding="utf-8")
    boundary = MemoryBoundary(tmp_path)

    def fail_replace(source, destination):
        raise OSError("simulated write failure")

    monkeypatch.setattr("lantern.memory_boundary.os.replace", fail_replace)
    result = boundary.replace(path, "replacement\n", authorize=True)

    assert result.status == MemoryWriteStatus.UNVERIFIED
    assert path.read_text(encoding="utf-8") == original


def test_existing_memory_that_cannot_be_read_is_blocked(tmp_path, monkeypatch):
    path = tmp_path / "memory.md"
    path.write_text("original\n", encoding="utf-8")
    boundary = MemoryBoundary(tmp_path)

    def fail_read(self, *args, **kwargs):
        raise OSError("simulated read failure")

    monkeypatch.setattr(type(path), "read_text", fail_read)
    result = boundary.append(path, "unsafe append\n")

    assert result.status == MemoryWriteStatus.BLOCKED
    assert result.reason == "EXISTING_STATE_NOT_VERIFIED"


def test_e_successful_write_is_independently_reread(tmp_path):
    path = tmp_path / "memory.md"
    expected = "verified content\n"

    result = MemoryBoundary(tmp_path).replace(path, expected)

    assert result.status == MemoryWriteStatus.WRITTEN
    assert path.read_text(encoding="utf-8") == expected
    assert path.read_text(encoding="utf-8") == expected


def test_f_verification_failure_reports_unverified_and_restores_original(tmp_path, monkeypatch):
    path = tmp_path / "memory.md"
    original = "original\n"
    path.write_text(original, encoding="utf-8")
    boundary = MemoryBoundary(tmp_path)
    real_read_text = type(path).read_text
    calls = {"count": 0}

    def fail_final_read(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated verification failure")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "read_text", fail_final_read)
    result = boundary.replace(path, "replacement\n", authorize=True)

    assert result.status == MemoryWriteStatus.UNVERIFIED
    assert path.read_text(encoding="utf-8") == original


def test_operations_are_distinct_and_reported(tmp_path):
    path = tmp_path / "memory.md"
    boundary = MemoryBoundary(tmp_path)

    append = boundary.append(path, "one\n")
    update = boundary.update(path, "one\n", "two\n")
    replace = boundary.replace(path, "three\n", authorize=True)

    assert append.operation == MemoryOperation.APPEND
    assert update.operation == MemoryOperation.UPDATE
    assert replace.operation == MemoryOperation.REPLACE


def test_delete_is_explicit_and_keeps_a_recovery_backup(tmp_path):
    path = tmp_path / "memory.md"
    path.write_text("original\n", encoding="utf-8")
    boundary = MemoryBoundary(tmp_path)

    blocked = boundary.delete(path)
    deleted = boundary.delete(path, authorize=True)

    assert blocked.status == MemoryWriteStatus.BLOCKED
    assert blocked.reason == "EXPLICIT_DELETE_REQUIRED"
    assert deleted.status == MemoryWriteStatus.WRITTEN
    assert not path.exists()
    assert path.with_name("memory.md.deleted").read_text(encoding="utf-8") == "original\n"


def test_append_cannot_accidentally_replace_existing_content(tmp_path):
    path = tmp_path / "memory.md"
    path.write_text("first\nsecond\n", encoding="utf-8")
    boundary = MemoryBoundary(tmp_path)

    result = boundary.append(path, "third\n")

    assert result.operation == MemoryOperation.APPEND
    assert result.status == MemoryWriteStatus.WRITTEN
    content = path.read_text(encoding="utf-8")
    assert content == "first\nsecond\nthird\n"
    assert content.startswith("first\nsecond\n")


def test_update_cannot_accidentally_delete_the_file(tmp_path):
    path = tmp_path / "memory.md"
    path.write_text("first\nsecond\nthird\n", encoding="utf-8")
    boundary = MemoryBoundary(tmp_path)

    result = boundary.update(path, "second\n", "second updated\n")

    assert result.operation == MemoryOperation.UPDATE
    assert result.status == MemoryWriteStatus.WRITTEN
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "first\nsecond updated\nthird\n"


def test_failed_operation_leaves_no_phantom_success_state(tmp_path, monkeypatch):
    path = tmp_path / "memory.md"
    original = "original\n"
    path.write_text(original, encoding="utf-8")
    boundary = MemoryBoundary(tmp_path)

    def fail_replace(source, destination):
        raise OSError("simulated write failure")

    monkeypatch.setattr("lantern.memory_boundary.os.replace", fail_replace)
    result = boundary.update(path, "original\n", "changed\n")

    # MemoryBoundary holds no in-memory cache of prior results; the only
    # record of the operation's outcome is the returned result object and
    # the file on disk. Both must agree that the operation did not succeed.
    assert result.status != MemoryWriteStatus.WRITTEN
    assert result.persisted is False
    assert not hasattr(boundary, "requests")
    assert not hasattr(boundary, "_cache")
    assert path.read_text(encoding="utf-8") == original
