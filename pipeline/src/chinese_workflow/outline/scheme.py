"""chinese_workflow.outline.scheme — the scheme prior: level-1 parts declared by the project
(docs/outliner-design.md §5.3; decision 5 of §14).

A sūtra's top level is the commentator's *scheme*, stated once (usually at the start of the
commentary) and then presupposed. A run over a span that does not contain the statement (a dev-span
run over T34n1723 陀羅尼品) cannot read it, so the project declares it, and this module builds the
level-1 parts around the tier-1 品 drafts.

Input : the tier-1 品 drafts of a commentary in sūtra mode, aligned to the root text
        (tier1.align_pins); `level1` = the project's `[[scheme.level1]]` entries
        {"heading_src", "from_pin", "to_pin", "source"}, e.g. Kuiji's first scheme (R03 F22;
        NEXT_STEPS decision (a)): 序分 = 序品; 正宗 = 方便品–授學無學人記品;
        流通 = 法師品–普賢菩薩勸發品; `root_pins` = the root text's tier-1 pins
        (tier1.build(root, mode="sutra", role="root").pins); optionally `commentary_pins` = the
        commentary's own tier-1 pins (whole file, structure only).
Output: (top-level drafts, report). Each entry that covers at least one draft becomes a level-1
        draft wrapping those drafts, in their order:
          origin "editorial" (the run did not read the statement), evidence = the entry's source,
          node_class "sutra-span", part_type None;
          commentary {announced: None, explained: the line where the part's first 品 (from_pin)
          begins in the commentary}, the Kuiji gold's convention for its level-1 parts (流通 =
          法師品's T34n1723_p0806c24): taken from `commentary_pins` (matched by name), which a
          span run needs, since its drafts start later (陀羅尼品); without commentary pins, or
          when from_pin has none, the explained line of the first wrapped draft;
          root_text {start: from_pin's start, end: to_pin's end, basis "chapter"}: the whole
          declared range, also when the run holds part of it (the gold's 流通 spans 法師品 to
          普賢菩薩勸發品 whatever the run covers);
          private key "_scheme_prior" = the entry, so the orchestrator can drop the prior when tier
          2 reads the statement itself (design §5.3: metadata.scheme_prior "superseded").
        Drafts inside no range stay top-level, in place, and are reported; an entry whose pins are
        not found, or that covers no draft, is reported and builds nothing.

Membership: a draft's place in the root is the root pin whose start equals its root_text.start
(set by align_pins), else the pin its name matches (tier1.find_pin); a range is [from_pin, to_pin]
in root-pin document order (T09n0262's 附文 falls inside 流通 and wraps nothing). The first range
that contains the draft wins.

Provenance: R03 F22 (Kuiji's 今為二解: two top-level schemes); docs/outliner-design.md §5.3.
Deterministic; imports only chinese_workflow.outline.tier1.
"""

from __future__ import annotations

import copy

from .tier1 import CHAPTER_TYPE, find_pin, pin_name


def _pin_index(draft: dict, root_pins: list) -> int | None:
    """The root pin a top-level draft stands for: by its aligned root span, else by name — but only
    for chapter drafts (tier 1's 品 nodes). A tier-2 draft at the top level (text before the first
    品, or after its unit's end) is never matched by a fuzzy name (review of 2026-09-27: 「初明方便之意」
    would otherwise match 方便品)."""
    rt = (draft.get("locations") or {}).get("root_text") or {}
    if rt.get("start"):
        for i, p in enumerate(root_pins):
            if p.start == rt["start"]:
                return i
    if draft.get("_anchor") is None or draft.get("part_type") != CHAPTER_TYPE:
        return None
    i, _ = find_pin(pin_name(draft.get("heading_src", "")), root_pins)
    return i


def _explained(draft: dict):
    return ((draft.get("locations") or {}).get("commentary") or {}).get("explained")


def _resolve(level1: list, root_pins: list, report: list) -> list:
    """[(entry, i_from, i_to)] of the entries whose pins are found, in the given order."""
    ranges = []
    for entry in level1:
        i_from, how_from = find_pin(pin_name(entry.get("from_pin", "")), root_pins)
        i_to, how_to = find_pin(pin_name(entry.get("to_pin", "")), root_pins)
        if i_from is None or i_to is None or i_from > i_to:
            report.append({"kind": "unresolved-range", "heading_src": entry.get("heading_src"),
                           "from_pin": entry.get("from_pin"), "to_pin": entry.get("to_pin"),
                           "detail": "pin not in the root text, or the range runs backwards"})
            continue
        for label, how in (("from_pin", how_from), ("to_pin", how_to)):
            if how != "exact":
                report.append({"kind": "fuzzy-pin", "heading_src": entry.get("heading_src"),
                               label: entry.get(label), "detail": how})
        ranges.append((entry, i_from, i_to))
    return ranges


def _part_start(entry: dict, commentary_pins: list | None, kids: list):
    """The commentary line where the part's first 品 begins (module docstring)."""
    if commentary_pins:
        chapters = [p for p in commentary_pins if p.part_type == CHAPTER_TYPE] or commentary_pins
        i, _ = find_pin(pin_name(entry.get("from_pin", "")), chapters)
        if i is not None:
            return chapters[i].start
    return _explained(kids[0])


def _wrapper(entry: dict, start: str, end: str, kids: list, explained) -> dict:
    return {
        "heading_src": entry["heading_src"],
        "part_type": None,
        "origin": "editorial",
        "evidence": entry.get("source") or "project scheme prior",
        "node_class": "sutra-span",
        "flags": [],
        "notes": ["scheme prior: level-1 part declared by the project (%s..%s), not read from "
                  "the commentary in this run" % (entry.get("from_pin"), entry.get("to_pin"))],
        "locations": {
            "scheme": "cbeta-kepan",
            "commentary": {"announced": None, "explained": explained},
            "root_text": {"start": start, "end": end, "basis": "chapter", "end_basis": None},
        },
        "_scheme_prior": dict(entry),
        "children": kids,
    }


def apply_level1(pin_drafts: list, level1: list, *, root_pins: list,
                 commentary_pins: list | None = None) -> tuple:
    """Wrap the 品 drafts in the project's level-1 parts (module docstring). Returns
    (drafts, report); the input drafts are not modified."""
    report: list = []
    ranges = _resolve(level1, root_pins, report)
    groups: dict = {}  # range index -> [drafts]
    order: list = []  # drafts, and range indexes where a wrapper goes, input order
    for d in copy.deepcopy(pin_drafts):
        i = _pin_index(d, root_pins)
        k = next((k for k, (_, a, b) in enumerate(ranges) if i is not None and a <= i <= b),
                 None)
        if k is None:
            order.append(d)
            report.append({"kind": "outside-every-range", "heading_src": d.get("heading_src"),
                           "explained": _explained(d),
                           "detail": "no root pin" if i is None
                           else "root pin %s" % root_pins[i].heading})
            continue
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(d)

    result = []
    for item in order:
        if isinstance(item, int):
            entry, i_from, i_to = ranges[item]
            kids = groups[item]
            item = _wrapper(entry, root_pins[i_from].start, root_pins[i_to].end, kids,
                            _part_start(entry, commentary_pins, kids))
        result.append(item)
    for k, (entry, _, _) in enumerate(ranges):
        if k not in groups:
            report.append({"kind": "empty-range", "heading_src": entry.get("heading_src"),
                           "from_pin": entry.get("from_pin"), "to_pin": entry.get("to_pin"),
                           "detail": "no 品 draft of this run falls in the range; no node built"})
    placed = [item for item in order if isinstance(item, int)]
    if placed != sorted(placed):
        report.append({"kind": "range-order",
                       "detail": "level-1 ranges are not in the document order of their 品 "
                                 "drafts: %s" % placed})
    return result, report
