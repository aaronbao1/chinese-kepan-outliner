# PROVENANCE: T1602 / ybh-dila

Gold outline of 顯揚聖教論 (T31n1602), imported unchanged from DILA's 瑜伽師地論資料庫 (YBh)
standalone 科判 download. **Structure only**: this file carries no Taishō line anchors, so every
node's `locations` is `{"scheme": "none"}` and every node carries flag `unmapped`. `scheme_id:
ybh-dila`, `outline_mode: sutra`, `commentary_id: null`, `root_text_id: T31n1602`,
`gold_status: imported-unchecked`, `origin: imported` on every node, `seeded_by: null`.

| File | What |
|---|---|
| `outline.json` | The gold, built by `chinese_workflow.eval.gold.ybh` from `data/raw/dila-ybh/T1602-kp.txt`. Rebuild with `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.ybh ../data/raw/dila-ybh/T1602-kp.txt`. `tests/unit/test_gold_ybh.py` checks the committed file against a fresh rebuild when the raw file is present |

## Source

- **URL:** `https://ybh.dila.edu.tw/download2/kp/T1602-kp.txt` (fetched by `scripts/fetch_dila_ybh.sh`; download page `https://ybh.dila.edu.tw/pages/download?locale=zh&menu=download`).
- **Fetched:** 2026-09-21. **sha256** (`scripts/CHECKSUMS`): `77ec1827cfb1236bf5ec85885ddf4c5254d45bcd9b1d989baf8cd3a2613593ec`, 96,186 bytes, 2,594 lines.
- **Raw file is gitignored**, never committed; `data/raw/dila-ybh/T1602-kp.txt` is fetched, not stored here.

## Format and import rules

Same `-kp.txt` grammar as T1605's sibling gold (see `data/reference-outlines/T1605/ybh-dila/PROVENANCE.md`
and `chinese_workflow.eval.gold.ybh`'s module docstring). This file's own counts:

- Depth (label letter cross-checked against indentation) agrees on every one of T1602's 2,594 lines
  (checked 2026-09-22): no node here is flagged `irregular_label`.
- `H4-5`-style merged labels: **14** nodes are flagged `merged_range` — e.g. `K5-9` 眼耳鼻舌身,
  `L1-2` 建立近分及根本, `J10-13` 身修、戒修、心修、慧修 (full list in `outline.json`'s nodes).
- `child_count_announced`: T1602's `-kp.txt` never uses the `（分N）` announcement anywhere (checked
  2026-09-22, unlike T1605); every node's `child_count_announced` is `null`, and consequently **0**
  nodes are flagged `count_mismatch`.
- `extent_announced` is always null (same reason as T1605).
- Node count and maximum depth agree exactly with the count made when DILA's files were first
  surveyed (2026-09-21; non-empty lines of the standalone file): **2,594 nodes, max depth 20**.

## `root_text_id`

DILA's download page states no CBETA volume number for T1602. `root_text_id: T31n1602` was
confirmed by inspecting the local clone `data/raw/cbeta/xml-p5` (git tag `2026R2`) on 2026-09-22:
`T/T31/T31n1602.xml` exists and its `<title level="m">` reads 顯揚聖教論. This was checked directly
with a command, not taken from a secondary source. No line of that XML file is read or
checked against the `-kp.txt` content — this gold is structure only, and `cbeta_release: 2026R2`
records only which release the id was confirmed to exist in.

## `outline_mode`

`metadata.outline_mode: "sutra"`, `commentary_id: null`. (An early draft of the build instructions
called this case self-outlining; the gold uses sūtra mode, for the reason below.)

This is `outline-schema-zh.json`'s `metadata_zh.commentary_id` documented **case (b)**: "sūtra mode
with a stating work that has no CBETA file id to cite". As with T1605 (see that gold's
PROVENANCE.md), DILA's own account (the 科判區 section of the YBh about page on the older CHIBS
mirror, `http://ybh.chibs.edu.tw/aboutYBh.php`, fetched 2026-09-22) is that T1602's 科判 follows
早島理・毛利俊英 (1990) —
an external stating work, not T1602 itself, and no CBETA id for that work is recorded anywhere in
this repo. So `commentary_id` stays null and the stating work is named here and in
`metadata.source_document.notes` instead (`scheme_id` is the fixed value `ybh-dila`, common to both
T1602 and T1605).

## Licence

`licence.id: CC-BY-SA-4.0` (`data/EVAL-SETS.md` rule 2), identical terms to T1605's sibling gold: DILA's
YBh download page footer "© CC BY-SA 4.0"
(`https://ybh.dila.edu.tw/pages/download?locale=zh&menu=download`), with the CHIBS mirror's "CC
BY-SA 3.0 台灣" statement (`http://ybh.chibs.edu.tw/aboutYBh.php`) also recorded and not reconciled
with the 4.0 statement. See T1605's PROVENANCE.md for the full text
of both statements; they are identical for T1602 (one licence covers the whole YBh site).

`eval_only: false` (redistribution with attribution and share-alike is permitted; this gold is
committed under `data/reference-outlines/`).

## What this gold is for

T1602 is the second of two licence-clean DILA YBh imports (with T1605): an out-of-domain,
structure-only eval set (`data/EVAL-SETS.md` rule 5) and a potential training example. Structure
only: it can score outline shape (parent/child structure, depth, sibling order, the merged_range
nodes) but not chunk-boundary or line-level metrics, which would first need an alignment to
`data/raw/cbeta/xml-p5/T/T31/T31n1602.xml`.
