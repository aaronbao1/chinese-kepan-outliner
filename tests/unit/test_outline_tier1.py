"""Tests for chinese_workflow.outline.tier1 (tier 1: the chapter TOC from cb:mulu; design §5.1).

Always run (committed fixtures): the T34n1723 陀羅尼品 excerpt (the T1723 dev span) and the
T09n0262 陀羅尼品 excerpt (tests/fixtures/cbeta-xml-p5/); G069n1977.xml (科判 path, not a gold).
Run when present (data/raw/cbeta/, gitignored): whole T09n0262 and T34n1723, checked against
CBETA's own works/toc (tests/fixtures/cbeta-api/works-toc-*.json). Only structure and lineheads of
T34n1723 outside the dev span are compared, never its prose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chinese_workflow.common import outline_doc
from chinese_workflow.common.paths import cbeta_xml_path
from chinese_workflow.ingest.lines import build_index
from chinese_workflow.ingest.text import InputText, load_input_text
from chinese_workflow.outline import tier1

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures"
T1723_DEV = FIX / "cbeta-xml-p5" / "T34n1723-excerpt-p0850a19-p0850b19.xml"
T0262_DEV = FIX / "cbeta-xml-p5" / "T09n0262-excerpt-p0058b08-p0059b27.xml"
G1977 = FIX / "cbeta-xml-p5" / "G069n1977.xml"
DEV = ("T34n1723_p0850a19", "T34n1723_p0850b19")


def sutra_doc(roots):
    doc, _ = outline_doc.build_prediction(
        roots, text_id="T0262", text_title_src="妙法蓮華經", outline_mode="sutra",
        root_text_id="T09n0262", commentary_id="T34n1723", scheme_id="kuiji-xuanzan",
        source_file="tests/fixtures/cbeta-xml-p5", generated_by="tests/unit/test_outline_tier1.py",
        source_document={"kind": "commentary", "text_id": "T34n1723", "title": "妙法蓮華經玄贊"},
        format_note="tier 1 test document")
    return doc


def assert_valid(doc):
    rep = outline_doc.validate(doc)
    assert rep.passed(), [f.render() for f in rep.errors]
    return rep


def raw_text(file_id, **kw):
    if cbeta_xml_path(file_id) is None:
        pytest.skip("data/raw/cbeta/%s.xml not fetched (scripts/fetch_cbeta.sh)" % file_id)
    return load_input_text(file_id, **kw)


def toc(work):
    """works/toc fixture flattened: [(title, lb, depth, type)], [lb of each juan entry]."""
    res = json.loads((FIX / "cbeta-api" / ("works-toc-%s.json" % work)).read_text("utf-8"))
    res = res["results"][0]
    out = []

    def walk(nodes, depth):
        for n in nodes:
            out.append((n["title"], n["lb"], depth, n.get("type")))
            walk(n.get("children") or [], depth + 1)

    walk(res["mulu"], 1)
    return out, [j["lb"] for j in res["juan"]]


def lb(linehead):
    return linehead.split("_p", 1)[1]


# --------------------------------------------------------------------------------- names, matching


@pytest.mark.parametrize("heading,name", [
    ("26 陀羅尼品", "陀羅尼"),
    ("妙法蓮華經陀羅尼品第二十六", "陀羅尼"),
    ("陀羅尼品", "陀羅尼"),
    ("〈陀羅尼品〉", "陀羅尼"),
    ("釋陀羅尼品", "陀羅尼"),
    ("1 序品", "序"),
    ("序品第一", "序"),
    ("持品", "持"),
    ("弘傳序", "弘傳序"),
    ("附文", "附文"),
])
def test_pin_name(heading, name):
    assert tier1.pin_name(heading) == name


def _pin(name, k):
    lh = "T99n9999_p0001a%02d" % k
    return tier1.Pin(name=name, heading=name + "品", start=lh, end=lh, part_type="品", level=1)


def test_find_pin_exact_overlap_contained():
    names = ["勸持", "從地踊出", "如來壽量", "法師", "法師功德"]
    pins = [_pin(n, k) for k, n in enumerate(names, 1)]
    assert tier1.find_pin("法師", pins) == (3, "exact")
    assert tier1.find_pin("從地涌出", pins) == (1, "overlap 2")
    assert tier1.find_pin("壽量", pins) == (2, "overlap 2")
    assert tier1.find_pin("持", pins) == (0, "contained")
    assert tier1.find_pin("譬喻", pins) == (None, None)
    # an unused pin is preferred
    assert tier1.find_pin("法師", pins, used={3}) == (3, "exact")  # the only exact one
    assert tier1.find_pin("師功", pins, used={4}) == (4, "overlap 2")  # no unused pin reaches 2


# ------------------------------------------------------------------------ sūtra mode, dev fixture


def test_dev_excerpt_gives_one_pin_draft():
    text = load_input_text(T1723_DEV, role="commentary")
    res = tier1.build(text, mode="sutra", role="commentary")
    assert len(res.drafts) == 1
    d = res.drafts[0]
    assert d["heading_src"] == "陀羅尼品"
    assert d["part_type"] == "品"
    assert d["origin"] == "explicit" and d["confidence"] == 1.0
    assert d["node_class"] == "sutra-span"
    assert d["evidence"] == "T34n1723_p0850a19: 陀羅尼品"  # the Kuiji gold's evidence for this node
    assert d["locations"] == {"scheme": "cbeta-kepan",
                              "commentary": {"announced": None, "explained": "T34n1723_p0850a19"},
                              "root_text": None}
    assert d["flags"] == ["unmapped"]  # until align_pins
    assert d["_anchor"] == "T34n1723_p0850a19" and d["children"] == []
    assert res.anchors == [{"anchor": "T34n1723_p0850a19", "heading_src": "陀羅尼品",
                            "part_type": "品"}]
    assert [(p.name, p.start, p.end, p.part_type, p.level) for p in res.pins] == [
        ("陀羅尼", "T34n1723_p0850a19", "T34n1723_p0850b19", "品", 1)]
    assert res.juan == [] and res.anomalies == []
    assert_valid(sutra_doc(res.drafts))  # unmapped flag keeps the unaligned draft valid


def test_dev_excerpt_aligns_to_root_chapter():
    root = tier1.build(load_input_text(T0262_DEV, role="root"), mode="sutra", role="root")
    assert root.drafts == [] and root.anchors == []
    assert [(p.name, p.heading, p.start, p.end) for p in root.pins] == [
        ("陀羅尼", "26 陀羅尼品", "T09n0262_p0058b08", "T09n0262_p0059b27")]
    comm = tier1.build(load_input_text(T1723_DEV, role="commentary"), mode="sutra",
                       role="commentary")
    aligned = tier1.align_pins(comm.drafts, root.pins)
    assert comm.drafts[0]["locations"]["root_text"] is None  # input untouched
    d = aligned[0]
    # the Kuiji gold's 陀羅尼品 node: root span p0058b08-p0059b27, basis chapter
    assert d["locations"]["root_text"] == {"start": "T09n0262_p0058b08", "end": "T09n0262_p0059b27",
                                           "basis": "chapter", "end_basis": None}
    assert d["flags"] == [] and d["notes"] == []
    doc = sutra_doc(aligned)
    assert_valid(doc)
    assert doc["nodes"][0]["display_label"] == "甲一"


def test_unmatched_pin_stays_unmapped():
    comm = tier1.build(load_input_text(T1723_DEV, role="commentary"), mode="sutra",
                       role="commentary")
    other = [tier1.Pin("譬喻", "3 譬喻品", "T09n0262_p0010b28", "T09n0262_p0016b06", "品", 1)]
    d = tier1.align_pins(comm.drafts, other)[0]
    assert d["locations"]["root_text"] is None and d["flags"] == ["unmapped"]
    assert d["notes"] and "no root-text 品" in d["notes"][0]
    assert_valid(sutra_doc([d]))


def test_span_restricts_drafts_not_pins():
    text = load_input_text(T1723_DEV, role="commentary")
    res = tier1.build(text, mode="sutra", role="commentary",
                      span=("T34n1723_p0850a20", "T34n1723_p0850b19"))
    # the mulu line is outside the span: no explicit draft, but the pin is carried (next test)
    assert [d["origin"] for d in res.drafts] == ["editorial"]
    assert len(res.pins) == 1
    res = tier1.build(text, mode="sutra", role="commentary",
                      span=("T34n1723_p0850a19", "T34n1723_p0850a19"))
    assert [d["heading_src"] for d in res.drafts] == ["陀羅尼品"]
    assert res.carried == []
    with pytest.raises(KeyError):
        tier1.build(text, mode="sutra", role="commentary",
                    span=("T34n1723_p0850a19", "T34n1723_p0850c01"))


def test_span_inside_a_unit_carries_the_pin():
    """E06 review §1 item 6 / §2 B2: a span whose first line lies inside a 品 whose heading line is
    before the span gets that 品 as an editorial ancestor, anchored on the span's first line, so tier-2
    drafts attach under it and align_pins gives it the root chapter."""
    text = load_input_text(T1723_DEV, role="commentary")
    res = tier1.build(text, mode="sutra", role="commentary",
                      span=("T34n1723_p0850a20", "T34n1723_p0850b19"))
    assert len(res.drafts) == 1
    d = res.drafts[0]
    assert d["heading_src"] == "陀羅尼品" and d["part_type"] == "品"
    assert d["origin"] == "editorial" and "confidence" not in d
    assert d["evidence"] == "cb:mulu type=品 level=1 on T34n1723_p0850a19: 陀羅尼品"
    assert d["flags"] == ["unmapped"] and d["node_class"] == "sutra-span"
    assert d["notes"] == [tier1.CARRIED_NOTE % (
        "T34n1723_p0850a19", "品", 1, "T34n1723_p0850a20", "T34n1723_p0850b19",
        "T34n1723_p0850a20", "T34n1723_p0850b19")]
    assert d["notes"][0].startswith("pin carried from T34n1723_p0850a19")
    assert d["locations"] == {"scheme": "cbeta-kepan",
                              "commentary": {"announced": None, "explained": "T34n1723_p0850a19"},
                              "root_text": None}
    assert d["_anchor"] == "T34n1723_p0850a20" and d["_carried_from"] == "T34n1723_p0850a19"
    assert d["children"] == []
    assert res.anchors == [{"anchor": "T34n1723_p0850a20", "heading_src": "陀羅尼品",
                            "part_type": "品"}]
    assert res.carried == [{"anchor": "T34n1723_p0850a20", "pin_start": "T34n1723_p0850a19",
                            "end": "T34n1723_p0850b19", "heading_src": "陀羅尼品",
                            "part_type": "品", "level": 1}]
    assert len(res.pins) == 1 and res.anomalies == []
    assert_valid(sutra_doc(res.drafts))
    root = tier1.build(load_input_text(T0262_DEV, role="root"), mode="sutra", role="root")
    aligned = tier1.align_pins(res.drafts, root.pins)[0]
    assert aligned["locations"]["root_text"] == {"start": "T09n0262_p0058b08",
                                                 "end": "T09n0262_p0059b27",
                                                 "basis": "chapter", "end_basis": None}
    assert aligned["flags"] == [] and aligned["origin"] == "editorial"
    assert_valid(sutra_doc([aligned]))


def test_span_straddling_two_units_carries_only_the_first():
    """T09n0262 read for its structure as if it were a commentary (its 品 are typed level-1 mulu; root
    text, outside every split): a span from inside 序品 (mulu p0001c18) into 方便品 (mulu p0005b24)
    gets 序品 carried, ending where the next-node rule ends it (p0005b23), and 方便品 as an ordinary
    explicit draft. A span starting between units (the 卷 line p0001c14, after 弘傳序 ends p0001c11
    and before 序品) carries nothing and says so."""
    text = raw_text("T09n0262", role="root")
    res = tier1.build(text, mode="sutra", role="commentary",
                      span=("T09n0262_p0005b20", "T09n0262_p0005b27"))
    assert [(d["heading_src"], d["origin"], d["_anchor"]) for d in res.drafts] == [
        ("1 序品", "editorial", "T09n0262_p0005b20"), ("2 方便品", "explicit", "T09n0262_p0005b24")]
    assert res.carried == [{"anchor": "T09n0262_p0005b20", "pin_start": "T09n0262_p0001c18",
                            "end": "T09n0262_p0005b23", "heading_src": "1 序品", "part_type": "品",
                            "level": 1}]
    assert res.drafts[0]["notes"][0].endswith("(T09n0262_p0005b20..T09n0262_p0005b23)")
    assert [a["anchor"] for a in res.anchors] == ["T09n0262_p0005b20", "T09n0262_p0005b24"]
    assert res.anomalies == []
    between = tier1.build(text, mode="sutra", role="commentary",
                          span=("T09n0262_p0001c14", "T09n0262_p0001c20"))
    assert [(d["heading_src"], d["origin"]) for d in between.drafts] == [("1 序品", "explicit")]
    assert between.carried == []
    assert between.anomalies == ["no typed cb:mulu unit holds the span's first line T09n0262_p0001c14 "
                                 "(it lies between units or after the last); no pin carried"]


def test_nested_units_are_carried_as_a_chain():
    """T09n0262's 附文 (level 1, mulu p0198a10) holds a level-2 序 (mulu p0198a12): a span inside the 序
    carries both, nested by @level, both anchored on the span's first line; a span that starts on the
    序's own mulu line carries the 附文 only and reads the 序 as an explicit draft."""
    text = raw_text("T09n0262", role="root")
    res = tier1.build(text, mode="sutra", role="commentary",
                      span=("T09n0262_p0198a13", "T09n0262_p0198a14"))
    [outer] = res.drafts
    [inner] = outer["children"]
    assert (outer["heading_src"], outer["part_type"], inner["part_type"]) == ("附文", "附文", "序")
    assert outer["origin"] == inner["origin"] == "editorial"
    assert outer["_anchor"] == inner["_anchor"] == "T09n0262_p0198a13"
    assert [(c["pin_start"], c["level"]) for c in res.carried] == [("T09n0262_p0198a10", 1),
                                                                  ("T09n0262_p0198a12", 2)]
    assert [a["anchor"] for a in res.anchors] == ["T09n0262_p0198a13"] * 2
    on_mulu = tier1.build(text, mode="sutra", role="commentary",
                          span=("T09n0262_p0198a12", "T09n0262_p0198a14"))
    [outer] = on_mulu.drafts
    assert outer["origin"] == "editorial" and [c["origin"] for c in outer["children"]] == ["explicit"]
    assert [c["heading_src"] for c in on_mulu.carried] == ["附文"]


def test_bad_mode_or_role():
    text = load_input_text(T1723_DEV, role="commentary")
    with pytest.raises(ValueError):
        tier1.build(text, mode="commentary-driven", role="commentary")
    with pytest.raises(ValueError):
        tier1.build(text, mode="sutra", role="translation")


# ----------------------------------------------------------------------- self-outlining, 科判 path

# (heading, depth, root_text.start, root_text.end, end_basis, child_count_announced) in pre-order,
# read off G069n1977.xml by hand (lines 79-93 of the file; 15 科判 mulu, levels 1-5)
G1977_TREE = [
    ("心要分二", 1, "0717a01", "0718a06", None, 2),
    ("初題目二", 2, "0717a01", "0717a02", "next-node", 2),
    ("初標題目", 3, "0717a01", "0717a01", "next-node", None),
    ("二述人號", 3, "0717a02", "0717a02", "next-node", None),
    ("二正文三", 2, "0717a03", "0718a06", None, 3),
    ("初始性三德體融本具", 3, "0717a03", "0717a04", "next-node", None),
    ("二終修稱性迷悟俱融三", 3, "0717a05", "0718a02", "next-node", 3),
    ("初迷德成惑", 4, "0717a05", "0717a06", "next-node", None),
    ("二悟虛可化四", 4, "0717a07", "0718a01", "next-node", 4),
    ("初三惑是虛妄", 5, "0717a07", "0717a07", "next-node", None),
    ("二佛悟知生迷", 5, "0717a08", "0717a09", "next-node", None),
    ("三立觀令破顯", 5, "0717a10", "0717a10", "next-node", None),
    ("四用觀破顯相", 5, "0717a11", "0718a01", "next-node", None),
    ("三迷悟俱融", 4, "0718a02", "0718a02", "next-node", None),
    ("三始終體一修證圓頓", 3, "0718a03", "0718a06", None, None),
]


def self_doc(roots):
    doc, private = outline_doc.build_prediction(
        roots, text_id="G1977", text_title_src="科始終心要", outline_mode="self-outlining",
        root_text_id="G069n1977", commentary_id=None, scheme_id="cbeta-mulu-kepan",
        source_file="tests/fixtures/cbeta-xml-p5/G069n1977.xml",
        generated_by="tests/unit/test_outline_tier1.py",
        source_document={"kind": "root-text", "text_id": "G069n1977", "title": "科始終心要"},
        format_note="tier 1 test document")
    return doc, private


def test_g1977_kepan_path_is_a_full_outline():
    res = tier1.build(load_input_text(G1977, role="root"), mode="self-outlining", role="root")
    got = []

    def walk(drafts, depth):
        for d in drafts:
            rt = d["locations"]["root_text"]
            got.append((d["heading_src"], depth, lb(rt["start"]), lb(rt["end"]), rt["end_basis"],
                        d.get("child_count_announced")))
            assert rt["basis"] == "cbeta-mulu"
            assert d["locations"]["commentary"] == {"announced": None, "explained": rt["start"]}
            assert d["part_type"] == "科判" and d["origin"] == "explicit"
            prefix = "cb:mulu type=科判 level=%d on %s: " % (depth, rt["start"])
            assert d["evidence"].startswith(prefix)
            walk(d["children"], depth + 1)

    walk(res.drafts, 1)
    assert got == G1977_TREE
    assert res.pins == []  # 科判 nodes are outline nodes, not chapter units
    assert res.juan == [{"n": "1", "linehead": "G069n1977_p0717a01", "label": ""}]
    assert res.anomalies == []
    assert len(res.anchors) == 15
    doc, private = self_doc(res.drafts)
    rep = assert_valid(doc)
    assert not [f for f in rep.warnings if f.code == "child-count"]
    assert private["1_1"]["_anchor"] == "G069n1977_p0717a01"


def test_g1977_span_keeps_whole_file_ends():
    span = ("G069n1977_p0717a05", "G069n1977_p0717a11")
    text = load_input_text(G1977, span=span, role="root")  # an InputText holding a span only
    res = tier1.build(text, mode="self-outlining", role="root")
    assert [d["heading_src"] for d in res.drafts] == ["二終修稱性迷悟俱融三"]
    top = res.drafts[0]
    # its end is read from the whole file (p0718a02), beyond the span
    assert top["locations"]["root_text"]["end"] == "G069n1977_p0718a02"
    assert "parent mulu lies before the span" in top["notes"][0]
    assert [d["heading_src"] for d in top["children"]] == ["初迷德成惑", "二悟虛可化四"]
    # 三迷悟俱融 (p0718a02) is outside the span: the heading's 三 differs from the children here
    assert top.get("child_count_announced") is None
    assert res.juan == [{"n": "1", "linehead": "G069n1977_p0717a01", "label": ""}]
    doc, _ = self_doc(res.drafts)
    assert_valid(doc)


def _kepan_rec(n, text, div_types, mulu=()):
    """A synthetic line record (ingest.lines shape) carrying 科判 mulu (level, text, div_type)."""
    return {"linehead": "X00n0000_p0001a%02d" % n, "n": "0001a%02d" % n, "ed": "X", "alt": [], "juan": 1,
            "text": text, "inline_notes": [], "excluded_notes": [], "gaiji": [], "unclear": [],
            "caesuras": [], "heads": [], "juan_marks": [], "in_verse": False, "div_types": list(div_types),
            "mulu": [{"level": lv, "type": "科判", "n": None, "text": t, "offset": 0, "div_type": dt}
                     for lv, t, dt in mulu]}


def test_kepan_parent_end_covers_children_in_another_div():
    """A 科判 parent whose mulu sits in another cb:div than a child's (X11n0268 p0190a06: 二歸精舍演法
    in a div type=orig, its child 二現通演呪 in type=other; E06 failed cell tier1-markup-OOD-X0268)
    ends at its last descendant's end, not where its own div's lines stop. Leaves keep the div trim."""
    recs = [
        _kepan_rec(1, "初標。", ["other"], [(1, "初標", "other")]),
        _kepan_rec(2, "經文。", ["other", "orig"], [(1, "二釋(二)", "orig"), (2, "初引經", "orig")]),
        _kepan_rec(3, "疏云。", ["other", "commentary"]),
        _kepan_rec(4, "次經。", ["other"], [(2, "二釋經", "other")]),
        _kepan_rec(5, "經文。", ["other", "orig"]),
        _kepan_rec(6, "疏云。", ["other", "commentary"]),
        _kepan_rec(7, "三結。", ["other"], [(1, "三結", "other")]),
    ]
    lhs = [r["linehead"] for r in recs]
    text = InputText(text_id="X00n0000", role="root", info={}, lines=recs, all_lineheads=lhs,
                     index=build_index(recs))
    res = tier1.build(text, mode="self-outlining", role="root")
    ends = {d["heading_src"]: lb(d["locations"]["root_text"]["end"]) for d in tier1.iter_drafts(res.drafts)}
    assert ends == {"初標": "0001a01", "二釋(二)": "0001a06", "初引經": "0001a02", "二釋經": "0001a06",
                    "三結": "0001a07"}
    parent = res.drafts[1]
    assert any("extended" in n and "X00n0000_p0001a05" in n for n in parent["notes"]), parent["notes"]
    doc, _ = outline_doc.build_prediction(
        res.drafts, text_id="X0000", text_title_src="synthetic", outline_mode="self-outlining",
        root_text_id="X00n0000", commentary_id=None, scheme_id="cbeta-mulu-kepan",
        source_file="synthetic", generated_by="tests/unit/test_outline_tier1.py",
        source_document={"kind": "root-text", "text_id": "X00n0000", "title": "synthetic"},
        format_note="tier 1 test document")
    assert_valid(doc)


# ----------------------------------------------------------------- whole files (data/raw/ present)


def test_t0262_pins_and_juan_match_works_toc():
    res = tier1.build(raw_text("T09n0262", role="root"), mode="sutra", role="root")
    want, want_juan = toc("T0262")
    assert len(want) == 33  # 28 品 + 3 序 + 1 附文 at level 1, 1 序 at level 2 (R02 F20)
    assert [(p.heading, lb(p.start), p.level, p.part_type) for p in res.pins] == want
    assert [lb(j["linehead"]) for j in res.juan] == want_juan
    assert res.drafts == [] and res.anomalies == []
    by_name = {p.name: p for p in res.pins}
    dharani = by_name["陀羅尼"]
    assert (dharani.start, dharani.end) == ("T09n0262_p0058b08", "T09n0262_p0059b27")
    # trailing 卷 close/open and translator lines are not part of the chapter (the Kuiji gold)
    assert by_name["方便"].end == "T09n0262_p0010b20"
    assert by_name["普賢菩薩勸發"].end == "T09n0262_p0062a29"
    # the 附文 runs out of string order (0056c01 -> 0198a10 ... 0198b11 -> 0056c02)
    assert by_name["妙音菩薩"].end == "T09n0262_p0056c01"
    appendix = by_name["附文"]
    assert (appendix.start, appendix.end) == ("T09n0262_p0198a10", "T09n0262_p0198b11")


def test_t1723_pins_markers_and_juan_match_works_toc():
    res = tier1.build(raw_text("T34n1723", role="commentary"), mode="sutra", role="root")
    want, want_juan = toc("T1723")
    typed = [(t, lb_, depth, ty) for t, lb_, depth, ty in want if ty]
    untyped = [lb_ for t, lb_, depth, ty in want if not ty]
    assert len(typed) == 28 and len(untyped) == 10
    assert [(p.heading, lb(p.start), p.level, p.part_type) for p in res.pins] == typed
    assert [lb(j["linehead"]) for j in res.juan] == want_juan and len(res.juan) == 20
    assert len(res.anomalies) == 10  # the per-卷 continuation markers (R02 F27)
    assert all("R02 F27" in a for a in res.anomalies)
    assert [a.split(" on T34n1723_p", 1)[1][:7] for a in res.anomalies] == untyped


def test_t1723_all_28_pin_align_to_distinct_t0262_pin():
    root = tier1.build(raw_text("T09n0262", role="root"), mode="sutra", role="root")
    comm = tier1.build(raw_text("T34n1723", role="commentary"), mode="sutra", role="commentary")
    assert len(comm.drafts) == 28 and len(comm.anchors) == 28
    aligned = tier1.align_pins(comm.drafts, root.pins)
    spans = [(d["locations"]["root_text"] or {}).get("start") for d in aligned]
    chapter_starts = [p.start for p in root.pins if p.part_type == "品"]
    assert None not in spans
    assert len(set(spans)) == 28 and set(spans) == set(chapter_starts)
    assert spans == chapter_starts  # Kuiji follows the sūtra's chapter order
    assert all(d["flags"] == [] for d in aligned)
    dharani = next(d for d in aligned if d["_anchor"] == DEV[0])
    assert dharani["locations"]["root_text"] == {"start": "T09n0262_p0058b08",
                                                 "end": "T09n0262_p0059b27",
                                                 "basis": "chapter", "end_basis": None}
    assert_valid(sutra_doc(aligned))


def test_t1723_dev_span_input_reads_structure_whole_file():
    text = raw_text("T34n1723", span=DEV, role="commentary")
    res = tier1.build(text, mode="sutra", role="commentary")
    assert [d["_anchor"] for d in res.drafts] == [DEV[0]]
    assert len(res.pins) == 28 and len(res.juan) == 20
    assert res.anomalies == []  # no continuation marker inside the dev span
