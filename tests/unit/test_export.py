"""Tests for chinese_workflow.export (knowledge-graph export v0, plan M9; design §8).

Round trips (export -> load -> the exported fields equal) on the SYNTHETIC fixture
tests/fixtures/outline-zh/minimal.json and on the part of the Kuiji gold a developer may read: levels
1-2 without notes plus the 陀羅尼品 subtree (dev span T34n1723_p0850a19..p0850b19), filtered
programmatically; no Kuiji content is printed (assertion messages carry node ids and counts only).
Also: URI stability across re-export and renumbering, the guards (eval-only, OOD and eval-only golds
of the registry, model-only nodes, test/reserve spans), determinism, and the BDRC terms against
data/raw/bdrc/owl-schema/core/bdo.ttl when that file is present.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from chinese_workflow.common import outline_doc
from chinese_workflow.common.jsonio import dumps, read_json, write_json
from chinese_workflow.common.lineheads import strip_offset
from chinese_workflow.common.splits import load_registry
from chinese_workflow.export import ExportRefused, export, load
from chinese_workflow.export.__main__ import main
from chinese_workflow.export.jsonld import check_source_path, context

REPO = Path(__file__).resolve().parents[2]
MINIMAL = REPO / "tests" / "fixtures" / "outline-zh" / "minimal.json"
KUIJI = REPO / "data" / "reference-outlines" / "T0262" / "kuiji-xuanzan" / "outline.json"
BDO_TTL = REPO / "data" / "raw" / "bdrc" / "owl-schema" / "core" / "bdo.ttl"
DHARANI = ("T34n1723_p0850a19", "T34n1723_p0850b19")  # dev span (data/eval-sets.json)


def _minimal() -> dict:
    """The synthetic fixture, made exportable in memory only: as committed it has no licence id and so
    is eval_only (the schema ties the two); the copy gets a synthetic SPDX LicenseRef and
    eval_only false, and still validates."""
    doc = read_json(MINIMAL)
    doc["metadata"]["eval_only"] = False
    doc["metadata"]["licence"]["id"] = "LicenseRef-synthetic-test"
    return doc


def _fields(n: dict) -> dict:
    """The fields the round trip must preserve (plan M9: lossless on the exported fields)."""
    locs = n.get("locations") or {}
    c, r = locs.get("commentary"), locs.get("root_text")
    return {
        "id": n["id"], "path": n["path"], "level": n["level"], "parent_id": n["parent_id"],
        "order": n["order"], "sibling_index": n["sibling_index"],
        "heading_src": n["heading_src"], "heading_en": n["heading_en"],
        "origin": n["origin"], "confidence": n.get("confidence"), "evidence": n.get("evidence", ""),
        "scheme": locs.get("scheme"), "locations_raw": locs.get("raw"),
        "commentary": None if c is None else {k: c.get(k) for k in
                                              ("announced", "explained", "raw", "text_id")},
        "root_text": None if r is None else {k: r.get(k) for k in
                                             ("start", "end", "basis", "end_basis", "raw",
                                              "text_id")},
        "child_count_announced": n.get("child_count_announced"),
        "extent_announced": n.get("extent_announced"),
        "flags": list(n.get("flags") or []), "display_label": n.get("display_label"),
        "node_class": n.get("node_class"), "part_type": n.get("part_type"),
        "source_node_id": n.get("source_node_id"), "scheme_id": n.get("scheme_id"),
    }


def _mismatches(doc: dict, loaded: dict) -> list:
    """Ids of nodes whose round-tripped fields differ (ids only: safe to print)."""
    before = {n["id"]: _fields(n) for n in doc["nodes"]}
    after = {n["id"]: _fields(n) for n in loaded["nodes"]}
    ids = sorted(set(before) | set(after))
    return [i for i in ids if before.get(i) != after.get(i)]


def _uris(graph: dict) -> dict:
    return {n["id"]: n["uri"] for n in load(graph)["nodes"]}


# ---------------------------------------------------------------------------------- round trips


def test_minimal_round_trip():
    doc = _minimal()
    graph, history = export(doc)
    loaded = load(graph)
    assert _mismatches(doc, loaded) == []
    meta = doc["metadata"]
    for key in ("root_text_id", "text_id", "scheme_id", "outline_mode", "commentary_id",
                "gold_status", "seeded_by", "cbeta_release", "source_file", "text_title_src",
                "text_title_en", "generated_by"):
        assert loaded["metadata"][key] == meta[key], key
    assert loaded["metadata"]["licence_id"] == meta["licence"]["id"]
    assert loaded["metadata"]["exported_node_count"] == len(doc["nodes"])
    # the inferred node keeps its confidence; the character offset survives (':4')
    by_id = {n["id"]: n for n in loaded["nodes"]}
    assert by_id["4_1"]["confidence"] == 0.6
    assert by_id["3_1.2_2"]["locations"]["commentary"]["explained"] == "T99n9998_p0002a11:4"
    assert len(history["outlines"]["T99n9999/synthetic-fixture"]["nodes"]) == len(doc["nodes"])


def test_shape_is_bdrc_style():
    graph, _ = export(_minimal())
    outline, nodes = graph["@graph"][0], [r for r in graph["@graph"] if "cw:origin" in r]
    assert outline["@type"] == "bdo:Outline"
    assert outline["bdo:outlineOf"].endswith("/work/T99n9999")
    assert outline["cw:schemeId"] == "synthetic-fixture"
    n = next(r for r in nodes if r["bdo:partTreeIndex"] == "3.2")
    assert n["bdo:partIndex"] == 2
    assert n["bdo:partType"] == "cw:nodeClass/sutra-span"
    assert {"@value": "後偈頌", "@language": "lzh"} in n["skos:prefLabel"]
    assert {"@value": "Verses", "@language": "en"} in n["skos:prefLabel"]
    loc = n["bdo:contentLocation"]
    assert loc["@type"] == "bdo:ContentLocation"
    assert loc["bdo:contentLocationStatementCBETA"] == "T99n9999_p0002b06"
    assert loc["cw:contentLocationEndStatementCBETA"] == "T99n9999_p0002c10"
    assert n["cw:commentaryExplained"]["bdo:contentLocationStatementCBETA"] == "T99n9998_p0002a11"
    assert n["cw:commentaryExplained"]["cw:charOffset"] == 4
    parent = next(r for r in nodes if r["bdo:partTreeIndex"] == "3")
    assert n["bdo:partOf"] == parent["@id"] and parent["bdo:partOf"] == outline["@id"]
    # the catalogue tree stays apart: works are referenced, never described in this graph
    assert not [r for r in graph["@graph"] if "/work/" in r.get("@id", "")]


def test_part_type_wins_over_node_class_and_round_trips():
    doc = _minimal()
    doc["nodes"][1]["part_type"] = "品"
    graph, _ = export(doc)
    node = next(r for r in graph["@graph"] if r.get("bdo:partTreeIndex") == "2")
    assert node["bdo:partType"] == "cw:partType/%E5%93%81"
    vocab = next(r for r in graph["@graph"] if r["@id"] == "cw:partType/%E5%93%81")
    assert vocab["@type"] == "bdo:PartType"
    assert _mismatches(doc, load(graph)) == []


def _kuiji_allowed() -> dict:
    """Levels 1-2 of the Kuiji gold (notes dropped) + the 陀羅尼品 subtree (commentary.explained in
    the dev span), as a valid zh-kepan document. Built programmatically; nothing is printed. Metadata
    keeps the zh-kepan fields only (no coverage, split notes or header notes: data/EVAL-SETS.md,
    'Do not open while developing')."""
    gold = read_json(KUIJI)
    lo, hi = DHARANI

    def in_dharani(n):
        exp = strip_offset(((n.get("locations") or {}).get("commentary") or {}).get("explained"))
        return exp is not None and lo <= exp <= hi

    kept, ids = [], set()
    for n in gold["nodes"]:  # document order: parents first
        if n["level"] <= 2 or (in_dharani(n) and n["parent_id"] in ids):
            m = copy.deepcopy(n)
            if m["level"] <= 2:
                m["notes"] = []
            kept.append(m)
            ids.add(m["id"])
    for k, m in enumerate(kept, 1):
        m["order"] = k
    keys = ("outline_profile", "source_file", "source_sha256", "text_id", "text_title_src",
            "text_title_en", "author", "source_language", "id_convention", "generated_by",
            "source_document", "outline_mode", "root_text_id", "commentary_id", "scheme_id",
            "seeded_by", "gold_status", "licence", "eval_only", "cbeta_release",
            "display_label_rule")
    meta = {k: copy.deepcopy(gold["metadata"][k]) for k in keys if k in gold["metadata"]}
    meta["format_note"] = ("Kuiji gold, levels 1-2 (notes dropped) + the 陀羅尼品 subtree, filtered "
                           "by tests/unit/test_export.py")
    return outline_doc.refresh_counts({"metadata": meta, "nodes": kept})


@pytest.mark.skipif(not KUIJI.exists(), reason="Kuiji gold not present")
def test_kuiji_allowed_part_round_trip():
    doc = _kuiji_allowed()
    deep = [n for n in doc["nodes"] if n["level"] > 2]
    n_outside = sum(1 for n in deep if not n["id"].startswith("3_1.17_2."))
    assert deep and n_outside == 0, "%d deep nodes outside the 陀羅尼品 subtree" % n_outside
    rep = outline_doc.validate(doc)
    n_errors = len(rep.errors)
    assert n_errors == 0, "filtered Kuiji document invalid: %d errors" % n_errors

    graph, _ = export(doc)
    outline = graph["@graph"][0]
    exported, withheld = outline["cw:exportedNodeCount"], outline.get("cw:withheldSplitCount", 0)
    assert (exported, withheld) == (len(doc["nodes"]), 0)
    loaded = load(graph)
    bad = _mismatches(doc, loaded)
    assert bad == [], "round trip differs on %d nodes: %s" % (len(bad), bad[:10])
    assert loaded["metadata"]["scheme_id"] == "kuiji-xuanzan"
    assert loaded["metadata"]["root_text_id"] == "T09n0262"
    assert loaded["metadata"]["commentary_id"] == "T34n1723"
    assert outline["bdo:outlineOf"].endswith("/work/T09n0262")
    # the 陀羅尼品 node sits at partTreeIndex 3.17 (third part, seventeenth 品 under it)
    assert any(r.get("bdo:partTreeIndex") == "3.17" for r in graph["@graph"])


# -------------------------------------------------------------------------------- URI stability


def test_reexport_with_history_keeps_uris_and_history():
    doc = _minimal()
    g1, h1 = export(doc)
    g2, h2 = export(copy.deepcopy(doc), id_history=h1)
    assert _uris(g1) == _uris(g2)
    assert h1 == h2
    assert dumps(g1) == dumps(g2)


def _insert_first_child(doc: dict, parent_id: str | None, draft: dict) -> tuple[dict, dict]:
    """Insert `draft` as the first child of parent_id (None: first top-level node) and renumber the
    tree with the shared numbering (common.outline_doc). Returns (new doc, {old id: new id})."""
    roots = outline_doc.to_drafts(doc)

    def find(drafts):
        for d in drafts:
            if d["_orig_id"] == parent_id:
                return d
            hit = find(d["children"])
            if hit:
                return hit
        return None

    parent = None if parent_id is None else find(roots)
    siblings = roots if parent is None else parent["children"]
    siblings.insert(0, dict(draft, children=[]))
    if parent is not None and parent.get("child_count_announced"):
        parent["child_count_announced"] += 1
    nodes, private = outline_doc.number_tree(roots)
    old_to_new = {p["_orig_id"]: nid for nid, p in private.items() if "_orig_id" in p}
    new = {"metadata": copy.deepcopy(doc["metadata"]), "nodes": nodes}
    return outline_doc.refresh_counts(new), old_to_new


NEW_NODE = {
    "heading_src": "新插入（SYNTHETIC）",
    "heading_en": "Inserted (synthetic)",
    "origin": "explicit",
    "evidence": "SYNTHETIC",
    "locations": {"scheme": "cbeta-kepan",
                  "commentary": {"announced": "T99n9998_p0001a05", "explained": "T99n9998_p0001a05"},
                  "root_text": None},
    "node_class": "commentary-internal",
}


@pytest.mark.parametrize("parent_id", [None, "2_1"])
def test_renumbered_nodes_keep_their_uri(parent_id):
    doc = _minimal()
    g1, h1 = export(doc)
    before = _uris(g1)
    doc2, old_to_new = _insert_first_child(doc, parent_id, NEW_NODE)
    assert outline_doc.validate(doc2).passed()
    g2, h2 = export(doc2, id_history=h1)
    after = _uris(g2)
    moved = [old for old, new in old_to_new.items() if old != new]
    assert moved  # the insertion really renumbered siblings (and their subtrees)
    assert all(before[old] == after[new] for old, new in old_to_new.items())
    new_id = "1_1" if parent_id is None else "2_1.1_2"
    assert after[new_id] not in before.values()
    key = "T99n9999/synthetic-fixture"
    assert len(h2["outlines"][key]["nodes"]) == len(h1["outlines"][key]["nodes"]) + 1
    assert _mismatches(doc2, load(g2)) == []


def test_edited_heading_gets_new_uri_and_old_entry_is_kept():
    doc = _minimal()
    g1, h1 = export(doc)
    doc2 = copy.deepcopy(doc)
    doc2["nodes"][4]["heading_src"] = "三正宗分（改）"  # 3_1; its two children's keys change too
    g2, h2 = export(doc2, id_history=h1)
    u1, u2 = _uris(g1), _uris(g2)
    changed = sorted(i for i in u1 if u1[i] != u2[i])
    assert changed == ["3_1", "3_1.1_2", "3_1.2_2"]
    key = "T99n9999/synthetic-fixture"
    assert set(h1["outlines"][key]["nodes"].items()) <= set(h2["outlines"][key]["nodes"].items())
    # and editing it back restores the original URIs from the history
    g3, _ = export(doc, id_history=h2)
    assert _uris(g3) == u1


def test_tied_siblings_get_distinct_uris():
    doc = _minimal()
    twin = copy.deepcopy(doc["nodes"][6])  # 3_1.2_2
    twin.update(id="3_1.3_2", path=["3_1", "3_2"], order=8, sibling_index=3, display_label="乙三")
    doc["nodes"][7]["order"] = 9
    doc["nodes"].insert(7, twin)
    graph, _ = export(outline_doc.refresh_counts(doc))
    u = _uris(graph)
    assert len(set(u.values())) == len(u)


# ---------------------------------------------------------------------------------------- guards


def test_eval_only_outline_is_refused():
    with pytest.raises(ExportRefused, match="eval_only"):
        export(read_json(MINIMAL))  # the fixture as committed: eval_only true


def test_unlicensed_outline_is_refused():
    doc = _minimal()
    doc["metadata"]["licence"]["id"] = None
    with pytest.raises(ExportRefused, match="licence"):
        export(doc)


def _protected_datasets(kind: str) -> list:
    reg = load_registry()
    if kind == "ood":
        return [d for d in reg["datasets"] if d.get("split") == "out-of-domain"]
    return [d for d in reg["datasets"]
            if (d.get("file_metadata") or {}).get("eval_only") is True]


def _impersonate(ds: dict, how: str) -> dict:
    """The synthetic fixture relabelled as a registered gold (no gold file is opened)."""
    doc = _minimal()
    fm = ds["file_metadata"]
    meta = doc["metadata"]
    if how == "text_id":
        meta["text_id"], meta["scheme_id"] = fm["text_id"], fm["scheme_id"]
    elif how == "root_text_id":
        meta["scheme_id"] = fm["scheme_id"]
        meta["root_text_id"] = fm["root_text_id"]
    else:
        meta["source_file"] = ds["path"]
    return doc


@pytest.mark.parametrize("how", ["text_id", "root_text_id", "source_file"])
@pytest.mark.parametrize("ds", _protected_datasets("ood") + _protected_datasets("eval-only"),
                         ids=lambda d: d["id"])
def test_registered_ood_and_eval_only_golds_are_refused(ds, how):
    # the two sdp golds share root_text_id + scheme_id, so either may be named
    with pytest.raises(ExportRefused, match="registered gold (%s|sdp-)" % re.escape(ds["id"])):
        export(_impersonate(ds, how))


def test_all_five_ood_golds_are_covered():
    ids = {d["file_metadata"]["text_id"] for d in _protected_datasets("ood")}
    assert ids == {"X0268", "P1573", "D8842", "T1605", "T1602"}


@pytest.mark.parametrize("ds", _protected_datasets("ood"), ids=lambda d: d["id"])
def test_ood_gold_path_is_refused_before_reading(ds, tmp_path):
    with pytest.raises(ExportRefused):
        check_source_path(REPO / ds["path"])
    out = tmp_path / "out.jsonld"
    assert main([str(REPO / ds["path"]), "--out", str(out)]) == 2
    assert not out.exists()


def test_eval_only_file_is_refused_by_the_cli(tmp_path):
    out = tmp_path / "out.jsonld"
    assert main([str(MINIMAL), "--out", str(out)]) == 2
    assert not out.exists()


def _model_only(doc: dict, node_id: str, scheme: str = "model-0123abcd") -> dict:
    n = next(n for n in doc["nodes"] if n["id"] == node_id)
    n.update(origin="inferred", confidence=0.5, scheme_id=scheme)
    return doc


def test_model_only_nodes_are_withheld_by_default():
    doc = _model_only(_minimal(), "4_1")
    graph, history = export(doc)
    outline = graph["@graph"][0]
    assert outline["cw:withheldModelOnly"] == ["4_1"]
    assert outline["cw:exportedNodeCount"] == len(doc["nodes"]) - 1
    assert "4_1" not in _uris(graph)
    assert len(history["outlines"]["T99n9999/synthetic-fixture"]["nodes"]) == len(doc["nodes"]) - 1


def test_model_only_gate_is_per_level_and_takes_the_subtree():
    doc = _model_only(_model_only(_minimal(), "3_1"), "3_1.1_2")  # a model-only parent + child
    graph, _ = export(doc, allow_model_only_levels=0)
    assert graph["@graph"][0]["cw:withheldModelOnly"] == ["3_1", "3_1.1_2", "3_1.2_2"]
    graph, _ = export(doc, allow_model_only_levels=1)
    assert graph["@graph"][0]["cw:withheldModelOnly"] == ["3_1.1_2"]
    graph, _ = export(doc, allow_model_only_levels=2)
    assert "cw:withheldModelOnly" not in graph["@graph"][0]
    assert _mismatches(doc, load(graph)) == []


def test_inferred_nodes_of_the_commentators_scheme_are_exported():
    doc = _minimal()  # 4_1 is inferred under the document scheme (not model-*)
    graph, _ = export(doc)
    assert "4_1" in _uris(graph)


def _deep_node(heading: str, explained: str) -> dict:
    return {"heading_src": heading, "heading_en": "", "origin": "explicit", "evidence": "SYNTHETIC",
            "locations": {"scheme": "cbeta-kepan",
                          "commentary": {"announced": explained, "explained": explained},
                          "root_text": None},
            "node_class": "commentary-internal"}


def test_test_and_reserve_span_nodes_are_withheld_unless_frozen():
    """Below the structure levels (1-2), a node whose locators touch a test or reserve span of a
    split text is withheld and only counted. The lineheads are bare T34n1723 coordinates (no text)."""
    doc = _minimal()
    doc["nodes"][1]["locations"]["commentary"]["explained"] = "T34n1723_p0651a10"  # 2_1: structure
    doc, _ = _insert_first_child(doc, "2_1.1_2", _deep_node("甲（SYNTHETIC）", "T34n1723_p0651a10"))
    doc, _ = _insert_first_child(doc, "3_1.1_2", _deep_node("乙（SYNTHETIC）", "T34n1723_p0900a01"))
    doc, _ = _insert_first_child(doc, "3_1.2_2", _deep_node("丙（SYNTHETIC）", "T34n1723_p0850a20"))
    # test span, reserve, dev respectively
    graph, _ = export(doc)
    outline = graph["@graph"][0]
    assert outline["cw:withheldSplitCount"] == 2
    assert set(_uris(graph)) == {n["id"] for n in doc["nodes"]} - {"2_1.1_2.1_3", "3_1.1_2.1_3"}
    graph, _ = export(doc, frozen="E01-freeze-test")
    assert graph["@graph"][0]["cw:frozen"] == "E01-freeze-test"
    assert "cw:withheldSplitCount" not in graph["@graph"][0]
    assert _mismatches(doc, load(graph)) == []


# ----------------------------------------------------------------------- determinism, vocabulary


def test_export_is_deterministic():
    a, ha = export(_minimal())
    b, hb = export(_minimal())
    assert dumps(a) == dumps(b) and dumps(ha) == dumps(hb)
    other, _ = export(_minimal(), base_uri="https://kg.example.net/")
    assert set(_uris(other).values()).isdisjoint(_uris(a).values())
    assert all(u.startswith("https://kg.example.net/node/") for u in _uris(other).values())


def _keys(obj, out: set) -> set:
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, out)
    return out


def _terms(graph: dict) -> set:
    used = {k for k in _keys(graph["@graph"], set()) if not k.startswith("@")}
    for r in graph["@graph"]:
        types = r.get("@type")
        used.update(types if isinstance(types, list) else [types])
        for key in ("bdo:contentLocation", "cw:commentaryAnnounced", "cw:commentaryExplained"):
            if isinstance(r.get(key), dict):
                used.add(r[key]["@type"])
    return {t for t in used if t}


def test_every_term_has_a_declared_prefix():
    doc = _minimal()
    doc["nodes"][1]["part_type"] = "品"
    graph, _ = export(_model_only(doc, "4_1"))
    prefixes = {k for k, v in context().items() if isinstance(v, str)}
    for term in _terms(graph):
        assert term.split(":", 1)[0] in prefixes, term


@pytest.mark.skipif(not BDO_TTL.exists(), reason="BDRC ontology not fetched (scripts/fetch_bdrc.sh)")
def test_bdo_terms_exist_in_the_bdrc_ontology():
    ttl = BDO_TTL.read_text(encoding="utf-8")
    defined = set(re.findall(r"^(bdo:[A-Za-z]+)\s*$", ttl, flags=re.MULTILINE))
    doc = _minimal()
    doc["nodes"][1]["part_type"] = "品"
    graph, _ = export(doc)
    used = {t for t in _terms(graph) if t.startswith("bdo:")}
    assert used and used <= defined, sorted(used - defined)


# ------------------------------------------------------------------------------------------- CLI


def test_cli_writes_the_export_and_a_stable_history(tmp_path):
    src = write_json(_minimal(), tmp_path / "outline.json")
    out, hist = tmp_path / "out.jsonld", tmp_path / "export" / "id-history.json"
    args = [str(src), "--out", str(out), "--id-history", str(hist)]
    assert main(args) == 0
    first_out, first_hist = out.read_bytes(), hist.read_bytes()
    assert main(args) == 0
    assert out.read_bytes() == first_out and hist.read_bytes() == first_hist
    assert _mismatches(_minimal(), load(read_json(out))) == []
