"""Checks the eval-set registry data/eval-sets.json (guide data/EVAL-SETS.md) against its files.

Always run (committed material only):
  * registry shape: unique ids, known kinds / formats, each dataset split-scoped, given one split
    or following another dataset's; the out-of-domain list consistent with the datasets;
  * split spans (the single source of truth for Global Constraint 5): well-formed lineheads of
    the named file, start < end, no overlap, only the last span open-ended, `unlisted` = reserve
    (what test_kepan_cases.py assumes); eval.gold.sdp_check's own T1718 SPLITS agree with them;
  * committed datasets exist and are not gitignored; eval-only datasets sit under data/raw/ and
    are gitignored (`git check-ignore`); a gold's eval_only matches where it lives;
  * every gold under data/reference-outlines/ is registered;
  * each committed gold validates with scripts/validate_outline.py (no errors) and its computed
    blocks (`file_metadata`, `counts`) equal what chinese_workflow.eval.registry (the module behind
    scripts/eval_sets.py) computes from it now; same for committed fixtures; the generated tables of
    data/EVAL-SETS.md equal a fresh rendering; a dataset's `scoring_scope` equals its derivation
    from the registry's juan_halves, and in_scoring_scope follows it;
  * the Kuiji gold's metadata.coverage_spans lie inside the registry's split spans; the zh schema
    types coverage / coverage_spans / split_notes (optional) and rejects malformed ones.
Run when data/raw/ is present (skip otherwise): the eval-only sdp golds validate and match their
recorded blocks (the heading check and crosswalk too); every sdp gold on disk is registered; the
T1718 卷-half table matches the XML and the served sdp HTML files; every split linehead is a line
of its raw file; every explained line of the T1718 sdp gold is in its scoring scope. (No sdp heading in the registry, its guide or any other tracked file:
tests/unit/test_sdp_eval_only_guard.py, Global Constraint 1.)
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from chinese_workflow.eval import registry

REPO = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO / "data" / "eval-sets.json"
GUIDE_PATH = REPO / "data" / "EVAL-SETS.md"
RAW = REPO / "data" / "raw"
KINDS = {"gold", "gold-aux", "parser-cases", "fixture"}
FORMATS = {
    "zh-kepan-outline",
    "heading-check",
    "crosswalk-tsv",
    "cases-jsonl",
    "tei-xml-excerpt",
    "aligned-text",
}
SPLIT_NAMES = {"dev", "validation", "test", "reserve"}
FIXED_SPLITS = SPLIT_NAMES | {"out-of-domain"}
LINEHEAD_RE = re.compile(
    r"^([A-Z]{1,2}[0-9]{2,3}n[0-9A-Za-z]{4,5})_p[0-9a-z][0-9]{3}[a-z][0-9]{2}$"
)


def _load_script(name: str):
    """A scripts/*.py file imported as a module (scripts/ is not a package)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


ES = registry  # chinese_workflow.eval.registry; scripts/eval_sets.py is a thin wrapper over it
REG = ES.load_registry(REGISTRY_PATH)
DATASETS = REG["datasets"]
BY_ID = {d["id"]: d for d in DATASETS}
TEXTS = REG["splits"]["texts"]
GOLDS = [d for d in DATASETS if d["format"] == "zh-kepan-outline"]
COMMITTED = [d for d in DATASETS if d["committed"]]
EVAL_ONLY = [d for d in DATASETS if not d["committed"]]


def _paths(ds: dict) -> list:
    return [ds["path"], *ds.get("extra_paths", [])]


def _git(*args: str) -> subprocess.CompletedProcess | None:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        return None
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


@pytest.fixture(scope="module")
def vo():
    return _load_script("validate_outline")


# ----------------------------------------------------------------------------------- registry shape


def test_registry_shape():
    ids = [d["id"] for d in DATASETS]
    assert len(ids) == len(set(ids)), ids
    for ds in DATASETS:
        assert ds["kind"] in KINDS, ds["id"]
        assert ds["format"] in FORMATS, ds["id"]
        assert isinstance(ds["committed"], bool), ds["id"]
        for p in _paths(ds):
            assert not Path(p).is_absolute() and ".." not in Path(p).parts, (ds["id"], p)
        experiments = ds.get("experiments") or []
        assert experiments and all(e["id"] and e["role"] for e in experiments), ds["id"]
        assert ds.get("licence") or ds.get("licence_id"), ds["id"]
        assert "counts" in ds and ds["counts"], (
            f"{ds['id']}: run python3 scripts/eval_sets.py --write"
        )
        scope, split, follows = ds.get("split_scope"), ds.get("split"), ds.get("split_follows")
        assert sum(x is not None for x in (scope, split, follows)) == 1, (
            f"{ds['id']}: give exactly one of split_scope, split, split_follows"
        )
        if scope:
            assert scope["text"] in TEXTS, ds["id"]
            assert ds["format"] == "zh-kepan-outline", ds["id"]
        elif follows:
            assert ds["kind"] == "gold-aux" and BY_ID[follows].get("split_scope"), ds["id"]
        else:
            assert split in FIXED_SPLITS, (ds["id"], split)
    for ds in GOLDS:
        assert ds.get("anchors") in {
            "commentary",
            "root",
            "commentary+root",
            "self",
            "structure-only",
        }, ds["id"]
        assert "licence_id" not in ds, (
            f"{ds['id']}: a gold's licence id is mirrored from the file (file_metadata)"
        )


def test_out_of_domain_list_matches_datasets():
    listed = set(REG["splits"]["out_of_domain"]["datasets"])
    assert listed == {d["id"] for d in DATASETS if d.get("split") == "out-of-domain"}


# -------------------------------------------------------------------------------------- split spans


@pytest.mark.parametrize("text", sorted(TEXTS))
def test_split_spans_well_formed(text):
    spec = TEXTS[text]
    # tests/unit/test_kepan_cases.py split_of() returns "reserve" for an unlisted line
    assert spec["unlisted"] == "reserve"
    spans = spec["spans"]
    assert spans
    for i, span in enumerate(spans):
        assert span["split"] in SPLIT_NAMES and span.get("label"), span
        for key in ("start", "end"):
            lh = span[key]
            if key == "end" and lh is None:
                assert i == len(spans) - 1, "only the last span may be open-ended"
                continue
            m = LINEHEAD_RE.match(lh)
            assert m and m.group(1) == spec["file"], (text, lh)
        assert span["end"] is None or span["start"] < span["end"], span


@pytest.mark.parametrize("text", sorted(TEXTS))
def test_split_spans_do_not_overlap(text):
    spans = sorted((s["start"], s["end"]) for s in TEXTS[text]["spans"])
    for (s1, e1), (s2, e2) in itertools.pairwise(spans):
        assert e1 is not None and e1 <= s2, (text, s1, e1, s2, e2)


def test_split_of_examples():
    assert ES.split_of(REG, "T1718", "T34n1718_p0016b01") == "dev"
    assert ES.split_of(REG, "T1718", "T34n1718_p0016b02") == "validation"
    assert ES.split_of(REG, "T1718", "T34n1718_p0063b11") == "reserve"
    assert ES.split_of(REG, "T1718", "T34n1718_p0001a04") == "reserve"  # the preface, before dev
    assert ES.split_of(REG, "T1723", "T34n1723_p0850b19") == "dev"
    assert ES.split_of(REG, "T1723", "T34n1723_p0850b20") == "reserve"
    assert ES.split_of(REG, "T1723", "T34n1723_p0737b04") == "reserve"


def test_sdp_check_splits_agree_with_registry():
    from chinese_workflow.eval.gold import sdp_check

    closed = [span for span in ES.split_spans(REG, "T1718") if span[2] is not None]
    assert list(sdp_check.SPLITS) == closed


def test_kepan_cases_read_the_registry():
    """tests/unit/test_kepan_cases.py takes its spans from the registry module (one source of truth)."""
    text = (REPO / "tests" / "unit" / "test_kepan_cases.py").read_text(encoding="utf-8")
    assert "from chinese_workflow.eval import registry" in text
    assert not re.search(r"\(\s*\"dev\",\s*\"T34n", text), "split spans hard-coded again"


def test_script_is_a_thin_wrapper_over_the_module():
    script = _load_script("eval_sets")
    assert script.main is ES.main
    assert len((REPO / "scripts" / "eval_sets.py").read_text(encoding="utf-8").splitlines()) < 40


def test_dataset_lookup_and_split_spans():
    assert ES.dataset(REG, "kuiji-xuanzan")["path"].endswith("kuiji-xuanzan/outline.json")
    with pytest.raises(KeyError):
        ES.dataset(REG, "no-such-dataset")
    assert ES.split_spans(REG, "T1723")[0] == ("dev", "T34n1723_p0850a19", "T34n1723_p0850b20")


def test_t1718_scoring_scope_is_the_served_juan_halves():
    """R2 (final review): the T1718 sdp gold's machine-readable scope = the 卷-halves sdp serves,
    computed from splits.texts.T1718.juan_halves (end exclusive)."""
    ds = BY_ID["sdp-T1718-zhiyi-wenju"]
    scope = ds["scoring_scope"]
    assert scope == ES.computed_scoring_scope(REG, ds)
    assert scope["key"] == "locations.commentary.explained" and scope["text"] == "T1718"
    halves = TEXTS["T1718"]["juan_halves"]
    assert [h["half"] for h in scope["served_juan_halves"]] == halves["served_by_sdp"]
    starts = list(halves["starts"].items())
    for h in scope["served_juan_halves"]:
        i = [half for half, _ in starts].index(h["half"])
        # the first half's page also serves the front matter: it opens at the file start (None)
        assert h["start"] == (None if i == 0 else starts[i][1])
        assert h["end"] == (starts[i + 1][1] if i + 1 < len(starts) else None)
    # only the T1718 gold is narrowed
    assert [d["id"] for d in DATASETS if d.get("scoring_scope")] == ["sdp-T1718-zhiyi-wenju"]
    ok = lambda lh: ES.in_scoring_scope(REG, "sdp-T1718-zhiyi-wenju", lh)
    assert ok("T34n1718_p0001b18") and ok("T34n1718_p0009b06")
    assert not ok("T34n1718_p0009b07")  # 卷一下: dev, but unserved
    assert ok("T34n1718_p0060c13") and not ok("T34n1718_p0060c14")  # the test split's unserved end
    assert ok("T34n1718_p0001a04")  # the preface, served on 卷一上's page (reserve by split)
    assert not ok(None) and not ok("T09n0262_p0001c19")
    assert ES.in_scoring_scope(REG, "sdp-T0262-zhiyi-wenju", "T09n0262_p0001c19")


def test_t1718_gold_explained_lines_are_in_its_scoring_scope():
    path = REPO / BY_ID["sdp-T1718-zhiyi-wenju"]["path"]
    if not path.exists():
        pytest.skip("sdp T1718 gold absent (eval-only, gitignored)")
    doc = json.loads(path.read_text(encoding="utf-8"))
    explained = [
        n["locations"]["commentary"]["explained"]
        for n in doc["nodes"]
        if n["locations"].get("scheme") == "cbeta-kepan"
        and (n["locations"].get("commentary") or {}).get("explained")
    ]
    assert explained
    assert all(ES.in_scoring_scope(REG, "sdp-T1718-zhiyi-wenju", lh) for lh in explained)
    # first_half_from_file_start: sdp's 卷一上 page opens on the file's first line
    page = RAW / "dila-sdp" / "T1718-juan1a.html"
    xml = RAW / "cbeta" / "T34n1718.xml"
    if page.exists() and xml.exists():
        from chinese_workflow.ingest.lines import extract

        anchors = re.findall(r'name="([0-9]{4}[a-c][0-9]{2})"', page.read_text(encoding="utf-8"))
        first_line = extract(xml).lines[0]["linehead"]
        assert "T34n1718_p" + min(anchors) == first_line


def test_kuiji_coverage_spans_inside_split_spans():
    doc = json.loads((REPO / BY_ID["kuiji-xuanzan"]["path"]).read_text(encoding="utf-8"))
    spans = TEXTS["T1723"]["spans"]
    found = {}
    for entry in doc["metadata"]["coverage_spans"]:
        if entry["node_id"] is None:  # the whole document at levels 1-2: not a split span
            continue
        start, end = entry["commentary"]["start"], entry["commentary"]["end"]  # end inclusive
        hit = [s for s in spans if s["start"] <= start and end < s["end"]]
        assert len(hit) == 1, (entry["heading_src"], start, end)
        found[entry["heading_src"]] = hit[0]["split"]
    assert found == {"序品": "test", "譬喻品": "test", "陀羅尼品": "dev"}
    notes = " ".join(doc["metadata"]["split_notes"])
    for s in spans:
        assert s["start"] in notes, s  # split_notes names every T1723 split span


# ----------------------------------------------------------------------------- where the files live


@pytest.mark.parametrize("ds", COMMITTED, ids=lambda d: d["id"])
def test_committed_datasets_exist_and_are_not_ignored(ds):
    for p in _paths(ds):
        assert (REPO / p).is_file(), p
        assert not p.startswith("data/raw/"), p
        res = _git("check-ignore", "-q", p)
        if res is None:
            pytest.skip("git not available")
        assert res.returncode == 1, (
            f"{p} is gitignored (exit {res.returncode}: {res.stderr.strip()})"
        )


@pytest.mark.parametrize("ds", EVAL_ONLY, ids=lambda d: d["id"])
def test_eval_only_datasets_are_under_raw_and_ignored(ds):
    for p in _paths(ds):
        assert p.startswith("data/raw/"), p
        res = _git("check-ignore", "-q", p)
        if res is None:
            pytest.skip("git not available")
        assert res.returncode == 0, (
            f"{p} is not gitignored (exit {res.returncode}: {res.stderr.strip()})"
        )


@pytest.mark.parametrize("ds", GOLDS, ids=lambda d: d["id"])
def test_eval_only_flag_matches_location(ds):
    meta = ds["file_metadata"]
    assert meta["outline_profile"] == "zh-kepan"
    assert meta["eval_only"] is (not ds["committed"]), ds["id"]
    if meta["licence_id"] is None:
        assert meta["eval_only"] is True and not ds["committed"]
    if ds["path"].startswith("data/reference-outlines/"):
        assert meta["eval_only"] is False


def test_every_reference_outline_is_registered():
    on_disk = {
        p.relative_to(REPO).as_posix()
        for p in (REPO / "data" / "reference-outlines").glob("*/*/outline.json")
    }
    assert on_disk
    assert on_disk <= {d["path"] for d in GOLDS}, sorted(on_disk - {d["path"] for d in GOLDS})


def test_every_sdp_gold_on_disk_is_registered():
    gold_dir = RAW / "dila-sdp" / "gold"
    if not gold_dir.is_dir():
        pytest.skip("data/raw/dila-sdp/gold/ absent (eval-only, gitignored)")
    on_disk = {p.relative_to(REPO).as_posix() for p in gold_dir.glob("*.outline.json")}
    assert on_disk <= {d["path"] for d in GOLDS}, sorted(on_disk - {d["path"] for d in GOLDS})


# ------------------------------------------------------------------- validation and computed blocks


@pytest.mark.parametrize("ds", GOLDS, ids=lambda d: d["id"])
def test_registered_gold_validates(vo, ds):
    path = REPO / ds["path"]
    if not path.exists():
        assert not ds["committed"], f"committed gold missing: {ds['path']}"
        pytest.skip(f"{ds['path']} absent (eval-only, gitignored)")
    rep = vo.validate_file(path)
    assert rep.profile == "zh-kepan"
    assert rep.passed(), [f.render() for f in rep.errors][:10]


@pytest.mark.parametrize("ds", DATASETS, ids=lambda d: d["id"])
def test_recorded_blocks_match_the_files(ds):
    got = ES.compute(ds, REG)
    if got is None:
        assert not ds["committed"], f"committed dataset missing: {ds['path']}"
        pytest.skip(f"{ds['path']} absent (eval-only, gitignored)")
    for key, value in got.items():
        assert ds.get(key) == value, (
            f"{ds['id']}.{key} is stale: run python3 scripts/eval_sets.py --write"
        )


def test_schema_types_the_coverage_metadata(vo):
    """coverage / coverage_spans / split_notes: optional, typed metadata_zh properties (D15)."""
    doc = json.loads((REPO / BY_ID["kuiji-xuanzan"]["path"]).read_text(encoding="utf-8"))
    assert not vo.validate_document(doc).errors
    bad = json.loads(json.dumps(doc))
    del bad["metadata"]["coverage_spans"][1]["max_level"]
    bad["metadata"]["split_notes"] = "not a list"
    codes = {f.code for f in vo.validate_document(bad).errors}
    assert codes == {"schema"}, codes
    none = json.loads(json.dumps(doc))
    for key in ("coverage", "coverage_spans", "split_notes"):
        del none["metadata"][key]
    assert not vo.validate_document(none).errors  # optional


def test_guide_tables_are_current():
    text = GUIDE_PATH.read_text(encoding="utf-8")
    fresh = ES.render_blocks(REG)
    assert ES.guide_blocks(text) == fresh, (
        "data/EVAL-SETS.md tables are stale: run python3 scripts/eval_sets.py --write"
    )


# ---------------------------------------------------------------------------------- raw-data checks


def test_t1718_juan_halves_match_raw():
    xml = RAW / "cbeta" / "T34n1718.xml"
    if not xml.exists():
        pytest.skip("data/raw/cbeta/T34n1718.xml absent")
    from chinese_workflow.eval.gold import sdp_check
    from chinese_workflow.ingest.lines import extract

    lines = extract(xml).lines
    lhs = [r["linehead"] for r in lines]
    got = {half: lhs[i] for i, half in sdp_check.juan_half_boundaries(lines)}
    halves = TEXTS["T1718"]["juan_halves"]
    assert got == halves["starts"]
    sdp = RAW / "dila-sdp"
    if not sdp.is_dir():
        pytest.skip("data/raw/dila-sdp/ absent")
    pages = sdp.glob("T1718-juan*.html")
    served = sorted(p.name[len("T1718-juan") : -len(".html")] for p in pages)
    assert served == sorted(halves["served_by_sdp"])


@pytest.mark.parametrize("text", sorted(TEXTS))
def test_split_lineheads_are_lines_of_raw(text):
    xml = RAW / "cbeta" / f"{TEXTS[text]['file']}.xml"
    if not xml.exists():
        pytest.skip(f"{xml.name} absent")
    from chinese_workflow.ingest.lines import extract

    known = {r["linehead"] for r in extract(xml).lines}
    for span in TEXTS[text]["spans"]:
        for lh in (span["start"], span["end"]):
            assert lh is None or lh in known, lh
