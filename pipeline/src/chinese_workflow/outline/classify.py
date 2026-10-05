"""chinese_workflow.outline.classify — deterministic classification of merged, anchored nodes before the
resolver runs (docs/outliner-design.md §5.5 (c); E06 review §1 item 6, §2 B2).

mark_out_of_span(doc, *, root_pins, order) -> (doc', report)                                 sūtra mode
    Input : a numbered zh-kepan outline after outline.anchor.resolve_root_spans and the before-resolver
            repair pass (a repair that nulls or clips a span changes what is a candidate); the root text's
            tier-1 pins (tier1.build(root, mode="sutra", role="root").pins; only type 品 is used) and the
            root file's line order (ingest.text.InputText.order).
    Output: a deep copy in which every sūtra-span node flagged `unmapped` whose announcement names an
            extent that cannot lie inside the root span of its nearest spanned ancestor carries the note
            OUT_OF_SPAN_NOTE % detail, and a report [{kind: "out-of-span", node_id, heading_src, detail}].
            The flag `unmapped` stays: the node has no root span in this build (validator rule
            [sutra-span-unmapped]); the schema's flags enum is closed and this is the reason, not a new
            locator state. outline.resolver skips such nodes (_jobs_root_spans) with the same kind.

    Wording read: extent_announced, locations.commentary.raw, heading_src. Only wording that announces an
    extent counts; a mere mention of a 品 (如〈…品〉說, 《維摩經》〈…品〉, 第二品, 上中下三品) does not. A node is
    out of span when
      (a) it names a 品 count N (N + ½ for 半) larger than the number of root 品 whose span overlaps the
          ancestor's span (Zhiyi 凡十五品半 / 凡十一品半 read inside 序品, T34n1718_p0002a08-a09). The count
          needs 凡 before it, 從/自 before it, or 半 / 訖 / 至 / 下 / 已來 after it, and no 第 before;
      (b) it names a 品 in 〈…〉 that tier1.find_pin resolves to a root 品 outside those (〈…〉 right after
          從/自/至/訖/盡, 經 allowed between, or right before 訖/至/下/已來, not after 》 or 如: 〈方便品〉,
          〈分別功德〉, 〈安樂行〉, and 〈踊出〉, which matches the root's 15th 品 by overlap; p0002a07-a11);
      (c) it runs to the end of the sūtra (訖經 / 盡經) while the ancestor's span does not overlap the
          last 品 (從偈後盡經, p0002a08-a09);
      (d) it is a division with >= 2 sūtra-span children all of which are out of span (又一時分為二, p0002a09).
    A node under no spanned ancestor is never marked: there the whole sūtra is admissible. Nothing else
    changes; explicit nodes keep heading, locators, class and level (assert_explicit_unchanged holds).
    A node that already carries the note is skipped, so marking twice marks once. Checked on the saved E06
    dev outlines: exactly the four item nodes of tier2-T1718-dev match (a)-(c) and no node of
    tier2-T1723-dev does.

Deterministic; imports chinese_workflow.common, .tier1 (pin matching) and .tier2.formulae.parse_num.
"""

from __future__ import annotations

import copy
import re

from ..common.lineheads import strip_offset
from ..common.outline_doc import children_map
from .tier1 import CHAPTER_TYPE, find_pin, pin_name
from .tier2.formulae import parse_num

OUT_OF_SPAN_PREFIX = "out-of-span: "
OUT_OF_SPAN_NOTE = OUT_OF_SPAN_PREFIX + "extent names 品 beyond this 品: %s"
PLACEHOLDER = "〓"  # stands for a removed 〈…〉 so the text around it does not run together
# a 品 count: a run of numerals not part of a longer one and not an ordinal (第二品); it announces an extent
# when 凡 / 從 / 自 stands before it or 半 / 訖 / 至 / 下 / 已來 follows (上中下三品, 九品 do neither)
COUNT_RE = re.compile(r"(?<![第一二三四五六七八九十])([一二三四五六七八九十]+)品(半)?")
COUNT_BEFORE = ("凡", "從", "自")
COUNT_AFTER = ("訖", "至", "下", "已來")
# a 〈…〉 announces an extent after 從/自/至/訖/盡 (經 may stand between: 從經〈…〉) or before 訖/至/下/已來;
# one right after 》 is a chapter of another text, one after 如 a cross-reference (如〈方便品〉下說)
PIN_NAME_RES = (
    re.compile(r"(?:從|自|至|訖|盡)經?〈([^〈〉]+)〉"),
    re.compile(r"(?<![》如])〈([^〈〉]+)〉(?=訖|至|下|已來)"),
)
PIN_NAME_RE = re.compile(r"〈[^〈〉]*〉")
TO_END_RE = re.compile(r"(?:訖|盡)經(?!文)")


def is_out_of_span(node: dict) -> bool:
    """Has mark_out_of_span marked this node?"""
    return any(isinstance(s, str) and s.startswith(OUT_OF_SPAN_PREFIX) for s in node.get("notes") or [])


def _wording(n: dict) -> str:
    com = (n.get("locations") or {}).get("commentary")
    raw = com.get("raw") if isinstance(com, dict) else None
    return "｜".join(s for s in (n.get("extent_announced"), raw, n.get("heading_src")) if s)


def _span(n: dict):
    rt = (n.get("locations") or {}).get("root_text") or {}
    if rt.get("start") and rt.get("end"):
        return strip_offset(rt["start"]), strip_offset(rt["end"])
    return None


def _overlapping(span: tuple, chapters: list, order) -> list:
    """Indexes of the 品 pins whose span overlaps [start, end] (both in the root file's line order)."""
    s, e = order.index(span[0]), order.index(span[1])
    return [i for i, p in enumerate(chapters)
            if p.start in order and p.end in order
            and order.index(p.start) <= e and order.index(p.end) >= s]


def _named_extents(text: str) -> list:
    """The 〈…〉 names in extent wording, in text order."""
    found = {m.start(1): m.group(1) for rx in PIN_NAME_RES for m in rx.finditer(text)}
    return [found[i] for i in sorted(found)]


def _counts(text: str):
    """The 品 counts that announce an extent (COUNT_RE with a before / after context), in text order, as
    (the wording with a 凡 / 從 / 自 before it, the numerals, 半 or None)."""
    masked = PIN_NAME_RE.sub(PLACEHOLDER, text)
    for m in COUNT_RE.finditer(masked):
        before = masked[max(0, m.start() - 1):m.start()]
        if before in COUNT_BEFORE or m.group(2) or masked[m.end():].startswith(COUNT_AFTER):
            yield (before if before in COUNT_BEFORE else "") + m.group(0), m.group(1), m.group(2)


def _beyond(text: str, covered: list, chapters: list) -> str | None:
    """Why the extent `text` names cannot lie inside the 品 `covered` (indexes into chapters); None when
    nothing in it points beyond them."""
    for name in _named_extents(text):
        i, how = find_pin(pin_name(name), chapters)
        if i is not None and i not in covered:
            return "〈%s〉 is %s (%s), outside" % (name, chapters[i].heading, how)
    for shown, digits, half in _counts(text):
        n = parse_num(digits)
        if n is not None:
            n = n + (0.5 if half else 0)
            if n > len(covered):
                return "%s names %g 品 and the ancestor's span holds %d" % (shown, n, len(covered))
    end = TO_END_RE.search(text)
    if end and chapters and (len(chapters) - 1) not in covered:
        return "%s runs to the end of the sūtra" % end.group(0)
    return None


def mark_out_of_span(doc: dict, *, root_pins: list, order) -> tuple[dict, list]:
    """Mark the unmapped sūtra-span nodes whose announced extent lies beyond their 品 (module
    docstring). Returns (a deep copy of doc, the report list)."""
    out = copy.deepcopy(doc)
    report: list = []
    if (out.get("metadata") or {}).get("outline_mode") != "sutra":
        return out, report
    chapters = [p for p in root_pins if p.part_type == CHAPTER_TYPE]
    nodes = out["nodes"]
    by_id = {n["id"]: n for n in nodes}
    kids = children_map(nodes)

    def candidate(n: dict) -> bool:
        return (n.get("node_class") == "sutra-span" and "unmapped" in (n.get("flags") or [])
                and _span(n) is None)

    def spanned_ancestor(n: dict):
        p = n.get("parent_id")
        while p is not None:
            sp = _span(by_id[p])
            if sp is not None:
                return by_id[p], sp
            p = by_id[p].get("parent_id")
        return None, None

    def mark(n: dict, detail: str) -> None:
        n["notes"] = list(n.get("notes") or []) + [OUT_OF_SPAN_NOTE % detail]
        report.append({"kind": "out-of-span", "node_id": n["id"],
                       "heading_src": n.get("heading_src", ""), "detail": detail})

    for n in nodes:  # (a)-(c): the node's own wording against its nearest spanned ancestor
        if not candidate(n) or is_out_of_span(n):
            continue
        anc, sp = spanned_ancestor(n)
        if sp is None or sp[0] not in order or sp[1] not in order:
            continue
        why = _beyond(_wording(n), _overlapping(sp, chapters, order), chapters)
        if why:
            mark(n, "%s; under %s 「%s」 %s..%s" % (why, anc["id"], anc.get("heading_src", ""), sp[0], sp[1]))
    for n in reversed(nodes):  # (d): a division whose parts all lie beyond the 品, innermost first
        if not candidate(n) or is_out_of_span(n):
            continue
        parts = [c for c in kids.get(n["id"], []) if c.get("node_class") == "sutra-span"]
        if len(parts) >= 2 and all(is_out_of_span(c) for c in parts):
            mark(n, "all %d parts of the division lie beyond this 品" % len(parts))
    return out, report
