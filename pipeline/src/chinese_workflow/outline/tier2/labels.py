"""Listings and labels: the items an announcement lists, and each item's label by the label rule of
tests/fixtures/kepan-formulae/README.md.

Input : the reading text (CBETA punctuation kept) and the position right after an announcement head.
Output: a Listing — its items in document order, each with offsets into the text, the verbatim item,
        its label (a contiguous piece of the text), a quoted lemma or span it carries, and an extent.

Label rule (README "Label rule", items 1-5): an item starts at an ordinal word (一…十, 一者, 第一, 初, 次,
後, 先, 餘, 中間, 中) or, in unnumbered lists, at 、 (or ；, or a span 從…至…); it ends at the next ordinal,
at 。 or ；, or where a nested announcement with its own listing starts; commas do not end it. From the
front remove the ordinal and its punctuation, a pointer (此 / 下), a locator (「A」下, 從…至…, 始於…訖…,
a count of lines, verses or 品) and a copula after the locator (為, 名, 是, 是其); from the end a final 也
and punctuation. Uddāna fillers (與, 及, 最為後, 分別, 略辯相應知) are dropped (R01 uddana, T1579); with a
count announced before the head, a closing phrase restating it (名十六異論) and a verse-initial 執 / 謂 on the
first item go too (T1602).
Document order: 初…後…中間… lists 1, 3, 2 (README pos-zhong-you-n-ju-*): 中 / 中間 items go before 後.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .formulae import (
    ANAPHOR_RE,
    BOOKSPAN_RE,
    COPULA_RE,
    EXTENT_CLS,
    EXTENT_RE,
    SPAN_RE,
    SPAN_WEAK_RE,
    UDDANA_CLOSERS,
    UDDANA_FILLERS,
    UDDANA_HEAD_RE,
    UDDANA_LEAD_VERBS,
    parse_num,
)

BOUNDARY = "、，,；;。：:？！"
SENT_STOP = "。？！"
LABEL_STOP = "。；;？！"
TRIM = "，,、：:；;。．.？！ 　「」『』"
LEAD = "，,、：:；;。．.？！ 　"
NUM1 = "一二三四五六七八九十"
NEW_UNIT = ("經「", "贊曰", "述曰", "疏曰")
TAIL_ANAPHOR_RE = re.compile(r"[，,](?=(?:此|今)(?:即)?初(?:[^\s，,。；：:「」]{0,2}?)(?:文|段|分)?(?:也)?(?:[。；]|$))")
QUOTE_XIA_LOC_RE = re.compile(
    r"(?:從)?「(?P<a>[^」]{1,40})」(?:等)?(?:以下|已下|下|去)?[，,、]?"
    r"(?:(?:至|訖|盡|竟|乃至)(?:「(?P<b>[^」]{1,40})」|[^，,。；「」]{1,8}(?=[，,])))?(?:已來|以來)?[，,]?"
)


@dataclass
class Item:
    start: int  # ordinal start (or item start in unnumbered lists)
    body_start: int  # after the ordinal and its punctuation
    end: int  # end of the item's label region (exclusive)
    ordinal: str  # the ordinal word as written ('' for unnumbered)
    order_key: float  # position in document order (中 / 中間 before 後)
    label: str = ""
    label_start: int = 0
    label_end: int = 0
    lemma: dict | None = None  # {"a", "b", "raw"} from a quoted locator
    extent: str | None = None  # 三頌, 有八句 … when a count locator was stripped
    locator: str | None = None  # the locator text removed (span or lemma)
    kind: str = ""  # 'first' | 'num' | 'next' | 'last' | 'mid' (ordinal lists)


@dataclass
class Listing:
    kind: str  # 'ordinal' | 'unnumbered' | 'span' | 'uddana' | 'none'
    items: list = field(default_factory=list)
    end: int = 0  # end of the listing region (exclusive)
    intro: str | None = None  # 謂 / 所謂 / 為 introducing unnumbered items
    rhetorical: bool = False  # 云何為N？ skipped before the items
    deferred: bool = False  # scanner, self-outlining: the count question opened the sentence after the head's clause
    complete: bool = True
    family: str = ""

    def labels(self) -> list:
        return [it.label for it in self.items]


# ------------------------------------------------------------------------------------ ordinals


def num_ordinal(text: str, q: int, want: int) -> tuple | None:
    """(ordinal text, end) when a numeral ordinal with value `want` starts at q: 二 / 第二 / 二者 / 二、;
    of a run of numerals the prefix with that value is taken (一三昧分 -> 一 + 三昧分)."""
    p = q + 1 if text.startswith("第", q) else q
    j = p
    while j < len(text) and j - p < 3 and text[j] in NUM1:
        j += 1
    for e in range(j, p, -1):
        if parse_num(text[p:e]) == want:
            end = e
            if end < len(text) and text[end] in "者是":
                end += 1
            while end < len(text) and text[end] in "、，,：:":
                end += 1
            return text[q:end], end
    return None


def match_ordinal(text: str, q: int, family: str, k: int, after_last: bool) -> tuple | None:
    """Is an expected next ordinal at q? family: 'num' | 'chu' | 'xian' | 'qian'; k = items so far.
    Returns (ordinal_text, body_start, kind) or None. kind: 'num' | 'next' | 'last' | 'mid'."""
    if q >= len(text):
        return None
    ch = text[q]
    if ch in NUM1 or ch == "第":
        mo = num_ordinal(text, q, k + 1)
        if mo and not after_last and _plausible_after_num(text, mo[1]):
            return mo[0], mo[1], "num"
        return None
    if family == "num":
        words = [] if after_last else ["後", "最後"]  # 一聖益、後凡益 (T1772)
    else:
        words = ["中間", "中"] if after_last else ["次", "後", "餘", "最後", "中間"]
    for w in sorted(words, key=len, reverse=True):
        if text.startswith(w, q):
            end = q + len(w)
            if end < len(text) and text[end] in "中" and w in ("後", "次"):
                return None  # 後中有二: a subject, not an item
            if w in ("中", "中間") and end < len(text) and text[end] in "有亦復":
                return None
            if w == "次" and text.startswith("次第", q):
                return None
            while end < len(text) and text[end] in "、，,：:":
                end += 1
            kind = {"次": "next", "後": "last", "最後": "last", "餘": "last"}.get(w, "mid")
            return text[q:end], end, kind
    return None


def _plausible_after_num(text: str, pos: int) -> bool:
    """A numeral ordinal is followed by a CJK character or a locator, not by another numeral or a
    closing mark."""
    if pos >= len(text):
        return False
    return text[pos] not in "。；？！」』" and not text[pos].isdigit()


def first_ordinal(text: str, p: int) -> tuple | None:
    """(family, ordinal text, body start) for a first item at p."""
    mo = num_ordinal(text, p, 1)
    if mo and _plausible_after_num(text, mo[1]):
        if not text.startswith(("一切", "一時", "一一"), p):
            return "num", mo[0], mo[1]
    for w, fam in (("最初", "chu"), ("初", "chu"), ("先", "xian"), ("前", "qian")):
        if text.startswith(w, p):
            end = p + len(w)
            if end < len(text) and text[end] in "中" and w != "前":
                return None  # 初中亦二: a subject
            while end < len(text) and text[end] in "、，,：:":
                end += 1
            return fam, text[p:end], end
    return None


# ------------------------------------------------------------------------------------ labels


NOT_INCIPIT_END = ("品", "分", "段", "偈", "卷", "初", "末", "後", "經", "文", "頌", "章")


def _incipit(x: str | None) -> bool:
    """Whether an unbracketed span end reads as quoted root text (如是我聞, 一時佛在) rather than a
    chapter or section name (序, 〈安樂行〉, 經末, 偈後, 下品下生 is still accepted and simply not found)."""
    return bool(x) and len(x) >= 3 and not any(ch in x for ch in "〈〉《》「」") and \
        not x.endswith(NOT_INCIPIT_END) and not x.startswith(("此", "初", "經", "偈"))


def clean_label(text: str, start: int, end: int, *, head_cls: str = "") -> dict:
    """Apply the label rule to text[start:end] (one item without its ordinal). Returns {label,
    label_start, label_end, lemma, extent, locator}."""
    s, e = start, end
    # the label ends at the first 。 or ；
    for i in range(s, e):
        if text[i] in LABEL_STOP:
            e = i
            break
    s = _skip(text, s, e)
    lemma = extent = locator = None
    stripped_locator = False
    for _ in range(4):
        s = _skip(text, s, e)
        seg = text[s:e]
        m = QUOTE_XIA_LOC_RE.match(seg) if seg.startswith(("「", "從「")) else None
        if m and m.end() < len(seg) and (m.group(0).endswith(("下", "，", ",", "去", "來", "、"))
                                          or "下" in m.group(0)):
            lemma = {"a": m.group("a"), "b": m.group("b"), "raw": m.group(0).rstrip("，,、")}
            locator = m.group(0)
            s += m.end()
            stripped_locator = True
            continue
        m = SPAN_RE.match(seg) if seg.startswith(("從", "自從", "始於", "始從", "自")) else None
        if m and m.end() < len(seg):
            a, b = m.group("a"), m.group("b")
            if a and a.startswith("「") or b and b.startswith("「"):
                lemma = {"a": (a or "").strip("「」"), "b": (b or "").strip("「」") or None,
                         "raw": m.group(0).rstrip("，,")}
            elif _incipit(a):
                # an unbracketed incipit, as CBETA prints 善導's 從如是我聞下，至…已來 (T1753): kept
                # as the lemma; the anchor sets a span only where it finds the words in the root text
                lemma = {"a": a, "b": b if _incipit(b) else None,
                         "raw": m.group(0).rstrip("，,"), "unbracketed": True}
            locator = m.group(0)
            s += m.end()
            stripped_locator = True
            continue
        m = SPAN_WEAK_RE.match(seg) or BOOKSPAN_RE.match(seg)
        if m and m.end() < len(seg):
            locator = m.group(0)
            s += m.end()
            stripped_locator = True
            continue
        m = EXTENT_RE.match(seg)
        if m and m.end() < len(seg) and m.group(0):
            if m.group("u") or _copula_follows(seg, m.end()):
                extent = m.group(0).rstrip("，,")
                s += m.end()
                stripped_locator = True
                continue
        if head_cls and head_cls[-1:] in EXTENT_CLS:
            m = re.match(r"[一二三四五六七八九十]+(?=[^一二三四五六七八九十])", seg)
            if m and m.end() < len(seg) and not stripped_locator:
                extent = m.group(0)
                s += m.end()
                stripped_locator = True
                continue
        break
    s = _skip(text, s, e)
    if stripped_locator:
        m = COPULA_RE.match(text, s)
        if m and m.end() < e:
            s = m.end()
    # final 也 and punctuation
    while e > s and text[e - 1] in TRIM:
        e -= 1
    if e - s > 1 and text[e - 1] == "也":
        e -= 1
        while e > s and text[e - 1] in TRIM:
            e -= 1
    while s < e and text[s] in TRIM:
        s += 1
    return {"label": text[s:e], "label_start": s, "label_end": e, "lemma": lemma, "extent": extent,
            "locator": locator}


def _copula_follows(seg: str, pos: int) -> bool:
    return pos < len(seg) and seg[pos] in "為名是"


def _skip(text: str, s: int, e: int) -> int:
    while s < e and text[s] in LEAD:
        s += 1
    return s


# ------------------------------------------------------------------------------------ listings


def parse_listing(text: str, pos: int, *, count: int | None, head_cls: str = "",
                  nested: list | None = None, stop_at: int | None = None,
                  sentence_closed: bool = False) -> Listing:
    """Parse the items that follow an announcement head ending at pos.

    count: the announced count (None when the head gives none, e.g. 就中初牒、次疑).
    nested: [(clause_start, end)] regions of other announcements with listings (skipped by the
    search for the next ordinal; an item's label ends where one starts).
    sentence_closed: the head ended its sentence (總有三分。初…): the first item must open a sentence.
    """
    n = len(text)
    limit = n if stop_at is None else min(n, stop_at)
    nested = nested or []
    p = pos
    while p < limit and text[p] in "：:，, 　":
        p += 1
    listing = Listing(kind="none", end=pos)
    # a rhetorical count question before the items (說有五分。云何為五？一者…)
    if p < limit and text[p] in SENT_STOP:
        p += 1
        sentence_closed = True
    m = re.match(r"(?:云何|何等|何者)(?:為|名)?[一二三四五六七八九十]+[？?。]", text[p:limit])
    if m:
        p += m.end()
        listing.rhetorical = True
        sentence_closed = True
    intro = None
    m = re.match(r"(?:所謂|謂|即)[：:]?", text[p:limit])
    if m:
        intro = m.group(0).rstrip("：:")
        p += m.end()
    listing.intro = intro
    fo = first_ordinal(text, p) if p < limit else None
    if fo is None and sentence_closed:
        return listing
    if fo is not None:
        return _ordinal_listing(text, p, fo, count=count, head_cls=head_cls, nested=nested,
                                limit=limit, listing=listing)
    return _unnumbered_listing(text, p, count=count, head_cls=head_cls, limit=limit, listing=listing)


def _in_nested(q: int, nested: list) -> tuple | None:
    for a, b in nested:
        if a <= q < b:
            return a, b
    return None


def _ordinal_listing(text, p, fo, *, count, head_cls, nested, limit, listing) -> Listing:
    family, otext, body = fo
    listing.kind, listing.family = "ordinal", family
    # 一者…二者 after 云何為N？ (śāstra enumerations) keep their items far apart; others stay close
    strong = listing.rhetorical or otext.rstrip("、，,：: ").endswith("者")
    max_sent, max_chars = (12, 1500) if strong else (3, 220)
    raw = [[p, body, otext, "first", None]]  # [start, body_start, ordinal, kind, nested_hint]
    k, after_last = 1, False
    q, crossed, since = body + 1, 0, 0
    while q < limit:
        if count is not None and k >= count:
            break
        region = _in_nested(q, nested)
        if region is not None:
            if raw[-1][4] is None:
                raw[-1][4] = region[0]
            q = region[1]
            continue
        if text.startswith(NEW_UNIT, q):
            break
        prev = text[q - 1]
        at_sent, at_clause = prev in SENT_STOP, prev in "；;"
        if at_sent:
            crossed += 1
            if ANAPHOR_RE.match(text, q):
                break
        if prev in BOUNDARY:
            allowed = crossed == 0 or (count is not None and (at_sent or at_clause)
                                       and crossed <= max_sent and since <= max_chars)
            if allowed:
                mo = match_ordinal(text, q, family, k, after_last)
                if mo is not None and not (mo[2] == "mid" and family == "num"):
                    raw.append([q, mo[1], mo[0], mo[2], None])
                    k += 1
                    crossed = since = 0
                    after_last = after_last or mo[2] == "last"
                    q = mo[1] + 1
                    continue
            if at_sent and (count is None or crossed > max_sent):
                break
        since += 1
        q += 1
    if count is not None and len(raw) < count:
        raw = _plain_gaps(text, raw, count, limit) or raw
    if count is not None and len(raw) < count:
        raw.extend(_plain_tail(text, raw[-1][1], count - len(raw), limit))
    items = []
    for idx, (start, bstart, otext_i, kind, hint) in enumerate(raw):
        nxt = raw[idx + 1][0] if idx + 1 < len(raw) else None
        end = nxt if nxt is not None else _sentence_end(text, bstart, limit)
        if nxt is None:  # …明不顛倒心，此初。 (T1700): the anaphor after a comma ends the listing
            m = TAIL_ANAPHOR_RE.search(text, bstart, end)
            if m:
                end = m.start()
            inner = [a for a, b in nested if bstart < a < end]
            if inner and hint is None:
                hint = min(inner)  # 五、…復是一會，亦有三分：… — a nested listing ends the last item
        if hint is not None and hint < end:
            end = hint
        lab = clean_label(text, bstart, end, head_cls=head_cls)
        it = Item(start=start, body_start=bstart, end=end, ordinal=otext_i, order_key=float(idx),
                  label=lab["label"], label_start=lab["label_start"], label_end=lab["label_end"],
                  lemma=lab["lemma"], extent=lab["extent"], locator=lab["locator"])
        it.kind = kind
        items.append(it)
    # document order: 中 / 中間 items listed after the 後 / 餘 item go before it
    lasts = [i for i, it in enumerate(items) if it.kind == "last"]
    if lasts:
        for it in items[lasts[0] + 1:]:
            if it.kind == "mid":
                it.order_key = lasts[0] - 0.5
    items.sort(key=lambda it: it.order_key)
    listing.items = items
    last_end = max(it.end for it in items)
    if last_end < limit and text[last_end] in "，,":
        listing.end = last_end + 1  # an anaphor follows on the same sentence
    else:
        listing.end = _sentence_end(text, last_end, limit, include=True)
    listing.complete = count is None or len(items) == count
    return listing


def _plain_gaps(text: str, raw: list, count: int, limit: int) -> list | None:
    """初品為序段；從〈方便〉至〈安樂行〉，開三顯一段；…；後去餘勢，流通段 (T1718 dev): unnumbered items
    separated by ； between numbered ones. Returns the completed raw list when that yields `count`."""
    out = []
    for idx, r in enumerate(raw):
        out.append(r)
        nxt = raw[idx + 1][0] if idx + 1 < len(raw) else _sentence_end_only(text, r[1], limit)
        first = text.find("；", r[1], nxt)
        if first < 0:
            continue
        for a, _ in _split(text, first + 1, nxt, "；"):
            out.append([a, a, "", "plain", None])
    return out if len(out) == count else None


def _plain_tail(text: str, body: int, missing: int, limit: int) -> list:
    """A list that numbers its first item only (初品為序；〈方便品〉訖…名正；從偈後盡經…名流通, R01 wen-wei-n):
    the rest of the sentence, split at ；, when that yields exactly the missing items."""
    send = _sentence_end_only(text, body, limit)
    first = text.find("；", body, send)
    if first < 0:
        return []
    parts = _split(text, first + 1, send, "；")
    if len(parts) != missing:
        return []
    return [[a, a, "", "plain", None] for a, _ in parts]


def _sentence_end_only(text: str, s: int, limit: int) -> int:
    for i in range(s, limit):
        if text[i] in SENT_STOP:
            return i
    return limit


def _sentence_end(text: str, s: int, limit: int, include: bool = False) -> int:
    for i in range(s, limit):
        if text[i] in LABEL_STOP:
            return i + 1 if include else i
    return limit


def _clause_start(text: str, pos: int, floor: int) -> int:
    """Start of the clause holding pos (after the previous comma / colon), not before floor."""
    i = pos
    while i > floor and text[i - 1] not in "，,：:、":
        i -= 1
    return i if i > floor else pos


def _unnumbered_listing(text, p, *, count, head_cls, limit, listing) -> Listing:
    """Items without ordinals: split at ； / 、 / ， (whichever yields the announced count), or span
    items 從…至… across sentences."""
    send = _sentence_end(text, p, limit)
    seg = text[p:send]
    if not seg:
        return listing
    # span items across sentences (從初訖「…」以來，略嘆。從「…」以下…，廣嘆德也。)
    if seg.startswith(("從", "自從", "始於")) and count:
        items, q = [], p
        while q < limit and len(items) < count:
            e = _sentence_end(text, q, limit)
            if not text.startswith(("從", "自從", "始於", "自"), q):
                break
            lab = clean_label(text, q, e, head_cls=head_cls)
            items.append(Item(start=q, body_start=q, end=e, ordinal="", order_key=len(items),
                              label=lab["label"], label_start=lab["label_start"],
                              label_end=lab["label_end"], lemma=lab["lemma"], extent=lab["extent"],
                              locator=lab["locator"]))
            q = e + 1
        if len(items) == count:
            listing.kind, listing.items = "span", items
            listing.end = min(limit, items[-1].end + 1)
            return listing
    for sep in ("；", "、", "，"):
        parts = _split(text, p, send, sep)
        if len(parts) < 2:
            continue
        if count is not None and len(parts) != count:
            continue
        if count is None and (sep != "、" or any(b - a > 4 for a, b in parts)):
            continue
        items = []
        for a, b in parts:
            lab = clean_label(text, a, b, head_cls=head_cls)
            items.append(Item(start=a, body_start=a, end=b, ordinal="", order_key=len(items),
                              label=lab["label"], label_start=lab["label_start"],
                              label_end=lab["label_end"], lemma=lab["lemma"], extent=lab["extent"],
                              locator=lab["locator"]))
        if all(it.label for it in items):
            listing.kind, listing.items = "unnumbered", items
            listing.end = min(limit, send + 1)
            return listing
    return listing


def _split(text: str, a: int, b: int, sep: str) -> list:
    """[(start, end)] of the pieces of text[a:b] separated by sep outside quotes."""
    out, depth, s = [], 0, a
    for i in range(a, b):
        c = text[i]
        if c in "「『〈《":
            depth += 1
        elif c in "」』〉》":
            depth = max(0, depth - 1)
        elif c == sep and depth == 0:
            out.append((s, i))
            s = i + 1
    out.append((s, b))
    return [(x, y) for x, y in out if y > x]


def uddana_count(text: str, head_start: int) -> int | None:
    """The count announced right before an uddāna head starting at head_start (何等十六？ / 有N種。, within 24
    characters), else None."""
    m = UDDANA_HEAD_RE.search(text[max(0, head_start - 24):head_start])
    return parse_num(m.group("n") or m.group("n2")) if m else None


def uddana_listing(text: str, pos: int, limit: int | None = None, *, expected: int | None = None) -> Listing:
    """The verse after 嗢拕南曰：, up to 。, split at 、 and ，; fillers dropped (R01 uddana, T1579).

    expected: the count announced before the head (uddana_count), or None. With one piece too many, a last
    piece that restates the count (名十六異論, T31n1602 p0521b16) is a closing phrase, not an item, and a
    verse-initial verb on the first piece (執因中有果) is not part of its label; with no count, a closing piece
    goes only when it carries a numeral, and the first item stays as written."""
    limit = len(text) if limit is None else limit
    p = pos
    while p < limit and text[p] in "：: ":
        p += 1
    send = _sentence_end(text, p, limit)
    items = []
    s = p
    for i in range(p, send + 1):
        if i == send or text[i] in "、，,":
            a, b = s, i
            s = i + 1
            a0 = a
            for f in ("與", "及", "并"):
                if text.startswith(f, a) and b - a > len(f):
                    a += len(f)
            for f in ("最為後", "分別"):
                if text[a:b].endswith(f) and b - a > len(f):
                    b -= len(f)
            piece = text[a:b]
            if not piece or piece in UDDANA_FILLERS or piece.endswith("相應知"):
                continue
            items.append(Item(start=a0, body_start=a, end=b, ordinal="", order_key=len(items),
                              label=piece, label_start=a, label_end=b))
    surplus = expected is not None and len(items) == expected + 1
    last = items[-1] if items else None
    if last is not None and len(items) >= 3 and len(last.label) >= 3 and last.label.startswith(UDDANA_CLOSERS) \
            and (surplus or expected is None and any(c in NUM1 for c in last.label)):
        items.pop()
        first = items[0]
        if surplus and first.label[:1] in UDDANA_LEAD_VERBS and len(first.label) > 2:
            first.body_start += 1
            first.label_start += 1
            first.label = first.label[1:]
    return Listing(kind="uddana", items=items, end=min(limit, send + 1), complete=True)
