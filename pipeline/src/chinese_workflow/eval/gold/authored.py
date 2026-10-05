"""chinese_workflow.eval.gold.authored — compile a hand-authored *.outline.txt into a zh-kepan gold.

Input : an *.outline.txt (format: README.md in this directory, "Authored golds") and the CBETA P5
        files of its commentary_id and root_text_id (data/raw/cbeta/<id>.xml, else
        data/raw/cbeta/xml-p5/**/<id>.xml; --commentary-xml / --root-xml override), read with
        chinese_workflow.ingest.lines.
Output: a zh-kepan outline document (context/baseline/outline-schema-zh.json) built with common.py,
        written as JSON only when every check below passes and scripts/validate_outline.py reports
        no error.

Checks (each error names the txt line it comes from):
  * every @exp / @ann / @src linehead exists in the commentary file, every @root linehead in the
    root-text file, and @root's start does not come after its end;
  * origin=explicit: heading_src occurs punctuation-insensitively (ingest.lines.find_spans) within
    ±2 lines (document order) of @src when given, else of @exp or @ann — or equals the text of a
    cb:mulu on the @exp line (a 品 heading is CBETA's TOC label, not body text); @ext occurs in
    the same window;
  * @lemma occurs within ±2 lines of @exp in the commentary — or of @lemsrc, the line the lemma
    is quoted on, when the node's topic marker stands further from it (Kuiji quotes a lemma once
    and announces several levels before 此初也; @lemsrc must then come before @exp, the hit must
    be a quotation with 經「 immediately before it, and no other 經「 may stand from it to the end
    of the @exp line, so @exp lies inside the lemma's block) — and resolves in the root text: its
    words before 至 start on the @root start line and the first occurrence of its words after 至
    ends on the @root end line (on or before it when @endbasis is given); a lemma without 至 must
    start and end there itself;
  * @cut (the annotator's cut words where Kuiji quotes no lemma) starts on the @root start line;
  * the locator backs the basis: @lemma iff @basis=lemma, @cut iff @basis=manual;
  * next-node rule: a sūtra-span node's @root end is the line of the last non-punctuation
    character before the start of the next sūtra-span node (pre-order, after its subtree) whose
    start is located by @lemma or @cut — the plan's (Task 4) "inclusive last line before the next
    sibling lemma", made checkable;
  * basis=chapter: the start is a root-text line carrying a 品 cb:mulu and the end is the last
    line of a 品 (the last line inside a `pin` div before the next 品 cb:mulu); a node without
    chapter-basis children spans one 品 (end in the 品 it starts in), a node with them spans
    exactly its first child's first 品 to its last child's last 品, and chapter-basis
    neighbours (next-node) cover consecutive 品; end_basis=chapter: the end is the last line of
    a 品, namely of the 品 the start is in (a start outside every 品 fails);
  * indentation is ASCII spaces only (a tab or U+3000 from a CJK IME is an error);
  * commentary-internal nodes carry no @root/@lemma/@cut; in sūtra mode a sūtra-span node without
    @root carries flag unmapped; inferred needs @conf and @evidence, editorial @evidence;
  * @n differs from the number of children: flag count_mismatch is added (with a note), not an
    error; @conf without origin inferred and @ext on a commentary-internal or non-explicit node
    are warnings;
  * coverage_span header lines (-> metadata.coverage_spans): the root (heading@exp line, or
    `document`) names exactly one node; both spans are lines of their files, in order; every
    commentary locator of the covered nodes lies in the commentary span and every covered
    sūtra-span leaf in the root-text span; with a numeric max_level no covered node is deeper,
    except, for the `document` entry, nodes inside another entry's subtree.

Usage: python -m chinese_workflow.eval.gold.authored <txt> -o <json>
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from chinese_workflow.eval.gold import common
from chinese_workflow.ingest.lines import build_index, find_spans, iter_lines, strip_punct

GENERATED_BY = "chinese_workflow.eval.gold.authored"
WINDOW = 2  # ± lines around @exp / @ann / @src for the verbatim checks
GANZHI = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"  # level 1..22 (R07 F15)
DIGITS = "〇一二三四五六七八九"

HEADER_REQUIRED = (
    "scheme_id",
    "root_text_id",
    "text_title_src",
    "text_title_en",
    "source_title",
    "seeded_by",
    "gold_status",
    "licence_statement",
    "eval_only",
    "cbeta_release",
)
HEADER_OPTIONAL = (
    "outline_mode",
    "commentary_id",
    "text_id",
    "author",
    "source_kind",
    "licence_id",
    "licence_holder",
    "licence_evidence",
    "origin_note",
)
HEADER_REPEATABLE = (
    "coverage",
    "coverage_span",
    "split_note",
    "anomaly",
    "source_note",
    "format_note",
)
HEADER_KEYS = frozenset(HEADER_REQUIRED + HEADER_OPTIONAL + HEADER_REPEATABLE)

FIELDS = frozenset(
    [
        "exp",
        "ann",
        "src",
        "lemsrc",
        "root",
        "basis",
        "endbasis",
        "lemma",
        "cut",
        "n",
        "ext",
        "origin",
        "class",
        "flags",
        "label",
        "note",
        "evidence",
        "conf",
    ]
)
REPEATABLE_FIELDS = frozenset(["note"])
ORIGINS = ("explicit", "inferred", "editorial")
CLASSES = ("sutra-span", "commentary-internal")
FLAGS = (
    "no_gloss",
    "parallel_ref",
    "unmapped",
    "coarsened",
    "truncated",
    "merged_range",
    "irregular_label",
    "anchor_inherited",
    "count_mismatch",
)
BASES = (
    "lemma",
    "extent-formula",
    "chapter",
    "sdp-anchor",
    "cbeta-mulu",
    "text-alignment",
    "self",
    "manual",
    "inferred",
)
END_BASES = BASES + ("next-node",)

HEADER_RE = re.compile(r"^([a-z][a-z0-9_]*):(?:[ ](.*))?$")
COVERAGE_RE = re.compile(
    r"root=(?P<root>\S+)\s+commentary=(?P<c1>\S+)\.\.(?P<c2>\S+)\s+"
    r"root_text=(?P<r1>\S+)\.\.(?P<r2>\S+)\s+max_level=(?P<max>[1-9][0-9]*|full)"
)
FIELD_RE = re.compile(r"(?:^|\s)@([a-z]+)=")

FORMAT_NOTE = (
    "Compiled by chinese_workflow.eval.gold.authored from a hand-authored outline text (metadata "
    "authored_file; format in pipeline/src/chinese_workflow/eval/gold/README.md). One line per "
    "node, two spaces per level, heading_src verbatim from the commentary as ingest.lines reads it "
    "(checked punctuation-insensitively within ±2 lines of the node's @src, @exp or @ann line, or "
    "equal to a cb:mulu label on the @exp line). commentary.explained = the line where the "
    "commentary takes the node up (its topic marker 此初 / 下明… / 第二… / …者, a 品's cb:mulu "
    "line); commentary.announced = the line where the parent's announcement lists it (null when "
    "none; equal to explained for a sub-item the commentary only lists). root_text: basis lemma = "
    "start and end fixed by matching the commentary's quoted lemma 經「A至B」 in the root text "
    "(A starts on start, B ends on end; end_basis next-node when the end is instead the line "
    "before the next division, chapter when it is the 品's last line, extent-formula when a stated "
    "stanza count fixes it, manual when the annotator set it, the reading in a note); manual = "
    "the annotator's cut words where the commentary quotes no "
    "lemma (notes give them); chapter = the root text's 品 cb:mulu line to the last line of the "
    "品 div. end is inclusive and equals the line of the last non-punctuation character before the "
    "next located division. display_label is generated unless the text gives one (see "
    "display_label_rule)."
)
DISPLAY_LABEL_RULE = (
    "generated: 干支 symbol of the node's level (甲 = 1 … 癸 = 10, 子 = 11 … 亥 = 22) + the sibling "
    "ordinal in Chinese numerals 一二三… (R07 F15); an @label in the outline text overrides it; "
    "null below level 22"
)


class AuthoredError(Exception):
    """One or more errors in an outline text; each message names its line."""

    def __init__(self, messages):
        self.messages = list(messages)
        super().__init__("\n".join(self.messages))


# ------------------------------------------------------------------------------------------ parse


@dataclass
class DraftNode:
    lineno: int
    level: int
    heading: str
    fields: dict
    children: list = field(default_factory=list)


@dataclass
class Parsed:
    name: str
    header: dict  # key -> str (repeatable keys: list of str)
    header_lineno: dict
    roots: list


def parse(text: str, name: str = "<outline.txt>") -> Parsed:
    """Parse an outline text; raises AuthoredError listing every syntax error with its line."""
    errors: list = []
    header: dict = {k: [] for k in HEADER_REPEATABLE}
    header_lineno: dict = {}
    roots: list = []
    stack: list = []  # open DraftNodes, stack[k] at level k + 1
    in_header = True

    def err(lineno, msg):
        errors.append("%s:%d: %s" % (name, lineno, msg))

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if in_header:
            m = HEADER_RE.match(line)
            if m:
                key, value = m.group(1), (m.group(2) or "").strip()
                if key not in HEADER_KEYS:
                    err(lineno, "unknown header key %r" % key)
                elif key in HEADER_REPEATABLE:
                    header[key].append(value)
                    header_lineno.setdefault(key, lineno)
                elif key in header:
                    err(
                        lineno,
                        "header key %r given twice (first on line %d)" % (key, header_lineno[key]),
                    )
                else:
                    header[key] = value
                    header_lineno[key] = lineno
                continue
            in_header = False
        lead = line[: len(line) - len(line.lstrip())]
        odd = sorted({ch for ch in lead if ch != " "})
        if odd:
            names = ", ".join(
                "tab"
                if ch == "\t"
                else "U+%04X%s" % (ord(ch), " (IDEOGRAPHIC SPACE)" if ch == "　" else "")
                for ch in odd
            )
            err(lineno, "%s in indentation: indent with ASCII spaces only, two per level" % names)
            continue
        indent = len(lead)
        if indent % 2:
            err(lineno, "indentation of %d spaces is not a multiple of two" % indent)
            continue
        level = indent // 2 + 1
        if level > len(stack) + 1:
            err(
                lineno, "level %d under a level-%d node (one level at a time)" % (level, len(stack))
            )
            continue
        body = line.strip()
        matches = list(FIELD_RE.finditer(body))
        heading = (body[: matches[0].start()] if matches else body).strip()
        fields: dict = {}
        for k, m in enumerate(matches):
            key = m.group(1)
            end = matches[k + 1].start() if k + 1 < len(matches) else len(body)
            value = body[m.end() : end].strip()
            if key not in FIELDS:
                err(lineno, "unknown field @%s" % key)
            elif key in REPEATABLE_FIELDS:
                fields.setdefault(key, []).append(value)
            elif key in fields:
                err(lineno, "field @%s given twice" % key)
            else:
                fields[key] = value
        if not heading:
            err(lineno, "empty heading")
        if "exp" not in fields:
            err(lineno, "missing @exp (the commentary line where the node is taken up)")
        node = DraftNode(lineno, level, heading, fields)
        del stack[level - 1 :]
        (stack[-1].children if stack else roots).append(node)
        stack.append(node)
    for key in HEADER_REQUIRED:
        if key not in header:
            errors.append("%s: header: missing required key %r" % (name, key))
    if not roots and not errors:
        errors.append("%s: no node lines" % name)
    if errors:
        raise AuthoredError(errors)
    return Parsed(name, header, header_lineno, roots)


# ------------------------------------------------------------------------------------- CBETA text


class Text:
    """The line records of one CBETA file with a whole-file text index."""

    def __init__(self, records, path=None):
        self.records = list(records)
        self.path = path
        self.pos = {r["linehead"]: i for i, r in enumerate(self.records)}
        self.index = build_index(self.records)
        self._chapters = None

    def has(self, lh) -> bool:
        return lh in self.pos

    def rec(self, lh) -> dict:
        return self.records[self.pos[lh]]

    def window(self, lh, k=WINDOW):
        i = self.pos[lh]
        lo, hi = max(0, i - k), min(len(self.records), i + k + 1)
        return build_index(self.records[lo:hi]), i

    def find_near(self, needle, lh, k=WINDOW):
        """Punctuation-insensitive hits within ±k lines of lh, nearest first (a hit on or after
        lh wins a tie); each {"start", "end", "text", "lines"}."""
        index, i = self.window(lh, k)
        hits = []
        for s in find_spans(index, needle, ignore_punct=True):
            d = self.pos[s["start"][0]] - i
            first, last = self.pos[s["start"][0]], self.pos[s["end"][0]]
            s["lines"] = [self.records[j]["linehead"] for j in range(first, last + 1)]
            hits.append(((abs(d), d < 0), s))
        return [s for _, s in sorted(hits, key=lambda h: h[0])]

    def find_all(self, needle):
        """Punctuation-insensitive hits in the whole file: [(global start, global end excl, span)]."""
        out = []
        for s in find_spans(self.index, needle, ignore_punct=True):
            gs = self.index.global_offset(*s["start"])
            ge = self.index.global_offset(*s["end"])
            out.append((gs, ge, s))
        return out

    def line_of(self, global_offset) -> str:
        return self.index.locate(global_offset)[0]

    def last_char_line_before(self, global_offset) -> str | None:
        """Line of the last non-punctuation character before global_offset (None at file start)."""
        _, keep = self.index.stripped()
        k = bisect.bisect_left(keep, global_offset)
        return self.line_of(keep[k - 1]) if k else None

    def chapters(self):
        """(start -> 品 index, end -> 品 index) for the 品 of this file, in document order: start =
        the line carrying a 品 cb:mulu; end = the last line inside a `pin` div before the next 品
        cb:mulu (the last non-empty line when the file has no pin div there)."""
        if self._chapters is None:
            marks = [
                i
                for i, r in enumerate(self.records)
                if any(m.get("type") == "品" for m in r["mulu"])
            ]
            starts, ends = {}, {}
            for k, i in enumerate(marks):
                stop = marks[k + 1] if k + 1 < len(marks) else len(self.records)
                span = self.records[i:stop]
                inside = [r for r in span if "pin" in r["div_types"] and r["text"]]
                inside = inside or [r for r in span if r["text"]] or span[:1]
                starts[self.records[i]["linehead"]] = k
                ends[inside[-1]["linehead"]] = k
            self._chapters = (starts, ends)
        return self._chapters

    def chapter_of(self, lh) -> int | None:
        """Index of the 品 whose span (chapters()) contains line lh, else None."""
        starts, ends = self.chapters()
        k = None
        for i, r in enumerate(self.records):
            if r["linehead"] in starts:
                k = starts[r["linehead"]]
            if r["linehead"] == lh:
                return k
            if r["linehead"] in ends and ends[r["linehead"]] == k:
                k = None
        return None

    def before(self, a, b) -> bool:
        """True when line a does not come after line b in document order."""
        return self.pos[a] <= self.pos[b]


def load_text(xml_path) -> Text:
    return Text(iter_lines(xml_path), xml_path)


def find_cbeta_xml(text_id: str, cbeta_dir) -> Path:
    cbeta_dir = Path(cbeta_dir)
    direct = cbeta_dir / ("%s.xml" % text_id)
    if direct.exists():
        return direct
    hits = sorted((cbeta_dir / "xml-p5").glob("**/%s.xml" % text_id))
    if hits:
        return hits[0]
    raise FileNotFoundError(
        "no CBETA file for %s under %s (run scripts/fetch_cbeta.sh)" % (text_id, cbeta_dir)
    )


# ---------------------------------------------------------------------------------------- compile


def chinese_numeral(k: int) -> str:
    """1..99 in Chinese numerals (一, 十, 十一, 二十, 二十一 …)."""
    if not 1 <= k <= 99:
        raise ValueError(k)
    tens, ones = divmod(k, 10)
    if tens == 0:
        return DIGITS[ones]
    return ("" if tens == 1 else DIGITS[tens]) + "十" + (DIGITS[ones] if ones else "")


def generated_label(level: int, sibling_index: int) -> str | None:
    if level > len(GANZHI) or sibling_index > 99:
        return None
    return GANZHI[level - 1] + chinese_numeral(sibling_index)


def _none(value):
    return None if value in (None, "", "null") else value


def _evidence(text: Text, lines) -> str:
    return " | ".join("%s: %s" % (lh, text.rec(lh)["text"]) for lh in lines)


@dataclass
class _Node:
    """Compile-time state of one node (draft = the dict handed to common.number_tree)."""

    src: DraftNode
    draft: dict
    parent: _Node | None
    children: list = field(default_factory=list)
    start_offset: int | None = None  # located root-text start (global offset), via lemma or cut
    chapters: tuple | None = None  # (first, last) 品 index of a basis-chapter span


def compile_outline(
    parsed: Parsed,
    commentary: Text,
    root: Text,
    *,
    authored_path=None,
    authored_bytes: bytes | None = None,
) -> tuple:
    """Check the parsed outline against the two CBETA texts and build the document.

    Returns (doc, warnings); raises AuthoredError listing every failed check."""
    h = parsed.header
    errors: list = []
    warnings: list = []
    mode = h.get("outline_mode") or "sutra"
    name = parsed.name

    def err(node: DraftNode, msg):
        errors.append("%s:%d: %s: %s" % (name, node.lineno, node.heading, msg))

    def warn(node: DraftNode, msg):
        warnings.append("%s:%d: %s: %s" % (name, node.lineno, node.heading, msg))

    flat: list = []

    def build(drafts, parent):
        out = []
        for k, dn in enumerate(drafts, 1):
            node = _Node(dn, {}, parent)
            flat.append(node)
            _fill(node, k)
            node.children = build(dn.children, node)
            out.append(node)
        return out

    def _fill(node: _Node, sibling_index: int):
        dn, f = node.src, node.src.fields
        notes = list(f.get("note", []))
        origin = f.get("origin", "explicit")
        if origin not in ORIGINS:
            err(dn, "@origin must be one of %s" % "|".join(ORIGINS))
        node_class = f.get("class", "sutra-span")
        if node_class not in CLASSES:
            err(dn, "@class must be one of %s" % "|".join(CLASSES))
        flags = [x.strip() for x in f.get("flags", "").split(",") if x.strip()]
        for x in flags:
            if x not in FLAGS:
                err(dn, "unknown flag %r" % x)
        flags = list(dict.fromkeys(flags))
        n = None
        if "n" in f:
            if re.fullmatch(r"[1-9][0-9]*", f["n"]):
                n = int(f["n"])
            else:
                err(dn, "@n must be a positive integer")
        # commentary lineheads
        exp, ann, src = f.get("exp"), _none(f.get("ann")), _none(f.get("src"))
        lemsrc = _none(f.get("lemsrc"))
        for key, lh in (("exp", exp), ("ann", ann), ("src", src), ("lemsrc", lemsrc)):
            if lh is not None and not commentary.has(lh):
                err(dn, "@%s %s is not a line of %s" % (key, lh, _id(commentary)))
        ok_lines = all(lh is None or commentary.has(lh) for lh in (exp, ann, src, lemsrc))
        # verbatim heading (+ extent)
        evidence = f.get("evidence")
        if origin == "explicit" and ok_lines and exp is not None:
            refs = [("src", src)] if src else [(k, v) for k, v in (("ann", ann), ("exp", exp)) if v]
            mulu = [m for m in commentary.rec(exp)["mulu"] if m.get("text") == dn.heading]
            hit, ref_used = None, None
            for _, ref in refs:
                hits = commentary.find_near(dn.heading, ref)
                if hits:
                    hit, ref_used = hits[0], ref
                    break
            auto = None
            if hit:
                auto = _evidence(commentary, hit["lines"])
                if strip_punct(dn.heading) == dn.heading and hit["text"] != dn.heading:
                    warn(
                        dn,
                        "heading matches only with punctuation ignored: source has %r"
                        % hit["text"],
                    )
            elif mulu:
                m = mulu[0]
                auto = "cb:mulu type=%s level=%s on %s: %s" % (
                    m.get("type"),
                    m.get("level"),
                    exp,
                    m.get("text"),
                )
            else:
                labels = [m.get("text") or "" for m in commentary.rec(exp)["mulu"]]
                err(
                    dn,
                    "heading not found within ±%d lines of %s (punctuation ignored)%s"
                    % (
                        WINDOW,
                        " / ".join("@%s %s" % kv for kv in refs),
                        "; cb:mulu on @exp: %s" % ", ".join(labels) if labels else "",
                    ),
                )
            if evidence is None:
                evidence = auto
            if "ext" in f:
                ext_refs = [ref_used] if ref_used else [v for _, v in refs]
                if not any(commentary.find_near(f["ext"], r) for r in ext_refs):
                    err(
                        dn,
                        "@ext %r not found within ±%d lines of %s"
                        % (f["ext"], WINDOW, " / ".join(ext_refs)),
                    )
        if origin in ("inferred", "editorial") and not evidence:
            err(
                dn,
                "origin %s needs @evidence (the cue, or who supplied it and on what ground)"
                % origin,
            )
        confidence = None
        if origin == "inferred":
            try:
                confidence = float(f["conf"])
                if not 0 <= confidence <= 1:
                    raise ValueError
            except (KeyError, ValueError):
                err(dn, "origin inferred needs @conf in [0, 1]")
        elif "conf" in f:
            warn(
                dn,
                "@conf ignored: confidence applies only to origin inferred (origin is %s)" % origin,
            )
        if "ext" in f and node_class == "commentary-internal":
            warn(dn, "@ext on a commentary-internal node: an extent formula measures root text")
        if "ext" in f and origin != "explicit":
            warn(dn, "@ext kept but not checked against the commentary (origin is %s)" % origin)
        # root-text span
        root_text = None
        if node_class == "commentary-internal":
            for key in ("root", "lemma", "cut", "basis", "endbasis"):
                if key in f:
                    err(dn, "commentary-internal node carries @%s (it has no root-text span)" % key)
        elif "root" in f:
            root_text = _root_span(node, f, notes)
        elif mode == "sutra" and "unmapped" not in flags:
            err(dn, "sutra-span node without @root must carry @flags=unmapped")
        if node_class == "sutra-span" and "root" not in f:
            for key in ("lemma", "cut", "basis", "endbasis"):
                if key in f:
                    err(dn, "@%s without @root" % key)
        # lemma in the commentary: near @exp, or near @lemsrc (the line it is quoted on) when
        # the node's topic marker stands further from the 經 line
        if lemsrc is not None and "lemma" not in f:
            err(dn, "@lemsrc without @lemma (it gives the line the lemma is quoted on)")
        lem_key, lem_line = ("lemsrc", lemsrc) if lemsrc is not None else ("exp", exp)
        if "lemma" in f and ok_lines and lem_line is not None:
            lem_hits = commentary.find_near(f["lemma"], lem_line)
            if not lem_hits:
                err(
                    dn,
                    "@lemma %r not found within ±%d lines of @%s %s"
                    % (f["lemma"], WINDOW, lem_key, lem_line),
                )
            elif lemsrc is not None and exp is not None:
                _check_lemsrc(dn, f["lemma"], lem_hits, lemsrc, exp, notes)
        node.draft = {
            "heading_src": dn.heading,
            "heading_en": "",
            "display_label": f.get("label") or generated_label(dn.level, sibling_index),
            "source_node_id": None,
            "origin": origin,
            **({"confidence": confidence} if confidence is not None else {}),
            "node_class": node_class,
            "flags": flags,
            "child_count_announced": n,
            "extent_announced": f.get("ext"),
            "locations": {
                "scheme": "cbeta-kepan",
                "commentary": {"announced": ann, "explained": exp},
                "root_text": root_text,
            },
            "evidence": evidence or "",
            "notes": notes,
        }

    def _check_lemsrc(dn: DraftNode, lemma: str, hits: list, lemsrc: str, exp: str, notes: list):
        # @lemsrc keeps @exp honest: the lemma is quoted (經「…」) before the topic marker, and no
        # other lemma is quoted from there to the end of the @exp line, so @exp stays inside the
        # lemma's block (a wrong @exp on the line that opens the next 經「 fails too)
        gap = commentary.pos[exp] - commentary.pos[lemsrc]
        if gap <= 0:
            err(dn, "@lemsrc %s does not come before @exp %s" % (lemsrc, exp))
            return
        index = commentary.index
        starts = [(index.global_offset(*h["start"]), h) for h in hits]
        quoted = [h for g, h in starts if index.text[max(0, g - 2) : g] == "經「"]
        if not quoted:
            err(
                dn,
                "@lemma %r near @lemsrc %s is not quoted as a lemma (no 經「 immediately before "
                "it)" % (lemma, lemsrc),
            )
            return
        exp_end = index.global_offset(exp, len(commentary.rec(exp)["text"]))
        between = index.text[index.global_offset(*quoted[0]["end"]) : exp_end]
        if "經「" in between:
            err(
                dn,
                "another lemma (經「) is quoted between @lemsrc %s and @exp %s: the node's lemma "
                "must be the last one quoted before its topic marker" % (lemsrc, exp),
            )
            return
        notes.append(
            "lemma 經「%s」 quoted on %s, %d line(s) before commentary.explained (the commentary "
            "in between quotes no other lemma)" % (lemma, lemsrc, gap)
        )

    def _root_span(node: _Node, f: dict, notes: list):
        dn = node.src
        m = re.fullmatch(r"(\S+)\.\.(\S+)", f["root"])
        if not m:
            err(dn, "@root must be <start>..<end>")
            return None
        start, end = m.groups()
        bad = [lh for lh in (start, end) if not root.has(lh)]
        for lh in bad:
            err(dn, "@root line %s is not a line of %s" % (lh, _id(root)))
        basis = f.get("basis")
        if basis not in BASES:
            err(dn, "@root needs @basis, one of %s" % "|".join(BASES))
        endbasis = f.get("endbasis")
        if endbasis is not None and endbasis not in END_BASES:
            err(dn, "@endbasis must be one of %s" % "|".join(END_BASES))
        # the locator field must back the basis: @lemma iff lemma, @cut iff manual
        if basis == "lemma" and "lemma" not in f:
            err(dn, "@basis=lemma needs @lemma (the commentary's quoted lemma)")
        if "lemma" in f and basis != "lemma":
            err(dn, "@lemma given but @basis is %s (a lemma-fixed span is basis lemma)" % basis)
        if basis == "manual" and "cut" not in f:
            err(dn, "@basis=manual needs @cut (the root-text words where the span starts)")
        if "cut" in f and basis != "manual":
            err(dn, "@cut given but @basis is %s (an annotator's cut is basis manual)" % basis)
        span = {"start": start, "end": end, "basis": basis}
        if endbasis is not None:
            span["end_basis"] = endbasis
        if bad:
            return span
        if not root.before(start, end):
            err(dn, "@root starts at %s, after its end %s" % (start, end))
        starts, ends = root.chapters()
        if basis == "chapter":
            if start not in starts:
                err(dn, "basis chapter: %s carries no 品 cb:mulu in %s" % (start, _id(root)))
            if end not in ends:
                err(dn, "basis chapter: %s is not the last line of a 品 in %s" % (end, _id(root)))
            if start in starts and end in ends:
                node.chapters = (starts[start], ends[end])
        if endbasis == "chapter" and (end not in ends or ends[end] != root.chapter_of(start)):
            in_pin = root.chapter_of(start)
            err(
                dn,
                "end_basis chapter: %s is not the last line of %s"
                % (
                    end,
                    "the 品 that %s is in" % start
                    if in_pin is not None
                    else "a 品 (%s is in no 品)" % start,
                ),
            )
        if "lemma" in f and basis == "lemma":
            located, raw, why = _resolve_lemma(f["lemma"], start, end, endbasis is not None)
            if located is None:
                err(
                    dn,
                    "@lemma %r does not resolve to @root %s..%s: %s"
                    % (f["lemma"], start, end, why),
                )
            else:
                node.start_offset = located
                span["raw"] = raw
        if "cut" in f and basis == "manual":
            hits = [h for h in root.find_all(f["cut"]) if root.line_of(h[0]) == start]
            if not hits:
                where = sorted({root.line_of(h[0]) for h in root.find_all(f["cut"])})
                err(
                    dn,
                    "@cut %r does not start on %s (found on: %s)"
                    % (f["cut"], start, ", ".join(where[:5]) or "nowhere"),
                )
            elif node.start_offset is None:
                node.start_offset = hits[0][0]
                notes.append(
                    "root span starts at the annotator's cut %s (%s, root-text wording); the "
                    "commentary quotes no lemma for this division" % (hits[0][2]["text"], start)
                )
        return span

    def _resolve_lemma(lemma, start, end, loose_end):
        splits = [(lemma[:i], lemma[i + 1 :]) for i, ch in enumerate(lemma) if ch == "至"]
        splits = [(a, b) for a, b in splits if strip_punct(a) and strip_punct(b)]
        whole = not splits
        if whole:
            splits = [(lemma, None)]
        why = []
        for a, b in splits:
            a_hits = [x for x in root.find_all(a) if root.line_of(x[0]) == start]
            if not a_hits:
                where = sorted({root.line_of(x[0]) for x in root.find_all(a)})
                why.append(
                    "「%s」 does not start on %s (found on: %s)"
                    % (a, start, ", ".join(where[:5]) or "nowhere")
                )
                continue
            a_start, a_end, _ = a_hits[0]
            if b is None:
                b_last = root.line_of(a_end - 1)
            else:
                b_hits = [x for x in root.find_all(b) if x[0] >= a_end]
                if not b_hits:
                    why.append("「%s」 not found after 「%s」" % (b, a))
                    continue
                b_last = root.line_of(b_hits[0][1] - 1)
            ok = root.before(b_last, end) if loose_end else b_last == end
            if ok:
                return a_start, lemma, None
            why.append(
                "「%s」 ends on %s, not %s%s"
                % (b or a, b_last, end, " or before" if loose_end else "")
            )
        return None, None, "; ".join(why)

    def _coverage(values: list, flat_nodes: list) -> list:
        # coverage_span header lines -> [(_Node or None for `document`, span dict)], checked
        # against the tree and the two texts (spans inclusive, like every span in the gold)
        out, scopes = [], []
        line = parsed.header_lineno.get("coverage_span", 0)

        def cerr(k, msg):
            errors.append("%s:%d: header coverage_span #%d: %s" % (name, line, k, msg))

        def subtree(nd):
            got = [nd]
            for c in nd.children:
                got.extend(subtree(c))
            return got

        for k, value in enumerate(values, 1):
            m = COVERAGE_RE.fullmatch(value)
            if not m:
                cerr(
                    k,
                    "expected 'root=<heading>@<commentary line>|document "
                    "commentary=<start>..<end> root_text=<start>..<end> max_level=<n>|full'",
                )
                continue
            g = m.groupdict()
            nd = None
            if g["root"] != "document":
                heading, _, exp = g["root"].rpartition("@")
                hits = [
                    x
                    for x in flat_nodes
                    if x.src.heading == heading and x.src.fields.get("exp") == exp
                ]
                if len(hits) != 1:
                    cerr(k, "root %s names %d nodes, not one" % (g["root"], len(hits)))
                    continue
                nd = hits[0]
            bad = [x for x in (g["c1"], g["c2"]) if not commentary.has(x)]
            bad += [x for x in (g["r1"], g["r2"]) if not root.has(x)]
            if bad:
                cerr(k, "not a line of its file: %s" % ", ".join(bad))
                continue
            if not commentary.before(g["c1"], g["c2"]) or not root.before(g["r1"], g["r2"]):
                cerr(k, "a span starts after its end")
                continue
            max_level = None if g["max"] == "full" else int(g["max"])
            scope = subtree(nd) if nd is not None else list(flat_nodes)
            if nd is not None and max_level is not None and max_level < nd.src.level:
                cerr(k, "max_level %d is above the root's level %d" % (max_level, nd.src.level))
            if max_level is not None:
                if nd is None:
                    scope = [x for x in scope if x.src.level <= max_level]
                else:
                    deep = [x for x in scope if x.src.level > max_level]
                    for x in deep[:3]:
                        cerr(
                            k,
                            "%s (line %d) is deeper than max_level %d"
                            % (x.src.heading, x.src.lineno, max_level),
                        )
            lo_c, hi_c = commentary.pos[g["c1"]], commentary.pos[g["c2"]]
            lo_r, hi_r = root.pos[g["r1"]], root.pos[g["r2"]]
            ids = {id(x) for x in scope}
            for x in scope:
                loc = x.draft["locations"]
                for lh in loc["commentary"].values():
                    if (
                        lh is not None
                        and commentary.has(lh)
                        and not lo_c <= commentary.pos[lh] <= hi_c
                    ):
                        cerr(
                            k,
                            "%s (line %d): commentary line %s outside %s..%s"
                            % (x.src.heading, x.src.lineno, lh, g["c1"], g["c2"]),
                        )
                rt = loc["root_text"]
                leaf = not any(id(c) in ids for c in x.children)
                known = rt is not None and root.has(rt["start"]) and root.has(rt["end"])
                if (
                    leaf
                    and known
                    and not (lo_r <= root.pos[rt["start"]] and root.pos[rt["end"]] <= hi_r)
                ):
                    cerr(
                        k,
                        "%s (line %d): leaf span %s..%s outside %s..%s"
                        % (x.src.heading, x.src.lineno, rt["start"], rt["end"], g["r1"], g["r2"]),
                    )
            scopes.append((nd, max_level, scope))
            out.append(
                (
                    nd,
                    {
                        "commentary": {"start": g["c1"], "end": g["c2"]},
                        "root_text": {"start": g["r1"], "end": g["r2"]},
                        "max_level": max_level,
                    },
                )
            )
        # the `document` entry's depth limit: deeper nodes must lie in another entry's subtree
        covered = {id(x) for nd, _, scope in scopes if nd is not None for x in scope}
        for k, (nd, max_level, _) in enumerate(scopes, 1):
            if nd is None and max_level is not None:
                loose = [x for x in flat_nodes if x.src.level > max_level and id(x) not in covered]
                for x in loose[:3]:
                    cerr(
                        k,
                        "%s (line %d) is deeper than max_level %d and in no other entry"
                        % (x.src.heading, x.src.lineno, max_level),
                    )
        return out

    roots_ = build(parsed.roots, None)

    # child counts
    for node in flat:
        n = node.draft["child_count_announced"]
        if n is not None and n != len(node.children):
            if "count_mismatch" not in node.draft["flags"]:
                node.draft["flags"].append("count_mismatch")
            node.draft["notes"].append(
                "child_count_announced %d but %d children in this outline" % (n, len(node.children))
            )
            warn(
                node.src,
                "@n %d but %d children: flag count_mismatch added" % (n, len(node.children)),
            )

    # basis chapter: a node without chapter-basis children spans one 品; a node with them spans
    # exactly its first child's first 品 to its last child's last 品
    for node in flat:
        if node.chapters is None:
            continue
        kids = [c for c in node.children if c.chapters is not None]
        if not kids and node.chapters[0] != node.chapters[1]:
            err(
                node.src,
                "basis chapter: span runs over 品 #%d-#%d; a node without 品 children must end "
                "on the last line of the 品 it starts in"
                % (node.chapters[0] + 1, node.chapters[1] + 1),
            )
        elif kids and (kids[0].chapters[0], kids[-1].chapters[1]) != node.chapters:
            err(
                node.src,
                "basis chapter: span covers 品 #%d-#%d but its 品 children cover #%d-#%d"
                % (
                    node.chapters[0] + 1,
                    node.chapters[1] + 1,
                    kids[0].chapters[0] + 1,
                    kids[-1].chapters[1] + 1,
                ),
            )

    # next-node rule for root-text ends
    order = {id(nd): k for k, nd in enumerate(flat)}

    def subtree_end(node):
        while node.children:
            node = node.children[-1]
        return order[id(node)] + 1

    for node in flat:
        rt = node.draft["locations"]["root_text"]
        if rt is None or not root.has(rt["end"]):
            continue
        nxt = next(
            (
                m
                for m in flat[subtree_end(node) :]
                if m.draft["node_class"] == "sutra-span"
                and m.draft["locations"]["root_text"] is not None
            ),
            None,
        )
        if nxt is None:
            continue
        if node.chapters is not None and nxt.chapters is not None:
            # chapter-basis neighbours: the next one starts with the very next 品
            if nxt.chapters[0] != node.chapters[1] + 1:
                err(
                    node.src,
                    "root span ends with 品 #%d but the next division (line %d, %s) starts with "
                    "品 #%d: 品 spans must be consecutive"
                    % (node.chapters[1] + 1, nxt.src.lineno, nxt.src.heading, nxt.chapters[0] + 1),
                )
            continue
        if nxt.start_offset is None:
            continue
        want = root.last_char_line_before(nxt.start_offset)
        if want != rt["end"]:
            err(
                node.src,
                "root span ends on %s, but the next division (line %d, %s) starts after "
                "text ending on %s" % (rt["end"], nxt.src.lineno, nxt.src.heading, want),
            )

    coverage = _coverage(h.get("coverage_span") or [], flat)

    if errors:
        raise AuthoredError(errors)

    def to_draft(node):
        d = dict(node.draft)
        d["children"] = [to_draft(c) for c in node.children]
        return d

    nodes = common.number_tree([to_draft(r) for r in roots_])
    node_id = {id(nd): nodes[k]["id"] for k, nd in enumerate(flat)}
    coverage_spans = [
        {
            "node_id": node_id[id(nd)] if nd is not None else None,
            "heading_src": nd.src.heading if nd is not None else None,
            **span,
        }
        for nd, span in coverage
    ]
    doc = {
        "metadata": _metadata(
            parsed, nodes, commentary, root, authored_path, authored_bytes, coverage_spans
        ),
        "nodes": nodes,
    }
    return doc, warnings


def _id(text: Text) -> str:
    return text.records[0]["linehead"].split("_p")[0] if text.records else "?"


def _metadata(
    parsed, nodes, commentary: Text, root: Text, authored_path, authored_bytes, coverage_spans=()
) -> dict:
    h = parsed.header
    eval_only = h["eval_only"].lower()
    if eval_only not in ("true", "false"):
        raise AuthoredError(
            [
                "%s:%d: header: eval_only must be true or false"
                % (parsed.name, parsed.header_lineno["eval_only"])
            ]
        )
    source_notes = list(h["source_note"])
    for label, text in (("commentary", commentary), ("root text", root)):
        if text.path is not None:
            source_notes.append(
                "%s: %s sha256 %s"
                % (label, common.repo_relative(text.path), common.sha256_file(text.path))
            )
    fields = {
        "source_file": common.repo_relative(commentary.path) if commentary.path else "<records>",
        "source_sha256": common.sha256_file(commentary.path) if commentary.path else None,
        "authored_file": common.repo_relative(authored_path) if authored_path else parsed.name,
        "authored_sha256": hashlib.sha256(authored_bytes).hexdigest() if authored_bytes else None,
        "text_id": _none(h.get("text_id")),
        "text_title_src": h["text_title_src"],
        "text_title_en": h["text_title_en"],
        "author": _none(h.get("author")),
        "source_language": "lzh",
        "format_note": " ".join([FORMAT_NOTE] + h["format_note"]),
        "origin_note": h.get("origin_note")
        or "explicit = the heading is the commentary's own "
        "wording (verbatim-checked); inferred / editorial carry their evidence.",
        "generated_by": GENERATED_BY,
        "anomalies": list(h["anomaly"]),
        "source_document": {
            "kind": h.get("source_kind") or "commentary",
            "text_id": _none(h.get("commentary_id")),
            "title": h["source_title"],
            "url": None,
            "notes": source_notes,
        },
        "outline_mode": h.get("outline_mode") or "sutra",
        "root_text_id": h["root_text_id"],
        "commentary_id": _none(h.get("commentary_id")),
        "scheme_id": h["scheme_id"],
        "seeded_by": _none(h["seeded_by"]),
        "gold_status": h["gold_status"],
        "licence": {
            "id": _none(h.get("licence_id")),
            "holder": _none(h.get("licence_holder")),
            "statement": h["licence_statement"],
            "evidence": _none(h.get("licence_evidence")),
        },
        "eval_only": eval_only == "true",
        "cbeta_release": _none(h["cbeta_release"]),
        "display_label_rule": DISPLAY_LABEL_RULE,
        "coverage": list(h["coverage"]),
        "split_notes": list(h["split_note"]),
    }
    if parsed.header.get("coverage_span"):
        fields["coverage_spans"] = list(coverage_spans)
    return common.zh_metadata(nodes, **fields)


# -------------------------------------------------------------------------------------------- CLI


def compile_file(txt_path, commentary_xml=None, root_xml=None, cbeta_dir=None) -> tuple:
    """Parse and compile one outline text; (doc, warnings, validator report)."""
    txt_path = Path(txt_path)
    data = txt_path.read_bytes()
    parsed = parse(data.decode("utf-8"), common.repo_relative(txt_path))
    cbeta_dir = Path(cbeta_dir) if cbeta_dir else common.REPO_ROOT / "data" / "raw" / "cbeta"
    com_id = _none(parsed.header.get("commentary_id"))
    if commentary_xml is None:
        if com_id is None:
            raise AuthoredError(
                ["%s: header: commentary_id is null; pass --commentary-xml" % parsed.name]
            )
        commentary_xml = find_cbeta_xml(com_id, cbeta_dir)
    if root_xml is None:
        root_xml = find_cbeta_xml(parsed.header["root_text_id"], cbeta_dir)
    doc, warnings = compile_outline(
        parsed,
        load_text(commentary_xml),
        load_text(root_xml),
        authored_path=txt_path,
        authored_bytes=data,
    )
    report = common.validate(doc, parsed.name)
    return doc, warnings, report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m chinese_workflow.eval.gold.authored",
        description="Compile a hand-authored *.outline.txt into a zh-kepan gold outline (JSON).",
    )
    ap.add_argument(
        "txt", help="the outline text, e.g. data/reference-outlines/T0262/kuiji-xuanzan/outline.txt"
    )
    ap.add_argument("-o", "--output", required=True, help="JSON file to write")
    ap.add_argument("--cbeta-dir", help="where <id>.xml files live (default data/raw/cbeta)")
    ap.add_argument("--commentary-xml", help="CBETA file of the commentary (overrides lookup)")
    ap.add_argument("--root-xml", help="CBETA file of the root text (overrides lookup)")
    args = ap.parse_args(argv)
    try:
        doc, warnings, report = compile_file(
            args.txt, args.commentary_xml, args.root_xml, args.cbeta_dir
        )
    except AuthoredError as exc:
        for msg in exc.messages:
            print("error: " + msg, file=sys.stderr)
        print(
            "FAIL %s: %d error(s), nothing written" % (args.txt, len(exc.messages)), file=sys.stderr
        )
        return 1
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    for msg in warnings:
        print("warning: " + msg, file=sys.stderr)
    for f in report.errors + report.warnings:
        print("validator: " + f.render(), file=sys.stderr)
    if report.errors:
        print("FAIL %s: validator errors, nothing written" % args.txt, file=sys.stderr)
        return 1
    out = common.write_json(doc, args.output)
    meta = doc["metadata"]
    print(
        "PASS %s -> %s: %d nodes, depth %d, per level %s, %d warning(s), %d validator warning(s)"
        % (
            args.txt,
            common.repo_relative(out),
            meta["node_count"],
            meta["max_depth"],
            meta["nodes_per_level"],
            len(warnings),
            len(report.warnings),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
