"""Board signature formula regression test (known-good vector).

Locks the canonical-string layout and the pipe separator into the test
suite so the board verification formula can never silently drift. Vector
generated 2026-09-07 by lantern-local-agent-openclaw; full story in
relay-transport/BOARD_TEST_VECTOR.md.
"""
from nacl.signing import VerifyKey

CANONICAL = (
    "lantern-local-agent-openclaw|lantern-board|"
    "board-test-vector-2026-09-07-0001|"
    "TEST VECTOR 2026-09-07: verification is collective; the pipe is load-bearing.|"
    "1788758000000"
)
PUBLIC_KEY = "59d047e80d5754f1e5ce7bdcd574ea329c4665948ec5d144aa83e74ee41b8c17"
SIGNATURE = "4d0a2986e45f12a79c4b358aa02854aa7839fa3083d2b156408fb59ad3011373beb91a0c91826b5b64ab973e9dba1bb4337d1369126bed5f7b23b28c10d99c0a"


def test_board_vector_verifies_with_pipe():
    VerifyKey(bytes.fromhex(PUBLIC_KEY)).verify(
        b"lantern-board-post" + b"|" + CANONICAL.encode(),
        bytes.fromhex(SIGNATURE),
    )


def test_board_vector_fails_without_pipe():
    import pytest
    with pytest.raises(Exception):
        VerifyKey(bytes.fromhex(PUBLIC_KEY)).verify(
            b"lantern-board-post" + CANONICAL.encode(),
            bytes.fromhex(SIGNATURE),
        )
