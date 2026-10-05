"""Tests for chinese_workflow.ingest.structure and chinese_workflow.ingest.run (M1a, design §4).

Always run: the committed fixtures tests/fixtures/cbeta-xml-p5/ (G069n1977 whole file, the T0262
陀羅尼品 excerpt, the T1723 excerpt = the T1723 dev span) and tests/fixtures/cbeta-api/
works-toc-T0262.json. Run when present, skip otherwise: data/raw/cbeta/T09n0262.xml (whole file,
scripts/fetch_cbeta.sh).

Expected values were read off the fixture XML: the caesuras of the 陀羅尼品 gāthā (0059b12–b16),
its five g (charDecl unicode mappings), the 至 inline notes of the T1723 lemmas.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from lxml import etree

from chinese_workflow.common.jsonio import read_json, read_jsonl, sha256_file
from chinese_workflow.common.paths import cbeta_xml_path
from chinese_workflow.common.splits import SplitGuard, SplitViolation
from chinese_workflow.ingest.run import main, parse_span, run
from chinese_workflow.ingest.structure import (
    ELEMENT_KINDS,
    build_structure,
    element_counts,
    normalization_config,
    verse_runs,
)
from chinese_workflow.ingest.text import load_input_text

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures"
XML = FIX / "cbeta-xml-p5"
G1977 = XML / "G069n1977.xml"
T0262X = XML / "T09n0262-excerpt-p0058b08-p0059b27.xml"
T1723X = XML / "T34n1723-excerpt-p0850a19-p0850b19.xml"
TOC_T0262 = FIX / "cbeta-api" / "works-toc-T0262.json"

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
ROLES = {G1977: "commentary", T0262X: "root", T1723X: "commentary"}


def unicode_map(path: Path) -> dict:
    """{charDecl id: mapped character} from the file's header (mapping type unicode)."""
    root = etree.parse(str(path)).getroot()
    out = {}
    for ch in root.iter(TEI + "char"):
        for m in ch.iter(TEI + "mapping"):
            if m.get("type") == "unicode":
                out[ch.get(XML_ID)] = chr(int(m.text.strip()[2:], 16))
    return out


def check_structure(text, st: dict) -> None:
    """The contract every structure/1 dict meets, checked against the InputText it came from."""
    idx, s = text.index, text.text
    assert st["schema"] == "structure/1" and st["cbeta_release"] == "2026R2"
    assert st["sha256"] == text.sha256 and st["length"] == len(s)
    assert st["span"] == {"first": text.first_linehead, "last": text.last_linehead}
    assert [(ln["linehead"], ln["start"], ln["length"], ln["juan"]) for ln in st["lines"]] == [
        (lh, a, n, rec["juan"])
        for lh, a, n, rec in zip(idx.lineheads, idx.starts, idx.lengths, text.lines)
    ]
    els = st["elements"]
    assert {e["kind"] for e in els} <= set(ELEMENT_KINDS)
    # global offsets: exactly the index's, in document order
    for e in els:
        assert e["char_start"] == idx.global_offset(e["linehead"], e["offset"])
    assert [e["char_start"] for e in els] == sorted(e["char_start"] for e in els)
    # every mark of the line records is reported once
    recs = text.lines
    want = {
        "juan": sum(len(r["juan_marks"]) for r in recs),
        "mulu": sum(len(r["mulu"]) for r in recs),
        "head": sum(1 for r in recs for h in r["heads"] if h["kind"] == "head"),
        "jhead": sum(1 for r in recs for h in r["heads"] if h["kind"] == "jhead"),
        "verse": len(verse_runs(recs)),
        "note": sum(len(r["inline_notes"]) + len(r["excluded_notes"]) for r in recs),
        "caesura": sum(len(r["caesuras"]) for r in recs),
        "gaiji": sum(len(r["gaiji"]) for r in recs),
        "unclear": sum(len(r["unclear"]) for r in recs),
    }
    assert element_counts(st) == {k: v for k, v in want.items() if v}
    # the character at each position is what the element says it is (assertion messages carry
    # the element only, never the text)
    for e in els:
        k, cs, a = e["kind"], e["char_start"], e["attrs"]
        rec = text.record(e["linehead"])
        if k in ("head", "jhead"):
            assert s[cs : cs + len(a["text"])] == a["text"], e
        elif k == "note" and a["in_text"]:
            assert a["length"] > 0 and cs + a["length"] <= len(s), e
            assert (e["offset"], e["offset"] + a["length"]) in map(tuple, rec["inline_notes"]), e
        elif k == "caesura":
            # inside a verse line, between two non-empty pieces of it
            assert rec["in_verse"] and 0 < e["offset"] < len(rec["text"]), e
        elif k == "verse":
            i = idx.lineheads.index(e["linehead"])
            j = idx.lineheads.index(a["linehead_end"])
            assert a["lines"] == j - i + 1 and a["char_end"] == idx.starts[j] + idx.lengths[j], e
            assert all(r["in_verse"] for r in recs[i : j + 1]), e
        elif k == "unclear":
            assert s[cs : cs + 3] == "[?]", e


@pytest.mark.parametrize("path", [G1977, T0262X, T1723X], ids=lambda p: p.stem[:8])
def test_structure_contract_on_fixtures(path):
    text = load_input_text(path, role=ROLES[path])
    st = build_structure(text)
    check_structure(text, st)
    assert st["text_id"] == text.text_id and st["role"] == ROLES[path]
    assert st["source"] == str(path.relative_to(REPO))


def test_t0262_excerpt_elements():
    text = load_input_text(T0262X, role="root")
    st = build_structure(text)
    s = text.text
    assert element_counts(st) == {
        "mulu": 1, "head": 1, "verse": 1, "note": 103, "caesura": 5, "gaiji": 5,
    }
    by = {}
    for e in st["elements"]:
        by.setdefault(e["kind"], []).append(e)
    (mulu,) = by["mulu"]
    assert mulu["linehead"] == "T09n0262_p0058b08" and mulu["char_start"] == 0
    assert mulu["attrs"] == {
        "level": 1, "type": "品", "n": "26", "text": "26 陀羅尼品", "div_type": "pin",
    }
    assert by["head"][0]["attrs"]["text"] == "妙法蓮華經陀羅尼品第二十六"
    # the gāthā 0059b12–b16: one verse group, a caesura between the two pādas of every line
    (verse,) = by["verse"]
    assert verse["linehead"] == "T09n0262_p0059b12"
    assert verse["attrs"]["linehead_end"] == "T09n0262_p0059b16" and verse["attrs"]["lines"] == 5
    assert s[verse["char_start"] : verse["attrs"]["char_end"]].startswith("「若不順我呪，")
    assert s[verse["char_start"] : verse["attrs"]["char_end"]].endswith("當獲如是殃。」")
    assert [s[e["char_start"] - 1 : e["char_start"] + 1] for e in by["caesura"]] == [
        "，惱", "，如", "，亦", "，調", "，當",
    ]
    # gaiji: the character at char_start is the charDecl unicode mapping of its ref
    cmap = unicode_map(T0262X)
    assert [(e["attrs"]["via"], s[e["char_start"]] == cmap[e["attrs"]["ref"]])
            for e in by["gaiji"]] == [("unicode", True)] * 5
    assert s[by["gaiji"][0]["char_start"]] == "䭾"  # 0058b27 佛䭾, CB00501
    # inline notes: the dhāraṇī numbers and fanqie glosses are small print kept in the text
    notes = [(e["linehead"][-7:], s[e["char_start"] : e["char_start"] + e["attrs"]["length"]])
             for e in by["note"]]
    assert notes[:5] == [("0058b19", x) for x in "一二三四五"]
    assert ("0058b20", "羊鳴音") in notes


def test_t1723_excerpt_elements():
    text = load_input_text(T1723X, role="commentary")
    st = build_structure(text)
    s = text.text
    assert element_counts(st) == {"mulu": 1, "head": 1, "note": 7}
    mulu = next(e for e in st["elements"] if e["kind"] == "mulu")
    assert (mulu["attrs"]["type"], mulu["attrs"]["level"], mulu["attrs"]["text"]) == (
        "品", 1, "陀羅尼品",
    )
    # the 至 of every lemma 經「A至B」 is an inline note
    notes = [e for e in st["elements"] if e["kind"] == "note"]
    assert all(e["attrs"]["in_text"] and e["attrs"]["length"] == 1 for e in notes)
    assert "".join(s[e["char_start"]] for e in notes) == "至" * 7
    assert all(s.rfind("經「", 0, e["char_start"]) > s.rfind("」", 0, e["char_start"])
               for e in notes)


def test_g1977_juan_marks_and_kepan_mulu():
    text = load_input_text(G1977, role="commentary")
    st = build_structure(text)
    s = text.text
    assert element_counts(st) == {"juan": 2, "mulu": 16, "jhead": 2, "note": 1}
    juan = [(e["linehead"], e["attrs"]["fun"]) for e in st["elements"] if e["kind"] == "juan"]
    assert juan == [("G069n1977_p0717a01", "open"), ("G069n1977_p0718a06", "close")]
    kinds_a01 = [e["kind"] for e in st["elements"] if e["linehead"] == "G069n1977_p0717a01"]
    assert kinds_a01 == ["juan", "mulu", "mulu", "mulu", "mulu", "jhead"]
    kepan = [e for e in st["elements"] if e["kind"] == "mulu" and e["attrs"]["type"] == "科判"]
    assert len(kepan) == 15 and kepan[0]["attrs"]["text"] == "心要分二"
    assert all(s[e["char_start"] :].startswith(text.record(e["linehead"])["text"])
               for e in kepan)  # every 科判 node of this file starts a line
    note = next(e for e in st["elements"] if e["kind"] == "note")
    assert s[note["char_start"]] == "竟"


def test_normalization_config():
    cfg = normalization_config(load_input_text(T0262X, role="root"))
    assert cfg["regime"] == "none" and cfg["text_id"] == "T09n0262"
    assert cfg["punctuation"] == "新式標點" and cfg["punctuation_resp"] == "CBETA"
    assert cfg["gaiji_routes"] == {"unicode": 5} and cfg["excluded_notes"] == 0
    assert "inline" in cfg["notes_policy"]
    g = normalization_config(load_input_text(G1977))
    assert g["punctuation"] == "原書標點" and g["gaiji_routes"] == {}


# ------------------------------------------------------------------------------------ run / CLI


def test_run_writes_the_four_files(tmp_path):
    res = run(T0262X, role="root", out_dir=tmp_path)
    text = load_input_text(T0262X, role="root")
    p = {k: Path(v) for k, v in res["paths"].items()}
    assert sorted(x.name for x in tmp_path.iterdir()) == [
        "T09n0262.lines.jsonl", "T09n0262.structure.json", "T09n0262.txt",
        "normalization.config.json",
    ]
    # the txt reproduces InputText.text byte for byte (no separator, no trailing newline)
    assert p["text"].read_bytes() == text.text.encode("utf-8")
    assert sha256_file(p["text"]) == text.sha256 == res["sha256"]
    assert read_jsonl(p["lines"]) == json.loads(json.dumps(text.lines))
    st = read_json(p["structure"])
    assert st == json.loads(json.dumps(build_structure(text)))
    check_structure(text, st)
    assert read_json(p["normalization"]) == normalization_config(text)
    assert res["counts"] == {
        "lines": 92, "chars": len(text.text), "excluded_notes": 0, "gaiji": 5,
        "elements": {"mulu": 1, "head": 1, "verse": 1, "note": 103, "caesura": 5, "gaiji": 5},
    }
    assert res["split_guard"][0]["splits"] == ["unsplit"]


def test_run_span_is_self_contained(tmp_path):
    span = ("T09n0262_p0059b12", "T09n0262_p0059b16")
    res = run(T0262X, role="root", out_dir=tmp_path, span=span)
    st = read_json(res["paths"]["structure"])
    txt = Path(res["paths"]["text"]).read_text(encoding="utf-8")
    assert st["span"] == {"first": span[0], "last": span[1]}
    assert [ln["linehead"][-7:] for ln in st["lines"]] == ["0059b1%d" % i for i in range(2, 7)]
    assert txt.startswith("「若不順我呪，") and len(txt) == st["length"] == 62
    assert element_counts(st) == {"verse": 1, "caesura": 5}
    assert st["elements"][0]["char_start"] == 0
    assert [txt[e["char_start"]] for e in st["elements"] if e["kind"] == "caesura"] == list(
        "惱如亦調當"
    )


def test_run_is_deterministic(tmp_path):
    a = run(T1723X, role="commentary", out_dir=tmp_path / "a")
    b = run(T1723X, role="commentary", out_dir=tmp_path / "b")
    for k in a["paths"]:
        assert Path(a["paths"][k]).read_bytes() == Path(b["paths"][k]).read_bytes()


def test_run_rejects_bad_role(tmp_path):
    with pytest.raises(ValueError):
        run(T0262X, role="sutra", out_dir=tmp_path)


def test_split_guard(tmp_path):
    # the T1723 excerpt is exactly the dev span: allowed, and recorded
    res = run(T1723X, role="commentary", out_dir=tmp_path / "dev")
    assert res["split_guard"][0]["splits"] == ["dev"]
    # the same lines declared test by a registry: refused before anything is written
    registry = {
        "splits": {"texts": {"T1723": {"file": "T34n1723", "unlisted": "reserve", "spans": [
            {"split": "test", "start": "T34n1723_p0850a19", "end": "T34n1723_p0850b20"}]}}},
        "datasets": [],
    }
    with pytest.raises(SplitViolation):
        run(T1723X, role="commentary", out_dir=tmp_path / "test",
            guard=SplitGuard(registry=registry))
    assert not (tmp_path / "test").exists()
    frozen = SplitGuard(frozen="v1", registry=registry)
    run(T1723X, role="commentary", out_dir=tmp_path / "frozen", guard=frozen)
    assert frozen.report[0]["splits"] == ["test"] and frozen.report[0]["frozen"] == "v1"


def test_parse_span():
    assert parse_span(None) is None and parse_span("") is None
    assert parse_span("T09n0262_p0059b12..T09n0262_p0059b16") == (
        "T09n0262_p0059b12", "T09n0262_p0059b16",
    )
    with pytest.raises(ValueError):
        parse_span("T09n0262_p0059b12")


def test_cli_in_process(tmp_path, capsys):
    assert main(["run", str(G1977), "--role", "commentary", "--out", str(tmp_path),
                 "--span", "G069n1977_p0717a03..G069n1977_p0717a04"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["counts"]["lines"] == 2
    assert Path(res["paths"]["text"]).read_text(encoding="utf-8").startswith("夫三諦者。")
    # 'lines' forwards to the line extractor CLI
    assert main(["lines", str(G1977), "--tsv"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "G069n1977_p0717a01\t1\t始終心要"


def test_python_m_entrypoint(tmp_path):
    env = dict(os.environ)
    src = str(REPO / "pipeline" / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(
        [sys.executable, "-W", "error::RuntimeWarning", "-m", "chinese_workflow.ingest", "run",
         str(T0262X), "--role", "root", "--out", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["counts"]["lines"] == 92
    assert (tmp_path / "T09n0262.structure.json").exists()


# --------------------------------------------------------------------------- raw-gated: T09n0262


def test_t0262_whole_file_mulu_against_works_toc(tmp_path):
    path = cbeta_xml_path("T09n0262")
    if path is None:
        pytest.skip("data/raw/cbeta/T09n0262.xml not fetched (scripts/fetch_cbeta.sh)")
    res = run(path, role="root", out_dir=tmp_path)
    st = read_json(res["paths"]["structure"])
    text = load_input_text(path, role="root")
    check_structure(text, st)
    mulu = [e for e in st["elements"] if e["kind"] == "mulu"]
    juan = [e for e in mulu if e["attrs"]["type"] == "卷"]
    nodes = [e for e in mulu if e["attrs"]["type"] != "卷"]
    assert len(juan) == 7
    assert sorted(
        {lv: sum(1 for e in nodes if e["attrs"]["level"] == lv)
         for lv in {e["attrs"]["level"] for e in nodes}}.items()
    ) == [(1, 32), (2, 1)]
    toc = json.loads(TOC_T0262.read_text(encoding="utf-8"))["results"][0]
    want = []

    def walk(ns, depth):
        for n in ns:
            want.append((n["title"], n["lb"], depth, n["type"]))
            walk(n.get("children") or [], depth + 1)

    walk(toc["mulu"], 1)
    got = [(e["attrs"]["text"], e["linehead"].split("_p")[1], e["attrs"]["level"],
            e["attrs"]["type"]) for e in nodes]
    assert got == want
    assert [e["linehead"].split("_p")[1] for e in juan] == [j["lb"] for j in toc["juan"]]
    # each 品 node sits where its printed heading starts
    heads = {e["char_start"] for e in st["elements"] if e["kind"] == "head"}
    assert all(e["char_start"] in heads for e in nodes if e["attrs"]["type"] == "品")
