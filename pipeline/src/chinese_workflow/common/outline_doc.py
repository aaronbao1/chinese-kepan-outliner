"""Draft tree -> numbered zh-kepan outline document (docs/outliner-design.md §5.0).

Every outline source (tier 1, tier 2, the scheme prior, the resolver) emits *draft nodes*: dicts with the
node fields it knows plus "children" (a list, source order). Keys that start with "_" are private working
data (e.g. "_offset", the character offset of an entry marker); they never enter the document and are
returned separately, keyed by the final node id, for the anchor step.

build_prediction(roots, **meta) numbers the tree in pre-order, fills every key the zh-kepan profile requires
(context/baseline/outline-schema-zh.json, D15), generates indicator_display (sibling index + subscript level
per token, e.g. '2₁1₂') and display_label (干支 of the level + Chinese ordinal, R07 F15), and computes the
metadata counts. validate(doc) runs scripts/validate_outline.py in process (its single owner).
fill_span_starts(doc) writes the second commentary locator, locations.commentary.span_start (sdp's anchor
rule: a first child starts where its parent does, when the build covers the parent's start), after a
build's last tree edit (outline.pipeline).
"""

from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType

from . import lineheads
from .paths import REPO_ROOT, VALIDATOR

ZH_PROFILE = "zh-kepan"
ID_CONVENTION = (
    "zh-kepan: each id token is <sibling_index>_<level> in decimal, tokens joined by '.', "
    "e.g. '2_1.1_2.3_3' = second top node -> its first child -> that child's third child; "
    "sibling order is the source's order."
)
GANZHI = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"  # level 1..22 (R07 F15)
DIGITS = "〇一二三四五六七八九"
SUBSCRIPTS = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
DISPLAY_LABEL_RULE = (
    "generated: 干支 symbol of the node's level (甲 = 1 … 癸 = 10, 子 = 11 … 亥 = 22) + the sibling "
    "ordinal in Chinese numerals 一二三… (R07 F15); null below level 22 or past sibling 99"
)
CBETA_LICENCE = {
    "id": "CC-BY-NC-SA-4.0",
    "holder": "CBETA (中華電子佛典協會)",
    "statement": (
        "Derived from CBETA 2026R2 text (CC BY-NC-SA 4.0 with CBETA's notice, "
        "data/raw/cbeta/LICENCE-NOTICE.txt). Whether an outline is 改作 is an open question to CBETA "
        "(R02 F7); not for publication before that answer and a repository LICENSE."
    ),
    "evidence": "R02 F7/F29; data/reference-outlines/NOTICE",
}
# every key a zh-kepan node must carry (base required + node_zh required), with its default
NODE_DEFAULTS = {
    "heading_src": "",
    "heading_en": "",
    "origin": "explicit",
    "evidence": "",
    "notes": [],
    "node_class": "sutra-span",
    "flags": [],
    "child_count_announced": None,
    "extent_announced": None,
    "source_node_id": None,
    "locations": {"scheme": "none"},
}
KEY_ORDER = (
    "id", "indicator_display", "level", "path", "parent_id", "order", "heading_src", "heading_en",
    "source_language", "locations", "origin", "confidence", "evidence", "topic_category", "notes",
    "sibling_index", "child_count_announced", "extent_announced", "node_class", "flags",
    "source_node_id", "display_label", "scheme_id", "part_type",
)


def chinese_numeral(k: int) -> str:
    """1..99 in Chinese numerals (一, 十, 十一, 二十, 二十一 …)."""
    if not 1 <= k <= 99:
        raise ValueError(k)
    tens, ones = divmod(k, 10)
    if tens == 0:
        return DIGITS[ones]
    return ("" if tens == 1 else DIGITS[tens]) + "十" + (DIGITS[ones] if ones else "")


def generated_label(level: int, sibling_index: int) -> str | None:
    if level > len(GANZHI) or sibling_index > 99:
        return None
    return GANZHI[level - 1] + chinese_numeral(sibling_index)


def indicator(path: list) -> str:
    """zh-kepan path ['2_1', '1_2'] -> '2₁1₂' (Kurt's indicator with digits at every level)."""
    out = []
    for token in path:
        value, level = token.rsplit("_", 1)
        out.append(value + level.translate(SUBSCRIPTS))
    return "".join(out)


def number_tree(roots: list) -> tuple[list, dict]:
    """Flatten drafts in pre-order. Returns (nodes, private) where private maps node id -> the draft's
    '_'-prefixed keys. Drafts are not modified."""
    nodes: list = []
    private: dict = {}

    def visit(drafts: list, parent_path: list):
        for k, draft in enumerate(drafts, 1):
            path = parent_path + ["%d_%d" % (k, len(parent_path) + 1)]
            nid = ".".join(path)
            node = {
                "id": nid,
                "indicator_display": indicator(path),
                "level": len(path),
                "path": path,
                "parent_id": ".".join(parent_path) if parent_path else None,
                "order": len(nodes) + 1,
                "sibling_index": k,
            }
            for key, value in NODE_DEFAULTS.items():
                node[key] = copy.deepcopy(value)
            for key, value in draft.items():
                if key == "children":
                    continue
                if key.startswith("_"):
                    private.setdefault(nid, {})[key] = value
                elif key not in ("id", "level", "path", "parent_id", "order", "sibling_index",
                                 "indicator_display"):
                    node[key] = copy.deepcopy(value)
            if "display_label" not in draft:
                node["display_label"] = generated_label(len(path), k)
            nodes.append({key: node[key] for key in _ordered_keys(node)})
            visit(draft.get("children") or [], path)

    visit(roots, [])
    return nodes, private


def _ordered_keys(node: dict) -> list:
    known = [k for k in KEY_ORDER if k in node]
    return known + sorted(k for k in node if k not in KEY_ORDER)


def level_counts(nodes: list) -> dict:
    levels = Counter(n["level"] for n in nodes)
    return {
        "node_count": len(nodes),
        "max_depth": max(levels, default=0),
        "nodes_per_level": {str(lv): c for lv, c in sorted(levels.items())},
    }


def prediction_metadata(nodes: list, *, text_id: str, text_title_src: str, outline_mode: str,
                        root_text_id: str | None, commentary_id: str | None, scheme_id: str,
                        source_file: str, source_document: dict, generated_by: str,
                        format_note: str, text_title_en: str = "", cbeta_release: str | None = "2026R2",
                        licence: dict | None = None, eval_only: bool = False, **extra) -> dict:
    """zh-kepan metadata of a prediction (gold_status 'prediction', seeded_by null)."""
    meta = {
        "outline_profile": ZH_PROFILE,
        "source_file": source_file,
        "source_sha256": extra.pop("source_sha256", None),
        "text_id": text_id,
        "text_title_src": text_title_src,
        "text_title_en": text_title_en,
        "author": extra.pop("author", None),
        "source_language": "lzh",
        "format_note": format_note,
        "id_convention": ID_CONVENTION,
        "generated_by": generated_by,
        "source_document": source_document,
        "outline_mode": outline_mode,
        "root_text_id": root_text_id,
        "commentary_id": commentary_id if outline_mode == "sutra" else None,
        "scheme_id": scheme_id,
        "seeded_by": None,
        "gold_status": "prediction",
        "licence": licence or dict(CBETA_LICENCE),
        "eval_only": eval_only,
        "cbeta_release": cbeta_release,
        "display_label_rule": DISPLAY_LABEL_RULE,
    }
    meta.update(extra)
    meta.update(level_counts(nodes))
    return meta


def build_prediction(roots: list, **meta) -> tuple[dict, dict]:
    """Number the draft tree and wrap it in a prediction document. Returns (doc, private)."""
    nodes, private = number_tree(roots)
    doc = {"metadata": prediction_metadata(nodes, **meta), "nodes": nodes}
    return doc, private


def refresh_counts(doc: dict) -> dict:
    """Recompute metadata counts after nodes were edited in place."""
    doc["metadata"].update(level_counts(doc["nodes"]))
    return doc


def children_map(nodes: list) -> dict:
    """parent id (None for roots) -> [child nodes] in document order."""
    out: dict = {}
    for n in nodes:
        out.setdefault(n["parent_id"], []).append(n)
    return out


# ----------------------------------------------------------------- the span-start locator (T2, 2026-10-02)


def fill_span_starts(doc: dict) -> dict:
    """Write locations.commentary.span_start and span_start_inherited on every node that has a
    cbeta-kepan commentary position, in place, from the tree and the explained lines alone (E06 review
    2026-10-02, direction A3; final review 2026-10-03, Important 1).

    The rule is sdp's anchor rule (data/EVAL-SETS.md item 3): a node's text starts where its parent's
    does when it is the parent's first child, else at its own explained line. A first child inherits
    its parent's span_start (span_start_inherited true; so a chain of first children shares one line,
    as sdp keys them) only when it really is the parent's first child, i.e. only when the build covers
    the parent's start; two cases say it does not, and the child then gets its own explained line
    (span_start_inherited false):
      - the parent is an editorial node (the scheme prior's levels, a carried pin: outline.scheme,
        outline.tier1): its explained line is where the scheme or a mulu line puts it, not where its
        text starts, and in a span build its true first child may lie before the span;
      - the parent's span_start lies before metadata.span.first, the first line of the build (an
        explicit parent can too, through a carried or outer start): the build's first child is then
        only the first child the build has. A build without metadata.span (a hand-made document) has
        no such cut.
    Every other node, and a first child whose parent has no span_start, gets its own explained line
    (false; null when explained is null). A node without a commentary position (another location
    scheme, or commentary null) gets nothing and counts as having no span_start for its children.
    First children are read off document order (children_map), not sibling_index. Idempotent:
    recomputed on every call, never read from the input, so it runs once, after the last tree edit of
    a build (outline.pipeline) or on a saved outline (python -m chinese_workflow.outline span-start).
    Returns doc."""
    kids = children_map(doc["nodes"])
    first = {c[0]["id"] for p, c in kids.items() if p is not None and c}
    by_id = {n["id"]: n for n in doc["nodes"]}
    span = (doc.get("metadata") or {}).get("span")
    cut = lineheads.strip_offset(span.get("first")) if isinstance(span, dict) else None
    starts: dict = {}  # node id -> its span_start (None: none)

    def before_build(ref) -> bool:  # a start line of the same file that lies before the build's first line
        return (cut is not None and lineheads.is_ref(ref) and lineheads.is_ref(cut)
                and lineheads.file_id(ref) == lineheads.file_id(cut) and lineheads.strip_offset(ref) < cut)

    for n in doc["nodes"]:
        loc = n.get("locations") if isinstance(n.get("locations"), dict) else {}
        com = loc.get("commentary") if loc.get("scheme") == "cbeta-kepan" else None
        if not isinstance(com, dict):
            starts[n["id"]] = None
            continue
        parent = by_id.get(n.get("parent_id"))
        inherited = None
        if n["id"] in first and parent is not None and parent.get("origin") != "editorial":
            inherited = starts.get(parent["id"])
            if before_build(inherited):
                inherited = None
        if inherited is not None:
            com["span_start"], com["span_start_inherited"] = inherited, True
        else:
            com["span_start"], com["span_start_inherited"] = com.get("explained"), False
        starts[n["id"]] = com["span_start"]
    return doc


def to_drafts(doc: dict) -> list:
    """Inverse of number_tree: a document's nodes as a nested draft tree (ids dropped, fields kept), so a
    stage can insert nodes and renumber. The original id is kept in '_orig_id'."""
    kids = children_map(doc["nodes"])
    drop = {"id", "indicator_display", "level", "path", "parent_id", "order", "sibling_index"}

    def build(parent):
        out = []
        for n in kids.get(parent, []):
            d = {k: copy.deepcopy(v) for k, v in n.items() if k not in drop}
            d["_orig_id"] = n["id"]
            if n.get("display_label") == generated_label(n["level"], n["sibling_index"]):
                d.pop("display_label", None)  # regenerate after renumbering
            d["children"] = build(n["id"])
            out.append(d)
        return out

    return build(None)


# ------------------------------------------------------------------- the explicit-node invariant

EXPLICIT_ORIGINS = ("explicit", "imported", "editorial")


def explicit_fingerprint(doc: dict) -> dict:
    """What no later step may change about an explicit (or imported / editorial) node: keyed by a
    content key that survives renumbering (commentary.explained + heading + position among explicit
    siblings), the heading, the commentary locators, the explicit ancestor chain and child count
    announced, and its level (so no inferred ancestor may be inserted above an explicit node). Inferred
    children may be added; this fingerprint ignores them."""
    by_id = {n["id"]: n for n in doc["nodes"]}

    def comm(n):
        c = (n.get("locations") or {}).get("commentary") or {}
        return (c.get("announced"), c.get("explained"))

    def explicit_ancestors(n):
        out = []
        p = n.get("parent_id")
        while p is not None:
            pn = by_id[p]
            if pn.get("origin") in EXPLICIT_ORIGINS:
                out.append((pn["heading_src"], comm(pn)))
            p = pn.get("parent_id")
        return tuple(reversed(out))

    fp = {}
    for n in doc["nodes"]:
        if n.get("origin") not in EXPLICIT_ORIGINS:
            continue
        key = (n["heading_src"], comm(n), explicit_ancestors(n))
        fp[repr(key)] = {"origin": n["origin"], "level": n["level"],
                         "child_count_announced": n.get("child_count_announced"),
                         "node_class": n.get("node_class")}
    return fp


def assert_explicit_unchanged(before: dict, after: dict) -> None:
    """Raise AssertionError naming the first explicit node that a step removed or altered."""
    fb, fa = explicit_fingerprint(before), explicit_fingerprint(after)
    missing = [k for k in fb if k not in fa]
    changed = [k for k in fb if k in fa and fb[k] != fa[k]]
    if missing or changed:
        raise AssertionError("explicit nodes modified: missing %s, changed %s" % (missing[:3], changed[:3]))


# ------------------------------------------------------------------------------------ validation


def load_validator() -> ModuleType:
    """scripts/validate_outline.py as a module (scripts/ is not a package)."""
    mod = sys.modules.get("validate_outline")
    if mod is not None and Path(getattr(mod, "__file__", "")).resolve() == VALIDATOR:
        return mod
    spec = importlib.util.spec_from_file_location("validate_outline", VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_outline"] = mod
    spec.loader.exec_module(mod)
    return mod


def validate(doc: dict, path: str = "<document>"):
    """Report of scripts/validate_outline.py (.errors, .warnings, .passed())."""
    return load_validator().validate_document(doc, "auto", path)


def pipeline_commit() -> dict:
    """{'commit': sha or None, 'dirty': bool or None} of the repository, for generated_by / run.json."""
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                    cwd=REPO_ROOT, capture_output=True, text=True,
                                    check=True).stdout.strip())
        return {"commit": sha, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}
