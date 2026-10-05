"""python -m chinese_workflow.chunk — write the interlinear outline of one target text.

Input:  --outline outline.json, --outlined-text outlined-text.json, --sentences sentences.json, and
        --target SOURCE (a CBETA file id resolved under data/raw/cbeta/, or a path to a P5 file);
        --span FIRST..LAST restricts the target (default: the outlined-text's first..last linehead).
Output: DIR/chunks.json (chunks/1), DIR/chunks.md, DIR/chunks.docx; a one-line summary on stdout.

    python -m chinese_workflow.chunk --outline run/outline.json \
        --outlined-text run/outlined-text.json --sentences run/sentences.json \
        --target T34n1723 --out run/ [--sentence-cap 6] [--size-chars 180|none] [--frozen TAG]
"""

from __future__ import annotations

import argparse
import sys

from .chunker import DEFAULT_SENTENCE_CAP, DEFAULT_SIZE_CHARS, parse_span, run


def _size(value: str) -> int | None:
    if value.lower() in ("none", "0", ""):
        return None
    return int(value)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m chinese_workflow.chunk", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outline", required=True)
    ap.add_argument("--outlined-text", required=True)
    ap.add_argument("--sentences", required=True)
    ap.add_argument("--target", required=True, help="CBETA file id or path to its P5 XML")
    ap.add_argument("--span", default=None, help="FIRST..LAST lineheads of the target")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sentence-cap", type=int, default=DEFAULT_SENTENCE_CAP)
    ap.add_argument("--size-chars", type=_size, default=DEFAULT_SIZE_CHARS,
                    help="length budget in characters; 'none' disables it")
    ap.add_argument("--frozen", default=None, help="frozen-outliner tag (needed for test spans)")
    args = ap.parse_args(argv)
    result = run(args.outline, args.outlined_text, args.sentences, args.target, args.out,
                 span=parse_span(args.span), sentence_cap=args.sentence_cap,
                 size_chars=args.size_chars, frozen=args.frozen)
    counts = result["chunks"]["metadata"]["counts"]
    print("chunks: %d (merged %d, split-leaf %d, unoutlined %d); markers %d; announcements %d "
          "(unplaced %d) -> %s" % (
              counts["chunks"], counts["merged_chunks"], counts["fallback"]["split-leaf"],
              counts["fallback"]["unoutlined"], counts["markers"], counts["announcements"],
              counts["announcements_unplaced"], result["paths"]["chunks_json"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
