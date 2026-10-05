"""Tests for chinese_workflow.outline.scheme (the scheme prior, design §5.3) and
chinese_workflow.outline.merge (design §5.4).

Offline: the T34n1723 / T09n0262 陀羅尼品 excerpts, hand-made root pins for the chapters the Kuiji
scheme names (T09n0262 lineheads: the root text, outside every split), and the Kuiji gold's dev
subtree, read through outline.oracle, as stand-in tier-2 drafts. With data/raw/: tier 1 + scheme
prior over the whole T34n1723 + T09n0262, checked against the gold's level-1/level-2 skeleton
(explained lines and root spans) read through the oracle filter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chinese_workflow.common import outline_doc
from chinese_workflow.common.paths import REFERENCE_OUTLINES, cbeta_xml_path
from chinese_workflow.ingest.text import load_input_text
from chinese_workflow.outline import merge, oracle, scheme, tier1
from chinese_workflow.outline.tier1 import Pin

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures" / "cbeta-xml-p5"
T1723_DEV = FIX / "T34n1723-excerpt-p0850a19-p0850b19.xml"
T0262_DEV = FIX / "T09n0262-excerpt-p0058b08-p0059b27.xml"
KUIJI = REFERENCE_OUTLINES / "T0262" / "kuiji-xuanzan" / "outline.json"
DEV = ("T34n1723_p0850a19", "T34n1723_p0850b19")
DHARANI = "T34n1723_p0850a19"

SOURCE = "Kuiji's first scheme, R03 F22 (今為二解, T34n1723_p0661b10); NEXT_STEPS decision (a)"
KUIJI_LEVEL1 = [
    {"heading_src": "序分", "from_pin": "序品", "to_pin": "序品", "source": SOURCE},
    {"heading_src": "正宗", "from_pin": "方便品", "to_pin": "授學無學人記品", "source": SOURCE},
    {"heading_src": "流通", "from_pin": "法師品", "to_pin": "普賢菩薩勸發品", "source": SOURCE},
]


def T(line):
    return "T09n0262_p" + line


# the chapters KUIJI_LEVEL1 names, with their spans in T09n0262 (read off the file's cb:mulu)
HAND_PINS = [
    Pin("序", "1 序品", T("0001c18"), T("0005b23"), "品", 1),
    Pin("方便", "2 方便品", T("0005b24"), T("0010b20"), "品", 1),
    Pin("授學無學人記", "9 授學無學人記品", T("0029b22"), T("0030b27"), "品", 1),
    Pin("法師", "10 法師品", T("0030b28"), T("0032b15"), "品", 1),
    None,  # 陀羅尼品, from the excerpt
    Pin("普賢菩薩勸發", "28 普賢菩薩勸發品", T("0061a05"), T("0062a29"), "品", 1),
]


def root_pins_offline():
    dharani = tier1.build(load_input_text(T0262_DEV, role="root"), mode="sutra", role="root").pins
    return [p if p is not None else dharani[0] for p in HAND_PINS]


def dharani_draft(root_pins):
    comm = tier1.build(load_input_text(T1723_DEV, role="commentary"), mode="sutra",
                       role="commentary")
    return tier1.align_pins(comm.drafts, root_pins)


def sutra_doc(roots):
    doc, private = outline_doc.build_prediction(
        roots, text_id="T0262", text_title_src="妙法蓮華經", outline_mode="sutra",
        root_text_id="T09n0262", commentary_id="T34n1723", scheme_id="kuiji-xuanzan",
        source_file="tests/fixtures/cbeta-xml-p5",
        generated_by="tests/unit/test_outline_scheme_merge.py",
        source_document={"kind": "commentary", "text_id": "T34n1723", "title": "妙法蓮華經玄贊"},
        format_note="scheme/merge test document")
    rep = outline_doc.validate(doc)
    assert rep.passed(), [f.render() for f in rep.errors]
    return doc, private


def walk(drafts, level=1):
    for d in drafts:
        yield level, d
        yield from walk(d.get("children") or [], level + 1)


def loc(d):
    c = d["locations"]["commentary"] or {}
    r = d["locations"]["root_text"] or {}
    return c.get("explained"), r.get("start"), r.get("end")


# ------------------------------------------------------------------------------ scheme prior


def test_level1_wraps_the_dev_chapter_in_liutong():
    pins = root_pins_offline()
    drafts, report = scheme.apply_level1(dharani_draft(pins), KUIJI_LEVEL1, root_pins=pins)
    assert len(drafts) == 1
    top = drafts[0]
    assert top["heading_src"] == "流通" and top["origin"] == "editorial"
    assert top["evidence"] == SOURCE and top["node_class"] == "sutra-span"
    # the gold's 流通: explained = its first 品's line; root span = the whole declared range
    assert top["locations"]["commentary"] == {"announced": None, "explained": DHARANI}
    assert top["locations"]["root_text"] == {"start": T("0030b28"), "end": T("0062a29"),
                                             "basis": "chapter", "end_basis": None}
    assert [d["heading_src"] for d in top["children"]] == ["陀羅尼品"]
    assert top["_scheme_prior"]["from_pin"] == "法師品"
    assert sorted((r["kind"], r["heading_src"]) for r in report) == [
        ("empty-range", "序分"), ("empty-range", "正宗")]
    doc, private = sutra_doc(drafts)
    assert [n["level"] for n in doc["nodes"]] == [1, 2]
    assert private["1_1"]["_scheme_prior"]["heading_src"] == "流通"
    assert private["1_1.1_2"]["_anchor"] == DHARANI


def test_level1_explained_from_commentary_pins():
    # a span run holds only 陀羅尼品; the commentary's own pins (structure, whole file) give the
    # line where 流通's first 品 (法師品) begins, the gold's convention for level-1 parts
    pins = root_pins_offline()
    comm_pins = [Pin("法師", "法師品", "T34n1723_p0806c24", "T34n1723_p0811a11", "品", 1),
                 Pin("陀羅尼", "陀羅尼品", DHARANI, "T34n1723_p0850b19", "品", 1)]
    drafts, _ = scheme.apply_level1(dharani_draft(pins), KUIJI_LEVEL1, root_pins=pins,
                                    commentary_pins=comm_pins)
    assert drafts[0]["locations"]["commentary"]["explained"] == "T34n1723_p0806c24"
    # from_pin without a commentary pin: the first wrapped draft's line
    drafts, _ = scheme.apply_level1(dharani_draft(pins), KUIJI_LEVEL1, root_pins=pins,
                                    commentary_pins=comm_pins[1:])
    assert drafts[0]["locations"]["commentary"]["explained"] == DHARANI
    sutra_doc(drafts)


def test_level1_leaves_uncovered_drafts_top_level():
    pins = root_pins_offline()
    only_zhengzong = [KUIJI_LEVEL1[1], {"heading_src": "某分", "from_pin": "見寶塔品",
                                         "to_pin": "見寶塔品", "source": "test"}]
    drafts, report = scheme.apply_level1(dharani_draft(pins), only_zhengzong, root_pins=pins)
    assert [d["heading_src"] for d in drafts] == ["陀羅尼品"]
    kinds = sorted(r["kind"] for r in report)
    assert kinds == ["empty-range", "outside-every-range", "unresolved-range"]
    sutra_doc(drafts)


# ------------------------------------------------------------------------------------- merge


def test_merge_attaches_dev_subtree_under_its_anchor():
    pins = root_pins_offline()
    wrapped, _ = scheme.apply_level1(dharani_draft(pins), KUIJI_LEVEL1, root_pins=pins)
    gold = oracle.oracle_drafts(KUIJI, keep_span=DEV)
    gold_dharani = next(d for lv, d in walk(gold) if lv == 2 and d["locations"]["commentary"]
                        ["explained"] == DHARANI)
    tier2 = {DHARANI: gold_dharani["children"]}
    roots, report = merge.attach(wrapped, tier2)
    assert report == []
    assert wrapped[0]["children"][0]["children"] == []  # input untouched
    merged = roots[0]["children"][0]
    assert merged["heading_src"] == "陀羅尼品" and merged["origin"] == "explicit"
    got = [(lv, d["heading_src"], loc(d)) for lv, d in walk(merged["children"])]
    want = [(lv, d["heading_src"], loc(d)) for lv, d in walk(gold_dharani["children"])]
    assert got == want and len(got) == 44
    doc, _ = sutra_doc(roots)
    assert doc["metadata"]["node_count"] == 1 + 1 + 44


def _t2(heading, line):
    return {"heading_src": heading, "origin": "explicit", "confidence": 1.0, "evidence": "test",
            "node_class": "commentary-internal", "flags": [], "notes": [],
            "locations": {"scheme": "cbeta-kepan",
                          "commentary": {"announced": None, "explained": "T34n1723_p0850" + line},
                          "root_text": None},
            "children": []}


def test_merge_keeps_document_order_and_reports():
    pins = root_pins_offline()
    base = dharani_draft(pins)
    base[0]["children"] = [_t2("甲", "a21"), _t2("丙", "b05")]
    tier2 = {DHARANI: [_t2("乙", "a25"), _t2("丁", "b10")],
             None: [_t2("前", "a19")],
             "T34n1723_p0850b01": [_t2("失", "b01")]}
    roots, report = merge.attach(base, tier2)
    assert [d["heading_src"] for d in roots] == ["前", "陀羅尼品"]
    assert [d["heading_src"] for d in roots[1]["children"]] == ["甲", "乙", "丙", "丁"]
    assert report == [{"kind": "unknown-anchor", "anchor": "T34n1723_p0850b01", "drafts": 1,
                       "detail": "no tier-1 draft has this anchor; drafts not attached"}]
    sutra_doc(roots)
    # equal lines: existing children first
    base[0]["children"] = [_t2("甲", "a21")]
    roots, _ = merge.attach(base, {DHARANI: [_t2("乙", "a21")]})
    assert [d["heading_src"] for d in roots[0]["children"]] == ["甲", "乙"]


def test_merge_shared_line_goes_to_innermost():
    g1977 = FIX / "G069n1977.xml"
    res = tier1.build(load_input_text(g1977, role="root"), mode="self-outlining", role="root")
    line = "G069n1977_p0717a01"
    note = {"heading_src": "註", "origin": "explicit", "confidence": 1.0, "evidence": "test",
            "node_class": "sutra-span", "flags": [], "notes": [],
            "locations": {"scheme": "cbeta-kepan",
                          "commentary": {"announced": None, "explained": line},
                          "root_text": {"start": line, "end": line, "basis": "self"}},
            "children": []}
    roots, report = merge.attach(res.drafts, {line: [note]})
    assert report[0]["kind"] == "ambiguous-anchor" and report[0]["targets"] == 3
    innermost = roots[0]["children"][0]["children"][0]
    assert innermost["heading_src"] == "初標題目"
    assert [d["heading_src"] for d in innermost["children"]] == ["註"]


# ------------------------------------------------------------- whole files (data/raw/ present)


def test_kuiji_scheme_reproduces_gold_skeleton():
    for fid in ("T09n0262", "T34n1723"):
        if cbeta_xml_path(fid) is None:
            pytest.skip("data/raw/cbeta/%s.xml not fetched (scripts/fetch_cbeta.sh)" % fid)
    root = tier1.build(load_input_text("T09n0262", role="root"), mode="sutra", role="root")
    comm = tier1.build(load_input_text("T34n1723", role="commentary"), mode="sutra",
                       role="commentary")
    aligned = tier1.align_pins(comm.drafts, root.pins)
    gold = oracle.oracle_drafts(KUIJI, keep_span=DEV)  # levels 1-2 through the filter
    want = [(lv, d["heading_src"], loc(d)) for lv, d in walk(gold) if lv <= 2]
    for comm_pins in (None, comm.pins):
        drafts, report = scheme.apply_level1(aligned, KUIJI_LEVEL1, root_pins=root.pins,
                                             commentary_pins=comm_pins)
        assert report == []
        got = [(lv, d["heading_src"], loc(d)) for lv, d in walk(drafts)]
        assert len(got) == 31
        assert got == want
        sutra_doc(drafts)
    # a dev-span run: one 品 draft, the level-1 part still as in the gold
    span_run = tier1.build(load_input_text("T34n1723", span=DEV, role="commentary"),
                           mode="sutra", role="commentary")
    drafts, _ = scheme.apply_level1(tier1.align_pins(span_run.drafts, root.pins), KUIJI_LEVEL1,
                                    root_pins=root.pins, commentary_pins=span_run.pins)
    got = [(lv, d["heading_src"], loc(d)) for lv, d in walk(drafts)]
    liutong = [w for w in want if w[1] == "流通"] + [w for w in want if w[2][0] == DHARANI]
    assert got == liutong
    sutra_doc(drafts)


def test_level1_never_wraps_a_tier2_draft_by_fuzzy_name():
    """Review of 2026-09-27: a top-level tier-2 draft (text before the first 品) whose heading shares
    two characters with a 品 name (「初明方便之意」 ~ 方便品) stays top-level; only chapter drafts are
    matched by name."""
    pins = root_pins_offline()
    preface = _t2("初明方便之意", "a19")
    preface["node_class"] = "sutra-span"
    drafts, report = scheme.apply_level1([preface] + dharani_draft(pins), KUIJI_LEVEL1,
                                         root_pins=pins)
    assert [d["heading_src"] for d in drafts] == ["初明方便之意", "流通"]
    assert any(r["kind"] == "outside-every-range" for r in report)
