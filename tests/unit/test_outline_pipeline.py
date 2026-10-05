"""outline.pipeline.build end to end, offline, on the two committed 陀羅尼品 excerpts (the T1723 dev
span and the T0262 chapter it comments on; data/EVAL-SETS.md, "Parser cases and fixtures"): sūtra
mode, source tier2, no resolver. Checks what a build writes after its last tree edit — every node
carries the span-start locator (common.outline_doc.fill_span_starts; E06 review 2026-10-02, A3) —
and that the build read only the dev span."""

from __future__ import annotations

import pytest

from chinese_workflow.common.paths import FIXTURES
from chinese_workflow.outline.pipeline import OutlineConfig, build

COM_XML = FIXTURES / "cbeta-xml-p5" / "T34n1723-excerpt-p0850a19-p0850b19.xml"
ROOT_XML = FIXTURES / "cbeta-xml-p5" / "T09n0262-excerpt-p0058b08-p0059b27.xml"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    cfg = OutlineConfig(mode="sutra", root="T09n0262", commentary="T34n1723",
                        scheme_id="kuiji-xuanzan", source="tier2",
                        xml={"T34n1723": str(COM_XML), "T09n0262": str(ROOT_XML)})
    return build(cfg, tmp_path_factory.mktemp("dharani-build"))


def test_build_validates_and_reads_only_the_dev_span(built):
    assert built["report"]["validation"]["passed"]
    prose = next(e for e in built["report"]["split_guard"]
                 if e["purpose"] == "outline: T34n1723 prose")
    assert prose["splits"] == ["dev"]


def test_every_node_leaves_the_build_with_a_span_start(built):
    """Every node of this build has a commentary position with an explained line, so every node
    gets the pair: a first child its parent's start (inherited), everyone else its own line."""
    nodes = built["doc"]["nodes"]
    coms = {n["id"]: n["locations"]["commentary"] for n in nodes}
    assert all(isinstance(c, dict) and c.get("explained") for c in coms.values())
    assert all("span_start" in c and "span_start_inherited" in c for c in coms.values())
    firsts = [n for n in nodes if n["parent_id"] and n["sibling_index"] == 1]
    assert len(firsts) >= 10
    for n in firsts:
        c = coms[n["id"]]
        assert c["span_start_inherited"] is True
        assert c["span_start"] == coms[n["parent_id"]]["span_start"]
    for n in nodes:
        if n not in firsts:
            c = coms[n["id"]]
            assert c["span_start_inherited"] is False and c["span_start"] == c["explained"]
