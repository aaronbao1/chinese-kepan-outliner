# EVAL-SETS — the kēpàn outliner's evaluation datasets and splits

Everything needed to measure the outliner: gold outlines, the heading check, the parser test cases, fixtures, and the dev / validation / test / reserve split. Built 2026-09-22, under the rules in "Rules for gold data" below.

- **Machine-readable registry:** `data/eval-sets.json`. It is the **single source of truth for the split spans**: `tests/unit/test_kepan_cases.py` reads them from there, and `tests/unit/test_gold_registry.py` checks that `eval.gold.sdp_check`'s copy agrees.
- **Computed, never typed:** each dataset's `file_metadata` and `counts` in the registry, and every table in this file between `<!-- eval-sets:… -->` markers, come from `python3 scripts/eval_sets.py --write`. `--check` (and the registry test) fail when a file present on disk no longer matches. Eval-only files live under `data/raw/` (gitignored); on a checkout without them the recorded numbers stand and their checks skip.
- **Vocabulary:** the terms of Kurt Keutzer's Tibetan workflow (`docs/glossary.md`). A gold here is an *independent outline* (`outline.json`) under profile `zh-kepan` (`context/baseline/outline-schema-zh.json`, D15 in `docs/chinese-workflow-mapping.md`). Every gold passes `scripts/validate_outline.py` with exit 0.

## At a glance

"Anchors" says which text the gold's locators point into: `commentary` = lines of the commentary that states the outline; `root` = spans of the sūtra it divides; `self` = lines of a text that outlines itself; `structure-only` = no locators at all.

<!-- eval-sets:datasets begin -->
| Dataset | File | In git | Anchors | Licence | gold_status | Size | Split | Used by |
|---|---|---|---|---|---|---|---|---|
| `sdp-T1718-zhiyi-wenju` | `data/raw/dila-sdp/gold/T1718.zhiyi-wenju-sdp.outline.json` | no (gitignored) | commentary | none (eval-only) | imported-unchecked | 1,458 nodes, depth 19, 908 leaves | per node, by locations.commentary.explained in T1718 | E01 |
| `sdp-T0262-zhiyi-wenju` | `data/raw/dila-sdp/gold/T0262.zhiyi-wenju-sdp.outline.json` | no (gitignored) | root | none (eval-only) | imported-unchecked | 2,048 nodes, depth 19, 1,345 leaves | per node, by locations.commentary.explained in T1718 | E02, E03 |
| `sdp-crosswalk-T0262-T1718` | `data/raw/dila-sdp/gold/crosswalk-T0262-T1718.tsv` | no (gitignored) | — | none (eval-only) | — | 1,728 links | as `sdp-T0262-zhiyi-wenju` | E03 |
| `sdp-T1718-heading-check` | `data/raw/dila-sdp/gold/heading-check.tsv` | no (gitignored) | — | none (eval-only) | — | 1,458 nodes checked | as `sdp-T1718-zhiyi-wenju` | E01 |
| `kuiji-xuanzan` | `data/reference-outlines/T0262/kuiji-xuanzan/outline.json` | yes | commentary+root | CC-BY-NC-SA-4.0 | draft-unreviewed | 149 nodes, depth 11, 104 leaves | per node, by locations.commentary.explained in T1723 | E01, E02, E03, E04 |
| `cbeta-mulu-X0268` | `data/reference-outlines/X0268/cbeta-mulu-kepan/outline.json` | yes | self | CC-BY-NC-SA-4.0 | imported-unchecked | 2,611 nodes, depth 28, 1,505 leaves | out-of-domain | self-outlining mode |
| `cbeta-mulu-P1573` | `data/reference-outlines/P1573/cbeta-mulu-kepan/outline.json` | yes | self | CC-BY-NC-SA-4.0 | imported-unchecked | 127 nodes, depth 14, 80 leaves | out-of-domain | self-outlining mode |
| `cbeta-mulu-D8842` | `data/reference-outlines/D8842/cbeta-mulu-kepan/outline.json` | yes | self | CC-BY-NC-SA-4.0 | imported-unchecked | 40 nodes, depth 10, 24 leaves | out-of-domain | self-outlining mode |
| `ybh-T1605` | `data/reference-outlines/T1605/ybh-dila/outline.json` | yes | structure-only | CC-BY-SA-4.0 | imported-unchecked | 2,605 nodes, depth 24, 1,688 leaves | out-of-domain | self-outlining mode |
| `ybh-T1602` | `data/reference-outlines/T1602/ybh-dila/outline.json` | yes | structure-only | CC-BY-SA-4.0 | imported-unchecked | 2,594 nodes, depth 20, 1,885 leaves | out-of-domain | self-outlining mode |
| `kepan-formulae-cases` | `tests/fixtures/kepan-formulae/cases.jsonl` | yes | — | CC-BY-NC-SA-4.0 | — | 148 cases (close 3, division 112, genre-gate 5, not-division 28) | dev | E01 |
| `cbeta-excerpt-T1723-dharani` | `tests/fixtures/cbeta-xml-p5/T34n1723-excerpt-p0850a19-p0850b19.xml` | yes | — | CC-BY-NC-SA-4.0 | — | 60,407 bytes | dev | E01 |
| `cbeta-excerpt-T0262-dharani` | `tests/fixtures/cbeta-xml-p5/T09n0262-excerpt-p0058b08-p0059b27.xml` | yes | — | CC-BY-NC-SA-4.0 | — | 42,742 bytes | dev | E01 |
<!-- eval-sets:datasets end -->

## Rules for gold data

These rules bind every gold, fixture and parser case listed here. They were fixed when the sets were built (2026-09-22), as the "Global Constraints" of the plan that built them (a development document, not part of this repository). They keep that numbering, so "Global Constraint N" in code comments and records means rule N below.

1. **sdp is eval-only.** Whatever is derived from `data/raw/dila-sdp/` (trees, headings, spans, the gold JSON, check reports) is written only under `data/raw/dila-sdp/gold/`, which is gitignored. None of it goes into `data/reference-outlines/`, `tests/fixtures/` or any other committed file, except aggregate counts, sdp node ids and a few locator facts (in tests and in this guide), and never heading text. Tests over sdp data skip when the raw files are absent, and a committed fixture in sdp's HTML or JSON format is synthetic and says so in its first line. `tests/unit/test_sdp_eval_only_guard.py` scans every tracked file for sdp headings.
2. **Licences.** A gold derived from CBETA (the T1723, X0268, P167n1573 and D14n8842 headings and anchors) is under CC BY-NC-SA 4.0 with CBETA's notice and the release label `2026R2` (snapshot `data/raw/cbeta/LICENCE-NOTICE.txt`). A gold derived from DILA's YBh outlines is under CC BY-SA 4.0, as the DILA site's footer states; the different "CC BY-SA 3.0 台灣" statement of the CHIBS mirror is recorded in the gold's PROVENANCE.md. Third-party material is never relicensed more permissively.
3. **Format.** Every gold is an outline document with `metadata.outline_profile = "zh-kepan"` and passes `scripts/validate_outline.py` with exit 0. Line references follow the schema's CBETA linehead grammar (e.g. `T34n1723_p0850a20`) and are resolved with `chinese_workflow.ingest.lines` against the CBETA 2026R2 XML under `data/raw/cbeta/`, never typed from memory.
4. **Honest provenance.** An imported gold has `origin: imported` and `source_node_id` on its nodes, `gold_status: imported-unchecked` (`imported-checked` only after a documented check) and `seeded_by: null`. A machine-drafted gold names the drafting model in `seeded_by` and has `gold_status: draft-unreviewed`, and its PROVENANCE.md says that a person must review it before any headline score is reported against it (a gold seeded by a model favours that model). Headings are verbatim source text (`heading_src`); nothing paraphrased is labelled verbatim.
5. **Splits.** The dev, validation, test and reserve spans of T1718 and T1723 are those under "Splits" below; the registry is authoritative. Out-of-domain: X11n0268's 科判 tree and the YBh T1605 / T1602 outlines. Parser test cases and fixtures quote only dev spans or texts other than T1718 and T1723: no validation- or test-span text goes into a case or a fixture.
6. **Builders and checks.** Gold builders live in `pipeline/src/chinese_workflow/eval/gold/` and may import `chinese_workflow.ingest`, never `outline`, `chunk` or `translate`. Fetch scripts keep their header conventions, pace their requests (0.4 s), offer `--check`, and own only their source's lines in `scripts/CHECKSUMS`. Tests live under `tests/` and skip cleanly when `data/raw/` is absent. A fact about CBETA, sdp, YBh or Kuiji is stated as verified only when a cited source or a recorded command backs it.

## Splits

These are the spans of rule 5 above. Lineheads are CBETA's, release 2026R2. Split spans are **start-inclusive, end-exclusive**; gold spans (`root_text.end`, `metadata.coverage_spans`) are **inclusive**. Within T34n1718 and T34n1723, comparing lineheads as strings gives document order (checked by `test_kepan_cases.py::test_split_files_are_monotonic`).

<!-- eval-sets:split-spans begin -->
| Text (file) | Split | Start (inclusive) | End (exclusive) | What |
|---|---|---|---|---|
| T1718 (`T34n1718`) | **dev** | `T34n1718_p0001b18` | `T34n1718_p0016b02` | 卷第一上–卷第一下 |
| T1718 (`T34n1718`) | **validation** | `T34n1718_p0016b02` | `T34n1718_p0036a26` | 卷第二上 to the start of 釋方便品 |
| T1718 (`T34n1718`) | **test** | `T34n1718_p0036a26` | `T34n1718_p0063b11` | 釋方便品 |
| T1718 (`T34n1718`) | **reserve** | `T34n1718_p0063b11` | end of file | from p0063b11 to the end of the file |
| T1718 (`T34n1718`) | reserve | every line no span above holds | | |
| T1723 (`T34n1723`) | **dev** | `T34n1723_p0850a19` | `T34n1723_p0850b20` | 陀羅尼品 |
| T1723 (`T34n1723`) | **test** | `T34n1723_p0651a06` | `T34n1723_p0694b22` | 序品, levels 1–3 below the 品 node (outline levels 3–5 of the Kuiji gold) |
| T1723 (`T34n1723`) | **test** | `T34n1723_p0734b07` | `T34n1723_p0737b04` | 譬喻品 opening |
| T1723 (`T34n1723`) | reserve | every line no span above holds | | |
<!-- eval-sets:split-spans end -->

- **Reserve** is not to be looked at while developing. For T1718 that is everything from `T34n1718_p0063b11`, plus the preface before `p0001b18`; for T1723, everything outside the three spans.
- **Out-of-domain:** X11n0268's 科判 tree and the YBh T1605 / T1602 outlines (rule 5). P167n1573 and D14n8842 are not named in rule 5; the registry files them with X11n0268 (same builder and kind of source, outside T1718 / T1723). That filing has not been reviewed.
- **Quoting rule:** parser test cases and fixtures may quote only dev spans or texts outside T1718 / T1723. No validation- or test-span text in any case or fixture.
- **Prompts and training:** no gold or fixture that holds dev, validation or test material is used as prompt or training material for a system evaluated on those spans (the Kuiji gold says so in `metadata.split_notes`). The sdp golds are never used that way at all (eval-only).

### Do not open while developing

These files hold test-split answer keys (E01–E04) in committed form. Do not open them while developing or tuning a parser or outliner that is evaluated on those spans.
- `data/reference-outlines/T0262/kuiji-xuanzan/outline.txt` and `outline.json`: the 序品 and 譬喻品-opening subtrees (between their `TEST SPLIT` banners in `outline.txt`), the notes on those two 品 nodes, and the header lines that describe them (the conventions comments where they cite 序品 examples, the `coverage` lines; in the JSON, `metadata.coverage`). The skeleton (levels 1–2) and the 陀羅尼品 subtree (dev) may be read.
- `data/reference-outlines/T0262/kuiji-xuanzan/PROVENANCE.md`: the 序品 and 譬喻品 items of "Review status" and of "What is covered".
- `tests/unit/test_gold_kuiji_testsplit.py`: the assertions about those two subtrees (moved out of `tests/unit/test_gold_authored.py`, which a developer may read).

E04's answer key (Kuiji's 譬喻品 opening with its Tibetan translation and a hand alignment) and the research notes that discuss the same divisions (R03 F15 and F23) are not part of this repository.

The sdp golds are eval-only and live outside git; their validation and test nodes are answer keys too (E01–E03).

### Nodes per split

A gold node belongs to the split of its **commentary line** (`locations.commentary.explained`). "no locator" = the node has no explained line.

<!-- eval-sets:splits begin -->
| Gold | Split text, locator | dev | validation | test | reserve | no locator |
|---|---|---|---|---|---|---|
| `sdp-T1718-zhiyi-wenju` | T1718, locations.commentary.explained | 12 (unmapped 2) | 101 | 151 (anchor_inherited 6, unmapped 1) | 181 (anchor_inherited 3, unmapped 2) | 1,013 (truncated 26, unmapped 1,013) |
| `sdp-T0262-zhiyi-wenju` | T1718, locations.commentary.explained | 10 (anchor_inherited 1) | 101 (anchor_inherited 18) | 150 (anchor_inherited 6) | 179 (anchor_inherited 36) | 1,608 (anchor_inherited 203) |
| `kuiji-xuanzan` | T1723, locations.commentary.explained | 45 | 0 | 77 (count_mismatch 19, truncated 21) | 27 (truncated 25) | 0 |
<!-- eval-sets:splits end -->

### T1718 卷-halves and what sdp serves

sdp serves the HTML (and so the anchors) of only 9 of T1718's 20 卷-halves; the other 11 fail on the server, deterministically. Start lines are from the file's `cb:mulu type="卷"` entries.

<!-- eval-sets:juan-halves begin -->
| 卷-half | First line | Served by sdp | Split(s) it overlaps |
|---|---|---|---|
| 1a | `T34n1718_p0001b18` | yes | dev |
| 1b | `T34n1718_p0009b07` | **no** | dev |
| 2a | `T34n1718_p0016b02` | yes | validation |
| 2b | `T34n1718_p0023a20` | yes | validation |
| 3a | `T34n1718_p0030b10` | yes | validation, test |
| 3b | `T34n1718_p0037b11` | yes | test |
| 4a | `T34n1718_p0045c12` | yes | test |
| 4b | `T34n1718_p0052c02` | yes | test |
| 5a | `T34n1718_p0060c14` | **no** | test, reserve |
| 5b | `T34n1718_p0067b07` | yes | reserve |
| 6a | `T34n1718_p0074c04` | **no** | reserve |
| 6b | `T34n1718_p0082a15` | yes | reserve |
| 7a | `T34n1718_p0090b20` | **no** | reserve |
| 7b | `T34n1718_p0098a06` | **no** | reserve |
| 8a | `T34n1718_p0106a02` | **no** | reserve |
| 8b | `T34n1718_p0112c16` | **no** | reserve |
| 9a | `T34n1718_p0120b23` | **no** | reserve |
| 9b | `T34n1718_p0127a14` | **no** | reserve |
| 10a | `T34n1718_p0135b02` | **no** | reserve |
| 10b | `T34n1718_p0141c02` | **no** | reserve |
<!-- eval-sets:juan-halves end -->

What that means per split, for E01:
- **dev:** only 卷一上 (`T34n1718_p0001b18`–`p0009b07`) has answer-key nodes. The gold has no node whose explained line falls in 卷一下, and sdp has none there either: its Version1 static files serve 卷一下 with no outline nodes (R08 F7). Score dev predictions only inside 卷一上.
- **validation:** fully served.
- **test:** 卷五上's part `T34n1718_p0060c14`–`p0063b11` is unserved and has no gold node; exclude it from the test score (out of scope, item 5 of "Using these sets").
- **reserve:** mostly unserved.

### Root-text experiments and the splits

The split spans are commentary spans. T0262 itself is not split: a root-text experiment (E02, E03) inherits the split of the commentary span it is scored against. **T0262 序品 is dev + validation on the Zhiyi side and test on the Kuiji side.** In the sdp T0262 gold, every 序品 node with an explained line has it in T1718's dev or validation span; Kuiji's 序品 commentary is a test span. A root-text experiment has to fix which comparison is its headline before it runs, and must not tune on the other.

**Root lines that no gold commentary line fixes** (the scorer's rule since the review of E06, 2026-10-01; `eval/score.py`, "splits"):
- A gold node takes the split of its own `commentary.explained`.
- A predicted node that starts on the root line of a known gold node (one with its own explained line) takes that node's split, as its likely twin.
- Any other predicted node, and every gold node without an explained line, takes the most protected split (reserve > test > validation > dev) of the commentary from its nearest known gold neighbour before its root line to the nearest after it, including the known nodes on its line, since its commentary lies between theirs. A gold node without an explained line is no known node's twin: its commentary may follow a same-line node's across a split boundary.

So every root line gets a split (item 5: no region of T0262 is excluded), and no gold node of unknown split is scored in a split less protected than one it may belong to (item 1). Against the sdp T0262 gold, the 1,608 gold nodes without an explained line go to reserve (1,602), test (5) and dev (1, whose neighbours are both dev), and a prediction identical to any gold node gets that node's split. A prediction on one of 序品's 319 lines is dev on 4 of them, validation on 311, test on 3 and reserve on 1. The earlier rule left 4,437 of T09n0262's 5,374 lines without a split, so predictions there were neither TP nor FP.

## The datasets

### sdp golds (eval-only): `sdp-T1718-zhiyi-wenju`, `sdp-T0262-zhiyi-wenju`

The CHIBS 法華經數位資料庫 (sdp.chibs.edu.tw) 科判 of the Lotus Sūtra, which follows Zhiyi's 法華文句 (T1718) and links each node to it. No licence is published (R04 F32), so both golds are **eval-only**: they live only under `data/raw/dila-sdp/gold/` (gitignored), are never committed, and are never used as prompt or training material. Committed files may carry only aggregate counts, node ids and a few locator facts from them, never headings (rule 1). `scheme_id: zhiyi-wenju-sdp`; `gold_status: imported-unchecked`. Rebuild: `bash scripts/fetch_dila_sdp.sh` then `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.sdp`.

- **T1718 gold (E01's answer key)** is anchored in the commentary. `commentary.explained` is the T34n1718 line where the node's own text starts. That is sdp's anchor rule, and it is not the line of Zhiyi's announcing formula. `root_text` is borrowed from the T0262 node that links to it, where the link is corroborated.
- **T0262 gold (E02/E03, scheme `zhiyi-wenju-sdp`)** is anchored in the root text. `root_text` comes from sdp's T09n0262 line anchors. `commentary.explained` is the linked T1718 line, present only where that T1718 half is served.
- **Gaps:** the unserved 卷-halves (above). 27 tree nodes came back `fetch_error` (Task 1); one subtree was recovered from the HTML, and the 26 unknown ones carry `truncated`. sdp's level 1 (正宗分 2–20品) is editorial, not Zhiyi's (R03 F23). `anchor_inherited` marks start lines that were inherited, not observed.
- **Crosswalk** (`sdp-crosswalk-T0262-T1718`): one row per (T0262 node, T1718 id) with status `located` / `gap` / `not-in-tree` / `uncorroborated`.

#### Heading check (`sdp-T1718-heading-check`, Task 3)

`python -m chinese_workflow.eval.gold.sdp_check` classifies every T1718 gold node's heading against Zhiyi's own wording in a window around its explained line:
- `verbatim` = a contiguous substring;
- `partial` = LCS ≥ 0.6 of the heading;
- `absent`;
- `no-text` = no window.

A node without an explained line inherits its nearest explained ancestor's window, so its true location is unknown. The noise baseline matches a randomly chosen other node's heading against the same own windows. It shows how much of the `partial` rate chance alone produces.

<!-- eval-sets:heading-check begin -->
| Nodes | verbatim | partial | absent | no-text | total |
|---|---|---|---|---|---|
| **all** | 94 | 279 | 969 | 116 | 1,458 |
| inherited window (location unknown) | 2 | 19 | 876 | 0 | 897 |
| no-text | 0 | 0 | 0 | 116 | 116 |
| own window, dev | 2 | 5 | 5 | 0 | 12 |
| own window, outside every split (mostly reserve) | 28 | 115 | 38 | 0 | 181 |
| own window, test | 33 | 80 | 38 | 0 | 151 |
| own window, validation | 29 | 60 | 12 | 0 | 101 |
| noise baseline (random other heading, own windows, 3 reshuffles) | 10 | 129 | 1,196 | — | 1,335 |
<!-- eval-sets:heading-check end -->

Reading: among nodes with their own window, the sdp headings are mostly Zhiyi's words in part, and about a fifth are verbatim. The inherited bucket is almost all `absent`, because those nodes sit in unserved halves and search the wrong window. That says nothing about the headings. Against R03 F23's 24-group hand sample (node level): 14 of 41 hand-verbatim nodes read `verbatim`, 9 `partial` and 18 `absent`, most of the `absent` ones in the inherited region (the F23 calibration table in `data/raw/dila-sdp/gold/HEADING-CHECK.md`, eval-only and not committed, which `sdp_check` writes). **Score sdp golds on structure and locators, not on heading text.**

### Kuiji gold: `kuiji-xuanzan` (committed, draft)

`data/reference-outlines/T0262/kuiji-xuanzan/`: Kuiji's 科判 of T0262 from his 妙法蓮華經玄贊 (T34n1723), first whole-sūtra scheme (序分 / 正宗 / 流通; R03 F22). The source of truth is `outline.txt`, which a reviewer reads line by line. `outline.json` is compiled from it by `chinese_workflow.eval.gold.authored`, which checks every heading, lemma and span against the XML. The gold is anchored twice. `commentary.explained` is the T34n1723 line of Kuiji's topic marker (此初 / 下明… / 第二…). `root_text` is the T09n0262 span that Kuiji's quoted lemma (經「A至B」) fixes, or else the annotator's cut, with the end inclusive. Gates (三門分別 …) are `commentary-internal` and have no root span.

- **Draft, not reviewed.** `gold_status: draft-unreviewed`, `seeded_by: claude-opus-5-5 (SDD draft 2026-09-22)` (SDD: a subagent-driven drafting session). **No headline score is reported against it before a human review** (R06 F19: a model-seeded gold is biased toward that model). A Claude-based outliner's score on it must say that Claude seeded the gold, even after review. Start with the review-first list in `PROVENANCE.md`.
- **Coverage** (`metadata.coverage_spans`; nodes per entry in the registry's `counts.coverage_spans`):
  - levels 1–2 complete (3 parts, 28 品);
  - 序品 down to outline level 5 (test);
  - 譬喻品 opening at full depth (test);
  - 陀羅尼品 at full depth (dev);
  - the other 25 品 at level 2 only, flagged `truncated`.
- **Spans the commentary does not fix** (`root_text.basis: manual`, `end_basis: manual` / `extent-formula`) are the drafter's reading:
  - sub-items Kuiji lists without a lemma (陀羅尼品);
  - starts cut by hand where Kuiji's lemma differs from T09n0262 (序品);
  - one hand-set end and the ends fixed by stanza counts (譬喻品 opening).
- **Licence:** CC BY-NC-SA 4.0 + CBETA's notice + release 2026R2 (`data/reference-outlines/NOTICE`); `eval_only: false`. The split discipline is separate from the licence.

### CBETA 科判 golds: `cbeta-mulu-X0268`, `cbeta-mulu-P1573`, `cbeta-mulu-D8842` (committed)

CBETA's own `cb:mulu type="科判"` markup, imported as it stands (R02 F15/F28: 4 files in the corpus carry it, 3 are built here). These are self-outlining golds: each node sits on a line of the outlined text itself, and `commentary.explained` = `root_text.start` = that line (`basis: cbeta-mulu`). `root_text.end` is the last line before the next node that is not a descendant. `imported-unchecked`: whose 科判 X11n0268's markup encodes is unrecorded (R02 F28). P1573's tree opens twice at source level 2, so it has two roots flagged `irregular_label`. The XML files' sha256 are stated in each `PROVENANCE.md`, computed from the xml-p5 clone that `scripts/fetch_cbeta_xml_p5.sh` pins by commit. They need no `scripts/CHECKSUMS` lines, since that script checks the clone by commit, not file by file. Rebuild: `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.cbeta_mulu`.

### YBh golds: `ybh-T1605`, `ybh-T1602` (committed, structure only)

DILA's 瑜伽師地論資料庫 `-kp.txt` outlines of 集論 (T31n1605) and 顯揚聖教論 (T31n1602). The downloads carry **no Taishō anchors**, so every node has `locations.scheme: none` and flag `unmapped`. Only the tree can be scored: parent, order, depth, headings, DILA's labels (`display_label`) and announced counts. `outline_mode` is `sutra` (case b): the outline is stated in a work with no CBETA id (T1605: 韓清淨's 集論科文別釋; T1602: 早島理・毛利俊英 1990). The outliner, though, reads the treatise alone, so for the outliner these are self-outlining-mode inputs. Licence CC BY-SA 4.0 per the DILA footer; the CHIBS mirror's "CC BY-SA 3.0 台灣" is unreconciled (each `PROVENANCE.md`). T1605's `count_mismatch` nodes are disagreements inside DILA's data. T1602's `merged_range` nodes (labels like `K5-9`) stand for several siblings. Rebuild: `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.ybh`.

### Parser cases and fixtures (committed)

- **`kepan-formulae-cases`**, `tests/fixtures/kepan-formulae/cases.jsonl` (format and label rule in its README). These are dev material for the tier-2 formula parser:
  - `division` cases give the child count, labels and anaphor;
  - `not-division` cases are doctrinal 「有N」 lists;
  - `genre-gate` cases are 註-genre text (T1775) where no structure should come out.

  T1718 / T1723 cases lie inside the dev spans. No case shares more than 8 consecutive characters with a validation or test span. The labels are a machine draft: a human reviewer is to check them and freeze the case ids before any parser is scored on them (start with the README's "Review first" list, which includes six cases where the label rule and the label's meaning part).

  Accepted deviation from the build's rule of at least two positives per Kuiji variant: Kuiji's 今為二解 (R03 F25) is attested only once as a division, in T1788 (慧沼), so it has no slug and no case (README, "Kuiji variants").
- **`cbeta-excerpt-T1723-dharani`** and **`cbeta-excerpt-T0262-dharani`** are the whole T1723 dev span (陀羅尼品 commentary) and the T0262 chapter it comments on, as verbatim CBETA XML with the header intact (recipe in `tests/fixtures/cbeta-xml-p5/README.md`). They serve as offline smoke fixtures; the Kuiji gold's 陀羅尼品 subtree compiles against them.

Not eval sets: `tests/fixtures/sdp-synthetic/` (synthetic sdp-format pages for the importer's tests), `tests/fixtures/dila-ybh/` (the first 60 lines of T1605's `-kp.txt`), `tests/fixtures/outline-zh/minimal.json` (the schema's synthetic example) and `tests/fixtures/cbeta-xml-p5/G069n1977.xml` (a small whole file with 科判 markup, for the parser's 科判 path).

## Which experiment uses what

The sets were built for E01–E04. Of these only E01 has a record in this repository; the capability sweeps E06 and E07 reuse its datasets on the dev and validation splits and add the out-of-domain golds. The E02–E04 rows say what the sets were designed for.

| Experiment | Datasets | How |
|---|---|---|
| E01 explicit-only recovery | `sdp-T1718-zhiyi-wenju` (answer key), `sdp-T1718-heading-check`, `kepan-formulae-cases`, the two excerpts; then `kuiji-xuanzan` for T1723 | T1718 first: develop on dev (卷一上 only has a key), tune on validation, report on test. Then T1723: develop on 陀羅尼品, report on 序品 and the 譬喻品 opening |
| E02 model-only baseline | `sdp-T0262-zhiyi-wenju`, `kuiji-xuanzan` | the model outlines T0262 序品 raw text; score against both schemes (T0262 序品 is dev + validation on the Zhiyi side, test on the Kuiji side, see above) |
| E03 hybrid parser + resolver | `sdp-T0262-zhiyi-wenju`, `kuiji-xuanzan`, `sdp-crosswalk-T0262-T1718` | as E01/E02, split by `origin` |
| E04 cross-lingual | `kuiji-xuanzan` (ch. 1–11 only: the 序品 and 譬喻品-opening subtrees plus levels 1–2); its Tibetan answer key is not part of this repository | D4017, the Tibetan Kuiji, ends after 見寶塔品 (ch. 11; R03 F5/F20), so the 陀羅尼品 subtree has no Tibetan counterpart |
| Self-outlining mode | `cbeta-mulu-X0268` (and P1573, D8842), `ybh-T1605`, `ybh-T1602` | out-of-domain; X0268 with locators, YBh structure only |

## Using these sets (notes for the scorer)

1. **Load the registry, not paths from memory.** `data/eval-sets.json` has each dataset's path, split scope and counts. Read it through `chinese_workflow.eval.registry` (`scripts/eval_sets.py` is a thin CLI over it): `load_registry()`, `dataset(registry, id)`, `split_of(registry, text, linehead)` (the reference split lookup; it gives `unlisted` → reserve for lines no span holds), `split_spans`, `served_juan_halves` and `in_scoring_scope(registry, dataset_id, linehead)` (item 5). Refuse to score a reserve-split node during development.
2. **E01 node selection: a node is scorable iff `locations.commentary.explained` is not null.** Do not select by flag `unmapped`. In the T1718 gold, `unmapped` also marks nodes that have an explained line but no borrowed `root_text` (the schema's sūtra-mode rule requires the flag). Of those, 2 are in dev (sdp nodes T1718D01_002 and T1718D03_002) and 3 elsewhere; the registry's `counts.by_split` lists them per split.
3. **E01 match key vs sdp's anchor.** sdp's explained line is the line where the node's text span starts. Zhiyi's division formula, which announces the node, can come lines or pages later. Three known pairs of node start and formula line:
   - `T34n1718_p0005c29` vs `p0006a01`;
   - `p0030b15` vs `p0030b22`;
   - `p0036a26` vs `p0040a26`. Here `p0036a26` is the title line 釋方便品 (its `cb:mulu type="品"` in T34n1718.xml).

   A parser that reports the formula line misses at t = 0. R06 chose t = 0 at `lb` granularity before this was known. E01, E06 and E07 key the commentary golds on the take-up line, `locations.commentary.explained`. Whether E01 should key on the node's text-span start instead (sdp's convention) is still open (E06 review, Q1); the registry does not decide it.

   Since 2026-10-02 (E06 review, direction A3) the outliner writes both locators on every node — `locations.commentary.explained`, the take-up line, and `locations.commentary.span_start`, the text-span start under sdp's convention (a first child inherits its parent's start unless the parent is editorial or starts before the build's first line; `span_start_inherited` says so) — and `eval/score.py` scores on either (`--key commentary.span_start`: predictions at their `span_start`, the gold at its own `span_start` where present, else at its `explained` line; a gold node's split is still that of its `explained` line, a prediction's that of its `span_start` line; every row also without inherited predictions). Which key E01 reports on is still open, so a dev or validation row is reported under both keys until that decision is made.
4. **Which locator a row keys on.** The schema's D15 row (HYPOTHESIS) keys the eval on `root_text.start` in sūtra mode. The T1718 gold is a sūtra-mode gold, yet E01 scores a parser of the commentary, so E01 keys on `locations.commentary.explained`. The sūtra-mode key `root_text.start` is used for root-text scoring over T0262: the T0262 sets of E06 and E07 (and the planned E02/E03 in the table above).
5. **Scoring scope and `truncated`** (the scoring contract as revised after review, 2026-09-22; the schema's flag description, the D15 addendum and the gold README carry the same rule, and the T1718 sdp gold's `metadata.format_note` its served-halves clause):
   - **A gold that declares `metadata.coverage_spans` (the Kuiji gold): scope alone decides.** A predicted node is in scope iff two things hold: its start locator lies inside an entry's span (`commentary.explained`, or `root_text.start` for root-text scoring), and its level is at most that entry's `max_level` (`null` = no limit). An in-scope prediction that matches no gold node is FP, also under a `truncated` node. An out-of-scope prediction is neither TP nor FP. There, `truncated` is informational.
   - **A gold without `coverage_spans` (the sdp golds; scope = the whole gold):** a prediction under a `truncated` node that matches no encoded node is neither TP nor FP. The sdp T1718 gold's 26 unrecoverable `fetch_error` nodes carry `truncated`.
   - **In the T1718 sdp gold (E01, keyed on `commentary.explained`), "the whole gold" still means the text sdp serves.** Score only predictions whose explained line lies in a served 卷-half ("T1718 卷-halves and what sdp serves" above). For dev that is only 卷一上 (`T34n1718_p0001b18`–`p0009b07`); the test split excludes `T34n1718_p0060c14`–`p0063b11`. A prediction in an unserved region is out of scope, neither TP nor FP. Otherwise every correct prediction there would count as FP. Machine-readable: the dataset's `scoring_scope` in the registry (the served halves, computed; 卷一上's page also carries the preface, so that half opens at the file start) and `registry.in_scoring_scope`.
   - **Root-text scoring against the T0262 sdp gold (E02/E03, keyed on `root_text.start`): the scope is all of T0262.** sdp serves all seven 卷 of T0262, and every node has a root span, so no region is excluded. The missing T1718 halves only leave some nodes without a `commentary.explained` line, which root-text scoring does not use.
   - **In every gold:** the unencoded source children of a `truncated` node are not FN, and its encoded descendants are scored normally.
   - **Tree edit distance:** prune out-of-scope predicted subtrees before scoring. Without `coverage_spans`, also prune those predicted subtrees under `truncated` nodes that match no encoded node; a predicted node that matches an encoded descendant stays.
6. **Inclusive vs exclusive.** `root_text.end` is inclusive in every gold, and so are the ends in `coverage_spans`. Split spans are end-exclusive. An `end_basis: next-node` end is the line before the next node's start when that node begins its line, else the next node's start line itself, which the two share (the next node starts mid-line; schema `end_basis`, D15 addendum), so sibling spans may overlap by one line.
7. **`count_mismatch`** means the announced count (`child_count_announced`) knowingly differs from the children present. The reasons differ by gold: truncation in the Kuiji gold, the source's own inconsistency in X0268, P1573 and T1605. Score the tree against the children present. Score a predicted child count against `child_count_announced`, and read a disagreement at these nodes as the source's, not the parser's. `coarsened` is a property of the source, and no gold uses it at present.
8. **`anchor_inherited`** means the start line was inherited, not observed (sdp nodes with no anchor of their own). Report t = 0 scores with and without these nodes.
9. **Headings.**
   - sdp `heading_src` keeps sdp's leading ordinal (`1 `, `1-5 `); strip it with `chinese_workflow.eval.gold.sdp.strip_ordinal`. sdp headings are largely not Zhiyi's words (heading check above).
   - Kuiji and CBETA-mulu headings are the source's own text, ordinal included, never normalised.
   - YBh headings are DILA's, with the label moved to `display_label`.
10. **Structure-only golds (YBh)** have no locators, so a locator-keyed S-F1 cannot run on them. Use a structure-only match (heading + depth + parent path) or tree edit distance, and say which. A `merged_range` node stands for several siblings, so a prediction that splits it is not an error. X11n0268 has one `merged_range` node too, `1_1.1_2.6_3.2_4`: one `cb:mulu` holding two labels on line `X11n0268_p0185a08`, kept whole (`cbeta_mulu.py`). A prediction that splits it into the two siblings is not an error either: count the predicted siblings that start on that line under the same parent as one match of that node (one TP, no FP).
11. **Draft golds and leakage.** Before any headline number on the Kuiji gold, check `gold_status`, which must be `reviewed`. Report `seeded_by` with every score. Keep `eval_only` golds out of prompts. Do not open the files listed under "Do not open while developing" (above) while developing.
12. **`metadata.text_id` differs by gold kind; do not key on it.** It names the text whose tree the gold encodes: `T1718` in the commentary-keyed sdp T1718 gold (sdp's tree of the commentary), `T0262` in the sdp T0262 gold and in the Kuiji gold (the root text; the Kuiji gold's `commentary_id` is `T34n1723`), the file's own id in the self-outlining CBETA 科判 golds (`X0268`, `P1573`, `D8842`) and in the YBh golds (`T1605`, `T1602`). A scorer finds the gold for an experiment by the registry's dataset id (`data/eval-sets.json`), pairs a prediction with it on `metadata.root_text_id` + `metadata.scheme_id` (+ `metadata.commentary_id` in sūtra mode: the sdp golds share `T09n0262` + `zhiyi-wenju-sdp` + `T34n1718` and differ in their key), and takes the locator from the dataset's `split_scope.by` and item 4 (E01: `commentary.explained` in T34n1718 / T34n1723; E02/E03: `root_text.start` in T09n0262).

## Rebuilding and checking

```
bash scripts/fetch_cbeta.sh && bash scripts/fetch_cbeta_xml_p5.sh      # CBETA 2026R2 (checksums / pinned commit)
bash scripts/fetch_dila_sdp.sh && bash scripts/fetch_dila_ybh.sh      # sdp (eval-only) and YBh raw files
cd pipeline
.venv/bin/python -m chinese_workflow.eval.gold.sdp                    # sdp golds + crosswalk -> data/raw/dila-sdp/gold/
.venv/bin/python -m chinese_workflow.eval.gold.sdp_check              # heading check -> data/raw/dila-sdp/gold/
.venv/bin/python -m chinese_workflow.eval.gold.cbeta_mulu             # X0268, P1573, D8842
.venv/bin/python -m chinese_workflow.eval.gold.ybh                    # T1605, T1602
.venv/bin/python -m chinese_workflow.eval.gold.authored ../data/reference-outlines/T0262/kuiji-xuanzan/outline.txt \
    -o ../data/reference-outlines/T0262/kuiji-xuanzan/outline.json   # Kuiji gold
cd ..
python3 scripts/validate_outline.py data/reference-outlines/*/*/outline.json data/raw/dila-sdp/gold/*.outline.json
python3 scripts/eval_sets.py --write                                   # registry counts + the tables above
cd pipeline && .venv/bin/python -m pytest ../tests -q                  # incl. tests/unit/test_gold_registry.py
```

`tests/unit/test_gold_registry.py` checks the following:
- every registered gold on disk validates;
- committed datasets exist and are not gitignored;
- eval-only ones are under `data/raw/` and gitignored;
- split spans are well-formed and do not overlap, and they agree with `sdp_check.SPLITS`;
- the 卷-half table matches the XML and the served sdp files;
- the Kuiji gold's `coverage_spans` lie inside their split spans;
- every gold under `data/reference-outlines/` and `data/raw/dila-sdp/gold/` is registered;
- the computed blocks match the files;
- no sdp heading appears in any tracked file, this one and the registry included (`tests/unit/test_sdp_eval_only_guard.py`, with an allowlist of explained coincidences).

Skips are per check, when `data/raw/` is absent.
