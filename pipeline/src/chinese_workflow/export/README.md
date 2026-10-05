# export — independent outline → knowledge-graph JSON-LD (v0)

**Input:** an independent outline, `outline.json` under profile zh-kepan (`context/baseline/outline-schema-zh.json`, D15), and optionally the id history of earlier exports (`export/id-history.json`).
**Output:** one JSON-LD document per (work = `metadata.root_text_id`, scheme = `metadata.scheme_id`), BDRC-shaped, conventionally named `<text_id>.<scheme_id>.jsonld`, and the updated id history. `load(jsonld)` re-imports the exported fields for the round-trip check.

Provenance: plan M9 (D20) and §5 "Knowledge graph"; `docs/outliner-design.md` §8. The shape follows BDRC's ontology `core/bdo.ttl` as R07 F20 reads it (VERIFIED; R07 S50, buda-base/owl-schema commit 4f3bf4a, local copy `data/raw/bdrc/owl-schema/core/bdo.ttl`). Every `bdo:` term below is checked against that file by `tests/unit/test_export.py` when it is present. The design choices (our `cw:` terms, the URI rule, the withholding rules) are proposals that have not been reviewed.

The stage reads only `outline.json` files and imports only `chinese_workflow.common`.

```python
from chinese_workflow.export import export, load
graph, history = export(doc, id_history=None, base_uri="https://example.org/chinese-workflow/",
                        allow_model_only_levels=0)        # also: source_path=, frozen=
loaded = load(graph)                                      # {"metadata": {...}, "nodes": [...]}
```
```
python -m chinese_workflow.export OUTLINE.json --out OUT.jsonld [--id-history export/id-history.json]
    [--base-uri URI] [--allow-model-only-levels N] [--frozen TAG]
```
The CLI exits with status 2 when a guard refuses the outline and prints a summary line to stderr: nodes exported, model-only nodes withheld (with their ids), nodes withheld by the split guard (a count).

## Shape

`@graph` holds, in this order: one `bdo:Outline`, one resource per exported node in document order, then the `bdo:PartType` resources the nodes use, sorted. The catalogue (work) tree stays apart from the outline tree (plan §5): a work can carry several outlines, one per scheme, so no outline describes the work itself. Works are referenced by IRI, `<base>work/<CBETA file id>`, and are never described or given parts here.

- **Outline** `<base>outline/<root_text_id>/<scheme_id>`, type `bdo:Outline`, `bdo:outlineOf` the work, `skos:prefLabel` = the titles (`@language` `lzh` and `en`). Attribution: `cw:rootTextId`, `cw:textId`, `cw:schemeId`, `cw:outlineMode`, `cw:commentaryId`, `cw:goldStatus`, `cw:seededBy`, `cw:cbetaRelease`, `cw:licenceId` (SPDX id), `cw:sourceFile`, `cw:generatedBy`. Export report: `cw:exportedNodeCount`, `cw:withheldModelOnly` (an ordered list of node ids), `cw:withheldSplitCount` (a count only), `cw:frozen`.
- **Node** `<base>node/<uuid>`, types `bdo:Instance` and `cw:OutlineNode`.
  - Tree: `bdo:partOf` is the parent node, or the outline for a level-1 node. `bdo:partIndex` = `sibling_index`. `bdo:partTreeIndex` = the digit path, e.g. `"3.17"`.
  - Type: `bdo:partType` = `cw:partType/<part_type, percent-encoded>` when `part_type` is set (e.g. 品), else `cw:nodeClass/<node_class>`.
  - Headings: `skos:prefLabel`, with `heading_src` in `lzh` and `heading_en` in `en`. An empty heading is omitted.
  - Root-text span: `bdo:contentLocation` → a `bdo:ContentLocation` with `bdo:contentLocationInstance` (the work), `bdo:contentLocationStatementCBETA` (start linehead), `cw:contentLocationEndStatementCBETA` (end linehead), `cw:charOffset` / `cw:endCharOffset` (our `:n` suffix), `cw:basis`, `cw:endBasis`, `cw:raw` and `cw:cbetaFileId` (only when `root_text.text_id` overrides).
  - Commentary positions: `cw:commentaryAnnounced` and `cw:commentaryExplained`, each a `bdo:ContentLocation` shaped like the one above. Also `cw:commentaryRaw`, `cw:commentaryFileId`, and `cw:commentaryUnlocated` (a position exists but neither locator is set).
  - The rest: `cw:origin`, `cw:confidence`, `cw:evidence`, `cw:childCountAnnounced`, `cw:extentAnnounced`, `cw:flags` (an `@list`, so order survives), `cw:displayLabel`, `cw:nodeClass`, `cw:sourceNodeId`, `cw:schemeId` (a node-level lens), `cw:locationScheme` (only when not `cbeta-kepan`) and `cw:locationRaw`.
- Not exported: `notes`, `indicator_display` (derivable), `topic_category`, and the gold-only metadata (`coverage`, `coverage_spans`, `split_notes`, `format_note`).

### BDRC terms used vs ours

| BDRC (`bdo:` = `http://purl.bdrc.io/ontology/core/`) | Our use |
|---|---|
| `bdo:Outline`, `bdo:outlineOf` | the outline per (work, scheme) and its work |
| `bdo:Instance` | node type; it is the domain of `partOf`, `partIndex`, `partTreeIndex`, `partType` and `contentLocation` |
| `bdo:partOf`, `bdo:partIndex`, `bdo:partTreeIndex`, `bdo:partType`, `bdo:PartType` | the tree, as BDRC defines it: children indexed 1..n, and a dotted index "5.1.3.2" |
| `bdo:contentLocation`, `bdo:ContentLocation`, `bdo:contentLocationInstance` | the root-text span, and the facet shape of the commentary positions |
| `bdo:contentLocationStatementCBETA` | the start linehead, `TnnNnnnn_pPPPPrLL` |

Everything in `cw:` (`<base>ontology/`) is ours. The terms BDRC lacks are the announced/explained pair (R07 F20: no BDRC property carries "announced vs explained"), the end of a CBETA span, character offsets, attribution (`schemeId`, `origin`, `confidence`, `goldStatus`, `seededBy`, ...), announced counts and extents, and flags. Where we stretch BDRC:
1. `bdo:contentLocationStatementCBETA` is an annotation property whose superproperty `bdo:contentLocationStatement` has domain `bdo:Instance`. We attach it to the `ContentLocation` facet instead, because a node carries up to three locations (root span, announced, explained). The facet already has start/End pairs for pages and lines, but no End statement, hence `cw:contentLocationEndStatementCBETA`.
2. A level-1 node is `bdo:partOf` the `bdo:Outline`, not an Instance.
3. BDRC's own PartType individuals are in its types ontology (`http://purl.bdrc.io/ontology/types/PartType/`, imported by `bdo.ttl`, not fetched). Mapping our part types to them (品 → chapter?) is an open point.

## Node URIs and the id history

A node's **content key** is sha256 over (parent's content key, `heading_src`, `commentary.explained`, `root_text.start`). Siblings that tie on all of these get their occurrence number in the key. The key has no id and no `sibling_index`, so a node renumbered by an inserted sibling keeps its key. The history maps outline identity (`<root_text_id>/<scheme_id>`) → content key → URI:
```json
{"schema": "cw-export-id-history/1",
 "outlines": {"T09n0262/kuiji-xuanzan": {"uri": "<base>outline/T09n0262/kuiji-xuanzan", "nodes": {"<sha256>": "<base>node/<uuid>"}}}}
```
A key already in the history keeps its URI. A new key gets `uuid5(NAMESPACE_URL, "<base>node/<identity>#<key>")`, so an export with no history is still deterministic and an unchanged outline always gets the same URIs. Entries are never deleted, so a URI is never reused for another node, and reverting an edit restores the old URI. Limitation (v0): editing a heading or an explained locator mints a new URI for that node and its whole subtree, because the key chains through the parent. Tests: re-export, insertion of a sibling at level 1 and at level 2, an edited heading and its revert, tied siblings.

## Guards

1. `metadata.eval_only` must be `false`, and `metadata.licence.id` must be set (the schema makes a null licence imply eval-only).
2. Registered golds that are out-of-domain (X0268, P1573, D8842, T1605, T1602) or eval-only (the sdp golds under `data/raw/`) are refused. The match is on the path (the CLI checks it before reading the file), `metadata.source_file`, `text_id` + `scheme_id`, or `root_text_id` + `scheme_id`, against `data/eval-sets.json`. v0 refuses OOD golds even after the freeze. The plan allows them then (M9 accept), which needs a `frozen` path through this guard.
3. **Model-only nodes** (`origin: inferred` under a `model-*` scheme, D21) are withheld unless `allow_model_only_levels` ≥ their level. The default, 0, means never (the per-depth gate, plan §5). Their ids are listed.
4. **Split spans.** Without `frozen`, a node below levels 1–2 is withheld when any of its CBETA locators lies in a test or reserve span of a split text (T1718, T1723; `common.splits.split_of_line`). Design §2.4 says no stage reads those spans, and §3 treats levels 1–2 of the Kuiji gold as structure. Only the count is reported, since ids would reveal the tree shape of an answer key. As a result, the committed Kuiji gold exports as its skeleton plus the 陀羅尼品 subtree, which is what M9 accepts.

A withheld node takes its subtree with it. Siblings keep their source `sibling_index`, so `bdo:partIndex` may have gaps where nodes were withheld.

## Round trip

`load` reads the shape `export` writes; it is not a general JSON-LD processor, and the stage has no RDF library. For every exported node it rebuilds the fields that zh-kepan names, in document order (sorted by `partTreeIndex`):
- id, path and level (from `partTreeIndex`), and parent (from `partOf`, checked against the index);
- `sibling_index`, `heading_src`, `heading_en`, `origin`, `confidence`, `evidence`;
- the commentary locators, and root-text start / end / basis / end_basis / raw / text_id;
- `child_count_announced`, `extent_announced`, `flags`, `display_label`, `node_class`, `part_type`, `source_node_id`, the node-level `scheme_id`;
- the node's URI.

It also returns the outline's attribution. Tested on the synthetic `tests/fixtures/outline-zh/minimal.json` and on the Kuiji gold's allowed part (levels 1–2 without notes + the 陀羅尼品 subtree, filtered in the test).

## Open design points (plan §5 and Appendix H item 21)

- The base URI: `example.org` is a placeholder.
- Whether content-keyed URIs are the stable-URI policy they want.
- The announced/explained property names.
- Whether Zhiyi's 迹/本 lenses become separate outlines. For now a node-level `scheme_id` is exported as `cw:schemeId` inside one outline.
- Whether DharmaNexus `segmentnr` is the join key to parallels.
- The PartType mapping.

Not in v0: the catalogue backbone (`cbeta-metadata` T.json, MIT, R08 F39; DILA authorities, R08 F37/F38/F49) and its licence partition from the CBETA-derived (NC) outlines.
