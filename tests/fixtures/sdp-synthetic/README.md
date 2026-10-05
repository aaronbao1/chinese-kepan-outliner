SYNTHETIC — every file in this folder is invented test data in the *format* of sdp.chibs.edu.tw (法華經數位資料庫) output; none of it is copied from sdp or from any real text (rule 1 of "Rules for gold data" in `data/EVAL-SETS.md`: sdp is eval-only, so a committed fixture in its format must be synthetic and say so in its first line).

# tests/fixtures/sdp-synthetic/

Input for `tests/unit/test_gold_sdp.py`, which runs `chinese_workflow.eval.gold.sdp` on two fictional documents: a root text `T9999` (CBETA-style file id `T99n9999`) and its commentary `T9998` (`T99n9998`). Every heading, text and line anchor was written for this fixture; generic 科判 labels such as 通序, 別序, 長行, 偈頌, 正宗分 are ordinary terms and coincide with labels sdp also uses, but no heading, text or line was copied from sdp. The line texts the importer checks the HTML against are given in the test itself (`SYN_ROOT_LINES`, `SYN_COM_LINES`).

| File | Shape copied from | What it exercises |
|---|---|---|
| `tree-T9999-full.json` | `data/raw/dila-sdp/tree-T0262-full.json` (scripts/sdp_tree.py) | 15 nodes, 3 levels; tree text of heading-only nodes differs from the HTML heading (as sdp's 品 nodes do) |
| `T9999-juan1.html`, `T9999-juan2.html` | sdp `getHtml` pages of T0262 | nested content divs; a heading-only node with a bare heading (`T9999D01_002`); a node whose text starts before its first anchor (`T9999D03_002`); a prose node with no anchor of its own (`T9999D03_006`); a verse block and a node starting inside verse without an anchor before its first text (`T9999D03_005`); link2oth `文句` links, one to a non-commentary id, one malformed concatenation (`T9998D02_004T9998D02_009`); a server message after 】 (`T9999D02_002`); a div left open at a page end and continued as bare text on the next page; a bare heading matching no tree node (【附文】); a heading-only leaf with only a bare heading (`T9999D02_005`) |
| `tree-T9998-full.json` | `data/raw/dila-sdp/tree-T1718-full.json` | a `fetch_error` node (`T9998D02_002`) whose subtree is recovered from the HTML, one child on the next page |
| `T9998-juan1a.html`, `1b`, `2b` | sdp `getHtml` pages of T1718 (卷-halves) | page `2a` deliberately absent: node `T9998D02_003` falls in the gap; text before the first anchor of the first node; text inserted by sdp and absent from the CBETA line (`合成品第一` before `T9998D01_002`'s first anchor, as sdp inserts 序品第一 before T1718D01_003's) |

Links: `T9999D01_001` → `T9998D02_004` is deliberately wrong (the headings differ); `T9999D03_007` → `T9998D03_002` shares a heading but lies outside its parent's span in the commentary tree.
