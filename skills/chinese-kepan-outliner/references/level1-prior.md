# Level-1 prior

Part of the resolver's system prompt (read at runtime by `outline/resolver.py`; docs/outliner-design.md §5.3 calls this "a prior for the resolver's prompt, not a rule"). Sources: R01 F2 and F17 in `context/research/R01-kepan-tradition-and-coverage/findings.md`, both PARTIAL.

What the top level of a sūtra's kēpàn usually looks like:

- The tripartition 序分／正宗分／流通分 (introduction, main teaching, dissemination) is the dominant default level-1 scheme of Sui–Tang and later sūtra commentaries (R01 F2, PARTIAL). Among the works of the Taishō 經疏部 whose first fascicle announces a level-1 division, about nine in ten are three-fold (R01 F17, PARTIAL: 53 of 59 in a single-reader adjudication; a re-reading puts the announcing works at 60–61, so the counts are soft by one or two, the proportion is not).
- It is a prior, not a rule. Two-fold and five-fold top levels occur, some commentaries offer two alternative schemes, some state the division only in a later fascicle, labels vary (教起因緣／聖教所說／依教奉行, 由序／正體／流通), and a level-1 boundary can fall inside a chapter (品) rather than at its edge (R01 F2, F17).
- The top level belongs to the commentator: different commentaries divide the same sūtra differently (R01 F1, F2).

How to use it here:

- With a commentary, the level-1 division is the commentator's. It is either already in the outline (explicit, or editorial from the project's declared scheme) or out of reach of this step: you never add nodes above existing ones.
- Without a commentary (a model-only run), prefer a three-fold reading when the text has a recognisable opening frame and closing (序 … 正宗 … 流通), and say in the rationale that the prior, not the text, supplied the label.
- Never force three parts where the text articulates two, four or five.
