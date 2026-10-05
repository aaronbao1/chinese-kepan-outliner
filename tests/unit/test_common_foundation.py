"""chinese_workflow.common: linehead grammar, draft numbering, prediction documents, the split guard."""

from __future__ import annotations

import copy

import pytest

from chinese_workflow.common import lineheads, outline_doc, splits
from chinese_workflow.eval import registry as reg


def test_linehead_parse_and_offset():
    r = lineheads.parse("T34n1723_p0850b01:12")
    assert r.file == "T34n1723" and r.page == "0850" and r.register == "b" and r.line == 1
    assert r.offset == 12 and r.linehead == "T34n1723_p0850b01"
    assert lineheads.strip_offset("T34n1723_p0850b01:12") == "T34n1723_p0850b01"
    assert lineheads.file_id("X11n0268_p0185a08") == "X11n0268"
    with pytest.raises(ValueError):
        lineheads.parse("T34n1723_0850b01")


def test_line_order():
    order = lineheads.LineOrder(["A01n0001_p0001a01", "A01n0001_p0001a02", "A01n0001_p0001a03"])
    assert order.distance("A01n0001_p0001a01", "A01n0001_p0001a03:4") == 2
    assert order.between("A01n0001_p0001a02", "A01n0001_p0001a03") == [
        "A01n0001_p0001a02", "A01n0001_p0001a03"]
    assert order.prev("A01n0001_p0001a01") is None


def _draft(heading, children=(), **kw):
    return {"heading_src": heading, "children": list(children), **kw}


def test_build_prediction_validates():
    loc = {"scheme": "cbeta-kepan",
           "commentary": {"announced": None, "explained": "T99n9998_p0001a01"},
           "root_text": None}
    roots = [_draft("甲", [_draft("乙", locations=loc, node_class="commentary-internal", _offset=3)],
                    locations=loc, node_class="commentary-internal")]
    doc, private = outline_doc.build_prediction(
        roots, text_id="T9999", text_title_src="合成", outline_mode="sutra",
        root_text_id="T99n9999", commentary_id="T99n9998", scheme_id="synthetic-fixture",
        source_file="synthetic:none",
        source_document={"kind": "synthetic", "text_id": "T99n9998", "title": "合成疏"},
        generated_by="test", format_note="synthetic")
    ids = [n["id"] for n in doc["nodes"]]
    assert ids == ["1_1", "1_1.1_2"]
    assert doc["nodes"][1]["indicator_display"] == "1₁1₂"
    assert doc["nodes"][1]["display_label"] == "乙一"
    assert private == {"1_1.1_2": {"_offset": 3}}
    rep = outline_doc.validate(doc)
    assert rep.passed(), [f.render() for f in rep.errors]
    again = outline_doc.to_drafts(doc)
    doc2, _ = outline_doc.build_prediction(again, **{k: doc["metadata"][k] for k in (
        "text_id", "text_title_src", "outline_mode", "root_text_id", "commentary_id", "scheme_id",
        "source_file", "source_document", "generated_by", "format_note")})
    assert [n["id"] for n in doc2["nodes"]] == ids


_META = dict(text_id="T9999", text_title_src="合成", outline_mode="sutra", root_text_id="T99n9999",
             commentary_id="T99n9998", scheme_id="synthetic-fixture", source_file="synthetic:none",
             source_document={"kind": "synthetic", "text_id": "T99n9998", "title": "合成疏"},
             generated_by="test", format_note="synthetic")


def _com(line):
    """A commentary-internal draft's location on a synthetic commentary line (None: not located)."""
    return {"scheme": "cbeta-kepan", "commentary": {"announced": None, "explained": line},
            "root_text": None}


def _gate(heading, children=(), **kw):
    return _draft(heading, children, node_class="commentary-internal", **kw)


def test_fill_span_starts_chains_first_children():
    """sdp's anchor rule (data/EVAL-SETS.md item 3): a first child's text starts where its parent's
    does, recursively; every other node starts at its own explained line; a node without a
    commentary position gets nothing and ends the chain below it."""
    roots = [
        _gate("甲", [_gate("乙", [_gate("丙", locations=_com("T99n9998_p0001a05"))],
                            locations=_com("T99n9998_p0001a03")),
                     _gate("丁", locations=_com("T99n9998_p0001a07")),
                     _gate("戊", [_gate("己", locations=_com("T99n9998_p0001a09"))])],  # 戊: scheme none
              locations=_com("T99n9998_p0001a01")),
        _gate("庚", [_gate("辛", locations=_com(None))], locations=_com("T99n9998_p0001b01")),
    ]
    doc, _ = outline_doc.build_prediction(roots, **_META)
    assert not any("span_start" in (n["locations"].get("commentary") or {}) for n in doc["nodes"])
    assert outline_doc.fill_span_starts(doc) is doc
    got = {n["heading_src"]: tuple((n["locations"].get("commentary") or {}).get(k, "absent")
                                   for k in ("span_start", "span_start_inherited"))
           for n in doc["nodes"]}
    assert got == {
        "甲": ("T99n9998_p0001a01", False),  # a root: its own line
        "乙": ("T99n9998_p0001a01", True),   # first child: its parent's start
        "丙": ("T99n9998_p0001a01", True),   # first child of a first child: the chain's start
        "丁": ("T99n9998_p0001a07", False),  # has an elder sibling: its own line
        "戊": ("absent", "absent"),         # no commentary position: nothing written
        "己": ("T99n9998_p0001a09", False),  # its parent has no span start: its own line
        "庚": ("T99n9998_p0001b01", False),
        "辛": ("T99n9998_p0001b01", True),   # inherits although its own explained is null
    }
    rep = outline_doc.validate(doc)
    assert rep.passed(), [f.render() for f in rep.errors]
    again = copy.deepcopy(doc)
    corrupted = 0
    for n in again["nodes"]:  # wrong values on every node that has the pair: a read-back would keep them
        com = n["locations"].get("commentary")
        if isinstance(com, dict):
            com["span_start"], com["span_start_inherited"] = "T99n9998_p0009c29", not com["span_start_inherited"]
            corrupted += 1
    assert corrupted == 7 and again != doc
    assert outline_doc.fill_span_starts(again) == doc  # idempotent: recomputed, never read back


def _span_build(roots, first="T99n9998_p0010a01", last="T99n9998_p0010c29"):
    """A span build's document: metadata.span is the build's first and last line (ingest.structure)."""
    doc, _ = outline_doc.build_prediction(roots, span={"first": first, "last": last}, **_META)
    return outline_doc.fill_span_starts(doc)


def _pair(doc):
    return {n["heading_src"]: ((n["locations"].get("commentary") or {}).get("span_start"),
                               (n["locations"].get("commentary") or {}).get("span_start_inherited"))
            for n in doc["nodes"]}


def test_span_start_does_not_inherit_from_an_editorial_parent_before_the_span():
    """Final review 2026-10-03, Important 1: the scheme prior's level-1 node is editorial and its
    explained line (the part's first 品) lies 44 pages before the dev span. Its explicit first child
    and the chain below start in the span: the child takes its own line, never the editorial parent's,
    and its own first children inherit that."""
    def tree(**kw):
        return [_gate("流通分", [_gate("藥王品", [_gate("品文分三", [_gate("初明福", locations=_com("T99n9998_p0010a05"))],
                                                        locations=_com("T99n9998_p0010a03"))],
                                        locations=_com("T99n9998_p0010a01")),
                                 _gate("妙音品", locations=_com("T99n9998_p0010b01"))],
                      locations=_com("T99n9998_p0001a01"), **kw)]
    got = _pair(_span_build(tree(origin="editorial")))
    assert got == {
        "流通分": ("T99n9998_p0001a01", False),  # editorial root: its own explained line, outside the span
        "藥王品": ("T99n9998_p0010a01", False),  # first child of an editorial parent: its own line
        "品文分三": ("T99n9998_p0010a01", True),  # first child of an in-span explicit parent: inherits
        "初明福": ("T99n9998_p0010a01", True),   # and so down the chain
        "妙音品": ("T99n9998_p0010b01", False),
    }
    # the same tree with an explicit root: its start still lies before the span, so the cut is the same
    assert _pair(_span_build(tree())) == got


def test_span_start_does_not_inherit_a_carried_pins_start():
    """Task 5's carried pin (outline.tier1._carried_draft: origin editorial, explained = the mulu line
    before the span, 'unmapped') is the span's only ancestor of the part of the unit the span starts
    in; the build's first child under it is only the first child the build has, so it keeps its own
    line, and an explicit parent with a start before the span cuts the chain the same way."""
    pin = _gate("陀羅尼品", [_gate("總說", [_gate("初標", locations=_com("T99n9998_p0010a02"))],
                                   locations=_com("T99n9998_p0010a01")),
                            _gate("別說", locations=_com("T99n9998_p0010a09"))],
                origin="editorial", flags=["unmapped"], locations=_com("T99n9998_p0003b11"))
    got = _pair(_span_build([pin]))
    assert got == {"陀羅尼品": ("T99n9998_p0003b11", False), "總說": ("T99n9998_p0010a01", False),
                   "初標": ("T99n9998_p0010a01", True), "別說": ("T99n9998_p0010a09", False)}
    # an explicit parent whose start lies before the span (offset on the line is ignored) and a start on
    # the span's own first line: only the first is cut
    explicit = [_gate("甲", [_gate("乙", [_gate("丙", locations=_com("T99n9998_p0010a03"))],
                                   locations=_com("T99n9998_p0010a02"))],
                      locations=_com("T99n9998_p0009c28:4")),
                _gate("丁", [_gate("戊", locations=_com("T99n9998_p0010a05"))],
                      locations=_com("T99n9998_p0010a01:7"))]
    got = _pair(_span_build(explicit))
    assert got["乙"] == ("T99n9998_p0010a02", False) and got["丙"] == ("T99n9998_p0010a02", True)
    assert got["戊"] == ("T99n9998_p0010a01:7", True)  # on the first line: inside the build


def test_span_start_inherits_in_a_whole_text_build_and_without_a_span():
    """A build over the whole file (span first = the file's first line) and a document without
    metadata.span cut nothing: the plain chain inherits as before, editorial roots excepted."""
    def tree():
        return [_gate("甲", [_gate("乙", [_gate("丙", locations=_com("T99n9998_p0001a05"))],
                                   locations=_com("T99n9998_p0001a03"))],
                      locations=_com("T99n9998_p0001a01"))]
    expect = {"甲": ("T99n9998_p0001a01", False), "乙": ("T99n9998_p0001a01", True),
              "丙": ("T99n9998_p0001a01", True)}
    assert _pair(_span_build(tree(), first="T99n9998_p0001a01", last="T99n9998_p0020c29")) == expect
    doc, _ = outline_doc.build_prediction(tree(), **_META)
    assert "span" not in doc["metadata"]
    assert _pair(outline_doc.fill_span_starts(doc)) == expect


def test_span_start_cli_adds_the_locator_to_a_saved_outline(tmp_path, capsys):
    """python -m chinese_workflow.outline span-start IN --out OUT: IN is left as it is; OUT carries
    the pair on every node with a commentary position, says who filled it, and validates."""
    import json

    from chinese_workflow.common.jsonio import read_json, write_json
    from chinese_workflow.outline.__main__ import main as outline_main

    roots = [_gate("甲", [_gate("乙", locations=_com("T99n9998_p0001a03"))],
                   locations=_com("T99n9998_p0001a01"))]
    doc, _ = outline_doc.build_prediction(roots, **_META)
    src = write_json(doc, tmp_path / "outline.json")
    out = tmp_path / "outline.span-start.json"
    assert outline_main(["span-start", str(src), "--out", str(out)]) == 0
    got = read_json(out)
    assert [n["locations"]["commentary"]["span_start_inherited"] for n in got["nodes"]] == [False, True]
    assert got["nodes"][1]["locations"]["commentary"]["span_start"] == "T99n9998_p0001a01"
    assert got["metadata"]["span_start_filled_by"].startswith(
        "python -m chinese_workflow.outline span-start @ ")
    assert "span_start" not in read_json(src)["nodes"][0]["locations"]["commentary"]  # input untouched
    line = json.loads(capsys.readouterr().out)
    assert line["span_start_inherited"] == 1 and line["validation"]["passed"] is True
    # --out may not be the input itself (an argument error, exit code 2): it is left as it is
    before = src.read_bytes()
    with pytest.raises(SystemExit) as exc:
        outline_main(["span-start", str(src), "--out", str(tmp_path / "." / "outline.json")])
    assert exc.value.code == 2 and src.read_bytes() == before


def test_split_guard_agrees_with_registry():
    registry = reg.load_registry()
    for text, spec in reg.split_texts(registry).items():
        for span in spec["spans"]:
            for lh in (span["start"], span["end"]):
                if lh is None:
                    continue
                assert splits.split_of_line(registry, lh) == reg.split_of(registry, text, lh)
    assert splits.split_of_line(registry, "T09n0262_p0001c18") == "unsplit"


def test_split_guard_refuses_test_and_reserve():
    guard = splits.SplitGuard()
    assert guard.check_lines(["T34n1723_p0850a19", "T34n1723_p0850b19"]) == {"dev"}
    with pytest.raises(splits.SplitViolation):
        guard.check_lines(["T34n1723_p0651a06"])  # 序品: test
    with pytest.raises(splits.SplitViolation):
        guard.check_lines(["T34n1723_p0850b20"])  # after the dev span: reserve
    frozen = splits.SplitGuard(frozen="outliner-v1")
    assert frozen.check_lines(["T34n1723_p0651a06"]) == {"test"}


def test_split_guard_golds():
    guard = splits.SplitGuard()
    with pytest.raises(splits.SplitViolation):
        guard.check_gold("cbeta-mulu-X0268")
    with pytest.raises(splits.SplitViolation):
        guard.check_gold("sdp-T1718-zhiyi-wenju", as_input=True)
    assert guard.check_gold("kuiji-xuanzan")["id"] == "kuiji-xuanzan"
    assert splits.SplitGuard(frozen="v1").check_gold("cbeta-mulu-X0268")
