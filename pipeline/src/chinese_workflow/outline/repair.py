"""chinese_workflow.outline.repair — local validator errors become a degraded outline, not a discarded one
(docs/outliner-design.md §5.0 'Degradation'; E06 review 2026-10-02 §2 row B5).

Input : a numbered zh-kepan document (after outline_doc.build_prediction and anchor.resolve_root_spans) and
        the error Findings of scripts/validate_outline.py over it.
Output: the document edited in place, and the list of repairs that outline-report.json records under
        `degraded[].repairs`. Non-local findings are ignored and left to the caller, which fails the build.

Only the codes whose cause is one node or one sibling group are repaired, each the way the explicit sources
already treat the case:
  [sibling-order]        in the validator's sibling group (parent_id, scheme_id when not the main scheme) the
                         non-decreasing chain of the locator with the most explicit (non-inferred) nodes is
                         kept — so an inferred node never displaces an explicit one — ties going to the chain
                         whose explicit nodes come earlier in document order, then to the one keeping more
                         inferred nodes; the rest are demoted as tier 2's _self_mode_order
                         demotes an item taken up out of order: commentary.explained -> null (no explained
                         position; the listing position would again precede the elder sibling's treatment),
                         root_text -> start/end null with raw kept (anchor.write's unplaced shape) + flag
                         unmapped on a sutra-span node. Note 'demoted: sibling-order, was <ref>'.
  [child-outside-parent] an inferred child's span is clipped to its parent's; an explicit child's end raises
                         the parent's end and each shorter ancestor's, as tier 1's _unit_ends raises a unit's
                         end to its last descendant's (end_basis kept, as there); an explicit child's start is
                         clipped unless the parent is inferred, whose start is lowered instead. A span that
                         would invert is nulled (+ unmapped).
  [cbeta-order]          a root_text span whose start follows its end is nulled, raw kept, + unmapped.
Explicit nodes: a demotion, a raise or a clip changes an explicit node, so the pipeline runs this before the
resolver's `before` snapshot (common.outline_doc.assert_explicit_unchanged). What protects explicit nodes in the
pass after the resolver is not the chain choice (two explicit siblings that disagree would still lose one) but
that the resolver validates every change it makes (resolver._Merger.apply: the explicit fingerprint and the
validator), so it hands back a document whose explicit nodes validate; the pipeline asserts the fingerprint
after that pass (headings, levels, commentary locators; not root_text). Comparison of refs is the validator's
own (compare_refs with metadata.work_files ranking), reached through outline_doc.load_validator().
"""

from __future__ import annotations

from ..common import outline_doc
from .anchor import nulled_basis

LOCAL_CODES = ("sibling-order", "child-outside-parent", "cbeta-order")
ORDERED = ("root_text.start", "commentary.explained")
MAX_PASSES = 3


def is_local(finding) -> bool:
    """A finding this module repairs (the codes whose cause is one node or one sibling group)."""
    return finding.code in LOCAL_CODES


def _root_text(n: dict):
    loc = n.get("locations") if isinstance(n.get("locations"), dict) else {}
    rt = loc.get("root_text") if loc.get("scheme") == "cbeta-kepan" else None
    return rt if isinstance(rt, dict) else None


def _locator(n: dict, what: str):
    if what == "root_text.start":
        return (_root_text(n) or {}).get("start")
    com = (n.get("locations") or {}).get("commentary")
    return com.get("explained") if isinstance(com, dict) else None


def _group_scheme(n: dict, meta: dict):
    s = n.get("scheme_id")
    return s if isinstance(s, str) and s != meta.get("scheme_id") else None


def _null_root_text(n: dict) -> None:
    """start/end -> null, raw kept (as anchor.write leaves an unplaced node: the basis is anchor.nulled_basis
    of the old one, so a derived basis becomes `lemma` here as there), flag unmapped."""
    rt = _root_text(n)
    if rt is not None:
        if isinstance(rt.get("raw"), str):
            keep = {"text_id": rt["text_id"]} if rt.get("text_id") else {}
            keep.update({"start": None, "end": None, "basis": nulled_basis(rt.get("basis")), "raw": rt["raw"]})
            n["locations"]["root_text"] = keep
        else:
            n["locations"]["root_text"] = None
    if n.get("node_class") == "sutra-span" and "unmapped" not in n["flags"]:
        n["flags"].append("unmapped")


def _demote(n: dict, what: str, was: str) -> dict:
    if what == "commentary.explained":
        n["locations"]["commentary"]["explained"] = None
    else:
        _null_root_text(n)
    n["notes"].append("demoted: sibling-order, was %s" % was)
    return {"kind": "demoted", "node_id": n["id"], "code": "sibling-order", "locator": what, "was": was}


def _extend(key: tuple, i: int, inferred: bool) -> tuple:
    """The chain key after appending sibling i: (explicit count, minus the explicit nodes' positions,
    inferred count); a larger key is better, compared lexicographically."""
    explicit, order, inf = key
    return (explicit, order, inf + 1) if inferred else (explicit + 1, order + (-i,), inf)


def _demote_out_of_order(siblings: list, what: str, cmp, parse) -> list:
    """Keep the best non-decreasing chain of `what` among the siblings and demote the rest. The best chain
    has the most explicit (non-inferred) nodes, so an inferred node never displaces an explicit one; ties
    go to the chain whose explicit nodes come earlier in document order (an inferred sibling cannot decide
    which of two explicit ones is kept), then to the chain with more inferred nodes, then to earlier
    nodes."""
    have = [(m, _locator(m, what)) for m in siblings]
    have = [(m, v) for m, v in have if parse(v)]
    if not have:
        return []
    inferred = [m.get("origin") == "inferred" for m, _ in have]
    best = [_extend((0, (), 0), i, inferred[i]) for i in range(len(have))]
    prev: list = [None] * len(have)
    for i in range(len(have)):
        for j in range(i):
            if (cmp(have[j][1], have[i][1]) or 0) <= 0:
                key = _extend(best[j], i, inferred[i])
                if key > best[i]:
                    best[i], prev[i] = key, j
    keep, k = set(), max(range(len(have)), key=lambda i: (best[i], -i))
    while k is not None:
        keep.add(k)
        k = prev[k]
    return [_demote(m, what, v) for i, (m, v) in enumerate(have) if i not in keep]


def _set_bound(n: dict, key: str, value: str, kind: str) -> dict:
    """Set root_text.<key> ('start' or 'end') of n to value, with a note and a repair entry of `kind`
    ('lowered' / 'raised' / 'clipped')."""
    rt = _root_text(n)
    was = rt.get(key)
    rt[key] = value
    n["notes"].append("%s: child-outside-parent, root_text.%s was %s" % (kind, key, was))
    return {"kind": kind, "node_id": n["id"], "code": "child-outside-parent", "field": "root_text." + key,
            "was": was, "now": value}


def _null_span(n: dict, code: str) -> list:
    rt = _root_text(n)
    if rt is None or (rt.get("start") is None and rt.get("end") is None):  # none, or already nulled
        return []
    was = "%s..%s" % (rt.get("start"), rt.get("end"))
    _null_root_text(n)
    n["notes"].append("nulled: %s, was %s" % (code, was))
    return [{"kind": "nulled", "node_id": n["id"], "code": code, "was": was}]


def _fit_into_parent(n: dict, by_id: dict, cmp) -> list:
    """An inferred child is clipped to its parent's span; an explicit child's end raises its parent's
    end (and the ancestors'), as tier 1's _unit_ends raises a unit's end to its last descendant's; an
    explicit child's start is clipped (an inferred parent's start is lowered instead). A span that
    would invert is nulled."""
    p = by_id.get(n.get("parent_id"))
    child, parent = _root_text(n), _root_text(p) if p else None
    if not child or not parent or not child.get("start") or not parent.get("start"):
        return []
    out = []
    c_start, c_end = child["start"], child.get("end") or child["start"]
    p_start, p_end = parent["start"], parent.get("end")
    if (cmp(p_start, c_start) or 0) > 0:
        if n.get("origin") != "inferred" and p.get("origin") == "inferred":
            out.append(_set_bound(p, "start", c_start, "lowered"))
        else:
            out.append(_set_bound(n, "start", p_start, "clipped"))
    if p_end and (cmp(c_end, p_end) or 0) > 0:
        if n.get("origin") == "inferred":
            out.append(_set_bound(n, "end", p_end, "clipped"))
        else:
            q = p
            while q is not None:
                rt = _root_text(q)
                if not rt or not rt.get("end") or (cmp(rt["end"], c_end) or 0) >= 0:
                    break
                out.append(_set_bound(q, "end", c_end, "raised"))
                q = by_id.get(q.get("parent_id"))
    rt = _root_text(n)
    if rt and rt.get("start") and rt.get("end") and (cmp(rt["start"], rt["end"]) or 0) > 0:
        out += _null_span(n, "child-outside-parent")
    return out


def repair(doc: dict, errors: list) -> list:
    """Repair the local errors among `errors` (validator Findings: .code, .where, .message) in `doc`, in
    place; returns the repair entries (module docstring). Non-local findings are ignored."""
    vo = outline_doc.load_validator()
    meta = doc.get("metadata") or {}
    by_id = {n["id"]: n for n in doc["nodes"]}
    file_rank = vo._file_rank(meta.get("work_files"))[0]

    def cmp(a, b):
        return vo.compare_refs(a, b, file_rank)

    repairs, groups_done = [], set()
    for f in errors:
        n = by_id.get(f.where)
        if f.code not in LOCAL_CODES or n is None:
            continue
        if f.code == "sibling-order":
            what = f.message.split(" ", 1)[0]  # the validator's '<what> <ref> comes before …'
            key = (n.get("parent_id"), _group_scheme(n, meta), what)
            if what not in ORDERED or key in groups_done:
                continue
            groups_done.add(key)
            siblings = [m for m in doc["nodes"]
                        if m.get("parent_id") == key[0] and _group_scheme(m, meta) == key[1]]
            repairs += _demote_out_of_order(siblings, what, cmp, vo.parse_ref)
        elif f.code == "child-outside-parent":
            repairs += _fit_into_parent(n, by_id, cmp)
        else:
            repairs += _null_span(n, "cbeta-order")
    return repairs
