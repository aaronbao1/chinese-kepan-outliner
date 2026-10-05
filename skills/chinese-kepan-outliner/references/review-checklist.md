# Review checklist for a predicted outline (the human step after the resolver)

A predicted outline mixes the commentator's own (explicit) divisions with nodes a model inferred, so a person reviews it before it is used or scored. Review in this order and record every decision in the node's `notes` ("review 2026-MM-DD <initials>: kept / moved / deleted / renamed — reason").

1. **Validation first.** `python -m chinese_workflow.outline validate outline.json` shows 0 errors. Warnings to read: `[child-count]` (announced count ≠ children found — a missed or extra child), `[sibling-order]` in sūtra mode, `[announce-after-explain]`.
2. **Inferred nodes, lowest `confidence` first.** For each: is there a division in the text at all (not a doctrinal list)? Is the parent right? Is the span inside the parent's span and in order? Is `scheme_id` the project's scheme (or `model-…` for a model-only outline)? Delete what the text does not support; never promote an inferred node to `explicit` — an explicit node needs a marker in the commentary.
3. **`unmapped` nodes.** A sūtra-span node with no root span: find the lemma by hand or leave it unmapped with a note; do not guess a line.
4. **The parser report** (`outline-report.json` → `tier2.report`, `tier2.rejected`): an announcement the parser could not attach, a list it rejected as doctrinal. Each needs a decision (attach under a named node / confirm the rejection).
5. **Level 1.** In sūtra mode, the top level is the commentator's scheme. If it came from the project's scheme prior (`origin: editorial`), check that the project cites where the commentator states it.
6. **Headings.** `heading_src` is the text's own wording (label rule of `tests/fixtures/kepan-formulae/README.md`); `heading_en` is a gloss with its provenance in `notes` — correct wording, never the Chinese.
7. **Chunks.** In `chunks.md`, every taken-up marker precedes the node's first chunk; no chunk runs over 6 sentences except `split-leaf` windows; announcement lines follow the chunk that announces them. `python -m chinese_workflow.eval.chunk_invariants` passes.
8. **Before any score.** A reviewed prediction is still a prediction. Promotion to a gold (`gold_status: reviewed`) is a human act with `seeded_by` kept (R06 F19).
