"""chinese_workflow.common — what every stage may import (docs/outliner-design.md §2).

  paths        repository locations (REPO_ROOT, DATA, the registry, the validator)
  jsonio       UTF-8 JSON I/O, sha256 of files and of canonical JSON
  lineheads    CBETA linehead grammar: split, strip the ':<n>' offset, file id, document order
  outline_doc  draft tree -> numbered zh-kepan prediction document; in-process validation
  splits       the split guard over data/eval-sets.json (test / reserve / OOD refused unless frozen)

Stages import only this package, chinese_workflow.llm and chinese_workflow.ingest library functions
(tests/unit/test_stage_boundaries.py).
"""
