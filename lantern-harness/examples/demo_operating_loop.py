#!/usr/bin/env python3
"""Runnable demo: the full Lantern Harness operating loop end-to-end,
against a real (disposable, temp-directory) Lantern node.

    USER INTENT
      -> real Observation recorded in EvidenceKernel
      -> PromptCompiler structures the request (no fabricated fields)
      -> ConfidenceField reads real evidence/contradiction/integrity state
      -> DecisionStateMachine recommends (never authorizes) a next action
      -> RealityBoundary would gate any actual external action (none here)

Run:
    python3 examples/demo_operating_loop.py

Everything printed below is produced by real code paths -- no output is
hardcoded or simulated. Where the demo has genuinely no data for a field
(e.g. contradicting evidence), it prints exactly what the real components
report (UNKNOWN / NOT_PROVIDED / empty), rather than inventing content.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lantern_harness.bridge import LanternBridge
from lantern_harness.operating_loop import OperatingLoop
from lantern_harness.self_model import SelfModel
from lantern_harness.spine import BranchStore, SpineCommitter
from lantern_harness.tools.boundary import ToolBoundary


def main():
    data_dir = Path(tempfile.mkdtemp(prefix="lantern_harness_demo_"))
    print(f"[demo] using a disposable Lantern node at {data_dir}\n")

    bridge = LanternBridge(data_dir=data_dir, node_id="demo-node")
    identity = bridge.ensure_identity()
    print(f"[demo] identity: {identity}\n")
    bridge.startup()

    tool_boundary = ToolBoundary()
    loop = OperatingLoop(bridge, tool_boundary)

    print("=== Step 1: an ordinary question, no prior evidence ===")
    result = loop.run("Is our new pricing model going to increase revenue?", concept="pricing_model")
    print(result.format())
    print()

    print("=== Step 2: record two independent, agreeing observations as evidence ===")
    obs_a = bridge.observe("Sales in the pilot region rose 12% after the new pricing model.", source="sales_report_q1", reliability=0.9)
    bridge.add_evidence("pricing_model", obs_a.id, weight=1.0, sign=1)
    obs_b = bridge.observe("Independent customer survey shows willingness to pay increased.", source="customer_survey", reliability=0.8)
    bridge.add_evidence("pricing_model", obs_b.id, weight=1.0, sign=1)

    result2 = loop.run("Given the new evidence, should we roll out the pricing model?", concept="pricing_model")
    print(result2.format())
    print()

    print("=== Step 3: open an exploratory branch (never auto-committed) ===")
    result3 = loop.run("Investigate whether the pricing change would hurt long-term retention.", concept="pricing_model", open_branch=True)
    print(result3.format())
    print()

    print("=== Step 4: a branch cannot commit itself -- explicit authorization required ===")
    committer = SpineCommitter(bridge)
    refused = committer.commit(
        result3.branch, statement="pricing model increases short-term revenue",
        authorized=False, authorized_by="nobody",
    )
    print(f"[demo] commit attempt without authorization: {refused.status} -- {refused.reason}\n")

    committed = committer.commit(
        result3.branch, statement="pricing model increases short-term revenue, long-term retention unresolved",
        authorized=True, authorized_by="demo-operator",
    )
    print(f"[demo] commit attempt WITH explicit authorization: {committed.status}")
    if committed.entry is not None:
        print(f"[demo] committed to Spine, Chronicle hash={committed.entry.chronicle_hash}\n")

    print("=== Step 5: Self-Model -- what does the system honestly know about itself right now? ===")
    self_model = SelfModel(bridge, tool_boundary)
    print(self_model.describe().format())


if __name__ == "__main__":
    main()
