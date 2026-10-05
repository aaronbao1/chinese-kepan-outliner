# E00 — kēpàn coverage census over CBETA T (大正藏) and X (卍新纂續藏)

> **Note (2026-10-05, clean copy):** this record is kept as written; its references to planning notes, research threads (R-codes), NEXT_STEPS and the freeze tags point to the development repository and are not part of this copy.

**Date:** 2026-09-22 (labelled 2026-09-21 pass 2 in `context/research/R01-*`)  **Owner:** Aaron  **Status:** done

## Hypothesis

Written before running (R01 F4/F7, H4, H2; NEXT_STEPS §1 R01):

H-E00a (H4 quantifier). Fewer than one in four of the Taishō root-text numbers T0001–T1692 (sūtras T0001–1420, vinaya T1421–1504, Indian śāstras T1505–1692) belong to a CBETA 部類 cluster that holds at least one Chinese commentary of the kēpàn-bearing genre (title class 疏／文句／玄贊／科, rule below), in T or X together; coverage is concentrated so that the ten best-covered clusters hold more than half of all such commentaries.

H-E00b (H2 quantifier). Among the 111 經疏部 works whose juan 1 announces a level-1 division of the root text with an explicit count, the count 3 is the mode but at least one in five announce a count other than 3, or announce none in juan 1.

H-E00c (R04 F37 follow-up). Fewer than 10 of the 158 T 經疏部／律疏部／論疏部 works have a CBETA `works/toc` outline deeper than 2 levels (i.e. anything beyond 卷／品 plus per-juan markers).

Falsified if: (a) ≥ 25 % of T0001–T1692 numbers sit in a commented cluster; (b) 3 is not the mode, or ≥ 80 % of announcing works announce exactly 3 and the rest none; (c) ≥ 10 works have `works/toc` depth ≥ 3.

## Why it matters / what decision it informs

H4 fixes the commentary-driven vs text-driven weighting of `pipeline/outline` (R01 brief, "Decision this unblocks"): if only a minority of root texts have a kēpàn-genre commentary, the text-driven resolver is the main path by count and the commentary parser serves an important minority. H2 fixes whether level 1 of the outline can be a hard prior of ≤ 3 nodes in Project Instructions. The `works/toc` count tells R02/R04 whether CBETA's own 目次 can seed gold outlines for any of the commentaries themselves.

## Method

Inputs (all public CBETA/DILA API data, fetched 2026-09-22 with 0.4 s pacing, cached verbatim under `out/api/` so every table can be rebuilt offline; `out/` is gitignored):

1. `https://cbdata.dila.edu.tw/stable/download/all-works.json` — every CBETA work id + title + juan list (5,748 works).
2. `https://cbdata.dila.edu.tw/stable/catalog_entry?q=orig-T` and `q=orig-X`, crawled recursively — the 底本 (Taishō / 卍續藏) 部 of every T and X work (`orig-T.035` = 經疏部一 … `orig-T.047` = 論疏部五; `orig-X.002` = 大小乘釋經部 …).
3. `https://cbdata.dila.edu.tw/stable/catalog_entry?q=CBETA` crawled recursively over the 23 CBETA 部類 — CBETA's own grouping of root texts with their commentaries into cluster nodes whose labels read `<root T-range> <name>／疏 <commentary volumes>` (e.g. `T0262-65 法華經／疏 T33-34, X27-35, …`). This is the grouping instrument; no title heuristics decide cluster membership.
4. `works?work=<id>` (byline, dynasty, `orig_category`, `category`, cjk_chars), `works/toc?work=<id>` (CBETA 目次 tree: node count, depth, level ≥ 2 node types) and `juans?work=<id>&juan=1` (first fascicle text) for each of the 158 T 經疏部 (111) + 律疏部 (12) + 論疏部 (35) works.
5. `search/title?q=` for 科, 科文, 科註, 科解, 科節, 科判 (percent-encoded; the bare-CJK URL returns "invalid URL"), and a local filter over (1) for T/X titles containing 科.
6. `search?q=序分|正宗分|流通分&rows=0` to re-check the three work counts cited in R01 S28.

Procedure:

- **Denominators.** From (2): number of T works whose 底本 部 lies in T0001–T1692 (阿含 … 論集), split sūtra / vinaya / śāstra; X0001–0207 印度撰述 listed separately.
- **Cluster table.** From (3): every 部類 node whose descendant works include at least one T work in 經疏部／律疏部／論疏部／諸宗部／續經疏部 or X work in 釋經部／釋律部／釋論部, or any other-canon work, together with root-text works (底本 部 in the Indian ranges above). Root texts and commentaries are told apart by 底本 部 from (2), never by title.
- **Genre classification rule (title-based, stated once, applied by code):**
  - class **疏** ("kēpàn-bearing genre" in the sense of R01 F12): title contains any of 疏, 文句, 玄贊, 科 (科文／科註／科解／科節 fall under 科);
  - class **注／註**: title contains 注 or 註 and none of the class-疏 markers (a title with both, e.g. 科註, is class 疏);
  - class **other**: anything else (義記, 述記, 贊述, 玄義, 宗要, 遊意, 鈔, 記, 解, 論, 講義, 頌, 集 …). Class *other* contains works that do carry a kēpàn (T1764 義記 has a five-part level 1, R01 F2), so "root texts with ≥ 1 class-疏 commentary" is a **lower bound** on kēpàn coverage and "≥ 1 non-注 commentary" the upper bound; both are reported.
- **Level-1 announcement grep** (H-E00b) over the plain text of juan 1 of each 經疏部 work (HTML from `juans` stripped of line-head spans, note anchors and footnotes): pattern family A `(此經|一經|經文|一部|此論|大文|就文|正文|經)[^。；：]{0,6}(大分為|分為|開為|判為|略為|略分為|分作|開作|別有|總有|凡有|略有|具有|有|分|開|判)N(分|段|門|科|章|節|周|意)`, family B `(大分為|大分|總分為|大科分|大判|文別有|總有|凡有)N(分|段|門|科|章|節)?`, family C tripartite vocabulary (序分 ∧ (正宗分|正說分|正宗|正說) ∧ 流通分, or 序正流通), with N ∈ 一…十. Every match is written with 30 characters of context to `out/level1_matches.tsv`; the announced level-1 count per work is the N of the first A/B match, **then adjudicated by hand** against the context (玄義-preamble gate counts such as 十門 are not level-1 divisions of the root text) with every override recorded in `level1_adjudication.tsv`. A work whose juan 1 has no match is "none in juan 1", which is not "no division" (T1735's 別解文義 begins in juan 4).
- **`works/toc`**: node count, max depth, multiset of `type` values at depth ≥ 2, per work; report works with depth ≥ 3 and what their level-2+ types are (API side; R02 does the XML `cb:mulu` side).
- **X0231 leaf classification and X0584 depth** (R01 F6; separate script `x0231_leaves.py`, local XML only): X0231 `<list>/<item>` tree parsed with lxml; leaf = item without a child list; leaf text = item text minus nested lists, CJK only, leading ordinal (初／次／後／一…十／第N) stripped; a leaf is **sūtra-span** if its trailing 4-gram, else 3-gram, occurs in the running text of T0279 (body text with `note`/`rdg`/`cb:mulu` removed, `lem` kept, CJK only), searched monotonically from the previous sūtra-span leaf's position with global fallback; **commentary-internal** if instead found in T1735's running text; else **unresolved**. Sūtra-span leaf size = 。？！； marks in T0279 between consecutive sūtra-span anchors (same proxy as R04 F27/F33). X0584: lists, items, max nesting, leaf items recomputed by the same parser.

Metrics: counts and shares as defined above; no model, no scoring against gold.

Reproduce: `python3 census.py` (fetch + cache + tables), `python3 level1.py` (grep + distribution), `python3 x0231_leaves.py` (local XML). Python 3.9, stdlib + lxml + requests. Pinned inputs: CBETA API 4.6.7 / data 2026R2; local XML from `scripts/fetch_cbeta.sh` (tag 2026R2, see `scripts/CHECKSUMS`).

Two rule changes were made after the first run and are recorded here rather than hidden: (1) the cluster rule was changed from
"minimal qualifying node" to "deepest qualifying ancestor per commentary" because the former orphaned the 金剛經, 心經 and 起信論 疏
folders (their 部類 node has a deeper qualifying sibling); (2) other-canon works (F, L, P, J, K, G …) were dropped from the commentary
count because they are mostly other editions of the same texts. A label-parsing bug that mapped 律疏部 to 律部 (prefix match) was fixed;
vinaya figures before the fix counted T1804–1815 as root texts. (3) The X0231 leaf test as pre-registered (trailing 4-/3-gram of the
item text, single monotone search) was replaced once the XML had been read: the leaf incipit is the inline `<note>` (X0231) or the run
before 下 in the heading (X0584), and a single-pass monotone search collapsed after the first false two-character match (27 anchors,
10,477 "out of order"); the run uses a two-pass alignment (LIS skeleton over rare incipits, then interval-constrained search) and
re-links the ○-continued segments before measuring depth — see the docstring of `x0231_leaves.py`. The hypotheses were not changed.

## Result

| Hypothesis | Result | Verdict |
|---|---|---|
| H-E00a: < 25 % of T0001–T1692 root works have a class-疏 commentary; top-10 families > 50 % of commentaries | 148 / 1,757 = 8.4 % (any commentary 18.7 %; sūtra 6.1 %, vinaya 3.4 %, śāstra 28.9 %); top-10 families 58 % of 793 memberships | holds |
| H-E00b: among 經疏部 works announcing a level-1 count in juan 1, 3 is the mode but ≥ 1 in 5 announce ≠ 3 or none | 59 of 111 announce: 53 three-fold (90 %), 3 two-fold, 1 five-fold, 2 dual; 9 defer the division to a later fascicle; 43 none | mode holds; "≥ 1 in 5 ≠ 3" fails among announcers (10 %), holds only counting non-announcers |
| H-E00c: < 10 of the 158 T 疏部 works have `works/toc` depth ≥ 3 | 7 (39 have depth ≥ 2; 4 carry 序分／正宗分／流通分 as toc nodes) | holds |

Full tables in `SUMMARY.md` and `out/`.

## Interpretation

Kēpàn-genre commentaries exist for a small, sharply concentrated minority of root texts (by CBETA work id: 8.4 % overall, 6.1 % of
sūtras, 28.9 % of śāstras); the concentration is 法華, 金剛, 心經, 四分律, 楞嚴, 維摩, 梵網, 成唯識, 淨土 (阿彌陀／觀經／無量壽), 華嚴, 起信,
圓覺, 楞伽, 涅槃, 因明, 金光明, 仁王. Text-driven inference is therefore the main path by count and the commentary parser serves the
minority that matters most (R01 H4 → VERIFIED with this quantifier). Level 1 is a strong tripartite prior (90 % of announcing 經疏部
works) but not a fixed schema (R01 H2 stays PARTIAL, now quantified). CBETA's own 目次 encodes a kēpàn level 1 for only 4 of 158
commentaries, so gold outlines cannot be seeded from `works/toc` beyond those (feeds R02/R04). X0231/X0584 are deeper than the raw
XML suggested (36 / 41 levels after re-linking ○ segments) and their sūtra-anchored leaves are far below chunk size (median 2 sentence
marks), confirming that the chunking-skill must merge leaves upward (R01 H6). Next: E01 (explicit parse of T1718 juan 1–2 against a
hand gold) and E02 (model-only baseline); the ambiguous 2-character incipits argue for anchoring by lemma + position, not by string
search alone, in the resolver.
