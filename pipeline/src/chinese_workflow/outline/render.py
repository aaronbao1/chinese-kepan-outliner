"""Render an independent outline in Kurt Keutzer's format: outline.docx and outline.md.

Design: docs/outliner-design.md §5.7.

Input:  an outline document (outline.json), either
          - zh-kepan (metadata.outline_profile == 'zh-kepan',
            context/baseline/outline-schema-zh.json), the outliner's output; or
          - a base document in Kurt's schema (context/baseline/outline-schema.json), e.g.
            tests/fixtures/outline-base/minimal-base.json (synthetic).
Output: outline.docx, written by chinese_workflow.common.docx.write_docx (zipfile, no
        python-docx), and outline.md, the same paragraphs as text.

Kurt's format (docs/outliner-design.md, "Output formats"): three front-matter paragraphs (bold title
line, subtitle, format note); one entry paragraph per node, indented 144 x (level - 1) twips,
'[<indicator> – <English>][<first>, <explained>]†', where the indicator's values are bold runs
and its level numbers bold runs with w:vertAlign="subscript" ('1₁B₂' = runs 1, _1_, B, _2_).

Base documents are re-typeset as Kurt's docx: a heading_src paragraph before each entry, the
translation's chapter and Part headings, bracketed entries without an indicator
([COLOPHON] [p. 368]). The parser's own record of the source is replayed, so that the docx
parser reads the render back into the same JSON (the parser, scripts/parse_sabcad_outline.py,
and its round-trip test are in the development repository, not in this copy):
  - paragraph_index (nodes, chapters, Parts, unindexed entries, orphan and unclassified
    paragraphs) and metadata.paragraph_stats place every paragraph at its source index, padded
    with empty paragraphs; without indices the paragraphs follow document order, no padding;
  - a node's `evidence` (its entry paragraph as typed, whitespace-normalised) is re-typed when it
    agrees with the node's fields, which keeps separator slips such as ' – – ' or a stray '2.';
    otherwise the entry is composed from indicator_display, heading_en, locations and dagger;
  - the per-node notes that describe typing (indent twips, first-line indent, paragraph style,
    a tab, a subscript run with stray whitespace, a heading_src separated from its entry by a
    chapter heading) and metadata.indent_check.nodes_without_indent.
What cannot come back: italics inside English headings (the parser drops them), fonts, colours,
sizes, spacing and centring (common.docx writes none), docProps/core.xml beyond title and
creator, and so metadata.source_file, source_sha256 and source_docx_core_properties.

zh-kepan documents: front matter = '<text_title_src> 科判' (bold), 'An Outline for
<text_title_en>', one line with text, scheme_id, outline_mode, root text and commentary ids and
gold_status, and FORMAT_NOTE_ZH; then one paragraph per node:
    [<indicator_display> – <heading_en>][<announced>, <explained>] <display_label> <heading_src>
        {<root_text.start>–<root_text.end>}† (inferred, 0.7)
The pair is the node's commentary position (the text that states the outline); a null announced
shows the explained line twice, a missing position shows '—'. The root-text span is shown in
sūtra mode only. † when the node has dagger; '(inferred, c)' for inferred nodes, '(imported)' /
'(editorial)' likewise.

outline.md mirrors the docx: '#' title, front-matter paragraphs, then one nested list: each node
a list item indented two spaces per level below 1, subscripts as Unicode subscripts (in a base
document the item holds the heading_src line and, on a continuation line, the entry), chapter
and Part headings as bold items at the depth of the next node so the list is never interrupted.
Text is not markdown-escaped. Deterministic: the same document gives the same bytes (docx, md).

    python -m chinese_workflow.outline.render OUTLINE.json [--md OUT.md] [--docx OUT.docx]
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..common.docx import write_docx
from ..common.jsonio import read_json

TWIPS_PER_LEVEL = 144
ZH_PROFILE = "zh-kepan"
DASH = " – "
NONE_MARK = "—"
TO_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
FROM_SUBSCRIPT = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
INDICATOR_TOKEN = re.compile(r"([^₀-₉]+)([₀-₉]+)")
FORMAT_NOTE_ZH = (
    "Kēpàn outline (科判): one entry per node, indented by level: [indicator with level "
    "subscripts – English heading][CBETA line where the parent's division announces the entry, "
    "CBETA line where the entry is itself taken up and explained], both in the text that states "
    "the outline; then the 干支 label, the Chinese heading as the source gives it and, in sūtra "
    "mode, {the root-text lines the node governs}; (inferred, c) marks a node proposed by the "
    "outliner with confidence c."
)

# The docx parser (scripts/parse_sabcad_outline.py, a development-repository script, not in this
# copy): the entry tail, and the notes in which it records how the source typed an entry
# paragraph (the renderer types it the same way)
ENTRY_TAIL_RE = re.compile(r"^(?P<pre>.*?)\]\s*\[(?P<loc>[^\]]*)\]\s*(?P<dag>†)?\s*$", re.DOTALL)
NOTE_INDENT = re.compile(r"^paragraph indent \((\d+) twips\) implies level ")
NOTE_INDENT_ODD = re.compile(r"^paragraph indent (\d+) twips is not a multiple of ")
NOTE_FIRST_LINE = re.compile(r"^paragraph has an extra first-line indent of (\d+) twips")
NOTE_STYLE = re.compile(r"^paragraph style '(.+)' \(all other entries have no style\)$")
NOTE_SUBSCRIPT_WS = re.compile(
    r"^subscript run for (\S+)_(\d+) contains stray whitespace \((.+)\)$")
NOTE_TAB = "tab character inside the entry"
NOTE_SEPARATED = "Tibetan heading separated from its indicator by heading(s)"
NOTE_PART_TITLE = "title given on the following paragraph"
SEPARATOR_KINDS = ("chapter", "part", "part-title")


# ------------------------------------------------------------------------------------------ blocks


def _run(text: str, bold: bool = False, italic: bool = False, subscript: bool = False) -> dict:
    return {"text": text, "bold": bold, "italic": italic, "subscript": subscript}


@dataclass
class Block:
    """One docx paragraph plus what the markdown view needs (kind, level)."""

    runs: list
    # title | front | chapter | part | part-title | heading | entry | unindexed | other | empty
    kind: str
    level: int | None = None
    indent_twips: int | None = None
    first_line_twips: int | None = None
    style: str | None = None
    notes: list = field(default_factory=list)  # private: placement hints, never written

    def paragraph(self) -> dict:
        p: dict = {"runs": [dict(r) for r in self.runs]}
        if self.indent_twips:
            p["indent_twips"] = self.indent_twips
        if self.first_line_twips:
            p["first_line_twips"] = self.first_line_twips
        if self.style:
            p["style"] = self.style
        return p

    def text(self) -> str:
        """Display text: subscript runs as Unicode subscripts, whitespace normalised (the parser's
        display_text, i.e. a base node's `evidence`)."""
        s = "".join(r["text"].translate(TO_SUBSCRIPT) if r.get("subscript") else r["text"]
                    for r in self.runs)
        return " ".join(s.split())


def _indent(level: int | None) -> int | None:
    return TWIPS_PER_LEVEL * (level - 1) if level and level > 1 else None


def indicator_tokens(node: dict) -> list:
    """[(value, level digits)] of a node's indicator: from indicator_display
    ('2₁12₂' -> [('2', '1'), ('12', '2')]), else from path ('2_1' -> ('2', '1'))."""
    display = node.get("indicator_display")
    if display:
        tokens = INDICATOR_TOKEN.findall(display)
        if "".join(v + lv for v, lv in tokens) == display:
            return [(v, lv.translate(FROM_SUBSCRIPT)) for v, lv in tokens]
    return [tuple(token.rsplit("_", 1)) for token in node["path"]]


def _indicator_runs(tokens: list, level_text: dict | None = None) -> list:
    runs = []
    for value, level in tokens:
        runs.append(_run(value, bold=True))
        runs.append(_run((level_text or {}).get((value, level), level), bold=True, subscript=True))
    return runs


# ------------------------------------------------------------------------------ base documents


def _typing(node: dict, meta: dict) -> dict:
    """How the source typed this node's entry paragraph, from the parser's notes (defaults: Kurt's
    convention)."""
    t = {"indent": _indent(node["level"]), "first_line": None, "style": None, "tab": False,
         "level_text": {}, "separated": False}
    if node["id"] in ((meta.get("indent_check") or {}).get("nodes_without_indent") or []):
        t["indent"] = None
    for note in node.get("notes") or []:
        m = NOTE_INDENT.match(note) or NOTE_INDENT_ODD.match(note)
        if m:
            t["indent"] = int(m.group(1))
        elif NOTE_FIRST_LINE.match(note):
            t["first_line"] = int(NOTE_FIRST_LINE.match(note).group(1))
        elif NOTE_STYLE.match(note):
            t["style"] = NOTE_STYLE.match(note).group(1)
        elif NOTE_SUBSCRIPT_WS.match(note):
            m = NOTE_SUBSCRIPT_WS.match(note)
            try:
                raw = ast.literal_eval(m.group(3))
            except (ValueError, SyntaxError):
                continue
            if isinstance(raw, str) and raw.strip() == m.group(2):
                t["level_text"][(m.group(1), m.group(2))] = raw
        elif note.startswith(NOTE_TAB):
            t["tab"] = True
        elif note.startswith(NOTE_SEPARATED):
            t["separated"] = True
    return t


def _location_bracket(loc: dict | None) -> str:
    loc = loc or {}
    if loc.get("raw"):
        return loc["raw"]
    scheme = loc.get("scheme")
    if scheme == "acip-folio":
        return "[%s, %s]" % (loc.get("first") or "", loc.get("explained") or "")
    if scheme == "page" and loc.get("page") is not None:
        return "[p. %s]" % loc["page"]
    return "[]"


def _agrees(rest: str, node: dict) -> bool:
    """Does an entry text (after '[<indicator>') carry the node's heading_en, location, dagger?"""
    m = ENTRY_TAIL_RE.match(rest)
    if not m or (m.group("dag") is not None) != bool(node.get("dagger")):
        return False
    raw = (node.get("locations") or {}).get("raw")
    if raw is not None and "[" + " ".join(m.group("loc").split()) + "]" != raw:
        return False
    return (node.get("heading_en") or "") in " ".join(m.group("pre").split())


def _entry_rest(node: dict) -> str:
    """The entry text after '[<indicator>': the source's own typing (evidence) when it agrees
    with the node's fields, else composed in Kurt's convention."""
    prefix = "[" + "".join(v + lv.translate(TO_SUBSCRIPT) for v, lv in indicator_tokens(node))
    evidence = node.get("evidence")
    if isinstance(evidence, str) and evidence.startswith(prefix):
        rest = evidence[len(prefix):]
        if _agrees(rest, node):
            return rest
    heading = node.get("heading_en") or ""
    dagger = "†" if node.get("dagger") else ""
    return ((DASH + heading) if heading else "") + "]" + _location_bracket(
        node.get("locations")) + dagger


def _base_node_blocks(node: dict, meta: dict) -> tuple:
    """(heading_src block or None, entry block) of a base node."""
    t = _typing(node, meta)
    rest = _entry_rest(node)
    if t["tab"] and " " in rest:
        rest = rest.replace(" ", "\t", 1)
    runs = [_run("[")] + _indicator_runs(indicator_tokens(node), t["level_text"]) + [_run(rest)]
    entry = Block(runs, "entry", node["level"], t["indent"], t["first_line"], t["style"])
    if t["separated"]:
        entry.notes.append("separated")
    heading = None
    if node.get("heading_src"):
        heading = Block([_run(node["heading_src"])], "heading", node["level"], t["indent"])
    return heading, entry


def _unindexed_blocks(u: dict) -> tuple:
    level = u.get("indent_level_guess")
    label, loc = u.get("text") or "", _location_bracket(u.get("locations"))
    runs = ([_run("["), _run(label + "]", bold=True)] if loc == "[]" else
            [_run("["), _run(label + "] ", bold=True), _run(loc)])
    entry = Block(runs, "unindexed", level, _indent(level))
    heading = None
    if u.get("heading_src"):
        heading = Block([_run(u["heading_src"])], "heading", level, _indent(level))
    return heading, entry


def _part_blocks(part: dict) -> list:
    raw, title = part.get("raw") or "", part.get("title") or ""
    if NOTE_PART_TITLE in (part.get("notes") or []) and title and raw.endswith(title):
        head = raw[: -len(title)].strip()
        if head:
            return [Block([_run(head)], "part"), Block([_run(title)], "part-title")]
    return [Block([_run(raw)], "part")]


def _heading_blocks(kind: str, heading: dict) -> list:
    """A chapter or Part heading of the translation as paragraph(s)."""
    return _part_blocks(heading) if kind == "part" else [Block([_run(heading["raw"])], "chapter")]


def _base_front(meta: dict) -> list:
    fm = meta.get("front_matter") or {}
    title = fm.get("title_line") or meta.get("text_title_src") or ""
    subtitle = fm.get("subtitle_line")
    if subtitle is None:
        subtitle = "An Outline for " + (meta.get("text_title_en") or "")
        if meta.get("author"):
            subtitle += " — " + meta["author"]
    lead = "An Outline for "
    sub_runs = ([_run(lead), _run(subtitle[len(lead):], italic=True)]
                if subtitle.startswith(lead) and len(subtitle) > len(lead) else [_run(subtitle)])
    return [Block([_run(title, bold=True)], "title"), Block(sub_runs, "front"),
            Block([_run(meta.get("format_note") or "")], "front")]


def _positional(doc: dict, front: list) -> list | None:
    """Every paragraph at its recorded paragraph_index, gaps filled with empty paragraphs; None when
    indices are missing or collide (then the caller lays paragraphs out in document order)."""
    meta = doc["metadata"]
    nodes = doc["nodes"]
    unindexed = doc.get("unindexed_entries") or []
    chapters, parts = meta.get("chapters") or [], meta.get("parts") or []
    if not nodes or not all(isinstance(x.get("paragraph_index"), int) and x["paragraph_index"] >= 0
                            for x in nodes + unindexed + chapters + parts):
        return None
    slots: dict = {}

    def put(i: int, block: Block) -> bool:
        if i in slots:
            return False
        slots[i] = block
        return True

    ok = all(put(i, b) for i, b in enumerate(front))
    for ch in chapters:
        ok = ok and put(ch["paragraph_index"], Block([_run(ch["raw"])], "chapter"))
    for pt in parts:
        for k, b in enumerate(_part_blocks(pt)):
            ok = ok and put(pt["paragraph_index"] + k, b)
    pending = []  # (entry index, heading block, separated)
    for node in nodes:
        heading, entry = _base_node_blocks(node, meta)
        ok = ok and put(node["paragraph_index"], entry)
        if heading is not None:
            pending.append((node["paragraph_index"], heading, "separated" in entry.notes))
    for u in unindexed:
        heading, entry = _unindexed_blocks(u)
        ok = ok and put(u["paragraph_index"], entry)
        if heading is not None:
            pending.append((u["paragraph_index"], heading, False))
    for o in meta.get("orphan_tibetan_headings") or []:
        ok = ok and put(o["paragraph_index"], Block([_run(o["text"])], "heading"))
    for u in meta.get("unclassified_paragraphs") or []:
        ok = ok and put(u["paragraph_index"], Block([_run(u["text"])], "other"))
    if not ok:
        return None
    # heading_src paragraphs: after the previous entry and after the chapter / Part headings standing
    # between the two, in the nearest free slot before the entry; a heading separated from its entry
    # by such headings goes before them, in the first free slot after the previous entry
    for idx, heading, separated in sorted(pending, key=lambda x: x[0]):
        lo = max([len(front) - 1] + [i for i, b in slots.items()
                                     if i < idx and b.kind in ("entry", "unindexed", "heading")])
        seps = sorted(i for i, b in slots.items() if lo < i < idx and b.kind in SEPARATOR_KINDS)
        if separated and seps:
            free = [i for i in range(lo + 1, seps[0]) if i not in slots]
        else:
            free = [i for i in range(idx - 1, max([lo] + seps), -1) if i not in slots]
        if not free:
            return None
        slots[free[0]] = heading
    total = max([(meta.get("paragraph_stats") or {}).get("paragraphs_total") or 0, max(slots) + 1])
    out = [slots.get(i) or Block([], "empty") for i in range(total)]
    styled = (meta.get("paragraph_stats") or {}).get("styled_paragraphs") or {}
    for style, indices in sorted(styled.items()):
        for i in indices:
            if 0 <= i < total:
                out[i].style = style
    return out


def _sequential(doc: dict, front: list, node_blocks) -> list:
    """Paragraphs in document order: chapter / Part headings before the first node that carries them
    (Parts first), unindexed entries after their after_node_id, no empty paragraphs."""
    meta = doc["metadata"]
    out = list(front)
    queues = {"part": list(meta.get("parts") or []), "chapter": list(meta.get("chapters") or [])}
    current = {"part": None, "chapter": None}
    after: dict = {}
    for u in doc.get("unindexed_entries") or []:
        after.setdefault(u.get("after_node_id"), []).append(u)

    def emit_unindexed(key):
        for u in after.pop(key, []):
            heading, entry = _unindexed_blocks(u)
            out.extend(b for b in (heading, entry) if b is not None)

    def headings_up_to(kind: str, raw: str) -> list:
        queue, blocks = queues[kind], []
        if any(x.get("raw") == raw for x in queue):
            while queue:
                x = queue.pop(0)
                blocks += _heading_blocks(kind, x)
                if x.get("raw") == raw:
                    break
        else:
            blocks.append(Block([_run(raw)], kind))
        return blocks

    emit_unindexed(None)
    for node in doc["nodes"]:
        seps = []
        for kind in ("part", "chapter"):
            value = node.get(kind)
            if value is not None and value != current[kind]:
                seps += headings_up_to(kind, value)
                current[kind] = value
        heading, entry = node_blocks(node)
        if heading is not None and "separated" in entry.notes:
            out += [heading] + seps + [entry]
        else:
            out += seps + [b for b in (heading, entry) if b is not None]
        emit_unindexed(node["id"])
    for kind in ("part", "chapter"):
        for x in queues[kind]:
            out += _heading_blocks(kind, x)
    for key in sorted(after, key=str):
        emit_unindexed(key)
    return out


def _base_blocks(doc: dict) -> list:
    front = _base_front(doc["metadata"])
    positional = _positional(doc, front)
    if positional is not None:
        return positional
    return _sequential(doc, front, lambda n: _base_node_blocks(n, doc["metadata"]))


# ----------------------------------------------------------------------------- zh-kepan documents


def _fmt_confidence(c) -> str | None:
    if isinstance(c, bool) or not isinstance(c, (int, float)):
        return None
    return ("%.2f" % c).rstrip("0").rstrip(".")


def commentary_pair(node: dict) -> tuple:
    """(announced, explained) as displayed: a null announced shows the explained line, a missing
    position '—'."""
    loc = node.get("locations") or {}
    c = (loc.get("commentary") or {}) if loc.get("scheme") == "cbeta-kepan" else {}
    announced, explained = c.get("announced"), c.get("explained")
    return (announced or explained or NONE_MARK, explained or NONE_MARK)


def root_span(node: dict, meta: dict) -> str | None:
    """'start–end' of the node's root-text span in sūtra mode, else None."""
    loc = node.get("locations") or {}
    if meta.get("outline_mode") != "sutra" or loc.get("scheme") != "cbeta-kepan":
        return None
    rt = loc.get("root_text") or {}
    if not (rt.get("start") or rt.get("end")):
        return None
    return "%s–%s" % (rt.get("start") or "?", rt.get("end") or "?")


def zh_entry_tail(node: dict, meta: dict) -> str:
    """The zh entry text after '[<indicator>'."""
    heading = node.get("heading_en") or ""
    s = ((DASH + heading) if heading else "") + "]" + "[%s, %s]" % commentary_pair(node)
    words = [w for w in (node.get("display_label"), node.get("heading_src")) if w]
    if words:
        s += " " + " ".join(words)
    span = root_span(node, meta)
    if span:
        s += " {" + span + "}"
    if node.get("dagger"):
        s += "†"
    origin = node.get("origin")
    if origin == "inferred":
        conf = _fmt_confidence(node.get("confidence"))
        s += " (inferred, %s)" % conf if conf is not None else " (inferred)"
    elif origin in ("imported", "editorial"):
        s += " (%s)" % origin
    return s


def _zh_node_blocks(node: dict, meta: dict) -> tuple:
    runs = [_run("[")] + _indicator_runs(indicator_tokens(node)) + [_run(zh_entry_tail(node, meta))]
    return None, Block(runs, "entry", node["level"], _indent(node["level"]))


def _zh_front(meta: dict) -> list:
    title = (meta.get("text_title_src") or meta.get("text_id") or "").strip()
    blocks = [Block([_run((title + " 科判").strip(), bold=True)], "title")]
    if meta.get("text_title_en"):
        sub = [_run("An Outline for "), _run(meta["text_title_en"], italic=True)]
        if meta.get("author"):
            sub.append(_run(" — " + meta["author"]))
        blocks.append(Block(sub, "front"))
    fields = [("text", "text_id"), ("scheme", "scheme_id"), ("mode", "outline_mode"),
              ("root text", "root_text_id"), ("commentary", "commentary_id"),
              ("gold status", "gold_status")]
    line = " · ".join("%s: %s" % (label, meta.get(key) or NONE_MARK) for label, key in fields)
    blocks.append(Block([_run(line)], "front"))
    blocks.append(Block([_run(FORMAT_NOTE_ZH)], "front"))
    return blocks


def _zh_blocks(doc: dict) -> list:
    meta = doc["metadata"]
    return _sequential(doc, _zh_front(meta), lambda n: _zh_node_blocks(n, meta))


# ------------------------------------------------------------------------------------------ API


def is_zh(doc: dict) -> bool:
    return (doc.get("metadata") or {}).get("outline_profile") == ZH_PROFILE


def blocks(doc: dict) -> list:
    return _zh_blocks(doc) if is_zh(doc) else _base_blocks(doc)


def paragraphs(doc: dict) -> list:
    """The docx paragraphs of an outline document, in chinese_workflow.common.docx's format."""
    return [b.paragraph() for b in blocks(doc)]


def render_docx(doc: dict, path) -> Path:
    bs = blocks(doc)
    title = next((b.text() for b in bs if b.kind == "title"), "")
    core = {"title": title, "creator": "chinese_workflow.outline.render"}
    return write_docx([b.paragraph() for b in bs], path, core=core)


def render_markdown(doc: dict) -> str:
    items: list = []  # (block, text); a Part title typed on the next paragraph joins its heading
    for b in blocks(doc):
        if b.kind == "empty":
            continue
        if b.kind == "part-title" and items and items[-1][0].kind == "part":
            items[-1] = (items[-1][0], items[-1][1] + " " + b.text())
        else:
            items.append((b, b.text()))
    # chapter / Part headings sit in the list at the depth of the next node, so that the nested list
    # is never interrupted (an interrupted list turns deep items into a code block)
    next_level, level = [1] * len(items), 1
    for i in range(len(items) - 1, -1, -1):
        if items[i][0].kind in ("heading", "entry", "unindexed"):
            level = items[i][0].level or 1
        next_level[i] = level
    lines: list = []
    for i, (b, text) in enumerate(items):
        if b.kind == "title":
            lines += ["# " + text, ""]
        elif b.kind == "front":
            lines += [text, ""]
        elif b.kind in ("chapter", "part", "part-title", "other"):
            fmt = "%s- %s" if b.kind == "other" else "%s- **%s**"
            lines.append(fmt % ("  " * (next_level[i] - 1), text))
        elif b.kind != "heading" and i and items[i - 1][0].kind == "heading":
            # the entry continues its heading_src item
            lines.append("  " * ((b.level or 1) - 1) + "  " + text)
        else:
            lines.append("  " * ((b.level or 1) - 1) + "- " + text)
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m chinese_workflow.outline.render",
        description="Render outline.json in Kurt's independent-outline format (markdown and docx).")
    ap.add_argument("outline", type=Path, help="outline.json (zh-kepan or Kurt's base schema)")
    ap.add_argument("--md", type=Path, help="write the markdown here")
    ap.add_argument("--docx", type=Path, help="write the docx here")
    args = ap.parse_args(argv)
    doc = read_json(args.outline)
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(render_markdown(doc), encoding="utf-8")
        print("wrote: %s" % args.md)
    if args.docx:
        print("wrote: %s" % render_docx(doc, args.docx))
    if not args.md and not args.docx:
        sys.stdout.write(render_markdown(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
