# E06 — capability sweep: the frozen v0 outliner on every non-test dataset

> **Note (2026-10-05, clean copy):** this record is kept as written, except that its closing list of proposed next runs was removed; its references to planning notes, research threads (R-codes), NEXT_STEPS and the freeze tags point to the development repository and are not part of this copy.

**Date:** 2026-10-01 (hypotheses and decision rules written before any run)  **Owner:** Aaron Bao (hypotheses drafted by Claude for Aaron to accept or replace)  **Status:** done 2026-10-01: read-out complete, validation look #2 logged, verification pass run, nothing committed. Parser-gate call and API budget pending (Aaron). Capability report: `REPORT.md`

> **Note (2026-10-04).** Kept as written. E06 was committed on 2026-10-03 (`813dd17`), so "nothing committed" no longer holds; its review led to the follow-up merged in `e02b42e`, re-measured by E07 (`../E07-capability-sweep-v1/README.md`).

## Hypothesis

Pre-registered 2026-10-01, before any E06 build or score. Frozen outliner: tag `outliner-v0-frozen-2026-10-01` = pipeline commit `8498eb3` (pipeline/ clean at tag time). "S-F1" etc. as in `chinese_workflow.eval.score`; t = 0 unless stated.

- **H1 (no regression since E01 read-out 1).** At the frozen commit, tier 2 on T1723 dev keeps S-F1 = 1.000, and tier 2 on T1718 validation stays below the parser gate (S-F1 < 0.40). Commits since `685a8a4` (incipit lemmas, review fixes) do not move either across those lines.
- **H2 (the resolver adds detection on Zhiyi).** On T1718 validation, hybrid (tier 2 + resolver + gloss, subagent-answered) has a locator-only F1 at least 0.05 above tier 2's.
- **H3 (the resolver costs precision where explicit structure is complete).** On T1723 dev (the 陀羅尼品, gold at full depth), hybrid S-F1 precision is below tier 2's: inferred children the gold does not have count as FP inside `coverage_spans`.
- **H4 (self-outlining transfer, CBETA 科判 golds).** On each of X0268, P1573 and D8842, tier 2 S-F1 < 0.30, and tier 1 (no 科判-typed mulu) S-F1 ≤ 0.05. The formula parser was developed on Kuiji/Zhiyi-style 疏 prose, and these 科判 trees are CBETA editorial markup over texts outside that style.
- **H5 (structure-only YBh).** On T1605 and T1602, every arm's structure-mode F1 (matched on heading_src) is < 0.10. DILA's headings are 韓清淨's or 早島・毛利's wording, not the treatise's, so heading-keyed matching cannot score text-derived headings.
- **H6 (root-text anchoring, 陀羅尼品).** Against the Kuiji gold keyed on `root_text.start` (T0262 陀羅尼品, dev), tier 2 S-F1 ≥ 0.80: the anchor step maps Kuiji's lemmas onto the sūtra lines the gold's spans start at.
- **H7 (model-only is below hybrid on root text).** On T0262 序品 against the sdp T0262 gold (key `root_text.start`, dev and validation regions), model-only S-F1 < 0.20 and below the hybrid with Zhiyi's commentary.

All are falsifiable by one read-out each. None is a headline: dev and validation never are, the Kuiji gold is `draft-unreviewed` and Claude-seeded, and the OOD golds are `imported-unchecked`.

## Why it matters / what decision it informs

- The **parser-gate call** pending from E01 (NEXT_STEPS §−1, 2026-09-27 item (b)): does the resolver rescue the Zhiyi side, or must attachment move wholesale to the resolver?
- **API key and budget for the `claude` adapter** (same item (e)): is the hybrid arm worth paying for, given what a Claude-answered resolver does here?
- **Out-of-domain capability**: what the v0 outliner does on texts and styles it was not built on. Reported to Kurt with the spec deliverables.

## Method

- **Freeze.** Lightweight local git tag `outliner-v0-frozen-2026-10-01` on `8498eb3`; every build and score that the split guard gates runs with `--frozen outliner-v0-frozen-2026-10-01`. E06's harness lives here and does not modify `pipeline/`.
- **Sets** (`data/eval-sets.json`; `data/EVAL-SETS.md` rules 1–12). Test spans of T1718 and T1723 are **not read and not scored** (Aaron, 2026-10-01: test stays blind until the parser-gate call and the Kuiji test-key review). Reserve is never scored.

| Set | Gold | Key | Split / scope | Arms |
|---|---|---|---|---|
| T1718-dev | `sdp-T1718-zhiyi-wenju` | commentary.explained | dev (served 卷一上) | tier1, tier2, hybrid |
| T1718-validation | `sdp-T1718-zhiyi-wenju` | commentary.explained | validation — **look #2**, logged in E01's `looks.json` | tier1, tier2, hybrid |
| T1723-dev | `kuiji-xuanzan` | commentary.explained | dev (陀羅尼品) | tier1, tier2, hybrid, oracle |
| T0262-dharani-root | `kuiji-xuanzan` | root_text.start | dev | tier2, hybrid, model-only |
| T0262-xu-root | `sdp-T0262-zhiyi-wenju` | root_text.start | dev, validation (regions inherited from T1718) | tier1, tier2, hybrid, model-only |
| OOD-X0268, OOD-P1573, OOD-D8842 | `cbeta-mulu-*` | commentary.explained (self) | whole, frozen | tier1, tier2, hybrid |
| OOD-T1605, OOD-T1602 | `ybh-*` | structure | whole, frozen | tier1, tier2, hybrid |

- **Sanity checks.** Each gold scored against itself (expect F = 1.000 on every row it can score); the oracle arm on T1723 dev; the 1,072-test suite (`pytest ../tests`: 1,072 passed, 11 skipped at the frozen commit, before E06).
- **Whole-pipeline runs.** `python -m chinese_workflow.runner run` on every `projects/*/project.toml` (chunk invariants, export), adapter `none`.
- **The hybrid and model-only arms.** No API key exists here, so the resolver runs through the `interactive` adapter. Its request files are answered by Claude Opus 5.5 subagents (one workflow), each told to read only its request files and `skills/chinese-kepan-outliner/references/`, never a gold, fixture or research file. A leakage audit greps their transcripts for gold paths afterwards. This is disclosed with every hybrid and model-only number: it is *Claude Code via the interactive adapter*, not the `claude` API config, and the Kuiji gold was seeded by the same model family (R06 F19).
- **Metrics.** S-F1, F-F1 at t = 0 and t = 1; without `anchor_inherited`; per depth; locator-only F1; child-count accuracy; structure-mode F1 for YBh. Validation and OOD are reported in aggregate only; per-node diagnostics are dev-only.

### Method addenda (after pre-registration, 2026-10-01)

Written after the run. The Hypothesis section and the Method above are unchanged. `metrics.json` `provenance.readme_sha256` (`d100a603…`) is the hash of this file before the Status line, these addenda, Result and Interpretation were written. The following changed after the hypotheses were written; details are in `SUMMARY.md` § "Design choices".

1. **The T1718-devval cell was added after review and is not in the matrix.** The pre-registered T1718-validation row builds over the validation span only. The design check *reachability* finds 0 of its 101 counted gold nodes reachable: each one hangs under dev ancestors that a validation-only build cannot supply, so S-F1 and F-F1 are 0 there for any outliner. T1718-devval builds T34n1718 over dev + validation and scores both rows.
   - `SUMMARY.md` reads H1's validation clause on devval. The hypothesis panel read it on the pre-registered row and treated devval as post hoc, and the verdict is the same either way.
   - Devval turned out not to be readable either (Result).
2. **The OOD 科判 inputs have the 科判 removed.** The CBETA 科判 golds *are* CBETA's `cb:mulu type="科判"` markup, and tier 1 reads that markup as nodes. So the README arms read `runs/_inputs/<file>.no-kepan.xml`: the 科判 mulu are removed, and lines, reading text, notes and 卷 marks were checked identical.
   - `tier1-markup` and `tier2-markup` on the original XML are kept as **LEAKED diagnostics**, never results.
   - No hybrid runs on the original, because its requests would show the gold's labels.
3. **The model-only arm needed its own wiring.** `pipeline.build` has no model-only path. The harness builds it in four steps:
   - the tier-1 品 pin of the target chapter;
   - the set's level-1 prior (Kuiji's three parts on T0262-dharani-root, none on T0262-xu-root);
   - `resolver.resolve(commentary=None, tasks=('subdivide',))`, for up to 3 subdivide rounds;
   - no anchor step and no gloss.
4. **How the interactive adapter's requests were answered.**
   - 84 answer subagents (Claude Opus 5.5, one workflow, one prompt template) answered 80 distinct request hashes. Each read only its own request file.
   - By task, over the 84 answers: gloss 47, subdivide 23, root-spans 7, adjudicate 7. Over the 80 distinct hashes: gloss 45, subdivide 23, root-spans 5, adjudicate 7.
   - Four hashes (two root-spans, two gloss) were answered twice, independently, in two cells. This contradicts `SUMMARY.md` design choice 14 ("answered once"). Each cell is scored on its own answer.
5. **There were eight answer rounds.** Rounds r1–r8 had 20 / 21 / 20 / 10 / 8 / 2 / 2 / 1 answers. The resolver tasks run in order (root-spans → subdivide → adjudicate, then gloss), and an answer can open new requests: model-only re-offers leaves for up to 3 rounds, and hybrid-OOD-T1605's subdivide ran 7 requests.
6. **`--frozen` was used only on the OOD score rows.** Builds run the split guard *without* the tag, so the guard itself refuses any test or reserve line; every cell's guard log shows dev, validation or unsplit reads only. `--frozen` is passed only to the OOD score rows, where the scorer requires it. An OOD row was scored only when `pipeline/` was byte-identical to the tag both at build and at score time.
7. **Validation look #2 took two passes.** The first pass (09:40 UTC) scored tier 1 and tier 2 on T1718-validation and T0262-xu-root while the LLM arms there were still pending. The hybrid and model-only arms followed at 10:58. The leakage audit found that no answer agent saw a score. Five entries were appended to E01's `looks.json`.
8. **A verification pass ran after the run.** It had six parts:
   - a leakage audit of every agent transcript (`audit_leakage.py` → `leakage-audit.json`);
   - an independent re-score of 16 rows;
   - a mechanism read, per node, on the dev subtrees only;
   - a coding of the problems the answer agents reported with their requests;
   - an aggregate OOD analysis (`ood-analysis.json`);
   - three independent readers per hypothesis.

   The verification scripts other than `audit_leakage.py` ran from the session scratchpad and are not in this directory.
9. **The freeze tag is no longer local.** Method calls `outliner-v0-frozen-2026-10-01` a lightweight local tag. On 2026-10-03 it was pushed to `origin`, together with E07's `outliner-v1-frozen-2026-10-03`. It still points at `8498eb3`, so nothing measured here changes.

## Result

Frozen tag `outliner-v0-frozen-2026-10-01` = `8498eb3`. `pipeline/` was byte-identical to the tag for every build and score (`metrics.json` provenance), and the verification pass re-checked this. The numbers come from `metrics.json`, which `SUMMARY.md` renders with per-depth rows. t = 0 unless stated.

**No row is a headline.** Dev and validation never are. The Kuiji gold is `draft-unreviewed` and seeded by claude-opus-5-5 (R06 F19). The sdp golds are eval-only, and the OOD golds are `imported-unchecked`. **hybrid and model-only are Claude Code answering through the interactive adapter** (model `claude-code-session`), not the `claude` API config.

### Scores

S-F1 matches on (key line, depth, parent path). Locator-only matches on the key line alone: detection without attachment. For YBh the column gives heading-only F. "gold / pred" are the nodes the scorer counted.

| Set (gold, key) | Row | Arm | S-F1 t=0 P / R / F | S-F1 t=1 F | locator-only F t=0 / t=1 | gold / pred |
|---|---|---|---|---|---|---|
| T1718-dev (sdp, commentary) | dev | tier1 | 1.000 / 0.083 / 0.154 | 0.154 | 0.154 / 0.154 | 12 / 1 |
| | dev | tier2 = hybrid | 0.034 / 0.083 / 0.049 | 0.049 | 0.244 / 0.390 | 12 / 29 |
| **T1718-validation** (README row) | validation | tier2 | 0.000 / 0.000 / 0.000 | 0.000 | 0.118 / 0.258 | 101 / 85 |
| | validation | hybrid | 0.000 / 0.000 / 0.000 | 0.000 | 0.125 / 0.260 | 101 / 91 |
| T1718-devval (post hoc) | validation | tier2 | 0.000 / 0.000 / 0.000 | 0.000 | 0.101 / 0.189 | 101 / 58 |
| | validation | hybrid | 0.000 / 0.000 / 0.000 | 0.000 | 0.320 / 0.400 | 101 / 99 |
| T1723-dev (Kuiji draft, commentary) | dev | tier1 | 1.000 / 0.022 / 0.043 | 0.043 | 0.043 / 0.043 | 45 / 1 |
| | dev | tier2 = hybrid = oracle | 1.000 / 1.000 / 1.000 | 1.000 | 1.000 / 1.000 | 45 / 45 |
| T0262-dharani-root (Kuiji draft, root) | dev | tier2 | 1.000 / 0.293 / 0.453 | 0.453 | 0.453 / 0.453 | 41 / 12 |
| | dev | hybrid | 1.000 / 1.000 / 1.000 | 1.000 | 1.000 / 1.000 | 41 / 41 |
| | dev | model-only | 0.029 / 0.024 / 0.026 | 0.105 | 0.658 / 0.868 | 41 / 35 |
| T0262-xu-root (sdp, root) | dev | tier2 = hybrid | 0.000 / 0.000 / 0.000 | 0.300 | 0.316 / 0.900 | 11 / 8 |
| | dev | model-only | 0.000 / 0.000 / 0.000 | 0.625 | 0.308 / 0.625 | 11 / 2 |
| | validation | tier2 | 0.000 / 0.000 / 0.000 | 0.000 | 0.197 / 0.197 | 101 / 21 |
| | validation | hybrid | 0.000 / 0.000 / 0.000 | 0.000 | 0.478 / 0.489 | 101 / 79 |
| | validation | model-only | 0.000 / 0.000 / 0.000 | 0.222 | 0.256 / 0.256 | 101 / 16 |
| OOD-X0268 (CBETA 科判, self) | whole | tier1 = tier2 | 0.000 / 0.000 / 0.000 | 0.000 | 0.000 / 0.000 | 2611 / 26 |
| | whole | hybrid | 0.000 / 0.000 / 0.000 | 0.000 | 0.000 / 0.000 | 2611 / 40 |
| OOD-P1573 (CBETA 科判, self) | whole | tier1 = tier2 | 0.500 / 0.008 / 0.016 | 0.031 | 0.016 / 0.031 | 127 / 2 |
| | whole | hybrid | 0.176 / 0.024 / 0.042 | 0.056 | 0.194 / 0.222 | 127 / 17 |
| OOD-D8842 (CBETA 科判, self) | whole | tier1 = tier2 | 0.500 / 0.025 / 0.048 | 0.048 | 0.048 / 0.048 | 40 / 2 |
| | whole | hybrid | 0.167 / 0.025 / 0.043 | 0.130 | 0.130 / 0.174 | 40 / 6 |
| OOD-T1605 (YBh, structure) | whole | tier1 / tier2 / hybrid | 0.000 each | — | heading-only 0.000 / 0.002 / 0.013 | 2605 / 10, 28, 86 |
| OOD-T1602 (YBh, structure) | whole | tier1 | 0.000 / 0.000 / 0.000 | — | heading-only 0.000 | 2594 / 11 |
| | whole | tier2, hybrid | **failed** (pipeline bug, below) | | | |

Notes on the table:
- **Zeros by construction.** Several zeros say nothing about the outliner:
  - T1718-validation (the pre-registered row): S-F1 and F-F1 are 0 for any outliner at t = 0 and t = 1, because 0 of its 101 counted gold nodes are reachable from a validation-only build (design check *reachability*). Only locator-only carries information there.
  - T0262-xu-root at t = 0: every arm's level 1 is the tier-1 序品 pin, while the gold's dev level 1 starts one line below it, so top-down matching finds nothing. Read t = 1 and locator-only.
  - OOD-X0268: every gold node starts inside one tier-1 leaf that no arm subdivides (Interpretation).
  - YBh: the predicted-node counts cap F below 0.10 (H5).
- tier1 scores 0 at t = 0 with 0 counted predictions on T1718-validation, on the validation row of T1718-devval and on both T0262-xu-root rows. On T0262-xu-root dev it reaches 0.167 at t = 1 (S-F1 and locator-only).
- The dev row of T1718-devval is tier2 = hybrid: 0.037 / 0.083 / 0.051, locator-only 0.256 / 0.359, 12 / 27.
- "tier2 = hybrid" means identical scores, not identical outlines. hybrid-T1718-dev adds 12 inferred nodes, none with a commentary line, so the commentary key cannot see them. hybrid-T1723-dev changes only root spans.
- LEAKED diagnostics (not results): P1573 markup arms score locator-only 0.992 and S-F1 0.023 (127 / 129); D8842 markup arms score 0.976 and 0.024 (40 / 42); the X0268 markup cells failed on a tier-1 bug.
- E01 parser gate, informative only: S-F1 t=0 on T1718 is 0.000 on both validation rows, which is below 0.40, and t=1 − t=0 = 0.

### Hypotheses

Each hypothesis was read by three readers independently. The verdict shown is the majority; the other verdicts are in brackets.

| H | Claim (short) | Panel | Why |
|---|---|---|---|
| H1 | No regression: T1723 dev tier2 = 1.000, and T1718 validation tier2 < 0.40 | **SUPPORTED-TRIVIALLY** (3/3) | T1723 dev is still 45/45. T1718 validation tier2 is identical to E01 read-out 1 (S-F1 0, locator-only 0.118, 85 counted). But the T1718 clause cannot fail there (reachability 0/101). The T1723 clause rests on the parser's own development chapter, scored against a Claude-seeded draft gold. |
| H2 | hybrid locator-only ≥ tier2 + 0.05 on T1718 validation | **NOT SUPPORTED** (3/3) | +0.007 (0.118 → 0.125; one extra hit). The post-hoc T1718-devval row shows +0.219 (0.101 → 0.320), but that row was not pre-registered. All 24 of its extra hits come from resolver-inferred children, and every one of them is an S-F1 FP. |
| H3 | hybrid S-F1 precision < tier2 on T1723 dev | **NOT SUPPORTED** (2) [UNDETERMINED 1] | Both are 1.000, but the mechanism never ran, so this is a non-test. There was no subdivide or adjudicate request: the largest leaf root span is 348 characters, under the 360 limit, and the parser report is empty. 0 nodes were added. |
| H4 | OOD 科判: tier2 < 0.30 and tier1 ≤ 0.05 on X0268, P1573 and D8842 | **SUPPORTED-TRIVIALLY** (2) [SUPPORTED 1] | All six inequalities hold (0.000 / 0.016 / 0.048). But tier 2 adds 0 nodes on all three texts, so tier2 = tier1, and the predicted-node counts nearly fix the bounds. Only D8842's tier-1 clause could have failed (0.048 against 0.05). |
| H5 | YBh: every arm < 0.10 | **UNDETERMINED** (2) [SUPPORTED-TRIVIALLY 1] | The 4 scored arms are 0, which the node counts guarantee (max F 0.008–0.064), as does the top-down match. T1602 tier2 and hybrid failed on a pipeline bug, so "every arm" was not measured. |
| H6 | tier2 S-F1 ≥ 0.80 on T0262-dharani-root | **NOT SUPPORTED** (3/3) | 0.453 (P 1.000, R 0.293). The anchor is exact wherever a lemma exists (12/12). The other 29 of the 41 gold spans are the drafter's manual cuts with no lemma, so 0.453 is the ceiling for any anchor that works from lemmas only. |
| H7 | model-only S-F1 < 0.20, and below hybrid, on T0262-xu-root | **NOT SUPPORTED** (2) [UNDETERMINED 1] | At t = 0 every arm scores 0 by construction: the gold's level 1 starts one line below the tier-1 pin. So "below the hybrid" fails as a tie. At t = 1 model-only beats hybrid: 0.625 against 0.300 on dev, 0.222 against 0.000 on validation. Locator-only favours hybrid on both rows: dev 0.316 against 0.308 (0.900 against 0.625 at t = 1), validation 0.478 against 0.256. |

None of the seven is supported on its merits.

### Sanity

- **Gold against itself.** Each gold was scored against itself: 13 of 13 set rows give S-F1 = F-F1 = 1.000 (`SUMMARY.md` § Sanity). The oracle arm on T1723 dev scores 1.000.
- **Perturbations** (`sanity.json`). 15 of 18 behave as expected. The 3 that do not are scorer defects, not data errors:
  - two come from the t = 1 greedy sibling pairing: a uniform +1-line shift scores t = 1 F 0.654 on P1573 and 0.733 on Kuiji dev instead of about 1;
  - one comes from structure-mode merged_range absorption.
- **Independent re-score.** 16 rows (12 cells) were re-scored with the scorer CLI from the saved outlines. Every compared field matches `metrics.json` exactly. Every outline sha256 equals the recorded one, `pipeline/` is identical to the tag, and the registry sha256 is `6b7d67cf…`.
- **Test suite.** At the frozen commit, before E06: 1,072 passed, 11 skipped (Method). It was not re-run after E06; `pipeline/` did not change.
- **Answer repeatability** (`leakage-audit.json` `duplicate_hash_answers`). The four hashes answered twice are the only repeat measurement of the LLM arms. The Kuiji root-spans request got the same 29 starts and 29 ends twice, although the response files differ. The T1718 dev + validation root-spans request did not: both answers covered 13 of the 15 nodes either one answered, and they agree on 13 starts and 12 ends. Every other LLM answer was drawn once, so no hybrid or model-only row has a variance estimate.
- **No interval estimates.** No row carries a confidence interval. The dev rows count 11–45 gold nodes, and the T1718 / T0262 validation rows 101.

### Leakage audit

`audit_leakage.py` writes `leakage-audit.json`, which holds paths, counts and digests only. All of the following are VERIFIED.

- **Answer agents.** 84 agents made 483 tool uses, and 0 were FORBIDDEN: none touched a gold, the raw sdp, YBh or CBETA data, `tests/`, `context/`, `skills/`, `docs/`, another request or response, a pipeline outline, a score file or the web.
  - 16 accesses in 15 agents were SUSPECT, and all are explained: 14 are `mkdir` or `ls` of the agent's own responses directory, and 2 are scratch files the agent wrote itself.
  - All 84 prompts are identical once paths and hashes are normalised. Each agent wrote its own response and no other. One agent also wrote two scratch files in the session scratchpad (the 2 SUSPECT accesses above).
- **Request files.** They hold 5,110 dev and 14,728 validation lines of T1718/T1723, with 0 test and 0 reserve lines. No gold-marker string appears in any request.
- **Driver and finalize agents.** 9 agents made 66 tool uses, all allowed.
- **Harness-building agents.** 6 agents made 336 tool uses and 0 reads of a "Do not open while developing" file. One command named such a file without opening it. Their programmatic reads of the sdp gold, for harness development, printed no sdp heading. Every test or reserve linehead in their tool results is one that committed docs already quote (0 undocumented).
- **Output files.** E06's output files pass the check in `tests/unit/test_sdp_eval_only_guard.py` with 0 hits.
- **HYPOTHESIS: the T0262-dharani-root 1.000 is same-model-family agreement, not a leak.**
  - The agent behind it read only its own request.
  - A second, independent agent answering the identical request gave the same 29 starts and 29 ends (in a differently worded response).
  - Both match the gold's 29 spans with basis `manual` (the drafter's reading), and claude-opus-5-5 seeded the gold.
  - A transcript audit cannot tell shared judgement from spans the text alone fixes, and it cannot see pretraining knowledge.

### Failures and defects

**Failed cells (4).**
- **tier2-OOD-T1602 and hybrid-OOD-T1602.** `outline/tier2/parser.py` `_self_mode_order` (lines 743–762) repairs an out-of-order explained position only for items never entered (`and not c.entered`, line 750). In T1602, one entered item of a 17-item listing is taken up before its elder sibling. The validator then rejects the whole 117-node outline, and the resolver refuses it as input.
- **tier1-markup-OOD-X0268 and tier2-markup-OOD-X0268** (LEAKED diagnostics only). `outline/tier1.py` `_unit_end` (lines 216–224) trims each unit back to its own `cb:div`, and `_self_span` (line 365) uses that end for 科判 units. A 科判 parent whose mulu sits in another div therefore ends before its child, giving 211 `child-outside-parent` errors.

**Other defects.** These were found while `pipeline/` was frozen, so none is fixed.
- **Resolver request size.**
  - `MAX_TEXT_CHARS` (`resolver.py:93`) counts text characters, but a block renders with a linehead on every line, which roughly doubles it, and the outline block has no limit. Requests reached 177,081 characters. 7 request files (6 distinct requests) exceeded 120,000.
  - `_comm_block` cuts the commentary from the front.
  - `_jobs_adjudicate` drops the root block when the union of spans is too long.
  - `_jobs_root_spans` shows only the admissible range.
  - Summed over cells, root-spans left 119 nodes unanswered and skipped 16, and adjudicate left 54 unanswered. The merge stage rejected 0 of the items that were answered.
- **Sūtra-mode resolver output can be invisible to the commentary key.** Subdivide children carry `commentary.explained` only when the model supplies one; in hybrid-T1718-dev that is 0 of 12. Subdivide also chooses leaves by root-span length, so the 13,945-character commentary leaf in the Zhiyi project is never offered.
- **Scorer** (`eval/score.py`, frozen):
  - `_match` pairs siblings greedily, so t = 1 is a lower bound.
  - Structure mode never absorbs a merged_range split whose parts have their own headings (T1602 only).
  - The root-text region rule leaves predictions in a region with no split as split_unknown, which undercounts FP.
  - `NO_HEADLINE_STATUS` lacks `imported-unchecked`. This is overridden here: every row has headline false.
- **Harness.** The reachability check is necessary but not sufficient. On T1718-devval validation it reports 101/101 reachable, yet S-F1 is 0 because of the gold's structure.
- **Provenance.** `common/outline_doc.py` `pipeline_commit` marks `+dirty` from a repo-wide status. `cell.json` records the check of `pipeline/` alone.
- **Stale requests.** 16 superseded gloss requests (state `stale`) remain under `runs/`. None blocks a score.

**Corrections to `SUMMARY.md`** (a generated file, not edited here). Design choice 14 says identical requests were answered once, and that hybrid-T1718-devval and hybrid-T0262-xu-root build the same outline. In the run, four shared hashes were answered twice (`reused_responses` is empty in every cell). Those two cells shared only their root-spans request: they have 132 and 129 nodes, and their subdivide and adjudicate requests were answered separately.

### Not run or not measured

- **Test spans** (T1718 釋方便品; T1723 序品 and 譬喻品 opening). Not read and not scored, by Aaron's decision of 2026-10-01: test stays blind until the parser-gate call and the Kuiji test-key review (Method). Reserve was never scored. Every number here is dev, validation or OOD.
- **T0262 序品 against the Kuiji gold.** Kuiji's 序品 commentary is a T1723 test span (`data/EVAL-SETS.md`, "Root-text experiments and the splits"). The Kuiji gold has no validation nodes, so its only E06 rows are the 陀羅尼品 dev subtree.
- **E04 (cross-lingual, `r03-piyu-opening`).** Not runnable:
  - its answer key is test-split material under "Do not open while developing";
  - Kurt's Tibetan skill is not yet saved in the repo (NEXT_STEPS §0);
  - D4017 ends at ch. 11, so the 陀羅尼品 dev chapter has no Tibetan counterpart.
- **The sdp T0262 gold outside 序品.** 1,608 of its 2,048 nodes have no split (registry open call, NEXT_STEPS §−1). T0262-xu-root scores only the 序品 nodes with a dev or validation line (11 and 101).
- **Heading and gloss quality.** Outside the YBh structure rows no score compares headings: S-F1 and locator-only key on lines. No score reads `heading_en` (the gloss), and `sdp-T1718-heading-check` was not used. Gloss answers were required before a cell could score (SUMMARY design choice 13), but their quality is unmeasured.
- **`sdp-crosswalk-T0262-T1718`** (E03's split by origin) was not used. F-F1 is in `SUMMARY.md` but not analysed here.
- **Parser cases** (`kepan-formulae-cases`) are exercised only by the pytest suite, not scored as a set.
- **T1602 tier 2 and hybrid** failed, so H5's "every arm" was not measured. The X0268 *-markup diagnostics failed too (Failures).
- **Chunks.** The project runs check the ten chunk invariants and chunk sizes only. Chunk quality and translation quality are not measured (E05).
- **Variance.** Each LLM cell was answered once (Sanity, answer repeatability).

### Whole-pipeline runs (`projects.json`)

All five `projects/*/project.toml` runs (adapter `none`) exit 0 in 0.16–0.45 s. Validation reports 0 errors, all ten chunk invariants hold, the export is written, and no test or reserve line is read.

| Project | Nodes | Chunks |
|---|---|---|
| guanjing-shandao | 47 | 490 |
| lotus-kuiji-dharani-comm | 46 | 11 |
| lotus-kuiji-dharani-root | 46 | 17 |
| lotus-zhiyi-wenju | 29 | 193 |
| qixin-self | 45 | 114 |

## Interpretation

Nothing here is a headline. Each claim names the rows it rests on. VERIFIED means computed in E06 (`metrics.json` and the verification outputs above). HYPOTHESIS means our reading.

**Explicit-formula detection.**
- **Kuiji, in sample.** Tier 2 recovers the dev chapter exactly [T1723-dev tier2, 45/45; VERIFIED], unchanged since E01 read-out 1. But the parser was developed on this chapter and the gold is a draft Claude seeded, so the result shows only that the rules encode the draft's reading of 陀羅尼品. It says nothing about generalisation.
- **Zhiyi.** On validation, detection itself is weak, not only attachment.
  - Locator-only recall at t = 0 is 0.079–0.109 on validation [T1718-validation tier2, 11 of 101 lines; T1718-devval tier2 (post hoc), 8] and 5 of 12 on dev [T1718-dev tier2].
  - At t = 1 recall rises to 0.238 and 0.149 on validation and to 8 of 12 on dev (locator-only F 0.258 / 0.189 / 0.390). That fits the known offset between the formula line and the span start (EVAL-SETS item 3). The numbers are VERIFIED; the cause beyond dev is a HYPOTHESIS.
  - The key is sdp's span start, so a formula line more than one line from it is a miss even at t = 1. Recall here is a lower bound on what the parser detects.
  - Even so, the parser is not a *high-recall* announcement detector on Zhiyi validation.
- **The project runs.** The same weakness shows there as giant leaves. Where the parser misses later siblings, one leaf takes 55% of the Zhiyi project, 27% of guanjing and 23% of qixin. A second guanjing leaf (17%) follows a false-positive division [`projects-notes.json`; VERIFIED].

**Attachment and nesting.** This is where the Zhiyi scores are lost, and the top-down scorer amplifies the loss.
- **Dev, per node.** The 11 dev misses sit on 4 lines, and tier 2 put exactly one node on each [T1718-dev tier2; `runs/tier2-T1718-dev/score-dev.json`; VERIFIED].
  - 2 misses match that node's line and depth but not its parent.
  - 2 are one level off.
  - The other 7 share a line with another gold node (3 and 6 gold nodes on two lines), so the line's one prediction can pair with only one of them.

  The prediction has a single level-1 node and hangs everything under it. The gold opens a second level-1 node, so nothing below that node can match.
- **Validation, aggregate.** All 101 counted validation nodes hang under one dev level-1 gold node that no arm matches, because every prediction has a single top-level node [T1718-devval validation (post hoc), every arm S-F1 0; VERIFIED]. So the S-F1 there measures one top-level attachment, not graded parser quality. On the pre-registered T1718-validation row it is 0 by construction.
- **Off domain.** Even perfect boundaries do not fix nesting. The leaked 科判 markup finds every gold line (locator-only recall 1.000, F 0.976–0.992), yet S-F1 is 0.023–0.024 [P1573 and D8842 *-markup, LEAKED diagnostics; VERIFIED]. Tier 1 nests the 科判 tree under the file's own mulu, one level deeper on another parent path (`SUMMARY.md` § Problems), and the top-down match then loses almost every subtree.

**The resolver (hybrid; Claude Code via the interactive adapter).**
- **It cannot fix attachment as built.** Principle 1 of `resolver-prompt.md` lets it add spans and children only; it may never move an explicit node (VERIFIED in the prompt and in the merge check of `output-contract.md`). On T1718 its 41 counted inferred children are all S-F1 FP [T1718-devval validation hybrid; VERIFIED].
- **It adds detection only when it has enough context.** Locator-only rises by +0.007 on the pre-registered validation-only build and by +0.219 on the post-hoc dev + validation build. The 24 extra hits there come from subdivide (19) and adjudicate (5) [T1718-validation; T1718-devval; VERIFIED]. The gain rests on the post-hoc row, and "context" as its cause is a HYPOTHESIS. On the validation-only build the resolver was starved:
  - root-spans skipped 16 nodes as too long and left 27 unanswered;
  - subdivide added 1 division;
  - adjudicate accepted 0 decisions.
- **What the answer agents reported.** They listed 255 request problems over 84 answers. Most point upstream, where an add-only resolver cannot repair them: wrong spans (20 answers), wrong parent (23), heading artefacts (23), stated divisions the parser missed (10). Next come problems in how requests are built: missing text (17), schema gaps (21), wrong candidates (12), the one-level rule (14), the no-gap rule (12). This is a HYPOTHESIS: one reader coded the themes.

**Root-span anchoring.**
- **The lemma anchor.** It is exact wherever Kuiji quotes a lemma (12 of 12, P 1.000) and does nothing elsewhere. 29 of the 41 gold spans in the dev subtree are the drafter's manual cuts with no lemma, so 0.453 is the ceiling [T0262-dharani-root tier2; Kuiji draft, Claude-seeded; VERIFIED]. In the project runs it fails on 善導's 從A下至B已來 lemmas (12 lemma-not-found) and on most Zhiyi nodes (24 of 29 unmapped) [`projects.json`; VERIFIED].
- **With the resolver.** It scores 1.000, from a single root-spans request whose 29 spans equal the gold's 29 manual cuts at both start and end. A second, independent answer to the same request is identical [T0262-dharani-root hybrid; VERIFIED].
  - **HYPOTHESIS: this is the same model family agreeing with its own draft (R06 F19), not independent skill.** Three observations point that way:
    - 21 of the 29 cuts are judgement calls.
    - 6 of them follow a convention under which a spell or verse item starts at its 即說呪曰 / 而說偈言 line. The model-only arm, also Claude, put those 1–2 lines later; under that convention the hybrid would score about 0.854.
    - 1 cut matches the drafter where the gold itself records an alternative.
  - Only Aaron's review of the 29 cuts, or a non-Claude answerer, can separate shared judgement from cuts the text alone fixes.
  - The score keys on starts only. The end agreement (41/41, at line level) was computed separately.

**Model-only outlining (Claude Code via the interactive adapter; root text, no commentary).**
- **Kuiji dev chapter.** Model-only finds boundaries but cannot produce the commentary's own levels.
  - Locator-only is 0.658 (0.868 at t = 1), and 23 of its 35 nodes have a gold twin with the same start and end [T0262-dharani-root model-only; Kuiji draft, Claude-seeded; VERIFIED].
  - But 22 of those 23 sit one or two levels too shallow. The gold's wrapper (品文分三) and its class level (二聖 / 二天 / 十神) exist only in Kuiji's commentary.
  - S-F1 is therefore 0.026. Against a commentator's gold, S-F1 measures that commentator's extra levels, not boundary detection.
- **Against the sdp gold (not Claude-seeded).** Precision is high and recall low. Locator-only is P 0.938, R 0.149 on validation, and S-F1 at t = 1 is 0.625 on dev and 0.222 on validation, above the hybrid's 0.300 / 0.000 [T0262-xu-root; VERIFIED].
  - The hybrid detects more: its locator-only F is higher on both rows (0.478 against 0.256 on validation). Model-only places fewer nodes, but more of them also match depth and parent path at t = 1 (13 of 16 on validation, against 0 of 79).
  - The dev row has 11 gold nodes and t = 1 is a lower bound (scorer `_match`).
  - HYPOTHESIS: pretraining knowledge of the Lotus 序品 cannot be excluded.

**Self-outlining and OOD transfer.**
- **Tier 2 transfers nothing.** It adds 0 nodes on X0268, P1573 and D8842 [OOD rows; VERIFIED]: the genre gate returns no-structure on the two 註, and P1573 has 0 announcements. Tier 2 abstains rather than build a wrong tree.
- **The resolver finds real boundaries at the wrong depth.** It adds nodes beneath leaves. The counts are small (11 and 3 new start lines) and the golds are `imported-unchecked`. On P1573, 10 of its 11 new start lines are gold start lines (boundary F1 0.237, against 0.067 by chance). But it places them at levels 2–3, while the gold mostly has them deeper, so S-F1 is 0.042. On D8842 boundary F1 is 0.15, against 0.048 by chance [OOD-P1573 and OOD-D8842 hybrid; `ood-analysis.json`; VERIFIED].
- **No arm can reach X0268's gold nodes.** All 2,611 start inside the body, which is one tier-1 leaf of 300,157 characters (96.6% of the text). The resolver skips that leaf as longer than `MAX_TEXT_CHARS` [OOD-X0268; VERIFIED].
- **YBh.** S-F1 = 0 follows from the node counts and the top-down match. Separately, only 14.7% of the DILA headings of 5+ characters in T1605 occur verbatim in the treatise (45.4% for T1602), so heading-keyed matching penalises headings taken from the text [OOD-T1605; `ood-analysis.json`; VERIFIED counts].

**Pipeline robustness.**
- **Single local errors discard whole outlines.** One out-of-order sibling pair among 117 nodes discards T1602's tier-2 outline and blocks its hybrid, and the tier-1 `_unit_end` bug fails the X0268 markup cells [VERIFIED]. The validator's all-or-nothing refusal protects provenance, but it means one parser slip costs a whole text.
- **The project runs are fast and clean** [`projects.json`; VERIFIED].

**Chunking.**
- **Chunk sizes behave everywhere** [`projects.json`; VERIFIED]:
  - no chunk exceeds 6 sentences, the top of Kurt's 4–6;
  - only two exceed 180 characters, and each is a single over-long sentence;
  - each run has 1–4 tiny chunks (titles, closing formulas, the CBETA header).
- **The weakness is upstream.** Listed-only nodes make up 34–60% of the nodes and get no span, and a giant leaf gives all its chunks one topic label [VERIFIED].
- **Translation quality is not measured here.** Whether outline-guided chunks help translation is E05's question.
