"""Tests for the Chinese outline-schema extension and its validator.

Covers context/baseline/outline-schema-zh.json (profile zh-kepan; divergence D15 in docs/chinese-workflow-mapping.md)
and scripts/validate_outline.py:
  * both schemas are valid Draft 2020-12 schemas, and the zh schema reproduces the base defs without drift;
  * a synthetic base document (tests/fixtures/outline-base/minimal-base.json) validates under both schemas (superset
    rule), and in a base document a parent_id naming the nearest present ancestor is a warning only;
  * the synthetic zh example (tests/fixtures/outline-zh/minimal.json) validates under zh and is rejected by the base;
  * mutated copies of the example fail for the intended reason (asserted on the validator's finding codes): sūtra-mode
    rules keyed on metadata.outline_mode, span order between siblings and between parent and child, ill-typed input
    (reported as [schema], never a crash), end-of-string pattern anchors, works split over several CBETA files.
Standard library + pytest + jsonschema only. jsonschema is imported unconditionally: a missing dependency must fail
the run, not skip it (it belongs in pipeline/pyproject.toml's dev extra).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
from pathlib import Path

import jsonschema
import pytest

REPO = Path(__file__).resolve().parents[2]
BASE_SCHEMA = REPO / "context/baseline/outline-schema.json"
ZH_SCHEMA = REPO / "context/baseline/outline-schema-zh.json"
BASE_MINIMAL = REPO / "tests/fixtures/outline-base/minimal-base.json"
MINIMAL = REPO / "tests/fixtures/outline-zh/minimal.json"


def _load(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def vo():
    """scripts/validate_outline.py imported as a module (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("validate_outline", REPO / "scripts/validate_outline.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_outline"] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def base_schema():
    return _load(BASE_SCHEMA)


@pytest.fixture(scope="module")
def zh_schema():
    return _load(ZH_SCHEMA)


@pytest.fixture()
def minimal():
    return _load(MINIMAL)


def _schema_errors(schema, doc):
    return list(jsonschema.Draft202012Validator(schema).iter_errors(doc))


# --- the schemas themselves -------------------------------------------------------------------------------------


def test_schemas_are_valid_draft_2020_12(base_schema, zh_schema):
    jsonschema.Draft202012Validator.check_schema(base_schema)
    jsonschema.Draft202012Validator.check_schema(zh_schema)


def test_zh_schema_reproduces_base_defs(base_schema, zh_schema):
    """The zh schema is standalone; guard against drift from the base it reproduces."""
    b, z = base_schema["$defs"], zh_schema["$defs"]
    for name in ("metadata", "chapter", "part", "unindexed_entry"):
        assert z[name] == b[name], f"$defs/{name} drifted from the base schema"
    for key in ("type", "required", "additionalProperties"):
        assert zh_schema[key] == base_schema[key]
    for key in ("metadata", "unindexed_entries"):
        assert zh_schema["properties"][key] == base_schema["properties"][key]
    assert zh_schema["properties"]["nodes"] == base_schema["properties"]["nodes"]

    bn, zn = b["node"], z["node"]
    assert zn["required"] == bn["required"]
    assert zn["additionalProperties"] is False
    assert (zn["if"], zn["then"]) == (bn["if"], bn["then"])
    for prop, sub in bn["properties"].items():
        if prop == "origin":  # widened: base values kept, two added
            assert set(sub["enum"]) <= set(zn["properties"]["origin"]["enum"])
            continue
        assert zn["properties"][prop] == sub, f"node.{prop} drifted from the base schema"

    base_branches = {br["properties"]["scheme"]["const"]: br for br in b["location"]["oneOf"]}
    zh_branches = {br["properties"]["scheme"]["const"]: br for br in z["location"]["oneOf"]}
    assert set(base_branches) < set(zh_branches) and "cbeta-kepan" in zh_branches
    for scheme, br in base_branches.items():
        if scheme == "cbeta-line":  # widened pattern, checked behaviourally below
            zb = zh_branches[scheme]
            assert (zb["required"], zb["additionalProperties"]) == (br["required"], br["additionalProperties"])
            assert set(zb["properties"]) == set(br["properties"])
            continue
        assert zh_branches[scheme] == br, f"location scheme {scheme} drifted from the base schema"


def test_cbeta_line_pattern_is_widened_not_narrowed(base_schema, zh_schema):
    base_pat = next(br for br in base_schema["$defs"]["location"]["oneOf"]
                    if br["properties"]["scheme"]["const"] == "cbeta-line")["properties"]["start"]["pattern"]
    zh_pat = next(br for br in zh_schema["$defs"]["location"]["oneOf"]
                  if br["properties"]["scheme"]["const"] == "cbeta-line")["properties"]["start"]["pattern"]
    samples = ["T09n0262_p0001c05", "X11n0268_p0180a12", "ABC1n1_p0001a01", "T34n1723_p0651b01"]
    for s in samples:
        assert re.match(base_pat, s), s
        assert re.match(zh_pat, s), f"{s} is base-valid but rejected by the widened zh pattern"
    for s in ["ZW12na070_pb001a01", "T49n2035_p0316d21", "T09n0262_p0001c05:12"]:
        assert re.match(zh_pat, s) and not re.match(base_pat, s), s
    # jsonschema applies patterns with re.search, where the base's '$' also matches before a final newline; the zh
    # pattern ends in (?![\s\S]) and rejects it, as ECMA-262 (JSON Schema's regex dialect) does for both patterns.
    assert re.search(base_pat, "T09n0262_p0001c05\n") and not re.search(zh_pat, "T09n0262_p0001c05\n")


@pytest.mark.parametrize("ref", [
    "T09n0262_p0001c05",      # Taishō, the canonical example (R02 F6)
    "T34n1723_p0651b01",
    "X11n0268_p0180a12",      # 卍續藏 (R02 F28)
    "T49n2035_p0316d21",      # register d (R02 F18)
    "T45n1879a_p0001a01",     # text number with letter suffix
    "J40nB492_p0485a01",      # text number with letter prefix
    "ZW12na070_pb001a01",     # front-matter page 'b001'
    "G069n1977_p0001a01",     # three-digit volume
    "T09n0262_p0001c05:0",    # character offset (our convention)
    "T09n0262_p0001c05:17",
])
def test_cbeta_ref_grammar_accepts(zh_schema, ref):
    assert re.search(zh_schema["$defs"]["cbeta_ref"]["pattern"], ref)  # re.search, as jsonschema applies it


@pytest.mark.parametrize("ref", [
    "T09n0262_p001c05",       # 3-digit page
    "T09n0262_p0001C05",      # upper-case register
    "T09n0262_0001c05",       # missing '_p'
    "T09n0262_p0001c5",       # 1-digit line
    "T09n0262_p0001c05:",     # empty offset
    "T09n0262_p0001c05:01",   # offset with a leading zero
    "t09n0262_p0001c05",      # lower-case canon
    "T09n0262p0001c05",       # missing '_'
    "T09n0262_p0001c05\n",    # trailing newline ('$' would let it through under Python's re.search)
    "T09n0262_p0001c05:3\n",
])
def test_cbeta_ref_grammar_rejects(zh_schema, ref):
    assert not re.search(zh_schema["$defs"]["cbeta_ref"]["pattern"], ref)


# --- superset rule: a base document --------------------------------------------------------------------------------


def test_base_document_validates_under_both_schemas(base_schema, zh_schema):
    doc = _load(BASE_MINIMAL)
    assert "outline_profile" not in doc["metadata"]
    assert _schema_errors(base_schema, doc) == []
    assert _schema_errors(zh_schema, doc) == []


@pytest.mark.parametrize("schema", ["base", "zh"])
def test_base_document_passes_validator(vo, schema):
    rep = vo.validate_document(_load(BASE_MINIMAL), schema)
    assert rep.schema == schema
    assert rep.findings == []


@pytest.mark.parametrize("schema", ["base", "zh"])
def test_absent_structural_parent_is_a_warning_in_base_documents(vo, schema):
    """A base document may lack a node's structural parent: parent_id then names the nearest present
    ancestor, with a note; accepted with a warning (an error under zh-kepan, whose ids are generated)."""
    doc = _load(BASE_MINIMAL)
    assert doc["nodes"][2]["id"] == "1_1.B_2"
    del doc["nodes"][2]
    for n in doc["nodes"][2:4]:
        assert n["parent_id"] == "1_1.B_2"
        n["parent_id"] = "1_1"
        n["notes"] = ["structural parent 1_1.B_2 absent from the source"]
    for order, n in enumerate(doc["nodes"], 1):
        n["order"] = order
    doc["metadata"].update(node_count=5, nodes_per_level={"1": 2, "2": 1, "3": 2})
    rep = vo.validate_document(doc, schema)
    assert rep.errors == []
    assert rep.codes("warning") == {"parent-nearest-ancestor"}
    assert [f.where for f in rep.warnings] == ["1_1.B_2.1_3", "1_1.B_2.2_3"]


def test_profile_opt_in_is_what_adds_requirements(zh_schema):
    """Documented edge of the superset rule: setting outline_profile on a base document opts it in."""
    doc = _load(BASE_MINIMAL)
    doc["metadata"]["outline_profile"] = "zh-kepan"
    messages = [e.message for e in _schema_errors(zh_schema, doc)]
    assert any("'scheme_id' is a required property" in m for m in messages)


# --- the synthetic zh example -----------------------------------------------------------------------------------


def test_minimal_is_labelled_synthetic(minimal):
    meta = minimal["metadata"]
    assert meta["gold_status"] == "synthetic-fixture"
    assert meta["source_document"]["kind"] == "synthetic"
    assert "SYNTHETIC" in meta["format_note"] and "SYNTHETIC" in meta["text_title_en"]
    assert 5 <= len(minimal["nodes"]) <= 8


def test_minimal_validates_under_zh(vo, zh_schema, minimal):
    assert _schema_errors(zh_schema, minimal) == []
    rep = vo.validate_document(minimal)
    assert rep.schema == "zh" and rep.profile == "zh-kepan"
    assert rep.findings == []


def test_minimal_is_not_a_base_document(base_schema, minimal):
    assert _schema_errors(base_schema, minimal) != []


def test_auto_schema_choice(vo, minimal):
    assert vo.choose_schema(minimal) == "zh"
    assert vo.choose_schema(_load(BASE_MINIMAL)) == "base"
    assert vo.choose_schema(minimal, "base") == "base"


# --- mutations: each must fail for its own reason ---------------------------------------------------------------


def _codes(rep):
    return rep.codes("error")


def _schema_messages(rep):
    return [(f.where, f.message) for f in rep.errors if f.code == "schema"]


def test_duplicate_id(vo, minimal):
    minimal["nodes"][3]["id"] = minimal["nodes"][2]["id"]
    rep = vo.validate_document(minimal)
    assert "duplicate-id" in _codes(rep)
    assert "schema" not in _codes(rep)


def test_bad_level(vo, minimal):
    minimal["nodes"][2]["level"] = 3  # path still has two tokens
    rep = vo.validate_document(minimal)
    assert {"level-path", "level-parent"} <= _codes(rep)
    assert "schema" not in _codes(rep)


@pytest.mark.parametrize("field,value", [
    ("start", "T99n9999_p001a01"),       # 3-digit page
    ("start", "T99n9999_p0001A01"),      # upper-case register
    ("end", "T99n9999-p0001a03"),        # wrong separator
])
def test_bad_line_ref(vo, minimal, field, value):
    minimal["nodes"][2]["locations"]["root_text"][field] = value
    rep = vo.validate_document(minimal)
    assert _codes(rep) == {"schema"}
    (where, message), = _schema_messages(rep)
    assert where == f"$.nodes[2].locations.root_text.{field}"
    assert "does not match" in message and "(keyword: pattern)" in message


def test_bad_commentary_ref(vo, minimal):
    minimal["nodes"][6]["locations"]["commentary"]["explained"] = "T99n9998_p0002a11:04"  # offset leading zero
    rep = vo.validate_document(minimal)
    (where, message), = _schema_messages(rep)
    assert where == "$.nodes[6].locations.commentary.explained" and "pattern" in message


def test_missing_scheme_id(vo, minimal):
    del minimal["metadata"]["scheme_id"]
    rep = vo.validate_document(minimal)
    assert _schema_messages(rep) == [("$.metadata", "'scheme_id' is a required property (keyword: required)")]
    assert _codes(rep) == {"schema"}


def test_missing_zh_node_field(vo, minimal):
    del minimal["nodes"][0]["sibling_index"]
    rep = vo.validate_document(minimal)
    assert ("$.nodes[0]", "'sibling_index' is a required property (keyword: required)") in _schema_messages(rep)


def test_root_span_start_after_end(vo, minimal):
    span = minimal["nodes"][2]["locations"]["root_text"]
    span["start"], span["end"] = span["end"], span["start"]
    rep = vo.validate_document(minimal)
    assert _codes(rep) == {"cbeta-order"}


def test_same_line_offsets_are_ordered(vo, minimal):
    span = minimal["nodes"][2]["locations"]["root_text"]
    span["start"], span["end"] = "T99n9999_p0001a01:9", "T99n9999_p0001a01:3"
    assert _codes(vo.validate_document(minimal)) == {"cbeta-order"}
    span["end"] = "T99n9999_p0001a01"  # no offset on one side: compared at line level, equal lines are fine
    assert vo.validate_document(minimal).errors == []


def test_sibling_index_inconsistent(vo, minimal):
    minimal["nodes"][4]["sibling_index"] = 2  # 3_1 is the third root
    rep = vo.validate_document(minimal)
    assert {"sibling-index", "id-sibling-index"} <= _codes(rep)


def test_node_count_mismatch(vo, minimal):
    minimal["metadata"]["node_count"] = 9
    assert _codes(vo.validate_document(minimal)) == {"metadata-count"}


def test_order_not_increasing(vo, minimal):
    minimal["nodes"][5]["order"] = 5
    assert "order-not-increasing" in _codes(vo.validate_document(minimal))


def test_parent_must_precede_and_be_ancestor(vo, minimal):
    minimal["nodes"][2]["parent_id"] = "3_1"
    rep = vo.validate_document(minimal)
    assert {"parent-after-child", "parent-not-ancestor"} & _codes(rep)


def test_missing_licence_forces_eval_only(vo, minimal):
    minimal["metadata"]["eval_only"] = False  # licence.id is null in the fixture
    rep = vo.validate_document(minimal)
    assert _schema_messages(rep) == [("$.metadata.eval_only", "True was expected (keyword: const)")]


def test_imported_node_needs_source_node_id(vo, minimal):
    minimal["nodes"][1]["origin"] = "imported"
    rep = vo.validate_document(minimal)
    assert _schema_messages(rep) == [("$.nodes[1].source_node_id", "None is not of type 'string' (keyword: type)")]
    minimal["nodes"][1]["source_node_id"] = "T0262D01_005"
    assert vo.validate_document(minimal).errors == []


def test_commentary_internal_has_no_root_span(vo, minimal):
    minimal["nodes"][0]["locations"]["root_text"] = {"start": "T99n9999_p0001a01", "end": None, "basis": "lemma"}
    assert _codes(vo.validate_document(minimal)) == {"class-root-text"}


def test_interpolated_basis_is_a_root_span_basis(vo, minimal, zh_schema):
    """E06 B3: anchor.resolve_root_spans places a node whose lemma is not found where its elder
    sibling's lemma ends and gives it basis 'interpolated' (outline/anchor.py); the schema enum carries
    it, says what it means, and still rejects a basis that is not in the enum."""
    prop = zh_schema["$defs"]["root_text_span"]["properties"]["basis"]
    assert "interpolated" in prop["enum"] and "interpolated = the lemma was not found" in prop["description"]
    rt = minimal["nodes"][1]["locations"]["root_text"]
    rt["basis"] = "interpolated"
    assert vo.validate_document(minimal).errors == []
    rt["basis"] = "guessed"
    got = _schema_messages(vo.validate_document(minimal))
    assert [w for w, _ in got] == ["$.nodes[1].locations.root_text.basis"]
    assert got[0][1].startswith("'guessed' is not one of [") and got[0][1].endswith("(keyword: enum)")


def test_sutra_span_without_root_needs_unmapped(vo, minimal):
    minimal["nodes"][3]["locations"]["root_text"] = None
    assert _codes(vo.validate_document(minimal)) == {"sutra-span-unmapped"}
    minimal["nodes"][3]["flags"].append("unmapped")
    assert vo.validate_document(minimal).errors == []


def test_ref_outside_declared_text(vo, minimal):
    minimal["nodes"][1]["locations"]["root_text"]["end"] = "T98n9999_p0001b02"
    assert "cbeta-text-id" in _codes(vo.validate_document(minimal))


def test_zh_profile_requires_kepan_location_scheme(vo, minimal):
    minimal["nodes"][0]["locations"] = {"scheme": "cbeta-line", "start": "T99n9998_p0001a06"}
    rep = vo.validate_document(minimal)
    assert ("$.nodes[0].locations.scheme",
            "'cbeta-line' is not one of ['cbeta-kepan', 'unparsed', 'none'] (keyword: enum)") in _schema_messages(rep)


def test_zh_ids_are_digits_only(vo, minimal):
    node = minimal["nodes"][2]
    node["id"], node["path"] = "2_1.A_2", ["2_1", "A_2"]
    rep = vo.validate_document(minimal)
    assert any(w == "$.nodes[2].id" and "pattern" in m for w, m in _schema_messages(rep))


def test_flag_truncated_is_distinct_from_coarsened(vo, minimal, zh_schema):
    """D15 addendum (2026-09-22): 'truncated' = the gold does not encode all of this node's source children (depth
    limit or covered-span end), a flag of its own next to 'coarsened' (the source stops subdividing); the description
    states the scoring contract. No validator rule keys on it; an unknown flag is still a schema error."""
    enum = zh_schema["$defs"]["node"]["properties"]["flags"]["items"]["enum"]
    assert {"truncated", "coarsened"} <= set(enum)
    desc = zh_schema["$defs"]["node"]["properties"]["flags"]["description"]
    assert "truncated = the gold does not encode all of this node's source children" in desc
    assert "neither TP nor FP" in desc and "are not FN" in desc and "metadata.coverage_spans" in desc
    # revised rule: with coverage_spans the scope alone decides and truncated is informational
    assert "max_level (null = no limit)" in desc and "truncated is informational" in desc
    assert "a gold without coverage_spans has the whole gold as scope" in desc
    minimal["nodes"][1]["flags"].append("truncated")
    assert vo.validate_document(minimal).findings == []
    minimal["nodes"][1]["flags"].append("stops_here")
    rep = vo.validate_document(minimal)
    assert [w for w, m in _schema_messages(rep)] == ["$.nodes[1].flags[1]"]


def test_unmapped_and_next_node_describe_the_rules_the_golds_use(zh_schema):
    """D15 addendum (final review 2026-09-22): 'unmapped' = the gold's primary locator is missing (root_text.start
    in a root-keyed gold, commentary.explained in the commentary-keyed sdp T1718 gold), consistent with the
    validator's [sutra-span-unmapped] rule; a next-node end is inclusive and may be the next node's own start line."""
    flags = zh_schema["$defs"]["node"]["properties"]["flags"]["description"]
    assert "unmapped = the gold's primary locator is missing" in flags
    assert "[sutra-span-unmapped]" in flags and "never by this flag" in flags
    assert "root-text span not resolvable" not in flags
    assert "only those predicted subtrees under a truncated node that match no encoded node" in flags
    end_basis = zh_schema["$defs"]["root_text_span"]["properties"]["end_basis"]["description"]
    assert "else the next node's start line itself, which the two nodes share" in end_basis
    assert "the line before the start of the next node" not in end_basis


def test_commentary_span_start_pair_validates(vo, minimal, zh_schema):
    """D15 addendum (2026-10-02, E06 review A3): commentary.span_start (the node's text-span start under sdp's
    anchor rule, written by common.outline_doc.fill_span_starts) and span_start_inherited are optional fields of a
    commentary position; they come and go together (dependentRequired); an unknown field is still rejected."""
    cp = zh_schema["$defs"]["commentary_position"]
    assert cp["properties"]["span_start"]["$ref"] == "#/$defs/cbeta_ref"
    assert cp["properties"]["span_start_inherited"]["type"] == "boolean"
    assert cp["dependentRequired"] == {"span_start": ["span_start_inherited"], "span_start_inherited": ["span_start"]}
    assert cp["required"] == ["announced", "explained"]  # the golds carry neither field
    minimal["nodes"][1]["locations"]["commentary"].update(span_start="T99n9998_p0001b01", span_start_inherited=False)
    com = minimal["nodes"][2]["locations"]["commentary"]  # 2_1.1_2, the first child of 2_1
    com.update(span_start="T99n9998_p0001b01", span_start_inherited=True)
    assert vo.validate_document(minimal).findings == []
    del com["span_start_inherited"]
    assert _schema_messages(vo.validate_document(minimal)) == [
        ("$.nodes[2].locations.commentary",
         "'span_start_inherited' is a dependency of 'span_start' (keyword: dependentRequired)")]
    com["span_start_inherited"] = True
    com["span_start_line"] = "T99n9998_p0001b01"
    (where, message), = _schema_messages(vo.validate_document(minimal))
    assert where == "$.nodes[2].locations.commentary" and "Additional properties are not allowed" in message
    del com["span_start_line"]
    com["span_start"] = "T99n9998_p0001b01\n"
    (where, message), = _schema_messages(vo.validate_document(minimal))
    assert where == "$.nodes[2].locations.commentary.span_start" and "(keyword: pattern)" in message


def test_warnings_do_not_fail_unless_strict(vo, minimal):
    minimal["nodes"][1]["child_count_announced"] = 3  # two children present, no count_mismatch flag
    rep = vo.validate_document(minimal)
    assert rep.codes("warning") == {"child-count"} and rep.passed() and not rep.passed(strict=True)
    minimal["nodes"][1]["flags"].append("count_mismatch")
    assert vo.validate_document(minimal).findings == []


# --- outline mode: sūtra-mode rules follow metadata.outline_mode, not commentary_id ---------------------------------


def _to_self_outlining(doc):
    """The fixture re-read as a self-outlining text: the fictional T99n9999 states its own outline."""
    meta = doc["metadata"]
    meta["outline_mode"], meta["commentary_id"] = "self-outlining", None
    meta["source_document"].update(kind="root-text", text_id="T99n9999")
    for n in doc["nodes"]:
        com = n["locations"]["commentary"]
        for key in ("announced", "explained"):
            if com and com[key]:
                com[key] = com[key].replace("T99n9998", "T99n9999")
    return doc


def test_outline_mode_is_required(vo, minimal):
    del minimal["metadata"]["outline_mode"]
    rep = vo.validate_document(minimal)
    assert _schema_messages(rep) == [("$.metadata", "'outline_mode' is a required property (keyword: required)")]


def test_self_outlining_fixture_variant_is_valid(vo, minimal):
    assert vo.validate_document(_to_self_outlining(minimal)).findings == []


def test_self_outlining_forbids_commentary_id(vo, minimal):
    _to_self_outlining(minimal)["metadata"]["commentary_id"] = "T99n9998"
    rep = vo.validate_document(minimal)
    assert ("$.metadata.commentary_id", "None was expected (keyword: const)") in _schema_messages(rep)


@pytest.mark.parametrize("location", [{"scheme": "none"}, {"scheme": "unparsed", "raw": "SYNTHETIC"}])
def test_sutra_span_without_root_scheme_needs_unmapped(vo, minimal, location):
    """A sūtra-mode sutra-span node whose location scheme carries no root span at all needs the flag too."""
    minimal["nodes"][3]["locations"] = location
    assert _codes(vo.validate_document(minimal)) == {"sutra-span-unmapped"}
    minimal["nodes"][3]["flags"].append("unmapped")
    assert vo.validate_document(minimal).errors == []


def test_sutra_mode_with_non_cbeta_stating_work(vo, minimal):
    """commentary_id null in sūtra mode (the YBh T1605 / T1602 case, R04 F3, R06 F28) keeps the sūtra-mode rules on;
    before outline_mode existed, null commentary_id meant self-outlining and switched them off."""
    minimal["metadata"]["commentary_id"] = None
    minimal["metadata"]["source_document"].update(kind="dataset", text_id=None)
    for n in minimal["nodes"]:
        n["locations"]["commentary"] = None  # an import with no positions in a CBETA text
    assert vo.validate_document(minimal).findings == []
    minimal["nodes"][3]["locations"]["root_text"] = None
    assert _codes(vo.validate_document(minimal)) == {"sutra-span-unmapped"}


def test_sutra_mode_null_commentary_id_positions_need_text_id(vo, minimal):
    minimal["metadata"]["commentary_id"] = None
    assert _codes(vo.validate_document(minimal)) == {"cbeta-text-id"}
    for n in minimal["nodes"]:
        n["locations"]["commentary"]["text_id"] = "T99n9998"
    assert vo.validate_document(minimal).findings == []


# --- span order across nodes (docs/architecture.md §4, §5 step 3) --------------------------------------------------


def test_sibling_root_spans_must_not_run_backwards(vo, minimal):
    a, b = minimal["nodes"][5]["locations"], minimal["nodes"][6]["locations"]
    a["root_text"], b["root_text"] = b["root_text"], a["root_text"]
    rep = vo.validate_document(minimal)
    assert _codes(rep) == {"sibling-order"}
    assert [f.where for f in rep.errors] == ["3_1.2_2"]


def test_child_root_span_inside_parent(vo, minimal):
    minimal["nodes"][2]["locations"]["root_text"].update(start="T99n9999_p0009a01", end="T99n9999_p0009a02")
    rep = vo.validate_document(minimal)
    assert "child-outside-parent" in _codes(rep)
    assert {f.where for f in rep.errors if f.code == "child-outside-parent"} == {"2_1.1_2"}


def test_child_root_span_end_inside_parent(vo, minimal):
    minimal["nodes"][6]["locations"]["root_text"]["end"] = "T99n9999_p0002c15"  # parent 3_1 ends at p0002c10
    assert _codes(vo.validate_document(minimal)) == {"child-outside-parent"}


def test_explained_order_is_a_warning_in_sutra_mode(vo, minimal):
    minimal["nodes"][6]["locations"]["commentary"]["explained"] = "T99n9998_p0001c03"  # elder sibling: p0001c04
    rep = vo.validate_document(minimal)
    assert rep.errors == [] and rep.codes("warning") == {"sibling-order"}


def test_explained_order_is_an_error_in_self_outlining_mode(vo, minimal):
    """In self-outlining mode commentary.explained is the explained locator of the eval key, so order matters."""
    _to_self_outlining(minimal)
    minimal["nodes"][6]["locations"]["commentary"]["explained"] = "T99n9999_p0001c03"
    assert _codes(vo.validate_document(minimal)) == {"sibling-order"}


def test_parallel_scheme_siblings_are_not_ordered_against_the_main_scheme(vo, minimal):
    a, b = minimal["nodes"][5]["locations"], minimal["nodes"][6]["locations"]
    a["root_text"], b["root_text"] = b["root_text"], a["root_text"]
    minimal["nodes"][6]["scheme_id"] = "synthetic-lens"  # a cross-cutting lens is its own sibling group
    assert "sibling-order" not in vo.validate_document(minimal).codes()


def test_base_explained_folio_order_is_a_warning(vo):
    doc = _load(BASE_MINIMAL)
    assert doc["nodes"][3]["id"] == "1_1.B_2.1_3" and doc["nodes"][4]["locations"]["explained"] == "2B"
    doc["nodes"][3]["locations"]["explained"] = "3A"  # elder sibling now explained after its younger sibling
    rep = vo.validate_document(doc)
    assert rep.errors == []
    assert [(f.code, f.where) for f in rep.warnings if f.code == "sibling-order"] == [("sibling-order", "1_1.B_2.2_3")]


# --- ill-typed input is reported, never crashes the run -----------------------------------------------------------


@pytest.mark.parametrize("mutate,where", [
    (lambda d: d["nodes"][2].__setitem__("parent_id", ["2_1"]), "$.nodes[2].parent_id"),
    (lambda d: d.__setitem__("unindexed_entries", 5), "$.unindexed_entries"),
    (lambda d: d["nodes"][1].__setitem__("path", "2_1"), "$.nodes[1].path"),
    (lambda d: d["nodes"][2].__setitem__("level", "2"), "$.nodes[2].level"),
    (lambda d: d["nodes"][3].__setitem__("flags", "unmapped"), "$.nodes[3].flags"),
    (lambda d: d["nodes"][4].__setitem__("locations", ["cbeta-kepan"]), "$.nodes[4].locations"),
    (lambda d: d["nodes"][5].__setitem__("id", 7), "$.nodes[5].id"),
    (lambda d: d["nodes"].__setitem__(6, "not a node"), "$.nodes[6]"),
    (lambda d: d["metadata"].__setitem__("work_files", "T99n9999"), "$.metadata.work_files"),
])
def test_type_invalid_input_is_a_schema_error(vo, minimal, mutate, where):
    mutate(minimal)
    rep = vo.validate_document(minimal)
    assert "internal" not in rep.codes()
    assert rep.codes() == {"schema"}, [f.render() for f in rep.findings]  # no knock-on structural findings
    assert where in {w for w, _ in _schema_messages(rep)}
    assert len(_schema_messages(rep)) == len(set(_schema_messages(rep)))  # each message once


def test_validator_exception_becomes_internal_error(vo, monkeypatch, capsys):
    def boom(doc, zh):
        raise TypeError("synthetic failure")
    monkeypatch.setattr(vo, "structural_findings", boom)
    rep = vo.validate_document(_load(MINIMAL))
    assert rep.codes() == {"internal"} and "synthetic failure" in rep.errors[0].message
    assert vo.main([str(MINIMAL), str(BASE_MINIMAL), "--quiet"]) == 1
    out = capsys.readouterr().out
    assert out.count("FAIL") == 2 and "validated 2 file(s)" in out  # the run went on to the second file


def test_cli_goes_on_after_a_type_invalid_file(vo, tmp_path, minimal, capsys):
    minimal["nodes"][2]["parent_id"] = ["2_1"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(minimal, ensure_ascii=False), encoding="utf-8")
    assert vo.main([str(bad), str(MINIMAL), "--quiet"]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("FAIL") and lines[1].startswith("PASS") and "1 passed, 1 failed" in lines[2]


# --- pattern anchoring: '$' vs end of string ----------------------------------------------------------------------


def _patterns(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "pattern":
                yield v
            else:
                yield from _patterns(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _patterns(v)


def test_zh_patterns_anchor_at_end_of_string(base_schema, zh_schema):
    """Every pattern the zh schema adds ends in (?![\\s\\S]); only the reproduced base patterns keep '$'."""
    base_patterns = set(_patterns(base_schema))
    added = [p for p in _patterns(zh_schema) if p not in base_patterns]
    assert added
    for p in added:
        assert p.endswith("(?![\\s\\S])"), p


@pytest.mark.parametrize("mutate,where", [
    (lambda d: d["nodes"][7].update(id="4_1\n", path=["4_1\n"]), "$.nodes[7].id"),
    (lambda d: d["metadata"].update(scheme_id="synthetic-fixture\n"), "$.metadata.scheme_id"),
    (lambda d: d["metadata"].update(root_text_id="T99n9999\n"), "$.metadata.root_text_id"),
    (lambda d: d["nodes"][2]["locations"]["root_text"].update(start="T99n9999_p0001a01\n"),
     "$.nodes[2].locations.root_text.start"),
])
def test_trailing_newline_rejected_in_zh_documents(vo, minimal, mutate, where):
    mutate(minimal)
    assert where in {w for w, _ in _schema_messages(vo.validate_document(minimal))}


def test_trailing_newline_flagged_in_base_documents(vo, base_schema):
    """The base schema's '$' lets '3A\\n' through under Python's re.search; the validator flags it instead."""
    doc = _load(BASE_MINIMAL)
    doc["nodes"][3]["locations"]["explained"] = "2A\n"
    assert _schema_errors(base_schema, doc) == []  # the gap being covered
    rep = vo.validate_document(doc)
    assert _codes(rep) == {"key-whitespace"}


# --- works split over several CBETA files (R02 F18) -----------------------------------------------------------------


def _as_multi_file_work(doc):
    """Move the fixture's root text into a fictional two-file work T98n9999 + T98n9999b."""
    doc["metadata"]["root_text_id"] = "T98n9999"
    for n in doc["nodes"]:
        rt = n["locations"]["root_text"]
        for key in ("start", "end"):
            if rt and rt[key]:
                rt[key] = rt[key].replace("T99n9999", "T98n9999")
    root_4 = doc["nodes"][7]["locations"]["root_text"]
    root_4.update(start="T98n9999b_p0001a01", end="T98n9999b_p0001a09")  # the last division sits in file 2
    return doc


def test_span_across_files_needs_work_files(vo, minimal):
    _as_multi_file_work(minimal)
    assert _codes(vo.validate_document(minimal)) == {"cbeta-text-id"}
    minimal["metadata"]["work_files"] = [["T98n9999", "T98n9999b"]]
    assert vo.validate_document(minimal).findings == []
    minimal["nodes"][4]["locations"]["root_text"]["end"] = "T98n9999b_p0001a09"  # 3_1 now runs into file 2
    assert vo.validate_document(minimal).findings == []


def test_files_of_a_work_are_ordered(vo, minimal):
    _as_multi_file_work(minimal)
    minimal["metadata"]["work_files"] = [["T98n9999b", "T98n9999"]]  # file 2 listed first: 4_1 now precedes 3_1
    assert "sibling-order" in _codes(vo.validate_document(minimal))


def test_file_in_two_work_entries(vo, minimal):
    minimal["metadata"]["work_files"] = [["T99n9999", "T99n9997"], ["T99n9996", "T99n9999"]]
    assert _codes(vo.validate_document(minimal)) == {"work-files"}


# --- command line -----------------------------------------------------------------------------------------------


def test_cli_exit_codes(vo, tmp_path, minimal, capsys):
    assert vo.main([str(BASE_MINIMAL), str(MINIMAL), "--quiet"]) == 0
    bad = copy.deepcopy(minimal)
    del bad["metadata"]["scheme_id"]
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    assert vo.main([str(bad_path)]) == 1
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert vo.main([str(broken), "--quiet"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "scheme_id" in out and "passed" in out
