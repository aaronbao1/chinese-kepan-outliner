# PROVENANCE: X0268 / cbeta-mulu-kepan

Gold outline of 楞嚴經集註 (X11n0268, 宋 思坦集註, CBETA canon X vol. 11), built directly from CBETA's
own `cb:mulu type="科判"` markup — an *explicit* structural gold that needs no alignment step (R02
G10). `scheme_id: cbeta-mulu-kepan`, `outline_mode: self-outlining`, `commentary_id: null`,
`root_text_id: X11n0268`, `source_document.kind: root-text`, `node_class: sutra-span` on every
node with a resolved `locations.root_text` (`basis: cbeta-mulu`) — see "node_class / outline_mode"
below: this follows `context/baseline/outline-schema-zh.json`'s own named example for X11n0268,
verbatim.

| File | What |
|---|---|
| `outline.json` | Built by `chinese_workflow.eval.gold.cbeta_mulu`. Never edit it by hand. Rebuild with `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.cbeta_mulu` (builds all three `cbeta-mulu-kepan` golds) |

There is no `outline.txt`: unlike the authored golds (`authored.py`), every field here is mechanically
read off CBETA's own `cb:mulu` elements (level, text, line), so there is nothing for a human to
transcribe — `cbeta_mulu.py`'s docstring is the format description, and `tests/unit/test_gold_cbeta_mulu.py`
is the source-of-truth check.

## Review status: `imported-unchecked`

- `gold_status: imported-unchecked`, `seeded_by: null` (nothing is machine-drafted or hand-drafted;
  every field is read mechanically off the XML).
- Not checked against any secondary source: not against the printed chart 首楞嚴經指文科節 (No.
  268-F, front matter, itself outside this markup's coverage, see "Coverage" below), not against a
  modern edition, not against another 科判 of the same sutra. The file records no source for this
  markup, so whose it is (思坦's own 集註, a later CBETA/DILA editorial pass, or a mix) is not
  known. A survey of the file (R02 F28) found it finer than the printed chart: of the 2,494 node
  labels of three or more characters, 493 occur in the chart and 1,984 occur nowhere else in the
  file.
- What a check would mean: for a sample of nodes, read the surrounding 集註 prose (`cb:div
  type="orig"` for the quoted sutra passage, `type="commentary"` for 思坦's gloss) and confirm the
  heading actually describes what follows; cross-check the 1,984 labels that occur nowhere
  else in the file against a second edition if one turns up.

## Who, how, when

- Built 2026-09-22 by Claude (claude-opus-5-5) as Task 7 of the plan that built the evaluation sets
  (not part of this repository), mechanically: `chinese_workflow.ingest.lines.extract()` gives every `cb:mulu` on its own-canon
  line (X-canon here, never the paired R017 line, R02 G16a); `cbeta_mulu.build_tree` nests them by
  source `@level` (module docstring), never inventing a node.
- Every heading is CBETA's own text, gaiji already resolved by `ingest.lines` (e.g. the level-27
  node quoting <g ref="#CB04474">㳷</g> reads as 㳷 in `heading_src`).

## Tree construction, in numbers

- 2,611 `cb:mulu type="科判"` nodes, source `@level` 1-28, every level present, **zero level jumps**
  (R02 F28: "every level present and no level skipped between consecutive nodes" — confirmed here,
  not merely assumed: `built.jump_count == 0`). Structural `level` therefore equals source `@level`
  everywhere in this file; `metadata.max_depth == 28` matches `metadata.nodes_per_level`'s own
  histogram, which reproduces R02 F28's verified per-level counts (3, 10, 23, 34, 52, 62, 78, 133,
  250, 302, 261, 298, 276, 172, 105, 96, 50, 57, 51, 58, 52, 42, 43, 37, 37, 18, 9, 2 for levels
  1-28) exactly — `tests/unit/test_gold_cbeta_mulu.py::test_x0268_level_histogram_matches_r02_f28`.
- 3 level-1 roots: 初序分(二), 二正宗分(六), 三流通分(二).
- 1 node flagged `merged_range`: the level-4 node at X11n0268_p0185a08 (source line 1859) holds
  two labels in one `cb:mulu` element, joined by a full-width space in the source —
  "二緣覺眾　三菩薩眾" — kept as one node, `heading_src` verbatim, rather than split into two nodes
  the source does not itself divide.
- `child_count_announced` (one-line summary; full detail below): read from a trailing
  parenthesised CJK numeral (always kept, `count_mismatch` flagged on disagreement) or a bare
  trailing numeral (kept only when it already matches the children present) — never invented.
- 1,105 nodes carry a trailing parenthesised CJK-numeral announcement ("初序分**(二)**" -> 2), the
  convention this file uses throughout. 7 of those disagree with the children actually present in
  this gold's tree and are flagged `count_mismatch` (kept, not dropped — e.g. a level-25 node
  "二總破諸法(二)" at X11n0268_p0286a18 announces 2 but has **no** `cb:mulu` children of its own in
  this tree; the same heading text recurs elsewhere in the file at level 6 *with* two children —
  the source reuses phrasing across parallel branches, and CBETA's markup does not subdivide every
  occurrence to the same depth). No bare (unparenthesised) trailing numeral in this file
  self-verifies against different children than its parenthesised counterpart would (X11n0268 does
  not use the bare convention).

## node_class / outline_mode: `sutra-span` / `self-outlining` (the schema's own named example)

`context/baseline/outline-schema-zh.json` names X11n0268 twice, for exactly this markup:
`source_document.kind` `"root-text"` is defined as "stated in, or marked up on, the outlined text
itself (a self-outlining treatise; CBETA cb:mulu type=科判 markup as in X11n0268, R02 F28)", and
`root_text_span.basis` `"cbeta-mulu"` is defined as "the lb preceding a CBETA cb:mulu 科判 node
(X11n0268, R02 F28)". This gold follows both directly:

- `outline_mode: "self-outlining"` (the outlined text states its own divisions, in its own
  `cb:mulu` markup); `source_document.kind: "root-text"`; `root_text_id: "X11n0268"`;
  `commentary_id: null` (the schema's hard constraint for this mode).
- `node_class: "sutra-span"` on every one of the 2,611 nodes: in self-outlining mode this means the
  node divides the outlined text itself, which every `cb:mulu type="科判"` node does by
  construction — there is no separate "commentary discourse" to set apart from "root text" when the
  outlined text states its own outline over itself. `locations.root_text` is therefore populated on
  every node, never null, and no node needs flag `unmapped`.
- `root_text.basis: "cbeta-mulu"`; `start` = the same linehead as `locations.commentary.explained`
  (checked, not assumed: every `cb:mulu type="科判"` in this file sits at offset 0 of its line — the
  very first thing after the `<lb>` that opens it — across all 2,611 nodes, so "the lb preceding
  the mulu" and "the lb the mulu sits on" are the same line in every case,
  `tests/unit/test_gold_cbeta_mulu.py::test_every_kepan_mulu_sits_at_offset_0_of_its_line`); `end`
  is the inclusive last own-canon line before the next node that is not this node's descendant
  (`end_basis: "next-node"`), computed bottom-up so a child's span always lies inside its parent's
  (`scripts/validate_outline.py` `[child-outside-parent]`, checked clean under `--strict`). The
  file's very last node, 二經家結流通, has no successor: its `end` is the file's own last own-canon
  line, `X11n0268_p0704a06` (`end_basis: null`, noted) — matching R02 F28's "juan 10 closes at
  0704a06" exactly.

(An earlier version of this gold set `outline_mode: "sutra"`, `commentary_id: "X11n0268"`,
`root_text_id: null`, `node_class: "commentary-internal"` on every node with `root_text: null`,
reading `commentary_id` as "the document that states the outline" independently of whether it was
also the root text, and called this a deliberate divergence from the schema's own docstring. A
review of that build found this read the schema's own `source_document.kind` /
`root_text_span.basis` definitions against their own worked example naming X11n0268; it was
corrected on 2026-09-22 to the assignment above.)

## R017 lineheads (R02 F28/G16a)

X11n0268 is one of the X-canon files where every line also carries a second edition's `lb`: an
adjacent `<lb ed="R017"/>` pairs with every `<lb ed="X"/>`. `chinese_workflow.ingest.lines` composes
this gold's `locations.commentary.{announced,explained}` from the file's **own X-canon** linehead
only (R02 G16a: the survey script's raw `prev_lb()` takes the nearest `lb` regardless of `@ed`,
which is why `data/raw/cbeta/survey/mulu-nodes-kepan.tsv`'s `prev_lb` column holds R017 numbers for
this file — this gold does not repeat that mistake). Every node whose line carries an R017 pairing
gets a note recording it (e.g. "this line also carries an R017 linehead R017_p0021a10 … this gold
uses only the file's own X-canon linehead"), so the information is not lost, only kept out of the
structural `locations` fields.

## Coverage

- The whole body, 首楞嚴經集註 juan 1-10 (X11n0268_p0180a12-p0703a15): every `cb:mulu type="科判"`
  node in the file.
- **Not** covered: the front matter, No. 268-A-F (X11n0268_p0165a01-p0180a02: four prefaces, the
  釋題, and the printed chart 首楞嚴經指文科節 itself) — it carries no `cb:mulu type="科判"` (R02
  F28).

## Editions

| File | Release | sha256 (computed; the checksum authority is the pinned xml-p5 clone commit, which `scripts/fetch_cbeta_xml_p5.sh` checks, so there are no per-file `scripts/CHECKSUMS` lines) |
|---|---|---|
| `data/raw/cbeta/xml-p5/X/X11/X11n0268.xml` (楞嚴經集註, 宋 思坦集註; header `$Date` 2026-07-13) | CBETA xml-p5, git tag `2026R2`, commit `dbdea41071e1e260ad84b72faefd4587333cf76d` (R02 F15/F25) | `a57eb812e914db28346b713b91fcc0004be5e0602d8581f0d5bd01a1cb5de807` |

Lineheads are stable only together with the release (R02 F13, F18). The raw files are gitignored;
fetch them with `scripts/fetch_cbeta_xml_p5.sh`. `metadata.source_sha256` repeats the digest above.

## Licence

CC BY-NC-SA 4.0 (`licence.id: CC-BY-NC-SA-4.0`), with CBETA's notice and release label `2026R2`.
See `data/reference-outlines/NOTICE`, which reproduces CBETA's 版權宣告 verbatim from
`data/raw/cbeta/LICENCE-NOTICE.txt`; 卍新纂續藏經 vols. 1-90 (X11n0268's canon) is explicitly listed
there among the CC-released volumes (CBETA's copyright page, https://cbeta.org/copyright,
fetched 2026-09-22).

The data is CBETA-derived: every heading is CBETA text (its own `cb:mulu` markup) and every
location a CBETA linehead (`data/EVAL-SETS.md` rule 2). It is for non-commercial use only
and is never relicensed permissively. `eval_only: false`, matching `T0262/kuiji-xuanzan`'s
treatment: the licence permits redistribution, even though this gold's *use* is restricted to the
out-of-domain evaluation split (`data/EVAL-SETS.md` rule 5), never as prompt or training material for a
system later scored against it.

Not settled: whether CBETA regards a table of headings and lineheads as 改作 (adaptation), which its
notice places outside the CC licence and for which it asks users to contact the rights holders.
Also open, and separate from licensing: whose 科判 this is — 思坦's own, a later CBETA/DILA pass,
or a mix (no source is recorded in the file; see "Review status").
