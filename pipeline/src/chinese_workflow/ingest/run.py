"""chinese_workflow.ingest.run — the ingest stage run and CLI (M1a, docs/outliner-design.md §4).

Input : one CBETA XML P5 file, by file id (resolved under data/raw/cbeta/, common.paths) or by
        path, a role ("root" | "commentary") and optionally a span (first, last) of lineheads,
        both inclusive.
Output: four files in out_dir —
  <id>.lines.jsonl           the ingest.lines records of the span (the canonical input)
  <id>.txt                   the reading text = InputText.text, lines concatenated without
                             separator, UTF-8, no trailing newline (offsets = TextIndex offsets)
  <id>.structure.json        structure/1 (ingest.structure.build_structure)
  normalization.config.json  ingest.structure.normalization_config (regime "none"); one per
                             out_dir, so ingest the root and the commentary into separate dirs
  and returns {"text_id", "sha256", "paths": {lines, text, structure, normalization},
  "counts": {lines, chars, elements: {kind: n}, excluded_notes, gaiji}, "split_guard": [...]}.

The split guard (common.splits, design §3) checks the span's lines before anything is written:
a span touching test or reserve lines of T34n1718 / T34n1723 (a whole-file ingest of either) is
refused unless `frozen` names a frozen outliner.

Usage : python -m chinese_workflow.ingest run SOURCE --role root|commentary --out DIR
               [--span FIRST..LAST] [--frozen TAG]
        python -m chinese_workflow.ingest lines ...      (= python -m chinese_workflow.ingest.lines)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..common.jsonio import write_json, write_jsonl
from ..common.splits import SplitGuard
from .structure import build_structure, element_counts, normalization_config
from .text import load_input_text

ROLES = ("root", "commentary")


def parse_span(value: str | None) -> tuple | None:
    """'T34n1723_p0850a19..T34n1723_p0850b19' -> (first, last); None or '' -> None."""
    if not value:
        return None
    first, sep, last = value.partition("..")
    if not sep or not first or not last:
        raise ValueError("span must be FIRST..LAST (two lineheads), got %r" % value)
    return first.strip(), last.strip()


def run(
    source,
    *,
    role: str,
    out_dir,
    span: tuple | None = None,
    frozen: str | None = None,
    guard: SplitGuard | None = None,
) -> dict:
    """Ingest one CBETA file (see the module docstring). `guard` lets a runner collect the split
    checks of every stage in one report; without it a guard with `frozen` is made here."""
    if role not in ROLES:
        raise ValueError("role must be one of %s, got %r" % (ROLES, role))
    text = load_input_text(source, span=span, role=role)
    guard = guard if guard is not None else SplitGuard(frozen=frozen)
    guard.check_lines([rec["linehead"] for rec in text.lines], purpose="ingest")

    structure = build_structure(text)
    config = normalization_config(text)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tid = text.text_id
    paths = {
        "lines": out / ("%s.lines.jsonl" % tid),
        "text": out / ("%s.txt" % tid),
        "structure": out / ("%s.structure.json" % tid),
        "normalization": out / "normalization.config.json",
    }
    write_jsonl(text.lines, paths["lines"])
    with open(paths["text"], "w", encoding="utf-8", newline="") as fh:
        fh.write(text.text)
    write_json(structure, paths["structure"])
    write_json(config, paths["normalization"])
    return {
        "text_id": tid,
        "sha256": text.sha256,
        "paths": {k: str(p) for k, p in paths.items()},
        "counts": {
            "lines": len(text.lines),
            "chars": len(text.text),
            "elements": element_counts(structure),
            "excluded_notes": config["excluded_notes"],
            "gaiji": sum(config["gaiji_routes"].values()),
        },
        "split_guard": list(guard.report),
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "lines":
        from .lines import main as lines_main

        return lines_main(argv[1:])
    ap = argparse.ArgumentParser(
        prog="python -m chinese_workflow.ingest",
        description="Ingest stage: CBETA XML P5 -> lines.jsonl, txt, structure.json, "
        "normalization config. 'lines ...' runs the line extractor CLI.",
    )
    sub = ap.add_subparsers(dest="command", required=True)
    rp = sub.add_parser("run", help="ingest one CBETA file into an output directory")
    rp.add_argument("source", help="CBETA file id (e.g. T09n0262) or path to a P5 XML file")
    rp.add_argument("--role", required=True, choices=ROLES)
    rp.add_argument("--out", required=True, help="output directory")
    rp.add_argument("--span", help="FIRST..LAST lineheads, inclusive (default: the whole file)")
    rp.add_argument("--frozen", help="tag of a frozen outliner (lifts the split guard)")
    sub.add_parser("lines", help="the line extractor CLI (python -m chinese_workflow.ingest.lines)")
    args = ap.parse_args(argv)
    result = run(
        args.source,
        role=args.role,
        out_dir=args.out,
        span=parse_span(args.span),
        frozen=args.frozen,
    )
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0
