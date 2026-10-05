# Output contract of the resolver

Part of the resolver's system prompt (read at runtime by `outline/resolver.py`) and the reference a Claude Code session follows when it answers `llm/requests/<hash>.md` with the interactive adapter. Derived from docs/outliner-design.md §5.6 and the zh-kepan outline schema `context/baseline/outline-schema-zh.json` (D15). The answer shapes are the JSON Schemas `pipeline/schemas/resolver-root-spans.schema.json`, `resolver-subdivide.schema.json` and `resolver-adjudicate.schema.json`; the gloss sub-step's is `gloss.schema.json`.

## What happens to an answer

1. The whole answer is validated against its JSON Schema. An answer that does not validate is logged (`llm/invalid.jsonl`) and nothing of it is used.
2. Each item is checked against the rules below. An item that breaks one is rejected and listed, with the reason, in the resolver report; the other items are merged.
3. After each merged item the outline is renumbered and two checks must pass: no explicit (or editorial, or imported) node lost or changed its heading, commentary lines, ancestors, level, node class or announced child count; and the outline validator (`scripts/validate_outline.py`) reports no error. An item that would break either is rejected.

## Rules for every item

- Refer only to node ids, report ids and lineheads that appear in the request. Lineheads carry no `:offset`.
- `start` ≤ `end` in text order. Spans stay inside the admissible range or the parent's span printed in the request.
- Siblings run in text order and do not overlap, except that consecutive siblings may share one boundary line.
- `confidence` is a number in [0, 1); an item with confidence 1 is rejected, because only the text's own statements are certain and those are already explicit nodes.
- `rationale` is not empty. It names the cue and quotes the Chinese.

## root-spans

`{"spans": [{node_id, start, end, confidence, rationale}]}`. Only nodes listed under "Nodes to resolve". The node keeps everything it had; its `locations.root_text` becomes `{start, end, basis: "inferred", end_basis: null}` (the commentary's lemma wording, if any, is kept in `raw`), the flag `unmapped` is removed, and a note records the adapter, model, confidence and rationale.

## subdivide

`{"divisions": [{parent_id, children: [{heading_src, start, end, depth, explained, confidence, rationale}], uncovered: [{start, end, kind, rationale}]}]}`. Only leaves listed under "Leaves to subdivide".

- `children` are in outline order: `depth` 1 is a child of the leaf, `depth` d + 1 a child of the nearest depth-d division before it (at most depth 3). Every divided node has at least two children, which lie inside its span in text order.
- Explained lines run in outline order from the leaf's: none comes before that of a node listed before it (the outlined text places nodes by them). An answer that breaks this is rejected.
- `uncovered` lists the lines of the leaf's span that no depth-1 division covers. They run in text order with the depth-1 divisions, without overlap except one shared boundary line. `kind` `paratext` marks lines that belong to no division; `kind` `overrun` marks lines that belong to a division the outline does not list. Overruns are listed in the resolver report (`overruns`) for review. No span of an existing node changes.
- `children: []` with `uncovered` lines changes nothing in the outline and is listed in the report (`reported`), with its overruns.
- A window of a too-long leaf: depth-1 divisions and uncovered ranges that begin in the window's core. Those that begin outside it are dropped and counted in the report (`windows`). An uncovered range that runs on past the lines shown ends at the last line shown.
- The pipeline joins the windows of a leaf into one division. Each division, and each uncovered range that runs on, ends on the line before the next division or uncovered range begins (on that line itself when the model ended the division there). The last one ends at the leaf's end.
- A window whose answer breaks a rule is rejected and adds no boundary: the division before it runs on, and lines before the leaf's first division stay uncovered. When the windows yield a single division, the leaf reads as one unit and is listed under `reported`, with its uncovered ranges.

Every child becomes a new node:

| Field | Value |
|---|---|
| `origin` | `inferred` |
| `confidence` | yours (< 1) |
| `evidence` | your rationale |
| `heading_src` | yours; `heading_en` stays empty for the gloss sub-step |
| `node_class` | the leaf's |
| `scheme_id` | the project's scheme, or `model-<first 8 hex of the prompt sha256>` when none is given |
| `locations` | sūtra mode: `root_text {start, end, basis: "inferred"}`, commentary `explained` = your `explained` (or none); self-outlining mode: `root_text {start, end, basis: "inferred"}`, commentary `explained` = your `explained` (a line inside the child's span); when you give null, its `start`, or the explained line before it in outline order when that is later and still inside its span |
| `notes` | adapter, model, task and request hash |

## adjudicate

`{"decisions": [{report_id, decision, target_node_id, children, confidence, rationale}]}`. `ignore` changes nothing and is listed in the report. `attach` adds `children` (one level, without `depth`) under `target_node_id` as subdivide adds its children, with commentary `announced` = the entry's line; the target must exist and have a span, the children must lie inside it, and they may not interleave with the target's existing children (they go wholly before or wholly after them).

## What you never do

Rename, move, reorder, merge or delete a node; add a node above an existing node; change a node you were not asked about; invent lineheads.
