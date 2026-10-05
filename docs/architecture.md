# Architecture of the Chinese kēpàn pipeline

This document describes the pipeline as it is in this repository. The outliner is the version frozen for experiment E07 as `outliner-v1-frozen-2026-10-03`; the tag is kept in the development repository, and this copy's code is that version plus changes that leave outline output unchanged (a clearer error for a CBETA file that has not been fetched, packaging metadata, the quickstart script, the fetch script, tests and documentation). The module-level design (algorithms, file contracts, command-line options, the scorer's rules) is in [`outliner-design.md`](outliner-design.md). The divergences from the Tibetan workflow this project parallels are in [`chinese-workflow-mapping.md`](chinese-workflow-mapping.md), and the terms in [`glossary.md`](glossary.md).

The repository holds:
- one Python package with one subpackage per stage (`pipeline/src/chinese_workflow/`);
- a Claude skill that walks a session through the outliner (`skills/chinese-kepan-outliner/`);
- the outline schemas (`context/baseline/`);
- gold outlines and their registry (`data/reference-outlines/`, `data/eval-sets.json`);
- five example projects (`projects/`) and the experiment records (`experiments/`).

There is no server, database or scheduler: a run is a directory, and a stage is a function with a command line.

Five stages are built: `ingest`, `outline`, `segment`, `chunk` and `export`, plus `eval` and a runner that chains them. The `context` and `translate` stages are stubs: each package holds a README with its planned contract and an `__init__.py` with a docstring, and no code.

Rules the code keeps:
- **Stages talk through files and objects.** A stage imports only `chinese_workflow.common`, `chinese_workflow.llm`, `chinese_workflow.ingest` and its own package; the outliner never reaches into the translator. `tests/unit/test_stage_boundaries.py` checks the imports statically.
- **CBETA's text is never altered.** Every offset indexes CBETA's characters and punctuation as they are. Where a step needs a normalized view (matching that ignores punctuation), it is computed with an offset map, never written back.
- **Deterministic first, model where rules stop.** The whole pipeline runs with no model. A model enters only through the resolver and the gloss (§3.2), and only when a project asks for one.
- **Split blindness is enforced by code.** No stage reads a test or reserve span of T1718 or T1723, or scores against an out-of-domain gold, unless a frozen outliner is named; out-of-domain golds are never inputs (`common/splits.py`; [`outliner-design.md`](outliner-design.md) §3).

## 1. Data flow

```
 CBETA TEI P5 XML, release 2026R2 (data/raw/cbeta/, fetched by scripts/fetch_cbeta.sh)
   sūtra mode:          the root text (e.g. T09n0262) + its designated commentary (e.g. T34n1723)
   self-outlining mode: one text that announces its own divisions (e.g. T32n1666)
          │
          ▼
   ┌───────────┐   input-text: <id>.txt (CBETA's characters and punctuation), <id>.lines.jsonl,
   │  ingest   │   <id>.structure.json (lines, 卷, cb:mulu, heads, verse, notes …),
   └───────────┘   normalization.config.json (regime "none")
          │
          ▼
   ┌───────────┐   tier 1 (cb:mulu) → tier 2 (formula parser) → merge → scheme prior → number
   │  outline  │   → anchor (root spans) → validate / repair → out-of-span classification
   │           │   → resolver + gloss (model adapter; off by default) → validate / repair
   └───────────┘   → span starts → validate → outlined-text → render
          │
          ├──► independent outline   outline.json (zh-kepan), outline.md, outline.docx
          │
          └──► outlined-text         outlined-text.json (node → character spans of the target text),
                     │               outlined-text.md, target.txt
                     ▼
              ┌───────────┐
              │  segment  │──► sentences.json (strategy 1 or 2, rule recorded)
              └───────────┘
                     ▼
              ┌───────────┐   outlined-and-chunked-text (interlinear outline):
              │   chunk   │──► chunks.json, chunks.md, chunks.docx; invariants.json
              └───────────┘
                     ▼
              ┌ ─ ─ ─ ─ ─ ┐
                 context      stub: per-chunk context bundle (not built)
              └ ─ ─ ─ ─ ─ ┘
              ┌ ─ ─ ─ ─ ─ ┐
                translate     stub: chunk-by-chunk draft, stitched in outline order (not built)
              └ ─ ─ ─ ─ ─ ┘

 outline.json ──► export ──► <text>.<scheme>.jsonld   (BDRC-shaped JSON-LD for a knowledge graph)
 outline.json ──► eval.score ◄── gold outline (data/reference-outlines/, or eval-only data/raw/dila-sdp/gold/)
                      └──► metrics.json
 chunks.json + outlined-text.json + sentences.json ──► eval.chunk_invariants ──► invariant report
```

`python -m chinese_workflow.runner run projects/<id>/project.toml` runs this chain for one project, from the outline build to the export ([`outliner-design.md`](outliner-design.md) §11). Every stage also has its own command line (§3).

## 2. Artefacts and the run directory

A run writes one directory, by default `data/processed/<project id>/` (gitignored); `--out` changes it. It is reproducible from `data/raw/` and the pipeline commit recorded in `run.json`.

```
data/processed/<project id>/
  run.json             project, sha256 of the project config, pipeline commit and dirty flag, date,
                       CBETA release, input files and their sha256, frozen tag, resolver config,
                       model-call ledger, per-stage counts, split-guard report
  input-text/          <id>.txt, <id>.lines.jsonl, <id>.structure.json for the text that states the
                       outline and for the target text; normalization.config.json (one file per
                       directory, so it holds the config of the last text ingested, the target)
  outline/             outline.json, outline.md, outline.docx, outlined-text.json, outlined-text.md,
                       target.txt, outline-report.json; llm/ (model cache and request files) when a
                       model adapter ran
  segment/             sentences.json
  chunk/               chunks.json, chunks.md, chunks.docx, invariants.json
  export/              <text_id>.<scheme_id>.jsonld, id-history.json
```

How the workflow's artefacts map onto these files:

| Workflow artefact | Our file(s) | Notes |
|---|---|---|
| input-text | `input-text/<id>.txt` + `.lines.jsonl` + `.structure.json` | exactly CBETA's characters and punctuation; normalization only through a recorded config, and the shipped regime is `none` |
| variorum-text | (none) | not built; the Taishō apparatus side-table would be a partial one (D2) |
| independent outline | `outline/outline.json`, `outline.md`, `outline.docx` | the JSON is the contract; the `.md` and `.docx` views are rendered from it ([`outliner-design.md`](outliner-design.md), "Output formats") |
| outlined-text | `outline/outlined-text.json` + `.md` | the outline plugged back into the target text (§5) |
| sentence boundaries | `segment/sentences.json` | with the strategy and rule recorded (D7) |
| outlined-and-chunked-text (interlinear outline) | `chunk/chunks.json`, `chunks.md`, `chunks.docx` | blank-line separated chunks with outline markers and announcement lines (D6, D14, D16) |
| context, draft translation | (none) | the `context` and `translate` stages are stubs |

The target text is the text the outlined-text and the chunks are over: the commentary or the root text (`target_role` in the project file). In self-outlining mode it is the text itself.

## 3. Stage contracts

| Stage | Input → output | Deterministic or model | Command | Status |
|---|---|---|---|---|
| `ingest` | one CBETA P5 XML file and a span → input-text, `structure.json`, normalization config | deterministic | `python -m chinese_workflow.ingest run SOURCE --role root\|commentary --out DIR [--span FIRST..LAST]` | built; `apparatus.json` not built |
| `outline` | the text that states the outline (the commentary in sūtra mode, the text itself in self-outlining mode), the root text in sūtra mode, a span, a scheme → `outline.json`, `.md`, `.docx`, `outlined-text.json`, `.md`, `outline-report.json` | deterministic; the resolver and gloss call a model when an adapter is set | `python -m chinese_workflow.outline build --project projects/<id>/project.toml --out DIR` | built |
| `segment` | target text + `outlined-text.json` → `sentences.json` | deterministic (strategies 1–2) | `python -m chinese_workflow.segment --target SOURCE --outlined-text PATH --out sentences.json` | built; the model-assisted strategy 3 is not |
| `chunk` | `outline.json` + `outlined-text.json` + `sentences.json` + target text → `chunks.json`, `.md`, `.docx` | deterministic (D14) | `python -m chinese_workflow.chunk --outline … --outlined-text … --sentences … --target … --out DIR` | built |
| `context` | a chunk record + outline → context bundle | — | — | stub |
| `translate` | chunk + context bundle + Project Instructions → draft | — | — | stub |
| `eval` | `outline.json` + a registered gold → `metrics.json`; chunk artefacts → invariant report | deterministic | `python -m chinese_workflow.eval.score --pred outline.json --gold <dataset id>`; `python -m chinese_workflow.eval.chunk_invariants chunks.json outlined-text.json sentences.json` | built |
| `export` | `outline.json` → BDRC-shaped JSON-LD | deterministic | `python -m chinese_workflow.export OUTLINE.json --out OUT.jsonld` | built (v0) |

The stage commands that read CBETA text or a gold apply the split guard themselves and take `--frozen TAG` to name a frozen outliner. The skill `skills/chinese-kepan-outliner/SKILL.md` gives a Claude Code session the same procedure step by step and names the command each step calls.

### 3.1 `ingest`

Reads one CBETA P5 XML file, named by file id (resolved under `data/raw/cbeta/`, then the whole-corpus clone `data/raw/cbeta/xml-p5/`) or by path, and restricted to a span of lineheads when one is given. It writes:
- `<id>.lines.jsonl`: one record per CBETA line, the canonical input of every later stage;
- `<id>.txt`: the reading text, i.e. the lines concatenated without a separator, so that a character offset indexes it directly;
- `<id>.structure.json` (`structure/1`): per-line start offsets and 卷 numbers, and the elements `juan`, `mulu`, `head`, `jhead`, `verse`, `note`, `caesura`, `gaiji` and `unclear`, each with its linehead and global character offset;
- `normalization.config.json`: regime `none` (no normalization is applied), the punctuation the file declares, gaiji routes and the notes policy (inline notes kept in the text, others excluded).

Matching that ignores punctuation goes through an offset-mapped view (`ingest/lines.py`: `strip_punct`, `TextIndex.stripped()`, `find_spans(…, ignore_punct=True)`). The Taishō apparatus side-table (`apparatus.json`, D2) is not built.

### 3.2 `outline`, the kēpàn outliner

One build (`outline/pipeline.py`) runs these steps:
1. **Tier 1** reads CBETA's `cb:mulu` table of contents. 品 and other typed units become nodes; 卷 are recorded apart. A file with 科判-typed `cb:mulu` yields a full kēpàn.
2. **Tier 2** is a stateful parser of the commentary's division formulae (lemma units, announcements, entry markers, gates), with a doctrinal-list filter and a genre gate.
3. **Merge** puts the tier-2 drafts under their tier-1 品.
4. **The scheme prior** builds the level-1 parts a project declares, when the run does not read the commentator's own statement of them.
5. **Numbering** gives ids, paths, sibling indices, indicators and 干支 labels.
6. **The anchor** places each node's lemma in the root text (§5).
7. **Validate and repair**: local order and containment errors are repaired and reported.
8. **Out-of-span classification** marks the nodes whose announced extent lies beyond their 品, so that no model is asked to place them.
9. **The resolver and the gloss** run when the project sets `source = "hybrid"` and a model adapter.
10. **Span starts, outlined-text, render**: a last validation, then the outlined-text and the renders.

Every node records its origin: `explicit` (read from markup or formulae), `editorial` (from the scheme prior, or a 品 carried above a span that starts inside it), `inferred` (from the model, confidence < 1) or `imported` (golds only). Explicit nodes are never changed by a later step, except by the logged repairs. The build fails only on errors the repair step does not cover, and it writes every artefact first.

Model-assisted steps. The resolver has three tasks:
- `root-spans` places nodes the anchor left `unmapped`;
- `subdivide` divides long leaves, up to three levels at a time;
- `adjudicate` decides the parser-report entries.

The gloss writes `heading_en`. Requests go through `chinese_workflow.llm`, which caches answers by request hash and validates every answer against a JSON Schema. It has four adapters: `none` (the default: no model call), `replay` (a recorded cassette), `claude` (the Anthropic API) and `interactive` (a Claude Code session answers request files). Module-level detail: [`outliner-design.md`](outliner-design.md) §5 and §10.

The two modes:
- *Sūtra mode*: the parser reads the designated commentary; nodes carry commentary positions and a root-text span.
- *Self-outlining mode*: the parser reads the text's own announcements.

Both modes produce the same artefacts.

### 3.3 `segment`

Two strategies, recorded in `sentences.json`:
- Strategy 1 ends a sentence after 。？！；, together with the closing quotes and brackets that follow.
- Strategy 2, the default, also breaks at headings and `cb:mulu` positions, makes each verse line (cut at caesuras) a `verse_line` unit, and in a commentary separates a quoted lemma (經「…」) from its gloss (贊曰 …).

Both strategies keep outlined-text span boundaries, so no sentence crosses a span. The sentence kinds are `prose`, `verse_line`, `lemma`, `gloss` and `heading`, and every sentence names the span (`node_id`) that holds it.

### 3.4 `chunk`

The units are the outlined-text spans: a leaf's text, or a parent's preamble (its text before its first child). Packing works as follows:
- Within one parent, consecutive units are packed greedily, in text order, into chunks of at most `sentence_cap` sentences (6) and `size_chars` characters (180). A parent's lead-in text therefore merges with the leaf children that follow it, and sibling leaves merge with each other. Nothing merges across parents.
- A unit over the budget is split at sentence ends (`fallback: split-leaf`).
- Text that no span covers is cut into windows of the same size (`fallback: unoutlined`).

Each chunk records its node (the smallest node covering it, which is its context key), its outline path, its `topic_category`, its CBETA location range and its sentence ids. `chunks.md` interleaves taken-up markers, chunk text and announcement lines in the workflow's interlinear-outline typography; `chunks.docx` is the same with subscript indicators. `eval.chunk_invariants` checks every run: the size cap, coverage of the whole target, sentence alignment, no split inside a leaf, merges within one parent, the `.md` ↔ `.json` round trip, monotone locators, and that every named node exists and every taken-up node has its marker. The formats are in [`outliner-design.md`](outliner-design.md), "Output formats".

### 3.5 `context` (stub)

Not built. The design is a per-chunk context bundle, retrieved by the chunk's outline node, topic-category and location range (D8):
- the commentary passage that treats the chunk (known from the outline in sūtra mode);
- parallel versions;
- glossary hits;
- prior translations;
- apparatus variants.

A model would rank and trim the bundle to a budget. Planned shape: `{chunk_id, outline_path, topic_category, chunk_type, entries: [{kind, text_id, loc, text, licence, how_found}], terms: [...], entities: [...]}`.

### 3.6 `translate` (stub)

Not built. The design is adapters with one interface, `translate(chunk, bundle, project_instructions) -> {draft, record}`, and a stitch step that concatenates the drafts in outline order under the outline's headings.

### 3.7 `eval`

`eval.score` scores a predicted `outline.json` against a gold named by its id in the registry `data/eval-sets.json`. The scores are S-F1 and F-F1 over (key line, depth, parent path) at tolerance t = 0 and t = 1, with per-depth rows and locator-only F1. Further diagnostic rows (the frontier/cascaded split of misses, an attachment-tolerant triple) are never fused into the headline. Structure-only F1 is used for the golds without locators. The key is `commentary.explained`, `root_text.start`, `commentary.span_start` or `structure`.

Every score prints its disclosures: gold status, `seeded_by`, split, key, tolerance. No score on a draft or imported-unchecked gold, or on a dev or validation split, is marked as a headline.

The golds are of four kinds:
- the Kuiji gold for T0262 / T1723 (committed, draft, model-seeded);
- the sdp golds for T1718 and T0262 (eval-only, built under `data/raw/dila-sdp/gold/` and never committed);
- the CBETA 科判 golds X0268, P1573 and D8842;
- the DILA YBh golds T1605 and T1602 (structure only).

Their provenance and splits are in [`../data/EVAL-SETS.md`](../data/EVAL-SETS.md), and the scorer's rules in [`outliner-design.md`](outliner-design.md) §9.

### 3.8 `export`

`export` writes one BDRC-shaped JSON-LD document per (work, scheme): a `bdo:Outline`, one node per outline node with `bdo:partOf`, `bdo:partIndex`, `bdo:partTreeIndex`, a `bdo:ContentLocation` for the root-text span, and our `cw:` terms for the commentary positions and attribution. Node URIs are minted from a content key and kept stable through an id history. The export refuses eval-only and out-of-domain outlines, withholds model-only nodes by default, and, unless a frozen outliner is named, withholds the nodes below level 2 that have a locator in a test or reserve span (D20; `pipeline/src/chinese_workflow/export/README.md`).

## 4. The outline artefact

`outline.json` is the one outline contract between stages. Its schema comes in two layers.

**The base schema**, `context/baseline/outline-schema.json` (JSON Schema 2020-12), gives the general shape of an independent outline, modelled on the outline format of the Tibetan workflow:
- `metadata`, whose required keys are `source_file`, `text_title_src`, `text_title_en`, `source_language`, `format_note`, `node_count`, `max_depth` and `generated_by`;
- `nodes` in document order, each with `id`, `level`, `path`, `parent_id`, `order`, `heading_src`, `heading_en`, `origin`, `locations`, `evidence` and `notes`;
- `unindexed_entries`.

Locations use one of the schemes `acip-folio`, `cbeta-line`, `page`, `unparsed` or `none`. An `inferred` node must carry a confidence and evidence.

**The zh-kepan profile**, `context/baseline/outline-schema-zh.json`, extends the base schema (divergence D15):
- **Opt-in.** A document opts in with `metadata.outline_profile = "zh-kepan"`. Every outline the pipeline writes, and every gold, is a zh-kepan document.
- **Document fields.** The opt-in adds `source_document`, `outline_mode` (`sutra` or `self-outlining`; an early design called this `mode`, with the values commentary-driven and text-driven), `root_text_id`, `commentary_id`, `scheme_id`, `seeded_by`, `gold_status`, `licence`, `eval_only` and `cbeta_release`.
- **Node fields.** It adds `sibling_index`, `node_class` (`sutra-span` or `commentary-internal`), `flags`, `child_count_announced`, `extent_announced`, `source_node_id` and `display_label`, and the origins `imported` and `editorial`.
- **Locations.** It adds the location scheme `cbeta-kepan`: `commentary {announced, explained, span_start}`, positions in the text that states the outline, and `root_text {start, end, basis, end_basis, raw}`, the root-text span the node governs.

Identity:
- **Path.** `path` is authoritative, e.g. `["1_1", "2_2"]`, read as the first node at level 1, then the second node at level 2.
- **Derived fields.** `id` is its joined form (`1_1.2_2`) and `level = len(path)`. `indicator_display` renders the path with level subscripts (`1₁2₂`), and `display_label` gives the 干支 form (甲一, 乙二).
- **Predictions.** A prediction sets `gold_status: prediction` and records in `generated_by` the source and the pipeline commit.

**Validation.** `scripts/validate_outline.py` (also `python -m chinese_workflow.outline validate`) checks the schema and the rules the schema cannot express:
- unique ids, pre-order, and agreement of parent, level and path;
- sibling indices and metadata counts;
- siblings monotone: among consecutive siblings of one scheme, a locator never decreases in document order (`root_text.start` is an error under zh-kepan; `commentary.explained` is an error in self-outlining mode and a warning in sūtra mode);
- a child's root span lies inside its parent's;
- in sūtra mode, a `sutra-span` node without a root span carries the flag `unmapped`.

The outline build runs the same validator in process.

## 5. Plugging the outline back into the text

The Tibetan workflow plugs the independent outline back into the original text to guide chunking. Here that is the `outline` stage's anchor step and its outlined-text, in this order:

1. **Positions in the stating text.** Tier 2 gives each node `commentary.announced`, the line where the parent's listing names it, and `commentary.explained`, the line (with `:<offset>`) where the commentary takes it up. Tier-1 nodes use their `cb:mulu` line, and scheme-prior parts the explained line of their first 品.
2. **Chapter spans.** In sūtra mode, the commentary's 品 nodes are matched to the root text's 品 by name and get the root chapter as their span (`basis: chapter`).
3. **Root spans, monotone** (sūtra mode, `outline/anchor.py`). Each `sutra-span` node is visited in pre-order. Its start is searched inside its parent's root span, from its elder sibling's start onward, so siblings' starts never go backwards:
   - The search looks for the node's lemma (A至B), ignoring punctuation.
   - Then, each reported, it tries a gapped match, the longest prefix or suffix of at least 4 characters, and an interpolated start where the elder sibling's lemma ends.
   - A node with no lemma but with placed children starts at its first child.
   - Any other node stays `unmapped`.

   Ends tile the parent: a node ends where its next placed sibling starts (`end_basis: next-node`), and the last child ends with its parent. Every fuzzy placement is in `outline-report.json`.
4. **Repair and classification.** Out-of-order or uncontained spans are repaired and noted on the node. Unmapped nodes whose announced extent lies beyond their 品 are marked out of span. With a model adapter, the resolver may place the remaining unmapped nodes inside their admissible ranges (`basis: inferred`).
5. **The outlined-text** (`outlined-text.json`, schema `pipeline/schemas/outlined-text.schema.json`). A node's position in the target text depends on the target:
   - for a commentary target (and in self-outlining mode), its `commentary.explained`;
   - for a root target, its `root_text.start`.

   A node the commentary only lists and never takes up has no position in a commentary target. A placed node's text runs to the next placed node's start in pre-order: a `preamble` span when that node is its descendant, otherwise a `leaf` span. The spans tile the whole target except a gap before the first node. Nodes with no position (commentary-internal nodes in a root target, unmapped nodes) are listed under `unplaced`, and the coverage ratio is recorded. `outlined-text.md` is the target text with a marker line before each placed node.
6. **Chunks key on the spans.** The chunker merges a parent's units upward into chunks (§3.4). Chunk boundaries therefore fall between leaves, or inside a leaf longer than the budget, and each chunk inherits the path and topic-category of the smallest node covering it.

## 6. The experiments

Each experiment is in `experiments/Enn-slug/`, made from `experiments/_template/` with its hypothesis written before the run. Reusable code is in `pipeline/`; experiment harnesses and records stay in the experiment's directory.

No number below is a headline. Dev and validation scores never are, the Kuiji gold is a draft seeded by a Claude model, and the sdp and out-of-domain golds are imported and unchecked. The test spans of T1718 and T1723 have never been scored.

| Experiment | What it exercises | Key results |
|---|---|---|
| [E00](../experiments/E00-kepan-census/SUMMARY.md): kēpàn coverage census | No pipeline stage. Its own scripts run over the CBETA API (4.6.7) and the 2026R2 XML. | 148 of 1,757 Taishō root works (8.4 %) sit in a CBETA cluster with a 疏-class commentary. Level 1 is three-fold in 53 of the 59 經疏部 works that announce one in their first 卷. In the 科文 chart X0231, sūtra-span leaves have a median of 2 sentence marks (85.2 % have 6 or fewer). |
| [E01](../experiments/E01-explicit-recovery/README.md): explicit-only recovery | `outline` with tier 1 alone and with tier 1 + tier 2 (no model), then `eval.score` | T1723 dev (Kuiji gold): tier 2 S-F1 1.000 (45 of 45 nodes; in-sample, on the chapter the parser was developed on). T1718 validation (sdp gold): S-F1 0.000 for both arms, below the pre-registered S-F1 gate of 0.40; tier-2 locator-only F1 0.118. |
| [E06](../experiments/E06-capability-sweep/README.md): capability sweep, v0 | `outline` arms tier 1, tier 2, hybrid and model-only on the dev and validation spans of the sdp and Kuiji golds and on the five out-of-domain golds; the runner on the five projects. The model arms were answered by Claude Code subagents through the `interactive` adapter. | Kuiji dev 45 of 45 again. On T0262's 陀羅尼品 root spans, tier 2 scores 0.453 (12 of 41, the lemma-anchored nodes) and the hybrid 1.000 (the resolver filled the 29 manual cuts; it is the same model family as the gold's seeder). S-F1 is 0.000 on every T1718 validation row. 4 cells failed on 2 pipeline bugs. The review of the run ([`REVIEW-2026-10-02.md`](../experiments/E06-capability-sweep/REVIEW-2026-10-02.md)) ranked the follow-up work. |
| [E07](../experiments/E07-capability-sweep-v1/README.md): capability sweep, v1 | E06's matrix on the outliner after that follow-up | All 41 cells build. The Kuiji results are unchanged (45 of 45; root 0.453; hybrid 41 of 41). S-F1 is still 0.000 on every T1718 validation row. A regression nothing caught earlier: the 「X」者 lemma-gloss rule attaches two glosses to the wrong items, and the anchor then misplaces the opening of 序品 (T0262 序品 set, tier-2 validation locator-only 0.197 → 0.015). On the 善導 project, 89 of 208 lemmas are not found (42.8 %). Every chunk invariant holds on all five projects. |

The tier-2 rules were developed on these dev spans. The Kuiji result is therefore in-sample, and the Zhiyi (sdp) scores are limited mainly by the gold's conventions: its key line and its editorial top level ([E07 README](../experiments/E07-capability-sweep-v1/README.md), "Interpretation").

## 7. What is not built

- **The translation half of the workflow.** The `context` and `translate` stages, a Project Instructions template, stitching and a translation-quality measure.
- **A variorum-text.** `ingest` does not write the Taishō apparatus side-table (D2), and nothing collates editions beyond it.
- **Model-assisted sentence segmentation** (strategy 3), and a separate chunker skill. The outliner skill calls the chunk module directly.
- **Model-only outlining as a project source.** `resolver.resolve(commentary=None)` exists, and the E06 and E07 harnesses ran it, but no `outline --source` value or project does.
- **A cross-lingual check.** Comparing an outline with the Tibetan workflow's outline of the same commentary in Tibetan (E04) was planned and has not been run.
- **Reconciling several commentators' outlines of one sūtra.** Each scheme is its own document (`scheme_id`); there is no merge logic.
- **Any orchestration, service or caching layer** beyond the model-response cache.

Known limitations, from the results:
- the lemma-gloss regression above is not fixed;
- on the 善導 project, lemma-not-found stays above the 25 % target (42.8 %; [`outliner-design.md`](outliner-design.md) §5.5);
- S-F1 on the out-of-domain golds is near zero;
- the chunk budget (6 sentences, 180 characters) is a default, not tuned;
- the `claude` adapter has been tested only against recorded responses: E06 and E07 used the `interactive` adapter.

## Related documents

- [`outliner-design.md`](outliner-design.md): the outliner at module level: algorithms, file contracts, command lines, the split guard, the scorer, and the output formats.
- [`chinese-workflow-mapping.md`](chinese-workflow-mapping.md): the divergences D1–D17, D20 and D21 from the Tibetan workflow, and the zh-kepan schema field by field (D15).
- [`glossary.md`](glossary.md): the workflow terms and ours.
- [`../pipeline/README.md`](../pipeline/README.md) and each stage README: install, run and the stage contracts.
- [`../data/EVAL-SETS.md`](../data/EVAL-SETS.md): the golds, the splits and the scorer's rules.
- [`../experiments/README.md`](../experiments/README.md): the experiment records.
