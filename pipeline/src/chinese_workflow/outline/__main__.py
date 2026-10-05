"""python -m chinese_workflow.outline — the outline stage's CLI.

  build       one outline build (outline.pipeline.build): from a project file or from flags
  validate    scripts/validate_outline.py on outline files (in process)
  span-start  add locations.commentary.span_start to a saved outline.json (common.outline_doc.
              fill_span_starts: the rule is in its docstring); written to --out, the input is left as it is

Examples:
  python -m chinese_workflow.outline build --project projects/lotus-kuiji-dharani-comm/project.toml \\
      --out data/processed/dharani-comm/outline
  python -m chinese_workflow.outline build --mode self-outlining --root T32n1666 --source tier2 \\
      --out /tmp/qixin
  python -m chinese_workflow.outline build --mode sutra --root T09n0262 --commentary T34n1723 \\
      --scheme kuiji-xuanzan --span dev --source tier1 --out /tmp/floor
Test and reserve spans of T1718 / T1723 are refused unless --frozen <tag> names a frozen outliner.
Exit status of build: 0 = outline written and validating (a repaired outline reports "degraded": <n> in the
JSON line and in outline-report.json); 1 = errors remain after repair (every artefact and outline-report.json
are still written, for inspection; the outline does not validate); 2 = the split guard refused the span;
3 = interactive resolver requests await a response.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..common import outline_doc
from ..common.jsonio import read_json, write_json
from ..common.project import load_project
from ..common.splits import SplitGuard, SplitViolation
from .pipeline import SOURCES, OutlineConfig, OutlineValidationError, build

INTERACTIVE_MODEL = "claude-code-session"


def _llm_config(resolver: dict, out_dir):
    adapter = (resolver or {}).get("adapter", "none")
    if adapter == "none":
        return None
    from ..llm import LLMConfig

    kwargs = {"adapter": adapter, "run_dir": out_dir}
    for key in ("model", "cassette", "max_tokens", "budget_usd"):
        if (resolver or {}).get(key) is not None:
            kwargs[key] = resolver[key]
    if adapter == "interactive" and not (resolver or {}).get("model"):
        # the answers come from whoever writes the response files (a Claude Code session following
        # the skill), not from an API model: say so in every note and report
        kwargs["model"] = INTERACTIVE_MODEL
    return LLMConfig(**kwargs)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m chinese_workflow.outline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build an outline")
    b.add_argument("--project", help="projects/<id>/project.toml (flags below override it)")
    b.add_argument("--mode", choices=("sutra", "self-outlining"))
    b.add_argument("--root", help="CBETA file id of the sūtra (sūtra mode) or the treatise")
    b.add_argument("--commentary", help="CBETA file id of the designated commentary (sūtra mode)")
    b.add_argument("--scheme", help="scheme_id")
    b.add_argument("--span", help="dev | validation | whole | FIRST..LAST")
    b.add_argument("--source", choices=SOURCES)
    b.add_argument("--target-role", choices=("commentary", "root"))
    b.add_argument("--adapter", choices=("none", "replay", "claude", "interactive"))
    b.add_argument("--xml", action="append", default=[], metavar="FILE_ID=PATH",
                   help="use this XML file for a CBETA file id (e.g. a fixture excerpt)")
    b.add_argument("--frozen", help="tag of a frozen outliner: allows test/reserve spans")
    b.add_argument("--out", required=True)
    v = sub.add_parser("validate", help="validate outline.json files")
    v.add_argument("files", nargs="+")
    s = sub.add_parser("span-start", help="add locations.commentary.span_start to a saved outline.json")
    s.add_argument("outline", help="a saved outline.json (left as it is)")
    s.add_argument("--out", required=True, help="where the copy with the pair filled is written")
    args = ap.parse_args(argv)

    if args.cmd == "validate":
        ok = True
        for f in args.files:
            rep = outline_doc.validate(read_json(f), f)
            print("%s %s: %d errors, %d warnings" % ("PASS" if rep.passed() else "FAIL", f,
                                                     len(rep.errors), len(rep.warnings)))
            for finding in rep.errors[:25]:
                print(finding.render())
            ok &= rep.passed()
        return 0 if ok else 1

    if args.cmd == "span-start":
        if Path(args.out).resolve() == Path(args.outline).resolve():
            ap.error("--out must not be the input outline (it is left as it is): %s" % args.outline)
        doc = read_json(args.outline)
        outline_doc.fill_span_starts(doc)
        commit = outline_doc.pipeline_commit()
        doc["metadata"]["span_start_filled_by"] = "python -m chinese_workflow.outline span-start @ %s%s" % (
            (commit["commit"] or "unknown")[:12], "+dirty" if commit["dirty"] else "")
        rep = outline_doc.validate(doc, args.out)
        write_json(doc, args.out)
        inherited = sum(1 for n in doc["nodes"]
                        if ((n.get("locations") or {}).get("commentary") or {}).get("span_start_inherited") is True)
        print(json.dumps({"outline": args.out, "nodes": len(doc["nodes"]), "span_start_inherited": inherited,
                          "validation": {"passed": rep.passed(),
                                         "errors": [f.render() for f in rep.errors[:5]]}},
                         ensure_ascii=False))
        return 0 if rep.passed() else 1

    proj = load_project(args.project) if args.project else {}
    fields = {
        "mode": args.mode or proj.get("mode"),
        "root": args.root or proj.get("root"),
        "commentary": args.commentary or proj.get("commentary"),
        "scheme_id": args.scheme or proj.get("scheme_id") or "unnamed-scheme",
        "span": args.span or proj.get("span"),
        "source": args.source or proj.get("source") or "tier2",
        "target_role": args.target_role or proj.get("target_role") or "commentary",
        "level1": list(((proj.get("scheme") or {}).get("level1")) or []),
        "xml": dict(proj.get("xml") or {}),
        "resolver": dict(proj.get("resolver") or {"adapter": "none"}),
        "oracle_gold": proj.get("oracle_gold"),
        "title": proj.get("title", ""),
        "heading_style": (proj.get("outline") or {}).get("heading_style", "source"),
    }
    if args.adapter:
        fields["resolver"]["adapter"] = args.adapter
    for item in args.xml:
        fid, _, path = item.partition("=")
        fields["xml"][fid] = path
    if not fields["mode"] or not fields["root"]:
        ap.error("--mode and --root (or --project) are required")
    if fields["mode"] == "self-outlining":
        fields["commentary"] = None
        fields["target_role"] = "root"
    cfg = OutlineConfig(**fields)
    guard = SplitGuard(frozen=args.frozen)
    try:
        result = build(cfg, args.out, guard=guard, llm_config=_llm_config(cfg.resolver, args.out))
    except SplitViolation as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 2
    except OutlineValidationError as exc:
        # errors no repair covers: the artefacts and outline-report.json are written for inspection.
        # Any other RuntimeError keeps its traceback.
        print("failed: %s" % exc, file=sys.stderr)
        return 1
    rep = result["report"]
    if result["pending"]:
        print("interactive resolver: %d request(s) await a response. For each, read the .md beside "
              "the request, write the JSON answer to llm/responses/<same name>.json, then re-run this "
              "command (skills/chinese-kepan-outliner/SKILL.md, step 3):" % len(result["pending"]))
        for req in result["pending"]:
            print("  " + req.replace(".json", ".md"))
    print(json.dumps({"outline": result["paths"]["outline"],
                      "nodes": result["doc"]["metadata"]["node_count"],
                      "max_depth": result["doc"]["metadata"]["max_depth"],
                      "validation": {"passed": rep["validation"]["passed"],
                                     "warnings": len(rep["validation"]["warnings"])},
                      "degraded": sum(len(e["repairs"]) for e in rep.get("degraded", [])),
                      "pending_interactive": len(result["pending"])},
                     ensure_ascii=False))
    return 3 if result["pending"] else 0


if __name__ == "__main__":
    sys.exit(main())
