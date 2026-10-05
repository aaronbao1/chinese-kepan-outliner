# tests/fixtures/cbeta-api/

Small verbatim responses of the CBETA API (https://cbdata.dila.edu.tw/stable/, API 4.6.7, data 2026R2), saved by
`experiments/E00-kepan-census/census.py fetch` (the `works-toc-*` files: by `scripts/fetch_cbeta_api.sh`, whose `--check`
verifies the `data/raw/cbeta-api/` originals) on 2026-09-22 and copied here unchanged so the E00 census can be
checked offline. Each file is < 25 KB. The full cache (≈ 1,200 responses, incl. the 158 `juans` fascicles) is regenerated into
`experiments/E00-kepan-census/out/api/` by re-running the fetch (gitignored). CBETA text inside these files is CC BY-NC-SA 4.0
(CBETA 版權宣告, reproduced in `data/reference-outlines/NOTICE` from the snapshot `data/raw/cbeta/LICENCE-NOTICE.txt`); catalogue labels are DILA's.

| File | Request | What it shows |
|---|---|---|
| `catalog_orig-T.json` | `catalog_entry?q=orig-T` | the 62 Taishō 原書 部 nodes with volume and T-number ranges (經疏部 = orig-T.035–041, 律疏部 042, 論疏部 043–047) |
| `catalog_orig-T.035.json` | `catalog_entry?q=orig-T.035` | 經疏部一 T1693–1717: 25 work leaves with `category` (CBETA 部類) and `creators` |
| `catalog_orig-X.json` | `catalog_entry?q=orig-X` | the 7 卍續藏 原書 部 nodes (印度撰述, 大小乘釋經部 …) |
| `catalog_CBETA.json` | `catalog_entry?q=CBETA` | the 23 CBETA 部類 |
| `catalog_CBETA.004.json` | `catalog_entry?q=CBETA.004` | 法華部類: three sub-nodes (法華經／疏, 法華經釋論, 天台宗) |
| `catalog_CBETA.004.001.json` | `catalog_entry?q=CBETA.004.001` | the root-text／疏 cluster labels (`T0262-65 法華經／疏 T33-34, X27-35, …`) |
| `catalog_CBETA.009.json` | `catalog_entry?q=CBETA.009` | 經集部類: 18 clusters, e.g. `T0663-65 金光明經 etc. T16／疏 T39, X20` |
| `title_科文.json` … `title_科判.json`, `title_科.json` | `search/title?q=<term>` (percent-encoded) | title hits: 科文 14, 科註 15, 科解 4, 科節 1, 科判 0; 科 `num_found` 93 but only the default 20 rows |
| `title200_科.json` | `search/title?q=科&rows=200` | all 93 科 title hits (74 X, 12 G, 2 ZW, 1 each U/S/P/JA/B; no T) |
| `search_序分.json`, `search_正宗分.json`, `search_流通分.json` | `search?q=<term>&rows=0` | `num_found` 771 / 454 / 605 works (re-check of R01 S28) |
| `works-toc-T0262.json` | `works/toc?work=T0262` | CBETA Online's outline tree for 妙法蓮華經: 33 `mulu` nodes (28 品 + 3 序 + 1 附文 at level 1, 1 序 at level 2 under the 附文, R02 F20) with `lb`/`juan`, plus a `juan` list of 7 (title 第一…第七, `lb` = the 卷 `cb:mulu` line). Oracle for `tests/unit/test_ingest_lines.py` (the ingest mulu tree must equal `works/toc`). Saved by `scripts/fetch_cbeta_api.sh` on 2026-09-22, sha256 `b63273d5c2c13550a293540134c1b80f6d7deb19fbadaaedbe793277f4d9a679` |
| `works-toc-T1718.json` | `works/toc?work=T1718` | 妙法蓮華經文句 tree: 43 nodes (1 序 + 28 品 at level 1, 14 untyped level-2 per-juan markers) and 20 half-juan (上/下) `juan` entries. Same oracle and provenance, sha256 `ce45000404def382de9c0280adba72c0d745f7a4c3634a5a2b92ad7bd6085ec6` |
| `works-toc-T1723.json` | `works/toc?work=T1723` | 妙法蓮華經玄贊 tree: 38 nodes (28 品 at level 1, 10 untyped level-2 per-juan markers, R02 F27 / R04 F37) and 20 half-juan (本/末) `juan` entries. Same oracle and provenance, sha256 `254d9a4982946fadeeeb155e6c28d8360acce647126ae7852be4e3ea6495b52a` |
