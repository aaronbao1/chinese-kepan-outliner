"""Tests for chinese_workflow.eval.gold (common.py, sdp.py) — Task 2 of the eval-dataset build.

Always run: the importer on the SYNTHETIC fixture tests/fixtures/sdp-synthetic/ (sdp's HTML/tree
format, invented content; README there), plus unit tests of the helpers and of common.py.
Run only when data/raw/ is present (skip otherwise; sdp is eval-only, Global Constraint 1): both
real golds validate, and the documented cases hold — node T0262D02_010 starts at
T09n0262_p0001c19 (its content div opens after anchor 0001c18, line 序品第一, and its first
anchor, 0001c19, comes before its first text 如是我聞), T0262D09_054 at 0010c12 (R03 F23: text
身意泰然 before its first anchor 0010c13), and the counts R04 F30/F31 report.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from chinese_workflow.eval.gold import common, sdp

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures" / "sdp-synthetic"
RAW_SDP = REPO / "data" / "raw" / "dila-sdp"
RAW_CBETA = REPO / "data" / "raw" / "cbeta"
GOLD_PKG = REPO / "pipeline" / "src" / "chinese_workflow" / "eval" / "gold"

# The SYNTHETIC CBETA-side lines the fixture's anchors point at ({linehead: text}, in line order,
# as common.line_texts returns them); invented like the fixture itself.
_ROOT = [
    "",
    "合成序文甲。",
    "合成序文乙。",
    "序品第一",
    "如是合成，我聞合成",
    "之文。",
    "長行合成文。以偈頌曰",
    "合成偈一　合成偈二　合成偈三　合成偈四",
    "合成偈五　合成偈六",
    "偈後長行。",
    "別序續文。",
    "附文合成。",
    "正宗分第二",
    "開顯合成文。",
    "授記合成文。授記長行文。",
    "授記偈頌文。",
    "偈頌續文。",
]
SYN_ROOT_LINES = {"T99n9999_p0001a%02d" % k: t for k, t in enumerate(_ROOT, 1)}
_COM = [
    ("0001a01", "此序文合成"),
    ("0001a02", "疏序正文。"),
    ("0001a03", "序分疏文。"),
    ("0001a04", "通序疏文。"),
    ("0001a05", "別序疏文。"),
    ("0001a06", "長行疏文。"),
    ("0001b01", ""),
    ("0001b02", "偈頌疏文。"),
    ("0001b03", "正宗分疏文。"),
    ("0002a01", "開顯疏文續。"),
    ("0002a02", "授記疏文。"),
]
SYN_COM_LINES = {"T99n9998_p" + n: t for n, t in _COM}
RAW_FILES = (
    [RAW_SDP / "tree-T0262-full.json", RAW_SDP / "tree-T1718-full.json"]
    + [RAW_SDP / ("T0262-juan%d.html" % k) for k in range(1, 8)]
    # the 9 T1718 卷-halves sdp serves (scripts/fetch_dila_sdp.sh; the other 11 are a server gap)
    + [RAW_SDP / ("T1718-juan%s.html" % k) for k in "1a 2a 2b 3a 3b 4a 4b 5b 6b".split()]
    + [RAW_CBETA / "T09n0262.xml", RAW_CBETA / "T34n1718.xml"]
)


def _sources():
    root = sdp.SdpSource(
        "T9999",
        "T99n9999",
        FIX / "tree-T9999-full.json",
        [("1", FIX / "T9999-juan1.html"), ("2", FIX / "T9999-juan2.html")],
    )
    com = sdp.SdpSource(
        "T9998",
        "T99n9998",
        FIX / "tree-T9998-full.json",
        [(k, FIX / ("T9998-juan%s.html" % k)) for k in ("1a", "1b", "2a", "2b")],
    )
    return root, com


@pytest.fixture(scope="module")
def syn():
    root, com = _sources()
    return sdp.build_golds(root, com, SYN_ROOT_LINES, SYN_COM_LINES)


def _by_sid(doc: dict) -> dict:
    return {n["source_node_id"]: n for n in doc["nodes"]}


def _root_span(node: dict):
    rt = node["locations"]["root_text"]
    return (rt["start"], rt["end"]) if rt else None


# ------------------------------------------------------------------------------ fixture itself


def test_fixture_files_say_synthetic_in_first_line():
    files = sorted(FIX.iterdir())
    assert {f.name for f in files} >= {
        "README.md",
        "tree-T9999-full.json",
        "tree-T9998-full.json",
        "T9999-juan1.html",
        "T9999-juan2.html",
    }
    for f in files:
        first = f.read_text(encoding="utf-8").splitlines()[0]
        assert "SYNTHETIC" in first, f.name


# ------------------------------------------------------------------------------------ small helpers


def test_split_title_and_display_label():
    assert sdp.split_title("【1-5 合成成就】") == ("1-5 合成成就", "")
    assert sdp.split_title("【1 合成問】\n請回報管理員，X,出現大於一次") == (
        "1 合成問",
        "請回報管理員，X,出現大於一次",
    )
    assert sdp.split_title("No. 262") == ("No. 262", "")
    assert sdp.display_label("1-5 合成成就") == "1-5"
    assert sdp.display_label("21 合成品(1合成)") == "21"
    assert sdp.display_label("合成序") is None
    assert sdp.display_label("2. Synthetica.合成品第二") is None


def test_link_ids_filters_by_document_and_splits_concatenations():
    links = ["T9997D01_001", "T9998D02_004T9998D02_009", "XX-KND04_020T9998D04_021", "T9998D01_001"]
    t = sdp.Title("【x】", links + ["T9998D01_001"], None, None, "1")
    ids, notes = sdp.link_ids(t, "T9998")
    # every T9998 id inside a link id, in order, once: concatenations with another version's id
    # (sdp's 'EN-KN…T1718…') are read too, not dropped
    assert ids == ["T9998D02_004", "T9998D02_009", "T9998D04_021", "T9998D01_001"]
    assert len(notes) == 2 and "XX-KND04_020T9998D04_021" in notes[1]
    assert sdp.link_ids(None, "T9998") == ([], [])


def test_text_on_line_tolerates_edition_differences_not_insertions():
    # CBETA T09n0262_p0016c05 / sdp's reading of it: one character differs
    assert sdp.text_on_line("父母念子。與子離", "邑，遂到其父所止之城。父每念子，與子離")
    # sdp inserts 序品第一 before T1718D01_003; CBETA T34n1718_p0003a18 has only 者也。
    assert not sdp.text_on_line("序品第一", "者也。")
    # sdp's inline apparatus is ignored; nothing left to compare counts as found
    assert sdp.text_on_line("〔上〕－【甲】", "無關")
    assert sdp.text_on_line("眉間光＋（明）【甲】", "從眉間光，下明")
    assert sdp.strip_ordinal("2 合成牛車") == "合成牛車" and sdp.strip_ordinal("序品") == "序品"


def test_corroboration_ignores_sdp_ordinals():
    node = lambda sid, text: sdp.SdpNode(sid, 1, None, tree_text=text)
    assert sdp.corroborated(node("a", "2 合成牛車"), node("b", "3 合成牛車"))
    assert sdp.corroborated(node("a", "合成牛車"), node("b", "1 合成牛車"))
    assert not sdp.corroborated(node("a", "2 合成牛車"), node("b", "2 合成羊車"))


def test_read_pages_start_rule_on_synthetic_html():
    pages = sdp.read_pages(
        [(k, (FIX / ("T9999-juan%s.html" % k)).read_text(encoding="utf-8")) for k in ("1", "2")]
    )
    d = pages.divs
    assert pages.doc_title.endswith("No. 9999 合成經")
    # first anchor inside the div comes before its text (nested: the anchor is in a child div)
    assert (d["T9999D02_001"].start, d["T9999D02_001"].inherited) == ("0001a05", False)
    # text before the first own anchor: start = the anchor before that text
    assert (d["T9999D03_002"].start, d["T9999D03_002"].inherited, d["T9999D03_002"].anchors) == (
        "0001a05",
        True,
        1,
    )
    # verse: the first text of the block is exact, a later verse text is not
    assert (d["T9999D03_004"].start, d["T9999D03_004"].exact) == ("0001a08", True)
    assert (d["T9999D03_005"].start, d["T9999D03_005"].inherited, d["T9999D03_005"].exact) == (
        "0001a08",
        True,
        False,
    )
    # no anchor of its own
    assert (d["T9999D03_006"].start, d["T9999D03_006"].anchors) == ("0001a15", 0)
    assert d["T9999D03_006"].first_anchor is None
    # does the node's content begin its line (nothing between the anchor and its first text)?
    assert d["T9999D02_001"].at_line_start and d["T9999D03_004"].at_line_start
    assert not d["T9999D03_002"].at_line_start  # 我聞合成 follows 如是合成， on 0001a05
    assert (d["T9999D03_002"].first_text, d["T9999D03_002"].first_anchor) == ("我聞合成", "0001a06")
    # div nesting is per page: a div open at a page end is closed there
    assert d["T9999D03_001"].parent == "T9999D02_001"
    assert d["T9999D02_003"].parent is None
    # headings: link labels excluded, links kept, server message after 】 kept in raw
    assert d["T9999D02_001"].title.raw == "【1 通序】" and d["T9999D02_001"].title.links == [
        "T9998D02_001"
    ]
    assert sdp.split_title(d["T9999D02_002"].title.raw)[1].startswith("請回報管理員")
    bare = [t.raw for kind, t in pages.order if kind == "bare"]
    assert bare == ["【1 序分二】", "【附文】", "【2 正宗分】", "【3 空節】"]
    assert pages.last_anchor == "0001a17"


# ------------------------------------------------------------------------------ merge with the tree


def test_resolve_root_heading_only_nodes_and_bare_headings():
    res = sdp.resolve(_sources()[0])
    n = res.nodes
    assert len(res.preorder) == 15 and res.missing == []
    assert (n["T9999D01_002"].title.raw, n["T9999D01_002"].title_is_bare) == ("【1 序分二】", True)
    assert (n["T9999D01_002"].start, n["T9999D01_002"].start_how, n["T9999D01_002"].start_from) == (
        "0001a05",
        "descendant",
        "T9999D02_001",
    )
    assert (n["T9999D01_003"].title.raw, n["T9999D01_003"].start) == ("【2 正宗分】", "0001a14")
    assert (n["T9999D02_005"].start, n["T9999D02_005"].start_how) == ("0001a17", "bare-heading")
    assert res.anomalies == [
        "bare heading 【附文】 (page 2, after line 0001a12) matches no tree node"
    ]


def test_resolve_commentary_gap_and_fetch_error_recovery():
    res = sdp.resolve(_sources()[1])
    n = res.nodes
    assert res.missing == ["2a"]
    assert n["T9998D02_002"].children == ["T9998D03_001", "T9998D03_002"]
    assert n["T9998D03_001"].recovered and n["T9998D03_002"].recovered
    assert res.preorder.index("T9998D03_002") == res.preorder.index("T9998D02_002") + 2
    assert (n["T9998D02_003"].gap, n["T9998D02_003"].start) == ("2a", None)
    assert n["T9998D02_004"].gap is None and n["T9998D02_004"].start == "0002a02"
    assert (n["T9998D01_001"].start, n["T9998D01_001"].start_how) == ("0001a01", "before-anchor")
    assert any("T9998D02_002" in a and "recovered" in a for a in res.anomalies)
    # without CBETA text the sdp-inserted 合成品第一 sets the start ...
    assert n["T9998D01_002"].start == "0001a02"


def test_resolve_falls_back_to_own_anchor_when_first_text_is_not_on_the_cbeta_line():
    n = sdp.resolve(_sources()[1], SYN_COM_LINES).nodes
    # ... with it, 合成品第一 is not on line 0001a02 (疏序正文。): the node's first own anchor
    assert (n["T9998D01_002"].start, n["T9998D01_002"].start_how) == ("0001a03", "own-anchor")
    assert "sdp-inserted" in n["T9998D01_002"].start_notes[0]
    # text that is on its line is kept
    assert (n["T9998D01_001"].start, n["T9998D01_001"].start_how) == ("0001a01", "before-anchor")


# ------------------------------------------------------------------------------- the two golds


def test_synthetic_golds_validate(syn):
    for doc in (syn.root, syn.commentary):
        rep = common.validate(doc)
        assert rep.errors == [] and rep.warnings == [], [f.render() for f in rep.findings]
        meta = doc["metadata"]
        assert meta["outline_profile"] == "zh-kepan" and meta["scheme_id"] == "zhiyi-wenju-sdp"
        assert (
            meta["eval_only"],
            meta["licence"]["id"],
            meta["gold_status"],
            meta["seeded_by"],
            meta["cbeta_release"],
            meta["outline_mode"],
        ) == (True, None, "imported-unchecked", None, "2026R2", "sutra")
        assert (meta["root_text_id"], meta["commentary_id"]) == ("T99n9999", "T99n9998")
        assert all(n["origin"] == "imported" and n["source_node_id"] for n in doc["nodes"])


def test_synthetic_root_gold_nodes(syn):
    by = _by_sid(syn.root)
    assert [n["source_node_id"] for n in syn.root["nodes"]][:3] == [
        "T9999D01_001",
        "T9999D01_002",
        "T9999D02_001",
    ]
    assert by["T9999D02_001"]["id"] == "2_1.1_2" and by["T9999D03_007"]["id"] == "3_1.2_2.2_3"
    # heading: bare heading for heading-only nodes, tree text in a note; display label = ordinal
    n = by["T9999D01_002"]
    assert (n["heading_src"], n["display_label"], n["flags"]) == (
        "1 序分二",
        "1",
        ["anchor_inherited"],
    )
    assert "sdp tree text differs: 序品第一" in n["notes"]
    assert by["T9999D01_001"]["display_label"] is None
    assert by["T9999D02_002"]["heading_src"] == "2 別序"
    assert any(x.startswith("sdp head_title text after 】") for x in by["T9999D02_002"]["notes"])
    # spans: end = the last line, inclusive: the line before the successor's start when the
    # successor begins its line, else the successor's (shared) start line; the last node ends at
    # the document's last anchor
    lh = lambda s: "T99n9999_p" + s
    assert _root_span(by["T9999D01_002"]) == (lh("0001a05"), lh("0001a13"))  # successor a14 begins
    assert _root_span(by["T9999D03_001"]) == (lh("0001a05"), lh("0001a05"))  # 我聞 mid-line a05
    assert _root_span(by["T9999D03_002"]) == (lh("0001a05"), lh("0001a06"))
    assert _root_span(by["T9999D03_004"]) == (lh("0001a08"), lh("0001a08"))  # verse, shared line
    assert _root_span(by["T9999D03_006"]) == (lh("0001a15"), lh("0001a15"))
    assert _root_span(by["T9999D02_005"]) == (lh("0001a17"), lh("0001a17"))
    assert by["T9999D01_002"]["locations"]["root_text"]["end_basis"] == "next-node"
    assert by["T9999D02_005"]["locations"]["root_text"]["end_basis"] == "sdp-anchor"
    # unmapped = this gold's primary locator (root_text) is missing: never here
    assert not any("unmapped" in n["flags"] for n in syn.root["nodes"])
    assert by["T9999D03_002"]["flags"] == []  # prose before its own anchor: not inherited
    assert "anchor_inherited" in by["T9999D03_005"]["flags"]  # verse after the anchored first line
    assert "anchor_inherited" in by["T9999D03_006"]["flags"]  # no anchor of its own
    assert "anchor_inherited" in by["T9999D02_005"]["flags"]  # bare-heading start
    assert by["T9999D01_002"]["locations"]["root_text"]["basis"] == "sdp-anchor"
    # commentary positions through the links
    com = lambda sid: by[sid]["locations"]["commentary"]
    assert com("T9999D02_001") == {
        "announced": None,
        "explained": "T99n9998_p0001a04",
        "raw": "sdp 文句 link T9998D02_001",
    }
    assert com("T9999D03_003")["explained"] == "T99n9998_p0001a06"  # link into a recovered node
    assert (
        com("T9999D02_004")["explained"] == "T99n9998_p0002a02"
    )  # malformed link, first part used
    for sid, why in (
        ("T9999D01_001", "not corroborated"),
        ("T9999D02_003", "HTML unavailable (卷 2a)"),
        ("T9999D03_001", "no 文句"),
    ):
        # a missing commentary line is the secondary locator here: noted, not flagged
        assert com(sid)["explained"] is None and "unmapped" not in by[sid]["flags"]
        assert any(why in x for x in by[sid]["notes"]), (sid, by[sid]["notes"])


def test_fetch_error_node_without_recovered_children_is_truncated(tmp_path):
    # a copy of the synthetic fixture with one more fetch_error node, T9998D02_005, that no HTML
    # page carries: its children are unknown, so the gold flags it truncated (D15 addendum)
    for f in FIX.iterdir():
        (tmp_path / f.name).write_bytes(f.read_bytes())
    tree_path = tmp_path / "tree-T9998-full.json"
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    tree[2]["children"].append(
        {
            "id": "T9998D02_005",
            "text": "3 SYNTHETIC",
            "leaf": False,
            "children": None,
            "fetch_error": "query maybe faile (SYNTHETIC)",
        }
    )
    tree_path.write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
    root, com = _sources()
    com = sdp.SdpSource(
        com.doc, com.cbeta_id, tree_path, [(k, tmp_path / Path(p).name) for k, p in com.html]
    )
    golds = sdp.build_golds(root, com, SYN_ROOT_LINES, SYN_COM_LINES)
    by = _by_sid(golds.commentary)
    assert "truncated" in by["T9998D02_005"]["flags"]
    assert any("its subtree is unknown" in x for x in by["T9998D02_005"]["notes"])
    assert "truncated" not in by["T9998D02_002"]["flags"]
    assert common.validate(golds.commentary).errors == []
    # the gold's own format_note states the fetch_error rule (gold README: import rules are there)
    note = golds.commentary["metadata"]["format_note"]
    assert "fetch_error" in note and "flag truncated" in note
    # the served-halves scope rule is the commentary (E01) gold's only; the root-text gold is not narrowed
    assert "Scoring scope (E01 keys on commentary.explained)" in note
    assert "Scoring scope" not in golds.root["metadata"]["format_note"]


def test_synthetic_commentary_gold_nodes(syn):
    by = _by_sid(syn.commentary)
    lh = lambda s: "T99n9999_p" + s
    assert [n["source_node_id"] for n in syn.commentary["nodes"]] == [
        "T9998D01_001",
        "T9998D01_002",
        "T9998D02_001",
        "T9998D02_002",
        "T9998D03_001",
        "T9998D03_002",
        "T9998D01_003",
        "T9998D02_003",
        "T9998D02_004",
    ]
    assert by["T9998D02_002"]["locations"]["commentary"] == {
        "announced": None,
        "explained": "T99n9998_p0001a05",
    }
    assert any(x.startswith("fetch_error:") for x in by["T9998D02_002"]["notes"])
    assert "truncated" not in by["T9998D02_002"]["flags"]  # its subtree was recovered
    assert syn.commentary["metadata"]["anomalies"] == [
        "T9998D02_002: sdp getTreeNode failed for it (fetch_error); "
        "its subtree was recovered from the HTML"
    ]
    # the sdp-inserted text before T9998D01_002's first anchor does not decide its line
    n = by["T9998D01_002"]
    assert n["locations"]["commentary"]["explained"] == "T99n9998_p0001a03" and n["flags"] == []
    assert any("sdp-inserted" in x for x in n["notes"])
    # root spans borrowed from the corroborated linking node
    assert _root_span(by["T9998D01_002"]) == (lh("0001a05"), lh("0001a13"))
    assert _root_span(by["T9998D02_004"]) == (
        lh("0001a15"),
        lh("0001a17"),
    )  # not from the wrong link
    # shares a heading but lies outside its parent's span in this tree: dropped, flagged, noted
    n = by["T9998D03_002"]
    assert n["locations"]["root_text"] is None and "unmapped" in n["flags"]
    assert any("outside its parent's root span" in x for x in n["notes"])
    # gap node: no position estimated (primary locator missing: flagged), a corroborated root span
    n = by["T9998D02_003"]
    assert n["locations"]["commentary"]["explained"] is None and "unmapped" in n["flags"]
    assert "sdp T9998 HTML unavailable (卷 2a)" in n["notes"]
    assert _root_span(n) == (lh("0001a14"), lh("0001a14"))
    # no root span: flagged, as the schema's sūtra-mode rule requires, though explained is set
    n = by["T9998D01_001"]
    assert n["locations"]["commentary"]["explained"] and n["flags"] == ["unmapped"]
    assert syn.stats["unmapped_by_gap"] == {
        "root nodes whose linked node is in 卷 2a": 1,
        "commentary nodes in 卷 2a": 1,
    }


def test_synthetic_crosswalk(syn):
    header, *rows = syn.crosswalk
    assert header == [
        "t9999_sdp_id",
        "t9999_gold_id",
        "t9999_start",
        "t9998_sdp_id",
        "t9998_gold_id",
        "t9998_explained",
        "status",
        "corroborated",
    ]
    assert len({(r[0], r[3]) for r in rows}) == len(rows)  # one row per link
    status = {(r[0], r[3]): r[6] for r in rows}
    assert status == {
        ("T9999D01_001", "T9998D02_004"): "uncorroborated",
        ("T9999D01_002", "T9998D01_002"): "located",
        ("T9999D02_001", "T9998D02_001"): "located",
        ("T9999D02_002", "T9998D02_002"): "located",
        ("T9999D03_003", "T9998D03_001"): "located",
        ("T9999D01_003", "T9998D01_003"): "located",
        ("T9999D02_003", "T9998D02_003"): "gap-2a",
        ("T9999D02_004", "T9998D02_004"): "located",
        ("T9999D02_004", "T9998D02_009"): "not-in-tree",
        ("T9999D03_007", "T9998D03_002"): "located",
    }
    corroborated = {(r[0], r[3]): r[7] for r in rows}
    assert corroborated[("T9999D01_001", "T9998D02_004")] == "no"
    assert corroborated[("T9999D02_004", "T9998D02_009")] == "n/a"
    assert corroborated[("T9999D02_003", "T9998D02_003")] == "yes"  # gap node, tree heading
    assert sum(v == "yes" for v in corroborated.values()) == 8
    row = next(r for r in rows if r[0] == "T9999D02_001")
    assert row[1:] == [
        "2_1.1_2",
        "T99n9999_p0001a05",
        "T9998D02_001",
        "2_1.1_2",
        "T99n9998_p0001a04",
        "located",
        "yes",
    ]


def test_missing_cbeta_line_is_flagged_never_kept():
    root, com = _sources()
    lines = {k: v for k, v in SYN_ROOT_LINES.items() if k != "T99n9999_p0001a16"}
    golds = sdp.build_golds(root, com, lines, SYN_COM_LINES)
    by = _by_sid(golds.root)
    n = by["T9999D03_007"]  # starts at the missing line
    assert n["locations"]["root_text"] is None and "unmapped" in n["flags"]
    assert any("T99n9999_p0001a16 is not a line of T99n9999" in x for x in n["notes"])
    n = by["T9999D03_006"]  # ends at it
    assert n["locations"]["root_text"]["end"] is None
    assert any("end T99n9999_p0001a16" in x for x in n["notes"])
    assert common.validate(golds.root).errors == []


# ------------------------------------------------------------------------------------------ common


def test_number_tree_assigns_zh_ids_in_preorder():
    drafts = [
        {
            "heading_src": "a",
            "children": [
                {"heading_src": "a1", "children": []},
                {"heading_src": "a2", "children": [{"heading_src": "a2i"}]},
            ],
        },
        {"heading_src": "b", "children": []},
    ]
    nodes = common.number_tree(drafts)
    assert [
        (n["id"], n["parent_id"], n["order"], n["sibling_index"], n["level"], n["heading_src"])
        for n in nodes
    ] == [
        ("1_1", None, 1, 1, 1, "a"),
        ("1_1.1_2", "1_1", 2, 1, 2, "a1"),
        ("1_1.2_2", "1_1", 3, 2, 2, "a2"),
        ("1_1.2_2.1_3", "1_1.2_2", 4, 1, 3, "a2i"),
        ("2_1", None, 5, 2, 1, "b"),
    ]
    assert nodes[3]["path"] == ["1_1", "2_2", "1_3"] and "children" not in nodes[0]
    assert "children" in drafts[0]  # drafts are not modified
    meta = common.zh_metadata(nodes, scheme_id="x", node_count=99)
    assert (
        meta["outline_profile"],
        meta["node_count"],
        meta["max_depth"],
        meta["nodes_per_level"],
    ) == ("zh-kepan", 5, 3, {"1": 2, "2": 2, "3": 1})


def test_common_uses_the_validator_script_not_a_copy():
    vo = common.load_validator()
    assert Path(vo.__file__).resolve() == REPO / "scripts" / "validate_outline.py"
    assert common.load_validator() is vo
    rep = common.validate(
        json.loads((REPO / "tests/fixtures/outline-zh/minimal.json").read_text(encoding="utf-8"))
    )
    assert rep.passed()
    src = (GOLD_PKG / "common.py").read_text(encoding="utf-8")
    assert "def structural_findings" not in src and "def compare_refs" not in src


def test_compose_linehead_and_json_roundtrip(tmp_path):
    assert common.compose_linehead("T09n0262", "0001c18") == "T09n0262_p0001c18"
    path = common.write_json({"a": "序"}, tmp_path / "x" / "o.json")
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": "序"} and "序" in path.read_text(
        encoding="utf-8"
    )


FORBIDDEN_STAGES = (
    "chinese_workflow.outline",
    "chinese_workflow.chunk",
    "chinese_workflow.translate",
)


def _imported_modules(src: str, package: str) -> list:
    """Every module a source file imports, relative imports resolved against `package` (the
    file's own package): `from ..outline import x` and `from .. import outline` count too, as
    `<parent>.outline` (final review M6). For `from M import a` both M and M.a are listed, since
    `a` may be a submodule."""
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - n.level + 1])
                mod = f"{base}.{n.module}" if n.module else base
            else:
                mod = n.module or ""
            out += [mod] + [f"{mod}.{a.name}" for a in n.names]
    return out


def test_stage_boundary_check_resolves_relative_imports():
    pkg = "chinese_workflow.eval"  # a module one level below chinese_workflow
    for src in (
        "from ..outline import parser",
        "from .. import outline",
        "from ..chunk.rules import x",
        "import chinese_workflow.translate",
        "from chinese_workflow import translate",
    ):
        assert any(m.startswith(FORBIDDEN_STAGES) for m in _imported_modules(src, pkg)), src
    for src in ("from ..ingest import lines", "from . import common", "from .gold import sdp"):
        assert not any(m.startswith(FORBIDDEN_STAGES) for m in _imported_modules(src, pkg)), src
    # from inside the gold package the outline stage is three levels up
    gold = "chinese_workflow.eval.gold"
    assert "chinese_workflow.outline" in _imported_modules("from ... import outline", gold)
    assert "chinese_workflow.ingest.lines" in _imported_modules("from ...ingest import lines", gold)


def test_gold_package_respects_stage_boundaries():
    """gold builders may import chinese_workflow.ingest, never outline / chunk / translate,
    absolute or relative."""
    for f in GOLD_PKG.glob("*.py"):
        for m in _imported_modules(f.read_text(encoding="utf-8"), "chinese_workflow.eval.gold"):
            assert not m.startswith(FORBIDDEN_STAGES), (f.name, m)


# ----------------------------------------------------------------------- real data (skip if absent)


@pytest.fixture(scope="module")
def real():
    missing = [p for p in RAW_FILES if not p.exists()]
    if missing:
        pytest.skip(
            "raw data absent (%s); run scripts/fetch_dila_sdp.sh and scripts/fetch_cbeta.sh"
            % ", ".join(common.repo_relative(p) for p in missing)
        )
    root, com = sdp.default_sources(RAW_SDP)
    return sdp.build_golds(
        root,
        com,
        common.line_texts(RAW_CBETA / "T09n0262.xml"),
        common.line_texts(RAW_CBETA / "T34n1718.xml"),
    )


def test_real_golds_validate(real):
    for doc in (real.root, real.commentary):
        rep = common.validate(doc)
        assert rep.errors == [], [f.render() for f in rep.errors[:10]]
        assert (doc["metadata"]["root_text_id"], doc["metadata"]["commentary_id"]) == (
            "T09n0262",
            "T34n1718",
        )


def test_real_tongxu_start_per_rule(real):
    by = _by_sid(real.root)
    n = by["T0262D02_010"]
    # the div opens after anchor 0001c18 (序品第一); its first anchor 0001c19 precedes its
    # text 如是我聞
    assert n["locations"]["root_text"]["start"] == "T09n0262_p0001c19"
    assert "anchor_inherited" not in n["flags"]
    # R03 F23: 身意泰然 begins on 0010c12, before the node's first anchor 0010c13
    assert by["T0262D09_054"]["locations"]["root_text"]["start"] == "T09n0262_p0010c12"
    # inclusive ends: 別序 begins line 0002b07, so 通序 ends on b06; D09_054 begins mid-line c12
    assert n["locations"]["root_text"]["end"] == "T09n0262_p0002b06"
    assert by["T0262D09_053"]["locations"]["root_text"]["end"] == "T09n0262_p0010c12"


# Checked by hand against T1718-juan1a.html and T34n1718.xml (fix round 1): the 12 T1718 nodes
# whose explained line lies in the dev split T34n1718_p0001b18 - p0016b02.
DEV_EXPLAINED = {
    "T1718D01_002": "0001b21",
    "T1718D01_003": "0003a19",  # not a18: sdp inserts 序品第一 there; a18 = 者也。
    "T1718D02_001": "0003a19",
    "T1718D03_001": "0003a19",
    "T1718D03_002": "0005c29",  # the line-final 釋 of 0005c29 opens 釋同聞眾
    "T1718D04_001": "0005c29",
    "T1718D05_001": "0005c29",
    "T1718D06_001": "0005c29",
    "T1718D07_001": "0005c29",
    "T1718D08_001": "0005c29",
    "T1718D08_002": "0007b04",
    "T1718D08_003": "0008a09",
}


def test_real_dev_span_explained_lines(real):
    got = {
        n["source_node_id"]: n["locations"]["commentary"]["explained"]
        for n in real.commentary["nodes"]
        if n["locations"]["commentary"]["explained"]
        and "T34n1718_p0001b18" <= n["locations"]["commentary"]["explained"] < "T34n1718_p0016b02"
    }
    assert got == {sid: "T34n1718_p" + lb for sid, lb in DEV_EXPLAINED.items()}
    # the fix reaches the T0262 gold through the 文句 link 序分 -> T1718D01_003
    by = _by_sid(real.root)
    assert by["T0262D01_005"]["locations"]["commentary"]["explained"] == "T34n1718_p0003a19"


def test_real_counts_match_r04(real):
    st = real.stats
    # R04 F30 / Task 1: T0262 tree 2,048 nodes / 1,345 leaves / 19 levels, 2,017 content divs,
    # 188 content nodes without an anchor of their own. F31 counts 1,688 content-div nodes with a
    # 文句 link; reading the T1718 ids inside its 7 malformed link ids (6 of them concatenated
    # with an EN-KN id) adds 6
    assert (st["root"]["nodes"], st["root"]["leaves"], st["root"]["max_depth"]) == (2048, 1345, 19)
    assert st["root"]["content-div nodes"] == 2017
    assert st["root"]["anchor_inherited: no anchor of its own"] == 188
    assert st["root"]["with commentary link, content-div nodes"] == 1694
    assert st["root"]["with commentary link"] == 1722
    by = _by_sid(real.root)
    assert "T1718D12_021" in by["T0262D12_021"]["locations"]["commentary"]["raw"]
    # crosswalk: one row per link, 1,378 corroborated (1 of them only once ordinals are ignored)
    rows = real.crosswalk[1:]
    assert len(rows) == len({(r[0], r[3]) for r in rows}) == 1728
    assert sum(r[7] == "yes" for r in rows) == 1378
    # Task 1: T1718 tree 1,453 nodes; the 5 HTML divs under fetch_error node T1718D08_018 are added
    assert (st["commentary"]["nodes"], st["commentary"]["recovered from HTML"]) == (1458, 5)
    assert st["commentary"]["fetch_error nodes"] == 27
    # the 26 whose subtree is unknown are flagged truncated; the recovered T1718D08_018 is not
    truncated = [n["source_node_id"] for n in real.commentary["nodes"] if "truncated" in n["flags"]]
    assert len(truncated) == 26 and "T1718D08_018" not in truncated
    assert not any("truncated" in n["flags"] for n in real.root["nodes"])
    assert all(n["locations"]["root_text"] for n in real.root["nodes"])
