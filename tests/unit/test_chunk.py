"""chunk stage: the interlinear outline (chunks.json / .md / .docx) over synthetic inputs.

The outline, the outlined-text sidecar and the sentences are built here from the T1723 dev excerpt
(tests/fixtures/cbeta-xml-p5/T34n1723-excerpt-p0850a19-p0850b19.xml, the whole 陀羅尼品 commentary)
and the T0262 陀羅尼品 excerpt, so these tests do not depend on the anchor or segment modules.
Synthetic outline (commentary target): 陀羅尼品 → 三門分別 (來意, 釋名, 解妨) and 品文分三
(初明持經之福, 次明神呪之方, 後明時眾獲益), positions read off the excerpt's own formulae.
"""

from __future__ import annotations

import copy
import itertools
import zipfile

import pytest
from lxml import etree

from chinese_workflow.chunk import chunker, render
from chinese_workflow.common import jsonio, outline_doc
from chinese_workflow.common.lineheads import strip_offset
from chinese_workflow.common.paths import FIXTURES
from chinese_workflow.ingest.text import load_input_text

T1723 = FIXTURES / "cbeta-xml-p5" / "T34n1723-excerpt-p0850a19-p0850b19.xml"
T0262 = FIXTURES / "cbeta-xml-p5" / "T09n0262-excerpt-p0058b08-p0059b27.xml"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DELIMS = "。？！；"
CLOSERS = "」』）"


# ------------------------------------------------------------------------------ synthetic inputs


def _draft(heading, children=(), **kw):
    return {"heading_src": heading, "children": list(children), **kw}


def _loc(announced, explained, root=None):
    return {"scheme": "cbeta-kepan", "commentary": {"announced": announced, "explained": explained},
            "root_text": root}


def _meta(**kw):
    meta = {"text_id": "T0262", "text_title_src": "妙法蓮華經", "outline_mode": "sutra",
            "root_text_id": "T09n0262", "commentary_id": "T34n1723",
            "scheme_id": "synthetic-test", "source_file": "synthetic:none",
            "source_document": {"kind": "commentary", "text_id": "T34n1723",
                                "title": "妙法蓮華經玄贊"},
            "generated_by": "tests/unit/test_chunk.py", "format_note": "synthetic test outline"}
    meta.update(kw)
    return meta


def commentary_target():
    return load_input_text(T1723, role="commentary")


def commentary_outline(t) -> dict:
    """The 3-level synthetic outline over the T1723 excerpt (positions from the text itself)."""

    def at(s):
        return t.locate(t.text.index(s))

    un = {"flags": ["unmapped"]}
    ci = {"node_class": "commentary-internal"}
    roots = [_draft("陀羅尼品", [
        _draft("三門分別", [
            _draft("來意", locations=_loc(at("一來意"), at("來意者")), **ci),
            _draft("釋名", locations=_loc(at("二釋名"), at("釋名者")), **ci),
            _draft("解妨", locations=_loc(at("三解妨"), at("解妨者")), **ci),
        ], locations=_loc(None, at("三門分別")), child_count_announced=3, **ci),
        _draft("品文分三", [
            _draft("明持經之福", locations=_loc(at("初明持經之福"), at("此初。")), **un),
            _draft("明神呪之方", locations=_loc(at("次明神呪之方"), at("經「爾時藥王至多所")),
                   topic_category="dhāraṇī spells", **un),
            _draft("明時眾獲益", locations=_loc(at("後明時眾獲益"), at("經「說是陀羅尼")), **un),
        ], locations=_loc(None, at("經「爾時藥王至功德")), child_count_announced=3, **un),
    ], locations=_loc(None, at("陀羅尼品"), {"start": "T09n0262_p0058b08",
                                             "end": "T09n0262_p0059b27", "basis": "chapter"}),
        part_type="品")]
    doc, _ = outline_doc.build_prediction(roots, **_meta())
    return doc


def root_outline(t) -> dict:
    """A root-target outline over the T0262 excerpt: children announced in the commentary."""

    def at(s):
        return t.locate(t.text.index(s))

    def span(start, end):
        return {"start": start, "end": end, "basis": "lemma"}

    roots = [_draft("陀羅尼品", [
        _draft("明持經之福", locations=_loc("T34n1723_p0850a30", "T34n1723_p0850b01:3",
                                           span(at("爾時，藥王"), "T09n0262_p0058b17"))),
        _draft("明神呪之方", locations=_loc("T34n1723_p0850a30:6", "T34n1723_p0850b03",
                                           span(at("爾時藥王菩薩白佛言"), "T09n0262_p0059b27"))),
    ], locations={"scheme": "cbeta-kepan", "commentary": None,
                  "root_text": {"start": "T09n0262_p0058b08", "end": "T09n0262_p0059b27",
                                "basis": "chapter"}},
        part_type="品")]
    doc, _ = outline_doc.build_prediction(roots, **_meta())
    return doc


def outlined_text(doc, t, role="commentary", drop=()) -> dict:
    """Pre-order anchoring as design §5.5 states it: a node starts at its explained locator
    (commentary target) or root_text.start (root target) and runs to the next node's start; a
    parent's text before its first child is its preamble. Node ids in `drop` lose their span (it
    becomes a gap)."""
    starts = []
    for n in doc["nodes"]:
        loc = n["locations"]
        ref = (loc["commentary"]["explained"] if role == "commentary"
               else loc["root_text"]["start"])
        starts.append((t.offset(ref), n["id"]))
    parents = {n["parent_id"] for n in doc["nodes"]}
    spans, gaps = [], []
    for i, (a, nid) in enumerate(starts):
        b = starts[i + 1][0] if i + 1 < len(starts) else len(t.text)
        if b <= a:
            continue
        if nid in drop:
            gaps.append({"char_start": a, "char_end": b, "reason": "test: span dropped"})
            continue
        spans.append({"node_id": nid, "kind": "preamble" if nid in parents else "leaf",
                      "char_start": a, "char_end": b,
                      "linehead_start": strip_offset(t.locate(a)),
                      "linehead_end": strip_offset(t.locate(b - 1)),
                      "resolution": "explained" if role == "commentary" else "root_text"})
    covered = sum(s["char_end"] - s["char_start"] for s in spans)
    lo, hi = starts[0][0], len(t.text)
    return {"schema": "outlined-text/1",
            "outline_ref": {"path": "synthetic/outline.json", "sha256": jsonio.sha256_json(doc)},
            "target": {"text_id": t.text_id, "role": role, "sha256": t.sha256,
                       "first_linehead": t.first_linehead, "last_linehead": t.last_linehead,
                       "length": len(t.text)},
            "spans": spans, "gaps": gaps,
            "coverage": {"start": lo, "end": hi, "chars": hi - lo, "covered": covered,
                         "ratio": covered / (hi - lo), "overlaps": 0}}


def sentences_for(ot, t) -> dict:
    """Strategy-1-like sentences (end at 。？！； plus closing brackets), cut at every span
    boundary."""
    cuts = sorted({0, len(t.text)} | {s["char_start"] for s in ot["spans"]}
                  | {s["char_end"] for s in ot["spans"]})
    owner = {s["char_start"]: s["node_id"] for s in ot["spans"]}
    out = []
    for a, b in itertools.pairwise(cuts):
        start = a
        i = a
        while i < b:
            if t.text[i] in DELIMS:
                j = i + 1
                while j < b and t.text[j] in CLOSERS:
                    j += 1
                out.append((start, j, owner.get(a)))
                start = i = j
                continue
            i += 1
        if start < b:
            out.append((start, b, owner.get(a)))
    return {"schema": "sentences/1", "strategy": 1, "punctuation_regime": "新式標點",
            "sentence_rule": "test: ends at 。？！； (closing brackets attached); cut at spans",
            "target": {"text_id": t.text_id, "sha256": t.sha256},
            "sentences": [{"id": "s%d" % k, "char_start": a, "char_end": b, "kind": "prose",
                           "node_id": nid} for k, (a, b, nid) in enumerate(out, 1)]}


def commentary_inputs(**kw):
    t = commentary_target()
    doc = commentary_outline(t)
    ot = outlined_text(doc, t, **kw)
    return doc, ot, sentences_for(ot, t), t


@pytest.fixture(scope="module")
def built():
    doc, ot, sents, t = commentary_inputs()
    return doc, ot, sents, t, chunker.build_chunks(doc, ot, sents, t)


# ----------------------------------------------------------------------------------------- rules


def test_synthetic_outline_validates():
    doc = commentary_outline(commentary_target())
    rep = outline_doc.validate(doc)
    assert rep.passed(), [f.render() for f in rep.errors]
    assert [n["id"] for n in doc["nodes"]][:3] == ["1_1", "1_1.1_2", "1_1.1_2.1_3"]


def test_chunks_validate_and_tile_the_text(built):
    doc, ot, sents, t, ch = built
    assert chunker.validate_chunks(ch) == []
    assert "".join(c["text"] for c in ch["chunks"]) == t.text
    pos = 0
    for k, c in enumerate(ch["chunks"], 1):
        assert c["chunk_id"] == "c%d" % k
        assert c["char_start"] == pos and c["text"] == t.text[c["char_start"]:c["char_end"]]
        assert c["loc_start"] == t.locate(c["char_start"])
        assert c["loc_end"] == t.locate(c["char_end"] - 1)
        pos = c["char_end"]
    assert pos == len(t.text)
    meta = ch["metadata"]
    assert meta["size_budget"] == {"sentence_cap": 6, "chars": 180}
    assert meta["target_role"] == "commentary" and meta["outline_ref"] == ot["outline_ref"]
    assert meta["counts"]["sentences"] == len(sents["sentences"])


def test_merge_rule_and_split_leaf(built):
    doc, ot, sents, t, ch = built
    rows = [(c["node_id"], tuple(c["leaf_ids"]), c["fallback"]) for c in ch["chunks"]]
    gate, text_div = "1_1.1_2", "1_1.2_2"
    # the 品 title is the 品 node's preamble; its children have children, so it stands alone
    assert rows[0] == ("1_1", ("1_1",), "none") and ch["chunks"][0]["text"] == "陀羅尼品"
    # gate preamble + 來意 + 釋名 merge (4 sentences); 解妨 (4 more) would pass the cap of 6
    assert rows[1] == (gate, (gate, gate + ".1_3", gate + ".2_3"), "none")
    assert rows[2] == (gate + ".3_3", (gate + ".3_3",), "none")
    # 品文分三 preamble + 初明持經之福 merge; 次明神呪之方 alone exceeds the budget -> split-leaf
    assert rows[3] == (text_div, (text_div, text_div + ".1_3"), "none")
    split = [c for c in ch["chunks"] if c["fallback"] == "split-leaf"]
    assert len(split) >= 2
    assert {c["node_id"] for c in split} == {text_div + ".2_3"}
    assert all(c["leaf_ids"] == [text_div + ".2_3"] for c in split)
    # 20 sentences at cap 6: four windows, evened out (not 6 + 6 + 6 + 2)
    assert [c["n_sentences"] for c in split] == [5, 5, 5, 5]
    assert rows[-1] == (text_div + ".3_3", (text_div + ".3_3",), "none")
    for c in ch["chunks"]:
        assert c["n_sentences"] <= 6 and c["n_chars"] <= 180
        assert c["n_sentences"] == len(c["sentence_ids"])
    assert ch["metadata"]["counts"]["merged_chunks"] == 2


def test_node_path_and_topic_category(built):
    ch = built[4]
    first, split = ch["chunks"][1], next(c for c in ch["chunks"] if c["fallback"] == "split-leaf")
    assert first["outline_path"] == ["1_1", "1_1.1_2"]
    assert first["topic_category"] == "陀羅尼品 / 三門分別"
    assert split["outline_path"] == ["1_1", "1_1.2_2", "1_1.2_2.2_3"]
    assert split["topic_category"] == "dhāraṇī spells"
    assert ch["chunks"][-1]["topic_category"] == "陀羅尼品 / 品文分三 / 明時眾獲益"
    assert ch["chunks"][3]["loc_start"] == "T34n1723_p0850a29"


def test_no_chunk_boundary_inside_a_unit(built):
    doc, ot, sents, t, ch = built
    for s in ot["spans"]:
        over = [c for c in ch["chunks"]
                if c["char_start"] < s["char_end"] and s["char_start"] < c["char_end"]]
        if len(over) > 1:
            assert all(c["fallback"] == "split-leaf" for c in over)
            assert over[0]["char_start"] == s["char_start"]
            assert over[-1]["char_end"] == s["char_end"]


def test_budget_knobs():
    doc, ot, sents, t = commentary_inputs()
    small = chunker.build_chunks(doc, ot, sents, t, sentence_cap=2, size_chars=None)
    assert small["metadata"]["size_budget"] == {"sentence_cap": 2, "chars": None}
    assert all(c["n_sentences"] <= 2 for c in small["chunks"])
    assert len(small["chunks"]) > len(chunker.build_chunks(doc, ot, sents, t)["chunks"])
    # a budget below the longest sentence: such a sentence stays whole, nothing else exceeds it
    tiny = chunker.build_chunks(doc, ot, sents, t, size_chars=10)
    for c in tiny["chunks"]:
        assert c["n_chars"] <= 10 or c["n_sentences"] == 1
    assert any(c["n_chars"] > 10 for c in tiny["chunks"])


def test_gap_becomes_unoutlined_windows():
    doc, ot, sents, t = commentary_inputs(drop=("1_1.2_2.2_3",))
    ch = chunker.build_chunks(doc, ot, sents, t)
    un = [c for c in ch["chunks"] if c["fallback"] == "unoutlined"]
    gap = ot["gaps"][0]
    assert un and un[0]["char_start"] == gap["char_start"] and un[-1]["char_end"] == gap["char_end"]
    for c in un:
        assert c["node_id"] is None and c["leaf_ids"] == [] and c["outline_path"] == []
        assert c["topic_category"] is None and c["n_sentences"] <= 6 and c["n_chars"] <= 180
    assert "1_1.2_2.2_3" not in {m["node_id"] for m in ch["markers"]}
    assert ch["metadata"]["counts"]["unoutlined_chars"] == gap["char_end"] - gap["char_start"]


def test_input_contract_violations():
    doc, ot, sents, t = commentary_inputs()
    bad = copy.deepcopy(sents)
    bad["target"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="different target"):
        chunker.build_chunks(doc, ot, bad, t)
    # merge two sentences across the 來意 / 釋名 boundary
    bad = copy.deepcopy(sents)
    cut = next(s["char_start"] for s in ot["spans"] if s["node_id"] == "1_1.1_2.2_3")
    k = next(i for i, s in enumerate(bad["sentences"]) if s["char_end"] == cut)
    bad["sentences"][k]["char_end"] = bad["sentences"][k + 1]["char_end"]
    del bad["sentences"][k + 1]
    with pytest.raises(ValueError, match="crosses the unit boundary"):
        chunker.build_chunks(doc, ot, bad, t)


# ------------------------------------------------------------------------------------ typography


def test_markers_and_announcements(built):
    doc, ot, sents, t, ch = built
    by_node = {m["node_id"]: m for m in ch["markers"]}
    # every node owns text here, so every node is taken up exactly once
    assert sorted(by_node) == sorted(n["id"] for n in doc["nodes"])
    assert len(ch["markers"]) == len(doc["nodes"])
    raiyi = by_node["1_1.1_2.1_3"]
    assert raiyi["indicator"] == "1₁1₂1₃" and raiyi["heading"] == "來意"
    assert raiyi["locator"] == t.locate(t.text.index("一來意"))  # announced, not explained
    assert by_node["1_1.2_2"]["locator"] == "T34n1723_p0850a29"  # never announced: explained
    # markers of merged units stack before the merged chunk, in outline order
    assert [m["node_id"] for m in ch["markers"] if m["before_chunk"] == "c2"] == [
        "1_1.1_2", "1_1.1_2.1_3", "1_1.1_2.2_3"]
    ann = [(a["node_id"], a["after_chunk"], a["parent_id"]) for a in ch["announcements"]]
    assert ann == [("1_1.1_2.1_3", "c2", "1_1.1_2"), ("1_1.1_2.2_3", "c2", "1_1.1_2"),
                   ("1_1.1_2.3_3", "c2", "1_1.1_2"), ("1_1.2_2.1_3", "c4", "1_1.2_2"),
                   ("1_1.2_2.2_3", "c4", "1_1.2_2"), ("1_1.2_2.3_3", "c4", "1_1.2_2")]
    assert ch["metadata"]["unplaced_announcements"] == []


def test_md_typography(built):
    doc, ot, sents, t, ch = built
    md = render.render_md(ch)
    runs = md.rstrip("\n").split("\n\n")
    assert len(runs) == len(ch["chunks"])
    assert runs[0] == "[1₁) 陀羅尼品 T34n1723_p0850a19]\n陀羅尼品"
    lines = runs[1].split("\n")
    assert lines[:3] == ["[1₁1₂) 三門分別 T34n1723_p0850a20]",
                         "[1₁1₂1₃) 來意 %s]" % t.locate(t.text.index("一來意")),
                         "[1₁1₂2₃) 釋名 %s]" % t.locate(t.text.index("二釋名"))]
    assert lines[3] == ch["chunks"][1]["text"] and lines[3].startswith("三門分別：")
    assert lines[4:] == ["1₁1₂1₃) 來意", "1₁1₂2₃) 釋名", "1₁1₂3₃) 解妨"]
    assert md.endswith("\n") and "\n\n\n" not in md


def test_md_round_trip(built):
    ch = built[4]
    back = render.parse_md(render.render_md(ch))
    assert back["chunk_texts"] == [c["text"] for c in ch["chunks"]]
    keys = ("indicator", "heading", "locator", "before_chunk")
    assert back["markers"] == [{k: m[k] for k in keys} for m in ch["markers"]]
    assert back["announcements"] == [{k: a[k] for k in ("indicator", "heading", "after_chunk")}
                                     for a in ch["announcements"]]
    kinds = [ln["type"] for ln in back["lines"]]
    assert kinds.count("chunk") == len(ch["chunks"])
    assert kinds.count("blank") == len(ch["chunks"]) - 1


def test_md_refuses_unreadable_content(built):
    ch = copy.deepcopy(built[4])
    ch["markers"][0]["heading"] = "兩行\n標題"
    with pytest.raises(ValueError, match="line break"):
        render.render_md(ch)
    ch = copy.deepcopy(built[4])
    ch["chunks"][0]["text"] = "[1₁) 偽 T34n1723_p0850a19]"
    with pytest.raises(ValueError, match="would not read back"):
        render.render_md(ch)


def test_root_target_announcements_follow_parent_chunk():
    t = load_input_text(T0262, role="root")
    doc = root_outline(t)
    ot = outlined_text(doc, t, role="root")
    ch = chunker.build_chunks(doc, ot, sentences_for(ot, t), t)
    assert chunker.validate_chunks(ch) == []
    assert ch["metadata"]["target_role"] == "root"
    assert "".join(c["text"] for c in ch["chunks"]) == t.text
    by_node = {m["node_id"]: m for m in ch["markers"]}
    assert by_node["1_1"]["locator"] == "T09n0262_p0058b08"  # no commentary: root_text.start
    assert by_node["1_1.1_2"]["locator"] == "T34n1723_p0850a30"  # announced, in the commentary
    first_of_parent = by_node["1_1"]["before_chunk"]
    assert [(a["node_id"], a["after_chunk"]) for a in ch["announcements"]] == [
        ("1_1.1_2", first_of_parent), ("1_1.2_2", first_of_parent)]
    assert ch["chunks"][0]["text"] == "妙法蓮華經陀羅尼品第二十六"
    assert render.parse_md(render.render_md(ch))["chunk_texts"] == [c["text"] for c in ch["chunks"]]


# ------------------------------------------------------------------------------ docx, determinism


def _docx_lines(path) -> list:
    """Paragraph texts of a docx, subscript runs turned back into Unicode subscript digits."""
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.iter(W + "p"):
        parts = []
        for r in p.iter(W + "r"):
            va = r.find("%srPr/%svertAlign" % (W, W))
            txt = "".join(tn.text or "" for tn in r.iter(W + "t"))
            if va is not None and va.get(W + "val") == "subscript":
                txt = txt.translate(str.maketrans("0123456789", render.SUBSCRIPT_DIGITS))
            parts.append(txt)
        out.append("".join(parts))
    return out


def test_docx_carries_markers_with_subscript_runs(built, tmp_path):
    ch = built[4]
    path = render.render_docx(ch, tmp_path / "chunks.docx")
    lines = _docx_lines(path)
    assert lines == render.render_md(ch).rstrip("\n").split("\n")
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert xml.count('w:vertAlign w:val="subscript"') > 0
    root = etree.fromstring(xml.encode("utf-8"))
    marker = next(p for p in root.iter(W + "p")
                  if "".join(t.text or "" for t in p.iter(W + "t")).startswith("[111213) 來意"))
    runs = [(("".join(t.text or "" for t in r.iter(W + "t"))),
             r.find("%srPr/%svertAlign" % (W, W)) is not None) for r in marker.iter(W + "r")]
    assert runs[:6] == [("[1", False), ("1", True), ("1", False), ("2", True), ("1", False),
                        ("3", True)]


def test_deterministic(tmp_path):
    a = chunker.build_chunks(*commentary_inputs())
    b = chunker.build_chunks(*commentary_inputs())
    assert jsonio.dumps(a) == jsonio.dumps(b)
    assert render.render_md(a) == render.render_md(b)
    pa = render.render_docx(a, tmp_path / "a.docx")
    pb = render.render_docx(b, tmp_path / "b.docx")
    assert pa.read_bytes() == pb.read_bytes()


def test_cli_writes_the_three_files(tmp_path, capsys):
    from chinese_workflow.chunk.__main__ import main

    doc, ot, sents, t = commentary_inputs()
    outline_path = jsonio.write_json(doc, tmp_path / "outline.json")
    ot["outline_ref"] = {"path": str(outline_path), "sha256": jsonio.sha256_file(outline_path)}
    ot_path = jsonio.write_json(ot, tmp_path / "outlined-text.json")
    s_path = jsonio.write_json(sents, tmp_path / "sentences.json")
    out = tmp_path / "out"
    assert main(["--outline", str(outline_path), "--outlined-text", str(ot_path),
                 "--sentences", str(s_path), "--target", str(T1723), "--out", str(out)]) == 0
    assert "chunks:" in capsys.readouterr().out
    ch = jsonio.read_json(out / "chunks.json")
    assert chunker.validate_chunks(ch) == []
    assert ch["metadata"]["split_guard"][0]["splits"] == ["dev"]
    assert ch["metadata"]["outline_ref"]["sha256"] == jsonio.sha256_file(outline_path)
    assert (out / "chunks.md").read_text(encoding="utf-8") == render.render_md(ch)
    assert zipfile.is_zipfile(out / "chunks.docx")
    # an outlined-text made from another outline is refused
    ot["outline_ref"]["sha256"] = "f" * 64
    jsonio.write_json(ot, ot_path)
    with pytest.raises(ValueError, match="different outline"):
        main(["--outline", str(outline_path), "--outlined-text", str(ot_path),
              "--sentences", str(s_path), "--target", str(T1723), "--out", str(out)])
