"""python -m chinese_workflow.ingest run SOURCE --role root|commentary --out DIR [--span A..B]

Input/Output: see chinese_workflow.ingest.run (one CBETA P5 file -> <id>.lines.jsonl, <id>.txt,
<id>.structure.json, normalization.config.json). `python -m chinese_workflow.ingest lines ...`
forwards to the line extractor CLI (chinese_workflow.ingest.lines).
"""

from __future__ import annotations

import sys

from .run import main

if __name__ == "__main__":
    sys.exit(main())
