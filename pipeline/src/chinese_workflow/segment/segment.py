"""chinese_workflow.segment.segment — sentence boundaries over one target text (§6, strategy 1–2).

Input : the target InputText (chinese_workflow.ingest.load_input_text; its role says whether it is
        a commentary) and, optionally, its outlined-text (outlined-text/1,
        pipeline/schemas/outlined-text.schema.json) over the same reading text (sha256 checked).
Output: sentences/1 (pipeline/schemas/sentences.schema.json):
        {schema, strategy, punctuation_regime, sentence_rule, target, sentences: [{id, char_start,
        char_end, kind: prose|verse_line|lemma|gloss|heading, node_id}]}, offsets global to the
        target's reading text, start inclusive, end exclusive.

Coverage. The sentences tile [first placed outlined-text span start (0 without outlined-text),
len(text)) with no gap or overlap. Text before the first span is not segmented; text after the
last span, and in outlined-text gaps, is, with node_id null.

Rules (both strategies):
  * a sentence ends after one of 。？！；, together with the run of terminators, closing
    quotes/brackets (」』）〕】》〉”’) and spaces (U+3000, U+0020) that directly follows it:
    「…甚多，世尊。」 ends after 」;
  * a sentence never crosses an outlined-text span or gap boundary. The brief puts this under
    strategy 2 only; it is applied to strategy 1 too because sentences/1 promises it for every
    file (schema description) and the chunker relies on it — the strategies differ only in the
    breaks below;
  * a piece that holds nothing but punctuation and spaces (ingest.lines.is_punct) is merged into
    the previous sentence, or into the next one when a span boundary separates it from the
    previous; it stays alone only when its span holds nothing else.
Strategy 2 (default) adds hard breaks and kinds:
  * heading: a head / jhead whose text stands at its offset in the reading text, and a line whose
    text is exactly a cb:mulu label (spaces ignored; also without the label's leading number,
    '26 陀羅尼品'); trailing spaces go with the heading. The position of every cb:mulu is a break
    as well (a CBETA TOC node starts there);
  * verse_line: each line with in_verse, split at its caesuras and after each run of U+3000 inside
    it (CBETA marks pāda boundaries with caesura in T verse: 「若不順我呪，|惱亂說法者，);
  * commentary targets only — the lemma/gloss switch: at a sentence start, 經「…」 followed by 。
    (kept) or directly by a gloss marker is one `lemma` sentence whatever punctuation the quote
    holds; a gloss marker (贊曰 / 述曰 / 釋曰) at a sentence start begins the gloss, and every
    sentence after a lemma or a gloss marker is `gloss` until the next heading; before the first
    of them it is `prose`. Verified on T34n1723 (玄贊: 經「…」。贊曰：); 述曰/釋曰 and other
    commentaries' lemma forms (「…」者, 經云, 論：) are HYPOTHESIS / not handled.
Strategy 1 kinds are all `prose`.

node_id = the outlined-text span (leaf or preamble) holding the sentence, null outside any span.

Known limits: in_verse is a line property of ingest.lines, so a line that starts in prose and
opens an lg mid-line would be treated as verse (none in T0262, T1666, T1753, T1703; the lines
records carry no lg/l offsets); `p` boundaries are not recorded either, so an unpunctuated
dhāraṇī runs into the next sentence (T0262 0058b19–c04); unpunctuated texts (no 。？！；) give
one sentence per hard segment.
"""

from __future__ import annotations

import bisect
import re

from ..common.jsonio import read_json
from ..common.paths import SCHEMAS
from ..ingest.lines import is_punct
from ..ingest.text import InputText

SCHEMA = "sentences/1"
KINDS = ("prose", "verse_line", "lemma", "gloss", "heading")
TERMINATORS = "。？！；"
CLOSERS = "」』）〕】》〉”’"
SPACES = "　 "
GLOSS_MARKERS = ("贊曰", "述曰", "釋曰")
LEMMA_OPENERS = ("經",)
MAX_LEMMA = 400  # characters; a longer 「…」 is not taken as a lemma

_GLOSS_RE = re.compile("[%s]*(?:%s)" % (SPACES, "|".join(GLOSS_MARKERS)))
_LEMMA_RE = re.compile("[%s]*(?:%s)「" % (SPACES, "|".join(LEMMA_OPENERS)))
_MULU_NUM_RE = re.compile(r"^[0-9]+\s+")

RULE_1 = (
    "strategy 1: a sentence ends after 。？！； plus the terminators, closing quotes/brackets and "
    "spaces directly following it; outlined-text span boundaries are never crossed; "
    "punctuation-only pieces join the previous sentence"
)
RULE_2 = (
    "strategy 2: strategy 1, plus hard breaks at headings (head/jhead text, a line equal to a "
    "cb:mulu label) and at every cb:mulu position, verse lines (in_verse lines split at caesuras "
    "and U+3000 runs) as verse_line units"
)
RULE_2_COMMENTARY = (
    ", and the lemma/gloss switch of commentaries (經「…」。 at a sentence start is one lemma; "
    "贊曰/述曰/釋曰 at a sentence start begins the gloss)"
)


# ------------------------------------------------------------------------------ outlined-text


def _placed_spans(ot: dict | None, n: int) -> list:
    """[(start, end, node_id)] of the non-empty outlined-text spans, sorted, clipped to [0, n]."""
    if not ot:
        return []
    out = []
    for sp in ot.get("spans", []):
        s, e = max(0, sp["char_start"]), min(n, sp["char_end"])
        if s < e:
            out.append((s, e, sp["node_id"]))
    out.sort(key=lambda t: (t[0], t[1]))
    return out


def _span_bounds(ot: dict | None, spans: list, n: int) -> set:
    bounds = set()
    for s, e, _ in spans:
        bounds.update((s, e))
    for g in (ot or {}).get("gaps", []):
        bounds.update((max(0, min(n, g["char_start"])), max(0, min(n, g["char_end"]))))
    return bounds


class _NodeLookup:
    """node_id of the span holding a position (the latest-starting one when spans overlap)."""

    def __init__(self, spans: list):
        self.spans = spans
        self.starts = [s for s, _, _ in spans]
        self.max_end = []
        m = -1
        for _, e, _ in spans:
            m = max(m, e)
            self.max_end.append(m)

    def __call__(self, pos: int):
        i = bisect.bisect_right(self.starts, pos) - 1
        while i >= 0 and self.max_end[i] > pos:
            s, e, node = self.spans[i]
            if s <= pos < e:
                return node
            i -= 1
        return None


def _check_target(target: InputText, ot: dict | None) -> None:
    if not ot:
        return
    t = ot.get("target", {})
    if t.get("sha256") != target.sha256:
        raise ValueError(
            "outlined-text target sha256 %s does not match the target text %s (%s)"
            % (t.get("sha256"), target.sha256, target.text_id)
        )


# ------------------------------------------------------------------------ strategy-2 regions


def _merge_regions(regions: list) -> list:
    out = []
    for s, e in sorted(regions):
        if out and s < out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [tuple(r) for r in out]


def _headings(target: InputText) -> tuple:
    """(heading regions [(s, e)], cb:mulu positions) over the target text."""
    text, idx = target.text, target.index
    regions, mulu_pos = [], set()
    for i, rec in enumerate(target.lines):
        ls, ll = idx.starts[i], idx.lengths[i]
        for h in rec["heads"]:
            head = h["text"]
            g = ls + h["offset"]
            if head.strip(SPACES) and text[g : g + len(head)] == head:
                e = g + len(head)
                while e < len(text) and text[e] in SPACES:
                    e += 1
                regions.append((g, e))
        line = rec["text"].strip(SPACES)
        for m in rec["mulu"]:
            mulu_pos.add(ls + m["offset"])
            label = (m["text"] or "").strip(SPACES)
            if line and label and line in (label, _MULU_NUM_RE.sub("", label)):
                regions.append((ls, ls + ll))
    return _merge_regions(regions), mulu_pos


def _verse_pieces(target: InputText) -> list:
    """[(s, e)] verse_line units: in_verse lines cut at caesuras and after inner U+3000 runs."""
    text, idx = target.text, target.index
    pieces = []
    for i, rec in enumerate(target.lines):
        ll = idx.lengths[i]
        if not rec["in_verse"] or ll == 0:
            continue
        ls = idx.starts[i]
        cuts = {0, ll}
        cuts.update(c for c in rec["caesuras"] if 0 < c < ll)
        line = text[ls : ls + ll]
        for m in re.finditer("　+", line):
            if m.start() > 0 and m.end() < ll:
                cuts.add(m.end())
        cuts = sorted(cuts)
        pieces.extend((ls + a, ls + b) for a, b in zip(cuts, cuts[1:]) if a < b)
    return pieces


def _containing(regions: list, starts: list, pos: int):
    i = bisect.bisect_right(starts, pos) - 1
    if i >= 0 and regions[i][0] <= pos < regions[i][1]:
        return regions[i]
    return None


# -------------------------------------------------------------------------------------- scan


class _Scanner:
    def __init__(self, text: str, end: int, breaks: list, commentary: bool,
                 headings: list, verse: list):
        self.text, self.end, self.breaks, self.commentary = text, end, breaks, commentary
        self.break_set = set(breaks)
        self.headings, self.h_starts = headings, [s for s, _ in headings]
        self.verse, self.v_starts = verse, [s for s, _ in verse]
        self.special_starts = sorted(set(self.h_starts) | set(self.v_starts))

    def next_break(self, pos: int) -> int:
        return self.breaks[bisect.bisect_right(self.breaks, pos)]

    def gloss_marker_at(self, pos: int) -> bool:
        return _GLOSS_RE.match(self.text, pos) is not None

    def lemma_end(self, pos: int):
        """End of a lemma 經「…」(。) starting at pos, or None."""
        text = self.text
        m = _LEMMA_RE.match(text, pos)
        if not m:
            return None
        depth, j = 1, m.end()
        stop = min(self.end, pos + MAX_LEMMA)
        while j < stop:
            c = text[j]
            if c == "「":
                depth += 1
            elif c == "」":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        else:
            return None
        q = j + 1
        if q < self.end and text[q] == "。":
            q += 1
        elif not (q >= self.end or q in self.break_set or self.gloss_marker_at(q)):
            return None
        while q < self.end and text[q] in SPACES:
            q += 1
        k = bisect.bisect_right(self.special_starts, pos)
        if k < len(self.special_starts) and self.special_starts[k] < q:
            return None  # a lemma never swallows a heading or a verse line
        return q

    def sentence_end(self, pos: int, limit: int) -> int:
        text, j = self.text, pos
        while j < limit:
            if text[j] in TERMINATORS:
                j += 1
                while j < limit and (text[j] in TERMINATORS or text[j] in CLOSERS):
                    j += 1
                while j < limit and text[j] in SPACES:
                    j += 1
                return j
            j += 1
        return limit

    def scan(self, start: int) -> list:
        units, pos, state, lemma_until = [], start, "prose", None
        while pos < self.end:
            nb = self.next_break(pos)
            reg = _containing(self.headings, self.h_starts, pos)
            if reg:
                end, kind, state, lemma_until = min(reg[1], nb), "heading", "prose", None
            elif (v := _containing(self.verse, self.v_starts, pos)) is not None:
                end, kind = min(v[1], nb), "verse_line"
            elif lemma_until is not None and pos < lemma_until:
                end, kind = min(lemma_until, nb), "lemma"
            else:
                lemma_until = None
                le = self.lemma_end(pos) if self.commentary else None
                if le is not None:
                    lemma_until, state = le, "gloss"
                    end, kind = min(le, nb), "lemma"
                else:
                    if self.commentary and self.gloss_marker_at(pos):
                        state = "gloss"
                    end, kind = self.sentence_end(pos, nb), state
            units.append([pos, end, kind])
            pos = end
        return units


def _merge_blank(units: list, text: str, bounds: set) -> list:
    """Merge punctuation/space-only pieces into the previous sentence, else into the next one,
    never across an outlined-text boundary."""

    def blank(u):
        return all(is_punct(ch) for ch in text[u[0] : u[1]])

    back = []
    for u in units:
        if back and blank(u) and back[-1][1] == u[0] and u[0] not in bounds:
            back[-1][1] = u[1]
        else:
            back.append(list(u))
    out, i = [], 0
    while i < len(back):
        u = back[i]
        if blank(u) and i + 1 < len(back) and u[1] not in bounds:
            back[i + 1][0] = u[0]
        else:
            out.append(u)
        i += 1
    return out


# --------------------------------------------------------------------------------------- API


def run(target: InputText, outlined_text: dict | None = None, *, strategy: int = 2) -> dict:
    """sentences/1 for `target` (see the module docstring)."""
    if strategy not in (1, 2):
        raise ValueError("strategy must be 1 or 2, got %r" % (strategy,))
    _check_target(target, outlined_text)
    text = target.text
    n = len(text)
    spans = _placed_spans(outlined_text, n)
    if spans:
        start = spans[0][0]
    elif outlined_text:
        start = max(0, min(n, outlined_text.get("coverage", {}).get("start", 0)))
    else:
        start = 0
    bounds = {b for b in _span_bounds(outlined_text, spans, n) if start <= b <= n}

    role = target.role or ((outlined_text or {}).get("target") or {}).get("role")
    commentary = strategy == 2 and role == "commentary"
    breaks = {start, n} | bounds
    headings, verse = [], []
    if strategy == 2:
        headings, mulu_pos = _headings(target)
        verse = _verse_pieces(target)
        # a heading wins over a verse piece it overlaps (heading regions are merged and sorted, so
        # the last one starting before the piece's end is the only one to test)
        h_starts = [s for s, _ in headings]

        def overlaps_heading(v):
            i = bisect.bisect_left(h_starts, v[1]) - 1
            return i >= 0 and headings[i][1] > v[0]

        verse = [v for v in verse if not overlaps_heading(v)]
        breaks |= mulu_pos
        for s, e in headings + verse:
            breaks.update((s, e))
    breaks = sorted(b for b in breaks if start <= b <= n)

    units = _Scanner(text, n, breaks, commentary, headings, verse).scan(start)
    units = _merge_blank(units, text, bounds)
    node_of = _NodeLookup(spans)
    sentences = [
        {"id": "s%d" % (k + 1), "char_start": s, "char_end": e, "kind": kind,
         "node_id": node_of(s)}
        for k, (s, e, kind) in enumerate(units)
    ]
    rule = RULE_1 if strategy == 1 else RULE_2 + (RULE_2_COMMENTARY if commentary else "")
    return {
        "schema": SCHEMA,
        "strategy": strategy,
        "punctuation_regime": target.info.get("punctuation"),
        "sentence_rule": rule,
        "target": {
            "text_id": target.text_id,
            "sha256": target.sha256,
            "role": role,
            "first_linehead": target.first_linehead,
            "last_linehead": target.last_linehead,
            "length": n,
        },
        "sentences": sentences,
    }


def validate(doc: dict) -> None:
    """Raise jsonschema.ValidationError unless `doc` is valid sentences/1."""
    import jsonschema

    schema = read_json(SCHEMAS / "sentences.schema.json")
    jsonschema.Draft202012Validator(schema).validate(doc)


def check(doc: dict, target: InputText, outlined_text: dict | None = None) -> list:
    """Invariant problems of a sentences/1 doc (empty list = none): full contiguous coverage to the
    end of the text, no empty sentence, no sentence across an outlined-text boundary, node_id =
    the span holding the sentence."""
    problems = []
    n = len(target.text)
    sents = doc["sentences"]
    spans = _placed_spans(outlined_text, n)
    bounds = sorted(_span_bounds(outlined_text, spans, n))
    if doc["target"]["sha256"] != target.sha256:
        problems.append("target sha256 differs")
    if not sents:
        return problems + (["no sentences"] if n else [])
    if sents[-1]["char_end"] != n:
        problems.append("last sentence ends at %d, text length %d" % (sents[-1]["char_end"], n))
    if spans and sents[0]["char_start"] != spans[0][0]:
        problems.append("first sentence starts at %d, first span at %d"
                        % (sents[0]["char_start"], spans[0][0]))
    node_of = _NodeLookup(spans)
    for a, b in zip(sents, sents[1:]):
        if a["char_end"] != b["char_start"]:
            problems.append("%s/%s not contiguous" % (a["id"], b["id"]))
    for s in sents:
        cs, ce = s["char_start"], s["char_end"]
        if not cs < ce:
            problems.append("%s is empty" % s["id"])
        k = bisect.bisect_right(bounds, cs)
        if k < len(bounds) and bounds[k] < ce:
            problems.append("%s crosses the outlined-text boundary %d" % (s["id"], bounds[k]))
        if s["node_id"] != node_of(cs):
            problems.append("%s node_id %r, span %r" % (s["id"], s["node_id"], node_of(cs)))
    return problems


# --------------------------------------------------------------------------------------- CLI


def main(argv=None) -> int:
    import argparse
    import sys
    from collections import Counter

    from ..common.jsonio import write_json
    from ..common.splits import SplitGuard
    from ..ingest.run import parse_span
    from ..ingest.text import load_input_text

    ap = argparse.ArgumentParser(
        prog="python -m chinese_workflow.segment",
        description="Segment stage: target text (+ outlined-text) -> sentences.json (sentences/1).",
    )
    ap.add_argument("--target", required=True, help="CBETA file id or path to a P5 XML file")
    ap.add_argument("--span", help="FIRST..LAST lineheads, inclusive (default: the outlined-text "
                    "target's span, else the whole file)")
    ap.add_argument("--role", choices=("root", "commentary"),
                    help="target role (default: the outlined-text target's role)")
    ap.add_argument("--outlined-text", help="outlined-text.json over the same target text")
    ap.add_argument("--strategy", type=int, choices=(1, 2), default=2)
    ap.add_argument("--frozen", help="tag of a frozen outliner (lifts the split guard)")
    ap.add_argument("--out", required=True, help="output path of sentences.json")
    args = ap.parse_args(argv)

    ot = read_json(args.outlined_text) if args.outlined_text else None
    ot_target = (ot or {}).get("target") or {}
    span = parse_span(args.span)
    if span is None and ot_target.get("first_linehead"):
        span = (ot_target["first_linehead"], ot_target["last_linehead"])
    role = args.role or ot_target.get("role")
    target = load_input_text(args.target, span=span, role=role)
    SplitGuard(frozen=args.frozen).check_lines(
        [rec["linehead"] for rec in target.lines], purpose="segment"
    )
    doc = run(target, ot, strategy=args.strategy)
    validate(doc)
    problems = check(doc, target, ot)
    if problems:
        for p in problems[:20]:
            print("invariant: %s" % p, file=sys.stderr)
        return 1
    write_json(doc, args.out)
    kinds = Counter(s["kind"] for s in doc["sentences"])
    print("%s: %d sentences (%s), strategy %d -> %s" % (
        target.text_id, len(doc["sentences"]),
        ", ".join("%s %d" % (k, kinds[k]) for k in KINDS if kinds[k]), args.strategy, args.out))
    return 0
