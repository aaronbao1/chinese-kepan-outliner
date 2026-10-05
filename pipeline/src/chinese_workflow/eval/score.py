"""chinese_workflow.eval.score — the outline scorer: a predicted independent outline vs a
registered gold -> metrics (docs/outliner-design.md §9; data/EVAL-SETS.md, "Using these sets (notes
for the scorer)", items 1-12).

Input : a predicted outline.json (profile zh-kepan, `gold_status: prediction`) and a gold named
        by its dataset id in the registry data/eval-sets.json, read through
        chinese_workflow.eval.registry (item 1). `gold=` passes a gold dict instead (tests:
        synthetic golds); `gold_id` is then a label, and the registry entry of that id, when there
        is one, still supplies the split scope, scoring scope and OOD status. Line order comes from
        the key file's CBETA XML (data/raw/cbeta/, via ingest.lines.iter_lines and
        common.paths.cbeta_xml_path) or from `line_orders`.
Output: a metrics dict (`--out metrics.json`):
          settings      what the run was asked and chose (key, t, split, frozen, line order, …);
          s_f1, f_f1    the headline row's blocks (= rows[headline_row]), for quick reading;
          disclosures   gold_status, seeded_by, eval_only, headline (+ reasons), split
                        (+ defaulted), t, key, nodes out of scope, pairing warnings, notes;
          counts        nodes per side: total, scorable, counted, excluded per reason;
          rows          per t ("t=0", "t=1", the requested t; "structure" in structure mode):
                        s_f1 / f_f1 {P, R, F, TP, FP, FN}, the same without anchor_inherited gold
                        nodes, per_depth, locator_only (heading_only in structure mode), the
                        numbers exempted under truncated / absorbed into merged_range, and the
                        diagnostic fields of the E06 review (2026-10-02, A1; never headline values):
                        fn_split (frontier / frontier_line_detected / cascaded), tp_rule with
                        s_f1_both_counted, tp_uncounted_pred and the check tp_le_counted_pred,
                        key_lines (counted and distinct key lines per side, the one-node-per-line
                        recall cap) and fp_by_kind (listed_only / commentary_internal / taken_up),
                        and the attachment-tolerant triple of A2 (2026-10-02; never headline
                        values, read only together: "diag" below): ancestor_consistent, reanchor,
                        depth_offset_hist;
          child_count   announced-count accuracy; guard: the split-guard log;
          diagnostics   dev split only: ids of FN gold and FP predicted nodes, the TP pairs
                        ([pred id, gold id]), the TPs whose prediction is uncounted, the frontier /
                        line-detected / cascaded FN ids and the FP ids per kind.
        Aggregate numbers only: no heading or note of a gold node is written or printed.
CLI   : python -m chinese_workflow.eval.score --pred outline.json --gold <dataset-id>
            [--key commentary.explained|root_text.start|commentary.span_start|structure] [--t 0]
            [--split dev|validation|test|reserve|all] [--frozen TAG] [--out metrics.json]
        prints one summary line; exit 2 when the split guard refuses, 1 on bad input.

Rules implemented (EVAL-SETS items; design §9):
  key      default from the dataset (items 4, 12): anchors `structure-only` -> structure (item 10);
           anchors `root` -> root_text.start (E02/E03, sdp T0262 gold); else the locator of
           `split_scope.by` (E01: commentary.explained); else commentary.explained.
           `metadata.text_id` is never used (item 12). Lines are compared without the `:n` offset.
           `commentary.span_start` (never a default; E06 review 2026-10-02, A3): a prediction is read
           at locations.commentary.span_start, its text-span start under sdp's anchor rule as
           common.outline_doc.fill_span_starts writes it (a first child inherits its parent's start);
           a gold node at its own span_start when its commentary position has the field, else at its
           explained line (in the golds that line is the text-span start, EVAL-SETS item 3; no gold is
           chained here). A prediction without the field has no key (item 2).
  scorable a node is scorable iff its key locator is not null (item 2), on both sides, never by flag
           `unmapped`. The scoring tree keeps scorable nodes, each attached to its nearest scorable
           ancestor (none = the virtual root).
  matching top-down: the virtual roots match; the children of a matched pair are aligned one-to-one
           on key lines within t lines of each other (line distance = index distance in the file's
           own line list), order-preserving in line order (same-line siblings in document order):
           the most pairs, then the least total distance, then the least total difference of
           document-order sibling indices (_align, a DP over the two sibling sequences). A node
           whose parent is unmatched does not match. S-F1 counts matched pairs; F-F1 also needs
           equal `origin`, mapped explicitly (ORIGIN_CLASS). Structure mode (YBh, item 10) matches
           on heading_src instead of a line; it has no line order and its key (heading + depth +
           parent path) none of siblings, so its siblings pair greedily by (equal heading,
           sibling-index difference, document order), as before. (Review of E06, 2026-10-01: the
           earlier greedy took a distance-0 pair that blocked two distance-1 pairs, so a uniformly
           shifted prediction scored below 1 at t = 1. At t = 0 every candidate pair shares a line,
           and the alignment differs from the greedy only where the greedy's pairs crossed among
           same-line siblings; there it pairs them in order, which loses a pair when a prediction
           lists same-line siblings in another order than the gold. Left as is: a shifted
           prediction that also lacks a sibling can still mis-pair at t = 1 where a shifted node
           lands on the missing sibling's line, since the least total distance prefers it.)
  t        rows at the requested t and always at t = 0 and t = 1 (R06 F24: t = 0 headline, t = 1
           diagnostic). Without the key file's XML: t = 0 by string equality, t > 0 unavailable.
  scope    (item 5) a gold with `metadata.coverage_spans`: a node is in scope iff its key line lies
           in an entry's inclusive span (entry.commentary for commentary.explained, entry.root_text
           for root_text.start) and its level <= the entry's max_level; unmatched in-scope
           predictions are FP, also under a `truncated` node; out-of-scope ones are neither.
           A gold without coverage_spans: an unmatched prediction whose nearest matched ancestor is
           paired with a `truncated` gold node is neither TP nor FP (nor is its subtree). Unencoded
           children of truncated nodes are never FN (they are not in the gold). A dataset with
           `scoring_scope` (sdp T1718: served 卷-halves) counts only what in_scoring_scope accepts.
  merged   (item 10) a matched `merged_range` gold node absorbs unmatched predicted siblings under
           the same parent into its match (one TP, no FP): in locator mode those within t lines of
           it; in structure mode, which has no lines, those between its pair and the pairs before
           and after it, where no unmatched gold sibling lies between them that they might stand
           for (else they stay FP). A split is recognised only when one part matches the merged
           node itself (in structure mode: carries its heading). A label that gives the range
           (display_label K5-9: five siblings) caps the parts, nearest first; the rest stay FP.
           The children of all the parts are matched against the merged node's children.
  anchor   (item 8) every row is also given without `anchor_inherited` gold nodes (their pairs and
           FN dropped, FP unchanged). Under commentary.span_start every row is also given without
           predictions whose span_start is inherited (their pairs and FP dropped, FN unchanged), the
           mirror image, so locator-only separates the parser's own lines from the chain's.
  diag     (review of E06, 2026-10-02, A2) every available row carries three attachment-tolerant
           diagnostics over the row's counted nodes plus their scorable ancestors (the "diagnostic
           forest"; children in line order, document order in structure mode; predictions exempt
           under truncated stay in the forest but are neither TP nor FP, EVAL-SETS item 5):
           ancestor_consistent = P/R/F of the ordered ancestor-consistent mapping (a pair needs key
           lines within t; an ancestor in one tree maps to an ancestor in the other; sibling order
           kept) with the most pairs counted on both sides and, among those, the most pairs, i.e.
           an ordered tree-edit mapping with unit insert/delete and no relabel. Counted first, so
           that a mapping through uncounted ancestors can never push out a counted pair that the
           top-down match keeps: in the line-order keys s_f1_both_counted's TP never exceeds
           ancestor_consistent's (in structure mode the top-down match is greedy and can exceed the
           ordered mapping).
           mapped_pairs = the size of that mapping, uncounted ancestors included. reanchor = the
           row's top-down pairs extended by letting each unmatched counted gold node, in document
           order, take a free predicted node within t (nearest level, then first in document
           order) and aligning its subtree below, with the number of anchors used;
           depth_offset_hist = the histogram of level(pred) - level(gold) over one-to-one pairs of
           counted nodes within t, order-preserving in (line, level) order. Both TP counts use the
           both-counted rule (compare s_f1_both_counted). Gold against itself: F = 1, anchors 0,
           every offset 0; one mis-attached subtree: AC-F1 high, 1 anchor, the subtree's offset as
           the mode; a flat prediction: AC-F1 still 0.4-0.7 (it maps the leaves) but anchors ~
           every node and a spread histogram, which is why the three are read together and never
           alone. merged_range (item 10) is not modelled: S-F1 aligns the children of the absorbed
           predicted siblings under the merged gold node, which the forest mapping does not (each
           prediction keeps its own children), and an absorbed prediction is neither TP nor FP in
           S-F1 but FP in ancestor_consistent and reanchor; so where a matched merged_range node
           absorbed siblings with children, s_f1_both_counted's TP can exceed ancestor_consistent's.
           Not reachable today: every gold that carries merged_range (X0268, the YBh outlines) is
           above AC_MAX_FOREST_NODES. The forest recurrence has O(|P||G| min(dP, lP) min(dG, lG))
           states and recurses once per node, so a row whose forests exceed AC_MAX_FOREST_NODES
           (600) together reports the triple as unavailable with the size (X0268: 2,611 gold nodes;
           the YBh golds: ~2,600); so does a row whose recurrence overflows the interpreter's
           recursion limit (a forest of 500 nodes or more can on Python 3.11), with the limit.
  counts   (item 7) child-count accuracy over matched pairs: predicted vs gold
           `child_count_announced`; a disagreement at a `count_mismatch` gold node is the source's,
           reported apart and left out of the denominator.
  splits   (items 1, 5, 11; design §3) a split-scoped dataset is scored on one split: both sides
           are restricted to nodes whose split locator (the dataset's `split_scope.by`, which is
           the key in E01) lies in that split of `split_scope.text` (registry.split_of). Default
           dev, disclosed. test, reserve and all (no restriction) need `frozen`; the counted key
           lines also pass SplitGuard.check_lines, and a registered gold passes
           SplitGuard.check_gold (OOD golds need `frozen`). Root-text scoring (key in T09n0262,
           split text T1718/T1723; "Root-text experiments and the splits"): a gold node takes the
           split of its own split locator. A predicted node takes the split of the known gold node
           (one with its own split locator) that starts on its key line, its likely twin (the last
           in document order). Otherwise, and always for a gold node without its own split
           locator (which is no known node's twin), the most protected split (reserve > test >
           validation > dev) of the split-text lines from the split locator of the nearest known
           gold node before its line to that of the nearest after it, and of the known ones on
           it: its commentary lies between theirs (none before: from the file start, read as
           unlisted; none after: to the file end). Only a gold with no known node at all leaves a
           node excluded (split_unknown). (Review of E06, 2026-10-01: the earlier rule took the
           split of the last gold node at or before the line, null when that node had no split
           locator, so predictions there were neither TP nor FP. The nearest known split alone
           would put gold nodes of unknown split, possibly test or reserve answer keys, into a dev
           or validation score.) An unregistered gold whose key lines lie in a split file is
           split-scoped by that file.
           Under commentary.span_start both locators lie in the split text: a gold node takes the
           split of its explained line (the registry's split locator), a predicted node the split of
           its span_start line; the served scope and coverage_spans are judged on the key line too.
  disclose gold_status, seeded_by, eval_only, split, t, key, nodes out of scope; `headline: false`
           for a draft-unreviewed, imported-unchecked, synthetic-fixture or prediction gold and for
           a dev or validation score (item 11; R06 F19; imported-unchecked since the review of E06,
           2026-10-01: an import is a headline only once a documented check makes it
           imported-checked, the sdp golds included). Pairing on root_text_id + scheme_id
           (+ commentary_id in sūtra mode) is reported as warnings, never refused (item 12;
           model-only outlines carry their own scheme, D21).

Deterministic; standard library + lxml (through ingest.lines). Imports only chinese_workflow.common,
chinese_workflow.ingest and chinese_workflow.eval (stage boundaries).
"""
from __future__ import annotations

import argparse
import bisect
import re
import sys
from collections import Counter
from functools import cache, lru_cache
from pathlib import Path

from chinese_workflow.common.jsonio import read_json, write_json
from chinese_workflow.common.lineheads import LineOrder, file_id, strip_offset
from chinese_workflow.common.paths import REPO_ROOT, cbeta_xml_path, repo_relative
from chinese_workflow.common.splits import SplitGuard, SplitViolation
from chinese_workflow.eval import registry as reg
from chinese_workflow.ingest.lines import iter_lines

SCHEMA = "outline-metrics/1"
KEYS = ("commentary.explained", "root_text.start", "commentary.span_start", "structure")
COMMENTARY_KEYS = ("commentary.explained", "commentary.span_start")  # lines of the stating text
SPLIT_BY_KEYS = ("commentary.explained", "root_text.start")  # what a registry split_scope.by may name
SPLIT_CHOICES = ("dev", "validation", "test", "reserve", "all")
NEEDS_FROZEN = ("test", "reserve", "all")
NO_HEADLINE_STATUS = ("draft-unreviewed", "imported-unchecked", "synthetic-fixture", "prediction")
DEVELOPMENT_SPLITS = ("dev", "validation")
PROTECTION = ("dev", "validation", "test", "reserve")  # least to most protected (root-text regions)
# F-F1 compares origin classes: the schema's four values are mapped explicitly (its node.origin says
# "eval maps these four values explicitly"). imported = an external outline's node, not yet checked
# against the commentary, for a division the source marks: counted as explicit (HYPOTHESIS until the
# sdp hand check, R03 F23/F24).
ORIGIN_CLASS = {
    "explicit": "explicit",
    "imported": "explicit",
    "editorial": "editorial",
    "inferred": "inferred",
}
REASONS = ("no_key", "split_unknown", "out_of_split", "out_of_scoring_scope", "out_of_coverage")
COUNTED = "counted"
NODE_KINDS = ("listed_only", "commentary_internal", "taken_up")  # the FP split (E06 review, A1)
# The attachment-tolerant diagnostics ("diag" above) run only when the two diagnostic forests hold
# at most this many nodes together: 300 + 300 random trees take ~6 s. The recurrence also recurses
# up to once per forest node, and Python's default recursion limit (1,000) holds it to about 1,000
# nodes together on Python 3.12 (one frame per level) but only about 500 on Python 3.11, the project
# minimum (the lru_cache wrapper costs a second frame per level; measured on flat forests): the cap
# is a time bound, and attachment() catches RecursionError and reports the triple unavailable with
# the limit, so a 3.11 run can lose a row of 500-600 nodes. Every registered dev / validation / test
# row is far below it (<= 181 gold nodes); X0268 and the YBh golds (~2,600 nodes) are not and report
# the triple as unavailable.
AC_MAX_FOREST_NODES = 600


class ScoreError(ValueError):
    """An input the scorer cannot score (malformed outline, unknown key, split of unsplit gold)."""


# ---------------------------------------------------------------------------------------- locators


def locator(node: dict, which: str) -> str | None:
    """The node's line for `which` (commentary.explained | commentary.span_start | root_text.start),
    offset stripped; None when the node has no cbeta-kepan location or the field is null."""
    loc = node.get("locations") or {}
    if loc.get("scheme") != "cbeta-kepan":
        return None
    if which == "commentary.explained":
        ref = (loc.get("commentary") or {}).get("explained")
    elif which == "commentary.span_start":
        ref = (loc.get("commentary") or {}).get("span_start")
    elif which == "root_text.start":
        ref = (loc.get("root_text") or {}).get("start")
    else:
        raise ScoreError("not a locator key: %r" % which)
    return strip_offset(ref) if ref else None


def key_line(node: dict, key: str, side: str) -> str | None:
    """The line a node is scored on under `key`. Under commentary.span_start a gold node whose
    commentary position lacks the field is read at its explained line: in the golds that line is the
    text-span start (sdp's anchor rule, EVAL-SETS item 3), and no gold is chained here. A prediction
    without the field has no key (item 2): run common.outline_doc.fill_span_starts on it first."""
    if key == "commentary.span_start" and side == "gold":
        loc = node.get("locations") or {}
        com = loc.get("commentary") if isinstance(loc.get("commentary"), dict) else {}
        if loc.get("scheme") == "cbeta-kepan" and "span_start" not in com:
            return locator(node, "commentary.explained")
    return locator(node, key)


def _locator_text(key: str) -> str:
    """Which text a locator key's lines lie in: the stating text ('commentary') or the root text."""
    return "root" if key == "root_text.start" else "commentary"


def _by_to_key(by: str) -> str:
    """A registry split_scope.by ('locations.commentary.explained …') -> a locator key."""
    for key in SPLIT_BY_KEYS:
        if by.startswith("locations." + key):
            return key
    raise ScoreError("unknown split_scope.by: %r" % by)


def default_key(ds: dict | None, gold: dict) -> str:
    """The key a dataset is scored on unless --key says otherwise (items 4, 10, 12)."""
    if ds:
        anchors = ds.get("anchors")
        if anchors == "structure-only":
            return "structure"
        if anchors == "root":
            return "root_text.start"
        if ds.get("split_scope"):
            return _by_to_key(ds["split_scope"]["by"])
    nodes = gold.get("nodes") or []
    if nodes and all((n.get("locations") or {}).get("scheme") != "cbeta-kepan" for n in nodes):
        return "structure"
    return "commentary.explained"


# -------------------------------------------------------------------------------------- line order


@lru_cache(maxsize=8)
def _xml_line_order(fid: str) -> LineOrder | None:
    path = cbeta_xml_path(fid)
    if path is None:
        return None
    return LineOrder(rec["linehead"] for rec in iter_lines(path))


class _Lines:
    """Document order of the files the key lines live in: from `provided` ({file id: [lineheads]}),
    else from the file's CBETA XML, else absent (string equality / string order fallback)."""

    def __init__(self, files, provided: dict | None = None):
        self.orders: dict = {}
        self.source: dict = {}
        for fid in sorted(files):
            if provided and fid in provided:
                self.orders[fid] = LineOrder(provided[fid])
                self.source[fid] = "provided"
            else:
                self.orders[fid] = _xml_line_order(fid)
                self.source[fid] = "cbeta-xml" if self.orders[fid] is not None else "absent"

    def complete(self, files) -> bool:
        return all(self.orders.get(f) is not None for f in files)

    def _index(self, lh: str) -> int | None:
        order = self.orders.get(file_id(lh))
        return order.index(lh) if order is not None and lh in order else None

    def distance(self, a: str, b: str) -> int | None:
        """Lines between a and b; None when they cannot be compared (other file, unknown line)."""
        if a == b:
            return 0
        if file_id(a) != file_id(b):
            return None
        i, j = self._index(a), self._index(b)
        return None if i is None or j is None else abs(i - j)

    def sort_key(self, lh: str):
        """A key that sorts the lines of one file in document order (string order without an order);
        None for a line the file's order lacks."""
        fid = file_id(lh)
        order = self.orders.get(fid)
        if order is None:
            return (fid, lh)
        return (fid, order.index(lh)) if lh in order else None

    def rank(self, lh: str) -> tuple:
        """sort_key for every line: one the file's order lacks sorts first, by string."""
        order = self.orders.get(file_id(lh))
        i = order.index(lh) if order is not None and lh in order else -1
        return (file_id(lh), i, lh)

    def within(self, lh: str, start: str, end: str) -> bool:
        """lh in the inclusive span start..end of one file."""
        fid = file_id(lh)
        if fid != file_id(start) or fid != file_id(end):
            return False
        i, s, e = self._index(lh), self._index(start), self._index(end)
        if None not in (i, s, e):
            return s <= i <= e
        return start <= lh <= end


# ------------------------------------------------------------------------------------ scoring tree


class _Tree:
    """The scoring tree of one outline: its scorable nodes (key not null; every node in structure
    mode), each attached to its nearest scorable ancestor (None = the virtual root), in document
    order."""

    def __init__(self, doc: dict, key: str, side: str):
        nodes = doc.get("nodes")
        if not isinstance(nodes, list):
            raise ScoreError("%s: no nodes array" % side)
        self.by_id: dict = {}
        for n in nodes:
            if not isinstance(n, dict) or "id" not in n:
                raise ScoreError("%s: a node without id" % side)
            if n["id"] in self.by_id:
                raise ScoreError("%s: duplicate node id %s" % (side, n["id"]))
            self.by_id[n["id"]] = n
        self.ids = [n["id"] for n in nodes]
        self.pos = {nid: i for i, nid in enumerate(self.ids)}
        self.key: dict = {}
        for n in nodes:
            k = (n.get("heading_src") or "").strip() if key == "structure" else key_line(n, key, side)
            if k is not None:
                self.key[n["id"]] = k
        self.parent: dict = {}
        self.children: dict = {None: []}
        for nid in self.ids:
            if nid not in self.key:
                continue
            p = self._raw_parent(nid)
            steps = 0
            while p is not None and p not in self.key:
                p = self._raw_parent(p)
                steps += 1
                if steps > len(self.ids):
                    raise ScoreError("%s: parent_id cycle at %s" % (side, nid))
            self.parent[nid] = p
            self.children.setdefault(p, []).append(nid)
        self.level = {nid: self._level(nid) for nid in self.ids}

    def _raw_parent(self, nid):
        p = self.by_id[nid].get("parent_id")
        if p is not None and p not in self.by_id:
            raise ScoreError("node %s: parent %s not in the outline" % (nid, p))
        return p

    def _level(self, nid) -> int:
        lv = self.by_id[nid].get("level")
        if isinstance(lv, int):
            return lv
        depth, p = 1, self._raw_parent(nid)
        while p is not None and depth <= len(self.ids):
            depth, p = depth + 1, self._raw_parent(p)
        return depth

    def flags(self, nid) -> list:
        return self.by_id[nid].get("flags") or []

    def span_start_inherited(self, nid) -> bool:
        com = (self.by_id[nid].get("locations") or {}).get("commentary")
        return isinstance(com, dict) and com.get("span_start_inherited") is True

    def origin(self, nid) -> str | None:
        o = self.by_id[nid].get("origin")
        return ORIGIN_CLASS.get(o, o)

    def count(self, nid):
        return self.by_id[nid].get("child_count_announced")


def _within(d, t: int) -> bool:
    """A locator distance d in lines (None: the two keys cannot be compared) is inside the tolerance t."""
    return d is not None and d <= t


def _align(n: int, m: int, near: dict) -> list:
    """Order-preserving alignment of two sibling sequences of lengths n (predicted) and m (gold):
    [(i, j)], increasing in both, with the most pairs, then the least total line distance, then the
    least total sibling-index difference. near {(i, j): (distance, sibling-index difference)} holds
    the pairs within t."""
    best = [[(0, 0, 0)] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        row, below = best[i], best[i + 1]
        for j in range(m - 1, -1, -1):
            b = max(below[j], row[j + 1])
            if (i, j) in near:
                c, (d, x) = below[j + 1], near[i, j]
                b = max(b, (c[0] + 1, c[1] - d, c[2] - x))
            row[j] = b
    out, i, j = [], 0, 0
    while i < n and j < m:  # ties: pair, then skip the gold node, then skip the predicted one
        c = best[i + 1][j + 1]
        if (i, j) in near and best[i][j] == (c[0] + 1, c[1] - near[i, j][0], c[2] - near[i, j][1]):
            out.append((i, j))
            i, j = i + 1, j + 1
        elif best[i][j] == best[i][j + 1]:
            j += 1
        else:
            i += 1
    return out


def _greedy(near: dict) -> list:
    """One-to-one pairs [(i, j)], sorted by i, taken greedily by (distance, sibling-index
    difference, i, j). Pairs may cross sibling order (structure mode: its key, heading + depth +
    parent path, has no order)."""
    pi, pj, out = set(), set(), []
    for (i, j), _ in sorted(near.items(), key=lambda e: (e[1], e[0])):
        if i not in pi and j not in pj:
            pi.add(i)
            pj.add(j)
            out.append((i, j))
    return sorted(out)


def _merged_parts(node: dict) -> int | None:
    """How many siblings a merged_range node stands for, from a display_label like K5-9 (5); None
    when the label does not say (X0268's node has none)."""
    m = re.search(r"(\d+)-(\d+)$", node.get("display_label") or "")
    return int(m[2]) - int(m[1]) + 1 if m and int(m[2]) > int(m[1]) else None


def _align_siblings(pt: _Tree, gt: _Tree, P: list, G: list, dist, t: int, rank) -> tuple:
    """One-to-one pairs of two sibling lists (P predicted, G gold, both in document order).
    Returns (P, G, near, aligned): P and G in line order (rank; same-line siblings stay in document
    order; rank None = structure mode, document order kept), near {(i, j): (line distance,
    difference of document-order sibling indices)} for the pairs within t, and aligned [(i, j)]
    (_align in line order; _greedy in structure mode)."""
    psib = {p: k for k, p in enumerate(P)}  # document-order sibling indices
    gsib = {g: k for k, g in enumerate(G)}
    if rank is not None:
        P = sorted(P, key=lambda p: rank(pt.key[p]))
        G = sorted(G, key=lambda g: rank(gt.key[g]))
    near = {}
    for i, p in enumerate(P):
        for j, g in enumerate(G):
            d = dist(pt.key[p], gt.key[g])
            if _within(d, t):
                near[i, j] = (d, abs(psib[p] - gsib[g]))
    aligned = _greedy(near) if rank is None else _align(len(P), len(G), near)
    return P, G, near, aligned


def _match(pt: _Tree, gt: _Tree, dist, t: int, rank=None) -> tuple[dict, dict]:
    """Top-down one-to-one matching. Returns (pairs {pred id: gold id}, absorbed {pred id: gold id}
    for predicted siblings folded into a merged_range gold node). rank (a sort key for key lines)
    puts siblings in line order for the alignment; None = structure mode (greedy pairs)."""
    pairs: dict = {}
    absorbed: dict = {}
    todo = [((None,), None)]
    while todo:
        pparents, gparent = todo.pop()
        P = sorted((c for pp in pparents for c in pt.children.get(pp, ())), key=pt.pos.__getitem__)
        G = gt.children.get(gparent, [])
        if not P or not G:
            continue
        P, G, near, aligned = _align_siblings(pt, gt, P, G, dist, t, rank)
        taken = {i for i, _ in aligned}
        groups = {j: [P[i]] for i, j in aligned}
        for k, (i, j) in enumerate(aligned):
            g = G[j]
            if "merged_range" not in gt.flags(g):
                continue
            if rank is None:
                # no line to go by: the unpaired predicted siblings between this pair and the
                # pairs before and after it, where no unpaired gold sibling lies between them that
                # they might stand for (a crossing pair leaves no such gap)
                ip, jp = aligned[k - 1] if k else (-1, -1)
                i_n, j_n = aligned[k + 1] if k + 1 < len(aligned) else (len(P), len(G))
                parts = ((list(range(ip + 1, i)) if jp + 1 == j else [])
                         + (list(range(i + 1, i_n)) if j + 1 == j_n else []))
            else:  # EVAL-SETS item 10: the predicted siblings within t lines of the merged node
                parts = [x for x in range(len(P)) if (x, j) in near]
            parts = sorted((x for x in parts if x not in taken),
                           key=lambda x: (near.get((x, j), (0, 0)), abs(x - i), x))
            cap = _merged_parts(gt.by_id[g])
            for x in parts if cap is None else parts[:cap - 1]:
                taken.add(x)
                absorbed[P[x]] = g
                groups[j].append(P[x])
        for i, j in aligned:
            pairs[P[i]] = G[j]
            todo.append((tuple(groups[j]), G[j]))
    return pairs, absorbed


# ------------------------------------------------------------- attachment-tolerant diagnostics


def _forest(tree: _Tree, elig: dict, rank) -> dict:
    """Children map of the diagnostic forest: the counted nodes and their scorable ancestors (None
    = the virtual root), children in line order (document order in structure mode, rank None)."""
    keep: set = set()
    for n in tree.ids:
        if elig.get(n) == COUNTED:
            p = n
            while p is not None and p not in keep:  # stops at an ancestor already kept
                keep.add(p)
                p = tree.parent.get(p)

    def order(c):
        return tree.pos[c] if rank is None else (rank(tree.key[c]), tree.pos[c])

    kids = {}
    for n in [None] + [x for x in tree.ids if x in keep]:
        kids[n] = tuple(sorted((c for c in tree.children.get(n, []) if c in keep), key=order))
    return kids


def _ac_mapping(kp: dict, kg: dict, ok, cp: set, cg: set) -> tuple[int, int]:
    """(pairs, counted) of an ordered ancestor-consistent mapping between the forests with children
    maps kp (predicted) and kg (gold), roots kp[None] / kg[None], a pair allowed iff ok(p, g): a
    memoised recurrence on ordered forests that takes the rightmost roots a, b and either deletes
    one (lifting its children) or, when ok(a, b), maps them and recurses into their children and
    into the rest. The mapping maximises the pairs with both nodes counted (cp, cg) first and all
    pairs second, so `counted` is the most any ordered ancestor-consistent mapping can credit, and
    `pairs` the size of the largest mapping that credits that many (a mapping through uncounted
    ancestors that pushed out a counted pair would score below the top-down match; the order is
    lexicographic on (counted, pairs), additive over the recurrence, so the recurrence stays
    exact). States: O(|P||G| min(depth, leaves)^2) (the special subforests of Zhang-Shasha);
    recursion depth <= |P| + |G| (one node leaves per level; the lru_cache wrapper costs a second
    frame per level before Python 3.12)."""

    @cache
    def M(A: tuple, B: tuple) -> tuple[int, int]:  # (counted pairs, pairs), maximised in that order
        if not A or not B:
            return (0, 0)
        a, b = A[-1], B[-1]
        best = max(M(A[:-1] + kp[a], B), M(A, B[:-1] + kg[b]))
        if ok(a, b):
            inner, rest = M(kp[a], kg[b]), M(A[:-1], B[:-1])
            both = 1 if (a in cp and b in cg) else 0
            best = max(best, (inner[0] + rest[0] + both, inner[1] + rest[1] + 1))
        return best

    counted, pairs = M(kp[None], kg[None])
    return pairs, counted


def _reanchor(pt: _Tree, gt: _Tree, dist, t: int, rank, pairs: dict, absorbed: dict,
              elig_g: dict) -> tuple[dict, int]:
    """The row's top-down pairs extended by re-anchoring: each unmatched counted gold node, in
    document order, takes a free predicted node within t (nearest level, then first in document
    order) and the two subtrees are aligned below the new pair (_align_siblings, free predicted
    children vs unmatched gold children). One pass suffices: candidates only disappear, so a gold
    node skipped for lack of one never gains one. Returns (pairs, anchors used)."""
    pairs = dict(pairs)
    used = set(pairs) | set(absorbed)
    matched_g = set(pairs.values())
    anchors = 0
    for g in gt.ids:
        if g not in gt.key or g in matched_g or elig_g[g] != COUNTED:
            continue
        cands = [p for p in pt.key if p not in used and _within(dist(pt.key[p], gt.key[g]), t)]
        if not cands:
            continue
        anchors += 1
        todo = [(min(cands, key=lambda p: (abs(pt.level[p] - gt.level[g]), pt.pos[p])), g)]
        while todo:
            p0, g0 = todo.pop()
            pairs[p0] = g0
            used.add(p0)
            matched_g.add(g0)
            P = [c for c in pt.children.get(p0, []) if c not in used]
            G = [c for c in gt.children.get(g0, []) if c not in matched_g]
            if P and G:
                P, G, _, aligned = _align_siblings(pt, gt, P, G, dist, t, rank)
                todo.extend((P[i], G[j]) for i, j in aligned)
    return pairs, anchors


def _depth_offsets(pt: _Tree, gt: _Tree, cp: list, cg: list, dist, t: int, rank) -> dict:
    """Histogram of level(pred) - level(gold) over one-to-one pairs of counted nodes within t: the
    two sides sorted by (line, level, document position) and aligned order-preservingly (_align:
    the most pairs, then the least total line distance, then the least total level difference);
    structure mode (rank None) pairs greedily on equal headings. At t = 0 this is, per line, the
    depth-order alignment of the gold chain with the predicted chain. Offsets are keyed "-1", "0",
    "+1"; the mode breaks ties by the smaller |offset|, then the smaller offset."""
    def kp(p):
        return pt.pos[p] if rank is None else (rank(pt.key[p]), pt.level[p], pt.pos[p])

    def kg(g):
        return gt.pos[g] if rank is None else (rank(gt.key[g]), gt.level[g], gt.pos[g])

    P, G = sorted(cp, key=kp), sorted(cg, key=kg)
    near = {}
    for i, p in enumerate(P):
        for j, g in enumerate(G):
            d = dist(pt.key[p], gt.key[g])
            if _within(d, t):
                near[i, j] = (d, abs(pt.level[p] - gt.level[g]))
    aligned = _greedy(near) if rank is None else _align(len(P), len(G), near)
    hist = Counter(pt.level[P[i]] - gt.level[G[j]] for i, j in aligned)
    n = len(aligned)
    mode = min(hist, key=lambda k: (-hist[k], abs(k), k)) if hist else None
    within1 = sum(c for k, c in hist.items() if abs(k - mode) <= 1) if hist else 0

    def label(k: int) -> str:
        return "%+d" % k if k else "0"

    return {"pairs": n, "hist": {label(k): hist[k] for k in sorted(hist)},
            "mode": None if mode is None else label(mode),
            "share_at_mode": round(hist[mode] / n, 6) if n else None,
            "share_within_1_of_mode": round(within1 / n, 6) if n else None}


# ------------------------------------------------------------------------------------------ splits


class _SplitMap:
    """The split of a node: 'unsplit' for a gold without split scope, else dev / validation / test /
    reserve of the split text, or None when it cannot be told (split_unknown)."""

    def __init__(self, registry: dict, ds: dict | None, key: str, gt: _Tree, lines: _Lines):
        self.registry, self.key, self.lines = registry, key, lines
        texts = registry.get("splits", {}).get("texts", {})
        self.text = self.by = None
        if key != "structure":
            scope = (ds or {}).get("split_scope")
            if scope:
                self.text, self.by = scope["text"], _by_to_key(scope["by"])
            elif ds is None:  # unregistered gold: split-scoped by the file its key lines lie in
                files = {file_id(k) for k in gt.key.values()}
                hits = sorted(t for t, spec in texts.items() if spec["file"] in files)
                if hits:
                    self.text = hits[0]
                    self.by = "commentary.explained" if key == "commentary.span_start" else key
        self.file = texts[self.text]["file"] if self.text else None
        # root-text scoring: the key lines lie in another text than the split locator's, so a node's
        # split is read off the gold's commentary lines (_region). Under commentary.span_start both
        # lie in the split text and the key line itself has a split.
        self.region = bool(self.text) and _locator_text(self.by) != _locator_text(key)
        self._keys: list = []
        self._lines: list = []
        self._bounds: list = []
        if self.region:  # known gold nodes in root-text order
            entries = []
            for g in gt.key:
                sk, own = lines.sort_key(gt.key[g]), self._own_line(gt.by_id[g])
                if sk is not None and own is not None:
                    entries.append(((sk, gt.pos[g]), own))
            entries.sort(key=lambda e: e[0])
            self._keys = [e[0] for e in entries]
            self._lines = [e[1] for e in entries]
            spans = reg.split_spans(registry, self.text)
            self._bounds = sorted({b for _, s, e in spans for b in (s, e) if b})

    @property
    def scoped(self) -> bool:
        return self.text is not None

    def _own_line(self, node: dict) -> str | None:
        loc = locator(node, self.by)
        return loc if loc is not None and file_id(loc) == self.file else None

    def _own(self, node: dict) -> str | None:
        loc = self._own_line(node)
        return None if loc is None else reg.split_of(self.registry, self.text, loc)

    def _stretch(self, lo: str | None, hi: str | None) -> str:
        """The most protected split of the split-text lines lo..hi, inclusive (None = from the
        file's start, read as unlisted since its first line is not known here, or to its end). The
        split changes only at span bounds; lineheads of one CBETA file compare as strings in
        document order (data/EVAL-SETS.md, "Splits")."""
        if lo is not None and hi is not None and hi < lo:
            lo, hi = hi, lo
        found = {reg.split_of(self.registry, self.text, lo) if lo is not None
                 else reg.split_texts(self.registry)[self.text]["unlisted"]}
        found.update(reg.split_of(self.registry, self.text, b) for b in self._bounds
                     if (lo is None or lo < b) and (hi is None or b <= hi))
        return max(found, key=PROTECTION.index)

    def _region(self, keyline: str, twin: bool) -> str | None:
        """The split of a key line that no own split locator decides. twin (a predicted node): that
        of the known gold node starting on the line, its likely twin (the last in document order).
        Else the most protected split of the commentary from the nearest known gold node before
        the line to the nearest after it, and of the known ones on it."""
        sk = self.lines.sort_key(keyline)
        if sk is None or not self._keys:
            return None
        lo = bisect.bisect_left(self._keys, (sk,)) - 1
        hi = bisect.bisect_right(self._keys, (sk, len(self._keys) + 10**9))
        if twin and hi - 1 > lo:
            return reg.split_of(self.registry, self.text, self._lines[hi - 1])
        found = {self._stretch(self._lines[lo] if lo >= 0 else None,
                               self._lines[hi] if hi < len(self._lines) else None)}
        found.update(reg.split_of(self.registry, self.text, x) for x in self._lines[lo + 1:hi])
        return max(found, key=PROTECTION.index)

    def _line_split(self, keyline: str) -> str | None:
        """The split of a key line that lies in the split text itself (None: another file)."""
        if file_id(keyline) != self.file:
            return None
        return reg.split_of(self.registry, self.text, keyline)

    def of(self, node: dict, keyline: str, side: str) -> str | None:
        if not self.scoped:
            return "unsplit"
        if self.by == self.key:
            return self._own(node)
        if not self.region:
            # commentary.span_start: a gold node by its explained line (the split locator), a
            # prediction by the span_start line it is keyed on, which lies in the split text
            return self._own(node) if side == "gold" else self._line_split(keyline)
        own = self._own(node) if side == "gold" else None
        return own if own is not None else self._region(keyline, twin=side != "gold")


# ----------------------------------------------------------------------------------------- metrics


def _prf(tp: int, fp: int, fn: int) -> dict:
    def r(x):
        return None if x is None else round(x, 6)

    p = tp / (tp + fp) if tp + fp else None
    rc = tp / (tp + fn) if tp + fn else None
    f = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {"P": r(p), "R": r(rc), "F": r(f), "TP": tp, "FP": fp, "FN": fn}


def _line_match(pred_lines: list, gold_lines: list, lines: _Lines, t: int) -> int:
    """Size of a maximum one-to-one matching of two line multisets within t lines (per file,
    sorted two-pointer greedy, optimal in one dimension); t = 0 is multiset intersection."""
    if t == 0:
        return sum((Counter(pred_lines) & Counter(gold_lines)).values())
    total = 0
    for fid in sorted({file_id(x) for x in pred_lines} & {file_id(x) for x in gold_lines}):
        a = sorted(i for i in (lines._index(x) for x in pred_lines if file_id(x) == fid)
                   if i is not None)
        b = sorted(i for i in (lines._index(x) for x in gold_lines if file_id(x) == fid)
                   if i is not None)
        i = j = 0
        while i < len(a) and j < len(b):
            if abs(a[i] - b[j]) <= t:
                total, i, j = total + 1, i + 1, j + 1
            elif a[i] < b[j]:
                i += 1
            else:
                j += 1
    return total


def _listed_only(node: dict) -> bool:
    """Mirrors outline.anchor.listed_only (eval imports no outline stage): tier 2 writes a node the
    commentary lists but never takes up with announced == explained, both carrying a ':<offset>'. A
    bare linehead on both sides (the golds; model-only outlines) is ambiguous and is not listed-only."""
    com = (node.get("locations") or {}).get("commentary")
    if not isinstance(com, dict):
        return False
    ann, exp = com.get("announced"), com.get("explained")
    return bool(ann) and ann == exp and ":" in ann


def _node_kind(node: dict) -> str:
    """listed_only | commentary_internal (node_class: a commentary-internal wrapper or method item) |
    taken_up (the rest): the split of FP predictions (review of E06, 2026-10-02, A1)."""
    if _listed_only(node):
        return "listed_only"
    if node.get("node_class") == "commentary-internal":
        return "commentary_internal"
    return "taken_up"


class _Scorer:
    def __init__(self, pt, gt, elig_p, elig_g, lines, key, coverage):
        self.pt, self.gt, self.elig_p, self.elig_g = pt, gt, elig_p, elig_g
        self.lines, self.key, self.coverage = lines, key, coverage
        self.counted_p = [p for p in pt.ids if elig_p[p] == COUNTED]
        self.counted_g = [g for g in gt.ids if elig_g[g] == COUNTED]

    def dist(self, a: str, b: str):
        if self.key == "structure":
            return 0 if a == b else None
        return self.lines.distance(a, b)

    def _under_truncated(self, p, pairs, absorbed) -> bool:
        a = self.pt.parent[p]
        while a is not None:
            g = pairs.get(a) or absorbed.get(a)
            if g is not None:
                return "truncated" in self.gt.flags(g)
            a = self.pt.parent[a]
        return False

    def outcome(self, t: int) -> dict:
        rank = None if self.key == "structure" else self.lines.rank
        pairs, absorbed = _match(self.pt, self.gt, self.dist, t, rank)
        matched_g = set(pairs.values())
        tp = [(p, g) for p, g in pairs.items() if self.elig_g[g] == COUNTED]
        fn = [g for g in self.counted_g if g not in matched_g]
        fp, exempt = [], []
        for p in self.counted_p:
            if p in pairs or p in absorbed:
                continue
            if not self.coverage and self._under_truncated(p, pairs, absorbed):
                exempt.append(p)
            else:
                fp.append(p)
        absorbed_counted = sum(1 for p, g in absorbed.items() if self.elig_g[g] == COUNTED)
        outside = sum(1 for p, g in pairs.items() if self.elig_g[g] != COUNTED
                      and self.elig_p[p] == COUNTED)
        # FN split (review of E06, 2026-10-02, A1): a miss whose scoring-tree parent is matched or
        # the root is a frontier miss, the rest cascade from one; a frontier miss is line-detected
        # when a free predicted node (scorable, unpaired, unabsorbed; counted or not) lies within t
        # of its key line, i.e. the line was found and the node attached or levelled wrongly
        free = [p for p in self.pt.key if p not in pairs and p not in absorbed]
        frontier, detected, cascaded = [], [], []
        for g in fn:
            par = self.gt.parent[g]
            if par is not None and par not in matched_g:
                cascaded.append(g)
                continue
            frontier.append(g)
            if any(_within(self.dist(self.pt.key[p], self.gt.key[g]), t) for p in free):
                detected.append(g)
        return {"tp": tp, "fp": fp, "fn": fn, "exempt": exempt, "absorbed": absorbed_counted,
                "matched_outside": outside, "fn_frontier": frontier,
                "fn_frontier_detected": detected, "fn_cascaded": cascaded,
                "pairs": pairs, "absorbed_pairs": absorbed}

    def rows(self, o: dict, t: int) -> dict:
        gt, pt = self.gt, self.pt

        def block(drop_g=lambda g: False, drop_p=lambda p: False):
            tp = [(p, g) for p, g in o["tp"] if not drop_g(g) and not drop_p(p)]
            fn = [g for g in o["fn"] if not drop_g(g)]
            fp = [p for p in o["fp"] if not drop_p(p)]
            same = sum(1 for p, g in tp if pt.origin(p) == gt.origin(g))
            s = _prf(len(tp), len(fp), len(fn))
            f = _prf(same, len(fp) + len(tp) - same, len(fn) + len(tp) - same)
            return tp, fn, fp, s, f

        def detect(tp, fn, fp) -> dict:
            """Key lines as multisets, matched within t: detection apart from attachment."""
            pl = [pt.key[p] for p, _ in tp] + [pt.key[p] for p in fp]
            gl = [gt.key[g] for _, g in tp] + [gt.key[g] for g in fn]
            if self.key == "structure":
                m = sum((Counter(pl) & Counter(gl)).values())
            else:
                m = _line_match(pl, gl, self.lines, t)
            return _prf(m, len(pl) - m, len(gl) - m)

        tp, fn, _, s, f = block()
        _, _, _, s_ai, f_ai = block(drop_g=lambda g: "anchor_inherited" in gt.flags(g))
        # review of E06, 2026-10-02, item 5: TP counts a pair when the gold node is counted (root-text
        # scoring can leave the prediction uncounted), FP runs over counted predictions; the
        # both-counted rule is given beside the headline until Q4 is decided, never instead of it
        tp_both = [(p, g) for p, g in tp if self.elig_p[p] == COUNTED]
        gold_lines = Counter(gt.key[g] for g in self.counted_g)
        pred_lines = Counter(pt.key[p] for p in self.counted_p)
        depth: dict = {}
        for _p, g in tp:
            depth.setdefault(gt.level[g], [0, 0, 0])[0] += 1
        for p in o["fp"]:
            depth.setdefault(pt.level[p], [0, 0, 0])[1] += 1
        for g in fn:
            depth.setdefault(gt.level[g], [0, 0, 0])[2] += 1
        detect_name = "heading_only" if self.key == "structure" else "locator_only"
        row = {
            "available": True,
            "t": t,
            "s_f1": s,
            "f_f1": f,
            "without_anchor_inherited": {"s_f1": s_ai, "f_f1": f_ai},
            "per_depth": {str(d): _prf(*v) for d, v in sorted(depth.items())},
            detect_name: detect(tp, fn, o["fp"]),
            "exempt_under_truncated": len(o["exempt"]),
            "absorbed_into_merged_range": o["absorbed"],
            "matched_to_gold_outside_scope": o["matched_outside"],
            "fn_split": {"frontier": len(o["fn_frontier"]),
                         "frontier_line_detected": len(o["fn_frontier_detected"]),
                         "cascaded": len(o["fn_cascaded"])},
            "tp_rule": "gold_counted",
            "s_f1_both_counted": _prf(len(tp_both), len(o["fp"]), len(fn) + len(tp) - len(tp_both)),
            "tp_uncounted_pred": len(tp) - len(tp_both),
            "tp_le_counted_pred": len(tp) <= len(self.counted_p),
            "key_lines": {
                "gold": {"counted": len(self.counted_g), "distinct": len(gold_lines)},
                "pred": {"counted": len(self.counted_p), "distinct": len(pred_lines)},
                "recall_cap_one_node_per_line": (round(len(gold_lines) / len(self.counted_g), 6)
                                                 if self.counted_g else None)},
            "fp_by_kind": {k: len(v) for k, v in self.fp_kinds(o["fp"]).items()},
        }
        if self.key == "commentary.span_start":  # EVAL-SETS item 8's mirror for predictions
            tp_i, fn_i, fp_i, s_i, f_i = block(drop_p=pt.span_start_inherited)
            row["without_span_start_inherited"] = {
                "s_f1": s_i, "f_f1": f_i, detect_name: detect(tp_i, fn_i, fp_i),
                "predictions_dropped": sum(1 for p in self.counted_p if pt.span_start_inherited(p))}
        row.update(self.attachment(o, t))  # the triple of A2 comes last (after A1's and A3's fields)
        return row

    def fp_kinds(self, fp: list) -> dict:
        """The FP predictions by node kind (NODE_KINDS), each list in prediction document order."""
        kinds: dict = {k: [] for k in NODE_KINDS}
        for p in sorted(fp, key=self.pt.pos.__getitem__):
            kinds[_node_kind(self.pt.by_id[p])].append(p)
        return kinds

    def attachment(self, o: dict, t: int) -> dict:
        """The attachment-tolerant diagnostic triple of a row (module docstring, "diag"): the blocks
        ancestor_consistent, reanchor and depth_offset_hist, or all three unavailable (one shape,
        with a reason) when the two diagnostic forests together exceed AC_MAX_FOREST_NODES or the
        recurrence overflows the interpreter's recursion limit (a forest under the cap can, on
        Python 3.11). TP needs both nodes counted; a prediction exempt under truncated is neither
        TP nor FP (EVAL-SETS item 5)."""
        rank = None if self.key == "structure" else self.lines.rank
        kp, kg = _forest(self.pt, self.elig_p, rank), _forest(self.gt, self.elig_g, rank)
        size = (len(kp) - 1) + (len(kg) - 1)

        def unavailable(reason: str) -> dict:
            return {k: {"available": False, "reason": reason}
                    for k in ("ancestor_consistent", "reanchor", "depth_offset_hist")}

        if size > AC_MAX_FOREST_NODES:
            return unavailable("diagnostic forest of %d nodes exceeds AC_MAX_FOREST_NODES = %d"
                               % (size, AC_MAX_FOREST_NODES))
        exempt = set(o["exempt"])
        cp_list = [p for p in self.counted_p if p not in exempt]
        cp, cg = set(cp_list), set(self.counted_g)

        def ok(p, g) -> bool:
            return _within(self.dist(self.pt.key[p], self.gt.key[g]), t)

        try:
            mapped, tp = _ac_mapping(kp, kg, ok, cp, cg)
        except RecursionError:  # the memo cache is local to the call, so nothing is left behind
            return unavailable("diagnostic forest of %d nodes exceeds the recursion limit (%d) of "
                               "the mapping recurrence" % (size, sys.getrecursionlimit()))
        rpairs, anchors = _reanchor(self.pt, self.gt, self.dist, t, rank, o["pairs"],
                                    o["absorbed_pairs"], self.elig_g)
        rtp = sum(1 for p, g in rpairs.items() if p in cp and g in cg)
        return {
            "ancestor_consistent": {"available": True, **_prf(tp, len(cp) - tp, len(cg) - tp),
                                    "mapped_pairs": mapped,
                                    "forest": {"pred": len(kp) - 1, "gold": len(kg) - 1}},
            "reanchor": {"available": True, **_prf(rtp, len(cp) - rtp, len(cg) - rtp),
                         "anchors": anchors},
            "depth_offset_hist": {"available": True,
                                  **_depth_offsets(self.pt, self.gt, cp_list, self.counted_g,
                                                   self.dist, t, rank)},
        }

    def child_count(self, o: dict) -> dict:
        c = Counter()
        for p, g in o["tp"]:
            ga, pa = self.gt.count(g), self.pt.count(p)
            if ga is None:
                c["pred_only"] += pa is not None
                continue
            c["eligible"] += 1
            c["at_count_mismatch"] += "count_mismatch" in self.gt.flags(g)
            if pa is None:
                c["missing"] += 1
            elif pa == ga:
                c["correct"] += 1
            elif "count_mismatch" in self.gt.flags(g):
                c["source_disagreements"] += 1
            else:
                c["wrong"] += 1
        denom = c["eligible"] - c["source_disagreements"]
        out = {k: c[k] for k in ("eligible", "correct", "wrong", "missing", "source_disagreements",
                                 "at_count_mismatch", "pred_only")}
        out["accuracy"] = round(c["correct"] / denom, 6) if denom else None
        out["note"] = ("predicted vs gold child_count_announced over matched pairs at the "
                       "requested t; a disagreement at a count_mismatch gold node is the source's "
                       "(EVAL-SETS item 7) and is left out of the accuracy's denominator")
        return out


# ---------------------------------------------------------------------------------------------- API


def _load_gold(gold_id: str, ds: dict | None, gold: dict | None) -> tuple[dict, str]:
    if gold is not None:
        return gold, "<dict>"
    if ds is None:
        raise KeyError("%s is not a registered dataset (data/eval-sets.json)" % gold_id)
    if ds.get("format") != "zh-kepan-outline":
        raise ScoreError("%s is not a gold outline (format %s)" % (gold_id, ds.get("format")))
    path = REPO_ROOT / ds["path"]
    if not path.exists():
        raise FileNotFoundError(
            "%s: %s is absent (eval-only golds live under data/raw/; see data/EVAL-SETS.md, "
            "'Rebuilding and checking')" % (gold_id, ds["path"])
        )
    return read_json(path), ds["path"]


def _pairing(pred: dict, gold: dict) -> list:
    pm, gm = pred.get("metadata") or {}, gold.get("metadata") or {}
    out = []
    fields = ["root_text_id", "scheme_id"]
    if gm.get("outline_mode") == "sutra":
        fields.append("commentary_id")
    for f in fields:
        if pm.get(f) != gm.get(f):
            out.append("metadata.%s differs: prediction %r, gold %r (item 12)" % (f, pm.get(f),
                                                                                    gm.get(f)))
    return out


def score(pred: dict, gold_id: str, *, key: str | None = None, t: int = 0, split: str | None = None,
          frozen: str | None = None, registry: dict | None = None, gold: dict | None = None,
          line_orders: dict | None = None) -> dict:
    """Score a predicted outline against a gold (module docstring). `line_orders` ({file id:
    [lineheads in document order]}) overrides the CBETA XML as the source of line order (tests, or
    a caller that already holds the line list). Raises SplitViolation where the split discipline
    refuses, ScoreError on input it cannot score."""
    registry = reg.load_registry() if registry is None else registry
    if not isinstance(t, int) or t < 0:
        raise ScoreError("t must be a non-negative integer")
    if split is not None and split not in SPLIT_CHOICES:
        raise ScoreError("split must be one of %s" % ", ".join(SPLIT_CHOICES))
    try:
        ds = reg.dataset(registry, gold_id)
    except KeyError:
        ds = None
    guard = SplitGuard(frozen=frozen, registry=registry)
    if ds is not None:
        guard.check_gold(gold_id)  # OOD golds: SplitViolation unless frozen
    gold, gold_path = _load_gold(gold_id, ds, gold)
    key = key or default_key(ds, gold)
    if key not in KEYS:
        raise ScoreError("key must be one of %s" % ", ".join(KEYS))
    gmeta = gold.get("metadata") or {}

    gt = _Tree(gold, key, "gold")
    pt = _Tree(pred, key, "prediction")
    if key == "structure":
        files: set = set()
    else:
        files = {file_id(k) for k in gt.key.values()} | {file_id(k) for k in pt.key.values()}
    lines = _Lines(files, line_orders)
    gold_files = {file_id(k) for k in gt.key.values()} if key != "structure" else set()
    splits = _SplitMap(registry, ds, key, gt, lines)
    notes: list = []
    keyless_truncated = sum(
        1 for n in (gold.get("nodes") or [])
        if "truncated" in (n.get("flags") or []) and n.get("id") not in gt.key)
    if keyless_truncated:
        # review of 2026-09-27: the exemption of item 5 needs the truncated node in the scoring
        # tree, and a node without a key line is not in it
        # under commentary.span_start a gold node is read at its own span_start where it carries one,
        # else at its explained line (key_line), so "no span_start line" would misstate what is missing
        what = ("key line (a gold node is read at its own span_start where it has one, else at its "
                "explained line)" if key == "commentary.span_start" else "%s line" % key)
        notes.append(
            "%d truncated gold node(s) have no %s, so predictions under them cannot be exempted "
            "(EVAL-SETS item 5) and count as FP where they are in scope; in the sdp T1718 gold they "
            "lie in unserved 卷-halves, outside the served scoring scope" % (keyless_truncated, what))

    # which split is scored (items 1, 5; design §3)
    defaulted = False
    if splits.scoped:
        if split is None:
            split, defaulted = "dev", True
            notes.append("no split given: the dev split is scored")
        if split in NEEDS_FROZEN and not frozen:
            raise SplitViolation(
                "split %s of %s needs --frozen <tag>: test and reserve are refused during "
                "development (data/EVAL-SETS.md, items 1 and 5)" % (split, gold_id)
            )
    else:
        if key == "structure" and (ds or {}).get("split_scope") and not frozen:
            # structure mode cannot tell which nodes lie in which split, so it would score the
            # test and reserve answer keys along with the rest (review of 2026-09-27)
            raise SplitViolation(
                "%s has split-scoped answer keys; structure mode cannot restrict them to a split, "
                "so it needs --frozen <tag>" % gold_id)
        if split not in (None, "all"):
            raise ScoreError("%s has no split scope: it is scored whole (omit split)" % gold_id)
        split = "unsplit"

    # scope of each node (items 2, 5)
    coverage = gmeta.get("coverage_spans") or []
    if coverage and key == "structure":
        notes.append("coverage_spans ignored in structure mode (no locators)")
        coverage = []
    served = bool(ds and ds.get("scoring_scope"))
    served_key = _by_to_key(ds["scoring_scope"]["key"]) if served else None

    def in_coverage(tree: _Tree, nid: str) -> bool:
        kl, lv = tree.key[nid], tree.level[nid]
        for entry in coverage:
            span = entry.get("commentary" if key in COMMENTARY_KEYS else "root_text") or {}
            if not (span.get("start") and span.get("end")):
                continue
            inside = lines.within(kl, strip_offset(span["start"]), strip_offset(span["end"]))
            if inside and (entry.get("max_level") is None or lv <= entry["max_level"]):
                return True
        return False

    def served_line(tree: _Tree, nid: str, node: dict) -> str | None:
        """The line the served scope is checked on: the key line when the key is a locator in the
        scope's text (a span_start prediction is judged where it stands), else the scope's own
        locator. Structure mode has no key line (its tree key is the heading), so it always takes
        the scope's own locator."""
        if key != "structure" and _locator_text(key) == _locator_text(served_key):
            return tree.key[nid]
        return locator(node, served_key)

    def eligibility(tree: _Tree, side: str) -> tuple[dict, dict]:
        elig, split_of = {}, {}
        for nid in tree.ids:
            if nid not in tree.key:
                elig[nid] = "no_key"
                continue
            node = tree.by_id[nid]
            sp = splits.of(node, tree.key[nid], side)
            split_of[nid] = sp
            if split not in ("all", "unsplit") and sp is None:
                elig[nid] = "split_unknown"
            elif split not in ("all", "unsplit") and sp != split:
                elig[nid] = "out_of_split"
            elif served and not reg.in_scoring_scope(registry, gold_id, served_line(tree, nid, node)):
                elig[nid] = "out_of_scoring_scope"
            elif coverage and not in_coverage(tree, nid):
                elig[nid] = "out_of_coverage"
            else:
                elig[nid] = COUNTED
        return elig, split_of

    elig_g, split_g = eligibility(gt, "gold")
    elig_p, split_p = eligibility(pt, "pred")

    # data-driven guard: the counted key lines (and, for root-text scoring, their computed splits)
    counted_lines = sorted({t_.key[n] for t_, el in ((gt, elig_g), (pt, elig_p))
                            for n in t_.ids if el[n] == COUNTED}) if key != "structure" else []
    guard.check_lines(counted_lines, purpose="score %s (split %s)" % (gold_id, split))
    blocked = sorted({s for sp_map, el in ((split_g, elig_g), (split_p, elig_p))
                      for n, s in sp_map.items() if el[n] == COUNTED and s in ("test", "reserve")})
    if blocked and not frozen:
        raise SplitViolation("scoring would count %s nodes; pass --frozen <tag>"
                             % "/".join(blocked))

    scorer = _Scorer(pt, gt, elig_p, elig_g, lines, key, bool(coverage))
    ts = [0] if key == "structure" else sorted({t, 0, 1})
    rows, outcomes = {}, {}
    for tt in ts:
        name = "structure" if key == "structure" else "t=%d" % tt
        if tt > 0 and not lines.complete(gold_files):
            rows[name] = {"available": False, "t": tt,
                          "reason": "no line order for %s (CBETA XML absent): t > 0 needs line "
                                    "distances" % ", ".join(sorted(f for f in gold_files
                                                                   if lines.orders.get(f) is None))}
            continue
        outcomes[tt] = scorer.outcome(tt)
        rows[name] = scorer.rows(outcomes[tt], tt)
    head_name = "structure" if key == "structure" else "t=%d" % t
    head_t = 0 if key == "structure" or t not in outcomes else t  # child counts, diagnostics
    if key != "structure" and t not in outcomes:
        notes.append("the requested t = %d is unavailable (no line order): child counts and "
                     "diagnostics are given at t = 0" % t)

    def tally(tree: _Tree, elig: dict) -> dict:
        c = Counter(elig.values())
        return {"nodes": len(tree.ids), "scorable": len(tree.key), "counted": c[COUNTED],
                "excluded": {r: c[r] for r in REASONS if c[r]}}

    counts = {"pred": tally(pt, elig_p), "gold": tally(gt, elig_g)}
    out_scope = {s: counts[s]["nodes"] - counts[s]["counted"] for s in ("pred", "gold")}

    gold_status = gmeta.get("gold_status")
    reasons = []
    if gold_status in NO_HEADLINE_STATUS:
        reasons.append("gold_status %s (EVAL-SETS item 11; R06 F19)" % gold_status)
    if split in DEVELOPMENT_SPLITS:
        reasons.append("%s split: a development score" % split)
    if gmeta.get("seeded_by"):
        notes.append("gold seeded by %s: a score of a system built on the same model must say so "
                     "(R06 F19)" % gmeta["seeded_by"])
    if key != "structure" and t >= 2:
        notes.append("t >= 2 spans a median leaf (R06 F24): diagnostic only")
    if key != "structure" and not lines.complete(gold_files):
        notes.append("line order absent for %s: t = 0 by string equality, span tests by string "
                     "order" % ", ".join(sorted(gold_files)))
    if counts["pred"]["excluded"].get("no_key"):
        notes.append("%d predicted nodes have no %s and are not scored (item 2)"
                     % (counts["pred"]["excluded"]["no_key"], key))
    if split == "validation":
        notes.append("validation look: record it in the experiment's looks.json (design §9)")
    if ds is None:
        notes.append("gold %s is not registered: no registry split scope, scoring scope or OOD "
                     "check%s" % (gold_id, "; split-scoped by its file" if splits.scoped else ""))
    if splits.scoped and splits.region:
        notes.append("root-text scoring: splits from %s of the gold, predictions by gold region"
                     % splits.by)
    if key == "commentary.span_start":
        notes.append("key commentary.span_start: predictions at their span_start (a first child's is "
                     "its parent's, common.outline_doc.fill_span_starts); gold nodes at their own "
                     "span_start where the field is present, else at their explained line (sdp's "
                     "anchor rule, EVAL-SETS item 3); splits: gold by explained, predictions by the "
                     "span_start line; rows also without predictions whose span_start is inherited. "
                     "The E01 key is undecided (item 3): report both keys")

    result = {
        "schema": SCHEMA,
        "settings": {
            "scorer": "chinese_workflow.eval.score",
            "gold_id": gold_id,
            "gold_path": gold_path,
            "key": key,
            "mode": "structure" if key == "structure" else "locator",
            "t": None if key == "structure" else t,
            "rows_at_t": ts if key != "structure" else [],
            "split": split,
            "split_text": splits.text,
            "split_locator": splits.by,
            "frozen": frozen,
            "line_order": {f: lines.source.get(f, "absent") for f in sorted(files)},
            "origin_classes": ORIGIN_CLASS,
            "diagnostic_forest_cap": AC_MAX_FOREST_NODES,
            "matching": "top-down; siblings aligned one-to-one in line order (most pairs, then "
                        "least total line distance, then least total sibling-index difference; "
                        "structure mode: greedy by equal heading); scorable = key not null, "
                        "attached to the nearest scorable ancestor",
            "prediction": {k: (pred.get("metadata") or {}).get(k)
                           for k in ("generated_by", "scheme_id", "gold_status")},
        },
        "disclosures": {
            "gold_status": gold_status,
            "seeded_by": gmeta.get("seeded_by"),
            "eval_only": gmeta.get("eval_only"),
            "headline": not reasons,
            "headline_reasons": reasons,
            "split": split,
            "split_defaulted": defaulted,
            "t": None if key == "structure" else t,
            "key": key,
            "nodes_out_of_scope": out_scope,
            "pairing_warnings": _pairing(pred, gold),
            "notes": notes,
        },
        "counts": counts,
        "headline_row": head_name,
        "s_f1": rows[head_name].get("s_f1"),  # the headline row's blocks, for quick reading
        "f_f1": rows[head_name].get("f_f1"),
        "rows": rows,
        "child_count": scorer.child_count(outcomes[head_t]),
        "guard": [{k: v for k, v in e.items() if k not in ("first", "last")} for e in guard.report],
    }
    if split == "dev":
        o = outcomes[head_t]
        by_p, by_g = pt.pos.__getitem__, gt.pos.__getitem__
        result["diagnostics"] = {
            "t": head_t,
            "fn_gold_ids": sorted(o["fn"], key=by_g),
            "fp_pred_ids": sorted(o["fp"], key=by_p),
            # review of E06, 2026-10-02, A1: the ids behind the row's fn_split / fp_by_kind /
            # tp_uncounted_pred, and the TP pairs themselves ([pred id, gold id])
            "tp_pairs": [[p, g] for p, g in sorted(o["tp"], key=lambda pg: by_p(pg[0]))],
            "tp_uncounted_pred_ids": sorted((p for p, _ in o["tp"] if elig_p[p] != COUNTED),
                                            key=by_p),
            "fn_frontier_gold_ids": sorted(o["fn_frontier"], key=by_g),
            "fn_frontier_line_detected_gold_ids": sorted(o["fn_frontier_detected"], key=by_g),
            "fn_cascaded_gold_ids": sorted(o["fn_cascaded"], key=by_g),
            "fp_pred_ids_by_kind": scorer.fp_kinds(o["fp"]),
        }
    return result


def summary(m: dict) -> str:
    """One line of aggregate numbers for the terminal."""
    s, d = m["settings"], m["disclosures"]
    row = m["rows"][m["headline_row"]]

    def f(x):
        return "n/a" if x is None else "%.3f" % x

    parts = ["%s split=%s key=%s %s:" % (s["gold_id"], s["split"], s["key"], m["headline_row"])]
    if row.get("available"):
        parts += ["S-F1 %s (P %s R %s; TP %d FP %d FN %d)" % (
                      f(row["s_f1"]["F"]), f(row["s_f1"]["P"]), f(row["s_f1"]["R"]),
                      row["s_f1"]["TP"], row["s_f1"]["FP"], row["s_f1"]["FN"]),
                  "F-F1 %s" % f(row["f_f1"]["F"])]
    else:
        parts.append("unavailable (no line order)")
    if s["mode"] == "locator" and m["headline_row"] != "t=1":
        r1 = m["rows"].get("t=1", {})
        parts.append("t=1 S-F1 %s" % (f(r1["s_f1"]["F"]) if r1.get("available") else "n/a"))
    parts.append("headline %s (gold_status %s)" % (str(d["headline"]).lower(), d["gold_status"]))
    return " ".join(parts)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="Score a predicted outline against a registered gold "
                                             "(docs/outliner-design.md §9; data/EVAL-SETS.md).")
    ap.add_argument("--pred", required=True, type=Path, help="predicted outline.json")
    ap.add_argument("--gold", required=True, help="registry dataset id (data/eval-sets.json)")
    ap.add_argument("--key", choices=KEYS, help="default: from the dataset (EVAL-SETS items 4, 12)")
    ap.add_argument("--t", type=int, default=0, help="line tolerance of the headline row")
    ap.add_argument("--split", choices=SPLIT_CHOICES, help="default: dev (split-scoped golds)")
    ap.add_argument("--frozen", help="tag of a frozen outliner (test, reserve, all, OOD need it)")
    ap.add_argument("--out", type=Path, help="write metrics.json here")
    args = ap.parse_args(argv)
    try:
        m = score(read_json(args.pred), args.gold, key=args.key, t=args.t, split=args.split,
                  frozen=args.frozen)
    except SplitViolation as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 2
    except (ScoreError, KeyError, FileNotFoundError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    if args.out:
        write_json(m, args.out)
    print(summary(m) + ("  -> %s" % repo_relative(args.out) if args.out else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
