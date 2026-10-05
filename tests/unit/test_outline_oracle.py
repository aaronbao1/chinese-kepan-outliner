"""Tests for chinese_workflow.outline.oracle (the walking skeleton's oracle guard, plan
Appendix A "SK").

The Kuiji gold (committed) is read only through oracle_drafts; assertions are on levels, lineheads
and counts, never on headings outside the 陀羅尼品 dev subtree. The refusal paths run on synthetic
golds and a synthetic registry (tmp_path), built with common.outline_doc and validated.
"""

from __future__ import annotations

import pytest

from chinese_workflow.common import outline_doc
from chinese_workflow.common.jsonio import write_json
from chinese_workflow.common.paths import REFERENCE_OUTLINES
from chinese_workflow.common.splits import SplitViolation
from chinese_workflow.outline import oracle

KUIJI = REFERENCE_OUTLINES / "T0262" / "kuiji-xuanzan" / "outline.json"
DEV = ("T34n1723_p0850a19", "T34n1723_p0850b19")  # the registry's dev span, end made inclusive


def walk(drafts, level=1):
    for d in drafts:
        yield level, d
        yield from walk(d["children"], level + 1)


def explained(d):
    return d["locations"]["commentary"]["explained"]


def in_dev(ref):
    return ref is not None and DEV[0] <= ref.split(":")[0] <= DEV[1]


def assert_valid(doc):
    rep = outline_doc.validate(doc)
    assert rep.passed(), [f.render() for f in rep.errors]


def test_kuiji_oracle_emits_skeleton_and_dev_subtree_only():
    drafts = oracle.oracle_drafts(KUIJI, keep_span=DEV)
    items = list(walk(drafts))
    assert all(level <= 2 or in_dev(explained(d)) for level, d in items)
    assert sum(1 for level, _ in items if level == 1) == 3
    assert sum(1 for level, _ in items if level == 2) == 28
    assert sum(1 for _, d in items if in_dev(explained(d))) == 45  # the dev subtree, count only
    assert len(items) == 3 + 28 + 44
    assert all(d["notes"] == [] for _, d in items)
    assert all(not set(d) & set(oracle.NUMBERING) for _, d in items)
    # evidence quoting a test/reserve line (the level-1 parts quote T34n1723_p0661b10) is withheld
    for _, d in items:
        if not in_dev(explained(d)):
            assert "raw" not in (d["locations"].get("commentary") or {})
            assert "raw" not in (d["locations"].get("root_text") or {})
    assert all(d["evidence"].startswith("oracle: evidence withheld") for level, d in items
               if level == 1)
    doc, private = outline_doc.build_prediction(
        drafts, text_id="T0262", text_title_src="妙法蓮華經", outline_mode="sutra",
        root_text_id="T09n0262", commentary_id="T34n1723", scheme_id="kuiji-xuanzan",
        source_file="data/reference-outlines/T0262/kuiji-xuanzan/outline.json",
        generated_by="chinese_workflow.outline.oracle",
        source_document={"kind": "commentary", "text_id": "T34n1723", "title": "妙法蓮華經玄贊"},
        format_note="oracle extract (test)")
    assert_valid(doc)
    assert len(private) == len(items)  # _oracle_id on every node, outside the document


def test_kuiji_dharani_node_is_the_dev_root():
    drafts = oracle.oracle_drafts(KUIJI, keep_span=DEV)
    dev_roots = [d for level, d in walk(drafts) if level == 2 and in_dev(explained(d))]
    assert len(dev_roots) == 1
    d = dev_roots[0]
    assert d["heading_src"] == "陀羅尼品"  # dev material may be read
    assert d["locations"]["root_text"]["start"] == "T09n0262_p0058b08"
    assert d["locations"]["root_text"]["end"] == "T09n0262_p0059b27"
    assert 1 + sum(1 for _ in walk(d["children"])) == 45


def test_oracle_refuses_test_span_and_ood_gold():
    with pytest.raises(SplitViolation):  # 序品 test span
        oracle.oracle_drafts(KUIJI, keep_span=("T34n1723_p0651a06", "T34n1723_p0694b21"))
    with pytest.raises(SplitViolation):  # reserve: the line after the dev span
        oracle.oracle_drafts(KUIJI, keep_span=("T34n1723_p0850a19", "T34n1723_p0850b20"))
    d8842 = REFERENCE_OUTLINES / "D8842" / "cbeta-mulu-kepan" / "outline.json"
    with pytest.raises(SplitViolation):  # out-of-domain: never input, refused before reading
        oracle.oracle_drafts(d8842, keep_span=("D14n8842_p0001a01", "D14n8842_p0001a02"))


# ------------------------------------------------------------------- synthetic gold and registry

F = "T99n9998"


def lh(n):
    return "%s_p0001a%02d" % (F, n)


def node(heading, line, children=(), evidence=None, raw=None):
    com = {"announced": None, "explained": lh(line)}
    if raw:
        com["raw"] = raw
    return {"heading_src": heading, "origin": "explicit", "node_class": "commentary-internal",
            "evidence": evidence or "%s: %s" % (lh(line), heading), "notes": ["gold note"],
            "locations": {"scheme": "cbeta-kepan", "commentary": com, "root_text": None},
            "children": list(children)}


def synthetic(tmp_path, roots):
    doc, _ = outline_doc.build_prediction(
        roots, text_id="T9998", text_title_src="合成", outline_mode="sutra",
        root_text_id="T99n9999", commentary_id=F, scheme_id="synthetic-fixture",
        source_file="synthetic:none",
        source_document={"kind": "synthetic", "text_id": F, "title": "合成疏"},
        generated_by="tests/unit/test_outline_oracle.py", format_note="synthetic")
    assert_valid(doc)
    return write_json(doc, tmp_path / "outline.json")


@pytest.fixture
def registry(monkeypatch):
    reg = {"splits": {"texts": {"T9998": {"file": F, "unlisted": "reserve", "spans": [
        {"split": "dev", "start": lh(1), "end": lh(5)},
        {"split": "test", "start": lh(5), "end": lh(7)},
        {"split": "dev", "start": lh(7), "end": lh(20)},
    ]}}}, "datasets": []}
    monkeypatch.setattr(oracle, "load_registry", lambda: reg)
    return reg


def test_kept_node_on_a_test_line_raises(tmp_path, registry):
    gold = synthetic(tmp_path, [node("甲", 1, [node("乙", 2, [node("丙", 3), node("丁", 6)])])])
    with pytest.raises(SplitViolation):  # both span ends are dev, the node at a06 is test
        oracle.oracle_drafts(gold, keep_span=(lh(3), lh(8)))
    drafts = oracle.oracle_drafts(gold, keep_span=(lh(3), lh(4)))
    assert [(lv, d["heading_src"]) for lv, d in walk(drafts)] == [(1, "甲"), (2, "乙"), (3, "丙")]


def test_orphan_in_span_raises(tmp_path, registry):
    gold = synthetic(tmp_path, [node("甲", 1, [node("乙", 2, [node("丙", 3, [node("丁", 9)])])])])
    with pytest.raises(ValueError):  # 丁 (a09) is in the span, its parent 丙 (a03, level 3) is not
        oracle.oracle_drafts(gold, keep_span=(lh(8), lh(10)))


def test_evidence_citing_a_test_line_is_withheld(tmp_path, registry):
    gold = synthetic(tmp_path, [
        node("甲", 1, [node("乙", 2)], evidence="%s: 今為二解" % lh(6), raw="今為二解"),
        node("戊", 8, [node("己", 9, [node("庚", 9, raw="此初")])])])
    drafts = oracle.oracle_drafts(gold, keep_span=(lh(9), lh(10)))
    items = [(lv, d) for lv, d in walk(drafts)]
    assert [(lv, d["heading_src"]) for lv, d in items] == [
        (1, "甲"), (2, "乙"), (1, "戊"), (2, "己"), (3, "庚")]
    first = items[0][1]
    assert first["evidence"].startswith("oracle: evidence withheld (cites a test line)")
    assert "raw" not in first["locations"]["commentary"]
    assert all(d["notes"] == [] for _, d in items)
    kept = items[-1][1]  # inside keep_span: copied as is (notes emptied)
    assert kept["locations"]["commentary"]["raw"] == "此初"
    assert kept["_oracle_id"] == "2_1.1_2.1_3"
