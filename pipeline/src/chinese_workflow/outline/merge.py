"""chinese_workflow.outline.merge — merge the explicit sources into one draft tree
(docs/outliner-design.md §5.4).

Input : the tier-1 draft tree (tier1.build, optionally wrapped by scheme.apply_level1), whose
        chapter drafts carry the private key "_anchor" = the linehead of their cb:mulu line; and
        the tier-2 drafts grouped by anchor, {linehead | None: [drafts in document order]}, keyed
        by Tier1Result.anchors.
Output: (roots, report). Tier-2 drafts for anchor lh become children of the tier-1 draft whose
        _anchor == lh, searched through the whole tree (level-1 wrappers included). Drafts under
        None (text before the first chapter of the span) go before the first top-level draft.
        Unknown anchors are reported and their drafts are not attached (design §5.2 honesty rule:
        never silently attached). When several tier-1 drafts share an anchor (three 科判 mulu on
        G069n1977_p0717a01), the last in pre-order, the innermost, receives the drafts, and the
        case is reported.

Order of authority: tier 2 (inside a 品) > tier 1 > scheme prior; nothing here edits a tier-1 or
prior node (design §2.3: explicit nodes are immutable). Sibling order is document order of
`commentary.explained` (the validator's [sibling-order]): the new drafts are merged into the
target's existing children as two sorted runs, existing children first on equal lines ("after any
existing children"), so no existing child moves relative to another. Lines are ordered by (page,
register, line, offset) within one file, the validator's comparison; a draft with no comparable
line keeps its place after those that have one. A sibling pair still out of order is reported.

Inputs are not modified; the result is a deep copy. Deterministic.
"""

from __future__ import annotations

import copy

from ..common.lineheads import is_ref, parse


def _key(draft: dict):
    """(file, page, register, line, offset) of commentary.explained, or None."""
    ref = ((draft.get("locations") or {}).get("commentary") or {}).get("explained")
    if not is_ref(ref):
        return None
    r = parse(ref)
    return (r.file, r.page, r.register, r.line, r.offset or 0)


def _before(a, b) -> bool:
    """a strictly before b, when both are comparable (same file)."""
    return a is not None and b is not None and a[0] == b[0] and a[1:] < b[1:]


def _merge_sorted(existing: list, new: list) -> list:
    out, i, j = [], 0, 0
    while i < len(existing) and j < len(new):
        if _before(_key(new[j]), _key(existing[i])):
            out.append(new[j])
            j += 1
        else:
            out.append(existing[i])
            i += 1
    return out + existing[i:] + new[j:]


def _ref(k) -> str:
    return "%s_p%s%s%02d%s" % (k[0], k[1], k[2], k[3], ":%d" % k[4] if k[4] else "")


def _order_problems(siblings: list, where) -> list:
    problems, last = [], None
    for d in siblings:
        k = _key(d)
        if k is None:
            continue
        if last is not None and _before(k, last):
            problems.append({"kind": "sibling-order", "anchor": where,
                             "detail": "%s explained before its elder sibling's %s"
                                       % (_ref(k), _ref(last))})
        last = k
    return problems


def _walk(drafts: list):
    for d in drafts:
        yield d
        yield from _walk(d.get("children") or [])


def attach(tier1_drafts: list, tier2_by_anchor: dict, *, anchor_ends: dict | None = None,
           line_index: dict | None = None) -> tuple:
    """Attach tier-2 drafts under their tier-1 anchors (module docstring). Returns
    (roots, report).

    anchor_ends ({anchor linehead: last line of the unit, inclusive}, from tier 1's pins) and
    line_index ({linehead: document position}) are optional: with both, a tier-2 draft explained after
    its anchor's unit ends is not the unit's (e.g. a treatise body after the translator's preface,
    CBETA 序 mulu of T32n1666) and goes to the top level, in document order."""
    roots = copy.deepcopy(tier1_drafts)
    report: list = []
    if anchor_ends and line_index:
        tier2_by_anchor = {a: list(ds) for a, ds in tier2_by_anchor.items()}
        spill = []
        for anchor, drafts in list(tier2_by_anchor.items()):
            end = anchor_ends.get(anchor) if anchor is not None else None
            if end is None or end not in line_index:
                continue
            keep = []
            for d in drafts:
                k = _key(d)
                lh = "%s_p%s%s%02d" % k[:4] if k else None
                if lh in line_index and line_index[lh] > line_index[end]:
                    spill.append(d)
                else:
                    keep.append(d)
            tier2_by_anchor[anchor] = keep
        if spill:
            report.append({"kind": "after-anchor-end", "drafts": len(spill),
                           "detail": "tier-2 drafts explained after their anchor's unit ends; "
                                     "moved to the top level"})
            tier2_by_anchor[None] = list(tier2_by_anchor.get(None) or []) + spill
    targets: dict = {}
    for d in _walk(roots):
        if d.get("_anchor") is not None:
            targets.setdefault(d["_anchor"], []).append(d)
    for anchor, drafts in tier2_by_anchor.items():
        if not drafts or anchor is None:
            continue
        new = copy.deepcopy(list(drafts))
        hits = targets.get(anchor)
        if not hits:
            report.append({"kind": "unknown-anchor", "anchor": anchor, "drafts": len(new),
                           "detail": "no tier-1 draft has this anchor; drafts not attached"})
            continue
        if len(hits) > 1:
            report.append({"kind": "ambiguous-anchor", "anchor": anchor, "targets": len(hits),
                           "detail": "attached to the innermost (last in pre-order) of the "
                                     "drafts sharing the line"})
        target = hits[-1]
        target["children"] = _merge_sorted(target.get("children") or [], new)
        report.extend(_order_problems(target["children"], anchor))
    lead = copy.deepcopy(list(tier2_by_anchor.get(None) or []))
    if lead:
        roots = _merge_sorted(lead, roots)  # ties: text before the first anchor stays first
        report.extend(_order_problems(roots, None))
    return roots, report
