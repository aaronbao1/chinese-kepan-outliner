# chunk — outlined-text + sentences → outlined-and-chunked-text

Kurt's spec (Agentic Tibetan 1.0 §1f Step 3): chunks no larger than 4–6 sentences, separated by blank lines, guided by the outline. Our additional rules (recorded as divergence D6 in `docs/chinese-workflow-mapping.md`):
- a chunk never crosses an outline leaf boundary; a leaf longer than 6 sentences is split. **Revised 2026-09-17 (R01/R07):** kēpàn leaves are far smaller than a chunk (X0231: 13,831 leaves, ≈1.2 sūtra sentences each; Kuiji leaves of one word or line), so leaves are hard *lower* bounds and the chunker **merges sibling leaves upward** within the same parent until the 4–6-sentence bound; the invariant becomes "a chunk boundary never splits a sub-chunk leaf", defined on the explained locator (R06). Each chunk records the leaf ids it unions; the smallest ancestor covering the chunk is the context key;
- stretches the outline does not cover (for example a text whose outlineable structure stops partway through) are `unoutlined` pseudo-nodes and get fixed windows of ≤ 6 sentences, tagged `fallback: unoutlined` so the degradation is visible downstream. R07 found that in T1718/T1723 nested division persists to the end; what occurs instead is no-gloss leaves, 下皆准知 pointers and unmapped verse — carried as node flags (`no_gloss`, `parallel_ref`, `unmapped`) rather than as `unoutlined`;
- a character budget (`size_chars`, 180 by default, `none` to turn it off) caps a chunk besides the sentence cap, because sentence length in editorially punctuated classical Chinese varies widely (HYPOTHESIS); the default is not tuned (E05, not yet run, is meant to set it).

**The Tibetan format.** In the Tibetan workflow's outlined-and-chunked-text, chunks are single paragraphs separated by blank lines, and the outline is interleaved two ways: where a parent enumerates its children, the child headings are *lifted out* of the running text as `1₁B₂) heading` lines; where a node is taken up, an inserted marker `[1₁B₂) heading [003B]]` carries the node's **first-appears** folio, not its explained folio. Its "4–6 sentences" works in practice as a length budget cut at strong boundaries (HYPOTHESIS). Our `chunks.md` reproduces this typography with CBETA locators in place of folios, and our size rule is a character budget plus a sentence cap (`docs/outliner-design.md`, "Output formats").

The stage is deterministic code over `sentences.json` and the outlined-text spans; the Tibetan workflow has the model do this step (its Project Instructions describe how to segment sentences, plus the `chunking-skill`), so this is divergence D14. The `chinese-chunker` skill calls this module rather than prompting for the chunking.

Which text is chunked follows the outline's `target_role`: the root sūtra (commentary passage becomes context) or the commentary itself (root lemma becomes context).

**Output:** `chunks.md` (Kurt's format: blank-line separated chunks, the outline annotation printed before the first chunk of each node) and `chunks.json` carrying, per chunk: chunk id, outline path, leaf id, topic-category, role, source location range, sentence ids, text, fallback tag.

## Implementation (2026-09-27)

**Input:** `outline.json` (zh-kepan), `outlined-text.json` (`outlined-text/1`), `sentences.json` (`sentences/1`) and the target `InputText` (`chinese_workflow.ingest.text`); the three JSON files must carry the target's sha256 and length, or the stage refuses them. **Output:** `chunks.json` (`chunks/1`, `pipeline/schemas/chunks.schema.json`), `chunks.md`, `chunks.docx`.

```
python -m chinese_workflow.chunk --outline outline.json --outlined-text outlined-text.json \
    --sentences sentences.json --target T34n1723 [--span FIRST..LAST] --out DIR \
    [--sentence-cap 6] [--size-chars 180|none] [--frozen TAG]
python -m chinese_workflow.eval.chunk_invariants DIR/chunks.json outlined-text.json sentences.json \
    [--outline outline.json] [--md DIR/chunks.md]
```

Modules: `chunker.py` (`build_chunks`, `validate_chunks`, `run`), `render.py` (`render_md`, `parse_md`, `render_docx`), `__main__.py` (CLI). The invariant checker is `eval/chunk_invariants.py` (`check`); it does not import this package and re-implements the `.md` reader/writer independently.

Rules as built (the defaults are proposals; E05, not yet run, is meant to set the budget):

- **Units and coverage.** Units are the outlined-text spans: a leaf's text, or a parent's preamble (its text before its first child). The chunks tile the whole target text `[0, len)`; whatever no span covers (reported gaps, text before the first or after the last node) is `unoutlined`.
- **Merge rule.** A unit's merge group is the node that owns it as a parent: a preamble belongs to its own node, a leaf to its parent. Maximal runs of consecutive units with the same merge group are packed greedily in text order while the chunk stays within `sentence_cap` (6) sentences and `size_chars` (180) characters. So a parent's preamble (typically the lead-in that announces the children) merges with the leaf children that follow it, and sibling leaves merge with each other. A child that has children of its own ends the run, and nothing merges across parents. Top-level leaves are not merged with each other, because no node would cover the result. A chunk's `node_id` is the unit's own node, or the merge group when it unions several units.
- **Oversize units.** A unit that alone exceeds the budget is split at sentence ends (`fallback: "split-leaf"`, also for an oversize preamble) into as many windows as a greedy cut needs, evened out in sentence count (20 sentences at cap 6 give 5 + 5 + 5 + 5). A single sentence longer than `size_chars` stays whole. Unoutlined stretches are cut the same way (`fallback: "unoutlined"`, `node_id: null`).
- **Markers.** A node is taken up when its subtree owns text in the target. Its marker `[<indicator_display>) <heading_src> <locator>]` precedes the chunk holding the first character of that text. The locator is `commentary.announced`, else `commentary.explained`, else `root_text.start`, with any `:offset` kept. When a chunk unions several units, the markers of all of them stand before it in outline order: this is where our merged chunks differ from the Tibetan format, whose chunks never hold two nodes' text.
- **Announcements.** Every node with `commentary.announced` gets a line `<indicator_display>) <heading_src>` after the chunk holding that position when the position lies in the target (commentary target, and self-outlining root targets). Otherwise (a root target in sūtra mode) the line goes after the parent's first chunk, and failing that just before the node's own first chunk. Nodes that still cannot be placed are listed in `metadata.unplaced_announcements`.
- **`chunks.md`.** Each run is marker lines, then one text line, then announcement lines (Kurt's K T A A…), and runs are separated by one blank line. `parse_md` reads runs positionally, so `parse_md(render_md(x))` returns `x`'s markers, announcements and chunk texts exactly. `render_md` refuses content that would not read back, such as a line break in a heading or a chunk text that reads as a marker. `chunks.docx` has the same lines, with the indicator's level digits as `w:vertAlign="subscript"` runs. Chunk ids are positional (`c1`…).
- **`run`** checks the target lines with the split guard (test and reserve lines need `--frozen`), refuses an outlined-text whose `outline_ref.sha256` is not the given `outline.json`, validates `chunks.json` against its schema, and records `generated_by`, input hashes and the guard report in `metadata`.

Tests: `tests/unit/test_chunk.py` and `tests/unit/test_chunk_invariants.py`. They use a synthetic outline over the T1723 dev excerpt (陀羅尼品 → 三門分別 {來意, 釋名, 解妨}, 品文分三 {3 children}) and a root-target outline over the T0262 excerpt, with a synthetic anchor and sentence splitter.

Known limitations:
- Packing is greedy. It does not look ahead to balance merged chunks, and a lemma (經「…」) can end one split-leaf window while its gloss (贊曰) starts the next: segment strategy 2 and deeper outline nodes are expected to make this rare.
- Announcement placement uses the announced locator's line (and offset, when given). A bare linehead on a line that is cut between two chunks places the line after the earlier chunk.
- The sentence cap counts `sentences.json` units only. Characters that no sentence covers form sentence-less atoms and count toward the length budget only.
