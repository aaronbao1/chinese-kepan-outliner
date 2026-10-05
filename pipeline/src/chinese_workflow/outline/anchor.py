"""outline.anchor — plug the independent outline back into the text (outliner-design §5.5).

Two deterministic jobs.

(a) resolve_root_spans(doc, root) -> (doc', report)                               sūtra mode
    Input : a numbered zh-kepan outline document (common.outline_doc) whose sūtra-span nodes
            may carry the commentary's quoted lemma in locations.root_text.raw, 'A至B' or 'A'
            (經「爾時藥王至功德甚多」 -> '爾時藥王至功德甚多'); the root text as an
            ingest.text.InputText (T09n0262, whole file or a span). Locators may carry ':<offset>'.
    Output: a deep copy of the document with locations.root_text {start, end, basis, end_basis,
            raw} filled for every sūtra-span node that can be placed, flag 'unmapped' on every
            other one (validator rule [sutra-span-unmapped]), and a report: a list of
            {node_id, heading, code, detail}, one per anomaly (codes below).

    Starts, depth-first in document order, each node searched inside its parent's window and
    after its elder siblings (monotone):
      1. lemma: A is searched from the cursor to the end of the parent window, punctuation-
         insensitive (CBETA punctuates, the commentary's quotation does not: 爾時藥王 vs
         爾時，藥王), taking the earliest hit, exact or not — an exact-first search would jump
         over a punctuated occurrence to a later exact one (爾時，藥王 b09 vs 爾時藥王 b17 in the
         陀羅尼品). B is searched after A: its last character's line is the lemma end. A lemma
         with several 至 is tried at each 至, preferring a split whose B is found. basis 'lemma'.
      2. no lemma (or none found): the children are searched in the node's window; start = the
         first placed child's start, with that child's basis.
      3. otherwise the node is unmapped (root_text null, or {start: null, …, raw} when it has a
         lemma).
    The cursor after a placed sibling is the furthest point its subtree reached (starts and lemma
    ends inside the window), so a younger sibling's lemma is not matched inside an elder's range
    (說是陀羅尼 occurs in the 陀羅尼品 before the lemma of the 品's last division). The cursor runs on
    across tier-1 roots, except past a summary (rule A): a subtree that (1) covers more of its window
    than it leaves after it, measured from the subtree's start to the window's end, (2) has its starts
    past every later lemma of the window (no whole A after its last start, headings left out) and (3)
    leaves at least two later lemmas with a whole A after the restore point (one is not enough: a
    correct final subtree followed by a single node that re-quotes an earlier lemma is no summary)
    does not move the cursor — what follows is searched from just after the summary's start
    ('summary-transparent'; 善導's 卷二 五門明義 places its items over the whole 觀經, and the 卷三 and
    卷四 lemmas lie inside it). Consequence, by construction: the summary's items past the restore point
    lie outside the span the tiling gives it (ends tile to the next placed sibling), so its last items
    are clamped ('end-clamped') and validation reports child-outside-parent, which the pipeline's repair
    pass handles. Rule B: a start found after the cursor (by any method below) that would leave two or
    more younger siblings, each with a whole A after the cursor and neither a whole nor a gapped A
    after the start, is rejected ('lemma-lookahead'), since a later hit of the same A leaves them still
    less: the generic lemma (善導's 佛告阿難, which recurs in every 觀) is given up, not its siblings. A
    sibling quoted loosely, that a gapped match still finds after the start, is not stranded.
    A lemma not found after the cursor is retried after the elder subtree's last start, A before the cursor
    ('lemma-inside-elder-lemma'; its B is searched like any other, anywhere after A in the parent
    window); then, after the cursor and each reported, by a gapped match of A (first two characters
    adjacent, each later one within GAP_MAX = 6 of the last, 等 skipped; 'lemma-gapped'), by the
    longest prefix of A of >= 4 characters ('lemma-prefix'), by the longest suffix of A of >= 4
    characters, whole or gapped ('lemma-suffix'); and when nothing matches but the cursor is exactly
    the elder sibling's lemma end — and that end was found as a B — the node starts there, the
    commentary dividing the text without gaps, with basis 'interpolated' ('lemma-interpolated').
    An elder whose lemma is an incipit alone (no 至B) gives no such point: its A marks where it
    starts, not where it ends, and interpolating after it would put the node at a wrong start and
    hide it from the resolver (which takes only unmapped nodes); the node stays unmapped. B is found
    whole anywhere after A in the parent window, or by a gapped / suffix match held inside the
    enclosing lemma's end ('lemma-end-gapped' / 'lemma-end-suffix'; a whole B may lie past it,
    because Kuiji's lemma is inherited down the first-child chain and names the first unit only).
    Known limitation (open after Task 8, whose rules A and B did not close it): end-quote semantics.
    善導's 從X已來 names where the item ENDS, but a lemma is read as an incipit, so such an item is
    placed at X (its end, not its start) and the next one is searched after it. Interpolation no
    longer papers over this: the last of the 耆闍會's three parts (一切大眾歡喜奉行,
    T12n0365_p0346b19) stays unmapped.
    Kept as given: a start whose basis is not 'lemma' (chapter from tier 1, the scheme prior's
    union, manual, inferred …), and its end when that end was not fixed by 'next-node' / 'lemma';
    such a node's children are searched inside its span.

    Ends tile each parent (D15 addendum; the golds' builder rule, eval.gold.authored): a node
    ends on the line of the last non-punctuation character before its next placed sibling's
    start — the line before that start when the sibling begins its line, that start line itself
    when the sibling starts mid-line — end_basis 'next-node'; the last placed child ends with its
    parent (end_basis inherited; the end of the whole text counts as 'next-node'). A lemma end on
    the same line makes end_basis 'lemma'; a lemma end later than the tiled end is reported
    ('lemma-end-beyond-span'), never applied. root_text.start carries ':<offset>' when the start
    falls mid-line (the golds write bare lineheads; the scorer compares lines and strips offsets),
    so a root target is cut where the lemma begins, not at its line start.

(b) outlined_text(doc, target, target_role=..., outline_ref=...) -> (sidecar, markdown)
    Input : the document, the target text as an InputText (the run's span), target_role
            'commentary' | 'root', outline_ref {path, sha256} of the written outline.json.
    Output: the outlined-text sidecar (pipeline/schemas/outlined-text.schema.json) and the human
            view outlined-text.md.

    Positions: commentary target -> commentary.explained (+ ':<offset>', the entry marker); root
    target -> root_text.start (line start unless the locator carries an offset); in
    self-outlining mode the commentary positions lie in the outlined text itself, so explained
    is used for either role and root_text.start is the fallback. resolution 'inherited' for a
    node flagged 'anchor_inherited'. A node with no position in the target (commentary-internal
    nodes for a root target, unmapped nodes, locators outside the span) or whose position
    precedes an earlier node's in pre-order is listed in `unplaced`. A placed node's text runs to
    the next placed node's start in pre-order: a 'preamble' span when that node is its
    descendant, else a 'leaf' span; zero-length spans are not written. Spans tile
    [coverage.start, coverage.end) = the whole target except the gap before the first placed
    node ("before first node"); coverage.ratio = covered / chars.
    Markdown: the target text with a line
        [<indicator_display>) <heading_src> — <heading_en> {<announced>, <explained>}]
    (' — <heading_en>' left out while heading_en is empty, '-' for a null locator,
    ' (inferred, <c>)' before the closing bracket for inferred nodes) before each placed node's
    start; the text is broken only at those insertions, blocks are separated by a blank line,
    CBETA characters kept exactly.

Report codes of (a): lemma-not-found, lemma-gapped, lemma-prefix, lemma-suffix,
lemma-interpolated, lemma-inside-elder-lemma, lemma-lookahead, lemma-end-not-found, lemma-end-gapped,
lemma-end-suffix, lemma-end-beyond-span, kept-start-out-of-order, outside-root-text,
under-commentary-internal, summary-transparent, end-clamped, unmapped, not-sutra-mode. Every start
or end found by a method other than the whole (exact or punctuation-insensitive) match is reported.

Imports only chinese_workflow.common and chinese_workflow.ingest (stage boundary, design §2).
"""

from __future__ import annotations

import bisect
import copy
import re
from itertools import pairwise

from ..common.outline_doc import children_map
from ..ingest.lines import strip_punct
from ..ingest.text import InputText

PREFIX_MIN = 4  # shortest prefix of a lemma's A accepted as a start (design §5.5 (a) 1)
SUFFIX_MIN = 4  # shortest suffix of a lemma part accepted (method 'suffix')
GAP_MAX = 6  # a gapped match: first two characters adjacent, each later one within GAP_MAX of the last
MIN_LATER = 2  # rules A and B act on two or more later lemmas, not one (a single lemma is a trade of one for one)
WILDCARD = "等"  # the commentary's 等 ("and so on") inside a lemma stands for text left out
LEMMA_BRACKETS = "「」『』"
QUOTE_RE = re.compile(r"[「『]([^」』]*)[」』]")
RETILED_END_BASES = ("next-node", "lemma")  # ends this step recomputes on every run
DERIVED_BASES = ("lemma", "interpolated")  # starts this step recomputes on every run (not kept)
TARGET_ROLES = ("commentary", "root")


def nulled_basis(basis) -> str:
    """The basis a root span keeps when its start is nulled (write()'s unplaced stub, repair's demotions
    and inversions): `lemma` when the old basis is derived (DERIVED_BASES; a null start is not
    interpolated, and `lemma` is what the next run searches from the raw) or missing, else the old basis."""
    return "lemma" if not basis or basis in DERIVED_BASES else basis


# ------------------------------------------------------------------------------------ text helpers


class _Text:
    """Search and line helpers over one InputText; positions are global offsets into its .text."""

    def __init__(self, it: InputText):
        self.it = it
        self.index = it.index
        self.hay, self.keep = it.index.stripped()  # text without punctuation, and its offset map
        self.order = it.order  # document order of the whole file
        self.n = len(it.text)
        self.heads = sorted(  # (start, end) offsets of the headings (品 titles, end titles …) in .text
            (it.offset(rec["linehead"]) + h["offset"], it.offset(rec["linehead"]) + h["offset"] + len(h["text"]))
            for rec in it.lines for h in rec.get("heads") or [] if h.get("text"))

    def find(self, needle: str, lo: int, hi: int) -> tuple | None:
        """Earliest punctuation-insensitive occurrence of needle starting in [lo, hi):
        (start, end exclusive), or None."""
        pat = strip_punct(needle)
        if not pat or lo >= hi:
            return None
        i = self.hay.find(pat, bisect.bisect_left(self.keep, lo))
        if i < 0 or self.keep[i] >= hi:
            return None
        return self.keep[i], self.keep[i + len(pat) - 1] + 1

    def line(self, pos: int) -> str:
        """Linehead of the character at pos."""
        return self.index.locate(pos)[0]

    def last_line_before(self, pos: int) -> str | None:
        """Line of the last non-punctuation character before pos (None when there is none)."""
        k = bisect.bisect_left(self.keep, pos)
        return self.line(self.keep[k - 1]) if k else None

    def line_end(self, linehead: str) -> int:
        """Offset just past the last character of a line of the text."""
        return self.it.offset(linehead) + len(self.index.line_text(linehead))

    def rank(self, ref: str | None) -> int | None:
        """Document-order index of a locator's line in the whole file (None when unknown)."""
        return self.order.index(ref) if ref is not None and ref in self.order else None

    def where(self, ref: str) -> str:
        """'in' | 'before' | 'after' | 'unknown': a locator relative to the text's lines."""
        if self.it.contains(ref):
            return "in"
        r = self.rank(ref)
        if r is None or not self.it.lines:
            return "unknown"
        return "before" if r < self.rank(self.it.first_linehead) else "after"


def lemma_parts(raw: str) -> list:
    """Candidate (A, B) pairs of a lemma: 'A至B' -> [(A, B)] for every 至 with text on both sides,
    left to right; 'A' -> [(A, None)]. The commentary's wrappers are accepted too: 經「A至B」 and
    「A」下 use the quotation; 從「A」下至「B」 / 從「A」去、至「B」 give (A, B) from the two quotations."""
    quotes = [q for q in QUOTE_RE.findall(raw) if strip_punct(q)]
    if len(quotes) >= 2:
        return [(quotes[0], quotes[-1])]
    s = quotes[0] if quotes else raw.strip().strip(LEMMA_BRACKETS)
    splits = [(s[:i], s[i + 1:]) for i, ch in enumerate(s) if ch == "至"]
    splits = [(a, b) for a, b in splits if strip_punct(a) and strip_punct(b)]
    if splits:
        return splits
    return [(s, None)] if strip_punct(s) else []


def _gapped(t: _Text, needle: str, lo: int, hi: int) -> tuple | None:
    """Earliest gapped occurrence of needle starting in [lo, hi): its first two characters adjacent
    (punctuation left out), each later one within GAP_MAX characters of the previous match; a 等 in
    the needle is skipped (無量諸天發無上道心 for 諸天發心; 爾時阿難即從座起前白佛言 for 阿難白佛).
    (start, end exclusive) or None."""
    pat = [ch for ch in strip_punct(needle) if ch != WILDCARD]
    if len(pat) < 3 or lo >= hi:
        return None
    hay, keep = t.hay, t.keep
    i = hay.find(pat[0] + pat[1], bisect.bisect_left(keep, lo))
    while i >= 0 and keep[i] < hi:
        j, ok = i + 1, True
        for ch in pat[2:]:
            nxt = hay.find(ch, j + 1, j + 2 + GAP_MAX)
            if nxt < 0:
                ok = False
                break
            j = nxt
        if ok:
            return keep[i], keep[j] + 1
        i = hay.find(pat[0] + pat[1], i + 1)
    return None


def _find_part(t: _Text, part: str, lo: int, hi: int, methods: tuple) -> tuple | None:
    """One lemma part (A or B) in [lo, hi) by the given methods, in order: 'whole' (punctuation-
    insensitive), 'gapped' (_gapped), 'suffix' (the longest suffix of >= SUFFIX_MIN characters,
    whole or gapped). Returns (start, end, method) or None."""
    for method in methods:
        if method == "whole":
            hit = t.find(part, lo, hi)
        elif method == "gapped":
            hit = _gapped(t, part, lo, hi)
        else:
            p = strip_punct(part)
            hit = None
            for k in range(1, len(p) - SUFFIX_MIN + 1):
                hit = t.find(p[k:], lo, hi) or _gapped(t, p[k:], lo, hi)
                if hit is not None:
                    break
        if hit is not None:
            return hit[0], hit[1], method
    return None


def _find_b(t: _Text, b: str, lo: int, hi: int, b_hi: int | None) -> tuple | None:
    """A lemma's B after its A: whole (punctuation-insensitive) anywhere in the parent window
    [lo, hi), else gapped / suffix only inside [lo, b_hi) — the enclosing lemma's end when an
    ancestor's lemma had a B, else hi. A whole B may lie past the enclosing lemma's end because
    Kuiji's lemma is inherited down the chain of first children (parser._give_lemma): a parent's
    lemma end is its first unit's, not its extent. A fuzzy B is held inside the enclosing lemma:
    善導's 示觀緣 B 云何得見極樂國土 would otherwise take a gapped match at T12n0365_p0342b24, far
    outside the 序分 it belongs to. (start, end, method) or None."""
    hit = _find_part(t, b, lo, hi, ("whole",))
    if hit is None:
        hit = _find_part(t, b, lo, hi if b_hi is None else min(hi, b_hi), ("gapped", "suffix"))
    return hit


def _find_whole(t: _Text, parts: list, lo: int, hi: int, b_hi: int | None = None,
                methods: tuple = ("whole",), b_lim: int | None = None) -> dict | None:
    """The earliest A of a lemma starting in [lo, hi) by `methods` (default: whole A only),
    preferring a 至-split whose B is found after A (_find_b). B is searched to b_lim (default hi):
    the inside-elder retry bounds A by the cursor and B by the parent window, because B may lie past
    the elder's lemma end. Returns {start, a_end, lemma_end (or None), method, b_method, a, b,
    b_lim} or None."""
    b_lim = hi if b_lim is None else b_lim
    first = None
    for a, b in parts:
        hit = _find_part(t, a, lo, hi, methods)
        if hit is None:
            continue
        method = hit[2]
        if method == "whole":
            method = "exact" if t.it.text[hit[0]:hit[1]] == a else "punct-insensitive"
        m = {"start": hit[0], "a_end": hit[1], "lemma_end": hit[1] if b is None else None,
             "method": method, "b_method": None, "a": a, "b": b, "b_lim": b_lim}
        if b is None:
            return m
        b_hit = _find_b(t, b, hit[1], b_lim, b_hi)
        if b_hit is not None:
            m["lemma_end"], m["b_method"] = b_hit[1], b_hit[2]
            return m
        first = first or m
    return first


def _find_prefix(t: _Text, parts: list, lo: int, hi: int, b_hi: int | None = None) -> dict | None:
    """The longest prefix (>= PREFIX_MIN characters, punctuation left out) of any A starting in
    [lo, hi); B, when the lemma has one, is searched after it (_find_b). Same shape as _find_whole."""
    best = None
    for a, b in parts:
        pa = strip_punct(a)
        for k in range(len(pa) - 1, PREFIX_MIN - 1, -1):
            if best is not None and k <= len(best["a"]):
                break
            hit = t.find(pa[:k], lo, hi)
            if hit is not None:
                b_hit = _find_b(t, b, hit[1], hi, b_hi) if b is not None else None
                best = {"start": hit[0], "a_end": hit[1], "lemma_end": b_hit[1] if b_hit else None,
                        "method": "prefix", "b_method": b_hit[2] if b_hit else None,
                        "a": pa[:k], "b": b, "full_a": a, "b_lim": hi}
                break
    return best


def _root_text(n: dict) -> dict | None:
    loc = n.get("locations")
    if not isinstance(loc, dict) or loc.get("scheme") != "cbeta-kepan":
        return None
    rt = loc.get("root_text")
    return rt if isinstance(rt, dict) else None


def _lemma_raw(rt: dict | None) -> str | None:
    raw = (rt or {}).get("raw")
    return raw if isinstance(raw, str) and lemma_parts(raw) else None


def _kept_start(rt: dict | None) -> str | None:
    """The start kept from the input (not re-derived from a lemma on this run), or None."""
    return rt.get("start") if rt and rt.get("start") and not (
        rt.get("basis") in DERIVED_BASES and _lemma_raw(rt)) else None


# -------------------------------------------------------------------- (a) root spans, sūtra mode


class _Resolver:
    def __init__(self, doc: dict, root: InputText, report: list):
        self.nodes = doc["nodes"]
        self.kids = children_map(self.nodes)
        self.t = _Text(root)
        self.report = report
        self.start_line: dict = {}  # node id -> start linehead
        self.pos: dict = {}  # node id -> global offset of the start (None: start outside the text)
        self.basis: dict = {}
        self.kept_start: set = set()  # start (and basis) kept from the input
        self.kept_end: dict = {}  # node id -> end linehead kept from the input
        self.lemma_end: dict = {}  # node id -> offset just past the lemma's last character
        self.untouched: set = set()  # root_text left exactly as given
        self.end: dict = {}  # node id -> (end linehead, end_basis)
        # pre-order of the nodes the starts pass visits (commentary-internal subtrees not entered), each
        # node's subtree end in it, the nodes whose lemma is searched, and their whole-A hits (rule A)
        self.order: list = []
        self.sub_end: dict = {}
        self._walk(None)
        self.searched = {n["id"] for n in self.order if n.get("node_class") == "sutra-span"
                         and _lemma_raw(_root_text(n)) and not _kept_start(_root_text(n))}
        self.hits: dict = {}
        self.rejected: set = set()  # (node id, start) rejected by rule B, reported once

    def _walk(self, parent_id) -> None:
        for n in self.kids.get(parent_id, []):
            self.order.append(n)
            if n.get("node_class") == "sutra-span":
                self._walk(n["id"])
            self.sub_end[n["id"]] = len(self.order)

    def hit_in(self, n: dict, lo: int, hi: int) -> bool:
        """Whether a whole (punctuation-insensitive) A of n's lemma starts in [lo, hi), outside the
        text's headings (a lemma quotes the sūtra, not its titles: 佛說觀無量壽佛經, T0365's end title,
        holds 無量壽佛)."""
        nid = n["id"]
        if nid not in self.hits:
            got = set()
            for a, _ in lemma_parts(_root_text(n)["raw"]):
                pat = strip_punct(a)
                i = self.t.hay.find(pat)
                while i >= 0:
                    p = self.t.keep[i]
                    if not self.in_heads(p):
                        got.add(p)
                    i = self.t.hay.find(pat, i + 1)
            self.hits[nid] = sorted(got)
        h = self.hits[nid]
        k = bisect.bisect_left(h, lo)
        return k < len(h) and h[k] < hi

    def in_heads(self, p: int) -> bool:
        """Whether offset p lies inside one of the text's headings."""
        k = bisect.bisect_right(self.t.heads, (p, float("inf"))) - 1
        return k >= 0 and p < self.t.heads[k][1]

    def gapped_in(self, n: dict, lo: int, hi: int) -> bool:
        """Whether a gapped match (_gapped) of an A of n's lemma starts in [lo, hi), outside the headings."""
        for a, _ in lemma_parts(_root_text(n)["raw"]):
            at = lo  # per part: one part's scan must not move the next part's window start
            while at < hi:
                g = _gapped(self.t, a, at, hi)
                if g is None:
                    break
                if not self.in_heads(g[0]):
                    return True
                at = g[0] + 1
        return False

    def summary(self, nid: str, start: int, last: int, reach: int, target: int, hi: int,
                owner_end: int) -> bool:
        """Rule A: the subtree of nid (start, last start, reach) is a summary when (1) it covers more of its
        window [.., hi) than it leaves after it, measured from its own start to the window's end (reach -
        start > hi - reach); (2) its starts run past every later lemma of the window (pre-order, inside the
        window's owner: none has a whole A after `last`); and (3) at least MIN_LATER later lemmas have a
        whole A after `target`, so younger nodes can be placed from there. One such lemma is not enough: a
        correct final subtree followed by one node that re-quotes an earlier lemma is no summary. A summary's
        items past `target` fall outside the span the tiling gives it (the clamp, validation's
        child-outside-parent, which the pipeline's repair pass handles). Starts, not the reach: a lemma END
        past a younger sibling's start is the inside-elder retry's case (find())."""
        if reach - start <= hi - reach:
            return False
        later = [m for m in self.order[self.sub_end[nid]:owner_end] if m["id"] in self.searched]
        if any(self.hit_in(m, last + 1, hi) for m in later):
            return False
        return sum(self.hit_in(m, target, hi) for m in later) >= MIN_LATER

    def note(self, n: dict, code: str, detail: str) -> None:
        self.report.append({"node_id": n["id"], "heading": n.get("heading_src", ""), "code": code,
                            "detail": detail})

    # ---- starts

    def starts(self, parent_id, lo: int, hi: int, b_hi: int | None = None,
               owner_end: int | None = None) -> tuple:
        """Place the sūtra-span children of parent_id (and their subtrees) inside [lo, hi); their
        lemma ends are searched before b_hi (the enclosing lemma's end when the parent's lemma had a
        B, else hi). owner_end: the end, in self.order, of the subtree that owns the window (the
        nearest kept ancestor with an end in the text; the whole outline at top level) — the later
        lemmas rule A looks at. Returns (reach, last, raw): the furthest offset the group reached
        (starts + 1, lemma ends inside the window) with summary subtrees left out (rule A), its last
        start offset (None when nothing was placed), and the furthest offset with summaries counted."""
        owner_end = len(self.order) if owner_end is None else owner_end
        cur = lo  # a younger sibling's lemma is searched from here
        fallback = lo  # … or, failing that, from just after the elder subtree's last start
        last = None
        raw_reach = lo
        prev_rank = None  # rank of the elder sibling's start line
        elder_end = None  # lemma end of the elder sibling placed last, only when derived from a found
        # B (interpolation, find()); an incipit-only lemma's 'end' is the end of A, no division point
        for n in self.kids.get(parent_id, []):
            nid = n["id"]
            if n.get("node_class") != "sutra-span":
                self.skip(n, "under-commentary-internal")
                continue
            before = (cur, last)
            rt = _root_text(n)
            raw = _lemma_raw(rt)
            kept = _kept_start(rt)
            if kept is not None:
                got = self.kept(n, rt, kept, lo, hi, prev_rank, b_hi, owner_end)
                if got is None:
                    continue
                pos, reach, sub_last, sub_raw = got
                elder_end = None
            else:
                m = self.find(n, raw, cur, fallback, hi, b_hi, elder_end) if raw else None
                if m is not None:
                    pos = m["start"]
                    self.place(nid, pos, "interpolated" if m["method"] == "interpolated" else "lemma")
                    if m["b"] is not None and m["lemma_end"] is None:
                        self.note(n, "lemma-end-not-found", self.end_not_found(m, b_hi))
                    if m["b_method"] not in (None, "whole"):
                        self.note(n, "lemma-end-" + m["b_method"], "end by the %s match of 「%s」, "
                                  "root text 「%s」 ending at %s" % (
                                      m["b_method"], m["b"],
                                      strip_punct(self.t.it.text[m["a_end"]:m["lemma_end"]])[-12:],
                                      self.loc(m["lemma_end"] - 1)))
                    if m["lemma_end"] is not None:
                        self.lemma_end[nid] = m["lemma_end"]
                    sub_b_hi = b_hi
                    if m["b"] is not None and m["lemma_end"] is not None:
                        sub_b_hi = m["lemma_end"] if b_hi is None else min(b_hi, m["lemma_end"])
                    reach, sub_last, sub_raw = self.starts(nid, pos, hi, sub_b_hi, owner_end)
                    if m["lemma_end"] is not None and m["lemma_end"] <= hi:
                        reach = max(reach, m["lemma_end"])
                        sub_raw = max(sub_raw, m["lemma_end"])
                    elder_end = m["lemma_end"] if m["b_method"] is not None else None
                else:
                    if raw:
                        self.note(n, "lemma-not-found", "「%s」 not found in the root text from "
                                  "%s to the end of the parent span" % (raw, self.loc(cur)))
                    elder_end = None
                    reach, sub_last, sub_raw = self.starts(nid, cur, hi, b_hi, owner_end)
                    first = next((c for c in self.kids.get(nid, [])
                                  if c["id"] in self.start_line and c["id"] not in self.untouched),
                                 None)
                    if first is None:
                        continue  # unmapped: flagged in write()
                    pos = self.pos[first["id"]]
                    self.start_line[nid] = self.start_line[first["id"]]
                    self.pos[nid] = pos
                    self.basis[nid] = self.basis[first["id"]]
            for p in (pos, sub_last):
                if p is not None:
                    last = p if last is None else max(last, p)
                    fallback = max(fallback, p + 1)
            cur = max(cur, fallback, reach)
            sub_raw = max(cur, sub_raw)
            raw_reach = max(raw_reach, sub_raw)
            if kept is None and pos is not None:
                # rule A: a summary subtree (its lemmas run past every later lemma of the window) does not
                # move the cursor; what follows is searched from where it was, but after the summary's start
                target = max(before[0], pos + 1)
                sub_end = pos if sub_last is None else max(pos, sub_last)
                if target < cur and self.summary(nid, pos, sub_end, sub_raw, target, hi, owner_end):
                    self.note(n, "summary-transparent", "subtree runs from %s to %s, its starts past every "
                              "later lemma in the window; the cursor returns to %s" % (
                                  self.loc(pos), self.loc(sub_raw - 1), self.loc(target)))
                    cur = fallback = target
                    last = pos if before[1] is None else max(before[1], pos)
                    elder_end = None
            prev_rank = self.t.rank(self.start_line[nid])
        return cur, last, raw_reach

    def end_not_found(self, m: dict, b_hi: int | None) -> str:
        """Detail of 'lemma-end-not-found': the limits the search of B used — a whole B to the parent
        window's end (m['b_lim']), a gapped / suffix B to the enclosing lemma's end when that is
        nearer (_find_b)."""
        whole = m["b_lim"]
        fuzzy = whole if b_hi is None else min(whole, b_hi)
        if fuzzy == whole:
            return "「%s」 not found after 「%s」 before %s" % (m["b"], m["a"], self.loc(whole))
        return "「%s」 not found after 「%s」 (whole before %s, gapped or suffix before %s)" % (
            m["b"], m["a"], self.loc(whole), self.loc(fuzzy))

    def find(self, n: dict, raw: str, cur: int, fallback: int, hi: int, b_hi: int | None = None,
             elder_end: int | None = None) -> dict | None:
        """A lemma's start: whole A after the cursor; else whole A after the elder subtree's last
        start (reported); else, each reported, a gapped match of A, the longest prefix of A, the
        longest suffix of A, all after the cursor; else, when the cursor is exactly the elder
        sibling's lemma end and that end was found as a B (elder_end; an incipit-only lemma has none),
        that point (method and basis 'interpolated', reported): the commentary divides the text
        without a gap, so an item whose lemma cannot be matched begins where its elder's lemma ends.
        The elder's A alone marks where the elder starts, not where it ends. Rule B: a start after
        the cursor that would leave two or more later siblings with neither a whole nor a gapped A after
        it, though each has a whole one after the cursor, is rejected ('lemma-lookahead') and the next
        method tried — a later hit cannot help (it leaves them still less), so the generic lemma is
        given up, not the siblings after it."""
        parts = lemma_parts(raw)
        m = self.lookahead(n, _find_whole(self.t, parts, cur, hi, b_hi), cur, hi)
        if m is None and fallback < cur:
            m = _find_whole(self.t, parts, fallback, cur, b_hi, b_lim=hi)  # A before cur, B anywhere in the window
            if m is not None:
                self.note(n, "lemma-inside-elder-lemma", "「%s」 found only inside the elder "
                          "sibling's lemma range, at %s" % (m["a"], self.t.it.locate(m["start"])))
        if m is None:
            m = self.lookahead(n, _find_whole(self.t, parts, cur, hi, b_hi, methods=("gapped",)), cur, hi)
            if m is not None:
                self.note(n, "lemma-gapped", "start by a gapped match of 「%s」 (root text 「%s」), "
                          "at %s" % (m["a"], strip_punct(self.t.it.text[m["start"]:m["a_end"]]),
                                     self.t.it.locate(m["start"])))
        if m is None:
            m = self.lookahead(n, _find_prefix(self.t, parts, cur, hi, b_hi), cur, hi)
            if m is not None:
                self.note(n, "lemma-prefix", "start by the prefix 「%s」 of 「%s」, at %s"
                          % (m["a"], m["full_a"], self.t.it.locate(m["start"])))
        if m is None:
            m = self.lookahead(n, _find_whole(self.t, parts, cur, hi, b_hi, methods=("suffix",)), cur, hi)
            if m is not None:
                self.note(n, "lemma-suffix", "start by a suffix of 「%s」 (root text 「%s」), at %s"
                          % (m["a"], strip_punct(self.t.it.text[m["start"]:m["a_end"]]),
                             self.t.it.locate(m["start"])))
        if m is None and elder_end is not None and cur == elder_end and cur < hi:
            k = bisect.bisect_left(self.t.keep, cur)  # the first character after the elder's lemma
            start = self.t.keep[k] if k < len(self.t.keep) and self.t.keep[k] < hi else cur
            self.note(n, "lemma-interpolated", "「%s」 not found; start = the elder sibling's lemma "
                      "end, %s" % (raw, self.loc(start)))
            m = {"start": start, "a_end": start, "lemma_end": None, "method": "interpolated",
                 "b_method": None, "a": raw, "b": None}
        return m

    def lookahead(self, n: dict, m: dict | None, cur: int, hi: int) -> dict | None:
        """Rule B (find()): m, unless its start leaves MIN_LATER or more later siblings of n, whose lemmas
        have a whole A in [cur, hi), with neither a whole nor a gapped A after that start (the fuzzy
        placement finds a loosely quoted sibling still; placing n there would cost more lemmas than it
        places); then None, reported 'lemma-lookahead'."""
        if m is None:
            return None
        sibs = self.kids.get(n.get("parent_id"), [])
        later = sibs[next(k for k, s in enumerate(sibs) if s["id"] == n["id"]) + 1:]
        lost = [s for s in later if s["id"] in self.searched and self.hit_in(s, cur, hi)
                and not self.hit_in(s, m["start"] + 1, hi) and not self.gapped_in(s, m["start"] + 1, hi)]
        if len(lost) < MIN_LATER:
            return m
        if (n["id"], m["start"]) in self.rejected:  # the same start found again by a fuzzier method
            return None
        self.rejected.add((n["id"], m["start"]))
        self.note(n, "lemma-lookahead", "「%s」 at %s rejected: the younger sibling(s) %s have their "
                  "lemma only before it" % (m["a"], self.t.it.locate(m["start"]), "、".join(
                      "%s 「%s」" % (s.get("heading_src", ""), _root_text(s)["raw"]) for s in lost)))
        return None

    def kept(self, n: dict, rt: dict, start: str, lo: int, hi: int, prev_rank,
             b_hi: int | None = None, owner_end: int | None = None) -> tuple | None:
        """A start kept from the input (chapter, scheme prior, manual, inferred …, or a start derived
        from children on an earlier run): record it and place its children inside it, their fuzzy
        lemma ends still bounded by b_hi. Returns (pos, reach, last start in the subtree, raw reach)
        or None when the span lies outside the text (then the node and its subtree are left as
        given). A kept end in the text bounds the children's window, which the node then owns."""
        nid = n["id"]
        eb = rt.get("end_basis") or rt.get("basis")
        end = rt.get("end") if eb not in RETILED_END_BASES else None
        where = self.t.where(start)
        end_where = self.t.where(end) if end else None
        if where in ("after", "unknown") or end_where in ("before", "unknown"):
            self.note(n, "outside-root-text", "kept span %s..%s is not in the root text %s..%s; "
                      "left as given" % (start, end, self.t.it.first_linehead,
                                         self.t.it.last_linehead))
            self.untouch(n)
            return None
        pos = self.t.it.offset(start) if where == "in" else None
        rank = self.t.rank(start)
        if prev_rank is not None and rank is not None and rank < prev_rank:
            self.note(n, "kept-start-out-of-order", "kept start %s precedes its elder sibling's"
                      % start)
        self.start_line[nid] = start
        self.pos[nid] = pos
        self.basis[nid] = rt.get("basis")
        self.kept_start.add(nid)
        if end is not None:
            self.kept_end[nid] = end
        lo_n = pos if pos is not None else lo
        hi_n = min(hi, self.t.line_end(end)) if end_where == "in" else hi
        reach, sub_last, sub_raw = self.starts(
            nid, lo_n, hi_n, b_hi, self.sub_end[nid] if end_where == "in" else owner_end)
        if end_where == "in":
            reach = max(reach, hi_n)
            sub_raw = max(sub_raw, hi_n)
        return pos, reach, sub_last, sub_raw

    def place(self, nid: str, pos: int, basis: str) -> None:
        self.start_line[nid] = self.t.line(pos)
        self.pos[nid] = pos
        self.basis[nid] = basis

    def skip(self, n: dict, code: str) -> None:
        """A commentary-internal node: its sūtra-span descendants cannot be placed (their parent has
        no root span); kept spans among them are left as given."""
        stack = list(self.kids.get(n["id"], []))
        while stack:
            d = stack.pop(0)
            if d.get("node_class") == "sutra-span":
                if (_root_text(d) or {}).get("start"):
                    self.untouched.add(d["id"])
                else:
                    self.note(d, code, "sūtra-span node under the commentary-internal node %s"
                              % n["id"])
            stack.extend(self.kids.get(d["id"], []))

    def untouch(self, n: dict) -> None:
        stack = [n]
        while stack:
            d = stack.pop()
            self.untouched.add(d["id"])
            stack.extend(self.kids.get(d["id"], []))

    def start_ref(self, nid: str) -> str:
        """root_text.start of a placed node: its linehead, with ':<offset>' when the start falls
        mid-line (the lemma's first character), so a root target is cut where the lemma begins."""
        pos = self.pos.get(nid)
        if pos is None or pos >= self.t.n:
            return self.start_line[nid]
        return self.t.it.locate(pos)

    def loc(self, pos: int) -> str:
        return self.t.it.locate(pos) if pos < self.t.n else "the end of the text"

    # ---- ends

    def line_before(self, nid: str) -> str | None:
        """End line for a node whose next placed sibling is nid (the next-node rule)."""
        pos = self.pos.get(nid)
        line = self.t.last_line_before(pos) if pos is not None else None
        return line if line is not None else self.t.order.prev(self.start_line[nid])

    def ends(self, parent_id, p_end: str | None, p_basis: str | None) -> None:
        placed = [n for n in self.kids.get(parent_id, [])
                  if n["id"] in self.start_line and n["id"] not in self.untouched]
        for i, n in enumerate(placed):
            nid = n["id"]
            start = self.start_line[nid]
            if nid in self.kept_end:
                end = self.kept_end[nid]
                rt = _root_text(n) or {}
                eb = rt.get("end_basis") or rt.get("basis")
            else:
                if i + 1 < len(placed):
                    end, eb = self.line_before(placed[i + 1]["id"]), "next-node"
                else:
                    end, eb = p_end, p_basis
                r_start, r_end = self.t.rank(start), self.t.rank(end)
                if end is None or (r_end is not None and r_start is not None and r_end < r_start):
                    self.note(n, "end-clamped", "tiled end %s precedes the start; end = start"
                              % end)
                    end = start
                elif p_end is not None and (self.t.rank(p_end) or 0) < (r_end or 0):
                    self.note(n, "end-clamped", "tiled end %s after the parent's end %s"
                              % (end, p_end))
                    end = p_end
                le = self.lemma_end.get(nid)
                if le is not None:
                    le_line = self.t.line(le - 1)
                    if le_line == end:
                        eb = "lemma"
                    elif (self.t.rank(le_line) or 0) > (self.t.rank(end) or 0):
                        self.note(n, "lemma-end-beyond-span", "lemma ends on %s, after the tiled "
                                  "end %s (not applied)" % (le_line, end))
            self.end[nid] = (end, eb)
            self.ends(nid, end, eb)

    # ---- write back

    def write(self) -> None:
        for n in self.nodes:
            nid = n["id"]
            if n.get("node_class") != "sutra-span" or nid in self.untouched:
                continue
            flags = n.get("flags") if isinstance(n.get("flags"), list) else []
            loc = n.get("locations") if isinstance(n.get("locations"), dict) else {}
            old = _root_text(n)
            if nid in self.start_line:
                end, eb = self.end[nid]
                if nid in self.kept_start:
                    rt = dict(old)
                    if nid not in self.kept_end:
                        rt["end"] = end
                        if eb is not None:
                            rt["end_basis"] = eb
                else:
                    rt = {"text_id": old.get("text_id")} if old and old.get("text_id") else {}
                    rt.update({"start": self.start_ref(nid), "end": end, "basis": self.basis[nid]})
                    if eb is not None:
                        rt["end_basis"] = eb
                    if old and isinstance(old.get("raw"), str):
                        rt["raw"] = old["raw"]
                if loc.get("scheme") != "cbeta-kepan":
                    if loc.get("scheme") not in (None, "none"):  # 'unparsed' keeps its raw location
                        n["flags"] = flags if "unmapped" in flags else flags + ["unmapped"]
                        self.note(n, "unmapped", "location scheme %r: no root span written"
                                  % loc.get("scheme"))
                        continue
                    loc = {"scheme": "cbeta-kepan", "commentary": None, "root_text": None}
                    n["locations"] = loc
                loc["root_text"] = rt
                n["flags"] = [f for f in flags if f != "unmapped"]
            else:
                if old is not None:
                    if isinstance(old.get("raw"), str):
                        keep = {"text_id": old["text_id"]} if old.get("text_id") else {}
                        keep.update({"start": None, "end": None,
                                     "basis": nulled_basis(old.get("basis")), "raw": old["raw"]})
                        loc["root_text"] = keep
                    else:
                        loc["root_text"] = None
                if "unmapped" not in flags:
                    n["flags"] = flags + ["unmapped"]
                self.note(n, "unmapped", "no root span (no lemma found, no placed child)")


def resolve_root_spans(doc: dict, root: InputText) -> tuple[dict, list]:
    """Fill root_text spans of a sūtra-mode outline from its lemmas (module docstring, (a)).
    Returns (a deep copy of doc with spans and 'unmapped' flags, the report list)."""
    out = copy.deepcopy(doc)
    report: list = []
    meta = out.get("metadata") or {}
    if meta.get("outline_mode") != "sutra":
        report.append({"node_id": None, "heading": "", "code": "not-sutra-mode",
                       "detail": "outline_mode %r: root spans are resolved in sūtra mode only"
                       % meta.get("outline_mode")})
        return out, report
    rid = meta.get("root_text_id")
    if rid and rid != root.text_id:
        raise ValueError("root text %s is not the outline's root_text_id %s" % (root.text_id, rid))
    r = _Resolver(out, root, report)
    r.starts(None, 0, r.t.n)
    text_end = r.t.last_line_before(r.t.n) or root.last_linehead
    r.ends(None, text_end, "next-node")
    r.write()
    return out, report


# -------------------------------------------------------------------------------- (b) outlined-text


def listed_only(n: dict) -> bool:
    """A node the commentary lists but never takes up: its explained position is the position of its
    own label in the parent's listing (announced == explained, both with a character offset, as tier 2
    writes them). Such a node has no text of its own in the commentary — as in the Tibetan workflow's
    interlinear outline, where a node announced but never taken up has none (D16) — so it gets no
    span and no marker when the commentary is the target; its root span, if any, still places it in a
    root target. Bare
    lineheads (the golds) are ambiguous and stay placed."""
    com = ((n.get("locations") or {}).get("commentary")) or {}
    if not isinstance(com, dict):
        return False
    ann, exp = com.get("announced"), com.get("explained")
    return bool(ann) and ann == exp and ":" in ann


def _position(n: dict, role: str, mode: str | None) -> tuple:
    """(locator, resolution) of a node's start in the target, or (None, None)."""
    loc = n.get("locations") if isinstance(n.get("locations"), dict) else {}
    scheme = loc.get("scheme")
    if scheme == "cbeta-line":
        if role == "root" and loc.get("start"):
            return loc["start"], "root_text"
        return None, None
    if scheme != "cbeta-kepan":
        return None, None
    com = loc.get("commentary") if isinstance(loc.get("commentary"), dict) else {}
    rt = loc.get("root_text") if isinstance(loc.get("root_text"), dict) else {}
    explained, start = com.get("explained"), rt.get("start")
    if role == "commentary" or (mode == "self-outlining" and explained):
        if listed_only(n):
            return None, None
        return (explained, "explained") if explained else (None, None)
    return (start, "root_text") if start else (None, None)


def _marker(n: dict) -> str:
    com = ((n.get("locations") or {}).get("commentary")) or {}
    if not isinstance(com, dict):
        com = {}
    s = "[%s) %s" % (n.get("indicator_display") or n["id"], n.get("heading_src") or "")
    if n.get("heading_en"):
        s += " — " + n["heading_en"]
    s += " {%s, %s}" % (com.get("announced") or "-", com.get("explained") or "-")
    if n.get("origin") == "inferred":
        c = n.get("confidence")
        s += " (inferred, %s)" % ("%g" % c if isinstance(c, (int, float)) else "-")
    return s + "]"


def outlined_text(doc: dict, target: InputText, *, target_role: str,
                  outline_ref: dict) -> tuple[dict, str]:
    """The outlined-text sidecar and its markdown view over `target` (module docstring, (b))."""
    if target_role not in TARGET_ROLES:
        raise ValueError("target_role must be one of %s, not %r" % (TARGET_ROLES, target_role))
    mode = (doc.get("metadata") or {}).get("outline_mode")
    text = target.text
    parent = {n["id"]: n.get("parent_id") for n in doc["nodes"]}
    placed, unplaced = [], []  # placed: (node, position, resolution), pre-order
    for n in doc["nodes"]:
        ref, how = _position(n, target_role, mode)
        if ref is None or not target.contains(ref):
            unplaced.append(n["id"])
            continue
        pos = target.offset(ref)
        if placed and pos < placed[-1][1]:
            unplaced.append(n["id"])  # precedes an earlier node in pre-order: cannot tile
            continue
        if "anchor_inherited" in (n.get("flags") or []):
            how = "inherited"
        placed.append((n, pos, how))

    def is_descendant(nid: str, of: str) -> bool:
        p = parent.get(nid)
        while p is not None:
            if p == of:
                return True
            p = parent.get(p)
        return False

    spans, gaps = [], []
    first = placed[0][1] if placed else len(text)
    if first > 0:
        gaps.append({"char_start": 0, "char_end": first,
                     "reason": "before first node" if placed else "no placed node"})
    for k, (n, pos, how) in enumerate(placed):
        nxt = placed[k + 1] if k + 1 < len(placed) else None
        end = nxt[1] if nxt else len(text)
        if end <= pos:
            continue  # zero length: a node taken up where the next one starts
        kind = "preamble" if nxt and is_descendant(nxt[0]["id"], n["id"]) else "leaf"
        spans.append({"node_id": n["id"], "kind": kind, "char_start": pos, "char_end": end,
                      "linehead_start": target.index.locate(pos)[0],
                      "linehead_end": target.index.locate(end - 1)[0], "resolution": how})
    covered = sum(s["char_end"] - s["char_start"] for s in spans)
    overlaps = sum(1 for a, b in pairwise(spans) if b["char_start"] < a["char_end"])
    chars = len(text)
    sidecar = {
        "schema": "outlined-text/1",
        "outline_ref": {"path": outline_ref["path"], "sha256": outline_ref["sha256"]},
        "target": {"text_id": target.text_id, "role": target_role, "sha256": target.sha256,
                   "first_linehead": target.first_linehead or "",
                   "last_linehead": target.last_linehead or "", "length": chars},
        "spans": spans,
        "gaps": gaps,
        "coverage": {"start": 0, "end": chars, "chars": chars, "covered": covered,
                     "ratio": covered / chars if chars else 0.0, "overlaps": overlaps},
        "unplaced": unplaced,
    }

    lines = []
    if first > 0:
        lines += [text[:first], ""]
    k = 0
    while k < len(placed):
        pos = placed[k][1]
        while k < len(placed) and placed[k][1] == pos:
            lines.append(_marker(placed[k][0]))
            k += 1
        end = placed[k][1] if k < len(placed) else len(text)
        if end > pos:
            lines.append(text[pos:end])
        lines.append("")
    return sidecar, "\n".join(lines)
