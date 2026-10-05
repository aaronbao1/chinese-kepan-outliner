"""Filters: is an announcement a division of the text, or a list of kinds / senses of a term? And does the
work belong to a genre that states no divisions at all?

Input : a scanner.Statement of kind announce / gate / uddana, the text, the mode, and what the parser
        knows (whether the subject names a node already announced).
Output: judge() -> (accepted, reasons); genre_gate() -> {"decision", "evidence"}.

Doctrinal-list filter (design §5.2 "Filters"; README negatives; R07 F2 列數者 is a list): an announcement
lists kinds or senses of a term when its classifier names kinds (種 / 義 / 相 / 事 …), when 謂 / 所謂 / 為
introduces the items, when it sits in a question or a citation, when its subject is a doctrinal term,
and when the items are bare terms. It divides the text when the classifier names text parts (分 / 段 /
科 / 門分別), when the subject is a text part (文 / 品 / 經 / X中 / 初中 / 答中 / 就X), when it follows a
lemma or an entry marker, when the items are ordered 初…次…後, carry lemma or span locators or say what
a stretch of text does (明 / 說 / 標 / 釋 / 結 / 歎 …), when an anaphor (今初 / 此初) follows, and when
the items reappear with root-text spans (T1721 大明一乘凡有二種, README fan-you-n-duan-04). In self-outlining
mode a listing whose items the treatise then takes up in order (所言X者 / X者 / 云何修行X門？, T1666) loses the
kinds / term / definition penalties (taken_up), and a listing found by the deferred count question (X有N種，
clause。云何為N？) earns the +2 云何為N？ bonus only when it is so taken up. The weights are a HYPOTHESIS tuned on
dev material; the case pass rates are in tests/unit/test_tier2_cases.py.
A division whose subject is the commentator's procedure (帖文, METHOD_TAILS) and whose items name no text
part and carry no lemma or locator is commentary-internal (is_method_list).

Genre gate (R07 F2): a 註 work (T1775 注維摩詰經) interleaves glosses by several named glossators and
states no division of its own; a title marking 註/注 without 疏 / 記 / 鈔 / 贊 / 義 / 述 / 論 / 文句 … and a low
density of accepted announcements yields no structure. The evidence also counts sentence-initial X曰： / X云：
attributions (attributions(); 'collected glosses' when several names recur — X0268 孤山云 / 苕溪云 / 長水云),
which does not enter the decision. The decision and its evidence are recorded.
"""

from __future__ import annotations

import re

from . import formulae as F

ACCEPT_MARGIN = 1  # accepted when pos - neg >= this
# self-outlining take-up override (E06 B7): a rejected listing whose items the treatise then treats in order
# loses its list-shape penalties. Window: the longest stretch in T1666 is 1,213 characters (略說發心有三種
# p0580b16 -> 證發心者 p0581a26); 2,000 keeps a margin under 1.5 Taishō pages and does not reach across a
# whole 分 (6,000 would let the YBh's glossary pairs 地有二種 / 水亦二種 match unrelated lists).
TAKE_UP_WINDOW = 2000
TAKE_UP_DROPS = ("-1 classifier", "-2 classifier", "-1 subject is a term", "-2 items are defined")
COLLECTED_MIN_NAMES = 3  # distinct glossators ...
COLLECTED_MIN_EACH = 3  # ... each attributed this often -> 'collected glosses' (evidence only)
# a division reported from another master (T1718 有師作四段, 光宅…, 舊云; R01 F21-F23 survey passages)
REPORTED_RE = re.compile(r"有師|諸師|古師|舊師|昔師|[^\s]師云|舊云|古云|或云|有人|有解|光宅|龍師|基師")
ANCHOR_SUBJECTS = ("品文", "此品", "本品", "品", "此經", "今此經", "經", "經文", "此經始終", "一經",
                   "一部", "此一部", "大文", "今經", "此論", "論文", "此疏")
STRUCT_TAILS = ("中", "之中", "文", "段", "品", "分", "科", "章", "頌", "偈", "長行", "門", "序")
PRONOUN_SUBJECTS = ("", "此", "其", "今", "然", "又", "且", "若", "如", "是", "故", "則", "即", "亦",
                    "復", "皆", "各", "於此", "此之", "今此")
PASSAGE_SUBJECTS = ("此中", "於中", "就中", "中", "其中", "此文", "今文", "於此中", "中文", "此段")
# the commentator's own procedure, not a stretch of text: 今帖文為四：一、列數；二、所以；三、引證；四、示相
# (T1718 dev T34n1718_p0002a20-a21; the four are how the 文句 glosses, not passages). One attested tail; grown
# only on attestation, like the formula inventory (tests/fixtures/kepan-formulae/README.md).
METHOD_TAILS = ("帖文",)


def text_vocab(label: str) -> bool:
    """Does a label say what a stretch of text does (明 / 說 / 標 / 釋 …) or name a text part?"""
    return any(c in F.TEXT_VERBS for c in label) or any(w in label for w in F.TEXT_WORDS)


def subject_kind(subject: str, topic: str = "") -> str:
    """'anchor' | 'struct' | 'pronoun' | 'term'."""
    s = subject
    for op in F.OPENERS:
        s = s.replace(op, "")
    s = s.strip("：:，, ")
    if s.startswith(("今初", "此初")):
        s = s[2:]
    bare = re.sub(r"(?:之中|中)$", "", re.sub(r"^(?:於|就)", "", s))
    if s in ANCHOR_SUBJECTS or bare in ANCHOR_SUBJECTS or \
            s.endswith(("分文", "帖文", "判文", "科文", "此經始終")):
        return "anchor"  # 品文 / 此經 / 今此經中 / 於此經中: the whole chapter or text
    if s in PASSAGE_SUBJECTS:
        return "struct"
    if s in PRONOUN_SUBJECTS:
        if topic and topic.endswith(STRUCT_TAILS):
            return "struct"
        return "pronoun"
    if re.fullmatch(r"(?:又|復|亦|或)?(?:一時|復次|又|或|今|次)", s):
        return "pronoun"  # 又一時分為二: an adverbial phrase, not a named part
    if s.startswith(("就", "於", "釋", "列", "明", "辨", "解", "判")) or s.endswith(STRUCT_TAILS) \
            or s in F.STRUCT_SUBJECTS:
        return "struct"
    if re.fullmatch(r"[初後次中]|[初後][文段分]|第?[一二三四五六七八九十]+[文段分中]?", s):
        return "struct"
    return "term"


def is_method_subject(subject: str) -> bool:
    """Does the subject name the commentator's procedure (METHOD_TAILS) rather than text? 分文 / 判文 / 科文
    divide the text and stay anchors."""
    return subject.strip("：:，, ").endswith(METHOD_TAILS)


def names_text_part(label: str) -> bool:
    """Does an item label name a part of a text (序, 正, 流通, 正宗, 長行 …)? Narrower than text_vocab: that
    also takes the verbs of what a stretch of text does (列 / 示 / 引 / 證), which a method list's items
    (列數 / 引證 / 示相) carry."""
    return label in ("序", "正") or any(w in label for w in F.TEXT_WORDS)


def is_method_list(subject: str, labels) -> bool:
    """A division of the commentator's procedure (is_method_subject) whose items name no text part: its
    items are exegetical methods, so tier 2 makes the wrapper and the items commentary-internal unless an item
    carries a lemma or a span locator (parser._wrapper). A 帖文 list of 序 / 正 / 流通 divides the text."""
    return is_method_subject(subject) and not any(names_text_part(lab) for lab in labels)


def span_mapped(text: str, st, window: int = 320) -> bool:
    """Do most of the items reappear right after root-text spans (從…至… / 自從…竟…) in the text that
    follows the listing? (T1721 大明一乘凡有二種：… 自從經初至〈神力品〉，明諸佛所乘之法 …)."""
    labels = [lab for lab in st.labels if len(lab) >= 2]
    if len(labels) < 2:
        return False
    tail = text[st.end:st.end + window]
    spans = [m.end() for m in re.finditer(r"(?:自從|從)[^。；]{1,30}?(?:至|竟|訖|盡)[^，,。；]{1,20}?[，,]?", tail)]
    hits = 0
    for lab in labels:
        need = set(lab)
        for e in spans:
            near = tail[e:e + max(12, len(lab) + 6)]
            if len(need & set(near)) >= 0.75 * len(need):
                hits += 1
                break
    return hits * 2 >= len(labels) and hits >= 2


def taken_up(text: str, st, bound: int) -> tuple:
    """(k, n): how many of the n listed items reappear, in order, as sentence-initial 所言X者 / X者 /
    云何修行X門？ between the listing and bound (T1666 p0577a22 覺與不覺有二種相 … 同相者 … 異相者). An item's
    name is its label up to the first comma (the label rule keeps a definition clause: 體大，謂…)."""
    names = [re.split(r"[，,]", lab)[0] for lab in st.labels]
    k, pos = 0, st.end
    for name in names:
        if not 1 <= len(name) <= 8:
            continue
        rx = re.compile(r"[。？！；」](?:復次[，,]?)?(?:所言|言|云何修行)?%s(?:者|[？?])" % re.escape(name))
        m = rx.search(text, max(pos - 1, 0), bound)
        if m:
            k += 1
            pos = m.end()
    return k, len(names)


def judge(st, text: str, *, mode: str = "sutra", label_match: bool = False,
          followed_by_anaphor: bool = False, take_up_bound: int | None = None) -> tuple:
    """(accepted, reasons, score) for one announcement / gate / uddāna statement. take_up_bound: end of the
    stretch in which a self-outlining text may take the listed items up (parser.run; None in sūtra mode and under
    the genre gate, where a deferred listing therefore gets no +2)."""
    reasons: list = []
    if st.kind == "uddana":
        return True, ["uddāna (R01 uddana)"], 3
    if st.in_quote == "citation":
        return False, ["inside a quotation"], -9
    pos = neg = 0
    items = st.items
    labels = st.labels
    cls = st.cls or ""
    subj = subject_kind(st.subject, st.topic)
    if st.kind == "gate":
        if st.in_question:
            return False, ["gate phrase in a question"], -1
        return True, ["gate N門%s (R03 F25)" % st.verb], 3
    if st.in_question:
        neg += 2
        reasons.append("-2 in a question")
    merged_class = st.total is not None and cls in ("類", "段", "分", "科", "別")
    if cls and cls[-1] in F.STRUCT_CLS or merged_class:
        w = 1 if st.verb == "為" else 2  # 論戒、定、慧為三分 vs 分為三 / 有三分
        pos += w
        reasons.append("+%d classifier %s names text parts" % (w, cls or "類"))
    elif cls and cls[-1] in F.EXTENT_CLS and items:
        pos += 1
        reasons.append("+1 lines/verses divided (%s)" % cls)
    elif cls and cls[-1] in F.DOCTRINAL_CLS:
        w = 1 if mode == "self-outlining" else 2
        neg += w
        reasons.append("-%d classifier %s names kinds" % (w, cls))
    if st.verb in ("分", "分為", "大分為", "細分為", "開為", "開", "判", "判為", "科", "科為", "分成", "開成"):
        pos += 1
        reasons.append("+1 division verb %s" % st.verb)
    if REPORTED_RE.search(st.subject) or REPORTED_RE.search(st.topic):
        return False, ["reports another master's division (not this commentator's scheme)"], -3
    if st.subject_start > 0 and text[st.subject_start - 1] == "、" and st.subject:
        neg += 2
        reasons.append("-2 subject closes a list of terms")
    if re.search(r"各各|各[有作為分]|皆[有作為]", text[max(0, st.subject_start - 2):st.head_end]):
        neg += 2
        reasons.append("-2 distributive (each has N)")
    if subj == "anchor":
        pos += 2
        reasons.append("+2 subject is the text / chapter")
    elif subj == "struct":
        pos += 1
        reasons.append("+1 subject is a text part")
    elif subj == "term" and not label_match:
        neg += 1
        reasons.append("-1 subject is a term")
    if label_match:
        pos += 2
        reasons.append("+2 subject names an announced node")
    if st.after in ("lemma", "opener", "enter") or st.unit_start:
        pos += 1
        reasons.append("+1 follows a lemma / entry marker")
    listing = st.listing
    if listing is not None and listing.intro:
        neg += 2
        reasons.append("-2 items introduced by %s" % listing.intro)
    elif listing is not None and listing.kind == "unnumbered" and text[st.head_end:st.head_end + 2].lstrip(
            "：:，,").startswith("為"):
        neg += 2
        reasons.append("-2 items introduced by 為")
    if listing is not None and listing.family in ("chu", "xian", "qian"):
        pos += 1
        reasons.append("+1 items ordered 初/先…後")
    if any(it.lemma or it.locator or it.extent for it in items):
        pos += 2
        reasons.append("+2 items carry lemma / span / extent locators")
    if followed_by_anaphor:
        pos += 2
        reasons.append("+2 an anaphor (今初 / 此初) follows")
    if labels and sum(1 for lab in labels if re.search(r"[，,]謂|^謂", lab)) * 2 >= len(labels):
        neg += 2
        reasons.append("-2 items are defined (X，謂Y)")
    if labels:
        voc = sum(1 for lab in labels if text_vocab(lab))
        if voc * 2 >= len(labels):
            pos += 1
            reasons.append("+1 items say what the text does")
        elif subj not in ("anchor", "struct") and all(len(lab) <= 4 for lab in labels):
            neg += 1
            reasons.append("-1 items are terms")
    deferred = listing is not None and listing.deferred
    took_up = False  # self-outlining: at least half of the items are taken up in order within the bound
    k = n = 0
    if mode == "self-outlining" and take_up_bound is not None and labels and (neg > 0 or deferred):
        k, n = taken_up(text, st, take_up_bound)
        took_up = n >= 2 and 2 * k >= n
    if mode == "self-outlining" and listing is not None and listing.rhetorical:
        if not deferred:
            pos += 2
            reasons.append("+2 云何為N？ enumeration (self-outlining)")
        elif took_up:
            # 此識有二種義，clause。云何為二？ defers the items; only taking them up shows they divide the text
            pos += 2
            reasons.append("+2 云何為N？ enumeration, deferred (self-outlining; %d/%d items taken up)" % (k, n))
    if took_up and neg > 0:
        for r in list(reasons):
            if r.startswith(TAKE_UP_DROPS):
                neg -= abs(int(r.split()[0]))
                reasons.remove(r)
        reasons.append("take-up override: %d/%d items taken up in order (self-outlining)" % (k, n))
    if labels and neg > 0 and not st.in_question and span_mapped(text, st):
        return True, reasons + ["items reappear with root-text spans (overrides the list signals)"], 9
    if not items:
        # a count without a listing divides only when it plainly names text parts
        if not (cls and cls[-1] in F.STRUCT_CLS or subj == "anchor" or label_match):
            return False, reasons + ["no listing"], pos - neg
    score = pos - neg
    return score >= ACCEPT_MARGIN and pos > 0, reasons, score


def is_listing_candidate(st) -> bool:
    """Worth a line in `rejected` (it looks like an announcement: it has a listing or a text-part
    classifier)."""
    if st.items and len(st.items) >= 2:
        return True
    return bool(st.cls) and st.cls[-1] in F.STRUCT_CLS


def attributions(text: str) -> dict:
    """{name: count} of sentence-initial X曰： / X云： attributions (T1775 什曰 / 肇曰 / 生曰; X0268 孤山云 /
    苕溪云 / 長水云), formulae.ATTRIBUTION_RE."""
    out: dict = {}
    for m in F.ATTRIBUTION_RE.finditer(text):
        out[m.group("who")] = out.get(m.group("who"), 0) + 1
    return out


def genre_gate(title: str, *, n_accepted: int, n_chars: int, attributions: dict | None = None,
               threshold: float = 0.4) -> dict:
    """{"decision": "outline" | "no-structure", "evidence": str}. threshold = accepted announcements per
    1,000 characters below which a 註-titled work is taken to state no divisions. attributions (from
    attributions()) is evidence only: 'collected glosses' when >= COLLECTED_MIN_NAMES names each occur >=
    COLLECTED_MIN_EACH times; it never changes the decision."""
    title = title or ""
    density = 1000.0 * n_accepted / n_chars if n_chars else 0.0
    zhu = bool(F.ZHU_TITLE_RE.search(title)) and not F.PASS_TITLE_RE.search(title)
    att = attributions or {}
    names = sorted((k for k, v in att.items() if v >= COLLECTED_MIN_EACH), key=lambda k: (-att[k], k))
    ev = "title %r; %d accepted announcements in %d characters (%.2f per 1,000); %d attributions " \
         "(X曰：/ X云：) by %d names, %d of them >= %d times" % (
             title, n_accepted, n_chars, density, sum(att.values()), len(att), len(names), COLLECTED_MIN_EACH)
    if names:
        ev += " (%s)" % "、".join(names[:5])
    if len(names) >= COLLECTED_MIN_NAMES:
        ev += "; collected glosses"
    if zhu and density < threshold:
        return {"decision": "no-structure",
                "evidence": ev + "; 註 genre (R07 F2): the title marks a 註 and announcements are sparse"}
    if zhu:
        return {"decision": "outline", "evidence": ev + "; 註 title, but announcements are dense"}
    return {"decision": "outline", "evidence": ev}
