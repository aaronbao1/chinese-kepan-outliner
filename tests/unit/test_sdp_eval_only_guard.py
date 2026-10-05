"""Global Constraint 1 guard: no sdp heading text in any tracked file.

sdp (sdp.chibs.edu.tw) publishes no licence, so everything derived from it is eval-only and lives
only under data/raw/dila-sdp/gold/ (gitignored). Committed files may carry aggregate counts, sdp node
ids and a few locator facts (data/EVAL-SETS.md, "Rules for gold data", rule 1), never heading text.

This test scans every file `git ls-files` lists for the headings of the two sdp golds (heading_src
with sdp's leading ordinal stripped, eval.gold.sdp.strip_ordinal):
  * headings of 5 or more characters, in every tracked file;
  * headings of 3 or 4 characters too, in files under pipeline/, scripts/, tests/ and data/ (code,
    fixtures, golds and the eval guide, where a short heading would most likely be a leak; prose
    elsewhere uses common exegetical terms freely).
A hit fails unless the allowlist below explains it. Every entry says why the string is not sdp
content: a sūtra or chapter title, CBETA's own text, or another source's own outline. Short headings
are common exegetical vocabulary, so most hits are coincidences with CBETA text; the allowlist names
each one instead of lowering the bar. It replaces two narrower guards (the registry/guide check in test_gold_registry.py and the
sdp_check.py check in test_gold_sdp_check.py; final review 2026-09-22).

Skips when git is unavailable or the sdp golds are absent (eval-only, gitignored).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
THIS = Path(__file__).resolve().relative_to(REPO).as_posix()
SDP_GOLDS = [
    REPO / "data" / "raw" / "dila-sdp" / "gold" / "T1718.zhiyi-wenju-sdp.outline.json",
    REPO / "data" / "raw" / "dila-sdp" / "gold" / "T0262.zhiyi-wenju-sdp.outline.json",
]
STRICT_PREFIXES = ("pipeline/", "scripts/", "tests/", "data/")
LONG, SHORT = 5, 3
ANYWHERE = ("",)
KUIJI = "data/reference-outlines/T0262/kuiji-xuanzan/"
X0268 = "data/reference-outlines/X0268/cbeta-mulu-kepan/"

# Coincidences: heading -> (path prefixes where it may occur, reason). These strings are not sdp
# content, so they may also stand here.
ALLOWED: dict[str, tuple[tuple[str, ...], str]] = {
    "妙法蓮華經": (
        ANYWHERE,
        "the title of T0262 itself; sdp's root heading repeats the sūtra's title",
    ),
    "無量義經": (
        ("tests/fixtures/cbeta-api/",),
        "a sūtra title (T0276) in CBETA's catalogue API response",
    ),
    "弘傳序": (
        ("tests/fixtures/cbeta-api/", "tests/unit/test_outline_tier1.py"),
        (
            "CBETA's own front-matter title in T09n0262 (cb:mulu type 序), in CBETA's works/toc "
            "response and in the tier-1 test of 品-name normalisation"
        ),
    ),
    "從地踊出": (
        ("tests/fixtures/cbeta-api/", KUIJI, "pipeline/src/chinese_workflow/outline/tier1.py",
         "tests/unit/test_outline_tier1.py"),
        (
            "CBETA's 品 title 從地踊出品 (T09n0262 cb:mulu): CBETA's works/toc responses, a "
            "Kuiji-gold note giving T09n0262's title of the 品, and tier 1's 品-name matching "
            "(T34n1723 從地涌出品 ~ T09n0262 從地踊出品) with its test"
        ),
    ),
    "普賢勸發": (
        ("tests/fixtures/kepan-formulae/",),
        "part of a CBETA 品 title (〈普賢勸發品〉) inside a parser case's verbatim text",
    ),
    "無學眾": (
        ("tests/fixtures/kepan-formulae/",),
        "verbatim T34n1721 text of a parser case (吉藏's 就無學眾開文為六)",
    ),
    "第二問": (
        ("tests/fixtures/kepan-formulae/",),
        "verbatim T37n1763 text of a parser case (第二問分)",
    ),
    "佛與授記": (("tests/unit/test_ingest_lines.py",), "a T34n1723 line quoted by the ingest test"),
    "與授記": (("tests/unit/test_ingest_lines.py",), "a T34n1723 line quoted by the ingest test"),
    "比丘眾": (
        ("tests/unit/test_ingest_lines.py", KUIJI),
        (
            "T09n0262's own words (與大比丘眾, p0001c20), quoted by the ingest test and by Kuiji's "
            "lemmas"
        ),
    ),
    "比丘尼": (
        ("tests/fixtures/cbeta-api/",),
        "a common noun in CBETA titles (CBETA's catalogue API responses)",
    ),
    "四眾歡喜": (
        (KUIJI,),
        "Zhiyi's own words in T34n1718, cited from R03 F23 in a Kuiji-gold note",
    ),
    "八部眾": (
        (KUIJI, X0268),
        "Kuiji's own words in T34n1723 (Kuiji gold) and X11n0268's own CBETA 科判 heading",
    ),
    "聲聞眾": (
        (KUIJI, X0268),
        "Kuiji's own words in T34n1723 (Kuiji gold) and X11n0268's own CBETA 科判 heading",
    ),
    "菩薩眾": (
        (
            KUIJI,
            X0268,
            "pipeline/src/chinese_workflow/eval/gold/cbeta_mulu.py",
            "tests/unit/test_gold_cbeta_mulu.py",
        ),
        (
            "Kuiji's own words in T34n1723 (Kuiji gold) and X11n0268's own CBETA 科判 heading, "
            "which the cbeta_mulu builder and its test cite"
        ),
    ),
    "眾成就": (
        (KUIJI,),
        "Kuiji's own words in T34n1723 (the 法華論's 眾成就 as he names it)",
    ),
    "明機感": (
        (
            X0268,
            "pipeline/src/chinese_workflow/ingest/lines.py",
            "tests/unit/test_ingest_lines.py",
        ),
        "X11n0268's own CBETA 科判 heading, cited by the ingest module and its test",
    ),
    "應二求": ((X0268,), "X11n0268's own CBETA 科判 heading"),
    "經家敘益": ((X0268,), "X11n0268's own CBETA 科判 heading"),
    "經家敘相": ((X0268,), "X11n0268's own CBETA 科判 heading"),
    "明得果": (
        ("data/reference-outlines/D8842/cbeta-mulu-kepan/",),
        "D14n8842's own CBETA 科判 heading",
    ),
    "正明得果": (
        ("data/reference-outlines/D8842/cbeta-mulu-kepan/",),
        "D14n8842's own CBETA 科判 heading",
    ),
    "國土清淨": (
        ("data/reference-outlines/T1602/ybh-dila/",),
        "a heading of DILA's own T1602 outline (YBh gold)",
    ),
}

# sdp content that predates Global Constraint 1, keyed by the sha256 prefix of the stripped heading so
# that this file does not copy it again: path prefixes, reason. Empty: the one sdp heading written
# before the rule (D15's example of an editorial node) has been replaced, so no sdp-coincident text
# remains in this repository.
ALLOWED_DIGESTS: dict[str, tuple[tuple[str, ...], str]] = {}

# Whole files exempt from the scan: path -> reason. Empty: the research records that quoted sdp's
# headings to document sdp itself are not part of this repository.
ALLOWED_FILES: dict[str, str] = {}


def _digest(heading: str) -> str:
    return hashlib.sha256(heading.encode("utf-8")).hexdigest()[:16]


def _allowed(path: str, heading: str) -> bool:
    if path in ALLOWED_FILES:
        return True
    if path == THIS and heading in ALLOWED:
        return True  # the allowlist itself
    entry = ALLOWED.get(heading) or ALLOWED_DIGESTS.get(_digest(heading))
    return entry is not None and path.startswith(entry[0])


def _sdp_headings() -> set:
    from chinese_workflow.eval.gold.sdp import strip_ordinal

    heads = set()
    for p in SDP_GOLDS:
        for n in json.loads(p.read_text(encoding="utf-8"))["nodes"]:
            h = strip_ordinal(n.get("heading_src") or "")
            if len(h) >= SHORT:
                heads.add(h)
    return heads


def _tracked_files() -> list | None:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        return None
    res = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True, text=True, check=False
    )
    if res.returncode != 0:
        return None
    return [f for f in res.stdout.split("\0") if f]


def test_no_sdp_heading_in_any_tracked_file():
    files = _tracked_files()
    if files is None:
        pytest.skip("git not available")
    if not all(p.exists() for p in SDP_GOLDS):
        pytest.skip("sdp golds absent (eval-only, gitignored; run scripts/fetch_dila_sdp.sh)")
    heads = _sdp_headings()
    by_prefix: dict = {}
    for h in heads:
        by_prefix.setdefault(h[:SHORT], []).append(h)
    leaks = []
    for path in files:
        try:
            text = (REPO / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binary, or deleted in the work tree
        strict = path.startswith(STRICT_PREFIXES)
        grams = {text[i : i + SHORT] for i in range(len(text) - SHORT + 1)}
        for g in grams & by_prefix.keys():
            for h in by_prefix[g]:
                if (strict or len(h) >= LONG) and h in text and not _allowed(path, h):
                    leaks.append((path, h))
    # report where and how long, never the heading itself
    shown = sorted((p, len(h), _digest(h)) for p, h in leaks)
    assert not leaks, f"sdp heading text in tracked files (path, length, sha256[:16]): {shown!r}"


def test_allowlist_entries_are_still_needed():
    """An entry that no longer matches any file is removed, so the allowlist stays a list of facts."""
    files = _tracked_files()
    if files is None:
        pytest.skip("git not available")
    if not all(p.exists() for p in SDP_GOLDS):
        pytest.skip("sdp golds absent (eval-only, gitignored)")
    heads = _sdp_headings()
    assert set(ALLOWED) <= heads, sorted(set(ALLOWED) - heads)  # coincidences, not sdp content
    by_digest = {_digest(h): h for h in heads}
    assert set(ALLOWED_DIGESTS) <= set(by_digest)
    entries = [(h, where) for h, (where, _reason) in ALLOWED.items() if where != ANYWHERE]
    entries += [(by_digest[d], where) for d, (where, _reason) in ALLOWED_DIGESTS.items()]
    prefixes = tuple(p for _h, where in entries for p in where)
    texts = {}
    for path in files:
        if path.startswith(prefixes):
            try:
                texts[path] = (REPO / path).read_text(encoding="utf-8")
            except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
                pass
    unused = [
        (_digest(h), where)
        for h, where in entries
        if not any(h in t for path, t in texts.items() if path.startswith(where))
    ]
    assert not unused, f"allowlist entries no longer needed (sha256[:16], where): {unused!r}"
    for path in ALLOWED_FILES:
        assert (REPO / path).is_file(), path
