"""chinese_workflow.outline.tier2 — the stateful kēpàn formula parser (docs/outliner-design.md §5.2).

Input : an ingest.text.InputText (a commentary span in sūtra mode, a treatise in self-outlining mode) and
        the tier-1 anchors inside it: [{"anchor": linehead, "heading_src", "part_type"}], document order.
Output: Tier2Result(by_anchor, report, rejected, genre_gate, stats): explicit draft nodes per anchor
        (None = text before the first anchor), the parser report (what rules could not decide; under a
        no-structure genre gate, which builds no node, also the statements it saw: gated-announcement /
        gated-enter / gated-close), the announcements the doctrinal-list filter rejected, the genre-gate
        decision, and counts.

    parse(text, *, anchors, mode="sutra", config=None) -> Tier2Result
    detect(snippet, *, mode="sutra", title=None) -> [statement dicts]   (unit tests, cases.jsonl)

Modules: formulae (inventory: numerals, classifiers, patterns), scanner (statements with offsets),
labels (listings and the label rule), filters (doctrinal-list filter, genre gate), parser (the state
machine and draft nodes). Provenance of the rules: R01 F3/F13/F21-F24 (formula table), R07 F2 (genre
gate, non-structural lists), R07 F17 and R03 F25 (Kuiji variants), the T1723 陀羅尼品 dev subtree of the
Kuiji gold (wrapper nodes, explained positions), tests/fixtures/kepan-formulae/README.md (label rule).
Imports only chinese_workflow.common / chinese_workflow.ingest and this package.
"""

from .parser import DEFAULT_CONFIG, Tier2Result, detect, parse

__all__ = ["DEFAULT_CONFIG", "Tier2Result", "detect", "parse"]
