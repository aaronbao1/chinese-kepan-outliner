"""chinese_workflow.eval.gold.sdp — import the 法華經數位資料庫 (sdp.chibs.edu.tw) 科判 as
two eval-only gold outlines (zh-kepan profile).

Input : data/raw/dila-sdp/ (scripts/fetch_dila_sdp.sh; gitignored, eval-only: Global
        Constraint 1, data/EVAL-SETS.md "Rules for gold data"; R04 F32):
          tree-T0262-full.json, tree-T1718-full.json
              nested getTreeNode trees {id, text, leaf, children} in server order (27 T1718
              nodes: children null + fetch_error)
          T0262-juan1..7.html, T1718-juan<k>.html (k = 1a..10b; only 9 of the 20 exist)
              sdp getHtml pages: nested <div class="content" id=…>, each with a
              <div class="head_title">【…】</div> head (link2oth links to other versions), and
              Taishō line anchors <a name="PPPPcLL" class="ref">
        data/raw/cbeta/T09n0262.xml, T34n1718.xml: line existence (chinese_workflow.ingest.lines)
Output: data/raw/dila-sdp/gold/T0262.zhiyi-wenju-sdp.outline.json   root-text gold (E03)
        data/raw/dila-sdp/gold/T1718.zhiyi-wenju-sdp.outline.json   commentary gold (E01)
        data/raw/dila-sdp/gold/crosswalk-T0262-T1718.tsv            one row per T0262 -> T1718 link
        stdout: counts (nodes, leaves, depth, links, unmapped by reason and by 卷-half)

Rules (Task 2 of docs/plans/2026-09-22-eval-datasets.md + the controller's resolutions of
2026-09-22, all stated below and in each gold's metadata.format_note):
  * Tree = the getTreeNode tree, node order = server order; ids assigned by common.number_tree.
    A fetch_error node is kept with its tree heading and a "fetch_error:" note; metadata.anomalies
    says whether its subtree is unknown or was recovered: when its content div is in the HTML, the
    divs between it and the next tree node become its subtree (HTML nesting gives the parent; a div
    opening a new page is attached to the recovered node one id level up). One whose subtree is
    unknown (non-leaf on the server, which is why its children were requested; none recovered)
    carries flag truncated: the gold does not encode its children (D15 addendum). Not flag
    coarsened, which would assert that the commentary stops subdividing.
  * heading_src = the head_title text inside 【…】, link labels excluded, edge whitespace stripped
    (text after 】, e.g. the server message 請回報管理員…, goes to a note); a node with no content
    div takes the bare head_title matched to it by position (headings and such nodes between two
    tree divs are paired from the end; a surplus heading is an anomaly), else the tree text.
    display_label = the heading's leading ordinal ("1", "1-5"), else null.
  * start (a Taishō lb) of a node with a content div = the first line anchor inside the div when it
    comes before the node's first text, otherwise the last anchor before that text (the line the
    text begins on; R03 F23's T0262D09_054). Text = everything but head_title headings, link labels
    and anchor labels. Fix round 1: when that first text does not occur on the CBETA line (see
    text_on_line: sdp inserts text CBETA lacks, e.g. 序品第一 before T1718D01_003), the node's first
    own anchor is used instead, with a note. A node without a content div whose pages exist
    (heading only) takes the start of its first pre-order descendant that has one, else the anchor
    before its bare heading. A node whose stretch lies in a page sdp does not serve (T1718
    卷-halves) gets no position, note "sdp T1718 HTML unavailable (卷 <k>)".
  * Flag anchor_inherited = the start is not an anchor observed in the node's own content: heading-
    only nodes; nodes with no anchor of their own (R04 F30's 188); nodes whose first text is verse
    after the block's anchored first line (sdp anchors only that line).
  * T0262 root_text = {start, end, basis "sdp-anchor", end_basis}; end = the node's last line,
    inclusive (schema; controller decision, fix round 1): the line before the successor's start
    (next node after the subtree) in CBETA line order when the successor begins its line, else the
    successor's start line, which the two share; the last node ends at the document's last anchor.
  * Links: every T1718 id inside a T0262 head's link2oth ids (7 are concatenations; noted). A link
    is used only when corroborated — the two sdp nodes share a heading (heading_src or tree text,
    sdp's leading ordinal aside);
    sdp's links are ids, not checked correspondences (R04 F31), and uncorroborated ones are mostly
    inconsistent with the tree around them. T0262 commentary.explained = the T1718 start of the
    first used link, else null (reason noted). T1718 commentary.explained = its own start,
    announced = null (sdp does not record it); root_text = the span of the first T0262 node
    (document order) with a used link to it, dropped (noted) when it breaks nesting with the
    nearest ancestor span or order with the elder siblings in the T1718 tree.
  * Flag unmapped (controller decision, fix round 1) = this gold's primary locator is missing:
    root_text in the T0262 gold, commentary.explained in the T1718 gold. A missing secondary
    locator is only noted — except that a T1718 node without root_text keeps the flag, which the
    schema's sūtra-mode rule requires (scripts/validate_outline.py [sutra-span-unmapped]).
  * Every linehead is checked against the CBETA file; a missing line is set to null and noted,
    never kept.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
from itertools import pairwise
from pathlib import Path

from chinese_workflow.eval.gold import common
from chinese_workflow.ingest.lines import strip_punct

SCHEME_ID = "zhiyi-wenju-sdp"
CBETA_RELEASE = "2026R2"
SDP_URL = "http://sdp.chibs.edu.tw/ui.html"

LB_RE = re.compile(r"^[0-9]{4}[a-z][0-9]{2}\Z")
ORDINAL_RE = re.compile(r"^([0-9]+(?:-[0-9]+)?)\s")
APP_NOTE_RE = re.compile(r"〔[^〕]*〕|【[^】]*】")  # sdp's inline apparatus, e.g. 〔上〕－【甲】
APP_MARKS = str.maketrans("", "", "＋＝－")
TEXT_PREFIX = 8
SID_RE = re.compile(r"^(?P<doc>.+?)D(?P<level>[0-9]+)_(?P<seq>[0-9]+)\Z")
_VOID = frozenset(
    ["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"]
)


# ------------------------------------------------------------------------------------ HTML reading


@dataclass
class Title:
    """One sdp head_title: raw text (link labels excluded), its link2oth ids, where it stands."""

    raw: str
    links: list
    anchor_before: str | None  # last line anchor before the heading, across pages
    owner: str | None  # content div whose head it is; None = a bare heading
    key: str  # page key ("1", "3a", …)
    at_line_start: bool = True  # no body text between anchor_before and the heading


@dataclass
class Div:
    id: str
    key: str
    parent: str | None  # enclosing content div on the same page
    title: Title | None = None
    start: str | None = None  # lb n
    inherited: bool = False  # start came from the anchor before the div's first text
    exact: bool = True  # False: the first text sits in verse after the anchored first verse line
    anchors: int = 0  # line anchors inside the div (nested divs included)
    first_anchor: str | None = None  # first line anchor inside the div, before or after its text
    first_text: str | None = None  # the text that resolved the start (when inherited)
    at_line_start: bool = True  # the div's content begins a line (no text since the anchor)


@dataclass
class Pages:
    """The HTML pages of one document read in order: divs, and the document order of content
    divs and bare headings."""

    divs: dict = field(default_factory=dict)
    order: list = field(default_factory=list)  # ("div", id) | ("bare", Title)
    last_anchor: str | None = None
    doc_title: str | None = None
    stray_links: list = field(default_factory=list)  # link2oth ids outside any head_title


class _PageEvents(HTMLParser):
    """Flat event stream of one sdp getHtml page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events: list = []
        self.stack: list = []  # [tag, classes, extra]
        self.pending_owner: str | None = None  # content div whose head may open next
        self.capture: list | None = None  # [text parts, link ids, owner] inside a head_title
        self.doc_title_parts: list = []

    def _inside(self, tag: str, cls: str) -> bool:
        return any(t == tag and cls in c for t, c, _ in self.stack)

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            return
        a = dict(attrs)
        cls = set((a.get("class") or "").split())
        extra = None
        if tag == "div" and "content" in cls:
            self.events.append(("open", a.get("id")))
            self.pending_owner = a.get("id")
            self.stack.append([tag, cls, None])
            return
        if tag == "div" and "head" in cls:
            extra = self.pending_owner
        elif tag == "div" and "head_title" in cls:
            owner = next(
                (x for t, c, x in reversed(self.stack) if t == "div" and "head" in c), None
            )
            self.capture = [[], [], owner]
        elif tag == "a" and "ref" in cls:
            self.events.append(("anchor", a.get("name")))
        elif tag == "a" and "link2oth" in cls:
            if self.capture is not None:
                self.capture[1].append(a.get("id"))
            else:
                self.events.append(("stray_link", a.get("id")))
        self.pending_owner = None
        self.stack.append([tag, cls, extra])

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k][0] == tag:
                for t, c, _ in reversed(self.stack[k:]):
                    if t == "div" and "content" in c:
                        self.events.append(("close", None))
                    elif t == "div" and "head_title" in c and self.capture is not None:
                        parts, links, owner = self.capture
                        self.events.append(("title", "".join(parts), links, owner))
                        self.capture = None
                del self.stack[k:]
                return

    def handle_data(self, data):
        if self._inside("a", "ref") or self._inside("a", "link2oth"):
            return
        if self.capture is not None:
            self.capture[0].append(data)
            return
        if self._inside("div", "docTitle"):
            self.doc_title_parts.append(data)
        if data.strip():
            self.pending_owner = None
            self.events.append(("text", data, self._inside("table", "lg_table")))

    def finish(self) -> list:
        self.close()
        while self.stack:  # unclosed elements at end of page
            self.handle_endtag(self.stack[-1][0])
        return self.events


def read_pages(pages: list) -> Pages:
    """[(key, html text)] in reading order -> Pages. A div's start is resolved by its first anchor
    or first text, whichever comes first (module docstring)."""
    out = Pages()
    unresolved: set = set()
    verse_since_anchor = False  # sdp anchors only the first line of a verse block (R04 F30)
    text_since_anchor = False
    for key, text in pages:
        parser = _PageEvents()
        parser.feed(text)
        events = parser.finish()
        if out.doc_title is None and parser.doc_title_parts:
            out.doc_title = " ".join("".join(parser.doc_title_parts).split())
        stack: list = []
        for ev in events:
            kind = ev[0]
            if kind == "anchor":
                name = ev[1]
                if not isinstance(name, str) or not LB_RE.match(name):
                    raise ValueError("page %s: line anchor with unexpected name %r" % (key, name))
                for d in stack:
                    out.divs[d].anchors += 1
                    out.divs[d].first_anchor = out.divs[d].first_anchor or name
                    if d in unresolved:
                        out.divs[d].start, out.divs[d].inherited = name, False
                        unresolved.discard(d)
                out.last_anchor, verse_since_anchor, text_since_anchor = name, False, False
            elif kind == "text":
                for d in stack:
                    if d in unresolved:
                        div = out.divs[d]
                        div.start, div.inherited, div.exact = (
                            out.last_anchor,
                            True,
                            not verse_since_anchor,
                        )
                        div.first_text, div.at_line_start = ev[1], not text_since_anchor
                        unresolved.discard(d)
                verse_since_anchor = verse_since_anchor or ev[2]
                text_since_anchor = True
            elif kind == "open":
                did = ev[1]
                if not did:
                    raise ValueError("page %s: content div without id" % key)
                if did in out.divs:
                    raise ValueError("page %s: content div %s occurs twice" % (key, did))
                out.divs[did] = Div(did, key, stack[-1] if stack else None)
                stack.append(did)
                unresolved.add(did)
                out.order.append(("div", did))
            elif kind == "close":
                stack.pop()
            elif kind == "stray_link":
                out.stray_links.append(ev[1])
            elif kind == "title":
                _, raw, links, owner = ev
                t = Title(
                    raw.strip(), list(links), out.last_anchor, owner, key, not text_since_anchor
                )
                if owner is not None and owner in out.divs and out.divs[owner].title is None:
                    out.divs[owner].title = t
                else:
                    t.owner = None
                    out.order.append(("bare", t))
    return out


def split_title(raw: str) -> tuple:
    """'【1 甲】…' -> ('1 甲', '…'): the heading inside the first 【…】 and any text after it."""
    raw = raw.strip()
    if raw.startswith("【") and "】" in raw:
        i = raw.index("】")
        return raw[1:i].strip(), raw[i + 1 :].strip()
    return raw, ""


def display_label(heading: str) -> str | None:
    m = ORDINAL_RE.match(heading)
    return m.group(1) if m else None


# ----------------------------------------------------------------------------- tree + HTML merge


@dataclass
class SdpSource:
    doc: str  # sdp document id, e.g. "T0262"
    cbeta_id: str  # CBETA file id of its text, e.g. "T09n0262"
    tree: Path
    html: list  # [(key, Path)] every page of the document in reading order; missing files allowed
    title_en: str = ""


@dataclass
class SdpNode:
    sid: str
    depth: int
    parent: str | None
    children: list = field(default_factory=list)
    tree_text: str | None = None  # None: recovered from the HTML
    fetch_error: str | None = None
    recovered: bool = False
    title: Title | None = None  # own head, or the bare heading matched to it
    title_is_bare: bool = False
    has_div: bool = False
    start: str | None = None  # lb n
    start_how: str | None = None  # anchor | before-anchor | descendant | bare-heading
    start_from: str | None = None  # descendant whose start was taken
    at_line_start: bool = True  # the node's content begins a line (end rule of its predecessor)
    start_notes: list = field(default_factory=list)
    own_anchors: int = 0  # line anchors inside its content div
    exact: bool = True  # False: first text in verse after the block's anchored first line
    gap: str | None = None  # unavailable pages the node falls in, e.g. "7a–10b"


@dataclass
class Resolved:
    source: SdpSource
    nodes: dict  # sid -> SdpNode
    preorder: list  # sids
    pages: Pages
    available: list  # page keys read
    missing: list  # page keys not on disk
    anomalies: list


def _walk(tree: list, depth: int = 1, parent: str | None = None):
    for n in tree:
        yield n, depth, parent
        yield from _walk(n.get("children") or [], depth + 1, n["id"])


def _sid_level(sid: str) -> int | None:
    m = SID_RE.match(sid)
    return int(m.group("level")) if m else None


def _gap_label(keys: list) -> str:
    return keys[0] if len(keys) == 1 else "%s–%s" % (keys[0], keys[-1])


def _lcs(a: str, b: str) -> int:
    """Length of the longest common subsequence of two short strings."""
    prev = [0] * (len(b) + 1)
    for ch in a:
        cur = [0]
        for j, bj in enumerate(b):
            cur.append(prev[j] + 1 if ch == bj else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def text_on_line(text: str, line: str) -> bool:
    """Does sdp text occur on a CBETA line? sdp's inline apparatus (〔…〕, 【甲】 sigla, ＋ ＝ －)
    is removed and punctuation ignored (ingest.lines.strip_punct); the first TEXT_PREFIX
    characters count as found when at least half of them occur in order on the line — sdp's
    edition differs from CBETA's here and there (父母念子 vs 父每念子, T09n0262_p0016c05), while an
    sdp insertion shares nothing with the line (序品第一 vs 者也。, T34n1718_p0003a18). A text
    chunk may run on past the line only in unanchored verse, hence the prefix. Text with nothing
    left to compare counts as found."""
    t = strip_punct(APP_NOTE_RE.sub("", text).translate(APP_MARKS))[:TEXT_PREFIX]
    return not t or 2 * _lcs(t, strip_punct(line)) >= len(t)


def resolve(source: SdpSource, line_texts: dict | None = None) -> Resolved:
    """Merge the tree with the HTML pages (module docstring). line_texts: {linehead: text} of the
    source's CBETA file, used to check that a start taken from the anchor before a node's first
    text really carries that text (None: no check)."""
    tree = json.loads(source.tree.read_text(encoding="utf-8"))
    available = [k for k, p in source.html if Path(p).exists()]
    missing = [k for k, p in source.html if not Path(p).exists()]
    key_index = {k: i for i, (k, _) in enumerate(source.html)}
    pages = read_pages(
        [(k, Path(p).read_text(encoding="utf-8")) for k, p in source.html if k in available]
    )
    anomalies: list = []

    nodes: dict = {}
    preorder: list = []
    for n, depth, parent in _walk(tree):
        node = SdpNode(
            n["id"], depth, parent, tree_text=n.get("text"), fetch_error=n.get("fetch_error")
        )
        nodes[n["id"]] = node
        preorder.append(n["id"])
        if parent is not None:
            nodes[parent].children.append(n["id"])
    pos = {item[1]: i for i, item in enumerate(pages.order) if item[0] == "div"}

    # recover the subtree of a fetch_error node from the HTML divs between it and the next tree node
    for sid in [s for s in preorder if nodes[s].fetch_error and s in pos]:
        k = preorder.index(sid)
        nxt = next((s for s in preorder[k + 1 :] if s in pos), None)
        lo, hi = pos[sid], pos[nxt] if nxt else len(pages.order)
        extra = [it[1] for it in pages.order[lo + 1 : hi] if it[0] == "div" and it[1] not in nodes]
        added: list = []
        for did in extra:
            html_parent = pages.divs[did].parent
            parent = html_parent if html_parent in added or html_parent == sid else None
            if html_parent is None:  # opens a new page: attach to the deepest open recovered node
                want = (_sid_level(did) or 0) - 1
                cands = [s for s in [sid] + added if _sid_level(s) == want]
                parent = cands[-1] if cands else None
            if parent is None or _sid_level(did) != nodes[parent].depth + 1:
                anomalies.append(
                    "HTML div %s near fetch_error node %s could not be placed; ignored" % (did, sid)
                )
                continue
            nodes[did] = SdpNode(did, nodes[parent].depth + 1, parent, recovered=True)
            nodes[parent].children.append(did)
            added.append(did)
        if added:
            # insert the recovered nodes after sid in pre-order (their HTML order is pre-order)
            preorder[k + 1 : k + 1] = added
    if pages.stray_links:
        anomalies.append(
            "%d link2oth links outside any sdp heading ignored: %s"
            % (len(pages.stray_links), ", ".join(map(str, pages.stray_links[:10])))
        )
    stray = [it[1] for it in pages.order if it[0] == "div" and it[1] not in nodes]
    for did in stray:
        anomalies.append("HTML content div %s is not in the tree; ignored" % did)

    # the HTML's div order must be the tree's pre-order restricted to div-bearing nodes
    with_div = [s for s in preorder if s in pos]
    if any(pos[a] >= pos[b] for a, b in pairwise(with_div)):
        raise ValueError("%s: HTML div order disagrees with the tree's pre-order" % source.doc)
    for sid in with_div:
        node, div = nodes[sid], pages.divs[sid]
        node.has_div, node.title = True, div.title
        node.own_anchors, node.exact = div.anchors, div.exact
        node.at_line_start = div.at_line_start
        if div.start is not None:
            node.start = div.start
            node.start_how = "before-anchor" if div.inherited else "anchor"
        lh = common.compose_linehead(source.cbeta_id, div.start) if div.start else None
        if (
            line_texts is not None
            and div.inherited
            and div.exact
            and div.first_text
            and lh in line_texts
            and not text_on_line(div.first_text, line_texts[lh])
        ):
            shown = " ".join(div.first_text.split())[:20]
            if div.first_anchor and div.first_anchor != div.start:
                node.start_notes.append(
                    "sdp text %s before the node's first own anchor is not on CBETA line %s "
                    "(sdp-inserted); start = its first own anchor %s"
                    % (shown, lh, div.first_anchor)
                )
                node.start, node.start_how, node.at_line_start = (
                    div.first_anchor,
                    "own-anchor",
                    True,
                )
            else:
                node.start_notes.append(
                    "sdp text %s is not on CBETA line %s, and the node has no later anchor of "
                    "its own; start kept" % (shown, lh)
                )

    # nodes without a div: heading-only (their pages exist) or in a gap (a page is missing)
    div_positions = [preorder.index(s) for s in with_div]
    for k, sid in enumerate(preorder):
        node = nodes[sid]
        if node.has_div:
            continue
        before = [p for p in div_positions if p < k]
        after = [p for p in div_positions if p > k]
        lo = key_index[pages.divs[preorder[before[-1]]].key] if before else -1
        hi = key_index[pages.divs[preorder[after[0]]].key] if after else len(source.html)
        gap = [key for key, _ in source.html[lo + 1 : hi] if key in missing]
        if gap:
            node.gap = _gap_label(gap)

    # Bare headings and heading-only nodes, each grouped by the tree div that follows them
    # (its position in pages.order; len(order) = end of document); within a group they are
    # matched in order, aligned at the end (the heading nearest the div goes to the node nearest
    # it). Surplus headings are anomalies; a node left without one keeps its tree text.
    end = len(pages.order)
    bare_groups: dict = defaultdict(list)
    waiting: list = []
    for i, item in enumerate(pages.order):
        if item[0] == "bare":
            waiting.append(item[1])
        elif item[1] in nodes and waiting:
            bare_groups[i], waiting = waiting, []
    if waiting:
        bare_groups[end] = waiting
    node_groups: dict = defaultdict(list)
    for k, sid in enumerate(preorder):
        if not nodes[sid].has_div and not nodes[sid].gap:
            nxt = next((s for s in preorder[k + 1 :] if nodes[s].has_div), None)
            node_groups[pos[nxt] if nxt else end].append(sid)
    for p in sorted(set(bare_groups) | set(node_groups)):
        titles, sids = bare_groups.get(p, []), node_groups.get(p, [])
        m = min(len(titles), len(sids))
        for sid, t in zip(sids[len(sids) - m :], titles[len(titles) - m :]):
            nodes[sid].title, nodes[sid].title_is_bare = t, True
        for t in titles[: len(titles) - m]:
            anomalies.append(
                "bare heading %s (page %s, after line %s) matches no tree node"
                % (t.raw, t.key, t.anchor_before)
            )

    # starts of heading-only nodes (never of gap nodes), innermost first
    for sid in reversed(preorder):
        node = nodes[sid]
        if node.has_div or node.gap:
            continue
        first = next((d for d in _descendants(nodes, sid) if nodes[d].start), None)
        if first is not None:
            node.start, node.start_how, node.start_from = nodes[first].start, "descendant", first
            node.at_line_start = nodes[first].at_line_start
        elif node.title is not None and node.title.anchor_before:
            node.start, node.start_how = node.title.anchor_before, "bare-heading"
            node.at_line_start = node.title.at_line_start
    for sid in preorder:
        if nodes[sid].fetch_error:
            what = (
                "its subtree was recovered from the HTML"
                if nodes[sid].children
                else "its subtree is unknown"
            )
            anomalies.append("%s: sdp getTreeNode failed for it (fetch_error); %s" % (sid, what))
    return Resolved(source, nodes, preorder, pages, available, missing, anomalies)


def _descendants(nodes: dict, sid: str):
    for c in nodes[sid].children:
        yield c
        yield from _descendants(nodes, c)


# ---------------------------------------------------------------------------------- node content


def node_heading(node: SdpNode) -> tuple:
    """(heading_src, evidence, notes) of a resolved node (module docstring)."""
    notes: list = []
    tree_text = node.tree_text.strip() if node.tree_text is not None else None
    if node.title is not None:
        heading, extra = split_title(node.title.raw)
        shown = node.title.raw[: node.title.raw.index("】") + 1] if extra else node.title.raw
        evidence = "sdp head_title %s (page %s)" % (shown, node.title.key)
        if extra:
            notes.append("sdp head_title text after 】, not part of the heading: %s" % extra)
        if node.title_is_bare:
            notes.append(
                "no content div in the sdp HTML; heading from the bare sdp heading on page %s"
                % node.title.key
            )
        if tree_text is not None and tree_text != heading:
            notes.append("sdp tree text differs: %s" % tree_text)
    else:
        heading = tree_text or ""
        evidence = "sdp tree text %s" % heading
        notes.append("heading from the sdp tree JSON (no sdp HTML heading for this node)")
    if not heading:
        notes.append(
            "no heading available: sdp gives this node an empty text"
            + ("" if node.title is not None else " and serves no HTML heading for it")
        )
    if node.recovered:
        notes.append(
            "recovered from the sdp HTML (page %s): not in the getTreeNode tree, whose "
            "request for its fetch_error ancestor failed" % (node.title.key if node.title else "?")
        )
    if node.fetch_error:
        notes.append(
            "fetch_error: sdp getTreeNode failed for this node (%s); %s"
            % (
                " ".join(node.fetch_error.split())[:120],
                "children recovered from the sdp HTML"
                if node.children
                else "its subtree is unknown, so it appears here without children",
            )
        )
    return heading, evidence, notes


def node_start(node: SdpNode, doc: str) -> tuple:
    """(lb n or None, flags, notes) for the start rules of the module docstring; flags holds
    anchor_inherited only (unmapped is set by the drafts, from the gold's primary locator)."""
    flags: list = []
    notes: list = list(node.start_notes)
    if node.start is None:
        notes.append(
            "sdp %s HTML unavailable (卷 %s)" % (doc, node.gap)
            if node.gap
            else "no start line found in the sdp HTML"
        )
        return None, flags, notes
    if node.start_how == "descendant":
        flags.append("anchor_inherited")
        notes.append(
            "no content div in the sdp HTML (heading only): start = that of its first "
            "descendant with one (%s)" % node.start_from
        )
    elif node.start_how == "bare-heading":
        flags.append("anchor_inherited")
        notes.append(
            "no content div and no located descendant in the sdp HTML: start = the line "
            "anchor before its bare sdp heading"
        )
    elif node.start_how == "before-anchor":
        if node.own_anchors == 0:
            flags.append("anchor_inherited")
            notes.append(
                "no line anchor of its own in the sdp HTML: start = the anchor before its "
                "first text"
            )
        elif not node.exact:
            flags.append("anchor_inherited")
            notes.append(
                "first text inside a verse block after its anchored first line: start = "
                "the last anchor before it (sdp anchors only a block's first line)"
            )
    return node.start, flags, notes


def _checked(lines, cbeta_id: str, lb: str | None, what: str, notes: list):
    """Compose a linehead and check that the CBETA file has it; a missing line -> None and a note
    (the drafts flag a missing primary locator)."""
    if lb is None:
        return None
    lh = common.compose_linehead(cbeta_id, lb)
    if lines is not None and lh not in lines:
        notes.append(
            "%s %s is not a line of %s (CBETA %s); dropped" % (what, lh, cbeta_id, CBETA_RELEASE)
        )
        return None
    return lh


def link_ids(title: Title | None, doc: str) -> tuple:
    """(link2oth ids into `doc`, notes): every well-formed `doc` id found inside a link id, in
    order, without repeats. sdp has 7 malformed ids in T0262's HTML (R04 F31), concatenations
    such as 'EN-KN…T1718…' or two T1718 ids run together; each is read as the ids it contains,
    with a note."""
    out: list = []
    notes: list = []
    pat = re.compile(r"%sD[0-9]+_[0-9]+" % re.escape(doc))
    for raw in title.links if title else []:
        parts = pat.findall(raw or "")
        if not parts:
            continue
        if parts != [raw]:
            notes.append("malformed sdp link id %s read as %s" % (raw, " + ".join(parts)))
        out.extend(x for x in parts if x not in out)
    return out, notes


def _flags(*groups) -> list:
    out: list = []
    for g in groups:
        for f in g:
            if f not in out:
                out.append(f)
    return out


# ----------------------------------------------------------------------------------- the two golds


@dataclass
class Golds:
    root: dict  # T0262 gold document
    commentary: dict  # T1718 gold document
    crosswalk: list  # rows (header first)
    stats: dict


def _spans(res: Resolved, line_order: list | None, compare) -> dict:
    """sid -> (start lb, end lb, end_basis). end = the node's last line, inclusive (schema
    root_text_span; controller decision, fix round 1): with successor = the next node after the
    subtree that has a start, the line before the successor's start in the CBETA file's line order
    when the successor begins at the start of its line, else the successor's start line (shared);
    never before the node's own start. The last node ends at the document's last anchor."""
    order = res.preorder
    index = {s: i for i, s in enumerate(order)}
    position = {lh.split("_p")[1]: i for i, lh in enumerate(line_order or [])}
    size: dict = {}
    for sid in reversed(order):
        size[sid] = 1 + sum(size[c] for c in res.nodes[sid].children)
    out = {}
    for sid in order:
        node = res.nodes[sid]
        if node.start is None:
            continue
        succ = next(
            (res.nodes[s] for s in order[index[sid] + size[sid] :] if res.nodes[s].start), None
        )
        if succ is None:
            out[sid] = (node.start, res.pages.last_anchor, "sdp-anchor")
            continue
        end = succ.start
        k = position.get(succ.start)
        if succ.at_line_start and k:
            prev = line_order[k - 1].split("_p")[1]
            key = res.source.cbeta_id + "_p"
            if (compare(key + node.start, key + prev) or 0) <= 0:
                end = prev
            else:
                end = node.start
        out[sid] = (node.start, end, "next-node")
    return out


def strip_ordinal(heading: str) -> str:
    """'2 合成甲' -> '合成甲': the heading without sdp's leading ordinal (see display_label)."""
    m = ORDINAL_RE.match(heading)
    return heading[m.end() :].strip() if m else heading.strip()


def _names(node: SdpNode) -> set:
    """The sdp headings a node is known by (heading_src and tree text), ordinals stripped."""
    names = {node_heading(node)[0]}
    if node.tree_text is not None:
        names.add(node.tree_text)
    return {strip_ordinal(x) for x in names} - {""}


def corroborated(a: SdpNode, b: SdpNode) -> bool:
    """A link between two sdp nodes is corroborated when they share a heading, sdp's leading
    ordinals aside ('2 合成甲' ~ '3 合成甲')."""
    return bool(_names(a) & _names(b))


def link_status(
    rres: Resolved, cres: Resolved, root_sid: str, com_sid: str, com_explained: dict
) -> str:
    """How a T0262 -> T1718 link is used: not-in-tree | gap-<k> | uncorroborated | unlocated |
    located. A link is corroborated when the two sdp nodes share a heading (heading_src or tree
    text): sdp's links are ids, not checked correspondences (R04 F31), and a link whose headings
    differ is mostly inconsistent with the tree around it (the crosswalk's uncorroborated rows)."""
    if com_sid not in cres.nodes:
        return "not-in-tree"
    if cres.nodes[com_sid].gap:
        return "gap-%s" % cres.nodes[com_sid].gap
    if not corroborated(rres.nodes[root_sid], cres.nodes[com_sid]):
        return "uncorroborated"
    return "located" if com_explained[com_sid][0] else "unlocated"


def _status_class(status: str) -> str:
    return "gap" if status.startswith("gap-") else status


def build_golds(root_src: SdpSource, com_src: SdpSource, root_lines=None, com_lines=None) -> Golds:
    """Resolve both sdp documents and build the T0262 (root-text) and T1718 (commentary) golds.
    root_lines / com_lines: the CBETA lines to check against — a {linehead: text} mapping in the
    file's line order (common.line_texts; enables the text check and the inclusive root_text.end)
    or a set of lineheads (existence only); None = unchecked."""
    rtexts = root_lines if isinstance(root_lines, Mapping) else None
    ctexts = com_lines if isinstance(com_lines, Mapping) else None
    rres, cres = resolve(root_src, rtexts), resolve(com_src, ctexts)
    R, C = root_src.doc, com_src.doc
    stats: dict = {
        "root": Counter(),
        "commentary": Counter(),
        "links": Counter(),
        "unmapped_by_gap": Counter(),
    }
    compare = common.load_validator().compare_refs

    # commentary starts (T1718 explained) and root spans (T0262), line-checked
    com_explained: dict = {}  # T1718 sid -> (linehead | None, flags, notes)
    for sid in cres.preorder:
        lb, flags, notes = node_start(cres.nodes[sid], C)
        com_explained[sid] = (
            _checked(com_lines, com_src.cbeta_id, lb, "start", notes),
            flags,
            notes,
        )
    root_span: dict = {}  # T0262 sid -> ((start lh, end lh, end_basis) | None, flags, notes)
    spans = _spans(rres, list(rtexts) if rtexts is not None else None, compare)
    for sid in rres.preorder:
        lb, flags, notes = node_start(rres.nodes[sid], R)
        start = _checked(root_lines, root_src.cbeta_id, lb, "start", notes)
        end = (
            _checked(root_lines, root_src.cbeta_id, spans[sid][1], "end", notes) if start else None
        )
        root_span[sid] = ((start, end, spans[sid][2]) if start else None, flags, notes)

    # T0262 -> T1718 links and their status
    links: dict = {}
    link_notes: dict = {}
    status: dict = {}  # (root sid, com sid) -> status
    linkers: dict = defaultdict(list)  # com sid -> root sids linking to it, document order
    corroborating: dict = defaultdict(list)  # the same, restricted to corroborated links
    for sid in rres.preorder:
        links[sid], link_notes[sid] = link_ids(rres.nodes[sid].title, com_src.doc)
        for t in links[sid]:
            st = status[(sid, t)] = link_status(rres, cres, sid, t, com_explained)
            stats["links"][_status_class(st)] += 1
            if sid not in linkers[t]:
                linkers[t].append(sid)
                if t in cres.nodes and corroborated(rres.nodes[sid], cres.nodes[t]):
                    corroborating[t].append(sid)

    def root_draft(sid: str) -> dict:
        node = rres.nodes[sid]
        heading, evidence, notes = node_heading(node)
        span, sflags, snotes = root_span[sid]
        flags, notes = list(sflags), notes + snotes + link_notes[sid]
        used = next((t for t in links[sid] if status[(sid, t)] == "located"), None)
        explained = com_explained[used][0] if used else None
        st = stats["root"]
        if not links[sid]:
            notes.append("no 文句 (%s) link in sdp: commentary position unknown" % C)
            st["no explained: no commentary link"] += 1
        elif used is None:
            why = []
            for t in links[sid]:
                s = status[(sid, t)]
                if s == "not-in-tree":
                    why.append(
                        "%s is not a node of the sdp %s tree (whose subtrees under "
                        "fetch_error nodes are unknown)" % (t, C)
                    )
                elif s.startswith("gap-"):
                    why.append("%s: sdp %s HTML unavailable (卷 %s)" % (t, C, s[4:]))
                elif s == "uncorroborated":
                    why.append("%s: headings differ (sdp link not corroborated)" % t)
                else:
                    why.append("%s has no start line" % t)
            notes.append("commentary position unknown: " + "; ".join(why))
            first = status[(sid, links[sid][0])]
            st["no explained: commentary link %s" % _status_class(first)] += 1
            if first.startswith("gap-"):
                stats["unmapped_by_gap"][
                    "root nodes whose linked node is in 卷 %s" % first[4:]
                ] += 1
        if len(links[sid]) > 1:
            notes.append(
                "several 文句 links (%s); explained from %s" % (", ".join(links[sid]), used)
            )
        if span is None:
            flags.append("unmapped")  # this gold's primary locator
            st["unmapped: no root span"] += 1
        st["with commentary link"] += bool(links[sid])
        st["with commentary link, content-div nodes"] += bool(links[sid]) and node.has_div
        st["commentary link used (explained set)"] += used is not None
        commentary = {"announced": None, "explained": explained}
        if links[sid]:
            commentary["raw"] = "sdp 文句 link " + " ".join(links[sid])
        root = None
        if span is not None:
            root = {
                "start": span[0],
                "end": span[1],
                "basis": "sdp-anchor",
                "end_basis": span[2],
                "raw": "sdp anchors %s-%s"
                % tuple(x.split("_p")[1] if x else "?" for x in span[:2]),
            }
        if node.fetch_error and not node.children:  # children unknown: see the docstring
            flags.append("truncated")
        return _draft(
            heading,
            sid,
            flags,
            root,
            commentary,
            evidence,
            notes,
            [root_draft(c) for c in node.children],
        )

    def com_draft(sid: str, parent_span, elder_starts: list) -> dict:
        """elder_starts: root_text.start of the elder siblings already emitted (the list is
        extended with this node's start)."""
        node = cres.nodes[sid]
        heading, evidence, notes = node_heading(node)
        explained, sflags, snotes = com_explained[sid]
        flags, notes = list(sflags), notes + snotes
        st = stats["commentary"]
        if node.gap:
            stats["unmapped_by_gap"]["commentary nodes in 卷 %s" % node.gap] += 1
        if explained is None:
            flags.append("unmapped")  # this gold's primary locator
            st["unmapped: no explained line"] += 1
        corr = corroborating.get(sid, [])
        mine = [s for s in corr if root_span[s][0] is not None]
        others = [s for s in linkers.get(sid, []) if s not in corr]
        root = None
        if mine:
            s0 = mine[0]
            start, end, end_basis = root_span[s0][0]
            clash = None
            if parent_span and (
                (compare(parent_span[0], start) or 0) > 0
                or (end and parent_span[1] and (compare(end, parent_span[1]) or 0) > 0)
            ):
                clash = "outside its parent's root span %s-%s" % parent_span
            elif elder_starts and (compare(elder_starts[-1], start) or 0) > 0:
                clash = "before an elder sibling's root span start %s" % elder_starts[-1]
            if clash:
                notes.append(
                    "span %s-%s of %s node %s (corroborated sdp link) lies %s in this "
                    "tree; not used" % (start, end, R, s0, clash)
                )
                st["no root span: corroborated span breaks nesting"] += 1
            else:
                root = {
                    "start": start,
                    "end": end,
                    "basis": "sdp-anchor",
                    "end_basis": end_basis,
                    "raw": "span of %s node %s, which links here (sdp 文句 link, same heading)"
                    % (R, s0),
                }
                elder_starts.append(start)
                if len(mine) > 1:
                    notes.append(
                        "linked from several %s nodes (%s); root span from %s"
                        % (R, ", ".join(mine), s0)
                    )
        elif corr:
            notes.append(
                "the %s node(s) %s linking here have no root-text span" % (R, ", ".join(corr))
            )
            st["no root span: linking node has no root span"] += 1
        elif others:
            notes.append(
                "%s node(s) %s link here but share no heading with it (sdp link not "
                "corroborated): root-text span not used" % (R, ", ".join(others))
            )
            st["no root span: link uncorroborated"] += 1
        else:
            notes.append("no %s node links here in sdp: root-text span unknown" % R)
            st["no root span: no root-text link"] += 1
        if root is None:  # the schema's sūtra-mode rule [sutra-span-unmapped] requires the flag
            flags.append("unmapped")
        own_span = (root["start"], root["end"]) if root else None
        kids: list = []
        kid_starts: list = []
        for c in node.children:  # a child's span must lie inside the nearest ancestor span
            kids.append(com_draft(c, own_span or parent_span, kid_starts))
        if node.fetch_error and not node.children:  # children unknown: see the docstring
            flags.append("truncated")
        return _draft(
            heading,
            sid,
            flags,
            root,
            {"announced": None, "explained": explained},
            evidence,
            notes,
            kids,
        )

    root_nodes = common.number_tree(
        [root_draft(s) for s in rres.preorder if rres.nodes[s].parent is None]
    )
    top_starts: list = []
    com_nodes = common.number_tree(
        [com_draft(s, None, top_starts) for s in cres.preorder if cres.nodes[s].parent is None]
    )

    rid = {n["source_node_id"]: n for n in root_nodes}
    cid = {n["source_node_id"]: n for n in com_nodes}
    r, c = R.lower(), C.lower()
    crosswalk = [
        [
            r + "_sdp_id",
            r + "_gold_id",
            r + "_start",
            c + "_sdp_id",
            c + "_gold_id",
            c + "_explained",
            "status",
            "corroborated",
        ]
    ]
    for sid in rres.preorder:
        for t in links[sid]:
            rn, cn = rid[sid], cid.get(t)
            rt = rn["locations"]["root_text"]
            exp = cn["locations"]["commentary"]["explained"] if cn else None
            crosswalk.append(
                [
                    sid,
                    rn["id"],
                    rt["start"] if rt else "",
                    t,
                    cn["id"] if cn else "",
                    exp or "",
                    status[(sid, t)],
                    "n/a" if cn is None else "yes" if sid in corroborating[t] else "no",
                ]
            )

    for label, nodes, res in (("root", root_nodes, rres), ("commentary", com_nodes, cres)):
        st = stats[label]
        st["nodes"] = len(nodes)
        st["leaves"] = sum(1 for n in nodes if not res.nodes[n["source_node_id"]].children)
        st["max_depth"] = max(n["level"] for n in nodes)
        st["flag unmapped"] = sum("unmapped" in n["flags"] for n in nodes)
        st["flag anchor_inherited"] = sum("anchor_inherited" in n["flags"] for n in nodes)
        st["with root_text span"] = sum(n["locations"]["root_text"] is not None for n in nodes)
        st["with commentary.explained"] = sum(
            n["locations"]["commentary"]["explained"] is not None for n in nodes
        )
        st["fetch_error nodes"] = sum(
            1 for n in nodes if res.nodes[n["source_node_id"]].fetch_error
        )
        st["recovered from HTML"] = sum(
            1 for n in nodes if res.nodes[n["source_node_id"]].recovered
        )
        for how, cnt in Counter(res.nodes[n["source_node_id"]].start_how for n in nodes).items():
            st["start: %s" % how] = cnt
        st["content-div nodes"] = sum(1 for n in nodes if res.nodes[n["source_node_id"]].has_div)
        st["anchor_inherited: no anchor of its own"] = sum(
            1
            for n in nodes
            if res.nodes[n["source_node_id"]].start_how == "before-anchor"
            and res.nodes[n["source_node_id"]].own_anchors == 0
        )
        st["anchor_inherited: verse after first line"] = sum(
            1
            for n in nodes
            if res.nodes[n["source_node_id"]].start_how == "before-anchor"
            and res.nodes[n["source_node_id"]].own_anchors > 0
            and not res.nodes[n["source_node_id"]].exact
        )
    root_doc = {
        "metadata": _metadata("root", root_src, com_src, rres, root_nodes),
        "nodes": root_nodes,
    }
    com_doc = {
        "metadata": _metadata("commentary", com_src, root_src, cres, com_nodes),
        "nodes": com_nodes,
    }
    return Golds(root_doc, com_doc, crosswalk, stats)


def _draft(heading, sid, flags, root, commentary, evidence, notes, children) -> dict:
    return {
        "heading_src": heading,
        "heading_en": "",
        "display_label": display_label(heading),
        "source_node_id": sid,
        "origin": "imported",
        "node_class": "sutra-span",
        "flags": _flags(flags),
        "child_count_announced": None,
        "extent_announced": None,
        "locations": {"scheme": "cbeta-kepan", "commentary": commentary, "root_text": root},
        "evidence": evidence,
        "notes": notes,
        "children": children,
    }


FORMAT_NOTE = (
    "Imported from the 法華經數位資料庫 (sdp.chibs.edu.tw, CHIBS/DDBC) 科判, whose nodes sdp "
    "links to 法華文句 T1718 (R04 F30, F31). Node tree = sdp's getTreeNode tree in server order; "
    "node ids renumbered to the zh-kepan convention, sdp's id kept in source_node_id. heading_src "
    "= the sdp head_title inside 【】 without link labels (edge whitespace stripped), else the "
    "tree text (noted). Line positions are sdp's Taishō line anchors composed as CBETA lineheads "
    "and checked against the CBETA %s file: a node's start is the first anchor inside its "
    "content div when it precedes the node's first text, otherwise the last anchor before that "
    "text (the line the text begins on); a node without a content div (heading only) takes its "
    "first located descendant's start, or the anchor before its bare heading. Flag "
    "anchor_inherited marks a start that is not an anchor observed in the node's own content: "
    "heading-only nodes, nodes with no anchor of their own, and nodes whose first text lies in "
    "a verse block after the block's anchored first line (sdp anchors only that line, R04 F30). "
    "A start taken from the anchor before the node's first text is replaced by the node's first "
    "own anchor when that text is not on the CBETA line (sdp-inserted text; noted). "
    "root_text.end is the node's last line, inclusive: with the successor = the next node in "
    "pre-order that is not a descendant, the line before the successor's start (CBETA line "
    "order) when the successor begins its line, else the successor's start line, shared by both "
    "(end_basis next-node); the last node ends at the document's last anchor. sdp's T0262 -> "
    "T1718 文句 links are ids, not checked correspondences (R04 F31): every T1718 id inside a "
    "link id is read (concatenated ids noted); a link is used only when the two sdp nodes share "
    "a heading, sdp's leading ordinal aside (heading_src or tree text); T0262 "
    "commentary.explained = the T1718 start of the first used "
    "link; a T1718 node's root_text = the span of the first T0262 node with a used link to it, "
    "dropped when it breaks nesting with the nearest ancestor span or order with the elder "
    "siblings in the T1718 tree. Nodes in T1718 卷-halves sdp does not serve get no T1718 line "
    "(never estimated). A node whose getTreeNode request failed (fetch_error; the request is made "
    "only for non-leaf nodes) keeps its tree heading and a 'fetch_error:' note; when its content "
    "div is in the HTML, the divs up to the next tree node become its subtree (noted as recovered), "
    "otherwise it carries flag truncated: the gold does not encode its children (this gold declares "
    "no coverage_spans, so its scope is the whole gold). "
    "child_count_announced and extent_announced are not extracted from sdp "
    "headings (null). Flag unmapped marks a missing primary locator of this gold: root_text in "
    "the T0262 (root-text) gold, commentary.explained in the T1718 (commentary) gold; a T1718 "
    "node without root_text is flagged too, as the schema's sūtra-mode rule requires. Any other "
    "missing locator is only noted."
)
# Appended to the commentary (T1718) gold's format_note only (D15 addendum, final review 2026-09-22).
COMMENTARY_SCOPE_NOTE = (
    " Scoring scope (E01 keys on commentary.explained): this gold declares no coverage_spans, so "
    "its scope is the whole gold, but only where sdp serves the commentary: score only predictions "
    "whose explained line lies in a %s 卷-half sdp serves (served here: %s; data/eval-sets.json "
    "records the halves); a prediction in an unserved half is out of scope, neither TP nor FP, "
    "since this gold has no node there. The T0262 gold is not narrowed: its root-text scope "
    "(E02/E03, root_text.start) is all of %s."
)
LICENCE = {
    "id": None,
    "holder": None,
    "statement": (
        "sdp publishes no licence or terms of use (only 'Copyright 2003-2007' on the 計畫小組 "
        "page; the 2002 CCK proposal's Public Domain intent is not a licence on the live "
        "data). Absence of a licence is not a grant: eval-only, not redistributed, not used "
        "as prompt or training material, never committed (Global Constraint 1 of "
        "docs/plans/2026-09-22-eval-datasets.md)."
    ),
    "evidence": (
        "context/research/R04-existing-digital-kepan-datasets/findings.md F32 (S70, S74, S75, S65)"
    ),
}


def _metadata(kind: str, this: SdpSource, other: SdpSource, res: Resolved, nodes: list) -> dict:
    root, com = (this, other) if kind == "root" else (other, this)
    m = re.search(r"No\. ?[0-9]+ (.+)$", res.pages.doc_title or "")
    title = m.group(1).strip() if m else this.doc
    pages = []
    for key, path in this.html:
        path = Path(path)
        if path.exists():
            pages.append("%s sha256 %s" % (common.repo_relative(path), common.sha256_file(path)))
        else:
            pages.append(
                "%s: not available (sdp serves no page for it; see the header of "
                "scripts/fetch_dila_sdp.sh)" % common.repo_relative(path)
            )
    served = [key for key, path in this.html if Path(path).exists()]
    scope_note = COMMENTARY_SCOPE_NOTE % (this.doc, ", ".join(served) or "none", root.doc)
    what = (
        "root-text gold: sdp's 科判 tree of %s with Taishō-line spans in %s and commentary "
        "positions in %s via sdp's 文句 links" % (this.doc, root.cbeta_id, com.cbeta_id)
        if kind == "root"
        else "commentary gold: sdp's 科判 tree of %s with explained lines in %s and root-text "
        "spans "
        "in %s taken from the %s nodes that link to each node"
        % (this.doc, com.cbeta_id, root.cbeta_id, root.doc)
    )
    return common.zh_metadata(
        nodes,
        source_file=common.repo_relative(this.tree),
        source_sha256=common.sha256_file(this.tree),
        text_id=this.doc,
        text_title_src=title,
        text_title_en=this.title_en,
        author=None,
        source_language="lzh",
        format_note=FORMAT_NOTE % CBETA_RELEASE + (scope_note if kind == "commentary" else ""),
        origin_note=(
            "Every node is origin 'imported' from sdp and unchecked against T1718's wording "
            "(Task 3 checks headings); sdp's editorial nodes (R03 F23) are not yet relabelled "
            "'editorial'."
        ),
        generated_by="chinese_workflow.eval.gold.sdp",
        anomalies=list(res.anomalies),
        source_document={
            "kind": "dataset",
            "text_id": None,
            "title": "法華經數位資料庫 (Saddharmapuṇḍarīka Database, CHIBS/DDBC) 科判 of %s %s"
            % (this.doc, title),
            "url": SDP_URL,
            "notes": [what] + pages,
        },
        outline_mode="sutra",
        root_text_id=root.cbeta_id,
        commentary_id=com.cbeta_id,
        scheme_id=SCHEME_ID,
        seeded_by=None,
        gold_status="imported-unchecked",
        licence=dict(LICENCE),
        eval_only=True,
        cbeta_release=CBETA_RELEASE,
        display_label_rule=(
            "the source's own label: the leading ordinal of the sdp heading "
            "('1' from 【1 …】, '1-5' from 【1-5 …】); null when it has none"
        ),
    )


# ------------------------------------------------------------------------------------------ CLI


def default_sources(sdp_dir: Path) -> tuple:
    root = SdpSource(
        "T0262",
        "T09n0262",
        sdp_dir / "tree-T0262-full.json",
        [(str(k), sdp_dir / ("T0262-juan%d.html" % k)) for k in range(1, 8)],
        title_en="Lotus Sūtra (Kumārajīva's translation)",
    )
    keys = ["%d%s" % (n, h) for n in range(1, 11) for h in "ab"]
    com = SdpSource(
        "T1718",
        "T34n1718",
        sdp_dir / "tree-T1718-full.json",
        [(k, sdp_dir / ("T1718-juan%s.html" % k)) for k in keys],
        title_en="Words and Phrases of the Lotus Sūtra (Zhiyi)",
    )
    return root, com


def write_tsv(rows: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sdp-dir", type=Path, default=common.REPO_ROOT / "data/raw/dila-sdp")
    ap.add_argument("--cbeta-dir", type=Path, default=common.REPO_ROOT / "data/raw/cbeta")
    ap.add_argument("--out-dir", type=Path, default=None, help="default: <sdp-dir>/gold")
    args = ap.parse_args(argv)
    out_dir = args.out_dir or args.sdp_dir / "gold"
    root_src, com_src = default_sources(args.sdp_dir)
    root_lines = common.line_texts(args.cbeta_dir / ("%s.xml" % root_src.cbeta_id))
    com_lines = common.line_texts(args.cbeta_dir / ("%s.xml" % com_src.cbeta_id))
    golds = build_golds(root_src, com_src, root_lines, com_lines)
    failed = 0
    for doc, src in ((golds.root, root_src), (golds.commentary, com_src)):
        path = common.write_json(doc, out_dir / ("%s.%s.outline.json" % (src.doc, SCHEME_ID)))
        rep = common.validate(doc, common.repo_relative(path))
        failed += not rep.passed()
        print(
            "%s  %s  nodes=%d  max_depth=%d  errors=%d  warnings=%d"
            % (
                "PASS" if rep.passed() else "FAIL",
                rep.path,
                rep.node_count,
                rep.max_depth,
                len(rep.errors),
                len(rep.warnings),
            )
        )
        for f in rep.errors[:10]:
            print(f.render())
    write_tsv(golds.crosswalk, out_dir / ("crosswalk-%s-%s.tsv" % (root_src.doc, com_src.doc)))
    for label in ("root", "commentary"):
        print("%s gold:" % label)
        for k, v in sorted(golds.stats[label].items()):
            print("  %-45s %d" % (k, v))
    print("nodes touched by a missing sdp %s 卷-half:" % com_src.doc)
    for k, v in sorted(golds.stats["unmapped_by_gap"].items()):
        print("  %-45s %d" % (k, v))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
