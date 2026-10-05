"""outline.classify.mark_out_of_span on a hand-built document whose wording is the T1718 dev text
T34n1718_p0002a07–a11 (Zhiyi's 分文為三 and 又一時分為二 read inside 序品) and T1788's 初之一品 (outside
every split). Root 品 pins are hand-written from the root text's cb:mulu (tests/fixtures/cbeta-api/
works-toc-T0262.json: titles and start lines; ends approximate — only overlap with the ancestor's span
matters) over a hand LineOrder, so the test is offline.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from chinese_workflow.common import outline_doc
from chinese_workflow.common.lineheads import LineOrder
from chinese_workflow.outline import classify
from chinese_workflow.outline.tier1 import Pin, pin_name

C, R = "T34n1718_p", "T09n0262_p"
TOC = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "cbeta-api" / "works-toc-T0262.json")
                 .read_text(encoding="utf-8"))["results"][0]["mulu"]
TITLE = {m["n"]: m["title"] for m in TOC if m.get("type") == "品"}  # CBETA's mulu text, e.g. "2 方便品"
ORDER = LineOrder([R + x for x in ("0001c18", "0001c19", "0002b06", "0005b23", "0005b24", "0010b20",
                                   "0037a09", "0039c17", "0039c18", "0042a28", "0044a05", "0046b20",
                                   "0061a05", "0062a29")])
PINS = [Pin(pin_name(TITLE[n]), TITLE[n], R + a, R + b, "品", 1) for n, a, b in (
    (1, "0001c18", "0005b23"), (2, "0005b24", "0010b20"), (14, "0037a09", "0039c17"),
    (15, "0039c18", "0042a28"), (17, "0044a05", "0046b20"), (28, "0061a05", "0062a29"))]


def _n(heading, explained, *, raw=None, extent=None, span=None, count=None, children=(), part_type=None):
    rt = None if span is None else {"start": R + span[0], "end": R + span[1], "basis": span[2],
                                     "end_basis": None}
    d = {"heading_src": heading, "origin": "explicit", "confidence": 1.0, "evidence": "test",
         "node_class": "sutra-span", "flags": [] if span else ["unmapped"], "notes": [],
         "child_count_announced": count, "extent_announced": extent,
         "locations": {"scheme": "cbeta-kepan",
                       "commentary": {"announced": None, "explained": C + explained, "raw": raw or heading},
                       "root_text": rt},
         "children": list(children)}
    if part_type:
        d["part_type"] = part_type
    return d


def _doc(roots):
    doc, _ = outline_doc.build_prediction(
        roots, text_id="T0262", text_title_src="妙法蓮華經", outline_mode="sutra", root_text_id="T09n0262",
        commentary_id="T34n1718", scheme_id="zhiyi-wenju", source_file="tests/unit/test_outline_classify.py",
        generated_by="tests/unit/test_outline_classify.py", format_note="classify test document",
        source_document={"kind": "commentary", "text_id": "T34n1718", "title": "妙法蓮華經文句"})
    assert outline_doc.validate(doc).passed(), [f.render() for f in outline_doc.validate(doc).errors]
    return doc


def zhiyi_doc():
    return _doc([_n("序品", "0001b21", span=("0001c18", "0005b23", "chapter"), part_type="品", children=[
        _n("天台智者分文為三", "0002a07", span=("0001c19", "0005b23", "lemma"), count=3, children=[
            _n("初序", "0003a19", raw="初品為序", span=("0001c19", "0005b23", "lemma"), children=[
                _n("通序", "0003a21", raw="從「如是」去、至「却坐一面」，通序",
                   span=("0001c19", "0002b06", "lemma"), children=[
                    _n("釋同聞眾", "0005c29", raw="釋同聞眾為三", count=3)])]),
            _n("正", "0002a07:14", raw="〈方便品〉訖〈分別功德〉十九行偈，凡十五品半，名正", extent="凡十五品半"),
            _n("流通", "0002a08:20", raw="從偈後盡經，凡十一品半，名流通", extent="凡十一品半")]),
        _n("又一時分為二", "0002a09:14", count=2, children=[
            _n("約迹開權顯實", "0002a10:2", raw="從序至〈安樂行〉十四品，約迹開權顯實"),
            _n("約本開權顯實", "0002a11", raw="從〈踊出〉訖經十四品，約本開權顯實")]),
        _n("初之一品", "0002a12", raw="初之一品同於今古")])])


def _by_heading(doc):
    return {n["heading_src"]: n for n in doc["nodes"]}


def test_whole_text_parts_under_a_pin_are_out_of_span():
    doc = zhiyi_doc()
    before = copy.deepcopy(doc)
    out, report = classify.mark_out_of_span(doc, root_pins=PINS, order=ORDER)
    assert doc == before  # input untouched
    marked = {n["heading_src"] for n in out["nodes"] if classify.is_out_of_span(n)}
    assert marked == {"正", "流通", "約迹開權顯實", "約本開權顯實", "又一時分為二"}
    assert [(e["kind"], e["heading_src"]) for e in report] == [
        ("out-of-span", "正"), ("out-of-span", "流通"), ("out-of-span", "約迹開權顯實"),
        ("out-of-span", "約本開權顯實"), ("out-of-span", "又一時分為二")]
    by = _by_heading(out)
    for h in marked:
        n = by[h]
        assert "unmapped" in n["flags"] and n["locations"]["root_text"] is None
        assert n["notes"][-1].startswith(classify.OUT_OF_SPAN_NOTE % "")
    detail = {e["heading_src"]: e["detail"] for e in report}
    assert "〈方便品〉 is %s (exact), outside" % TITLE[2] in detail["正"]
    assert "凡十一品半 names 11.5 品 and the ancestor's span holds 1" in detail["流通"]
    assert "〈安樂行〉 is %s (exact), outside" % TITLE[14] in detail["約迹開權顯實"]
    assert "〈踊出〉 is %s (overlap 2), outside" % TITLE[15] in detail["約本開權顯實"]
    assert detail["又一時分為二"] == "all 2 parts of the division lie beyond this 品"
    for h in ("正", "流通"):
        assert "under %s 「天台智者分文為三」 T09n0262_p0001c19..T09n0262_p0005b23" % by["天台智者分文為三"]["id"] \
            in detail[h]
    # untouched: an unmapped node whose wording names no 品 beyond the pin, one 品 count that fits
    for h in ("釋同聞眾", "初之一品"):
        assert not classify.is_out_of_span(by[h]) and by[h]["flags"] == ["unmapped"]
    assert outline_doc.validate(out).passed()
    outline_doc.assert_explicit_unchanged(doc, out)


def test_to_the_end_of_the_sutra_alone_is_out_of_span():
    doc = _doc([_n("序品", "0001b21", span=("0001c18", "0005b23", "chapter"), part_type="品", children=[
        _n("流通", "0002a08", raw="從偈後盡經")])])
    out, report = classify.mark_out_of_span(doc, root_pins=PINS, order=ORDER)
    assert [e["heading_src"] for e in report] == ["流通"]
    assert report[0]["detail"].startswith("盡經 runs to the end of the sūtra")


def test_no_spanned_ancestor_marks_nothing():
    """The validation-row situation before Task 5: no pin, so the whole sūtra is admissible."""
    doc = _doc([_n("分文為三", "0002a07", count=3, children=[
        _n("正", "0002a07:14", raw="〈方便品〉訖〈分別功德〉十九行偈，凡十五品半，名正", extent="凡十五品半")])])
    out, report = classify.mark_out_of_span(doc, root_pins=PINS, order=ORDER)
    assert report == [] and out == doc


def test_not_sutra_mode_is_a_no_op():
    doc = zhiyi_doc()
    doc["metadata"]["outline_mode"] = "self-outlining"
    doc["metadata"]["commentary_id"] = None
    out, report = classify.mark_out_of_span(doc, root_pins=PINS, order=ORDER)
    assert report == [] and out == doc


def test_marking_twice_marks_once():
    """The (a)-(c) loop skips a node that carries the note, as the (d) loop does: no second note, no second
    report entry, the same document."""
    out, report = classify.mark_out_of_span(zhiyi_doc(), root_pins=PINS, order=ORDER)
    assert len(report) == 5
    again, report2 = classify.mark_out_of_span(out, root_pins=PINS, order=ORDER)
    assert report2 == [] and again == out
    for n in again["nodes"]:
        assert sum(s.startswith(classify.OUT_OF_SPAN_PREFIX) for s in n["notes"]) == (
            1 if n["heading_src"] in {e["heading_src"] for e in report} else 0)


# ---- wording: an extent is announced, a 品 is only mentioned. Each case is one unmapped node worded `raw`
# under 序品's span, which overlaps one root 品. The wording is invented, except the 品 names (the root's own).

def _under_xu(raw, extent=None):
    doc = _doc([_n("序品", "0001b21", span=("0001c18", "0005b23", "chapter"), part_type="品", children=[
        _n("試", "0002a07", raw=raw, extent=extent)])])
    out, report = classify.mark_out_of_span(doc, root_pins=PINS, order=ORDER)
    assert outline_doc.validate(out).passed()
    return out, report


MENTIONS = [
    "如〈方便品〉說，今不重明",  # a cross-reference
    "如〈方便品〉下說",  # a cross-reference that happens to be followed by 下
    "〈方便品〉中說，此義云何",  # followed by a word that is not an extent word
    "《維摩經》〈方便品〉訖，說空義",  # a chapter of another text
    "從《維摩經》〈方便品〉說起",
    "就第二品明開權",  # an ordinal, not a count (2 > 1 under 序品)
    "第十五品中，說壽量",  # its numeral tail 五 must not count either
    "第二十五品",
    "上中下三品，合為九品",  # grades
    "經有二品，一明因，二明果",  # a count with no extent context
    "從〈序品〉十四品",  # the 〈…〉 is masked: the count after it is not a 從-count
]


def test_a_mention_of_a_pin_is_not_an_extent():
    for raw in MENTIONS:
        out, report = _under_xu(raw)
        assert report == [], raw
        n = _by_heading(out)["試"]
        assert n["flags"] == ["unmapped"] and not classify.is_out_of_span(n) and n["notes"] == [], raw


NAMED = ["從〈方便品〉說", "自〈方便品〉", "至〈方便品〉", "訖〈方便品〉", "盡〈方便品〉", "從經〈方便品〉說",
         "〈方便品〉訖", "〈方便品〉至", "〈方便品〉下，明", "〈方便品〉已來"]
# raw -> the start of the detail: the count with the 凡 / 從 / 自 before it, N (+ ½ for 半)
COUNTED = {"凡十五品半，名正": "凡十五品半 names 15.5", "凡三品": "凡三品 names 3", "二品半": "二品半 names 2.5",
           "從三品說": "從三品 names 3", "自三品": "自三品 names 3", "三品訖": "三品 names 3",
           "三品至": "三品 names 3", "三品下，明": "三品 names 3", "三品已來": "三品 names 3"}


def test_an_extent_in_wording_is_still_out_of_span():
    """The shapes the dev text uses (the five-node test above), and the neighbouring forms the regexes admit:
    方便品 is the root's second 品, outside 序品's span."""
    for raw in NAMED:
        _, report = _under_xu(raw)
        assert len(report) == 1, raw
        assert report[0]["detail"].startswith("〈方便品〉 is %s (exact), outside; under" % TITLE[2]), raw
    for raw, want in COUNTED.items():
        _, report = _under_xu(raw)
        assert len(report) == 1 and report[0]["detail"].startswith(want), (raw, report)
        assert "品 and the ancestor's span holds 1" in report[0]["detail"]
    _, report = _under_xu("名正", extent="凡十五品半")  # extent_announced is read as well
    assert len(report) == 1 and report[0]["detail"].startswith("凡十五品半 names 15.5")
    # a count that fits the span is no extent beyond it
    assert _under_xu("凡一品，同於今古")[1] == []
