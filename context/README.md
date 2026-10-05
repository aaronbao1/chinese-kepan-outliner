# context/

This folder holds the two outline schemas, both in `baseline/`. `outline-schema.json` is the base *independent-outline* schema, modelled on the outline format of Kurt Keutzer's agentic Tibetan translation workflow.
`outline-schema-zh.json` is the `zh-kepan` profile that extends it (a superset: every base document stays valid); every outline in this repository, the pipeline's output and the committed golds alike, validates against it (`scripts/validate_outline.py`).
The path `context/baseline/` is kept, although nothing else lives here, because the validator loads both files from it and the committed golds and recorded experiment outputs cite it.
