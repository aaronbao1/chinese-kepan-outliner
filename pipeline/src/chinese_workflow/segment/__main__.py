"""python -m chinese_workflow.segment --target SOURCE [--span A..B] [--outlined-text PATH]
[--strategy 1|2] --out sentences.json

Input/Output: see chinese_workflow.segment.segment (target text + outlined-text -> sentences/1).
"""

from __future__ import annotations

import sys

from .segment import main

if __name__ == "__main__":
    sys.exit(main())
