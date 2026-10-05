# E01 — explicit-only recovery: how much of a kēpàn do the chapter TOC and the formula parser recover?

> **Note (2026-10-05, clean copy):** this record is kept as written, except that its closing list of proposed next runs was removed; its references to planning notes, research threads (R-codes), NEXT_STEPS and the freeze tags point to the development repository and are not part of this copy.

**Date:** 2026-09-27 (hypothesis and decision rule written before any run)  **Owner:** Aaron Bao (hypothesis drafted by Claude for Aaron to accept or replace; plan M4)  **Status:** read-out 1 done 2026-09-27 (one validation look, `looks.json`); gate decision pending (Aaron)

> **Note (2026-10-04).** Kept as written. "Validation looks so far: 1" (Result) held at read-out 1; E06 (look #2) and E07 (look #3) have since appended to `looks.json`, which has 9 entries (`../E07-capability-sweep-v1/README.md`, "Looks, leakage, cost").

## Hypothesis

Pre-registered 2026-09-27, before the parser or scorer had produced any score:

- **H1 (the parser adds structure).** On the T1718 validation split, scored against the sdp gold with key `commentary.explained` at t = 0, tier 1 + tier 2 has a higher S-F1 than tier 1 alone (the chapter-TOC floor).
- **H2 (detection outruns attachment).** On the same split, the locator-only F1 of tier 1 + tier 2 (key line only, no depth or parent) is at least twice its S-F1: most of what the parser misses is where nodes attach and at what depth, not which lines carry a division. Reason for expecting it: sdp's upper levels are editorial (R03 F23 is not read here; `data/EVAL-SETS.md` says sdp's level 1 is editorial, not Zhiyi's) and rules alone have not fixed nesting (R07 F2, PARTIAL).

Both are falsifiable by one validation read-out each.

## Why it matters / what decision it informs

The parser gate of the plan (Appendix G, [gate:parser]; thresholds are the plan's defaults, not re-tuned here):

| S-F1 (t = 0, levels ≤ 4) on T1718 validation | Decision |
|---|---|
| ≥ 0.60 and above the chapter floor | the parser is the backbone of the outliner |
| 0.40–0.60 | one bounded iteration of ≤ 2 weeks |
| < 0.40 | the parser becomes a high-recall announcement detector; attachment moves to the resolver |

If S-F1(t = 1) − S-F1(t = 0) > 5 points, fix the key or the anchor before reading the gate (R06 F24 notes). The plan's second gate set, vms/mavb, is not imported yet, so this read-out uses T1718 validation only and says so.

## Method

- **Systems.** `tier1` = `python -m chinese_workflow.outline build … --source tier1`; `hybrid-explicit` = `--source tier2` (tier 1 + tier 2 + merge; resolver adapter `none`). Pipeline commit recorded in `runs/<run>/run.json`.
- **Sets** (`data/eval-sets.json`; `data/EVAL-SETS.md` rules 1–12):
  - development: the 113 parser cases (unit level, `tests/unit/test_tier2_cases.py`); T1718 dev (sdp gold; only 卷一上 is served, 12 answer-key nodes); T1723 dev = 陀羅尼品 (Kuiji gold, `draft-unreviewed`, Claude-seeded: development numbers only, never a headline).
  - validation: T1718 validation (sdp gold, 101 answer-key nodes) — the read-out for H1, H2 and the gate. Every look is logged in `looks.json`.
  - test: **not scored here.** The T1718 test and T1723 test spans are scored once, after the freeze (plan M7), by Aaron, with `--frozen`.
- **Metrics** (`chinese_workflow.eval.score`): S-F1, F-F1 at t = 0 and t = 1; per depth; locator-only F1; child-count accuracy; the doctrinal-list rejections of the parser, reported separately.
- **Disclosures.** The parser was developed by Claude on the dev spans and on commentaries outside T1718/T1723. The Kuiji gold was seeded by Claude (R06 F19), so a Claude-built parser's agreement with it is not independent evidence. sdp headings are not scored (`data/EVAL-SETS.md`, heading check).

## Result

Pipeline commit `685a8a4` (`metrics.json`, `SUMMARY.md`; outline builds under `runs/`, gitignored). Key `commentary.explained`, t = 0 unless stated. Validation looks so far: 1.

| Set (gold) | Arm | S-F1 P / R / F | S-F1 F at t = 1 | locator-only P / R / F | gold / predicted in scope |
|---|---|---|---|---|---|
| T1718 dev (sdp; only 卷一上 served) | tier 1 | 1.000 / 0.083 / 0.154 | 0.154 | 1.000 / 0.083 / 0.154 | 12 / 1 |
| T1718 dev | tier 1 + tier 2 | 0.034 / 0.083 / 0.049 | 0.049 | 0.172 / 0.417 / 0.244 | 12 / 29 |
| T1723 dev (Kuiji, draft, Claude-seeded) | tier 1 | 1.000 / 0.022 / 0.043 | 0.043 | 1.000 / 0.022 / 0.043 | 45 / 1 |
| T1723 dev | tier 1 + tier 2 | 1.000 / 1.000 / 1.000 | 1.000 | 1.000 / 1.000 / 1.000 | 45 / 45 |
| **T1718 validation (sdp)** | tier 1 | — / 0.000 / 0.000 | 0.000 | — / 0.000 / 0.000 | 101 / 0 |
| **T1718 validation (sdp)** | tier 1 + tier 2 | 0.000 / 0.000 / 0.000 | 0.000 | 0.129 / 0.109 / 0.118 | 101 / 85 |

The parser rejected 16 announcements in the validation span as doctrinal lists (9 in T1718 dev, 1 in T1723 dev). No score is a headline: dev and validation never are, and the Kuiji gold is `draft-unreviewed`.

Against the pre-registered statements:
- **H1 is not supported.** On T1718 validation tier 1 + tier 2 does not beat the chapter floor: both are S-F1 0.000 (the floor has no chapter heading inside the span, and none of the parser's 85 nodes sits on sdp's parent chain).
- **H2 holds, but only trivially.** Locator-only F1 (0.118) is at least twice S-F1 (0), because S-F1 is zero. The detection number itself is low: 11 of sdp's 101 node lines are lines where the parser places a node.
- **Parser gate:** S-F1 < 0.40, so the pre-registered default is the pivot: the parser becomes an announcement detector and attachment moves to the resolver. The t = 1 − t = 0 gap is 0, so the key is not what fails. **The gate call is Aaron's.**

## Interpretation

What the numbers say:
- On Kuiji's style the explicit parser reproduces the dev chapter exactly (45/45). This chapter is the one the parser was developed on, and the gold was drafted by Claude, so it shows only that the rules encode the draft gold's reading of 陀羅尼品. It says nothing about generalisation.
- On Zhiyi against the sdp tree the parser recovers almost nothing, at either level.

Why (from the dev span, which may be inspected; the validation nodes were not looked at one by one):
- **sdp's tree is not Zhiyi's formula tree.** Its level 1 puts 序品 and an editorial 序分 side by side (`data/EVAL-SETS.md`: sdp's level 1 is editorial). Its nodes run 8–10 levels deep under 序品, below any division Zhiyi announces with a formula. Its explained line is where a node's text starts, not where Zhiyi announces it (EVAL-SETS item 3).
- **The parser nests Zhiyi's whole-sūtra division (分文為三) under the 序品 anchor where it reads it.** So the parser's depth is off by two or more from sdp's everywhere below it. A top-down S-F1 then cannot match anything, even where the lines agree (dev: 5 of 12 lines agree, 1 node matches).
- **Zhiyi's looser formulae** (序有通、別，從「如是」去…, 釋同聞眾為三) are rarer and less regular than Kuiji's 「有N：初…次…」, and the parser was tuned mostly on Kuiji-style texts.
