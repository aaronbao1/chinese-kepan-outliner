"""Tests for chinese_workflow.eval.gold.ybh — Task 8 of the eval-dataset build (DILA YBh golds,
T1605 / T1602, structure only).

Always run: the Chinese-numeral / label-depth helpers; parse_kp + build_gold on the committed
fixture tests/fixtures/dila-ybh/T1605-kp.head60.txt (a genuine, truncated excerpt of DILA's own
file, not synthetic — README there); merged_range / irregular_label flagging on small SYNTHETIC
-kp.txt-shaped strings (invented labels/headings, no real text), since neither flag occurs in the
two in-scope files themselves (module docstring).
Run only when data/raw/dila-ybh/T1605-kp.txt and T1602-kp.txt are present (skip otherwise; fetch
with scripts/fetch_dila_ybh.sh): the full counts against R04 F9 (T1605 2,605 nodes / depth 24,
T1602 2,594 / depth 20), the count_mismatch / merged_range tallies, and that the committed
data/reference-outlines/<code>/ybh-dila/outline.json is not stale.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chinese_workflow.eval.gold import common, ybh

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "dila-ybh" / "T1605-kp.head60.txt"
RAW_DIR = REPO / "data" / "raw" / "dila-ybh"
GOLD_DIR = REPO / "data" / "reference-outlines"

# The 7 count_mismatch lines expected on the committed T1605-kp.txt (verified by hand against the
# raw file, module docstring): (line, label, heading, announced, actual children).
T1605_MISMATCHES = [
    (658, "J2", "答", 3, 2),
    (739, "J2", "答", 3, 2),
    (1080, "L2", "別釋空有", 3, 2),
    (1349, "K7", "邪行", 3, 2),
    (1576, "P2", "明戒業", 3, 2),
    (2088, "H2", "明三藏相攝及建立義", 3, 2),
    (2381, "H3", "明現觀所攝功德", 2, 3),
]


# ------------------------------------------------------------------------------------- helpers


def test_cn_to_int():
    cases = {
        "一": 1, "二": 2, "九": 9, "十": 10, "十一": 11, "十四": 14, "十五": 15, "十九": 19,
        "二十": 20, "二十一": 21, "二十三": 23, "二十四": 24,
    }
    for text, want in cases.items():
        assert ybh._cn_to_int(text) == want
    with pytest.raises(ValueError):
        ybh._cn_to_int("卅")
    # 零 (zero) is not in _CN_DIGITS and must error, not return 0: child_count_announced has
    # schema minimum 1 (fix round 1, controller)
    assert "零" not in ybh._CN_DIGITS
    with pytest.raises(ValueError):
        ybh._cn_to_int("零")


def test_label_level():
    assert ybh._label_level("A") == 1
    assert ybh._label_level("Z") == 26
    assert ybh._label_level("a") == 27
    assert ybh._label_level("g") == 33
    assert ybh._label_level("Aa") is None  # multi-letter: not a recognised single depth letter


def test_code_from_filename():
    assert ybh._code_from_filename(Path("data/raw/dila-ybh/T1605-kp.txt")) == "T1605"
    assert ybh._code_from_filename(Path("T1605-kp.head60.txt")) == "T1605"
    with pytest.raises(ValueError):
        ybh._code_from_filename(Path("not-a-kp-file.txt"))


# ----------------------------------------------------------------------- synthetic flag coverage


def test_merged_range_flag():
    # SYNTHETIC: invented labels/heading, not real DILA content
    recs = ybh.parse_kp("A1 標\n  B1-3 合說三事（分二）\n    C1 初\n", "syn-kp.txt")
    assert [r.label for r in recs] == ["A1", "B1-3", "C1"]
    assert recs[1].merged is True and "merged_range" in recs[1].flags
    assert recs[0].merged is False


def test_irregular_label_flag_on_disagreement():
    # SYNTHETIC: the label says depth 2 (B) but the indentation (4 spaces) says depth 3
    recs = ybh.parse_kp("A1 標\n    B1 誤植\n", "syn-kp.txt")
    assert recs[1].level == 2  # the label wins
    assert "irregular_label" in recs[1].flags
    assert "depth 2" in recs[1].notes[0] and "depth 3" in recs[1].notes[0]


def test_irregular_label_flag_on_multi_letter():
    # SYNTHETIC: a label this scheme's single-letter A-Z/a-z depth grammar does not cover
    recs = ybh.parse_kp("A1 標\n  Aa1 誤植\n", "syn-kp.txt")
    assert recs[1].level == 2  # falls back to indentation
    assert "irregular_label" in recs[1].flags


def test_parse_kp_rejects_unrecognised_lines():
    with pytest.raises(ValueError, match="syn-kp.txt:2"):
        ybh.parse_kp("A1 標\nnot a kp line\n", "syn-kp.txt")


# -------------------------------------------------------------------------- fixture (always run)


def test_parse_kp_on_fixture():
    text = FIXTURE.read_text(encoding="utf-8")
    recs = ybh.parse_kp(text, FIXTURE.name)
    assert len(recs) == 60
    assert recs[0].label == "A1"
    assert recs[0].heading == "以一頌總標「分」、「品」"
    assert recs[0].count is None
    assert recs[1].label == "A2"
    assert recs[1].heading == "次第別釋「分」、「品」"
    assert recs[1].count == 2
    assert recs[-1].label == "H1"
    assert recs[-1].heading == "辨根"
    assert recs[-1].count == 2
    assert recs[-1].level == 8
    assert all(not r.flags for r in recs)  # no irregular_label / merged_range anywhere in T1605


def test_build_gold_on_fixture():
    doc = ybh.build_gold("T1605", FIXTURE)
    rep = common.validate(doc)
    assert rep.errors == [] and rep.warnings == [], [f.render() for f in rep.findings]
    meta = doc["metadata"]
    assert meta["node_count"] == 60
    assert meta["max_depth"] == 13
    assert meta["outline_profile"] == "zh-kepan"
    assert meta["outline_mode"] == "sutra"
    assert meta["commentary_id"] is None
    assert meta["root_text_id"] == "T31n1605"
    assert meta["scheme_id"] == "ybh-dila"
    assert meta["gold_status"] == "imported-unchecked"
    assert meta["seeded_by"] is None
    assert meta["licence"]["id"] == "CC-BY-SA-4.0"
    assert meta["eval_only"] is False
    assert meta["cbeta_release"] == "2026R2"

    nodes = doc["nodes"]
    top = [n for n in nodes if n["level"] == 1]
    assert [n["display_label"] for n in top] == ["A1", "A2"]
    for n in nodes:
        assert n["origin"] == "imported"
        assert n["node_class"] == "sutra-span"
        assert n["locations"] == {"scheme": "none"}
        assert "unmapped" in n["flags"]
        assert n["source_node_id"].startswith(FIXTURE.name + ":L")

    by_label_heading = {(n["display_label"], n["heading_src"]): n for n in nodes}
    # every node whose child_count_announced disagrees with its actual children (the fixture cuts
    # some subtrees short) is flagged count_mismatch, with a note
    mismatched = [n for n in nodes if "count_mismatch" in n["flags"]]
    assert len(mismatched) == 7
    expect = {
        ("A2", "次第別釋「分」、「品」"): (2, 1),
        ("B1", "本事分"): (4, 1),
        ("C1", "三法品"): (4, 1),
        ("E2", "長行依九門別釋"): (9, 4),
        ("F4", "釋頌「何相」字問答體相門"): (3, 2),
        ("G2", "辨界相"): (3, 1),
        ("H1", "辨根"): (2, 0),
    }
    for key, (announced, actual) in expect.items():
        n = by_label_heading[key]
        assert n["child_count_announced"] == announced
        assert "count_mismatch" in n["flags"]
        assert ("announces %d child" % announced) in n["notes"][-1]
        assert ("has %d in this outline" % actual) in n["notes"][-1]


# ------------------------------------------------------------------ real data (skip if absent)


def _missing_raw():
    return [p for p in (RAW_DIR / "T1605-kp.txt", RAW_DIR / "T1602-kp.txt") if not p.exists()]


@pytest.fixture(scope="module")
def golds():
    missing = _missing_raw()
    if missing:
        pytest.skip(
            "raw YBh files absent (%s); run scripts/fetch_dila_ybh.sh"
            % ", ".join(common.repo_relative(p) for p in missing)
        )
    return {
        "T1605": ybh.build_gold("T1605", RAW_DIR / "T1605-kp.txt"),
        "T1602": ybh.build_gold("T1602", RAW_DIR / "T1602-kp.txt"),
    }


def test_full_counts_match_r04(golds):
    # R04 F9 / plan Task 8: T1605 2,605 nodes / depth 24; T1602 2,594 / depth 20
    m1605, m1602 = golds["T1605"]["metadata"], golds["T1602"]["metadata"]
    assert (m1605["node_count"], m1605["max_depth"]) == (2605, 24)
    assert (m1602["node_count"], m1602["max_depth"]) == (2594, 20)
    # controller decision, fix round 1: outline_mode "sutra", commentary_id null (case (b))
    assert m1605["outline_mode"] == m1602["outline_mode"] == "sutra"
    assert m1605["commentary_id"] is None and m1602["commentary_id"] is None

    def flagged(doc, flag):
        return sum(1 for n in doc["nodes"] if flag in n["flags"])

    assert flagged(golds["T1605"], "count_mismatch") == 7
    assert flagged(golds["T1602"], "count_mismatch") == 0
    assert flagged(golds["T1605"], "merged_range") == 0
    assert flagged(golds["T1602"], "merged_range") == 14
    assert flagged(golds["T1605"], "irregular_label") == 0
    assert flagged(golds["T1602"], "irregular_label") == 0
    assert all("unmapped" in n["flags"] for doc in golds.values() for n in doc["nodes"])
    assert all(n["locations"] == {"scheme": "none"} for doc in golds.values() for n in doc["nodes"])


def test_full_golds_validate_cleanly(golds):
    for code, doc in golds.items():
        rep = common.validate(doc)
        assert rep.errors == [], (code, [f.render() for f in rep.errors])
        assert rep.warnings == [], (code, [f.render() for f in rep.warnings])


def test_committed_gold_matches_disk(golds):
    for code, doc in golds.items():
        committed = GOLD_DIR / code / "ybh-dila" / "outline.json"
        assert committed.exists(), "run: python -m chinese_workflow.eval.gold.ybh"
        rebuilt = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
        assert rebuilt == committed.read_text(encoding="utf-8"), (
            "%s is stale: recompile with python -m chinese_workflow.eval.gold.ybh" % committed
        )


def test_cli_out_dir_is_the_reference_outlines_root(tmp_path):
    """--out-dir names the root, like cbeta_mulu's: two inputs in one call land in
    <out-dir>/<CODE>/ybh-dila/outline.json each, neither overwriting the other (final review M1)."""
    kp1605 = tmp_path / "in" / "T1605-kp.txt"
    kp1602 = tmp_path / "in" / "T1602-kp.txt"
    kp1605.parent.mkdir()
    kp1605.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    kp1602.write_text("A1 合成甲\nA2 合成乙\n  B1 合成丙\n", encoding="utf-8")  # SYNTHETIC
    out = tmp_path / "out"
    ybh.main([str(kp1605), str(kp1602), "--out-dir", str(out)])
    got = {
        code: json.loads((out / code / "ybh-dila" / "outline.json").read_text(encoding="utf-8"))
        for code in ("T1605", "T1602")
    }
    assert {c: d["metadata"]["text_id"] for c, d in got.items()} == {
        "T1605": "T1605",
        "T1602": "T1602",
    }
    assert len(got["T1602"]["nodes"]) == 3
    assert not (out / "outline.json").exists()


def test_cli_main_end_to_end(tmp_path):
    # both codes through the CLI in one call, into one --out-dir root (one folder per code)
    if _missing_raw():
        pytest.skip("raw YBh files absent; run scripts/fetch_dila_ybh.sh")
    rc = ybh.main(
        [str(RAW_DIR / "T1605-kp.txt"), str(RAW_DIR / "T1602-kp.txt"), "--out-dir", str(tmp_path)]
    )
    assert rc == 0
    outputs = {code: tmp_path / code / "ybh-dila" / "outline.json" for code in ("T1605", "T1602")}
    assert outputs["T1605"].exists() and outputs["T1602"].exists()
    doc1605 = json.loads(outputs["T1605"].read_text(encoding="utf-8"))
    doc1602 = json.loads(outputs["T1602"].read_text(encoding="utf-8"))
    assert doc1605["metadata"]["text_id"] == "T1605"
    assert doc1602["metadata"]["text_id"] == "T1602"


def test_cli_skips_out_of_scope_code(tmp_path, capsys):
    unknown = tmp_path / "T9999-kp.txt"  # SYNTHETIC: fictional code, not a real Taishō number
    unknown.write_text("A1 測試標題\n", encoding="utf-8")
    rc = ybh.main([str(unknown)])
    assert rc == 1
    assert "out of scope" in capsys.readouterr().err
