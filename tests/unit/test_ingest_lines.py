"""Tests for chinese_workflow.ingest.lines (CBETA XML P5 line extractor + text index).

Always run: tests/fixtures/cbeta-xml-p5/G069n1977.xml (committed, verbatim CBETA file) and the
committed works/toc JSON in tests/fixtures/cbeta-api/. Run when present, skip otherwise
(data/raw/ is gitignored; scripts/fetch_cbeta.sh, fetch_cbeta_xml_p5.sh, fetch_cbeta_api.sh,
fetch_dila_sdp.sh): T09n0262, T34n1723, T34n1718, T31n1602, T31n1605, X11n0268, X12n0281.

Expected line texts were read off the XML by hand. The T0262 prose lines were also checked,
punctuation-insensitively, against the Taishō line anchors ([0001c19] …) of DILA's SDP HTML
(data/raw/dila-sdp/T0262-juan1.html), an older Big5-era text with 。-only punctuation: 2,872 of
its 3,410 anchored lines match the extractor exactly once punctuation is stripped; the rest
differ for SDP-side reasons (verse stanzas under one anchor, headings, characters SDP drops such
as 睺/憙/呪, gaiji written as compositions, CBETA 【CB】 emendations like 迦→伽 at 0001c23).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from lxml import etree

from chinese_workflow.ingest.lines import (
    build_index,
    extract,
    find,
    find_spans,
    iter_lines,
    main,
    strip_punct,
)

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures"
G1977 = FIX / "cbeta-xml-p5" / "G069n1977.xml"
RAW = REPO / "data" / "raw"
RAW_XML = {
    "T0262": RAW / "cbeta" / "T09n0262.xml",
    "T1723": RAW / "cbeta" / "T34n1723.xml",
    "T1718": RAW / "cbeta" / "T34n1718.xml",
    "T1602": RAW / "cbeta" / "xml-p5" / "T" / "T31" / "T31n1602.xml",
    "T1605": RAW / "cbeta" / "xml-p5" / "T" / "T31" / "T31n1605.xml",
    "X0268": RAW / "cbeta" / "xml-p5" / "X" / "X11" / "X11n0268.xml",
    "X0281": RAW / "cbeta" / "xml-p5" / "X" / "X12" / "X12n0281.xml",
}
SDP_JUAN1 = RAW / "dila-sdp" / "T0262-juan1.html"

TEI = "{http://www.tei-c.org/ns/1.0}"
CB = "{http://www.cbeta.org/ns/1.0}"

_CACHE: dict = {}


def lines_of(path: Path) -> list:
    if path not in _CACHE:
        _CACHE[path] = extract(path).lines
    return _CACHE[path]


def raw(key: str) -> Path:
    p = RAW_XML[key]
    if not p.exists():
        pytest.skip(
            "%s not fetched (run the scripts/fetch_cbeta*.sh scripts)" % p.relative_to(REPO)
        )
    return p


def by_n(lines: list) -> dict:
    return {r["n"]: r for r in lines}


def lxml_body(path: Path):
    root = etree.parse(str(path)).getroot()
    return root, root.find(TEI + "text/" + TEI + "body")


def backward_jumps(lines: list) -> list:
    ns = [r["n"] for r in lines]
    return [(ns[i - 1], ns[i]) for i in range(1, len(ns)) if ns[i] <= ns[i - 1]]


# --------------------------------------------------------------------------- structural invariants

# lineheads are unique everywhere; the only backward jump in these files is T0262's 附文
# (T09 p. 198), inserted by CBETA between 妙音菩薩品 (ends 0056c01) and 普門品 (starts 0056c02).
EXPECTED_JUMPS = {
    "G1977": [],
    "T0262": [("0198b11", "0056c02")],
    "T1723": [],
    "T1718": [],
    "X0268": [],
    "X0281": [],
}


def _is_excluded_note(el) -> bool:
    return el.tag == TEI + "note" and "inline" not in (el.get("place") or "")


@pytest.mark.parametrize("key", ["G1977", "T0262", "T1723", "T1718", "X0268", "X0281"])
def test_line_invariants(key):
    path = G1977 if key == "G1977" else raw(key)
    ex = extract(path)
    lines = ex.lines
    root, body = lxml_body(path)
    canon = re.match(r"[A-Z]+", root.get("{http://www.w3.org/XML/1998/namespace}id")).group(0)
    own = [
        lb
        for lb in body.iter(TEI + "lb")
        if canon in (lb.get("ed") or "").split() and lb.get("type") != "old"
    ]
    other = [lb for lb in body.iter(TEI + "lb") if canon not in (lb.get("ed") or "").split()]

    lhs = [r["linehead"] for r in lines]
    assert len(lhs) == len(set(lhs)), "lineheads not unique"
    assert all(
        lh == "%s_p%s" % (root.get("{http://www.w3.org/XML/1998/namespace}id"), r["n"])
        for lh, r in zip(lhs, lines)
    )
    assert backward_jumps(lines) == EXPECTED_JUMPS[key]
    # one line per own-edition lb of text/body, in the same order
    assert [r["n"] for r in lines] == [lb.get("n") for lb in own]
    # other-edition lbs (X files' R017) are all kept as alt lineheads
    assert sum(len(r["alt"]) for r in lines) == len(other)
    # every cb:mulu of the file is reported exactly once, in document order (file-wide == body for
    # these files; corpus-wide, 8 files repeat 35 body mulu inside back/app/lem, which are skipped)
    file_mulu = list(root.iter(CB + "mulu"))
    got = [(m["type"], m["level"], m["n"]) for r in lines for m in r["mulu"]]
    want = [
        (m.get("type"), int(m.get("level")) if m.get("level") else None, m.get("n"))
        for m in file_mulu
    ]
    assert got == want
    # every g outside cb:mulu and excluded notes is accounted for in some line's gaiji list
    body_g = [
        g
        for g in body.iter(TEI + "g")
        if not any(a.tag == CB + "mulu" or _is_excluded_note(a) for a in g.iterancestors())
    ]
    assert sum(len(r["gaiji"]) for r in lines) == len(body_g)
    assert ex.unanchored == []
    # every non-inline note of text/body is recorded once, in document order, with its full text
    # (none of these files has one inside an excluded region); X0281 has 2,123, the others 0
    xnotes = [n for n in body.iter(TEI + "note") if _is_excluded_note(n)]
    got_x = [e for r in lines for e in r["excluded_notes"]]
    assert [(e["place"], e["type"]) for e in got_x] == [
        (n.get("place"), n.get("type")) for n in xnotes
    ]
    layout = str.maketrans("", "", "\n\r\t")
    for e, n in zip(got_x, xnotes):
        if next(n.iter(TEI + "g"), None) is None:  # g-free: text is the element's text as is
            assert e["text"] == "".join(n.itertext()).translate(layout)
    # offsets inside the line
    for r in lines:
        n = len(r["text"])
        assert all(0 <= s < e <= n for s, e in r["inline_notes"])
        assert all(0 <= g["offset"] < n for g in r["gaiji"])
        assert all(0 <= m["offset"] <= n for m in r["mulu"])
        assert all(0 <= x["offset"] <= n for x in r["excluded_notes"])


def test_iter_lines_matches_extract():
    assert list(iter_lines(G1977)) == extract(G1977).lines


# ------------------------------------------------------------------------- G069n1977 (always runs)


def test_g1977_known_lines():
    lines = lines_of(G1977)
    L = by_n(lines)
    assert len(lines) == 17
    assert all(r["juan"] == 1 for r in lines)
    assert L["0717a01"]["text"] == "始終心要"
    assert L["0717a01"]["heads"] == [{"kind": "jhead", "text": "始終心要", "offset": 0}]
    assert [(m["level"], m["type"], m["text"]) for m in L["0717a01"]["mulu"]] == [
        (1, "科判", "心要分二"),
        (2, "科判", "初題目二"),
        (3, "科判", "初標題目"),
        (None, "卷", ""),
    ]
    assert L["0717a01"]["juan_marks"] == [{"fun": "open", "n": "1", "offset": 0}]
    assert L["0717a02"]["text"] == "唐天台沙門釋湛然述"
    assert L["0717a03"]["text"] == "夫三諦者。天然之性德也。中諦者統一切法。真諦者泯一切法。俗諦者"
    assert L["0717a04"]["text"] == "立一切法。舉一即三非前後也。含生本具非造作之所得也。"
    assert L["0718a01"]["text"] == "解脫德。中觀者。破無明惑。證一切種智。成法身德。"
    # juan-close jhead with an inline note: kept in the text, marked in inline_notes
    assert L["0718a06"]["text"] == "始終心要竟"
    assert L["0718a06"]["inline_notes"] == [(4, 5)]
    assert L["0718a06"]["heads"][0]["text"] == "始終心要竟"
    # the 15 科判 nodes, levels 1-5, in order
    kepan = [(m["level"], m["text"]) for r in lines for m in r["mulu"] if m["type"] == "科判"]
    assert len(kepan) == 15
    assert kepan[-1] == (3, "三始終體一修證圓頓")
    assert {lv for lv, _ in kepan} == {1, 2, 3, 4, 5}
    # div_types is taken at the line's first content: on 0717a03 that is the two mulu before
    # the untyped <cb:div> opens; from 0717a04 on the line starts inside it (no @type -> None)
    assert L["0717a03"]["div_types"] == []
    assert L["0717a04"]["div_types"] == [None]


# ----------------------------------------------------------------------------- T09n0262 / T34n1723


def test_t0262_known_lines():
    L = by_n(lines_of(raw("T0262")))
    expected = {
        "0001a02": "No. 262 [Nos. 263, 264]",
        "0001c05": "溺之沈流；一極悲心，拯昏迷之失性。自漢至",
        "0001c12": "",
        "0001c14": "妙法蓮華經卷第一",
        "0001c17": "鳩摩羅什奉\u3000詔譯",
        "0001c18": "序品第一",
        "0001c19": "如是我聞：一時，佛住王舍城耆闍崛山中，",
        "0001c20": "與大比丘眾萬二千人俱，皆是阿羅漢，諸漏",
        "0001c21": "已盡，無復煩惱，逮得己利，盡諸有結，心得",
        "0001c24": "弗、大目揵連、摩訶迦旃延、阿\u3779樓馱、劫",
        "0002a15": "爾時釋提桓因，與其眷屬二萬天子俱。復",
        "0002c09": "「文殊師利！導師何故，眉間白毫，",
        "0002c10": "大光普照。雨曼陀羅、曼殊沙華，",
    }
    for n, text in expected.items():
        assert L[n]["text"] == text, n
    assert all(L[n]["juan"] == 1 for n in expected)
    assert L["0056c01"]["juan"] == 7
    # juan opener: empty 卷 mulu, jhead, juan mark
    assert L["0001c14"]["heads"] == [{"kind": "jhead", "text": "妙法蓮華經卷第一", "offset": 0}]
    assert [(m["type"], m["n"], m["text"]) for m in L["0001c14"]["mulu"]] == [("卷", "001", "")]
    assert L["0001c14"]["juan_marks"] == [{"fun": "open", "n": "001", "offset": 0}]
    # 品 opener: mulu text is CBETA's label, the head is the printed heading; the line carries
    # the pin div
    m = L["0001c18"]["mulu"]
    assert [(x["level"], x["type"], x["n"], x["text"], x["div_type"]) for x in m] == [
        (1, "品", "1", "1 序品", "pin")
    ]
    assert L["0001c18"]["heads"] == [{"kind": "head", "text": "序品第一", "offset": 0}]
    assert L["0001c18"]["div_types"] == ["pin"]
    assert L["0001c05"]["div_types"] == ["xu"]
    # gaiji CB00145 resolved through its unicode mapping (U+3779)
    assert L["0001c24"]["gaiji"] == [{"offset": 14, "ref": "CB00145", "via": "unicode"}]
    # verse in 序品: first line of the stanza opened at lb 0002c09, caesura offsets recorded;
    # a prose line is not verse
    assert L["0002c09"]["in_verse"] and L["0002c10"]["in_verse"]
    assert L["0002c09"]["caesuras"] == [6, 11]
    assert not L["0001c19"]["in_verse"]
    # the 附文's level-2 序 sits in div w > xu
    m = L["0198a12"]["mulu"][0]
    assert (m["level"], m["type"], m["text"], m["div_type"]) == (
        2,
        "序",
        "御製觀世音普門品經序",
        "xu",
    )
    assert L["0198a12"]["div_types"] == ["w", "xu"]


SDP_PROSE = ["0001c05", "0001c08", "0001c19", "0001c20", "0001c21", "0002a15"]


def test_t0262_prose_lines_agree_with_dila_sdp_anchors():
    L = by_n(lines_of(raw("T0262")))
    if not SDP_JUAN1.exists():
        pytest.skip("data/raw/dila-sdp not fetched (scripts/fetch_dila_sdp.sh)")
    html = SDP_JUAN1.read_text(encoding="utf-8")
    html = re.sub(
        r'<div class="head_title">.*?</div>', "", html, flags=re.S
    )  # SDP's own section titles
    for n in SDP_PROSE:
        m = re.search(r'id="%s">\[%s\]</a>(.*?)<a name="\d{4}[a-c]\d{2}"' % (n, n), html, re.S)
        assert m, n
        sdp = strip_punct(re.sub(r"<[^>]+>", "", m.group(1)))
        assert strip_punct(L[n]["text"]) == sdp, n


def test_t1723_known_lines():
    L = by_n(lines_of(raw("T1723")))
    a03 = L["0651a03"]
    assert a03["text"] == "妙法蓮華經玄贊卷第一本"
    assert a03["inline_notes"] == [(10, 11)]  # the small-print 本 of the jhead
    assert a03["heads"] == [{"kind": "jhead", "text": "妙法蓮華經玄贊卷第一本", "offset": 0}]
    assert [(m["type"], m["n"], m["text"]) for m in a03["mulu"]] == [("卷", "1a", "第一本")]
    assert a03["juan_marks"] == [{"fun": "open", "n": "001a", "offset": 0}]
    a06 = L["0651a06"]
    assert a06["text"] == "蓋聞至覺權真乘物機而誕跡，靈樞擅"
    assert [(m["level"], m["type"], m["text"]) for m in a06["mulu"]] == [
        (1, "品", "序品"),
        (2, None, "1"),
    ]
    assert L["0651a13"]["text"] == "妙藥，藻掞眾筌之表，\U000285c9軼百宗之外，籠七"
    assert L["0651a13"]["gaiji"] == [{"offset": 10, "ref": "CB04584", "via": "unicode"}]
    assert L["0651b07"]["text"] == "請中有二：一酬因，二酬請。初酬因有六："
    # PUA text in the XML, charDecl has only normal_unicode U+9EA8
    assert L["0655b01"]["text"] == "賈人獻佛\u9ea8蜜，佛與授記：汝於來世當得"
    assert L["0655b01"]["gaiji"] == [{"offset": 4, "ref": "CB00595", "via": "normal_unicode"}]
    # no unicode / normalized form at all -> stable placeholder
    assert "[#CB04599]" in L["0757b16"]["text"]
    # an inline note that runs across lb 0669c24: split into per-line spans
    assert L["0669c23"]["inline_notes"] == [(13, 23)]
    assert L["0669c24"]["inline_notes"] == [(0, len(L["0669c24"]["text"]))]
    # juan 2 starts with the milestone before lb 0671c15
    assert L["0671c14"]["juan"] == 1 and L["0671c15"]["juan"] == 2


def test_x0268_alt_lineheads_and_kepan():
    L = by_n(lines_of(raw("X0268")))
    assert L["0165a02"]["alt"] == []
    assert L["0165a03"]["alt"] == [{"ed": "R017", "n": "0001a01", "offset": 0}]
    assert L["0165a03"]["text"] == " 楞嚴集註序"
    assert L["0165a02"]["heads"][0]["text"] == "No. 268-A 楞嚴集註序"
    m = L["0360a17"]["mulu"]
    assert [(x["level"], x["type"]) for x in m] == [(10, "科判"), (11, "科判")]
    assert L["0360a17"]["alt"] == [{"ed": "R017", "n": "0201a17", "offset": 0}]


def test_x0281_interlinear_kepan_notes_are_recorded():
    # X12n0281 楞嚴經圓通疏 has no 科判-typed cb:mulu; its 科 are interlinear notes, kept out of the
    # text but recorded in excluded_notes where they sit (right after each ○)
    lines = lines_of(raw("X0281"))
    L = by_n(lines)
    assert not any(m["type"] == "科判" for r in lines for m in r["mulu"])
    assert sum(len(r["excluded_notes"]) for r in lines) == 2123
    a24 = L["0697a24"]
    assert a24["linehead"] == "X12n0281_p0697a24"
    assert a24["text"] == "○如是。○我聞。○一時。○佛。○在室羅筏城祇桓精"
    assert [(x["offset"], x["text"]) for x in a24["excluded_notes"]] == [
        (1, "初、序，分二：初、通序六：初、指法體。"),
        (5, "二、顯能聞"),
        (9, "三，明機感"),
        (13, "四稱化主"),
        (16, "五述住處"),
    ]
    assert all(x["place"] == "interlinear" and x["type"] is None for x in a24["excluded_notes"])
    assert all(a24["text"][x["offset"] - 1] == "○" for x in a24["excluded_notes"])
    # the labels are not reading text
    assert "顯能聞" not in "".join(r["text"] for r in lines[:200])
    # a note running over lb 0754a01 is recorded once, on the line where it starts
    c24, a01 = L["0753c24"], L["0754a01"]
    assert c24["excluded_notes"][-1] == {
        "offset": len(c24["text"]),
        "place": "interlinear",
        "type": None,
        "text": "云云",
    }
    assert a01["excluded_notes"] == [] and a01["text"].startswith("。此中對辯")


# -------------------------------------------------------------------------------- works/toc oracle


def toc_nodes(path: Path):
    res = json.loads(path.read_text(encoding="utf-8"))["results"][0]
    out = []

    def walk(nodes, depth):
        for n in nodes:
            out.append((n.get("title"), n.get("lb"), depth, n.get("type"), n.get("juan")))
            walk(n.get("children") or [], depth + 1)

    walk(res["mulu"], 1)
    return out, [(j["juan"], j["lb"], j["title"]) for j in res["juan"]]


def toc_json(work: str) -> Path:
    for p in (
        FIX / "cbeta-api" / ("works-toc-%s.json" % work),
        RAW / "cbeta-api" / ("works-toc-%s.json" % work),
    ):
        if p.exists():
            return p
    pytest.skip("works/toc JSON for %s not fetched (scripts/fetch_cbeta_api.sh)" % work)


# Known API-side difference: toc.rake drops the gaiji of X0268's
# 初以金<g ref="#CB01926">灰</g>喻 (U+2F835).
TOC_EXCEPTIONS = {("X0268", "0360a17"): ("初以金\U0002f835喻", "初以金喻")}


@pytest.mark.parametrize(
    "work,count",
    [("T0262", 33), ("T1723", 38), ("T1718", 43), ("T1602", 32), ("T1605", 18), ("X0268", 2637)],
)
def test_mulu_tree_matches_works_toc(work, count):
    want, want_juan = toc_nodes(toc_json(work))
    lines = lines_of(raw(work))
    got = [
        (m["text"], r["n"], m["level"], m["type"], r["juan"])
        for r in lines
        for m in r["mulu"]
        if m["type"] != "卷"
    ]
    assert len(want) == count
    assert len(got) == len(want)
    # titles in order (the works/toc oracle, tests/fixtures/cbeta-api/README.md), and lb, depth, type,
    # juan equal as well; the only tolerated differences are the API-side ones listed in TOC_EXCEPTIONS
    diffs = [(g, w) for g, w in zip(got, want) if g != w]
    for g, w in diffs:
        assert TOC_EXCEPTIONS.get((work, g[1])) == (g[0], w[0]), (g, w)
        assert g[1:] == w[1:]
    assert len(diffs) == sum(1 for k in TOC_EXCEPTIONS if k[0] == work)
    # the 卷 system: one API juan entry per 卷 mulu, same line and juan number, same label when
    # CBETA gives one
    juans = [(r["juan"], r["n"], m["text"]) for r in lines for m in r["mulu"] if m["type"] == "卷"]
    assert [(j, lb) for j, lb, _ in juans] == [(j, lb) for j, lb, _ in want_juan]
    assert all(t == wt for (_, _, t), (_, _, wt) in zip(juans, want_juan) if t)


# ----------------------------------------------------------------------------- text index and find


def test_index_roundtrip_and_find_on_fixture():
    lines = lines_of(G1977)
    idx = build_index(lines)
    assert idx.text == "".join(r["text"] for r in lines)
    for r in lines:
        assert idx.line_text(r["linehead"]) == r["text"]
    for g in range(len(idx.text) + 1):
        assert idx.global_offset(*idx.locate(g)) == g
    a03, a04 = "G069n1977_p0717a03", "G069n1977_p0717a04"
    # a boundary offset belongs to the next line
    assert idx.locate(idx.global_offset(a04, 0)) == (a04, 0)
    assert find(idx, "夫三諦者") == [(a03, 0)]
    # a quotation running across a line break is found and anchored at its first character
    n03 = len(idx.line_text(a03))
    assert find(idx, "俗諦者立一切法") == [(a03, n03 - 3)]
    assert find_spans(idx, "俗諦者立一切法") == [
        {"start": (a03, n03 - 3), "end": (a04, 4), "text": "俗諦者立一切法"}
    ]
    # punctuation-insensitive lemma matching
    assert find(idx, "天然之性德也中諦者") == []
    assert find(idx, "天然之性德也中諦者", ignore_punct=True) == [(a03, 5)]
    assert find(idx, "天然之性德也，中諦者。", ignore_punct=True) == [(a03, 5)]
    sp = find_spans(idx, "天然之性德也中諦者", ignore_punct=True)
    assert sp[0]["text"] == "天然之性德也。中諦者"
    # overlapping hits are all reported
    assert len(find(idx, "三")) == idx.text.count("三")
    # a sub-range
    sub = build_index(lines, start="G069n1977_p0718a01", end="G069n1977_p0718a02")
    assert sub.lineheads == ["G069n1977_p0718a01", "G069n1977_p0718a02"]
    assert find(sub, "三惑") == [("G069n1977_p0718a02", 2)]
    with pytest.raises(KeyError):
        build_index(lines, start="G069n1977_p9999a01")
    with pytest.raises(ValueError):
        idx.global_offset(a03, n03 + 1)


def test_index_find_on_t0262():
    lines = lines_of(raw("T0262"))
    idx = build_index(lines)
    c19, c20, c21 = ("T09n0262_p0001c%s" % x for x in ("19", "20", "21"))
    n20 = len(idx.line_text(c20))
    assert find(idx, "諸漏已盡") == [(c20, n20 - 2)]
    assert find_spans(idx, "諸漏已盡")[0]["end"] == (c21, 2)
    assert (c19, 0) not in find(idx, "如是我聞一時")
    assert (c19, 0) in find(idx, "如是我聞一時", ignore_punct=True)
    # empty lines (0001c12, 0001c13) never own an offset: their start maps to the next line
    # with text
    g = idx.global_offset("T09n0262_p0001c12", 0)
    assert idx.locate(g) == ("T09n0262_p0001c14", 0)
    # a range across the 附文 jump is taken in document order
    sub = build_index(lines, start="T09n0262_p0056c01", end="T09n0262_p0056c02")
    assert sub.lineheads[0] == "T09n0262_p0056c01" and sub.lineheads[1] == "T09n0262_p0198a10"


# --------------------------------------------------------------------------------------------- CLI


def test_cli_tsv_and_jsonl(capsys):
    assert main([str(G1977), "--tsv"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 17
    assert out[0] == "G069n1977_p0717a01\t1\t始終心要"
    assert main([str(G1977)]) == 0
    recs = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [r["linehead"] for r in recs] == [r["linehead"] for r in lines_of(G1977)]
    assert main([str(G1977), "--find", "天然之性德也中諦者", "--ignore-punct"]) == 0
    assert capsys.readouterr().out == "G069n1977_p0717a03\t5\n"


def test_python_m_entrypoint():
    env = dict(os.environ)
    src = str(REPO / "pipeline" / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(
        [
            sys.executable,
            "-W",
            "error::RuntimeWarning",
            "-m",
            "chinese_workflow.ingest.lines",
            str(G1977),
            "--tsv",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[-1] == "G069n1977_p0718a06\t1\t始終心要竟"


def test_package_exports():
    from chinese_workflow import ingest

    assert ingest.iter_lines is iter_lines
    assert ingest.find is find
