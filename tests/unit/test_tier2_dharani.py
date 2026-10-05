"""Tier 2 on the T1723 陀羅尼品 dev excerpt against the Kuiji gold's 陀羅尼品 subtree.

Input : tests/fixtures/cbeta-xml-p5/T34n1723-excerpt-p0850a19-p0850b19.xml (the dev span, committed) and
        data/reference-outlines/T0262/kuiji-xuanzan/outline.json, read ONLY through a filter that keeps
        the nodes whose commentary.explained lies in T34n1723_p0850a19..p0850b19 (the dev subtree, 45
        nodes with the 品 itself; data/EVAL-SETS.md "Do not open while developing"). Nothing outside
        that subtree is printed or compared.
Method: the drafts are numbered under a stub 品 node (common.outline_doc.build_prediction) and matched
        to the gold subtree top-down by (explained line without offset, depth below the 品, parent):
        children of a matched pair match when their explained lines are equal, one to one, greedily by
        sibling-index difference (the scorer's rule at t = 0, docs/outliner-design.md §9).

Achieved on 2026-09-27 (Claude Opus 5.5), which the asserts below hold: 44 predicted nodes below the 品,
44 gold nodes; 44 matched: precision 1.00, recall 1.00; the ordinal-keeping headings
(heading_style='source') equal the gold's headings on 44/44 matched nodes; child_count_announced
equal on 44/44; no parser-report entry; one rejected list (總持有四, inside a question).
The gold is a Claude-drafted, unreviewed gold (gold_status draft-unreviewed): no headline score.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chinese_workflow.common.lineheads import strip_offset
from chinese_workflow.common.outline_doc import build_prediction, children_map, validate
from chinese_workflow.ingest.text import load_input_text
from chinese_workflow.outline.tier2 import parse

REPO = Path(__file__).resolve().parents[2]
EXCERPT = REPO / "tests" / "fixtures" / "cbeta-xml-p5" / "T34n1723-excerpt-p0850a19-p0850b19.xml"
GOLD = REPO / "data" / "reference-outlines" / "T0262" / "kuiji-xuanzan" / "outline.json"
DEV_FIRST, DEV_LAST = "T34n1723_p0850a19", "T34n1723_p0850b19"
ANCHOR = {"anchor": DEV_FIRST, "heading_src": "陀羅尼品", "part_type": "品"}


def _explained(n: dict) -> str | None:
    return strip_offset(((n.get("locations") or {}).get("commentary") or {}).get("explained"))


def gold_dev_subtree() -> list:
    """The gold nodes explained inside the dev span (and nothing else)."""
    doc = json.loads(GOLD.read_text(encoding="utf-8"))
    return [n for n in doc["nodes"]
            if _explained(n) is not None and DEV_FIRST <= _explained(n) <= DEV_LAST]


def predicted(style: str = "label"):
    text = load_input_text(EXCERPT, role="commentary")
    res = parse(text, anchors=[ANCHOR], config={"heading_style": style})
    stub = {"heading_src": "陀羅尼品", "part_type": "品", "origin": "explicit",
            "evidence": "%s: 陀羅尼品" % DEV_FIRST, "node_class": "sutra-span",
            "locations": {"scheme": "cbeta-kepan",
                          "commentary": {"announced": None, "explained": DEV_FIRST},
                          "root_text": {"start": "T09n0262_p0058b08", "end": "T09n0262_p0059b27",
                                        "basis": "chapter"}},
            "children": res.by_anchor[DEV_FIRST]}
    doc, _ = build_prediction(
        [stub], text_id="T34n1723", text_title_src="妙法蓮華經玄贊", outline_mode="sutra",
        root_text_id="T09n0262", commentary_id="T34n1723", scheme_id="kuiji-xuanzan",
        source_file=str(EXCERPT.relative_to(REPO)),
        source_document={"kind": "commentary", "text_id": "T34n1723", "title": "妙法蓮華經玄贊"},
        generated_by="tests/unit/test_tier2_dharani.py", format_note="tier-2 drafts under a stub 品")
    return res, doc


def top_down(pred_nodes: list, gold_nodes: list) -> list:
    """Matched (pred, gold) pairs below the two roots (the 品 nodes)."""
    pk, gk = children_map(pred_nodes), children_map(gold_nodes)
    p_root = next(n for n in pred_nodes if n["parent_id"] is None)
    gold_ids = {n["id"] for n in gold_nodes}
    g_root = next(n for n in gold_nodes if n["parent_id"] not in gold_ids)
    pairs, queue = [], [(p_root, g_root)]
    while queue:
        p, g = queue.pop()
        cands = sorted((abs(a["sibling_index"] - b["sibling_index"]), i, j)
                       for i, a in enumerate(pk.get(p["id"], []))
                       for j, b in enumerate(gk.get(g["id"], [])) if _explained(a) == _explained(b))
        used_p, used_g = set(), set()
        for _, i, j in cands:
            if i in used_p or j in used_g:
                continue
            used_p.add(i)
            used_g.add(j)
            a, b = pk[p["id"]][i], gk[g["id"]][j]
            pairs.append((a, b))
            queue.append((a, b))
    return pairs


@pytest.fixture(scope="module")
def run():
    res, doc = predicted()
    gold = gold_dev_subtree()
    return res, doc, gold, top_down(doc["nodes"], gold)


def test_gold_filter_reads_only_the_dev_subtree(run):
    _, _, gold, _ = run
    assert len(gold) == 45
    assert all(DEV_FIRST <= _explained(n) <= DEV_LAST for n in gold)


def test_precision_recall(run):
    _, doc, gold, pairs = run
    n_pred, n_gold = len(doc["nodes"]) - 1, len(gold) - 1
    precision, recall = len(pairs) / n_pred, len(pairs) / n_gold
    assert (n_pred, n_gold) == (44, 44)
    assert precision >= 1.0 and recall >= 1.0, (precision, recall)


def test_counts_and_classes_agree(run):
    _, _, _, pairs = run
    same_count = sum(a["child_count_announced"] == b["child_count_announced"] for a, b in pairs)
    same_class = sum(a["node_class"] == b["node_class"] for a, b in pairs)
    assert same_count >= 44 and same_class >= 44


def test_source_headings_agree_with_gold():
    _, doc = predicted("source")
    gold = gold_dev_subtree()
    pairs = top_down(doc["nodes"], gold)
    same = sum(a["heading_src"] == b["heading_src"] for a, b in pairs)
    assert same >= 44, [(a["heading_src"], b["heading_src"]) for a, b in pairs
                        if a["heading_src"] != b["heading_src"]]


def test_wrappers_gate_and_lemmas(run):
    res, _, _, _ = run
    top = res.by_anchor[DEV_FIRST]
    assert [d["heading_src"] for d in top] == ["三門分別", "品文分三"]
    gate, text_div = top
    assert gate["node_class"] == "commentary-internal"
    assert all(c["node_class"] == "commentary-internal" for c in gate["children"])
    assert gate["locations"]["root_text"] is None
    assert text_div["child_count_announced"] == 3
    assert text_div["locations"]["root_text"]["raw"] == "爾時藥王至功德甚多"
    assert text_div["locations"]["root_text"]["basis"] == "lemma"
    first = text_div["children"][0]
    assert first["locations"]["commentary"]["announced"].startswith("T34n1723_p0850a30")
    assert first["locations"]["commentary"]["explained"].startswith("T34n1723_p0850b01")
    assert first["_lemma"]["a"] == "爾時藥王"


def test_evidence_and_private_offsets(run):
    res, _, _, _ = run
    text = load_input_text(EXCERPT, role="commentary")

    def walk(ds):
        for d in ds:
            yield d
            yield from walk(d["children"])

    for d in walk(res.by_anchor[DEV_FIRST]):
        for part in d["evidence"].split(" | "):
            lh, _, line = part.partition(": ")
            assert text.index.line_text(lh) == line
        assert text.locate(d["_offset"]) == d["locations"]["commentary"]["explained"]
        assert d["origin"] == "explicit" and d["confidence"] == 1.0


def test_report_and_rejected(run):
    res, _, _, _ = run
    assert res.report == []
    assert len(res.rejected) == 1 and "question" in res.rejected[0]["reason"]
    assert res.genre_gate["decision"] == "outline"
    assert res.stats["nodes"] == 44


def test_validates_except_root_spans(run):
    """The numbered drafts pass the validator except [sutra-span-unmapped], which the anchor stage
    settles (root spans come from the lemmas there)."""
    _, doc, _, _ = run
    rep = validate(doc)
    other = [e for e in rep.errors if e.code != "sutra-span-unmapped"]
    assert not other, [(e.code, e.message) for e in other]


def test_deterministic():
    a, _ = predicted()
    b, _ = predicted()
    dump = lambda r: json.dumps(sorted(r.by_anchor.items(), key=lambda kv: str(kv[0])),
                                ensure_ascii=False, sort_keys=True)
    assert dump(a) == dump(b)
