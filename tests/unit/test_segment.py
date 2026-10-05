"""Tests for chinese_workflow.segment (sentence boundaries, strategy 1–2, design §6).

Always run: the committed fixtures tests/fixtures/cbeta-xml-p5/T34n1723-excerpt-… (the T1723 dev
span: a commentary with 經「…」。贊曰：… lemma divisions) and T09n0262-excerpt-… (the 陀羅尼品
of the root text: five dhāraṇīs in prose paragraphs, one gāthā in lg/l with caesuras), plus
synthetic line records for the edge cases. Run when present, skip otherwise:
data/raw/cbeta/T09n0262.xml and the xml-p5 clone's T32n1666.xml (whole files).

Expected sentences were read off the fixture text by hand.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from chinese_workflow.common.jsonio import read_json, sha256_text, write_json
from chinese_workflow.common.paths import SCHEMAS, cbeta_xml_path
from chinese_workflow.ingest.lines import build_index
from chinese_workflow.ingest.text import InputText, load_input_text
from chinese_workflow.segment import KINDS, check, run, validate
from chinese_workflow.segment.segment import CLOSERS, main

REPO = Path(__file__).resolve().parents[2]
XML = REPO / "tests" / "fixtures" / "cbeta-xml-p5"
T0262X = XML / "T09n0262-excerpt-p0058b08-p0059b27.xml"
T1723X = XML / "T34n1723-excerpt-p0850a19-p0850b19.xml"


def t1723():
    return load_input_text(T1723X, role="commentary")


def t0262():
    return load_input_text(T0262X, role="root")


def texts(doc: dict, target) -> list:
    return [(s["kind"], target.text[s["char_start"] : s["char_end"]]) for s in doc["sentences"]]


def outlined_text(target, cuts: list, gaps: tuple = ()) -> dict:
    """A synthetic outlined-text/1 over `target`: spans [cuts[i], cuts[i+1]) named n1, n2, …,
    minus the (start, end) ranges in `gaps` (reported as gaps)."""
    spans, k = [], 0
    for a, b in zip(cuts, cuts[1:]):
        if (a, b) in gaps:
            continue
        k += 1
        spans.append({
            "node_id": "n%d" % k, "kind": "leaf", "char_start": a, "char_end": b,
            "linehead_start": target.index.locate(a)[0],
            "linehead_end": target.index.locate(b - 1)[0], "resolution": "explained",
        })
    covered = sum(s["char_end"] - s["char_start"] for s in spans)
    doc = {
        "schema": "outlined-text/1",
        "outline_ref": {"path": "synthetic", "sha256": "0" * 64},
        "target": {
            "text_id": target.text_id, "role": target.role or "root", "sha256": target.sha256,
            "first_linehead": target.first_linehead, "last_linehead": target.last_linehead,
            "length": len(target.text),
        },
        "spans": spans,
        "gaps": [{"char_start": a, "char_end": b, "reason": "synthetic"} for a, b in gaps],
        "coverage": {"start": cuts[0], "end": cuts[-1], "chars": cuts[-1] - cuts[0],
                     "covered": covered, "ratio": covered / (cuts[-1] - cuts[0]),
                     "overlaps": 0},
    }
    jsonschema.Draft202012Validator(
        read_json(SCHEMAS / "outlined-text.schema.json")).validate(doc)
    return doc


def rec(n: str, text: str, **kw) -> dict:
    """A minimal ingest.lines record of a synthetic file X01n0001."""
    r = {"linehead": "X01n0001_p0001a%s" % n, "n": "0001a" + n, "ed": "X", "alt": [], "juan": 1,
         "text": text, "inline_notes": [], "excluded_notes": [], "gaiji": [], "unclear": [],
         "caesuras": [], "mulu": [], "heads": [], "juan_marks": [], "in_verse": False,
         "div_types": []}
    r.update(kw)
    return r


def synthetic(lines: list, role: str | None = None) -> InputText:
    return InputText(text_id="X01n0001", role=role, info={"punctuation": "新式標點"},
                     lines=lines, all_lineheads=[r["linehead"] for r in lines],
                     index=build_index(lines))


# ---------------------------------------------------------------------------- T1723 (commentary)


def test_t1723_lemma_gloss_and_heading():
    t = t1723()
    doc = run(t)
    validate(doc)
    assert check(doc, t) == []
    got = texts(doc, t)
    assert got[0] == ("heading", "陀羅尼品")
    assert got[1] == ("prose", "三門分別：一來意，二釋名，三解妨。")
    kinds = [k for k, _ in got]
    first_lemma = kinds.index("lemma")
    # the 三門分別 introduction precedes every lemma: prose; after the first lemma: gloss
    assert set(kinds[1:first_lemma]) == {"prose"}
    assert set(kinds[first_lemma:]) == {"lemma", "gloss"}
    lemmas = [x for k, x in got if k == "lemma"]
    assert lemmas == [
        "經「爾時藥王至功德甚多」。", "經「爾時藥王至多所饒益」。", "經「爾時勇施至是諸佛已」。",
        "經「爾時毘沙門至無諸衰患」。", "經「爾時持國至是諸佛已」。",
        "經「爾時有羅剎女至如是法師」。", "經「說是陀羅尼至無生法忍」。",
    ]
    # 贊曰： opens the gloss sentence that directly follows every lemma
    for i, k in enumerate(kinds):
        if k == "lemma":
            assert kinds[i + 1] == "gloss" and got[i + 1][1].startswith("贊曰：")
    assert ("gloss", "贊曰：品文分三：初明持經之福，次明神呪之方，後明時眾獲益。") in got
    # a quoted term inside the gloss is not a lemma
    assert ("gloss", "「毘沙門」者此云多聞，四天王中北方之天也，常讚佛法。") in got
    assert doc["punctuation_regime"] == "新式標點" and doc["target"]["role"] == "commentary"
    assert "lemma" in doc["sentence_rule"]


def test_t1723_with_synthetic_outlined_text():
    t = t1723()
    s = t.text
    a20, a29, b03, b12, b14 = (t.offset("T34n1723_p0850%s" % x)
                               for x in ("a20", "a29", "b03", "b12", "b14"))
    mid_gloss = s.index("次明神呪之方")  # inside 贊曰：品文分三：… 後明時眾獲益。
    mid_lemma = s.index("多所饒益")  # inside 經「爾時藥王至多所饒益」。
    cuts = [a20, a29, mid_gloss, b03, mid_lemma, b12, b14, len(s)]
    ot = outlined_text(t, cuts, gaps=((b12, b14),))
    doc = run(t, ot)
    validate(doc)
    assert check(doc, t, ot) == []
    sents = doc["sentences"]
    # coverage starts at the first placed span (the heading line before it is not segmented)
    assert sents[0]["char_start"] == a20 and sents[-1]["char_end"] == len(s)
    for x in sents:
        assert not any(x["char_start"] < c < x["char_end"] for c in cuts), x
    got = [(x["node_id"], x["kind"], s[x["char_start"] : x["char_end"]]) for x in sents]
    assert ("n2", "gloss", "贊曰：品文分三：初明持經之福，") in got
    assert ("n3", "gloss", "次明神呪之方，後明時眾獲益。") in got
    # a boundary inside a lemma splits it; both halves stay lemma
    assert ("n4", "lemma", "經「爾時藥王至") in got and ("n5", "lemma", "多所饒益」。") in got
    # the gap holds sentences too, with node_id null
    gap = [x for x in sents if b12 <= x["char_start"] < b14]
    assert gap and all(x["node_id"] is None for x in gap)
    assert {x["node_id"] for x in sents} == {"n1", "n2", "n3", "n4", "n5", "n6", None}
    assert {x["kind"] for x in sents} == {"prose", "lemma", "gloss"}


def test_strategy_1_is_punctuation_only_but_keeps_span_boundaries():
    t = t1723()
    doc = run(t, strategy=1)
    validate(doc)
    assert check(doc, t) == []
    got = texts(doc, t)
    assert {k for k, _ in got} == {"prose"}
    # no heading break: the 品 title runs into the first sentence
    assert got[0][1] == "陀羅尼品三門分別：一來意，二釋名，三解妨。"
    assert ("prose", "經「爾時藥王至功德甚多」。") in got
    a29 = t.offset("T34n1723_p0850a29")
    mid = t.text.index("次明神呪之方")
    ot = outlined_text(t, [0, a29, mid, len(t.text)])
    doc = run(t, ot, strategy=1)
    assert check(doc, t, ot) == []
    assert doc["strategy"] == 1 and doc["sentence_rule"].startswith("strategy 1")


# ------------------------------------------------------------------------------------ T0262 (root)


def test_t0262_heading_and_verse_lines():
    t = t0262()
    doc = run(t)
    validate(doc)
    assert check(doc, t) == []
    got = texts(doc, t)
    assert got[0] == ("heading", "妙法蓮華經陀羅尼品第二十六")
    assert {k for k, _ in got} == {"heading", "prose", "verse_line"}  # a root: no lemma/gloss
    verse = [x for k, x in got if k == "verse_line"]
    # the gāthā 0059b12–b16 (lg/l with a caesura in every line): one unit per pāda
    assert verse == [
        "「若不順我呪，", "惱亂說法者，", "頭破作七分，", "如阿梨樹枝。", "如殺父母罪，",
        "亦如壓油殃，", "斗秤欺誑人，", "調達破僧罪。", "犯此法師者，", "當獲如是殃。」",
    ]
    i = [k for k, _ in got].index("verse_line")
    assert got[i - 1] == ("prose", "即於佛前而說偈言：")
    assert got[i + 10] == ("prose", "諸羅剎女說此偈已，白佛言：「世尊！")
    # the dhāraṇīs are prose paragraphs in CBETA (p, U+3000 between items, no lg): not verse
    assert all("安爾" not in x for x in verse)
    assert any(k == "prose" and x.startswith("即說呪曰：「安爾一　曼爾二") for k, x in got)
    # a closing quote stays with its terminator
    assert ("prose", "「甚多，世尊。」") in got


@pytest.mark.parametrize("load", [t0262, t1723], ids=["T0262", "T1723"])
@pytest.mark.parametrize("strategy", [1, 2])
def test_contract_and_determinism(load, strategy):
    t = load()
    a, b = run(t, strategy=strategy), run(load(), strategy=strategy)
    assert json.dumps(a, ensure_ascii=False) == json.dumps(b, ensure_ascii=False)
    validate(a)
    assert check(a, t) == []
    n = len(a["sentences"])
    assert [x["id"] for x in a["sentences"]] == ["s%d" % (i + 1) for i in range(n)]
    assert a["target"]["sha256"] == t.sha256 and a["target"]["length"] == len(t.text)
    assert {x["kind"] for x in a["sentences"]} <= set(KINDS)
    for x in a["sentences"]:
        piece = t.text[x["char_start"] : x["char_end"]]
        assert piece[0] not in CLOSERS, x  # closers stay with the sentence they close
        assert piece.strip("　 "), x


def test_outlined_text_of_another_text_is_refused():
    t = t0262()
    ot = outlined_text(t1723(), [0, 10])
    with pytest.raises(ValueError):
        run(t, ot)


def test_strategy_must_be_1_or_2():
    with pytest.raises(ValueError):
        run(t0262(), strategy=3)


# ---------------------------------------------------------------------------- synthetic records


def test_punctuation_only_pieces_merge():
    lines = [rec("01", "序品", heads=[{"kind": "head", "text": "序品", "offset": 0}]),
             rec("02", "。如是我聞。一時佛住。")]
    t = synthetic(lines)
    # strategy 2: the stray 。 after the heading joins the heading
    assert texts(run(t), t) == [("heading", "序品。"), ("prose", "如是我聞。"),
                                ("prose", "一時佛住。")]
    # a span boundary between heading and 。: it joins the next sentence instead
    ot = outlined_text(t, [0, 2, len(t.text)])
    doc = run(t, ot)
    assert check(doc, t, ot) == []
    assert texts(doc, t) == [
        ("heading", "序品"), ("prose", "。如是我聞。"), ("prose", "一時佛住。"),
    ]
    assert [x["node_id"] for x in doc["sentences"]] == ["n1", "n2", "n2"]


def test_mulu_line_is_a_heading_and_mulu_positions_break():
    lines = [rec("01", "陀羅尼品", mulu=[{"level": 1, "type": "品", "n": "26",
                                          "text": "26 陀羅尼品", "offset": 0,
                                          "div_type": "pin"}]),
             rec("02", "唐沙門某述"),
             rec("03", "初序分", mulu=[{"level": 2, "type": "科判", "n": None,
                                       "text": "初序分二", "offset": 0, "div_type": None}]),
             rec("04", "。次正宗。")]
    t = synthetic(lines)
    assert texts(run(t), t) == [("heading", "陀羅尼品"), ("prose", "唐沙門某述"),
                                ("prose", "初序分。"), ("prose", "次正宗。")]
    # strategy 1 has neither break
    assert texts(run(t, strategy=1), t) == [("prose", "陀羅尼品唐沙門某述初序分。"),
                                            ("prose", "次正宗。")]


def test_lemma_forms():
    lines = [rec("01", "經「爾時世尊。從三昧起」。贊曰：此明起定。如經「佛告」說。"),
             rec("02", "經「如是我聞」贊曰：信成就也。經「一時」者，謂說經時。"),
             rec("03", "述曰：此釋時也。")]
    t = synthetic(lines, role="commentary")
    got = texts(run(t), t)
    assert got == [
        ("lemma", "經「爾時世尊。從三昧起」。"),  # one lemma whatever the quote holds
        ("gloss", "贊曰：此明起定。"),
        ("gloss", "如經「佛告」說。"),  # a citation inside the gloss
        ("lemma", "經「如是我聞」"),  # no 。, but a gloss marker follows
        ("gloss", "贊曰：信成就也。"),
        ("gloss", "經「一時」者，謂說經時。"),  # 「…」者 is not taken as a lemma
        ("gloss", "述曰：此釋時也。"),
    ]
    # the same text as a root: no lemma/gloss at all
    t.role = None
    assert {k for k, _ in texts(run(t), t)} == {"prose"}


def test_verse_split_at_ideographic_space_runs():
    lines = [rec("01", "　諸法從緣生　諸法從緣滅", in_verse=True),
             rec("02", "我佛大沙門，常作如是說。", in_verse=True, caesuras=[6]),
             rec("03", "此偈明緣起。")]
    t = synthetic(lines)
    assert texts(run(t), t) == [
        ("verse_line", "　諸法從緣生　"), ("verse_line", "諸法從緣滅"),
        ("verse_line", "我佛大沙門，"), ("verse_line", "常作如是說。"),
        ("prose", "此偈明緣起。"),
    ]


# -------------------------------------------------------------------------------------------- CLI


def test_cli_in_process(tmp_path, capsys):
    t = t1723()
    ot = outlined_text(t, [t.offset("T34n1723_p0850a20"), t.offset("T34n1723_p0850a29"),
                           len(t.text)])
    write_json(ot, tmp_path / "outlined-text.json")
    out = tmp_path / "sentences.json"
    assert main(["--target", str(T1723X), "--outlined-text", str(tmp_path / "outlined-text.json"),
                 "--out", str(out)]) == 0
    assert "sentences" in capsys.readouterr().out
    doc = read_json(out)
    validate(doc)
    assert doc["target"]["role"] == "commentary"  # taken from the outlined-text
    assert doc["target"]["sha256"] == sha256_text(t.text)
    assert check(doc, t, ot) == []
    assert {x["node_id"] for x in doc["sentences"]} == {"n1", "n2"}


def test_python_m_entrypoint(tmp_path):
    env = dict(os.environ)
    src = str(REPO / "pipeline" / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    out = tmp_path / "s.json"
    proc = subprocess.run(
        [sys.executable, "-W", "error::RuntimeWarning", "-m", "chinese_workflow.segment",
         "--target", str(T0262X), "--span", "T09n0262_p0059b11..T09n0262_p0059b17",
         "--strategy", "2", "--out", str(out)],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    doc = read_json(out)
    # 惱。」 | 即於佛前而說偈言： | 10 pādas | 諸羅剎女說此偈已，白佛言：「世尊！ | 我等亦
    assert [x["kind"] for x in doc["sentences"]] == ["prose"] * 2 + ["verse_line"] * 10 + [
        "prose"] * 2
    assert doc["target"]["first_linehead"] == "T09n0262_p0059b11"


# ------------------------------------------------------------------------------------- raw-gated


def test_t0262_whole_file():
    path = cbeta_xml_path("T09n0262")
    if path is None:
        pytest.skip("data/raw/cbeta/T09n0262.xml not fetched (scripts/fetch_cbeta.sh)")
    t = load_input_text(path, role="root")
    doc = run(t)
    validate(doc)
    assert check(doc, t) == []
    s = t.text
    verse_chars = {i for k, r in enumerate(t.lines) if r["in_verse"]
                   for i in range(t.index.starts[k], t.index.starts[k] + t.index.lengths[k])}
    heads = {h["text"] for r in t.lines for h in r["heads"]}
    for x in doc["sentences"]:
        if x["kind"] == "verse_line":
            assert x["char_start"] in verse_chars, x
        if x["kind"] == "heading":
            assert s[x["char_start"] : x["char_end"]].rstrip("　 ") in heads, x
    n_heads = sum(len(r["heads"]) for r in t.lines)
    assert sum(1 for x in doc["sentences"] if x["kind"] == "heading") == n_heads
    assert sum(1 for x in doc["sentences"] if x["kind"] == "verse_line") > 1000


def test_t1666_opening_verse():
    path = cbeta_xml_path("T32n1666")
    if path is None:
        pytest.skip("T32n1666.xml not fetched (scripts/fetch_cbeta.sh T32n1666)")
    t = load_input_text(path, role="root")
    got = texts(run(t), t)
    verse = [x for k, x in got if k == "verse_line"]
    assert verse[:4] == ["歸命盡十方，", "最勝業遍知，", "色無礙自在，", "救世大悲者，"]
