"""chinese_workflow.runner — the headless harness (docs/outliner-design.md §11; plan TR6).

    python -m chinese_workflow.runner run projects/<id>/project.toml [--out DIR] [--frozen TAG]

runs ingest -> outline -> segment -> chunk -> chunk invariants -> export for one project and writes one run
directory with run.json. The runner is the only module that imports several stages; each stage still
talks to the next through the files it writes.
"""
