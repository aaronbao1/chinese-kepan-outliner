# pipeline/ — `chinese_workflow`

The Python package of the outliner. One subpackage per stage. Each stage's README states its **input artefact → output artefact** using the artefact names of Kurt Keutzer's Tibetan workflow (see [`docs/glossary.md`](../docs/glossary.md)). Stages talk through files and objects, never by importing each other's internals ([`tests/unit/test_stage_boundaries.py`](../tests/unit/test_stage_boundaries.py) checks this). The first-time setup, with the data fetch, is the top-level [Quickstart](../README.md#quickstart).

The second column names the step of the Tibetan workflow that each stage corresponds to, with its section in his workflow manuals ("Agentic Tibetan 1.0" unless "Manual 2.2" is named); the manuals are not included in this copy. D-numbers are the divergences listed in [`docs/chinese-workflow-mapping.md`](../docs/chinese-workflow-mapping.md).

| Stage | Tibetan-workflow step | Input → Output | Status |
|---|---|---|---|
| `ingest` | text preparation: e-text, structure and variants (§1a, §1b, §1e1, §1e2 in part) | CBETA XML (or other e-text) → **input-text** + preserved structural markup + apparatus side-table (partial variorum-text) | built (lines, `structure.json`, normalization config, `run`/CLI); the apparatus side-table is not built |
| `outline` | outlining, §1f Step 1 (`outliner-skill`) | input-text (root) [+ commentary input-text] → **independent outline** (`outline.json` + `.md`/`.docx` in Kurt's format) + **outlined-text** (explicit / editorial / inferred nodes; anchored spans) | built: tier 1, tier 2, scheme prior, merge, anchor, resolver + gloss (adapters none / replay / claude / interactive), render, oracle |
| `segment` | sentence segmentation, §1f Step 2 (`sentence-segmenter-skill`) | outlined-text → sentence boundaries (`sentences.json`) | built (strategies 1–2) |
| `chunk` | chunking, §1f Step 3 / §3a (`chunking-skill`); ours is deterministic code (D14) | outlined-text + sentences → **outlined-and-chunked-text** = interlinear outline (`chunks.md`/`.json`/`.docx`; ≤ 6 sentences and a length budget per chunk, never splitting a sub-chunk leaf; sibling leaves merged upward within one parent, D6, D16) | built |
| `context` | gathering the context a chunk needs: commentary, parallels, glossaries, past translations (§1d; Manual 2.2 §3b1–§3b2d) | chunk + topic-category → context bundle (commentary passages, parallel texts, glossary entries, prior translations) | stub |
| `translate` | chunk-by-chunk translation and stitching (Manual 2.2 §3b2e, §3a3) | chunk + context bundle + Project Instructions → draft | stub |
| `export` | the knowledge graph (D20) | independent outline → BDRC-shaped JSON-LD, one outline per (work, scheme) | built (v0) |
| `eval` | — (ours) | independent outline (`outline.json`) vs gold kēpàn; chunk invariants (`chunks.json`); translation sample → `metrics.json` | built: gold builders, registry, scorer (`eval.score`), chunk invariants; translation-sample evaluation not yet |

Shared, not stages: `common/` (paths, JSON I/O, lineheads, draft tree → zh-kepan documents, the split guard, project files, a small docx writer), `llm/` (cached, replayable model client), `runner/` (the headless harness). Module-level design: [`docs/outliner-design.md`](../docs/outliner-design.md). Contracts between stages: [`schemas/`](schemas/).

## Install

You need Python 3.11 or newer: project files are read with `tomllib` (`requires-python = ">=3.11"` in [`pyproject.toml`](pyproject.toml)). On macOS, `/usr/bin/python3` is 3.9; with it the editable install fails with a misleading pip error ('File "setup.py" or "setup.cfg" not found'), not with a Python-version error.

```bash
cd pipeline
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

With [uv](https://docs.astral.sh/uv/) instead:

```bash
cd pipeline
rm -rf .venv   # a failed python3.12 -m venv leaves a half-made one behind
uv venv --python 3.12 .venv && uv pip install --python .venv -e '.[dev]'
```

A uv venv has no pip of its own, so install into it with `uv pip`. Use the uv route if `python3.12 -m venv` fails inside `ensurepip` (seen with Homebrew Python on a recent macOS, as a pyexpat "Symbol not found" error). That failure leaves a half-made `.venv`, and `uv venv` refuses to overwrite it, hence the `rm -rf .venv`.

From the repository root, `bash scripts/quickstart.sh` makes the venv this way (falling back to uv), installs the package, fetches the CBETA files a project needs and runs it ([`scripts/quickstart.sh`](../scripts/quickstart.sh)).

What gets installed ([`pyproject.toml`](pyproject.toml)): `lxml` and `jsonschema`; the `dev` extra adds `pytest` and `ruff`; the `llm` extra adds the `anthropic` SDK (below). `ruff` is not a gate: `ruff check` reports findings on the current code.

## Run

```bash
.venv/bin/python -m chinese_workflow.runner run ../projects/<id>/project.toml [--out DIR] [--frozen TAG]
```

- The runner reads the CBETA XML that the project names from `data/raw/cbeta/` (fetched by `scripts/fetch_cbeta.sh`; see the top-level Quickstart), or from the whole-corpus clone `data/raw/cbeta/xml-p5/` when that exists (`common/paths.py`, `cbeta_xml_path`).
- It runs ingest → outline → segment → chunk → chunk invariants → export and writes `data/processed/<project id>/` unless `--out` says otherwise. The files are listed in the top-level README and in the runner's docstring ([`src/chinese_workflow/runner/__main__.py`](src/chinese_workflow/runner/__main__.py)).
- Exit 0 when every stage ran and the chunk invariants hold; 1 otherwise; 2 when the split guard refused the run.
- The runner takes only `--out` and `--frozen`. Everything else (texts, mode, scheme, span, outline source, adapter, chunk size) is set in `project.toml`. Its keys and defaults are in the docstring of [`src/chinese_workflow/common/project.py`](src/chinese_workflow/common/project.py); the five shipped projects are in [`../projects/`](../projects/).
- `--frozen TAG` names a frozen outliner (for example `outliner-v1-frozen-2026-10-03`, the development-repository tag E07 ran under); the name is recorded in `run.json`. Without it the split guard refuses any read of the test or reserve spans of T1718 and T1723 ([`docs/outliner-design.md`](../docs/outliner-design.md) §3, [`data/EVAL-SETS.md`](../data/EVAL-SETS.md)).

The stages also have their own command lines. For example, `python -m chinese_workflow.outline build --project ../projects/<id>/project.toml --out DIR` builds the outline alone, and its flags (`--span`, `--source`, `--adapter`, …) override the project file. `python -m chinese_workflow.eval.score` scores an `outline.json` against a registered gold. The skill [`skills/chinese-kepan-outliner/SKILL.md`](../skills/chinese-kepan-outliner/SKILL.md) walks through the outline, segment, chunk and export commands, and [`docs/outliner-design.md`](../docs/outliner-design.md) §9 and §11 give the scorer's and the runner's options.

## Tests

```bash
.venv/bin/pytest ../tests -q
```

With `../tests` as its argument, pytest does not read `pyproject.toml` and imports `src/` through the editable install. Run with no arguments from `pipeline/` (`.venv/bin/python -m pytest -q`), it reads `pyproject.toml`, which points it at `../tests` and puts `src/` on the path. Tests that need data you have not fetched are skipped, not failed; [`tests/README.md`](../tests/README.md) lists the counts to expect. In the development repository at tag `outliner-v1-frozen-2026-10-03`, with every `scripts/fetch_*.sh` run, the suite gave 1,374 passed, 11 skipped, 1 xfailed ([`experiments/E07-capability-sweep-v1/README.md`](../experiments/E07-capability-sweep-v1/README.md), "Instrument"). This repository leaves out the tests of material it does not include, so its count differs slightly.

## Model-assisted runs

The shipped projects set `source = "tier2"` and `[resolver] adapter = "none"`: no model is called, and headings stay in the source's own Chinese. The model-assisted resolver and gloss add inferred nodes, root-text spans and English headings (`heading_en`). They run only when the project sets **both** `source = "hybrid"` and an adapter other than `none` (`src/chinese_workflow/outline/pipeline.py`). With `source = "tier2"`, a `claude` adapter makes no model call and gives no warning.

**With the Anthropic API (`claude` adapter):**

```bash
.venv/bin/pip install -e '.[dev,llm]'     # or: uv pip install --python .venv -e '.[dev,llm]'
export ANTHROPIC_API_KEY=...
```

Then, in the project's `project.toml` (`source` is a top-level key: change the existing line, which sits above the first `[section]`):

```toml
source = "hybrid"

[resolver]
adapter = "claude"
budget_usd = 5.0        # optional cap in USD (example value); no cap unless set
# model = "claude-opus-5"   # the default
# max_tokens = 64000        # the default
```

- Defaults are in [`src/chinese_workflow/llm/client.py`](src/chinese_workflow/llm/client.py): model `claude-opus-5`, `max_tokens` 64000, effort `high`, no budget cap. A set `budget_usd` is checked before every call.
- Answers are cached per request hash under the run directory (`outline/llm/`), so a re-run makes no new calls for requests already answered.
- The `claude` adapter has been tested only against recorded responses (cassettes; [`docs/outliner-design.md`](../docs/outliner-design.md) §14, row 9). E06 and E07 used the `interactive` adapter instead.

**Other adapters:**
- `interactive`: the build writes request files and stops. A Claude Code session answers them and the build is re-run. This is how E06 and E07 ran the model arms; the procedure is step 3 of [`skills/chinese-kepan-outliner/SKILL.md`](../skills/chinese-kepan-outliner/SKILL.md).
- `replay`: answers come only from a recorded cassette (`[resolver] cassette = "<path>"`); a request with no recorded answer is an error.
