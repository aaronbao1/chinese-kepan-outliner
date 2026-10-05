"""Tests for chinese_workflow.eval.gold.authored — Task 4 of the eval-dataset build.

Always run: the parser and compiler on a SYNTHETIC outline text over SYNTHETIC line records / XML
(fictional ids T99n9998 = commentary, T99n9999 = root text; every word below is invented and says
nothing about a real text); the 陀羅尼品 subtree of the committed Kuiji outline.txt compiled against
the committed CBETA excerpts tests/fixtures/cbeta-xml-p5/T34n1723-excerpt-p0850a19-p0850b19.xml and
T09n0262-excerpt-p0058b08-p0059b27.xml (dev span only).
Run when data/raw/cbeta/T34n1723.xml and T09n0262.xml are present (skip otherwise): the committed
outline.txt compiles byte-identically to the committed outline.json and validates; its levels 1-2,
stop markers and coverage spans. The assertions about the 序品 and 譬喻品 subtrees (test-split
answer keys) are in tests/unit/test_gold_kuiji_testsplit.py, which is not to be opened while
developing (data/EVAL-SETS.md, "Do not open while developing").
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chinese_workflow.eval.gold import authored, common
from chinese_workflow.eval.gold.authored import AuthoredError, Text, compile_outline, parse

REPO = Path(__file__).resolve().parents[2]
GOLD_DIR = REPO / "data" / "reference-outlines" / "T0262" / "kuiji-xuanzan"
GOLD_TXT = GOLD_DIR / "outline.txt"
GOLD_JSON = GOLD_DIR / "outline.json"
RAW_CBETA = REPO / "data" / "raw" / "cbeta"
FIX_XML = REPO / "tests" / "fixtures" / "cbeta-xml-p5"
EXCERPT_COM = FIX_XML / "T34n1723-excerpt-p0850a19-p0850b19.xml"
EXCERPT_ROOT = FIX_XML / "T09n0262-excerpt-p0058b08-p0059b27.xml"

# ------------------------------------------------------------------------------ synthetic sources
# SYNTHETIC: (lb n, text, 品 cb:mulu label or None, inside a pin div)
ROOT_LINES = [
    ("0001a01", "合成經卷第一", None, False),
    ("0001a02", "甲品第一", "1 甲品", True),
    ("0001a03", "爾時世尊告大眾言：「汝等諦聽。」大眾", None, True),
    ("0001a04", "白佛言：「唯然，世尊。」", None, True),
    ("0001a05", "佛言：「善哉。」", None, True),
    ("0001a06", "乙品第二", "2 乙品", True),
    ("0001a07", "爾時文殊白佛言：「世尊！」佛默然。", None, True),
    ("0001a08", "", None, False),
    ("0001a09", "合成經卷第一", None, False),
]
COM_LINES = [
    ("0001b01", "甲品", "甲品", True),
    ("0001b02", "二門分別：一來意，二釋名。來意者，如前。", None, True),
    ("0001b03", "釋名者，甲者初也。", None, True),
    ("0001b04", "經「爾時世尊至汝等諦聽」。贊曰：品文分二：初", None, True),
    ("0001b05", "佛告眾，後眾答佛。此初。", None, True),
    ("0001b06", "經「大眾白佛至善哉」。贊曰：第二眾答。有二：", None, True),
    ("0001b07", "初眾答，後佛讚。", None, True),
    ("0001b08", "乙品", "乙品", True),
    ("0001b09", "經「爾時文殊至默然」。贊曰：此品一段。", None, True),
]

HEADER = """\
# SYNTHETIC outline text for tests/unit/test_gold_authored.py (fictional texts T99n9998/T99n9999)
scheme_id: synthetic-fixture
root_text_id: T99n9999
commentary_id: T99n9998
text_id: T9999
text_title_src: 合成經（SYNTHETIC）
text_title_en: Synthetic sūtra (SYNTHETIC)
source_title: 合成疏（SYNTHETIC）
seeded_by: null
gold_status: synthetic-fixture
licence_statement: Synthetic test data written in this repository; no third-party text.
eval_only: true
cbeta_release: null
coverage: everything
anomaly: none, synthetic
"""
C, R = "T99n9998_p0001", "T99n9999_p0001"
NODES = f"""\
甲品 @exp={C}b01 @root={R}a02..{R}a05 @basis=chapter
  # a comment inside the tree
  二門分別 @exp={C}b02 @class=commentary-internal @n=2
    一來意 @ann={C}b02 @exp={C}b02 @class=commentary-internal
    二釋名 @ann={C}b02 @exp={C}b03 @class=commentary-internal @note=first note @note=second note
  品文分二 @exp={C}b04 @lemma=爾時世尊至汝等諦聽 @root={R}a03..{R}a05 @basis=lemma @endbasis=chapter @n=2
    初佛告眾 @ann={C}b04 @exp={C}b05 @lemma=爾時世尊至汝等諦聽 @root={R}a03..{R}a03 @basis=lemma
    後眾答佛 @ann={C}b05 @exp={C}b06 @lemma=大眾白佛至善哉 @root={R}a03..{R}a05 @basis=lemma @n=2
      初眾答 @ann={C}b07 @exp={C}b07 @cut=大眾白佛言 @root={R}a03..{R}a04 @basis=manual
      後佛讚 @ann={C}b07 @exp={C}b07 @cut=佛言善哉 @root={R}a05..{R}a05 @basis=manual
乙品 @exp={C}b08 @root={R}a06..{R}a07 @basis=chapter
"""
TXT = HEADER + "\n" + NODES


def _records(xml_id, lines):
    return [
        {
            "linehead": "%s_p%s" % (xml_id, n),
            "text": text,
            "mulu": [{"type": "品", "level": 1, "text": mulu}] if mulu else [],
            "div_types": ["pin"] if pin else [],
        }
        for n, text, mulu, pin in lines
    ]


def _texts(root_lines=ROOT_LINES, com_lines=COM_LINES):
    return Text(_records("T99n9998", com_lines)), Text(_records("T99n9999", root_lines))


def _compile(txt=TXT, **kw):
    com, root = _texts(**kw)
    return compile_outline(parse(txt, "syn.outline.txt"), com, root)


def _errors(txt, **kw):
    with pytest.raises(AuthoredError) as exc:
        _compile(txt, **kw)
    return exc.value.messages


def _line_of(txt, needle):
    return next(k for k, line in enumerate(txt.splitlines(), 1) if needle in line)


# ------------------------------------------------------------------------------------------ parse


def test_parse_header_tree_and_fields():
    p = parse(TXT, "syn.outline.txt")
    assert p.header["scheme_id"] == "synthetic-fixture"
    assert p.header["coverage"] == ["everything"]
    assert [n.heading for n in p.roots] == ["甲品", "乙品"]
    jia = p.roots[0]
    assert [c.heading for c in jia.children] == ["二門分別", "品文分二"]
    assert [c.heading for c in jia.children[1].children] == ["初佛告眾", "後眾答佛"]
    gates = jia.children[0]
    assert gates.fields == {"exp": C + "b02", "class": "commentary-internal", "n": "2"}
    assert gates.children[1].fields["note"] == ["first note", "second note"]
    assert gates.children[1].level == 3
    assert gates.children[1].lineno == _line_of(TXT, "二釋名")


@pytest.mark.parametrize(
    "bad, message",
    [
        ("   三 @exp=X", "not a multiple of two"),
        ("      三 @exp=X", "one level at a time"),
        ("  三 @exp=X @bogus=1", "unknown field @bogus"),
        ("  三 @exp=X @n=1 @n=2", "@n given twice"),
        ("  三 @n=1", "missing @exp"),
        ("\t三 @exp=X", "tab in indentation"),
        ("  @exp=X", "empty heading"),
    ],
)
def test_parse_errors_name_their_line(bad, message):
    txt = TXT + bad + "\n"
    with pytest.raises(AuthoredError) as exc:
        parse(txt, "syn.outline.txt")
    lineno = len(txt.splitlines())
    assert any(
        message in m and m.startswith("syn.outline.txt:%d:" % lineno) for m in exc.value.messages
    ), exc.value.messages


def test_parse_header_errors():
    with pytest.raises(AuthoredError) as exc:
        parse("scheme_id: x\nbogus_key: y\n序 @exp=X\n", "h.txt")
    msgs = exc.value.messages
    assert any(m.startswith("h.txt:2:") and "unknown header key 'bogus_key'" in m for m in msgs)
    assert any("missing required key 'root_text_id'" in m for m in msgs)


def test_chinese_numerals_and_generated_labels():
    assert [authored.chinese_numeral(k) for k in (1, 10, 11, 19, 20, 21, 36, 99)] == [
        "一",
        "十",
        "十一",
        "十九",
        "二十",
        "二十一",
        "三十六",
        "九十九",
    ]
    assert authored.generated_label(2, 3) == "乙三"
    assert authored.generated_label(11, 1) == "子一"
    assert authored.generated_label(23, 1) is None


# ---------------------------------------------------------------------------------------- compile


def test_synthetic_outline_compiles_and_validates():
    doc, warnings = _compile()
    assert warnings == []
    rep = common.validate(doc)
    assert rep.errors == [] and rep.warnings == [], [f.render() for f in rep.findings]
    by = {n["heading_src"]: n for n in doc["nodes"]}
    assert [n["id"] for n in doc["nodes"]] == [
        "1_1",
        "1_1.1_2",
        "1_1.1_2.1_3",
        "1_1.1_2.2_3",
        "1_1.2_2",
        "1_1.2_2.1_3",
        "1_1.2_2.2_3",
        "1_1.2_2.2_3.1_4",
        "1_1.2_2.2_3.2_4",
        "2_1",
    ]
    assert by["初佛告眾"]["display_label"] == "丙一"
    assert by["品文分二"]["locations"]["root_text"] == {
        "start": R + "a03",
        "end": R + "a05",
        "basis": "lemma",
        "end_basis": "chapter",
        "raw": "爾時世尊至汝等諦聽",
    }
    assert by["二門分別"]["node_class"] == "commentary-internal"
    assert by["二門分別"]["locations"]["root_text"] is None
    assert by["二門分別"]["child_count_announced"] == 2
    assert by["後眾答佛"]["locations"] == {
        "scheme": "cbeta-kepan",
        "commentary": {"announced": C + "b05", "explained": C + "b06"},
        "root_text": {
            "start": R + "a03",
            "end": R + "a05",
            "basis": "lemma",
            "raw": "大眾白佛至善哉",
        },
    }
    # the heading crosses a line break of the commentary: evidence quotes both lines
    assert by["初佛告眾"]["evidence"] == "%sb04: %s | %sb05: %s" % (
        C,
        COM_LINES[3][1],
        C,
        COM_LINES[4][1],
    )
    assert by["甲品"]["evidence"] == C + "b01: 甲品"
    assert by["後佛讚"]["notes"] == [
        "root span starts at the annotator's cut 佛言：「善哉 (%sa05, root-text wording); the "
        "commentary quotes no lemma for this division" % R
    ]
    assert by["二釋名"]["notes"] == ["first note", "second note"]
    meta = doc["metadata"]
    assert meta["outline_profile"] == "zh-kepan"
    assert (meta["scheme_id"], meta["commentary_id"], meta["root_text_id"]) == (
        "synthetic-fixture",
        "T99n9998",
        "T99n9999",
    )
    assert meta["seeded_by"] is None and meta["eval_only"] is True and meta["cbeta_release"] is None
    assert meta["coverage"] == ["everything"] and meta["anomalies"] == ["none, synthetic"]
    assert (meta["node_count"], meta["max_depth"], meta["nodes_per_level"]) == (
        10,
        4,
        {"1": 2, "2": 2, "3": 4, "4": 2},
    )


def test_heading_must_occur_near_its_lines():
    txt = TXT.replace("一來意 @ann", "一來由 @ann")
    msgs = _errors(txt)
    assert len(msgs) == 1
    assert msgs[0].startswith(
        "syn.outline.txt:%d: 一來由: heading not found" % _line_of(txt, "一來由")
    )


def test_src_replaces_the_exp_ann_window():
    # 初佛告眾 is found near its @ann line; pointing @src at a far line makes the check fail there
    txt = TXT.replace("初佛告眾 @ann=", "初佛告眾 @src=%sb09 @ann=" % C)
    assert any("heading not found within ±2 lines of @src" in m for m in _errors(txt))


def test_mulu_label_is_accepted_as_heading():
    com = [list(x) for x in COM_LINES]
    com[0][1] = ""  # the 品 label only in cb:mulu, not in the body text
    com[7][1] = ""
    doc, _ = _compile(com_lines=[tuple(x) for x in com])
    jia = doc["nodes"][0]
    assert jia["evidence"] == "cb:mulu type=品 level=1 on %sb01: 甲品" % C


def test_unknown_lineheads_are_errors():
    txt = TXT.replace("@exp=%sb03" % C, "@exp=%sb99" % C).replace(
        "@root=%sa06..%sa07" % (R, R), "@root=%sa06..%sa66" % (R, R)
    )
    msgs = _errors(txt)
    assert any("@exp T99n9998_p0001b99 is not a line of T99n9998" in m for m in msgs)
    assert any("@root line T99n9999_p0001a66 is not a line of T99n9999" in m for m in msgs)


def test_lemma_must_resolve_to_the_root_span():
    txt = TXT.replace(
        "@lemma=大眾白佛至善哉 @root=%sa03..%sa05" % (R, R),
        "@lemma=大眾白佛至善哉 @root=%sa03..%sa04" % (R, R),
    )
    msgs = _errors(txt)
    assert any(
        "does not resolve" in m and "「善哉」 ends on T99n9999_p0001a05, not" in m for m in msgs
    )
    txt = TXT.replace("@lemma=大眾白佛至善哉", "@lemma=大眾白佛至善善")
    msgs = _errors(txt)
    assert any("not found within ±2 lines of @exp" in m for m in msgs)


def test_endbasis_loosens_the_lemma_end():
    # a lemma whose last words end before the span's end (a03..a05, 世尊 ends on a04): an error
    # unless @endbasis says the end was fixed otherwise
    com = [list(x) for x in COM_LINES]
    com[5][1] = com[5][1].replace("大眾白佛至善哉", "大眾白佛至世尊")
    com = [tuple(x) for x in com]
    txt = TXT.replace("@lemma=大眾白佛至善哉", "@lemma=大眾白佛至世尊")
    msgs = _errors(txt, com_lines=com)
    assert any("「世尊」 ends on T99n9999_p0001a04, not T99n9999_p0001a05" in m for m in msgs)
    doc, _ = _compile(
        txt.replace("@basis=lemma @n=2", "@basis=lemma @endbasis=next-node @n=2"), com_lines=com
    )
    rt = doc["nodes"][6]["locations"]["root_text"]
    assert (rt["start"], rt["end"], rt["basis"], rt["end_basis"]) == (
        R + "a03",
        R + "a05",
        "lemma",
        "next-node",
    )


def test_cut_must_start_on_the_root_start_line():
    txt = TXT.replace("@cut=佛言善哉 @root=%sa05" % R, "@cut=佛言善哉 @root=%sa04" % R)
    msgs = _errors(txt)
    assert any(
        "@cut '佛言善哉' does not start on T99n9999_p0001a04 (found on: T99n9999_p0001a05)" in m
        for m in msgs
    )


def test_next_node_rule_on_ends():
    txt = TXT.replace(
        "@cut=大眾白佛言 @root=%sa03..%sa04" % (R, R), "@cut=大眾白佛言 @root=%sa03..%sa03" % (R, R)
    )
    msgs = _errors(txt)
    assert len(msgs) == 1 and "初眾答: root span ends on T99n9999_p0001a03" in msgs[0]
    assert "starts after text ending on T99n9999_p0001a04" in msgs[0]


def test_chapter_basis_is_checked_against_pin_divs():
    txt = TXT.replace("@root=%sa06..%sa07" % (R, R), "@root=%sa06..%sa09" % (R, R))
    assert any("T99n9999_p0001a09 is not the last line of a 品" in m for m in _errors(txt))
    txt = TXT.replace("@root=%sa06..%sa07" % (R, R), "@root=%sa07..%sa07" % (R, R))
    assert any("T99n9999_p0001a07 carries no 品 cb:mulu" in m for m in _errors(txt))


def test_chapter_spans_one_pin_unless_it_has_pin_children():
    # a 品 node reaching into the next 品
    txt = TXT.replace(
        "甲品 @exp=%sb01 @root=%sa02..%sa05" % (C, R, R),
        "甲品 @exp=%sb01 @root=%sa02..%sa07" % (C, R, R),
    )
    msgs = _errors(txt)
    assert any("甲品: basis chapter: span runs over 品 #1-#2" in m for m in msgs)
    # a part node over 品 children must span exactly their 品
    part = (
        "部 @origin=editorial @evidence=synthetic grouping @exp=%sb01 @root=%sa02..%%s @basis=chapter\n"
        % (C, R)
    )
    nested = (
        HEADER + "\n" + part % (R + "a07") + "".join("  %s\n" % ln for ln in NODES.splitlines())
    )
    doc, _ = _compile(nested)
    assert [n["heading_src"] for n in doc["nodes"] if n["level"] == 1] == ["部"]
    msgs = _errors(nested.replace(part % (R + "a07"), part % (R + "a05")))
    assert any(
        "部: basis chapter: span covers 品 #1-#1 but its 品 children cover #1-#2" in m for m in msgs
    )


def test_chapter_neighbours_must_be_consecutive():
    txt = TXT + "甲品 @exp=%sb01 @root=%sa02..%sa05 @basis=chapter\n" % (C, R, R)
    msgs = _errors(txt)
    assert any(
        "乙品: root span ends with 品 #2 but the next division" in m
        and "starts with 品 #1: 品 spans must be consecutive" in m
        for m in msgs
    )


def test_endbasis_chapter_ends_the_start_pin():
    txt = TXT.replace(
        "@root=%sa03..%sa05 @basis=lemma @endbasis=chapter" % (R, R),
        "@root=%sa03..%sa04 @basis=lemma @endbasis=chapter" % (R, R),
    )
    msgs = _errors(txt)
    assert any(
        "品文分二: end_basis chapter: T99n9999_p0001a04 is not the last line of the 品" in m
        for m in msgs
    )


def test_endbasis_chapter_outside_every_pin_is_an_error():
    # start and end both outside every 品 (a01 is the juan title before 甲品): chapter_of(start)
    # is None and the end is no 品's last line, so ends.get(end) is None too — None == None must
    # not pass as "the last line of the 品 the start is in"
    node = (
        "卷首 @origin=editorial @evidence=synthetic @exp=%sb01 @cut=合成經卷第一 "
        "@root=%sa01..%sa01 @basis=manual @endbasis=chapter\n" % (C, R, R)
    )
    msgs = _errors(HEADER + "\n" + node + NODES)
    assert len(msgs) == 1, msgs
    assert "卷首: end_basis chapter: T99n9999_p0001a01 is not the last line of a 品" in msgs[0]
    assert "T99n9999_p0001a01 is in no 品" in msgs[0]


def test_lemsrc_moves_the_lemma_window():
    # 後眾答佛's lemma is quoted on b06; with its @exp moved to b09 (3 lines on) the ±2 window
    # around @exp misses it — Kuiji's nested announcements put 此初也 that far after the 經 line.
    # In COM_LINES b09 opens the next lemma, so this test gives b09 a topic marker instead
    far_com = [(n, "此初也。" if n == "0001b09" else t, m, p) for n, t, m, p in COM_LINES]
    old = "後眾答佛 @ann=%sb05 @exp=%sb06" % (C, C)
    far = TXT.replace(old, "後眾答佛 @ann=%sb05 @exp=%sb09" % (C, C))
    assert far != TXT
    msgs = _errors(far, com_lines=far_com)
    assert len(msgs) == 1 and "@lemma '大眾白佛至善哉' not found within ±2 lines of @exp" in msgs[0]
    ok = far.replace("後眾答佛 @ann=", "後眾答佛 @lemsrc=%sb06 @ann=" % C)
    doc, warnings = _compile(ok, com_lines=far_com)
    assert warnings == []
    node = next(n for n in doc["nodes"] if n["heading_src"] == "後眾答佛")
    assert node["locations"]["commentary"] == {"announced": C + "b05", "explained": C + "b09"}
    assert node["locations"]["root_text"]["raw"] == "大眾白佛至善哉"
    assert node["notes"] == [
        "lemma 經「大眾白佛至善哉」 quoted on %sb06, 3 line(s) before commentary.explained "
        "(the commentary in between quotes no other lemma)" % C
    ]
    # the same @exp where b09 opens the next lemma (經「爾時文殊…) is outside the lemma's block
    msgs = _errors(ok)
    assert len(msgs) == 1 and "another lemma (經「) is quoted between @lemsrc" in msgs[0]
    # @lemsrc is checked like @exp: the lemma must occur within ±2 lines of it
    msgs = _errors(ok.replace("@lemsrc=%sb06" % C, "@lemsrc=%sb01" % C), com_lines=far_com)
    assert any("@lemma '大眾白佛至善哉' not found within ±2 lines of @lemsrc" in m for m in msgs)
    msgs = _errors(ok.replace("@lemsrc=%sb06" % C, "@lemsrc=%sb99" % C), com_lines=far_com)
    assert any("@lemsrc T99n9998_p0001b99 is not a line of T99n9998" in m for m in msgs)
    msgs = _errors(TXT.replace("一來意 @ann=", "一來意 @lemsrc=%sb04 @ann=" % C))
    assert any("一來意: @lemsrc without @lemma" in m for m in msgs)
    # ... and it keeps @exp honest: it must come before @exp, with no other 經「 in between
    msgs = _errors(TXT.replace(old, "後眾答佛 @lemsrc=%sb06 @ann=%sb05 @exp=%sb05" % (C, C, C)))
    assert any("@lemsrc T99n9998_p0001b06 does not come before @exp" in m for m in msgs)
    early = TXT.replace(
        "初佛告眾 @ann=%sb04 @exp=%sb05" % (C, C), "初佛告眾 @ann=%sb04 @exp=%sb07" % (C, C)
    )
    msgs = _errors(early.replace("初佛告眾 @ann=", "初佛告眾 @lemsrc=%sb04 @ann=" % C))
    assert any("another lemma (經「) is quoted between @lemsrc" in m for m in msgs)


def test_lemsrc_block_includes_the_whole_exp_line():
    # a wrong @exp on the line that opens the next lemma (b06 starts 經「大眾白佛…) must fail:
    # the check runs to the end of the @exp line, not to its start
    old = "初佛告眾 @ann=%sb04 @exp=%sb05" % (C, C)
    assert old in TXT
    bad = TXT.replace(old, "初佛告眾 @lemsrc=%sb04 @ann=%sb04 @exp=%sb06" % (C, C, C))
    msgs = _errors(bad)
    assert len(msgs) == 1, msgs
    assert "another lemma (經「) is quoted between @lemsrc" in msgs[0]
    assert "初佛告眾" in msgs[0]


def test_lemsrc_hit_must_be_a_quoted_lemma():
    # the words of the lemma near @lemsrc must be a quotation (經「 immediately before them), not a
    # restatement of the sūtra words inside a gloss
    com = [
        (n, "贊曰：「大眾白佛至善哉」。第二眾答。有二：", m, p) if n == "0001b06" else (n, t, m, p)
        for n, t, m, p in COM_LINES
    ]
    old = "後眾答佛 @ann=%sb05 @exp=%sb06" % (C, C)
    lemsrc = TXT.replace(old, "後眾答佛 @lemsrc=%sb06 @ann=%sb05 @exp=%sb07" % (C, C, C))
    msgs = _errors(lemsrc, com_lines=com)
    assert len(msgs) == 1, msgs
    assert "後眾答佛" in msgs[0]
    assert "is not quoted as a lemma (no 經「 immediately before it)" in msgs[0]
    # the same lines with the lemma quoted as 經「…」 pass
    doc, _ = _compile(lemsrc)
    node = next(n for n in doc["nodes"] if n["heading_src"] == "後眾答佛")
    assert node["locations"]["commentary"]["explained"] == C + "b07"


COVERAGE = (
    f"coverage_span: root=甲品@{C}b01 commentary={C}b01..{C}b07 root_text={R}a02..{R}a05 "
    "max_level=full\n"
    f"coverage_span: root=document commentary={C}b01..{C}b09 root_text={R}a02..{R}a07 "
    "max_level=1\n"
)


def _with_coverage(coverage=COVERAGE):
    return TXT.replace("anomaly: none, synthetic\n", "anomaly: none, synthetic\n" + coverage)


def test_coverage_spans_compile_to_metadata():
    doc, warnings = _compile(_with_coverage())
    assert warnings == []
    assert doc["metadata"]["coverage_spans"] == [
        {
            "node_id": "1_1",
            "heading_src": "甲品",
            "commentary": {"start": C + "b01", "end": C + "b07"},
            "root_text": {"start": R + "a02", "end": R + "a05"},
            "max_level": None,
        },
        {
            "node_id": None,
            "heading_src": None,
            "commentary": {"start": C + "b01", "end": C + "b09"},
            "root_text": {"start": R + "a02", "end": R + "a07"},
            "max_level": 1,
        },
    ]
    assert common.validate(doc).errors == []
    # a text without coverage_span lines has no coverage_spans key
    assert "coverage_spans" not in _compile()[0]["metadata"]


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("root=甲品@", "root=丙品@", "root 丙品@T99n9998_p0001b01 names 0 nodes, not one"),
        (f"root_text={R}a02..{R}a05", f"root_text={R}a02..{R}a99", "not a line of its file"),
        (f"commentary={C}b01..{C}b07", f"commentary={C}b07..{C}b01", "a span starts after its end"),
        (f"commentary={C}b01..{C}b07", f"commentary={C}b01..{C}b05", "commentary line"),
        (f"root_text={R}a02..{R}a05", f"root_text={R}a02..{R}a04", "leaf span"),
        ("max_level=full", "max_level=2", "is deeper than max_level 2"),
        (f"root=甲品@{C}b01", f"root=甲品@{C}b01 extra", "expected 'root=<heading>@"),
    ],
)
def test_coverage_span_errors(old, new, message):
    cov = COVERAGE.replace(old, new, 1)
    assert cov != COVERAGE
    msgs = _errors(_with_coverage(cov))
    assert any("header coverage_span #1" in m and message in m for m in msgs), msgs


def test_coverage_span_document_depth_needs_another_entry():
    # the document entry's max_level 1 is fine only because 甲品's subtree has an entry of its own
    only_document = COVERAGE.split("\n")[1] + "\n"
    msgs = _errors(_with_coverage(only_document))
    assert any(
        "header coverage_span #1" in m and "is deeper than max_level 1 and in no other entry" in m
        for m in msgs
    ), msgs


@pytest.mark.parametrize(
    "heading, old, new, message",
    [
        ("後眾答佛", "@lemma=大眾白佛至善哉 @root", "@root", "@basis=lemma needs @lemma"),
        (
            "後佛讚",
            "@cut=佛言善哉 @root",
            "@lemma=佛言善哉 @root",
            "@lemma given but @basis is manual",
        ),
        ("後佛讚", "@cut=佛言善哉 @root", "@root", "@basis=manual needs @cut"),
        (
            "後眾答佛",
            "@lemma=大眾白佛至善哉 @root",
            "@cut=大眾白佛言 @root",
            "@cut given but @basis is lemma",
        ),
    ],
)
def test_locator_must_back_the_basis(heading, old, new, message):
    txt = TXT.replace(old, new, 1)
    assert txt != TXT
    msgs = _errors(txt)
    lineno = _line_of(txt, heading + " @")
    assert any(
        m.startswith("syn.outline.txt:%d: %s:" % (lineno, heading)) and message in m for m in msgs
    ), msgs


@pytest.mark.parametrize("space", ["\u3000", "\u3000\u3000", " \u3000 ", "\u00a0\u00a0"])
def test_non_ascii_indentation_is_an_error(space):
    txt = TXT.replace("  二門分別 @exp", space + "二門分別 @exp")
    with pytest.raises(AuthoredError) as exc:
        parse(txt, "syn.outline.txt")
    lineno = _line_of(txt, "二門分別")
    assert any(
        m.startswith("syn.outline.txt:%d:" % lineno)
        and "in indentation: indent with ASCII spaces only" in m
        for m in exc.value.messages
    ), exc.value.messages
    if "\u3000" in space:
        assert any("U+3000 (IDEOGRAPHIC SPACE)" in m for m in exc.value.messages)


def test_conf_and_ext_that_do_not_apply_are_warned():
    txt = TXT.replace(
        "二門分別 @exp=%sb02 @class=commentary-internal @n=2" % C,
        "二門分別 @exp=%sb02 @class=commentary-internal @n=2 @conf=0.4 @ext=二門" % C,
    )
    doc, warnings = _compile(txt)
    assert any("@conf ignored" in w for w in warnings)
    assert any("@ext on a commentary-internal node" in w for w in warnings)
    assert "confidence" not in doc["nodes"][1]
    txt = TXT.replace("乙品 @exp", "乙品丙 @origin=editorial @evidence=x @ext=一段 @exp")
    _, warnings = _compile(txt)
    assert any("@ext kept but not checked" in w for w in warnings)


def test_class_rules():
    txt = TXT.replace(
        "一來意 @ann=%sb02 @exp=%sb02 @class=commentary-internal" % (C, C),
        "一來意 @ann=%sb02 @exp=%sb02 @class=commentary-internal "
        "@root=%sa03..%sa03 @basis=manual" % (C, C, R, R),
    )
    assert any("commentary-internal node carries @root" in m for m in _errors(txt))
    txt = TXT.replace(
        "乙品 @exp=%sb08 @root=%sa06..%sa07 @basis=chapter" % (C, R, R), "乙品 @exp=%sb08" % C
    )
    assert any("without @root must carry @flags=unmapped" in m for m in _errors(txt))
    doc, _ = _compile(txt.replace("乙品 @exp=%sb08" % C, "乙品 @exp=%sb08 @flags=unmapped" % C))
    assert doc["nodes"][-1]["flags"] == ["unmapped"]
    assert common.validate(doc).errors == []


def test_origin_rules():
    txt = TXT.replace("乙品 @exp", "乙品 @origin=editorial @exp")
    assert any("origin editorial needs @evidence" in m for m in _errors(txt))
    txt = TXT.replace("乙品 @exp", "乙品丙 @origin=inferred @evidence=cue @exp")
    assert any("origin inferred needs @conf" in m for m in _errors(txt))
    doc, _ = _compile(
        TXT.replace("乙品 @exp", "乙品丙 @origin=inferred @conf=0.5 @evidence=cue @exp")
    )
    last = doc["nodes"][-1]
    assert (last["origin"], last["confidence"], last["evidence"]) == ("inferred", 0.5, "cue")


def test_count_mismatch_is_flagged_not_fatal():
    doc, warnings = _compile(TXT.replace("@n=2\n    一來意", "@n=3\n    一來意"))
    gates = doc["nodes"][1]
    assert gates["flags"] == ["count_mismatch"]
    assert "child_count_announced 3 but 2 children in this outline" in gates["notes"]
    assert len(warnings) == 1 and "@n 3 but 2 children" in warnings[0]
    assert common.validate(doc).errors == []


# -------------------------------------------------------------------------------- CLI, synthetic XML


def _write_xml(path, xml_id, lines):
    body = []
    for n, text, mulu, pin in lines:
        mulu_xml = '<cb:mulu type="品" level="1">%s</cb:mulu>' % mulu if mulu else ""
        line = '<lb n="%s" ed="T"/>%s<p>%s</p>' % (n, mulu_xml, text)
        body.append('<cb:div type="pin">%s</cb:div>' % line if pin else line)
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0" '
        'xml:id="%s"><text><body>\n%s\n</body></text></TEI>\n' % (xml_id, "\n".join(body)),
        encoding="utf-8",
    )


def test_cli_end_to_end_on_synthetic_xml(tmp_path, capsys):
    _write_xml(tmp_path / "T99n9998.xml", "T99n9998", COM_LINES)
    _write_xml(tmp_path / "T99n9999.xml", "T99n9999", ROOT_LINES)
    txt = tmp_path / "syn.outline.txt"
    txt.write_text(TXT, encoding="utf-8")
    out = tmp_path / "out" / "syn.outline.json"
    assert authored.main([str(txt), "-o", str(out), "--cbeta-dir", str(tmp_path)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert common.validate(doc).errors == []
    assert doc["metadata"]["authored_sha256"] == common.sha256_file(txt)
    assert doc["metadata"]["source_sha256"] == common.sha256_file(tmp_path / "T99n9998.xml")
    assert "PASS" in capsys.readouterr().out

    bad = tmp_path / "bad.outline.txt"
    bad.write_text(TXT.replace("二釋名 @ann", "二釋義 @ann"), encoding="utf-8")
    out2 = tmp_path / "bad.json"
    assert authored.main([str(bad), "-o", str(out2), "--cbeta-dir", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert ":%d: 二釋義: heading not found" % _line_of(TXT, "二釋名") in err
    assert not out2.exists()


# -------------------------------------------------------- Kuiji 陀羅尼品 subtree on committed excerpts


def _danluoni_subtree_txt() -> str:
    """The committed outline.txt's header + its 陀羅尼品 subtree, re-rooted at level 1."""
    lines = GOLD_TXT.read_text(encoding="utf-8").splitlines()
    header = []
    for line in lines:
        if line.strip() and not line.startswith("#") and not authored.HEADER_RE.match(line):
            break
        if not line.startswith("coverage_span:"):  # they name nodes of the whole gold
            header.append(line)
    start = next(k for k, line in enumerate(lines) if line.startswith("  陀羅尼品 @"))
    sub = [lines[start][2:]]
    for line in lines[start + 1 :]:
        if not line.startswith("    ") and line.strip() and not line.lstrip().startswith("#"):
            break
        sub.append(line[2:])
    return "\n".join(header + sub) + "\n"


def test_kuiji_danluoni_subtree_compiles_on_committed_excerpts():
    txt = _danluoni_subtree_txt()
    doc, warnings = compile_outline(
        parse(txt, "danluoni.outline.txt"),
        authored.load_text(EXCERPT_COM),
        authored.load_text(EXCERPT_ROOT),
    )
    assert warnings == []
    rep = common.validate(doc)
    assert rep.errors == [] and rep.warnings == [], [f.render() for f in rep.findings]
    nodes = doc["nodes"]
    assert doc["metadata"]["nodes_per_level"] == {"1": 1, "2": 2, "3": 6, "4": 5, "5": 14, "6": 17}
    assert doc["metadata"]["split_notes"] and "dev-split" in doc["metadata"]["split_notes"][0]
    assert nodes[0]["heading_src"] == "陀羅尼品"
    assert nodes[0]["locations"]["root_text"] == {
        "start": "T09n0262_p0058b08",
        "end": "T09n0262_p0059b27",
        "basis": "chapter",
    }
    top = [n for n in nodes if n["level"] == 2]
    # Kuiji convention: the 品's children are the gate node and the 品文 node
    assert [n["heading_src"] for n in top] == ["三門分別", "品文分三"]
    assert [n["node_class"] for n in top] == ["commentary-internal", "sutra-span"]
    pinwen = top[1]
    assert pinwen["child_count_announced"] == 3
    assert pinwen["locations"]["root_text"] == {
        "start": "T09n0262_p0058b09",
        "end": "T09n0262_p0059b27",
        "basis": "lemma",
        "end_basis": "chapter",
        "raw": "爾時藥王至功德甚多",
    }
    parts = [n for n in nodes if n["parent_id"] == pinwen["id"]]
    assert [n["heading_src"] for n in parts] == ["初明持經之福", "次明神呪之方", "後明時眾獲益"]
    gates = [n for n in nodes if n["parent_id"] == top[0]["id"]]
    assert [n["heading_src"] for n in gates] == ["一來意", "二釋名", "三解妨"]
    assert all(n["locations"]["root_text"] is None for n in gates)
    # every lemma division of the chapter (經「…」 at a29, b03, b06, b08, b12, b14, b18) is a node
    lemma_raw = {
        n["locations"]["root_text"]["raw"]
        for n in nodes
        if n["locations"]["root_text"] and n["locations"]["root_text"]["basis"] == "lemma"
    }
    assert lemma_raw == {
        "爾時藥王至功德甚多",
        "爾時藥王至多所饒益",
        "爾時勇施至是諸佛已",
        "爾時毘沙門至無諸衰患",
        "爾時持國至是諸佛已",
        "爾時有羅剎女至如是法師",
        "說是陀羅尼至無生法忍",
    }
    # the three parts of 品文分三 tile the chapter text
    spans = [
        (n["locations"]["root_text"]["start"], n["locations"]["root_text"]["end"]) for n in parts
    ]
    assert spans == [
        ("T09n0262_p0058b09", "T09n0262_p0058b17"),
        ("T09n0262_p0058b17", "T09n0262_p0059b26"),
        ("T09n0262_p0059b26", "T09n0262_p0059b27"),
    ]
    for n in nodes:
        assert n["origin"] == "explicit" and n["evidence"], n["heading_src"]


# ----------------------------------------------------------------------- real data (skip if absent)


@pytest.fixture(scope="module")
def compiled():
    need = [RAW_CBETA / "T34n1723.xml", RAW_CBETA / "T09n0262.xml"]
    missing = [p for p in need if not p.exists()]
    if missing:
        pytest.skip(
            "raw CBETA files absent (%s); run scripts/fetch_cbeta.sh"
            % ", ".join(common.repo_relative(p) for p in missing)
        )
    return authored.compile_file(GOLD_TXT)


def test_committed_gold_compiles_byte_identically(compiled, tmp_path):
    doc, warnings, report = compiled
    # compiler warnings are only of two kinds: an announced count cut short, naming a node that
    # carries flags truncated and count_mismatch, or a heading read across CBETA's punctuation.
    # Which nodes, and how many per test subtree: tests/unit/test_gold_kuiji_testsplit.py.
    truncated = {n["heading_src"] for n in doc["nodes"] if "truncated" in n["flags"]}
    counts = [w for w in warnings if "children: flag count_mismatch added" in w]
    for w in counts:
        assert w.split(": ")[1] in truncated, w
    for w in warnings:
        assert w in counts or "heading matches only with punctuation ignored" in w, w
    assert report.errors == []
    assert [(f.code, f.where) for f in report.warnings] == [("announce-after-explain", "1_1")]
    out = common.write_json(doc, tmp_path / "outline.json")
    assert out.read_bytes() == GOLD_JSON.read_bytes(), (
        "outline.json is stale: recompile with python -m chinese_workflow.eval.gold.authored"
    )


def test_committed_gold_levels_1_and_2(compiled):
    doc = compiled[0]
    meta = doc["metadata"]
    assert (meta["scheme_id"], meta["commentary_id"], meta["root_text_id"]) == (
        "kuiji-xuanzan",
        "T34n1723",
        "T09n0262",
    )
    assert meta["seeded_by"] == "claude-opus-5-5 (SDD draft 2026-09-22)"
    assert meta["gold_status"] == "draft-unreviewed"
    assert meta["licence"]["id"] == "CC-BY-NC-SA-4.0" and meta["cbeta_release"] == "2026R2"
    nodes = doc["nodes"]
    level1 = [n for n in nodes if n["level"] == 1]
    assert [n["heading_src"] for n in level1] == ["序分", "正宗", "流通"]
    assert {n["locations"]["commentary"]["announced"] for n in level1} == {"T34n1723_p0661b10"}
    kids = {n["id"]: [c for c in nodes if c["parent_id"] == n["id"]] for n in level1}
    assert [len(kids[n["id"]]) for n in level1] == [1, 8, 19]
    assert [n["child_count_announced"] for n in level1] == [1, 8, 19]
    # level 2 = T34n1723's 品 cb:mulu labels, in order, each @exp on its mulu line
    com = authored.load_text(RAW_CBETA / "T34n1723.xml")
    mulu = [
        (r["linehead"], m["text"]) for r in com.records for m in r["mulu"] if m.get("type") == "品"
    ]
    level2 = [n for n in nodes if n["level"] == 2]
    assert [(n["locations"]["commentary"]["explained"], n["heading_src"]) for n in level2] == mulu
    assert len(level2) == 28
    # level-2 root spans are consecutive 品 of T09n0262 (starts on its 品 cb:mulu lines, in order)
    root = authored.load_text(RAW_CBETA / "T09n0262.xml")
    pin_starts = [
        r["linehead"] for r in root.records if any(m.get("type") == "品" for m in r["mulu"])
    ]
    assert [n["locations"]["root_text"]["start"] for n in level2] == pin_starts


def test_committed_gold_stop_markers_and_coverage_spans(compiled):
    # controller decision 2026-09-22 (D15 addendum): flag truncated marks every node below which
    # Kuiji divides further but the gold stops; coarsened (the commentary itself stops) is unused
    doc = compiled[0]
    nodes = doc["nodes"]
    by_id = {n["id"]: n for n in nodes}
    parents = {n["parent_id"] for n in nodes}
    assert not any("coarsened" in n["flags"] for n in nodes)
    # the 25 品 without a subtree are truncated at level 2 (the truncated nodes inside the two
    # test subtrees: tests/unit/test_gold_kuiji_testsplit.py)
    bare = [n for n in nodes if n["level"] == 2 and n["id"] not in parents]
    assert len(bare) == 25 and all("truncated" in n["flags"] for n in bare)
    dharani = next(
        n for n in nodes if n["locations"]["commentary"]["explained"] == "T34n1723_p0850a19"
    )
    assert not any(
        "truncated" in n["flags"] for n in nodes if n["id"].startswith(dharani["id"] + ".")
    )
    # machine-readable coverage: the level-1/2 skeleton plus the three subtrees
    spans = doc["metadata"]["coverage_spans"]
    assert [(s["node_id"] is None, s["max_level"]) for s in spans] == [
        (True, 2),
        (False, 5),
        (False, None),
        (False, None),
    ]
    roots = [by_id[s["node_id"]] for s in spans[1:]]
    assert [r["locations"]["commentary"]["explained"] for r in roots] == [
        "T34n1723_p0651a06",
        "T34n1723_p0734b07",
        "T34n1723_p0850a19",
    ]
    assert all(
        r["level"] == 2 and r["heading_src"] == s["heading_src"] for r, s in zip(roots, spans[1:])
    )
    for s, r in zip(spans[1:], roots):
        assert r["locations"]["root_text"]["start"] <= s["root_text"]["start"]
    # the commentary spans are the split spans of global constraint 5 (end-exclusive there,
    # inclusive here), and the split note names each of them
    com = authored.load_text(RAW_CBETA / "T34n1723.xml")
    split_ends = {
        "T34n1723_p0651a06": "T34n1723_p0694b22",
        "T34n1723_p0734b07": "T34n1723_p0737b04",
        "T34n1723_p0850a19": "T34n1723_p0850b20",
    }
    for s in spans[1:]:
        start, end = s["commentary"]["start"], s["commentary"]["end"]
        assert com.records[com.pos[end] + 1]["linehead"] == split_ends[start]
        (note,) = doc["metadata"]["split_notes"]
        assert "%s–p%s" % (start, split_ends[start].split("_p")[1]) in note
    assert spans[0]["commentary"] == {
        "start": com.records[0]["linehead"],
        "end": com.records[-1]["linehead"],
    }
