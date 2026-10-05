# What the v0 kēpàn outliner can and cannot do (E06)

> **Note (2026-10-05, clean copy):** this record is kept as written, except that its "Next steps" list was removed; its references to planning notes, research threads (R-codes), NEXT_STEPS and the freeze tags point to the development repository and are not part of this copy.

**Date:** 2026-10-01  **For:** Aaron (and, if useful, Kurt)  **Source:** `README.md` (hypotheses, method, full result tables), `SUMMARY.md` / `metrics.json` (all scores)

> **Note (2026-10-04).** Kept as written. E06 is committed (`813dd17`); the pipeline bugs and scorer defects listed below were fixed in `2202123`, `0e6a9a8` and the follow-up `e02b42e`, and the fixed outliner was re-measured in `../E07-capability-sweep-v1/README.md`.

E06 ran the frozen outliner (tag `outliner-v0-frozen-2026-10-01` = `8498eb3`; `pipeline/` byte-identical to it) on the dev and validation splits of the sdp and Kuiji golds, on five out-of-domain (OOD) texts, and as five whole-pipeline project runs. It tested four configurations ("arms"):
- **tier 1**: the CBETA chapter table of contents only;
- **tier 2**: tier 1 plus the formula parser;
- **hybrid**: tier 2 plus the model resolver and gloss;
- **model-only**: the model outlining the root text with no commentary.

The test spans of T1718 and T1723 were not read and not scored (Aaron, 2026-10-01).

## Bottom line

- **Kuiji, the style the parser was built for:** the parser reproduces its development chapter exactly (45/45). The chapter is in-sample and the gold is a draft Claude seeded, so this says nothing yet about generalisation.
- **Zhiyi:** the parser recovers almost no structure. Structural F1 is 0 on every validation row. On the pre-registered row that 0 holds by construction, so it can't grade the parser. Line-level detection finds about one gold division in ten at t = 0, and one in five at t = 1.
- **The resolver (answered by Claude):** it adds boundaries, but as frozen it can only add, so it can't correct where the parser attached nodes. Its one structural gain is on Kuiji's root-text spans (dev): it matched the gold drafter's 29 hand cuts exactly. HYPOTHESIS: that reflects the same model family on both sides, not skill.
- **The seven pre-registered hypotheses:** none is supported on its merits. Two are supported only trivially, four are not supported, and one is undetermined.

## How to read the numbers

- **S-F1** matches a node on its key line, depth and parent path. **Locator-only F** matches the line alone, so it measures detection without attachment. t = 0 means exact lines; t = 1 allows one line of slack and is a lower bound (scorer defect, Caveats).
- **No number here is a headline.** Dev, validation and OOD rows never are.
- **The golds:**
  - the Kuiji gold is `draft-unreviewed`, seeded by claude-opus-5-5;
  - the sdp golds (Zhiyi) are eval-only and `imported-unchecked`, and their upper levels are editorial;
  - the OOD golds are `imported-unchecked`.
- **hybrid and model-only are Claude Code** (Claude Opus 5.5 subagents) answering the interactive adapter's request files. They are not the paid `claude` API configuration, and each request was answered once (no variance estimate).
- **Where the numbers come from.** Scores come from `metrics.json`; an independent re-score of 16 rows matched it exactly. Mechanism counts come from a single verification pass. Readings that go beyond the numbers are tagged HYPOTHESIS.

## Capability matrix

| Capability | Evidence (set, arm) | Score | Verdict | Confidence |
|---|---|---|---|---|
| Explicit-formula detection, Kuiji style | T1723 dev, tier 2 | S-F1 1.000 (45/45) | Works on its development chapter; generalisation untested | Low: in-sample, draft Claude-seeded gold |
| Explicit-formula detection, Zhiyi style | T1718 dev and validation, tier 2 | Locator-only F 0.244 (dev); 0.101–0.118 (validation), recall 0.08–0.11; at t = 1, F 0.189–0.258, recall 0.15–0.24 | Weak: finds about one division line in ten | Medium. Recall is a lower bound: sdp keys the span start, not Zhiyi's formula line, and the gold's upper levels are editorial |
| Attachment and nesting | All T1718 rows; leaked 科判 markup on OOD (diagnostic) | S-F1 0.000 on every T1718 validation row (by construction on the pre-registered row). Markup diagnostic: locator-only recall 1.000, F 0.976–0.992, yet S-F1 0.023–0.024 | Fails. This is the main loss: one wrong top-level attachment zeroes everything below it | High that it fails. Low on how much, because the top-down scorer amplifies it |
| Root-span anchoring from Kuiji's lemmas | T0262 陀羅尼品 (root key), tier 2, dev | P 1.000, R 0.293, F 0.453 | Exact where a lemma exists; no span otherwise. 29 of the 41 gold spans are the drafter's hand cuts | Medium: draft gold, 12 lemma/chapter nodes |
| Root spans with the resolver | Same set, hybrid, dev | S-F1 1.000; the 29 hand cuts match on starts and on ends; a second, independent answer agrees 29/29 | Matches the drafter. HYPOTHESIS: same-model agreement, not skill | Low as evidence of capability |
| Resolver: added detection on Zhiyi | T1718 validation (pre-registered) and T1718 dev+validation build (post hoc), hybrid vs tier 2 | Locator-only +0.007 (0.125 vs 0.118) / +0.219 (0.320 vs 0.101); S-F1 +0 | Pre-registered row: no gain. Post-hoc row: 24 extra line hits from inferred children. HYPOTHESIS: the gain needs the dev context | Medium-low |
| Model-only outlining of root text | T0262 陀羅尼品 (Kuiji gold, dev); T0262 序品 (sdp gold, dev + validation) | 陀羅尼品: locator-only 0.658 (0.868 at t = 1), S-F1 0.026. 序品 validation: locator P 0.938, R 0.149. S-F1 at t = 1: 0.625 (dev, n = 11), 0.222 (validation) | Finds boundaries precisely but too few, and one or two levels too shallow. It can't produce levels that exist only in a commentary. Hybrid's locator-only is higher on both sdp rows (0.316 vs 0.308 dev; 0.478 vs 0.256 validation) | Medium-low. HYPOTHESIS: some of this is pretraining knowledge of the Lotus Sūtra |
| Self-outlining and OOD transfer | X0268, P1573, D8842, T1605 (T1602: tier 1 only) | Tier 2 adds 0 nodes over tier 1. Hybrid S-F1 ≤ 0.043. Boundary F1 0.237 (P1573) / 0.15 (D8842), against 0.067 / 0.048 by chance | The rules don't transfer. The resolver finds some real boundaries, at the wrong depth | Medium-low: unchecked golds, small n (11 and 3 new start lines) |
| Robustness | Failed cells; resolver requests | 2 pipeline bugs each discard a whole outline (T1602 tier 2/hybrid; X0268 markup diagnostic). Requests up to 177,081 characters. Root-spans left 119 candidates unanswered | Brittle at the edges | High |
| Chunking | 5 project runs (adapter none) | 10/10 chunk invariants hold; no chunk over 6 sentences; 2 chunks over 180 characters (single over-long sentences) | Works mechanically. Quality inherits the outline's gaps: listed-only nodes are 34–60%, and leaves are giant where siblings were missed | Medium: chunk quality and translation quality not measured (E05) |

**Pre-registered hypotheses** (three judges, each through a different lens; majority verdict; the post-hoc T1718 dev+validation rows were not used for any verdict):

| H | Verdict (votes) |
|---|---|
| H1, no regression since E01 | Supported trivially (3/3): the T1723 clause holds on its merits, and the T1718 clause holds only because the score is 0 by construction |
| H2, the resolver adds detection on Zhiyi | Not supported (3/3): +0.007 against a +0.05 bar |
| H3, the resolver costs precision on Kuiji dev | Not supported (2, 1 undetermined). This wasn't a real test: the resolver added no nodes there, only root spans, which a commentary-keyed score can't see |
| H4, no transfer to the CBETA 科判 texts | Supported trivially (2, 1 supported): tier 2 abstained |
| H5, YBh near zero | Undetermined (2, 1 trivially supported): T1602's tier 2 and hybrid failed on a bug, and structure-mode S-F1 collapses top-down |
| H6, the lemma anchor reaches 0.80 | Not supported (3/3): 0.453 is the ceiling on this gold, since 29 of 41 spans have no lemma |
| H7, model-only is below hybrid on root text | Not supported (2, 1 undetermined): every arm is 0 at t = 0 by construction (the 序品 pin is one line off), and at t = 1 model-only's S-F1 is higher |

## What this changes for the parser-gate decision

E01's rule reads S-F1 on T1718 validation. E06 gives 0.000 again, below the 0.40 threshold, so the pre-registered default is the pivot: the parser becomes a high-recall announcement detector and attachment moves to the resolver. E06 adds three facts the rule did not foresee:
1. **The 0 is structural, not a grade.** On the pre-registered row it is 0 by construction: 0 of 101 gold nodes are reachable from a build that reads only the validation span, because all of them hang under dev ancestors. This was already true of E01's read-out 1. On the post-hoc dev+validation row, every counted validation node hangs under one editorial dev level-1 node that no arm matches, so the 0 still measures a single top-level attachment.
2. **The pivot's premise fails on Zhiyi.** The parser isn't high-recall. It finds 8–11% of the gold's division lines at t = 0 and 15–24% at t = 1.
3. **The resolver can't take over attachment yet.** As frozen it may only add nodes and spans, never move one, and every child it added on Zhiyi counts as a structural false positive.

So a pivot needs new resolver capability (re-attaching explicit nodes) and a read-out that doesn't collapse on one top-level error, such as a relative-depth or subtree-aligned F1. Not pivoting needs the Kuiji test read-out to show that the parser generalises within Kuiji. A third option is one bounded Zhiyi iteration: promote the whole-text division (分文為三) to level 1, and map formula lines to span starts.

## What this changes for the API-budget decision

**What the Claude-answered resolver bought in E06:**
- no structural gain on Zhiyi;
- line-level gains on the post-hoc build that had dev context;
- boundary detection above chance on two OOD texts;
- a perfect root-span score on Kuiji dev, which the gold's seeding confounds.

**Cost and how to proceed:**
- **What sets the cost is request size, not request count.** The 84 answered request files total about 2.64 million characters (about 2.45 million over the 80 distinct requests), about 30% of it fixed prompt.
- **A size-budget defect inflates the large requests.** The text limit counts characters before each line gets its linehead prefix, so 6 distinct resolver requests (7 files) exceeded 120,000 characters.
- **Interactive answering got all 80 requests through, in 8 rounds.** HYPOTHESIS: that is enough for development runs.
- **Recommended:** defer a paid budget. First fix request sizing, then price a run on re-measured requests. Buy API time when a run is too large to answer interactively, or when the test read-out should use the shipped `claude` configuration.

## Caveats

- **Zeros by construction.**
  - T1718-validation S-F1, every arm (reachability 0/101).
  - T0262 序品 at t = 0, every arm (the 序品 pin sits on the 品 title line, one line above the sdp gold's level-1 start).
  - X0268, every arm: the genre gate yields no tier-2 structure, and the ~300k-character body is one leaf the resolver skips as too large.
  - YBh structure-mode S-F1: DILA's headings are not the treatise's wording, and the matching collapses top-down.
- **Leakage.**
  - The audit found 0 forbidden accesses in 483 tool uses by the 84 answer agents, and no test or reserve text in any request. E06's output files pass the sdp eval-only guard with 0 hits.
  - A transcript audit can't see pretraining knowledge, and it can't separate shared judgement from what the text fixes.
- **The validation look took two passes.** Tier 1 and tier 2 were scored before the LLM arms were answered. No answer agent saw a score. E01's `looks.json` holds the new entries, uncommitted.
- **The scorer has known defects.** None is fixed, because `pipeline/` is frozen:
  - t = 1 scores are lower bounds, because siblings are paired greedily;
  - structure-mode merged-range splits count as FP (affects T1602 only);
  - root-text predictions in regions with no split are neither TP nor FP;
  - the headline flag was true on the OOD rows (overridden to false here).
- **Not run or not measured.**
  - The test spans, blind by decision, and so T0262 序品 against the Kuiji gold.
  - E04: Kurt's skill isn't on hand.
  - The 1,608 sdp T0262 nodes with no split.
  - Heading quality and gloss quality.
  - T1602 tier 2 and hybrid (they failed).
  - Chunk quality beyond the invariants.
  - Any variance estimate for the single-draw LLM answers.
- **Some analyses had one reader.** That includes the coding of the answer agents' problem reports and the cut-convention counts.

Details, file:function targets and the row behind every number are in `README.md` § Result and § Interpretation.
