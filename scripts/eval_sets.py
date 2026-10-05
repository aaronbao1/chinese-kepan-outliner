#!/usr/bin/env python3
"""scripts/eval_sets.py — recompute (--write) or check (--check, the default) the computed parts of the
eval-set registry data/eval-sets.json and the tables of its guide data/EVAL-SETS.md.

A thin CLI wrapper: the logic, and the read access a scorer uses (load_registry, dataset, split_of,
split_spans, served_juan_halves, in_scoring_scope), live in chinese_workflow.eval.registry
(pipeline/src/chinese_workflow/eval/registry.py), which is standard library only, so any python3 runs
this without the pipeline's virtualenv.

Usage : python3 scripts/eval_sets.py [--check | --write] [--registry PATH] [--guide PATH]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "src"))

from chinese_workflow.eval.registry import main

if __name__ == "__main__":
    sys.exit(main())
