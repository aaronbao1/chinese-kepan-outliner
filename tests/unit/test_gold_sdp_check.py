"""Tests for chinese_workflow.eval.gold.sdp_check (Task 3: automated heading check of the sdp
T1718 gold against T34n1718).

Entirely synthetic: invented Chinese placeholder text and a hand-built gold-node list, in the style
of tests/unit/test_gold_sdp.py's SYN_ROOT_LINES/SYN_COM_LINES (no sdp content and no real T1718
text; plan Global Constraint 1). The line records below carry only the keys sdp_check.py reads
(linehead, text, mulu) rather than a full chinese_workflow.ingest.lines record.

Fix round 2 (controller review): no committed file here or in sdp_check.py may hold a real sdp
heading, at all — not even the invented placeholders below may coincide with one;
tests/unit/test_sdp_eval_only_guard.py checks every tracked file against the live gold (skipping
cleanly when it is absent) so this cannot regress. Nothing here
reads gitignored scratch (absent on a fresh checkout).
"""

from __future__ import annotations

import json

from chinese_workflow.eval.gold import sdp_check as sc

# ------------------------------------------------------------------------------- normalize_heading


def test_strip_leading_ordinal_range():
    assert sc.normalize_heading("1-5 合成起迄段") == "合成起迄段"


def test_strip_leading_ordinal_single():
    assert sc.normalize_heading("2 合成乙段") == "合成乙段"


def test_strip_trailing_full_width_paren_range():
    assert sc.normalize_heading("1 合成知見段（2-10品）") == "合成知見段"


def test_strip_trailing_paren_with_juan_half_tokens():
    assert sc.normalize_heading("2 合成三段斷疑(2品末-10品)") == "合成三段斷疑"


def test_strip_trailing_paren_digit_fen_count():
    # the plan's own "(分N)" example (Task 3), digit form (fix round 2: not matched before this
    # round — the first TRAILING_PAREN_RE branch required the digit right after the paren, not
    # after 分)
    assert sc.normalize_heading("合成讀本(分2)") == "合成讀本"


def test_strip_trailing_paren_cjk_fen_count():
    # "(分N)" also in its CJK-numeral form, "（分二）" (fix round 1)
    assert sc.normalize_heading("合成讀本（分二）") == "合成讀本"


def test_strip_trailing_bare_count_suffix_when_it_matches_expected_counts():
    # fix round 1: only stripped when the value matches an expected count (here: 2 children)
    assert sc.normalize_heading("1 合成甲乙行上問二", expected_counts={2}) == "合成甲乙行上問"


def test_no_strip_trailing_numeral_that_is_not_a_known_count():
    # fix round 1: a trailing numeral that is the heading's own substance (not sdp's count tag) is
    # kept when it does not match any expected count — the default expected_counts=() never strips
    assert sc.normalize_heading("合成三顯一") == "合成三顯一"
    assert sc.normalize_heading("合成三顯一", expected_counts={2}) == "合成三顯一"


def test_strip_trailing_numeral_only_when_count_matches_exactly():
    # the same trailing numeral, with a matching vs a non-matching expected count
    assert sc.normalize_heading("合成起問二", expected_counts={2}) == "合成起問"
    assert sc.normalize_heading("合成起問二", expected_counts={3}) == "合成起問二"


def test_no_trailing_strip_when_heading_does_not_end_in_a_count():
    assert sc.normalize_heading("1 合成甲乙丙上長文", expected_counts={1, 2}) == "合成甲乙丙上長文"


def test_defensive_bracket_strip():
    assert sc.normalize_heading("【合成標題】") == "合成標題"


def test_normalize_heading_never_returns_empty_from_a_real_heading():
    # an ordinal-only or punctuation-only heading is not stripped down to nothing
    assert sc.normalize_heading("1") == "1"


# ------------------------------------------------------------------------------------ classify_text


def test_classify_verbatim():
    assert sc.classify_text("合成通序", "此段合成通序甲乙。") == ("verbatim", None)


def test_classify_partial_at_exactly_60_percent():
    # needle 甲乙丙丁戊 (5 chars); hay carries 甲,乙,丙 in order = 3/5 = 0.60
    cls, ratio = sc.classify_text("甲乙丙丁戊", "前甲後乙中丙尾")
    assert cls == "partial"
    assert ratio == 0.6


def test_classify_absent_below_60_percent():
    # only 2/5 = 0.40
    cls, ratio = sc.classify_text("甲乙丙丁戊", "前甲後乙尾")
    assert cls == "absent"
    assert ratio == 0.4


def test_classify_empty_needle_is_absent():
    assert sc.classify_text("", "某些文字") == ("absent", None)


def test_classify_ignores_punctuation_both_sides():
    assert sc.classify_text("甲乙", "甲、乙。") == ("verbatim", None)


def test_classify_two_character_heading_is_trivially_easy_to_pass():
    # module docstring: a 2-character heading needs only 2/2 in order, anywhere in the window
    cls, ratio = sc.classify_text("甲乙", "前雜文甲後雜文乙尾")
    assert cls == "partial"
    assert ratio == 1.0


# ------------------------------------------------------------------------------------ depth_band


def test_depth_band_boundaries():
    assert sc.depth_band(1) == "1-3"
    assert sc.depth_band(3) == "1-3"
    assert sc.depth_band(4) == "4-6"
    assert sc.depth_band(6) == "4-6"
    assert sc.depth_band(7) == "7-9"
    assert sc.depth_band(9) == "7-9"
    assert sc.depth_band(10) == "10-12"
    assert sc.depth_band(12) == "10-12"
    assert sc.depth_band(13) == "13+"
    assert sc.depth_band(19) == "13+"


# --------------------------------------------------------------------------- juan-half / label_at


def test_label_at_uses_most_recent_boundary():
    bounds = [(0, "1a"), (6, "1b")]
    assert sc.label_at(0, bounds) == "1a"
    assert sc.label_at(5, bounds) == "1a"
    assert sc.label_at(6, bounds) == "1b"
    assert sc.label_at(12, bounds) == "1b"


def test_label_at_before_first_boundary_is_none():
    assert sc.label_at(0, [(2, "1a")]) is None


def test_juan_half_boundaries_reads_mulu_type_juan_only():
    records = [
        {"linehead": "X_p1", "text": "", "mulu": [{"type": "卷", "n": "1a", "text": "第一上"}]},
        {"linehead": "X_p2", "text": "", "mulu": [{"type": "品", "n": "1", "text": "序品"}]},
        {"linehead": "X_p3", "text": "", "mulu": [{"type": "卷", "n": "1b", "text": "第一下"}]},
    ]
    assert sc.juan_half_boundaries(records) == [(0, "1a"), (2, "1b")]


# ------------------------------------------------------------------------------------- split_of


def _fake_split_positions():
    # the real T1718 split lineheads (plan Global Constraint 5), mapped to arbitrary synthetic
    # positions purely to exercise split_of's inclusive-start/exclusive-end arithmetic — these are
    # line-reference ids, not sdp content.
    return {
        "T34n1718_p0001b18": 0,
        "T34n1718_p0016b02": 10,
        "T34n1718_p0036a26": 20,
        "T34n1718_p0063b11": 30,
    }


def test_split_of_dev():
    lp = _fake_split_positions()
    assert sc.split_of(0, lp) == "dev"
    assert sc.split_of(9, lp) == "dev"


def test_split_of_boundary_is_exclusive_end_inclusive_start():
    lp = _fake_split_positions()
    assert sc.split_of(10, lp) == "validation"
    assert sc.split_of(19, lp) == "validation"
    assert sc.split_of(20, lp) == "test"
    assert sc.split_of(29, lp) == "test"


def test_split_of_outside_every_split_is_none():
    lp = _fake_split_positions()
    assert sc.split_of(30, lp) is None


# --------------------------------------------------------------------------------- merge_ranges


def test_merge_ranges_joins_overlapping():
    assert sc.merge_ranges([(0, 5), (3, 8)]) == [(0, 8)]


def test_merge_ranges_joins_textually_adjacent():
    # end + 1 == next start: genuinely contiguous in the file, joins into one range
    assert sc.merge_ranges([(0, 2), (3, 5)]) == [(0, 5)]


def test_merge_ranges_keeps_disjoint_ranges_separate():
    assert sc.merge_ranges([(0, 2), (10, 12)]) == [(0, 2), (10, 12)]


def test_merge_ranges_sorts_before_merging():
    assert sc.merge_ranges([(10, 12), (0, 2)]) == [(0, 2), (10, 12)]


# ------------------------------------------------------------------------------------ window_text


def test_window_text_joins_adjacent_ranges_without_a_separator():
    win = sc.Window("x", "own", [(0, 0), (1, 1)])
    line_order = ["a", "b"]
    line_texts = {"a": "甲", "b": "乙"}
    assert sc.window_text(win, line_order, line_texts) == "甲乙"


def test_window_text_joins_disjoint_ranges_with_range_separator():
    win = sc.Window("x", "own", [(0, 0), (2, 2)])
    line_order = ["a", "b", "c"]
    line_texts = {"a": "甲", "b": "乙", "c": "丙"}
    assert sc.window_text(win, line_order, line_texts) == "甲" + sc.RANGE_SEPARATOR + "丙"


def test_range_separator_prevents_a_spurious_verbatim_match_across_ranges():
    # "甲丙" is not really contiguous text anywhere — it only looks that way if the two ranges are
    # concatenated with no separator (own span ends in 甲, the disjoint announcing range starts
    # with 丙). With the separator, "甲丙" must not verbatim-match; each half alone still can.
    win = sc.Window("x", "own", [(0, 0), (2, 2)])
    line_order = ["a", "b", "c"]
    line_texts = {"a": "尾段甲", "b": "無關中段", "c": "丙起首段"}
    hay = sc.window_text(win, line_order, line_texts)
    assert sc.classify_text("甲丙", hay)[0] != "verbatim"
    assert sc.classify_text("甲", hay)[0] == "verbatim"
    assert sc.classify_text("丙", hay)[0] == "verbatim"


# ---------------------------------------------------------------------------------- compute_windows
#
# A small synthetic tree (invented headings/text, not sdp's or Zhiyi's; none of these strings occur
# in the real T1718 gold or in F23's findings.md table). Every heading's non-序 characters are
# unique to it and never reused in another heading or in the filler text, so no pair can spuriously
# LCS-match above the 60% partial threshold by sharing an unrelated run of characters (each heading
# shares only its single trailing "序" with the others, worth at most 1 character of any LCS).
#
#   A "起始序"              explained a02
#     B "承接序"            explained a03
#       C "孤僻序"          explained a05           (no match anywhere near it: ABSENT)
#         H "填空三"        (no explained: inherits C's window; its own heading DOES occur there,
#                            verbatim, from C's own span text — not the widened parent bonus)
#   D "轉折序"              explained b01, shares its anchor with its first child E
#     E "附屬序"            explained b01 (SAME anchor as D: the common sdp layout fix round 1
#                                          widens the window for)
#     F "隨後序"            explained b05 (own span has no match; parent D's announcing lines do,
#                                          only reachable once D's own narrow span is widened)
#     G "殿末序"            explained b07 = last line (ditto; also the open-ended last window)
#   R1 (top-level, no explained, no ancestor: NO-TEXT)


def _synthetic_lines():
    texts = [
        ("T99n9999_p0001a01", "", [{"type": "卷", "n": "1a", "text": "第一上"}]),
        ("T99n9999_p0001a02", "起始序文於此。", []),
        ("T99n9999_p0001a03", "承接序文於此。", []),
        ("T99n9999_p0001a04", "填空一填空二。", []),
        ("T99n9999_p0001a05", "填空三填空四。", []),
        ("T99n9999_p0001a06", "填空五填空六。", []),
        (
            "T99n9999_p0001b01",
            "轉折序起。分三：一附屬序，二隨後序，三殿末序。",
            [{"type": "卷", "n": "1b", "text": "第一下"}],
        ),
        ("T99n9999_p0001b02", "填空七填空八。", []),
        ("T99n9999_p0001b03", "填空九填空十。", []),
        ("T99n9999_p0001b04", "填空十一十二。", []),
        ("T99n9999_p0001b05", "填空十三十四。", []),
        ("T99n9999_p0001b06", "填空十五十六。", []),
        ("T99n9999_p0001b07", "填空十七十八。", []),
    ]
    return [{"linehead": lh, "text": t, "mulu": m} for lh, t, m in texts]


def _node(
    nid, parent_id, level, heading, explained, source_node_id=None, child_count_announced=None
):
    return {
        "id": nid,
        "parent_id": parent_id,
        "level": level,
        "heading_src": heading,
        "source_node_id": source_node_id or nid,
        "child_count_announced": child_count_announced,
        "locations": {"commentary": {"explained": explained}},
    }


def _synthetic_nodes():
    return [
        _node("A", None, 1, "起始序", "T99n9999_p0001a02"),
        _node("B", "A", 2, "承接序", "T99n9999_p0001a03"),
        _node("C", "B", 3, "孤僻序", "T99n9999_p0001a05"),
        _node("H", "C", 4, "填空三", None),
        _node("D", "A", 2, "轉折序", "T99n9999_p0001b01"),
        _node("E", "D", 3, "附屬序", "T99n9999_p0001b01"),  # shares D's own anchor
        _node("F", "D", 3, "隨後序", "T99n9999_p0001b05"),
        _node("G", "D", 3, "殿末序", "T99n9999_p0001b07"),
        _node("R1", None, 1, "無所屬頂層節點", None),
    ]


def _line_pos(records):
    return {r["linehead"]: i for i, r in enumerate(records)}


def test_shared_anchor_widens_own_window_to_minimum():
    # D and its first child E share one explained line (T99n9999_p0001b01) — the common sdp layout
    # fix round 1 targets. D's own window must still reach MIN_OWN_LINES lines, not collapse to 1.
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    lp = _line_pos(records)
    windows = sc.compute_windows(nodes, lp, len(records) - 1)
    start, end = windows["D"].ranges[0]
    assert end - start + 1 >= sc.MIN_OWN_LINES
    assert start == lp["T99n9999_p0001b01"]


def test_cap_uses_subtree_bound_not_narrow_own_span():
    """D is A's SECOND child; A's own span is narrow (ends right where its first child B begins).
    Capping D by A's narrow span (a bug an earlier version of this module had) would truncate D's
    span to nothing before it starts. The correct cap is A's *subtree* bound."""
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    lp = _line_pos(records)
    last_pos = len(records) - 1
    windows = sc.compute_windows(nodes, lp, last_pos)
    d_start, d_end = windows["D"].ranges[0]
    assert d_start == lp["T99n9999_p0001b01"]
    assert d_end >= lp["T99n9999_p0001b03"]  # at least MIN_OWN_LINES, not before D even starts


def test_no_text_class_for_top_level_node_without_explained():
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    lp = _line_pos(records)
    windows = sc.compute_windows(nodes, lp, len(records) - 1)
    assert windows["R1"].kind == "no-text"
    assert windows["R1"].owner is None
    assert windows["R1"].ranges == []


def test_null_node_inherits_ancestor_full_window():
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    lp = _line_pos(records)
    windows = sc.compute_windows(nodes, lp, len(records) - 1)
    assert windows["H"].kind == "inherited"
    assert windows["H"].owner == "C"
    assert windows["H"].ranges == windows["C"].ranges


def test_announcing_lines_bonus_uncapped_by_parents_own_narrow_span():
    # fix round 1: D's own span (via E sharing its anchor) is narrow; F's parent-announcing bonus
    # must still reach D's subtree bound, not D's own narrow own_end.
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    lp = _line_pos(records)
    windows = sc.compute_windows(nodes, lp, len(records) - 1)
    own, bonus = windows["F"].ranges
    assert own == (lp["T99n9999_p0001b05"], lp["T99n9999_p0001b06"])
    assert bonus[0] == lp["T99n9999_p0001b01"]
    assert bonus[1] >= lp["T99n9999_p0001b02"]  # at least ANNOUNCING_LINES, not just 1 line


def test_last_explained_node_window_runs_to_end_of_file():
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    lp = _line_pos(records)
    last_pos = len(records) - 1
    windows = sc.compute_windows(nodes, lp, last_pos)
    own_range = windows["G"].ranges[0]
    assert own_range[1] == last_pos


# ------------------------------------------------------------------------------------- check_nodes


def test_check_nodes_end_to_end_classes():
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    results = {r.node_id: r for r in sc.check_nodes(nodes, records)}

    assert results["A"].cls == "verbatim"
    assert results["B"].cls == "verbatim"
    assert results["C"].cls == "absent"
    assert results["H"].cls == "verbatim"  # inherited window, own heading found there
    assert results["D"].cls == "verbatim"
    assert results["F"].cls == "verbatim"  # only via the parent's widened announcing-lines bonus
    assert results["G"].cls == "verbatim"  # ditto
    assert results["R1"].cls == "no-text"


def test_check_nodes_juan_half_and_depth_band():
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    results = {r.node_id: r for r in sc.check_nodes(nodes, records)}
    assert results["A"].juan_half == "1a"
    assert results["D"].juan_half == "1b"
    assert results["R1"].juan_half is None  # no-text: no window, no juan-half
    assert results["C"].depth_band == "1-3"
    assert results["H"].depth_band == "4-6"


def test_inherited_node_has_no_own_juan_half_or_split():
    # fix round 1, controller decision: an inherited node's own location is unknown and must not be
    # attributed to its owner's 卷-half/split.
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    results = {r.node_id: r for r in sc.check_nodes(nodes, records)}
    assert results["H"].window_kind == "inherited"
    assert results["H"].juan_half is None
    assert results["H"].split is None


def test_child_count_used_to_strip_a_real_trailing_count_suffix():
    # D announces exactly 2 children (E, F, G are 3 actual children, but child_count_announced
    # overrides when set) — give D a heading whose trailing numeral matches child_count_announced.
    nodes = _synthetic_nodes()
    for n in nodes:
        if n["id"] == "D":
            n["heading_src"] = "合序丁起二"
            n["child_count_announced"] = 2
    records = _synthetic_lines()
    results = {r.node_id: r for r in sc.check_nodes(nodes, records)}
    assert results["D"].heading_norm == "合序丁起"


def test_actual_child_count_used_when_no_child_count_announced():
    # E, F, G are D's three actual children; a trailing "三" on D's heading should strip.
    nodes = _synthetic_nodes()
    for n in nodes:
        if n["id"] == "D":
            n["heading_src"] = "合序丁起三"
    records = _synthetic_lines()
    results = {r.node_id: r for r in sc.check_nodes(nodes, records)}
    assert results["D"].heading_norm == "合序丁起"


def test_to_tsv_rows_header_and_row_count():
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    results = sc.check_nodes(nodes, records)
    rows = sc.to_tsv_rows(results)
    assert rows[0] == sc.TSV_HEADER
    assert len(rows) == len(results) + 1


# --------------------------------------------------------------------------------- noise_baseline


def test_noise_baseline_is_reproducible_and_only_counts_own_windows():
    nodes = _synthetic_nodes()
    records = _synthetic_lines()
    a = sc.noise_baseline(nodes, records, seed=1, trials=2)
    b = sc.noise_baseline(nodes, records, seed=1, trials=2)
    assert a == b  # seeded: reproducible
    own_count = sum(1 for r in sc.check_nodes(nodes, records) if r.window_kind == "own")
    assert sum(a.values()) == own_count * 2  # trials=2, one draw per "own"-window node per trial


# --------------------------------------------------------------------------------- F23 calibration


def test_f23_node_class_group_numbers_are_a_subset_of_f23_groups():
    group_numbers = {g for g, _bucket, _checkable in sc.F23_GROUPS}
    used = {group for _hand, group in sc.F23_NODE_CLASS.values()}
    assert used <= group_numbers


def test_f23_node_class_holds_no_heading_text():
    # controller decision, fix round 1: only ids, classes and group numbers — no Chinese heading
    # text anywhere in the committed calibration tables.
    for value in list(sc.F23_NODE_CLASS.keys()) + [str(v) for v in sc.F23_NODE_CLASS.values()]:
        assert not any("一" <= ch <= "鿿" for ch in value), value
    for row in sc.F23_GROUPS:
        assert not any(isinstance(x, str) and any("一" <= ch <= "鿿" for ch in x) for x in row)


def _result(source_node_id, cls):
    return sc.NodeResult(
        node_id=source_node_id,
        source_node_id=source_node_id,
        level=2,
        depth_band="1-3",
        heading_src="x",
        heading_norm="x",
        window_kind="own",
        window_owner=source_node_id,
        window_lineheads="",
        juan_half="1a",
        split="dev",
        cls=cls,
        ratio=None,
    )


def test_confusion_table_counts_a_known_agreement():
    # some id in F23_NODE_CLASS with hand class "verbatim" (R03 F23);
    # giving it our own "verbatim" class should land in the verbatim/verbatim cell.
    sid = next(s for s, (hand, _g) in sc.F23_NODE_CLASS.items() if hand == "verbatim")
    table, missing = sc.confusion_table([_result(sid, "verbatim")])
    assert "| verbatim | 1 | 0 | 0 | 0 | 1 |" in table
    # every other F23-named id is absent from this tiny results list, hence reported missing, not
    # silently counted as 0 agreement
    assert len(missing) == len(sc.F23_NODE_CLASS) - 1
    assert sid not in missing


def test_confusion_table_disagreement_lands_off_diagonal():
    # some id in F23_NODE_CLASS with hand class "editorial"; giving it "verbatim" is a disagreement.
    sid = next(s for s, (hand, _g) in sc.F23_NODE_CLASS.items() if hand == "editorial")
    table, _ = sc.confusion_table([_result(sid, "verbatim")])
    assert "| editorial | 1 | 0 | 0 | 0 | 1 |" in table


def test_confusion_table_reports_unknown_id_as_missing_not_found():
    # a source_node_id this module has never heard of (not in F23_NODE_CLASS) simply never
    # contributes to the table; it is not an error, just outside the calibration sample.
    table, missing = sc.confusion_table([_result("T1718D99_999", "verbatim")])
    assert "T1718D99_999" not in table
    assert "T1718D99_999" not in missing
    assert len(missing) == len(sc.F23_NODE_CLASS)


def test_group_tally_matches_confusion_table_population():
    # every F23_NODE_CLASS entry's group number is one of the checkable groups (or one of the
    # excluded ones only if it has no node — none do, since excluded groups have no entries at all)
    checkable = {g for g, _bucket, checkable in sc.F23_GROUPS if checkable}
    used = {group for _hand, group in sc.F23_NODE_CLASS.values()}
    assert used <= checkable


# --------------------------------------------------------------------------------------- main() CLI


def test_main_end_to_end_on_synthetic_gold(tmp_path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:cb="http://www.cbeta.org/ns/1.0" xml:id="T99n9999">
<teiHeader><fileDesc><titleStmt><title level="m">Synthetic</title></titleStmt>
<publicationStmt><date>2026</date></publicationStmt>
<sourceDesc><bibl>synthetic</bibl></sourceDesc></fileDesc></teiHeader>
<text><body><div type="pin">
<lb n="0001a01" ed="T"/>合序甲起首語。
<lb n="0001a02" ed="T"/>合序乙起首語。
</div></body></text>
</TEI>
"""
    (tmp_path / "synthetic.xml").write_text(xml, encoding="utf-8")

    gold = {
        "metadata": {"commentary_id": "T99n9999"},
        "nodes": [
            {
                "id": "1_1",
                "order": 1,
                "level": 1,
                "parent_id": None,
                "heading_src": "合成頂層",
                "source_node_id": "SYN1",
                "child_count_announced": None,
                "locations": {"commentary": {"explained": "T99n9999_p0001a01"}},
            },
            {
                "id": "1_1.1_2",
                "order": 2,
                "level": 2,
                "parent_id": "1_1",
                "heading_src": "合序乙起",
                "source_node_id": "SYN2",
                "child_count_announced": None,
                "locations": {"commentary": {"explained": "T99n9999_p0001a02"}},
            },
        ],
    }
    (tmp_path / "gold.json").write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")

    out_dir = tmp_path / "out"
    rc = sc.main(
        [
            "--gold",
            str(tmp_path / "gold.json"),
            "--cbeta",
            str(tmp_path / "synthetic.xml"),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    tsv_path = out_dir / "heading-check.tsv"
    md_path = out_dir / "HEADING-CHECK.md"
    assert tsv_path.exists()
    assert md_path.exists()
    tsv_text = tsv_path.read_text(encoding="utf-8")
    assert "SYN1" in tsv_text
    assert "SYN2" in tsv_text
    assert "verbatim" in tsv_text  # SYN2's "合序乙起" occurs verbatim on line a02
    md_text = md_path.read_text(encoding="utf-8")
    assert "## Overall" in md_text
    assert "## Fix round 1: before / after and noise baseline" in md_text
