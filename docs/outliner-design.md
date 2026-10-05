# Kēpàn outliner: module-level design

**Status.** This document describes the outliner as built: the version frozen for experiment E07 as `outliner-v1-frozen-2026-10-03` (`experiments/E07-capability-sweep-v1/README.md`). The tag is kept in the development repository; this copy's code is that version plus changes that leave outline output unchanged (a clearer error for a CBETA file that has not been fetched, packaging metadata, the quickstart script, the fetch script, tests and documentation). E07's finding 1 is not fixed: §5.2's partial-name rule for 「X」者 glosses mis-anchors two 序品 glosses. The defaults in §14 are design choices, not tuned values.

This document describes the kēpàn outliner down to modules, algorithms and file contracts. `docs/architecture.md` gives the stage boundaries and the data flow; `context/baseline/outline-schema-zh.json` (D15 in `docs/chinese-workflow-mapping.md`) fixes `outline.json`. This file says *how* each part works.

Vocabulary: `docs/glossary.md` (the Tibetan workflow's terms, and ours).

**References.** "Task N", "M1a", "M6", "Appendix H item 8b", "plan §5" and similar codes point to plans in the development repository, and "R0n Fnn" to its research notes; neither is part of this copy. "E06 review A1–C7" (and "tier C") are the directions in `experiments/E06-capability-sweep/REVIEW-2026-10-02.md` §2, and its Q codes the decisions in §3. D-codes are the divergences in `docs/chinese-workflow-mapping.md`.

**Replaceable parts.** The chapter-TOC baseline (tier 1), the formula parser (tier 2), the resolver and the scorer each sit behind a stable interface (`outline --source tier1|tier2|hybrid`, `eval.score`), so any one of them can be replaced without touching the rest.

## 1. Scope

In scope: the outliner pipeline and the artefacts the Tibetan workflow's outliner emits. The step numbers are those of that workflow (`docs/chinese-workflow-mapping.md`); they index its manuals, which are not included in this copy.

| Stage / part | Workflow step | Output | Section |
|---|---|---|---|
| `ingest` (M1a) | 1e1 | input-text + `structure.json` + normalization config | §4 |
| `outline` tier 1 (chapter TOC) | 1f Step 1 | explicit 卷/品/分/科判 nodes | §5.1 |
| `outline` tier 2 (formula parser) | 1f Step 1 | explicit nodes from division formulae | §5.2 |
| `outline` scheme prior | 1f Step 1 | level-1 parts declared by the project | §5.3 |
| `outline` merge, anchor | 1f Step 1 | independent outline + outlined-text | §5.4, §5.5 |
| `outline` resolver + gloss (model) | 1f Step 1 | inferred nodes, root spans, `heading_en` | §5.6 |
| `outline` render | 1f Step 1 (the workflow's Word outline) | `outline.md`, `outline.docx` | §5.7, "Output formats" |
| `segment` | 1f Step 2 | `sentences.json` | §6 |
| `chunk` | 1f Step 3 / 3a | interlinear outline: `chunks.md`, `chunks.json`, `chunks.docx` | §7, "Output formats" |
| `export` (M9 v0) | knowledge graph (D20) | JSON-LD per (work, scheme) | §8 |
| `eval` scorer + chunk invariants | ours (D12) | `metrics.json` | §9 |
| `llm` client | — | cached, replayable model calls | §10 |
| `runner` + `projects/<id>/project.toml` | — | one run directory | §11 |
| skill `chinese-kepan-outliner` v1 | `outliner-skill` | procedure for Claude Code | §12 |
| experiment E01 | ours | pre-registered, dev/validation read-out | §13 |

Out of scope here: the `context` and `translate` stages, stitching, the Taishō apparatus side-table (M1b), and any test-split score (a test span is scored once, with a frozen outliner).

## 2. Principles carried into the code

1. **Stages talk through files.** Each stage has `run(...)` and a CLI (`python -m chinese_workflow.<stage> …`). A stage imports only `chinese_workflow.common`, `chinese_workflow.llm` and `chinese_workflow.ingest` library functions; `eval` may import `outline` data helpers only through files. An AST test enforces this (plan Appendix C rule 4).
2. **`outline.json` is the one outline contract** (zh-kepan, D15), validated by `scripts/validate_outline.py`, its single owner. A prediction sets `gold_status: prediction`, `seeded_by: null`, `eval_only: false` unless its inputs force true, and `generated_by` = source + pipeline commit.
3. **Explicit nodes are immutable.** Tier 1, tier 2 and the scheme prior produce `origin: explicit` nodes (the scheme prior produces `editorial`, §5.3). The resolver may add `inferred` children and fill spans marked `basis: inferred`, never change an explicit node's heading, parent, order or `commentary` locators. A merge unit test checks it (plan gate: 0 explicit nodes modified). The repair step of §5.0 may null an explicit node's out-of-order locator (`commentary.explained` in self-outlining mode, a `root_text` span), raise an explicit parent's `root_text.end` to its last child's and clip an explicit child's span into its parent's, but its first pass runs before the resolver's snapshot of the explicit nodes and keeps the old value in the node's note, so the gate still holds across the resolver. Repair also runs once more after the resolver and the gloss when either ran (`outline.pipeline`): the resolver validates every change it makes (`resolver._Merger.apply`), so it hands back a document whose explicit nodes validate, and the pipeline asserts the explicit fingerprint after it (headings, levels, commentary locators; not `root_text`, which a repair may raise or clip).
4. **Split blindness is enforced by code** (§3): no stage reads a test or reserve span of T1718/T1723, or an OOD-test gold, unless `--frozen <tag>` names a frozen outliner.
5. **CBETA text is never altered.** Offsets index the reading text of `ingest.lines` (CBETA punctuation kept). Normalization, when a stage needs it (tier 2 matching ignores punctuation), is a function with a recorded config, never a rewritten file.
6. **Deterministic first, model where rules stop.** The pipeline runs end to end with no model (resolver adapter `none`): nodes it cannot place stay flagged (`unmapped`), never guessed silently.

## 3. Split guard (`common/splits.py`)

The registry `data/eval-sets.json` is the only split source. `SplitGuard(frozen: str | None)`:

- `check_span(file_id, start, end)` → the set of splits the inclusive line range touches, from the registry's split spans; for files the registry does not split, `{"unsplit"}`.
- Refuses (raises `SplitViolation`) a range that touches `test` or `reserve` (T1718/T1723 lines that no span holds are reserve, EVAL-SETS "Using these sets" item 1) unless `frozen` is set. `dev` and `validation` pass; `validation` is recorded so a read-out can say how often it was looked at.
- `check_gold(dataset_id)` refuses OOD golds (`split_scope.kind == "out-of-domain"`) as *inputs or prompt material* at any time, and as *scoring targets* unless frozen (every OOD gold is treated as an out-of-domain test set).
- Every check is appended to a report that the runner writes into `run.json` (`split_guard`).

Consequence: a run over the whole of T34n1723 needs `--frozen`; development runs pass `--span dev` (the runner turns it into the dev span of the commentary). Tier 1 reads only `cb:mulu`, `head` and `juan` markup of a whole file, which is structure, not commentary prose; the guard allows it through `check_structure(file_id)` and records it (the Kuiji gold's levels 1–2 are readable for the same reason, EVAL-SETS "Do not open").

## 4. `ingest` (M1a)

`ingest.run(xml_path, role, out_dir, span=None)` writes, for one CBETA file:

- `<id>.lines.jsonl`: the `ingest.lines` records (restricted to `span` when given), the canonical input;
- `<id>.txt`: the reading text, lines concatenated without separator (so offsets equal `TextIndex` offsets);
- `<id>.structure.json`: `{text_id, role, cbeta_release, punctuation, punctuation_resp, span, lines: [{linehead, start, length, juan}], elements: [{kind: juan|mulu|head|jhead|verse|note|caesura, linehead, offset, char_start, attrs}]}`, char offsets global to `<id>.txt`;
- `normalization.config.json`: `{regime: "none", punctuation: <declared>, gaiji_routes: {...counts}, notes_policy: "inline kept, others excluded (ingest.lines)"}`.

A `role` is `root` or `commentary`. `ingest` never writes normalized text; `ingest/lines.py` offers `strip_punct`, `TextIndex.stripped()` (a punctuation-free view with an offset map) and `find` / `find_spans(…, ignore_punct=True)` for matching.

## 5. `outline`

### 5.0 Document assembly (`common/outline_doc.py`)

Every outline source emits **draft nodes** (dicts with the node fields it knows plus `children`); `build_prediction(roots, meta)` numbers them in pre-order (ids `<k>_<level>` digits only, `path`, `parent_id`, `order`, `sibling_index`), fills `indicator_display` (`2₁1₂`: sibling index + subscript level per token), `display_label` (干支 of the level + Chinese ordinal, R07 F15; null past level 22), every zh node key the profile requires, and the zh metadata. `validate(doc)` runs the validator in process.

**Degradation (`outline/repair.py`, E06 review B5).** The build validates the numbered document after the root spans, before the resolver, and once more after the resolver and gloss when they ran. Three codes are *local* — their cause is one node or one sibling group — and are repaired rather than failed, each as the explicit sources already treat the case: `[sibling-order]` keeps, per sibling group, the non-decreasing chain of the locator with the most explicit (non-inferred) nodes, so an inferred node never displaces an explicit one (ties: the chain whose explicit nodes come earlier in document order, so an inferred sibling never decides which of two explicit ones stays; then the chain with more inferred nodes), and demotes the others as tier 2's `_self_mode_order` demotes an item taken up out of order (`commentary.explained → null`; `root_text → start/end null`, raw kept, flag `unmapped`), with a note `demoted: sibling-order, was <ref>`; `[child-outside-parent]` clips an inferred child's span to its parent's, or raises an explicit parent's end (and each shorter ancestor's) to its child's as tier 1 raises a unit's end to its last descendant's; an explicit child that starts before its parent has its start clipped to the parent's, except under an inferred parent, whose start is lowered to the child's instead; a span that would invert is nulled; `[cbeta-order]` nulls the inverted span. `outline-report.json` lists each pass under `degraded` (`stage`, the first-pass `errors`, the `repairs`); the key is absent when nothing was repaired, which is the case for the two E06 dev builds and the offline fixtures. Schema errors, `[not-preorder]`, `[sibling-index]` and the rest remain hard failures, as does a local error that does not settle in three rounds: the build skips the resolver and gloss (a hybrid build's `resolver.status` reads `skipped: input fails validation after repair`, since the resolver validates its input), writes every artefact and `outline-report.json`, and then raises `OutlineValidationError`. Exit codes: `outline build` 0 with a `degraded` count, 1 only when errors remain; the runner likewise.

### 5.1 Tier 1: the chapter table of contents (`outline/tier1.py`)

Input: the `ingest.lines` records of one file (structure only). Output: draft nodes from `cb:mulu`:

- Nesting by `level` (the 卷 system, `level: None`, is separate: 卷 are not outline nodes but are recorded in `metadata.juan` for the renderer).
- `@type` verbatim in `part_type`; `heading_src` = the mulu text; `commentary.explained` (sūtra mode, file = commentary) or `root_text.start` (self-outlining) = the mulu's line.
- T1723's untyped level-2 mulu entries are per-卷 continuation markers (R02 F27): dropped as nodes, kept in `metadata.anomalies`.
- 科判-typed mulu (X0268, P1573, D8842, G069n1977) make tier 1 a full kēpàn (self-outlining); OOD golds are refused as inputs by the guard, so the path is tested on G069n1977.
- In sūtra mode the root text's tier 1 gives the 品 table `{name → (start, end)}` (T0262: 28 品 + 3 序 + 附文, R02 F20); commentary 品 nodes are matched to root 品 by name (strip 〈〉, 品第N, 妙法蓮華經; exact, then longest common substring ≥ 2) and get `root_text {start, end, basis: "chapter"}`.
- A span build whose first line lies inside a 品 (or other typed unit) whose `cb:mulu` is before the span carries that unit as an **editorial** ancestor (`origin: editorial`, note `pin carried from <linehead>`, anchored on the span's first line so tier-2 drafts attach under it; `align_pins` gives it the root chapter like any 品; report `tier1.carried`). Without it a span build has no 品 pin and the resolver's admissible ranges become the whole sūtra (E06 `tier1-T1718-validation`: 0 drafts, 16 skipped).

`outline --source tier1` alone is the "chapter floor" baseline of E01.

### 5.2 Tier 2: the stateful formula parser (`outline/tier2/`)

Input: the commentary's lines (a span or the whole file, guard permitting) and the tier-1 nodes that fall in it. Output: explicit draft nodes attached under the tier-1 (and scheme-prior) nodes.

**Scanner.** The span's reading text is cut into *clauses* at 。；？！ and at `：` when it follows a count (有三：). Each clause keeps its global offsets, its first and last linehead. Inline notes stay in the text (they carry chart counts, R01 F3).

**Detectors** (regular expressions over a punctuation-stripped view with an offset map, R01 formula table + Kuiji variants of R07 F17 / R03 F25; the inventory lives in `tier2/formulae.py` and is mirrored for humans in `skills/chinese-kepan-outliner/references/formula-table.md`):

| Kind | Examples | Effect |
|---|---|---|
| `lemma` | 經「A至B」。贊曰： · 「A」下 · 從「A」下至「B」 · 從「A」去、至「B」 | opens a *treatment unit*; the lemma (A, B) is kept for anchoring |
| `announce` | X有N：… · 分N · 分為N · 文為N · 大分為N · 文有N分 · 總有N分 · 說有N分 · N門分別：… · 凡有N段 · X中有N · 初中亦N · 有N，合為M類：… | announces N children of a target node, with labels when listed |
| `enter` | 此初 · 今初 · 此初也 · 此初X · 初X者 · 第N(X) · N、X者 · 次X · 後X · 下明X · 下X · 品第N段X · 已說X分。次說Y分 · X論者，謂如有一 (self-outlining) · N、就X(位)?中(即有其M) · N、從A下至B已來，Y (善導) · 「X」者 / 「X」，… (Zhiyi, T1718) | moves the cursor to a node, creating it if the text takes up an unannounced child |
| `gate` | 三門分別：一來意，二釋名，三解妨 · N門料簡 | a commentary-internal division (node_class `commentary-internal`) |
| `uddana` | 嗢拕南曰 | self-outlining root-text mode; the count announced before the head (何等N) separates items from a closing phrase |

**Weak `X者` markers and the function-word exclusion** (Task 6, 2026-10-02). `X者，` (an optional lead 所言 / 言 / 其 / 又 / 次 / 今, then X of one to eight characters) is a weak `enter`, resolved against labels only. When X opens with a function word (`FUNCTION_HEAD`: 雖 若 如 故 則 而 但 且 乃 即 亦 皆 既 由 因 以 為 其 之 所 於 此 彼 是 有 無 不) the clause is a conditional or a connective, not the name of a part (若無常者, 若即於蘊施設我者 of T1602), and it yields no enter; the lead is not X, so 其來意者 still enters. `初、X者` is ordinal 1 only with the separator behind 初 (初、解化前序者 of T1753): 初若無常者 is read by the weak `X者` rule above, never as an ordinal-1 enter that would bypass the exclusion.

**Target resolution** (which node an announcement divides): the subject decides — 答中 / 問中 → the child whose label contains 答 / 問; 初中 / 初文 / 中初文 → first child (of the cursor, or of the last announced division when the cursor has none); 後中 → last child; N中 → child N; 品文 / 此品 / 文 at 品 level → the 品 node; bare 有N / 分N right after a lemma or enter marker → the cursor. 又就前X中 / 就前X中 / 就上X中 (X one or two characters) → a **re-division** of the item whose label contains X (containment, not `sim()`: 序 ⊂ 明其序分): candidates are the items of the nearest scope level that has any; 前X takes the earliest announced among them and the same-headed items of outer levels (善導 T37n1753_p0251c25 has 明其序分 twice in scope and means the 王宮會's, announced first), 上X the one named last; the items become the item's own children and its `explained` moves to the re-division line. A lone part-word core (文 / 分 / 段 / 科, with or without 之: 又就前分中) is no re-division target: it falls to the later rules and heads a node of its own subject, while 就前文分中 and 就前序中 still divide. When the core is contained in several headings in scope (序 in 明其序分 and in 明正宗序分), the 前 / 上 choice above still divides one of them and the parse reports `ambiguous-target` for the announcement (Task 7, 2026-10-03). 就此X中 is anaphoric (the cursor), never a name. An announcement whose target is a tier-1 node (品, 卷) creates a **wrapper node** headed by the announcing phrase (三門分別, 品文分三): a 品 carries a gate and a text division side by side (the Kuiji gold's convention for the dev 品).

**善導's three idioms** (T37n1753, E06 review B3; slugs `jiu-x-zhong`, `cong-xia-zhi-lai`, `ming-x-jing` in the cases README). `N、就X中(，亦先舉，次辨，後結。)(即有其M)` is a strong `enter` (`jiu_zhong`): X is a listed item in scope, else child N of the nearest division whose child N is not taken up and shares X's characters in order (禁父緣 in 正明發起序禁父之緣), else the next sibling of the last 就X中 node (初日觀, 水觀, …), else a new node under the home; M is X's child count and `有其M` is read as X's announcement (an X headed by 此 / 前 / 上來 / 上文, or by 上 followed by one or two characters, none of them 品 or 輩 (`上[^品輩]{1,2}`), is an anaphor or a re-division and keeps the announcement path: 就上序中即有其二 re-divides 明其序分, while 上品 / 上輩 and 上品中生 are names and enter). `N、從A下，至B已來，Y` is an `ord_lemma` enter with an unbracketed lemma A至B (A alone when no end is given) that the anchor splits at 至; the item is child N of the nearest division whose items are such spans. A and B are bare words (a quotation or title mark, 「」『』〈〉《》, makes it no span item), A has two characters at least, and a 至 after 下 must open a whole 至B已來 / 至B已下 (T1753 p0265b28). The enter is **strong** when A is an incipit (`labels._incipit`) or the item states its end (至B已來); otherwise it is **weak** (二、從此無間已下，明四正斷 of T42n1828, the weak numbered item it was before Task 8): still placed where a division waits for a span item (31 of T1753's 246 span items, 三、從是為下，總結 among them), and when nothing takes it, neither an `unmatched-enter` nor a `lost` state (T1753: 8 → 7 unresolved). `(上來雖有N句不同，)廣明X竟` closes X (the cursor goes to X's parent; the verb needs the 廣 / 總 / 略 prefix or the recap lead, and 辨 / 辯 only after the prefix: a bare 解所緣竟 or 辨色聚訖 is prose, 357 sentence starts over CBETA against 128 now, 39 of them in T1753); `廣料簡X竟` ends the sorting of X before its items are treated: counted when X names a node in the cursor chain, the cursor goes to X (not to its parent: popping loses X's items, T1753 288 enters → 219; a 料簡 close that finds X only by label outside the chain is not counted, where a 廣明X竟 is and pops to X's parent); a 廣X竟 that names no node (8 of the 38 in T1753) is reported `unmatched-close` and not counted. A `就X中` run takes no item past its division's announced count when the run is all the division holds (a division that holds other children before the run, a text's stub or T1753's 七門料簡 wrapper, is not guarded: without that narrowing the whole `anchors=[]` parse of T1753 cascades, enters 288 → 234, unresolved 7 → 56, closes 30 → 24, nodes 659 → 523). A gate wraps its items under the cursor whether or not the cursor is already divided. Residuals (not fixed): a span item that opens right after a verse closed `』」` with no 。 before the 」 is not read as a sentence start (水觀's item 3, 三、從瑠璃地上下; one after `。」` is, `_sentence_starts`); 三、就得益分中 and 五、就耆闍會中 (卷四) name 五門 items stated under 卷二's anchor and are reported `unmatched-enter`; 十四、就上輩觀行善文前總料簡 has no 中 and is no entry; the listed-only 一明… sub-items of every 有其N head get no span (`anchor.listed_only`); the 卷三 count 即有其十六 is still rejected (no listing, term subject), so the 觀 hang under the 卷 anchor; with no 卷 anchors, 卷三's run of 觀 lands under 卷一's 七門料簡 wrapper (announced 七, four 門 entered, 17 children in the end: six of the 觀 are appended there by the narrowing above), and the anchored build is unaffected; a division whose items mix 初、言X者 with 三、從A已下 spans (化前序) leaves the span items `unmatched-enter`.

**Labels** follow the label rule of `tests/fixtures/kepan-formulae/README.md` (split at ordinal words or 、; strip locators, pointer words, copulas, final 也). The children are created at announcement time with `commentary.announced` = the line of their label and `explained` = the same line (announced = explained allowed); an `enter` marker that later takes a child up moves its `explained` to the marker's line. An enter marker for a child index beyond the listed labels creates it (第二聖 under 二聖). A numeral in a label (二聖, 十神) sets a *count hint* that an explicit later announcement overrides.

**Quoted-lemma glosses (Zhiyi).** 「X」者 / 「X」，… / 「X」N句 at a sentence start (`lemma_zhe`, slug `lemma-zhe`) takes up the word X of the sūtra: the heading and `root_text.raw` are X. The scanner emits it in sūtra mode only, for X of 1–14 characters, not for X with a 、 and not for the comma form after a sentence citing with 云：「 (a 。 inside the quotation does not end that sentence: 論云：「甲。乙」。「X」，…), nor for any form at a ；-start whose sentence so far cites. The parser reads it, in order, as (1) a sub-gloss of the open gloss unit when X is part of that unit's word (釋「聞」者 under 我聞) or its 名也 after a 姓也 (「阿若」者 after 「憍陳如」，姓也); (2) an item named X of a division up the cursor chain (the listed 如是), or a child of a listed item that X partly names (王舍城 under 王城耆山, similarity 0.5), the walk stopping at the first complete division; (3) a new member of the nearest division still taking members (an open count 五或六或七, a count not reached, a division listed by a gloss run); (4) a sibling of the open gloss unit, or the first member of the node the text is in. ≥ 3 one-clause glosses (≤ 30 characters each before the next statement) right after a count-only or open-count announcement are its listing: listed-only items that the full treatments take up later. While a gloss unit is open, a weak marker that names a node already taken up is a mention, not a move (Zhiyi's 約教釋 restates the head word: 大者，… under 「大」者; 位大者 inside the 摩訶迦葉 gloss would otherwise match the label 位 of 三位 through `sim()`'s one-character rule and carry the cursor there; counted in `tier2.stats.weak_mentions`, 8 on the dev span). A second 「X」者 for an item already taken up (an entered item named X at similarity ≥ 0.9, an exact label for a one-character label; or, as 又「X」者, the open unit's word or a gloss beside it) is a mention too: no duplicate-headed member, no move, counted in `tier2.stats.gloss_repeats` (0 on the dev span). A bare 「X」者 repeating a gloss is another occurrence of the word in the sūtra and stays a node (T1705: 「何以故」者 twice under 標). Known limits, not changed: the gloss-run listing ignores an announced count, `_next_slot` needs all children `entered` (a `lemma_zhe` member under a count-only division blocks later 下明X slots), a mention or repeat leaves the cursor where it is, and a lone 「聞」者 after the 我聞 unit has closed can count as a repeat of the entered item 我聞 through `sim()`'s containment (auditable in `gloss_repeats`, 0 on every measured text). Not a unit: a gloss inside a 經「A至B」。贊曰 unit (Kuiji glosses a word of the lemma: counted in `tier2.stats.gloss_in_lemma_unit`, T1723 dev p0850b09; the unit needs the opener (`F.OPENERS`: 贊曰, 述曰, … and 頌曰, the opener of a verse section's head citation 經「A至B」。頌曰：): a 經「…」 in prose is a `sutra-cite` lemma statement that neither arms nor disarms the unit: before a unit it arms nothing, T1705 經「千」字者非 followed by the real take-up 「有十心」者; inside an armed unit it leaves it armed, a 如經「以要言之」等 in the body of T1700's 述曰 unit, p0142c15, must not turn the 「X」者 word glosses behind it into nodes, +4 on T1700 when it did), a title word (序 / 品 / 經 / 卷), a gloss before the first division (both reported as `lemma-gloss-at-stub`); the subject nodes of 釋同聞眾為三 stay under the division, because `_home` treats `lemma_zhe` nodes as transparent. Acceptance was outline shape on the T1718 dev span (E06 review B6: 27 take-ups, 9 nodes in 卷一下 from 0, largest leaf 12 % from 55 %), not the sdp dev score, which this device lowers in precision by construction. HYPOTHESIS tuned on T1718 dev with T33n1705 (outside every split) as the margin check.

**Filters.** *Doctrinal-list filter:* an announcement is a list, not a division, when its subject is a doctrinal term rather than a text unit — heuristics: classifier 種 / 義 / 類 / 門(outside N門分別) / 位 after N; subject not in {文, 品, 經, 此, 中, 初, 次, 後, 答, 問, a current label}; not adjacent to a lemma or enter marker; items are terms (≤ 4 characters, no verbs 明/說/標/歎/釋). Rejected announcements are reported with the reason (E01 reports doctrinal-list false positives separately). *Self-outlining take-up (E06 B7):* when the treatise then takes the listed items up in order (所言X者 / X者 / 云何修行X門？) the list-shape penalties are dropped; the window is 2,000 characters or the next close statement (已說X分, 上明X, X竟); a listing found from a count question that opens the next sentence (X有N種義，clause。云何為N？) gets the 云何為N？ bonus only on such a take-up. *Genre gate:* a work whose title marks it 註/注 (T1775) and whose announcement density is below a threshold yields no tier-2 nodes; 疏 / 記 / 贊 / 文句 / 義疏 / 玄贊 / 述記 / 鈔 / 論 pass. The decision and its evidence go to `metadata.genre_gate`. The evidence counts X曰： / X云： attributions (generic, not a glossator list); on no-structure the machine's rejections and gated statements are still reported (E06 B9, Task 12): accepted announcements as `gated-announcement`, strong entry markers as `gated-enter` and closing markers as `gated-close` in `parser_report` (counted in `tier2.stats` as `gated_announcements` / `gated_enters` / `gated_closes`), the rejected announcements in `rejected`; no node is built.

**Node classes.** Gates and their children are `commentary-internal`; everything under a lemma unit is `sutra-span`; announcement wrappers inherit from their children (a text division is `sutra-span`).

**Output fields.** `heading_src` is the source's wording of the item with its ordinal (初明持經之福, 第二聖), as the golds keep it (`data/EVAL-SETS.md` item 9); the label rule of the parser cases (ordinal stripped) is the alternative `heading_style = "label"`. `origin: explicit`, `confidence: 1.0`, `evidence` = `"<linehead>: <line text>"` of the announcement line(s) (the Kuiji gold's form), `child_count_announced` = N (after count hints are overridden), `extent_announced` = a stated extent (四行, 三頌), `commentary.raw` = the marker text, `root_text.raw` = the lemma as `A至B`.

**Honesty rule.** What the rules cannot decide (an announcement whose target is ambiguous, an enter marker that matches no child) is recorded in `metadata.parser_report` with its line, never silently attached. The resolver may pick these up.

### 5.3 Scheme prior (`outline/scheme.py`)

A sūtra's top level is the commentator's *scheme*, stated once (usually at the start of the commentary) and then presupposed. When the processed span does not contain that statement (a dev-span run), the project declares it: `project.toml` `[[scheme.level1]]` entries `{heading_src, from_pin, to_pin, source}` (e.g. Kuiji's first scheme: 序分 = 序品; 正宗 = 方便品–授學無學人記品; 流通 = 法師品–end; R03 F22). The prior builds level-1 nodes around the tier-1 品 nodes; `commentary.explained` = the explained line of its first 品 (the gold's convention), `root_text` = the union of its 品 spans. They carry `origin: editorial` and `evidence` = the config source, because this run did not read the statement. **v1 limitation (2026-09-27):** when tier 2 does read a whole-text statement (Zhiyi's 分文為三 with 品 ranges, Kuiji's opening division), it stays where it is read, as a wrapper under the 品 anchor that holds it, and the prior (if declared) still builds level 1. Promoting the statement to level 1 needs 品 ranges parsed out of the listing and a rule for parts that begin inside a 品 (Zhiyi's 正 ends at the 分別功德品 verses), and E01 showed it would not make Zhiyi's tree match sdp's (sdp drops the 品 level that the Kuiji gold keeps), so it waits for a gold that needs it. The design intent stays: explicit nodes win over the prior.

Level-1 prior for texts with no declared scheme: none. R01 F17 (PARTIAL: 53 of 59 three-fold) is a prior for the *resolver's prompt*, not a rule.

### 5.4 Merge (`outline/merge.py`)

Order of authority: tier 2 (inside a 品) > tier 1 > scheme prior. Tier-2 nodes of one 品 become descendants of that 品's tier-1 node. Merge never renumbers explicit content: sibling order = document order of `commentary.explained` (ties: announcement order). The merged tree is numbered and validated (§5.0).

### 5.5 Anchor (`outline/anchor.py`) → outlined-text

Two jobs, and a classification between the first and the resolver ((c)).

**(a) Root spans (sūtra mode).** For each `sutra-span` node, in pre-order, inside its parent's root span (monotone: a start never precedes an elder sibling's start; the cursor runs on across tier-1 roots, except past a summary (rule A). A subtree is a **summary** when (1) it covers more of its window than it leaves after it, measured from the subtree's own start to the window's end; (2) its starts run past every later lemma of the window (none has a whole A after the subtree's last start, headings left out); and (3) at least two later lemmas have a whole A after the restore point, just after the summary's start (one is not enough: a correct final subtree followed by one node that re-quotes an earlier lemma is no summary, and with a single lemma A clamped three nodes and failed validation). A summary does not move the cursor, so what follows is searched from the restore point, reported `summary-transparent`; this keeps 善導's 卷二 五門明義, whose items run over the whole 觀經, from hiding the 卷三 and 卷四 lemmas. Consequence, by construction: the summary's items past the restore point lie outside the span the tiling gives it (its end is the line before the next placed sibling), so its last items are clamped (`end-clamped`) and the validator reports child-outside-parent, which the before-resolver repair pass handles (guanjing: 8 errors, 17 repairs; with rule A off nothing is repaired and `lemma-not-found` is 159 of 208). Rule B — a start found after the cursor that would leave two or more younger siblings, each with a whole A after the cursor and neither a whole nor a gapped A after it, is rejected, reported `lemma-lookahead`, because a later hit of the same A leaves them still less; a sibling quoted loosely that a gapped match still finds is not stranded — gives up a generic lemma such as 佛告阿難 rather than the siblings after it):
1. a lemma A(至B) → the earliest punctuation-insensitive occurrence of A in the root text within the parent span, from the elder sibling's start (an exact-first search would skip 「爾時，藥王」 for a later 「爾時藥王」, because Kuiji quotes without CBETA's punctuation); then, each reported, a gapped match of A (first two characters adjacent, each later one within 6 of the last, 等 a wildcard — 善導's 阿難白佛 for 爾時阿難即從座起前白佛言), the longest prefix of A ≥ 4 characters, the longest suffix of A ≥ 4 characters (日觀初句佛告韋提汝及眾生: a locator before the incipit) → start; when nothing matches and the cursor is exactly the elder sibling's lemma end, and that end was found as a B, the node starts there, basis `interpolated` (the commentary tiles the text; an elder whose lemma is an incipit alone has no end to tile from — interpolating after its A would put the node at a wrong start and hide it from the resolver, so the node stays `unmapped`); B, searched after A → lemma end: whole anywhere after A in the parent span (also in the retry of a lemma found only inside the elder sibling's lemma range, where A is bounded by the cursor and B by the parent span), gapped / suffix only inside the enclosing lemma's end (a wrong fuzzy end must not run past the parent 分; a whole B may, because Kuiji's lemma is inherited down the first-child chain and names the first unit only);
2. no lemma, but children with spans → start = first child's start;
3. otherwise `root_text: null` and flag `unmapped` (the validator's sūtra-mode rule), for the resolver.
Ends tile: a node's end is the line before its next non-descendant sibling's start, or that start line itself when the sibling starts mid-line (`end_basis: next-node`, D15 addendum); the last child ends with its parent; a lemma end later than that is reported as an anomaly, not applied. Every non-whole method is in the anchor report (`lemma-gapped`, `lemma-prefix`, `lemma-suffix`, `lemma-interpolated`, `lemma-end-gapped`, `lemma-end-suffix`), so a reviewer can audit each fuzzy placement; on 善導's 五門 (T1753 over T0365, outside every split) they take unmapped nodes 35 → 23 and `lemma-not-found` 12 → 2 once 又就前序中 is attached under 序分 (§5.2), with the Kuiji dev root outline unchanged (2026-10-03). Known limitation, still open after Task 8 (rules A and B do not address it): end-quote semantics — 善導's 從X已來 names where an item *ends*, but a lemma is read as an incipit, so such an item is placed at X and the next one searched after it (the 耆闍會's 耆闍流通分, 一切大眾歡喜奉行, stays unmapped; interpolation no longer papers over it).

**Gate not met (Task 8, 2026-10-03).** After Task 8's anchor rules A and B, 善導's 疏 over T0365 (`projects/guanjing-shandao`) places 119 of 208 lemmas: `lemma-not-found` is 89 = 42.8 % against Task 8's ≤ 25 % gate (卷二 4/52, 卷三 31/98, 卷四 54/58; before fix round 3 it was 90 of 209 = 43.1 %, 卷四 55/59, with three 下品上生 items attached by index to the items of the unrelated 十一門 listing). The residual is a last item of one 觀 quoted loosely (作此觀 for 作是觀者) matching the same words one or more 觀 later, which strands the next 觀: the stranded lemmas are cousins, which rule B's sibling lookahead cannot see, and a joint assignment of starts across a root's whole subtree is the next step (tier C of the review). Most of the misses are 卷四's: 54 of the 89 are 卷四 lemmas, searched from p0346b15 (47) and p0346b19 (7), because 卷三's misplaced tail (普觀 at p0346a18, 雜想觀 at p0346b06:17) carries the cursor to the sūtra's last lines and rule A does not fire on 卷三. `tests/e2e/test_outliner_e2e.py::test_guanjing_run_keeps_the_counts_of_task_8` pins today's counts as ceilings (`lemma-not-found` at most 43 % of the lemma nodes, at least 119 placed) and `test_guanjing_run_meets_the_plan_gate` is a strict xfail at the 25 % gate; neither is a claim that the gate is met.

**(b) The outlined-text** over the *target* text (`target_role` = `commentary` or `root`). Contract `outlined-text.json` (`pipeline/schemas/outlined-text.schema.json`):

```
{ "schema": "outlined-text/1", "outline_ref": {path, sha256},
  "target": {text_id, role, sha256, first_linehead, last_linehead, length},
  "spans": [ {node_id, kind: "leaf"|"preamble", char_start, char_end, linehead_start, linehead_end,
              resolution: "explained"|"root_text"|"inherited"} ],
  "gaps": [ {char_start, char_end, reason} ], "coverage": {start, end, chars, covered, ratio, overlaps},
  "unplaced": [ … ] }
```

Field by field, with an example: "Output formats", "The outlined-text".

Positions: commentary target → a node starts at its enter marker's offset (tier 2 records it as `commentary.explained` with `:<offset>`) or, for tier-1/prior nodes, at the start of its explained line; a node the commentary only lists and never takes up (announced = explained, both with an offset) gets no span there, as in the workflow's interlinear outline, where an announced node that is never taken up has no text of its own (D16). Root target → at `root_text.start`, which carries `:<offset>` when the lemma starts mid-line (the scorer compares lines). A node's text runs to the next node's start in pre-order; the text between a parent's start and its first child's start is the parent's `preamble`. Spans of `leaf` + `preamble` tile the covered range with no overlap; zero-length nodes (items listed but never taken up) get no span. `outlined-text.md` is the human view: the input-text with `[indicator) heading_src — heading_en {announced, explained}]` inserted at each node start, `(inferred, 0.7)` for inferred nodes ("Output formats").

**(c) Out-of-span classification (`outline/classify.py`; sūtra mode, between (a) and the resolver).** It runs on the document after the pre-resolver validate-and-repair pass (§5.0 *Degradation*), so a repair that nulls or clips a span does not leave a stale classification. An unmapped sūtra-span node whose wording *announces an extent* beyond the root 品 its nearest spanned ancestor covers, and a division all of whose parts do, get the note `out-of-span: extent names 品 beyond this 品: …` and a report entry `kind: out-of-span`; the flag stays `unmapped` (closed flags enum; the node has no span in this build) and the resolver does not ask for them. The extent wording is: a 品 count (凡十五品半) with 凡 / 從 / 自 before it or 半 / 訖 / 至 / 下 / 已來 after it and no 第 before it; a 〈品〉 name right after 從 / 自 / 至 / 訖 / 盡 (經 may stand between) or right before 訖 / 至 / 下 / 已來, and not after 》 or 如; 訖經 / 盡經. A mere mention (如〈方便品〉說, 《維摩經》〈方便品〉, 第二品, 上中下三品) is no extent. Marking is idempotent. Zhiyi's 分文為三 parts 正 / 流通 and 又一時分為二 read inside 序品 are the E06 case. Method lists (今帖文為四：列數/所以/引證/示相) are commentary-internal from tier 2 (`filters.METHOD_TAILS`) unless an item names a text part (序 / 正 / 流通).

### 5.6 Resolver and gloss (`outline/resolver.py`, `outline/gloss.py`)

The resolver is the model-assisted part (plan M6). It runs per 品 (or per 卷 window in self-outlining mode) with the ancestor path in the prompt, so no call needs the whole text: a request holds one unit and the path above it, which keeps it small and keeps the model on the unit at hand. Three task types, one structured-output schema each (`pipeline/schemas/resolver-*.schema.json`):

| Task | Asked when | Output | Merge rule |
|---|---|---|---|
| `root-spans` | sūtra-span nodes flagged `unmapped` and not marked out-of-span (§5.5 (c)) | `{node_id, start, end, confidence, rationale}` | only inside the parent span, monotone; `basis: inferred`; flag `unmapped` removed |
| `subdivide` | a sūtra-span leaf whose span is longer than 360 characters (twice the chunk length budget; `subdivide_min_chars`), or every leaf with a span in a model-only run (no commentary) | `{parent_id, children: [{heading_src, start, end, depth, explained, confidence, rationale}], uncovered: [{start, end, kind, rationale}]}` | new `inferred` divisions only, up to depth 3 (each divided node has ≥ 2 children); `uncovered` lines are gaps (`paratext`) or text that belongs to a division the outline lacks (`overrun`, reported, no span changes); `scheme_id` = the project scheme, or `model-<prompt-hash>` with no commentary (D21) |
| `adjudicate` | a parser-report entry (ambiguous target, list-vs-division) | `{report_id, decision, target_node_id?, confidence, rationale}` | may attach an announcement the parser left out, as `inferred` |

**Request size (2026-10-01, after E06).** Every size counts characters as rendered (`<linehead>\t<text>` per line, about twice the text for CBETA lines). A user message holds at most `MAX_REQUEST_CHARS` (100,000); a text block shared by several candidates at most `MAX_TEXT_CHARS` (60,000); an outline listing longer than `MAX_OUTLINE_CHARS` (20,000) keeps only the candidates' ancestors, siblings and subtrees. A unit's candidates go into as few requests as fit. Each request shows the unit's whole commentary when it fits, otherwise each candidate's own range, trimmed to its head when needed. A candidate whose own lines do not fit one request is skipped and reported (root-spans, adjudicate). A subdivide leaf that does not fit is sent in windows instead: a core of `WINDOW_CHARS` (4,000) text characters with a quarter of that as context on each side, one request each, answered with the depth-1 divisions and uncovered ranges that begin in the core. The windows are joined into one division of the leaf: each division runs to the line before the next one begins. When only one division results, the leaf is reported as one unit with its uncovered ranges. Adjudicate shows the root text of the node whose treatment holds the entry when the unit's root text does not fit. E06 found requests of up to 177,081 characters, because the old budget counted text before rendering and left the outline listing unbounded. It also found a 300,157-character leaf (X0268) skipped whole, because a leaf over the budget was skipped rather than windowed.

**Divisions the model may give (2026-10-01, from E06's answer agents).** Subdivide takes up to three levels at once (`depth`), because one level could not express a two-level structure. The divisions may leave declared gaps (`uncovered`): before, the no-gap rule forced paratext into children, and a leaf over-extended by a missed sibling forced mis-parented children. Instead the model reports the `overrun` and leaves its lines out. In self-outlining mode a child's `explained` line may differ from its span start. It must lie inside the span, and explained lines run in outline order, because the outlined text places nodes by them.

Inferred nodes always carry `confidence` < 1, `evidence` = the rationale, and a note naming the adapter and model. The gloss sub-step (D17) fills `heading_en` for every node in one call per 品, with provenance in `notes`; with adapter `none` it leaves `heading_en: ""` and notes "not glossed".

Prompts live in `skills/chinese-kepan-outliner/references/` (resolver prefix: output contract, formula table, level-1 prior) so the skill and the headless run use one prompt source. Exemplars may come only from a named exemplar pool (`resolver.exemplar_block`), which refuses eval-only, out-of-domain and split golds. The pool is empty by default, so no prompt carries a worked example from a gold.

Adapters (§10): `none` (the default; set in `project.toml`, whether or not an API key is present), `replay` (tests), `claude` (Anthropic API), `interactive` (Claude Code session: requests are written to `llm/requests/*.json`, the session writes `llm/responses/*.json` following the skill, the CLI validates and merges).

### 5.7 Render (`outline/render.py`)

`outline.md` and `outline.docx` in the Tibetan workflow's independent-outline format: one paragraph per node, indented `144 × (level − 1)` twips, `[<indicator> – <heading_en>][<announced>, <explained>]` with the indicator's level numbers as `w:vertAlign="subscript"` runs, followed by the 干支 label and `heading_src`. For zh outlines the location pair is the CBETA pair in the text that states the outline, and in sūtra mode the root span follows in braces. The docx is written by `common/docx.py` with `zipfile` and the standard library (no python-docx). A base-profile document is rendered in the base format itself, and paragraph indices recorded from a source docx put every paragraph back at its source position. The formats are in "Output formats" below; `tests/unit/test_outline_render.py` checks the zh renders and that rendering is deterministic for both profiles.

## 6. `segment` (strategy 1–2)

`sentences.json` (`pipeline/schemas/sentences.schema.json`): `{schema: "sentences/1", strategy, punctuation_regime, sentence_rule, target, sentences: [{id, char_start, char_end, kind: prose|verse_line|lemma|gloss|heading, node_id}]}`. Strategy 1 ends a sentence after 。？！； (with the closing quotes and brackets that follow). Strategy 2 (the default) adds hard breaks at the lemma/gloss switch (經「…」。 | 贊曰：), at headings and `cb:mulu` positions, and makes each verse line (`in_verse`, cut at caesuras) a `verse_line` unit. Both strategies keep the outlined-text span boundaries: sentences never cross one, and every character of a span belongs to exactly one sentence (`pipeline/src/chinese_workflow/segment/README.md`).

## 7. `chunk`: the interlinear outline

Rules (D6, D14): walk the outline; for each parent, merge its consecutive leaf spans (and its preamble) into chunks while the chunk stays within the **sentence cap** (6) and the **length budget** (180 characters of reading text by default; recorded in `metadata.size_budget`; a default, not tuned); never split a leaf unless it alone exceeds the budget, and then split it at sentence ends (`fallback: split-leaf`); never merge across parents; text no span covers becomes `fallback: unoutlined` windows under the same budget. Contract `chunks.json` (`pipeline/schemas/chunks.schema.json`): the interlinear outline's content with CBETA locators — `metadata{target, target_role, outline_ref, sentence_rule, size_budget, counts, …}`, `markers[]`, `announcements[]`, `chunks[{chunk_id, node_id, leaf_ids, outline_path, topic_category, loc_start, loc_end, char_start, char_end, sentence_ids, n_sentences, n_chars, fallback, text}]` ("Output formats").

`chunks.md` reproduces the three line types of the workflow's interlinear outline: the taken-up marker `[<indicator>) <heading_src> <locator>]` before a node's first chunk, where the locator is `commentary.announced` when the node was announced, else `commentary.explained` (the workflow's marker carries the first-appears folio); announcement lines `<indicator>) <heading_src>` directly after the chunk that holds the announcing text (for a root target, which holds no announcements, after the parent's first chunk); chunks separated by blank lines. For a commentary target the announced labels stay in the running text as well (Chinese announces inline); the announcement lines are insertions (D16). `chunks.docx` renders the same with subscript indicators. `eval.chunk_invariants` checks: the schema; the size cap; contiguous full coverage of the target; sentence alignment; no sub-leaf split; merges within one parent; the `.md` ↔ `.json` round trip; monotone locators; that every named node exists; and that every taken-up node has exactly one marker, before its first chunk.

## 8. `export`: knowledge-graph v0 (M9)

`export.export(doc, id_history=…) → (graph, history)`, written as `<text_id>.<scheme_id>.jsonld`, BDRC-shaped (R07 F20): one `bdo:Outline` per (work, `scheme_id`); nodes as `bdo:Instance`-like parts with `bdo:partOf`, `bdo:partIndex` (= `sibling_index`), `bdo:partTreeIndex` (= the digit path), `bdo:partType`, `bdo:contentLocation` with `contentLocationStatementCBETA` from `root_text` (and our extensions `cw:commentaryAnnounced` / `cw:commentaryExplained` for the commentary positions), attribution (`cw:schemeId`, `cw:origin`, `cw:confidence`, `cw:seededBy`, `cw:goldStatus`). Node URIs are minted from a content key (sha256 over the parent's key, `heading_src`, `commentary.explained` and `root_text.start`) and kept in an id history (`export/id-history.json`: outline identity → content key → URI), so a node renumbered by an inserted sibling keeps its URI. Refuses `eval_only` outlines and OOD golds (§3); model-only nodes are exported only up to the level `allow_model_only_levels` allows (default 0: never); without `--frozen`, nodes below level 2 with a locator in a test or reserve span are withheld and only counted (`pipeline/src/chinese_workflow/export/README.md`). `export.load(jsonld)` re-imports the exported fields for the lossless round-trip test.

## 9. `eval`: the scorer

`python -m chinese_workflow.eval.score --pred outline.json --gold <dataset-id> [--key commentary.explained|root_text.start|commentary.span_start|structure] [--t 0] [--split dev] [--frozen TAG]` → `metrics.json`.

- **Key** defaults to the dataset's `split_scope.by` (E01: `commentary.explained`; root-text scoring, as in the T0262 sets of E06 and E07: `root_text.start`; EVAL-SETS "Using these sets" items 4, 12). Locators are compared at line granularity (`:n` offsets stripped). `commentary.span_start` (E06 review A3, 2026-10-02) scores a prediction at its text-span start (`common.outline_doc.fill_span_starts`: a first child inherits its parent's, unless the parent is editorial or starts before the build's first line) against the gold's `span_start` where present, else its `explained` line; never a default while the E01 key is open (EVAL-SETS item 3).
- **Matching** is top-down: the virtual roots match; the children of a matched pair are aligned one-to-one on key lines within `t` lines of each other (line distance = index distance in the file's own line list), order-preserving in line order: the most pairs, then the least total distance, then the least total sibling-index difference (a DP over the two sibling sequences; it replaced a greedy pairing that mis-paired shifted predictions at t = 1, review of E06, 2026-10-01; structure mode, which has no line order, keeps the greedy pairing by equal heading). A node whose parent is unmatched cannot match. This is "(explained locator, depth, parent path)" with tolerance (R06 F24). **S-F1** counts matched pairs; **F-F1** also requires equal `origin`.
- **Scope and splits** follow EVAL-SETS "Using these sets" items 1, 2, 5–8, 10, 11 exactly: nodes are scorable iff their key locator is not null; `coverage_spans` scope (Kuiji); served 卷-halves (sdp T1718); `truncated` handling; `merged_range` (in structure mode, where there are no lines, the split parts are the unmatched predicted siblings beside the merged node's pair, with no unmatched gold sibling between; a label like `K5-9` caps them); root-text scoring gives a gold node without its own split locator, and a prediction on no known gold node's line, the most protected split of the commentary between its nearest known gold neighbours (`eval/score.py` docstring, "splits"); reserve always refused during development; `test` needs `--frozen`; OOD golds need `--frozen`.
- **Rows:** S-F1 / F-F1 at t = 0 and t = 1 (the t = 1 − t = 0 gap is the anchor diagnostic, R06 F24 notes); per depth; with and without `anchor_inherited` (and, under `commentary.span_start`, without predictions whose `span_start` is inherited); child-count accuracy against `child_count_announced`; a **locator-only F1** diagnostic (key line only, no depth or parent) that shows how much of a low S-F1 is attachment rather than detection; structure-only F1 (heading + depth + parent path) for the YBh golds.
- **Diagnostic fields (A1 of the E06 review, 2026-10-02):** each row also reports the FN split into frontier misses (scoring-tree parent matched or root; `line_detected` when a free predicted node sits within t of the line) and cascaded misses, the FP split by node kind (listed-only by the anchor's rule, commentary-internal by `node_class`, taken-up), the distinct-key-lines recall cap (sdp's parent-and-first-child chains: 5 lines for 12 dev nodes on T1718), and the root-text TP rule side by side — the headline keeps "TP when the gold node is counted"; `s_f1_both_counted` requires both sides counted, with `tp_uncounted_pred` and the check `tp_le_counted_pred` (E06 review, §3 Q4, undecided). The dev diagnostics name the TP pairs and the ids behind each split. None of these changes S-F1, F-F1 or locator-only.
- **Attachment-tolerant triple (A2 of the E06 review, 2026-10-02; diagnostic, never the headline):** each row also reports `ancestor_consistent` (F1 of the ordered ancestor-consistent mapping with the most both-counted pairs (then the most pairs) over counted nodes and their scorable ancestors — a tree-edit mapping with unit insert/delete and no relabel, lines within t; counted first, so in the line-order keys it never falls below the both-counted S-F1; in structure mode the top-down match is greedy and can exceed the ordered mapping), `reanchor` (top-down pairs plus re-anchoring of unmatched gold nodes on free predictions, with the anchor count) and `depth_offset_hist` (level(pred) − level(gold) over line-matched pairs). The three are read together: AC-F1 alone is gameable (a flat prediction scores 0.68 on the Kuiji dev subtree, but with 41 anchors and a spread histogram), while one top-level slip reads as a high AC-F1 with one anchor and one modal offset (tier2-T0262-xu-root: 0.842, 1 anchor at t = 1; T1718 dev: 0.195, 4 anchors, so attachment is not its main loss; model-only 陀羅尼品: 0.658 / 0.842 at t = 0 / 1, depth-offset mode −1 at both t with a tail at −2). Forests above 600 nodes (X0268, YBh) skip it with a reason, as does a recurrence that overflows the recursion limit (Python 3.11, about 500 nodes). None of this changes S-F1, F-F1 or locator-only.
- **Disclosures** are printed with every score: `gold_status`, `seeded_by`, `eval_only`, the split (and whether it was defaulted), t, the key, the nodes out of scope and pairing warnings; a validation score also carries a reminder to log the look in the experiment's `looks.json` (`experiments/E01-explicit-recovery/looks.json` holds the validation looks so far). No headline on a `draft-unreviewed` or `imported-unchecked` gold, nor on a dev or validation score (the output says `headline: false`).

`python -m chinese_workflow.eval.chunk_invariants chunks.json outlined-text.json sentences.json` → invariant report.

## 10. `llm`: the shared model client

`llm.client.call(task, request, schema, config) → response`, where a request is `{system, messages, schema_name, meta}`. The request hash (sha256 of the canonical JSON of task, model, request and schema) keys a JSONL cache (`llm/responses.jsonl` in the outline build's directory, i.e. `<run>/outline/llm/` under the runner). Adapters: `none` (raises `NoModel`; callers degrade), `replay` (cassette only; a miss is an error), `claude` (Anthropic Messages API with JSON-schema structured output, the SDK imported lazily from the `llm` extra, key from `ANTHROPIC_API_KEY`; model default `claude-opus-5`, recorded with the returned model id and date; token and cost ledger), `interactive` (writes the request file and a prompt `.md` for a Claude Code session; the response file is validated against the schema before use). Every response is validated against its schema; an invalid one is recorded and not merged.

## 11. `runner` and projects

`projects/<id>/project.toml` (TOML, because Python 3.11 reads it with the standard library's `tomllib`; keys and defaults in the docstring of `common/project.py`):

```toml
id = "lotus-kuiji-dharani-comm"
mode = "sutra"                      # or "self-outlining"
root = "T09n0262"                   # CBETA file id
commentary = "T34n1723"             # omitted in self-outlining mode
scheme_id = "kuiji-xuanzan"
target_role = "commentary"          # the text the outlined-text and chunks are over
span = "dev"                        # dev | validation | whole | <start>..<end>
source = "tier2"                    # tier1 | tier2 | hybrid | oracle (the outline source)
[xml]                               # optional per-file XML overrides (e.g. test fixtures)
[[scheme.level1]]                   # optional scheme prior, §5.3
[resolver] adapter = "none"         # none | replay | claude | interactive
[chunk] sentence_cap = 6            # size_chars = 180
[segment] strategy = 2
[export] enabled = true
[outline] heading_style = "source"   # or "label" (ordinal stripped)
```

`python -m chinese_workflow.runner run projects/<id>/project.toml [--frozen TAG] [--out DIR]` (default `data/processed/<project id>/`) runs the outline build (tier 1 → tier 2 → merge → scheme prior → number → root spans → validate and repair → out-of-span classification → resolver and gloss when configured → span starts → validate → outlined-text → render), writes the ingest artefacts of the stated text's span and of the target, then runs segment → chunk → chunk invariants → export. It writes `run.json`: the project, the sha256 of its configuration, the pipeline commit and dirty flag, the date, the CBETA release, the input files with their sha256, the frozen tag, the resolver configuration, the model-call ledger, per-stage counts and the split-guard report. Exit 0 when every stage ran and the chunk invariants hold, 1 otherwise, 2 when the split guard refused the run. Stages are idempotent; a re-run reuses cached model responses.

Projects shipped: `lotus-kuiji-dharani-comm` (target T1723 陀羅尼品, dev span), `lotus-kuiji-dharani-root` (target T0262 陀羅尼品 with the commentary as context), `lotus-zhiyi-wenju` (T0262 with Zhiyi's T1718, target the commentary, dev span), `guanjing-shandao` (T0365 with 善導's T1753, target the commentary, whole texts, outside every split), `qixin-self` (T1666 大乘起信論, self-outlining, outside every split; 2 parser cases quote it, which is allowed as dev material).

## 12. Skill `chinese-kepan-outliner` v1

`SKILL.md` gives Claude Code the procedure in the workflow's order, naming the CLI each step calls: pick the project → ingest → outline (tier 1 + tier 2 + prior) → read `parser_report` → resolve (interactive adapter: answer each request file per the references) → gloss → validate → review inferred nodes, lowest confidence first → render → segment → chunk → export. `references/`: `output-contract.md`, `formula-table.md`, `level1-prior.md`, `review-checklist.md`, `resolver-prompt.md`, `gloss-prompt.md`, `split-discipline.md` (the "Do not open" list).

## 13. E01 as built here

`experiments/E01-explicit-recovery/` from the template, with the hypothesis written before the run. Arms: tier 1 alone (the floor) vs tier 1 + tier 2 (+ scheme prior where a project declares one). Sets: the parser cases (unit level), T1718 dev (served 卷一上) and T1718 validation (sdp gold, key `commentary.explained`), T1723 dev (Kuiji gold, draft: no headline). Test spans are not scored.

## 14. Design decisions (defaults)

| # | Decision | Default taken | Why |
|---|---|---|---|
| 1 | E01 match key (Appendix H item 3) | `commentary.explained` = the line where the node is taken up (enter marker / lemma), t = 0 headline, t = 1 column | the Kuiji gold's rule; sdp's "text start" is usually the same line; the t-gap measures the rest |
| 2 | Replaceable parts | tier 1, tier 2, the resolver and the scorer behind stable interfaces (`outline --source`, `eval.score`) | any one can be replaced without touching the rest |
| 3 | Default target role | `commentary` (the project default); the root target is built from the same outline (`lotus-kuiji-dharani-root`) | the commentary states the outline, so a commentary target needs no root anchoring to be chunked |
| 4 | Project file format | `project.toml` | stdlib `tomllib`, no new dependency |
| 5 | Scheme prior from the project file | `origin: editorial` | the run did not read the statement |
| 6 | Wrapper nodes for 品-level divisions | 三門分別 / 品文分N as nodes | the Kuiji dev subtree's convention |
| 7 | Chunk length budget | 180 characters, cap 6 sentences | the workflow's four-to-six-sentence bound as the cap; budget ≈ 6 × the median CBETA sentence (R01 F6); not tuned |
| 8 | Commentary-target announcement lines | inserted after the lead-in chunk, labels kept in the running text | Chinese announces inline (D16) |
| 9 | Resolver default adapter | `none` (no model call) | a run calls no model unless its project asks for one; `claude` and `interactive` are built and tested against recorded responses (cassettes) |
| 10 | Test spans and OOD golds | refused without `--frozen` | EVAL-SETS; plan §5 |

The divergences from the Tibetan workflow that this design introduces are D16 (interlinear conventions for sūtra mode and commentary targets), D17 (`heading_en` from a gloss step), D20 (knowledge-graph export) and D21 (model-only outlines under a model scheme), in `docs/chinese-workflow-mapping.md`.

## Output formats

The outliner writes three views a person reads (the independent outline, the outlined-text and the interlinear outline), each beside the JSON contract it is rendered from. Every render is deterministic: the same input gives the same bytes. The examples below come from the shipped project `lotus-kuiji-dharani-comm` (Kuiji's commentary T1723 on the Lotus Sūtra's 陀羅尼品, built with no model, so `heading_en` is empty).

**Word files.** `common/docx.py` writes every `.docx` with `zipfile` and the standard library (no python-docx). The package holds `[Content_Types].xml`, `_rels/.rels`, `word/document.xml` and `docProps/core.xml` (title and creator only), with fixed zip timestamps. Each paragraph is one `w:p`, and each run keeps its text verbatim (`xml:space="preserve"`). A run's properties are bold (`w:b`), italic (`w:i`) or subscript (`w:vertAlign w:val="subscript"`). An indent becomes `w:ind w:left` in twips. The writer adds no styles part, fonts, sizes or spacing.

### The independent outline: `outline.md`, `outline.docx`

`outline/render.py` renders `outline.json` in the independent-outline format of the Tibetan workflow:
- **Paragraphs.** One paragraph per node, indented 144 twips per level below 1.
- **Indicator.** Each entry opens with the bracketed indicator. Its values are bold runs and its level numbers bold subscript runs: `1₁2₂` is the runs `1`, `1` (subscript), `2`, `2` (subscript).

For a zh-kepan document (every outline the pipeline writes):
- **Front matter:**
  - the bold title `<text_title_src> 科判`;
  - `An Outline for <text_title_en>`, when the document has an English title;
  - one line giving the text, scheme, mode, root text, commentary and gold status;
  - a fixed format note.
- **One entry per node:** `[<indicator_display> – <heading_en>][<announced>, <explained>] <display_label> <heading_src> {<root_text.start>–<root_text.end>}† (inferred, c)`. In this entry:
  - ` – <heading_en>` is left out while `heading_en` is empty;
  - the pair is the node's commentary position in the text that states the outline. A null `announced` shows the explained line twice, and a missing position shows `—`;
  - the root-text span in braces appears in sūtra mode only, with `?` for a missing start or end;
  - `†` marks a node with `dagger`. `(inferred, c)` marks an inferred node with confidence c, and `(imported)` and `(editorial)` mark those origins.
- **`outline.md`** mirrors the docx: a `#` title, the front-matter paragraphs, then one nested list, indented two spaces per level, with the level numbers as Unicode subscripts. The text is not markdown-escaped.

```
- [1₁][T34n1723_p0806c24, T34n1723_p0806c24] 甲一 流通 {T09n0262_p0030b28–T09n0262_p0062a29} (editorial)
  - [1₁1₂][T34n1723_p0850a19, T34n1723_p0850a19] 乙一 陀羅尼品 {T09n0262_p0058b08–T09n0262_p0059b27}
    - [1₁1₂1₃][T34n1723_p0850a20, T34n1723_p0850a20] 丙一 三門分別
      - [1₁1₂1₃1₄][T34n1723_p0850a20:5, T34n1723_p0850a20:17] 丁一 一來意
```

A base-profile document (no `outline_profile`) is rendered in the base format itself:
- a `heading_src` paragraph before each entry;
- entries `[<indicator> – <heading_en>][<first>, <explained>]†`, with the location as the source typed it;
- the translation's chapter and Part headings, and bracketed entries without an indicator (`unindexed_entries`).

When the nodes carry `paragraph_index`, every paragraph goes back to its source position, padded with empty paragraphs; otherwise the paragraphs follow document order. Only an outline imported from a Word source carries `paragraph_index` (and the chapter and Part headings); no tool in this copy records them, so a base document here, such as the synthetic one below, renders in document order. `tests/unit/test_outline_render.py` checks the zh renders on `tests/fixtures/outline-zh/minimal.json`, and determinism on that file and on the synthetic base document `tests/fixtures/outline-base/minimal-base.json`.

### The outlined-text: `outlined-text.json`, `outlined-text.md`

`outline/anchor.py` writes `outlined-text.json` (schema `outlined-text/1`, `pipeline/schemas/outlined-text.schema.json`):
- **`outline_ref {path, sha256}`**: the outline it was built from;
- **`target {text_id, role, sha256, first_linehead, last_linehead, length}`**: the text it is over;
- **`spans`**: one entry per placed node, `{node_id, kind: leaf | preamble, char_start, char_end, linehead_start, linehead_end, resolution: explained | root_text | inherited}`;
- **`gaps`**, `{char_start, char_end, reason}`, and **`coverage`**, `{start, end, chars, covered, ratio, overlaps}`;
- **`unplaced`**: the nodes with no position in the target.

Offsets are global character offsets into the target's reading text, which is written beside it as `target.txt`. Starts are inclusive and ends exclusive. The spans tile the target except a gap before the first placed node.

`outlined-text.md` is the target text, broken only where a node starts, with a marker line before each placed node: `[<indicator_display>) <heading_src> — <heading_en> {<announced>, <explained>}]`. In the marker line:
- ` — <heading_en>` is left out while it is empty;
- `-` stands for a null locator;
- ` (inferred, c)` comes before the closing bracket for an inferred node.

The blocks are separated by a blank line, and CBETA's characters are kept exactly.

```
[1₁1₂1₃) 三門分別 {-, T34n1723_p0850a20}]
三門分別：一來意，二釋名，三解妨。

[1₁1₂1₃1₄) 一來意 {T34n1723_p0850a20:5, T34n1723_p0850a20:17}]
來意者，論云「為護眾生諸難」，如前已釋。
```

### The interlinear outline: `chunks.json`, `chunks.md`, `chunks.docx`

`chunk/chunker.py` writes `chunks.json` (schema `chunks/1`, `pipeline/schemas/chunks.schema.json`):
- **`metadata`**:
  - `target {text_id, sha256, …}`, `target_role`, `outline_ref {path, sha256}`;
  - `sentence_rule`, `size_budget {sentence_cap, chars}`, `counts`;
  - the merge, marker and announcement rules in words, and `unplaced_announcements`.
- **`markers`**: `{node_id, indicator, heading, locator, before_chunk}`. The locator is `commentary.announced`, else `commentary.explained`, else `root_text.start`, with any `:offset` kept.
- **`announcements`**: `{node_id, indicator, heading, after_chunk, parent_id}`.
- **`chunks`**, one entry per chunk:
  - `chunk_id`: `c1`, `c2`, … in text order;
  - `node_id`: the smallest node covering the chunk, which is its context key, or null for an unoutlined window;
  - `leaf_ids`: the outlined-text spans the chunk unions;
  - `outline_path`, `topic_category`;
  - `loc_start`, `loc_end`: lineheads, with `:offset` when mid-line;
  - `char_start`, `char_end`, `sentence_ids`, `n_sentences`, `n_chars`;
  - `fallback`: `none`, `unoutlined` or `split-leaf`;
  - `text`: the exact slice of the target text.

`chunk/render.py` renders `chunks.md` with the three line types of the Tibetan workflow's interlinear outline, using CBETA locators in place of folios:

```
[<indicator>) <heading_src> <locator>]      taken-up marker (locator left out when null)
<chunk text>                                one line = one chunk
<indicator>) <heading_src>                  announcement line
```

Each chunk gives one run: its markers, its text line, then its announcement lines. The runs are separated by one blank line. When several units merge into one chunk, their markers stand one after another before it. `parse_md(render_md(x))` gives back `x`'s markers, announcements and chunk texts exactly. `render_md` refuses content that would not read back, such as a line break in a heading or a chunk text that reads as a marker. `eval.chunk_invariants` re-implements the reader independently and checks the round trip on every run.

```
[1₁1₂2₃) 品文分三 T34n1723_p0850a29]
經「爾時藥王至功德甚多」。贊曰：品文分三：初明持經之福，次明神呪之方，後明時眾獲益。
1₁1₂2₃1₄) 初明持經之福
1₁1₂2₃2₄) 次明神呪之方
1₁1₂2₃3₄) 後明時眾獲益
```

Here the commentary announces the three parts inline, so the announcement lines are insertions after the chunk that holds the listing (D16).

`chunks.docx` has one paragraph per line and an empty paragraph per blank separator. The indicator's level digits are ordinary digits in subscript runs, and the document title is `<text_id> outlined-and-chunked-text`.

The other machine contracts are `sentences.json` (§6), the JSON-LD export (§8), `metrics.json` (§9) and `run.json` (§11).
