"""Tests for Task 1 of the eval-dataset build: scripts/fetch_dila_sdp.sh's recursive-tree and
T1718-text outputs (data/raw/dila-sdp/, gitignored, eval-only per plan Global Constraint 1 — never
a committed fixture).

All tests here skip when the raw files they need are absent (run scripts/fetch_dila_sdp.sh, which
in turn calls scripts/sdp_tree.py). 卷 boundaries for the T1718 anchor-range checks come from
data/raw/cbeta/T34n1718.xml via chinese_workflow.ingest.lines (cb:mulu type="卷"), never typed from
memory (plan Global Constraint 3).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from chinese_workflow.ingest.lines import extract

REPO = Path(__file__).resolve().parents[2]
SDP = REPO / "data" / "raw" / "dila-sdp"
T1718_XML = REPO / "data" / "raw" / "cbeta" / "T34n1718.xml"

TREE_FILES = {"T0262": SDP / "tree-T0262-full.json", "T1718": SDP / "tree-T1718-full.json"}

# the 20 卷-half keys T1718's tree is split into, "1a" (卷第一上) .. "10b" (卷第十下) — see
# scripts/fetch_dila_sdp.sh's header for why sdp's getHtml returns one 卷-half per call for T1718
# (unlike T0262, where one getHtml call covers a whole 卷).
JUAN_KEYS = ["%d%s" % (n, half) for n in range(1, 11) for half in ("a", "b")]
JUAN_HTML = {k: SDP / ("T1718-juan%s.html" % k) for k in JUAN_KEYS}

ANCHOR_RE = re.compile(r'name="(\d{4}[abc]\d{2})"')


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip("%s not fetched (run scripts/fetch_dila_sdp.sh)" % path.relative_to(REPO))
    return path


def _walk(nodes: list):
    """Yield every node dict of a sdp tree (a list of top-level nodes, each carrying "children"),
    depth-first, in the server order the tree was fetched in."""
    for n in nodes:
        yield n
        yield from _walk(n.get("children") or [])


def _load_tree(key: str) -> list:
    return json.loads(_require(TREE_FILES[key]).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------- tree structure


@pytest.mark.parametrize("key", ["T0262", "T1718"])
def test_tree_parses_and_has_expected_shape(key):
    tree = _load_tree(key)
    assert isinstance(tree, list) and tree, "tree is empty"
    nodes = list(_walk(tree))
    assert nodes
    for n in nodes:
        assert isinstance(n["id"], str) and n["id"], n
        assert isinstance(n["text"], str), n
        assert isinstance(n["leaf"], bool), n
        if n.get("fetch_error") is not None:
            # a node sdp_tree.py could never expand (a per-node server defect, e.g. T1718D08_018
            # returning a non-JSON body every time) -- recorded, not dropped, not treated as a leaf
            assert set(n) == {"id", "text", "leaf", "children", "fetch_error"}, n
            assert n["leaf"] is False, n
            assert n["children"] is None, n
            assert isinstance(n["fetch_error"], str) and n["fetch_error"], n
        else:
            assert set(n) == {"id", "text", "leaf", "children"}, n
            assert isinstance(n["children"], list), n
            if n["leaf"]:
                assert n["children"] == [], "leaf node %s has children" % n["id"]
    # node ids follow the documented "<docid>D<level>_<seq>" scheme (scripts/fetch_dila_sdp.sh
    # header); this also means every id in the T0262 tree is distinguishable from every id in the
    # T1718 tree, so the two trees' id sets cannot collide
    assert all(re.match(r"^%sD\d+_\d+$" % re.escape(key), n["id"]) for n in nodes)


@pytest.mark.parametrize("key", ["T0262", "T1718"])
def test_tree_ids_unique(key):
    nodes = list(_walk(_load_tree(key)))
    ids = [n["id"] for n in nodes]
    assert len(ids) == len(set(ids)), "duplicate node ids in the %s tree" % key


def test_tree_root_matches_saved_root_json():
    """tree-T<id>-full.json's top level must equal the id/text/leaf of the already-committed
    tree-T<id>-root.json (same getTreeNode call; the full tree just expands every non-leaf node
    further)."""
    for key, root_file in (("T0262", "tree-T0262-root.json"), ("T1718", "tree-T1718-root.json")):
        root_path = SDP / root_file
        if not root_path.exists():
            pytest.skip("%s not fetched" % root_file)
        root_nodes = json.loads(root_path.read_text(encoding="utf-8"))
        full = _load_tree(key)
        assert [(n["id"], n["text"], n["leaf"]) for n in full] == [
            (n["id"], n["text"], n["leaf"]) for n in root_nodes
        ]


# --------------------------------------------------------------------- T1718 卷-half HTML coverage


def _t1718_juan_boundaries():
    """[(linehead, k)] for T34n1718.xml's 20 cb:mulu type="卷" markers, in document order — the
    ground truth for which CBETA lines belong to which 卷-half."""
    if not T1718_XML.exists():
        pytest.skip("data/raw/cbeta/T34n1718.xml not fetched (scripts/fetch_cbeta.sh)")
    ex = extract(T1718_XML)
    mulu = [(r["linehead"], m["n"]) for r in ex.lines for m in r["mulu"] if m["type"] == "卷"]
    assert len(mulu) == 20, "expected 20 卷 mulu (1a..10b) in T34n1718.xml, found %d" % len(mulu)
    return mulu


@pytest.mark.parametrize("k", JUAN_KEYS)
def test_t1718_juan_html_contains_own_anchors(k):
    path = _require(JUAN_HTML[k])
    boundaries = _t1718_juan_boundaries()
    ns = [n for _, n in boundaries]
    i = ns.index(k)
    start_n = boundaries[i][0].split("_p")[1]
    end_n = boundaries[i + 1][0].split("_p")[1] if i + 1 < len(boundaries) else None

    html = path.read_text(encoding="utf-8")
    anchors = set(ANCHOR_RE.findall(html))
    assert anchors, "%s has no Taishō line anchors" % path.name
    # the file reaches into its own 卷-half (not entirely earlier material): true even for 1a,
    # whose file also carries the preface/byline front matter that precedes 卷第一上's own mulu
    # milestone, so 1a's anchors legitimately start *before* start_n.
    assert any(a >= start_n for a in anchors), (
        "%s never reaches its own 卷 start %s (last anchor %s)" % (path.name, start_n, max(anchors))
    )
    # no anchor strays past the *next* 卷-half's start (sdp's getHtml has been observed to include
    # that one boundary anchor as the last item of the preceding half, never anything past it) --
    # and, symmetrically, this file's own first anchor is usually a few lines *after* start_n, not
    # before it (sdp attributes the exact mulu boundary line to the *preceding* half's file as its
    # last item; e.g. 卷第四下 starts at 0052c02, but T1718-juan4b.html's own first anchor is
    # 0052c03) -- not asserted strictly since 1a's front matter is the documented exception.
    if end_n is not None:
        assert all(a <= end_n for a in anchors), (
            "%s has an anchor past its own 卷-half (next starts at %s)" % (path.name, end_n)
        )
