"""chinese_workflow.ingest.structure — the structure side-table of one ingested text (M1a, §4).

Input : an InputText (chinese_workflow.ingest.text.load_input_text): the line records of
        chinese_workflow.ingest.lines over a span, with the TextIndex over their reading text.
Output: build_structure() -> the structure/1 dict that ingest.run writes as <id>.structure.json;
        normalization_config() -> the dict written as normalization.config.json.

structure/1 (docs/outliner-design.md §4):
  schema          "structure/1"
  text_id, role   CBETA file id; "root" | "commentary" | None
  cbeta_release   the pinned xml-p5 tag (common.paths.CBETA_RELEASE)
  title, punctuation, punctuation_resp, header_date   teiHeader values (ingest.lines header info)
  source          the XML file read (repository-relative when inside the repository)
  span            {"first", "last"}: first and last linehead of the text, inclusive
  length, sha256  length and sha256 of the reading text (= <id>.txt = InputText.text)
  lines           [{"linehead", "start", "length", "juan"}], start = global offset of the line
  elements        [{"kind", "linehead", "offset", "char_start", "attrs"}], one per structural mark,
                  char_start = InputText.index.global_offset(linehead, offset), in document order
                  (line order, then offset, then the kind order of ELEMENT_KINDS).

Element kinds and attrs (every mark of the line records is reported; nothing is dropped):
  juan     cb:juan open/close                    {"fun", "n"}
  mulu     cb:mulu (CBETA's editorial TOC; its label is not reading text)
                                                 {"level", "type", "n", "text", "div_type"}
  head     head, the printed heading             {"text"}  (text[char_start:][:len(text)] == text)
  jhead    cb:jhead, the juan title              {"text"}
  verse    a maximal run of consecutive lines with in_verse (an lg/l group as ingest.lines sees
           it; two adjacent lg with no line between them form one run)
                                                 {"linehead_end", "char_end", "lines"}
  note     an inline note (small print kept in the text), one element per line fragment
                                                 {"place": "inline", "in_text": true, "length"}
           or a note kept out of the text (interlinear, authorial ...), recorded where it sits
                                                 {"place", "type", "text", "in_text": false}
  caesura  a verse caesura (renders as nothing)  {}
  gaiji    a g element in the text               {"ref", "via"}  (via = the charDecl route)
  unclear  an empty unclear, rendered "[?]" by ingest.lines   {"rendered": "[?]"}

`unclear` is not in the §4 kind list; it is reported because "[?]" is this pipeline's rendering,
not CBETA's text, and a later stage must be able to find it.
"""

from __future__ import annotations

from collections import Counter

from ..common.paths import CBETA_RELEASE, repo_relative
from .lines import UNCLEAR_MARK
from .text import InputText

SCHEMA = "structure/1"
ELEMENT_KINDS = ("juan", "mulu", "head", "jhead", "verse", "note", "caesura", "gaiji", "unclear")
_RANK = {k: i for i, k in enumerate(ELEMENT_KINDS)}
_RANK["jhead"] = _RANK["head"]  # a line carries one or the other; keep document order between them

NOTES_POLICY = (
    "inline notes (@place inline, inline2) are kept in the text and marked as note elements "
    "(in_text true); every other body note is kept out of the text and recorded where it sits "
    "(excluded_notes of the line records, note elements with in_text false); rules of "
    "chinese_workflow.ingest.lines"
)


def verse_runs(lines: list) -> list:
    """[(i, j)] index ranges (inclusive) of maximal runs of consecutive in_verse line records."""
    runs, i, n = [], 0, len(lines)
    while i < n:
        if lines[i]["in_verse"]:
            j = i
            while j + 1 < n and lines[j + 1]["in_verse"]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    return runs


def _line_elements(rec: dict) -> list:
    """(offset, kind, attrs) of one line record, in the record's list order per kind."""
    out = []
    for m in rec["juan_marks"]:
        out.append((m["offset"], "juan", {"fun": m["fun"], "n": m["n"]}))
    for m in rec["mulu"]:
        attrs = {k: m[k] for k in ("level", "type", "n", "text", "div_type")}
        out.append((m["offset"], "mulu", attrs))
    for h in rec["heads"]:
        out.append((h["offset"], h["kind"], {"text": h["text"]}))
    for s, e in rec["inline_notes"]:
        out.append((s, "note", {"place": "inline", "in_text": True, "length": e - s}))
    for x in rec["excluded_notes"]:
        attrs = {"place": x["place"], "type": x["type"], "text": x["text"], "in_text": False}
        out.append((x["offset"], "note", attrs))
    for c in rec["caesuras"]:
        out.append((c, "caesura", {}))
    for g in rec["gaiji"]:
        out.append((g["offset"], "gaiji", {"ref": g["ref"], "via": g["via"]}))
    for u in rec.get("unclear", []):
        out.append((u, "unclear", {"rendered": UNCLEAR_MARK}))
    return out


def build_structure(text: InputText) -> dict:
    """The structure/1 side-table of `text` (see the module docstring)."""
    idx = text.index
    info = text.info
    keyed = []
    for i, rec in enumerate(text.lines):
        for seq, (off, kind, attrs) in enumerate(_line_elements(rec)):
            keyed.append(((i, off, _RANK[kind], seq), rec["linehead"], off, kind, attrs))
    for i, j in verse_runs(text.lines):
        attrs = {
            "linehead_end": text.lines[j]["linehead"],
            "char_end": idx.starts[j] + idx.lengths[j],
            "lines": j - i + 1,
        }
        keyed.append(((i, 0, _RANK["verse"], -1), text.lines[i]["linehead"], 0, "verse", attrs))
    keyed.sort(key=lambda t: t[0])
    elements = [
        {
            "kind": kind,
            "linehead": lh,
            "offset": off,
            "char_start": idx.global_offset(lh, off),
            "attrs": attrs,
        }
        for _, lh, off, kind, attrs in keyed
    ]
    lines = [
        {"linehead": lh, "start": s, "length": n, "juan": rec["juan"]}
        for lh, s, n, rec in zip(idx.lineheads, idx.starts, idx.lengths, text.lines)
    ]
    return {
        "schema": SCHEMA,
        "text_id": text.text_id,
        "role": text.role,
        "cbeta_release": CBETA_RELEASE,
        "title": info.get("title"),
        "punctuation": info.get("punctuation"),
        "punctuation_resp": info.get("punctuation_resp"),
        "header_date": info.get("header_date"),
        "source": repo_relative(text.source_path) if text.source_path else None,
        "span": {"first": text.first_linehead, "last": text.last_linehead},
        "length": len(text.text),
        "sha256": text.sha256,
        "lines": lines,
        "elements": elements,
    }


def normalization_config(text: InputText) -> dict:
    """What ingest did to CBETA's characters: only the recorded renderings (regime none)."""
    routes = Counter(g["via"] for rec in text.lines for g in rec["gaiji"])
    return {
        "text_id": text.text_id,
        "regime": "none",
        "punctuation": text.info.get("punctuation"),
        "punctuation_resp": text.info.get("punctuation_resp"),
        "gaiji_routes": {k: routes[k] for k in sorted(routes)},
        "notes_policy": NOTES_POLICY,
        "excluded_notes": sum(len(rec["excluded_notes"]) for rec in text.lines),
        "renderings": {
            "space": "U+3000 x @quantity (ingest.lines convention)",
            "unclear": "%s for an empty unclear (ingest.lines convention); %d in this text"
            % (UNCLEAR_MARK, sum(len(rec.get("unclear", [])) for rec in text.lines)),
            "gaiji": "charDecl unicode > normal_unicode > normalized form > element text > "
            "[#<id>] placeholder; each g listed with its route (gaiji elements)",
        },
    }


def element_counts(structure: dict) -> dict:
    """{kind: count} of a structure/1 dict, in ELEMENT_KINDS order (zero counts omitted)."""
    c = Counter(e["kind"] for e in structure["elements"])
    return {k: c[k] for k in ELEMENT_KINDS if c[k]}
