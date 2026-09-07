"""Board v2 signature formula regression test (position-binding).

Locks the position-bound canonical layout: domain + "|" +
node_id|board|message_id|content|created_ms|prev_hash. The trailing
prev_hash is what makes repositioning/forking a signature failure.
Vector generated 2026-09-07; story in relay-transport/BOARD_TEST_VECTOR.md.
"""
from nacl.signing import VerifyKey

CANONICAL = (
    "lantern-local-agent-openclaw|lantern-board|"
    "board-test-vector-v2-2026-09-07-0001|"
    "TEST VECTOR v2: the position is load-bearing; a fork is a signature failure.|"
    "1788758000000|GENESIS"
)
PUBLIC_KEY = "59d047e80d5754f1e5ce7bdcd574ea329c4665948ec5d144aa83e74ee41b8c17"
SIGNATURE = "ba79575b4f4fcecda85256bbea140a9361bafe8996fee5bb61e97dd8e582d0db558b8a2eed6daa2c5d2009a69a8e9c93c83de5e27763b298c9af921a26f9c107"


def test_board_v2_vector_verifies():
    VerifyKey(bytes.fromhex(PUBLIC_KEY)).verify(
        b"lantern-board-post" + b"|" + CANONICAL.encode(),
        bytes.fromhex(SIGNATURE),
    )


def test_board_v2_vector_fails_without_position():
    import pytest
    with pytest.raises(Exception):
        VerifyKey(bytes.fromhex(PUBLIC_KEY)).verify(
            b"lantern-board-post" + b"|" + CANONICAL.rsplit("|", 1)[0].encode(),
            bytes.fromhex(SIGNATURE),
        )
