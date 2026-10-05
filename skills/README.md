# skills/ — Claude skills we author

Kurt Keutzer's Tibetan workflow is built from Claude skills (`tibetan-sabcad-outliner`, `variorum_skill`, `sentence-segmenter-skill`, `chunking-skill`). This repository mirrors that: each skill is a directory with `SKILL.md` (frontmatter: name, description) plus reference files. Skills wrap the deterministic parts of `pipeline/` and add the model-assisted parts as instructions.

| Skill | Counterpart | Status |
|---|---|---|
| `chinese-kepan-outliner/` | `tibetan-sabcad-outliner` | v1 (2026-09-27): procedure over the pipeline CLIs, interactive resolver loop, references. Its reference files are those of the frozen outliner that E07 ran (tag `outliner-v1-frozen-2026-10-03` in the development repository); `SKILL.md` has had documentation edits since. The procedure is ours: it follows the Tibetan workflow's output format and was not derived from the text of the Tibetan skill |
