"""outline.pipeline.build over a span whose first line lies inside a 品 whose heading line is before the span
(E06 review §1 item 6, §2 B2): tier 1 carries the 品 as an editorial ancestor, tier 2's drafts attach under
it, and the tree below the pin is the one the whole-span build gives. Offline: the committed T1723 / T0262
陀羅尼品 excerpts (the T1723 dev span, tests/fixtures/cbeta-xml-p5/).
"""

from __future__ import annotations

import json
from pathlib import Path

from chinese_workflow.common import outline_doc
from chinese_workflow.outline import classify
from chinese_workflow.outline.pipeline import OutlineConfig, build

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures" / "cbeta-xml-p5"
XML = {"T34n1723": str(FIX / "T34n1723-excerpt-p0850a19-p0850b19.xml"),
       "T09n0262": str(FIX / "T09n0262-excerpt-p0058b08-p0059b27.xml")}
CARRIED = {"anchor": "T34n1723_p0850a20", "pin_start": "T34n1723_p0850a19", "end": "T34n1723_p0850b19",
           "heading_src": "陀羅尼品", "part_type": "品", "level": 1}


def _cfg(span):
    return OutlineConfig(mode="sutra", root="T09n0262", commentary="T34n1723", scheme_id="kuiji-xuanzan",
                         span=span, source="tier2", target_role="commentary", xml=dict(XML))


def _below(doc: dict) -> list:
    """The nodes below the pin: ids, headings, classes, locations without the span_start pair (the pair
    differs by design: a carried editorial pin gives its first child no start to inherit)."""
    def loc(n):
        out = json.loads(json.dumps(n["locations"]))
        for k in ("span_start", "span_start_inherited"):
            out["commentary"].pop(k, None)
        return out
    return [(n["id"], n["heading_src"], n["node_class"], loc(n)) for n in doc["nodes"][1:]]


def _pair(doc: dict, nid: str) -> tuple:
    com = next(n for n in doc["nodes"] if n["id"] == nid)["locations"]["commentary"]
    return com["span_start"], com["span_start_inherited"]


def test_span_build_from_the_second_line_keeps_the_pin_and_the_tree(tmp_path):
    whole = build(_cfg(None), tmp_path / "whole")
    part = build(_cfg(("T34n1723_p0850a20", "T34n1723_p0850b19")), tmp_path / "part")
    w, p = whole["doc"], part["doc"]
    assert w["metadata"]["node_count"] == 45 and p["metadata"]["node_count"] == 45
    pin_w, pin_p = w["nodes"][0], p["nodes"][0]
    assert pin_w["origin"] == "explicit" and pin_p["origin"] == "editorial"
    assert pin_p["heading_src"] == "陀羅尼品" and pin_p["part_type"] == "品"
    assert pin_p["notes"][0].startswith("pin carried from T34n1723_p0850a19")
    assert pin_p["locations"]["root_text"] == pin_w["locations"]["root_text"] == {
        "start": "T09n0262_p0058b08", "end": "T09n0262_p0059b27", "basis": "chapter", "end_basis": None}
    assert pin_p["locations"]["commentary"]["explained"] == "T34n1723_p0850a19"
    assert pin_p["flags"] == []
    assert _below(p) == _below(w)  # same ids, headings, classes, commentary lines and root spans
    # span starts (final review 2026-10-03, Important 1): the whole build's first child inherits the
    # explicit 品's line 850a19; the part build starts at 850a20, so under the carried editorial pin the
    # build's first child keeps its own line and its first children inherit that
    assert _pair(w, "1_1.1_2") == ("T34n1723_p0850a19", True)
    assert _pair(p, "1_1.1_2") == ("T34n1723_p0850a20", False)
    assert _pair(p, "1_1.1_2.1_3") == ("T34n1723_p0850a20", True)
    assert _pair(p, pin_p["id"]) == ("T34n1723_p0850a19", False)
    rep = part["report"]
    assert rep["tier1"] == {"drafts": 1, "pins": 1, "anomalies": [], "carried": [CARRIED]}
    assert whole["report"]["tier1"]["carried"] == []
    assert all(e["kind"] != "unknown-anchor" for e in rep["merge"])
    assert rep["validation"]["passed"] and outline_doc.validate(p).passed()
    assert rep["classify"] == [] and whole["report"]["classify"] == []  # no node names a 品 beyond this one
    # the carried pin has no position in the span's outlined text (its line is outside); its children do
    sidecar = json.loads(Path(part["paths"]["outlined_text"]).read_text(encoding="utf-8"))
    assert sidecar["unplaced"][:1] == [pin_p["id"]]
    assert sidecar["coverage"]["covered"] > 0


def _patched_cfg(tmp_path):
    """The span build over a copy of the excerpt in which one item label of 此初聖。有四 is replaced by the
    invented 三凡二品: T0262 has one 品 in its excerpt (the 陀羅尼品 the span covers), so the item is an
    unmapped node that names more 品 than its ancestor's span holds."""
    src = Path(XML["T34n1723"]).read_text(encoding="utf-8")
    old = "三結勝，四佛讚"
    assert src.count(old) == 1
    patched = tmp_path / "T34n1723-excerpt-patched.xml"
    patched.write_text(src.replace(old, "三凡二品，四佛讚"), encoding="utf-8")
    cfg = _cfg(("T34n1723_p0850a20", "T34n1723_p0850b19"))
    cfg.xml = {**XML, "T34n1723": str(patched)}
    return cfg


def test_classification_runs_on_the_repaired_document(tmp_path, monkeypatch):
    """The before-resolver validate-and-repair pass sees no classification; the classification is made on
    its result (a repair that nulls or clips a span would otherwise leave a stale one)."""
    from chinese_workflow.outline import pipeline

    seen = []
    real = pipeline._validate_and_repair

    def spy(doc, report, stage):
        seen.append((stage, any(classify.is_out_of_span(n) for n in doc["nodes"])))
        return real(doc, report, stage)

    monkeypatch.setattr(pipeline, "_validate_and_repair", spy)
    built = build(_patched_cfg(tmp_path), tmp_path / "out")
    assert seen == [("before-resolver", False)]
    assert len(built["report"]["classify"]) == 1
    assert sum(classify.is_out_of_span(n) for n in built["doc"]["nodes"]) == 1


def test_out_of_span_node_reaches_the_build_report_and_the_resolver_skip(tmp_path):
    """Merge level: `build` marks the node (report["classify"], the note), and the resolver, asked through
    the interactive adapter, lists it under skipped as out-of-span instead of putting it into its request."""
    from chinese_workflow.llm import LLMConfig

    cfg = _patched_cfg(tmp_path)
    cfg.source, cfg.resolver = "hybrid", {"adapter": "interactive"}
    built = build(cfg, tmp_path / "out", llm_config=LLMConfig(adapter="interactive", run_dir=tmp_path / "llm"))
    rep, doc = built["report"], built["doc"]
    [entry] = rep["classify"]
    node = next(n for n in doc["nodes"] if n["id"] == entry["node_id"])
    assert node["heading_src"] == "三凡二品" and "unmapped" in node["flags"]
    assert entry["kind"] == "out-of-span" and entry["detail"].startswith("凡二品 names 2 品")
    assert node["notes"][-1] == classify.OUT_OF_SPAN_NOTE % entry["detail"]
    assert [n["id"] for n in doc["nodes"] if classify.is_out_of_span(n)] == [node["id"]]
    task = rep["resolver"]["task_report"]
    assert rep["resolver"]["status"] == "pending interactive responses"
    assert [(s["node_id"], s["kind"]) for s in task["skipped"]] == [(node["id"], "out-of-span")]
    assert task["skipped"][0]["reason"] == node["notes"][-1]
    assert task["requests"] >= 1 and rep["validation"]["passed"]
