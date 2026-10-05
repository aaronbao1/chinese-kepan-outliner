"""Checks the labelled cases for the tier-2 explicit-division parser
(tests/fixtures/kepan-formulae/cases.jsonl, documented in that directory's README.md) and the two
CBETA XML excerpts committed for offline parser smoke tests
(tests/fixtures/cbeta-xml-p5/*-excerpt-*.xml).

Always run (no data/raw/ needed): JSONL schema, unique ids, known formula slugs, the shape of
`expected`, labels/heading/lemma/anaphor verbatim in `text` and the checkable parts of the
README label rule, coverage minima, Global Constraint 5 on each case's start linehead, and the
excerpts: size, header, parse with ingest.lines, T1723 excerpt inside the dev span.

Run when the raw XML is present (skip otherwise; data/raw/ is gitignored, see
scripts/fetch_cbeta.sh and scripts/fetch_cbeta_xml_p5.sh): every `text` occurs
punctuation-insensitively starting within +-1 line of its `linehead`; T1718/T1723 cases also end
inside the dev span; no case shares more than SHARED_RUN_MAX consecutive characters with the
T1718 validation/test or T1723 test spans, and no case from another text is a verbatim copy of
T1718/T1723 text outside the dev span (sub-commentaries such as T1724 quote T1723); T1718/T1723 lineheads are monotonic (so
the string comparison used for the split check is document order); each excerpt is byte-for-byte
the documented cut of its raw file (so its CBETA header is intact) and its lines equal the raw
file's lines.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import pytest
from lxml import etree

from chinese_workflow.eval import registry
from chinese_workflow.ingest.lines import build_index, extract, find_spans, strip_punct

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures"
CASES_PATH = FIX / "kepan-formulae" / "cases.jsonl"
README = FIX / "kepan-formulae" / "README.md"
XML_FIX = FIX / "cbeta-xml-p5"
RAW = REPO / "data" / "raw" / "cbeta"
TEI = "{http://www.tei-c.org/ns/1.0}"

# Global Constraint 5, read from its single source of truth data/eval-sets.json ("splits"; human
# guide data/EVAL-SETS.md). Spans are CBETA lineheads, [start, end); end None = to the end of the
# file. In T1718 and T1723 only DEV may be quoted by a case or a fixture; the rest is validation,
# test or reserve (reserve: T1718 from p0063b11 to the end, T1723 everything outside the spans
# listed). Other texts are unrestricted.
REG = registry.load_registry()


def load_splits(reg: dict = REG) -> tuple[dict, dict]:
    """(SPLITS, SPLIT_FILES) from the registry module: {text: [(split, start, end)]}, {text: file id}."""
    texts = registry.split_texts(reg)
    splits = {t: registry.split_spans(reg, t) for t in texts}
    return splits, {t: spec["file"] for t, spec in texts.items()}


SPLITS, SPLIT_FILES = load_splits()

# Formula slugs (README.md gives the row text and sources for each).
R01_ROWS = {  # R01's formula table; rows in tests/fixtures/kepan-formulae/README.md
    "wen-wei-n",
    "fen-wei-n-cong-zhi",
    "jiu-you-n",
    "jiu-zhong",
    "jiu-kai-wen-wei-n",
    "zhong-you-n",
    "chu-zhong-yi-n",
    "ordinal-lemma-xia",
    "wen-you-n-fen",
    "zhong-you-n-ju",
    "da-fen-wei-n",
    "wen-bie-you-n",
    "cong-xia-zhi-fen",
    "zong-you-n-fen",
    "shuo-you-n-fen",
    "fan-you-n-duan",
    "chart-note",
    "uddana",
}
KUIJI_VARIANTS = {  # R07 F17 / R03 F25 variants not already covered by an R01 row
    "men-fenbie",
    "men-liaojian",
    "fen-n",
    "you-n",
    "zanyue-lemma",
    "fen-wei-n",
    "zixia-di-n",
    "ci-zhong",
}
TREATISE_VARIANTS = {  # self-outlining idioms: T1602 take-ups (E06 review B4), T1666 take-up / deferred count (E06 B7)
    "lun-zhe-wei-ru-you-yi",
    "you-n-takeup",
    "you-n-deferred",
}
SHANDAO_IDIOMS = {  # 善導 (T1753, E06 review B3)
    "jiu-x-zhong",
    "cong-xia-zhi-lai",
    "ming-x-jing",
}
ZHIYI_DEVICES = {  # E06 review §1 item 2 / B6: Zhiyi's non-formulaic take-up device (T1718 dev)
    "lemma-zhe",
}
SLUGS = R01_ROWS | KUIJI_VARIANTS | TREATISE_VARIANTS | SHANDAO_IDIOMS | ZHIYI_DEVICES
GENRE_GATE_SOURCES = {"T1775"}  # 註 genre (R07 F2)

KINDS = {"division": "pos", "not-division": "neg", "genre-gate": "gate", "close": "close"}
FIELDS = {"id", "kind", "formula", "source", "linehead", "text", "expected", "why"}
OPTIONAL_FIELDS = {"mode"}  # "self-outlining": the detectors run in that mode (default "sutra")
EXPECTED_REQUIRED = {"child_count", "labels", "anaphor"}
EXPECTED_OPTIONAL = {"heading", "ordinal", "lemma", "applies_to", "anaphor_path", "opens"}
LINEHEAD_RE = re.compile(
    r"^([A-Z]{1,2})([0-9]{2,3})n([0-9A-Za-z]{4,5})_p[0-9a-z][0-9]{3}[a-z][0-9]{2}$"
)
YOU_N_RE = re.compile(r"有[二三四五六七八九十]")
# Label rule (README "Labels"): a label or heading is a verbatim, contiguous piece of `text`; the
# ordinal word, locator, copula, a final 也 and edge punctuation are removed from it.
ORDINAL_START_RE = re.compile(
    r"^(第[一二三四五六七八九十]+|[一二三四五六七八九十]+[、．者]|[初次後先餘][、，])"
)
EDGE_PUNCT = set("，、；：。．？！「」『』〈〉《》（）")
# Global Constraint 5 guard: no case shares more than this many consecutive characters
# (punctuation ignored) with the T1718 validation/test or T1723 test spans.
SHARED_RUN_MAX = 8

# file: (xml:id, first linehead, last linehead, raw source, raw file line ranges kept verbatim).
# Recipe (tests/fixtures/cbeta-xml-p5/README.md): the listed 1-based inclusive line ranges of the
# raw file, then the two lines "</body>" and "</text></TEI>" and a final newline. The first range
# is the whole teiHeader plus "<text><body>" (CBETA: "distributed with this header intact").
EXCERPTS = {
    "T34n1723-excerpt-p0850a19-p0850b19.xml": (
        "T34n1723",
        "T34n1723_p0850a19",
        "T34n1723_p0850b19",
        RAW / "T34n1723.xml",
        [(1, 1562), (19727, 19758)],
    ),
    "T09n0262-excerpt-p0058b08-p0059b27.xml": (
        "T09n0262",
        "T09n0262_p0058b08",
        "T09n0262_p0059b27",
        RAW / "T09n0262.xml",
        [(1, 447), (5649, 5743)],
    ),
}


def excerpt_from_raw(raw: Path, ranges: list) -> bytes:
    lines = raw.read_text(encoding="utf-8").split("\n")
    out = [ln for a, b in ranges for ln in lines[a - 1 : b]]
    return "\n".join(out + ["</body>", "</text></TEI>", ""]).encode("utf-8")


def load_cases() -> list:
    with CASES_PATH.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


CASES = load_cases()


def stem_of(linehead: str) -> str:
    return linehead.split("_p")[0]


def split_of(source: str, linehead: str) -> str:
    """Split of a T1718/T1723 linehead (string order = document order, see
    test_split_files_are_monotonic); 'reserve' when no listed span holds it (the registry's
    `unlisted`, which tests/unit/test_gold_registry.py pins to reserve)."""
    return registry.split_of(REG, source, linehead)


def raw_xml(stem: str) -> Path | None:
    canon, vol = re.match(r"([A-Z]+)(\d+)", stem).groups()
    for p in (RAW / f"{stem}.xml", RAW / "xml-p5" / canon / (canon + vol) / f"{stem}.xml"):
        if p.exists():
            return p
    return None


_LINES: dict = {}
_INDEX: dict = {}


def lines_of(path: Path) -> list:
    if path not in _LINES:
        _LINES[path] = extract(path).lines
    return _LINES[path]


def index_of(path: Path):
    if path not in _INDEX:
        lines = lines_of(path)
        _INDEX[path] = (build_index(lines), {r["linehead"]: i for i, r in enumerate(lines)})
    return _INDEX[path]


def raw_or_skip(case: dict) -> Path:
    p = raw_xml(stem_of(case["linehead"]))
    if p is None:
        pytest.skip(f"raw XML for {case['source']} not fetched (scripts/fetch_cbeta*.sh)")
    return p


# ------------------------------------------------------------------------- always: schema, rules


def test_cases_file_is_jsonl_with_unique_ids():
    assert len(CASES) >= 50
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)), sorted(i for i in ids if ids.count(i) > 1)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_case_schema(case):
    assert FIELDS <= set(case) <= FIELDS | OPTIONAL_FIELDS
    assert case.get("mode", "sutra") in ("sutra", "self-outlining")
    kind, formula = case["kind"], case["formula"]
    assert kind in KINDS
    assert formula in SLUGS or (formula is None and kind == "genre-gate")
    tail = formula if formula else case["source"].lower()
    assert re.fullmatch(rf"{KINDS[kind]}-{re.escape(tail)}-\d{{2}}", case["id"]), case["id"]
    m = LINEHEAD_RE.match(case["linehead"])
    assert m, case["linehead"]
    assert case["source"] == m.group(1) + m.group(3), (case["source"], case["linehead"])
    text = case["text"]
    assert isinstance(text, str) and text.strip() == text and text and "\n" not in text
    assert strip_punct(text[:1]) == text[:1], "text must not start with punctuation"
    assert isinstance(case["why"], str) and case["why"] and "\n" not in case["why"]
    if kind == "genre-gate":
        assert case["source"] in GENRE_GATE_SOURCES


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_expected_shape(case):
    exp = case["expected"]
    if case["kind"] == "close":  # 善導's 廣明X竟: {close: X}, X verbatim in the text
        assert set(exp) == {"close"} and exp["close"] and exp["close"] in case["text"]
        return
    if case["kind"] != "division":
        assert exp is None
        return
    assert isinstance(exp, dict)
    assert EXPECTED_REQUIRED <= set(exp) <= EXPECTED_REQUIRED | EXPECTED_OPTIONAL
    n, labels, anaphor = exp["child_count"], exp["labels"], exp["anaphor"]
    assert isinstance(labels, list) and all(isinstance(s, str) and s for s in labels)
    if n is None:  # a heading-type statement: opens one node, announces no children
        assert labels == [] and exp.get("heading")
    else:
        assert isinstance(n, int) and n >= 2
        if labels:
            assert len(labels) == n
    assert anaphor is None or (isinstance(anaphor, str) and anaphor)
    if exp.get("ordinal") is not None:  # null: no ordinal is written (次下先就上品上生位中)
        assert isinstance(exp["ordinal"], int) and exp["ordinal"] >= 1
    assert "opens" not in exp or exp["opens"] is False  # only the false form is written
    for key in ("applies_to", "anaphor_path"):
        if key in exp:
            path = exp[key]
            assert (
                isinstance(path, list) and path and all(isinstance(i, int) and i >= 1 for i in path)
            )
    if "anaphor_path" in exp:
        assert anaphor and exp["anaphor_path"] != [1]  # [1] is the default: omit it
    text = case["text"]
    assert anaphor is None or anaphor in text, anaphor
    lemma = exp.get("lemma")
    # 善導's unbracketed span 從A下，至B已來 has the lemma A至B: A and B are verbatim, the 至 between them is not
    for s in (lemma.split("至") if lemma and case["formula"] == "cong-xia-zhi-lai" else [lemma]):
        assert s is None or s in text, s
    names = labels + ([exp["heading"]] if exp.get("heading") else [])
    for s in names:
        assert s in text, s
        assert s[0] not in EDGE_PUNCT and s[-1] not in EDGE_PUNCT, s
        assert not s.endswith("也"), s
        assert not ORDINAL_START_RE.match(s), s


def test_coverage_minima():
    pos = [c for c in CASES if c["kind"] in ("division", "close")]  # a close case is the positive of ming-x-jing
    for slug in sorted(SLUGS):
        n = sum(1 for c in pos if c["formula"] == slug)
        assert n >= 2, f"{slug} has {n} positives"
    you_n_neg = [c for c in CASES if c["kind"] == "not-division" and YOU_N_RE.search(c["text"])]
    assert len(you_n_neg) >= 15
    assert sum(1 for c in CASES if c["kind"] == "genre-gate") >= 3


def test_readme_documents_every_slug():
    text = README.read_text(encoding="utf-8")
    for slug in sorted(SLUGS):
        assert f"`{slug}`" in text, slug


def test_split_spans_do_not_overlap():
    for source, spans in SPLITS.items():
        closed = sorted((s, e) for _, s, e in spans if e is not None)
        for (s1, e1), (s2, e2) in itertools.pairwise(closed):
            assert s1 < e1 <= s2 < e2, (source, s1, e1, s2, e2)


@pytest.mark.parametrize("case", [c for c in CASES if c["source"] in SPLITS], ids=lambda c: c["id"])
def test_case_starts_in_dev_span(case):
    assert stem_of(case["linehead"]) == SPLIT_FILES[case["source"]]
    assert split_of(case["source"], case["linehead"]) == "dev", case["linehead"]


def test_split_of_examples():
    assert split_of("T1718", "T34n1718_p0016b01") == "dev"
    assert split_of("T1718", "T34n1718_p0016b02") == "validation"
    assert split_of("T1718", "T34n1718_p0149a29") == "reserve"
    assert split_of("T1723", "T34n1723_p0850a18") == "reserve"
    assert split_of("T1723", "T34n1723_p0850b19") == "dev"
    assert split_of("T1723", "T34n1723_p0850b20") == "reserve"
    assert split_of("T1723", "T34n1723_p0735a01") == "test"


# ------------------------------------------------------------------------ always: XML excerpts


@pytest.mark.parametrize("name", sorted(EXCERPTS))
def test_excerpt_is_small_well_formed_with_header(name):
    path = XML_FIX / name
    xml_id, first, last, _, _ = EXCERPTS[name]
    data = path.read_bytes()
    header_end = data.index(b"</teiHeader>") + len(b"</teiHeader>")
    # < 50 KB of excerpted text; the header is carried whole (T1723's alone is 56,505 bytes).
    assert len(data) - header_end < 50_000 and len(data) < 64 * 1024
    root = etree.parse(str(path)).getroot()
    assert root.get("{http://www.w3.org/XML/1998/namespace}id") == xml_id
    assert root.find(TEI + "teiHeader/" + TEI + "fileDesc") is not None
    ex = extract(path)
    assert not ex.unanchored
    lhs = [r["linehead"] for r in ex.lines]
    assert lhs[0] == first and lhs[-1] == last
    assert len(lhs) == len(set(lhs))
    mulu = [m for r in ex.lines for m in r["mulu"]]
    assert [m["type"] for m in mulu] == ["品"] and "陀羅尼品" in mulu[0]["text"]
    if xml_id == "T34n1723":
        assert all(split_of("T1723", lh) == "dev" for lh in lhs)


def test_cbeta_fixture_readme_lists_excerpts():
    text = (XML_FIX / "README.md").read_text(encoding="utf-8")
    for name in EXCERPTS:
        assert f"`{name}`" in text, name


# ---------------------------------------------------------------------------- when raw present


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_text_occurs_at_linehead(case):
    path = raw_or_skip(case)
    idx, pos = index_of(path)
    i = pos[case["linehead"]]
    spans = find_spans(idx, case["text"], ignore_punct=True)
    near = [s for s in spans if abs(pos[s["start"][0]] - i) <= 1]
    assert near, f"{case['text']} not found within +-1 line of {case['linehead']}"
    if case["source"] in SPLITS:  # the whole text, not only its start, lies in the dev span
        for s in near:
            assert split_of(case["source"], s["start"][0]) == "dev"
            assert split_of(case["source"], s["end"][0]) == "dev"


def _outside_dev_text() -> str:
    parts = []
    for source, stem in SPLIT_FILES.items():
        p = raw_xml(stem)
        if p is None:
            pytest.skip(f"raw {stem} not fetched")
        parts += [r["text"] for r in lines_of(p) if split_of(source, r["linehead"]) != "dev"]
        parts.append("\x00")
    return strip_punct("".join(parts))


def test_no_long_run_shared_with_validation_or_test():
    parts = []
    for source, stem in SPLIT_FILES.items():
        p = raw_xml(stem)
        if p is None:
            pytest.skip(f"raw {stem} not fetched")
        held_out = [
            r["text"]
            for r in lines_of(p)
            if split_of(source, r["linehead"]) in ("validation", "test")
        ]
        parts.append(strip_punct("".join(held_out)))
    held = "\x00".join(parts)
    n = SHARED_RUN_MAX + 1
    for c in CASES:
        t = strip_punct(c["text"])
        shared = [t[i : i + n] for i in range(len(t) - n + 1) if t[i : i + n] in held]
        assert not shared, (c["id"], shared[0])


def test_other_texts_do_not_copy_split_text():
    forbidden = _outside_dev_text()
    for c in CASES:
        if c["source"] not in SPLITS:
            assert strip_punct(c["text"]) not in forbidden, c["id"]


@pytest.mark.parametrize("source", sorted(SPLIT_FILES))
def test_split_files_are_monotonic(source):
    p = raw_xml(SPLIT_FILES[source])
    if p is None:
        pytest.skip(f"raw {SPLIT_FILES[source]} not fetched")
    lhs = [r["linehead"] for r in lines_of(p)]
    assert all(a < b for a, b in itertools.pairwise(lhs))


@pytest.mark.parametrize("name", sorted(EXCERPTS))
def test_excerpt_is_the_documented_cut_of_raw(name):
    _, _, _, raw, ranges = EXCERPTS[name]
    if not raw.exists():
        pytest.skip(f"{raw.name} not fetched")
    assert (XML_FIX / name).read_bytes() == excerpt_from_raw(raw, ranges)


@pytest.mark.parametrize("name", sorted(EXCERPTS))
def test_excerpt_lines_equal_raw(name):
    _, first, last, raw, _ = EXCERPTS[name]
    if not raw.exists():
        pytest.skip(f"{raw.name} not fetched")
    full = lines_of(raw)
    lhs = [r["linehead"] for r in full]
    run = full[lhs.index(first) : lhs.index(last) + 1]
    keys = ("linehead", "text", "inline_notes", "excluded_notes", "gaiji", "mulu", "heads")
    got = [{k: r[k] for k in keys} for r in extract(XML_FIX / name).lines]
    assert got == [{k: r[k] for k in keys} for r in run]
