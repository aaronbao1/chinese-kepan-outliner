---
name: chinese-kepan-outliner
description: Produce the kēpàn (科判) outline of a classical Chinese Buddhist text from CBETA — the independent outline (outline.json + Kurt-style .md/.docx), the outlined-text, and the interlinear outline (outlined-and-chunked-text) — separating divisions the commentary states (explicit) from ones a model proposes (inferred). Use when outlining, chunking or preparing a CBETA text (a sūtra with its designated commentary, or a self-outlining treatise) for translation or for the knowledge graph.
---

# chinese-kepan-outliner (v1)

The Chinese counterpart of Kurt Keutzer's `tibetan-sabcad-outliner` (Agentic Translation Workflow 1.0 §1f Step 1, his `outliner-skill`). It emits his two artefacts — the *independent outline* and the *interlinear outline* — plus `outline.json`, the machine-readable form that feeds the knowledge graph. The design is `docs/outliner-design.md`; the divergences from Kurt's model are rows D3–D6, D11, D14–D17, D20–D21 of `docs/chinese-workflow-mapping.md`.

The procedure below is ours. It produces the two artefacts in the shape of the Tibetan workflow's own outlines (the formats as implemented are described in `docs/outliner-design.md`, "Output formats"), but it was not derived from the text of the Tibetan skill.

## Before you start: the split discipline

Read `references/split-discipline.md`. In short: never open the test answer keys listed in `data/EVAL-SETS.md` ("Do not open while developing"); runs over test or reserve spans of T1718 / T1723 are refused unless `--frozen <tag>` names a frozen outliner; eval-only and out-of-domain golds are never input or prompt material.

## Inputs

- A **project file** `projects/<id>/project.toml` (template: `projects/lotus-kuiji-dharani-comm/project.toml`): `mode` (`sutra` = a sūtra outlined by its designated commentary; `self-outlining` = a treatise or commentary that announces its own divisions), `root` and `commentary` (CBETA file ids such as `T09n0262`, `T34n1723`), `scheme_id` (whose division this is — mandatory: commentators divide the same sūtra differently), `target_role` (the text the outlined-text and chunks are over), `span`, `source`, optional `[[scheme.level1]]` (the commentator's top-level division when the run does not read it), `[resolver] adapter`.
- The CBETA XML (release 2026R2) under `data/raw/cbeta/` (`scripts/fetch_cbeta.sh` fetches the pinned works; any other file comes from the corpus clone of `scripts/fetch_cbeta_xml_p5.sh`), or per-file overrides in `[xml]`.

## Procedure

Run from `pipeline/` with its venv (`.venv/bin/python`). Each step names the CLI it calls; `python -m chinese_workflow.runner run <project.toml>` does steps 1–7 in one go (headless) and stops before the human steps.

1. **Outline, explicit layer.** `python -m chinese_workflow.outline build --project <project.toml> --out <run>/outline` with `source = "tier2"`. This runs tier 1 (CBETA's `cb:mulu` chapter table: 卷/品/分/科判), tier 2 (the stateful formula parser over the commentary: announcements 有N / 分N / 文為N / N門分別 …, entry markers 此初 / 今初 / 第二 / 下明 …, lemma units 經「A至B」。贊曰, the doctrinal-list filter and the genre gate — `references/formula-table.md`), the scheme prior, the merge and the root spans (lemma → sūtra lines). Explicit nodes are the commentator's own divisions; never edit them.
2. **Read the parser report** (`<run>/outline/outline-report.json` → `tier2.report`, `tier2.rejected`, `anchor`): announcements whose target the rules could not decide, rejected doctrinal lists, lemmas not found in the sūtra, nodes left `unmapped`.
3. **Resolve (model-assisted).** With `source = "hybrid"` and `[resolver] adapter = "interactive"`, the build writes requests into `<run>/outline/llm/requests/<hash>.json` and `.md` (one per 品, or several when a 品's candidates do not fit one request; a leaf too long for one request comes in windows, one request each) and stops with a list of pending requests. For each request: read the `.md` (it carries the ancestor path, the commentary span, the sūtra span, the explicit nodes and the question — `references/resolver-prompt.md`), answer strictly in the JSON schema it gives, and write the answer to `<run>/outline/llm/responses/<hash>.json`. Then re-run the build: responses are validated and merged. Rules: inferred nodes only, `confidence` < 1, a rationale in `evidence`, the project's `scheme_id`; never move, rename or re-parent an explicit node (the build checks this and rejects the whole response otherwise); spans must lie inside the parent's span. With `adapter = "claude"` (API key in `ANTHROPIC_API_KEY`, `pip install -e 'pipeline[llm]'`) the same requests go to the API; `replay` re-uses recorded responses.
4. **Gloss.** The same loop fills `heading_en` for every node (`references/gloss-prompt.md`); the gloss's provenance goes in each node's `notes`.
5. **Validate.** `python -m chinese_workflow.outline validate <run>/outline/outline.json` (the build already does it; zero errors required). If `outline-report.json` has a `degraded` key, the build repaired local errors: read each entry's `repairs` and review those nodes (their `notes` say `demoted: …`, `clipped: …`, `raised: …` or `nulled: …`) together with the inferred nodes in step 6.
6. **Review inferred nodes** (human; Kurt's review gate): `references/review-checklist.md`, lowest confidence first. Record decisions in the node's `notes`; a reviewed prediction can be promoted to a gold only by a human (`gold_status: reviewed`).
7. **Segment and chunk** into the interlinear outline: `python -m chinese_workflow.segment …` → `sentences.json`; `python -m chinese_workflow.chunk …` → `chunks.md` / `.json` / `.docx` in Kurt's typography (taken-up markers `[<indicator>) heading <locator>]`, announcement lines `<indicator>) heading`, blank-line chunks of ≤ 6 sentences and ≤ the length budget; sibling leaves merged upward within one parent). `python -m chinese_workflow.eval.chunk_invariants …` must pass.
8. **Export** for the knowledge graph: `python -m chinese_workflow.export <run>/outline/outline.json --out <run>/export/…jsonld` (BDRC-shaped, one outline per work and scheme; refuses eval-only and out-of-domain inputs; model-only nodes are not exported by default).

## Outputs (per run directory; `docs/outliner-design.md` §11)

| Kurt's artefact | File |
|---|---|
| independent outline | `outline/outline.json`, `outline/outline.md`, `outline/outline.docx` |
| outlined-text | `outline/outlined-text.md` (+ `outlined-text.json`, the node → span sidecar) |
| outlined-and-chunked-text (interlinear outline) | `chunk/chunks.md`, `chunk/chunks.docx` (+ `chunks.json`) |
| (ours) knowledge-graph export | `export/<text>.<scheme>.jsonld` |
| (ours) provenance | `run.json`, `outline/outline-report.json` |

## Scoring (not part of producing an outline)

`python -m chinese_workflow.eval.score --pred <run>/outline/outline.json --gold <dataset-id> --split dev` scores against a registered gold (`data/eval-sets.json`): S-F1 / F-F1 over (explained locator, depth, parent path) at t = 0 and t = 1. Test splits and out-of-domain golds need `--frozen`; a `draft-unreviewed` gold never gives a headline number.
