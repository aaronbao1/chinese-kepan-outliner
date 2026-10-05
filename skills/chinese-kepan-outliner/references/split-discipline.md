# Split discipline for anyone running or developing the outliner

Source of truth: `data/EVAL-SETS.md` and `data/eval-sets.json`. This page is the short version a session reads before it touches the outliner.

## Never open while developing or tuning

- `data/reference-outlines/T0262/kuiji-xuanzan/outline.txt` and `outline.json`, except the skeleton (levels 1–2, without notes) and the 陀羅尼品 subtree (dev). Read those two parts only through a filter (`chinese_workflow.outline.oracle.oracle_drafts`), never the whole file.
- `data/reference-outlines/T0262/kuiji-xuanzan/PROVENANCE.md`: its 序品 and 譬喻品 items.
- `tests/unit/test_gold_kuiji_testsplit.py`.
- R03 findings F15 and F23 (research notes in the development repository only, not in this copy).
- The sdp golds under `data/raw/dila-sdp/gold/` outside the T1718 dev span; and never copy an sdp heading into any file (`tests/unit/test_sdp_eval_only_guard.py`).

## Spans

| Text | dev (develop) | validation (tune; every look logged) | test (once, frozen) | reserve (never while developing) |
|---|---|---|---|---|
| T1718 | `T34n1718_p0001b18`–`p0016b02` | `p0016b02`–`p0036a26` | `p0036a26`–`p0063b11` | from `p0063b11`, and the preface |
| T1723 | `T34n1723_p0850a19`–`p0850b20` (陀羅尼品) | — | `p0651a06`–`p0694b22` (序品), `p0734b07`–`p0737b04` (譬喻品 opening) | everything else |

Ends are exclusive. The runner and the outline CLI refuse test and reserve spans unless `--frozen <tag>` is given (`chinese_workflow.common.splits.SplitGuard`).

## Golds as material

- Eval-only golds (sdp and its derivatives) are never prompt, exemplar or training material.
- Out-of-domain golds (X0268, P1573, D8842, T1605, T1602) are OOD tests until the registry-roles decision: not input material, and scored only with `--frozen`.
- No gold or fixture holding dev, validation or test material is used as a prompt or exemplar for a system scored on those spans. The exemplar pool is empty until Aaron names it.

## Texts that reproduce split text (do not use as input or exemplar)

T1719 法華文句記, X0596 妙經文句私志記, X0584's 文句科文 (from `X27n0584_p0686a01`), X0594 法華經疏義纘, TX10n0007 (mirrors the T1723 test key), YP10n0015 (sits in the T1718 reserve).
