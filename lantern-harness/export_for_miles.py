#!/usr/bin/env python3
"""
MILES HANDOFF EXPORTER
Run from the root of the Lantern Harness repository:
    python export_for_miles.py
Creates:
    MILES_HANDOFF.md
Purpose:
    Give another reasoning/coding agent enough real repository information
    to diagnose and repair the harness without requiring a ZIP archive.
Important:
    This program DOES NOT execute the Lantern Harness.
It statically inspects the repository using Python's AST parser and source
files, then produces a text report containing:
    - repository map
    - dependency/configuration information
    - important source files
    - classes/functions
    - imports
    - function call relationships
    - entry points
    - security-sensitive operations
    - TODO/stub/fallback markers
    - tests
    - likely execution paths
    - architectural boundaries
    - source code for critical files
    - explicit unknown/missing states
The generated report is intended for Miles or another reasoning agent.
"""
from __future__ import annotations
import ast
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "MILES_HANDOFF.md"
PY_EXTENSIONS = {".py"}
TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".ini",
    ".cfg",
    ".conf",
    ".sh",
}
IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    "node_modules",
    "dist",
    "build",
    "site-packages",
}
MAX_FILE_SIZE = 1_000_000
# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_PATTERNS = [
    re.compile(
        r'(?i)(api[_-]?key)\s*[:=]\s*["\']?[^"\',\s]+'
    ),
    re.compile(
        r'(?i)(secret[_-]?key)\s*[:=]\s*["\']?[^"\',\s]+'
    ),
    re.compile(
        r'(?i)(password)\s*[:=]\s*["\']?[^"\',\s]+'
    ),
    re.compile(
        r'(?i)(token)\s*[:=]\s*["\']?[^"\',\s]+'
    ),
    re.compile(
        r'(?i)(private[_-]?key)\s*[:=]\s*["\']?[^"\',\s]+'
    ),
    re.compile(
        r'(?i)(authorization)\s*:\s*bearer\s+\S+'
    ),
]
SECRET_VALUE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]
def redact(text: str) -> str:
    """Redact likely secrets while preserving surrounding structure."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(
            lambda match: f"{match.group(1)}=<REDACTED>",
            text,
        )
    for pattern in SECRET_VALUE_PATTERNS:
        text = pattern.sub("<REDACTED>", text)
    return text
# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
def should_skip(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)
def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))
def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            return "[FILE TOO LARGE TO INCLUDE]"
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
def all_files():
    for path in sorted(ROOT.rglob("*")):
        if should_skip(path):
            continue
        if path.is_file():
            yield path
def python_files():
    for path in all_files():
        if path.suffix == ".py":
            yield path
# ---------------------------------------------------------------------------
# AST analysis
# ---------------------------------------------------------------------------
class PythonAnalysis:
    def __init__(self, path: Path):
        self.path = path
        self.source = ""
        self.tree: ast.AST | None = None
        self.imports = []
        self.functions = []
        self.classes = []
        self.calls = []
        self.entrypoints = []
        self.security_calls = []
        self.markers = []
        self.parse()
    def parse(self):
        source = read_text(self.path)
        if source is None:
            return
        self.source = source
        try:
            self.tree = ast.parse(
                source,
                filename=str(self.path),
            )
        except SyntaxError as exc:
            self.markers.append(
                f"SYNTAX_ERROR line={exc.lineno}: {exc.msg}"
            )
            return
        visitor = ASTVisitor(self)
        try:
            visitor.visit(self.tree)
        except Exception as exc:
            self.markers.append(
                f"AST_ANALYSIS_ERROR: {type(exc).__name__}: {exc}"
            )
class ASTVisitor(ast.NodeVisitor):
    def __init__(self, analysis: PythonAnalysis):
        self.analysis = analysis
        self.current_scope = []
    # -------------------------
    # Imports
    # -------------------------
    def visit_Import(self, node):
        for alias in node.names:
            self.analysis.imports.append(
                f"import {alias.name}"
            )
        self.generic_visit(node)
    def visit_ImportFrom(self, node):
        module = node.module or ""
        names = ", ".join(
            alias.name
            for alias in node.names
        )
        prefix = "." * node.level
        self.analysis.imports.append(
            f"from {prefix}{module} import {names}"
        )
        self.generic_visit(node)
    # -------------------------
    # Functions
    # -------------------------
    def visit_FunctionDef(self, node):
        qualified = ".".join(
            self.current_scope + [node.name]
        )
        self.analysis.functions.append(
            {
                "name": qualified,
                "line": node.lineno,
                "async": False,
            }
        )
        if node.name in {
            "main",
            "run",
            "run_repl",
            "bootstrap",
            "respond",
            "handle",
            "serve",
            "start",
        }:
            self.analysis.entrypoints.append(
                f"{qualified}() at line {node.lineno}"
            )
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()
    def visit_AsyncFunctionDef(self, node):
        qualified = ".".join(
            self.current_scope + [node.name]
        )
        self.analysis.functions.append(
            {
                "name": qualified,
                "line": node.lineno,
                "async": True,
            }
        )
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()
    # -------------------------
    # Classes
    # -------------------------
    def visit_ClassDef(self, node):
        qualified = ".".join(
            self.current_scope + [node.name]
        )
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append("<unknown>")
        self.analysis.classes.append(
            {
                "name": qualified,
                "line": node.lineno,
                "bases": bases,
            }
        )
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()
    # -------------------------
    # Calls
    # -------------------------
    def visit_Call(self, node):
        try:
            target = ast.unparse(node.func)
        except Exception:
            target = "<unknown>"
        caller = (
            ".".join(self.current_scope)
            if self.current_scope
            else "<module>"
        )
        self.analysis.calls.append(
            {
                "caller": caller,
                "target": target,
                "line": node.lineno,
            }
        )
        security_targets = {
            "subprocess.run",
            "subprocess.Popen",
            "subprocess.call",
            "os.system",
            "eval",
            "exec",
            "open",
            "requests.get",
            "requests.post",
            "httpx.get",
            "httpx.post",
        }
        if target in security_targets:
            self.analysis.security_calls.append(
                f"{target} at line {node.lineno}"
            )
        self.generic_visit(node)
    # -------------------------
    # Suspicious markers
    # -------------------------
    def visit_Constant(self, node):
        if isinstance(node.value, str):
            value = node.value
            suspicious = [
                "TODO",
                "FIXME",
                "STUB",
                "NotImplemented",
                "placeholder",
                "mock",
                "temporary",
            ]
            for marker in suspicious:
                if marker.lower() in value.lower():
                    self.analysis.markers.append(
                        f"{marker} at line {node.lineno}"
                    )
        self.generic_visit(node)
def analyze_repository():
    analyses = []
    for path in python_files():
        analyses.append(
            PythonAnalysis(path)
        )
    return analyses
# ---------------------------------------------------------------------------
# Repository map
# ---------------------------------------------------------------------------
def repository_map() -> str:
    lines = []
    for path in all_files():
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        lines.append(relative(path))
    return "\n".join(lines)
# ---------------------------------------------------------------------------
# Dependency/configuration analysis
# ---------------------------------------------------------------------------
def configuration_report() -> str:
    candidates = [
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "package.json",
        "config.json",
        "config/config.json",
        ".env.example",
        ".env.template",
    ]
    output = []
    for name in candidates:
        path = ROOT / name
        if not path.exists():
            continue
        content = read_text(path)
        if content is None:
            continue
        output.append(
            f"### `{name}`\n\n"
            f"```text\n"
            f"{redact(content)}\n"
            f"```\n"
        )
    if not output:
        return "No recognized dependency/configuration files found."
    return "\n".join(output)
# ---------------------------------------------------------------------------
# Source extraction
# ---------------------------------------------------------------------------
IMPORTANT_FILES = [
    "main.py",
    "pyproject.toml",
    "README.md",
    "lantern_harness/bridge.py",
    "lantern_harness/operating_loop.py",
    "lantern_harness/permission_authority.py",
    "lantern_harness/reality_boundary.py",
    "lantern_harness/prompt_compiler.py",
    "lantern_harness/confidence_field.py",
    "lantern_harness/decision_state_machine.py",
    "lantern_harness/self_model.py",
    "lantern_harness/spine.py",
    "lantern_harness/transfer_manifest.py",
    "lantern_harness/mcp_server.py",
    "lantern_harness/config.py",
    "lantern_harness/bootstrap.py",
    "lantern_harness/harness_status.py",
    "lantern_harness/perspective_differential.py",
]
def language_for(path: Path) -> str:
    return {
        ".py": "python",
        ".toml": "toml",
        ".json": "json",
        ".md": "markdown",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".sh": "bash",
    }.get(path.suffix.lower(), "text")
def source_block(name: str) -> str:
    path = ROOT / name
    if not path.exists():
        return (
            f"### `{name}`\n\n"
            "**STATUS: MISSING**\n"
        )
    content = read_text(path)
    if content is None:
        return (
            f"### `{name}`\n\n"
            "**STATUS: UNREADABLE**\n"
        )
    content = redact(content)
    return (
        f"### `{name}`\n\n"
        f"```{language_for(path)}\n"
        f"{content}\n"
        f"```\n"
    )
# ---------------------------------------------------------------------------
# Static call graph
# ---------------------------------------------------------------------------
def call_graph(analyses) -> str:
    output = []
    for analysis in analyses:
        if not analysis.calls:
            continue
        output.append(
            f"### `{relative(analysis.path)}`"
        )
        for call in analysis.calls:
            output.append(
                f"- line {call['line']}: "
                f"`{call['caller']}` → `{call['target']}`"
            )
        output.append("")
    return "\n".join(output) or "No calls discovered."
# ---------------------------------------------------------------------------
# Classes/functions
# ---------------------------------------------------------------------------
def symbol_report(analyses) -> str:
    output = []
    for analysis in analyses:
        if not analysis.classes and not analysis.functions:
            continue
        output.append(
            f"### `{relative(analysis.path)}`"
        )
        for cls in analysis.classes:
            bases = ""
            if cls["bases"]:
                bases = (
                    " extends "
                    + ", ".join(cls["bases"])
                )
            output.append(
                f"- CLASS `{cls['name']}`"
                f"{bases}"
                f" — line {cls['line']}"
            )
        for fn in analysis.functions:
            kind = (
                "ASYNC FUNCTION"
                if fn["async"]
                else "FUNCTION"
            )
            output.append(
                f"- {kind} `{fn['name']}()`"
                f" — line {fn['line']}"
            )
        output.append("")
    return "\n".join(output) or "No Python symbols discovered."
# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
def import_report(analyses) -> str:
    output = []
    for analysis in analyses:
        if not analysis.imports:
            continue
        output.append(
            f"### `{relative(analysis.path)}`"
        )
        for item in sorted(set(analysis.imports)):
            output.append(f"- `{item}`")
        output.append("")
    return "\n".join(output) or "No imports discovered."
# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def entrypoint_report(analyses) -> str:
    output = []
    for analysis in analyses:
        for entry in analysis.entrypoints:
            output.append(
                f"- `{relative(analysis.path)}`: {entry}"
            )
    if not output:
        return "No conventional entry points discovered."
    return "\n".join(output)
# ---------------------------------------------------------------------------
# Security-sensitive operations
# ---------------------------------------------------------------------------
def security_report(analyses) -> str:
    output = []
    for analysis in analyses:
        if not analysis.security_calls:
            continue
        output.append(
            f"### `{relative(analysis.path)}`"
        )
        for item in analysis.security_calls:
            output.append(
                f"- {item}"
            )
        output.append("")
    if not output:
        return (
            "No statically recognized security-sensitive calls found."
        )
    return "\n".join(output)
# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------
def marker_report(analyses) -> str:
    output = []
    for analysis in analyses:
        if not analysis.markers:
            continue
        output.append(
            f"### `{relative(analysis.path)}`"
        )
        for marker in analysis.markers:
            output.append(
                f"- {redact(marker)}"
            )
        output.append("")
    return "\n".join(output) or "No obvious markers discovered."
# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_report() -> str:
    tests_dir = ROOT / "tests"
    if not tests_dir.exists():
        return "No `tests/` directory found."
    tests = []
    for path in sorted(
        tests_dir.rglob("test_*.py")
    ):
        tests.append(
            f"- `{relative(path)}`"
        )
    if not tests:
        return "No pytest test files discovered."
    return "\n".join(tests)
# ---------------------------------------------------------------------------
# Critical verification questions
# ---------------------------------------------------------------------------
def verification_questions() -> str:
    return """
Miles MUST verify these against executable source rather than trusting
documentation:
1. Does `LanternBridge` actually connect to the real Lantern APIs?
2. Does `OperatingLoop` actually enforce the intended sequence?
3. Does a reasoning provider have any direct path to tools?
4. Can MCP bypass `ToolBoundary`?
5. Can `PermissionAuthority` be bypassed?
6. Are permissions scoped and revocable?
7. Can model-generated text become evidence without independent observation?
8. Does `RealityBoundary` actually prevent that?
9. Does Spine require explicit human authorization before commitment?
10. Can model output modify persistent state without authorization?
11. Does `TransferManifest` preserve authority and provenance?
12. Does `SelfModel` reflect real runtime state?
13. Are provider adapters advisory, or can they directly mutate state?
14. What happens when Lantern is unavailable?
15. What happens when the reasoning model fails?
16. What happens when authorization is missing?
17. What happens when evidence is contradictory?
18. What happens when a tool call is malformed?
19. What happens when an unknown command is supplied?
20. Which protections exist in code and which exist only in prompts/comments?
For each answer use:
OBSERVED
CORROBORATED
CLAIMED
BLOCKED
UNKNOWN
DISPROVEN
"""
# ---------------------------------------------------------------------------
# Execution model
# ---------------------------------------------------------------------------
def execution_model(analyses) -> str:
    """
    This section is intentionally generated from discovered symbols rather
    than pretending that a fixed architecture is necessarily correct.
    """
    known_files = {
        relative(a.path)
        for a in analyses
    }
    output = [
        "The following execution model is a STATIC ANALYSIS HYPOTHESIS.",
        "",
        "It must be checked against the call graph above.",
        "",
    ]
    if "main.py" in known_files:
        output.append(
            "`main.py` appears to be an application entrypoint."
        )
    if "lantern_harness/bridge.py" in known_files:
        output.append(
            "`lantern_harness/bridge.py` appears to contain the Lantern "
            "integration boundary."
        )
    if "lantern_harness/operating_loop.py" in known_files:
        output.append(
            "`lantern_harness/operating_loop.py` appears to contain "
            "structured execution behavior."
        )
    if "lantern_harness/permission_authority.py" in known_files:
        output.append(
            "`lantern_harness/permission_authority.py` appears to contain "
            "authorization logic."
        )
    if "lantern_harness/reality_boundary.py" in known_files:
        output.append(
            "`lantern_harness/reality_boundary.py` appears to contain "
            "claim/evidence boundary logic."
        )
    if "lantern_harness/spine.py" in known_files:
        output.append(
            "`lantern_harness/spine.py` appears to contain persistence/"
            "commitment logic."
        )
    return "\n".join(output)
# ---------------------------------------------------------------------------
# Main report
# ---------------------------------------------------------------------------
def build_report() -> str:
    analyses = analyze_repository()
    now = datetime.now(
        timezone.utc
    ).isoformat()
    parts = []
    parts.append(
        "# MILES — LANTERN HARNESS HANDOFF\n\n"
        f"Generated: `{now}`\n\n"
        "This report was generated directly from the current repository.\n\n"
        "**Repository contents are the source of truth.**\n\n"
        "Static analysis was performed without executing the application.\n"
    )
    parts.append(
        "\n## 1. REPOSITORY MAP\n\n"
        "```text\n"
        + repository_map()
        + "\n```\n"
    )
    parts.append(
        "\n## 2. DISCOVERED EXECUTION MODEL\n\n"
        + execution_model(analyses)
        + "\n"
    )
    parts.append(
        "\n## 3. DISCOVERED ENTRY POINTS\n\n"
        + entrypoint_report(analyses)
        + "\n"
    )
    parts.append(
        "\n## 4. CLASSES AND FUNCTIONS\n\n"
        + symbol_report(analyses)
        + "\n"
    )
    parts.append(
        "\n## 5. IMPORT GRAPH\n\n"
        + import_report(analyses)
        + "\n"
    )
    parts.append(
        "\n## 6. STATIC CALL GRAPH\n\n"
        + call_graph(analyses)
        + "\n"
    )
    parts.append(
        "\n## 7. SECURITY-SENSITIVE OPERATIONS\n\n"
        + security_report(analyses)
        + "\n"
    )
    parts.append(
        "\n## 8. DEPENDENCIES AND CONFIGURATION\n\n"
        + configuration_report()
        + "\n"
    )
    parts.append(
        "\n## 9. TESTS\n\n"
        + test_report()
        + "\n"
    )
    parts.append(
        "\n## 10. TODO / STUB / FALLBACK / PARTIAL MARKERS\n\n"
        + marker_report(analyses)
        + "\n"
    )
    parts.append(
        "\n## 11. IMPORTANT SOURCE FILES\n\n"
        + "\n".join(
            source_block(name)
            for name in IMPORTANT_FILES
        )
    )
    parts.append(
        "\n## 12. VERIFICATION QUESTIONS\n\n"
        + verification_questions()
    )
    parts.append(
        """
## 13. INTERPRETATION RULE
Do NOT assume a feature exists merely because:
- README.md says it exists
- a prompt says it exists
- a comment says it exists
- a class has the expected name
- a method has the expected name
- a test file exists
Prefer executable source behavior.
If source proves the behavior:
    OBSERVED
If multiple independent tests or source paths support it:
    CORROBORATED
If the repository merely claims the behavior:
    CLAIMED
If code explicitly prevents the behavior:
    BLOCKED
If the repository does not provide enough information:
    UNKNOWN
If source or tests demonstrate that the claim is false:
    DISPROVEN
## 14. CENTRAL QUESTION FOR MILES
Determine precisely:
    What can this harness actually cause to happen?
and:
    What can the reasoning model NOT cause to happen
    without the required authorization?
Trace those answers through:
    model
      |
      v
    reasoning adapter
      |
      v
    bridge
      |
      v
    operating loop
      |
      v
    tool boundary
      |
      v
    permission authority
      |
      v
    external/tool action
      |
      v
    persistent state
Do not stop at interfaces.
Follow the implementation.
## 15. SECURITY NOTICE
This report is sanitized using heuristic secret detection.
It is NOT a guarantee that every secret has been found.
Before giving this report to another system, manually check:
- credentials
- API keys
- bearer tokens
- private keys
- passwords
- cookies
- session identifiers
- personal information
- private endpoints
- internal hostnames
Never treat redaction as a substitute for secret rotation.
## 16. HANDOFF
Give Miles the contents of this file.
Miles should be able to use it to:
1. understand the repository;
2. locate the important implementation;
3. follow the actual call relationships;
4. identify missing boundaries;
5. identify stubbed behavior;
6. identify bypass paths;
7. identify failing assumptions;
8. propose the smallest repair necessary.
Accuracy is more important than making the system appear complete.
"""
    )
    return "\n".join(parts)
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    report = build_report()
    OUT.write_text(
        report,
        encoding="utf-8",
    )
    print()
    print("=" * 70)
    print("MILES HANDOFF CREATED")
    print("=" * 70)
    print()
    print(f"Repository: {ROOT}")
    print(f"Output:     {OUT}")
    print(f"Characters: {len(report):,}")
    print()
    print("No application code was executed.")
    print("No ZIP file was created.")
    print()
    print("Give Miles the contents of:")
    print()
    print(f"    {OUT}")
    print()
if __name__ == "__main__":
    main()
