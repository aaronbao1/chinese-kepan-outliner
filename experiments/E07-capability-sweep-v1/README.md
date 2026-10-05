# E07 — capability sweep v1: the E06 sweep re-run on the outliner after the E06 follow-up

> **Note (2026-10-05, clean copy):** this record is kept as written, except that its closing lists of proposed next runs and of open decisions for the author were removed; its references to planning notes, research threads (R-codes), NEXT_STEPS and the freeze tags point to the development repository and are not part of this copy.

**Date:** 2026-10-03 (hypotheses and decision rules written before any E07 build or score)  **Owner:** Aaron Bao (hypotheses drafted by Claude for Aaron to accept or replace)  **Status:** done 2026-10-03. Every cell built and scored; validation look #3 and one OOD look logged; verification pass, leakage audit and completeness critic run. Nothing committed (Aaron reviews first).

> **Note (2026-10-04).** Kept as written. E07 was committed in `b3315b6` and merged into `main` in `433e8e9` (2026-10-03), so "Nothing committed" no longer holds.

Asked by Aaron on 2026-10-03 ("run full eval tests on the new pipeline and changes"), with scope chosen by him: every set except test (dev, validation look #3, the five OOD texts), the LLM arms included, recorded here.

Naming: the E06 review (§2 C7, §3 Q8) proposed "E07" for structure-agnostic OOD diagnostics. That experiment is not this one; if it is pre-registered later it takes the next free number. This sweep reads the OOD texts with the scorer as it stands at the freeze, including the attachment-tolerant triple of review A2. That triple is not C7's boundary-F1 and heading-similarity design.

## Hypothesis

Pre-registered 2026-10-03, before any E07 build or score. Frozen outliner: lightweight local tag `outliner-v1-frozen-2026-10-03` = `014c125` (main after the E06 follow-up merge `e02b42e` and later documentation commits; `pipeline/` clean). "S-F1" etc. as in `chinese_workflow.eval.score`; t = 0 and key `commentary.explained` unless stated. E06 numbers are from `../E06-capability-sweep/metrics.json` (frozen v0, `8498eb3`).

Regression checks: the follow-up was claimed neutral on these.
- **H1 (Kuiji explicit arms unchanged).** T1723-dev tier 2 S-F1 = 1.000 (45/45). T0262-dharani-root tier 2 S-F1 = 0.453 (P 1.000, 12 TP of 41 counted gold).
- **H2 (every cell builds).** Every non-diagnostic cell of the matrix builds; E06 had two cells fail on pipeline bugs, one of them hybrid-OOD-T1602 on one sibling pair. A `degraded` build counts as built, and its repairs are reported.

The Zhiyi side:
- **H3 (shape, not score).** On T1718-dev, tier 2 predicts more counted nodes than E06's 29, and its S-F1 stays ≤ 0.10. The follow-up added Zhiyi's 「X」者 lemma-gloss units (review B6) but no top-level promotion (C1 is undecided). The review's what-ifs say lemma units alone add FP and no TP against the 12-node sdp dev key.
- **H4 (the key decides detection).** On T1718-dev, tier 2's locator-only F1 under `--key commentary.span_start` is at least 0.10 above its locator-only F1 under `commentary.explained`. The review measured the key choice alone moving dev locator-only between 3/12 and 11/12.
- **H5 (the parser-gate row does not cross the gate).** On every T1718 validation row (the pre-registered validation-only build and the dev+validation build), every arm's S-F1 t = 0 stays < 0.40. This is validation look #3.
- **H6 (the 品 pin reaches validation-only builds).** On the pre-registered T1718-validation build, tier 1 yields at least one node; E06 yielded 0, because no 品 pin was carried. On hybrid-T1718-validation and hybrid-T1718-devval, the resolver's root-spans task reports 0 nodes skipped for a degenerate admissible range (E06 skipped 16 on the validation-only build).

The resolver and model arms:
- **H7 (request size is bounded).** No request `.md` of any E07 cell exceeds 120,000 characters. E06's largest was 177,081, and 7 files exceeded 120,000. `MAX_REQUEST_CHARS` is now 100,000 rendered characters per user message.
- **H8 (Kuiji root spans stay near-perfect under the new prompt).** hybrid-T0262-dharani-root S-F1 t = 0 ≥ 0.95. The review expected 40/41 after the re-recorded cassette moved 2 of 29 cuts. The same-model confound of E06 stands: the Kuiji gold was seeded by Claude.
- **H9 (model-only stays below hybrid on 序品).** On T0262-xu-root dev at t = 1, model-only's S-F1 under the both-counted TP rule (`s_f1_both_counted`) does not exceed hybrid's. Both TP rules are reported side by side, per review Q4.
- **H10 (the attachment-tolerant triple reads a one-slip tree as one slip).** On T0262-xu-root dev at t = 1, tier 2's ancestor-consistent F1 is ≥ 0.80, with ≤ 2 re-anchors. The review's prototype gave 0.842 with 1 anchor.

Out of domain (one logged look):
- **H11 (CBETA 科判 transfer stays low).** On X0268, P1573 and D8842, read without their 科判 markup, tier 2 S-F1 < 0.30 and tier 1 S-F1 ≤ 0.05. This replicates E06 H4 on the new pipeline.
- **H12 (YBh structure mode stays low).** On T1605 and T1602, every arm's structure-mode S-F1 is < 0.10. E06's H5 was left undetermined because hybrid-T1602 failed.

Kurt's deliverable, from the project runs (adapter `none`):
- **H13 (fewer giant shared labels).** In the guanjing project, the share of chunks whose leaf outline node carries more than 31 chunks (i.e. a label shared with more than 30 other chunks) is < 30 %; the E06 review measured 68 %. In the Zhiyi project the same share is below its E06 value; the review measured 71 %. Both E06 values are recomputed by this harness from E06's saved runs, by the same rule as E07's.

Each is falsifiable by one read-out. None is a headline: dev and validation never are, the Kuiji gold is `draft-unreviewed` and Claude-seeded, the sdp and OOD golds are `imported-unchecked`, and the follow-up was developed on these dev spans.

### Decision rules (written before the run)

- H1 or H2 false: a regression in the follow-up; it is listed with the cell and the cause before anything else is read.
- H5 false (any validation row ≥ 0.40): the parser-gate reading changes and Aaron's gate call must be re-read; no default action.
- H5 true: the gate reading is the same as E06's. The review's recommendation stands: no pivot before Q1/Q2.
- H3/H4: if H4 holds and H3 holds, the key and top-level conventions (review Q1, Q2) remain what limits the Zhiyi score, not detection.
- H7 false: request sizing is still a cost defect; no API budget is priced from this run.
- H11/H12 are a logged OOD look. A failure is read only in aggregate, and no OOD-specific tuning follows from it before an OOD diagnostics experiment is pre-registered (review Q8).

## Why it matters / what decision it informs

- **Did the E06 follow-up regress anything,** and what does it change on the rows E06 measured? The follow-up implemented tiers A and B of the review in 12 tasks: scorer diagnostics, the span-start key, the 品 pin carried into span builds, repair before and after the resolver, the 善導 idioms, the Zhiyi lemma device, anchor rules, the genre-gate scope, and the self-outlining take-up override.
- **The parser-gate call and the API budget** (both Aaron's; NEXT_STEPS §−1, REVIEW-2026-10-02 §2 "pending calls"): validation look #3 and the resolver's request sizes under the new sizing.
- **The spec for Kurt** (`014c125`): which capability numbers can be quoted on the v1 outliner.

## Method

- **Freeze.** Tag `outliner-v1-frozen-2026-10-03` on `014c125`. Every OOD score row runs with `--frozen outliner-v1-frozen-2026-10-03`, and only while `pipeline/` is byte-identical to the tag at build and at score time (E06 rule). E07's harness lives here and does not modify `pipeline/`.
- **Harness.** `run_e07.py` is E06's `run_e06.py` with the tag, paths and look notes changed, plus:
  - the follow-up scorer's diagnostic fields in every row: `fn_split`, the TP-rule pair (`s_f1_both_counted`, `tp_uncounted_pred`, `tp_le_counted_pred`), `key_lines`, `fp_by_kind`, and the triple `ancestor_consistent` / `reanchor` / `depth_offset_hist`;
  - a second key row `commentary.span_start` beside every `commentary.explained` row on the T1718 and T1723 commentary sets;
  - the build's `degraded` repairs in `cell.json`;
  - a comparison column against E06's `metrics.json` in `SUMMARY.md`.

  `run_projects.py` and `sanity_e07.py` are E06's with the same changes. `run_projects.py` adds the shared-label share of H13.
- **Sets and arms.** E06's matrix unchanged (`../E06-capability-sweep/README.md` "Method" table, including the post-hoc T1718-devval cell, the OOD inputs with their 科判 markup removed, and the `*-markup` LEAKED diagnostics). Test spans of T1718 and T1723 are **not read and not scored**. Reserve is never scored.
- **Validation look #3.** Rows: T1718-validation, T1718-devval (validation row) and T0262-xu-root (validation row), all arms. Logged in E01's `looks.json` (appended, never edited) and in `looks-e07.json`. The scorer runs once over all arms of a set (no partial look).
- **OOD look.** The five OOD sets, all arms, scored once and logged in `looks-e07.json`, kind `ood-look`. They are read in aggregate only.
- **The hybrid and model-only arms.** Same as E06: the `interactive` adapter (model id `claude-code-session`). Its request files are answered by Claude Opus 5.5 subagents in one workflow with E06's prompt template, each reading only its own request file. A leakage audit (`audit_leakage.py`, pointed at this run's transcripts) greps every answer agent's tool uses afterwards. Disclosed with every hybrid and model-only number: this is *Claude Code via the interactive adapter*, not the `claude` API config, and the Kuiji gold was seeded by the same model family (R06 F19). `MODEL_ONLY_ROUNDS` stays 3, as in E06.
- **Sanity.** Gold against itself on every row (expect F = 1.000), the oracle arm on T1723 dev, the perturbation checks of `sanity_e06.py`, and the full suite: `pytest ../tests` at the tag gave 1,374 passed, 11 skipped, 1 xfailed (2026-10-03, before any E07 build).
- **Whole-pipeline runs.** `python -m chinese_workflow.runner run` on every `projects/*/project.toml`, adapter `none`.
- **Metrics.** As E06 (S-F1 and F-F1 at t = 0 and t = 1, without `anchor_inherited`, per depth, locator-only, child-count accuracy, structure mode for YBh), plus the follow-up's diagnostics above. Validation and OOD are reported in aggregate only. Per-node diagnostics are dev-only.

### Method addenda (after pre-registration, 2026-10-03)

Written after the run. The Hypothesis section and the Method above are unchanged. The README as pre-registered has sha256 `c26f1c9b63d72b674c69bac7128febb9…`, computed before the first build. The directory is untracked, so the only other evidence of order is mtime: README 20:42, first `cell.json` 20:45 (PDT).

1. **Harness edits during the run.**
   - At 21:12, after the first build and before any score was computed, `pending` gained `--compact` and `--set`, and model-only rounds now keep the pipeline's rejection message. No build or scoring logic changed. The first scores, dev rows only, were read at 21:13.
   - After the scoring run, only text and SUMMARY sections changed: stale E06 cross-references in the design choices, the findings list, request-size / project / leakage sections, and the gold-vs-itself attachment triple. SUMMARY was re-rendered from the score cache. E01's `looks.json` is byte-identical before and after, and no look event was added.
2. **The answer loop was not one workflow.**
   - A first workflow (`wf_baee7e39`) was stopped after its driver agent, asked to echo about 170 JSON request records, was killed after 17 minutes. It answered nothing.
   - The requests were then answered by three parallel workflows, each with E06's answer prompt unchanged except for paths:
     - group A, the six dev/validation sets (`wf_b47ae20e`, 5 rounds, 26 answers);
     - B1, X0268 (`wf_1c3b66c7`, 7 rounds, 310 answers);
     - B2, the other four OOD sets (`wf_2ee77c56`, 12 rounds, 182 answers).
   - Per round, a driver ran `build` and `pending --compact` and the script parsed the listing.
   - Identical requests in two cells were answered once and copied, per E06's design choice 14. E06 had answered 4 hashes twice.
   - In total there were 518 answer agents and 518 distinct answers in 529 response files. Every answer validated against its schema on the first attempt, so there were 0 re-answers.
3. **E06's in-process matcher swap was removed from `sanity_e07.py`.** The v1 scorer already aligns siblings order-preservingly by DP, and the region-rule check reads `_region(line, twin=True)`.
4. **Premise corrections** (the Hypothesis text stays as written):
   - H2: E06 had 4 failed cells from 2 bugs (tier2- and hybrid-OOD-T1602 on one sibling pair, and the two X0268 `*-markup` diagnostics). Both fixes predate this freeze, so H2 had little power to fail.
   - H6: E06's 16 skips were "admissible range longer than 40,000 characters". "Degenerate" is the review's word, not a skip kind.
   - H10: the 0.80 bar was calibrated on E06's outline, with 8 counted dev predictions.
   - H13: the "68 %" quoted for E06 is the review's rule (a label on more than 30 chunks). Under H13's own rule (more than 31), E06 guanjing is 61.2 %.
5. **The freeze tag is no longer local.** The Hypothesis section calls `outliner-v1-frozen-2026-10-03` a lightweight local tag. After the run it was pushed to `origin` (2026-10-03), together with E06's `outliner-v0-frozen-2026-10-01`. It still points at `014c125`.

## Result

Frozen tag `outliner-v1-frozen-2026-10-03` = `014c125`. `pipeline/` was byte-identical to the tag for every build and score, and the rescorers re-checked this. Numbers come from `metrics.json` and `projects.json`; `SUMMARY.md` renders them with per-depth rows, diagnostics tables and E06 columns. t = 0 and key `commentary.explained` unless stated. No row is a headline.

**Instrument.**
- `pytest ../tests` at the tag: 1,374 passed, 11 skipped (sdp's unserved 卷-halves), 1 xfailed (guanjing plan gate).
- `sanity_e07.py`: every gold scores 1.000 against itself on every row; the attachment triple reads AC-F1 1.000 with 0 anchors and offset mode 0 wherever the forest is under the cap. All 18 perturbation checks pass, including E06's two failing scorer repros (the +1 shift and a merged_range split whose second part has its own heading), so those scorer fixes hold.
- Three independent rescorers re-ran the scorer CLI on all 58 result rows, the 6 leaked rows and E06's 17 rescored OOD rows: **0 mismatches**.
- E06's saved outlines rescored by the v1 scorer reproduce every E06 headline value (0 differences). So the E06 columns in SUMMARY are clean comparisons of outliner against outliner.

### The pre-registered hypotheses

Each hypothesis was read by a panel of three independent readers: a literal reader, a skeptic and an E06-comparison auditor. All 13 panels were unanimous.

| | Verdict | Numbers |
|---|---|---|
| H1 Kuiji explicit arms unchanged | **supported** | T1723-dev tier 2 S-F1 1.000 (45/45); T0262-dharani-root tier 2 0.453 (12 TP of 41, P 1.000). Both outlines are identical to E06's. |
| H2 every cell builds | **supported** | 41 of 41 cells built (E06: 4 failed). 0 repairs inside the matrix; model-only has no repair path. The guanjing *project* build is degraded: 8 local validator errors, 17 repairs. |
| H3 Zhiyi shape, not score | **supported** | T1718-dev tier 2: 49 counted predictions (E06 29; 58 nodes, 9 out of the served scope), S-F1 0.033 (E06 0.049). Every added node is a 「X」者 lemma-gloss unit: +20 counted FP, TP unchanged at 1. |
| H4 the key decides detection | **supported, at the smallest possible margin** | Locator-only 0.295 under `span_start` vs 0.164 under `explained`: +0.131, i.e. exactly the 4 TP the bar needs. At t = 1 the gain is +0.033. Without inherited span_starts it is +0.018. The whole gain is first-child chains stacking on one gold line that carries 6 stacked gold nodes. E06's outline under the same key goes the other way (0.244 → 0.146). |
| H5 the gate row does not cross 0.40 | **supported trivially** | S-F1 t = 0 is 0.000 on every T1718 validation row, arm and key. The validation-only row is 0 by construction (reachability 0 of 101). On devval all 101 misses cascade from one dev top-level miss (frontier 0): every build has one top-level node, and no promotion (C1) exists. |
| H6 the 品 pin reaches validation-only builds | **supported trivially** | tier1-T1718-validation yields 1 node, the carried pin: editorial and uncounted, so reachability is still 0 of 101. hybrid-T1718-validation skipped 0 root-spans nodes (E06: 16, all too-long ranges). devval skipped 5, all of kind `out-of-span` (the new classification), none for range. One-line admissible ranges rose: 67 of 112 asked on validation (E06: 19 of 35). |
| H7 request size bounded | **not supported** | Largest request `.md` 122,885 characters; 3 files (2 distinct requests, all root-spans) over 120,000. The cap holds on the user message (max 99,834 ≤ 100,000). The rendered file adds a 20,294-character system prompt (14,090 at v0) and the schema. |
| H8 Kuiji root spans near-perfect | **supported** | hybrid-T0262-dharani-root S-F1 1.000 (41/41). A fresh answer gives the same 29 cuts as E06 (29/29). Four separate Claude answers to this request now agree. Single sample, same model family as the gold's seeder. |
| H9 model-only below hybrid on 序品 | **not supported** | T0262-xu-root dev, t = 1, both-counted: model-only 0.609 vs hybrid 0.235 (gold-counted rule: 0.667 vs 0.333). The premise was already false in E06 under the v1 scorer (0.308 vs 0.211). |
| H10 the triple reads a one-slip tree | **not supported** | tier 2 xu-root dev, t = 1: AC-F1 0.533, 1 anchor, P 1.000. The triple does read the tree as one slip, but the build places only 4 counted dev predictions (E06: 8), which caps AC-F1 at 0.533. The v1 scorer gives E06's outline 0.842 with 1 anchor, as the review's prototype did. |
| H11 CBETA 科判 transfer low | **supported trivially** | tier 2 S-F1: X0268 0.000, P1573 0.016, D8842 0.048. tier 1 is the same: these outlines are node-for-node E06's. Even the leaked `*-markup` copy scores only 0.023 / 0.024 on P1573 / D8842, so the bar cannot discriminate there. |
| H12 YBh structure mode low | **supported trivially** | Structure-mode S-F1 0.000 for every arm on T1605 and T1602. hybrid-T1602 now builds (523 nodes; tier 2 180). Tier-2 rules were developed on T1602 (review B4), so T1602 is no longer a clean OOD text for tier 2 / hybrid. |
| H13 fewer giant shared labels | **supported (granularity, in-sample)** | Share of chunks whose label is on more than 31 chunks: guanjing 61.2 % → 23.4 %, Zhiyi 71.0 % → 0.0 %. Under the review's rule (more than 30): guanjing 67.6 % → 23.4 %. This measures how finely labels divide, not whether they are right. Zhiyi's drop is the same lemma units that add only FP in H3. guanjing's largest label still covers 97 chunks. |

### Rows not covered by a hypothesis

| Set / row | Arm | S-F1 t=0 (E06) | locator-only (E06) | note |
|---|---|---|---|---|
| T0262-xu-root dev | tier2 | 0.000 (0.000) | 0.400 (0.316) | 4 counted predictions (E06 8); t = 1 both-counted 0.267 |
| T0262-xu-root validation (aggregate) | tier2 | 0.000 (0.000) | **0.015 (0.197)** | the regression below |
| T0262-xu-root validation (aggregate) | hybrid | 0.000 (0.000) | 0.416 (0.478) | |
| T0262-xu-root validation (aggregate) | model-only | 0.000 (0.000) | 0.508 (0.256) | 210 counted predictions (E06 16); P 0.376, R 0.782 at t = 0 |
| T1718-devval validation (aggregate) | tier2 / hybrid | 0.000 (0.000) | 0.157 / 0.287 (0.101 / 0.320) | span_start: 0.172 / 0.338 |
| T0262-dharani-root dev | model-only | 0.083 (0.026) | 0.688 (0.658) | 55 predictions (E06 35); max depth 8 |
| T1723-dev dev-span | tier2 / hybrid / oracle | 0.400 | 0.733 | the oracle itself scores 0.400: convention clash (below) |
| OOD-X0268 whole | hybrid | 0.000 (0.000) | 0.174 (0.000) | 338 nodes, 273 at level 2 |
| OOD-P1573 / D8842 whole | hybrid | 0.038 / 0.073 (0.042 / 0.043) | 0.367 / 0.255 (0.194 / 0.130) | |

### What the verification pass found

These are mechanism reads, dev-only per node, validation and OOD in aggregate. VERIFIED means reproduced from files or commands; the evidence is in the verification workflow's outputs, summarised in `metrics.json` `findings`.

1. **A regression in Zhiyi root anchoring, not pre-registered (VERIFIED).**
   - **Cause.** The follow-up's 「X」者 lemma-gloss device (`outline/tier2/parser.py` `_resolve_lemma_zhe`, partial-name rule `GLOSS_PARTIAL = 0.5`, Task 10, `2a356cc`) attaches two glosses to one- and two-character listed items of 序品's opening. The anchor then places those items' lemmas (the opening's short lemmas) on later sūtra lines instead of `T09n0262_p0001c19`.
   - **Effect.** tier2 xu-root dev counted predictions drop from 8 to 4, and validation locator-only from 0.197 to 0.015 (aggregate). The hybrid's root-spans requests inherit the mis-anchored siblings as admissible ranges, and the answerers declined most nodes rather than give knowingly wrong spans: 84 of 112 and 138 of 204 not answered.
   - **Counterfactual (dev only).** Setting `GLOSS_PARTIAL = 0.95` restores E06's dev row: 8 counted, locator-only 0.316 at t = 0 and 0.900 at t = 1.
   - **What is not the cause.** `anchor.py` swapped between the tags leaves root starts unchanged. Separately, the method-list rule (`c40d9b2`) drops 10 verse-section starts.
   - **Why nothing caught it.** Both misfiring glosses lie in T1718's *validation* commentary. Task 10's acceptance was dev-only outline shape, and Task 7's regression check was the Kuiji build. **A fix motivated by these two glosses is validation-informed**: it must be justified on dev or out-of-split text, and the next validation look must say so. The Kuiji root (H1) is untouched: lemma_zhe never fires on T1723 dev.
2. **`commentary.span_start` is valid only for golds keyed by sdp's chained rule (VERIFIED).**
   - The Kuiji gold keys nodes at take-up lines. Under span_start, 12 of the 14 dev first children inherit an earlier line, so even the oracle scores 0.400 (locator-only 0.733).
   - The T1723 `dev-span` rows therefore measure the convention clash, not the outliner.
   - On T1718-dev (sdp), the span_start gain is entirely inherited positions (H4).
3. **The resolver duplicates explicit structure (VERIFIED).** On hybrid-T1718-dev, the one accepted subdivide adds 7 inferred nodes under `…6_5`. They are a twin of an explicit subtree tier 2 already built under `…9_5`; 6 of 7 headings are identical. No key counts them, because they have no commentary locator, so hybrid = tier 2 on every T1718 row.
4. **Root-spans cannot repair upstream anchoring on Zhiyi (VERIFIED).** On hybrid-T1718-dev, 0 of 25 nodes were accepted: 10 had the one-line range `p0005b23` and 15 had `p0003c11–p0005b23`. The 1.000 on the Kuiji dharani root comes entirely from 29 filled manual cuts.
5. **model-only grew because the subdivide contract changed (VERIFIED).**
   - **Contract change.** Answers may now nest to depth 3 (schema `resolver-subdivide/2`) and declare paratext gaps.
   - **Growth.** The xu-root tree went 3/10/21 nodes after rounds 1–3 in E06 and 20/104/224 in E07. It had not converged: round 3 still divided 40 of 72 leaves.
   - **Dev credit.** 4 of its 7 counted TPs at t = 1 pair nodes that cover different text, because the gold's chain shares one start line.
   - **Dharani-root.** 0.026 → 0.083 comes from the paratext gap shifting the first child onto the gold's line.
6. **X0268 windowing flattens the outline (VERIFIED).** Its 300k-character leaf is answered in 76 depth-1-only windows. The result: 273 of 338 nodes at level 2, one parent with 259 children. Every windowed answer reported a window-grain problem.
7. **Gloss re-keying wastes interactive answers (VERIFIED).**
   - **Mechanism.** A gloss request carries its ancestors' English glosses, so each answered ancestor changes the hash of every descendant window.
   - **Waste.** Of 559 request files, the final builds consumed 300. 229 were answered and unused, and 30 never answered; all 259 are gloss requests. 351 of 518 answer agents were gloss, which no score reads.
   - **API comparison.** A sequential API run would not pay this (HYPOTHESIS, from the code path). It would be 300 calls: 118 subdivide, 42 adjudicate, 15 root-spans and 125 gloss, 263 of them OOD. Input would be about 8.35 M characters of system and user messages.
8. **guanjing is better, but not "largest leaf 26 % → 3 %" (VERIFIED).**
   - Largest span of any kind: 27.0 % → 20.7 % of the target. It is now an 11,188-character preamble carried by 97 chunks; 3 of its node's 4 children are listed-only and never taken up (why: HYPOTHESIS).
   - Largest label: 25.9 % → 17.5 % of chunks.
   - The 3 % figure is the largest childless node, which is not what a chunk's label follows.
   - lemma-not-found: 89 of 208 (42.8 %; plan gate ≤ 25 %; not met, as design §5.5 records).
   - Across all five projects, every chunk invariant holds.
   - Share of chunks whose label covers more than 2,000 characters: guanjing 86.9 % → 31.0 %, Zhiyi 71.0 % → 31.5 %, qixin 54.4 % → 13.1 %.
9. **What the answerers reported** (1,358 problems from 518 answers, coded by two independent coders with their own codebooks; agreement not quantified because the codebooks differ):
   - Both put truncated or misaligned gloss context first: 285 / 339.
   - Then upstream tree or span defects: 89 + 51 / 208 + 32.
   - Then X0268's window grain: 209 / 135 + 69.
   - In-domain cells, 114 problems: about half are upstream locator or structure defects (anchoring, mis-parenting).
   - Adjudicate's attach/ignore decision set cannot express "set the explained line of an existing node" or "insert a middle child".

### Looks, leakage, cost

- **Validation look #3.** T1718-validation, T1718-devval and T0262-xu-root, all arms, one pass each (`looks-e07.json` 16 look events). E01's `looks.json` +3 entries.
- **OOD look.** Five sets, all arms, one pass (15 `ood-look` events).
- **E06's outlines rescored by the v1 scorer.** 29 `recompute-e06` events, 16 of them on validation rows. They are not in E01's log. The headline values are unchanged, but their new diagnostic fields (both-counted, the triple, span rows) had not been seen before.
- **Test spans.** Neither read nor scored. Every build's guard log shows dev, validation or unsplit reads only.
- **Leakage audit** (`leakage-audit.json`), over 518 answer agents and 2,510 tool uses:
  - 0 agents with test or reserve text, 0 gold markers in request files, 0 sdp headings in any response; E07 outputs pass the sdp eval-only guard.
  - **One access is classed FORBIDDEN, and it is a false positive:** agent `a43952d1` ran `wc` on a mistyped, non-existent copy of its own request path, then read its own request.
  - **164 SUSPECT accesses**, all benign: 158 are explained by the audit (own responses directory, own scratch file), and the 6 it left unexplained are the same kinds, checked by hand. Six agents wrote helper scripts into the session scratchpad, all built from their own request. One generic file name was reused by a later agent, which regenerated it from its own request before use.
  - **Model-only exposure.** The model-only xu-root request shows the whole 序品 pin, including 3 test-region and 1 reserve-region root lines of T09n0262. These are uncounted, but visible.
- **Cost** (Claude Code via the interactive adapter, not the API config):
  - 548 Opus 5.5 subagents in the answer workflows: 518 answerers, 26 drivers and a few unlabelled.
  - 3.03 M output tokens and 146.7 M cache-read tokens; about 44.6 M subagent tokens by workflow accounting.
  - hybrid-OOD-X0268 alone took 310 agents and 43 % of output tokens, for S-F1 0.000.
  - Answered request text: 10.47 M characters in 529 files, 4.0× E06's characters and 6.3× its files. In-domain alone it is 2.44 M (E06 2.00 M).
  - Verification: 51 agents, about 7.5 M subagent tokens.

## Interpretation

What we now believe:
- **The follow-up did what it was built to do on its own dev material, and it regressed one thing it was not checked on.**
  - Kuiji is unchanged (H1, H8).
  - Every cell builds (H2).
  - Zhiyi's dev outline has the shape the review asked for: lemma units in 卷一下, smaller labels (H3, H13).
  - Request sizing and the pin carry work as designed (H6; H7 fails only on its file-level definition).
  - The lemma-gloss device's partial-name rule broke Zhiyi root anchoring on 序品 (finding 1). That shows only in a set the follow-up never measured: the root-text sets, via validation-span glosses.
- **The parser-gate reading is unchanged, and look #3 added no evidence for it.** Every validation S-F1 zero is forced: by reachability on the pre-registered row, and on devval by one top-level miss that no build can fix without C1. The lenient columns moved both ways: tier 2 devval locator-only 0.101 → 0.157, hybrid 0.320 → 0.287. They are not a gate reading.
- **Scores against the sdp keys measure conventions more than outlines.**
  - The key moves locator-only only through chain stacking (H4, finding 2).
  - The top level decides S-F1 (H5).
  - Precision against the 12-node dev key penalises correct lemma units (H3).
  - Review Q1 (key) and Q2 (top level) remain what blocks reading the Zhiyi side at all.
- **The LLM arms changed for contract reasons, not capability reasons.**
  - model-only's rise (H9) comes from depth-3 subdivide and a new prompt, with N = 1.
  - hybrid on Zhiyi is tier 2 plus a duplicated subtree (finding 3).
  - Root-spans on Zhiyi cannot work while the anchor mis-places siblings (finding 4).
  - No hybrid or model-only delta here can be attributed to the follow-up without repeat samples (review Q11).
- **OOD is still unreadable with S-F1** (H11, H12 trivially). X0268's hybrid finds lines (locator-only 0.174) but in a flat tree (finding 6). T1602 now builds end to end, but it is in-sample for tier 2.

What we don't know:
- whether the lemma_zhe fix restores xu-root without losing 卷一下's units (dev-testable);
- why guanjing's 97-chunk preamble keeps three listed-only children;
- answer-to-answer variance of any LLM arm;
- what a sequential API run actually costs (the 300-call figure is from the code path).
