# PROVENANCE: P1573 / cbeta-mulu-kepan

Gold outline of 修懺要旨 (P167n1573, 宋 知禮述, CBETA canon P vol. 167), built directly from CBETA's
own `cb:mulu type="科判"` markup — an *explicit* structural gold that needs no alignment step (R02
G10). `scheme_id: cbeta-mulu-kepan`, `outline_mode: self-outlining`, `commentary_id: null`,
`root_text_id: P167n1573`, `source_document.kind: root-text`, `node_class: sutra-span` on every
node with a resolved `locations.root_text` (`basis: cbeta-mulu`) — this follows
`context/baseline/outline-schema-zh.json`'s own named example for X11n0268, verbatim.

See `X0268/cbeta-mulu-kepan/PROVENANCE.md` for the shared design (node_class, outline_mode /
commentary_id / root_text_id, licence): identical reasoning, restated here only where this file
differs.

| File | What |
|---|---|
| `outline.json` | Built by `chinese_workflow.eval.gold.cbeta_mulu`. Never edit it by hand. Rebuild with `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.cbeta_mulu` (builds all three `cbeta-mulu-kepan` golds) |

## Review status: `imported-unchecked`, `seeded_by: null` — see X0268's PROVENANCE.md.

## Tree construction, in numbers

- 127 `cb:mulu type="科判"` nodes, source `@level` **2-15** (R02 F15) — this file's tree, unlike
  X11n0268's, does not start at source level 1. `metadata.max_depth` in `outline.json` is **14**,
  not 15: the structural `level` this gold assigns is always `parent.level + 1` (never the raw
  source `@level`, module docstring), and since the whole file's first node opens at source level 2
  with no source-level-1 ancestor anywhere before it, every node's structural level is its source
  level minus 1 (source levels 2-15 -> structural levels 1-14). This is not a mismatch to fix; it
  is the intended behaviour of "never invent a node", applied uniformly.
- **2 nodes flagged `irregular_label`** for opening at a source level other than 1 with no
  shallower node pending — i.e. two separate top-level structural roots, each carrying a note
  giving its true source level:
  - `○要旨分二` (source level 2, the very first `cb:mulu` of the file) — structural root 1.
  - `分三` (source level 2, opening a second top-level run once the first root's subtree closes) —
    structural root 2.

  Both are genuine features of the source (知禮's 科判 apparently divides this short text into two
  independently-headed top-level parts, `○要旨分二` and `分三`, rather than one single level-1 root
  over both), not parser artefacts: `built.jump_count == 2` is asserted by
  `tests/unit/test_gold_cbeta_mulu.py`, and the rest of each subtree nests cleanly below its root
  with no further jumps.
- `child_count_announced` (one-line summary; full detail follows): read from a trailing
  parenthesised CJK numeral (always kept, `count_mismatch` flagged on disagreement) or a bare
  trailing numeral (kept only when it already matches the children present) — never invented.
  Verified for 47 of 127 nodes (both the parenthesised convention, e.g. `初緫題(三)` -> 3, and the
  bare convention self-verified against actual children, e.g. root `分三`'s bare trailing "三" -> 3,
  matching its three children 初體性元徧/二體德圓具/三體量隨徧). 2 nodes are flagged `count_mismatch`
  (announced count kept, disagreement noted, not dropped).

## Well-formedness (a file whose tree is not well formed would be skipped, with the reason logged)

Included. The two source-level-2 roots above are the only irregularity; every other node nests
cleanly (127 total matches R02 F15's count exactly; `tests/unit/test_gold_cbeta_mulu.py::test_real_golds_match_survey`
checks it against `data/raw/cbeta/survey/mulu-nodes-kepan.tsv`), so there is no ambiguous nesting
or orphaned node that would call for skipping this file.

## Editions

| File | Release | sha256 (computed; the checksum authority is the pinned xml-p5 clone commit, which `scripts/fetch_cbeta_xml_p5.sh` checks, so there are no per-file `scripts/CHECKSUMS` lines) |
|---|---|---|
| `data/raw/cbeta/xml-p5/P/P167/P167n1573.xml` (修懺要旨, 宋 知禮述; header `$Date` 2025-01-30) | CBETA xml-p5, git tag `2026R2`, commit `dbdea41071e1e260ad84b72faefd4587333cf76d` (R02 F15) | `296df96888af8d9e48c3fb44e25d700fcaefe8f1d77d0bde9d4c1251d8468197` |

Lineheads are stable only together with the release (R02 F13, F18). The raw files are gitignored;
fetch them with `scripts/fetch_cbeta_xml_p5.sh`. `metadata.source_sha256` repeats the digest above.

## Licence

CC BY-NC-SA 4.0 (`licence.id: CC-BY-NC-SA-4.0`), with CBETA's notice and release label `2026R2`;
`eval_only: false` (the licence permits redistribution). See `data/reference-outlines/NOTICE` and
`X0268/cbeta-mulu-kepan/PROVENANCE.md` for the full statement — identical here. P167n1573 is from
《永樂北藏》 (Northern Yongle Edition of the Canon, per its own `titleStmt`), listed by name under
"歷代藏經補輯" in Category A of `data/raw/cbeta/LICENCE-NOTICE.txt` (the snapshot of https://cbeta.org/copyright; CC-released, alongside 房山石經
and 趙城金藏).
