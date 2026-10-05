"""Tier 2: a division whose subject names the commentator's procedure (帖文, R01 anchor subject) and whose
items carry no lemma or span locator divides the commentary's own discourse, not the sūtra: the wrapper
and its items are commentary-internal (E06 review §1 item 6, B2: the four items 列數/所以/引證/示相 were
asked for root spans no span inside 序品 can hold). Text: the T1718 dev lines T34n1718_p0002a20–a24 on a
synthetic T99n9998 line grid, then two synthetic filler lines that take up the last two items.
"""

from __future__ import annotations

from chinese_workflow.ingest.lines import build_index
from chinese_workflow.ingest.text import InputText
from chinese_workflow.outline.tier2 import detect, parse
from chinese_workflow.outline.tier2.filters import (
    is_method_list,
    is_method_subject,
    names_text_part,
    subject_kind,
)

LINES = [
    ("T99n9998_p0001a01", "但單流通者，說法未竟也，有無之意云爾。今"),
    ("T99n9998_p0001a02", "帖文為四：一、列數；二、所以；三、引證；四、示相。列"),
    ("T99n9998_p0001a03", "數者：一因緣、二約教、三本迹、四觀心。始從「如"),
    ("T99n9998_p0001a04", "是」終于「而退」，皆以四意消文，而今略書，"),
    ("T99n9998_p0001a05", "或三、二、一，貴在得意不煩筆墨。二、所以者，"),
    ("T99n9998_p0001a06", "合成疏文釋義。三、引證。合成疏文釋義。四、示相者，合成疏文。"),
]
# the same opening over three text parts: a division of the text, not of the commentator's procedure
PARTS = [
    ("T99n9998_p0001a01", "但單流通者，說法未竟也，有無之意云爾。今"),
    ("T99n9998_p0001a02", "帖文為三：一、序；二、正；三、流通。序"),
    ("T99n9998_p0001a03", "者：合成疏文釋義。二、正者，合成疏文。三、"),
    ("T99n9998_p0001a04", "流通者，合成疏文釋義。"),
]
ANCHOR = {"anchor": "T99n9998_p0001a01", "heading_src": "合成品", "part_type": "品"}


def _text(lines=LINES) -> InputText:
    recs = [{"linehead": lh, "text": t} for lh, t in lines]
    return InputText(text_id="T99n9998", role="commentary", info={}, lines=recs,
                     all_lineheads=[lh for lh, _ in lines], index=build_index(recs))


def test_method_subject():
    assert is_method_subject("今帖文") and is_method_subject("帖文") and is_method_subject("贊曰：今帖文")
    for s in ("天台智者分文", "品文", "此經", "今此經中", "科文", "判文", "文"):
        assert not is_method_subject(s), s
    assert is_method_subject("今帖文：") and not is_method_subject("帖文為四")  # the subject, not the head
    assert subject_kind("今帖文") == "anchor"  # still a whole-text target: a wrapper under the 品


def test_method_list_needs_items_that_name_no_text_part():
    assert names_text_part("序") and names_text_part("正") and names_text_part("流通")
    assert names_text_part("正宗") and names_text_part("序分")
    # the method items carry text verbs (列 / 示 / 引 / 證), which is why text_vocab is not the test
    for lab in ("列數", "所以", "引證", "示相"):
        assert not names_text_part(lab), lab
    assert is_method_list("今帖文", ["列數", "所以", "引證", "示相"])
    assert not is_method_list("今帖文", ["序", "正", "流通"])
    assert not is_method_list("今帖文", ["列數", "正宗"])  # one text part makes it a division of the text
    assert not is_method_list("天台智者分文", ["列數", "所以"])  # not a procedure subject


def test_tiewen_division_and_its_items_are_commentary_internal():
    res = parse(_text(), anchors=[ANCHOR], config={"heading_style": "source"})
    [wrapper] = res.by_anchor["T99n9998_p0001a01"]
    assert wrapper["heading_src"] == "今帖文為四" and wrapper["child_count_announced"] == 4
    assert wrapper["node_class"] == "commentary-internal" and wrapper["locations"]["root_text"] is None
    assert [c["heading_src"] for c in wrapper["children"]] == ["一列數", "二所以", "三引證", "四示相"]
    assert all(c["node_class"] == "commentary-internal" and c["locations"]["root_text"] is None
               for c in wrapper["children"])
    assert "unmapped" not in wrapper["flags"] and res.report == []
    [st] = [s for s in detect("".join(t for _, t in LINES)) if s["kind"] == "announce"]
    assert st["subject"] == "今帖文" and st["accepted"] and all(i["lemma"] is None for i in st["items"])


def test_tiewen_division_of_text_parts_stays_a_sutra_span():
    res = parse(_text(PARTS), anchors=[ANCHOR], config={"heading_style": "source"})
    [wrapper] = res.by_anchor["T99n9998_p0001a01"]
    assert wrapper["heading_src"] == "今帖文為三"
    assert [c["heading_src"] for c in wrapper["children"]] == ["一序", "二正", "三流通"]
    assert wrapper["node_class"] == "sutra-span"
    assert all(c["node_class"] == "sutra-span" for c in wrapper["children"])
