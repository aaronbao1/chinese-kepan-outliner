# reference-outlines/

Gold outlines for evaluation, committed and licence-clean. Layout: `<text-id>/<scheme_id>/outline.json` + `PROVENANCE.md`. A hand-authored gold also has `outline.txt`: that file is the source of truth, and `outline.json` is compiled from it and never edited by hand. Each `outline.json` is an *independent outline* under profile `zh-kepan` (`context/baseline/outline-schema-zh.json`; D15 in `docs/chinese-workflow-mapping.md`) and passes `scripts/validate_outline.py`. `PROVENANCE.md` says who made the gold, from which source and edition, how, under which `scheme_id`, with `seeded_by` which system if any (a gold seeded by a model is biased toward that model, R06 F19), its licence and its review status.

**Registry.** Every gold here is registered in `data/eval-sets.json`, and `tests/unit/test_gold_registry.py` fails on an unregistered one. The registry's guide, `data/EVAL-SETS.md`, holds the rest: node counts, what each gold anchors, split membership, gaps, the experiments that use it, and the notes for scoring against it.

**Licences** (`NOTICE` carries the notices the licences require; nothing here is relicensed permissively):
- CBETA-derived golds: CC BY-NC-SA 4.0 + CBETA's notice + release label `2026R2`.
- DILA-YBh-derived golds: CC BY-SA 4.0. The CHIBS mirror's "CC BY-SA 3.0 台灣" statement is unreconciled.
- The sdp (法華經數位資料庫) golds publish no licence. They are eval-only and never placed here: they live in `data/raw/dila-sdp/gold/`, which is gitignored.

| Folder | Text | Outline from | Built by (`pipeline/src/chinese_workflow/eval/gold/`) | Status | Split |
|---|---|---|---|---|---|
| `T0262/kuiji-xuanzan/` | 妙法蓮華經 (T09n0262) | Kuiji's 妙法蓮華經玄贊 (T34n1723), first whole-sūtra scheme | `authored.py` from `outline.txt` | **draft-unreviewed**, model-seeded: needs a human review before any headline score | dev (陀羅尼品), test (序品, 譬喻品 opening), rest reserve |
| `X0268/cbeta-mulu-kepan/` | 楞嚴經集註 (X11n0268) | CBETA's own `cb:mulu type="科判"` markup (self-outlining) | `cbeta_mulu.py` | imported-unchecked | out-of-domain |
| `P1573/cbeta-mulu-kepan/` | 修懺要旨 (P167n1573) | as X0268 | `cbeta_mulu.py` | imported-unchecked | out-of-domain (registry decision) |
| `D8842/cbeta-mulu-kepan/` | 般若心經註解 (D14n8842) | as X0268 | `cbeta_mulu.py` | imported-unchecked | out-of-domain (registry decision) |
| `T1605/ybh-dila/` | 大乘阿毘達磨集論 (T31n1605) | DILA YBh `-kp.txt` (following 韓清淨's 科文), structure only | `ybh.py` | imported-unchecked | out-of-domain |
| `T1602/ybh-dila/` | 顯揚聖教論 (T31n1602) | DILA YBh `-kp.txt` (following 早島理・毛利俊英 1990), structure only | `ybh.py` | imported-unchecked | out-of-domain |

**Adding a gold:**
1. Build it with a module in `pipeline/src/chinese_workflow/eval/gold/`. Read line references from CBETA with `chinese_workflow.ingest.lines`; never type them.
2. Write its `PROVENANCE.md`.
3. Register it in `data/eval-sets.json`.
4. Run `python3 scripts/eval_sets.py --write`, then the tests.
