"""Tests for chinese_workflow.eval.score (the outline scorer; docs/outliner-design.md §9,
data/EVAL-SETS.md "Using these sets" items 1-12).

Always run: synthetic checks on tests/fixtures/scorer/ — a SYNTHETIC gold over the fictional texts
T99n9998 (commentary) / T99n9999 (root) and a SYNTHETIC registry with invented split spans, served
halves and OOD entries; every heading and line there is invented. Predictions are perturbed copies
of that gold.
Gold-backed checks (print nothing, write no gold content; headings blanked in memory):
  (a) Kuiji gold, dev split: a prediction made of the gold's levels 1-2 and its dev subtree (the
      one whose root opens the T1723 dev span, selected programmatically) scores S-F1 1.0; the CLI
      writes the same result to metrics.json;
  (b) sdp T1718 gold, dev split (skips when the eval-only file is absent): a prediction made of
      the gold's dev nodes scores S-F1 1.0.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from chinese_workflow.common.jsonio import read_json
from chinese_workflow.common.splits import SplitViolation
from chinese_workflow.eval import registry as reg
from chinese_workflow.eval import score as sc
from chinese_workflow.eval.score import ScoreError, score

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures" / "scorer"
GOLD = read_json(FIX / "T99n9998.synthetic-gold.outline.json")
REG = read_json(FIX / "registry.synthetic.json")
C, R = "T99n9998_p", "T99n9999_p"


def _lines(fid: str) -> list:
    return ["%s_p%04d%s%02d" % (fid, pg, col, ln) for pg in (1, 2, 3) for col in "abc"
            for ln in range(1, 30)]


ORDERS = {"T99n9998": _lines("T99n9998"), "T99n9999": _lines("T99n9999")}
DEV_NODES = 11  # synthetic gold nodes whose explained line is in the synthetic dev span


# ------------------------------------------------------------------------------------------ helpers


def pred_of(doc=GOLD) -> dict:
    p = copy.deepcopy(doc)
    p["metadata"]["gold_status"] = "prediction"
    return p


def gold_of() -> dict:
    return copy.deepcopy(GOLD)


def node(doc: dict, nid: str) -> dict:
    return next(n for n in doc["nodes"] if n["id"] == nid)


def drop(doc: dict, nid: str, keep_children: bool = False) -> dict:
    if keep_children:
        doc["nodes"] = [n for n in doc["nodes"] if n["id"] != nid]
    else:
        doc["nodes"] = [n for n in doc["nodes"]
                        if n["id"] != nid and not n["id"].startswith(nid + ".")]
    return doc


def add_child(doc: dict, parent: str, nid: str, explained: str, after: str | None = None, **extra):
    par = node(doc, parent)
    new = copy.deepcopy(par)
    new.update(id=nid, parent_id=parent, level=par["level"] + 1, heading_src="新段",
               child_count_announced=None, flags=[])
    new["locations"]["commentary"] = {"announced": C + explained, "explained": C + explained}
    new.update(extra)
    idx = doc["nodes"].index(node(doc, after or parent)) + 1
    doc["nodes"].insert(idx, new)
    return new


def set_explained(doc: dict, nid: str, line: str | None):
    node(doc, nid)["locations"]["commentary"]["explained"] = None if line is None else C + line


def shift(doc: dict, delta: int) -> dict:
    order = ORDERS["T99n9998"]
    for n in doc["nodes"]:
        com = n["locations"]["commentary"]
        com["explained"] = order[order.index(com["explained"]) + delta]
    return doc


def run(pred: dict, gold: dict | None = None, gold_id: str = "synthetic-commentary", **kw) -> dict:
    kw.setdefault("line_orders", ORDERS)
    return score(pred, gold_id, registry=REG, gold=gold_of() if gold is None else gold, **kw)


def row(m: dict, t: int = 0, which: str = "s_f1") -> dict:
    return m["rows"]["t=%d" % t][which]


def tpfpfn(r: dict) -> tuple:
    return r["TP"], r["FP"], r["FN"]


# ------------------------------------------------------------------------------- synthetic checks


def test_identity_scores_one_everywhere():
    m = run(pred_of(), split="dev")
    for t in (0, 1):
        r = m["rows"]["t=%d" % t]
        assert r["available"]
        for block in (r["s_f1"], r["f_f1"], r["without_anchor_inherited"]["s_f1"],
                      r["without_anchor_inherited"]["f_f1"], r["locator_only"]):
            assert block["F"] == 1.0 and block["FP"] == 0 and block["FN"] == 0
        assert r["s_f1"]["TP"] == DEV_NODES
        assert all(d["F"] == 1.0 for d in r["per_depth"].values())
    assert m["counts"]["gold"]["counted"] == DEV_NODES
    assert m["counts"]["gold"]["excluded"] == {"out_of_split": 4}
    assert m["child_count"]["eligible"] == 4 and m["child_count"]["accuracy"] == 1.0
    d = m["disclosures"]
    assert d["gold_status"] == "synthetic-fixture" and d["headline"] is False
    assert d["split"] == "dev" and d["split_defaulted"] is False
    assert d["key"] == "commentary.explained"
    assert d["nodes_out_of_scope"] == {"pred": 4, "gold": 4}
    assert m["settings"]["line_order"] == {"T99n9998": "provided"}
    d = m["diagnostics"]
    assert (d["t"], d["fn_gold_ids"], d["fp_pred_ids"]) == (0, [], [])
    assert m["headline_row"] == "t=0" and m["s_f1"] == row(m) and m["f_f1"] == row(m, 0, "f_f1")


def test_default_split_is_dev_and_said_so():
    m = run(pred_of())
    assert m["settings"]["split"] == "dev" and m["disclosures"]["split_defaulted"] is True
    assert any("dev split is scored" in n for n in m["disclosures"]["notes"])
    assert row(m)["TP"] == DEV_NODES


def test_one_line_shift_misses_at_t0_and_matches_at_t1():
    m = run(shift(pred_of(), +1), split="dev")
    assert tpfpfn(row(m, 0)) == (0, DEV_NODES, DEV_NODES) and row(m, 0)["F"] == 0.0
    assert tpfpfn(row(m, 1)) == (DEV_NODES, 0, 0) and row(m, 1)["F"] == 1.0
    assert row(m, 0, "locator_only")["F"] == 0.0 and row(m, 1, "locator_only")["F"] == 1.0
    m1 = run(shift(pred_of(), -1), split="dev", t=1)
    assert m1["headline_row"] == "t=1" and sorted(m1["rows"]) == ["t=0", "t=1"]
    assert row(m1, 1)["F"] == 1.0


def test_dropped_subtree_lowers_recall_only():
    m = run(drop(pred_of(), "2_1.2_2"), split="dev")
    r = row(m)
    assert tpfpfn(r) == (8, 0, 3) and r["P"] == 1.0 and r["R"] == round(8 / 11, 6)
    depth = m["rows"]["t=0"]["per_depth"]
    assert tpfpfn(depth["1"]) == (2, 0, 0)
    assert tpfpfn(depth["2"]) == (4, 0, 1)
    assert tpfpfn(depth["3"]) == (2, 0, 2)
    assert m["diagnostics"]["fn_gold_ids"] == ["2_1.2_2", "2_1.2_2.1_3", "2_1.2_2.2_3"]


def test_merged_siblings_lose_the_second_subtree():
    p = pred_of()
    drop(p, "2_1.2_2", keep_children=True)  # 乙段 merged into 甲段: its children now sit under 甲段
    for nid in ("2_1.2_2.1_3", "2_1.2_2.2_3"):
        node(p, nid)["parent_id"] = "2_1.1_2"
    m = run(p, split="dev")
    assert tpfpfn(row(m)) == (8, 2, 3)
    # locator-only: the one missing line is 乙段's (shared with 乙一): detection 10 of 11
    assert tpfpfn(row(m, 0, "locator_only")) == (10, 0, 1)


def test_wrong_parent_is_no_match_but_locator_only_credits_it():
    p = pred_of()
    node(p, "2_1.3_2")["parent_id"] = "1_1"  # 丙段 re-attached under 序分
    m = run(p, split="dev")
    assert tpfpfn(row(m)) == (10, 1, 1)
    d = m["diagnostics"]
    assert (d["t"], d["fn_gold_ids"], d["fp_pred_ids"]) == (0, ["2_1.3_2"], ["2_1.3_2"])
    assert row(m, 0, "locator_only")["F"] == 1.0


def test_origin_mismatch_keeps_s_f1_and_lowers_f_f1():
    p = pred_of()
    node(p, "2_1.3_2").update(origin="inferred", confidence=0.5)
    m = run(p, split="dev")
    assert row(m)["F"] == 1.0
    assert tpfpfn(row(m, 0, "f_f1")) == (10, 1, 1)
    g = gold_of()
    for n in g["nodes"]:
        n["origin"] = "imported"  # an external outline's nodes count as explicit (ORIGIN_CLASS)
    assert row(run(pred_of(), gold=g, split="dev"), 0, "f_f1")["F"] == 1.0


def test_coverage_spans_decide_scope_and_truncated_is_informational():
    g = gold_of()
    drop(g, "1_1.1_2")
    drop(g, "1_1.2_2")
    node(g, "1_1")["flags"] = ["truncated"]
    g["metadata"]["coverage_spans"] = [
        {"node_id": None, "heading_src": None, "max_level": 1, "root_text": None,
         "commentary": {"start": C + "0001a01", "end": C + "0003a29"}},
        {"node_id": "2_1", "heading_src": "正宗", "max_level": None, "root_text": None,
         "commentary": {"start": C + "0001b01", "end": C + "0001b29"}},
    ]
    m = run(pred_of(), gold=g, split="dev")
    assert tpfpfn(row(m)) == (7, 0, 0)
    assert m["counts"]["pred"]["excluded"] == {"out_of_split": 4, "out_of_coverage": 4}
    # an in-scope prediction under the truncated node that matches nothing is FP
    p = pred_of()
    add_child(p, "1_1", "1_1.9_2", "0001b20", after="1_1.2_2.2_3")
    m = run(p, gold=g, split="dev")
    assert tpfpfn(row(m)) == (7, 1, 0)
    assert m["rows"]["t=0"]["exempt_under_truncated"] == 0


def test_truncated_without_coverage_spans_exempts_unencoded_children():
    g = gold_of()
    drop(g, "2_1.2_2.1_3")
    drop(g, "2_1.2_2.2_3")
    node(g, "2_1.2_2")["flags"] = ["truncated"]
    p = pred_of()
    add_child(p, "2_1.2_2.1_3", "2_1.2_2.1_3.1_4", "0001b06")  # grandchild under an exempt node
    add_child(p, "2_1.3_2", "2_1.3_2.1_3", "0001b16")  # under a complete node: FP
    m = run(p, gold=g, split="dev")
    r = m["rows"]["t=0"]
    assert tpfpfn(r["s_f1"]) == (9, 1, 0)
    assert r["exempt_under_truncated"] == 3
    assert m["diagnostics"]["fp_pred_ids"] == ["2_1.3_2.1_3"]


def test_merged_range_counts_split_siblings_as_one_match():
    g = gold_of()
    node(g, "2_1.1_2")["flags"] = ["merged_range"]
    add_child(g, "2_1.1_2", "2_1.1_2.1_3", "0001b03")
    p = pred_of()
    add_child(p, "2_1", "2_1.9_2", "0001b01", after="2_1.1_2")  # the second half of the merged node
    add_child(p, "2_1.9_2", "2_1.9_2.1_3", "0001b03")  # its child = the merged node's child
    m = run(p, gold=g, split="dev")
    assert tpfpfn(row(m)) == (12, 0, 0)
    assert m["rows"]["t=0"]["absorbed_into_merged_range"] == 1
    node(g, "2_1.1_2")["flags"] = []  # the same prediction against an unmerged node
    assert tpfpfn(row(run(p, gold=g, split="dev"))) == (11, 2, 1)


def test_anchor_inherited_rows_with_and_without():
    g = gold_of()
    node(g, "2_1.3_2")["flags"] = ["anchor_inherited"]
    m = run(drop(pred_of(), "2_1.3_2"), gold=g, split="dev")
    assert tpfpfn(row(m)) == (10, 0, 1)
    without = m["rows"]["t=0"]["without_anchor_inherited"]["s_f1"]
    assert tpfpfn(without) == (10, 0, 0) and without["F"] == 1.0
    m = run(pred_of(), gold=g, split="dev")
    assert tpfpfn(m["rows"]["t=0"]["without_anchor_inherited"]["s_f1"]) == (10, 0, 0)


def test_child_count_accuracy_reads_count_mismatch_as_the_sources():
    p = pred_of()
    node(p, "2_1")["child_count_announced"] = 2
    node(p, "1_1.2_2")["child_count_announced"] = None
    cc = run(p, split="dev")["child_count"]
    assert (cc["eligible"], cc["correct"], cc["wrong"], cc["missing"]) == (4, 2, 1, 1)
    assert cc["accuracy"] == 0.5
    g = gold_of()
    node(g, "2_1")["flags"] = ["count_mismatch"]
    cc = run(p, gold=g, split="dev")["child_count"]
    assert (cc["wrong"], cc["source_disagreements"], cc["at_count_mismatch"]) == (0, 1, 1)
    assert cc["accuracy"] == round(2 / 3, 6)


def test_same_line_siblings_pair_by_sibling_index():
    g = gold_of()
    set_explained(g, "1_1.2_2.2_3", "0001a06")  # 初段 and 後段 now share a line
    node(g, "1_1.2_2.2_3").update(origin="inferred", confidence=0.5)
    p = pred_of(g)
    m = run(p, gold=g, split="dev")
    assert row(m, 0, "f_f1")["F"] == 1.0


def test_reserve_is_refused_without_frozen():
    for split in ("reserve", "all"):
        with pytest.raises(SplitViolation):
            run(pred_of(), split=split)
    m = run(pred_of(), split="all", frozen="synthetic-freeze")
    assert tpfpfn(row(m)) == (15, 0, 0) and m["disclosures"]["headline"] is False
    m = run(pred_of(), split="reserve", frozen="synthetic-freeze")
    assert tpfpfn(row(m)) == (1, 0, 0)
    assert "diagnostics" not in m


def test_test_split_needs_frozen():
    with pytest.raises(SplitViolation):
        run(pred_of(), split="test")
    m = run(pred_of(), split="test", frozen="synthetic-freeze")
    assert tpfpfn(row(m)) == (1, 0, 0)
    assert m["settings"]["frozen"] == "synthetic-freeze"
    assert "diagnostics" not in m  # node ids only on the dev split


def test_ood_gold_needs_frozen():
    with pytest.raises(SplitViolation):
        run(pred_of(), gold_id="synthetic-ood")
    m = run(pred_of(), gold_id="synthetic-ood", frozen="synthetic-freeze")
    assert m["settings"]["split"] == "unsplit" and tpfpfn(row(m)) == (15, 0, 0)
    with pytest.raises(ScoreError):
        run(pred_of(), gold_id="synthetic-ood", frozen="synthetic-freeze", split="dev")
    # the real registry: an OOD gold is refused before anything is read
    with pytest.raises(SplitViolation):
        score({"metadata": {}, "nodes": []}, "cbeta-mulu-D8842")


def test_served_halves_restrict_scope():
    g = gold_of()
    for n in g["nodes"]:
        if n["id"] == "2_1" or n["id"].startswith("2_1."):  # the unserved half: no anchors
            n["locations"]["commentary"]["explained"] = None
    m = run(pred_of(), gold=g, gold_id="synthetic-served", split="dev")
    assert tpfpfn(row(m)) == (5, 0, 0)
    assert m["counts"]["pred"]["excluded"]["out_of_scoring_scope"] == 6
    assert m["counts"]["gold"]["excluded"]["no_key"] == 6
    # the same gold without a scoring scope: every prediction in the unserved half is FP
    assert tpfpfn(row(run(pred_of(), gold=g, split="dev"))) == (5, 6, 0)


def test_structure_key_checks_the_served_scope_on_the_scopes_own_locator():
    """--key structure has no key line (its tree key is the heading text): the served scope is judged
    on the scope's own locator as before, not on the heading (T2 review 2026-10-02)."""
    m = run(pred_of(), gold_id="synthetic-served", key="structure", frozen="synthetic-freeze")
    assert m["settings"]["key"] == "structure"
    assert tpfpfn(m["rows"]["structure"]["s_f1"]) == (9, 0, 0)
    for side in ("gold", "pred"):
        assert m["counts"][side]["excluded"] == {"out_of_scoring_scope": 6}
        assert m["counts"][side]["counted"] == 9


def test_structure_mode_for_structure_only_golds():
    g = gold_of()
    for n in g["nodes"]:
        n["locations"] = {"scheme": "none"}
    m = run(pred_of(g), gold=g, gold_id="synthetic-structure", frozen="synthetic-freeze")
    assert m["settings"]["key"] == "structure" and list(m["rows"]) == ["structure"]
    assert tpfpfn(m["rows"]["structure"]["s_f1"]) == (15, 0, 0)
    p = pred_of(g)
    node(p, "2_1.2_2")["heading_src"] = "異段"
    m = run(p, gold=g, gold_id="synthetic-structure", frozen="synthetic-freeze")
    r = m["rows"]["structure"]
    assert tpfpfn(r["s_f1"]) == (12, 3, 3)
    assert tpfpfn(r["heading_only"]) == (14, 1, 1)


def set_root(n: dict, start: str):
    n["locations"]["root_text"] = {"start": R + start, "end": R + start, "basis": "inferred",
                                   "end_basis": None}
    return n


def test_root_text_key_splits_predictions_by_gold_region():
    m = run(pred_of(), gold_id="synthetic-root", split="dev")
    assert m["settings"]["key"] == "root_text.start"
    assert m["settings"]["split_locator"] == "commentary.explained"
    assert tpfpfn(row(m)) == (DEV_NODES, 0, 0)
    p = pred_of()
    set_root(add_child(p, "2_1.2_2", "2_1.2_2.9_3", "0001b12", after="2_1.2_2.2_3"), "0001b25")
    set_root(add_child(p, "2_1", "2_1.9_2", "0001b20", after="2_1.3_2"), "0001c15")
    set_root(add_child(p, "3_1", "3_1.9_2", "0002a20", after="3_1.3_2"), "0002b15")
    m = run(p, gold_id="synthetic-root", split="dev")
    # b25 lies between two dev nodes (乙二 b21, 丙段 c11): dev, FP. c15 follows 丙段, the last dev
    # node, and precedes 流通 (validation): its commentary may lie on either side of the split
    # boundary, so it takes the more protected split. b15 lies between a test and a reserve node.
    assert tpfpfn(row(m)) == (DEV_NODES, 1, 0)
    assert m["counts"]["pred"]["excluded"] == {"out_of_split": 6}
    m = run(p, gold_id="synthetic-root", split="validation")
    assert tpfpfn(row(m)) == (2, 1, 0)  # c15 counts in validation


# ------------------------------------------------- E06 scorer defects (experiments/E06, 2026-10-01)
# Minimal synthetic golds over the fictional file T99n9997 (lines a01..a29), unregistered, so they
# are scored whole ("unsplit"); every heading is invented.

F7 = "T99n9997"
L7 = ["%s_p0001a%02d" % (F7, i) for i in range(1, 30)]


def syn(nid, parent, level, line=None, heading="", flags=None, origin="explicit") -> dict:
    loc = ({"scheme": "cbeta-kepan",
            "commentary": {"announced": None, "explained": L7[line - 1] if line else None},
            "root_text": None} if line else {"scheme": "none"})
    return {"id": nid, "parent_id": parent, "level": level, "origin": origin,
            "heading_src": heading, "flags": flags or [], "locations": loc}


def syn_doc(*nodes, status="synthetic-fixture") -> dict:
    return {"metadata": {"gold_status": status}, "nodes": list(nodes)}


def syn_run(pred: dict, gold: dict, **kw) -> dict:
    kw.setdefault("line_orders", {F7: L7})
    return score(pred, "synthetic-unregistered", registry=REG, gold=gold, **kw)


def shift7(doc: dict, delta: int) -> dict:
    p = copy.deepcopy(doc)
    for n in p["nodes"]:
        com = n["locations"]["commentary"]
        com["explained"] = L7[L7.index(com["explained"]) + delta]
    return p


def test_t1_aligns_a_uniformly_shifted_prediction():
    """E06 defect 1: the greedy took the distance-0 pair (pred 1.1 @a03, gold 1.2 @a03) and left
    pred 1.2 @a04 without a partner; an order-preserving alignment pairs both at distance 1."""
    g = syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 2), syn("1.2", "1", 2, 3))
    m = syn_run(shift7(g, +1), g)
    assert m["settings"]["split"] == "unsplit"
    assert tpfpfn(row(m, 1)) == (3, 0, 0) and row(m, 1)["F"] == 1.0
    assert tpfpfn(row(m, 0)) == (0, 3, 3)  # t = 0 unchanged
    assert tpfpfn(row(m, 1, "locator_only")) == (3, 0, 0)


def test_t1_shift_of_dense_random_trees_scores_one():
    """Seeded: trees whose siblings sit on consecutive lines, every line shifted by +-1, score
    S-F1 = 1.0 at t = 1 (the greedy scored them below 1 whenever a node and its next sibling's
    line collided)."""
    import random

    rng = random.Random(1)
    for _ in range(40):
        nodes = _dense_tree(rng, [], [2], None, 1)
        g = syn_doc(*nodes)
        for delta in (+1, -1):
            m = syn_run(shift7(g, delta), g)
            assert row(m, 1)["F"] == 1.0, (delta, [(n["id"], n["locations"]["commentary"]
                                                    ["explained"][-3:]) for n in nodes])


def _dense_tree(rng, nodes: list, line: list, parent, level) -> list:
    """Pre-order nodes on lines a02..a27: siblings on the same or the next line, a first child on
    its parent's line or the next."""
    for k in range(rng.randint(1, 3)):
        if line[0] >= 27:
            break
        nid = "%s.%d" % (parent, k + 1) if parent else str(k + 1)
        nodes.append(syn(nid, parent, level, line[0]))
        if level < 4 and rng.random() < 0.5:
            line[0] += rng.choice((0, 1))
            _dense_tree(rng, nodes, line, nid, level + 1)
        line[0] += rng.choice((0, 1, 1))
    return nodes


def test_same_line_siblings_align_in_order_when_one_is_missing():
    """Gold 甲 > 子 @a02, 丑 @a04, 寅 @a04 (two siblings share a04); the prediction omits 子. The
    greedy paired by sibling-index difference and crossed (pred 1st @a04 with gold 寅, pred 2nd with
    丑), so the grandchildren missed; the alignment keeps sibling order."""
    g = syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 2), syn("1.2", "1", 2, 4),
                syn("1.2.1", "1.2", 3, 5), syn("1.3", "1", 2, 4), syn("1.3.1", "1.3", 3, 8))
    p = copy.deepcopy(g)
    p["nodes"] = [n for n in p["nodes"] if n["id"] != "1.1"]
    m = syn_run(p, g)
    assert tpfpfn(row(m, 0)) == (5, 0, 1)  # the greedy: (3, 2, 3)


def test_t0_pairs_siblings_listed_out_of_line_order_as_before():
    """Review of the fix: siblings are aligned in line order, not document order, so a prediction
    that lists siblings out of line order (a listed-only node on its announcement line, design
    §5.5) keeps the pairs the greedy gave it at t = 0."""
    g = syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 2), syn("1.2", "1", 2, 5),
                syn("1.3", "1", 2, 8))
    p = copy.deepcopy(g)
    p["nodes"] = [p["nodes"][0], p["nodes"][3], p["nodes"][1], p["nodes"][2]]
    m = syn_run(p, g)
    assert tpfpfn(row(m, 0)) == (4, 0, 0) and tpfpfn(row(m, 1)) == (4, 0, 0)


def test_structure_mode_pairs_permuted_siblings_as_before():
    """Structure mode has no line axis and its key (heading + depth + parent path, item 10) does not
    include sibling order: permuted siblings still match."""
    g = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙"),
                syn("1.2", "1", 2, heading="丙"))
    p = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="丙"),
                syn("1.2", "1", 2, heading="乙"), status="prediction")
    assert tpfpfn(syn_run(p, g, key="structure")["rows"]["structure"]["s_f1"]) == (3, 0, 0)


def test_structure_merged_range_absorbs_no_more_parts_than_its_label_spans():
    """A merged_range node labelled K5-6 stands for two siblings: one split part is absorbed, a
    third predicted sibling is FP."""
    g = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙",
                                                    flags=["merged_range"]))
    g["nodes"][1]["display_label"] = "K5-6"
    p = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙"),
                syn("1.2", "1", 2, heading="丙"), syn("1.3", "1", 2, heading="丁"),
                status="prediction")
    r = syn_run(p, g, key="structure")["rows"]["structure"]
    assert tpfpfn(r["s_f1"]) == (2, 1, 0) and r["absorbed_into_merged_range"] == 1


def test_structure_merged_range_absorbs_a_split_part_with_its_own_heading():
    """E06 defect 2 (EVAL-SETS item 10): a prediction that splits a merged_range node is not an
    error; in structure mode the parts carry their own headings."""
    g = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙",
                                                    flags=["merged_range"]))
    p = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙"),
                syn("1.2", "1", 2, heading="丙"), status="prediction")
    m = syn_run(p, g, key="structure")
    r = m["rows"]["structure"]
    assert tpfpfn(r["s_f1"]) == (2, 0, 0)
    assert r["absorbed_into_merged_range"] == 1


def test_structure_merged_range_split_parts_bring_their_children():
    g = syn_doc(syn("1", None, 1, heading="甲"),
                syn("1.1", "1", 2, heading="乙", flags=["merged_range"]),
                syn("1.1.1", "1.1", 3, heading="乙一"), syn("1.1.2", "1.1", 3, heading="丙一"),
                syn("1.2", "1", 2, heading="丁"))
    p = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙"),
                syn("1.1.1", "1.1", 3, heading="乙一"), syn("1.2", "1", 2, heading="丙"),
                syn("1.2.1", "1.2", 3, heading="丙一"), syn("1.3", "1", 2, heading="丁"),
                status="prediction")
    r = syn_run(p, g, key="structure")["rows"]["structure"]
    assert tpfpfn(r["s_f1"]) == (5, 0, 0) and r["absorbed_into_merged_range"] == 1


def test_structure_merged_range_does_not_absorb_beside_a_missed_gold_sibling():
    """A part is absorbed only from a gap of the alignment that holds no unmatched gold sibling:
    there the extra prediction may be an attempt at that sibling, so it stays FP."""
    g = syn_doc(syn("1", None, 1, heading="甲"),
                syn("1.1", "1", 2, heading="乙", flags=["merged_range"]),
                syn("1.2", "1", 2, heading="丁"))
    p = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙"),
                syn("1.2", "1", 2, heading="丙"), status="prediction")
    r = syn_run(p, g, key="structure")["rows"]["structure"]
    assert tpfpfn(r["s_f1"]) == (2, 1, 1) and r["absorbed_into_merged_range"] == 0


def test_structure_split_of_an_unmerged_node_stays_fp():
    g = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙"))
    p = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙"),
                syn("1.2", "1", 2, heading="丙"), status="prediction")
    r = syn_run(p, g, key="structure")["rows"]["structure"]
    assert tpfpfn(r["s_f1"]) == (2, 1, 0) and r["absorbed_into_merged_range"] == 0


def test_root_text_region_between_known_nodes_takes_their_split():
    """E06 defect 3: a gold node without its own split locator (乙二) used to open a region of
    unknown split, so its twin and an extra prediction after it were neither TP nor FP. Both of its
    known neighbours (乙一, 丙段) are dev, so its commentary lies in dev."""
    g = gold_of()
    set_explained(g, "2_1.2_2.2_3", None)
    p = pred_of(g)
    set_root(add_child(p, "2_1.2_2", "2_1.2_2.9_3", "0001b12", after="2_1.2_2.2_3"), "0001b25")
    m = run(p, gold=g, gold_id="synthetic-root", split="dev")
    assert tpfpfn(row(m)) == (DEV_NODES, 1, 0)
    assert "split_unknown" not in m["counts"]["pred"]["excluded"]
    assert "split_unknown" not in m["counts"]["gold"]["excluded"]
    assert m["diagnostics"]["fp_pred_ids"] == ["2_1.2_2.9_3"]


def test_root_text_region_after_the_last_known_node_is_reserve():
    """The E06 repro: gold 1, 1.1 explained in dev (root a01, a02), 1.2 without an explained line
    (a05), and a prediction with an extra child at a08. Nothing known follows a02, so the
    commentary on a05 and a08 may lie anywhere to the end of the file: reserve (out of split), not
    split_unknown."""
    dev_start = C + "0001a01"
    g = syn_doc(syn("1", None, 1), syn("1.1", "1", 2), syn("1.2", "1", 2))
    for n, root in zip(g["nodes"], ("0001a01", "0001a02", "0001a05"), strict=True):
        n["locations"] = {"scheme": "cbeta-kepan",
                          "commentary": {"announced": None,
                                         "explained": None if n["id"] == "1.2" else dev_start},
                          "root_text": {"start": R + root, "end": R + root}}
    p = copy.deepcopy(g)
    p["nodes"].append(set_root(copy.deepcopy(p["nodes"][2]) | {"id": "1.3"}, "0001a08"))
    m = run(p, gold=g, gold_id="synthetic-root", split="dev")
    assert tpfpfn(row(m)) == (2, 0, 0)
    assert m["counts"]["pred"]["excluded"] == {"out_of_split": 2}
    assert m["counts"]["gold"]["excluded"] == {"out_of_split": 1}


def test_root_text_unknown_gold_node_on_a_known_nodes_line_is_not_given_its_split():
    """Review of the fix: a gold node without an explained line (1.2) that starts on the root line
    of a known one (1.1, dev) is not that node's twin; its commentary may follow 1.1's past the dev
    boundary, so it takes the most protected split between its neighbours (dev c20 .. validation
    p0002b10): validation. Predictions there still take 1.1's split (their likely twin)."""
    g = syn_doc(syn("1", None, 1), syn("1.1", "1", 2), syn("1.2", "1", 2), syn("1.3", "1", 2))
    for n, root, ex in zip(g["nodes"], ("0001a01", "0001a05", "0001a05", "0001a10"),
                           ("0001c20", "0001c28", None, "0002b10"), strict=True):
        n["locations"] = {"scheme": "cbeta-kepan",
                          "commentary": {"announced": None, "explained": ex and C + ex},
                          "root_text": {"start": R + root, "end": R + root}}
    m = run(copy.deepcopy(g), gold=g, gold_id="synthetic-root", split="dev")
    assert tpfpfn(row(m)) == (2, 0, 0)
    assert m["counts"]["gold"]["excluded"] == {"out_of_split": 2}
    assert m["rows"]["t=0"]["matched_to_gold_outside_scope"] == 1  # the twin of 1.2
    m = run(copy.deepcopy(g), gold=g, gold_id="synthetic-root", split="validation")
    assert tpfpfn(row(m)) == (2, 0, 0)


def test_imported_unchecked_gold_is_never_a_headline():
    """E06 defect 4: an OOD row on an imported-unchecked gold reported headline true."""
    g = gold_of()
    g["metadata"]["gold_status"] = "imported-unchecked"
    m = run(pred_of(), gold=g, gold_id="synthetic-ood", frozen="synthetic-freeze")
    d = m["disclosures"]
    assert d["split"] == "unsplit" and d["headline"] is False
    assert any("imported-unchecked" in r for r in d["headline_reasons"])
    assert "headline false" in sc.summary(m)


def test_without_line_order_t1_is_unavailable():
    m = run(pred_of(), split="dev", line_orders=None)  # no XML for the fictional file
    assert m["settings"]["line_order"] == {"T99n9998": "absent"}
    assert m["rows"]["t=1"]["available"] is False
    assert row(m)["F"] == 1.0
    m = run(pred_of(), split="dev", t=1, line_orders=None)
    assert m["rows"]["t=1"]["available"] is False and "unavailable" in sc.summary(m)


def test_validation_split_and_pairing_warnings():
    p = pred_of()
    p["metadata"]["scheme_id"] = "model-0123abcd"
    m = run(p, split="validation")
    assert tpfpfn(row(m)) == (2, 0, 0)
    assert any("validation look" in n for n in m["disclosures"]["notes"])
    assert any("scheme_id" in w for w in m["disclosures"]["pairing_warnings"])
    assert "diagnostics" not in m


def test_nodes_without_key_are_not_scored():
    p = pred_of()
    set_explained(p, "2_1.3_2", None)
    m = run(p, split="dev")
    assert tpfpfn(row(m)) == (10, 0, 1)
    assert m["counts"]["pred"]["excluded"]["no_key"] == 1
    with pytest.raises(ScoreError):
        run(pred_of(), key="root_text.end")


def test_output_is_deterministic():
    assert run(pred_of(), split="dev") == run(pred_of(), split="dev")


def _perturbed_preds(seed: int, n: int = 60):
    """Seeded generator of n perturbed copies of the identity prediction: one gold node dropped, up
    to three shifted by one line, one re-attached to another parent (or the root)."""
    import random

    rng = random.Random(seed)
    order = ORDERS["T99n9998"]
    for _ in range(n):
        p = drop(pred_of(), rng.choice(GOLD["nodes"])["id"])
        for node in rng.sample(p["nodes"], min(3, len(p["nodes"]))):
            com = node["locations"]["commentary"]
            com["explained"] = order[order.index(com["explained"]) + rng.choice((-1, 1))]
        if p["nodes"]:
            victim = rng.choice(p["nodes"])
            others = [x["id"] for x in p["nodes"] if not x["id"].startswith(victim["id"])]
            victim["parent_id"] = rng.choice(others + [None])
        yield p


def test_invariants_under_random_perturbations():
    """Seeded: drop, shift and re-attach nodes at random; the counts must stay consistent."""
    for p in _perturbed_preds(0):
        m = run(p, split="dev")
        gold_counted = m["counts"]["gold"]["counted"]
        for t in (0, 1):
            r = m["rows"]["t=%d" % t]
            s, f, loc = r["s_f1"], r["f_f1"], r["locator_only"]
            assert s["TP"] + s["FN"] == gold_counted
            assert f["TP"] <= s["TP"] <= loc["TP"]
            assert s["FP"] <= m["counts"]["pred"]["counted"]
            for block in (s, f, loc):
                assert all(block[k] is None or 0.0 <= block[k] <= 1.0 for k in ("P", "R", "F"))
            # the attachment-tolerant triple (A2): the both-counted top-down pairs are one ordered
            # ancestor-consistent mapping and the mapping maximises counted pairs first, so AC's TP
            # cannot fall below the both-counted S-F1 TP, by construction in the line-order modes (this
            # test's key; structure mode's greedy top-down match can exceed the ordered mapping; and
            # merged_range aside: no case here); the re-anchoring starts from the top-down pairs, so neither can reanchor's;
            # the histogram pairs are the locator-only TP
            ac, ra, dh = r["ancestor_consistent"], r["reanchor"], r["depth_offset_hist"]
            both = r["s_f1_both_counted"]["TP"]
            assert both <= ac["TP"] <= loc["TP"] and both <= ra["TP"] <= loc["TP"]
            assert ra["anchors"] <= gold_counted - s["TP"]
            assert dh["pairs"] == loc["TP"] and sum(dh["hist"].values()) == dh["pairs"]


# -------------------------------------------- diagnostic fields (review of E06, 2026-10-02, A1)
# Row fields beside the headline (never a headline value) and the dev diagnostics that explain them.
# Synthetic trees only: the F7 fixture (unregistered, scored whole) and the registered synthetic gold.


def test_fn_split_frontier_cascaded_and_line_detected():
    """A FN whose scoring-tree parent is matched (or the root) is a frontier miss, the rest cascade
    from it; a frontier miss is line-detected when a FREE (unpaired, unabsorbed) predicted node sits
    within t of its key line. Gold 1 @a01 > 1.1 @a03 > {1.1.1 @a05, 1.1.2 @a07}, 1.2 @a10; the
    prediction puts 1.1 on a04 (one line off) and a top-level node 2 on 1.2's line."""
    g = syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 3), syn("1.1.1", "1.1", 3, 5),
                syn("1.1.2", "1.1", 3, 7), syn("1.2", "1", 2, 10))
    p = syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 4), syn("1.1.1", "1.1", 3, 5),
                syn("1.1.2", "1.1", 3, 7), syn("2", None, 1, 10), status="prediction")
    m = syn_run(p, g)
    r0, r1 = m["rows"]["t=0"], m["rows"]["t=1"]
    # t = 0: 1.1 (a04 is not within 0 of a03) and 1.2 are frontier misses; 1.2's line holds the free
    # prediction 2; 1.1.1 and 1.1.2 cascade from 1.1
    assert tpfpfn(r0["s_f1"]) == (1, 4, 4)
    assert r0["fn_split"] == {"frontier": 2, "frontier_line_detected": 1, "cascaded": 2}
    # t = 1: 1.1 and its children match; only 1.2 is missed, and 2 still sits on its line
    assert tpfpfn(r1["s_f1"]) == (4, 1, 1)
    assert r1["fn_split"] == {"frontier": 1, "frontier_line_detected": 1, "cascaded": 0}


def test_fn_split_top_level_miss_is_frontier_and_not_line_detected():
    """A missed TOP-LEVEL gold node (scoring-tree parent: the virtual root) is a frontier miss, and its
    child cascades from it. Gold 1 @a01 > 1.1 @a03, 2 @a10; the prediction has only 2 @a10 and a free
    top-level node @a20, so nothing sits within t of 1's line (a01): frontier_line_detected stays 0."""
    g = syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 3), syn("2", None, 1, 10))
    p = syn_doc(syn("2", None, 1, 10), syn("3", None, 1, 20), status="prediction")
    m = syn_run(p, g)
    for t in (0, 1):
        r = m["rows"]["t=%d" % t]
        assert tpfpfn(r["s_f1"]) == (1, 1, 2)
        assert r["fn_split"] == {"frontier": 1, "frontier_line_detected": 0, "cascaded": 1}


def test_fn_split_of_a_dropped_subtree_and_of_the_identity():
    m = run(drop(pred_of(), "2_1.2_2"), split="dev")
    assert m["rows"]["t=0"]["fn_split"] == {"frontier": 1, "frontier_line_detected": 0, "cascaded": 2}
    m = run(pred_of(), split="dev")
    assert m["rows"]["t=0"]["fn_split"] == {"frontier": 0, "frontier_line_detected": 0, "cascaded": 0}


def _root_asymmetry_gold() -> dict:
    """Gold 1 (root a01, explained dev c20) > 1.1 (root a05, dev c28), 1.2 (root a05, validation
    p0002b10), 1.3 (root a10, validation p0002b12). Scored on root_text.start, both predictions on a05
    take the split of their likely twin, the LAST known gold node on that line (1.2: validation), so
    an identical prediction's 1.1 is uncounted although it is the counted gold 1.1's match."""
    g = syn_doc(syn("1", None, 1), syn("1.1", "1", 2), syn("1.2", "1", 2), syn("1.3", "1", 2))
    for n, root, ex in zip(g["nodes"], ("0001a01", "0001a05", "0001a05", "0001a10"),
                           ("0001c20", "0001c28", "0002b10", "0002b12"), strict=True):
        n["locations"] = {"scheme": "cbeta-kepan",
                          "commentary": {"announced": None, "explained": C + ex},
                          "root_text": {"start": R + root, "end": R + root}}
    return g


def test_root_text_tp_rule_both_counted_is_reported_beside_the_headline():
    """E06 review item 5: a matched pair is TP when the GOLD node is counted even if the prediction is
    not, while FP runs over counted predictions only, so TP can exceed the counted predictions
    (model-only-T0262-xu-root dev t = 1: TP 5 on 2 counted predictions). The headline keeps that
    rule; the both-counted rule, the number of such pairs and the TP <= counted check sit beside it."""
    g = _root_asymmetry_gold()
    m = run(copy.deepcopy(g), gold=g, gold_id="synthetic-root", split="dev")
    assert m["counts"]["pred"]["counted"] == 1 and m["counts"]["gold"]["counted"] == 2
    for t in (0, 1):
        r = m["rows"]["t=%d" % t]
        assert tpfpfn(r["s_f1"]) == (2, 0, 0)  # the headline rule, unchanged
        assert r["tp_rule"] == "gold_counted"
        assert r["tp_uncounted_pred"] == 1 and r["tp_le_counted_pred"] is False
        assert tpfpfn(r["s_f1_both_counted"]) == (1, 0, 1)
        assert r["s_f1_both_counted"]["F"] == round(2 / 3, 6)
    # commentary scoring: a TP's prediction lies in the gold node's split, so the rules agree
    r = run(pred_of(), split="dev")["rows"]["t=0"]
    assert r["s_f1_both_counted"] == r["s_f1"] and r["tp_uncounted_pred"] == 0
    assert r["tp_le_counted_pred"] is True


def test_key_lines_cap_recall_for_one_node_per_line_predictions():
    """EVAL-SETS item 3 / E06 review item 1: sdp keys a parent and its first child on one line, so a
    gold of N counted nodes on n distinct key lines caps the recall of an outliner that keys one node
    per line at n/N (5/12 on the T1718 dev row). Gold 1 @a01 > 1.1 @a01 (a chain), 1.2 @a03."""
    g = syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 1), syn("1.2", "1", 2, 3))
    r = syn_run(copy.deepcopy(g), g)["rows"]["t=0"]
    assert tpfpfn(r["s_f1"]) == (3, 0, 0)
    assert r["key_lines"] == {"gold": {"counted": 3, "distinct": 2},
                              "pred": {"counted": 3, "distinct": 2},
                              "recall_cap_one_node_per_line": round(2 / 3, 6)}
    r = run(pred_of(), split="dev")["rows"]["t=0"]
    assert r["key_lines"]["gold"] == {"counted": DEV_NODES, "distinct": 7}
    assert r["key_lines"]["recall_cap_one_node_per_line"] == round(7 / 11, 6)


def test_fp_split_by_node_kind():
    """E06 review A1: FP predictions split into listed-only (announced == explained, both with a
    ':<offset>', as tier 2 writes a node the commentary lists but never takes up: the anchor's rule),
    commentary-internal (node_class) and taken-up (the rest; a bare linehead on both sides is
    ambiguous and counts as taken up, as the anchor leaves it placed)."""
    g = syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 2))
    listed = syn("1.2", "1", 2, 5)
    listed["locations"]["commentary"] = {"announced": L7[4] + ":3", "explained": L7[4] + ":3"}
    wrapper = syn("1.3", "1", 2, 7)
    wrapper["node_class"] = "commentary-internal"
    bare = syn("1.4", "1", 2, 9)
    bare["locations"]["commentary"]["announced"] = bare["locations"]["commentary"]["explained"]
    p = syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 2), listed, wrapper, bare,
                syn("1.5", "1", 2, 11), status="prediction")
    r = syn_run(p, g)["rows"]["t=0"]
    assert tpfpfn(r["s_f1"]) == (2, 4, 0)
    assert r["fp_by_kind"] == {"listed_only": 1, "commentary_internal": 1, "taken_up": 2}
    assert sum(r["fp_by_kind"].values()) == r["s_f1"]["FP"]


def test_dev_diagnostics_carry_tp_pairs_fn_split_and_fp_kinds():
    """The dev-only diagnostics (ids only) name the TP pairs, the frontier / cascaded FN, the TPs
    whose prediction is uncounted and the FP ids per kind, beside fn_gold_ids / fp_pred_ids. 丙段
    (2_1.3_2) re-attached under 序分 is a frontier miss whose line holds the free prediction; a
    listed-only child and a commentary-internal child are added under 正宗."""
    p = pred_of()
    node(p, "2_1.3_2")["parent_id"] = "1_1"
    listed = add_child(p, "2_1", "2_1.9_2", "0001b20", after="2_1.3_2")
    listed["locations"]["commentary"] = {"announced": C + "0001b20:5", "explained": C + "0001b20:5"}
    wrapper = add_child(p, "2_1", "2_1.8_2", "0001b22", after="2_1.9_2")
    wrapper["node_class"] = "commentary-internal"
    m = run(p, split="dev")
    assert tpfpfn(row(m)) == (10, 3, 1)
    d = m["diagnostics"]
    assert d["t"] == 0
    assert d["fn_gold_ids"] == ["2_1.3_2"]
    assert d["fp_pred_ids"] == ["2_1.3_2", "2_1.9_2", "2_1.8_2"]
    assert len(d["tp_pairs"]) == 10 and all(a == b for a, b in d["tp_pairs"])
    assert d["tp_pairs"][0] == ["1_1", "1_1"] and d["tp_pairs"][-1] == ["2_1.2_2.2_3", "2_1.2_2.2_3"]
    assert d["tp_uncounted_pred_ids"] == []
    assert d["fn_frontier_gold_ids"] == ["2_1.3_2"]
    assert d["fn_frontier_line_detected_gold_ids"] == ["2_1.3_2"]
    assert d["fn_cascaded_gold_ids"] == []
    assert d["fp_pred_ids_by_kind"] == {"listed_only": ["2_1.9_2"],
                                        "commentary_internal": ["2_1.8_2"],
                                        "taken_up": ["2_1.3_2"]}
    assert m["rows"]["t=0"]["fp_by_kind"] == {"listed_only": 1, "commentary_internal": 1,
                                              "taken_up": 1}
    # the identity prediction: every dev node is a TP pair, nothing else
    d = run(pred_of(), split="dev")["diagnostics"]
    assert len(d["tp_pairs"]) == DEV_NODES
    assert d["fn_frontier_gold_ids"] == [] and d["fn_cascaded_gold_ids"] == []
    assert d["fp_pred_ids_by_kind"] == {"listed_only": [], "commentary_internal": [], "taken_up": []}
    # root-text scoring: the uncounted prediction of a TP pair is named
    g = _root_asymmetry_gold()
    d = run(copy.deepcopy(g), gold=g, gold_id="synthetic-root", split="dev")["diagnostics"]
    assert d["tp_pairs"] == [["1", "1"], ["1.1", "1.1"]] and d["tp_uncounted_pred_ids"] == ["1.1"]
    # no diagnostics block off the dev split (unchanged)
    assert "diagnostics" not in run(pred_of(), split="validation")


def test_diagnostic_fields_are_consistent_under_random_perturbations():
    """Seeded: the new fields must add up to the headline counts on every perturbation."""
    for p in _perturbed_preds(2):
        m = run(p, split="dev")
        for t in (0, 1):
            r = m["rows"]["t=%d" % t]
            s, b = r["s_f1"], r["s_f1_both_counted"]
            assert b["TP"] + r["tp_uncounted_pred"] == s["TP"] and b["FP"] == s["FP"]
            assert b["TP"] + b["FN"] == m["counts"]["gold"]["counted"]
            # commentary scoring: a TP's prediction lies within t of a dev gold line, hence in dev
            assert r["tp_uncounted_pred"] == 0 and r["tp_le_counted_pred"] is True
            fs = r["fn_split"]
            assert fs["frontier"] + fs["cascaded"] == s["FN"]
            assert fs["frontier_line_detected"] <= fs["frontier"]
            assert sum(r["fp_by_kind"].values()) == s["FP"]
            assert r["key_lines"]["gold"]["counted"] == m["counts"]["gold"]["counted"]
            assert r["key_lines"]["pred"]["counted"] == m["counts"]["pred"]["counted"]
            assert r["key_lines"]["gold"]["distinct"] <= r["key_lines"]["gold"]["counted"]
        d = m["diagnostics"]
        assert len(d["tp_pairs"]) == m["rows"]["t=0"]["s_f1"]["TP"]
        assert sorted(d["fn_frontier_gold_ids"] + d["fn_cascaded_gold_ids"]) == sorted(d["fn_gold_ids"])
        assert sorted(sum(d["fp_pred_ids_by_kind"].values(), [])) == sorted(d["fp_pred_ids"])


# ------------------------------------------- the span_start key (T2; E06 review 2026-10-02, A3)
# The outliner writes locations.commentary.span_start beside explained (a first child inherits its
# parent's start, common.outline_doc.fill_span_starts). --key commentary.span_start reads a prediction
# there and the gold, which has no such field, at its explained line (sdp's text-span start).

INHERITED_DEV = 4  # first children among the gold's dev nodes: 1_1.1_2, 1_1.2_2.1_3, 2_1.1_2, 2_1.2_2.1_3


def chained(doc: dict) -> dict:
    from chinese_workflow.common.outline_doc import fill_span_starts

    return fill_span_starts(doc)


def test_span_start_key_identity_and_the_rows_without_inherited_predictions():
    m = run(chained(pred_of()), split="dev", key="commentary.span_start")
    s = m["settings"]
    assert (s["key"], s["mode"], s["split_locator"]) == ("commentary.span_start", "locator",
                                                         "commentary.explained")
    for t in (0, 1):
        r = m["rows"]["t=%d" % t]
        assert tpfpfn(r["s_f1"]) == (DEV_NODES, 0, 0) and tpfpfn(r["locator_only"]) == (DEV_NODES, 0, 0)
        w = r["without_span_start_inherited"]
        assert tpfpfn(w["s_f1"]) == (DEV_NODES - INHERITED_DEV, 0, 0)
        assert tpfpfn(w["f_f1"]) == (DEV_NODES - INHERITED_DEV, 0, 0)
        assert tpfpfn(w["locator_only"]) == (DEV_NODES - INHERITED_DEV, 0, 0)
        assert w["predictions_dropped"] == INHERITED_DEV
    assert any("explained line" in n and "E01 key" in n for n in m["disclosures"]["notes"])
    # the existing key's rows are as they were: no second block there
    assert "without_span_start_inherited" not in run(pred_of(), split="dev")["rows"]["t=0"]


def test_span_start_key_needs_the_field_on_predictions():
    """No silent fallback for a prediction: an outline without the pair has no key (item 2)."""
    m = run(pred_of(), split="dev", key="commentary.span_start")
    assert m["counts"]["pred"]["excluded"] == {"no_key": 15} and tpfpfn(row(m)) == (0, 0, DEV_NODES)
    assert any("have no commentary.span_start" in n for n in m["disclosures"]["notes"])


def test_keyless_truncated_gold_note_names_the_line_the_span_start_key_reads():
    """A truncated gold node without a line is outside the scoring tree and its predictions cannot be
    exempted (item 5). Under commentary.span_start the gold is read at its explained line (or its own
    span_start), so the note must not say it has no commentary.span_start line (final review 2026-10-03)."""
    g = gold_of()
    node(g, "2_1.2_2")["flags"] = ["truncated"]
    set_explained(g, "2_1.2_2", None)
    notes = {key: [n for n in run(chained(pred_of()), gold=copy.deepcopy(g), split="dev",
                                  key=key)["disclosures"]["notes"] if "truncated gold node" in n]
             for key in ("commentary.explained", "commentary.span_start")}
    assert len(notes["commentary.explained"]) == 1 and len(notes["commentary.span_start"]) == 1
    assert "have no commentary.explained line" in notes["commentary.explained"][0]
    note = notes["commentary.span_start"][0]
    assert "explained line" in note and "commentary.span_start line" not in note


def test_span_start_key_credits_a_first_child_taken_up_after_its_text_starts():
    """甲段's take-up line moves two lines on: a miss under the explained key, a match under the
    span_start key, where it stands on its parent's line (sdp keys it there)."""
    p = pred_of()
    set_explained(p, "2_1.1_2", "0001b03")
    assert tpfpfn(row(run(copy.deepcopy(p), split="dev"))) == (10, 1, 1)
    m = run(chained(p), split="dev", key="commentary.span_start")
    assert tpfpfn(row(m)) == (DEV_NODES, 0, 0)
    assert node(p, "2_1.1_2")["locations"]["commentary"] == {
        "announced": C + "0001b01", "explained": C + "0001b03",
        "span_start": C + "0001b01", "span_start_inherited": True}


def test_span_start_key_splits_a_prediction_by_its_span_start_line():
    """A first child taken up in the validation span under a dev parent starts, under sdp's rule, on
    its parent's dev line: counted in dev (FP here, the gold has no such child); under the explained
    key it is out of the dev split. Gold nodes keep the split of their explained line."""
    p = pred_of()
    add_child(p, "2_1.3_2", "2_1.3_2.1_3", "0002a10")  # 丙段 (dev, b14) gets a first child at a validation line
    assert run(copy.deepcopy(p), split="dev")["counts"]["pred"]["excluded"] == {"out_of_split": 5}
    m = run(chained(p), split="dev", key="commentary.span_start")
    assert tpfpfn(row(m)) == (DEV_NODES, 1, 0)
    assert m["counts"]["pred"]["excluded"] == {"out_of_split": 4}
    assert m["counts"]["gold"]["excluded"] == {"out_of_split": 4}
    assert m["diagnostics"]["fp_pred_ids"] == ["2_1.3_2.1_3"]
    # the one FP is itself an inherited first child: the rows without inherited predictions drop it
    w = m["rows"]["t=0"]["without_span_start_inherited"]
    assert tpfpfn(w["s_f1"]) == (DEV_NODES - INHERITED_DEV, 0, 0)
    assert w["predictions_dropped"] == INHERITED_DEV + 1  # the gold's four and this one


def test_span_start_key_judges_the_served_scope_on_the_span_start_line():
    g = gold_of()
    for n in g["nodes"]:
        if n["id"] == "2_1" or n["id"].startswith("2_1."):  # the unserved half: no anchors
            n["locations"]["commentary"]["explained"] = None
    p = pred_of()
    add_child(p, "1_1.2_2.2_3", "1_1.2_2.2_3.1_4", "0001b20")  # under 後段 (a10, served), taken up unserved
    m = run(chained(p), gold=g, gold_id="synthetic-served", split="dev", key="commentary.span_start")
    assert tpfpfn(row(m)) == (5, 1, 0)  # it stands on a10: in scope, FP
    assert m["counts"]["pred"]["excluded"]["out_of_scoring_scope"] == 6
    assert m["counts"]["gold"]["excluded"]["no_key"] == 6


def test_span_start_key_reads_a_gold_at_its_own_span_start_where_it_has_one():
    g = gold_of()
    node(g, "2_1.3_2")["locations"]["commentary"].update(span_start=C + "0001b12",
                                                          span_start_inherited=False)
    assert tpfpfn(row(run(pred_of(), gold=g, split="dev"))) == (DEV_NODES, 0, 0)  # explained key: as before
    m = run(chained(pred_of()), gold=g, split="dev", key="commentary.span_start")
    assert tpfpfn(row(m)) == (10, 1, 1) and m["diagnostics"]["fn_gold_ids"] == ["2_1.3_2"]
    assert m["counts"]["gold"]["excluded"] == {"out_of_split": 4}  # its split still follows explained


def test_span_start_rows_are_consistent_under_random_perturbations():
    """Seeded (the shared generator; same perturbations as the inlined one the brief wrote)."""
    for p in _perturbed_preds(2, 40):
        m = run(chained(p), split="dev", key="commentary.span_start")
        for t in (0, 1):
            r = m["rows"]["t=%d" % t]
            s, w = r["s_f1"], r["without_span_start_inherited"]
            assert s["TP"] + s["FN"] == m["counts"]["gold"]["counted"]
            assert r["f_f1"]["TP"] <= s["TP"] <= r["locator_only"]["TP"]
            assert w["s_f1"]["TP"] <= s["TP"] and w["s_f1"]["FP"] <= s["FP"]
            assert w["s_f1"]["FN"] == s["FN"]
            assert w["predictions_dropped"] <= m["counts"]["pred"]["counted"]


# ------------------------------- attachment-tolerant diagnostics (review of E06, 2026-10-02, A2)
# One synthetic gold of 9 nodes (lines a01..a11; 1.2 and its first child share a04, a same-line
# chain) and four controls built from it: gold, one-slip (the root's second child 1.2 nested under
# its first child 1.1, subtree relevelled), flat (every node at level 1 under the virtual root),
# half (every other leaf dropped). Each control has a known reading of the triple.


def _gold9() -> dict:
    return syn_doc(syn("1", None, 1, 1), syn("1.1", "1", 2, 2), syn("1.2", "1", 2, 4),
                   syn("1.2.1", "1.2", 3, 4), syn("1.2.2", "1.2", 3, 7),
                   syn("1.2.2.1", "1.2.2", 4, 7), syn("1.2.2.2", "1.2.2", 4, 8),
                   syn("1.2.3", "1.2", 3, 9), syn("1.3", "1", 2, 11))


def _one_slip(doc: dict) -> dict:
    p = copy.deepcopy(doc)
    for n in p["nodes"]:
        if n["id"] == "1.2":
            n["parent_id"] = "1.1"
        if n["id"] == "1.2" or n["id"].startswith("1.2."):
            n["level"] += 1
    return p


def _flat(doc: dict) -> dict:
    p = copy.deepcopy(doc)
    for n in p["nodes"]:
        n["parent_id"], n["level"] = None, 1
    return p


def _half(doc: dict) -> dict:
    p = copy.deepcopy(doc)
    parents = {n["parent_id"] for n in p["nodes"]}
    leaves = [n["id"] for n in p["nodes"] if n["id"] not in parents]
    p["nodes"] = [n for n in p["nodes"] if n["id"] not in set(leaves[::2])]
    return p


def _triple(m: dict, t: int) -> tuple:
    r = m["rows"]["t=%d" % t]
    return r["ancestor_consistent"], r["reanchor"], r["depth_offset_hist"]


def test_attachment_diagnostics_gold_against_itself_is_one_with_no_anchors():
    g = _gold9()
    m = syn_run(copy.deepcopy(g), g)
    for t in (0, 1):
        ac, ra, dh = _triple(m, t)
        assert ac["available"] and ac["F"] == 1.0 and ac["TP"] == 9 and ac["mapped_pairs"] == 9
        assert ac["forest"] == {"pred": 9, "gold": 9}
        assert ra["F"] == 1.0 and ra["anchors"] == 0
        assert dh["pairs"] == 9 and dh["hist"] == {"0": 9} and dh["mode"] == "0"
        assert dh["share_at_mode"] == 1.0 and dh["share_within_1_of_mode"] == 1.0
    assert m["settings"]["diagnostic_forest_cap"] == sc.AC_MAX_FOREST_NODES


def test_attachment_diagnostics_one_slip_is_high_with_one_anchor_and_mode_plus_one():
    """The root's second child (6 of 9 nodes) nested under the first: S-F1 keeps 3 pairs; the
    ancestor-consistent mapping gives up only 1.1 (8 of 9); one re-anchor recovers everything; the
    slipped subtree reads as the +1 mode of the histogram."""
    g = _gold9()
    m = syn_run(_one_slip(g), g)
    assert tpfpfn(row(m)) == (3, 6, 6)
    for t in (0, 1):
        ac, ra, dh = _triple(m, t)
        assert tpfpfn(ac) == (8, 1, 1) and ac["F"] == round(16 / 18, 6) and ac["mapped_pairs"] == 8
        assert tpfpfn(ra) == (9, 0, 0) and ra["F"] == 1.0 and ra["anchors"] == 1
        assert dh["hist"] == {"0": 3, "+1": 6} and dh["mode"] == "+1"
        assert dh["share_at_mode"] == round(6 / 9, 6) and dh["share_within_1_of_mode"] == 1.0


def test_attachment_diagnostics_flat_prediction_is_below_one_slip_and_reanchors_every_node():
    """The gameability caveat: a flat list still maps the 6 leaves (AC-F1 0.667, below one-slip's
    0.889), but every node but the root is a re-anchor and the offsets spread over -3..0. AC-F1
    is read only beside anchors and the histogram."""
    g = _gold9()
    m = syn_run(_flat(g), g)
    assert tpfpfn(row(m)) == (1, 8, 8)
    ac, ra, dh = _triple(m, 0)
    assert tpfpfn(ac) == (6, 3, 3) and ac["F"] == round(12 / 18, 6)
    assert ac["F"] < _triple(syn_run(_one_slip(g), g), 0)[0]["F"]
    assert ra["anchors"] == 8 and ra["F"] == 1.0  # every counted node but the root (paired top-down)
    assert dh["pairs"] == 9 and dh["hist"] == {"-3": 2, "-2": 3, "-1": 3, "0": 1}
    assert dh["mode"] == "-1" and dh["share_at_mode"] == round(3 / 9, 6)


def test_attachment_diagnostics_dropped_leaves_leave_the_triple_equal_to_s_f1():
    """Deletions only (3 of 6 leaves dropped): nothing is mis-attached, so all three F agree with
    S-F1 (0.8), no anchor is used and every offset is 0."""
    g = _gold9()
    m = syn_run(_half(g), g)
    assert tpfpfn(row(m)) == (6, 0, 3) and row(m)["F"] == 0.8
    for t in (0, 1):
        ac, ra, dh = _triple(m, t)
        assert ac["F"] == ra["F"] == row(m, t)["F"] == 0.8
        assert ra["anchors"] == 0 and dh["hist"] == {"0": 6} and dh["share_at_mode"] == 1.0


def test_attachment_diagnostics_are_skipped_above_the_forest_cap():
    """301 + 301 forest nodes exceed AC_MAX_FOREST_NODES (600): the triple reports unavailable
    with the size; S-F1 is untouched."""
    big = syn_doc(syn("1", None, 1, 1), *[syn("1.%d" % k, "1", 2, 2 + k % 27) for k in range(300)])
    m = syn_run(copy.deepcopy(big), big)
    assert row(m)["F"] == 1.0 and row(m)["TP"] == 301
    for block in _triple(m, 0):
        assert block["available"] is False
        assert "602 nodes exceeds AC_MAX_FOREST_NODES = 600" in block["reason"]


def test_attachment_diagnostics_in_structure_mode_pair_on_headings():
    """Structure mode has no lines: a pair needs equal headings; the forest keeps document order.
    丙 and its child 丁 nested one level too deep: the mapping drops 乙, one anchor recovers both."""
    g = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙"),
                syn("1.2", "1", 2, heading="丙"), syn("1.2.1", "1.2", 3, heading="丁"))
    p = syn_doc(syn("1", None, 1, heading="甲"), syn("1.1", "1", 2, heading="乙"),
                syn("1.1.1", "1.1", 3, heading="丙"), syn("1.1.1.1", "1.1.1", 4, heading="丁"),
                status="prediction")
    r = syn_run(p, g, key="structure")["rows"]["structure"]
    assert tpfpfn(r["s_f1"]) == (2, 2, 2)
    assert tpfpfn(r["ancestor_consistent"]) == (3, 1, 1)
    assert r["reanchor"]["anchors"] == 1 and r["reanchor"]["F"] == 1.0
    assert r["depth_offset_hist"]["hist"] == {"0": 2, "+1": 2}


def test_attachment_diagnostics_sit_beside_the_span_start_rows():
    """Under commentary.span_start (A3) the triple joins the without-inherited block on every row,
    and it reads the same key lines as S-F1 does."""
    m = run(chained(pred_of()), split="dev", key="commentary.span_start")
    for t in (0, 1):
        r = m["rows"]["t=%d" % t]
        ac, ra, dh = _triple(m, t)
        assert "without_span_start_inherited" in r
        assert tpfpfn(ac) == (DEV_NODES, 0, 0) and tpfpfn(ra) == (DEV_NODES, 0, 0)
        assert ra["anchors"] == 0 and dh["hist"] == {"0": DEV_NODES}


def test_attachment_diagnostics_exempt_under_truncated_is_neither_tp_nor_fp():
    """EVAL-SETS item 5 for the triple: a prediction under a matched truncated gold node (no
    coverage_spans) is exempt from S-F1's FP and likewise from AC-F1's and reanchor's."""
    g = gold_of()
    drop(g, "2_1.2_2.1_3")
    drop(g, "2_1.2_2.2_3")
    node(g, "2_1.2_2")["flags"] = ["truncated"]
    m = run(pred_of(), gold=g, split="dev")
    r = m["rows"]["t=0"]
    assert tpfpfn(r["s_f1"]) == (9, 0, 0) and r["exempt_under_truncated"] == 2
    assert tpfpfn(r["ancestor_consistent"]) == (9, 0, 0) and tpfpfn(r["reanchor"]) == (9, 0, 0)
    assert r["depth_offset_hist"]["pairs"] == 9


def test_attachment_diagnostics_maximise_counted_pairs_before_all_pairs():
    """Review of Task 3 (Important 1): the mapping maximises both-counted pairs first. Prediction
    A_p (counted, a02) | B_p (a03) > C_p (a04) > D_p (counted, a10) against gold A_g (counted, a02)
    > Y_g (a03) > Z_g (a04) > W_g (counted, a20): B_p, C_p and Y_g, Z_g lie outside the coverage
    spans (uncounted ancestors); D_p and W_g are counted. Pairing B_p-Y_g and C_p-Z_g gives two pairs and no counted one;
    S-F1 pairs A_p-A_g (TP 1, both counted) and, A_p being no ancestor of B_p, excludes B_p-Y_g.
    The counted-first mapping keeps A_p-A_g, so AC-TP cannot fall below the both-counted S-F1 TP."""
    def at(line, nid, parent, level):
        return syn(nid, parent, level, line)

    gold = syn_doc(at(2, "A", None, 1), at(3, "Y", "A", 2), at(4, "Z", "Y", 3), at(20, "W", "Z", 4))
    gold["metadata"]["coverage_spans"] = [
        {"node_id": None, "heading_src": None, "max_level": None, "root_text": None,
         "commentary": {"start": L7[a - 1], "end": L7[b - 1]}} for a, b in ((1, 2), (10, 10), (20, 20))]
    pred = syn_doc(at(2, "a", None, 1), at(3, "b", None, 1), at(4, "c", "b", 2), at(10, "d", "c", 3))
    m = syn_run(pred, gold)
    assert m["counts"]["pred"]["counted"] == 2 and m["counts"]["gold"]["counted"] == 2
    for t in (0, 1):
        r = m["rows"]["t=%d" % t]
        ac = r["ancestor_consistent"]
        assert r["s_f1_both_counted"]["TP"] == 1
        assert ac["TP"] >= r["s_f1_both_counted"]["TP"]
        assert tpfpfn(ac) == (1, 1, 1) and ac["mapped_pairs"] == 1
        assert ac["forest"] == {"pred": 4, "gold": 4}
        assert tpfpfn(r["reanchor"]) == (1, 1, 1) and r["reanchor"]["anchors"] == 0
    # the recurrence itself, on the forests as children maps (ancestors included): (pairs, counted)
    line = {"a": 2, "b": 3, "c": 4, "d": 100, "A": 2, "Y": 3, "Z": 4, "W": 200}
    kp = {None: ("a", "b"), "a": (), "b": ("c",), "c": ("d",), "d": ()}
    kg = {None: ("A",), "A": ("Y",), "Y": ("Z",), "Z": ("W",), "W": ()}
    assert sc._ac_mapping(kp, kg, lambda p, g: line[p] == line[g], {"a", "d"}, {"A", "W"}) == (1, 1)


def test_attachment_diagnostics_report_a_recursion_overflow_as_unavailable():
    """Review of Task 3 (Important 2): the recurrence recurses once per forest node (about twice on
    Python 3.11, where the lru_cache wrapper costs a frame), so a forest under the cap can overflow
    the stack; attachment() reports that as the triple unavailable, as it does the cap, instead of
    aborting the score. Forced on any Python by lowering the limit around a 60 + 60 flat forest."""
    big = syn_doc(*[syn("n%d" % k, None, 1, 1 + k % 27) for k in range(60)])
    depth, frame = 0, sys._getframe()
    while frame is not None:
        depth, frame = depth + 1, frame.f_back
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(depth + 80)  # room for score() down to the recurrence, not for the recurrence
    try:
        m = syn_run(copy.deepcopy(big), big)
    finally:
        sys.setrecursionlimit(limit)
    assert row(m)["F"] == 1.0 and row(m)["TP"] == 60  # S-F1 is untouched
    for t in (0, 1):
        for block in _triple(m, t):
            assert block["available"] is False
            assert "120 nodes" in block["reason"] and "recursion limit" in block["reason"]
            assert "AC_MAX_FOREST_NODES" not in block["reason"]  # not the cap's message
    assert sc.AC_MAX_FOREST_NODES > 120  # the forest is under the cap: the guard is the recursion one


# ------------------------------------------------------------------------------ gold-backed checks


def _blank(doc: dict) -> dict:
    """Headings, notes and evidence blanked (locator scoring does not read them)."""
    for n in doc["nodes"]:
        n.update(heading_src="", heading_en="", evidence="", notes=[])
    md = doc["metadata"]
    for k in ("coverage", "coverage_spans", "split_notes", "anomalies"):
        md.pop(k, None)
    md.update(gold_status="prediction", seeded_by=None)
    return doc


def _kuiji_dev_prediction(registry: dict) -> dict:
    """Levels 1-2 of the Kuiji gold plus the subtree whose root opens the T1723 dev span."""
    ds = reg.dataset(registry, "kuiji-xuanzan")
    gold = read_json(REPO / ds["path"])
    dev_start = next(s for split, s, _ in reg.split_spans(registry, "T1723") if split == "dev")
    root = next(n["id"] for n in gold["nodes"] if n["level"] == 2
                and sc.locator(n, "commentary.explained") == dev_start)
    keep = [n for n in gold["nodes"]
            if n["level"] <= 2 or n["id"] == root or n["id"].startswith(root + ".")]
    return _blank({"metadata": gold["metadata"], "nodes": keep})


def test_kuiji_dev_subtree_scores_one(capsys):
    registry = reg.load_registry()
    m = score(_kuiji_dev_prediction(registry), "kuiji-xuanzan", split="dev")
    dev_nodes = reg.dataset(registry, "kuiji-xuanzan")["counts"]["by_split"]["dev"]["nodes"]
    assert tpfpfn(row(m)) == (dev_nodes, 0, 0) and row(m)["F"] == 1.0
    if m["rows"]["t=1"]["available"]:
        assert row(m, 1)["F"] == 1.0
    assert m["disclosures"]["headline"] is False
    assert m["disclosures"]["gold_status"] == "draft-unreviewed" and m["disclosures"]["seeded_by"]
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_cli_writes_metrics_for_kuiji_dev(tmp_path, capsys):
    from chinese_workflow.common.jsonio import write_json

    pred = write_json(_kuiji_dev_prediction(reg.load_registry()), tmp_path / "pred.json")
    out = tmp_path / "metrics.json"
    assert sc.main(["--pred", str(pred), "--gold", "kuiji-xuanzan", "--split", "dev",
                    "--out", str(out)]) == 0
    m = read_json(out)
    assert m["rows"]["t=0"]["s_f1"]["F"] == 1.0 and m["settings"]["split"] == "dev"
    line = capsys.readouterr().out
    assert "S-F1 1.000" in line and "headline false" in line
    assert sc.main(["--pred", str(pred), "--gold", "kuiji-xuanzan", "--split", "test"]) == 2


SDP_T1718 = REPO / "data" / "raw" / "dila-sdp" / "gold" / "T1718.zhiyi-wenju-sdp.outline.json"


@pytest.mark.skipif(not SDP_T1718.exists(), reason="eval-only sdp gold absent (data/raw/)")
def test_sdp_t1718_dev_nodes_score_one(capsys):
    registry = reg.load_registry()
    gold = read_json(SDP_T1718)
    keep = []
    for n in gold["nodes"]:
        ex = sc.locator(n, "commentary.explained")
        if ex and reg.split_of(registry, "T1718", ex) == "dev":
            keep.append(n)
    pred = _blank({"metadata": copy.deepcopy(gold["metadata"]), "nodes": copy.deepcopy(keep)})
    del gold
    m = score(pred, "sdp-T1718-zhiyi-wenju", split="dev")
    dev_nodes = reg.dataset(registry, "sdp-T1718-zhiyi-wenju")["counts"]["by_split"]["dev"]["nodes"]
    assert tpfpfn(row(m)) == (dev_nodes, 0, 0) and row(m)["F"] == 1.0
    assert m["disclosures"]["gold_status"] == "imported-unchecked"
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_structure_mode_on_a_split_gold_needs_frozen():
    """Review of 2026-09-27: structure mode cannot restrict a split-scoped gold to one split, so on the
    Kuiji gold (test and reserve answer keys inside) it is refused without --frozen."""
    with pytest.raises(SplitViolation):
        score({"metadata": {}, "nodes": []}, "kuiji-xuanzan", key="structure")
