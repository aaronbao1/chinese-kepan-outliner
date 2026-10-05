# PROVENANCE: D8842 / cbeta-mulu-kepan

Gold outline of 般若心經註解 (D14n8842, 日本 釋圓耳撰, CBETA canon D vol. 14), built directly from
CBETA's own `cb:mulu type="科判"` markup — an *explicit* structural gold that needs no alignment
step (R02 G10). `scheme_id: cbeta-mulu-kepan`, `outline_mode: self-outlining`, `commentary_id:
null`, `root_text_id: D14n8842`, `source_document.kind: root-text`, `node_class: sutra-span` on
every node with a resolved `locations.root_text` (`basis: cbeta-mulu`) — this follows
`context/baseline/outline-schema-zh.json`'s own named example for X11n0268, verbatim.

See `X0268/cbeta-mulu-kepan/PROVENANCE.md` for the shared design (node_class, outline_mode /
commentary_id / root_text_id, licence): identical reasoning, restated here only where this file
differs.

| File | What |
|---|---|
| `outline.json` | Built by `chinese_workflow.eval.gold.cbeta_mulu`. Never edit it by hand. Rebuild with `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.cbeta_mulu` (builds all three `cbeta-mulu-kepan` golds) |

## Review status: `imported-unchecked`, `seeded_by: null` — see X0268's PROVENANCE.md.

## Tree construction, in numbers

- 40 `cb:mulu type="科判"` nodes, source `@level` 1-10, **zero level jumps** (matching R02 F28's
  survey figure exactly; `built.jump_count == 0`, `built.node_count == 40`,
  `built.max_source_level == 10`). This is the cleanest of the three files: one level-1 root
  (`科此經為二`) and a single well-nested tree below it.
- `child_count_announced` (one-line summary; full detail follows): read from a trailing
  parenthesised CJK numeral (always kept, `count_mismatch` flagged on disagreement) or a bare
  trailing numeral (kept only when it already matches the children present) — never invented. This
  file uses **only the bare-trailing-numeral convention**, never
  parentheses ("科此經為二" -> 2, "次本文二" -> 2, "初經家㨿行標起又四" -> 4 — no "(N)" anywhere in
  the file). 16 of 40 nodes self-verify (the bare numeral equals the children actually present) and
  get `child_count_announced` set; the file has no `count_mismatch` cases — every branching node's
  announced count matches its children exactly, checked node by node against an indented
  dump of the file while designing `cbeta_mulu.py`; `scripts/validate_outline.py` rechecks it on
  every run (its `[child-count]` rule warns on any node whose announced count differs from its
  children, and this gold has no warning).
- **Not** extracted for X11n0268 or P167n1573: those two files use the parenthesised convention as
  their primary marker, and this module only accepts a *bare* trailing numeral when it already
  matches the children present (self-verified), never inventing or asserting one that does not —
  see `cbeta_mulu.py`'s module docstring, "child_count_announced".

## Well-formedness (a file whose tree is not well formed would be skipped, with the reason logged)

Included: this is the most straightforward of the three files, with a single, cleanly-levelled
tree from source level 1 to 10 and no jumps at all. 40 matches R02 F15's count exactly
(`tests/unit/test_gold_cbeta_mulu.py::test_real_golds_match_survey` checks it against
`data/raw/cbeta/survey/mulu-nodes-kepan.tsv`).

## Editions

| File | Release | sha256 (computed; the checksum authority is the pinned xml-p5 clone commit, which `scripts/fetch_cbeta_xml_p5.sh` checks, so there are no per-file `scripts/CHECKSUMS` lines) |
|---|---|---|
| `data/raw/cbeta/xml-p5/D/D14/D14n8842.xml` (般若心經註解, 日本 釋圓耳撰; header `$Date` 2025-01-30) | CBETA xml-p5, git tag `2026R2`, commit `dbdea41071e1e260ad84b72faefd4587333cf76d` (R02 F15) | `97452c581188cc58b3feac25235a1dd4a3c222a1ad156d6a182f6382908e615a` |

Lineheads are stable only together with the release (R02 F13, F18). The raw files are gitignored;
fetch them with `scripts/fetch_cbeta_xml_p5.sh`. `metadata.source_sha256` repeats the digest above.

## Licence

CC BY-NC-SA 4.0 (`licence.id: CC-BY-NC-SA-4.0`), with CBETA's notice and release label `2026R2`;
`eval_only: false` (the licence permits redistribution). See `data/reference-outlines/NOTICE` and
`X0268/cbeta-mulu-kepan/PROVENANCE.md` for the full statement — identical here. D14n8842 is from
「國家圖書館善本佛典」 (Selections from the Taipei National Central Library Buddhist Rare Book
Collection, per its own `titleStmt`), listed by name in Category A of
`data/raw/cbeta/LICENCE-NOTICE.txt` (the snapshot of https://cbeta.org/copyright; CC-released).
