# PROVENANCE: T1605 / ybh-dila

Gold outline of 大乘阿毘達磨集論 (T31n1605), imported unchanged from DILA's 瑜伽師地論資料庫 (YBh)
standalone 科判 download. **Structure only**: this file carries no Taishō line anchors, so every
node's `locations` is `{"scheme": "none"}` and every node carries flag `unmapped`. `scheme_id:
ybh-dila`, `outline_mode: sutra`, `commentary_id: null`, `root_text_id: T31n1605`,
`gold_status: imported-unchecked`, `origin: imported` on every node, `seeded_by: null`.

| File | What |
|---|---|
| `outline.json` | The gold, built by `chinese_workflow.eval.gold.ybh` from `data/raw/dila-ybh/T1605-kp.txt`. Rebuild with `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.ybh ../data/raw/dila-ybh/T1605-kp.txt`. `tests/unit/test_gold_ybh.py` checks the committed file against a fresh rebuild when the raw file is present |

## Source

- **URL:** `https://ybh.dila.edu.tw/download2/kp/T1605-kp.txt` (fetched by `scripts/fetch_dila_ybh.sh`; download page `https://ybh.dila.edu.tw/pages/download?locale=zh&menu=download`).
- **Fetched:** 2026-09-21. **sha256** (`scripts/CHECKSUMS`): `bddb5f6630f41a0d9e8dea36facb7b6b9e9748c4d38fed5a9acfecf452f59843`, 109,166 bytes, 2,605 lines.
- **T1606 note:** `T1606-kp.txt` (雜集論), downloaded the same day, was byte-identical to `T1605-kp.txt` (same sha256; `scripts/fetch_dila_ybh.sh` therefore does not fetch it separately — see its header). No separate T1606 gold is built from it; a T1606 gold, if wanted, would be this same file re-labelled.
- **Raw file is gitignored**, never committed; `data/raw/dila-ybh/T1605-kp.txt` is fetched, not stored here.

## Format and import rules

DILA's `-kp.txt`: UTF-8 without BOM, one node per line, two ASCII spaces of indentation per level, a
label (depth letter A=level 1 … Z=26, then a=27 … + a decimal sibling number; a hyphenated sibling
range such as `H4-5` marks one node standing for several of DILA's original siblings), a space,
then the heading, with an optional trailing full-width `（分<Chinese numeral>）` announcing the
number of children. Full rules, with the exact counts for this file, are in
`chinese_workflow.eval.gold.ybh`'s module docstring and `metadata.format_note`; summary:

- Depth is taken from the label's letter, cross-checked against the line's indentation. They agree
  on every one of T1605's 2,605 lines (checked 2026-09-22): no node here is flagged `irregular_label`.
- `H4-5`-style merged labels: none in T1605 (0 nodes flagged `merged_range`).
- `child_count_announced` (from `（分N）`): 917 of the 2,605 nodes carry one; it disagrees with the
  number of children actually present in **7** of them (flagged `count_mismatch`, warning-level,
  `scripts/validate_outline.py [child-count]`): the labels J2 答 (×2), L2 別釋空有, K7 邪行, P2
  明戒業, H2 明三藏相攝及建立義 (all announce 3, have 2) and H3 明現觀所攝功德 (announces 2, has 3).
  These are genuine disagreements in DILA's own source data, not a parsing artefact (checked by
  hand against the raw file, 2026-09-22).
- `extent_announced` is always null: the standalone `-kp.txt` carries no verse-extent formulas.
- Node count and maximum depth agree exactly with the count made when DILA's files were first
  surveyed (2026-09-21; non-empty lines of the standalone file): **2,605 nodes, max depth 24**.

## `root_text_id`

DILA's download page states no CBETA volume number for T1605. `root_text_id: T31n1605` was
confirmed by inspecting the local clone `data/raw/cbeta/xml-p5` (git tag `2026R2`) on 2026-09-22:
`T/T31/T31n1605.xml` exists and its `<title level="m">` reads 大乘阿毘達磨集論. This was checked
directly with a command, not taken from a secondary source. No
line of that XML file is read or checked against the `-kp.txt` content — this gold is structure
only, and `cbeta_release: 2026R2` records only which release the id was confirmed to exist in.

## `outline_mode`

`metadata.outline_mode: "sutra"`, `commentary_id: null`. (An early draft of the build instructions
called this case self-outlining; the gold uses sūtra mode, for the reason below.)

This is `outline-schema-zh.json`'s `metadata_zh.commentary_id` documented **case (b)**: "sūtra mode
with a stating work that has no CBETA file id to cite". DILA's own account (the outline section of the YBh manual,
`https://ybh.dila.edu.tw/pages/outline?locale=zh&menu=manual`) is that T1605's 科判 follows 韓清淨's 大乘阿毘達磨集論科文別釋 (【韓科】) — an external
stating work, not T1605 itself, and no CBETA id for that work is recorded anywhere in this repo. So
`commentary_id` stays null and the stating work is named here and in `metadata.source_document.notes`
instead (`scheme_id` is the fixed value `ybh-dila`, common to both T1605 and T1602, not a
per-stating-work name the way `sdp.py`'s scheme ids are).

DILA's per-node source labels (【韓科】 vs earlier drafts) are recorded in DILA's TEI masters, whose
markup the YBh XML manual on DILA's wiki (`https://wiki.dila.edu.tw/`) documents and which DILA does
not publish. They are not in this plain-text export and are not reconstructed here.

## Licence

`licence.id: CC-BY-SA-4.0` (`data/EVAL-SETS.md` rule 2). DILA's YBh download page footer
(`https://ybh.dila.edu.tw/pages/download?locale=zh&menu=download`, fetched 2026-09-21, snapshotted at
`data/raw/dila-ybh/download-page.html`, sha256 `8effae0070dc3a641285c2fed6cd5e852e53343640266f04cf4f112067992e23`
per `scripts/CHECKSUMS`) reads "© CC BY-SA 4.0" (icons cc / by / sa; no NC icon). "法鼓文理
學院 DILA 1999-2026".

**Unreconciled licence statement (`data/EVAL-SETS.md` rule 2):** the CHIBS mirror of YBh's own 關於本站
page states a different licence line: "本資料庫係採用創用 CC 姓名標示-相同方式分享 3.0 台灣 授權
條款授權" (CC BY-SA 3.0 台灣), in the footer of `http://ybh.chibs.edu.tw/aboutYBh.php` (fetched
2026-09-22; the same path on ybh.dila.edu.tw returns 404). This is recorded here, not reconciled with
the live DILA download page's 4.0 statement; no attempt is made here to determine which is
authoritative or current.

`eval_only: false` (the licence permits redistribution with attribution and share-alike; this gold
is committed under `data/reference-outlines/`, unlike the eval-only sdp golds under
`data/raw/dila-sdp/gold/`).

## What this gold is for

T1605 is one of two licence-clean DILA YBh imports (with T1602): an out-of-domain, structure-only
eval set (`data/EVAL-SETS.md` rule 5) and a potential training example. Because it carries no
Taishō anchors, it can score outline *structure* (parent/child shape, depth, sibling order,
`child_count_announced` agreement) but not chunk-boundary or line-level metrics; for those the outline
would first have to be aligned to `data/raw/cbeta/xml-p5/T/T31/T31n1605.xml`.
