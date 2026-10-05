"""chinese_workflow.eval.gold.ybh — import DILA's 瑜伽師地論資料庫 (YBh, ybh.dila.edu.tw) standalone
科判 `-kp.txt` downloads as structure-only gold outlines (zh-kepan profile, outline_mode "sutra"
with commentary_id null: the stating work has no CBETA id to cite, metadata_zh.commentary_id's
documented case (b) — controller decision, fix round 1).

Input : data/raw/dila-ybh/<CODE>-kp.txt (scripts/fetch_dila_ybh.sh; gitignored; CC BY-SA 4.0,
        R04 F29; tests/fixtures/dila-ybh/T1605-kp.head60.txt + README.md for the format).
        Format (R04 F25, F9; verified again directly on the full T1605/T1602 files 2026-09-22):
        UTF-8 without BOM, one node per line, indentation of two ASCII spaces per level, a label
        (depth letter A=level 1, B=2, … Z=26, then a=27 … + a decimal sibling number, e.g. "C1";
        a hyphenated sibling range such as "H4-5" or "K5-9" marks one node standing for several of
        DILA's original siblings, flagged merged_range), one space, then the heading, with an
        optional trailing full-width "（分<Chinese numeral>）" giving the number of children this
        node's own division announces (child_count_announced). No Taishō line references anywhere
        in this file (the interleaved *-text-kp.zip variant carries the same labels as headings
        inside the text but still no line refs; not parsed here).
Output: data/reference-outlines/<CODE>/ybh-dila/outline.json — zh-kepan, outline_mode "sutra"
        with commentary_id null (the stating work — 韓清淨's 集論科文別釋 for T1605, 早島理・毛利俊英
        1990 for T1602 — has no CBETA id to cite), structure only: every node's locations.scheme is
        "none" and every node carries flag "unmapped" (the standalone file carries no Taishō
        anchors to resolve a root-text span from).
        stdout (CLI): node/depth counts vs R04 F9 (T1605 2,605 nodes / depth 24, T1602 2,594 / 20)
        and the child_count_announced-vs-actual-children mismatch count (flag count_mismatch).

Rules (Task 8 of docs/plans/2026-09-22-eval-datasets.md; controller resolutions 2026-09-22):
  * Depth comes from the label's letter, cross-checked against the line's indentation (two spaces
    per level). They agree on every line of T1605 (2,605 lines) and T1602 (2,594 lines) — checked
    by direct comparison on 2026-09-22 — so no node of either gold carries flag irregular_label.
    Where they would disagree, or the label uses more than one letter (T1579 reaches a 33rd level
    by continuing 'a'..'g' past 'Z'; not in scope here — see "T1579" below), depth is taken from
    the label and the disagreement is reported and flagged irregular_label (module-level, not
    exercised by the two in-scope files).
  * A hyphenated sibling number ("H4-5", "K5-9", …) flags merged_range. T1602 has 14 such nodes;
    T1605 has none.
  * locations = {"scheme": "none"}; flags always include "unmapped" (the download carries no
    Taishō anchors at all, so there is no root-text span to fail to resolve). In this gold's
    outline_mode "sutra", scripts/validate_outline.py's own [sutra-span-unmapped] rule requires
    exactly this for every sutra-span node without a cbeta-kepan root span, so the flag is not
    merely documentary here — it is what keeps every node valid (see tests/unit/test_gold_ybh.py).
  * child_count_announced is the int parsed from a trailing "（分<numeral>）"; when it disagrees
    with the number of children actually present in this outline, the node is flagged
    count_mismatch (warning-level, scripts/validate_outline.py [child-count]) and gets a note.
    T1605 has 917 announced counts, 7 of them mismatched; T1602 announces none at all (T1602's
    -kp.txt has no "（分N）" anywhere — checked 2026-09-22), so it has no count_mismatch nodes.
  * outline_mode = "sutra", commentary_id = null (controller decision, fix round 1: the task-8
    task's earlier "(self-outlining)" wording was a controller error, corrected here). This is
    metadata_zh.commentary_id's documented case (b): "sūtra mode with a stating work that has no
    CBETA file id to cite". T1605's 科判 follows 韓清淨's 大乘阿毘達磨集論科文別釋 (【韓科】; R04 F3
    PARTIAL, R06 F28); T1602's follows 早島理・毛利俊英 (1990; R06 F28). Neither stating work has a
    CBETA id recorded in this repo, so commentary_id stays null and the stating work is named in
    source_document.notes instead (scheme_id is the plan's fixed literal value "ybh-dila" for
    both texts, not a per-stating-work name as sdp.py's scheme ids are). See each PROVENANCE.md.
  * root_text_id: DILA's download page never states a CBETA volume number. Confirmed instead by
    inspecting the local clone data/raw/cbeta/xml-p5 (git tag 2026R2): T/T31/T31n1605.xml and
    T/T31/T31n1602.xml exist and their <title level="m"> elements read 大乘阿毘達磨集論 and
    顯揚聖教論 respectively (checked 2026-09-22; a command run in this task, not an R04 source —
    the provenance rule, data/EVAL-SETS.md "Rules for gold data", rule 6).
    root_text_id = "T31n1605" / "T31n1602"; cbeta_release = "2026R2".
    No line of either CBETA file is read or checked against the -kp.txt content: this gold is
    structure only.
  * T1579 (out of scope): its -kp.txt uses the same letter+number scheme up to depth 33 (continues
    'a'..'g' past 'Z', which this parser's single-letter A-Z/a-z scheme does handle), but also (at
    least) 49 lines whose label carries a verse-based suffix this parser does not recognise at all
    ("Oa 後序" — a letter with no digit; "M39-48ab", "N48ab", "K14-17ab" — a sibling range or
    number followed by half-verse letters "ab"/"cd"). This module raises rather than guessing at
    those; T1579 needs its own label grammar before it can be imported (checked 2026-09-22, not
    attempted here: the plan's Task 8 names T1605 and T1602).

Folder / files: data/reference-outlines/<CODE>/ybh-dila/outline.json + PROVENANCE.md (the latter
hand-written, not generated by this module).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from chinese_workflow.eval.gold import common

SCHEME_ID = "ybh-dila"
CBETA_RELEASE = "2026R2"
YBH_URL = "https://ybh.dila.edu.tw/pages/download?locale=zh&menu=download"

_LINE_RE = re.compile(r"^( *)([A-Za-z]+)([0-9]+(?:-[0-9]+)?) (.*)\Z")
_COUNT_RE = re.compile(r"（分([一二三四五六七八九十百]+)）\s*\Z")
_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

# Sources this module knows how to build (plan Task 8 scope). Root-text-id confirmed 2026-09-22
# against data/raw/cbeta/xml-p5 at tag 2026R2 (module docstring); not from an R04 sources.md row.
SOURCES = {
    "T1605": {
        "root_text_id": "T31n1605",
        "title_src": "大乘阿毘達磨集論",
        "title_en": "Compendium of Abhidharma (lit. gloss of 大乘阿毘達磨集論 'Compendium of "
        "Mahāyāna Abhidharma'; conventionally Asaṅga's *Abhidharmasamuccaya* — authorship not "
        "independently verified in this repo)",
        "stating_work": (
            "韓清淨's 大乘阿毘達磨集論科文別釋 (【韓科】); R04 F3 (PARTIAL), R06 F28. No CBETA id "
            "for this stating work is recorded in this repo."
        ),
    },
    "T1602": {
        "root_text_id": "T31n1602",
        "title_src": "顯揚聖教論",
        "title_en": "lit. 'Treatise Elucidating and Elevating the Sacred Teaching' (顯揚聖教論; "
        "no established English title verified in this repo)",
        "stating_work": (
            "早島理・毛利俊英 (1990); R06 F28. No CBETA id for this stating work is recorded in "
            "this repo."
        ),
    },
}


def _cn_to_int(s: str) -> int:
    """Chinese numeral -> int. Exercises 一 … 二十四 (T1605's （分N） range) but is kept general for
    any two-digit or low three-digit count; raises on a form this repo has not seen."""
    if s in _CN_DIGITS:
        return _CN_DIGITS[s]
    if s == "十":
        return 10
    if "百" in s:
        hpart, _, rest = s.partition("百")
        hundreds = _CN_DIGITS[hpart] if hpart else 1
        return hundreds * 100 + (_cn_to_int(rest) if rest else 0)
    if "十" in s:
        tpart, _, rest = s.partition("十")
        tens = _CN_DIGITS[tpart] if tpart else 1
        ones = _CN_DIGITS[rest] if rest else 0
        return tens * 10 + ones
    raise ValueError("unrecognised Chinese numeral %r" % s)


def _label_level(letters: str) -> int | None:
    """A=1 … Z=26, a=27 … z=52 (module docstring, "T1579" note); None for anything else (multi-
    letter, or a letter this scheme does not cover)."""
    if len(letters) != 1:
        return None
    c = letters
    if "A" <= c <= "Z":
        return ord(c) - ord("A") + 1
    if "a" <= c <= "z":
        return 26 + ord(c) - ord("a") + 1
    return None


@dataclass
class Rec:
    """One parsed line of a -kp.txt file."""

    lineno: int
    level: int
    label: str  # e.g. "A1", "K5-9"
    heading: str
    count: int | None  # child_count_announced
    merged: bool
    flags: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    raw: str = ""  # the line, stripped of surrounding whitespace


def parse_kp(text: str, filename: str) -> list[Rec]:
    """UTF-8 -kp.txt text -> one Rec per line, in file order (module docstring format). Raises
    ValueError, naming filename:lineno, on a line the label/heading grammar does not recognise
    (never silently guessed — see the "T1579" docstring note)."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]  # the file's own trailing newline
    out: list[Rec] = []
    for i, line in enumerate(lines, 1):
        m = _LINE_RE.match(line)
        if not m:
            raise ValueError(
                "%s:%d: line does not match the -kp.txt label/heading grammar: %r"
                % (filename, i, line)
            )
        indent, letters, num, rest = m.groups()
        indent_level = len(indent) // 2 + 1
        letter_level = _label_level(letters)
        flags: list = []
        notes: list = []
        if letter_level is None:
            level = indent_level
            flags.append("irregular_label")
            notes.append(
                "label %s%s: depth letter %r is not a single A-Z/a-z letter; depth taken from "
                "the line's indentation (%d)" % (letters, num, letters, indent_level)
            )
        elif letter_level != indent_level:
            level = letter_level
            flags.append("irregular_label")
            notes.append(
                "label %s%s implies depth %d but the line's indentation implies depth %d; depth "
                "taken from the label" % (letters, num, letter_level, indent_level)
            )
        else:
            level = letter_level
        merged = "-" in num
        if merged:
            flags.append("merged_range")
            notes.append(
                "source label %s%s stands for one node covering original DILA siblings %s"
                % (letters, num, num)
            )
        cm = _COUNT_RE.search(rest)
        count = _cn_to_int(cm.group(1)) if cm else None
        heading = _COUNT_RE.sub("", rest).strip() if cm else rest.strip()
        out.append(Rec(i, level, letters + num, heading, count, merged, flags, notes, line.strip()))
    return out


def _draft(rec: Rec, filename: str) -> dict:
    flags = list(rec.flags)
    flags.append("unmapped")  # every node: the standalone file carries no Taishō anchors
    return {
        "heading_src": rec.heading,
        "heading_en": "",
        "display_label": rec.label,
        "source_node_id": "%s:L%d %s" % (filename, rec.lineno, rec.label),
        "origin": "imported",
        "node_class": "sutra-span",
        "flags": flags,
        "child_count_announced": rec.count,
        "extent_announced": None,
        "locations": {"scheme": "none"},
        "evidence": "%s line %d: %s" % (filename, rec.lineno, rec.raw),
        "notes": list(rec.notes),
        "children": [],
    }


def build_tree(records: list[Rec], filename: str) -> tuple[list[dict], list[dict], list[str]]:
    """records (document order) -> (roots, all draft dicts in document order, doc-level anomaly
    strings). A node's parent is the nearest preceding node of a shallower level; a gap between
    levels (the label/indentation jumps by more than one) is not expected for T1605/T1602 (module
    docstring) but is handled like Kurt's "nearest present ancestor" convention, noted on both the
    node and the returned anomaly list, rather than raising."""
    stack: list[tuple[int, dict]] = []
    roots: list[dict] = []
    all_nodes: list[dict] = []
    anomalies: list[str] = []
    for rec in records:
        node = _draft(rec, filename)
        all_nodes.append(node)
        while stack and stack[-1][0] >= rec.level:
            stack.pop()
        if stack:
            parent_level, parent = stack[-1]
            if parent_level != rec.level - 1:
                msg = (
                    "%s:%d (%s): depth %d's nearest present ancestor is at depth %d, not %d; "
                    "attached to that ancestor" % (filename, rec.lineno, rec.label, rec.level,
                                                    parent_level, rec.level - 1)
                )
                anomalies.append(msg)
                node["notes"].append(msg)
            parent["children"].append(node)
        else:
            roots.append(node)
        stack.append((rec.level, node))
    return roots, all_nodes, anomalies


def _flag_count_mismatches(all_nodes: list[dict]) -> int:
    """Adds flag count_mismatch (+ a note) wherever child_count_announced disagrees with the
    number of children actually present; returns how many nodes were flagged."""
    n = 0
    for node in all_nodes:
        cc = node["child_count_announced"]
        if cc is not None and cc != len(node["children"]):
            node["flags"].append("count_mismatch")
            node["notes"].append(
                "source announces %d child(ren) but this node has %d in this outline" % (cc, len(node["children"]))
            )
            n += 1
    return n


FORMAT_NOTE = (
    "Imported from DILA's 瑜伽師地論資料庫 standalone 科判 download, %(filename)s (R04 F9, F25; "
    "tests/fixtures/dila-ybh/README.md): UTF-8 without BOM, one node per line, indentation of two "
    "ASCII spaces per level, label = depth letter (A=level 1, B=2, … Z=26, then a=27 …) + sibling "
    "number, a space, then the heading; a hyphenated sibling range in the label (e.g. 'H4-5') "
    "marks one node standing for several of DILA's original siblings, flagged merged_range (%(merged)d "
    "such node(s) here). A trailing full-width '（分<Chinese numeral>）' gives the number of "
    "children DILA's outline announces for that node (child_count_announced; %(announced)d of "
    "%(node_count)d nodes here carry one); it disagrees with the number of children actually "
    "present in %(mismatch)d of them, each flagged count_mismatch (warning-level, "
    "scripts/validate_outline.py [child-count]). Depth is taken from the label's letter, cross-"
    "checked against the line's indentation; the two agree on every line of this file (checked "
    "2026-09-22), so no node here is flagged irregular_label. The standalone -kp.txt carries no "
    "Taishō line anchors (R04 F25/F9): every node's locations.scheme is 'none' and every node "
    "carries flag 'unmapped'. In this gold's outline_mode 'sutra', scripts/validate_outline.py's "
    "[sutra-span-unmapped] rule requires exactly this for every sutra-span node without a "
    "cbeta-kepan root span (module docstring) — the flag is not merely documentary here."
)

LICENCE = {
    "id": "CC-BY-SA-4.0",
    "holder": "法鼓文理學院 DILA (Dharma Drum Institute of Liberal Arts), 1999–2026",
    "statement": (
        "DILA YBh download page footer (data/raw/dila-ybh/download-page.html): \"© CC BY-SA "
        "4.0\" (icons cc / by / sa; no NC icon; R04 F29, F9). The CHIBS mirror's 關於本站 page "
        "states a different, unreconciled licence line: \"本資料庫係採用創用 CC 姓名標示-相同方式"
        "分享 3.0 台灣 授權條款授權\" (CC BY-SA 3.0 台灣; R06 F28, S45) — recorded here per "
        "Global Constraint 2 of docs/plans/2026-09-22-eval-datasets.md, not reconciled with the "
        "live DILA download page's 4.0 statement."
    ),
    "evidence": (
        "context/research/R04-existing-digital-kepan-datasets/findings.md F29 (S16); "
        "context/research/R06-outline-eval-metrics/findings.md F28 (S45)"
    ),
}


def build_gold(code: str, kp_path: Path) -> dict:
    """The full pipeline for one -kp.txt file: parse -> tree -> flag mismatches -> number ->
    metadata -> zh-kepan document. code: "T1605" or "T1602" (keys of SOURCES)."""
    info = SOURCES[code]
    filename = kp_path.name
    text = kp_path.read_text(encoding="utf-8")
    records = parse_kp(text, filename)
    roots, all_nodes, anomalies = build_tree(records, filename)
    mismatches = _flag_count_mismatches(all_nodes)
    nodes = common.number_tree(roots)

    announced = sum(1 for n in nodes if n["child_count_announced"] is not None)
    merged = sum(1 for n in nodes if "merged_range" in n["flags"])
    irregular = sum(1 for n in nodes if "irregular_label" in n["flags"])
    format_note = FORMAT_NOTE % {
        "filename": filename,
        "merged": merged,
        "announced": announced,
        "node_count": len(nodes),
        "mismatch": mismatches,
    }
    if irregular:
        format_note += (
            " %d node(s) here are flagged irregular_label (label/indentation disagreement or an "
            "unrecognised depth letter); see their notes." % irregular
        )

    meta = common.zh_metadata(
        nodes,
        source_file=common.repo_relative(kp_path),
        source_sha256=common.sha256_file(kp_path),
        text_id=code,
        text_title_src=info["title_src"],
        text_title_en=info["title_en"],
        author=None,
        source_language="lzh",
        format_note=format_note,
        origin_note=(
            "Every node is origin 'imported' from DILA's standalone %s and unchecked against %s's "
            "own CBETA text (structure only: no Taishō line anchors are read or resolved here). "
            "DILA's own composite per-node provenance labels (【韓科】/【倫科】 etc., R04 F3, F10, "
            "F28) are carried in DILA's internal TEI, not in this plain-text export, and are not "
            "reconstructed here." % (filename, code)
        ),
        generated_by="chinese_workflow.eval.gold.ybh",
        anomalies=list(anomalies),
        source_document={
            "kind": "dataset",
            "text_id": None,
            "title": "DILA 瑜伽師地論資料庫 (ybh.dila.edu.tw) 科判 of %s %s" % (code, info["title_src"]),
            "url": YBH_URL,
            "notes": [
                "raw file: %s sha256 %s" % (common.repo_relative(kp_path), common.sha256_file(kp_path)),
                "DILA's own account of provenance (R04 F3, F28): this outline follows %s. "
                "metadata.outline_mode is 'sutra' with commentary_id null: the stating work above "
                "has no CBETA id to cite (metadata_zh.commentary_id's documented case (b); "
                "controller decision, fix round 1). See PROVENANCE.md." % info["stating_work"],
                "root_text_id %s: DILA's download page states no CBETA volume; confirmed instead "
                "by inspecting data/raw/cbeta/xml-p5/T/T31/%s.xml (TEI <title level=\"m\">) at the "
                "local clone's tag 2026R2, 2026-09-22 (a command run in this task, not an R04 "
                "sources.md entry)." % (info["root_text_id"], info["root_text_id"]),
            ],
        },
        outline_mode="sutra",
        root_text_id=info["root_text_id"],
        commentary_id=None,
        scheme_id=SCHEME_ID,
        seeded_by=None,
        gold_status="imported-unchecked",
        licence=dict(LICENCE),
        eval_only=False,
        cbeta_release=CBETA_RELEASE,
        display_label_rule=(
            "the source's own label, verbatim (e.g. 'A1'; a hyphenated range such as 'H4-5' or "
            "'K5-9' for a node standing in for several of DILA's original siblings, flagged "
            "merged_range)"
        ),
    )
    return {"metadata": meta, "nodes": nodes}


# ------------------------------------------------------------------------------------------ CLI


def _code_from_filename(path: Path) -> str:
    m = re.match(r"^([A-Za-z][A-Za-z0-9]*)-kp", path.name)
    if not m:
        raise ValueError("%s: filename does not look like '<CODE>-kp*.txt'" % path)
    return m.group(1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "kp_txt", nargs="*", type=Path,
        help="one or more -kp.txt files (default: data/raw/dila-ybh/T1605-kp.txt and T1602-kp.txt)",
    )
    ap.add_argument(
        "--out-dir", type=Path, default=common.REPO_ROOT / "data" / "reference-outlines",
        help="root of the reference outlines; each file is written to "
        "<out-dir>/<CODE>/ybh-dila/outline.json (default: data/reference-outlines)",
    )
    args = ap.parse_args(argv)
    paths = args.kp_txt or [
        common.REPO_ROOT / "data/raw/dila-ybh/T1605-kp.txt",
        common.REPO_ROOT / "data/raw/dila-ybh/T1602-kp.txt",
    ]
    failed = 0
    for kp_path in paths:
        code = _code_from_filename(kp_path)
        if code not in SOURCES:
            print("SKIP  %s: %s is out of scope for this module (see the docstring's 'T1579' "
                  "note)" % (kp_path, code), file=sys.stderr)
            failed += 1
            continue
        doc = build_gold(code, kp_path)
        # one folder per code under the root (as cbeta_mulu's --out-dir), so several inputs never
        # overwrite each other's outline.json
        path = common.write_json(doc, args.out_dir / code / "ybh-dila" / "outline.json")
        rep = common.validate(doc, common.repo_relative(path))
        failed += not rep.passed()
        meta = doc["metadata"]
        mismatches = sum(1 for n in doc["nodes"] if "count_mismatch" in n["flags"])
        merged = sum(1 for n in doc["nodes"] if "merged_range" in n["flags"])
        print(
            "%s  %s  nodes=%d  max_depth=%d  count_mismatch=%d  merged_range=%d  errors=%d  "
            "warnings=%d"
            % (
                "PASS" if rep.passed() else "FAIL",
                rep.path,
                rep.node_count,
                rep.max_depth,
                mismatches,
                merged,
                len(rep.errors),
                len(rep.warnings),
            )
        )
        for f in rep.errors[:10]:
            print(f.render())
        for f in rep.warnings[:10]:
            print(f.render())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
