# tests/fixtures/cbeta-xml-p5/

Small, verbatim CBETA XML P5 files and line-range excerpts used as parser fixtures (E01). Bytes are untouched (CBETA punctuation and markup kept), headers intact; an
excerpt keeps whole lines of its source file and adds only the two closing lines named in its row.

| File | What | Source | sha256 |
|---|---|---|---|
| `G069n1977.xml` | 科始終心要 (佛教大藏經 vol. 69, no. 1977), 5,949 bytes: the smallest file in the corpus that carries `cb:mulu type="科判"` nodes — 15 科判-typed nodes on levels 1–5 plus 1 卷 node (16 `cb:mulu` in all); the whole tree is on file lines 79–93. Fixture for the explicit-division parser's 科判 path. | `cbeta-org/xml-p5` tag `2026R2` (commit `dbdea41071e1e260ad84b72faefd4587333cf76d`), path `G/G069/G069n1977.xml`; identical bytes in `data/raw/cbeta/G069n1977.xml` (`scripts/fetch_cbeta.sh`) | `52dbf25e7dac2e0de173b11780c18b78c8ffb6b85985b0bde296cb4493f5c5d6` |
| `T34n1723-excerpt-p0850a19-p0850b19.xml` | 妙法蓮華經玄贊 (Kuiji), the whole 陀羅尼品 commentary: 31 lines `T34n1723_p0850a19`–`T34n1723_p0850b19` (the T1723 dev span of the eval splits; nothing outside it), one `cb:div type="pin"` with its `cb:mulu`/`head`, the 三門分別 gate and the 經「…」。贊曰：… lemma divisions. 60,407 bytes: 56,505 of them are the unmodified teiHeader (its charDecl alone is ~55 KB), 3,902 the excerpt. Offline smoke fixture for the explicit-division parser. | Raw file lines 1–1562 (XML declaration, `TEI` start tag, whole `teiHeader`, `<text><body>`) and 19727–19758 (the 陀羅尼品 `cb:div`) of `data/raw/cbeta/T34n1723.xml` (xml-p5 tag `2026R2`, sha256 `8f73a6fb…94802ce`, `scripts/CHECKSUMS`), then the added lines `</body>` and `</text></TEI>`. Left out: the `back` apparatus (its targets, the body `anchor`s, are kept). | `8ef50108e70bc786cc68f3f652dfd9a4553776e0a0f2632082b1dfe72faeaa81` |
| `T09n0262-excerpt-p0058b08-p0059b27.xml` | 妙法蓮華經 陀羅尼品第二十六 (卷第七): 92 lines `T09n0262_p0058b08`–`T09n0262_p0059b27`, one `cb:div type="pin"` with `cb:mulu level="1" n="26" type="品"` (26 陀羅尼品), 103 inline notes, 5 `g` (all resolved via the header's charDecl), 1 `lg`. 42,742 bytes. The root text the T1723 excerpt comments on. | Raw file lines 1–447 (declaration, `TEI` start tag, whole `teiHeader`, `<text><body>`) and 5649–5743 (the 陀羅尼品 `cb:div`) of `data/raw/cbeta/T09n0262.xml` (xml-p5 tag `2026R2`, sha256 `c8975bef…c5df017`), then the added lines `</body>` and `</text></TEI>`. `back` left out. | `63d80b12a5cdcdf842f96f4cd5f63be474ca6b0e42b9fb07bbd696a3c6133cf8` |

Licence: CBETA releases 佛教大藏經 (G) and the other 類別 A collections under CC BY-NC-SA 4.0 with the conditions in its
版權宣告 (reproduced in `data/reference-outlines/NOTICE` from the snapshot `data/raw/cbeta/LICENCE-NOTICE.txt`; the file's own header says "Available for non-commercial use when
distributed with this header intact."). The same terms cover 大正藏 (T). The fixtures are redistributed here for
non-commercial research with their headers unmodified (G069n1977 whole, the two excerpts as described above); keep it
that way. This is why the T1723 excerpt exceeds the ~50 KB fixture guideline (tests/README.md): its header alone is
56,505 bytes.

Excerpt recipe (run from the repo root; `tests/unit/test_kepan_cases.py` rebuilds both from the raw files and
compares bytes):

```
python3 -c '
import pathlib
def cut(src, ranges, out):
    L = pathlib.Path(src).read_text(encoding="utf-8").split("\n")
    parts = [ln for a, b in ranges for ln in L[a - 1 : b]] + ["</body>", "</text></TEI>", ""]
    pathlib.Path(out).write_text("\n".join(parts), encoding="utf-8")
cut("data/raw/cbeta/T34n1723.xml", [(1, 1562), (19727, 19758)], "tests/fixtures/cbeta-xml-p5/T34n1723-excerpt-p0850a19-p0850b19.xml")
cut("data/raw/cbeta/T09n0262.xml", [(1, 447), (5649, 5743)], "tests/fixtures/cbeta-xml-p5/T09n0262-excerpt-p0058b08-p0059b27.xml")
'
```

## Ingest oracle counts (recounted 2026-09-22)

The counts the ingest tests rely on, recounted from the raw 2026R2 files (`scripts/fetch_cbeta.sh`;
T09n0262.xml sha256 `c8975bef…c5df017`, T34n1723.xml sha256 `8f73a6fb…94802ce`, full digests in `scripts/CHECKSUMS`).
They agree with R02 F19/F21; no difference was found.

| File | `app` | `note[@type="orig"]` elements | distinct orig ids | all `note` | own-edition `lb` in `text/body` (= lines) | `cb:mulu` (non-卷 / `works/toc` nodes) |
|---|---|---|---|---|---|---|
| T09n0262.xml | 945 | 1,015 | 1,004 | 2,297 | 5,374 (+35 repeated in `back`: 22 inside `lem`, 13 inside the `cb:tt` apparatus) | 40 (33) |
| T34n1723.xml | 2,260 | 2,058 | 2,058 | 5,920 | 17,960 (+50 repeated in `back`, all inside `lem`) | 58 (38) |
| G069n1977.xml (this directory) | 0 | 0 | 0 | 1 (inline) | 17 | 16 (15) |

Command (run from the repo root; the lb/mulu columns are what `tests/unit/test_ingest_lines.py` asserts through
`chinese_workflow.ingest.lines`):

```
python3 -c '
import sys
from lxml import etree
T = "{http://www.tei-c.org/ns/1.0}"
for p in sys.argv[1:]:
    r = etree.parse(p).getroot()
    orig = [n for n in r.iter(T + "note") if n.get("type") == "orig"]
    print(p, "app=%d" % sum(1 for _ in r.iter(T + "app")), "note[@type=orig]=%d" % len(orig),
          "distinct_orig_ids=%d" % len({n.get("n") for n in orig}), "note_all=%d" % sum(1 for _ in r.iter(T + "note")))
' data/raw/cbeta/T09n0262.xml data/raw/cbeta/T34n1723.xml
```

(`grep -o '<app[ >]' | wc -l` and `grep -o '<note[^>]*type="orig"' | wc -l` give the same 945 / 1,015 and 2,260 / 2,058.)
