# PROVENANCE: T0262 / kuiji-xuanzan

Gold outline of the Lotus Sūtra (妙法蓮華經, T09n0262) following the 科判 that Kuiji (窺基) states in his 妙法蓮華經玄贊 (T34n1723). `scheme_id: kuiji-xuanzan`, `outline_mode: sutra`, `commentary_id: T34n1723`, `root_text_id: T09n0262`.

| File | What |
|---|---|
| `outline.txt` | **Source of truth.** One node per line, readable for review; format in `pipeline/src/chinese_workflow/eval/gold/README.md` ("Authored golds") |
| `outline.json` | Compiled from `outline.txt`. Never edit it by hand. Rebuild with `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.authored ../data/reference-outlines/T0262/kuiji-xuanzan/outline.txt -o ../data/reference-outlines/T0262/kuiji-xuanzan/outline.json`. `tests/unit/test_gold_authored.py` checks that the two agree byte for byte |

**Test-split material.** The 序品 and 譬喻品-opening subtrees are test-split answer keys (E01–E04). So are the items about them below (review list and "What is covered") and their assertions in `tests/unit/test_gold_kuiji_testsplit.py`. Do not open them while developing a parser or outliner evaluated on those spans (`data/EVAL-SETS.md`, "Do not open while developing"). Who reviews them, and when, is not yet decided.

## Review status: DRAFT, NOT REVIEWED

- `gold_status: draft-unreviewed`, `seeded_by: "claude-opus-5-5 (SDD draft 2026-09-22)"`.
- **A person must review `outline.txt` line by line before any headline score is reported against this gold.** A gold drafted by a model and then corrected by a person is biased toward that model (R06 F19). Any score a Claude-based outliner gets on this gold must say that Claude seeded it, even after review.
- What review means: for every node, check (1) the heading against the commentary line shown in the JSON `evidence`; (2) the parent-child structure against Kuiji's announcement (「有N：初…後…」); (3) the root-text span. The spans marked `basis: manual` in the 陀羅尼品 subtree are the drafter's reading of the sūtra, since Kuiji lists those sub-items without quoting a lemma. Each carries a note with the cut words. After review, set `gold_status: reviewed` in the header, keep `seeded_by`, and recompile.
- In the 序品 subtree (a **test-split** answer key, outline levels 3–5: three below the 品 node), check first:
  - **the 品文 level.** The node 七種成就 (「論說〈序品〉有七種成就」, T34n1723_p0661c09) has the seven 成就 of the 法華論 as children, because Kuiji takes the text up by them (「七成就中，自下第二眾成就也」 p0666a15–a16 … 「下第七文殊師利答成就」 p0688a21). Kuiji also groups them 「七中分二，初二通序，後五別序」 (c25–c26); that grouping is only a note. The alternative is a 品文 node 七中分二 (`@n` 2) with the seven at level 3, which would push every 成就's own division below the depth limit. The heading is the shortest phrase with the count (七種成就); 序品有七種成就 is the longer option;
  - **一序分成就 and its four children**, taken from the 通序 list 「通序有五：一總顯已聞，二說教時，三說教主，四所化處，五所被機，此入眾成，序成但四」 (c26–c28). The fifth item is 眾成就. The 論 itself names only two, 城 and 山 (c29–p0662a01);
  - **眾成就's shape**: a gate node 以五門解釋 (p0666a16) and a text node 眾成中有二段 (「然經明眾成中有二段」, p0667a22, which Kuiji states inside the fifth gate) as siblings, both leaves at the depth limit. 「初眾分四：一聲聞眾，二菩薩眾，三八部眾，四諸王眾」 (p0666c16–c17), which R03 F23 cites as Kuiji's 眾 division, is here the content of gate 四明次第 (the order of the fifteen 眾), not a division of the text. The text division is binary (內護眾／外護眾 …, p0667a24–a29);
  - **the heading 後慈氏雙申兩意發問先因** (p0683a07–a08). It was changed after review (2026-09-22) from 後慈氏雙申兩意, CBETA's punctuation, which puts a 。 after 兩意. The take-up calls the part 「雙申兩意發問先因」 (p0683c09–c10) and its prose halves 雙申兩意 / 發問先因 (c11, c12), and the three names are parallel. Confirm the reading;
  - **`@exp` where Kuiji gives no 此初**: 初彌勒示相懷疑 at p0683a15 (「初中有四」, after the three names are glossed at a08–a15); 一依三昧成就 at p0679a03 (the listing inside its lemma's treatment); 一序分成就 and 一總顯已聞 at p0661c28 (「序成但四，「如是我聞」即為初也」);
  - **the four `@cut` starts** (three lemma variants; 五依止說因成就 and 一放光 share the first) where Kuiji's lemma differs from T09n0262: 白豪 for 白毫 (p0680b11; T09n0262's apparatus gives 毫＝豪【博】), 照於東方 for 照東方 (p0680c23), 充足求佛道 for 充足求道者 (p0694b04). No variant is recorded in T09n0262 for the last two;
  - **what counts as a division in the six gates**: gate 一's 五義 are nodes, each 「…中有二」 (like 來意有二). Gate 二's 四宗 / 教三 / 宗八, gate 三's two unnumbered topics (經題 p0657c03, 品名 p0658c15) and gate 四's 「理有八違」 are kept as notes;
  - **the 15 `truncated` nodes at level 5**, whose notes name what is left out. 14 of them keep an announced count (`count_mismatch`). 一總顯已聞 has no `@n`, because what lies below it is the gate formula 「以三門分別」 (p0662a04).
- In the 譬喻品 opening (a **test-split** answer key), check first:
  - the end of 初鶖子聞法領喜述成得記, T09n0262_p0012b01 (`end_basis: manual`). The covered commentary does not fix it; the note gives the reading and the alternative (p0012a06);
  - the six ends fixed by stanza counts (`end_basis: extent-formula`). The compiler does not count stanzas; the drafter counted them by script (51 verse lines = 25½ 頌 = 2½ + 23; 23 = 2½ + 5½ + 14 + 1; 5½ = 3½ + 2; 3½ = 2 + 1½; 2 = 1 + 1);
  - what is and is not a node: the two items of 來意有二 and the three numbered 釋妨 questions are commentary-internal nodes; the 法華論 apparatus (七喻 / 三平等 / 十無上 per 品), 又由三義, the three kinds of 菩提心 and 《瑜伽》's six phrases are kept as notes (content lists, not divisions);
  - the headings 一鶖子上根聞法說而已悟 and 二論云: Kuiji gives these two items no label, so each heading is the item's opening words.

## Who, how, when

- Drafted 2026-09-22 by Claude (claude-opus-5-5) as Task 4 of the plan that built the evaluation sets (a development document, not part of this repository; its rules are in `data/EVAL-SETS.md`, "Rules for gold data"). The 28 品 lines were generated with a short script that paired T34n1723's `cb:mulu type="品"` entries with T09n0262's, in order. The 陀羅尼品 subtree was written by hand from the `chinese_workflow.ingest.lines` output of the two XML files.
- The 譬喻品 opening subtree was added on 2026-09-22 by Claude (claude-opus-5-5) as Task 5 of the same plan. It was written by hand from `ingest.lines` output of T34n1723_p0734b07–p0737b08 and T09n0262 譬喻品. At the time it was seeded by §1 of a hand alignment of this passage with its Tibetan translation, made in research thread R03 (not part of this repository). Every quotation there was re-checked against the XML; the discrepancies are recorded as comments in `outline.txt`. No T34n1723 line after p0737b08 was read (reserve split).
- The 序品 subtree (outline levels 3–5, three below the 品 node) was added on 2026-09-22 by Claude (claude-opus-5-5) as Task 6 of the same plan. It was written by hand from `ingest.lines` output of T34n1723_p0651a01–p0694b22 and T09n0262 序品. It is not seeded by any fixture. R03 F1, F4, F22 and F23 were used for orientation and every quotation was re-read in the XML. No T34n1723 line outside that span was read, except the 陀羅尼品 and 譬喻品 lines already in this gold.
- Every heading is copied from `ingest.lines` output. The compiler (`chinese_workflow.eval.gold.authored`) checks each one against the XML and rejects the file if a check fails:
  - explicit headings must occur within ±2 lines of the node's commentary line, punctuation ignored;
  - quoted lemmas (經「…」) must occur in the commentary, near the node's own line or near its `@lemsrc`, and resolve to the stated T09n0262 span;
  - the annotator's cut words must start on the span's first line;
  - consecutive divisions must tile the sūtra text;
  - 品 spans must match T09n0262's own 品 markup.
- Evidence for each explicit node: the JSON `evidence` field quotes the T34n1723 line(s) on which the heading was found.

## Editions

| File | Release | sha256 (`scripts/CHECKSUMS`) |
|---|---|---|
| `data/raw/cbeta/T34n1723.xml` (妙法蓮華經玄贊, 唐 窺基撰) | CBETA xml-p5 tag `2026R2`, fetched 2026-09-21 | `8f73a6fbf18f31485dd7890ca064a5d45fa37d0f7caca10308c1762da94802ce` |
| `data/raw/cbeta/T09n0262.xml` (妙法蓮華經, 鳩摩羅什譯) | CBETA xml-p5 tag `2026R2`, fetched 2026-09-21 | `c8975bef9da3bbe0faec9d47ab3f2efb8147fb530d5c17f130045a336c5df017` |

Lineheads are stable only together with the release (R02 F13). The raw files are gitignored; fetch them with `scripts/fetch_cbeta.sh`. `metadata.source_document.notes` repeats both digests.

## Scheme choice (R03 F22)

Kuiji gives two whole-sūtra divisions, introduced with 「今為二解」 (T34n1723_p0661b10). This gold follows the **first**:

| Level 1 | Kuiji's wording | 品 | T09n0262 span |
|---|---|---|---|
| 序分 | 「初一品名序分」 (p0661b10) | 序品 (ch. 1) | p0001c18–p0005b23 |
| 正宗 | 「次八品名正宗，正說一乘授三根記」 (p0661b11) | 方便品–授學無學人記品 (ch. 2–9) | p0005b24–p0030b27 |
| 流通 | 「餘十九品總名流通，讚證受命付令行故」 (p0661b26–b27) | 法師品–普賢菩薩勸發品 (ch. 10–28) | p0030b28–p0062a29 |

Why the first scheme:
- Kuiji ranks it higher: 「故知八品正宗為勝」 (T34n1723_p0816a15). He also treats 壽量品 as 流通 (p0828c14–21).
- 慧沼 adopts it: 「雖有二釋，意取初釋」 (T1724 0863b19–21).
- This is the recommendation of R03 F22 and F24. Those rows are PARTIAL on what the texts say, and the recommendation is ours.

The headings are written as Kuiji writes them: 序分, 正宗, 流通. They are not normalised to 正宗分 or 流通分.

Not encoded as nodes; recorded as a comment block in `outline.txt`:
- The **second scheme** (「或」, p0661b27–c08). 序分 stays as in the first scheme. 正宗 becomes ch. 2–20, in three groups:
  - 12 品 明一乘境;
  - 2 品 明一乘行;
  - 5 品 說一乘果.

  流通 becomes 「〈神力品〉下」, ch. 21–28. This division coincides with 淨法師's 1/19/8, which Kuiji quotes at p0661b08–09. Encoding it would need a second scheme_id that re-parents ch. 10–20.
- The **8½-品 sub-variant** 「或并〈法師品〉半八品半為正宗」 (p0661b21–b22).

This gold differs from the sdp/Zhiyi gold (`zhiyi-wenju-sdp`) at level 1 for ch. 10–20. R03 F23 lists the other expected differences.

## What is covered (metadata `coverage`)

- **Level 1**: complete (3 nodes, above).
- **Level 2**: complete. It holds the 28 品. Each heading is T34n1723's `cb:mulu type="品"` label, for example 持品, 壽量品, 從地涌出品, 觀世音普門品. Where the label differs from T09n0262's 品 title, a note gives the T09n0262 title. Each commentary position (`explained`) is the line of that `cb:mulu`. Each span runs from T09n0262's 品 `cb:mulu` line to the last line inside that 品's `pin` div; juan titles and T09n0262's 附文 (p0198a10–b11) fall outside every span.
- **陀羅尼品**: full depth. It holds every division Kuiji announces in T34n1723_p0850a19–p0850b19 (the dev split, `data/EVAL-SETS.md` rule 5):
  - the gate node 三門分別 with its gates (一來意, 二釋名, 三解妨), `commentary-internal`;
  - the node 品文分三 (Kuiji's division of the chapter text, T34n1723_p0850a29; `@n` 3, span T09n0262_p0058b09–p0059b27) with the three parts as its children, per the Kuiji 品文 convention (decided 2026-09-22; `outline.txt` header comment and the gold README);
  - the five dhāraṇī sections, grouped in three classes (「有五，合為三類：初二聖，次二天，後十神」);
  - every sub-item Kuiji lists.

  That is 45 nodes: 4 commentary-internal, 11 with `basis: lemma` (the 7 lemmas Kuiji quotes, 經「…」 at p0850a29, b03, b06, b08, b12, b14 and b18; a class node shares its first member's lemma and ends by `end_basis: next-node`, the 品文分三 node by `end_basis: chapter`), 29 with `basis: manual` (sub-items listed without a lemma), and the 品 node (`basis: chapter`).
- **譬喻品 opening**: full depth over every division Kuiji takes up in T34n1723_p0734b07 up to, not including, p0737b04 (the test split, `data/EVAL-SETS.md` rule 5). That is 36 nodes:
  - the gate node 三門分別 (Kuiji's variant 「一敘來意，二解品名，三釋妨難」, R03 F25) with its three gates, the two items of 來意有二 and the three numbered 釋妨 questions: 9 nodes, `commentary-internal`;
  - the node 大文分二 (「就此品中大文分二」, p0735b21–b22; `@n` 2, span T09n0262_p0010b29–p0016b06) and, under its first part 初鶖子聞法領喜述成得記, the part 第二鶖子聞法領解 (prose, 4 lemma divisions with their sub-items; verse, 25½ stanzas down to 初一頌具相降魔德): 27 nodes, all `basis: lemma`. The 13 leaves are Kuiji's 13 lemma blocks (R03 F15) and tile T09n0262_p0010b29–p0010c27.

  Divisions announced in the span but taken up after p0737b04 are not nodes: 後佛廣以譬喻化彼中根, 次十四頌喜今聞而惱盡, 後一頌知佛子而道成, 後之二頌明自興嗟, 後一頌半名利高廣德, 後一頌好滿不共德. Six nodes whose parts run past p0737b04 carry flag `truncated`; five of them also carry `count_mismatch`, since they keep the count Kuiji announces. Nine nodes carry `@lemsrc`, because Kuiji announces several levels between a quoted lemma and its 此初也 (gold README, Kuiji conventions).
- **序品**: outline levels 3–5 (three below the 品 node) over T34n1723_p0651a06 up to, not including, p0694b22 (the test split, `data/EVAL-SETS.md` rule 5). That is 38 nodes (2 + 13 + 23 at levels 3, 4 and 5):
  - the gate node 略以六門料簡 (p0651b01; R03 F1) with its six gates and gate 一's five 義: 12 nodes, `commentary-internal`;
  - the node 七種成就 (p0661c09; `@n` 7, span T09n0262_p0001c19–p0005b23) with the seven 成就 of the 法華論 and, under them, the parts Kuiji announces: 一序分成就 → the four 序成 items; 二眾成就 → the gate node 以五門解釋 (`commentary-internal`) and the text node 眾成中有二段; 四 → 三種軌儀; 五 → 放光 / 照境 / 所見; 六 → 文段有三; 七 → 大分為三. That is 26 nodes: 21 with `basis: lemma` (seven with `@lemsrc`; three of these point to p0651b01, where Kuiji quotes 如是我聞 before the gates), 4 with `basis: manual` (lemma variants) and the gate node.

  The whole-sūtra division in gate 六釋經之本文 (p0661b10) is level 1 of this outline and is not repeated. Level-5 nodes under which Kuiji divides further carry flag `truncated` (15 nodes, 14 of them with `count_mismatch`); each note names what is left out. Nothing is omitted by the span end, since the span ends at 方便品.
- **Every other 品**: level 2 only. Each of these 25 品 nodes carries flag `truncated`.
- **Where the gold stops, and what is scored** (decided 2026-09-22; the D15 addendum in `docs/chinese-workflow-mapping.md`).
  - Flag `truncated` = the gold does not encode all of this node's source children, because of the depth limit or the end of a covered span. There are 46 such nodes: 25 品 nodes, 15 in 序品 and 6 in the 譬喻品 opening.
  - No node carries `coarsened` (the commentary itself stops subdividing a long span). Before this decision the 21 subtree nodes carried `coarsened`; each was checked, and in each case Kuiji goes on dividing.
  - **Scope.** `metadata.coverage_spans` (below) alone decides what is scored. A predicted node is in scope iff its start locator (`commentary.explained`; in sūtra-mode root-text scoring, `root_text.start`) lies inside an entry's span and its level ≤ that entry's `max_level` (null = no limit). Only the start must lie in the span, not the whole span: 大文分二's root span runs to the end of 譬喻品, past its entry's `root_text` end, because an entry's `root_text` bounds the covered leaves.
  - In-scope predictions that match no gold node are FP, including under a `truncated` node. Out-of-scope predictions are neither TP nor FP.
  - **`truncated`.** A `truncated` node's encoded descendants are scored normally and its unencoded source children are not FN. In this gold the flag is informational, since the scope already excludes what it marks: the children of the 25 bare 品 are below level 2, those of the 序品 nodes below level 5, and those of the 譬喻品 nodes start after p0737b03.
  - **Tree edit distance:** prune the out-of-scope predicted subtrees.
- The coverage entries are machine-readable in `metadata.coverage_spans`, compiled from the header's `coverage_span` lines. Spans are inclusive lineheads, and the `root_text` span bounds the covered leaves. `max_level` is an absolute outline level; null means full depth.

  | Subtree root | Commentary | Root text | Max level |
  |---|---|---|---|
  | document | T34n1723_p0651a01–p0854b24 | T09n0262_p0001c18–p0062a29 | 2 |
  | 序品 | T34n1723_p0651a06–p0694b21 | T09n0262_p0001c18–p0005b23 | 5 |
  | 譬喻品 | T34n1723_p0734b07–p0737b03 | T09n0262_p0010b28–p0010c27 | full |
  | 陀羅尼品 | T34n1723_p0850a19–p0850b19 | T09n0262_p0058b08–p0059b27 | full |

## Licence

CC BY-NC-SA 4.0 (`licence.id: CC-BY-NC-SA-4.0`; `licence.holder`: CBETA Foundation (財團法人佛教電子佛典基金會), which per the notice took over CBETA (中華電子佛典協會) and its rights on 2023-08-07), with CBETA's notice and release label `2026R2`. See `data/reference-outlines/NOTICE`, which reproduces CBETA's 版權宣告 verbatim from `data/raw/cbeta/LICENCE-NOTICE.txt`.

The data is CBETA-derived: every heading is CBETA text and every location a CBETA linehead (`data/EVAL-SETS.md` rule 2). CBETA's copyright notice (https://cbeta.org/copyright) releases its materials under CC BY-NC-SA 4.0 except where it says otherwise, and asks that redistributed or re-processed material carry the notice and the version information; every CBETA XML header adds "Available for non-commercial use when distributed with this header intact." This gold is for non-commercial use only and is never relicensed permissively. `eval_only: false`, because the licence permits redistribution.

Which split each part belongs to is fixed by rule 5 of `data/EVAL-SETS.md`, independent of the licence (`metadata.split_notes` says so in the JSON; do not use this outline as prompt or training material for a system evaluated on those spans):
- 陀羅尼品 is dev;
- 序品 (outline levels 3–5, the split table's "levels 1–3 below the 品 node") and the 譬喻品 opening are test;
- the rest of T1723 is reserve.

Not settled: whether CBETA regards an outline table of headings and lineheads as 改作 (adaptation), which its notice places outside the CC licence and for which it asks users to contact the rights holders.
