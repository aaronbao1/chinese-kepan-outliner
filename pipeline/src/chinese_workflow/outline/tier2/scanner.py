"""The tier-2 scanner: the statements of a commentary's reading text, in document order.

Input : a string (InputText.text of a span, or any snippet) with CBETA's punctuation kept, and the mode
        ('sutra' | 'self-outlining').
Output: a list of Statement, each with global character offsets into that string:
  lemma     經「A至B」 (R03 F25) or the sentence before 贊曰 when no 經「」 is written (T1772 如是我聞。贊曰：),
            「A」下 at a sentence start (T1735); opens a treatment unit. formula: zanyue-lemma (an opener
            follows the 經「…」), sutra-cite (a 經「…」 in prose: no opener, so Kuiji's word-gloss guard is not
            armed), opener-lemma, quoted-lemma
  opener    贊曰 / 述曰 / 疏曰 … (the commentary's voice after a lemma)
  announce  X有N / 分為N / 文為N … with its listing (labels.py), R01 table + R07 F17 variants
  gate      N門分別 / N門料簡 / 略作N門明義 (R03 F25)
  uddana    嗢拕南曰： (R01 uddana)
  enter     entry markers (此初 / 今初 / 第N / N、X者 / 下明X / 品第N段X / N「A」下，X / 次說X分 / X者 — not when X
            opens with a function word, 若無常者 — / 「X」者 in sūtra mode / X論者，謂如有一 · 云何修行X門？ ·
            所言X者 in self-outlining mode)
  close     closing markers (上明X / 已說X分 / X竟)
Nothing here decides whether an announcement divides the text (filters.py) or which node a statement
refers to (parser.py). Detection works on the punctuated text: CBETA 新式標點 separates the list items
(、，；) and ends the head (：); texts without punctuation are matched on the same patterns with fewer hits.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from . import formulae as F
from .labels import Item, Listing, _incipit, clean_label, parse_listing, uddana_count, uddana_listing


@dataclass
class Statement:
    kind: str  # lemma | opener | announce | gate | uddana | enter | close
    start: int
    end: int
    text: str
    formula: str = ""
    # announcements
    count: int | None = None
    cls: str = ""
    verb: str = ""
    subject: str = ""
    subject_start: int = 0
    topic: str = ""
    head_start: int = 0
    head_end: int = 0
    total: str | None = None  # 有五 in 有五，合為三類; 有十六句 in 有十六句，大分為三
    listing: Listing | None = None
    # entry markers
    enter_kind: str = ""
    strength: str = ""  # strong | weak
    marker: str = ""
    ordinal: int | None = None
    x: str = ""
    heading: str = ""
    heading_verbatim: str = ""
    lemma: dict | None = None
    # context
    after: str = "text"  # kind of the adjacent preceding statement ('text' when prose lies between)
    unit_start: bool = False  # first statement of a treatment unit (after a lemma / opener)
    in_quote: str | None = None  # citation | dialog | question | None
    in_question: bool = False
    outer: Statement | None = None  # the announcement whose listing holds this one
    outer_item: int | None = None  # index (document order) of the item of `outer` holding it
    accepted: bool | None = None
    reasons: list = field(default_factory=list)

    @property
    def labels(self) -> list:
        return self.listing.labels() if self.listing else []

    @property
    def items(self) -> list:
        return self.listing.items if self.listing else []


# ------------------------------------------------------------------------------------ quotes


def quote_spans(text: str) -> list:
    """[(start, end, kind)] of 「」/『』 quotations. kind: lemma (經「…」, 「A」下), term (a short quoted
    word glossed: 「如是」者), dialog (答曰：「…」), question (問曰：「…」), citation (everything else)."""
    out, stack = [], []
    for i, c in enumerate(text):
        if c in F.QUOTE_OPEN:
            stack.append(i)
        elif c in F.QUOTE_CLOSE and stack:
            s = stack.pop()
            out.append((s, i + 1, _quote_kind(text, s, i + 1)))
    out.sort()
    return out


def _quote_kind(text: str, s: int, e: int) -> str:
    before = text[max(0, s - 4):s]
    after = text[e:e + 3]
    if before.endswith(("經", "經：", "經:")):
        return "lemma"
    if after.startswith(("下", "以下", "已下", "去", "至", "訖", "等")) or before.endswith(("從", "至", "訖")):
        return "lemma"
    if before.endswith(("答曰：", "答曰:", "答：", "答:")):
        return "dialog"
    if before.endswith(("問曰：", "問曰:", "問：", "問:")):
        return "question"
    if e - s <= 14 and not before.endswith(("云", "云：", "曰：", "言", "言：", "說")):
        return "term"
    return "citation"


class QuoteMap:
    def __init__(self, spans: list):
        self.spans = spans
        self.starts = [s for s, _, _ in spans]

    def kind_at(self, pos: int) -> str | None:
        """Kind of the innermost quotation holding pos (None outside quotes)."""
        i = bisect.bisect_right(self.starts, pos) - 1
        best = None
        while i >= 0:
            s, e, k = self.spans[i]
            if s < pos < e:
                if best is None or s > best[0]:
                    best = (s, k)
            if pos - s > 4000:
                break
            i -= 1
        return best[1] if best else None


# ------------------------------------------------------------------------------------ heads


def _boundary_back(text: str, pos: int, stops: str = "。；;：:，,、？！○", breaks=frozenset()) -> int:
    i = pos
    while i > 0 and text[i - 1] not in stops and text[i - 1] not in F.QUOTE_OPEN + F.QUOTE_CLOSE \
            and i not in breaks:
        i -= 1
    return i


def _subject(text: str, head_start: int, breaks=frozenset()) -> tuple:
    """(subject, subject_start, topic): the clause part before the head, and, when that is empty, the
    previous comma clause (二歎德中，有二十句 -> topic 二歎德中)."""
    b = _boundary_back(text, head_start, breaks=breaks)
    subject = text[b:head_start]
    topic = ""
    if not subject.strip() and b > 0 and text[b - 1] in "，," and b not in breaks:
        b2 = _boundary_back(text, b - 1, breaks=breaks)
        topic = text[b2:b - 1]
    for op in F.OPENERS:
        subject = subject.removeprefix(op)
    return subject.strip(), head_start - len(subject.strip()), topic.strip()


def _head_candidates(text: str, qmap: QuoteMap, breaks=frozenset()) -> list:
    heads = []
    for rx, kind in ((F.GATE_RE, "gate"), (F.HEAD_RE, "announce"), (F.ADV_HEAD_RE, "announce")):
        for m in rx.finditer(text):
            n = F.parse_num(m.group("num"))
            if n is None or n < 2:
                continue
            q = qmap.kind_at(m.start())
            if q in ("lemma", "term"):
                continue
            if kind == "announce" and m.groupdict().get("pre", "").startswith("別") \
                    and text[m.start() - 1:m.start()] == "分":
                continue  # 分別有二種: 分別 is a verb, not 文別有N
            st = Statement(kind=kind, start=m.start(), end=m.end(), text=m.group(0), count=n,
                           verb=m.group("verb"), head_start=m.start(), head_end=m.end())
            st.cls = m.groupdict().get("cls") or ""
            if kind == "gate":
                st.cls = "門"
                if m.group("after"):  # N門分別者 is a reference back, not an announcement
                    continue
            st.in_quote = q
            heads.append(st)
    for m in F.ALT_COUNT_RE.finditer(text):
        q = qmap.kind_at(m.start())
        if q in ("lemma", "term"):
            continue
        st = Statement(kind="announce", start=m.start(), end=m.end(), text=m.group(0), count=None,
                       verb=m.group("verb"), head_start=m.start(), head_end=m.end(),
                       formula="alt-count")
        st.total = m.group("num")
        st.in_quote = q
        heads.append(st)
    for m in F.JIUZHONG_RE.finditer(text):
        q = qmap.kind_at(m.start())
        if q in ("lemma", "term"):
            continue
        st = Statement(kind="announce", start=m.start(), end=m.end(), text=m.group(0), count=None,
                       verb="", head_start=m.start(), head_end=m.end())
        st.in_quote = q
        heads.append(st)
    heads.extend(_you_list_heads(text, qmap))
    heads.sort(key=lambda h: (h.start, -(h.end - h.start)))
    out = []
    for h in heads:  # overlapping matches: keep the first (longest at a position)
        if out and h.start < out[-1].end:
            continue
        out.append(h)
    # 有十六句，大分為三 / 有五，合為三類: the first count is a total, the second the division
    merged = []
    for h in out:
        if merged:
            prev = merged[-1]
            gap = text[prev.end:h.start]
            if (prev.kind == "announce" and h.kind == "announce" and len(gap) <= 4
                    and gap[:1] in "，," and re.fullmatch(r"[，,](?:[大細今略文]|[分開合束攝判]之){0,2}", gap)
                    and not re.match(r"[：:]", text[prev.end:prev.end + 1])):
                h.total = text[prev.start:prev.end]
                h.start = prev.start
                merged[-1] = h
                continue
        merged.append(h)
    for h in merged:
        if h.formula == "you-list-span":
            continue
        if h.verb in ("就中", "於中"):
            h.subject, h.subject_start, h.topic = h.verb, h.start, ""
            continue
        if h.verb in ("中，", "中,"):  # 自下第二正校量中，初…次… (T1700)
            h.verb = "中"
            h.subject, h.subject_start, h.topic = _subject(text, h.start, breaks)
            h.subject = (h.subject + "中") if h.subject else "中"
            h.start = h.subject_start
            continue
        h.subject, h.subject_start, h.topic = _subject(text, h.start, breaks)
        if h.subject.startswith(("今初", "此初")):
            h.subject = h.subject[2:]
            h.subject_start += 2
        h.start = h.subject_start
    return merged


SUBJECT_ENTER_RE = re.compile(
    r"(?:(?:自下|從此以下|從此已下)?第[一二三四五六七八九十]{1,2}|(?:自下|下)(?:明|釋|辨)|次(?:明|釋|辨))"
)


def _split_subject_markers(text: str, heads: list, mode: str) -> list:
    """自下第二正校量有二 / 第二答中有二 / 下釋疑有四 (T1700): a subject that opens with an entry marker is
    that marker; the announcement then divides the node it enters (a bare subject)."""
    out = []
    for h in heads:
        if h.subject and h.kind == "announce" and SUBJECT_ENTER_RE.match(h.subject):
            s = h.subject_start
            x = h.subject
            m = re.match(r"(?P<m>(?:自下|從此以下|從此已下)?第(?P<n>[一二三四五六七八九十]{1,2})[、，,]?)", x)
            if m:
                st = Statement(kind="enter", start=s, end=h.head_start, text=x, enter_kind="ordinal",
                               strength="strong", marker=m.group("m"), ordinal=F.parse_num(m.group("n")))
                rest = x[m.end():]
            else:
                m = re.match(r"(?:自下|下|次)(?:明|釋|辨)", x)
                st = Statement(kind="enter", start=s, end=h.head_start, text=x, enter_kind="xia",
                               strength="strong", marker=m.group(0))
                rest = x[len(m.group(0)) - 1:] if m.group(0)[-1] in "明" else x[len(m.group(0)):]
            rest = re.sub(r"(?:之中|中)$", "", rest)
            st.x = rest
            st.heading = rest
            st.heading_verbatim = x
            out.append(st)
            h.subject, h.subject_start = "", h.head_start
            h.start = h.head_start
    return out


def _you_list_heads(text: str, qmap: QuoteMap) -> list:
    """序有通、別，從「如是」去、至「却坐一面」，通序也；從「爾時世尊」去、至品，別序也 (T1718 dev): X有A、B
    followed by one span clause per item; the label is the name the span clause gives (通序)."""
    out = []
    for m in F.YOU_LIST_RE.finditer(text):
        if qmap.kind_at(m.start()) is not None:
            continue
        short = m.group("items").split("、")
        send = m.end()
        while send < len(text) and text[send] not in "。？！":
            send += 1
        segs, a = [], m.end()
        for i in range(m.end(), send + 1):
            if i == send or text[i] in "；;":
                if i > a:
                    segs.append((a, i))
                a = i + 1
        if len(segs) != len(short):
            continue
        items = []
        for k, (a, b) in enumerate(segs):
            lab = clean_label(text, a, b)
            if not lab["locator"] or not lab["label"]:
                break
            items.append(Item(start=a, body_start=a, end=b, ordinal="", order_key=k, label=lab["label"],
                              label_start=lab["label_start"], label_end=lab["label_end"],
                              lemma=lab["lemma"], extent=lab["extent"], locator=lab["locator"]))
        if len(items) != len(short):
            continue
        hs = m.start("subj") + len(m.group("subj"))
        st = Statement(kind="announce", start=m.start(), end=min(len(text), send + 1),
                       text=text[m.start():send + 1], count=len(items), verb="有", head_start=hs,
                       head_end=m.end("items"), formula="you-list-span")
        st.listing = Listing(kind="span", items=items, end=min(len(text), send + 1))
        st.subject, st.subject_start = m.group("subj"), m.start()
        out.append(st)
    return out


def _rhetorical(text: str, head: Statement) -> bool:
    return F.RHETORICAL_RE.search(text[max(0, head.start - 3):head.start]) is not None


# ------------------------------------------------------------------------------------ entry markers


def _sentence_starts(text: str, openers: list, breaks=frozenset()) -> list:
    starts = {0} | set(breaks)
    for i, c in enumerate(text):
        if c in "。？！；;○" or c in "，," and text.startswith(("此初", "今初", "此即初"), i + 1):
            starts.add(i + 1)
        elif c in "，," and i >= 1 and text[i - 1] in "云曰" and text.startswith("此", i + 1):
            starts.add(i + 1)  # 世親釋云，此舉事校量也 (T1700)
        elif c in "：:" and re.match(r"(?:初|[一二三四五六七八九十]{1,3})[、，,]從", text[i + 1:i + 6]):
            starts.add(i + 1)  # 就禁父緣中即有其七：一、從爾時王舍大城以下 (T1753): the items follow the colon
        elif c in F.QUOTE_CLOSE and i >= 1 and text[i - 1] in "。？！" and re.match(
                r"(?:初|[一二三四五六七八九十]{1,3})[、，,]從", text[i + 1:i + 6]):
            starts.add(i + 1)  # …。」二、從有一太子下 (T1753): a span item opens right after a closed quotation
    for o in openers:
        starts.add(o.end)
    out = []
    for s in sorted(starts):
        while s < len(text) and text[s] in " 　○":
            s += 1
        if s < len(text):
            out.append(s)
    return sorted(set(out))


def _clean_heading(x: str) -> str:
    x = x.strip("，,、：:；;。 　")
    if len(x) > 1 and x.endswith("也"):
        x = x[:-1].rstrip("，,、")
    return x


PREV_SENTENCE_MAX = 600  # characters _prev_sentence looks back (a sentence holding a longer quotation is cut)


def _prev_sentence(text: str, s: int) -> str:
    """The sentence that ends right before the sentence start s (at a ；-start: the sentence so far),
    quotes included — _boundary_back stops at 「」 and would cut a citation 論云：「…」 short. A 。？！ inside a
    quotation ends no sentence of the text around it (論云：「迦羅是實時。示內弟子時」。 is one sentence, so
    the 云：「 that opens the quotation stays in view of the citation filter), unless it closes the quotation
    (「初句總，後句別。」當知諸句皆歎羅漢句耳。 returns the 當知 sentence only). A sentence that itself ends
    。」 is looked through to its opening quote. Looks back PREV_SENTENCE_MAX characters at most."""
    e = len(text[:s].rstrip(" 　○"))
    lo = max(e - PREV_SENTENCE_MAX, 0)
    k, depth = e - 1, 0
    while k >= lo and text[k] in F.QUOTE_CLOSE:  # the sentence ends inside quotations: look through them
        depth += 1
        k -= 1
    if k >= lo and text[k] in "。？！":  # its own final terminator
        k -= 1
    while k >= lo:
        ch = text[k]
        if ch in F.QUOTE_CLOSE:
            depth += 1
        elif ch in F.QUOTE_OPEN:
            depth = max(depth - 1, 0)
        elif ch in "。？！" and (depth == 0 or text[k + 1:k + 2] in tuple(F.QUOTE_CLOSE)):
            b = k + 1  # a boundary: outside every quotation, or the terminator that closes one (。」)
            while b < e and text[b] in F.QUOTE_CLOSE:
                b += 1
            return text[b:e]
        k -= 1
    return text[lo:e]


CITES_RE = re.compile(r"[云曰][：:]?「")


def _lemma_zhe_at(text: str, s: int) -> Statement | None:
    """「X」者 / 「X」， / 「X」N句 at a sentence start (F.LEMMA_ZHE_RE): Zhiyi takes up the word X of the
    sūtra (T1718 dev). Not an entry: X lists several items with 、 (「難陀、跋難陀」 inside the 目連 story,
    p0013c11); the comma form when the sentence before cites with 云：「 (論云：「迦羅是實時」，…。
    「三摩耶是假時」，… continues the citation, p0004b26; the 者 form after such a sentence stays: 「中」者
    p0005c28); any form at a ；-start whose sentence so far cites. What the gloss opens is the parser's
    decision (parser._resolve_lemma_zhe)."""
    m = F.LEMMA_ZHE_RE.match(text, s)
    if m is None:
        return None
    a = m.group("a")
    if "、" in a:
        return None
    before = text[:s].rstrip(" 　○")
    comma = m.group("f") in ("，", ",")
    if CITES_RE.search(_prev_sentence(text, s)) and (comma or before.endswith(("；", ";"))):
        return None
    st = Statement(kind="enter", start=m.start(), end=m.end(), text=m.group(0), enter_kind="lemma_zhe",
                   strength="strong", marker=m.group(0), x=a, lemma={"a": a, "b": None, "raw": a})
    if m.group("ext"):
        st.lemma["extent"] = m.group("ext")
    st.heading = a
    st.heading_verbatim = a
    return st


def _enter_at(text: str, s: int, unit: bool, mode: str) -> Statement | None:
    """The entry / closing marker starting at s, if any."""
    def mk(kind, m, enter_kind, strength, x="", ordinal=None, lemma=None, heading=None, verbatim=None):
        st = Statement(kind=kind, start=m.start(), end=m.end(), text=m.group(0), enter_kind=enter_kind,
                       strength=strength, marker=m.group(0), ordinal=ordinal, x=x, lemma=lemma)
        st.heading = _clean_heading(heading if heading is not None else x)
        st.heading_verbatim = _clean_heading(verbatim if verbatim is not None else m.group(0))
        return st

    if mode == "self-outlining":
        m = F.PROPONENT_RE.match(text, s)
        if m:  # 計我論者，謂如有一 (T1602): x = 計我, which sim() maps to the listed 我 by its last character
            return mk("enter", m, "proponent", "strong", x=m.group("x"))
        m = F.YUNHE_XIUXING_RE.match(text, s)
        if m:  # 云何修行施門？ (T1666 p0581c17) takes up 施門 of 修行有五門
            return mk("enter", m, "yunhe_men", "strong", x=m.group("x"), heading=m.group("x"),
                      verbatim=m.group("x"))
        m = F.SUOYAN_RE.match(text, s)
        if m:  # 所言覺義者 (T1666 p0576b11) takes up 覺義 of 此識有二種義
            return mk("enter", m, "suoyan", "strong", x=m.group("x"), heading=m.group("x"),
                      verbatim=m.group("m"))
    else:  # a quoted lemma is a quotation of the sūtra: sūtra mode only
        st = _lemma_zhe_at(text, s)
        if st is not None:
            return st
    m = F.ORD_LEMMA_RE.match(text, s)
    if m:
        a = m.group("a")
        return mk("enter", m, "ord_lemma", "strong", x=m.group("x"), ordinal=F.parse_num(m.group("n")),
                  lemma={"a": a, "b": None, "raw": a})
    m = F.ORD_SPAN_RE.match(text, s)
    if m:  # 善導: 一、從次作水想下，至內外映徹已來，總標地體 (T1753)
        a, b, n = m.group("a"), m.group("b"), m.group("n")
        has_end, lemma = b is not None, None
        if _incipit(a):
            b = b if _incipit(b) else None
            lemma = {"a": a, "b": b, "raw": a + ("至" + b if b else ""), "unbracketed": True}
        # Strong only where the item reads as 善導's: A is an incipit (labels._incipit) or the item states its end
        # (至B已來). Otherwise 二、從此無間已下，明四正斷 (T42n1828) is the weak numbered item it was before Task 8:
        # still placed when a division is waiting for a span item (31 of T1753's 246 span items, 三、從是為下，總結
        # among them), but when nothing takes it, it is neither an unmatched-enter nor a lost state.
        st = mk("enter", m, "ord_lemma", "strong" if lemma or has_end else "weak", x=m.group("x"),
                ordinal=1 if n == "初" else F.parse_num(n), lemma=lemma, verbatim=n + "、" + m.group("x"))
        st.formula = "cong-xia-zhi-lai"
        return st
    m = F.JIU_X_ZHONG_RE.match(text, s)
    if m and not F.jiu_x_zhong_anaphoric(m.group("x")) and (
            m.group("n") or m.group("tail") or m.group("num")):
        # 善導: 二、就水觀中，亦先舉，次辯，後結。即有其六 (T1753): enter 水觀 as item 2, child count 6
        n, x = m.group("n"), m.group("x")
        verbatim = ("%s、" % n if n else "") + "就" + x + ("位中" if m.group("m").endswith("位中") else "中")
        st = mk("enter", m, "jiu_zhong", "strong", x=x, ordinal=F.parse_num(n) if n else None,
                verbatim=verbatim)
        st.marker = m.group("m")
        st.formula = "jiu-x-zhong"
        if m.group("num"):
            st.count = F.parse_num(m.group("num"))
            st.verb, st.cls = "有其", m.group("cls") or ""
            st.subject_start = st.head_start = m.start("cv") if m.group("cv") else m.start("num") - 2
            st.head_end = m.end("cls") if m.group("cls") else m.end("num")
        return st
    m = F.PIN_DUAN_RE.match(text, s)
    if m:
        return mk("enter", m, "pin_duan", "strong", x=m.group("x"), ordinal=F.parse_num(m.group("n")))
    m = F.ORD_ENTER_RE.match(text, s)
    if m and F.parse_num(m.group("n")):
        pre = m.group("pre") or ""
        verb = m.group(0)[len(pre):]
        return mk("enter", m, "ordinal", "strong", x=m.group("x"), ordinal=F.parse_num(m.group("n")),
                  verbatim=verb)
    m = F.NEXT_ITEM_RE.match(text, s)
    if m:
        w = m.group("w")
        n = 1 if w == "初" else (None if w in ("次", "後") else F.parse_num(w.lstrip("第")))
        st = mk("enter", m, "next_item", "strong", x=m.group("x"), ordinal=n,
                verbatim=m.group(0).rstrip("也"))
        st.marker = m.group("m") + m.group("x")
        return st
    m = F.ANAPHOR_RE.match(text, s)
    if m:
        x = m.group("x") or ""
        return mk("enter", m, "anaphor", "strong", x=x, ordinal=1, heading=x,
                  verbatim=("初" + x) if x else "")
    m = F.CISHUO_RE.match(text, s)
    if m:
        pre = m.group("pre")
        return mk("enter", m, "cishuo", "strong" if mode == "self-outlining" else "weak",
                  x=m.group("x"), ordinal=1 if pre == "初" else None)
    m = F.YISHUO_RE.match(text, s)
    if m:
        return mk("close", m, "yishuo", "weak", x=m.group("x"))
    m = F.MING_JING_RE.match(text, s)
    if m:  # 善導: 上來雖有七句不同，廣明禁父緣竟 (T1753)
        st = mk("close", m, "ming_jing", "weak", x=m.group("x"), verbatim=m.group("v") + m.group("x"))
        st.formula = "ming-x-jing"
        return st
    m = F.CLOSE_RE.match(text, s)
    if m:
        return mk("close", m, "close", "weak", x=m.group("x"))
    m = F.XIA_RE.match(text, s)
    if m and (m.group("v") or (unit and m.group("pre") in ("下", "自下"))):
        pre = m.group("pre")
        heading = (m.group("v") or "") + m.group("x")
        strength = "strong" if pre in ("下", "自下") else "weak"
        return mk("enter", m, "xia", strength, x=heading, heading=heading, verbatim=heading)
    m = F.THIS_RE.match(text, s)
    if m:
        return mk("enter", m, "this", "weak", x=m.group("x"), verbatim=m.group("x"))
    m = F.NUM_ZHE_RE.match(text, s)
    if m and (m.group("n") == "初" or F.parse_num(m.group("n"))):
        return mk("enter", m, "num_zhe", "weak", x=m.group("x"),
                  ordinal=1 if m.group("n") == "初" else F.parse_num(m.group("n")))
    m = F.NUM_ITEM_RE.match(text, s)
    if m and F.parse_num(m.group("n")):
        return mk("enter", m, "num_item", "weak", x=m.group("x"), ordinal=F.parse_num(m.group("n")))
    m = F.X_ZHE_RE.match(text, s)
    if m and m.group("x")[0] not in F.FUNCTION_HEAD:  # 若無常者 / 若即於蘊施設我者 (T1602) name no part
        return mk("enter", m, "x_zhe", "weak", x=m.group("x"))
    return None


# ------------------------------------------------------------------------------------ scan


def scan(text: str, *, mode: str = "sutra", breaks=None) -> list:
    """All statements of text in document order (see the module docstring). breaks: offsets that end a
    sentence although no punctuation marks it (headings, from the line records)."""
    breaks = frozenset(b for b in (breaks or ()) if 0 < b < len(text))
    sorted_breaks = sorted(breaks)
    qmap = QuoteMap(quote_spans(text))
    lemmas, openers = [], []
    for m in F.OPENER_RE.finditer(text):
        if qmap.kind_at(m.start()) is None:
            openers.append(Statement(kind="opener", start=m.start(), end=m.end(), text=m.group(0)))
    if mode != "self-outlining":
        for m in F.SUTRA_LEMMA_RE.finditer(text):
            q = m.group("q")
            a, _, b = q.partition("至")
            # Kuiji's lemma has its opener right behind it (經「A至B」。贊曰：, T1723 p0850a19); a 經「…」 in prose
            # is a citation (T1705: 經「千」字者非, a textual note) and must not arm the parser's gloss guard
            armed = any(0 <= o.start - m.end() <= 2 for o in openers)
            lemmas.append(Statement(kind="lemma", start=m.start(), end=m.end(), text=m.group(0),
                                    formula="zanyue-lemma" if armed else "sutra-cite",
                                    lemma={"a": a, "b": b or None, "raw": q}))
        covered = {o.start for o in openers
                   if any(0 <= o.start - lm.end <= 2 for lm in lemmas)}
        for o in openers:  # 如是我聞。贊曰： — the sentence before the opener is the lemma (T1772)
            if o.start in covered:
                continue
            if o.start > 0 and text[o.start - 1] in F.QUOTE_CLOSE:  # 「須菩提！…」述曰 (T1700)
                depth, a = 0, o.start - 1
                while a >= 0:
                    if text[a] in F.QUOTE_CLOSE:
                        depth += 1
                    elif text[a] in F.QUOTE_OPEN:
                        depth -= 1
                        if depth == 0:
                            break
                    a -= 1
                if a >= 0 and o.start - a <= 400:
                    q = text[a + 1:o.start - 1]
                    lemmas.append(Statement(kind="lemma", start=a, end=o.start, text=text[a:o.start],
                                            formula="quoted-lemma", lemma={"a": q, "b": None, "raw": q}))
                continue
            b = o.start
            while b > 0 and text[b - 1] in "。 　":
                b -= 1
            a = b
            while a > 0 and text[a - 1] not in "。？！；」○":
                a -= 1
            q = text[a:b]
            if 0 < len(q) <= 60 and qmap.kind_at(a) is None:
                lemmas.append(Statement(kind="lemma", start=a, end=b, text=q, formula="opener-lemma",
                                        lemma={"a": q, "b": None, "raw": q}))
    heads = _head_candidates(text, qmap, breaks)
    lemma_regions = [(lm.start, lm.end) for lm in lemmas]

    def in_lemma(pos):
        return any(a <= pos < b for a, b in lemma_regions)

    heads = [h for h in heads if not in_lemma(h.start)]
    subject_enters = _split_subject_markers(text, heads, mode)
    # listings, later heads first, so that an earlier listing knows where nested ones sit
    for i in range(len(heads) - 1, -1, -1):
        h = heads[i]
        if h.listing is not None:
            continue
        if _rhetorical(text, h):
            h.kind = "rhetorical"
            continue
        nested = [(x.subject_start if x.subject else x.start, x.listing.end) for x in heads[i + 1:]
                  if x.listing is not None and len(x.listing.items) >= 2]
        closed = text[h.end:h.end + 1] in "。"
        j = bisect.bisect_right(sorted_breaks, h.end)
        stop = sorted_breaks[j] if j < len(sorted_breaks) else None
        h.listing = parse_listing(text, h.end, count=h.count if h.cls[-1:] not in F.EXTENT_CLS else None,
                                  head_cls=h.cls, nested=nested, sentence_closed=closed, stop_at=stop)
        if mode == "self-outlining" and h.count and h.listing.kind != "ordinal":
            # 此識有二種義，能攝一切法、生一切法。云何為二？一者、覺義…: the count question opens the next
            # sentence; the listing is the enumeration after it, not the clause after the head
            md = F.DEFERRED_RHETORICAL_RE.match(text, h.end)
            if md and F.parse_num(md.group("n")) == h.count and (stop is None or md.end() < stop):
                deferred = parse_listing(text, md.end(), count=h.count, head_cls=h.cls, nested=nested,
                                         sentence_closed=True, stop_at=stop)
                if deferred.kind == "ordinal" and deferred.rhetorical:
                    deferred.deferred = True  # judge grants its +2 only when the items are taken up
                    h.listing = deferred
        if h.cls[-1:] in F.EXTENT_CLS and h.listing.items:
            h.total = h.total or text[h.head_start:h.head_end]
            h.count = len(h.listing.items)
        elif h.cls[-1:] in F.EXTENT_CLS:
            h.count = None
        elif h.count is None and h.listing.items:
            h.count = len(h.listing.items)
        h.end = max(h.end, h.listing.end if h.listing.items else h.end)
        h.formula = h.formula or _formula_slug(text, h)
    heads = [h for h in heads if h.kind != "rhetorical"]
    uddanas = []
    for m in F.UDDANA_RE.finditer(text):
        lst = uddana_listing(text, m.end(), expected=uddana_count(text, m.start()))
        if len(lst.items) >= 2:
            # no subject: it starts at the head (not 0, which made the division's raw and explained
            # position reach back to the start of the text)
            st = Statement(kind="uddana", start=m.start(), end=lst.end, text=text[m.start():lst.end],
                           count=len(lst.items), listing=lst, formula="uddana", subject_start=m.start(),
                           head_start=m.start(), head_end=m.end())
            uddanas.append(st)
    # entry and closing markers at sentence starts (and 自下第N after a comma)
    unit_starts = {o.end for o in openers}
    for lm in lemmas:
        e = lm.end
        while e < len(text) and text[e] in "。 　":
            e += 1
        unit_starts.add(e)
    enters = []
    starts = set(_sentence_starts(text, openers, breaks))
    starts.update(m.start() for m in re.finditer(r"(?:自下|從此以下|從此已下)第", text))
    # 上明說經因起分，下明發請廣說分 (T1772): the entry after a closing clause
    starts.update(m.start(1) for m in re.finditer(r"上(?:明|來|已)[^。；，,]{1,14}[，,]((?:自下|下)(?:明|釋|辨)?)", text))
    for s in sorted(starts):
        if in_lemma(s):
            continue
        q = qmap.kind_at(s)
        if q in ("lemma", "term", "citation", "question"):
            continue
        st = _enter_at(text, s, s in unit_starts, mode)
        if st is not None:
            enters.append(st)
        elif mode != "self-outlining":
            m = F.QUOTE_XIA_RE.match(text, s)
            if m and s not in unit_starts:
                a = m.group("a")
                lemmas.append(Statement(kind="lemma", start=m.start(), end=m.end(), text=m.group(0),
                                        formula="quote-xia",
                                        lemma={"a": a, "b": m.group("b"), "raw": m.group(0)}))
    # walk: listings consume their region; nested heads inside a listing are kept
    cands = sorted(lemmas + openers + heads + uddanas + enters + subject_enters,
                   key=lambda st: (st.start, _PRIO.get(st.kind, 9)))
    out, consumed_until, consumer_nested, consumer = [], -1, [], None
    for st in cands:
        if st.start < consumed_until:
            if st.kind in ("announce", "gate") and any(a <= st.start < b for a, b in consumer_nested):
                st.outer = consumer
                st.outer_item = max((k for k, it in enumerate(consumer.items) if it.start <= st.start),
                                    default=None)
                out.append(st)
            continue
        out.append(st)
        if st.kind in ("announce", "gate", "uddana") and st.listing and st.listing.items:
            consumed_until = st.end
            consumer = st
            consumer_nested = [(x.start, x.end) for x in heads
                               if x is not st and st.start < x.start < st.end and x.listing
                               and len(x.listing.items) >= 2]
        elif st.kind in ("lemma", "enter", "close", "opener"):
            consumed_until = max(consumed_until, st.end)
    out.sort(key=lambda st: (st.start, _PRIO.get(st.kind, 9)))
    _context(text, out, qmap)
    return out


_PRIO = {"lemma": 0, "opener": 1, "enter": 2, "close": 2, "gate": 3, "uddana": 3, "announce": 4}


def _formula_slug(text: str, h: Statement) -> str:
    """A slug in the vocabulary of tests/fixtures/kepan-formulae/README.md (informational)."""
    subj, verb, cls = h.subject, h.verb, h.cls
    if h.kind == "gate":
        return "men-liaojian" if verb == "料簡" else ("men-fenbie" if verb == "分別" else "cong-xia-zhi-fen")
    if h.listing and h.listing.kind == "span":
        return "fen-wei-n-cong-zhi"
    if cls[-1:] in F.EXTENT_CLS and h.listing and h.listing.items:
        return "zhong-you-n-ju"
    if subj.startswith("就") and verb in ("又",):
        return "jiu-you-n"
    if subj.startswith("就") and "開" in (subj + verb):
        return "jiu-kai-wen-wei-n"
    if subj.startswith("就中") or subj == "就中":
        return "jiu-zhong"
    if verb in ("亦", "復", "又", "更") or subj in ("初中", "後中") or re.fullmatch(r"[一二三四五六七八九十]+中", subj):
        return "chu-zhong-yi-n"
    if "凡" in text[h.head_start:h.head_end] and cls == "段":
        return "fan-you-n-duan"
    if "大分" in text[h.head_start:h.head_end] or verb == "大分為":
        return "da-fen-wei-n"
    if subj.endswith("文") and "別" in text[h.head_start:h.head_end]:
        return "wen-bie-you-n"
    if cls == "分" and subj.endswith("文") and verb == "有":
        return "wen-you-n-fen"
    if cls == "分" and "總" in text[h.head_start:h.head_end] or "略有" in text[h.head_start:h.head_end]:
        return "zong-you-n-fen"
    if cls == "分" and text[h.head_start - 1:h.head_start] == "說":
        return "shuo-you-n-fen"
    if subj.endswith("文") and verb == "為":
        return "wen-wei-n"
    if subj.startswith("此中") or subj == "此中" or subj == "於中":
        return "ci-zhong"
    if subj.endswith("中") and verb == "有":
        return "zhong-you-n"
    if verb in ("分為", "細分為", "開為"):
        return "fen-wei-n"
    if verb == "分":
        return "fen-n"
    if verb == "有":
        return "you-n"
    return verb


def _context(text: str, stmts: list, qmap: QuoteMap) -> None:
    """after / unit_start / in_question of each statement."""
    prev = None
    unit_open = False
    for st in stmts:
        gap = text[prev.end:st.start] if prev is not None else text[:st.start]
        adjacent = prev is not None and all(c in F.ALL_PUNCT for c in gap)
        st.after = prev.kind if adjacent else "text"
        if prev is not None and prev.kind == "enter" and adjacent:
            st.after = "enter"
        if st.kind in ("lemma", "opener"):
            unit_open = True
        elif unit_open:
            st.unit_start = adjacent or prev is None
            unit_open = False
        if st.kind in ("announce", "gate"):
            st.in_quote = st.in_quote or qmap.kind_at(st.start)
            sent = _boundary_back(text, st.start, stops="。？！")
            before = text[sent:st.start]
            st.in_question = st.in_quote == "question" or (
                any(q in before for q in F.QUESTION_OPEN) and "答" not in before)
        if st.outer is None or st.kind in ("lemma", "opener", "enter", "close") or st.listing and st.listing.items:
            prev = st
