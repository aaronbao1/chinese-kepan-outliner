"""Tests for chinese_workflow.outline.repair (docs/outliner-design.md §5.0 'Degradation'; E06 review B5).

Synthetic: mutations of tests/fixtures/outline-zh/minimal.json, the recipes test_outline_schema.py uses to
provoke [sibling-order], [child-outside-parent] and [cbeta-order]; every repaired document must validate.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from chinese_workflow.common import outline_doc
from chinese_workflow.outline import repair

REPO = Path(__file__).resolve().parents[2]
MINIMAL = REPO / "tests/fixtures/outline-zh/minimal.json"


@pytest.fixture
def minimal():
    doc = json.loads(MINIMAL.read_text(encoding="utf-8"))
    assert outline_doc.validate(doc).passed()
    return doc


def _errors(doc):
    return outline_doc.validate(doc).errors


def _node(doc, nid):
    return next(n for n in doc["nodes"] if n["id"] == nid)


def _to_self_outlining(doc):
    """The fixture re-read as a self-outlining text (as test_outline_schema._to_self_outlining)."""
    meta = doc["metadata"]
    meta["outline_mode"], meta["commentary_id"] = "self-outlining", None
    meta["source_document"].update(kind="root-text", text_id="T99n9999")
    for n in doc["nodes"]:
        com = n["locations"]["commentary"]
        for key in ("announced", "explained"):
            if com and com[key]:
                com[key] = com[key].replace("T99n9998", "T99n9999")
    return doc


def _append_child(doc, parent_id, child):
    """Append a draft child under parent_id and renumber (ids, order, sibling_index, counts)."""
    drafts = outline_doc.to_drafts(doc)
    stack = list(drafts)
    while stack:
        d = stack.pop()
        if d["_orig_id"] == parent_id:
            d["children"].append(child)
            break
        stack.extend(d["children"])
    doc["nodes"], _ = outline_doc.number_tree(drafts)
    return outline_doc.refresh_counts(doc)


def _inferred(start, end, explained):
    return {"heading_src": "", "heading_en": "", "origin": "inferred", "confidence": 0.5,
            "evidence": "synthetic cue", "node_class": "sutra-span", "source_language": "lzh",
            "locations": {"scheme": "cbeta-kepan",
                          "commentary": {"announced": None, "explained": explained, "raw": ""},
                          "root_text": {"start": start, "end": end, "basis": "inferred", "end_basis": None,
                                        "raw": ""}},
            "children": []}


def test_sibling_root_spans_out_of_order_demote_the_younger(minimal):
    a, b = minimal["nodes"][5]["locations"], minimal["nodes"][6]["locations"]  # 3_1.1_2, 3_1.2_2
    a["root_text"], b["root_text"] = b["root_text"], a["root_text"]
    errors = _errors(minimal)
    assert {f.code for f in errors} == {"sibling-order"}
    repairs = repair.repair(minimal, errors)
    assert repairs == [{"kind": "demoted", "node_id": "3_1.2_2", "code": "sibling-order",
                        "locator": "root_text.start", "was": "T99n9999_p0001b03"}]
    n = _node(minimal, "3_1.2_2")
    # the swap gave 3_1.2_2 its elder's span, raw included; the raw lemma survives the demotion
    assert n["locations"]["root_text"] == {"start": None, "end": None, "basis": "lemma", "raw": "經「爾時世尊」"}
    assert "unmapped" in n["flags"]
    assert n["notes"][-1] == "demoted: sibling-order, was T99n9999_p0001b03"
    assert _node(minimal, "3_1.1_2")["locations"]["root_text"]["start"] == "T99n9999_p0002b06"
    assert outline_doc.validate(minimal).passed()


@pytest.mark.parametrize("old, kept", [("interpolated", "lemma"), ("lemma", "lemma"), ("inferred", "inferred"),
                                       ("chapter", "chapter")])
def test_a_demoted_span_takes_the_basis_anchor_gives_an_unplaced_stub(minimal, old, kept):
    """Final review 2026-10-03: repair and anchor.write null a span by the same rule
    (anchor.nulled_basis): a derived basis becomes `lemma`, any other basis is kept."""
    a, b = minimal["nodes"][5]["locations"], minimal["nodes"][6]["locations"]
    a["root_text"], b["root_text"] = b["root_text"], a["root_text"]
    b["root_text"]["basis"] = old
    repair.repair(minimal, _errors(minimal))
    rt = _node(minimal, "3_1.2_2")["locations"]["root_text"]
    assert (rt["start"], rt["end"], rt["basis"]) == (None, None, kept)
    assert rt["raw"] == "經「爾時世尊」"


def test_self_mode_explained_out_of_order_loses_its_position(minimal):
    _to_self_outlining(minimal)
    minimal["nodes"][6]["locations"]["commentary"]["explained"] = "T99n9999_p0001c03"  # elder: p0001c04
    errors = _errors(minimal)
    assert {f.code for f in errors} == {"sibling-order"}
    repairs = repair.repair(minimal, errors)
    assert repairs == [{"kind": "demoted", "node_id": "3_1.2_2", "code": "sibling-order",
                        "locator": "commentary.explained", "was": "T99n9999_p0001c03"}]
    n = _node(minimal, "3_1.2_2")
    assert n["locations"]["commentary"]["explained"] is None
    assert n["locations"]["commentary"]["announced"] == "T99n9999_p0001c03"
    assert n["notes"][-1] == "demoted: sibling-order, was T99n9999_p0001c03"
    assert outline_doc.validate(minimal).passed()


def test_inferred_siblings_never_displace_an_explicit_one(minimal):
    """Two inferred siblings in order among themselves but before the explicit one: the plain longest
    run would keep the two and demote the explicit node; the weights keep the explicit node."""
    e = _node(minimal, "3_1.1_2")
    e["locations"]["root_text"].update(start="T99n9999_p0002b06", end="T99n9999_p0002c10")
    i1 = _node(minimal, "3_1.2_2")
    i1.update(origin="inferred", confidence=0.5)
    i1["locations"]["root_text"].update(start="T99n9999_p0001b03", end="T99n9999_p0001b04")
    _append_child(minimal, "3_1", _inferred("T99n9999_p0001b05", "T99n9999_p0002b05", "T99n9998_p0002a12"))
    errors = _errors(minimal)
    assert [f.where for f in errors] == ["3_1.2_2"] and errors[0].code == "sibling-order"
    repairs = repair.repair(minimal, errors)
    assert [r["node_id"] for r in repairs] == ["3_1.2_2", "3_1.3_2"]
    assert _node(minimal, "3_1.1_2")["locations"]["root_text"]["start"] == "T99n9999_p0002b06"
    assert outline_doc.validate(minimal).passed()


@pytest.mark.parametrize("with_inferred", [False, True])
def test_an_inferred_sibling_does_not_decide_which_explicit_sibling_is_kept(minimal, with_inferred):
    """Review of Task 9: with explicit E1 (3_1.1_2) at p0002b06 and E2 (3_1.2_2) at p0001b03, E2 is the younger
    and is demoted; an inferred sibling at p0001b05 that fits after E2 used to make E1 the one demoted.
    The chain key is lexicographic (explicit count, earlier explicit nodes, inferred count): the inferred
    node never changes which explicit node stays, and is itself demoted here."""
    a, b = minimal["nodes"][5]["locations"], minimal["nodes"][6]["locations"]
    a["root_text"], b["root_text"] = b["root_text"], a["root_text"]
    expected = ["3_1.2_2"]
    if with_inferred:
        _append_child(minimal, "3_1", _inferred("T99n9999_p0001b05", "T99n9999_p0002b05", "T99n9998_p0002a12"))
        expected = ["3_1.2_2", "3_1.3_2"]
    errors = _errors(minimal)
    assert {f.code for f in errors} == {"sibling-order"}
    repairs = repair.repair(minimal, errors)
    assert [r["node_id"] for r in repairs] == expected
    assert _node(minimal, "3_1.1_2")["locations"]["root_text"]["start"] == "T99n9999_p0002b06"
    assert outline_doc.validate(minimal).passed()


def test_more_inferred_nodes_win_only_among_equal_explicit_chains(minimal):
    """Two explicit siblings in order and two inferred ones that fit before them: the explicit pair stays
    (explicit count first), the inferred ones go."""
    _append_child(minimal, "3_1", _inferred("T99n9999_p0001b03", "T99n9999_p0001b04", "T99n9998_p0002a12"))
    _append_child(minimal, "3_1", _inferred("T99n9999_p0001b04", "T99n9999_p0001b05", "T99n9998_p0002a13"))
    errors = _errors(minimal)
    assert {f.code for f in errors} == {"sibling-order"}
    repairs = repair.repair(minimal, errors)
    assert [r["node_id"] for r in repairs] == ["3_1.3_2", "3_1.4_2"]
    assert outline_doc.validate(minimal).passed()


def test_explicit_child_past_parent_end_raises_the_parent(minimal):
    minimal["nodes"][6]["locations"]["root_text"]["end"] = "T99n9999_p0002c15"  # 3_1 ends at p0002c10
    errors = _errors(minimal)
    assert {f.code for f in errors} == {"child-outside-parent"}
    repairs = repair.repair(minimal, errors)
    assert repairs == [{"kind": "raised", "node_id": "3_1", "code": "child-outside-parent",
                        "field": "root_text.end", "was": "T99n9999_p0002c10", "now": "T99n9999_p0002c15"}]
    assert _node(minimal, "3_1")["notes"][-1] == "raised: child-outside-parent, root_text.end was T99n9999_p0002c10"
    assert outline_doc.validate(minimal).passed()


def test_inferred_child_past_parent_end_is_clipped(minimal):
    n = minimal["nodes"][6]
    n.update(origin="inferred", confidence=0.5)
    n["locations"]["root_text"]["end"] = "T99n9999_p0002c15"
    repairs = repair.repair(minimal, _errors(minimal))
    assert repairs == [{"kind": "clipped", "node_id": "3_1.2_2", "code": "child-outside-parent",
                        "field": "root_text.end", "was": "T99n9999_p0002c15", "now": "T99n9999_p0002c10"}]
    assert _node(minimal, "3_1")["locations"]["root_text"]["end"] == "T99n9999_p0002c10"
    assert outline_doc.validate(minimal).passed()


def test_child_before_parent_start_is_clipped(minimal):
    minimal["nodes"][1]["locations"]["root_text"]["start"] = "T99n9999_p0001a02"  # 2_1; child 2_1.1_2 starts a01
    errors = _errors(minimal)
    assert {f.code for f in errors} == {"child-outside-parent"}
    repairs = repair.repair(minimal, errors)
    assert repairs == [{"kind": "clipped", "node_id": "2_1.1_2", "code": "child-outside-parent",
                        "field": "root_text.start", "was": "T99n9999_p0001a01", "now": "T99n9999_p0001a02"}]
    assert outline_doc.validate(minimal).passed()


def test_inverted_span_is_nulled(minimal):
    span = minimal["nodes"][2]["locations"]["root_text"]  # 2_1.1_2
    span["start"], span["end"] = span["end"], span["start"]
    errors = _errors(minimal)
    assert {f.code for f in errors} == {"cbeta-order"}
    repairs = repair.repair(minimal, errors)
    assert repairs == [{"kind": "nulled", "node_id": "2_1.1_2", "code": "cbeta-order",
                        "was": "T99n9999_p0001a03..T99n9999_p0001a01"}]
    n = _node(minimal, "2_1.1_2")
    assert n["locations"]["root_text"]["start"] is None and "unmapped" in n["flags"]
    assert n["notes"][-1] == "nulled: cbeta-order, was T99n9999_p0001a03..T99n9999_p0001a01"
    assert outline_doc.validate(minimal).passed()


def _swap_siblings(doc):  # [sibling-order]
    a, b = doc["nodes"][5]["locations"], doc["nodes"][6]["locations"]
    a["root_text"], b["root_text"] = b["root_text"], a["root_text"]


def _child_past_parent(doc):  # [child-outside-parent]
    doc["nodes"][6]["locations"]["root_text"]["end"] = "T99n9999_p0002c15"


def _invert_span(doc):  # [cbeta-order]
    span = doc["nodes"][2]["locations"]["root_text"]
    span["start"], span["end"] = span["end"], span["start"]


@pytest.mark.parametrize("mutate", [_swap_siblings, _child_past_parent, _invert_span])
def test_repairing_twice_with_the_same_findings_changes_nothing(minimal, mutate):
    """Review of Task 9: stale findings (the validator was not re-run between two repair() calls) must not
    add a second note or entry; _null_span used to log 'nulled ... was None..None'."""
    mutate(minimal)
    errors = _errors(minimal)
    assert repair.repair(minimal, errors)
    after_first = copy.deepcopy(minimal)
    assert repair.repair(minimal, errors) == []
    assert minimal == after_first


def test_non_local_errors_are_left_alone(minimal):
    del minimal["nodes"][0]["sibling_index"]
    errors = _errors(minimal)
    assert errors and not any(repair.is_local(f) for f in errors)
    assert repair.repair(minimal, errors) == []
    assert not outline_doc.validate(minimal).passed()


def test_a_valid_document_is_untouched(minimal):
    before = copy.deepcopy(minimal)
    assert repair.repair(minimal, _errors(minimal)) == []
    assert minimal == before


# ---- the pipeline's validate -> repair -> re-validate round (outline.pipeline._validate_and_repair)


def test_pipeline_round_leaves_no_degraded_key_on_a_valid_document(minimal):
    from chinese_workflow.outline.pipeline import _validate_and_repair

    report: dict = {}
    assert _validate_and_repair(minimal, report, "before-resolver").passed()
    assert report == {}


def test_pipeline_round_records_the_first_pass_errors_and_the_repairs(minimal):
    from chinese_workflow.outline.pipeline import _validate_and_repair

    minimal["nodes"][6]["locations"]["root_text"]["end"] = "T99n9999_p0002c15"
    report: dict = {}
    assert _validate_and_repair(minimal, report, "after-resolver").passed()
    (entry,) = report["degraded"]
    assert entry["stage"] == "after-resolver"
    assert [f.startswith("  error   [child-outside-parent] 3_1.2_2: ") for f in entry["errors"]] == [True]
    assert [r["kind"] for r in entry["repairs"]] == ["raised"]


def test_pipeline_round_repairs_what_it_covers_and_returns_what_it_does_not(minimal):
    """A hard error beside a local one: the local one is repaired and reported, the hard one stays in the
    returned Report (the build then raises 'failed validation after repair')."""
    from chinese_workflow.outline.pipeline import _validate_and_repair

    del minimal["nodes"][0]["sibling_index"]
    minimal["nodes"][6]["locations"]["root_text"]["end"] = "T99n9999_p0002c15"
    report: dict = {}
    val = _validate_and_repair(minimal, report, "before-resolver")
    assert not val.passed() and not any(repair.is_local(f) for f in val.errors)
    assert [r["code"] for e in report["degraded"] for r in e["repairs"]] == ["child-outside-parent"]
