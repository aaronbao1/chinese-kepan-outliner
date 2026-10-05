"""CLI of the export stage (knowledge-graph export v0, plan M9).

Input:  OUTLINE.json (an independent outline, profile zh-kepan).
Output: OUT.jsonld (BDRC-shaped JSON-LD, R07 F20) and, with --id-history, the updated id history.

    python -m chinese_workflow.export OUTLINE.json --out OUT.jsonld [--id-history id-history.json]
        [--base-uri URI] [--allow-model-only-levels N] [--frozen TAG]

Exit status 2 when the guards refuse the outline (eval-only, or a registered OOD / eval-only gold).
A summary line goes to stderr: nodes exported, model-only nodes withheld (ids), split-withheld count.
"""

from __future__ import annotations

import argparse
import sys

from .jsonld import DEFAULT_BASE, ExportRefused, run


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m chinese_workflow.export", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outline", help="outline.json (profile zh-kepan)")
    ap.add_argument("--out", required=True, help="the JSON-LD file to write")
    ap.add_argument("--id-history", default=None,
                    help="id history (read if present, then rewritten), e.g. export/id-history.json")
    ap.add_argument("--base-uri", default=DEFAULT_BASE)
    ap.add_argument("--allow-model-only-levels", type=int, default=0,
                    help="export model-only (model-* scheme, inferred) nodes at levels <= N; "
                         "default 0 = never (plan D21: only after a per-depth gate)")
    ap.add_argument("--frozen", default=None,
                    help="tag of a frozen outliner: lifts the test/reserve span withholding")
    args = ap.parse_args(argv)
    try:
        outline = run(args.outline, args.out, id_history_path=args.id_history,
                      base_uri=args.base_uri, allow_model_only_levels=args.allow_model_only_levels,
                      frozen=args.frozen)
    except ExportRefused as exc:
        print("export refused: %s" % exc, file=sys.stderr)
        return 2
    withheld = outline.get("cw:withheldModelOnly") or []
    print("exported %d nodes to %s; withheld: %d model-only%s, %d in test/reserve spans"
          % (outline["cw:exportedNodeCount"], args.out, len(withheld),
             " (%s)" % ", ".join(withheld) if withheld else "",
             outline.get("cw:withheldSplitCount", 0)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
