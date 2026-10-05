# chinese-workflow: a kēpàn outliner for classical Chinese Buddhist texts

A pipeline that builds a kēpàn (科判) outline of a classical Chinese Buddhist text from the XML edition of CBETA (the Chinese Buddhist Electronic Text Association) and uses it to cut the text into chunks for translation, each chunk labelled with its place in the outline. It parallels Kurt Keutzer's agentic translation workflow for Tibetan and uses that workflow's names for its artefacts.

Author: Aaron Bao. Collaborator: Charles (Shengyu) Wang.

## What it is

A kēpàn is a commentator's nested division of a sūtra or treatise. The commentaries this pipeline reads state it in their own prose, with formulae such as 文為N ("the text is in N parts") and 初中亦二 ("within the first, again two"), and then take up each part in turn; some kēpàn were also printed as separate charts (科文). The outline plays the part the sa bcad (the Tibetan topical outline) plays for Tibetan texts: it says where each passage sits in the whole, which is the context a translator of that passage needs.

The outliner reads the CBETA XML of a text, plus a designated commentary when the text is a sūtra, and writes:
- the *independent outline*: `outline.json`, rendered as Markdown and Word;
- the *outlined-text*: the target text with the outline added as annotation;
- the *interlinear outline* (the *outlined-and-chunked-text*): the text cut into chunks of at most 6 sentences, each placed under its outline node, as Markdown, Word and JSON;
- a knowledge-graph export of the outline (BDRC-shaped JSON-LD, i.e. following the ontology of the Buddhist Digital Resource Center).

The first pair of texts is the Lotus Sūtra (T0262) with Kuiji's commentary 法華玄贊 (T1723); Zhiyi's 法華文句 (T1718) is the second commentary. Two more projects run a commentary on another sūtra (Shandao's on the Contemplation Sūtra) and a treatise that outlines itself (the Awakening of Faith). The later stages of a translation workflow, building context for a chunk and translating it, are stubs.

## Status

- **Built:** the outliner pipeline, ingest → outline → segment → chunk → export, with eval beside it. One command runs a project end to end ([Quickstart](#quickstart)).
- **Not built:** the `context` and `translate` stages (stubs) and the variant apparatus in `ingest` ([`pipeline/README.md`](pipeline/README.md)).
- **Evaluated version:** v1, measured by E07. v0 was measured by E06.

| Freeze tag | Commit | Evaluated by | Contents |
|---|---|---|---|
| `outliner-v0-frozen-2026-10-01` | `8498eb3` | E06 | the pipeline as first built |
| `outliner-v1-frozen-2026-10-03` | `014c125` | E07 | v0 plus the changes chosen in the E06 review: scorer fixes, fixes for the two bugs that failed builds, and parser, anchor and resolver changes |

The freeze tags, and the commit hashes the experiment records cite, belong to the development repository. The code in this copy is v1 plus changes that leave outline output unchanged: a clearer error for a CBETA file that has not been fetched, packaging metadata, the quickstart script, a `fetch_cbeta.sh` that pins more works, tests, and documentation and comments.

**Bottom line.** No quality number here can be relied on yet:
- Both perfect scores come from Kuiji's 陀羅尼品, the dev chapter the parser was developed on, against a draft gold that Claude seeded and no person has reviewed: tier 2 rebuilds 45 of 45 nodes on the commentary, and the hybrid matches 41 of 41 nodes keyed on sūtra lines, using a model of the same family as the gold's seeder.
- Every strict structural score (S-F1) on Zhiyi's validation text is 0.000. E07 shows that these zeros are forced by how the rows are built, so they do not measure the parser. Two scoring conventions decide what the Zhiyi side can show, and neither is settled.
- No test span has been scored.

## Quickstart

You need Python 3.11 or newer (the code reads TOML with `tomllib`; [`pipeline/pyproject.toml`](pipeline/pyproject.toml) says `requires-python = ">=3.11"`), plus git, bash and curl. On macOS, `/usr/bin/python3` is 3.9 and will not work. The pipeline run is offline and needs no API key. Steps 1 and 2 download the CBETA files (GitHub, cbeta.org) and the Python packages (PyPI). From the root of a clone of this repository:

```bash
# 1. Data: the 19 CBETA works that scripts/fetch_cbeta.sh pins (the five projects' texts among them),
#    release 2026R2 (about 35 MB), into data/raw/cbeta/
bash scripts/fetch_cbeta.sh

# 2. Install with any Python >= 3.11 (change python3.12 to the one you have)
cd pipeline
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'

# 3. Run one project end to end, then the tests
.venv/bin/python -m chinese_workflow.runner run ../projects/lotus-kuiji-dharani-comm/project.toml
.venv/bin/pytest ../tests -q
```

Or, from the repository root, `bash scripts/quickstart.sh` finds a suitable Python, makes the venv, fetches the CBETA files that one project needs and runs it, in one go (`--all` runs every project). It does not run the tests; it prints the command. Its header explains each step ([`scripts/quickstart.sh`](scripts/quickstart.sh)).

Notes on the steps:
- **Step 1.** `fetch_cbeta.sh` downloads each work from `cbeta-org/xml-p5` at tag `2026R2` and checks its size against the tag's git tree. When the bytes match the sha256 recorded in `scripts/CHECKSUMS`, the script leaves that file unchanged, so the checkout stays clean and `run.json` does not record it as dirty. `bash scripts/fetch_cbeta.sh --check` re-verifies the files ([`scripts/fetch_cbeta.sh`](scripts/fetch_cbeta.sh)). Some tests and golds read other CBETA files, which come from the whole-corpus clone, `scripts/fetch_cbeta_xml_p5.sh` (about 5 GB; [`scripts/README.md`](scripts/README.md)).
- **Step 2.** If `python3.12 -m venv` fails inside `ensurepip`, it leaves a half-made `.venv`. Remove it and use [uv](https://docs.astral.sh/uv/) instead: `rm -rf .venv && uv venv --python 3.12 .venv && uv pip install --python .venv -e '.[dev]'`. More in [`pipeline/README.md`](pipeline/README.md).
- **Step 3.** On success the run prints a JSON summary with `"ok": true`. The exit code is 0 when every stage ran and the chunk invariants hold, 1 otherwise, and 2 when the split guard refused the run. The default project is small: Kuiji's commentary on one chapter, 陀羅尼品 (31 CBETA lines). It runs in seconds and gives 46 outline nodes and 11 chunks; for a whole commentary, `projects/guanjing-shandao/project.toml` gives 555 chunks (E07 `projects.json`). A `degraded` count above 0 (guanjing-shandao: 17) means the build found local order or containment errors and repaired them; each repair is listed in `outline/outline-report.json` ([`docs/outliner-design.md`](docs/outliner-design.md) §5.0). Tests that need data you have not fetched are skipped, not failed; [`tests/README.md`](tests/README.md) gives the counts to expect.

Each run writes `data/processed/<project id>/` (gitignored):

| File | What it is |
|---|---|
| `outline/outline.md`, `outline.docx`, `outline.json` | the independent outline, rendered and machine-readable ([Output formats](docs/outliner-design.md#output-formats)) |
| `chunk/chunks.md`, `chunks.docx`, `chunks.json` | the interlinear outline (outlined-and-chunked-text) |
| `outline/outlined-text.md` | the outlined-text: the target text with the outline added as annotation |
| `export/<text>.<scheme>.jsonld` | the knowledge-graph export (BDRC-shaped JSON-LD) |
| `run.json` | pipeline commit and dirty flag, CBETA release, input sha256, resolver settings, model-call ledger, per-stage counts, split-guard report |

The runner's docstring lists every file ([`pipeline/src/chinese_workflow/runner/__main__.py`](pipeline/src/chinese_workflow/runner/__main__.py)).

**English headings without an API key.** The shipped projects use no model (`[resolver] adapter = "none"`), so their headings stay in the source's own Chinese. To see English headings, run the offline replay of the same chapter. It reads the committed CBETA excerpts and replays recorded Claude answers, so it needs neither `data/raw/` nor a key:

```bash
# from pipeline/, as in step 3
.venv/bin/python -m chinese_workflow.runner run ../tests/fixtures/projects/dharani-offline-hybrid.toml
```

Its `data/processed/dharani-offline-hybrid/outline/outline.md` gives every node an English heading beside the Chinese one. For new English headings and inferred nodes on other texts, the model-assisted resolver and gloss need `source = "hybrid"` and an adapter other than `none`: `claude` or `interactive` for new answers, `replay` for recorded ones ([`pipeline/README.md`](pipeline/README.md), "Model-assisted runs").

## How it works

Each stage is a subpackage of [`pipeline/src/chinese_workflow/`](pipeline/src/chinese_workflow/), and its README states its input and output artefacts. Stages exchange files and never import each other's internals; [`tests/unit/test_stage_boundaries.py`](tests/unit/test_stage_boundaries.py) enforces this. The module-level design is [`docs/outliner-design.md`](docs/outliner-design.md).

| Stage | Input → output | Status |
|---|---|---|
| `ingest` | CBETA XML → input-text with line anchors and structure markup | built; variant apparatus not yet |
| `outline` | input-text, plus the commentary → independent outline (`outline.json`, `.md`, `.docx`) and outlined-text | built |
| `segment` | outlined-text → sentences | built |
| `chunk` | outlined-text + sentences → interlinear outline (`chunks.md`, `.json`, `.docx`) | built |
| `export` | independent outline → BDRC-shaped JSON-LD, one outline per (work, scheme) | built (v0) |
| `context` | chunk + topic-category → context bundle | stub |
| `translate` | chunk + context → draft translation | stub |
| `eval` | outline vs gold → scores; chunk invariants | built |

Inside `outline`:
- **Nodes.** Each outline node has an `origin`: `explicit` (the text or its commentarial tradition marks the division), `editorial` (supplied with no announcement in the text, e.g. a part of a declared scheme prior or a carried 品), `imported` (from an external digital outline, not yet checked) or `inferred` (proposed by the outliner, with confidence and evidence). Each outline names its commentator's scheme (`scheme_id`).
- **Two modes.** In *sūtra mode* a commentary states the outline and the pipeline maps it onto the sūtra. In *self-outlining mode* a treatise or commentary outlines itself.
- **Tier 1** is CBETA's own table of contents (卷 fascicles, 品 chapters, and 科判 markup where CBETA has it). It is the floor.
- **Tier 2** is a stateful parser for division formulae such as 文為N or 初中亦二. It keeps a stack of open divisions, resolves anaphora (今初 "now the first"), and has a genre gate and a filter for doctrinal lists that look like divisions.
- **Scheme prior.** A project may declare a commentator's top-level parts.
- **Merge and anchor.** Merge combines tier 1, tier 2 and the prior. The anchor maps the commentary's lemmas (the sūtra phrases it quotes before explaining them) onto sūtra lines and writes the outlined-text.
- **Resolver and gloss** (the model). They add inferred nodes, root-text spans and English headings, and never change an explicit node. Adapters: `none` (no model; unplaced nodes stay flagged), `replay` (recorded answers), `claude` (Anthropic API), `interactive` (the build writes request files, a Claude Code session answers them, and the build is re-run). To drive the whole outliner from Claude Code, open this repository in Claude Code and ask it to follow [`skills/chinese-kepan-outliner/SKILL.md`](skills/chinese-kepan-outliner/SKILL.md). The skill is a folder in the repo, not an installed skill, and its steps run from `pipeline/`.
- **Chunking** caps a chunk at 6 sentences, the upper end of the Tibetan workflow's 4–6, and adds a length budget (default 180 characters). A chunk holds whole outline leaves, merged upward within one parent (a leaf over the cap is split at sentence ends), so it can be shorter than 4 sentences. Divergences D6 and D14 in [`docs/chinese-workflow-mapping.md`](docs/chinese-workflow-mapping.md) record this. The budget is a default, not a tuned value ([`docs/outliner-design.md`](docs/outliner-design.md) §7).

**Guards and records.** A split guard refuses test and reserve lines unless the run names a frozen tag (`--frozen`). Any string passes as the tag: the guard records it but does not check that the tag exists ([`pipeline/src/chinese_workflow/common/splits.py`](pipeline/src/chinese_workflow/common/splits.py)). So a Lotus project run over its whole commentary with `--frozen` shows the test spans; do not read them if you mean to report a test score. Each run writes `run.json` (table above). Model answers are cached, so a run can be replayed without new calls.

## Projects

The runner (`chinese_workflow.runner`) takes one `projects/<id>/project.toml` and writes `data/processed/<id>/`.

| Project | Mode | Texts | Span |
|---|---|---|---|
| [`lotus-kuiji-dharani-comm`](projects/lotus-kuiji-dharani-comm/project.toml) | sūtra | Kuiji T1723 on T0262; target: the commentary | T1723 dev (陀羅尼品) |
| [`lotus-kuiji-dharani-root`](projects/lotus-kuiji-dharani-root/project.toml) | sūtra | the same; target: the sūtra | T1723 dev |
| [`lotus-zhiyi-wenju`](projects/lotus-zhiyi-wenju/project.toml) | sūtra | Zhiyi T1718 on T0262 | T1718 dev |
| [`guanjing-shandao`](projects/guanjing-shandao/project.toml) | sūtra | Shandao's 觀無量壽佛經疏 (T1753) on 佛說觀無量壽佛經 (T0365, the Contemplation Sūtra) | whole text; no gold |
| [`qixin-self`](projects/qixin-self/project.toml) | self-outlining | 大乘起信論 (T1666, the Awakening of Faith) | whole text; no gold |

## Evaluation data and provenance

The registry [`data/eval-sets.json`](data/eval-sets.json) lists every gold, fixture and split, and its guide is [`data/EVAL-SETS.md`](data/EVAL-SETS.md). Every gold is an independent outline under the `zh-kepan` profile ([`context/baseline/outline-schema-zh.json`](context/baseline/outline-schema-zh.json)), which extends the base independent-outline schema ([`context/README.md`](context/README.md)).

| Gold | Source | Licence | Status | Where | In git |
|---|---|---|---|---|---|
| Zhiyi scheme on T1718 and T0262 (`sdp-*`) | 法華經數位資料庫 of CHIBS, the Chung-Hwa Institute of Buddhist Studies (sdp.chibs.edu.tw), keyed to T1718 | none published, so eval-only | imported, unchecked | `data/raw/dila-sdp/gold/` | no |
| Kuiji scheme on T0262 (`kuiji-xuanzan`) | hand-built from T1723 | CC BY-NC-SA 4.0 | draft, Claude-seeded, unreviewed | `data/reference-outlines/T0262/kuiji-xuanzan/` | yes |
| X0268, P1573, D8842 (`cbeta-mulu-*`) | CBETA's own `cb:mulu type="科判"` markup | CC BY-NC-SA 4.0 | imported, unchecked; out-of-domain | `data/reference-outlines/<id>/cbeta-mulu-kepan/` | yes |
| T1605, T1602 (`ybh-*`) | 科判 files of YBh, the 瑜伽師地論 (Yogācārabhūmi) database of DILA (Dharma Drum Institute of Liberal Arts); structure only | CC BY-SA 4.0 | imported, unchecked; out-of-domain | `data/reference-outlines/<id>/ybh-dila/` | yes |
| Parser cases | division formulae quoted from dev spans or texts outside the splits | CC BY-NC-SA 4.0 | machine-drafted labels, unreviewed (148 cases) | `tests/fixtures/kepan-formulae/` | yes |

**Splits.** T1718 and T1723 are cut by CBETA line into dev, validation, test and reserve spans ([`data/EVAL-SETS.md`](data/EVAL-SETS.md), "Splits"). For T1723, dev is the 陀羅尼品 commentary, and test is the 序品 subtree and the 譬喻品 (Parable chapter) opening. A test span is to be scored once per frozen system; none has been scored. Out-of-domain golds are scored only with a frozen tag. A few committed files hold test-split answer keys; [`data/EVAL-SETS.md`](data/EVAL-SETS.md), "Do not open while developing", names them.

**Never committed, and why:**
- `data/raw/` (about 5 GB with the whole-corpus clones). CBETA XML-P5 at release 2026R2 and the other sources are fetched by `scripts/fetch_*.sh`, not redistributed. They are pinned by sha256 in `scripts/CHECKSUMS`, or by git commit for the whole-corpus clones ([`scripts/README.md`](scripts/README.md)).
- sdp's trees, headings and spans. sdp publishes no licence, so they stay under `data/raw/dila-sdp/`; committed files hold only aggregate counts, sdp node ids and a few locator facts. [`tests/unit/test_sdp_eval_only_guard.py`](tests/unit/test_sdp_eval_only_guard.py) fails if an sdp heading appears in a tracked file, and tests that need sdp data skip when it is absent. To score against the Zhiyi golds, build them locally: `bash scripts/fetch_dila_sdp.sh`, then `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.sdp` ([`data/EVAL-SETS.md`](data/EVAL-SETS.md), "Rebuilding and checking"). Keep the result local and use it for evaluation only.
- `data/processed/` (pipeline outputs) and `experiments/**/out/` and `runs/` (bulk experiment outputs). They are reproducible from `data/raw/` and a commit.

Sources and their terms are listed in [`data/README.md`](data/README.md). [`data/reference-outlines/NOTICE`](data/reference-outlines/NOTICE) carries the notices the committed golds' licences require. Whether an outline table of headings and line references counts as an adaptation (改作) under CBETA's notice has not been settled with CBETA (NOTICE, item 1).

## Results

**Terms.** *Tier 1*: CBETA's own table of contents. *Tier 2*: the rule parser for the commentary's division formulae. *Hybrid*: tier 2 plus a Claude pass that adds inferred nodes, sūtra spans and English headings. *Model-only*: Claude outlining the sūtra with no commentary. An *arm* is one of these four; a *cell* is one arm run on one dataset. A *gold* is a reference outline. *sdp* is the Lotus kēpàn that CHIBS publishes at sdp.chibs.edu.tw, which follows Zhiyi. A *lemma* is a sūtra phrase the commentary quotes before commenting on it; the *anchor* places each lemma on a sūtra line. *S-F1* is node F1: a predicted node counts only if its key line, its depth and its whole parent path match the gold, so one wrong ancestor fails the whole subtree under it. *Locator-only F1* checks the key line alone, so it measures detection without placement in the tree ([`docs/outliner-design.md`](docs/outliner-design.md) §9). *Dev, validation, test*: fixed spans of T1718 and T1723, used to develop, to tune (each scoring of validation is a logged *look*) and to report once; *reserve* is not looked at. *In-sample*: measured on text the rules were developed on. A *chunk invariant* is a check every chunk must pass: size cap, no split inside a leaf, merges within one parent, full coverage ([`docs/outliner-design.md`](docs/outliner-design.md) §7). More in [`docs/glossary.md`](docs/glossary.md).

| Exp. | Question | Read-out | Record |
|---|---|---|---|
| E00 | How much of the canon has a kēpàn? | 8.4 % of Taishō root works (148 of 1,757) sit in a CBETA catalogue cluster that also holds a commentary of the kēpàn-bearing genre (疏, 文句, 玄贊 or 科 in the title). The count is by cluster and by title rule, so it estimates coverage rather than counting it work by work. Level 1 is three-fold in 53 of the 59 經疏部 (the Taishō's sūtra-commentary section) commentaries that announce a level-1 count in their first fascicle | [`experiments/E00-kepan-census/`](experiments/E00-kepan-census/README.md) |
| E01 | What does the rule parser recover alone? | T1723 dev 45/45 (in-sample); T1718 validation S-F1 0.000, locator-only 0.118. The pre-registered gate (S-F1 < 0.40) points to using the parser only to detect announcements and moving attachment to the model; v1 still uses the parser as its main structure builder | [`experiments/E01-explicit-recovery/`](experiments/E01-explicit-recovery/README.md) |
| E06 | What can v0 do, set by set and arm by arm? | capability matrix in `REPORT.md`; what the numbers mean in `REVIEW-2026-10-02.md` | [`experiments/E06-capability-sweep/`](experiments/E06-capability-sweep/README.md) |
| E07 | The same matrix on v1 | below | [`experiments/E07-capability-sweep-v1/`](experiments/E07-capability-sweep-v1/README.md) (`README.md`, `SUMMARY.md`) |

Every experiment records its hypotheses before the run.

**How to read the numbers.** No number below is a headline. All come from dev, validation or out-of-domain sets. No build or score has read the test spans of T1718 or T1723; each build's split-guard log shows dev, validation or unsplit reads only (E07 README, "Looks, leakage, cost"). One exposure is recorded: E07's model-only request for 序品 (the opening chapter) showed 3 sūtra lines in the test region and 1 in the reserve, unscored. The Zhiyi golds are imported from sdp and unchecked. sdp's top level is an editor's division of the sūtra, not Zhiyi's, and the Zhiyi dev answer key has only 12 nodes ([`data/EVAL-SETS.md`](data/EVAL-SETS.md), "Splits"). The model arms were answered once each by Claude Code subagents through the `interactive` adapter, not through the `claude` API adapter, and the Kuiji gold was seeded by the same model family.

**What E07 found on v1** ([`experiments/E07-capability-sweep-v1/README.md`](experiments/E07-capability-sweep-v1/README.md)):
- **Kuiji (T1723), dev chapter 陀羅尼品 (the Dhāraṇī chapter, ch. 26).** The parser rebuilds all 45 gold nodes (S-F1 1.000), as v0 did. This is in-sample.
- **Kuiji, sūtra spans of the same chapter.** On the root-text set (T0262-dharani-root) the hybrid scores S-F1 1.000 (41 of 41): the model supplies the 29 spans that the gold's drafter cut by hand where Kuiji quotes no lemma, and tier 2 alone stops at 0.453 (12 of 41). A fresh answer gave the same 29 cuts as E06's. Each answer is a single sample from the same model family that seeded the gold, so the score may show agreement with the seeder rather than accuracy (H8).
- **Zhiyi (T1718), validation.** S-F1 is 0.000 on every row, arm and key. The set-up forces these zeros. In the validation-only build every gold node hangs under an ancestor outside the build, so none can match. In the dev+validation build one top-level node is missing, and since S-F1 needs the whole parent path, every node below it misses too (H5). Two conventions decide this and are not settled: which line keys a node (sdp uses the line where the node's text starts, the Kuiji gold the line where the commentary takes the node up), and the top level under Zhiyi's scheme (E06 review, Q1 and Q2).
- **Zhiyi, dev.** v1 reads Zhiyi's 「X」者 device, where he quotes a phrase of the sūtra and then explains it. Predictions in the scored range rise from 29 to 49 (58 nodes in all; 9 fall outside the text sdp serves). The dev answer key has only 12 nodes, and every added node counts against it as a false positive, so S-F1 moves 0.049 → 0.033 (H3).
- **A regression.** That device matches a gloss to a listed item by part of the item's name. At the start of 序品 it attaches two glosses to the wrong short items, and the anchor places their lemmas on later sūtra lines. On the T0262 序品 root-text set, tier-2 validation locator-only F1 falls 0.197 → 0.015. In a dev-only test, raising the match threshold (`GLOSS_PARTIAL` 0.5 → 0.95) restores v0's 序品 dev row. The defect was found on validation text, so a fix has to be justified on dev or out-of-split text; it is not in v1 (E07 finding 1).
- **Robustness.** All 41 cells build. In v0 four cells failed on two bugs: tier 2 and hybrid on T1602, and two X0268 diagnostic cells (H2).
- **Chunks.** Chunk labels are much finer. The share of chunks whose label covers more than 2,000 characters fell for `guanjing-shandao` 86.9 % → 31.0 %, `lotus-zhiyi-wenju` 71.0 % → 31.5 % and `qixin-self` 54.4 % → 13.1 % (E07 finding 8). These are in-sample, because the changes were developed on these texts (H13), and they show how finely the labels divide, not whether the divisions are right. Every chunk invariant holds in all five projects.
- **Shandao 善導 (T1753, project `guanjing-shandao`).** The anchor cannot place 89 of 208 lemmas (42.8 %), against a target of at most 25 % that a strict xfail test holds open ([`docs/outliner-design.md`](docs/outliner-design.md) §5.5).
- **Out of domain.** Tier-2 S-F1 stays below 0.05 on the three CBETA 科判 texts and is 0.000 on the two YBh texts (H11, H12). Tier-2 rules were developed on T1602, so it is no longer a clean out-of-domain text for tier 2 (H12).

**Reproducing a result.** Each experiment folder has its harness (for example `experiments/E07-capability-sweep-v1/run_e07.py`); its docstring gives the commands and the input files. The tier-1 and tier-2 arms rebuild from `data/raw/` alone. The hybrid and model-only arms need the recorded model answers under the gitignored `runs/` directory, or a new answering pass. The full data needs `fetch_cbeta.sh`, `fetch_cbeta_xml_p5.sh` (about 5 GB), `fetch_dila_sdp.sh` with the sdp gold build above, and `fetch_dila_ybh.sh` ([`experiments/README.md`](experiments/README.md)).

## Known limitations

What the results above show the outliner does not yet do, or what they cannot tell:
- **No reliable quality number.** No test span has been scored. The Kuiji gold and the 148 parser-case labels are machine drafts that no person has reviewed, and the parser was developed on the Kuiji dev chapter. The sdp and out-of-domain golds are imported and unchecked.
- **The Zhiyi scores measure scoring conventions more than outlines.** The validation zeros are forced by reachability and by one top-level miss (E07 H5). The `commentary.span_start` key is valid only for golds keyed the way sdp is; against the Kuiji gold even the oracle scores S-F1 0.400 with it (E07 finding 2).
- **The 序品 lemma-gloss regression is not fixed** (E07 finding 1).
- **Anchoring is weak on Shandao's commentary.** 42.8 % of lemmas are not found. Its largest chunk label is an 11,188-character preamble carried by 97 chunks (E07 finding 8).
- **The resolver adds, but cannot repair.** On Zhiyi it duplicated an explicit subtree that tier 2 had already built (finding 3). Its root-text spans cannot fix siblings the anchor misplaced: 0 of 25 accepted on T1718 dev (finding 4). On X0268 it answers a leaf of about 300,000 characters in 76 windows, each allowed only one level, which flattens the outline: 273 of 338 nodes sit at level 2 (finding 6). The largest rendered request was 122,885 characters, although the user message is capped at 100,000 (H7).
- **Interactive runs re-ask.** A gloss request carries its ancestors' English glosses, so each answer changes the requests below it: in E07, 229 of 529 answered request files went unused (finding 7).
- **Out of domain is unreadable with S-F1** (H11, H12).
- **The model arms rest on single answers** from the same model family that seeded the Kuiji gold, with no estimate of answer-to-answer variance. The `claude` API adapter has been tested only against recorded responses ([`pipeline/README.md`](pipeline/README.md)).
- **Not measured at all:** the quality of headings and English glosses, whether the chunk divisions are right, and whether outline-guided chunks help translation. The 180-character chunk budget is an untuned default.

## Repository map

```
README.md          this page
LICENSE            MIT, for the code and our documentation (scope: § Licence)
pipeline/          Python package chinese_workflow: one subpackage per stage, plus common/, llm/, runner/
  schemas/         JSON schemas of the files the stages exchange
projects/          the five project.toml files the runner takes
skills/            chinese-kepan-outliner: the Claude Code skill (v1) that drives the pipeline
context/baseline/  the two outline schemas: the base independent-outline schema and the zh-kepan profile
data/              eval-sets.json + EVAL-SETS.md (registry, splits, rules); reference-outlines/ (committed golds);
                   raw/ and processed/ (gitignored)
experiments/       E00, E01, E06, E07: hypotheses, method, results (records)
tests/             pytest: unit/, e2e/, fixtures/
scripts/           fetch scripts + CHECKSUMS, quickstart, outline validator, eval-set registry tool
docs/              design, architecture, divergences from the Tibetan workflow, glossary (index: docs/README.md)
```

## Where to read more

For a first visit, in this order:
1. [`docs/outliner-design.md`](docs/outliner-design.md): how the outliner is built. For a first pass read §1, §2, the opening of each part of §5, §7, §9 and "Output formats". The rest of §5.2 and §5.5 is rule-level detail about Chinese formulae.
2. [`experiments/E07-capability-sweep-v1/README.md`](experiments/E07-capability-sweep-v1/README.md): what v1 can and cannot do. Read the hypothesis table under "Result", then "Interpretation", which ends with "What we don't know"; the rest is the experiment record. The glossary's "Reading the experiment tables" explains the set names and diagnostic terms the record uses. For the effect on chunking, read [`experiments/E06-capability-sweep/REVIEW-2026-10-02.md`](experiments/E06-capability-sweep/REVIEW-2026-10-02.md) §1, item 8.
3. [`data/EVAL-SETS.md`](data/EVAL-SETS.md): the golds, the splits and the scoring rules.

Then, as needed: [`docs/chinese-workflow-mapping.md`](docs/chinese-workflow-mapping.md) (every divergence from the Tibetan workflow, with its reason), [`docs/glossary.md`](docs/glossary.md), [`experiments/E06-capability-sweep/REPORT.md`](experiments/E06-capability-sweep/REPORT.md), [`docs/architecture.md`](docs/architecture.md), and [`docs/README.md`](docs/README.md) for the index of `docs/`.

### Codes in comments and records

Code comments, docstrings and the experiment records cite some sources by code:
- **R01–R08**, with finding, source and hypothesis numbers (F, S, H, G), are research notes; **Task N**, **M** and **TR** numbers, **Appendix** items and **plan §** are implementation plans. Both are in the development repository and are not included in this copy. A claim that cites one keeps the status its source gave it.
- **D1–D17, D20 and D21** are the divergences from the Tibetan workflow, defined in [`docs/chinese-workflow-mapping.md`](docs/chinese-workflow-mapping.md). D18 and D19 were proposed for the translation stages in a development plan and are not used here.
- **A1–C7** are the directions in §2 of [`experiments/E06-capability-sweep/REVIEW-2026-10-02.md`](experiments/E06-capability-sweep/REVIEW-2026-10-02.md), and **Q1–Q11** the numbered decisions of its §3.
- **H1, H2, …** in an experiment record are that record's pre-registered hypotheses.

Other conventions:
- **Text ids.** Taishō numbers as `T0262`; CBETA file ids as `T09n0262`; CBETA lineheads as `T34n1723_p0850a20` (canon, volume, text number, page, register, line; grammar in [`context/baseline/outline-schema-zh.json`](context/baseline/outline-schema-zh.json)), at release 2026R2.
- **Evidence labels.** In the records and design notes, `VERIFIED` marks a claim reproduced from a cited file, command, count or source, and `HYPOTHESIS` a reading not yet checked. `PARTIAL` and `REFUTED` appear beside R-codes, as the status the research note gave the finding.
- **Vocabulary.** The artefact names are those of the Tibetan workflow: *input-text*, *outlined-text*, *outlined-and-chunked-text* (= *interlinear outline*), *independent outline*, *chunk*, *topic-category*. Chinese-side terms and our pipeline and evaluation terms are in [`docs/glossary.md`](docs/glossary.md).

## Licence

The code and our own documentation are under the MIT License ([`LICENSE`](LICENSE)). Third-party material in the repository keeps its own terms:
- **CBETA text and data** (CC BY-NC-SA 4.0, with CBETA's notice; [`data/reference-outlines/NOTICE`](data/reference-outlines/NOTICE)): the Kuiji gold and the three CBETA 科判 golds under `data/reference-outlines/`, the CBETA XML excerpts and API responses under `tests/fixtures/`, the parser cases (`tests/fixtures/kepan-formulae/`), the recorded model answers (`tests/fixtures/llm-cassettes/`), the tests that quote CBETA text (for example `tests/unit/test_tier2_cases.py`), the skill's formula table (`skills/chinese-kepan-outliner/references/formula-table.md`) and the quotations in E00 (including `level1_adjudication.tsv`).
- **Short CBETA quotations elsewhere** stay under CBETA's terms: the Chinese passages quoted in code comments and docstrings (for example in `pipeline/src/chinese_workflow/outline/tier2/`), in the documentation (for example `docs/outliner-design.md` and `docs/chinese-workflow-mapping.md`) and in the experiment records (for example E06's `projects.json` and `projects-notes.json`).
- **DILA catalogue labels.** The CBETA API responses in `tests/fixtures/cbeta-api/` carry catalogue labels from DILA (Dharma Drum Institute of Liberal Arts), for which no licence is stated.
- **DILA YBh outline structure** (CC BY-SA 4.0): the two YBh golds (`data/reference-outlines/T1602/`, `T1605/`) and `tests/fixtures/dila-ybh/`.
- **sdp** is never redistributed. No sdp heading, tree or span is committed; committed files hold only aggregate counts, sdp node ids and a few locator facts ([`data/EVAL-SETS.md`](data/EVAL-SETS.md), "Rules for gold data", rule 1). A fixture in sdp's format is synthetic and says so.
