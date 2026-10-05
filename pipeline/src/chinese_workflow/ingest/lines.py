"""chinese_workflow.ingest.lines — CBETA XML P5 line extractor (first piece of the ingest stage).

Splits one CBETA TEI P5 file into the typographic lines of its own edition and gives each line
its composed CBETA linehead, so that dataset builders can anchor gold-outline nodes to Taishō /
Xuzangjing lines and every later stage can cite a location as (linehead, char offset) — the
coordinate system fixed in ingest/README.md.

Input : one file of cbeta-org/xml-p5 at tag 2026R2, e.g. data/raw/cbeta/T09n0262.xml,
        data/raw/cbeta/xml-p5/X/X11/X11n0268.xml, tests/fixtures/cbeta-xml-p5/G069n1977.xml.
Output: one record (a dict) per `lb` of the file's own edition, in document order:
  linehead      "{TEI/@xml:id}_p{lb/@n}", e.g. "T09n0262_p0001c05" (R02 F6/F13)
  n, ed         the lb's @n and the file's canon (the @ed token that made this lb a line)
  alt           [{"ed", "n", "offset"}]: lbs of other editions falling on this line (X files
                interleave <lb ed="R017"/>, R02 F6/F28) and extra tokens of a multi-token @ed
  juan          int from the last milestone[@unit="juan"]/@n (None before the first one)
  text          the line's reading text (rules below)
  inline_notes  [(start, end)] spans of `text` that come from inline notes
  excluded_notes [{"offset", "place", "type", "text"}]: notes kept out of `text` (rule below),
                recorded where they sit: offset = position in `text` the note would occupy;
                place/type = @place/@type verbatim; text = full note text, also when the note
                runs over an lb (it is recorded once, on the line where it starts)
  gaiji         [{"offset", "ref", "via"}], one per g;
                via = unicode | normal_unicode | normalized | text | placeholder
  unclear       [offset] of each empty `unclear` (rendered "[?]")
  caesuras      [offset] of each `caesura` (verse segment boundary; renders as nothing)
  mulu          [{"level", "type", "n", "text", "offset", "div_type"}]: cb:mulu starting on
                this line, @type/@level passed through verbatim (level int, None when absent,
                i.e. the 卷 system); div_type = innermost enclosing div @type (R02 F11/F17/F27)
  heads         [{"kind": "head"|"jhead", "text", "offset"}]: headings starting on this line,
                full text even when the heading runs over several lines
  juan_marks    [{"fun", "n", "offset"}]: cb:juan open/close (skipped inside note/lem, R02 F1)
  in_verse      True when any of the line's text lies inside lg/l, or the lb itself does
  div_types     enclosing cb:div (or div) @type stack, outermost first, taken where the line's
                first content starts (so the line opening a 品 carries "pin"), or at the lb
                for an empty line

Reading-text rules (from R02 F1/F5/F19/F21 and a scan of every text/body of the 5,017-file
2026R2 clone):
  * Text after an own-edition lb belongs to that line until the next one, across element
    boundaries. Newline, CR and tab are XML layout (CBETA writes a newline before every lb/pb)
    and are dropped; nothing else is.
  * CBETA's punctuation is kept exactly; normalization is a later, configured step.
  * `app` never occurs in a 2026R2 body (the Taishō apparatus is stand-off in `back`, R02 F21),
    so the body already carries the lemma; should an inline app appear, lem is read, rdg skipped.
  * `note` stays in `text` only when @place contains "inline" (inline, inline2: small-print
    text, marked in inline_notes). Every other body note is kept out of `text` but recorded in
    `excluded_notes`, never dropped. In 2026R2 text/body these are 3,304 place="interlinear"
    notes in 24 X files and 33 type="authorial" (no @place) notes in 13 Y files; T bodies have
    none (census of all 5,017 files, 2026-09-22; inline 1,098,618, inline2 10). A note inside an
    already-excluded region goes with that region and is not recorded: the only case is X23n0438,
    whose 47 interlinear notes gloss Siddham inside a cb:t xml:lang="sa-Sidd" (so 3,290 recorded
    corpus-wide).
    Interlinear notes can be the kēpàn itself: X12n0281 楞嚴經圓通疏 has no 科判-typed cb:mulu
    (21 cb:mulu, none 科判) and prints its 科 as 2,123 interlinear notes, e.g. line 0697a24 is
    ○<note place="interlinear">初、序，分二：初、通序六：初、指法體。</note>如是。
    ○<note place="interlinear">二、顯能聞</note>我聞。○…三，明機感…一時。… so its text is
    "○如是。○我聞。○一時。…" and the labels are in excluded_notes at offsets 1, 5, 9, … —
    a kēpàn source the cb:mulu-only 科判 census (R02 F15/F28: 4 files) misses. X26n0566
    (初標觀行 / 二標斷惑 / 三標證真), X62n1196 (一發心持名願 …) and X25n0488 (初斷行施住相疑。 …
    二十七、斷入寂如何說法疑。, mixed with glosses) carry section labels the same way; other files
    use interlinear notes for glosses, readings and Siddham. Observed on the 2026R2 files
    (2026-09-22), not yet an R02 finding.
  * `g`: charDecl mapping[@type="unicode"], else mapping[@type="normal_unicode"], else charProp
    "normalized form", else (no charDecl entry) the element text when not a Private Use code
    point, else "[#<id>]" (e.g. "[#CB01234]", "[#SD-A5A9]"). Every g in `text` is listed in
    `gaiji` with the route taken, so no character substitution is silent. A g inside a mulu label
    or an excluded note is resolved the same way but not listed (`gaiji` offsets index `text`).
  * `cb:mulu` content is CBETA's editorial TOC, not copy text: reported in `mulu`, never in text.
  * `cb:tt` (parallel Siddham / Rañjana / Sanskrit + Chinese) keeps only the cb:t whose xml:lang
    is zh-* or absent; any element other than note/p/lg with @place or @cb:place containing
    "foot" is excluded; figDesc is excluded; sic/orig inside choice are excluded (no choice
    occurs in a 2026R2 body).
  * `space` renders as quantity x U+3000 (quantity="0": nothing); an empty `unclear` renders as
    "[?]". Both are this module's conventions, not CBETA's.
  * lb with type="old" (Y canon) are ignored; lb whose @ed lacks the file's canon become `alt`.
  * Text before the first own-edition lb (none in T/X/G files) goes to Extraction.unanchored;
    mulu/head/juan markers and excluded notes seen before it are attached to the first line at
    offset 0, so every cb:mulu of text/body is reported exactly once.

Known shape of the output (checked on all 5,017 files of the 2026R2 clone, 2026-09-22: every file
parses, lines = own-edition lb of text/body in every file, nothing unanchored): lineheads are
unique in every file but not always monotonic — 52 files step backwards (T49n2035 96 times);
T09n0262 inserts its 附文 (T09 p. 198a–b) between 妙音菩薩品 and 普門品, so its lb sequence runs
0056c01 -> 0198a10 … 0198b11 -> 0056c02. Lines come from text/body only: `back` repeats lbs
(35 in T0262, 50 in T1723) and, in 8 files, 35 cb:mulu inside apparatus lem, all copies of body
nodes; they are not reported.

Text index: build_index() concatenates a line range (no separator) and maps (linehead, offset)
<-> global offset; find() / find_spans() locate a string in it, optionally ignoring punctuation
and spaces (Unicode categories P*, Z*, Cc, Cf) for punctuation-insensitive lemma matching.

Usage : python -m chinese_workflow.ingest.lines <xml>          JSON Lines, one record per line
        python -m chinese_workflow.ingest.lines <xml> --tsv    linehead<TAB>juan<TAB>text
        python -m chinese_workflow.ingest.lines <xml> --find 諸漏已盡 [--ignore-punct]
                                                               linehead<TAB>offset per hit

Provenance: markup inventory and anchoring rules from
context/research/R02-cbeta-xml-structure-markup/findings.md (F1, F6, F11, F17, F19, F21, F27,
F28); reads lb/mulu the way scripts/survey_cbeta_xml_p5.py does. Standard library plus lxml.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Iterator, NamedTuple

from lxml import etree

TEI_NS = "http://www.tei-c.org/ns/1.0"
CB_NS = "http://www.cbeta.org/ns/1.0"
_T = "{%s}" % TEI_NS
_C = "{%s}" % CB_NS
_XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

_LB, _PB, _ANCHOR, _MILESTONE = _T + "lb", _T + "pb", _T + "anchor", _T + "milestone"
_G, _SPACE, _CAESURA, _UNCLEAR = _T + "g", _T + "space", _T + "caesura", _T + "unclear"
_NOTE, _LEM, _RDG = _T + "note", _T + "lem", _T + "rdg"
_HEAD, _LG, _L, _DIV, _FIGDESC = _T + "head", _T + "lg", _T + "l", _T + "div", _T + "figDesc"
_CHOICE, _SIC, _ORIG = _T + "choice", _T + "sic", _T + "orig"
_MULU, _JHEAD, _JUAN, _CBDIV = _C + "mulu", _C + "jhead", _C + "juan", _C + "div"
_TT_T = _C + "t"  # a cb:t inside cb:tt

_LAYOUT = str.maketrans("", "", "\n\r\t")
UNCLEAR_MARK = "[?]"
SPACE_CHAR = "\u3000"  # IDEOGRAPHIC SPACE


def _is_pua(ch: str) -> bool:
    cp = ord(ch)
    return 0xE000 <= cp <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD


def is_punct(ch: str) -> bool:
    """True for what find(ignore_punct=True) skips: punctuation (P*), spaces incl. U+3000 (Z*),
    controls (Cc, Cf)."""
    cat = unicodedata.category(ch)
    return cat[0] in "PZ" or cat in ("Cc", "Cf")


def strip_punct(s: str) -> str:
    return "".join(ch for ch in s if not is_punct(ch))


# ------------------------------------------------------------------------------------------ header


def _char_table(root) -> dict:
    """{id: (resolved string, via)} from teiHeader charDecl (char and glyph entries)."""
    table = {}
    decl = root.find(".//%scharDecl" % _T)
    if decl is None:
        return table
    for ch in decl:
        if ch.tag not in (_T + "char", _T + "glyph"):
            continue
        cid = ch.get(_XML_ID)
        if not cid:
            continue
        maps = {}
        for m in ch.iter(_T + "mapping"):
            ty, val = m.get("type"), (m.text or "").strip()
            if ty and val.startswith("U+") and ty not in maps:
                try:
                    maps[ty] = chr(int(val[2:], 16))
                except ValueError:
                    pass
        normalized = None
        for prop in ch.iter(_T + "charProp"):
            if (prop.findtext(_T + "localName") or "").strip() == "normalized form":
                normalized = (prop.findtext(_T + "value") or "").strip() or None
        if "unicode" in maps:
            table[cid] = (maps["unicode"], "unicode")
        elif "normal_unicode" in maps:
            table[cid] = (maps["normal_unicode"], "normal_unicode")
        elif normalized:
            table[cid] = (normalized, "normalized")
        else:
            table[cid] = ("[#%s]" % cid, "placeholder")
    return table


def _header_info(root) -> dict:
    xml_id = root.get(_XML_ID) or ""
    m = re.match(r"[A-Z]+", xml_id)
    resp = {}
    for rs in root.iter(_T + "respStmt"):
        if rs.get(_XML_ID):
            resp[rs.get(_XML_ID)] = (rs.findtext(_T + "name") or "").strip()
    punct = root.find(".//%seditorialDecl/%spunctuation" % (_T, _T))
    has_punct = punct is not None
    return {
        "xml_id": xml_id,
        "canon": m.group(0) if m else "",
        "title": (root.findtext(".//%stitleStmt/%stitle[@level='m']" % (_T, _T)) or "").strip(),
        "header_date": (root.findtext(".//%spublicationStmt/%sdate" % (_T, _T)) or "").strip(),
        # editorialDecl/punctuation: 新式標點 | 原書標點 | AI 標點 | 基本句讀 (R02 F19)
        "punctuation": " ".join((punct.findtext(_T + "p") or "").split()) if has_punct else None,
        "punctuation_resp": resp.get((punct.get("resp") or "").lstrip("#")) if has_punct else None,
    }


# ------------------------------------------------------------------------------------------ walker


class _Ctx(NamedTuple):
    # hidden: content is not reading text (rdg, non-inline note, mulu, foot-placed, ...)
    hidden: bool = False
    captures: tuple = ()  # open buffers collecting mulu / head text
    divs: tuple = ()  # enclosing div @type stack
    verse: bool = False  # inside lg / l
    in_note: bool = False  # inside any note or lem (cb:juan guard, R02 F1)
    inline: bool = False  # inside a visible inline note


@dataclass
class Extraction:
    """Result of extract(): header info, line records, and any text found before the first line."""

    info: dict
    lines: list
    unanchored: list = field(default_factory=list)


class _Walker:
    def __init__(self, info: dict, chars: dict):
        self.xml_id = info["xml_id"]
        self.canon = info["canon"]
        self.chars = chars
        self.lines: list = []
        self.cur: dict | None = None
        self.parts: list = []  # text pieces of the current line
        self.length = 0  # len("".join(parts))
        self.fixed = False  # current line has content (div_types / juan frozen)
        self.juan: int | None = None
        self.inline_depth = 0
        self.inline_open: int | None = None
        self.pending: list = []  # (key, record) seen before the first line
        self.unanchored: list = []

    # -- line bookkeeping
    def _finish(self):
        if self.cur is None:
            return
        if self.inline_depth and self.inline_open is not None and self.length > self.inline_open:
            self.cur["inline_notes"].append((self.inline_open, self.length))
        self.cur["text"] = "".join(self.parts)
        self.inline_open = None

    def _new_line(self, lb, ctx: _Ctx, extra_eds: list):
        self._finish()
        n = lb.get("n") or ""
        rec = {
            "linehead": "%s_p%s" % (self.xml_id, n),
            "n": n,
            "ed": self.canon,
            "alt": [{"ed": e, "n": n, "offset": 0} for e in extra_eds],
            "juan": self.juan,
            "text": "",
            "inline_notes": [],
            "excluded_notes": [],
            "gaiji": [],
            "unclear": [],
            "caesuras": [],
            "mulu": [],
            "heads": [],
            "juan_marks": [],
            "in_verse": bool(ctx.verse),
            "div_types": list(ctx.divs),
        }
        self.lines.append(rec)
        self.cur, self.parts, self.length, self.fixed = rec, [], 0, False
        if self.inline_depth:
            self.inline_open = 0
        for key, item in self.pending:
            rec[key].append(item)
        self.pending = []

    def _touch(self, ctx: _Ctx):
        """First content on the current line freezes its div stack."""
        if self.cur is not None and not self.fixed:
            self.cur["div_types"] = list(ctx.divs)
            self.fixed = True

    def _offset(self) -> int:
        return self.length if self.cur is not None else 0

    def _attach(self, key: str, item: dict, ctx: _Ctx, touch: bool = True):
        """touch=False: the marker does not count as the line's first content (div_types is
        still taken where the reading text starts)."""
        if self.cur is None:
            self.pending.append((key, item))
        else:
            if touch:
                self._touch(ctx)
            self.cur[key].append(item)

    def _emit(self, s: str, ctx: _Ctx):
        s = s.translate(_LAYOUT)
        if not s:
            return
        for buf in ctx.captures:
            buf.append(s)
        if ctx.hidden:
            return
        if self.cur is None:
            self.unanchored.append(s)
            return
        self._touch(ctx)
        self.parts.append(s)
        self.length += len(s)
        if ctx.verse:
            self.cur["in_verse"] = True

    # -- traversal
    def walk(self, el, ctx: _Ctx):
        if el.text:
            self._emit(el.text, ctx)
        for child in el:
            self.visit(child, ctx)
            if child.tail:
                self._emit(child.tail, ctx)

    def visit(self, el, ctx: _Ctx):
        tag = el.tag
        if not isinstance(tag, str):  # comment / PI: its tail is emitted by the caller
            return
        if tag == _LB:
            self._lb(el, ctx)
            return
        if tag in (_PB, _ANCHOR):
            return
        if tag == _MILESTONE:
            if el.get("unit") == "juan":
                m = re.match(r"\d+", el.get("n") or "")
                self.juan = int(m.group(0)) if m else None
                if self.cur is not None and not self.fixed:
                    self.cur["juan"] = self.juan
            return
        if tag == _G:
            self._g(el, ctx)
            return
        if tag == _SPACE:
            try:
                q = int(el.get("quantity") or "1")
            except ValueError:
                q = 1
            if q > 0:
                self._emit(SPACE_CHAR * q, ctx)
            return
        if tag == _CAESURA:
            if not ctx.hidden and self.cur is not None:
                self.cur["caesuras"].append(self.length)
            return
        if tag == _UNCLEAR and not el.text and len(el) == 0:
            if not ctx.hidden and self.cur is not None:
                self.cur["unclear"].append(self.length)
            self._emit(UNCLEAR_MARK, ctx)
            return

        place = (el.get("place") or "") + " " + (el.get(_C + "place") or "")
        if tag == _MULU:
            buf: list = []
            lv = el.get("level")
            rec = {
                "level": int(lv) if lv and lv.isdigit() else None,
                "type": el.get("type"),
                "n": el.get("n"),
                "text": "",
                "offset": self._offset(),
                "div_type": ctx.divs[-1] if ctx.divs else None,
            }
            self._attach("mulu", rec, ctx)
            self.walk(el, ctx._replace(hidden=True, captures=(buf,)))
            rec["text"] = "".join(buf)
            return
        if tag in (_HEAD, _JHEAD) and not ctx.hidden:
            buf = []
            rec = {
                "kind": "jhead" if tag == _JHEAD else "head",
                "text": "",
                "offset": self._offset(),
            }
            self._attach("heads", rec, ctx)
            self.walk(el, ctx._replace(captures=ctx.captures + (buf,)))
            rec["text"] = "".join(buf)
            return
        if tag == _NOTE:
            if "inline" not in (el.get("place") or ""):
                if ctx.hidden:  # in an excluded region (X23n0438's Siddham glosses): goes with it
                    self.walk(el, ctx._replace(captures=(), in_note=True))
                    return
                # kept out of text and out of any enclosing head/jhead text, but recorded
                buf = []
                rec = {
                    "offset": self._offset(),
                    "place": el.get("place"),
                    "type": el.get("type"),
                    "text": "",
                }
                self._attach("excluded_notes", rec, ctx, touch=False)
                self.walk(el, ctx._replace(hidden=True, captures=(buf,), in_note=True))
                rec["text"] = "".join(buf)
            elif ctx.hidden:  # inline note inside mulu text or an excluded region
                self.walk(el, ctx._replace(in_note=True))
            else:
                self._inline_open()
                self.walk(el, ctx._replace(in_note=True, inline=True))
                self._inline_close()
            return
        if tag == _JUAN:
            if not ctx.hidden and not ctx.in_note:
                self._attach(
                    "juan_marks",
                    {"fun": el.get("fun"), "n": el.get("n"), "offset": self._offset()},
                    ctx,
                )
            self.walk(el, ctx)
            return
        if (
            tag in (_RDG, _FIGDESC)
            or (
                tag in (_SIC, _ORIG)
                and el.getparent() is not None
                and el.getparent().tag == _CHOICE
            )
            or (tag == _TT_T and not _is_zh(el))
            or ("foot" in place and tag not in (_NOTE, _T + "p", _LG))
        ):
            self.walk(el, ctx._replace(hidden=True, captures=()))
            return
        if tag == _LEM:
            self.walk(el, ctx._replace(in_note=True))
            return
        if tag in (_CBDIV, _DIV):
            self.walk(el, ctx._replace(divs=ctx.divs + (el.get("type"),)))
            return
        if tag in (_LG, _L):
            self.walk(el, ctx._replace(verse=True))
            return
        self.walk(el, ctx)

    def _lb(self, lb, ctx: _Ctx):
        if lb.get("type") == "old":
            return
        eds = (lb.get("ed") or "").split()
        if not eds or self.canon in eds:
            self._new_line(lb, ctx, [e for e in eds if e != self.canon])
            return
        for e in eds:
            item = {"ed": e, "n": lb.get("n") or "", "offset": self._offset()}
            if self.cur is None:
                self.pending.append(("alt", item))
            else:
                self.cur["alt"].append(item)

    def _g(self, el, ctx: _Ctx):
        ref = (el.get("ref") or "").lstrip("#")
        txt = (el.text or "").translate(_LAYOUT)
        if ref in self.chars:
            s, via = self.chars[ref]
        elif txt and not any(_is_pua(c) for c in txt):
            s, via = txt, "text"
        else:
            s, via = "[#%s]" % (ref or "?"), "placeholder"
        if not ctx.hidden and self.cur is not None:
            self.cur["gaiji"].append({"offset": self.length, "ref": ref, "via": via})
        self._emit(s, ctx)

    def _inline_open(self):
        if self.inline_depth == 0 and self.cur is not None:
            self.inline_open = self.length
        self.inline_depth += 1

    def _inline_close(self):
        self.inline_depth -= 1
        if self.inline_depth == 0:
            if (
                self.cur is not None
                and self.inline_open is not None
                and self.length > self.inline_open
            ):
                self.cur["inline_notes"].append((self.inline_open, self.length))
            self.inline_open = None


def _is_zh(t) -> bool:
    lang = t.get(_XML_LANG)
    place = (t.get("place") or "") + (t.get(_C + "place") or "")
    return (lang is None or lang.startswith("zh")) and "foot" not in place


# --------------------------------------------------------------------------------------------- API


def extract(xml_path) -> Extraction:
    """Parse one CBETA P5 file; return its header info and line records (see module docstring)."""
    root = etree.parse(str(xml_path)).getroot()
    info = _header_info(root)
    body = root.find("%stext/%sbody" % (_T, _T))
    w = _Walker(info, _char_table(root))
    if body is not None:
        w.walk(body, _Ctx())
    w._finish()
    for key, item in w.pending:  # markers after the last lb cannot happen, but never drop one
        if w.lines:
            w.lines[-1][key].append(item)
    return Extraction(info=info, lines=w.lines, unanchored=w.unanchored)


def iter_lines(xml_path) -> Iterator[dict]:
    """Yield the line records of one CBETA P5 file in document order."""
    yield from extract(xml_path).lines


@dataclass
class TextIndex:
    """A run of lines concatenated without separator; maps (linehead, offset) <-> global offset."""

    lineheads: list
    starts: list  # global offset of each line's first character
    lengths: list
    text: str
    _pos: dict = field(default_factory=dict, repr=False)
    _stripped: tuple | None = field(default=None, repr=False)

    def __post_init__(self):
        self._pos = {lh: i for i, lh in enumerate(self.lineheads)}

    def __len__(self) -> int:
        return len(self.text)

    def line_text(self, linehead: str) -> str:
        i = self._pos[linehead]
        return self.text[self.starts[i] : self.starts[i] + self.lengths[i]]

    def global_offset(self, linehead: str, offset: int = 0) -> int:
        """(linehead, char offset in that line) -> offset in self.text; offset may equal the line
        length."""
        i = self._pos[linehead]
        if not 0 <= offset <= self.lengths[i]:
            raise ValueError(
                "offset %d outside line %s (length %d)" % (offset, linehead, self.lengths[i])
            )
        return self.starts[i] + offset

    def locate(self, global_offset: int) -> tuple:
        """offset in self.text -> (linehead, offset in line); an offset on a line boundary
        belongs to the next non-empty line."""
        if not self.lineheads or not 0 <= global_offset <= len(self.text):
            raise ValueError(
                "offset %d outside text of length %d" % (global_offset, len(self.text))
            )
        i = max(bisect.bisect_right(self.starts, global_offset) - 1, 0)
        return self.lineheads[i], global_offset - self.starts[i]

    def stripped(self) -> tuple:
        """(text without is_punct characters, list mapping each stripped index to its global
        offset), cached."""
        if self._stripped is None:
            keep = [i for i, ch in enumerate(self.text) if not is_punct(ch)]
            self._stripped = ("".join(self.text[i] for i in keep), keep)
        return self._stripped


def build_index(
    lines: Iterable[dict], start: str | None = None, end: str | None = None
) -> TextIndex:
    """Concatenate the records from linehead `start` through `end` (inclusive, in document order;
    None = open end)."""
    lhs, starts, lengths, parts = [], [], [], []
    pos, on = 0, start is None
    for rec in lines:
        if not on and rec["linehead"] == start:
            on = True
        if on:
            lhs.append(rec["linehead"])
            starts.append(pos)
            lengths.append(len(rec["text"]))
            parts.append(rec["text"])
            pos += len(rec["text"])
            if end is not None and rec["linehead"] == end:
                break
    if not on:
        raise KeyError("start linehead not found: %s" % start)
    if end is not None and (not lhs or lhs[-1] != end):
        raise KeyError("end linehead not found after start: %s" % end)
    return TextIndex(lineheads=lhs, starts=starts, lengths=lengths, text="".join(parts))


def _hits(index: TextIndex, needle: str, ignore_punct: bool) -> list:
    """[(global start, global end)] of every (possibly overlapping) occurrence of needle."""
    if ignore_punct:
        hay, mapping = index.stripped()
        pat = strip_punct(needle)
    else:
        hay, mapping, pat = index.text, None, needle
    out = []
    if not pat:
        return out
    i = hay.find(pat)
    while i >= 0:
        j = i + len(pat) - 1
        out.append((mapping[i], mapping[j] + 1) if mapping is not None else (i, j + 1))
        i = hay.find(pat, i + 1)
    return out


def find(index: TextIndex, needle: str, ignore_punct: bool = False) -> list:
    """[(linehead, offset)] where needle starts; ignore_punct skips is_punct characters in text and
    needle alike."""
    return [index.locate(s) for s, _ in _hits(index, needle, ignore_punct)]


def find_spans(index: TextIndex, needle: str, ignore_punct: bool = False) -> list:
    """Like find(), with the matched span:
    [{"start": (lh, off), "end": (lh, off exclusive), "text": matched text}]."""
    out = []
    for s, e in _hits(index, needle, ignore_punct):
        lh, off = index.locate(e - 1)
        out.append({"start": index.locate(s), "end": (lh, off + 1), "text": index.text[s:e]})
    return out


# --------------------------------------------------------------------------------------------- CLI


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m chinese_workflow.ingest.lines",
        description="Dump the lines of a CBETA XML P5 file with their lineheads.",
    )
    ap.add_argument("xml", help="CBETA TEI P5 file, e.g. data/raw/cbeta/T09n0262.xml")
    ap.add_argument(
        "--tsv", action="store_true", help="print linehead<TAB>juan<TAB>text instead of JSON Lines"
    )
    ap.add_argument(
        "--find", metavar="NEEDLE", help="print linehead<TAB>offset for each occurrence of NEEDLE"
    )
    ap.add_argument(
        "--ignore-punct", action="store_true", help="with --find: ignore punctuation and spaces"
    )
    args = ap.parse_args(argv)
    ex = extract(args.xml)
    out = sys.stdout
    try:
        if args.find is not None:
            for lh, off in find(build_index(ex.lines), args.find, ignore_punct=args.ignore_punct):
                out.write("%s\t%d\n" % (lh, off))
        elif args.tsv:
            for rec in ex.lines:
                out.write(
                    "%s\t%s\t%s\n"
                    % (rec["linehead"], "" if rec["juan"] is None else rec["juan"], rec["text"])
                )
        else:
            for rec in ex.lines:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out.flush()
    except BrokenPipeError:  # e.g. piped into head: silence the flush at interpreter exit
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    if ex.unanchored:
        print(
            "warning: %d text pieces before the first line: %r"
            % (len(ex.unanchored), ex.unanchored[:3]),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
