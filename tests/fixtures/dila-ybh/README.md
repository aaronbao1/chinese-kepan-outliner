# tests/fixtures/dila-ybh/

Small excerpts of DILA's 瑜伽師地論資料庫 (YBh) standalone 科判 files, for parser tests of the `-kp.txt` format.

| File | Source | What it is |
|---|---|---|
| `T1605-kp.head60.txt` | https://ybh.dila.edu.tw/download2/kp/T1605-kp.txt (fetched 2026-09-21, sha256 of the full file `bddb5f6630f41a0d9e8dea36facb7b6b9e9748c4d38fed5a9acfecf452f59843`, 109,166 bytes, 2,605 lines) | first 60 lines, bytes unchanged |

Format (checked on the full T1579, T1602 and T1605 files when they were fetched; `chinese_workflow.eval.gold.ybh`'s docstring has the full rules):
UTF-8 without BOM; one node per line; indentation of two ASCII spaces per level; label = depth letter (`A` = level 1 … `Z` = 26,
then `a` = 27 …) + sibling number, followed by one space and the title; ranges such as `H4-5` mark merged nodes. No Taishō
references in the standalone file; the `-text-kp.zip` variant interleaves the same labels as `【D1 問】` headings into the text.

Licence: the YBh download page footer (https://ybh.dila.edu.tw/pages/download?locale=zh&menu=download) reads
"© CC BY-SA 4.0" (法鼓文理學院 DILA 1999-2026); the older CHIBS mirror's about page states CC BY-SA 3.0 Taiwan instead
(the YBh golds' `PROVENANCE.md` records both). This excerpt is redistributed under CC BY-SA 4.0 with attribution to DILA; the full files are fetched by `scripts/fetch_dila_ybh.sh` and are gitignored.
