# segment — outlined-text → sentence boundaries

HYPOTHESIS (R02): classical Chinese has no native sentence punctuation; CBETA supplies modern punctuation (。，；：) that is editorial and inconsistent across texts, and some texts are unpunctuated. This stage decides sentence boundaries the chunker will respect. Options to evaluate: (1) trust CBETA punctuation; (2) punctuation + heuristics; (3) model-assisted. Record which was used in the output metadata.

Hard boundaries the segmenter never crosses: outline leaf spans (from the outlined-text sidecar); verse line groups — a stanza or couplet counts as one unit, matching the Tibetan workflow, which treats a couplet or a four-line verse as one semantic unit (Manual 2.2 §3b2) (HYPOTHESIS re CBETA's verse markup); the switch between a quoted lemma and its gloss in commentaries (經曰 … / 贊曰 …, HYPOTHESIS re markers).

**Output:** `sentences.json` = `[{id, char_start, char_end, kind: prose | verse_line | verse_stanza | lemma | gloss}]` plus the strategy and config used.

## Implementation (strategies 1–2, 2026-09-27)

`segment.py`: `run(target: InputText, outlined_text: dict | None = None, *, strategy=2) -> sentences/1`, `validate(doc)` (jsonschema, `pipeline/schemas/sentences.schema.json`), `check(doc, target, outlined_text)` (invariant problems: contiguous coverage to the end of the text, no empty sentence, no sentence across an outlined-text boundary, `node_id` = the span holding the sentence).

```
python -m chinese_workflow.segment --target SOURCE [--span FIRST..LAST] [--role root|commentary]
       [--outlined-text PATH] [--strategy 1|2] [--frozen TAG] --out sentences.json
```

Without `--span`/`--role` the outlined-text's target span and role are used; the outlined-text's `target.sha256` must equal the target text's. The CLI applies the split guard, validates against the schema and refuses to write when `check` finds a problem.

Rules (details in the module docstring):
- Coverage: from the first placed outlined-text span (0 without one) to the end of the text; text in gaps or after the last span gets `node_id: null`.
- Strategy 1: a sentence ends after 。？！； plus the terminators, closing quotes/brackets and spaces that directly follow (`「甚多，世尊。」` is one sentence). All `prose`.
- Strategy 2 (default) adds breaks and kinds: `heading` (a `head`/`jhead` whose text stands at its offset; a line equal to a `cb:mulu` label, with or without its leading number); a break at every `cb:mulu` position; `verse_line` (each `in_verse` line cut at its caesuras and after inner U+3000 runs, i.e. one unit per pāda in Taishō verse); in commentaries, `lemma` (經「…」 at a sentence start, followed by 。 or directly by a gloss marker, one sentence whatever it holds) and `gloss` (from a gloss marker 贊曰 / 述曰 / 釋曰 or a lemma until the next heading; `prose` before).
- Punctuation-only pieces join the previous sentence, or the next one when a span boundary separates them from the previous.

Decisions:
- Both strategies keep outlined-text span boundaries. The design lists that break under strategy 2, but `sentences/1` promises it for every file and the chunker needs it; the strategies differ only in the heading, verse and lemma/gloss breaks.
- The lemma/gloss markers are checked on T34n1723 only (玄贊: `經「…」。贊曰：`). 述曰 / 釋曰 and other lemma forms (「…」者, 經云, 論：) are HYPOTHESIS and not recognised as lemmas.
- The dhāraṇīs of T0262 are `p` with U+3000 between items, not `lg`, so they are `prose`.

Limits: an unpunctuated passage (a dhāraṇī, a `原書標點`/`基本句讀` text) gives one sentence per hard segment; line-level `in_verse` treats a line that opens an `lg` mid-line as verse; without `p` starts in `ingest.lines` a paragraph with no final terminator runs into the next one (T0262 0058b19–c04).

Tests: `tests/unit/test_segment.py` (T1723 dev excerpt with and without a synthetic outlined-text, the T0262 陀羅尼品 excerpt, synthetic line records for merges, mulu headings, lemma forms and verse spaces; whole-file T09n0262 and T32n1666 when `data/raw/` is present).
