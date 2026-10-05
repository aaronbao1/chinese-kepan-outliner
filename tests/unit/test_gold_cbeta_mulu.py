"""Tests for chinese_workflow.eval.gold.cbeta_mulu — Task 7 of
the eval-datasets plan (self-outlining / sutra-span / root_text: Fix round 1,
2026-09-22, per the controller's correction against the schema's own named example for X11n0268).

Always run: the numeral parser (cjk_number / announced_count) and the tree builder on a SYNTHETIC
CBETA-shaped XML fixture (fictional id X99n9998; every heading below is invented and says nothing
about a real text) exercising every documented case: a clean level-1 root, a level jump (level 1 ->
level 3 directly), a fresh top-level run with no level-1 ancestor, a merged two-label node (full-
width space), a parenthesised child count that matches, one that does not (count_mismatch), a bare
trailing numeral that self-verifies, one that does not (silently null), an R017 alt-linehead pair
(X-canon files only), and root_text span computation (same-line clamping, gap-line inclusion,
bottom-up parent-from-last-child inheritance, and the end-of-file fallback for the last node).

Run when data/raw is present (skip otherwise; scripts/fetch_cbeta_xml_p5.sh):
data/raw/cbeta/xml-p5/X/X11/X11n0268.xml, P/P167/P167n1573.xml, D/D14/D14n8842.xml and
data/raw/cbeta/survey/mulu-nodes-kepan.tsv (R02 F15/F28) — the three real golds build, validate
with zero errors even under --strict, and their node counts and level histograms agree with the
survey.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

from chinese_workflow.eval.gold import cbeta_mulu, common

REPO = Path(__file__).resolve().parents[2]
RAW_CBETA = REPO / "data" / "raw" / "cbeta"
XML_P5 = RAW_CBETA / "xml-p5"
SURVEY = RAW_CBETA / "survey" / "mulu-nodes-kepan.tsv"


# ------------------------------------------------------------------------------ numeral parsing


@pytest.mark.parametrize(
    "s,want",
    [
        ("一", 1),
        ("二", 2),
        ("九", 9),
        ("十", 10),
        ("十一", 11),
        ("十二", 12),
        ("二十", 20),
        ("二十三", 23),
        ("", None),
        ("十十", None),  # not a shape this parses
        ("甲", None),
        ("百", None),
    ],
)
def test_cjk_number(s, want):
    assert cbeta_mulu.cjk_number(s) == want


@pytest.mark.parametrize(
    "heading,want_count,want_paren",
    [
        ("初序分(二)", 2, True),
        ("二正宗分(六)", 6, True),
        ("初通序(六)", 6, True),
        ("科此經為二", 2, False),
        ("次本文二", 2, False),
        ("初能觀人", None, False),  # no trailing numeral at all
        ("二緣覺眾　三菩薩眾", None, False),  # ends in 眾, not a numeral
        ("十地菩薩", None, False),  # numeral is a PREFIX, not trailing
        ("(二)", 2, True),  # the parenthesised marker is unambiguous even with no leading text
    ],
)
def test_announced_count(heading, want_count, want_paren):
    assert cbeta_mulu.announced_count(heading) == (want_count, want_paren)


# --------------------------------------------------------------------------- synthetic tree build


def _hit(level, text, linehead, ordinal, r017=None):
    return cbeta_mulu.MuluHit(level=level, heading_src=text, linehead=linehead, ordinal=ordinal, r017_linehead=r017)


def _by_heading(nodes, text):
    hit = [n for n in nodes if n["heading_src"] == text]
    assert len(hit) == 1, (text, [n["heading_src"] for n in nodes])
    return hit[0]


# The full own-canon line sequence of the (invented) file, INCLUDING lines with no mulu on them
# (0001a05, 0002a02, 0003a02) — needed to check that root_text.end walks the file's whole line
# order, not just the lines that carry a cb:mulu.
SYN_ALL_LINEHEADS = [
    "X99n9998_p0001a01",
    "X99n9998_p0001a02",
    "X99n9998_p0001a03",
    "X99n9998_p0001a04",
    "X99n9998_p0001a05",  # gap: no mulu here
    "X99n9998_p0002a01",
    "X99n9998_p0002a02",  # gap: no mulu here
    "X99n9998_p0003a01",
    "X99n9998_p0003a02",  # trailing gap: the file's true last line
]


@pytest.fixture
def synthetic_nodes():
    """A SYNTHETIC hit sequence (module docstring) run through build_tree, then common.number_tree."""
    hits = [
        _hit(1, "初根(二)", "X99n9998_p0001a01", 1),
        _hit(3, "初根之孫(誤跳)", "X99n9998_p0001a01", 2),  # level jump: 1 -> 3 directly
        _hit(2, "次根之子(二)", "X99n9998_p0001a02", 3),  # back to a proper child of the root
        _hit(3, "初孫甲(二)", "X99n9998_p0001a02", 4),  # parenthesised, matches (2 children below)
        _hit(4, "曾孫一", "X99n9998_p0001a03", 5),
        _hit(4, "曾孫二　又一支", "X99n9998_p0001a03", 6, r017="R017_p9998a03"),  # merged + R017
        _hit(3, "二孫乙(三)", "X99n9998_p0001a04", 7),  # parenthesised, MISMATCH (only 1 child)
        _hit(4, "曾孫三", "X99n9998_p0001a04", 8),
        _hit(1, "分二", "X99n9998_p0002a01", 9),  # a fresh top-level run, no level-1 ancestor issue
        _hit(2, "分二之甲", "X99n9998_p0002a01", 10),
        _hit(2, "分二之乙", "X99n9998_p0002a01", 11),
        _hit(1, "另起爐灶二", "X99n9998_p0003a01", 12),  # bare trailing numeral, 0 children: unverified
    ]
    built = cbeta_mulu.build_tree(hits, "X99n9998", SYN_ALL_LINEHEADS)
    nodes = common.number_tree(built.roots)
    return nodes, built


def _span(node):
    rt = node["locations"]["root_text"]
    return rt["start"], rt["end"]


def test_level_jump_flagged_and_structural_level(synthetic_nodes):
    nodes, built = synthetic_nodes
    jump = _by_heading(nodes, "初根之孫(誤跳)")
    assert jump["level"] == 2  # structural: parent (初根, level 1) + 1, never inventing level 2
    assert jump["parent_id"] == _by_heading(nodes, "初根(二)")["id"]
    assert "irregular_label" in jump["flags"]
    assert any('level="3"' in n and 'level="1"' in n for n in jump["notes"])
    assert built.jump_count == 1  # the only true jump; the two level-1 roots below are not jumps


def test_merged_heading_kept_verbatim_and_flagged(synthetic_nodes):
    nodes, built = synthetic_nodes
    merged = _by_heading(nodes, "曾孫二　又一支")
    assert "merged_range" in merged["flags"]
    assert any("full-width space" in n for n in merged["notes"])
    assert built.merged_count == 1


def test_r017_linehead_kept_only_as_a_note(synthetic_nodes):
    nodes, _ = synthetic_nodes
    merged = _by_heading(nodes, "曾孫二　又一支")
    assert merged["locations"]["commentary"]["explained"] == "X99n9998_p0001a03"
    assert merged["locations"]["commentary"]["announced"] == "X99n9998_p0001a03"
    assert any("R017_p9998a03" in n and "X-canon" in n for n in merged["notes"])


def test_child_count_paren_matches(synthetic_nodes):
    nodes, built = synthetic_nodes
    ok = _by_heading(nodes, "初孫甲(二)")
    assert ok["child_count_announced"] == 2  # 曾孫一, 曾孫二merged: 2 children, matches
    assert "count_mismatch" not in ok["flags"]
    root = _by_heading(nodes, "初根(二)")
    assert root["child_count_announced"] == 2  # 初根之孫(誤跳), 次根之子(二): 2 children, matches
    assert "count_mismatch" not in root["flags"]


def test_child_count_paren_mismatch_flagged(synthetic_nodes):
    nodes, built = synthetic_nodes
    bad = _by_heading(nodes, "二孫乙(三)")
    assert bad["child_count_announced"] == 3
    assert "count_mismatch" in bad["flags"]
    assert any("announces 3 children" in n and "1 present" in n for n in bad["notes"])
    assert built.count_mismatch == 1


def test_bare_trailing_numeral_self_verified(synthetic_nodes):
    nodes, built = synthetic_nodes
    two_kids = _by_heading(nodes, "分二")
    assert two_kids["child_count_announced"] == 2  # 分二之甲, 分二之乙: bare "二", self-verified
    assert "count_mismatch" not in two_kids["flags"]


def test_bare_trailing_numeral_not_verified_stays_null(synthetic_nodes):
    nodes, _ = synthetic_nodes
    lone_root = _by_heading(nodes, "另起爐灶二")
    assert lone_root["child_count_announced"] is None  # bare "二" announced, 0 children: unverified
    assert lone_root["flags"] == []  # no spurious count_mismatch for an unverified bare numeral


def test_every_node_is_sutra_span_with_resolved_root_text(synthetic_nodes):
    nodes, _ = synthetic_nodes
    assert all(n["node_class"] == "sutra-span" for n in nodes)
    assert all(n["locations"]["root_text"] is not None for n in nodes)
    assert all(n["locations"]["root_text"]["basis"] == "cbeta-mulu" for n in nodes)
    assert all(n["locations"]["scheme"] == "cbeta-kepan" for n in nodes)
    assert all("unmapped" not in n["flags"] for n in nodes)  # never needed: root_text is never null


def test_root_text_start_equals_own_linehead(synthetic_nodes):
    nodes, _ = synthetic_nodes
    for n in nodes:
        assert n["locations"]["root_text"]["start"] == n["locations"]["commentary"]["explained"]


def test_root_text_end_same_line_clamped(synthetic_nodes):
    """A leaf whose very next hit sits on the same physical line cannot end before it starts."""
    nodes, _ = synthetic_nodes
    jump = _by_heading(nodes, "初根之孫(誤跳)")  # next hit (次根之子) is on the very next line
    assert _span(jump) == ("X99n9998_p0001a01", "X99n9998_p0001a01")
    sun1 = _by_heading(nodes, "曾孫一")  # next hit (曾孫二) shares its own line 0001a03
    assert _span(sun1) == ("X99n9998_p0001a03", "X99n9998_p0001a03")
    kid10 = _by_heading(nodes, "分二之甲")  # next hit (分二之乙) shares its own line 0002a01
    assert _span(kid10) == ("X99n9998_p0002a01", "X99n9998_p0002a01")


def test_root_text_end_includes_gap_lines(synthetic_nodes):
    """end walks the file's FULL line order, not just cb:mulu-bearing lines."""
    nodes, _ = synthetic_nodes
    sun3 = _by_heading(nodes, "曾孫三")  # next hit (分二) starts at 0002a01; gap line 0001a05 is its
    assert _span(sun3) == ("X99n9998_p0001a04", "X99n9998_p0001a05")
    kid11 = _by_heading(nodes, "分二之乙")  # next hit (另起爐灶二) starts at 0003a01; gap 0002a02
    assert _span(kid11) == ("X99n9998_p0002a01", "X99n9998_p0002a02")


def test_root_text_end_inherited_bottom_up(synthetic_nodes):
    """An interior node's end is exactly its last child's end (module docstring), all the way up."""
    nodes, _ = synthetic_nodes
    assert _span(_by_heading(nodes, "初孫甲(二)")) == ("X99n9998_p0001a02", "X99n9998_p0001a03")
    assert _span(_by_heading(nodes, "二孫乙(三)")) == ("X99n9998_p0001a04", "X99n9998_p0001a05")
    assert _span(_by_heading(nodes, "次根之子(二)")) == ("X99n9998_p0001a02", "X99n9998_p0001a05")
    assert _span(_by_heading(nodes, "初根(二)")) == ("X99n9998_p0001a01", "X99n9998_p0001a05")
    assert _span(_by_heading(nodes, "分二")) == ("X99n9998_p0002a01", "X99n9998_p0002a02")


def test_root_text_end_of_file_for_last_node(synthetic_nodes):
    """The file's very last cb:mulu node has no successor: end = the file's true last line, not
    its own start line, end_basis null, and a note explaining why."""
    nodes, _ = synthetic_nodes
    last = _by_heading(nodes, "另起爐灶二")
    assert _span(last) == ("X99n9998_p0003a01", "X99n9998_p0003a02")
    rt = last["locations"]["root_text"]
    assert rt["end_basis"] is None
    assert any("last cb:mulu" in n for n in last["notes"])


def test_root_text_end_basis_next_node_otherwise(synthetic_nodes):
    nodes, _ = synthetic_nodes
    ordinary = _by_heading(nodes, "初孫甲(二)")
    assert ordinary["locations"]["root_text"]["end_basis"] == "next-node"


def test_root_text_child_spans_lie_inside_parent_spans(synthetic_nodes):
    """scripts/validate_outline.py [child-outside-parent], checked directly here too."""
    nodes, _ = synthetic_nodes
    by_id = {n["id"]: n for n in nodes}
    order = {lh: i for i, lh in enumerate(SYN_ALL_LINEHEADS)}
    for n in nodes:
        if n["parent_id"] is None:
            continue
        parent = by_id[n["parent_id"]]
        p_start, p_end = _span(parent)
        c_start, c_end = _span(n)
        assert order[p_start] <= order[c_start] <= order[c_end] <= order[p_end]


def test_source_node_id_is_ordinal(synthetic_nodes):
    nodes, _ = synthetic_nodes
    ids = [n["source_node_id"] for n in nodes]
    assert ids == ["X99n9998#%d" % (i + 1) for i in range(len(nodes))]


def test_three_top_level_roots(synthetic_nodes):
    nodes, _ = synthetic_nodes
    assert sum(1 for n in nodes if n["parent_id"] is None) == 3  # 初根, 分二, 另起爐灶


def test_synthetic_tree_validates(synthetic_nodes):
    nodes, _ = synthetic_nodes
    doc = {
        "metadata": common.zh_metadata(
            nodes,
            source_file="synthetic",
            source_sha256=None,
            text_id="X9998",
            text_title_src="合成經",
            text_title_en="",
            author=None,
            source_language="lzh",
            format_note="synthetic fixture for test_gold_cbeta_mulu",
            generated_by="test_gold_cbeta_mulu",
            source_document={"kind": "root-text", "text_id": "X99n9998", "title": "合成經", "url": None, "notes": []},
            outline_mode="self-outlining",
            root_text_id="X99n9998",
            commentary_id=None,
            scheme_id=cbeta_mulu.SCHEME_ID,
            seeded_by=None,
            gold_status="synthetic-fixture",
            licence={"id": None, "holder": None, "statement": "synthetic", "evidence": None},
            eval_only=True,
            cbeta_release="2026R2",
        ),
        "nodes": nodes,
    }
    rep = common.validate(doc)
    assert rep.errors == []
    assert rep.warnings == []


# ---------------------------------------------------------------------------- CLI, synthetic XML


def _write_xml(path: Path, xml_id: str, author: str, title: str, body_lines: list) -> None:
    """body_lines: [(own-canon lb n, [(level, text), ...] mulu on this line, r017 n or None)]."""
    parts = []
    for n, mulu_specs, r017 in body_lines:
        lb = '<lb n="%s" ed="X"/>' % n
        if r017:
            lb += '<lb n="%s" ed="R017"/>' % r017
        mulu = "".join(
            '<cb:mulu level="%d" type="科判">%s</cb:mulu>' % (lv, t) for lv, t in mulu_specs
        )
        parts.append("%s%s<cb:div type=\"orig\"><p>text.</p></cb:div>" % (lb, mulu))
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0" '
        'xml:id="%s"><teiHeader><fileDesc><titleStmt>'
        '<title level="m" xml:lang="zh-Hant">%s</title><author>%s</author>'
        "</titleStmt></fileDesc></teiHeader>"
        "<text><body>\n%s\n</body></text></TEI>\n" % (xml_id, title, author, "\n".join(parts)),
        encoding="utf-8",
    )


def test_cli_end_to_end_on_synthetic_xml(tmp_path, capsys, monkeypatch):
    xml_path = tmp_path / "X99n9998.xml"
    _write_xml(
        xml_path,
        "X99n9998",
        "某甲述",
        "合成經集註",
        [
            ("0001a01", [(1, "初根(二)")], None),
            ("0001a02", [(2, "次根之子")], None),
        ],
    )
    out = tmp_path / "out" / "outline.json"
    rc = cbeta_mulu.main([str(xml_path), "--out", str(out)])
    assert rc == 0
    printed = capsys.readouterr().out
    assert "PASS" in printed and "nodes=2" in printed
    assert out.exists()


def test_cli_skips_missing_file(tmp_path, capsys):
    rc = cbeta_mulu.main([str(tmp_path / "nope.xml"), "--out", str(tmp_path / "out.json")])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out
    assert not (tmp_path / "out.json").exists()


# ----------------------------------------------------------------------- real data (skip if absent)


def _survey_counts() -> dict:
    counts: dict = Counter()
    levels: dict = {}
    with open(SURVEY, encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            counts[row["file"]] += 1
            levels.setdefault(row["file"], set()).add(int(row["level"]))
    return counts, levels


@pytest.fixture(scope="module")
def raw_ready():
    need = [
        XML_P5 / "X" / "X11" / "X11n0268.xml",
        XML_P5 / "P" / "P167" / "P167n1573.xml",
        XML_P5 / "D" / "D14" / "D14n8842.xml",
        SURVEY,
    ]
    missing = [p for p in need if not p.exists()]
    if missing:
        pytest.skip(
            "raw CBETA xml-p5 clone or survey absent (%s); run scripts/fetch_cbeta_xml_p5.sh "
            "and scripts/survey_cbeta_xml_p5.py" % ", ".join(common.repo_relative(p) for p in missing)
        )


@pytest.mark.parametrize(
    "cbeta_id,short_id,expect_nodes,expect_max_level",
    [
        ("X11n0268", "X0268", 2611, 28),
        ("P167n1573", "P1573", 127, 15),
        ("D14n8842", "D8842", 40, 10),
    ],
)
def test_real_golds_match_survey(raw_ready, cbeta_id, short_id, expect_nodes, expect_max_level):
    counts, levels = _survey_counts()
    assert counts[cbeta_id] == expect_nodes
    assert max(levels[cbeta_id]) == expect_max_level

    xml_path = cbeta_mulu._default_xml(XML_P5, cbeta_id)
    doc, built = cbeta_mulu.build_gold(xml_path, cbeta_id, short_id)
    assert built.node_count == expect_nodes
    assert built.max_source_level == expect_max_level
    assert doc["metadata"]["node_count"] == expect_nodes
    rep = common.validate(doc)
    assert rep.errors == []
    assert rep.warnings == []  # --strict-clean, not just error-free
    assert all(n["node_class"] == "sutra-span" for n in doc["nodes"])
    assert all(n["locations"]["root_text"] is not None for n in doc["nodes"])
    assert all(n["locations"]["root_text"]["basis"] == "cbeta-mulu" for n in doc["nodes"])
    assert all(n["locations"]["root_text"]["start"] <= n["locations"]["root_text"]["end"]
               for n in doc["nodes"])
    assert doc["metadata"]["licence"]["id"] == "CC-BY-NC-SA-4.0"
    assert doc["metadata"]["eval_only"] is False
    assert doc["metadata"]["outline_mode"] == "self-outlining"
    assert doc["metadata"]["commentary_id"] is None
    assert doc["metadata"]["root_text_id"] == cbeta_id
    assert doc["metadata"]["source_document"]["kind"] == "root-text"


def test_x0268_level_histogram_matches_r02_f28(raw_ready):
    xml_path = cbeta_mulu._default_xml(XML_P5, "X11n0268")
    doc, built = cbeta_mulu.build_gold(xml_path, "X11n0268", "X0268")
    # R02 F28 (verifier panel, 2026-09-22): the 科判-only level histogram, levels 1..28.
    want = [3, 10, 23, 34, 52, 62, 78, 133, 250, 302, 261, 298, 276, 172, 105, 96, 50, 57, 51, 58,
            52, 42, 43, 37, 37, 18, 9, 2]
    got = [doc["metadata"]["nodes_per_level"][str(lv)] for lv in range(1, 29)]
    assert got == want
    assert built.jump_count == 0  # F28: "no level skipped between consecutive nodes"
    assert built.merged_count == 1  # the one known 二緣覺眾／三菩薩眾 element


def test_every_kepan_mulu_sits_at_offset_0_of_its_line(raw_ready):
    """root_text.basis cbeta-mulu ("the lb preceding a CBETA cb:mulu 科判 node") requires "the lb
    the mulu sits on" and "the lb immediately preceding the mulu" to be the same thing; true only
    if every mulu is the very first token of its line (module docstring) — checked on all three
    files, not assumed."""
    from chinese_workflow.ingest.lines import extract

    for cbeta_id in cbeta_mulu.FILES:
        ex = extract(cbeta_mulu._default_xml(XML_P5, cbeta_id))
        offsets = {m["offset"] for r in ex.lines for m in r["mulu"] if m["type"] == "科判"}
        assert offsets == {0}, cbeta_id


def test_x0268_last_node_ends_at_the_known_last_line(raw_ready):
    """R02 F28: "juan 10 closes at 0704a06" — the file's true last own-canon line, which the very
    last 科判 node (and its rightmost ancestors) must end at (end_basis null, module docstring)."""
    xml_path = cbeta_mulu._default_xml(XML_P5, "X11n0268")
    doc, _ = cbeta_mulu.build_gold(xml_path, "X11n0268", "X0268")
    last = doc["nodes"][-1]
    assert last["heading_src"] == "二經家結流通"
    rt = last["locations"]["root_text"]
    assert rt["end"] == "X11n0268_p0704a06"
    assert rt["end_basis"] is None
    assert any("last cb:mulu" in n for n in last["notes"])


def test_committed_golds_match_rebuild(raw_ready):
    """The committed data/reference-outlines/*/cbeta-mulu-kepan/outline.json files are exactly
    what python -m chinese_workflow.eval.gold.cbeta_mulu currently produces (stale-file guard, in
    the style of test_gold_authored's byte-identical check)."""
    for cbeta_id, (short_id, _rel) in cbeta_mulu.FILES.items():
        committed = REPO / "data" / "reference-outlines" / short_id / "cbeta-mulu-kepan" / "outline.json"
        if not committed.exists():
            pytest.skip("%s not built yet" % common.repo_relative(committed))
        xml_path = cbeta_mulu._default_xml(XML_P5, cbeta_id)
        doc, _ = cbeta_mulu.build_gold(xml_path, cbeta_id, short_id)
        import json

        assert doc == json.loads(committed.read_text(encoding="utf-8")), (
            "%s is stale: rebuild with python -m chinese_workflow.eval.gold.cbeta_mulu" % short_id
        )
