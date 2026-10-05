# Glossary

The terms used in this repository's documents, code and experiment records: the workflow terms the project takes from Kurt Keutzer's agentic translation workflow for Tibetan, Chinese-side terms, the sources and formats the pipeline reads, our own pipeline and evaluation terms, how to read the experiment tables, and a few Tibetan-side terms. The definitions are ours.

## Workflow terms

These are the terms of Kurt Keutzer's Tibetan workflow, which this project parallels for classical Chinese. We use them in that sense and do not coin alternatives. The right-hand column says where each one is in this repository.

| Term | Meaning | In this repository |
|---|---|---|
| input-text | The Unicode e-text of one edition of a source text, i.e. what the workflow outlines, chunks and translates. | The `ingest` stage's `<id>.txt` (CBETA's characters and punctuation, unchanged), with `<id>.lines.jsonl` and `<id>.structure.json` beside it. |
| variorum-text | One text with the readings of several editions marked as variants. | Not built. CBETA's encoding of the Taishō apparatus would give a partial one (divergence D2 in [`chinese-workflow-mapping.md`](chinese-workflow-mapping.md)). |
| independent outline | The outline of a text as a document of its own: one entry per division, with its heading, its place in the tree and where it is announced and treated in the text. | `outline/outline.json`, rendered as `outline.md` and `outline.docx` ([`outliner-design.md`](outliner-design.md), "Output formats"). |
| outlined-text | The text with its outline added as annotation: each division's heading inserted where its text begins. | `outline/outlined-text.json` (node → character spans) and its readable view `outlined-text.md`. |
| outlined-and-chunked-text, interlinear outline | The outlined-text cut into translation chunks separated by blank lines, with the outline's headings interleaved between the chunks. "Interlinear outline" is another name for the same artefact. | `chunk/chunks.md`, `chunks.json` and `chunks.docx`. |
| chunk | The unit sent for translation. The workflow keeps it to about four to six sentences. | One entry of `chunks.json`: by default at most 6 sentences and 180 characters, cut inside one outline parent (D6). |
| basic unit of translation | The level the outline is carried down to. | We take it to be an outline leaf. This is our reading, not a definition from the workflow (D6). |
| topic-category | What an outline node supplies for finding context to translate a chunk. | A chunk's `topic_category`: its node's own value, else the node's heading path (D17). |
| Project Instructions | The translation's style and presentation decisions, given to the model as standing instructions. | Not built: the `translate` stage is a stub (D9). |

## Chinese-side terms

| Term | Meaning | Evidence in this repository |
|---|---|---|
| 科判 kēpàn | A commentator's hierarchical division of a text into nested, labelled sections. The commentary announces a division in its prose (分三：初…次…後…) and then takes up each part in turn. It is the Chinese counterpart of the Tibetan sa bcad. | The tradition's own names are 科文, 科, 科註 and 科節. CBETA's title search finds 93 works with 科 in the title, none in the Taishō, and none titled with 科判 ([E00](../experiments/E00-kepan-census/SUMMARY.md) §3). |
| kēpàn coverage | How many texts have a kēpàn at all. | 148 of 1,757 Taishō root works (8.4 %) sit in a CBETA 部類 cluster that holds at least one commentary of the 疏 title class. This is a cluster-level bound, not a per-work count. The Lotus Sūtra's family is the largest, with 85 commentaries ([E00](../experiments/E00-kepan-census/SUMMARY.md) §3). |
| 科文 kēwén | An outline written out as a chart of its own, apart from the commentary: the tradition's form of an independent outline. | X0231 華嚴經疏科文 and X0584 法華三大部科文 are such charts. Once their ○-continued segments are re-linked, they reach depth 36 and 41 (lower bounds; [E00](../experiments/E00-kepan-census/SUMMARY.md) §6). |
| 三分 (序分 / 正宗分 / 流通分) | The three-part division of a sūtra into introduction, main teaching and dissemination. | The usual level 1 of a sūtra commentary's kēpàn, but a prior, not a rule: of the 59 經疏部 commentaries that announce a level-1 count in their first 卷, 53 make it three-fold ([E00](../experiments/E00-kepan-census/SUMMARY.md) §4). CBETA's table of contents carries it as level-1 nodes for 4 of the 158 Taishō 疏部 works: T1703, T1705, T1715 and T1814 (E00 §5). |
| 品, 卷 | 品 is a chapter of a sūtra. 卷 is a fascicle, the text's physical division. | Tier 1 reads both from CBETA's `cb:mulu`. 品 become outline nodes; 卷 are recorded in `metadata.juan`. |
| 疏, 注 / 註 | Commentary genres. A 疏 (or a 文句, 玄贊, 義記 …) divides its text and announces the divisions. An interlinear 注 glosses phrase by phrase and usually announces none. | The parser's genre gate builds no tier-2 nodes for a work whose title marks it 注 / 註 when its announcement density is low (`outline/tier2/filters.py`, `genre_gate`). |
| 干支 label | The traditional label of a kēpàn node: a heavenly stem or earthly branch for the level (甲 = 1 … 癸 = 10, 子 = 11 … 亥 = 22), then the sibling's ordinal (甲一, 乙二). | `display_label`, generated by `common/outline_doc.py`. There are only 22 symbols, so no label is generated below level 22. |
| CBETA | The Chinese Buddhist Electronic Text Association. It publishes the canon (the Taishō and other collections) as TEI P5 XML, one file per work, at `github.com/cbeta-org/xml-p5`, under CC BY-NC-SA 4.0 with its own notice. | This repository pins release tag 2026R2 (`scripts/fetch_cbeta.sh`, sha256 in `scripts/CHECKSUMS`). |
| Taishō (T), X, and other canons | The collections CBETA encodes: T is the Taishō canon (大正新脩大藏經) and X the Xuzangjing (卍續藏). File ids name the canon, volume and number: `T09n0262` is Taishō volume 9, number 262. | Projects, golds and locators all use CBETA file ids. |
| `cb:mulu` | CBETA's table-of-contents markup: one element per 卷, 品, 序, 分 … with a `@type` and a `@level`. | Tier 1 reads it. Four files of the 2026R2 corpus carry `cb:mulu` of type 科判, i.e. a full kēpàn: X11n0268 (2,611 nodes), P167n1573 (127), D14n8842 (40) and G069n1977 (15). This count comes from a survey run with `scripts/survey_cbeta_xml_p5.py`. The first three are out-of-domain golds, and G069n1977 is a test fixture. |
| linehead | CBETA's line reference. In `T34n1723_p0850a20`, `T34n1723` is the file id and `p0850a20` is page 0850, register a, line 20. | Every locator in this repository is a linehead, optionally followed by `:<offset>`, a character offset within the line (`common/lineheads.py`). |

## Other sources and formats

| Term | Meaning | In this repository |
|---|---|---|
| TEI P5 | Version P5 of the Text Encoding Initiative's guidelines, the XML vocabulary in which CBETA encodes its texts. | `ingest` reads CBETA's TEI P5 files (`data/raw/cbeta/`). |
| DILA | Dharma Drum Institute of Liberal Arts (法鼓文理學院), which serves the CBETA API and publishes the YBh database and the `cbeta-metadata` catalogue. | Sources and licences in [`../data/README.md`](../data/README.md). |
| YBh | DILA's 瑜伽師地論 (Yogācārabhūmi) database, whose downloadable 科判 files give the outline structure of T1605 and T1602. | The two structure-only golds `ybh-T1605` and `ybh-T1602` (`data/EVAL-SETS.md`). |
| CHIBS | Chung-Hwa Institute of Buddhist Studies (中華佛學研究所), publisher of the 法華經數位資料庫 that the sdp golds come from. | See *sdp* below. |
| BDRC | Buddhist Digital Resource Center. Its ontology (`bdo:`) gives the shape of the knowledge-graph export. | The `export` stage; `scripts/fetch_bdrc.sh` fetches the ontology for `tests/unit/test_export.py`. |

## Pipeline and evaluation terms (ours)

These terms are ours, not the Tibetan workflow's. Where one of its terms applies, that term is used instead.

| Term | Meaning | Where defined |
|---|---|---|
| sūtra mode, self-outlining mode | The outliner's two modes (`metadata.outline_mode`). In *sūtra mode* the outline is stated in another document, usually a commentary, and divides the sūtra. In *self-outlining mode* the text announces its own divisions, as a treatise does. | [`outliner-design.md`](outliner-design.md) §5; D3 |
| announced, explained (taken up) | A node's two positions in the text that states the outline (`locations.commentary`): *announced* is where the parent's division lists the node, and *explained* is where the node's own treatment begins (its take-up line). | D15 in [`chinese-workflow-mapping.md`](chinese-workflow-mapping.md) |
| listed-only | A node that the commentary lists but never takes up. It has no text of its own in the commentary, so it gets no span and no marker when the commentary is the target. | `outline/anchor.py` (`listed_only`) |
| origin: explicit, inferred, imported, editorial | Where a node comes from. *explicit*: read from the text's own markup or division formulae. *inferred*: proposed by a model, with a confidence below 1. *imported*: taken over from an external outline and not yet checked. *editorial*: supplied with no announcement in the text, e.g. a scheme-prior part. | `context/baseline/outline-schema-zh.json` (`origin`) |
| scheme | One commentator's division of a text. A sūtra can have several, so every outline names its scheme in `scheme_id` (e.g. `kuiji-xuanzan`). | D15 |
| tier 1 | The outline source read from CBETA's own table of contents: 卷 and 品 entries, and 科判 markup where CBETA has it. It is the floor every build starts from. | [`outliner-design.md`](outliner-design.md) §5.1 |
| tier 2 | The stateful rule parser for a commentary's division formulae (文為N, "the text is in N parts"; 初中亦二, "within the first, again two"; …): a stack of open divisions, anaphora, a genre gate and a doctrinal-list filter. | [`outliner-design.md`](outliner-design.md) §5.2 |
| scheme prior | A commentator's top-level parts, declared in the project file and merged with tiers 1 and 2 when the run does not read the commentator's own statement of them. | [`outliner-design.md`](outliner-design.md) §5.3 |
| lemma | A sūtra phrase that a commentary quotes before commenting on it, e.g. Kuiji's 經「A至B」 ("the sūtra, from A to B"). | `data/EVAL-SETS.md`, Kuiji gold |
| anchor | The step that places each lemma on sūtra lines, giving nodes their root-text spans, and writes the outlined-text. `lemma-not-found` is a lemma it cannot place. | [`outliner-design.md`](outliner-design.md) §5.5 |
| resolver, gloss | The model-assisted steps. The resolver adds inferred nodes and root-text spans; the gloss writes English headings (`heading_en`). Neither changes an explicit node. | [`outliner-design.md`](outliner-design.md) §5.6 |
| adapter | How the resolver and gloss reach a model: `none` (no model), `replay` (recorded answers only), `claude` (Anthropic API) or `interactive` (a Claude Code session answers request files). | [`outliner-design.md`](outliner-design.md) §10 |
| cassette | A file of recorded model requests and answers, keyed by request hash, that the `replay` adapter serves instead of calling a model. Editing a hashed prompt file changes every request hash, so the cassettes must then be re-recorded. | `tests/fixtures/llm-cassettes/`; [`outliner-design.md`](outliner-design.md) §10 |
| oracle | An outline read from a gold instead of built (`outline --source oracle`), letting through only what a developer may see. It let every stage run before the outliner existed, and in the sweeps it is the reference arm on T1723 dev. | `pipeline/src/chinese_workflow/outline/oracle.py` |
| hybrid, model-only | Two outline sources besides tiers 1 and 2. *Hybrid* is tier 2 plus the resolver and gloss. *Model-only* is the model outlining the root text with no commentary. | `experiments/E06-capability-sweep/README.md`, Method |
| arm, cell | In the capability sweeps E06 and E07, an *arm* is one outline source (tier 1, tier 2, hybrid, model-only), and a *cell* is one arm built on one dataset. | `experiments/E06-capability-sweep/README.md`, Method |
| gold | A reference outline that predictions are scored against, registered in `data/eval-sets.json`. | `data/EVAL-SETS.md` |
| sdp | The Lotus kēpàn of the CHIBS 法華經數位資料庫 (sdp.chibs.edu.tw), which follows Zhiyi's T1718. It publishes no licence, so the golds built from it are eval-only and never committed. | `data/EVAL-SETS.md`, sdp golds |
| S-F1, F-F1 | Node F1. A predicted node matches a gold node only if its key line (within a tolerance of t lines), its depth and its whole parent path match, so a node under an unmatched parent cannot match. F-F1 also requires the same `origin`. | [`outliner-design.md`](outliner-design.md) §9 |
| locator-only F1 | F1 over key lines alone, ignoring depth and parent. It measures detection without placement in the tree. | `pipeline/src/chinese_workflow/eval/score.py` (`locator_only`) |
| key | The locator a node is scored on: `commentary.explained` (the commentary line that takes the node up), `root_text.start` (its first sūtra line) or `commentary.span_start` (the start of its text span, which a first child shares with its parent). Which commentary line should key a node is open: the sdp golds use the line where the node's text starts, the Kuiji gold the line where Kuiji takes the node up (E06 review §3, item 1). | [`outliner-design.md`](outliner-design.md) §9; `data/EVAL-SETS.md` |
| dev, validation, test, reserve | Fixed line spans of T1718 and T1723. Development uses dev; validation is looked at a logged number of times; test is scored once, with a frozen outliner; reserve is not looked at. | `data/EVAL-SETS.md`, "Splits" |
| split guard | The check that refuses any read of a test or reserve span, and any use of an out-of-domain gold, unless a frozen outliner is named. Every check is logged in the run's report. | `pipeline/src/chinese_workflow/common/splits.py`; [`outliner-design.md`](outliner-design.md) §3 |
| look | One scoring pass over validation (or out-of-domain) rows. Validation looks are logged in `experiments/E01-explicit-recovery/looks.json`; E06 and E07 also keep their own logs (`looks-e06.json`, `looks-e07.json`), which include the out-of-domain looks. | `experiments/E07-capability-sweep-v1/README.md`, Method |
| frozen tag | A git tag naming the outliner version an evaluation measured: `outliner-v0-frozen-2026-10-01` for E06, `outliner-v1-frozen-2026-10-03` for E07. The tags are in the development repository. `--frozen <tag>` lets a run read test and reserve spans and score out-of-domain golds; the guard records the tag but does not check that it exists. | [`outliner-design.md`](outliner-design.md) §3; `pipeline/src/chinese_workflow/common/splits.py` |
| out-of-domain (OOD) | The golds outside T1718 and T1723 (X0268, P1573, D8842, T1605, T1602), scored only with a frozen tag. | `data/EVAL-SETS.md`, "Splits" |
| in-sample | Measured on text that the rules or prompts were developed on, and so not evidence of generalisation. | [`../README.md`](../README.md), Results, "Terms" |
| chunk invariant | A check every chunk must pass: size cap, no split inside a leaf, merges within one parent, full coverage, and the `.md` ↔ `.json` round trip. | [`outliner-design.md`](outliner-design.md) §7 |
| degraded | A build that found local order or containment errors and repaired them instead of failing. Each repair is in `outline-report.json`. | [`outliner-design.md`](outliner-design.md) §5.0 |

## Reading the experiment tables

The E06 and E07 records name sets, cells and diagnostics compactly. The sets are defined in the "Method" table of [`../experiments/E06-capability-sweep/README.md`](../experiments/E06-capability-sweep/README.md).

| Term | Meaning |
|---|---|
| set name | `<text>-<subset>`. `T1718-dev`, `T1718-validation` and `T1723-dev` are scored on commentary lines. A `-root` set (`T0262-dharani-root`, `T0262-xu-root`) is scored on lines of the sūtra T0262 (`root_text.start`): `dharani` is the 陀羅尼品, `xu` the 序品. `OOD-<id>` is an out-of-domain gold. |
| devval | One build over the dev and validation spans together (`T1718-devval`), scored on each; added after E06's pre-registration. |
| cell name | `<arm>-<set>`, e.g. `tier2-T1718-dev` or `hybrid-T0262-dharani-root`. A `*-markup` cell reads an out-of-domain text with its CBETA 科判 markup left in: a diagnostic marked LEAKED, never a result. |
| counted | A node the scorer counts: it has a key locator inside the scored split, scope and coverage. "Counted predictions" and "counted gold" are these nodes; the others are excluded with a reason (`eval/score.py`). |
| pin | The tier-1 node of a 品 (chapter). A build that starts inside a 品 carries its pin as an `editorial` ancestor above the span (`outline/tier1.py`, carried pins). |
| reachability | A design check of the sweep harnesses: how many counted gold nodes have all their ancestors inside what the cell's build can produce. Zero reachable means S-F1 is 0 for any outliner. |
| frontier, cascaded, both-counted, AC-F1, anchors | Scorer diagnostics, never the headline. A frontier miss has a matched parent (or is at the root); a cascaded miss sits under an unmatched one. The both-counted TP rule needs both sides counted. AC-F1 (ancestor-consistent F1), its anchor count and the depth-offset histogram form the attachment-tolerant triple ([`outliner-design.md`](outliner-design.md) §9). |

## Tibetan-side terms

| Term | Meaning |
|---|---|
| sa bcad | The Tibetan topical outline of a text: nested divisions, each with a heading. The Tibetan workflow's outliner recovers it. |
| ACIP folio | A folio reference into an Asian Classics Input Project e-text. The Tibetan outline format locates each entry by a pair of folios, [where it first appears in its parent's division, where it is taken up and explained]; the zh-kepan profile keeps this pair as CBETA lines (`locations.commentary`). |
| Toh | The Tōhoku catalogue number of a Kangyur or Tengyur text. |
