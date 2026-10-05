"""chinese_workflow.eval.gold.sdp_check — automated heading check of the sdp T1718 gold against
T34n1718 (Task 3).

Input : data/raw/dila-sdp/gold/T1718.zhiyi-wenju-sdp.outline.json (Task 2's commentary gold; read
        only, never modified) and data/raw/cbeta/T34n1718.xml (chinese_workflow.ingest.lines).
Output: data/raw/dila-sdp/gold/heading-check.tsv (one row per node) and HEADING-CHECK.md (counts),
        both under the sdp eval-only directory (plan Global Constraint 1); nothing is written to the
        gold JSON, to sdp.py, or to any committed path except this module and its test. Neither of
        those two committed files ever holds sdp heading text (fix round 2, controller decision):
        only node ids, F23's classes and group numbers, and CBETA lineheads; a real heading, when
        one is illustrated in a comment or docstring, is referenced by its node id and read from the
        live gold at run time instead of being quoted — checked by
        tests/unit/test_sdp_eval_only_guard.py (skips when the gold is absent).

Question this answers: sdp's T1718 node headings are sometimes Zhiyi's own words, sometimes
paraphrase, sometimes an sdp editorial label. For every node of the T1718 gold, does the heading
(sdp's ordinal and count-suffix stripped) actually occur in Zhiyi's text near where the node is
anchored?

Classes
-------
verbatim  the stripped heading occurs punctuation-insensitively, as a contiguous substring within
          one merged range of the node's window (below) — never spanning two ranges that are not
          textually adjacent (RANGE_SEPARATOR).
partial   not verbatim, but at least 60% of the stripped heading's characters occur, in order (as a
          subsequence, not necessarily contiguous, and free to bridge separator-joined ranges — a
          known source of permissiveness on short headings; see HEADING-CHECK.md's noise baseline),
          inside the window: len(LCS(heading, window)) / len(heading) >= 0.6. This ratio is
          generous for short headings: a 2-character heading needs only 2/2 characters found in
          order anywhere in a (possibly wide) window to pass, a 3-character heading only 2/3.
absent    neither.
no-text   the node has no window at all (below) — reported and counted separately, never folded
          into "absent": a node in this class was never searched.

Heading normalisation (resolution, exact regexes)
--------------------------------------------------
Applied in order, each step skipped if it would leave the heading empty:
 1. sdp's leading ordinal, via sdp.strip_ordinal (sdp.ORDINAL_RE = ^([0-9]+(-[0-9]+)?)\\s): "1-5 "
    or "2 " at the start.
 2. A heading that is entirely wrapped in 【…】 (a defensive case; sdp.py's own head_title split
    normally strips these already, so this fires only on tree-text-derived headings that still
    carry them) has the brackets removed.
 3. TRAILING_PAREN_RE, repeated while it matches: a trailing parenthetical that opens with a digit,
    half- or full-width, or with 分 + a digit or CJK numeral — "(分2)", "（分二）", "（2-10品）",
    "(2品末-10品)" — covers the plan's (Task 3) "(分N)" and "（N-M品）" examples, sdp's "N品末-M品"
    variant,
    and both forms of "(分N)" (fix round 2: the digit form was not actually matched before this
    round; test_strip_trailing_paren_digit_fen_count pins it now).
 4. TRAILING_COUNT_RE, applied once, **only when its value equals one of the caller's
    expected_counts** (fix round 1: a trailing numeral is often the heading's own substance, not a
    count tag — a node's own child count in the gold, not the numeral, decides whether it is a count
    tag at all; check_nodes passes each node's actual child count and, when set,
    child_count_announced; normalize_heading's own default, expected_counts=(), never strips):
    a trailing run of 1-3 bare CJK numerals 一-十 (not 百/千/萬/〇, so a numeral that is substantive
    content, e.g. in a chapter title, is never even considered) or bare ASCII digits — sdp's habit
    of appending a disambiguating count after the phrase itself when the count matches (the "上問"
    remainder before a stripped count is not further stripped: only the outermost count token is
    ever considered). Fix round 2: sdp also uses a trailing single digit as a bare *ordinal*
    disambiguator between same-named sibling sections (e.g. a node named "X一" next to a sibling "X
    二") — this rule leaves such a digit alone whenever it does not equal that node's own child
    count, which is usually the case for an ordinal (see HEADING-CHECK.md's note on this for a real
    example over the checked data).
The result is matched punctuation-insensitively (chinese_workflow.ingest.lines.strip_punct on both
sides), never on the raw heading.

Window (resolution, exact rule; fix round 1 widened both bounds below — see HEADING-CHECK.md's
before/after)
-------------------------------------------------------------------------------------------------
Every node with locations.commentary.explained set is a *window owner*. Preorder = the gold's own
node order (pre-order by construction, common.number_tree). For a window owner N:
  - its own span ("own_end" in compute_windows) runs from its explained line to the line before the
    explained line of the next node in preorder that itself has a non-null explained line (skipping
    intervening null-explained nodes, whether N's own descendants or not, and never jumping outside
    N's own subtree by design), but is never narrower than MIN_OWN_LINES = 3 lines (fix round 1: a
    parent and its first-explained child commonly share one sdp anchor — the review that produced
    this fix round found sdp's own formula for a node routinely sits one or two lines after that
    shared anchor (e.g. T1718D03_006's own line, T34n1718_p0030b13, is one line before the line that
    names its child T1718D04_012; the heading is not quoted here, Global Constraint 1). This is
    capped so it never runs past "the parent's span end": not
    the direct parent's own (possibly equally narrow) span, but the *subtree* bound of the nearest
    explained ancestor of N — how far that ancestor's entire subtree extends before the first
    non-descendant, non-null-explained node (found via subtree size, skipping the whole subtree, not
    just the next node); subtree_bound[N] itself, not an ancestor's, is what actually bounds the
    MIN_OWN_LINES widening (see test_cap_uses_subtree_bound_not_narrow_own_span, still guarding the
    fix round 0 bug this rule replaced).
  - PLUS, if N has a direct parent, the parent's own *announcing lines*: the parent's explained line
    plus its next ANNOUNCING_LINES - 1 = 2 lines, capped by the parent's own *subtree* bound (fix
    round 1: not by the parent's own narrow span, which is exactly the quantity MIN_OWN_LINES above
    exists to correct — capping the bonus by it would reintroduce the same bug one level removed;
    "the parent's first 3 lines uncapped by the parent's own span" is the controller's phrase for
    this) — added as a second range. This is what lets a child's heading be found in the parent's
    single enumerating sentence ("文為二：一...，二...") even when the child's own explained line
    only carries its later elaboration, and is not itself widened by MIN_OWN_LINES (it is always
    exactly ANNOUNCING_LINES lines, never fewer, since it does not inherit N's own narrow-window
    problem).
  - The two (or more, for an inherited node — below) ranges of a window are merged when overlapping
    or textually adjacent (so a term split across a CBETA line break inside one genuinely contiguous
    span still joins into one contiguous string) and otherwise joined with RANGE_SEPARATOR, a
    private-use character that survives punctuation-stripping on both sides of a match: two ranges
    that are not adjacent in the file can never contribute to one "verbatim" (contiguous-substring)
    match (fix round 1; merge_ranges, window_text). The "partial" (LCS) check is a subsequence match
    and is not stopped by the separator — seen above.
A node whose own locations.commentary.explained is null is not a window owner: it is classified
using its parent's window unchanged (the parent's own window if the parent is an owner, else the
window the parent itself inherited, recursively up the tree) — never its own span, and never a
fresh search of the whole file. A node with no window at all (no ancestor, including itself, has a
non-null explained line) is class no-text.

Every window can still reach into another node's textual territory (e.g. because a long run of
intervening nodes are all null, so the nearest bound is far away, or because MIN_OWN_LINES/the
announcing bonus deliberately widen a window past its single anchor line) — a known, accepted source
of "partial" (and occasionally "verbatim") matches that are not really about the node they are
reported against; see HEADING-CHECK.md's noise baseline (a random other node's heading, matched
against the same windows) for how much of the real rate this could explain; data/EVAL-SETS.md
gives the aggregate counts.

Depth bands and 卷-half
------------------------
depth_band(level): "1-3", "4-6", "7-9", "10-12", "13+" (arbitrary but fixed groupings of the gold's
node levels 1-19; stated here so the report is reproducible).
juan-half/split: only reported for window_kind "own" — an inherited node's *own* location is
unknown (its explained line is null; the window searched is its ancestor's, not this node's place in
the text), so check_nodes never attributes it to that ancestor's 卷-half or split, and reporting
functions bucket it as "(inherited — location unknown)" instead (fix round 1, controller decision).
juan-half itself: T1718's own cb:mulu(type="卷") entries ("1a" .. "10b"), taken from the line an
"own" node's own explained anchor falls on (chinese_workflow.ingest.lines mulu records).

Splits: the fixed dev/validation/test T1718 spans of plan Global Constraint 5, compared by line
position in the file's own line order (inclusive start, exclusive end); an "own" node is attributed
to the split its own explained line falls in.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from chinese_workflow.eval.gold import common
from chinese_workflow.eval.gold.sdp import strip_ordinal
from chinese_workflow.ingest.lines import extract, strip_punct

PARTIAL_THRESHOLD = 0.6
ANNOUNCING_LINES = 3  # the parent's own first N lines, added to a window (resolution)
MIN_OWN_LINES = 3  # a node's own span is never narrower than this (fix round 1)
# Joins two ranges that are not textually adjacent so a "verbatim" (contiguous-substring) match can
# never bridge them; a private-use character, never CBETA text and not stripped by strip_punct
# (Unicode category Co, outside is_punct's P*/Z*/Cc/Cf), so it survives into the punctuation-
# stripped text on both the needle and haystack side. The LCS ("partial") check still bridges
# ranges, since a subsequence match never requires contiguity — see HEADING-CHECK.md's noise
# baseline for how permissive that leaves "partial" on short headings.
RANGE_SEPARATOR = ""

# ---- heading normalisation -------------------------------------------------------------------

_WRAPPED_RE = re.compile(r"\A【(.+)】\Z")
# opens with a digit ("（2-10品）", "(2品末-10品)") or with 分 + a digit or CJK numeral(s), covering
# both "(分2)" and "（分二）" (fix round 2: the digit form was not actually covered before — the
# first branch requires the digit to follow the paren directly, not after 分).
TRAILING_PAREN_RE = re.compile(r"[(（](?:[0-9]|分[0-9一二三四五六七八九十]+)[^()（）]*[)）]\s*\Z")
TRAILING_COUNT_RE = re.compile(r"(?:[一二三四五六七八九十]{1,3}|[0-9]+)\Z")
_CJK_DIGIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _parse_count(token: str) -> int | None:
    """A TRAILING_COUNT_RE match -> its integer value, or None if it is not a well-formed count
    (CJK forms up to 2 digits' worth of magnitude, matching the regex's {1,3}-char cap: a bare
    digit, a bare CJK digit 一-九, 十 alone (10), 十 + digit (11-19), digit + 十 (20/30/.../90),
    digit + 十 + digit)."""
    if token.isdigit():
        return int(token)
    if token in _CJK_DIGIT:
        return _CJK_DIGIT[token]
    if token == "十":
        return 10
    if len(token) == 2:
        if token[0] == "十" and token[1] in _CJK_DIGIT:
            return 10 + _CJK_DIGIT[token[1]]
        if token[1] == "十" and token[0] in _CJK_DIGIT:
            return _CJK_DIGIT[token[0]] * 10
        return None
    if len(token) == 3 and token[1] == "十" and token[0] in _CJK_DIGIT and token[2] in _CJK_DIGIT:
        return _CJK_DIGIT[token[0]] * 10 + _CJK_DIGIT[token[2]]
    return None


# T1718 splits (plan Global Constraint 5; inclusive start, exclusive end). Sourced verbatim, never
# typed from memory of the corpus, only of this file.
SPLITS = [
    ("dev", "T34n1718_p0001b18", "T34n1718_p0016b02"),
    ("validation", "T34n1718_p0016b02", "T34n1718_p0036a26"),
    ("test", "T34n1718_p0036a26", "T34n1718_p0063b11"),
]


def normalize_heading(heading_src: str, expected_counts=()) -> str:
    """heading_src (as imported, sdp's leading ordinal and 【】 wrapper included) -> the text to
    match against Zhiyi's wording (module docstring, exact regexes). expected_counts: the node's
    actual child count and/or child_count_announced (fix round 1) — a trailing bare numeral is a
    "count suffix" and stripped only when its value is one of these; otherwise it is kept, because a
    trailing numeral is often the heading's own substance, not sdp's count tag, or a bare ordinal
    disambiguating two same-named siblings (T1718D05_012 is a fixed four-character Tiantai term
    ending in a numeral, with no reason to have exactly that many children; see HEADING-CHECK.md's
    note on this, over the real checked data, for a worked example). Passing () (the default) never
    strips, matching a caller with no count information to check against."""
    h = strip_ordinal(heading_src or "").strip()
    if not h:
        return h
    m = _WRAPPED_RE.match(h)
    if m and m.group(1).strip():
        h = m.group(1).strip()
    while True:
        m = TRAILING_PAREN_RE.search(h)
        if not m or not h[: m.start()].strip():
            break
        h = h[: m.start()].strip()
    m = TRAILING_COUNT_RE.search(h)
    if m and h[: m.start()].strip():
        value = _parse_count(m.group(0))
        if value is not None and value in expected_counts:
            h = h[: m.start()].strip()
    return h


# ---- text matching ---------------------------------------------------------------------------


def _lcs_len(a: str, b: str) -> int:
    """Length of the longest common SUBSEQUENCE of a and b (not necessarily contiguous), same
    algorithm as sdp.py's private _lcs (module docstring: "at least 60% ... in order")."""
    prev = [0] * (len(b) + 1)
    for ch in a:
        cur = [0]
        for j, bj in enumerate(b):
            cur.append(prev[j] + 1 if ch == bj else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def classify_text(needle: str, hay: str) -> tuple:
    """(class, ratio): needle/hay are raw (not yet punctuation-stripped) strings; class is one of
    verbatim/partial/absent. ratio is the LCS ratio (None for verbatim, since it is always 1.0 by
    construction of "contains")."""
    n = strip_punct(needle)
    h = strip_punct(hay)
    if not n:
        return "absent", None
    if n in h:
        return "verbatim", None
    ratio = _lcs_len(n, h) / len(n)
    return ("partial" if ratio >= PARTIAL_THRESHOLD else "absent"), ratio


# ---- windows ---------------------------------------------------------------------------------


@dataclass
class Window:
    owner: str | None  # node id whose span this is (None: no-text)
    kind: str  # "own" | "inherited" | "no-text"
    ranges: list = field(default_factory=list)  # [(start_pos, end_pos)] inclusive, line positions


def _explained(node: dict) -> str | None:
    return node.get("locations", {}).get("commentary", {}).get("explained")


def compute_windows(nodes: list, line_pos: dict, last_pos: int) -> dict:
    """nodes: the gold's nodes in preorder (id, parent_id, locations.commentary.explained; extra
    keys ignored, so a test can pass minimal dicts). line_pos: {linehead: position in the file's own
    line order}. last_pos: that order's last index. Returns {node id: Window} (module docstring).

    Two bounds per window-owning node N, both walking forward in preorder and skipping
    null-explained nodes (never opening a fresh search of the whole file):
      - own_end[N]: N's own span, ending at the line before the very next node in preorder (child,
        sibling or beyond) that has a non-null explained line, but never shorter than MIN_OWN_LINES
        (fix round 1: a parent and its first-explained child sharing one anchor — the common sdp
        layout — used to collapse N's own span to that single shared line, hiding a formula Zhiyi
        states on the next line or two — T1718D03_006 above is a real example, by linehead) —
        capped so it never runs past subtree_bound[N]
        itself (below), and never past
        subtree_bound of the nearest explained ancestor of N when that is smaller ("the parent's
        span end" of the resolution).
      - subtree_bound[N]: how far N's own subtree's territory extends — the line before the first
        non-null-explained node that is NOT one of N's descendants (found via subtree size, so it
        skips the whole subtree at once, not just N). This, not own_end, is the correct quantity to
        cap a *descendant's* own_end with: own_end can be as narrow as one line for a node with an
        explained child, and capping a later child's own_end by it (rather than by the ancestor's
        much wider subtree_bound) would wrongly truncate that child's window before it starts
        (checked by test_cap_uses_subtree_bound_not_narrow_own_span). subtree_bound[N] <=
        subtree_bound of any ancestor of N, since N's subtree is nested inside it, so raising
        own_end[N]'s floor to MIN_OWN_LINES capped by subtree_bound[N] (rather than by the tighter
        ancestor-derived cap already baked into the un-widened own_end) is always safe."""
    ids = [n["id"] for n in nodes]
    index = {nid: i for i, nid in enumerate(ids)}
    parent_of = {n["id"]: n.get("parent_id") for n in nodes}
    explained = {n["id"]: _explained(n) for n in nodes}
    children: dict = {nid: [] for nid in ids}
    for n in nodes:
        pid = n.get("parent_id")
        if pid is not None and pid in children:
            children[pid].append(n["id"])
    size: dict = {}
    for nid in reversed(ids):
        size[nid] = 1 + sum(size[c] for c in children[nid])

    # nearest explained ancestor of each node, self included when the node is itself explained
    # (preorder guarantees a parent is resolved before its children reach this loop).
    owner: dict = {}
    for nid in ids:
        pid = parent_of[nid]
        owner[nid] = (
            nid if explained[nid] is not None else (owner.get(pid) if pid is not None else None)
        )

    def first_explained_at_or_after(start_index: int) -> str | None:
        for later_id in ids[start_index:]:
            if explained[later_id] is not None:
                return later_id
        return None

    subtree_bound: dict = {}
    own_end: dict = {}
    for nid in ids:
        if explained[nid] is None:
            continue
        nxt = first_explained_at_or_after(index[nid] + size[nid])
        subtree_bound[nid] = (line_pos[explained[nxt]] - 1) if nxt is not None else last_pos
    for nid in ids:
        if explained[nid] is None:
            continue
        start_p = line_pos[explained[nid]]
        nxt = first_explained_at_or_after(index[nid] + 1)
        raw_end = (line_pos[explained[nxt]] - 1) if nxt is not None else last_pos
        pid = parent_of[nid]
        ancestor = owner.get(pid) if pid is not None else None
        if ancestor is not None:
            raw_end = min(raw_end, subtree_bound[ancestor])
        raw_end = max(raw_end, start_p)
        # widen to at least MIN_OWN_LINES, never past this node's own subtree bound (fix round 1)
        own_end[nid] = max(raw_end, min(start_p + MIN_OWN_LINES - 1, subtree_bound[nid]))

    # Each window-owning node's OWN window (its span + its OWN direct parent's announcing lines) is
    # computed once here, independently of the others. An inherited (null-explained) node then
    # reuses its owner's window exactly — not a fresh computation from the inherited node's own
    # direct parent, which is a different node from the owner whenever the null node sits more than
    # one level below its nearest explained ancestor.
    own_window: dict = {}
    for n in nodes:
        nid = n["id"]
        if owner.get(nid) != nid:
            continue
        ranges = [(line_pos[explained[nid]], own_end[nid])]
        pid = n.get("parent_id")
        if pid is not None:
            p_owner = owner.get(pid)
            if p_owner is not None:
                p_start = line_pos[explained[p_owner]]
                # fix round 1: the parent's own first ANNOUNCING_LINES lines, capped by the
                # parent's *subtree* bound, not by its (possibly one-line) own_end — the controller
                # decision's "uncapped by the parent's own span".
                p_end = min(p_start + ANNOUNCING_LINES - 1, subtree_bound[p_owner])
                ranges.append((p_start, p_end))
        own_window[nid] = ranges

    windows: dict = {}
    for n in nodes:
        nid = n["id"]
        own = owner.get(nid)
        if own is None:
            windows[nid] = Window(None, "no-text", [])
        elif own == nid:
            windows[nid] = Window(own, "own", own_window[own])
        else:
            windows[nid] = Window(own, "inherited", own_window[own])
    return windows


def merge_ranges(ranges: list) -> list:
    """Sorted, merged [(start, end)] (inclusive positions): overlapping or textually adjacent
    (end + 1 >= next start) ranges become one, so two ranges that are genuinely contiguous in the
    file join seamlessly (no separator, so a term split across that join, e.g. by a CBETA line
    break, still matches) while unrelated ranges do not merge."""
    out: list = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def window_text(win: Window, line_order: list, line_texts: dict) -> str:
    """The window's searchable text: each merged range's lines joined directly (module docstring:
    a genuinely contiguous span may join a term split across a line break), separate merged ranges
    joined by RANGE_SEPARATOR so a contiguous ("verbatim") match can never bridge two unrelated
    ranges (e.g. a node's own span and its parent's announcing lines, not adjacent text)."""
    parts = [
        "".join(line_texts[lh] for lh in line_order[start : end + 1])
        for start, end in merge_ranges(win.ranges)
    ]
    return RANGE_SEPARATOR.join(parts)


# ---- 卷-half / depth band / split -------------------------------------------------------------


def depth_band(level: int) -> str:
    if level <= 3:
        return "1-3"
    if level <= 6:
        return "4-6"
    if level <= 9:
        return "7-9"
    if level <= 12:
        return "10-12"
    return "13+"


def juan_half_boundaries(line_records: list) -> list:
    """[(position, "1a"), (position, "1b"), ...] from cb:mulu(type="卷") entries, in line order."""
    out = []
    for pos, rec in enumerate(line_records):
        for m in rec["mulu"]:
            if m["type"] == "卷":  # 卷
                out.append((pos, m["n"]))
    return out


def label_at(pos: int, boundaries: list) -> str | None:
    """The most recent boundary label at or before pos, else None (before the first one)."""
    label = None
    for bpos, blabel in boundaries:
        if bpos > pos:
            break
        label = blabel
    return label


def split_of(pos: int, line_pos: dict) -> str | None:
    for name, start, end in SPLITS:
        if start not in line_pos or end not in line_pos:
            continue
        if line_pos[start] <= pos < line_pos[end]:
            return name
    return None


# ---- per-node result -------------------------------------------------------------------------


@dataclass
class NodeResult:
    node_id: str
    source_node_id: str | None
    level: int
    depth_band: str
    heading_src: str
    heading_norm: str
    window_kind: str
    window_owner: str | None
    window_lineheads: str  # human-readable ranges, for the TSV
    juan_half: str | None
    split: str | None
    cls: str
    ratio: float | None


def check_nodes(nodes: list, line_records: list) -> list:
    """nodes: T1718 gold nodes (preorder). line_records: chinese_workflow.ingest.lines records of
    the commentary file, in document order. Returns one NodeResult per node, in preorder.

    juan_half/split are set only for window_kind "own": an inherited node's *own* location is
    unknown (its explained line is null; the window searched is its ancestor's, not its own place in
    the text), so it is never attributed to that ancestor's 卷-half or split — reporting functions
    bucket it as "(inherited — location unknown)" instead (fix round 1, controller decision)."""
    line_order = [r["linehead"] for r in line_records]
    line_texts = {r["linehead"]: r["text"] for r in line_records}
    line_pos = {lh: i for i, lh in enumerate(line_order)}
    last_pos = len(line_order) - 1
    windows = compute_windows(nodes, line_pos, last_pos)
    half_bounds = juan_half_boundaries(line_records)
    by_id = {n["id"]: n for n in nodes}
    child_count: dict = Counter(n["parent_id"] for n in nodes if n.get("parent_id") is not None)

    out = []
    for n in nodes:
        nid = n["id"]
        win = windows[nid]
        expected_counts = {child_count.get(nid, 0)}
        announced = n.get("child_count_announced")
        if announced is not None:
            expected_counts.add(announced)
        heading_norm = normalize_heading(n.get("heading_src") or "", expected_counts)
        half = None
        split = None
        if win.kind == "no-text":
            cls, ratio = "no-text", None
            ranges_repr = ""
        else:
            hay = window_text(win, line_order, line_texts)
            cls, ratio = classify_text(heading_norm, hay)
            ranges_repr = ";".join("%s-%s" % (line_order[s], line_order[e]) for s, e in win.ranges)
            if win.kind == "own":
                owner_pos = line_pos[_explained(by_id[win.owner])]
                half = label_at(owner_pos, half_bounds)
                split = split_of(owner_pos, line_pos)
        out.append(
            NodeResult(
                node_id=nid,
                source_node_id=n.get("source_node_id"),
                level=n.get("level"),
                depth_band=depth_band(n.get("level") or 0),
                heading_src=n.get("heading_src") or "",
                heading_norm=heading_norm,
                window_kind=win.kind,
                window_owner=win.owner,
                window_lineheads=ranges_repr,
                juan_half=half,
                split=split,
                cls=cls,
                ratio=ratio,
            )
        )
    return out


# ---- reporting -------------------------------------------------------------------------------

TSV_HEADER = [
    "node_id",
    "source_node_id",
    "level",
    "depth_band",
    "juan_half",
    "split",
    "class",
    "ratio",
    "window_kind",
    "window_owner",
    "window_lineheads",
    "heading_src",
    "heading_norm",
]


def to_tsv_rows(results: list) -> list:
    rows = [TSV_HEADER]
    for r in results:
        rows.append(
            [
                r.node_id,
                r.source_node_id or "",
                str(r.level),
                r.depth_band,
                r.juan_half or "",
                r.split or "",
                r.cls,
                "" if r.ratio is None else "%.3f" % r.ratio,
                r.window_kind,
                r.window_owner or "",
                r.window_lineheads,
                r.heading_src,
                r.heading_norm,
            ]
        )
    return rows


def write_tsv(rows: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")


def _counter_table(results: list, key) -> str:
    counts: dict = {}
    classes = ["verbatim", "partial", "absent", "no-text"]
    for r in results:
        counts.setdefault(key(r), Counter())[r.cls] += 1
    lines = ["| %s | %s | total |" % ("key", " | ".join(classes))]
    lines.append("|" + "---|" * (len(classes) + 2))
    for k in sorted(counts):
        c = counts[k]
        total = sum(c.values())
        lines.append("| %s | %s | %d |" % (k, " | ".join(str(c[cl]) for cl in classes), total))
    return "\n".join(lines)


# ---- F23 calibration -------------------------------------------------------------------------
#
# The 24 hand-classified sdp node groups of context/research/R03-.../findings.md F23 (the "sdp
# sample" table under F23), keyed by T1718 node id. Controller decision (fix round 1): this table
# holds only sdp node ids, F23's class for that node, and F23's row/group number (1-24, table
# order) -- no heading text: a node's actual heading_src is read from the live gold at report time
# (confusion_table), never duplicated here. F23_GROUPS is the 24 rows themselves (group number ->
# bucket, checkable-here flag), for the group-level tally (brief: 13 verbatim incl. the 答 group /
# 3 paraphrase / 5 editorial / 3 mixed).
#
# Fix round 1: groups 4 (T1718D03_002) and 14 (T1718D01_004) were wrongly marked unverifiable --
# both exist as their own T1718 gold nodes (found by heading text + tree position, not via the
# T0262-side crosswalk link, which for group 14 lands on a different, uncorroborated T1718 node --
# sdp.py's docstring's known-wrong link). 21 of 24 groups are now checkable; only groups 19-21
# (F23's T1718D07_021-022, D08_034, D09_050-056) stay excluded: none of those ids occur in the
# current T1718 gold or in its source tree-T1718-full.json (checked directly, both ways), and they
# fall under T1718D06_025, one of the 26 fetch_error subtrees Task 2 could not recover ("its subtree
# is unknown", sdp.py docstring). Also fixed: T1718D05_003 is F23's "1 editorial" of its group's
# "2 verbatim, 1 editorial", not "absent" (a class this checker uses, not F23's); T1718D04_001 is
# F23's own "bare term" note inside a "mixed" group, not plain "verbatim". (Fix round 2, controller
# decision: this table and its comments hold only sdp node ids, never heading text -- see
# tests/unit/test_sdp_eval_only_guard.py, which checks this against the live gold.)

F23_NODE_CLASS = {
    # T1718 node id: (F23 hand class, F23 group number)
    "T1718D02_001": ("verbatim", 1),
    "T1718D02_002": ("verbatim", 2),
    "T1718D03_001": ("editorial", 3),
    "T1718D03_002": ("editorial", 4),
    "T1718D04_001": ("mixed", 5),
    "T1718D05_001": ("verbatim", 6),
    "T1718D05_002": ("verbatim", 6),
    "T1718D05_003": ("editorial", 6),
    "T1718D03_003": ("verbatim", 7),
    "T1718D03_004": ("paraphrase", 8),
    "T1718D04_003": ("verbatim", 9),
    "T1718D04_004": ("verbatim", 9),
    "T1718D04_005": ("verbatim", 9),
    "T1718D04_006": ("verbatim", 9),
    "T1718D04_007": ("verbatim", 9),
    "T1718D04_008": ("verbatim", 9),
    "T1718D03_005": ("verbatim", 10),
    "T1718D04_009": ("verbatim", 10),
    "T1718D04_010": ("verbatim", 10),
    "T1718D03_006": ("verbatim", 11),
    "T1718D04_011": ("verbatim", 11),
    "T1718D04_012": ("verbatim", 11),
    "T1718D05_004": ("verbatim", 12),
    "T1718D03_007": ("editorial", 13),
    "T1718D05_006": ("verbatim", 13),
    "T1718D05_007": ("verbatim", 13),
    "T1718D05_008": ("verbatim", 13),
    "T1718D05_009": ("verbatim", 13),
    "T1718D01_004": ("editorial", 14),
    "T1718D02_003": ("editorial", 15),
    "T1718D04_015": ("verbatim", 16),
    "T1718D05_012": ("verbatim", 16),
    "T1718D05_013": ("verbatim", 16),
    "T1718D04_016": ("mixed", 17),
    "T1718D05_014": ("paraphrase", 18),
    "T1718D06_026": ("verbatim", 22),
    "T1718D07_023": ("verbatim", 22),
    "T1718D07_024": ("verbatim", 22),
    "T1718D07_025": ("verbatim", 22),
    "T1718D06_027": ("verbatim", 23),
    "T1718D08_036": ("verbatim", 23),
    "T1718D08_037": ("verbatim", 23),
    "T1718D08_038": ("verbatim", 23),
    "T1718D08_039": ("verbatim", 23),
    "T1718D08_040": ("verbatim", 23),
    "T1718D08_041": ("verbatim", 23),
    "T1718D08_042": ("verbatim", 23),
    "T1718D08_043": ("verbatim", 23),
    "T1718D08_044": ("verbatim", 23),
    "T1718D08_045": ("verbatim", 23),
    "T1718D06_028": ("verbatim", 24),
}

# The 24 groups (group number, bucket, checkable-here) for the group-level tally (brief: 13/3/5/3).
F23_GROUPS = [
    (1, "verbatim", True),
    (2, "verbatim", True),
    (3, "editorial", True),
    (4, "editorial", True),
    (5, "mixed", True),
    (6, "mixed", True),
    (7, "verbatim", True),
    (8, "paraphrase", True),
    (9, "verbatim", True),
    (10, "verbatim", True),
    (11, "verbatim", True),
    (12, "verbatim", True),
    (13, "verbatim", True),
    (14, "editorial", True),
    (15, "editorial", True),
    (16, "verbatim", True),
    (17, "mixed", True),
    (18, "paraphrase", True),
    (19, "verbatim", False),
    (20, "paraphrase", False),
    (21, "editorial", False),
    (22, "verbatim", True),
    (23, "verbatim", True),
    (24, "verbatim", True),
]


def confusion_table(results: list) -> tuple:
    """(markdown table, unmatched ids): F23_NODE_CLASS hand-class vs the automated class, over the
    nodes both name. Headings shown come from `results` (the live gold), never from F23_NODE_CLASS,
    which holds no heading text (controller decision, fix round 1)."""
    by_id: dict = {}
    for r in results:
        if r.source_node_id:
            by_id[r.source_node_id] = r
    classes = ["verbatim", "partial", "absent", "no-text"]
    hand_classes = sorted({hand for hand, _group in F23_NODE_CLASS.values()})
    table = {h: Counter() for h in hand_classes}
    missing = []
    for sid, (hand, _group) in F23_NODE_CLASS.items():
        r = by_id.get(sid)
        if r is None:
            missing.append(sid)
            continue
        table[hand][r.cls] += 1
    lines = ["| F23 hand class \\ automated | %s | total |" % " | ".join(classes)]
    lines.append("|" + "---|" * (len(classes) + 2))
    for h in hand_classes:
        row = table[h]
        total = sum(row.values())
        lines.append("| %s | %s | %d |" % (h, " | ".join(str(row[c]) for c in classes), total))
    return "\n".join(lines), missing


def group_tally() -> str:
    counts = Counter(bucket for _, bucket, _ in F23_GROUPS)
    verified = Counter(bucket for _, bucket, checkable in F23_GROUPS if checkable)
    lines = ["| bucket | groups (F23) | of which checkable here |", "|---|---|---|"]
    for b in sorted(counts):
        lines.append("| %s | %d | %d |" % (b, counts[b], verified.get(b, 0)))
    return "\n".join(lines)


def _half_key(r: "NodeResult") -> str:
    """Per-卷-half/per-split bucketing (fix round 1, controller decision): an "own"-window node is
    keyed by its own actual location; an "inherited" node's true location is unknown (its own
    explained line is null — the window searched is its ancestor's, not evidence of where this node
    itself sits) and must not be folded into the ancestor's half/split; a "no-text" node has no
    window at all."""
    if r.window_kind == "own":
        return r.juan_half or "(own, before the first 卷 boundary)"
    if r.window_kind == "inherited":
        return "(inherited — location unknown)"
    return "(no-text)"


def _split_key(r: "NodeResult") -> str:
    if r.window_kind == "own":
        return r.split or "(own, outside every split — mostly reserve)"
    if r.window_kind == "inherited":
        return "(inherited — location unknown)"
    return "(no-text)"


def _disambiguator_example(nodes: list) -> tuple | None:
    """A live example (fix round 2, controller decision), picked from the gold at report time, of a
    node whose trailing bare numeral is *kept* by the count rule because it does not equal that
    node's own child count: sdp sometimes uses a trailing digit as a bare ordinal disambiguating two
    same-named sibling sections, not as a count tag, and normalize_heading's expected_counts rule
    (fix round 1) happens to leave such a digit alone whenever it does not match. Returns
    (source_node_id, heading_src, heading_norm, child_count) for the first such node found in
    preorder with at least 2 children (so the example is not a trivial single-child case), or None.
    Never hardcoded, so no heading text lives in this module (see the module docstring)."""
    child_count = Counter(n["parent_id"] for n in nodes if n.get("parent_id") is not None)
    for n in nodes:
        stripped = strip_ordinal(n.get("heading_src") or "").strip()
        m = TRAILING_COUNT_RE.search(stripped)
        if not m:
            continue
        value = _parse_count(m.group(0))
        if value is None:
            continue
        count = child_count.get(n["id"], 0)
        if count < 2:
            continue
        expected = {count}
        announced = n.get("child_count_announced")
        if announced is not None:
            expected.add(announced)
        if value not in expected:
            heading = n["heading_src"]
            return (
                n.get("source_node_id"),
                heading,
                normalize_heading(heading, expected),
                count,
            )
    return None


def noise_baseline(nodes: list, line_records: list, seed: int = 0, trials: int = 3) -> Counter:
    """Control for the real counts: classify a RANDOMLY CHOSEN OTHER node's heading (not this
    node's own) against each "own"-window node's window, over `trials` reshuffles (seeded, so the
    report is reproducible). How often would an unrelated heading register verbatim/partial on these
    same windows by chance? A high noise rate would mean the real rate is not very informative;
    reviewer's own experiment (fix round 1 review) found roughly 1% verbatim / 9% partial by chance
    on the widened "own" windows — see HEADING-CHECK.md for this run's numbers."""
    line_order = [r["linehead"] for r in line_records]
    line_texts = {r["linehead"]: r["text"] for r in line_records}
    line_pos = {lh: i for i, lh in enumerate(line_order)}
    last_pos = len(line_order) - 1
    windows = compute_windows(nodes, line_pos, last_pos)
    heads = [normalize_heading(n.get("heading_src") or "") for n in nodes]
    own_ids = [n["id"] for n in nodes if windows[n["id"]].kind == "own"]
    rng = random.Random(seed)
    cnt: Counter = Counter()
    for _ in range(trials):
        for nid in own_ids:
            other = rng.choice(heads)
            hay = window_text(windows[nid], line_order, line_texts)
            cnt[classify_text(other, hay)[0]] += 1
    return cnt


# Fix round 0's real-data run: the "own" window's own_end was capped at the very next explained node
# in preorder with no MIN_OWN_LINES floor, and the parent's announcing lines were capped by the
# parent's own (equally narrow) span, not its subtree bound — both widened in fix round 1. Recorded
# here (re-run with the OLD window code, from commit d340d9e, against the CURRENT — fix-round-1 —
# F23_NODE_CLASS, so only the window logic differs between before/after, not the calibration set)
# rather than recomputed live, so HEADING-CHECK.md always shows fix round 1's own before/after,
# independent of what a later fix round changes next.
BEFORE_FIX_ROUND_1 = {
    "overall": {"verbatim": 75, "partial": 185, "absent": 1082, "no-text": 116},
    # F23 hand-class "verbatim" nodes whose window_kind is "own" (25 of 41 checkable verbatim node
    # ids; the other 16 are "inherited" — the 譬喻品 gap-region chain, stays "absent" for all but
    # one both before and after, see the report's "Notable disagreements" #3). window_kind itself —
    # own/inherited/no-text — is unchanged by this fix round, only a window's reach is, so "before"
    # and "after" are counted over the identical 25 nodes.
    "f23_verbatim_own_window": {"verbatim": 9, "partial": 10, "absent": 6},
}


def write_report(
    results: list, path: Path, noise: Counter | None = None, nodes: list | None = None
) -> None:
    classes = ["verbatim", "partial", "absent", "no-text"]
    overall = Counter(r.cls for r in results)
    lines = [
        "# HEADING-CHECK — sdp T1718 gold vs Zhiyi's wording (Task 3)",
        "",
        "Generated by `python -m chinese_workflow.eval.gold.sdp_check`. See `sdp_check.py`'s",
        "module docstring for the exact matching and window rules; results only, never committed.",
        "",
        "## Overall",
        "",
        "| class | count |",
        "|---|---|",
    ]
    for c in classes:
        lines.append("| %s | %d |" % (c, overall[c]))
    lines += ["| **total** | **%d** |" % len(results), ""]
    lines += ["## Per window_kind", "", _counter_table(results, lambda r: r.window_kind), ""]
    lines += [
        "## Per depth band (by window_kind: a band's own/inherited/no-text mix)",
        "",
        _counter_table(results, lambda r: "%s / %s" % (r.depth_band, r.window_kind)),
        "",
    ]
    lines += [
        "## Per 卷-half",
        "",
        "An inherited node's true location is unknown and is never attributed to its ancestor's",
        "卷-half (fix round 1); see `(inherited — location unknown)` below.",
        "",
        _counter_table(results, _half_key),
        "",
    ]
    outside_split = sum(1 for r in results if r.window_kind == "own" and r.split is None)
    lines += [
        "## Per split",
        "",
        "Same rule as 卷-half: an inherited node's split is `(inherited — location unknown)`, not",
        "its ancestor's. `(own, outside every split — mostly reserve)` (fix round 2: %d nodes) is"
        % outside_split,
        "almost entirely T1718's reserve span (plan Global Constraint 5, from T34n1718_p0063b11 to",
        "the end), not spread across the corpus; a handful of nodes before the dev split's own",
        "start line are the only exceptions.",
        "",
        _counter_table(results, _split_key),
        "",
    ]
    if nodes is not None:
        example = _disambiguator_example(nodes)
        if example is not None:
            sid, heading, norm, count = example
            lines += [
                "## Note: sdp's ordinal-like trailing digits",
                "",
                "sdp sometimes uses a trailing bare numeral as an *ordinal* disambiguating two",
                "same-named sibling sections, not as a count tag. Fix round 1's count rule strips",
                "a trailing numeral only when it equals the node's own child count, so an ordinal",
                "digit that does not usually stays. Live example from this run:",
                "",
                "node `%s`, heading `%r` (%d children) normalises to `%r` — the trailing digit is"
                % (sid, heading, count, norm),
                "kept because it does not equal the child count.",
                "",
            ]
    lines += ["## F23 calibration — group-level tally", ""]
    lines += [
        "Brief's stated tally: 13 verbatim (incl. the 答 group), 3 paraphrase, 5 editorial, "
        "3 mixed.",
        "",
        group_tally(),
        "",
    ]
    table, missing = confusion_table(results)
    lines += ["## F23 calibration — node-level confusion table", "", table, ""]
    if missing:
        lines += [
            "Not found in the current T1718 gold (excluded from the table above): "
            + ", ".join(missing),
            "",
        ]
    lines += [
        "## Fix round 1: before / after and noise baseline",
        "",
        "**Overall, before this fix round** (own_end had no MIN_OWN_LINES floor; announcing lines",
        "were capped by the parent's own narrow span, not its subtree bound):",
        "",
        "| class | before | after |",
        "|---|---|---|",
    ]
    for c in classes:
        lines.append("| %s | %d | %d |" % (c, BEFORE_FIX_ROUND_1["overall"][c], overall[c]))
    lines += [
        "",
        "**F23 hand-verbatim nodes with an own window: automated class, before vs after** (25",
        "nodes both times — the fix round 1 review's own scratch experiment used this same slice;",
        'the other 16 checkable verbatim-hand nodes are "inherited" and stay absent both before',
        "and after, except one that now reads partial by the same widened-window mechanism — see",
        '"Notable disagreements" #3):',
        "",
        "| automated class | before | after |",
        "|---|---|---|",
    ]
    verbatim_after: Counter = Counter()
    by_sid = {r.source_node_id: r for r in results if r.source_node_id}
    for sid, (hand, _group) in F23_NODE_CLASS.items():
        if hand != "verbatim":
            continue
        r = by_sid.get(sid)
        if r is not None and r.window_kind == "own":
            verbatim_after[r.cls] += 1
    for c in ("verbatim", "partial", "absent"):
        lines.append(
            "| %s | %d | %d |"
            % (c, BEFORE_FIX_ROUND_1["f23_verbatim_own_window"].get(c, 0), verbatim_after[c])
        )
    lines += [""]
    if noise is not None:
        total_noise = sum(noise.values())
        lines += [
            "**Noise baseline** (fix round 1): a randomly chosen OTHER node's heading, matched",
            'against each "own"-window node\'s window, 3 reshuffles (seed 0) — a control for how',
            "much of the real verbatim/partial rate could arise by chance alone on these windows:",
            "",
            "| class | count | rate |",
            "|---|---|---|",
        ]
        for c in ("verbatim", "partial", "absent"):
            lines.append("| %s | %d | %.1f%% |" % (c, noise[c], 100.0 * noise[c] / total_noise))
        lines += [""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---- CLI -------------------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--gold",
        type=Path,
        default=common.REPO_ROOT / "data/raw/dila-sdp/gold/T1718.zhiyi-wenju-sdp.outline.json",
    )
    ap.add_argument("--cbeta", type=Path, default=None, help="default: metadata.commentary_id")
    ap.add_argument("--out-dir", type=Path, default=None, help="default: the gold's own directory")
    args = ap.parse_args(argv)

    doc = json.loads(args.gold.read_text(encoding="utf-8"))
    cbeta_id = doc["metadata"]["commentary_id"]
    cbeta_path = args.cbeta or (common.REPO_ROOT / "data/raw/cbeta" / ("%s.xml" % cbeta_id))
    out_dir = args.out_dir or args.gold.parent

    nodes = sorted(doc["nodes"], key=lambda n: n["order"])
    line_records = extract(cbeta_path).lines
    results = check_nodes(nodes, line_records)
    noise = noise_baseline(nodes, line_records)

    write_tsv(to_tsv_rows(results), out_dir / "heading-check.tsv")
    write_report(results, out_dir / "HEADING-CHECK.md", noise=noise, nodes=nodes)

    counts = Counter(r.cls for r in results)
    print(
        "T1718 heading check: %d nodes  verbatim=%d partial=%d absent=%d no-text=%d"
        % (len(results), counts["verbatim"], counts["partial"], counts["absent"], counts["no-text"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
