"""eval.chunk_invariants: the report passes on the chunk stage's output and fails on tampering.

Inputs are the synthetic outline / outlined-text / sentences of tests/unit/test_chunk.py (built over
the T1723 dev excerpt and the T0262 陀羅尼品 excerpt).
"""

from __future__ import annotations

import copy

import pytest
from test_chunk import (
    T0262,
    commentary_inputs,
    outlined_text,
    root_outline,
    sentences_for,
)

from chinese_workflow.chunk import chunker, render
from chinese_workflow.common import jsonio
from chinese_workflow.eval import chunk_invariants as inv
from chinese_workflow.ingest.text import load_input_text


@pytest.fixture(scope="module")
def case():
    doc, ot, sents, t = commentary_inputs()
    return doc, ot, sents, chunker.build_chunks(doc, ot, sents, t)


def _failing(report) -> set:
    return {k for k, v in report["invariants"].items() if not v["ok"]}


def test_all_invariants_pass(case):
    doc, ot, sents, ch = case
    rep = inv.check(ch, ot, sents, doc, md=render.render_md(ch))
    assert rep["ok"], {k: v["violations"][:3] for k, v in rep["invariants"].items() if not v["ok"]}
    assert set(rep["invariants"]) == set(inv.INVARIANTS)
    assert rep["invariants"]["md_round_trip"]["source"] == "chunks.md"
    st = rep["stats"]
    assert st["chunks"] == len(ch["chunks"]) and st["over_cap"] == 0 and st["over_budget"] == 0
    assert st["fallback"] == {"none": 5, "unoutlined": 0, "split-leaf": 4}
    assert st["median_sentences"] == 5 and st["median_chars"] == 70


def test_passes_without_outline_and_md(case):
    doc, ot, sents, ch = case
    rep = inv.check(ch, ot, sents)
    assert rep["ok"], _failing(rep)
    assert rep["invariants"]["nodes_exist"]["checked_against"] == "outlined-text ids"
    assert rep["invariants"]["md_round_trip"]["source"] == "re-rendered"


def test_passes_on_root_target_and_gap():
    t = load_input_text(T0262, role="root")
    doc = root_outline(t)
    ot = outlined_text(doc, t, role="root")
    sents = sentences_for(ot, t)
    ch = chunker.build_chunks(doc, ot, sents, t)
    assert inv.check(ch, ot, sents, doc)["ok"]
    doc, ot, sents, t = commentary_inputs(drop=("1_1.2_2.2_3",))
    ch = chunker.build_chunks(doc, ot, sents, t, sentence_cap=3, size_chars=None)
    rep = inv.check(ch, ot, sents, doc)
    assert rep["ok"], _failing(rep)
    assert rep["stats"]["fallback"]["unoutlined"] >= 2


def test_independent_md_writer_matches_the_renderer(case):
    ch = case[3]
    assert inv.render_md_independent(ch) == render.render_md(ch)


def _tampered(case, edit):
    doc, ot, sents, ch = case
    ch = copy.deepcopy(ch)
    edit(ch)
    return inv.check(ch, ot, sents, doc)


def test_tampered_text_fails_coverage(case):
    def edit(ch):
        c = ch["chunks"][2]
        c["text"] = "問" + c["text"][1:]

    rep = _tampered(case, edit)
    assert not rep["ok"] and "coverage" in _failing(rep)
    assert any("sha256" in v for v in rep["invariants"]["coverage"]["violations"])


def test_moved_boundary_fails_leaf_split_and_sentences(case):
    doc, ot, sents, ch = case

    def edit(ch):
        # move the c2 / c3 boundary 5 characters into the 解妨 leaf
        a, b = ch["chunks"][1], ch["chunks"][2]
        a["char_end"] += 5
        b["char_start"] += 5
        a["text"], b["text"] = a["text"] + b["text"][:5], b["text"][5:]
        a["n_chars"] += 5
        b["n_chars"] -= 5

    rep = _tampered(case, edit)
    failing = _failing(rep)
    assert {"no_sub_leaf_split", "sentence_alignment"} <= failing
    assert "coverage" not in failing  # still a tiling of the same text


def test_merge_across_parents_fails(case):
    def edit(ch):
        # fold the 解妨 chunk (parent 三門分別) into the next chunk (品文分三's units)
        a, b = ch["chunks"][2], ch["chunks"][3]
        b["char_start"], b["text"] = a["char_start"], a["text"] + b["text"]
        b["n_chars"] += a["n_chars"]
        b["leaf_ids"] = a["leaf_ids"] + b["leaf_ids"]
        b["sentence_ids"] = a["sentence_ids"] + b["sentence_ids"]
        b["n_sentences"] = len(b["sentence_ids"])
        b["loc_start"] = a["loc_start"]
        n = len(ch["chunks"])
        del ch["chunks"][2]
        remap = {"c%d" % k: "c%d" % (k - 1 if k > 3 else k) for k in range(1, n + 1)}
        for c in ch["chunks"]:
            c["chunk_id"] = remap[c["chunk_id"]]
        for m in ch["markers"]:
            m["before_chunk"] = remap[m["before_chunk"]]
        for x in ch["announcements"]:
            x["after_chunk"] = remap[x["after_chunk"]]

    rep = _tampered(case, edit)
    failing = _failing(rep)
    assert "merge_within_parent" in failing and "size_cap" in failing


def test_over_cap_fails_size(case):
    doc, ot, sents, ch = case
    ch = copy.deepcopy(ch)
    ch["metadata"]["size_budget"] = {"sentence_cap": 4, "chars": 60}
    rep = inv.check(ch, ot, sents, doc)
    viol = rep["invariants"]["size_cap"]["violations"]
    assert not rep["ok"] and any("sentences > cap 4" in v for v in viol)
    assert any("characters > budget 60" in v for v in viol)
    assert rep["stats"]["over_cap"] >= 1


def test_marker_faults_fail(case):
    rep = _tampered(case, lambda ch: ch["markers"].pop(3))
    assert "markers_taken_up" in _failing(rep)
    assert "md_round_trip" not in _failing(rep)  # the json is still representable

    def misplace(ch):
        ch["markers"][0]["before_chunk"] = "c2"

    rep = _tampered(case, misplace)
    assert "markers_taken_up" in _failing(rep)

    def wrong_locator(ch):
        m = next(m for m in ch["markers"] if m["node_id"] == "1_1.1_2.1_3")
        m["locator"] = "T34n1723_p0850a21"  # explained line instead of the announced one

    assert "markers_taken_up" in _failing(_tampered(case, wrong_locator))

    def ghost(ch):
        ch["announcements"][0]["node_id"] = "9_1"

    assert "nodes_exist" in _failing(_tampered(case, ghost))


def test_locator_faults_fail(case):
    def backwards(ch):
        ch["chunks"][4]["loc_start"] = "T34n1723_p0850a20"

    rep = _tampered(case, backwards)
    assert "monotone_locators" in _failing(rep)

    def not_a_ref(ch):
        ch["chunks"][0]["loc_end"] = "a19"

    assert "monotone_locators" in _failing(_tampered(case, not_a_ref))


def test_md_mismatch_fails(case):
    doc, ot, sents, ch = case
    md = render.render_md(ch).replace("1₁1₂3₃) 解妨\n", "", 1)
    rep = inv.check(ch, ot, sents, doc, md=md)
    assert _failing(rep) == {"md_round_trip"}


def test_cli(case, tmp_path, capsys):
    doc, ot, sents, ch = case
    paths = {name: jsonio.write_json(obj, tmp_path / name) for name, obj in (
        ("chunks.json", ch), ("outlined-text.json", ot), ("sentences.json", sents),
        ("outline.json", doc))}
    (tmp_path / "chunks.md").write_text(render.render_md(ch), encoding="utf-8")
    args = [str(paths["chunks.json"]), str(paths["outlined-text.json"]),
            str(paths["sentences.json"]), "--outline", str(paths["outline.json"])]
    assert inv.main(args) == 0
    out = capsys.readouterr().out
    assert '"ok": true' in out and '"source": "chunks.md"' in out
    (tmp_path / "chunks.md").write_text("[1₁) 孤]\n", encoding="utf-8")
    assert inv.main(args) == 1
