# eval/gold — gold-outline builders

**Input:** an external or hand-written outline source plus the CBETA text it anchors to — for `sdp.py`, sdp's 科判 trees and `getHtml` pages in `data/raw/dila-sdp/` (fetched by `scripts/fetch_dila_sdp.sh`) and `data/raw/cbeta/T09n0262.xml`, `T34n1718.xml` (line existence via `chinese_workflow.ingest.lines`).
**Output:** *gold outlines*: independent-outline documents under profile `zh-kepan` (`context/baseline/outline-schema-zh.json`, D15 in `docs/chinese-workflow-mapping.md`) that pass `scripts/validate_outline.py`, for the eval stage to score *independent outlines* against.

May import `chinese_workflow.ingest`; never `outline`, `chunk` or `translate` (stage boundary; `tests/unit/test_gold_sdp.py` checks it).

| Module | Input → output |
|---|---|
| `common.py` | nested draft tree → numbered zh-kepan nodes (`id` / `path` / `parent_id` / `order` / `sibling_index`), metadata counts, JSON writer, CBETA linehead composition, `known_lineheads` / `line_texts` (a file's lines, in order, with their text); runs `scripts/validate_outline.py` in-process by loading that script with importlib (the script stays the only owner of the checks) |
| `sdp.py` | `data/raw/dila-sdp/` → `data/raw/dila-sdp/gold/T0262.zhiyi-wenju-sdp.outline.json` (root-text gold, for E03: T0262 spans from sdp's line anchors, T1718 lines through sdp's 文句 links), `T1718.zhiyi-wenju-sdp.outline.json` (commentary gold, for E01: T1718 lines, T0262 spans borrowed from the linking T0262 nodes), `crosswalk-T0262-T1718.tsv` (one row per link, with its status) |
| `authored.py` | a hand-authored `*.outline.txt` (format below) + the CBETA files of its `commentary_id` / `root_text_id` → a checked zh-kepan gold JSON, e.g. `data/reference-outlines/T0262/kuiji-xuanzan/outline.txt` → `outline.json` |
| `sdp_check.py` | `data/raw/dila-sdp/gold/T1718.zhiyi-wenju-sdp.outline.json` + `data/raw/cbeta/T34n1718.xml` → `data/raw/dila-sdp/gold/heading-check.tsv`, `HEADING-CHECK.md` (every T1718 gold node's heading classified verbatim / partial / absent / no-text against Zhiyi's own wording in a window around its explained line; calibrated against R03 F23's 24-group hand sample; section below) |
| `cbeta_mulu.py` | one CBETA P5 file with `cb:mulu type="科判"` markup (X11n0268, P167n1573, D14n8842 in the pinned `data/raw/cbeta/xml-p5/` clone) → its self-outlining gold `data/reference-outlines/<short id>/cbeta-mulu-kepan/outline.json` (section below) |
| `ybh.py` | `data/raw/dila-ybh/<CODE>-kp.txt` → `data/reference-outlines/<CODE>/ybh-dila/outline.json`, structure only (T1605, T1602; T1579 out of scope: label forms the parser does not read; section below) |

Run: `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.sdp` (≈2 s; prints PASS/FAIL per gold and the counts).

**sdp golds are eval-only** (no licence published, R04 F32; rule 1 of "Rules for gold data" in `data/EVAL-SETS.md`): they are written only under `data/raw/dila-sdp/gold/` (gitignored), never committed, never used as prompt or training material. `metadata`: `scheme_id: zhiyi-wenju-sdp`, `origin: imported` on every node with sdp's id in `source_node_id`, `gold_status: imported-unchecked`, `seeded_by: null`, `licence.id: null`, `eval_only: true`, `cbeta_release: 2026R2`, `outline_mode: sutra`, `root_text_id: T09n0262`, `commentary_id: T34n1718`. The import rules (start line and its CBETA text check, heading-only nodes, missing T1718 卷-halves, `fetch_error` nodes, link corroboration) are in `sdp.py`'s docstring and in each gold's `metadata.format_note`. `root_text.end` is the node's last line, inclusive (`end_basis: next-node`): the line before the successor's start when the successor begins its line, else the successor's start line, which the two share (the schema's `next-node` rule, D15 addendum). A fetch_error node whose children sdp could not return (non-leaf on the server; none recovered from the HTML: 26 in the T1718 gold) carries flag `truncated`, since the gold does not encode its children. Flag `unmapped` marks a missing *primary* locator of the gold — `root_text` in the T0262 (root-text) gold, `commentary.explained` in the T1718 (commentary) gold; a missing secondary locator is only noted, except that a T1718 node without `root_text` keeps the flag because the schema's sūtra-mode rule requires it (`validate_outline.py` `[sutra-span-unmapped]`). So a scorer selects nodes by the locator it keys on, never by the flag.

**Scope of the T1718 gold (E01).** It declares no `coverage_spans`, so its scope is the whole gold, but only where sdp serves T1718: E01 keys on `commentary.explained` and scores only predictions whose explained line lies in a served 卷-half (9 of 20; `juan_halves` and `scoring_scope` in `data/eval-sets.json`). A prediction in an unserved half is out of scope, neither TP nor FP. The T1718 gold's `metadata.format_note` says so. The T0262 gold is not narrowed: root-text scoring against it (E02/E03, `root_text.start`) has all of T0262 as scope, since sdp serves all seven 卷.

## Authored golds (`authored.py`)

Golds drafted by hand or by a model (the Kuiji 玄贊 gold) keep their source of truth in a readable text file that a reviewer can check line by line; the JSON is compiled from it and never edited by hand.

Run: `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.authored <txt> -o <json>` (≈1 s). Looks up `data/raw/cbeta/<id>.xml`, else `data/raw/cbeta/xml-p5/**/<id>.xml`, for the header's `commentary_id` and `root_text_id` (`--cbeta-dir`, `--commentary-xml`, `--root-xml` override). Prints PASS with the counts, or every error with its txt line number and writes nothing (exit 1). Test: `tests/unit/test_gold_authored.py`.

### Format of `*.outline.txt`

UTF-8. Blank lines and lines whose first non-space character is `#` are ignored anywhere.

**Header** — the leading block of `key: value` lines (key in lower case); the first other line starts the nodes. `null` means null.

| Key | Required | Goes to `metadata.` |
|---|---|---|
| `scheme_id` | yes | `scheme_id` |
| `outline_mode` | no (default `sutra`) | `outline_mode` |
| `root_text_id` | yes | `root_text_id` (CBETA file id, e.g. `T09n0262`) |
| `commentary_id` | in sūtra mode, to find the XML | `commentary_id`, `source_document.text_id` (e.g. `T34n1723`) |
| `text_id`, `text_title_src`, `text_title_en`, `author` | titles yes | same names |
| `source_kind` (default `commentary`), `source_title` | title yes | `source_document.kind` / `.title` |
| `seeded_by`, `gold_status` | yes | same names |
| `licence_id`, `licence_holder`, `licence_statement`, `licence_evidence` | statement yes | `licence.{id, holder, statement, evidence}` |
| `eval_only` (`true`/`false`), `cbeta_release` | yes | same names |
| `origin_note` | no | `origin_note` |
| `coverage`, `split_note`, `anomaly`, `source_note`, `format_note` | repeatable | `coverage`, `split_notes` [lists], `anomalies`, `source_document.notes` (the compiler adds the sha256 of both XML files), appended to `format_note` |
| `coverage_span` | repeatable | `coverage_spans`: one entry per line, `root=<heading>@<@exp linehead>` (or `root=document`) `commentary=<start>..<end> root_text=<start>..<end> max_level=<n>` (or `max_level=full`) → `{node_id, heading_src, commentary {start, end}, root_text {start, end}, max_level}`; spans inclusive; the `root_text` span bounds the covered leaves, not every node's span; `max_level` is the absolute outline level down to which the subtree is complete, null (`full`) for full depth, i.e. every division the commentary takes up in the span. Scoring scope: see the Stop marker convention below |

The compiler adds `source_file` / `source_sha256` (the commentary XML), `authored_file` / `authored_sha256` (the txt), `generated_by`, `display_label_rule`, `source_language: lzh`, and the counts (`common.zh_metadata`).

**Nodes** — one per line, **two ASCII spaces per level** (a tab or any other whitespace in the indent, e.g. U+3000 from a CJK IME, is an error; one level deeper at a time), then `heading_src` exactly as `ingest.lines` gives it (the source's ordinal included: `一來意`, `初明持經之福`; never normalised), then ` @key=value` fields. A value runs to the next ` @key=` (so a value cannot contain one).

| Field | Meaning | JSON |
|---|---|---|
| `@exp=<linehead>` | **required**: commentary line where the node is taken up — its topic marker (此初 / 下明… / 第二… / …者); for a 品, the line of its `cb:mulu`; for a sub-item the commentary only lists, the listing line | `locations.commentary.explained` |
| `@ann=<linehead>` | line where the parent's announcement lists the node | `locations.commentary.announced` (else null) |
| `@src=<linehead>` | line the heading is copied from, when it is not within ±2 lines of `@exp`/`@ann` (the check then uses only this line) | evidence |
| `@lemsrc=<linehead>` | line the commentary quotes the node's `@lemma` on (its 經 line), when that is more than 2 lines before `@exp` — Kuiji quotes a lemma once, then announces several levels before 此初也; the lemma check then uses this line. Must come before `@exp`; the lemma must be quoted there as 經「…」, and no other 經「 may stand from it to the end of the `@exp` line: for a `@lemsrc` node `@exp` is bounded to the lemma's block (up to the next 經「), not to ±2 lines | a generated note (`lemma 經「…」 quoted on …`) |
| `@root=<start>..<end>` | root-text span, inclusive lineheads | `locations.root_text.start/end` |
| `@basis=` / `@endbasis=` | how start / end were fixed (schema enums; `@endbasis` only when it differs, e.g. `next-node`) | `root_text.basis` / `end_basis` |
| `@lemma=<text>` | the commentary's quoted lemma (inside 經「…」); given **iff** `@basis=lemma` | `root_text.raw` |
| `@cut=<text>` | the annotator's cut words in the root text, for a division the commentary lists without quoting a lemma; given **iff** `@basis=manual` | a generated note |
| `@n=<int>` | announced child count | `child_count_announced` |
| `@ext=<text>` | announced extent (八品, 有十一行), verbatim-checked like the heading; a warning on a commentary-internal node or a non-explicit one (then unchecked) | `extent_announced` |
| `@origin=` | `explicit` (default) / `inferred` (needs `@conf`, `@evidence`) / `editorial` (needs `@evidence`) | `origin` |
| `@conf=<0..1>` | confidence of an `inferred` node (required there; on any other origin it is ignored with a warning) | `confidence` |
| `@class=` | `sutra-span` (default) / `commentary-internal` (no `@root`) | `node_class` |
| `@flags=a,b` | schema flags | `flags` |
| `@label=` | display label; default generated 干支 + ordinal (level 2, 3rd sibling → 乙三) | `display_label` |
| `@note=<text>` | repeatable | `notes` |
| `@evidence=<text>` | overrides the generated evidence (the source line(s) where the heading was found) | `evidence` |

`heading_en` is "" and `source_node_id` null (nothing is imported). Ids, paths and order come from `common.number_tree`.

### Checks (errors name the txt line)

- Every `@exp`/`@ann`/`@src` linehead is a line of the commentary file, every `@root` linehead a line of the root text; start ≤ end.
- `origin=explicit`: the heading occurs punctuation-insensitively within ±2 lines (document order) of `@src`, else of `@ann` or `@exp` — or equals a `cb:mulu` label on the `@exp` line (品 headings are CBETA's TOC labels). `@ext` occurs in the same window. A match that needs punctuation ignored is reported as a warning.
- `@lemma`: occurs within ±2 lines of `@exp` (of `@lemsrc` when given; `@lemsrc` needs `@lemma`, comes before `@exp`, the hit near it must be a quotation — 經「 immediately before it — and no other 經「 stands between that quotation and the end of the `@exp` line, so `@exp` lies inside the lemma's block; a topic marker that shares its line with the next quoted lemma therefore cannot take `@lemsrc`); in the root text, its words before 至 start on the `@root` start line and the first following occurrence of its words after 至 ends on the `@root` end line (on or before it with `@endbasis`).
- `@cut`: starts on the `@root` start line.
- The locator backs the basis: `@lemma` iff `@basis=lemma`, `@cut` iff `@basis=manual` (a span with neither `chapter`, `lemma` nor `manual` basis is only checked for existence and order).
- Next-node rule: a sūtra-span node's end is the line of the last non-punctuation character before the start of the next sūtra-span node after its subtree, whenever that node's start is located by `@lemma` or `@cut` (so siblings tile the text; the end is the inclusive last line, possibly shared with the next node's first line).
- `basis=chapter`: start carries a 品 `cb:mulu` in the root text; end is the last line of a 品 (last line inside a `pin` div before the next 品 `cb:mulu`; juan titles and T09n0262's 附文 fall outside). A node without chapter-basis children spans one 品 (its end is the last line of the 品 it starts in); a node with chapter-basis children spans exactly their first to last 品; chapter-basis nodes that follow each other (next-node rule) cover consecutive 品. `end_basis=chapter`: end is the last line of a 品, namely of the 品 the start is in (a start outside every 品 fails).
- commentary-internal nodes have no `@root`/`@lemma`/`@cut`; in sūtra mode a sūtra-span node without `@root` must carry `@flags=unmapped`.
- `@n` ≠ number of children → flag `count_mismatch` and a note are added (a warning, not an error).
- `coverage_span`: the root names exactly one node (heading and `@exp`), or the whole document; all four lineheads exist and each span is in order; every commentary locator of the covered nodes lies in the commentary span and every covered sūtra-span leaf in the root-text span; with a numeric `max_level` no covered node is deeper, except that for `root=document` deeper nodes are allowed inside another entry's subtree.
- Then `scripts/validate_outline.py` (in-process, `common.validate`): errors fail the run, warnings are printed.

### Kuiji conventions (all chapters of `T0262/kuiji-xuanzan`; decided 2026-09-22)

- A 品 node's children are its gate node(s) (三門分別 / 六門料簡 …, `commentary-internal`, with the gates as children) and, when Kuiji announces a division of the chapter text itself (陀羅尼品 「品文分三」, 譬喻品's own formula at T34n1723_p0735b21 — same rule: the shortest verbatim phrase naming the division noun and the count; test-split material, not quoted here), **one sūtra-span node whose heading is that announcing phrase verbatim** (`品文分三`), `@n` = the announced count, `@root` = the span it divides (from the first division's start to the 品's end: `@basis=lemma` on the first lemma, `@endbasis=chapter`); the N divisions are its children.
- `@exp` = the line of the node's topic marker (此初 / 下明… / 第二… / …者; a 品's `cb:mulu` line); `@ann` = the line of the parent's announcement; a sub-item Kuiji only lists has `@ann` = `@exp`.
- Lemma divisions (經「A至B」) have `@lemma` + `@basis=lemma`; a class node that groups lemma divisions carries its first member's lemma with `@endbasis=next-node`; sub-items listed without a lemma have the annotator's `@cut` + `@basis=manual`.
- A node whose topic marker stands more than two lines after the 經 line quoting its lemma keeps `@exp` on the marker and gives the 經 line as `@lemsrc` (Kuiji quotes a lemma once, then announces several levels before 此初也).
- End bases other than the lemma's own end: `next-node` (checked: the next located division starts after it); `chapter` (the 品文 node); `extent-formula` for a verse division whose end Kuiji fixes by a stanza count (N頌, 二十五頌半) and whose next division is not in the outline — the compiler does not count stanzas, so the note gives the verse lines counted; `manual` for an end the covered commentary does not fix, with the reading and its alternative in a note.
- **Stop marker and scoring scope** (decided 2026-09-22; the flag is a schema amendment recorded as the D15 addendum in `docs/chinese-workflow-mapping.md`):
  - Flag `truncated` = the gold does not encode all of this node's source children: it stops at a depth limit, or Kuiji takes the rest up after the end of the covered span. The node keeps any count Kuiji announces (`@n`, then `count_mismatch`).
  - Flag `coarsened` keeps the schema's meaning, a property of the source: the commentary itself stops subdividing although the root-text span is long.
  - **Scope.** In a gold that declares `metadata.coverage_spans`, scope alone decides what is scored. A predicted node is in scope iff its start locator lies inside an entry's span and its level ≤ that entry's `max_level` (null = no limit). The start locator is `commentary.explained`, or `root_text.start` in sūtra-mode root-text scoring. Only the start must lie in the span: a covered node's root span may run past the entry's `root_text` end (a 品文 node spans to the end of the 品), because an entry's `root_text` bounds the covered leaves, not every node's span.
  - In such a gold, in-scope predictions that match no gold node are FP, including under a `truncated` node, and out-of-scope predictions are neither TP nor FP. A gold without `coverage_spans` (e.g. the sdp golds) has the whole gold as its scope; for the T1718 sdp gold (E01) that means the 卷-halves sdp serves (sdp section above).
  - **`truncated`.** In every gold, a `truncated` node's encoded descendants are scored normally and its unencoded source children are not FN. With `coverage_spans` the flag is informational, since the scope already excludes what it marks. Without `coverage_spans`, predicted nodes under a `truncated` node that match no encoded node are neither TP nor FP.
  - **Tree edit distance:** prune the out-of-scope predicted subtrees, and in a gold without `coverage_spans` also those predicted subtrees under `truncated` nodes that match no encoded node.
- A covered span that stops inside a 品 (rule 5 of `data/EVAL-SETS.md` fixes the split spans): a division is a node only if Kuiji takes it up before the span's end. A node whose announced children run past it carries `truncated`; a comment in `outline.txt` lists the children left out. Commentary-internal nodes are the gates and the items a gate announces or numbers (a gate's 「來意有二」 items, the numbered 問 of a 釋妨 gate); doctrinal lists inside a treatment (「有三義」, a 論's list assigning 品 to its categories, a quoted treatise's list of phrases) are content, kept in notes.
- A depth-limited subtree: a node at the last encoded level under which Kuiji announces, lists or quotes (經「…」) further divisions carries `truncated`, plus `@n` and `count_mismatch` where Kuiji announces a count for it. When what lies below it is only a gate formula (「…等，以三門分別」), the count belongs to that formula and the node has no `@n`. Its note names what is left out. A 品 node without a subtree also carries `truncated`.
- **Decided 2026-09-22:** an explicit announcement node (品文-style, heading = Kuiji's announcing phrase) is created only when a part has its own gate formula (commentary-internal gate node(s)) alongside the division of its text. Gate node and announcement node are then siblings, even where Kuiji states the text division inside his last gate. This is the case at the 品 level (陀羅尼品: 三門分別 and 品文分三) and, below the 品, in one part of the 序品 subtree (gate formula at T34n1723_p0666a16, text division at p0667a22; test-split answer key, so not quoted here: `data/EVAL-SETS.md`, "Do not open while developing"). Otherwise the divisions Kuiji announces are the node's direct children, as in 陀羅尼品's 後答 (「答中有三」).
- **Decided 2026-09-22:** where Kuiji's lemma differs from T09n0262's wording (a variant character; an added or missing word), `@lemma` cannot resolve, so the start is the annotator's `@cut` in T09n0262's words (`@basis=manual`) and the note quotes Kuiji's lemma and any variant T09n0262's apparatus records.
- The header's `split_note` says which split spans the outline holds answer keys for (`data/EVAL-SETS.md`, rule 5).

## sdp heading check (`sdp_check.py`)

Run: `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.sdp_check` (reads the T1718 sdp gold, never modifies it). Its outputs, `heading-check.tsv` (one row per node) and `HEADING-CHECK.md` (tallies, the F23 calibration and a noise baseline), live only under `data/raw/dila-sdp/gold/` (gitignored, eval-only). The committed module and its test hold no sdp heading text; `tests/unit/test_sdp_eval_only_guard.py` checks every tracked file for sdp headings (`data/EVAL-SETS.md`, rule 1).

It classifies every node's heading against a window of Zhiyi's own wording built from `locations.commentary.explained`:
- `verbatim`: a contiguous substring, punctuation-insensitive;
- `partial`: LCS ≥ 0.6 of the heading;
- `absent`;
- `no-text`: no window.

Before matching, the heading loses sdp's leading ordinal and a trailing count, but a count only where it equals the node's child count.

The window is the node's own span, at least 3 lines, plus the first 3 lines of its parent's span. A node with no explained line inherits its nearest explained ancestor's window instead of being searched against the whole file, so its true location is unknown. The module docstring gives the exact regexes and window rule. The aggregate counts, per split, are in `data/EVAL-SETS.md`.

## CBETA 科判 golds (`cbeta_mulu.py`)

These golds import a 科判 tree straight out of CBETA's own `cb:mulu type="科判"` markup. No alignment step is needed: the markup states level, heading and line (R02 F15/F28; four files in the 2026R2 corpus carry it, three are built here, and G069n1977 is a test fixture). Run: `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.cbeta_mulu` (builds all three, ≈1 s).

`metadata`:
- `scheme_id: cbeta-mulu-kepan`;
- `outline_mode: self-outlining`, `source_document.kind: root-text`, `root_text_id` = the file's own id, `commentary_id: null` (the schema's own worked example for X11n0268);
- `origin: imported` on every node, with `source_node_id` = `<file id>#<ordinal>`;
- `gold_status: imported-unchecked`, `seeded_by: null`;
- `licence.id: CC-BY-NC-SA-4.0`, `eval_only: false`.

Every node is `sutra-span`. `commentary.announced` = `commentary.explained` = `root_text.start` = the own-canon line the mulu sits on (`basis: cbeta-mulu`). Every mulu sits at offset 0 of its line, which is checked. `root_text.end` is the inclusive last line before the next node that is not a descendant (`end_basis: next-node`); the file's last branch ends on the file's last line (`end_basis: null`). X11n0268's R017 lineheads on the same lines are notes, never locators.

Flags:
- A level jump in the source, or a node that opens at a level other than 1 with nothing shallower pending (P167n1573, twice), is flagged `irregular_label`. The output level is always the structural parent + 1: no node is invented.
- A mulu holding two labels is kept whole and flagged `merged_range`.

`child_count_announced` is read from a trailing parenthesised numeral and always kept, with `count_mismatch` when the children disagree. A bare trailing numeral is kept only when it equals the children present.

The XML sha256 is stated in each `PROVENANCE.md`; `scripts/fetch_cbeta_xml_p5.sh` pins the clone by commit, so there are no per-file `scripts/CHECKSUMS` lines.

## YBh golds (`ybh.py`)

DILA's 瑜伽師地論資料庫 publishes 科判 outlines as plain `-kp.txt` files with no Taishō line anchors. `ybh.py` imports them as **structure-only** golds: `locations.scheme: "none"` and flag `unmapped` on every node. Run: `cd pipeline && .venv/bin/python -m chinese_workflow.eval.gold.ybh` (T1605 and T1602 by default, ≈1 s).

Parsing:
- Depth comes from the label's letter (A = 1 … Z = 26, a = 27 …), cross-checked against the 2-space indentation. A disagreement is flagged `irregular_label`, with depth taken from the label; none occurs in T1605 or T1602.
- A hyphenated label (`H4-5`) is flagged `merged_range`.
- A trailing `（分N）` gives `child_count_announced`, flagged `count_mismatch` when it disagrees with the children present.
- `display_label` = DILA's label.

`metadata`:
- `outline_mode: sutra` with `commentary_id: null`. This is `metadata_zh.commentary_id`'s case (b): the stating work has no CBETA id (T1605: 韓清淨's 集論科文別釋; T1602: 早島理・毛利俊英 1990).
- `root_text_id` was checked against the local xml-p5 clone.
- `licence.id: CC-BY-SA-4.0`, with the CHIBS mirror's 3.0 台灣 statement recorded in `PROVENANCE.md`; `eval_only: false`.

## The registry

Every gold these modules build is registered in `data/eval-sets.json`, together with its path, anchors, licence, split scope, gaps and the experiments that use it. `data/EVAL-SETS.md` is the guide and ends with the notes for scoring. After rebuilding a gold, run `python3 scripts/eval_sets.py --write` so that the recorded counts and the guide's tables follow; `tests/unit/test_gold_registry.py` fails when they are stale, or when a gold is not registered.
