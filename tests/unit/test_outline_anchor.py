"""outline.anchor: root spans from the commentary's lemmas (sūtra mode) and the outlined-text
sidecar (docs/outliner-design.md §5.5).

Acceptance: the Kuiji gold's 陀羅尼品 subtree (the T1723 dev split) and its ancestors, filtered
programmatically — nothing else of the gold is read into the test (data/EVAL-SETS.md, "Do not open
while developing"; notes of levels 1–2 are dropped) — is stripped of every root span except the 品's
chapter span and the lemma raws, then resolved over the committed T09n0262 陀羅尼品 excerpt:
every lemma-based start and end must equal the gold's; the gold's manual (hand-cut) spans come out
unmapped. Synthetic cases on the same excerpt exercise the fuzzy methods (gapped, prefix, suffix,
interpolated) and their report codes; 善導's 五門 over T12n0365 (both outside every split) is the
raw-gated table GUANJING_SPANS.
Offline on the committed fixtures; the whole-file checks skip without data/raw/.
"""

from __future__ import annotations

import collections
import json
import re

import jsonschema
import pytest

from chinese_workflow.common import outline_doc
from chinese_workflow.common.paths import FIXTURES, REFERENCE_OUTLINES, SCHEMAS, cbeta_xml_path
from chinese_workflow.ingest.text import load_input_text
from chinese_workflow.outline import anchor, repair

ROOT_XML = FIXTURES / "cbeta-xml-p5" / "T09n0262-excerpt-p0058b08-p0059b27.xml"
COM_XML = FIXTURES / "cbeta-xml-p5" / "T34n1723-excerpt-p0850a19-p0850b19.xml"
GOLD = REFERENCE_OUTLINES / "T0262" / "kuiji-xuanzan" / "outline.json"
DEV = ("T34n1723_p0850a19", "T34n1723_p0850b19")  # inclusive; the registry's dev span of T1723
PIN = ("T09n0262_p0058b08", "T09n0262_p0059b27")  # the 陀羅尼品 of T09n0262 (chapter span)
REF = {"path": "outline.json", "sha256": "0" * 64}
MARKER = re.compile(r"^\[\S+\) .*\{\S+, \S+\}( \(inferred, \S+\))?\]$")
SIDECAR = jsonschema.Draft202012Validator(
    json.loads((SCHEMAS / "outlined-text.schema.json").read_text(encoding="utf-8")))


# ----------------------------------------------------------------------------------------- helpers


def _dev_gold() -> list:
    """The gold's 陀羅尼品 node (level 2, explained in the dev span), its subtree and its ancestors,
    in document order. Nothing else of the gold is kept; notes of levels 1–2 are dropped."""
    nodes = json.loads(GOLD.read_text(encoding="utf-8"))["nodes"]

    def explained(n):
        com = (n.get("locations") or {}).get("commentary") or {}
        return (com.get("explained") or "").split(":")[0]

    pins = [n for n in nodes if n["level"] == 2 and DEV[0] <= explained(n) <= DEV[1]]
    if len(pins) != 1:
        raise RuntimeError("expected one dev 品 node in the Kuiji gold, found %d" % len(pins))
    pin = pins[0]
    by_id = {n["id"]: n for n in nodes}
    chain, p = [], pin["parent_id"]
    while p is not None:
        chain.append(by_id[p])
        p = by_id[p]["parent_id"]
    sub = [n for n in nodes if n["id"] == pin["id"] or n["id"].startswith(pin["id"] + ".")]
    out = []
    for n in list(reversed(chain)) + sub:
        n = json.loads(json.dumps(n))
        if n["level"] <= 2:
            n["notes"] = []
        out.append(n)
    return out


def _meta(**kw) -> dict:
    meta = {"text_id": "T0262", "text_title_src": "妙法蓮華經", "outline_mode": "sutra",
            "root_text_id": "T09n0262", "commentary_id": "T34n1723", "scheme_id": "kuiji-xuanzan",
            "source_file": "tests/unit/test_outline_anchor.py",
            "source_document": {"kind": "synthetic", "text_id": None, "title": "anchor test"},
            "generated_by": "tests/unit/test_outline_anchor.py",
            "format_note": "anchor test document"}
    meta.update(kw)
    return meta


def _dev_doc(strip: bool) -> tuple:
    """(document renumbered from the dev gold nodes, {new id: gold node}). strip=True keeps only the
    品's chapter span and the lemma raws, the input the anchor step gets from tiers 1 and 2."""
    gold = _dev_gold()
    by_orig = {n["id"]: n for n in gold}
    drafts = outline_doc.to_drafts({"nodes": gold})

    def walk(ds):
        for d in ds:
            rt = d["locations"].get("root_text")
            pin = rt is not None and rt.get("basis") == "chapter" and d["heading_src"] == "陀羅尼品"
            if strip and rt is not None and not pin:
                d["locations"]["root_text"] = (
                    {"start": None, "end": None, "basis": "lemma", "raw": rt["raw"]}
                    if rt.get("basis") == "lemma" else None)
            walk(d["children"])

    walk(drafts)
    doc, private = outline_doc.build_prediction(
        drafts, **_meta(source_document={"kind": "commentary", "text_id": "T34n1723",
                                         "title": "妙法蓮華經玄贊"}))
    return doc, {nid: by_orig[p["_orig_id"]] for nid, p in private.items()}


def _root():
    return load_input_text(ROOT_XML, role="root")


def _commentary():
    return load_input_text(COM_XML, role="commentary")


def _line(ref):
    """A locator at line granularity (the scorer compares lines; anchor starts carry ':n'
    when mid-line)."""
    return ref.split(":", 1)[0] if isinstance(ref, str) else ref


def _rt(n: dict) -> dict | None:
    return n["locations"].get("root_text")


def _loc(explained=None, root_text=None, announced=None) -> dict:
    return {"scheme": "cbeta-kepan", "commentary": {"announced": announced, "explained": explained},
            "root_text": root_text}


def _node(heading, raw=None, children=(), explained=None, root_text=None, **kw) -> dict:
    if raw is not None:
        root_text = {"start": None, "end": None, "basis": "lemma", "raw": raw}
    return {"heading_src": heading, "locations": _loc(explained, root_text),
            "children": list(children), **kw}


def _pin_doc(children) -> dict:
    """A synthetic outline: one 品 node with the chapter span of the T09n0262 excerpt."""
    pin = _node("陀羅尼品", explained=DEV[0], children=children,
                root_text={"start": PIN[0], "end": PIN[1], "basis": "chapter"})
    return outline_doc.build_prediction([pin], **_meta())[0]


def _valid(doc: dict) -> None:
    rep = outline_doc.validate(doc)
    assert rep.passed(), [f.render() for f in rep.errors]


def _check_sidecar(sc: dict, text: str) -> None:
    """Schema-valid; spans ordered and disjoint, tiling [coverage.start, coverage.end) together
    with the gaps."""
    SIDECAR.validate(sc)
    pieces = sorted([(s["char_start"], s["char_end"]) for s in sc["spans"]]
                    + [(g["char_start"], g["char_end"]) for g in sc["gaps"]])
    at = sc["coverage"]["start"]
    for a, b in pieces:
        assert a == at and b > a, (a, b, at)
        at = b
    assert at == sc["coverage"]["end"] == len(text)
    assert sc["coverage"]["overlaps"] == 0
    assert sc["coverage"]["covered"] == sum(s["char_end"] - s["char_start"] for s in sc["spans"])


def _md_text(md: str) -> str:
    return "".join(line for line in md.split("\n") if line and not MARKER.match(line))


def _md_markers(md: str) -> list:
    return [line for line in md.split("\n") if MARKER.match(line)]


# -------------------------------------------------------------------- (a) root spans: acceptance


def test_resolve_reproduces_the_gold_lemma_spans():
    doc, gold = _dev_doc(strip=True)
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    outline_doc.assert_explicit_unchanged(doc, out)
    lemma, manual = [], []
    for n in out["nodes"]:
        g = gold[n["id"]]
        grt, rt = _rt(g), _rt(n)
        if n["node_class"] == "commentary-internal":
            assert rt is None
            continue
        if grt and grt["basis"] == "lemma":
            lemma.append(n["heading_src"])
            assert (_line(rt["start"]), rt["basis"], rt["raw"]) == (grt["start"], "lemma", grt["raw"]), \
                n["heading_src"]
            assert rt["end"] == grt["end"], n["heading_src"]
            assert rt["end_basis"] == (grt.get("end_basis") or "lemma"), n["heading_src"]
            assert "unmapped" not in n["flags"]
        elif grt and grt["basis"] == "manual":
            manual.append(n["heading_src"])
            assert rt is None and "unmapped" in n["flags"], n["heading_src"]
    assert len(lemma) == 11 and len(manual) == 29
    pin = next(n for n in out["nodes"] if n["heading_src"] == "陀羅尼品")
    assert _rt(pin) == _rt(gold[pin["id"]])  # tier 1's chapter span is kept as given
    top = out["nodes"][0]  # stripped level-1 node: start derived from its only placed child, the 品
    assert (_rt(top)["start"], _rt(top)["basis"]) == (PIN[0], "chapter")
    codes = sorted({r["code"] for r in report})
    assert codes == ["unmapped"] and len(report) == 29


def test_resolve_does_not_modify_its_input_and_is_idempotent():
    doc, _ = _dev_doc(strip=True)
    before = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    once, _ = anchor.resolve_root_spans(doc, _root())
    assert json.dumps(doc, ensure_ascii=False, sort_keys=True) == before
    twice, _ = anchor.resolve_root_spans(once, _root())
    assert twice == once


# --------------------------------------------------------------------- (a) root spans: synthetic


@pytest.mark.parametrize("raw, parts", [
    ("爾時藥王至功德甚多", [("爾時藥王", "功德甚多")]),
    ("經「爾時藥王至功德甚多」", [("爾時藥王", "功德甚多")]),
    ("「爾時勇施」下", [("爾時勇施", None)]),
    ("從「爾時毘沙門」下至「無諸衰患」", [("爾時毘沙門", "無諸衰患")]),
    ("乃至受持至功德甚多", [("乃", "受持至功德甚多"), ("乃至受持", "功德甚多")]),
    ("", []),
    ("「」。", []),
])
def test_lemma_parts(raw, parts):
    assert anchor.lemma_parts(raw) == parts


def test_mid_line_start_shares_the_line_and_lemma_end_binds():
    # 功德甚/多。」爾時藥王菩薩白佛言 — the second division starts mid-line on T09n0262_p0058b17
    doc = _pin_doc([_node("初", "爾時藥王至功德甚多"), _node("次", "爾時藥王至多所饒益")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    first, second = (_rt(n) for n in out["nodes"][1:])
    assert (_line(first["start"]), first["end"], first["end_basis"]) == (
        "T09n0262_p0058b09", "T09n0262_p0058b17", "lemma")
    assert (_line(second["start"]), second["end"], second["end_basis"]) == (
        "T09n0262_p0058b17", PIN[1], "chapter")  # last child: ends with the 品
    assert [r["code"] for r in report] == []


def test_prefix_fallback_and_interpolation_after_the_elder_lemma_end():
    # 甲: no whole or gapped match of A (汝 is not within 6 of 言 at b17), the prefix 爾時藥王菩薩白佛言 is; B 多所饒益 at c08.
    # 乙's lemma is nowhere in the text: it starts where 甲's lemma ends (the first character after 益。」, c09).
    doc = _pin_doc([_node("甲", "爾時藥王菩薩白佛言汝等至多所饒益"), _node("乙", "如來壽量至不可思議")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    a, b = out["nodes"][1:]
    assert (_rt(a)["start"], _rt(a)["end"], _rt(a)["basis"], _rt(a)["end_basis"]) == (
        "T09n0262_p0058b17:3", "T09n0262_p0058c08", "lemma", "lemma")
    assert _rt(b) == {"start": "T09n0262_p0058c09", "end": PIN[1], "basis": "interpolated",
                      "end_basis": "chapter", "raw": "如來壽量至不可思議"}
    assert "unmapped" not in b["flags"]
    assert [(r["node_id"], r["code"]) for r in report] == [
        (a["id"], "lemma-prefix"), (b["id"], "lemma-interpolated")]


def test_gapped_in_scans_each_lemma_part_from_the_window_start(monkeypatch):
    """gapped_in (rule A/B's lookahead) searches the window [lo, hi) once per candidate A of a
    lemma; a part whose only matches are in headings moves its own scan on, never the next part's
    (final review 2026-10-03: `lo` advanced across the parts of a 至-split lemma)."""
    doc = _pin_doc([_node("甲", "甲甲甲至乙乙乙至丙丙丙")])  # parts: A = 甲甲甲 / A = 甲甲甲至乙乙乙
    res = anchor._Resolver(doc, _root(), [])
    node = doc["nodes"][1]
    calls = []

    def fake(t, a, lo, hi):
        calls.append((a, lo, hi))
        return (50, 53) if a == "甲甲甲" and lo <= 50 else None  # part 1: one match, in a heading

    monkeypatch.setattr(anchor, "_gapped", fake)
    monkeypatch.setattr(res, "in_heads", lambda p: p == 50)
    assert res.gapped_in(node, 10, 100) is False
    assert calls == [("甲甲甲", 10, 100), ("甲甲甲", 51, 100), ("甲甲甲至乙乙乙", 10, 100)]
    # a match outside the headings in the second part is found from the window start
    monkeypatch.setattr(anchor, "_gapped", lambda t, a, lo, hi: (
        (50, 53) if a == "甲甲甲" and lo <= 50 else (20, 25) if a != "甲甲甲" and lo <= 20 else None))
    assert res.gapped_in(node, 10, 100) is True


@pytest.mark.parametrize("old, kept", [("interpolated", "lemma"), ("lemma", "lemma"), (None, "lemma"),
                                       ("inferred", "inferred"), ("manual", "manual")])
def test_an_unplaced_stub_has_no_derived_basis(old, kept):
    """Final review 2026-10-03: one rule for a nulled root span (anchor.nulled_basis, shared with
    outline.repair): a derived basis (DERIVED_BASES, or none) becomes `lemma`, any other basis is kept."""
    assert anchor.nulled_basis(old) == kept
    rt = {"start": None, "end": None, "raw": "如來壽量至不可思議"}
    if old is not None:
        rt["basis"] = old
    doc = _pin_doc([_node("甲", root_text=rt)])
    out, _ = anchor.resolve_root_spans(doc, _root())  # the lemma is not in the excerpt: a null start
    got = _rt(out["nodes"][1])
    assert (got["start"], got["end"], got["basis"], got["raw"]) == (None, None, kept, "如來壽量至不可思議")
    assert "unmapped" in out["nodes"][1]["flags"]


def test_first_child_lemma_not_found_stays_unmapped():
    # no elder sibling, so no lemma end to interpolate from
    doc = _pin_doc([_node("甲", "如來壽量至不可思議"), _node("乙", "爾時勇施至無諸衰患")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    a, b = out["nodes"][1:]
    assert _rt(a) == {"start": None, "end": None, "basis": "lemma", "raw": "如來壽量至不可思議"}
    assert "unmapped" in a["flags"]
    assert (_rt(b)["start"], _rt(b)["end"]) == ("T09n0262_p0058c09", PIN[1])
    assert [(r["node_id"], r["code"]) for r in report] == [(a["id"], "lemma-not-found"), (a["id"], "unmapped")]


def test_gapped_lemma_skips_characters_and_a_wildcard():
    # 爾時藥王等白佛: 等 stands for 菩薩. At b09 白 lies 14 characters after 王 (no match); b17 爾時藥王菩薩白佛言 matches.
    doc = _pin_doc([_node("甲", "爾時藥王等白佛"), _node("乙", "爾時勇施至無諸衰患")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    a, b = out["nodes"][1:]
    assert (_rt(a)["start"], _rt(a)["end"], _rt(a)["basis"], _rt(a)["end_basis"]) == (
        "T09n0262_p0058b17:3", "T09n0262_p0058c08", "lemma", "next-node")
    assert _line(_rt(b)["start"]) == "T09n0262_p0058c09"
    assert [(r["node_id"], r["code"]) for r in report] == [(a["id"], "lemma-gapped")]
    assert "爾時藥王菩薩白佛" in report[0]["detail"]


def test_suffix_of_the_lemma_places_a_locator_prefixed_incipit():
    # 藥王品末 is the commentator's locator, not root text: no whole, gapped or prefix match; the suffix 爾時勇施菩薩 is
    doc = _pin_doc([_node("甲", "藥王品末爾時勇施菩薩")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    a = out["nodes"][1]
    assert (_rt(a)["start"], _rt(a)["end"], _rt(a)["end_basis"]) == ("T09n0262_p0058c09", PIN[1], "chapter")
    assert [(r["node_id"], r["code"]) for r in report] == [(a["id"], "lemma-suffix")]


def test_lemma_end_by_gapped_and_suffix_matches_is_reported():
    # B 功德多 for 功德甚多 (gapped, ends on b17); B 得多所饒益 for 多所饒益 (suffix, c08)
    doc = _pin_doc([_node("甲", "爾時藥王至功德多"), _node("乙", "爾時藥王至得多所饒益")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    a, b = out["nodes"][1:]
    assert (_line(_rt(a)["start"]), _rt(a)["end"], _rt(a)["end_basis"]) == (
        "T09n0262_p0058b09", "T09n0262_p0058b17", "lemma")
    assert (_rt(b)["start"], _rt(b)["end"]) == ("T09n0262_p0058b17:3", PIN[1])
    assert [(r["node_id"], r["code"]) for r in report] == [
        (a["id"], "lemma-end-gapped"), (b["id"], "lemma-end-suffix")]


def test_fuzzy_lemma_end_stays_inside_the_enclosing_lemma():
    # 諸衰等患 (gapped 諸衰患) occurs first at a13, past the parent 甲's lemma end c08: not taken under 甲, taken at top level
    child = _node("子", "爾時藥王至諸衰等患")
    out, report = anchor.resolve_root_spans(
        _pin_doc([_node("甲", "爾時藥王至多所饒益", children=[child])]), _root())
    _valid(out)
    a, c = out["nodes"][1:]
    assert _line(_rt(c)["start"]) == _line(_rt(a)["start"]) == "T09n0262_p0058b09"
    assert [(r["node_id"], r["code"]) for r in report] == [(c["id"], "lemma-end-not-found")]
    assert "whole before the end of the text, gapped or suffix before T09n0262_p0058c08:13" in report[0]["detail"]
    out2, report2 = anchor.resolve_root_spans(_pin_doc([_node("乙", "爾時藥王至諸衰等患")]), _root())
    b = out2["nodes"][1]
    assert [(r["node_id"], r["code"]) for r in report2] == [(b["id"], "lemma-end-gapped")]
    assert "T09n0262_p0059a13" in report2[0]["detail"]


def test_interpolation_needs_the_elder_lemma_end_exactly_and_is_idempotent():
    # 乙 (lemma nowhere) starts where 甲's lemma ends: the character after 功德甚多。」 on b17. 丙 (lemma nowhere) follows an
    # interpolated node, which has no lemma end, so it stays unmapped.
    doc = _pin_doc([_node("甲", "爾時藥王至功德甚多"), _node("乙", "如來壽量至不可思議"),
                    _node("丙", "法師功德至常精進")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    a, b, c = out["nodes"][1:]
    assert (_rt(a)["end"], _rt(a)["end_basis"]) == ("T09n0262_p0058b17", "lemma")
    assert _rt(b) == {"start": "T09n0262_p0058b17:3", "end": PIN[1], "basis": "interpolated",
                      "end_basis": "chapter", "raw": "如來壽量至不可思議"}
    assert _rt(c)["start"] is None and "unmapped" in c["flags"]
    assert [(r["node_id"], r["code"]) for r in report] == [
        (b["id"], "lemma-interpolated"), (c["id"], "lemma-not-found"), (c["id"], "unmapped")]
    twice, _ = anchor.resolve_root_spans(out, _root())
    assert twice == out  # an interpolated start is re-derived, not kept


def test_interpolation_needs_an_elder_lemma_end_found_as_a_b():
    # 甲's lemma is an incipit alone (爾時藥王菩薩, no 至B): its 'end' is only the end of A, not a point where the
    # commentary divides the text. 乙 (lemma nowhere) is not placed right after 甲's A (that start would also hide 乙
    # from the resolver, which takes only unmapped nodes): it stays unmapped.
    doc = _pin_doc([_node("甲", "爾時藥王菩薩"), _node("乙", "如來壽量至不可思議")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    a, b = out["nodes"][1:]
    assert (_rt(a)["start"], _rt(a)["end"]) == ("T09n0262_p0058b09", PIN[1])
    assert _rt(b) == {"start": None, "end": None, "basis": "lemma", "raw": "如來壽量至不可思議"}
    assert "unmapped" in b["flags"]
    assert [(r["node_id"], r["code"]) for r in report] == [(b["id"], "lemma-not-found"), (b["id"], "unmapped")]


def test_a_node_interpolated_once_and_unmapped_later_loses_the_derived_basis():
    doc = _pin_doc([_node("甲", "爾時藥王至功德甚多"), _node("乙", "如來壽量至不可思議")])
    once, _ = anchor.resolve_root_spans(doc, _root())
    assert _rt(once["nodes"][2])["basis"] == "interpolated"
    once["nodes"][1]["locations"]["root_text"]["raw"] = "爾時藥王菩薩"  # the elder's lemma lost its B
    again, _ = anchor.resolve_root_spans(once, _root())
    _valid(again)
    assert _rt(again["nodes"][2]) == {"start": None, "end": None, "basis": "lemma",
                                      "raw": "如來壽量至不可思議"}
    assert "unmapped" in again["nodes"][2]["flags"]


def test_inside_elder_retry_searches_a_whole_b_anywhere_in_the_parent_window():
    # 甲's lemma ends at 無諸衰患 (a13), so 乙 and 丙 begin inside its range and are found by the inside-elder retry (A
    # before the cursor). Their B 是諸佛已 lies past the cursor (a21): it is a whole B anywhere after A in the parent
    # window, not 'lemma-end-not-found', and 乙's lemma end (a21) is then past its tiled end (a13).
    doc = _pin_doc([_node("甲", "爾時勇施至無諸衰患"), _node("乙", "爾時毘沙門至是諸佛已"),
                    _node("丙", "爾時持國至是諸佛已")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    a, b, c = out["nodes"][1:]
    assert (_line(_rt(b)["start"]), _rt(b)["end"], _rt(b)["end_basis"]) == (
        "T09n0262_p0059a07", "T09n0262_p0059a13", "next-node")
    assert (_rt(c)["start"], _rt(c)["end"]) == ("T09n0262_p0059a13:16", PIN[1])
    assert [(r["node_id"], r["code"]) for r in report] == [
        (b["id"], "lemma-inside-elder-lemma"), (c["id"], "lemma-inside-elder-lemma"),
        (a["id"], "lemma-end-beyond-span"), (b["id"], "lemma-end-beyond-span")]


def test_monotone_siblings_and_lemma_end_beyond_the_tiled_end():
    # 甲's lemma end (如是法師, b26) lies past 乙's start: reported, not applied; 乙 is found only
    # inside 甲's lemma range (after 甲's start). 丙 quotes a lemma that occurs only before its elder
    # siblings, so it stays unmapped (starts never precede an elder sibling's start).
    doc = _pin_doc([_node("甲", "爾時勇施至如是法師"), _node("乙", "爾時毘沙門至無諸衰患"),
                    _node("丙", "爾時藥王至功德甚多")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    a, b, c = out["nodes"][1:]
    assert (_line(_rt(a)["start"]), _rt(a)["end"], _rt(a)["end_basis"]) == (
        "T09n0262_p0058c09", "T09n0262_p0059a06", "next-node")
    assert (_line(_rt(b)["start"]), _rt(b)["end"]) == ("T09n0262_p0059a07", PIN[1])
    assert _rt(c)["start"] is None and "unmapped" in c["flags"]
    assert [(r["node_id"], r["code"]) for r in report] == [
        (b["id"], "lemma-inside-elder-lemma"), (c["id"], "lemma-not-found"),
        (a["id"], "lemma-end-beyond-span"), (c["id"], "unmapped")]


# A summary: three items whose starts run to the 品's last lines (b09, c09, b17), as 善導's 卷二 五門 runs over the
# whole 觀經; 爾時毘沙門至無諸衰患 (a07) and 爾時持國至是諸佛已 (a13) lie between its second and third item.
SUMMARY = [("子", "爾時藥王至多所饒益"), ("丑", "爾時勇施"), ("寅", "諸羅剎女說此偈已")]
YOUNGER = [("卯", "爾時毘沙門至無諸衰患"), ("辰", "爾時持國至是諸佛已")]


def test_a_summary_subtree_does_not_move_the_cursor():
    # rule A: 總's subtree covers more of the window than it leaves (b09..b17 of b08..b27), its starts run past every
    # later lemma (卯's only A is at a07, 辰's at a13) and two later lemmas have a whole A after the restore point, so the
    # cursor returns to just after 總's start and 卯, 辰 are placed by a plain search, not left unmapped behind the
    # cursor (b17) and the elder's last start.
    doc = _pin_doc([_node("總", children=[_node(h, raw) for h, raw in SUMMARY])]
                   + [_node(h, raw) for h, raw in YOUNGER])
    out, report = anchor.resolve_root_spans(doc, _root())
    total, yin, mao, chen = out["nodes"][1], out["nodes"][4], out["nodes"][5], out["nodes"][6]
    assert (_rt(mao)["start"], _rt(mao)["end"], _rt(mao)["basis"]) == (
        "T09n0262_p0059a07", "T09n0262_p0059a13", "lemma")
    assert (_rt(chen)["start"], _rt(chen)["end"]) == ("T09n0262_p0059a13:16", PIN[1])
    assert "unmapped" not in mao["flags"] and "unmapped" not in chen["flags"]
    assert _rt(total)["end"] == "T09n0262_p0059a06"  # the summary's tiled end; its later items are clamped to it
    codes = [(r["node_id"], r["code"]) for r in report]
    assert (total["id"], "summary-transparent") in codes
    assert not [c for _, c in codes if c in ("lemma-not-found", "unmapped")]
    assert "the cursor returns to T09n0262_p0058b09:1" in next(r["detail"] for r in report
                                                              if r["code"] == "summary-transparent")
    # the consequence, by construction: 寅 starts at b17 but its parent 總 ends at a06 (the next sibling's start), so the
    # output is not valid as it stands — child-outside-parent on 寅 only, which the pipeline's repair pass handles
    errors = outline_doc.validate(out).errors
    assert [(f.code, f.where) for f in errors] == [("child-outside-parent", yin["id"])]
    assert repair.repair(out, errors) and outline_doc.validate(out).passed()

    # the same summary as a whole tier-1 root (a 卷): the next root continues from just after its start
    two = outline_doc.build_prediction(
        [_node("甲卷", children=[_node(h, raw) for h, raw in SUMMARY]),
         _node("乙卷", children=[_node(h, raw) for h, raw in YOUNGER])], **_meta())[0]
    out2, report2 = anchor.resolve_root_spans(two, _root())
    juan1, yin2, mao2, chen2 = out2["nodes"][0], out2["nodes"][3], out2["nodes"][5], out2["nodes"][6]
    assert [(_rt(n)["start"], _rt(n)["basis"]) for n in (mao2, chen2)] == [
        ("T09n0262_p0059a07", "lemma"), ("T09n0262_p0059a13:16", "lemma")]
    assert [(r["node_id"], r["code"]) for r in report2 if r["code"] == "summary-transparent"] == [
        (juan1["id"], "summary-transparent")]
    errors2 = outline_doc.validate(out2).errors
    assert [(f.code, f.where) for f in errors2] == [("child-outside-parent", yin2["id"])]


def test_a_final_subtree_followed_by_one_requoting_node_is_not_a_summary():
    # the same subtree with ONE younger lemma (卯, whose only A, a07, lies before 寅's start b17): a correct final
    # subtree followed by a node that re-quotes an earlier lemma. One later lemma is not enough for rule A (it needs two
    # with a whole A after the restore point): the cursor stays after the subtree, only 卯 is unmapped, and nothing is
    # clamped — the outline stays valid. (With A firing on one lemma, 丑 and 寅 were clamped and validation failed.)
    doc = _pin_doc([_node("總", children=[_node(h, raw) for h, raw in SUMMARY]), _node(*YOUNGER[0])])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    total, zi, chou, yin, mao = out["nodes"][1:]
    assert _rt(mao)["start"] is None and "unmapped" in mao["flags"]
    assert [_line(_rt(n)["start"]) for n in (zi, chou, yin)] == [
        "T09n0262_p0058b09", "T09n0262_p0058c09", "T09n0262_p0059b17"]
    assert (_rt(total)["end"], _rt(yin)["end"]) == (PIN[1], PIN[1])
    assert [(r["node_id"], r["code"]) for r in report] == [
        (mao["id"], "lemma-not-found"), (mao["id"], "unmapped")]


def test_tier1_roots_share_the_cursor_unless_an_elder_is_a_summary():
    # no summary: 甲卷's last start (c09) lies before 寅's A (a07), so 甲卷 is not one — its lemma end (b26) merely
    # runs past 寅. The cursor runs on from root to root (no per-root restart), so 寅, searched from b26 in 乙卷, is
    # not found; within one root the inside-elder retry finds it (A after the elder's last start).
    doc = outline_doc.build_prediction(
        [_node("甲卷", children=[_node("子", "爾時藥王至功德甚多"), _node("丑", "爾時勇施至如是法師")]),
         _node("乙卷", children=[_node("寅", "爾時毘沙門至無諸衰患")])], **_meta())[0]
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    yin = out["nodes"][4]
    assert _rt(yin)["start"] is None and "unmapped" in yin["flags"]
    codes = [(r["node_id"], r["code"]) for r in report]
    assert (yin["id"], "lemma-not-found") in codes
    assert "summary-transparent" not in [c for _, c in codes]

    one = outline_doc.build_prediction(
        [_node("甲卷", children=[_node("子", "爾時藥王至功德甚多"), _node("丑", "爾時勇施至如是法師"),
                                _node("寅", "爾時毘沙門至無諸衰患")])], **_meta())[0]
    out1, report1 = anchor.resolve_root_spans(one, _root())
    yin1 = out1["nodes"][3]
    assert _rt(yin1)["start"] == "T09n0262_p0059a07"
    assert (yin1["id"], "lemma-inside-elder-lemma") in [(r["node_id"], r["code"]) for r in report1]


def test_a_generic_lemma_that_strands_its_younger_siblings_is_given_up():
    # rule B: after 丑 (b17:3, an incipit, so no interpolation point) the earliest 佛告 is b19 (佛告諸羅剎女), past the
    # only A of 乙 (c09) and of 丙 (a07). Taking it would cost two lemmas to place one, and no later 佛告 can do better,
    # so it is rejected: 甲 stays unmapped and 乙, 丙 are placed (without the rule both were left behind the cursor).
    lead = [_node("子", "爾時藥王至功德甚多"), _node("丑", "爾時藥王菩薩白佛言")]
    doc = _pin_doc(lead + [_node("甲", "佛告"), _node("乙", "爾時勇施"), _node("丙", "爾時毘沙門")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    jia, yi, bing = out["nodes"][3:]
    assert _rt(jia)["start"] is None and "unmapped" in jia["flags"]
    assert (_rt(yi)["start"], _rt(bing)["start"]) == ("T09n0262_p0058c09", "T09n0262_p0059a07")
    assert [(r["node_id"], r["code"]) for r in report] == [
        (jia["id"], "lemma-lookahead"), (jia["id"], "lemma-not-found"), (jia["id"], "unmapped")]
    assert "「佛告」 at T09n0262_p0059b19:15 rejected" in report[0]["detail"]


def test_lookahead_keeps_the_earliest_hit_when_it_strands_fewer_than_two():
    # no lookahead needed: from the 品's start the earliest 佛告 is b12 (佛告藥王), before 乙 and 丙 — kept, not b19
    doc = _pin_doc([_node("甲", "佛告"), _node("乙", "爾時勇施"), _node("丙", "爾時毘沙門")])
    out, report = anchor.resolve_root_spans(doc, _root())
    assert _rt(out["nodes"][1])["start"] == "T09n0262_p0058b12:9"
    assert report == []
    # one younger sibling stranded: placing 甲 costs one lemma and places one, so the earliest hit (b19) is kept
    lead = [_node("子", "爾時藥王至功德甚多"), _node("丑", "爾時藥王菩薩白佛言")]
    out2, report2 = anchor.resolve_root_spans(_pin_doc(lead + [_node("甲", "佛告"), _node("乙", "爾時勇施")]),
                                              _root())
    jia, yi = out2["nodes"][3:]
    assert _rt(jia)["start"] == "T09n0262_p0059b19:15"
    assert _rt(yi)["start"] is None
    assert "lemma-lookahead" not in [r["code"] for r in report2]


def test_lookahead_counts_a_loosely_quoted_sibling_as_placeable():
    # rule B counts a younger sibling as stranded only when it has neither a whole nor a gapped A after the candidate
    # start. 甲's A is right at a07. 乙 is quoted loosely: its whole A occurs only at c07 (before a07), but a gapped match
    # puts it at a08 (愍念眾生、擁護此法師故，說是陀羅尼); 丙 has a whole A only at c04 and is placed after 乙 by a suffix of
    # its A (a20). Only 丙 is lost by 甲 at a07 (one, under the threshold), so 甲 is kept and all three are placed; counting
    # whole hits only, both 乙 and 丙 were "lost" and 甲, the correct hit, was given up.
    doc = _pin_doc([_node("甲", "爾時毘沙門"), _node("乙", "愍念擁護此法師故說是陀羅尼"),
                    _node("丙", "六十二億恒河沙等諸佛所說若有侵毀此法師者")])
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    jia, yi, bing = out["nodes"][1:]
    assert [_rt(n)["start"] for n in (jia, yi, bing)] == [
        "T09n0262_p0059a07", "T09n0262_p0059a08:2", "T09n0262_p0059a20:15"]
    assert not [n for n in out["nodes"] if "unmapped" in n["flags"]]
    assert [(r["node_id"], r["code"]) for r in report] == [(yi["id"], "lemma-gapped"), (bing["id"], "lemma-suffix")]


def test_the_cursor_stays_monotone_within_one_root():
    # 寅 quotes 爾時藥王至功德甚多, which occurs only before 子's own start (b09) and 丑's (c09): within one root a start
    # never precedes an elder sibling's start, so 寅 is not placed at b09. Its lemma is found nowhere after the cursor
    # (丑's lemma end, b26), so it starts where that lemma ends (interpolated).
    doc = outline_doc.build_prediction(
        [_node("甲卷", children=[_node("子", "爾時藥王至功德甚多"), _node("丑", "爾時勇施至如是法師"),
                                _node("寅", "爾時藥王至功德甚多")])], **_meta())[0]
    out, report = anchor.resolve_root_spans(doc, _root())
    _valid(out)
    zi, chou, yin = out["nodes"][1:]
    assert _rt(zi)["start"] == "T09n0262_p0058b09"
    assert (_rt(yin)["start"], _rt(yin)["basis"]) == ("T09n0262_p0059b26:14", "interpolated")
    assert (yin["id"], "lemma-interpolated") in [(r["node_id"], r["code"]) for r in report]


def test_start_derived_from_children_and_commentary_internal_left_alone():
    gate = _node("三門分別", node_class="commentary-internal", explained=DEV[0])
    wrapper = _node("二天", children=[_node("初", "爾時毘沙門至無諸衰患"), _node("後", "爾時持國至是諸佛已")])
    out, report = anchor.resolve_root_spans(_pin_doc([gate, wrapper]), _root())
    _valid(out)
    g, w, first, last = out["nodes"][1:]
    assert _rt(g) is None and g["flags"] == []
    assert _rt(w) == {"start": "T09n0262_p0059a07", "end": PIN[1], "basis": "lemma",
                      "end_basis": "chapter"}
    assert (_rt(first)["end"], _rt(first)["end_basis"]) == ("T09n0262_p0059a13", "lemma")
    assert (_line(_rt(last)["start"]), _rt(last)["end"]) == ("T09n0262_p0059a13", PIN[1])
    assert report == []


def test_not_sutra_mode_is_a_no_op_and_wrong_root_text_is_refused():
    doc = _pin_doc([_node("甲", "爾時勇施")])
    self_doc = json.loads(json.dumps(doc))
    self_doc["metadata"]["outline_mode"] = "self-outlining"
    out, report = anchor.resolve_root_spans(self_doc, _root())
    assert out == self_doc and [r["code"] for r in report] == ["not-sutra-mode"]
    with pytest.raises(ValueError):
        anchor.resolve_root_spans(doc, _commentary())


@pytest.mark.skipif(cbeta_xml_path("T09n0262") is None, reason="no data/raw/cbeta/T09n0262.xml")
def test_resolve_over_the_whole_root_text_agrees():
    doc, gold = _dev_doc(strip=True)
    out, _ = anchor.resolve_root_spans(doc, load_input_text("T09n0262", role="root"))
    _valid(out)
    for n in out["nodes"]:
        grt = _rt(gold[n["id"]])
        if grt and grt["basis"] == "lemma":
            assert (_line(_rt(n)["start"]), _rt(n)["end"]) == (grt["start"], grt["end"]), n["heading_src"]


# 善導's 觀經疏 五門 over the 觀經 (T37n1753 卷二 p0251c09-p0252b01 lemmas; T12n0365 whole): both texts lie outside every
# eval split. heading: (start, end, basis, end_basis) after T7; the unfound raw 阿難為耆闍大眾傳說 is 善導's own
# description taken as a lemma by SPAN_RE (not fixed here; the node takes its first child's start).
GUANJING_TREE = _node("觀經序分義", children=[_node("五門明義", children=[
    _node("明其序分", "如是我聞至五苦所逼云何見極樂世界", children=[
        _node("證信序", "如是我聞一句"),
        _node("正明發起序", children=[
            _node("明化前序", "一時佛在至法王子而為上首"),
            _node("正明發起序禁父之緣", "王舍大城至顏色和悅"),
            _node("明禁母緣", "時阿闍世至不令復出"),
            _node("明厭苦緣", "時韋提希被幽閉至共為眷屬"),
            _node("明其欣淨緣", "唯願為我廣說至教我正受"),
            _node("明散善顯行緣", "爾時世尊即便微笑至淨業正因"),
            _node("正明定善示觀緣", "佛告阿難等諦聽至云何得見極樂國土")])]),
    _node("明正宗分", "日觀初句佛告韋提汝及眾生至下品下生"),
    _node("正明得益分", "說是語時至諸天發心"),
    _node("明流通分", "阿難白佛至韋提等歡喜"),
    _node("復是一會", "阿難為耆闍大眾傳說", children=[
        _node("耆闍序分", "爾時世尊足步虛空還耆闍崛山"),
        _node("耆闍正宗分", "阿難廣為大眾說如上事"),
        _node("耆闍流通分", "一切大眾歡喜奉行")])])])
GUANJING_SPANS = {
    "明其序分": ("T12n0365_p0340c29", "T12n0365_p0341c27", "lemma", "lemma"),
    "證信序": ("T12n0365_p0340c29", "T12n0365_p0340c29", "lemma", "next-node"),
    "正明發起序": ("T12n0365_p0340c29:5", "T12n0365_p0341c27", "lemma", "lemma"),
    "明化前序": ("T12n0365_p0340c29:5", "T12n0365_p0341a02", "lemma", "lemma"),
    "正明發起序禁父之緣": ("T12n0365_p0341a02:16", "T12n0365_p0341a14", "lemma", "lemma"),
    "明禁母緣": ("T12n0365_p0341a14:8", "T12n0365_p0341b02", "lemma", "lemma"),
    "明厭苦緣": ("T12n0365_p0341b02:5", "T12n0365_p0341b16", "lemma", "lemma"),
    "明其欣淨緣": ("T12n0365_p0341b16:5", "T12n0365_p0341c01", "lemma", "lemma"),
    "明散善顯行緣": ("T12n0365_p0341c01:10", "T12n0365_p0341c14", "lemma", "lemma"),
    "正明定善示觀緣": ("T12n0365_p0341c15", "T12n0365_p0341c27", "lemma", "lemma"),
    "明正宗分": ("T12n0365_p0341c27:17", "T12n0365_p0346a27", "lemma", "next-node"),
    "正明得益分": ("T12n0365_p0346a27:4", "T12n0365_p0346b05", "lemma", "next-node"),
    "明流通分": ("T12n0365_p0346b05:2", "T12n0365_p0346b17", "lemma", "next-node"),
    "復是一會": ("T12n0365_p0346b18", "T12n0365_p0346b21", "lemma", "next-node"),
    "耆闍序分": ("T12n0365_p0346b18", "T12n0365_p0346b18", "lemma", "lemma"),
    "耆闍正宗分": ("T12n0365_p0346b18:19", "T12n0365_p0346b21", "lemma", "next-node"),
}
# 善導's 耆闍流通分 lemma 一切大眾歡喜奉行 is an END quote (從X已來: the item ends where X does); read as an incipit it
# matched nothing, and since T7's fix round the elder's lemma (阿難廣為大眾說如上事, no 至B) is no division point to
# interpolate from, so the node stays unmapped (end-quote semantics: Task 8).
GUANJING_UNMAPPED = ["耆闍流通分"]
GUANJING_CODES = {"lemma-end-gapped": 2, "lemma-gapped": 3, "lemma-suffix": 1, "lemma-prefix": 1,
                  "lemma-end-not-found": 2, "lemma-not-found": 2, "unmapped": 1}


@pytest.mark.skipif(cbeta_xml_path("T12n0365") is None, reason="no data/raw/cbeta/xml-p5/T/T12/T12n0365.xml")
def test_shandao_guanjing_lemmas_over_the_whole_sutra():
    doc = outline_doc.build_prediction([GUANJING_TREE], **_meta(
        text_id="T0365", text_title_src="觀無量壽佛經", root_text_id="T12n0365", commentary_id="T37n1753",
        scheme_id="shandao-guanjing-shu"))[0]
    out, report = anchor.resolve_root_spans(doc, load_input_text("T12n0365", role="root"))
    _valid(out)
    got = {n["heading_src"]: (_rt(n)["start"], _rt(n)["end"], _rt(n)["basis"], _rt(n).get("end_basis"))
           for n in out["nodes"] if n["heading_src"] in GUANJING_SPANS}
    assert got == GUANJING_SPANS
    assert [n["heading_src"] for n in out["nodes"] if "unmapped" in n["flags"]] == GUANJING_UNMAPPED
    assert dict(collections.Counter(r["code"] for r in report)) == GUANJING_CODES
    # the old cascade's search start p0346b19:9 (nine ids before T7) is named now only by the unmapped node's own entry
    assert [r["heading"] for r in report if "T12n0365_p0346b19:9" in r["detail"]] == ["耆闍流通分"]


# ------------------------------------------------------------------------------- (b) outlined-text


def test_outlined_text_over_the_commentary_dev_excerpt():
    doc, gold = _dev_doc(strip=False)
    com = _commentary()
    sc, md = anchor.outlined_text(doc, com, target_role="commentary", outline_ref=REF)
    _check_sidecar(sc, com.text)
    assert sc["coverage"]["ratio"] == 1.0 and sc["gaps"] == []
    assert sc["unplaced"] == [doc["nodes"][0]["id"]]  # the 流通 node is explained before the span
    assert "".join(com.text[s["char_start"]:s["char_end"]] for s in sc["spans"]) == com.text
    assert sc["target"] == {"text_id": "T34n1723", "role": "commentary", "sha256": com.sha256,
                            "first_linehead": DEV[0], "last_linehead": DEV[1],
                            "length": len(com.text)}
    first = sc["spans"][0]
    assert gold[first["node_id"]]["heading_src"] == "陀羅尼品" and first["kind"] == "preamble"
    assert com.text[first["char_start"]:first["char_end"]] == "陀羅尼品"
    by_node = {s["node_id"]: s for s in sc["spans"]}
    for n in doc["nodes"][1:]:
        s = by_node.get(n["id"])
        if s is not None:
            assert s["linehead_start"] == n["locations"]["commentary"]["explained"]
            assert s["resolution"] == "explained"
            kids = [m for m in doc["nodes"] if m["parent_id"] == n["id"]]
            assert s["kind"] == ("preamble" if kids else "leaf"), n["heading_src"]
    assert _md_text(md) == com.text
    assert len(_md_markers(md)) == len(doc["nodes"]) - 1
    assert _md_markers(md)[0] == "[1₁1₂) 陀羅尼品 {-, T34n1723_p0850a19}]"


def test_outlined_text_over_the_root_excerpt_after_resolve():
    doc, _ = _dev_doc(strip=True)
    root = _root()
    out, _ = anchor.resolve_root_spans(doc, root)
    sc, md = anchor.outlined_text(out, root, target_role="root", outline_ref=REF)
    _check_sidecar(sc, root.text)
    assert sc["coverage"]["ratio"] == 1.0
    unplaced = {n["id"] for n in out["nodes"] if _rt(n) is None or _rt(n)["start"] is None}
    assert set(sc["unplaced"]) == unplaced and len(unplaced) == 4 + 29
    for s in sc["spans"]:
        node = next(n for n in out["nodes"] if n["id"] == s["node_id"])
        assert s["linehead_start"] == _line(_rt(node)["start"]) and s["resolution"] == "root_text"
    assert "".join(root.text[s["char_start"]:s["char_end"]] for s in sc["spans"]) == root.text
    assert _md_text(md) == root.text


def test_mid_line_offsets_split_the_commentary_text():
    com = _commentary()

    def at(linehead, needle):
        return "%s:%d" % (linehead, com.index.line_text(linehead).index(needle))

    a = at("T34n1723_p0850b01", "此初")
    b = at("T34n1723_p0850b03", "下明神呪")
    c = at("T34n1723_p0850b18", "品第三段")
    tree = [_node("品文分三", explained="T34n1723_p0850a29", children=[
        _node("初", explained=a), _node("次", explained=b, children=[
            _node("初二聖", explained="T34n1723_p0850b05")]),
        _node("後", explained=c, origin="inferred", confidence=0.7)])]
    doc = outline_doc.build_prediction(tree, **_meta())[0]
    sc, md = anchor.outlined_text(doc, com, target_role="commentary", outline_ref=REF)
    _check_sidecar(sc, com.text)
    text = {s["node_id"]: com.text[s["char_start"]:s["char_end"]] for s in sc["spans"]}
    kinds = {s["node_id"]: s["kind"] for s in sc["spans"]}
    ids = [n["id"] for n in doc["nodes"]]
    assert text[ids[0]].startswith("經「爾時藥王至功德甚多」") and text[ids[0]].endswith("獲益。")
    assert text[ids[1]].startswith("此初。") and text[ids[1]].endswith("贊曰：")
    assert text[ids[2]] == "下明神呪之方。有五，合為三類：初二聖，次二天，後十神。"
    assert text[ids[4]] == "品第三段時眾獲益。"
    assert [kinds[i] for i in ids] == ["preamble", "leaf", "preamble", "leaf", "leaf"]
    assert sc["spans"][1]["linehead_start"] == sc["spans"][0]["linehead_end"] == "T34n1723_p0850b01"
    assert sc["gaps"] == [{"char_start": 0, "char_end": com.offset("T34n1723_p0850a29"),
                           "reason": "before first node"}]
    assert sc["coverage"]["ratio"] < 1
    assert _md_text(md) == com.text
    lines = md.split("\n")
    assert lines[lines.index(_md_markers(md)[1]) - 2].endswith("獲益。")  # b01 broken mid-line
    assert _md_markers(md)[-1].endswith("{-, %s} (inferred, 0.7)]" % c)


def test_root_start_with_an_offset_splits_mid_line():
    doc = _pin_doc([
        _node("持經之福", root_text={"start": "T09n0262_p0058b09", "end": "T09n0262_p0058b17",
                                  "basis": "manual"}),
        _node("神呪之方", root_text={"start": "T09n0262_p0058b17:3", "end": PIN[1],
                                  "basis": "manual"})])
    out, report = anchor.resolve_root_spans(doc, _root())
    assert out == doc and report == []  # complete manual spans are kept as given
    root = _root()
    sc, _ = anchor.outlined_text(out, root, target_role="root", outline_ref=REF)
    _check_sidecar(sc, root.text)
    text = [root.text[s["char_start"]:s["char_end"]] for s in sc["spans"]]
    assert text[0] == "妙法蓮華經陀羅尼品第二十六"
    assert text[1].endswith("功德甚多。」") and text[2].startswith("爾時藥王菩薩白佛言")


def test_outlined_text_rejects_an_unknown_role():
    with pytest.raises(ValueError):
        anchor.outlined_text(_pin_doc([]), _root(), target_role="translation", outline_ref=REF)
