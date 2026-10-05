"""Stage boundaries (docs/outliner-design.md §2; plan Appendix C rule 4; docs/architecture.md: stages
talk through files, and the outliner does not reach into the translator).

Every stage package under pipeline/src/chinese_workflow/ may import only chinese_workflow.common,
chinese_workflow.llm, chinese_workflow.ingest and its own package. Exceptions, each with its reason:
  eval    also imports eval.* (its own) — never outline, chunk, segment, context, translate, export;
  runner  is the headless harness: the one module that imports several stages (it still hands files on);
  llm     imports only common.
The check is static (ast), so it also covers modules no test imports.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2] / "pipeline" / "src" / "chinese_workflow"
SHARED = {"common", "llm", "ingest"}
STAGES = ["ingest", "outline", "segment", "chunk", "context", "translate", "eval", "export", "llm",
          "common"]
ALLOWED = {
    "common": set(),
    "llm": {"common"},
    "ingest": {"common"},
}


def _package(py: Path) -> list:
    """Dotted package of a module file, e.g. .../outline/tier2/parser.py -> ['chinese_workflow',
    'outline', 'tier2']; an __init__.py is its own package."""
    rel = py.relative_to(PKG.parent).with_suffix("")
    parts = list(rel.parts)
    return parts[:-1]


def _imports(py: Path) -> set:
    """The chinese_workflow subpackages (first component after chinese_workflow) a module imports."""
    tree = ast.parse(py.read_text(encoding="utf-8"))
    pkg = _package(py)
    out = set()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".") for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = (node.module or "").split(".")
            else:
                base = pkg[: len(pkg) - (node.level - 1)] + (node.module.split(".") if node.module
                                                            else [])
            if len(base) == 1 and base[0] == "chinese_workflow":
                names = [["chinese_workflow", a.name] for a in node.names]
            else:
                names = [base]
        for parts in names:
            if len(parts) > 1 and parts[0] == "chinese_workflow":
                out.add(parts[1])
    return out


@pytest.mark.parametrize("stage", STAGES)
def test_stage_imports_only_shared_packages(stage):
    root = PKG / stage
    if not root.exists():
        pytest.skip("stage %s not present" % stage)
    allowed = ALLOWED.get(stage, SHARED) | {stage}
    bad = []
    for py in sorted(root.rglob("*.py")):
        for target in _imports(py):
            if target not in allowed:
                bad.append("%s imports chinese_workflow.%s" % (py.relative_to(PKG), target))
    assert not bad, "\n".join(bad)


def test_outline_never_imports_translate_or_chunk():
    for py in (PKG / "outline").rglob("*.py"):
        targets = _imports(py)
        assert not targets & {"translate", "chunk", "context", "segment", "eval"}, py
