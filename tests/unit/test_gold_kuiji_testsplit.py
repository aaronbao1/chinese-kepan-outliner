"""TEST-SPLIT ANSWER KEY — do not open while developing a parser/outliner evaluated on E01–E04 (see
data/EVAL-SETS.md, "Do not open while developing").

The assertions about the Kuiji gold's two test-split subtrees, the 序品 (outline levels 3-5, commentary
T34n1723_p0651a06 up to p0694b22) and the 譬喻品 opening (T34n1723_p0734b07 up to p0737b04), moved out of
tests/unit/test_gold_authored.py (final review, 2026-09-22) so that a developer can run and read the
compiler's tests without reading the answer keys. They check lineheads, classes and counts, and the one
heading the compiler warns about.

Run when data/raw/cbeta/T34n1723.xml and T09n0262.xml are present (skip otherwise).
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

from chinese_workflow.eval.gold import authored, common

REPO = Path(__file__).resolve().parents[2]
GOLD_TXT = REPO / "data" / "reference-outlines" / "T0262" / "kuiji-xuanzan" / "outline.txt"
RAW_CBETA = REPO / "data" / "raw" / "cbeta"


@pytest.fixture(scope="module")
def compiled():
    need = [RAW_CBETA / "T34n1723.xml", RAW_CBETA / "T09n0262.xml"]
    missing = [p for p in need if not p.exists()]
    if missing:
        pytest.skip(
            "raw CBETA files absent (%s); run scripts/fetch_cbeta.sh"
            % ", ".join(common.repo_relative(p) for p in missing)
        )
    return authored.compile_file(GOLD_TXT)


def _line_of(txt: str, needle: str) -> int:
    return next(i for i, line in enumerate(txt.splitlines(), 1) if needle in line)


def _subtree(nodes: list, explained: str) -> list:
    pin = next(
        n
        for n in nodes
        if n["level"] == 2 and n["locations"]["commentary"]["explained"] == explained
    )
    return [n for n in nodes if n["id"].startswith(pin["id"] + ".")]


def test_compiler_warnings_name_the_test_subtrees(compiled):
    _doc, warnings, _report = compiled
    # announced counts cut short, by the end of a covered span (譬喻品 opening, 5) or by the depth
    # limit (序品 levels 3–5, 14), each naming a node that carries flags truncated and count_mismatch;
    # and one 序品 heading read across CBETA's punctuation
    counts = [w for w in warnings if "children: flag count_mismatch added" in w]
    assert len(counts) == 5 + 14
    (heading,) = [w for w in warnings if w not in counts]
    # the heading joins 發問先因 to the label across CBETA's 。 (review 2026-09-22)
    lineno = _line_of(GOLD_TXT.read_text(encoding="utf-8"), "後慈氏雙申兩意發問先因 @")
    assert heading.startswith(
        "%s:%d: 後慈氏雙申兩意發問先因: " % (common.repo_relative(GOLD_TXT), lineno)
    )
    assert "heading matches only with punctuation ignored" in heading


def test_truncated_nodes_in_the_test_subtrees(compiled):
    nodes = compiled[0]["nodes"]
    truncated = [n for n in nodes if "truncated" in n["flags"]]
    assert len(truncated) == 46  # 25 bare 品 (test_gold_authored.py) + 15 in 序品 + 6 in 譬喻品
    xu = _subtree(nodes, "T34n1723_p0651a06")
    piyu = _subtree(nodes, "T34n1723_p0734b07")
    assert sum("truncated" in n["flags"] for n in xu) == 15
    assert sum("truncated" in n["flags"] for n in piyu) == 6
    # the 序品 entry of coverage_spans stops at outline level 5, and the subtree reaches it
    (entry,) = [
        s for s in compiled[0]["metadata"]["coverage_spans"] if s["max_level"] not in (None, 2)
    ]
    assert entry["commentary"]["start"] == "T34n1723_p0651a06"
    assert max(n["level"] for n in xu) == entry["max_level"] == 5


def test_committed_gold_piyu_opening(compiled):
    # 譬喻品 opening = a TEST-split answer key (commentary T34n1723_p0734b07 to p0737b04), checked
    # through lineheads and counts only, so no test-span text is quoted here (global constraint 5)
    nodes = compiled[0]["nodes"]
    pin = next(n for n in nodes if n["locations"]["commentary"]["explained"] == "T34n1723_p0734b07")
    sub = [n for n in nodes if n["id"].startswith(pin["id"] + ".")]
    assert len(sub) == 36
    assert [n["node_class"] for n in sub if n["parent_id"] == pin["id"]] == [
        "commentary-internal",  # the gate node
        "sutra-span",  # the 品文 node (大文分二)
    ]
    # every commentary locator lies inside the split span: nothing is read from the reserve
    for n in sub:
        for lh in n["locations"]["commentary"].values():
            assert lh is None or "T34n1723_p0734b08" <= lh < "T34n1723_p0737b04", (n["id"], lh)
    # one leaf per lemma block: Kuiji's 13 經「…」贊曰 blocks over p0735b21–p0737b02 (R03 F15)
    parents = {n["parent_id"] for n in nodes}
    leaves = [n for n in sub if n["node_class"] == "sutra-span" and n["id"] not in parents]
    assert len(leaves) == 13
    assert len({n["locations"]["root_text"]["raw"] for n in leaves}) == 13
    spans = [
        (n["locations"]["root_text"]["start"], n["locations"]["root_text"]["end"]) for n in leaves
    ]
    assert spans[0][0] == "T09n0262_p0010b29" and spans[-1][1] == "T09n0262_p0010c27"
    # the leaves tile T09n0262_p0010b29–c27: each starts on its predecessor's last line (a shared
    # line) or on the line after it, never earlier and with no line skipped
    root = authored.load_text(RAW_CBETA / "T09n0262.xml")
    for (_, prev_end), (next_start, _) in pairwise(spans):
        assert root.pos[next_start] - root.pos[prev_end] in (0, 1), (prev_end, next_start)
    # the four parts of 釋歡喜之所以 start on the 領解 prose cuts of R03 F23
    four = next(n for n in sub if n["locations"]["commentary"]["explained"] == "T34n1723_p0735c08")
    assert four["child_count_announced"] == 4
    assert [n["locations"]["root_text"]["start"] for n in sub if n["parent_id"] == four["id"]] == [
        "T09n0262_p0010c02",
        "T09n0262_p0010c04",
        "T09n0262_p0010c10",
        "T09n0262_p0010c13",
    ]
    # the nodes whose announced children run past p0737b04 are flagged truncated
    flagged = sorted(
        n["locations"]["commentary"]["explained"] for n in sub if "truncated" in n["flags"]
    )
    assert flagged == [
        "T34n1723_p0735b21",
        "T34n1723_p0735b23",
        "T34n1723_p0737a13",
        "T34n1723_p0737a25",
        "T34n1723_p0737a27",
        "T34n1723_p0737b01",
    ]


def test_committed_gold_xupin_levels_1_to_3(compiled):
    # 序品 levels 1–3 = a TEST-split answer key (commentary T34n1723_p0651a06 to p0694b22), checked
    # through lineheads, classes and counts only, so no test-span text is quoted here (global
    # constraint 5)
    nodes = compiled[0]["nodes"]
    root = authored.load_text(RAW_CBETA / "T09n0262.xml")
    pin = next(n for n in nodes if n["level"] == 2 and n["id"].startswith("1_1."))
    assert pin["locations"]["commentary"]["explained"] == "T34n1723_p0651a06"
    sub = [n for n in nodes if n["id"].startswith(pin["id"] + ".")]
    per_level = {}
    for n in sub:
        per_level[n["level"]] = per_level.get(n["level"], 0) + 1
    # three levels below the 品 node, no deeper
    assert per_level == {3: 2, 4: 13, 5: 23}
    # every commentary locator lies inside the split span: nothing is read from the reserve
    for n in sub:
        for lh in n["locations"]["commentary"].values():
            assert lh is None or "T34n1723_p0651a06" <= lh < "T34n1723_p0694b22", (n["id"], lh)
    kids = {n["id"]: [c for c in nodes if c["parent_id"] == n["id"]] for n in [pin] + sub}
    gate, pinwen = kids[pin["id"]]
    # Kuiji convention: the gate node (六門, R03 F1) and the node for the division of the 品 text
    assert (gate["node_class"], pinwen["node_class"]) == ("commentary-internal", "sutra-span")
    assert gate["child_count_announced"] == 6 and len(kids[gate["id"]]) == 6
    assert [g["locations"]["commentary"]["explained"] for g in kids[gate["id"]]] == [
        "T34n1723_p0651b04",
        "T34n1723_p0657a08",
        "T34n1723_p0657c03",
        "T34n1723_p0659a17",
        "T34n1723_p0660b04",
        "T34n1723_p0661a28",
    ]
    for n in sub:
        if n["id"].startswith(gate["id"]):
            assert n["node_class"] == "commentary-internal" and n["locations"]["root_text"] is None
    # the 品文 node: the 法華論's seven 成就 (p0661c09), spanning the 品 text after its title line
    assert pinwen["locations"]["commentary"]["explained"] == "T34n1723_p0661c09"
    assert pinwen["child_count_announced"] == 7 and len(kids[pinwen["id"]]) == 7
    rt = pinwen["locations"]["root_text"]
    assert (rt["start"], rt["end"], rt["end_basis"]) == (
        "T09n0262_p0001c19",
        "T09n0262_p0005b23",
        "chapter",
    )
    # the seven are taken up in order, each after the listing at p0661c11–c24
    seven = kids[pinwen["id"]]
    ann = [n["locations"]["commentary"]["announced"] for n in seven]
    assert all("T34n1723_p0661c11" <= a <= "T34n1723_p0661c24" for a in ann) and ann == sorted(ann)
    exp = [n["locations"]["commentary"]["explained"] for n in seven]
    assert exp == sorted(exp)
    # sūtra-span children tile their parent: first start = parent start, last end = parent end,
    # each next start on the previous end line or the line after it
    for n in [pinwen] + sub:
        spans = [
            (c["locations"]["root_text"]["start"], c["locations"]["root_text"]["end"])
            for c in kids.get(n["id"], [])
            if c["node_class"] == "sutra-span"
        ]
        if not spans or n["node_class"] != "sutra-span":
            continue
        prt = n["locations"]["root_text"]
        assert spans[0][0] == prt["start"] and spans[-1][1] == prt["end"], n["id"]
        for (_, prev_end), (next_start, _) in pairwise(spans):
            assert root.pos[next_start] - root.pos[prev_end] in (0, 1), (n["id"], prev_end)
    # four starts (three lemma variants; two nodes share the first) are the annotator's cut where
    # Kuiji's lemma differs from T09n0262's wording
    manual = sorted(
        n["locations"]["commentary"]["explained"]
        for n in sub
        if n["locations"]["root_text"] and n["locations"]["root_text"]["basis"] == "manual"
    )
    assert manual == [
        "T34n1723_p0680b11",
        "T34n1723_p0680b28",
        "T34n1723_p0680c23",
        "T34n1723_p0694b05",
    ]
    # the level-5 nodes under which Kuiji divides further are flagged truncated (depth limit)
    flagged = sorted(
        n["locations"]["commentary"]["explained"] for n in sub if "truncated" in n["flags"]
    )
    assert flagged == [
        "T34n1723_p0651b06",
        "T34n1723_p0652b19",
        "T34n1723_p0653b28",
        "T34n1723_p0653c26",
        "T34n1723_p0655a02",
        "T34n1723_p0661c28",
        "T34n1723_p0666a16",
        "T34n1723_p0667a22",
        "T34n1723_p0679b29",
        "T34n1723_p0680a19",
        "T34n1723_p0681a20",
        "T34n1723_p0683a15",
        "T34n1723_p0683c09",
        "T34n1723_p0688b05",
        "T34n1723_p0694b05",
    ]
    assert all(n["level"] == 5 for n in sub if "truncated" in n["flags"])
    assert all(n["origin"] == "explicit" and n["evidence"] for n in sub)
