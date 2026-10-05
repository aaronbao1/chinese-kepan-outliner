"""The tier-2 state machine: statements -> explicit draft nodes (docs/outliner-design.md §5.2).

Input : an ingest.text.InputText (the commentary span in sūtra mode, the treatise in self-outlining
        mode) and the tier-1 anchors inside it, document order: [{"anchor": linehead, "heading_src",
        "part_type"}] (the line of each cb:mulu 品).
Output: Tier2Result(by_anchor, report, rejected, genre_gate, stats). by_anchor maps each anchor linehead
        (None for text before the first anchor) to its draft nodes, nested via "children", in document
        order; numbering is done later by common.outline_doc.build_prediction.

The machine keeps a cursor (the node the text is in), the last division (whose items 此初 enters) and
the pending lemma of the current treatment unit (經「A至B」。贊曰：). Rules (design §5.2; the T1723 dev
subtree's conventions, R03 F25; R07 F17):
  * an announcement divides a target resolved from its subject: 答中 / 問中 -> the child labelled 答 / 問;
    初中 / 初文 / 中初文 -> the first child (created, headed by the subject, when the cursor has none);
    後中 -> the last; N中 -> child N; 品文 / 此品 / 文 at chapter level -> the chapter; X中 / 就X -> the
    node labelled X; 又就前X中 / 就上X中 -> a re-division of the item whose label contains X (前X the
    earliest announced among same-named candidates, 上X the one named last; 就此X中 is the cursor);
    bare 有N / 分N after a lemma or entry marker -> the cursor; a bare 有N right after a
    listing -> the listed item its labels share characters with (七佛讚揚 <- 總讚 / 別讚 / 勸讚).
  * a division of a tier-1 node (the 品) or a gate creates a wrapper node headed by the announcing
    phrase (三門分別, 品文分三), the Kuiji gold's convention (design §14 item 6).
  * items become children at announcement time, announced = explained = the item's position; an entry
    marker that takes an item up moves its explained there; a node entered as the first statement after a
    lemma is explained at the lemma. A numeral that opens a label (二聖, 十神) is a count hint; 此初聖 /
    第二聖 create members of 二聖; an explicit later count (十神。有七) overrides the hint. In self-outlining
    mode X論者，謂如有一 takes up the listed doctrine X (計我論者 -> 我, T1602), 云何修行X門？ the listed 門 and
    所言X者 the listed item X (T1666; an unresolved 所言X者 leaves the text where it was); an X者 whose X
    opens with a function word (若無常者) is no marker. A listing the treatise then takes up in order is
    taken for a division (filters.taken_up; the bound is 2,000 characters or the next close statement:
    已說X分, 上明X, X竟).
  * Zhiyi's 「X」者 / 「X」，… at a sentence start (lemma_zhe, T1718 dev; E06 review B6) takes up the word
    X of the sūtra: a sub-gloss of the open gloss unit when X is part of its word (釋「聞」者 under 我聞)
    or its 名也 after a 姓也 (「阿若」者 after 「憍陳如」，姓也); else an item named X of a division up the
    cursor chain (the listed 如是), or a child of a listed item X partly names (王舍城 under 王城耆山);
    else a new member of the nearest division still taking members (open count 五或六或七, count not
    reached, listed by a gloss run); else a sibling of the open gloss unit, or the first member of the
    node the text is in. ≥ 3 one-clause glosses right after a count-only / open-count announcement are
    its listing (listed-only items). While a gloss unit is open, a weak marker naming a node already taken
    up is a mention, not a move (大者，… restates the head word of 「大」者; counted in stats.weak_mentions).
    A second 「X」者 for an item already taken up (an entered item named X; or, as 又「X」者, the open unit's
    word or a gloss beside it) is a mention too: no node, no move (stats.gloss_repeats); a bare 「X」者
    repeating a gloss is another occurrence of the word in the sūtra and stays a node. Not a unit: inside a 經「A至B」。
    贊曰 unit (Kuiji glosses a word of the lemma; a 經「…」 in prose, with no 贊曰 behind it, opens no such
    unit and, inside an armed unit, does not close it: it neither arms nor disarms the guard), a title word, or
    any gloss before the first division (reported). root_text.raw = X.
    Known limits (HYPOTHESIS, not changed): `_gloss_run` ignores an announced count (it lists every run of
    ≥ 3 short glosses, whatever the count says); `_next_slot` takes the next slot of a count-only division
    only while all its children are kind `entered`, so a lemma_zhe member under such a division blocks the
    later 下明X slots; a repeat or a mention does not move the cursor; a lone 「聞」者 after the 我聞 unit
    has closed can count as a repeat of the entered item 我聞 through `sim()`'s containment (聞 inside 我聞,
    at least half its length: 0.9); auditable in `stats.gloss_repeats`, 0 on every measured text.
  * the lemma of a unit goes to the node the unit enters first and down its chain of first children.
  * anything the rules cannot decide goes to `report`; announcements the filter rejects to `rejected`; under
    the genre gate (no-structure) nothing is built, but accepted announcements, strong entry markers and
    closing markers go to `report` as gated-announcement / gated-enter / gated-close and the rejections to
    `rejected`.
Deterministic: the same text and anchors give the same drafts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import formulae as F
from .chart import chart_items, chart_tree, is_chart
from .filters import (TAKE_UP_WINDOW, attributions, genre_gate, is_listing_candidate, is_method_list, judge,
                      subject_kind)
from .scanner import Statement, scan

LABEL_STYLES = ("label", "source")
DEFAULT_CONFIG = {
    "heading_style": "label",  # 'label' (README label rule) | 'source' (ordinal kept: 初明持經之福)
    "genre_threshold": 0.4,  # accepted announcements per 1,000 characters (genre gate)
    "sim_label": 0.75,  # label similarity needed to resolve 下明X / 此X / X者 without an index
}


@dataclass
class Tier2Result:
    by_anchor: dict  # anchor linehead (str) or None -> list of draft nodes (nested via "children")
    report: list  # {"id", "linehead", "offset", "kind", "text", "reason"}: what rules could not decide
    rejected: list  # {"linehead", "offset", "text", "reason"}: announcements the filter rejected
    genre_gate: dict  # {"decision": "outline" | "no-structure", "evidence": str}
    stats: dict  # counts


class Node:
    """A node under construction (converted to a draft dict at the end)."""

    def __init__(self, heading: str, verbatim: str, kind: str, node_class: str = "sutra-span"):
        self.heading = heading
        self.verbatim = verbatim or heading
        self.kind = kind  # anchor | root | wrapper | item | entered | subject | lemma_zhe
        self.node_class = node_class
        self.parent: Node | None = None
        self.children: list = []
        self.announced: int | None = None
        self.explained: int | None = None
        self.entered = False
        self.evidence: list = []  # [(start, end)] character spans; their lines form the evidence
        self.count: int | None = None  # explicit announced count
        self.hint: int | None = None  # count hint from a numeral in the label
        self.noun: str | None = None  # 聖 of 二聖
        self.extent: str | None = None
        self.lemma: dict | None = None
        self.raw: list = []
        self.notes: list = []
        self.flags: list = []
        self.divided = False
        self.anchored = False  # entered by an entry marker or named by a label
        self.open_count = False  # 通序為五或六或七: members are taken up without a count (T1718 dev)
        self.gloss_listed = False  # its items came from a run of one-clause 「X」者 glosses
        self.surname = False  # a lemma_zhe unit glossed 姓也 (its 名也 gloss is a sub-gloss: 阿若 / 憍陳如)
        self.marker_kind: str | None = None  # formula of the marker that entered or created it (sibling rules)

    def add(self, child: Node) -> Node:
        child.parent = self
        self.children.append(child)
        return child

    @property
    def index(self) -> int:
        return self.parent.children.index(self) + 1 if self.parent else 0

    def chain(self):
        n = self
        while n is not None:
            yield n
            n = n.parent

    def is_stub(self) -> bool:
        return self.kind in ("anchor", "root")


# ------------------------------------------------------------------------------------ similarity


def sim(x: str, label: str) -> float:
    """How well a marker's name x matches a label: 1 equal, 0.9 containment, else the share of the
    label's characters found in x."""
    if not x or not label:
        return 0.0
    if x == label:
        return 1.0
    if len(label) == 1:  # 明數 / 歎德 for the items 數 / 歎 (T1718)
        return 0.9 if label in (x[0], x[-1]) else 0.0
    if label in x or x in label:
        short, long_ = sorted((len(x), len(label)))
        return 0.9 if 2 * short >= long_ else 0.6  # 修行 inside a 26-character label is no match
    return len(set(x) & set(label)) / len(set(label))


def _subsequence(x: str, label: str) -> bool:
    """禁父緣 in 正明發起序禁父之緣: the characters of x occur in label in order (gapped containment)."""
    it = iter(label)
    return bool(x) and all(ch in it for ch in x)


def _strip_subject(s: str) -> str:
    for op in F.OPENERS:
        s = s.replace(op, "")
    s = s.strip("：:，, ")
    s = re.sub(r"^(?:今初|此初|今|然|又|且|即|則|其|此之|此|所言|言|就|於|釋|列|辨|明|次|是)", "", s)
    s = re.sub(r"(?:之中|中|者|段|下)$", "", s)
    return s


def _names_part(s: str) -> bool:
    """Can a subject head a node of its own? 2-10 characters, not a function word at either end
    (雖 / 分之 / 若如是 are not names)."""
    return 2 <= len(s) <= 10 and s[0] not in F.FUNCTION_HEAD and s[-1] not in "之也故者矣耶乎"


COUNT_HINT_RE = re.compile(r"^([二三四五六七八九十]{1,2})([^\s，。、；：]{1,2})$")
# quoted-lemma glosses (lemma_zhe, T1718 dev)
# units opened by 經「A至B」。贊曰 / 贊曰 (Kuiji). A 經「…」 in prose is a "sutra-cite" lemma statement (no opener
# behind it): it is not listed here, so a citation in Zhiyi's own text does not silence his glosses (T1705)
ZANYUE_FORMULAE = ("zanyue-lemma", "opener-lemma", "quoted-lemma")
GLOSS_RUN_MIN = 3  # one-clause glosses that make a listing
GLOSS_RUN_MAX = 30  # characters a one-clause gloss may leave before the next statement (dev: 6-20 vs 173)
GLOSS_PARTIAL = 0.5  # similarity at which X names part of a listed item (王舍城 / 王城耆山 = 0.5)
# 又就前序中 / 就上X中: a re-division of the item named X announced earlier (善導, T37n1753_p0251c25);
# 此 is left out on purpose: 就此X中 is anaphoric (the node the text is in), not a name. A lone part word
# as the core (就前分中 / 就前文中 / 就前段中 / 於上文中 / 就前科中) names no item — it is contained in every
# 明X分 label — so it is left to the rules that follow in _target (the previous behaviour).
REDIVISION_RE = re.compile(
    r"(?:[又復亦次])?(?:就|於)(?P<which>前|上)(?P<x>(?![文分段科](?:之)?中)[^此前上中之]{1,2})(?:之)?中")


# ------------------------------------------------------------------------------------ the machine


class _Machine:
    def __init__(self, text: str, *, anchors: list, anchor_offsets: list, mode: str, config: dict,
                 locate=None):
        self.s = text
        self.mode = mode
        self.cfg = config
        self.locate = locate or (lambda off: str(off))
        self.roots: dict = {None: Node("", "", "root")}
        self.bounds = []  # [(offset, anchor linehead)]
        for a, off in zip(anchors, anchor_offsets):
            if off is None:
                continue
            node = Node(a.get("heading_src") or "", "", "anchor")
            self.roots[a["anchor"]] = node
            self.bounds.append((off, a["anchor"]))
        self.bounds.sort()
        self.cur_anchor = None
        self.stub = self.roots[None]
        self.cursor = self.stub
        self.last_div: Node | None = None
        self.pending: dict | None = None  # {"lemma", "start"}
        self.lemma_node: Node | None = None
        self.fresh = False
        self.prev_kind = ""  # kind of the previous processed statement
        self.prev_div_target: Node | None = None
        self.lost = False  # an entry marker we could not place: bare announcements are not attached
        self.core_note: str | None = None  # set by _by_core when its candidates carry several headings
        self.made: dict = {}  # id(announcement statement) -> the item nodes it created
        self.gloss_unit: Node | None = None  # the lemma_zhe unit most recently opened as a member
        self.listed_ids: set = set()  # id(statement) of glosses consumed as listed items (_gloss_run)
        # formula of the latest lemma statement of this anchor (zanyue-lemma: Kuiji). Not `pending`, which run()
        # clears as soon as prose follows a fresh lemma whose first statement did not resolve
        self.lemma_formula: str | None = None
        self.report: list = []
        self.rejected: list = []
        self.stats = {"statements": 0, "announcements": 0, "gates": 0, "uddanas": 0, "enters": 0,
                      "enters_unresolved": 0, "closes": 0, "lemmas": 0, "rejected": 0, "wrappers": 0,
                      "report": 0, "gated_announcements": 0, "gated_enters": 0, "gated_closes": 0,
                      "enters_lemma_zhe": 0, "gloss_listed": 0, "gloss_in_lemma_unit": 0, "weak_mentions": 0,
                      "gloss_repeats": 0}

    # -- bookkeeping
    def _report(self, st: Statement, kind: str, reason: str):
        ref = self.locate(st.start)
        lh, _, off = ref.partition(":")
        self.report.append({"id": "t2-%04d" % (len(self.report) + 1), "linehead": lh,
                            "offset": int(off) if off else 0, "kind": kind,
                            "text": self.s[st.start:min(st.end, st.start + 80)], "reason": reason})

    def _reject(self, st: Statement, reasons: list):
        """An announcement the filter rejected goes to `rejected` when it looks like one (is_listing_candidate)."""
        if not is_listing_candidate(st):
            return
        self.stats["rejected"] += 1
        ref = self.locate(st.start)
        lh, _, off = ref.partition(":")
        self.rejected.append({"linehead": lh, "offset": int(off) if off else 0,
                              "text": self.s[st.start:min(st.end, st.start + 80)],
                              "reason": "; ".join(reasons)})

    def _switch_anchor(self, pos: int):
        new = None
        for off, lh in self.bounds:
            if off <= pos:
                new = lh
        if new != self.cur_anchor:
            self.cur_anchor = new
            self.stub = self.roots[new]
            self.cursor = self.stub
            self.last_div = None
            self.pending = None
            self.lemma_node = None
            self.fresh = False
            self.prev_kind = ""
            self.lost = False
            self.gloss_unit = None
            self.lemma_formula = None

    def _pos(self, st: Statement, start: int | None = None) -> int:
        """Where a node taken up by st is explained: the lemma when st opens the unit."""
        if self.fresh and self.pending is not None:
            return self.pending["start"]
        return st.start if start is None else start

    def _give_lemma(self, node: Node, *, first_statement: bool):
        if self.pending is None or node.node_class == "commentary-internal":
            return
        if first_statement or self.lemma_node is not None and node.parent is self.lemma_node and node.index == 1:
            if node.lemma is None:
                node.lemma = dict(self.pending["lemma"])
            self.lemma_node = node

    def _enter(self, node: Node, st: Statement, marker: str):
        first = self.fresh
        node.anchored = True
        if not node.entered:
            node.explained = self._pos(st)
            node.entered = True
        if marker:
            node.raw.append(marker)
        self._give_lemma(node, first_statement=first)
        self.cursor = node
        self.fresh = False

    # -- scope and matching
    def _scope(self):
        """Nodes whose children a marker may name: the cursor and its ancestors up to the stub."""
        out = []
        for n in self.cursor.chain():
            out.append(n)
            if n is self.stub:
                break
        return out

    def _by_label(self, x: str, threshold: float, *, prefer_unentered: bool = True) -> Node | None:
        best, best_key = None, None
        for depth, n in enumerate(self._scope()):
            # wrappers are transparent: the items of 品文分三 are named from the 品 level
            cands = list(n.children) + [g for c in n.children if c.kind == "wrapper" for g in c.children]
            for c in cands:
                v = sim(x, c.heading)
                if v < threshold:
                    continue
                key = (v, not c.entered if prefer_unentered else 0, -depth, -c.index)
                if best_key is None or key > best_key:
                    best, best_key = c, key
        return best

    def _by_core(self, x: str, *, earliest: bool) -> Node | None:
        """The item named by the core x of a re-division subject (序 ⊂ 明其序分), by containment, not
        sim(). Candidates are the items of the nearest scope level that has any (wrappers
        transparent, as in _by_label). 上X takes the one of them named last (the one just treated).
        前X ("the former X") contrasts same-named items: it takes the earliest announced among the
        nearest level's candidates and the same-headed items of outer levels — T1753 p0251c25 has
        明其序分 twice in scope, the 耆闍會's (nearest) and the 王宮會's, and means the latter; an
        outer item with another heading (卷一's 先標序題 in a no-anchor run) is never meant. None
        when no label in scope contains x. When the candidates carry more than one distinct heading
        (x = 序 inside both 明其序分 and 明正宗序分), the choice above is still made, and self.core_note
        says so: _announce reports 'ambiguous-target' once the announcement is accepted (a
        containment match cannot tell differently named items apart)."""
        def pos(c: Node):
            p = c.announced if c.announced is not None else c.explained
            return p if p is not None else float("inf")

        levels = []
        for n in self._scope():
            cands = list(n.children) + [g for c in n.children if c.kind == "wrapper" for g in c.children]
            levels.append([c for c in cands if c.kind != "wrapper" and x in c.heading])
        k = next((i for i, lv in enumerate(levels) if lv), None)
        if k is None:
            return None
        names = {c.heading for c in levels[k]}
        if earliest:
            pool = levels[k] + [c for lv in levels[k + 1:] for c in lv if c.heading in names]
            node = min(pool, key=pos)
        else:
            node = max(levels[k], key=pos)
        if len(names) > 1:
            self.core_note = ("re-division of the item named by 「%s」: %d differently named items contain "
                              "it (%s); took %r, the %s announced" % (
                                  x, len(names), "、".join(sorted(names)), node.heading,
                                  "earliest" if earliest else "latest"))
        return node

    def _new_child(self, parent: Node, heading: str, verbatim: str, st: Statement, kind="entered",
                   index: int | None = None) -> Node:
        cls = parent.node_class if not parent.is_stub() else "sutra-span"
        node = Node(heading, verbatim, kind, cls)
        node.evidence.append((st.start, st.end))
        m = COUNT_HINT_RE.match(heading)
        if m:
            node.hint, node.noun = F.parse_num(m.group(1)), m.group(2)
        parent.add(node)
        if index is not None and index != node.index:
            node.notes.append("created for index %d; %d sibling(s) before it" % (index, node.index - 1))
        return node

    # -- statements
    def run(self, stmts: list):
        closes = [st.start for st in stmts if st.kind == "close"]  # 已說X分 / 上明X / X竟: the treatise's own boundaries
        for i, st in enumerate(stmts):
            if id(st) in self.listed_ids:
                continue  # a one-clause gloss already taken as a listed item (_gloss_run)
            self._switch_anchor(st.start)
            self.stats["statements"] += 1
            if self.fresh and st.kind not in ("lemma", "opener") and not (
                    st.after in ("lemma", "opener") or st.unit_start):
                self.fresh = False  # prose lies between the lemma and this statement: stale lemma
                self.pending = None
            if st.kind == "lemma":
                self.pending = {"lemma": st.lemma, "start": st.start}
                if st.formula != "sutra-cite":  # a prose 經「…」 neither arms nor disarms the Kuiji guard
                    self.lemma_formula = st.formula
                self.lemma_node = None
                self.fresh = True
                self.stats["lemmas"] += 1
            elif st.kind == "opener":
                pass
            elif st.kind == "close":
                self._close(st)
            elif st.kind == "enter":
                self._enter_marker(st)
            elif st.kind in ("announce", "gate", "uddana"):
                bound = None
                if self.mode == "self-outlining":
                    nxt = [c for c in closes if c >= st.end]  # a close that starts where the listing ends bounds it
                    bound = min(st.end + TAKE_UP_WINDOW, nxt[0] if nxt else len(self.s), len(self.s))
                if not self._announce(st, stmts[i + 1:i + 24], take_up_bound=bound):
                    self.prev_kind = "rejected"
                    continue
            self.prev_kind = st.kind

    def gated(self, stmts: list):
        """The genre gate said no-structure: build nothing, but record what the formula machine saw, so the
        report shows the evidence and the resolver's adjudicate task can weigh it (X0268 楞嚴經集註: 9 of its
        261 announcement-like statements pass the filter; 137 are rejected, 128 of those inside citations)."""
        for st in stmts:
            if st.kind in ("announce", "gate", "uddana"):
                accepted, reasons, _ = judge(st, self.s, mode=self.mode)
                if accepted:
                    self.stats["gated_announcements"] += 1
                    self._report(st, "gated-announcement", "%s; genre gate: no-structure (no node built)"
                                 % "; ".join(reasons))
                else:
                    self._reject(st, reasons)
            elif st.kind == "enter" and st.strength == "strong":
                self.stats["gated_enters"] += 1
                self._report(st, "gated-enter", "entry marker %r; genre gate: no-structure (no node to enter)"
                             % st.marker)
            elif st.kind == "close":
                self.stats["gated_closes"] += 1
                self._report(st, "gated-close", "closing marker %r; genre gate: no-structure" % st.marker)

    def _close(self, st: Statement):
        x = _strip_subject(st.x)
        pops = sorting = False
        if st.enter_kind == "ming_jing":
            # 善導's 廣明X竟 closes X, the node the text is in or one of its ancestors (named by its heading or by
            # the 就X中 marker that entered it): the text goes on in X's parent (三、就禁母緣中 is X's sibling).
            # 廣料簡X竟 / 略料簡X竟 ends the sorting of X before its items are treated (p0252b02 廣料簡發起序竟,
            # then 初、解化前序者): X is not finished, so the cursor goes to X, not to its parent (popping loses
            # X's items: T1753 288 enters -> 219, unresolved 8 -> 75). Either way a close that names a node
            # counts; one that names none is reported (`unmatched-close`), not dropped. A 料簡 close found by
            # label outside the cursor chain names none: it is not counted and the cursor does not move to X.
            sorting = re.match("[廣總略]?料簡", st.heading_verbatim) is not None
            pops = not sorting
            for n in self._scope():
                if n.is_stub():
                    break
                if sim(x, n.heading) >= self.cfg["sim_label"] or any(x in r for r in n.raw if r):
                    self._closed(n, pops)
                    return
        node = self._by_label(x, self.cfg["sim_label"], prefer_unentered=False)
        if node is not None and node.entered and not sorting:  # a 料簡 close counts only for a node in the chain
            self._closed(node, pops)
        elif st.enter_kind == "ming_jing":
            self._report(st, "unmatched-close", "closing marker %r names no node in the cursor chain; not counted"
                         % st.marker)

    def _closed(self, node: Node, pops: bool):
        """The cursor after a close of node: its parent for 廣明X竟 (the text goes on beside X; found by label
        outside the chain too), X itself for 上明X / 廣料簡X竟."""
        self.cursor = node.parent if pops and node.parent is not None else node
        self.gloss_unit = None
        self.stats["closes"] += 1

    # entry markers
    def _enter_marker(self, st: Statement):
        node = None
        k = st.enter_kind
        if k == "anaphor":
            node = self._resolve_anaphor(st)
        elif k in ("ordinal", "ord_lemma", "num_zhe", "num_item", "pin_duan"):
            node = self._resolve_span_item(st) if st.formula == "cong-xia-zhi-lai" else None
            if node is None:
                node = self._resolve_ordinal(st)
        elif k == "next_item":
            node = self._resolve_next_item(st)
        elif k == "jiu_zhong":
            node = self._resolve_jiu_zhong(st)
        elif k in ("xia", "this", "x_zhe", "cishuo", "proponent", "yunhe_men", "suoyan"):
            thr = 0.9 if k in ("x_zhe", "proponent") else self.cfg["sim_label"]
            x = st.x
            node = self._by_label(x, thr)
            if node is None and k == "cishuo":
                node = self._by_label(x[1:], thr)  # 說立義分 -> 立義分
            if node is None and k == "xia" and st.strength == "strong":
                node = self._in_turn(x, 0.4) or self._next_slot(st)
        elif k == "lemma_zhe":
            node = self._resolve_lemma_zhe(st)
            if node is None:
                return  # a word gloss inside a lemma unit or a repeat (counted), a title word / stub (reported)
        if node is None:
            if st.strength == "strong":
                self.stats["enters_unresolved"] += 1
                self._report(st, "unmatched-enter", "entry marker %r names no announced node in scope"
                             % st.marker)
                # 所言X者 glosses a term (T1666 所言空者 / 所言不空者 name the two aspects of 真如 whose listing
                # the scanner drops as 分別有二種義); the text has not moved, so it neither sets nor clears
                # `lost`: the next bare announcement still attaches (此識有二種義 p0576b10), and one that
                # follows an earlier unplaced marker still reports ambiguous-target. Every other strong
                # marker moves the text.
                if k != "suoyan":
                    self.lost = True
            return
        if st.strength == "weak" and node.entered and self.gloss_unit is not None:
            # inside a gloss unit's discussion a weak marker that names a node already taken up is a mention, not a
            # move: Zhiyi's 約教釋 restates the head word (大者，大力羅漢所敬也 under 「大」者; 位大者 inside
            # 「摩訶迦葉」 matched the label 位 of 三位 through sim()'s one-character rule). Counted in
            # tier2.stats.weak_mentions so the rule can be audited (it is silent otherwise)
            self.stats["weak_mentions"] += 1
            return
        self.lost = False
        self.stats["enters"] += 1
        if st.enter_kind == "ord_lemma" and st.lemma:
            node.lemma = node.lemma or dict(st.lemma)
            self.pending = {"lemma": st.lemma, "start": st.start}
            self.fresh = True
        if k == "lemma_zhe":
            node.lemma = node.lemma or dict(st.lemma)
            if st.lemma.get("extent"):
                node.extent = node.extent or st.lemma["extent"]
            node.surname = self.s[st.end:st.end + 3].lstrip("，,").startswith("姓也")
            node.notes.append("entered by the quoted-lemma gloss %s (lemma_zhe)" % st.marker)
            self.stats["enters_lemma_zhe"] += 1
        else:
            self.gloss_unit = None  # the text moved by another marker: no gloss unit is open
        self._enter(node, st, st.marker)
        node.marker_kind = node.marker_kind or st.formula or st.enter_kind
        if k == "jiu_zhong" and st.count:
            # 即有其M after 就X中: a count-only division of X; its items arrive as 一、從A下至B已來 entries
            if node.divided:
                self._report(st, "divided-twice", "%r is already divided; its 有其%d is ignored"
                             % (node.heading, st.count))
            else:
                self.stats["announcements"] += 1
                self._divide(node, st)
                self.last_div = node
                self.prev_div_target = node

    def _resolve_next_item(self, st: Statement) -> Node | None:
        """初、X也 / 次、X也 / 二、X也: the next item of a division announced as 有N：初、X也 (a count with
        items named one by one as they are taken up, T1772), or a listed item of that index."""
        for node in self._scope():
            if not node.count:
                continue
            k = len(node.children)
            n = st.ordinal if st.ordinal is not None else (k + 1 if k < node.count else None)
            if n is None:
                continue
            if n <= k:
                c = node.children[n - 1]
                if sim(st.x, c.heading) >= 0.5 or c.kind == "entered" and n == k:
                    return c
                continue
            if n == k + 1 <= node.count:
                return self._new_child(node, st.heading, st.heading_verbatim, st, index=n)
        return None

    def _resolve_anaphor(self, st: Statement) -> Node | None:
        d = self.last_div
        if d is None or not (d.children or d.count or d.hint):
            return None
        x = st.x
        if not d.children:
            return self._new_child(d, x or "初", "初" + x, st, index=1)
        c1 = d.children[0]
        if c1.noun and x and x != c1.heading and x.startswith(c1.noun):
            # 此初聖: enter 二聖 and its first member (README pos-you-n-02, anaphor_path [1, 1])
            self._enter(c1, st, "")
            if c1.children:
                return c1.children[0]
            return self._new_child(c1, x, "初" + x, st, index=1)
        return c1

    def _resolve_ordinal(self, st: Statement) -> Node | None:
        n, x = st.ordinal, _strip_subject(st.x) if st.x else ""
        if n is None:
            return None
        scope = self._scope()
        if st.enter_kind == "pin_duan":
            for c in self.stub.children:
                if c.kind == "wrapper" and c.node_class != "commentary-internal" \
                        and len(c.children) >= n:
                    return c.children[n - 1]
            return None
        # a member of a counted class (第二聖 under 二聖, 第二天王 under 二天)
        for node in scope:
            if node.noun and x and x.startswith(node.noun) and \
                    n <= max(node.hint or 0, node.count or 0):
                if len(node.children) >= n:
                    return node.children[n - 1]
                if len(node.children) == n - 1:
                    return self._new_child(node, x, st.heading_verbatim, st, index=n)
        # the n-th item named x anywhere in this chapter (自下第三結勸生彼 -> 結勸生彼, a sibling's item)
        if len(x) >= 2:
            hit = self._named_item(x, n)
            if hit is not None:
                return hit
        # an announced item with this index and a matching (or no) name, nearest division first
        weak = st.strength == "weak"
        passed = False  # a nearer division was passed over: index alone no longer decides
        for node in scope:  # nearest division first
            if len(node.children) >= n:
                c = node.children[n - 1]
                v = sim(x, c.heading) if x else 0.0
                # its turn: not taken up, and no younger sibling taken up yet
                in_turn = not c.entered and not any(y.entered for y in node.children[n:])
                if v >= 0.5 or (not weak and (not x or (in_turn and (not passed or v >= 0.3)))):
                    return c
            if node.children:
                passed = True
        if weak:
            return None
        # the next sibling of an entered node (sequence: 上明X，自下第二…)
        for node in scope:
            if node.parent is None or node.is_stub():
                continue
            if node.index == n - 1:
                p = node.parent
                if len(p.children) >= n:
                    return p.children[n - 1]
                if p.count is None or n <= p.count:
                    return self._new_child(p, x, st.heading_verbatim, st, index=n)
        # a count-only division waiting for its items
        for node in scope:
            if node.count and not node.children and n == 1:
                return self._new_child(node, x, st.heading_verbatim, st, index=n)
        return None

    def _named_item(self, x: str, n: int) -> Node | None:
        """The n-th item named x (similarity >= 0.9) anywhere under the current stub, not yet taken
        up; the first in document order when several qualify."""
        found = []

        def walk(nodes):
            for c in nodes:
                if not c.entered and c.index == n and sim(x, c.heading) >= 0.9:
                    found.append(c)
                walk(c.children)

        walk(self.stub.children)
        return max(found, key=lambda c: sim(x, c.heading)) if found else None

    def _in_turn(self, x: str, threshold: float) -> Node | None:
        """下佛廣答 for the item 世尊廣答: the best-matching item whose turn it is (not yet taken up, its
        elder sibling taken up), at a lower similarity than a free label match needs."""
        best, best_v = None, threshold
        for n in self._scope():
            for i, c in enumerate(n.children):
                if c.entered or (i > 0 and not n.children[i - 1].entered):
                    continue
                v = sim(x, c.heading)
                if v >= best_v and (best is None or v > best_v):
                    best, best_v = c, v
        return best

    def _next_slot(self, st: Statement) -> Node | None:
        """下明X naming no listed item: the next item of a division announced with a count only."""
        for node in self._scope():
            if node.count and len(node.children) < node.count and \
                    all(c.kind == "entered" for c in node.children):
                return self._new_child(node, st.heading, st.heading_verbatim, st,
                                       index=len(node.children) + 1)
        return None

    # quoted-lemma glosses (Zhiyi, T1718 dev; E06 review B6)
    def _resolve_lemma_zhe(self, st: Statement) -> Node | None:
        """What 「X」者 opens (module docstring). None: in a text whose latest lemma was 經「…」/贊曰
        (Kuiji: the gloss explains a word of that lemma; counted), a second gloss of an item already taken
        up (a mention; counted), or a title word / a gloss before the first division (reported)."""
        x = st.x
        if self.lemma_formula in ZANYUE_FORMULAE:
            self.stats["gloss_in_lemma_unit"] += 1  # Kuiji: 「毘沙門」者此云多聞 inside 經「…」。贊曰 (T1723 dev)
            return None
        if x in F.TITLE_WORDS or self.cursor.is_stub():
            self._report(st, "lemma-gloss-at-stub", "quoted-lemma gloss %s before any division (a title "
                         "word or the preamble); not a unit" % st.marker)
            return None
        chain = list(self.cursor.chain())
        unit = self.gloss_unit if self.gloss_unit in chain else None
        after = self.s[st.end:st.end + 3].lstrip("，,")
        if unit is not None and (x != unit.heading and (x in unit.heading or unit.heading in x)
                                 or unit.surname and after.startswith("名也")):
            node = self._new_child(unit, x, x, st, kind="lemma_zhe")
            node.notes.append("sub-gloss inside the unit %r (lemma_zhe)" % unit.heading)
            return node
        best, best_v, accepting = None, 0.0, None
        taken = None  # an item named X (>= 0.9) that an earlier gloss or marker already took up
        for n in chain:
            if n.is_stub():
                break
            if not n.divided:
                continue
            acc = self._accepting(n)
            for c in n.children:
                if c.kind != "item":
                    continue  # never a node another gloss created: sim(摩訶迦栴延, 摩訶迦葉) = 0.75
                v = sim(x, c.heading)
                # named by X and not yet taken up, or (in a division still taking members) named in part
                if (not c.entered if v >= 0.9 else acc and v >= GLOSS_PARTIAL) and v > best_v:
                    best, best_v = c, v
                # sim()'s one-character rule (0.9 for 佛子 vs 佛) names no repeat: an exact label only
                if c.entered and v >= 0.9 and (v == 1.0 or len(c.heading) > 1) and taken is None:
                    taken = c
            if acc and accepting is None:
                accepting = n
            if not acc:
                break  # a complete division: nothing above it takes this gloss
        if best is not None and best_v >= 0.9:
            self.gloss_unit = best
            return best
        if taken is None and unit is not None and st.marker.startswith("又"):
            # 又「大」者: Zhiyi restates the open unit's word (or a gloss beside it). A bare 「X」者 repeating a gloss
            # is another occurrence of the word in the sūtra (T1705: 「何以故」者 twice under 標) and stays a node
            beside = [unit] + ([g for g in unit.parent.children if g.kind == "lemma_zhe"] if unit.parent else [])
            taken = next((g for g in beside if g.heading == x), None)
        if taken is not None:
            # a second 「X」者 for an item already taken up restates it (又「如是」者 after item 1 entered): a
            # mention, not a duplicate-headed member; the text does not move. Counted (tier2.stats.gloss_repeats)
            self.stats["gloss_repeats"] += 1
            return None
        if best is not None:
            node = self._new_child(best, x, x, st, kind="lemma_zhe")
            node.notes.append("names part of the listed item %r (lemma_zhe, similarity %.2f)"
                              % (best.heading, best_v))
            self.gloss_unit = node
            return node
        if accepting is not None:
            parent = accepting
        elif unit is not None and unit.parent is not None:
            parent = unit.parent
        else:
            parent = next((n for n in chain if n.is_stub() or n.anchored), self.stub)
        node = self._new_child(parent, x, x, st, kind="lemma_zhe")
        self.gloss_unit = node
        return node

    @staticmethod
    def _accepting(n: Node) -> bool:
        """A division still taking members: its count is open (五或六或七), not reached, or its items
        came from a gloss run (their take-ups name them)."""
        return n.open_count or n.gloss_listed or (n.count is not None and len(n.children) < n.count)

    def _gloss_run(self, div: Node, st: Statement, following: list) -> None:
        """≥ GLOSS_RUN_MIN consecutive one-clause 「X」者 glosses right after a count-only or open-count
        announcement are its LISTING (T1718 p0003a21: 通序為五或六或七云云。「如是」者，舉所聞之法體。
        「我聞」者，能持之人也。… six glosses, 6-20 characters each): listed-only items (announced ==
        explained, lemma raw = X) that the full treatments take up later (又「如是」者 at p0003a25, 173
        characters before its next statement). The run ends at a gloss followed by more than
        GLOSS_RUN_MAX characters, or one repeating an X of the run; weak enters inside are skipped."""
        if st.kind != "announce" or st.items or div.children:
            return
        cands = [f for f in following if not (f.kind == "enter" and f.strength == "weak")]
        run, seen = [], set()
        for j, f in enumerate(cands):
            if f.kind != "enter" or f.enter_kind != "lemma_zhe" or f.x in seen:
                break
            if not run and not re.fullmatch(r"(?:云云)?[。；：:，, 　]*", self.s[st.end:f.start]):
                break
            nxt = cands[j + 1] if j + 1 < len(cands) else None
            tail = self.s[f.end:nxt.start] if nxt is not None else self.s[f.end:f.end + GLOSS_RUN_MAX + 1]
            if len(tail) > GLOSS_RUN_MAX:
                break
            run.append(f)
            seen.add(f.x)
        if len(run) < GLOSS_RUN_MIN:
            return
        head = self.s[st.subject_start:st.head_end]
        for f in run:
            node = Node(f.x, f.x, "item", div.node_class)
            node.announced = node.explained = f.start
            node.evidence.append((f.start, f.end))
            node.raw.append(f.marker)
            node.lemma = dict(f.lemma)
            node.notes.append("listed by a one-clause gloss after %r (lemma_zhe listing)" % head)
            div.add(node)
            self.listed_ids.add(id(f))
        div.gloss_listed = True
        self.stats["gloss_listed"] += len(run)

    def _resolve_jiu_zhong(self, st: Statement) -> Node | None:
        """N、就X中 (善導, T1753). X is (1) a listed item in scope by label, or (2) with an ordinal, child N of
        the nearest division in scope whose child N is not yet taken up and shares X's characters in order
        (禁父緣 vs 正明發起序禁父之緣); else (3) the next sibling of the last 就X中 node in scope (就初日觀中 …
        二、就水觀中 … 十三、就雜想觀中 under one 卷; 次就上品中生位中 after 上品上生) — the heading is X and the
        node is created with _new_child, index N, unless the division has its count and N lies past it (or it
        is full); else (4), with no ordinal or ordinal 1, a new node under _home() (the first of a run). An
        ordinal > 1 with no slot is unresolved (reported)."""
        x, n = _strip_subject(st.x), st.ordinal
        node = self._by_label(x, self.cfg["sim_label"])
        if node is not None and node.entered and x != node.heading and x not in node.heading \
                and node.heading not in x:
            node = None  # an item already treated that only shares characters (上品中生 vs 上品上生 under sim())
        if node is None and n is not None:
            for d in self._scope():
                if len(d.children) >= n:
                    c = d.children[n - 1]
                    if not c.entered and (sim(x, c.heading) >= 0.5 or _subsequence(x, c.heading)):
                        node = c
                        break
        if node is not None:
            return node
        def created(c: Node) -> bool:  # made by a 就X中 of this rule (a listed item entered by one keeps kind "item")
            return c.kind == "entered" and c.marker_kind == "jiu-x-zhong"

        for p in self._scope():
            if p.children and created(p.children[-1]):
                # the run is the trailing siblings made by 就X中 (p may hold other children before it: the stub of
                # a text without anchors, whose count the run is no part of); an item the scanner missed leaves
                # a gap in the run, not a stop
                run = next((i for i, c in enumerate(reversed(p.children)) if not created(c)), len(p.children))
                # a division whose children are all this run, with its announced count, takes no item past it: an
                # ordinal beyond p.count (or any item of a full division) is not appended, it goes on as
                # unresolved (unmatched-enter), as in _resolve_ordinal. Only when the run is all p holds: with
                # other children before it (the stub of a text without anchors; the 七門料簡 wrapper of T1753,
                # announced 七, whose 門 are not the run) the guard is off. A residual, measured on T1753 with
                # anchors=[]: the narrowing changes 9 of 33 `_resolve_jiu_zhong` decisions (six appends plus three
                # downstream grade parents), each append adding one of 卷三's 像觀 … 雜想觀 to
                # 卷一's 七門料簡 wrapper (count 7, four 門 entered, 17 children in the end); the anchored build
                # is unaffected. Without the narrowing the anchors=[] parse cascades (enters 288 -> 234, unresolved
                # 7 -> 56, closes 30 -> 24, nodes 659 -> 523), so it stays.
                full = p.count is not None and run == len(p.children) and (
                    len(p.children) >= p.count if n is None else n > p.count)
                if (n is None or n > run) and not full:
                    return self._new_child(p, x, st.heading_verbatim, st, index=n)
                break
        if n is not None and n != 1:
            return None
        home = self._home()
        while not home.is_stub() and home.parent is not None and home.count and len(home.children) >= home.count:
            home = home.parent  # a division with all its announced items takes no new one (初日觀 after the 七緣)
        return self._new_child(home, x, st.heading_verbatim, st)

    def _resolve_span_item(self, st: Statement) -> Node | None:
        """N、從A下至B已來，Y (善導): item N of the nearest division in scope whose items are such spans — a
        count-only division with N-1 span items so far (child N created, heading Y), or a listed span item N
        not yet taken up. A division of 一明… sub-items (no spans) under an item is passed over, so item 4
        of 上品上生 is not read as sub-item 4 of its item 3. None falls back to _resolve_ordinal."""
        n = st.ordinal
        if n is None:
            return None
        for d in self._scope():
            k = len(d.children)
            if n <= k:
                c = d.children[n - 1]
                if c.lemma and not c.entered and sim(st.heading, c.heading) >= 0.5:
                    return c
                continue
            # n > k + 1: an item before it was not found (一、從此想成時者 has no 下, a mixed 初、言X者 / 三、從A已下
            # listing); the run goes on rather than stops, and the child records the gap (_new_child notes)
            # a node entered by 就X中 with no 即有其M (次就上品中生位中，亦先舉，次辨，後結。) takes its items in turn
            slot = k < n <= d.count if d.count else d.marker_kind == "jiu-x-zhong" and n == k + 1
            if slot and all(c.marker_kind == "cong-xia-zhi-lai" for c in d.children):
                node = self._new_child(d, st.heading, st.heading_verbatim, st, index=n)
                if st.lemma:  # an item carrying a lemma divides the root text whatever its parent (as in _divide)
                    node.node_class = "sutra-span"
                return node
        return None

    # announcements
    def _target(self, st: Statement) -> tuple:
        """(node, how) the announcement divides; node None when undecidable. how: anchor | cursor |
        label | index | subject | overlap | sequence | nested | redivision."""
        if st.outer is not None and st.outer_item is not None:
            made = self.made.get(id(st.outer))
            if made and st.outer_item < len(made):
                return made[st.outer_item], "nested"  # 一、根本事依處，有六：… divides item 一
        subj = st.subject
        kind = subject_kind(subj, st.topic)
        s = _strip_subject(subj)
        cur = self.cursor
        if kind == "anchor" or (cur.is_stub() and s in ("", "文", "此文", "大文")):
            return self.stub, "anchor"
        if st.items and all(it.locator and ("〈" in it.locator or "品" in it.locator) for it in st.items):
            return self.stub, "anchor"  # items are chapter ranges: a division of the whole text
        # 答中 / 問中
        m = re.fullmatch(r"(答|問)", s)
        if m:
            for n in self._scope():
                for c in n.children:
                    if m.group(1) in c.heading:
                        return c, "label"
                if m.group(1) in n.heading and not n.is_stub():
                    return n, "label"
        # 又就前序中復分為二 / 就上X中: a re-division of the item named X (not a new sibling wrapper)
        m = REDIVISION_RE.fullmatch(subj.strip("：:，, "))
        if m:
            node = self._by_core(m.group("x"), earliest=m.group("which") == "前")
            if node is not None:
                return node, "redivision"
        # 初中 / 初文 / 中初文 / 後中 / 二中 / 初分之中
        m = re.fullmatch(r"中?(初|前|後|第?[一二三四五六七八九十]+)(文|分|段|科)?(?:之)?", s)
        adverb = re.search("[復亦又]", self.s[st.head_start:st.head_end]) is not None
        if m and (subj.endswith(("中", "文", "分", "段", "科")) or subj.startswith("中") or adverb):
            w = m.group(1)
            k = 1 if w in ("初", "前") else (-1 if w == "後" else F.parse_num(w.lstrip("第")))
            if k is not None:
                return self._by_index(cur, k, subj, st)
        # a label named by the subject (or by the topic clause before it)
        for cand in (s, _strip_subject(st.topic)):
            if cand and cand not in ("文", "此", "中") and len(cand) >= 1:
                node = self._by_label(cand, 0.75 if len(cand) >= 2 else 1.0, prefer_unentered=False)
                if node is not None and not node.divided:
                    return node, "label"
        if kind in ("pronoun", "struct") and s in ("", "文", "此文", "大文", "長行", "偈", "頌", "本文"):
            return self._bare_target(st)
        if kind == "struct" and not s:
            return self._bare_target(st)
        if s and kind in ("term", "struct") and _names_part(s):
            return None, "subject:" + s
        return self._bare_target(st)

    def _home(self) -> Node:
        """Where a node named only by its own announcement's subject goes: under the nearest node the
        text entered by a marker or a label (not under another such node or its items), so a run of
        X有N種 topics become siblings rather than a chain."""
        for n in self.cursor.chain():
            if n.is_stub() or (n.anchored and n.kind not in ("subject", "lemma_zhe")):
                return n
        return self.stub

    def _by_index(self, base: Node, k: int, subj: str, st: Statement) -> tuple:
        heading = re.sub(r"^中(?=[初後第一二三四五六七八九十])", "", _strip_subject(subj) or subj)
        if base.children:
            if k == -1:
                return base.children[-1], "index"
            if 1 <= k <= len(base.children):
                return base.children[k - 1], "index"
            if base.count and k <= base.count and k == len(base.children) + 1:
                return self._new_child(base, heading, heading, st, index=k), "index"
            return None, "index-out-of-range"
        if (base.count or base.hint) and (k == 1 or k == -1 and (base.count or base.hint) == 1):
            node = self._new_child(base, heading, heading, st, index=1)
            node.notes.append("heading from the subject %r of the announcement" % subj)
            return node, "index"
        if self.last_div is not None and self.last_div.children and self.last_div is not base:
            d = self.last_div
            if k == -1:
                return d.children[-1], "index"
            if 1 <= k <= len(d.children):
                return d.children[k - 1], "index"
        return None, "index-unresolved"

    def _bare_target(self, st: Statement) -> tuple:
        cur = self.cursor
        if self.lost:
            return None, "after-unplaced-marker"
        if not cur.divided or st.kind == "gate":
            # a gate wraps its items in a node of its own under the cursor, divided or not (T1753: 略作五門明義
            # after 即有其二 divided 出文顯證, a head HEAD_RE's 其 made visible)
            return cur, "cursor"
        # the cursor is already divided: a bare 有N names one of its items
        if self.prev_kind in ("announce", "gate") and self.prev_div_target is cur:
            # score = how many of the new labels share a character with the item
            scores = [(sum(1 for lab in st.labels if set(lab) & set(c.heading)), c)
                      for c in cur.children]
            best = max((sc for sc, _ in scores), default=0)
            winners = [c for sc, c in scores if sc == best]
            if best > 0 and len(winners) == 1:
                return winners[0], "overlap"
            return None, "ambiguous-after-listing"
        if st.after in ("lemma", "opener") or st.unit_start:
            for c in cur.children:
                if not c.entered and not c.divided:
                    return c, "sequence"
        return None, "cursor-divided"

    def _announce(self, st: Statement, following: list, take_up_bound: int | None = None) -> bool:
        """Place one announcement; False when the filter rejects it."""
        self.core_note = None
        tgt, how = self._target(st)
        anaphor_next = any(f.kind == "enter" and f.enter_kind == "anaphor" and f.start - st.end <= 6
                           for f in following[:1])
        accepted, reasons, _ = judge(st, self.s, mode=self.mode,
                                     label_match=how in ("label", "nested", "redivision"),
                                     followed_by_anaphor=anaphor_next, take_up_bound=take_up_bound)
        if not accepted:
            self._reject(st, reasons)
            return False
        if how == "redivision" and self.core_note:
            self._report(st, "ambiguous-target", self.core_note)
        if tgt is None and how.startswith("subject:"):
            # a named part no earlier listing announced (釋同聞眾為三): a node headed by the subject
            name = how.split(":", 1)[1]
            tgt = self._new_child(self._home(), name, st.subject, st, kind="subject")
            if any(it.lemma or it.locator for it in st.items):
                tgt.node_class = "sutra-span"
            tgt.evidence = [(st.subject_start, st.head_end)]
            tgt.notes.append("introduced by the subject of its own announcement; no listed item "
                             "matches %r" % name)
            how = "subject"
        if tgt is None:
            self._report(st, "ambiguous-target", "announcement of %s children; target undecided (%s)"
                         % (st.count, how))
            return True
        wrap = st.kind == "gate" or tgt.is_stub() or (tgt.divided and how == "anchor")
        if tgt.divided and not wrap:
            self._report(st, "divided-twice", "%r is already divided; second division ignored"
                         % tgt.heading)
            return True
        if how in ("sequence",):
            self._report(st, "target-by-sequence", "bare announcement after a new lemma; attached to "
                         "the next item not yet taken up (%s)" % tgt.heading)
        self.stats["announcements" if st.kind == "announce" else st.kind + "s"] += 1
        first = self.fresh
        pos = self._pos(st, st.subject_start)
        if wrap:
            div = self._wrapper(tgt, st, pos)
        else:
            div = tgt
            if how in ("label", "index", "anchor", "cursor", "redivision") and tgt.kind != "subject":
                div.anchored = div.anchored or how != "cursor" or tgt.entered
            if not div.entered:
                div.explained = pos
                div.entered = True
            self._give_lemma(div, first_statement=first)
        self._divide(div, st)
        self.cursor = div
        self.last_div = div
        self.prev_div_target = div
        self.fresh = False
        self.gloss_unit = None
        self._gloss_run(div, st, following)
        return True

    def _wrapper(self, parent: Node, st: Statement, pos: int) -> Node:
        a = st.subject_start if st.kind != "uddana" else st.start
        head = self.s[a:st.head_end]
        head = re.sub(r"^(?:%s)[：:]?" % "|".join(F.OPENERS), "", head)
        heading = re.sub(r"^(?:[略聊今先試]?[以作用]|[今然又且])", "", head).strip("：:，, ")
        procedural = (st.kind == "gate" and st.verb in F.GATE_VERBS) or is_method_list(
            st.subject, [it.label for it in st.items])
        cls = "commentary-internal" if procedural and not any(
            it.lemma or it.locator for it in st.items) else "sutra-span"
        if self.mode == "self-outlining":
            cls = "sutra-span"
        w = Node(heading, head, "wrapper", cls)
        w.evidence.append((st.subject_start, st.head_end))
        w.explained = pos
        w.entered = True
        w.raw.append(head)
        parent.add(w)
        if cls != "commentary-internal":
            self._give_lemma(w, first_statement=self.fresh)
        self.stats["wrappers"] += 1
        return w

    def _divide(self, div: Node, st: Statement):
        div.divided = True
        items = st.items
        if st.count is not None:
            div.count = st.count
        elif items:
            div.count = len(items)
        regroup = F.EXTENT_CLS | {"類", "段", "分", "科", "別"}
        if st.total and st.formula != "alt-count" and st.cls[-1:] in regroup:
            m = re.search(r"[一二三四五六七八九十]+[句行頌偈]", st.total)
            if m:
                div.extent = div.extent or st.total
            else:
                div.notes.append("announced %s before regrouping them into %d" % (st.total, div.count))
        div.raw.append(self.s[st.subject_start:st.head_end])
        if st.formula == "alt-count":
            div.notes.append("count left open: %s" % st.total)
            div.open_count = True
        existing = list(div.children)
        made = []
        for i, it in enumerate(items):
            verbatim = (it.ordinal.strip("、，,：: ") + it.label) if it.ordinal else it.label
            if i < len(existing) and existing[i].kind == "entered":
                node = existing[i]  # an item entered before the listing (count-only division)
                node.heading = node.heading or it.label
                node.announced = it.start
            else:
                # an item carrying a lemma or span locator divides the root text whatever its parent
                cls = "sutra-span" if (it.lemma or it.locator) else div.node_class
                node = Node(it.label, verbatim, "item", cls)
                node.announced = it.start
                node.explained = it.start
                div.add(node)
            node.evidence.append((it.start, max(it.label_end, it.start + 1)))
            node.raw.append(self.s[it.start:it.label_end])
            if it.lemma:
                node.lemma = node.lemma or dict(it.lemma)
            if it.extent:
                node.extent = it.extent
            made.append(node)
            m = COUNT_HINT_RE.match(it.label)
            if m:
                node.hint, node.noun = F.parse_num(m.group(1)), m.group(2)
        self.made[id(st)] = made
        if items and st.count is not None and len(items) != st.count:
            self._report(st, "incomplete-listing", "announced %d, listed %d" % (st.count, len(items)))


# ------------------------------------------------------------------------------------ drafts


def _drafts(m: _Machine, root: Node, text_obj, style: str) -> list:
    def ref(off):
        return None if off is None else m.locate(off)

    def evidence(spans):
        if text_obj is None:
            return " | ".join(m.s[a:b] for a, b in spans)
        lines = []
        for a, b in spans:
            la = text_obj.locate(a).split(":")[0]
            lb = text_obj.locate(max(a, b - 1)).split(":")[0]
            i, j = text_obj.index._pos[la], text_obj.index._pos[lb]
            for lh in text_obj.index.lineheads[i:j + 1]:
                if lh not in lines:
                    lines.append(lh)
        return " | ".join("%s: %s" % (lh, text_obj.index.line_text(lh)) for lh in lines)

    def conv(n: Node) -> dict:
        kids = [conv(c) for c in n.children]
        count = n.count if n.count is not None else (n.hint if n.children else None)
        flags = list(n.flags)
        if count is not None and n.children and len(n.children) != count or n.count is not None and not n.children:
            flags.append("count_mismatch")
        root_text = None
        if n.node_class == "sutra-span" and n.lemma is not None and m.mode != "self-outlining":
            raw = n.lemma.get("raw") or ""
            if n.lemma.get("unbracketed"):  # 從A下，至B已來 without 「」: hand the anchor A至B
                raw = n.lemma["a"] + ("至" + n.lemma["b"] if n.lemma.get("b") else "")
            elif n.lemma.get("b") and "至" not in raw:
                raw = "%s至%s" % (n.lemma["a"], n.lemma["b"])
            root_text = {"start": None, "end": None, "basis": "lemma", "end_basis": None, "raw": raw}
        notes = list(n.notes)
        if n.hint and n.count is None and n.children:
            notes.append("child count from the numeral in the label %r" % n.heading)
        heading = n.heading if style == "label" else n.verbatim
        d = {
            "heading_src": heading or n.verbatim,
            "locations": {
                "scheme": "cbeta-kepan",
                "commentary": {"announced": ref(n.announced), "explained": ref(n.explained),
                               "raw": " | ".join(r for r in n.raw if r) or heading},
                "root_text": root_text,
            },
            "origin": "explicit",
            "confidence": 1.0,
            "evidence": evidence(n.evidence),
            "node_class": n.node_class,
            "child_count_announced": count,
            "extent_announced": n.extent,
            "flags": sorted(set(flags)),
            "notes": notes,
            "children": kids,
            "_offset": n.explained,
            "_announced_offset": n.announced,
            "_tier2_kind": n.kind,
            "_source_heading": n.verbatim,
        }
        if n.lemma is not None:
            d["_lemma"] = dict(n.lemma)
        return d

    return [conv(c) for c in root.children]


def _self_mode_order(m: _Machine, root: Node):
    """Self-outlining mode: explained is the scored locator and must not decrease among siblings. A
    node whose explained position precedes an elder sibling's gets none (reported), rather than a
    position out of order: an item listed but never taken up whose listing line precedes an elder
    sibling's treatment, or a node taken up before an elder sibling's treatment (an entry marker that
    names the wrong item or a treatment the rules missed; before scanner._enter_at's function-head rule,
    T31n1602 p0524a11 若無常者 took up 常 inside the treatment of its elder 我). Its children keep their
    positions."""
    def walk(n: Node):
        last = None
        for c in n.children:
            if c.explained is not None and last is not None and c.explained < last:
                if c.entered:
                    ref = m.locate(c.explained)
                    c.notes.append("taken up out of order (at %s, before an elder sibling's treatment); "
                                   "no explained position" % ref)
                    kind, reason = "entered-out-of-order", "taken up before an elder sibling's treatment"
                else:
                    ref = m.locate(c.announced) if c.announced is not None else ""
                    c.notes.append("listed but not taken up; no explained position")
                    kind, reason = "not-taken-up", "listed item never entered"
                c.explained = None
                lh, _, off = ref.partition(":")
                m.report.append({"id": "t2-%04d" % (len(m.report) + 1), "linehead": lh,
                                 "offset": int(off) if off else 0, "kind": kind,
                                 "text": c.heading, "reason": reason})
            if c.explained is not None:
                last = c.explained if last is None else max(last, c.explained)
            walk(c)
    walk(root)


def _heading_breaks(text) -> set:
    """Offsets where a heading (head / jhead / cb:mulu line) starts or ends: a subject or a listing
    never runs across them."""
    out = set()
    for i, rec in enumerate(text.lines):
        base = text.index.starts[i]
        for h in rec.get("heads") or []:
            out.add(base + h["offset"])
            out.add(min(base + h["offset"] + len(h.get("text") or ""), base + len(rec["text"])))
        if rec.get("mulu"):
            out.add(base)
            line = rec["text"].strip()
            for mu in rec["mulu"]:
                title = re.sub(r"^[\d\s.]+", "", mu.get("text") or "")
                # a title line (陀羅尼品) ends a sentence; a cb:mulu inside prose only starts one
                if title and title in line and len(line) <= len(title) + 6:
                    out.add(base + len(rec["text"]))
    return out


def _count_nodes(drafts: list) -> int:
    return sum(1 + _count_nodes(d["children"]) for d in drafts)


# ------------------------------------------------------------------------------------ API


def parse(text, *, anchors: list, mode: str = "sutra", config: dict | None = None) -> Tier2Result:
    """Run tier 2 over an InputText (see the module docstring)."""
    cfg = dict(DEFAULT_CONFIG, **(config or {}))
    if cfg["heading_style"] not in LABEL_STYLES:
        raise ValueError("heading_style must be one of %s" % (LABEL_STYLES,))
    s = text.text
    offsets = []
    for a in anchors:
        lh = a["anchor"]
        offsets.append(text.index.global_offset(lh, 0) if text.contains(lh) else None)
    m = _Machine(s, anchors=anchors, anchor_offsets=offsets, mode=mode, config=cfg,
                 locate=text.locate)
    for a, off in zip(anchors, offsets):
        if off is None:
            m.report.append({"id": "t2-%04d" % (len(m.report) + 1), "linehead": a["anchor"], "offset": 0,
                             "kind": "anchor-outside-span", "text": a.get("heading_src") or "",
                             "reason": "tier-1 anchor not in the span; no drafts for it"})
    lines = [(text.index.starts[i], text.index.starts[i] + text.index.lengths[i], lh)
             for i, lh in enumerate(text.index.lineheads)]
    notes = [(text.index.starts[i] + a, text.index.starts[i] + b)
             for i, rec in enumerate(text.lines) for a, b in rec.get("inline_notes") or []]
    items = chart_items(s, lines, notes)
    if is_chart(items, sum(1 for rec in text.lines if rec["text"].strip())):
        return _chart_result(m, items, anchors, offsets, text, mode, cfg)
    stmts = scan(s, mode=mode, breaks=_heading_breaks(text))
    title = (text.info or {}).get("title", "")
    n_acc = 0
    for st in stmts:
        if st.kind in ("announce", "gate", "uddana"):
            if judge(st, s, mode=mode)[0]:
                n_acc += 1
    gate = genre_gate(title, n_accepted=n_acc, n_chars=len(s), attributions=attributions(s),
                      threshold=cfg["genre_threshold"])
    by_anchor: dict = {}
    if gate["decision"] == "no-structure":
        by_anchor = {None: []}
        for a, off in zip(anchors, offsets):
            if off is not None:
                by_anchor[a["anchor"]] = []
        m.gated(stmts)  # no nodes, but the evidence goes to report / rejected (E06 B9)
        stats = dict(m.stats, nodes=0, statements=len(stmts), report=len(m.report))
        return Tier2Result(by_anchor=by_anchor, report=m.report, rejected=m.rejected, genre_gate=gate,
                           stats=stats)
    m.run(stmts)
    for key, root in m.roots.items():
        if mode == "self-outlining":
            _self_mode_order(m, root)
        by_anchor[key] = _drafts(m, root, text, cfg["heading_style"])
    stats = dict(m.stats)
    stats["nodes"] = sum(_count_nodes(v) for v in by_anchor.values())
    stats["report"] = len(m.report)
    return Tier2Result(by_anchor=by_anchor, report=m.report, rejected=m.rejected, genre_gate=gate,
                       stats=stats)


def _chart_result(m: _Machine, items: list, anchors: list, offsets: list, text, mode: str,
                  cfg: dict) -> Tier2Result:
    """A chart (科文) text: the tree its lines state (chart.py), per anchor."""
    bounds = sorted((off, a["anchor"]) for a, off in zip(anchors, offsets) if off is not None)

    def anchor_of(pos):
        key = None
        for off, lh in bounds:
            if off <= pos:
                key = lh
        return key

    by_anchor: dict = {None: []}
    for _, lh in bounds:
        by_anchor[lh] = []
    groups: dict = {}
    for it in items:
        groups.setdefault(anchor_of(it["start"]), []).append(it)

    def conv(n) -> dict:
        it = n["item"]
        ref = text.locate(it["start"])
        lh = ref.split(":")[0]
        root_text = None
        if it["incipit"] and mode != "self-outlining":
            root_text = {"start": None, "end": None, "basis": "lemma", "end_basis": None,
                         "raw": it["incipit"]}
        count = it["count"]
        kids = [conv(c) for c in n["children"]]
        flags = ["count_mismatch"] if count is not None and len(kids) != count else []
        heading = it["label"] if cfg["heading_style"] == "label" else it["ordinal"] + it["label"]
        return {"heading_src": heading or it["ordinal"],
                "locations": {"scheme": "cbeta-kepan",
                              "commentary": {"announced": ref, "explained": ref,
                                             "raw": text.index.line_text(lh)},
                              "root_text": root_text},
                "origin": "explicit", "confidence": 1.0,
                "evidence": "%s: %s" % (lh, text.index.line_text(lh)),
                "node_class": "sutra-span", "child_count_announced": count,
                "extent_announced": None, "flags": flags, "notes": ["chart line (R01 chart-note)"],
                "children": kids, "_offset": it["start"], "_announced_offset": it["start"],
                "_tier2_kind": "chart", "_source_heading": it["ordinal"] + it["label"]}

    for key, group in groups.items():
        by_anchor[key] = [conv(n) for n in chart_tree(group)]
    nodes = sum(_count_nodes(v) for v in by_anchor.values())
    gate = {"decision": "outline", "evidence": "chart (科文): %d chart lines" % len(items)}
    stats = dict(m.stats, nodes=nodes, chart_lines=len(items))
    return Tier2Result(by_anchor=by_anchor, report=m.report, rejected=[], genre_gate=gate, stats=stats)


def detect(snippet: str, *, mode: str = "sutra", title: str | None = None,
           lines: list | None = None, notes: list | None = None) -> list:
    """The statements tier 2 finds in a snippet, as dicts (for scoring the labelled cases):
    {kind, formula, start, end, text, count, labels, items, subject, topic, target, anaphor, heading,
     ordinal, lemma, marker, strength, enter_kind, accepted, reasons}.
    Announcements are judged by the filter with the snippet as context (an earlier label in the snippet
    counts as a label match); title, when given, applies the genre gate."""
    if lines and notes:
        items = chart_items(snippet, lines, notes)
        if is_chart(items, len(lines)) or any(it["count"] for it in items[:1]):
            return _chart_statements(snippet, items)
    stmts = scan(snippet, mode=mode)
    gated = False
    if title is not None:
        g = genre_gate(title, n_accepted=0, n_chars=max(len(snippet), 1))
        gated = g["decision"] == "no-structure"
    seen_labels: list = []
    out = []
    for i, st in enumerate(stmts):
        d = {"kind": st.kind, "formula": st.formula, "start": st.start, "end": st.end,
             "text": snippet[st.start:st.end], "count": st.count, "labels": st.labels,
             "items": [{"label": it.label, "start": it.start, "end": it.end, "ordinal": it.ordinal,
                        "lemma": it.lemma, "extent": it.extent} for it in st.items],
             "subject": st.subject, "topic": st.topic, "target": None, "anaphor": None,
             "heading": st.heading or None, "ordinal": st.ordinal, "lemma": st.lemma,
             "marker": st.marker or None, "strength": st.strength or None,
             "enter_kind": st.enter_kind or None, "accepted": None, "reasons": []}
        if st.kind in ("announce", "gate", "uddana"):
            nxt = stmts[i + 1] if i + 1 < len(stmts) else None
            anaphor_next = nxt is not None and nxt.kind == "enter" and nxt.enter_kind == "anaphor" \
                and nxt.start - st.end <= 6
            s = _strip_subject(st.subject)
            label_match = bool(s) and any(sim(s, lab) >= 0.8 for lab in seen_labels)
            acc, reasons, _ = judge(st, snippet, mode=mode, label_match=label_match,
                                    followed_by_anaphor=anaphor_next,
                                    take_up_bound=len(snippet) if mode == "self-outlining" else None)
            if gated:
                acc, reasons = False, reasons + ["genre gate: 註 genre"]
            d["accepted"], d["reasons"] = acc, reasons
            d["target"] = _target_hint(st)
            for f in stmts[i + 1:]:
                if f.kind in ("announce", "gate", "uddana"):
                    break
                if f.kind == "enter" and f.enter_kind == "anaphor":
                    d["anaphor"] = f.marker
                    break
            if acc:
                seen_labels.extend(st.labels)
        elif st.kind == "enter" and st.enter_kind == "lemma_zhe" and st.x in F.TITLE_WORDS:
            d["accepted"], d["reasons"] = False, ["a title word (序 / 品 / 經 / 卷) glossed: not a unit"]
        elif st.kind == "enter" and (gated or st.count):
            # under the gate nothing is accepted; 就X中即有其M (T1753) is its own accepted announcement
            d["accepted"] = False if gated else True
        out.append(d)
    return out


def _chart_statements(snippet: str, items: list) -> list:
    """detect() for a chart: one statement per non-leaf line (heading, ordinal, count, child labels)."""
    out = []

    def walk(nodes):
        for n in nodes:
            it = n["item"]
            if n["children"] or it["count"]:
                out.append({"kind": "chart", "formula": "chart-note", "start": it["start"],
                            "end": it["end"], "text": snippet[it["start"]:it["end"]],
                            "count": it["count"], "labels": [c["item"]["label"] for c in n["children"]],
                            "items": [], "subject": "", "topic": "", "target": "cursor",
                            "anaphor": None, "heading": it["label"],
                            "ordinal": F.parse_num(it["ordinal"].lstrip("第").rstrip("者"))
                            if it["ordinal"] not in ("", "初", "次", "後", "先", "中", "前") else
                            (1 if it["ordinal"] == "初" else None),
                            "lemma": None, "marker": None, "strength": None, "enter_kind": None,
                            "accepted": True, "reasons": ["chart line with a count note"]})
            walk(n["children"])

    walk(chart_tree(items))
    return out


def _target_hint(st: Statement) -> str:
    kind = subject_kind(st.subject, st.topic)
    s = _strip_subject(st.subject)
    if kind == "anchor":
        return "anchor"
    m = re.fullmatch(r"中?(初|後|第?[一二三四五六七八九十]+)(文|分|段|科)?(?:之)?", s)
    if m and (st.subject.endswith(("中", "文", "分", "段", "科")) or st.subject.startswith("中")):
        w = m.group(1)
        k = 1 if w == "初" else (-1 if w == "後" else F.parse_num(w.lstrip("第")))
        if k is not None:  # parse_num("一一") is None (一一之中各有四種, T38n1782): fall through to the label hint
            return "index:%d" % k
    if s in ("答", "問"):
        return "label:" + s
    m = REDIVISION_RE.fullmatch(st.subject.strip("：:，, "))
    if m:
        return "redivision:" + m.group("x")
    if kind in ("pronoun",) or not s:
        return "cursor"
    return "label:" + s
