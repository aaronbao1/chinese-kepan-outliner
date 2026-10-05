"""chinese_workflow.eval.gold.common — what every gold builder needs.

Input : a nested draft tree built by an importer (sdp.py, and the later cbeta_mulu / ybh / authored
        builders): a list of top-level dicts, each carrying the node fields it knows (heading_src,
        locations, flags, …) and "children": [...] in source order.
Output: a zh-kepan outline document (context/baseline/outline-schema-zh.json) — nodes numbered in
        pre-order with digit ids / path / parent_id / order / sibling_index, metadata counts —
        written as UTF-8 JSON and checked in-process by scripts/validate_outline.py.

The structural and schema checks stay in scripts/validate_outline.py (their single owner); this
module loads that script with importlib from the repository path, resolved relative to this file,
and never copies its logic. Line existence comes from chinese_workflow.ingest.lines.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType

from chinese_workflow.ingest.lines import iter_lines

REPO_ROOT = Path(__file__).resolve().parents[5]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_outline.py"

ZH_PROFILE = "zh-kepan"
ID_CONVENTION = (
    "zh-kepan: each id token is <sibling_index>_<level> in decimal, tokens joined by '.', "
    "e.g. '2_1.1_2.3_3' = second top node -> its first child -> that child's third child; "
    "sibling order is the source's order."
)


def load_validator() -> ModuleType:
    """scripts/validate_outline.py as a module (scripts/ is not a package). Reuses an already
    loaded copy of the same file, e.g. the one the test suite registers."""
    mod = sys.modules.get("validate_outline")
    if mod is not None and Path(getattr(mod, "__file__", "")).resolve() == VALIDATOR_PATH:
        return mod
    spec = importlib.util.spec_from_file_location("validate_outline", VALIDATOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_outline"] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


def validate(doc: dict, path: str = "<document>"):
    """Schema + structural checks of scripts/validate_outline.py on an in-memory document; returns
    its Report (``.errors``, ``.warnings``, ``.passed()``)."""
    return load_validator().validate_document(doc, "auto", path)


def number_tree(roots: list) -> list:
    """Flatten a nested draft tree into zh-kepan nodes in pre-order.

    Each draft is a dict of node fields plus "children" (a list, possibly empty). The returned
    nodes carry id / level / path / parent_id / order / sibling_index (sibling order = list order)
    followed by the draft's own fields; "children" is dropped. Drafts are not modified."""
    out: list = []

    def visit(drafts: list, parent_path: list):
        for k, draft in enumerate(drafts, 1):
            path = parent_path + ["%d_%d" % (k, len(parent_path) + 1)]
            node = {
                "id": ".".join(path),
                "level": len(path),
                "path": path,
                "parent_id": ".".join(parent_path) if parent_path else None,
                "order": len(out) + 1,
                "sibling_index": k,
            }
            node.update(
                {key: v for key, v in draft.items() if key != "children" and key not in node}
            )
            out.append(node)
            visit(draft.get("children") or [], path)

    visit(roots, [])
    return out


def level_counts(nodes: list) -> dict:
    """node_count / max_depth / nodes_per_level as the metadata block states them."""
    levels = Counter(n["level"] for n in nodes)
    return {
        "node_count": len(nodes),
        "max_depth": max(levels, default=0),
        "nodes_per_level": {str(lv): c for lv, c in sorted(levels.items())},
    }


def zh_metadata(nodes: list, **fields) -> dict:
    """A zh-kepan metadata block: the given fields, the profile marker and id convention (unless
    given), and counts computed from the nodes (always recomputed, never taken from fields)."""
    meta = {"outline_profile": ZH_PROFILE, "id_convention": ID_CONVENTION}
    meta.update(fields)
    meta.update(level_counts(nodes))
    return meta


def compose_linehead(cbeta_id: str, lb_n: str) -> str:
    """CBETA composed linehead, e.g. ('T09n0262', '0001c18') -> 'T09n0262_p0001c18' (R02 F6)."""
    return "%s_p%s" % (cbeta_id, lb_n)


def known_lineheads(xml_path) -> frozenset:
    """Every linehead of a CBETA P5 file's own edition (chinese_workflow.ingest.lines)."""
    return frozenset(rec["linehead"] for rec in iter_lines(xml_path))


def line_texts(xml_path) -> dict:
    """{linehead: reading text} of a CBETA P5 file's own-edition lines, in the file's line order
    (chinese_workflow.ingest.lines; the order is not always monotonic, e.g. T09n0262's 附文)."""
    return {rec["linehead"]: rec["text"] for rec in iter_lines(xml_path)}


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def write_json(doc: dict, path) -> Path:
    """Write a document as UTF-8 JSON (CJK kept literal, one key per line), creating parents."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def repo_relative(path) -> str:
    """Repository-relative form of a path for metadata (the absolute path if outside the repo)."""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)
