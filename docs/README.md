# docs/

Design and reference documents. The code is described stage by stage in [`../pipeline/README.md`](../pipeline/README.md) and the README of each stage under `pipeline/src/chinese_workflow/`; the evaluation data and splits in [`../data/EVAL-SETS.md`](../data/EVAL-SETS.md); the experiments in [`../experiments/README.md`](../experiments/README.md).

| Document | What it is |
|---|---|
| [`outliner-design.md`](outliner-design.md) | Module-level design of the outliner as built and evaluated (v1): stages, algorithms, file contracts, command lines, the split guard and the scorer's rules. Its section "Output formats" describes the rendered outline (Markdown and Word) and the interlinear chunk format; §14 lists the design decisions and their defaults. Start here. |
| [`architecture.md`](architecture.md) | The pipeline-level architecture as built: data flow, the run directory, stage contracts, the outline artefact, plugging the outline back into the text, the experiments, and what is not built (the `context` and `translate` stages are stubs). For module-level detail, `outliner-design.md` and the stage READMEs take precedence. |
| [`chinese-workflow-mapping.md`](chinese-workflow-mapping.md) | Where the Chinese pipeline diverges from the Tibetan workflow it parallels, and why: the D-codes (D1–D17, D20, D21) that code comments and records cite, and D15 in detail, the `zh-kepan` extension of the outline schema. |
| [`glossary.md`](glossary.md) | Terms: the Tibetan workflow's names for the artefacts (*independent outline*, *outlined-text*, *chunk*, …), the Chinese-side terms, the pipeline's and the scorer's own terms, and a few Tibetan-side terms for comparison. |

Some code comments and records cite planning documents, a specification and research notes (R-codes, Task N, plan §). Those live in the development repository and are not part of this copy; [`../README.md`](../README.md#codes-in-comments-and-records) explains the codes.
