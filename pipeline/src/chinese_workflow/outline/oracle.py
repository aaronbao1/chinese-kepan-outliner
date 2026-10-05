"""chinese_workflow.outline.oracle — the oracle extractor of the walking skeleton (plan Appendix
A "SK", oracle guard; outline --source oracle).

The skeleton runs every stage before the outliner exists, so its outline comes from a gold, read by
code that lets through only what a developer may see (data/EVAL-SETS.md, "Do not open while
developing").

Input : a gold outline.json (zh-kepan); for SK the Kuiji gold
        data/reference-outlines/T0262/kuiji-xuanzan/outline.json, and keep_span = (first, last)
        commentary lineheads, inclusive: the T34n1723 dev span is
        ("T34n1723_p0850a19", "T34n1723_p0850b19") (the registry's span ends, exclusive, at
        p0850b20).
Output: draft nodes (nested, document order, common.outline_doc idiom) for
          * every node of level <= max_level (default 2: the gold's 3 parts and 28 品), and
          * every node whose commentary.explained lies in keep_span,
        with structural fields only: numbering fields dropped (build_prediction renumbers),
        `notes` emptied, nothing from metadata (no metadata.coverage, no split notes). The gold
        node id is kept as the private key "_oracle_id" (never enters a document).
        On nodes of level <= max_level outside keep_span, wording that quotes a test or reserve
        line is withheld: `evidence` becomes a pointer when a linehead it cites lies in a test or
        reserve span (the Kuiji gold's 序分/正宗/流通 evidence quotes Kuiji's statement at
        T34n1723_p0661b10, inside the 序品 test span), and the `raw` wording of both location
        parts is dropped.

Refusals (common.splits; EVAL-SETS rules):
  * SplitViolation when a kept node below max_level has an explained line in a test or reserve
    span (checked on locators before any node content is copied), or when keep_span's ends are
    test or reserve lines;
  * SplitViolation when the gold is registered in data/eval-sets.json as out-of-domain or
    eval-only: never input material (design §3; D8842 waits for Aaron's re-filing, plan SK);
  * ValueError when a node kept by keep_span has a parent that is not kept (the span cuts a
    subtree below max_level), so that no node is re-parented silently.
It prints nothing and writes nothing.

Provenance: docs/plans/2026-09-24-outliner-and-translation.md Appendix A "SK" (oracle guard);
data/EVAL-SETS.md "Splits" and "Do not open while developing"; docs/outliner-design.md §3.
"""

from __future__ import annotations

import copy
import re

from ..common.jsonio import read_json
from ..common.lineheads import is_ref, parse
from ..common.paths import repo_relative
from ..common.splits import (
    BLOCKED,
    SplitViolation,
    is_eval_only,
    is_ood,
    load_registry,
    split_of_line,
)

NUMBERING = ("id", "indicator_display", "level", "path", "parent_id", "order", "sibling_index")
_REF_IN_TEXT = re.compile(r"[A-Z]+[0-9]+n[0-9A-Za-z]+_p[0-9a-z][0-9]{3}[a-z][0-9]{2}")


def _pos(ref: str) -> tuple:
    r = parse(ref)
    return (r.file, r.page, r.register, r.line)


def _in_span(ref, lo: tuple, hi: tuple) -> bool:
    if not is_ref(ref):
        return False
    p = _pos(ref)
    return p[0] == lo[0] == hi[0] and lo[1:] <= p[1:] <= hi[1:]


def _explained(node: dict):
    return ((node.get("locations") or {}).get("commentary") or {}).get("explained")


def _check_registered(gold_path, registry: dict) -> None:
    rel = repo_relative(gold_path)
    for ds in registry.get("datasets", []):
        if ds.get("path") == rel and (is_ood(ds) or is_eval_only(ds)):
            raise SplitViolation("%s (%s) is %s: never oracle input material"
                                 % (ds["id"], rel, "out-of-domain" if is_ood(ds) else "eval-only"))


def _structural(node: dict, in_span: bool, registry: dict) -> dict:
    d = {k: copy.deepcopy(v) for k, v in node.items() if k not in NUMBERING}
    d["notes"] = []
    d["_oracle_id"] = node["id"]
    if in_span:
        return d
    cited = {split_of_line(registry, ref) for ref in _REF_IN_TEXT.findall(d.get("evidence") or "")}
    blocked = sorted(cited & set(BLOCKED))
    if blocked:
        d["evidence"] = "oracle: evidence withheld (cites a %s line); gold node %s" % (
            "/".join(blocked), node["id"])
    loc = d.get("locations") or {}
    for part in ("commentary", "root_text"):
        if isinstance(loc.get(part), dict):
            loc[part].pop("raw", None)
    return d


def oracle_drafts(gold_path, *, keep_span: tuple, max_level: int = 2) -> list:
    """Draft nodes of a gold restricted to levels <= max_level plus the nodes explained inside
    keep_span (module docstring). Raises SplitViolation / ValueError as described there."""
    registry = load_registry()
    _check_registered(gold_path, registry)
    first, last = keep_span
    for ref in (first, last):
        if split_of_line(registry, ref) in BLOCKED:
            raise SplitViolation("keep_span end %s lies in a %s span"
                                 % (ref, split_of_line(registry, ref)))
    lo, hi = _pos(first), _pos(last)
    if lo[0] != hi[0] or lo[1:] > hi[1:]:
        raise ValueError("keep_span %s..%s is not a forward span of one file" % (first, last))

    nodes = read_json(gold_path)["nodes"]
    # pass 1, on locators only: which nodes are kept, and may they be?
    kept: dict = {}  # id -> inside keep_span
    for n in nodes:
        in_span = _in_span(_explained(n), lo, hi)
        if n["level"] <= max_level or in_span:
            kept[n["id"]] = in_span
    for n in nodes:
        if n["id"] in kept and n["level"] > max_level:
            split = split_of_line(registry, _explained(n))
            if split in BLOCKED:
                raise SplitViolation("a kept node below level %d is explained on a %s line"
                                     % (max_level, split))
    orphans = sum(1 for n in nodes if n["id"] in kept and n["parent_id"] is not None
                  and n["parent_id"] not in kept)
    if orphans:
        raise ValueError("%d node(s) in keep_span have a parent outside the kept set" % orphans)

    # pass 2: the nested drafts (nodes are in pre-order: a parent precedes its children)
    roots: list = []
    by_id: dict = {}
    for n in nodes:
        if n["id"] not in kept:
            continue
        d = _structural(n, kept[n["id"]], registry)
        d["children"] = []
        by_id[n["id"]] = d
        (by_id[n["parent_id"]]["children"] if n["parent_id"] is not None else roots).append(d)
    return roots
