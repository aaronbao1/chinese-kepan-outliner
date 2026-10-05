"""chunk.render — chunks/1 <-> chunks.md, and chunks.docx (Kurt's interlinear-outline typography).

Input:  a chunks/1 dict (chunk/chunker.py).
Output: render_md -> the text of chunks.md; parse_md -> the typed lines and the markers,
        announcements and chunk texts read back from it; render_docx -> chunks.docx.

chunks.md reproduces the three line types of Kurt's outlined-and-chunked-text
(docs/outliner-design.md, "Output formats"), with CBETA locators in place of folios:

    [<indicator>) <heading_src> <locator>]      taken-up marker (locator omitted when null)
    <chunk text>                                one paragraph = one chunk (the target text slice)
    <indicator>) <heading_src>                  announcement line(s)

A *run* is: the markers whose before_chunk is the chunk, the chunk text, the announcements whose
after_chunk is the chunk (Kurt's K T A A…). Runs are separated by one blank line; the file ends with
a newline. parse_md reads a run positionally (marker lines, then exactly one text line, then
announcement lines), so parse_md(render_md(x)) returns x's markers, announcements and chunk texts
exactly; render_md refuses (ValueError) content that would not read back (a newline in a line, a
chunk text that reads as a marker, a heading ending in something that reads as a locator).

In chunks.docx each line is one paragraph and each blank separator an empty paragraph; the
indicator's level digits (Unicode subscripts in the .md, e.g. '1₁2₂') become ordinary digits in
w:vertAlign="subscript" runs, as in Kurt's docx (docs/outliner-design.md, "Output formats").
"""

from __future__ import annotations

import re
from pathlib import Path

from ..common.docx import write_docx
from ..common.lineheads import is_ref

MARKER_RE = re.compile(r"\[(?P<indicator>[^\s\)\]\[]+)\) (?P<rest>.*)\]", re.DOTALL)
ANNOUNCEMENT_RE = re.compile(r"(?P<indicator>[^\s\)\]\[]+)\) (?P<heading>.*)", re.DOTALL)
SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉"
_FROM_SUB = str.maketrans(SUBSCRIPT_DIGITS, "0123456789")


# ------------------------------------------------------------------------------------ line forms


def marker_line(indicator: str, heading: str, locator: str | None) -> str:
    return "[%s) %s%s]" % (indicator, heading, (" " + locator) if locator else "")


def announcement_line(indicator: str, heading: str) -> str:
    return "%s) %s" % (indicator, heading)


def parse_marker(line: str) -> dict | None:
    """'[1₁2₂) 品文分三 T34n1723_p0850a29]' -> {indicator, heading, locator}; None
    otherwise."""
    m = MARKER_RE.fullmatch(line)
    if not m:
        return None
    rest = m.group("rest")
    head, sep, last = rest.rpartition(" ")
    if sep and is_ref(last):
        return {"indicator": m.group("indicator"), "heading": head, "locator": last}
    return {"indicator": m.group("indicator"), "heading": rest, "locator": None}


def parse_announcement(line: str) -> dict | None:
    m = ANNOUNCEMENT_RE.fullmatch(line)
    if not m:
        return None
    return {"indicator": m.group("indicator"), "heading": m.group("heading")}


# --------------------------------------------------------------------------------------- runs


def _runs(chunks: dict) -> list:
    """[(marker dicts, chunk dict, announcement dicts)] in chunk order."""
    before: dict = {}
    after: dict = {}
    for m in chunks["markers"]:
        before.setdefault(m["before_chunk"], []).append(m)
    for a in chunks["announcements"]:
        after.setdefault(a["after_chunk"], []).append(a)
    ids = {c["chunk_id"] for c in chunks["chunks"]}
    dangling = sorted((set(before) | set(after)) - ids)
    if dangling:
        raise ValueError("markers / announcements refer to unknown chunks: %s" % dangling[:5])
    return [(before.get(c["chunk_id"], []), c, after.get(c["chunk_id"], []))
            for c in chunks["chunks"]]


def _checked(line: str, what: str) -> str:
    if "\n" in line or "\r" in line:
        raise ValueError("%s contains a line break: %r" % (what, line[:60]))
    return line


def render_md(chunks: dict) -> str:
    """chunks.md: one run per chunk (markers, text, announcements), blank line between runs."""
    blocks = []
    for markers, chunk, announcements in _runs(chunks):
        lines = []
        for m in markers:
            line = _checked(marker_line(m["indicator"], m["heading"], m["locator"]),
                            "marker of %s" % m["node_id"])
            back = parse_marker(line)
            if back != {"indicator": m["indicator"], "heading": m["heading"],
                        "locator": m["locator"]}:
                raise ValueError("marker of %s would not read back: %r" % (m["node_id"], line))
            lines.append(line)
        text = _checked(chunk["text"], "chunk %s" % chunk["chunk_id"])
        if text == "" or parse_marker(text) is not None:
            raise ValueError("chunk %s text would not read back as a chunk: %r"
                             % (chunk["chunk_id"], text[:60]))
        lines.append(text)
        for a in announcements:
            line = _checked(announcement_line(a["indicator"], a["heading"]),
                            "announcement of %s" % a["node_id"])
            if parse_announcement(line) != {"indicator": a["indicator"], "heading": a["heading"]}:
                raise ValueError("announcement of %s would not read back: %r"
                                 % (a["node_id"], line))
            lines.append(line)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n" if blocks else ""


def parse_md(md: str) -> dict:
    """Read chunks.md back. Returns {"lines": [typed lines], "chunk_texts": [...],
    "markers": [{indicator, heading, locator, before_chunk}], "announcements": [{indicator, heading,
    after_chunk}]}; chunk ids are positional ('c1', 'c2', …, as chunk/chunker.py numbers them).
    Typed lines: {"line": 1-based line number, "type": "marker" | "chunk" | "announcement" |
    "blank", "text": the raw line, plus the parsed fields and "chunk" (the chunk id of the run)}."""
    raw = md.split("\n")
    if raw and raw[-1] == "":
        raw.pop()
    typed: list = []
    chunk_texts: list = []
    markers: list = []
    announcements: list = []
    pending: list = []  # (typed line, marker) awaiting their chunk
    in_text = False
    cid = None
    for i, line in enumerate(raw, 1):
        if line == "":
            if pending:
                raise ValueError("line %d: marker(s) without a chunk text" % i)
            typed.append({"line": i, "type": "blank", "text": line})
            in_text = False
            continue
        if not in_text:
            m = parse_marker(line)
            if m is not None:
                entry = {"line": i, "type": "marker", "text": line, **m}
                typed.append(entry)
                pending.append((entry, m))
                continue
            chunk_texts.append(line)
            cid = "c%d" % len(chunk_texts)
            typed.append({"line": i, "type": "chunk", "text": line, "chunk": cid})
            for entry, m in pending:
                entry["chunk"] = cid
                markers.append({**m, "before_chunk": cid})
            pending = []
            in_text = True
            continue
        a = parse_announcement(line)
        if a is None:
            raise ValueError("line %d: a second text line in one run (expected an announcement): %r"
                             % (i, line[:60]))
        typed.append({"line": i, "type": "announcement", "text": line, "chunk": cid, **a})
        announcements.append({**a, "after_chunk": cid})
    if pending:
        raise ValueError("end of file: marker(s) without a chunk text")
    return {"lines": typed, "chunk_texts": chunk_texts, "markers": markers,
            "announcements": announcements}


# --------------------------------------------------------------------------------------- docx


def _indicator_runs(prefix: str, indicator: str, suffix: str) -> list:
    """Runs for prefix + indicator + suffix; subscript digits of the indicator become ordinary
    digits with subscript=True. Adjacent runs of one kind are merged."""
    typed = [(ch, False) for ch in prefix]
    typed += [(ch.translate(_FROM_SUB), ch in SUBSCRIPT_DIGITS) for ch in indicator]
    typed += [(ch, False) for ch in suffix]
    runs: list = []
    for ch, sub in typed:
        if runs and runs[-1]["subscript"] == sub:
            runs[-1]["text"] += ch
        else:
            runs.append({"text": ch, "subscript": sub})
    return runs


def docx_paragraphs(chunks: dict) -> list:
    """The paragraphs of chunks.docx (common.docx.write_docx format)."""
    paras: list = []
    for k, (markers, chunk, announcements) in enumerate(_runs(chunks)):
        if k:
            paras.append({"runs": []})
        for m in markers:
            suffix = ") %s%s]" % (m["heading"], (" " + m["locator"]) if m["locator"] else "")
            paras.append({"runs": _indicator_runs("[", m["indicator"], suffix)})
        paras.append({"runs": [{"text": chunk["text"]}]})
        for a in announcements:
            paras.append({"runs": _indicator_runs("", a["indicator"], ") %s" % a["heading"])})
    return paras


def render_docx(chunks: dict, path) -> Path:
    """Write chunks.docx (deterministic bytes; see common/docx.py)."""
    meta = chunks.get("metadata", {})
    title = "%s outlined-and-chunked-text" % meta.get("target", {}).get("text_id", "")
    return write_docx(docx_paragraphs(chunks), path, core={"title": title.strip()})
