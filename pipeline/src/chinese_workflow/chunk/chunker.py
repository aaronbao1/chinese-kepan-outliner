"""chunk.chunker — outlined-text + sentences -> outlined-and-chunked-text (interlinear outline).

Input:  outline.json (zh-kepan outline document), outlined-text.json (outlined-text/1, the outline's
        leaf and preamble spans over the target), sentences.json (sentences/1), and the target
        InputText (chinese_workflow.ingest.text) whose reading text all three index.
Output: a chunks/1 dict (pipeline/schemas/chunks.schema.json): metadata, markers, announcements and
        chunks; `run` also writes chunks.json, chunks.md and chunks.docx (chunk/render.py).

Rules (docs/outliner-design.md §7; mapping D6, D14):

* Units. The outlined-text spans (a leaf's text, or a parent's preamble = its text before its first
  child) are the units; the stretches no span covers (gaps, and anything before the first or after
  the last span) are unoutlined. The chunks tile the whole target text [0, len(text)).
* Merge rule (MERGE_RULE). A unit's *merge group* is the node that owns it as a parent: a preamble
  belongs to its own node P, a leaf to its parent. Maximal runs of consecutive units with the same
  merge group are packed greedily, in text order, into chunks of at most `sentence_cap` sentences
  and `size_chars` characters. So a parent's preamble merges with the leaf children that follow it,
  and sibling leaves merge with each other, but a child that has children of its own ends the run
  (its subtree is a run of its own), and nothing merges across parents. Top-level leaves (no parent)
  are never merged with each other, because no node would cover the merged chunk.
* A unit that alone exceeds the budget is split at sentence ends into windows that respect it
  (`fallback: "split-leaf"`; also used for an oversize preamble): as few windows as a greedy cut
  needs, evened out in sentence count (_balanced_windows). A unit that is one sentence longer than
  `size_chars` stays whole (`fallback: "none"`).
* Unoutlined stretches become windows of the same kind under the same budget
  (`fallback: "unoutlined"`, `node_id: null`).
* A chunk's node_id is the smallest outline node covering its units: the unit's own node for a
  single unit, the merge group for several. topic_category = that node's topic_category, else its
  heading path (heading_src, root first) joined with " / ".
* Markers (Kurt's taken-up markers; docs/outliner-design.md, "Output formats"): a node is taken up
  when its subtree owns text in the target; its marker precedes the chunk that holds the first
  character of that text. Locator = commentary.announced, else commentary.explained, else
  root_text.start (offsets kept). Several markers before one chunk are in outline (pre-)order.
* Announcements (§3.1): every node with a commentary.announced locator gets an announcement line
  after the chunk that holds that position when it lies in the target (a commentary target);
  otherwise (a root target) after its parent's first chunk; failing that, just before its own first
  chunk. Nodes that still cannot be placed are listed in metadata.unplaced_announcements.

Deterministic: no clock, no randomness; the same inputs give the same dict. Imports only
chinese_workflow.common and chinese_workflow.ingest (stage boundary, design §2).
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from pathlib import Path

from ..common import jsonio
from ..common.paths import SCHEMAS
from ..ingest.text import InputText

SCHEMA_ID = "chunks/1"
SCHEMA_PATH = SCHEMAS / "chunks.schema.json"
DEFAULT_SENTENCE_CAP = 6
DEFAULT_SIZE_CHARS = 180
FALLBACKS = ("none", "unoutlined", "split-leaf")

MERGE_RULE = (
    "merge group of a unit = its owning parent (a preamble belongs to its own node, a leaf to its "
    "parent; a top-level leaf is its own group); maximal runs of consecutive units with one merge "
    "group are packed greedily in text order while the chunk stays within sentence_cap sentences "
    "and size_chars characters; a unit that alone exceeds the budget is split at sentence ends "
    "(split-leaf, windows evened out); unoutlined stretches are cut the same way (unoutlined)"
)
MARKER_RULE = (
    "a node whose subtree owns text in the target is taken up; its marker precedes the chunk "
    "holding that text's first character; locator = commentary.announced, else "
    "commentary.explained, else root_text.start"
)
ANNOUNCEMENT_RULE = (
    "a node with commentary.announced is announced after the chunk holding that position when it "
    "lies in the target, else after its parent's first chunk, else just before its own first chunk"
)


# ----------------------------------------------------------------------------------- data classes


@dataclass(frozen=True)
class Atom:
    """An indivisible stretch: one sentence, or characters that no sentence covers (sid None)."""

    start: int
    end: int
    sid: str | None

    @property
    def n_sentences(self) -> int:
        return 1 if self.sid is not None else 0


@dataclass
class Segment:
    """A unit (an outlined-text span) or an unoutlined stretch, with its atoms."""

    start: int
    end: int
    span: dict | None
    group: tuple
    atoms: list = field(default_factory=list)

    @property
    def n_sentences(self) -> int:
        return sum(a.n_sentences for a in self.atoms)

    @property
    def n_chars(self) -> int:
        return self.end - self.start


@dataclass
class _Chunk:
    units: list  # Segments whose spans the chunk unions (one Segment for split / unoutlined)
    atoms: list
    fallback: str

    @property
    def start(self) -> int:
        return self.atoms[0].start

    @property
    def end(self) -> int:
        return self.atoms[-1].end


# --------------------------------------------------------------------------------------- helpers


def _fits(n_sentences: int, n_chars: int, cap: int, budget: int | None) -> bool:
    return n_sentences <= cap and (budget is None or n_chars <= budget)


def _windows(atoms: list, cap: int, budget: int | None) -> list:
    """Greedy windows of consecutive atoms within the budget; an atom that alone exceeds it stands
    alone."""
    out, cur, ns, nc = [], [], 0, 0
    for a in atoms:
        s, c = a.n_sentences, a.end - a.start
        if cur and not _fits(ns + s, nc + c, cap, budget):
            out.append(cur)
            cur, ns, nc = [], 0, 0
        cur.append(a)
        ns += s
        nc += c
    if cur:
        out.append(cur)
    return out


def _balanced_windows(atoms: list, cap: int, budget: int | None) -> list:
    """As few windows as the greedy cut needs, but evened out: the smallest sentence cap (from
    ceil(sentences / windows) up) that still gives that number of windows under the same length
    budget. 20 sentences at cap 6 -> 5 + 5 + 5 + 5 rather than 6 + 6 + 6 + 2."""
    base = _windows(atoms, cap, budget)
    k = len(base)
    total = sum(a.n_sentences for a in atoms)
    if k < 2 or total == 0:
        return base
    for c in range(max(1, -(-total // k)), cap):
        w = _windows(atoms, c, budget)
        if len(w) == k:
            return w
    return base


def _pack(run: list, cap: int, budget: int | None) -> list:
    """Chunks of one run of units that share a merge group (see MERGE_RULE)."""
    out: list = []
    cur: list = []
    ns = nc = 0

    def flush():
        nonlocal cur, ns, nc
        if cur:
            out.append(_Chunk(units=list(cur), atoms=[a for u in cur for a in u.atoms],
                              fallback="none"))
        cur, ns, nc = [], 0, 0

    for seg in run:
        s, c = seg.n_sentences, seg.n_chars
        if not _fits(s, c, cap, budget) and len(seg.atoms) > 1:
            flush()
            for w in _balanced_windows(seg.atoms, cap, budget):
                out.append(_Chunk(units=[seg], atoms=w, fallback="split-leaf"))
            continue
        if cur and not _fits(ns + s, nc + c, cap, budget):
            flush()
        cur.append(seg)
        ns += s
        nc += c
    flush()
    return out


def _commentary(node: dict) -> dict:
    loc = node.get("locations") or {}
    return (loc.get("commentary") or {}) if loc.get("scheme") == "cbeta-kepan" else {}


def marker_locator(node: dict) -> str | None:
    """commentary.announced, else commentary.explained, else root_text.start (offsets kept)."""
    loc = node.get("locations") or {}
    scheme = loc.get("scheme")
    if scheme == "cbeta-kepan":
        comm = loc.get("commentary") or {}
        root = loc.get("root_text") or {}
        return comm.get("announced") or comm.get("explained") or root.get("start")
    if scheme == "cbeta-line":
        return loc.get("start")
    return None


def _check_inputs(outlined_text: dict, sentences: dict, target: InputText) -> None:
    if outlined_text.get("schema") != "outlined-text/1":
        raise ValueError("outlined-text: schema %r, expected 'outlined-text/1'"
                         % outlined_text.get("schema"))
    if sentences.get("schema") != "sentences/1":
        raise ValueError("sentences: schema %r, expected 'sentences/1'" % sentences.get("schema"))
    sha = target.sha256
    ot, st = outlined_text["target"], sentences["target"]
    if ot["sha256"] != sha:
        raise ValueError("outlined-text was built over a different target text "
                         "(sha256 %s, target %s)" % (ot["sha256"][:12], sha[:12]))
    if st["sha256"] != sha:
        raise ValueError("sentences were built over a different target text (sha256 %s, target %s)"
                         % (st["sha256"][:12], sha[:12]))
    if ot["length"] != len(target.text):
        raise ValueError("outlined-text target length %d != target text length %d"
                         % (ot["length"], len(target.text)))


def _segments(spans: list, n: int, parent_of: dict) -> list:
    """Units and unoutlined stretches tiling [0, n), in text order."""
    segs: list = []
    pos = 0
    for sp in spans:
        a, b = sp["char_start"], sp["char_end"]
        if a < pos:
            raise ValueError("outlined-text spans overlap at offset %d (%s)" % (a, sp["node_id"]))
        if b > n:
            raise ValueError("span of %s ends at %d, past the target text (%d)"
                             % (sp["node_id"], b, n))
        if a > pos:
            segs.append(Segment(pos, a, None, ("gap", pos)))
        nid = sp["node_id"]
        if sp["kind"] == "preamble":
            group = ("node", nid)
        elif parent_of[nid] is None:
            group = ("top", nid)
        else:
            group = ("node", parent_of[nid])
        segs.append(Segment(a, b, sp, group))
        pos = b
    if pos < n:
        segs.append(Segment(pos, n, None, ("gap", pos)))
    return segs


def _assign_atoms(segs: list, sentences: list, n: int) -> int:
    """Distribute the sentences over the segments; characters no sentence covers become
    sentence-less atoms, cut at segment boundaries. Returns the number of uncovered characters.
    A sentence that crosses a segment boundary is a contract violation of the segment stage
    (ValueError)."""
    sents = sorted((s for s in sentences if s["char_end"] > s["char_start"]),
                   key=lambda s: (s["char_start"], s["char_end"]))
    starts = [g.start for g in segs]
    uncovered = 0
    pos = 0

    def add(a: int, b: int, sid: str | None):
        i = bisect.bisect_right(starts, a) - 1
        seg = segs[i]
        if b > seg.end:
            if sid is not None:
                raise ValueError("sentence %s [%d, %d) crosses the unit boundary at %d"
                                 % (sid, a, b, seg.end))
            seg.atoms.append(Atom(a, seg.end, None))
            add(seg.end, b, None)
            return
        seg.atoms.append(Atom(a, b, sid))

    for s in sents:
        a, b = s["char_start"], s["char_end"]
        if a < pos:
            raise ValueError("sentences overlap at offset %d (%s)" % (a, s["id"]))
        if b > n:
            raise ValueError("sentence %s ends at %d, past the target text (%d)" % (s["id"], b, n))
        if a > pos:
            uncovered += a - pos
            add(pos, a, None)
        add(a, b, s["id"])
        pos = b
    if pos < n:
        uncovered += n - pos
        add(pos, n, None)
    return uncovered


def _runs(segs: list) -> list:
    """Maximal runs of consecutive segments with the same merge group (gaps are runs of one)."""
    runs: list = []
    for seg in segs:
        if runs and seg.span is not None and runs[-1][-1].span is not None \
                and runs[-1][-1].group == seg.group:
            runs[-1].append(seg)
        else:
            runs.append([seg])
    return runs


# ------------------------------------------------------------------------------------ build_chunks


def build_chunks(doc: dict, outlined_text: dict, sentences: dict, target: InputText, *,
                 sentence_cap: int = DEFAULT_SENTENCE_CAP,
                 size_chars: int | None = DEFAULT_SIZE_CHARS,
                 outline_ref: dict | None = None) -> dict:
    """The chunks/1 document of `target` (see the module docstring for the rules)."""
    if sentence_cap < 1:
        raise ValueError("sentence_cap must be >= 1")
    if size_chars is not None and size_chars < 1:
        raise ValueError("size_chars must be >= 1 or None")
    _check_inputs(outlined_text, sentences, target)
    text = target.text
    n = len(text)

    nodes = {nd["id"]: nd for nd in doc["nodes"]}
    rank = {nd["id"]: i for i, nd in enumerate(doc["nodes"])}
    parent_of = {nd["id"]: nd.get("parent_id") for nd in doc["nodes"]}
    spans = sorted((s for s in outlined_text["spans"] if s["char_end"] > s["char_start"]),
                   key=lambda s: (s["char_start"], s["char_end"]))
    for sp in spans:
        if sp["node_id"] not in nodes:
            raise ValueError("outlined-text span of %r: no such node in the outline"
                             % sp["node_id"])

    segs = _segments(spans, n, parent_of)
    uncovered = _assign_atoms(segs, sentences["sentences"], n)
    raw: list = []
    for run in _runs(segs):
        if run[0].span is None:
            raw.extend(_Chunk(units=[run[0]], atoms=w, fallback="unoutlined")
                       for w in _balanced_windows(run[0].atoms, sentence_cap, size_chars))
        else:
            raw.extend(_pack(run, sentence_cap, size_chars))

    def path_of(nid: str) -> list:
        out = []
        while nid is not None:
            out.append(nid)
            nid = parent_of[nid]
        return out[::-1]

    def topic(nid: str) -> str:
        tc = nodes[nid].get("topic_category")
        if tc:
            return tc
        return " / ".join(nodes[p].get("heading_src", "") for p in path_of(nid))

    chunks = []
    for k, ch in enumerate(raw, 1):
        if ch.fallback == "unoutlined":
            node_id, leaf_ids = None, []
        else:
            leaf_ids = [u.span["node_id"] for u in ch.units]
            node_id = leaf_ids[0] if len(ch.units) == 1 else ch.units[0].group[1]
        sids = [a.sid for a in ch.atoms if a.sid is not None]
        chunks.append({
            "chunk_id": "c%d" % k,
            "node_id": node_id,
            "leaf_ids": leaf_ids,
            "outline_path": path_of(node_id) if node_id else [],
            "topic_category": topic(node_id) if node_id else None,
            "loc_start": target.locate(ch.start),
            "loc_end": target.locate(ch.end - 1),
            "char_start": ch.start,
            "char_end": ch.end,
            "sentence_ids": sids,
            "n_sentences": len(sids),
            "n_chars": ch.end - ch.start,
            "fallback": ch.fallback,
            "text": text[ch.start:ch.end],
        })

    # ---- markers: taken-up nodes, before the chunk holding their subtree's first character
    chunk_starts = [c["char_start"] for c in chunks]

    def chunk_at(offset: int) -> int:
        return max(bisect.bisect_right(chunk_starts, offset) - 1, 0)

    first: dict = {}
    for sp in spans:
        nid = sp["node_id"]
        while nid is not None:
            if sp["char_start"] < first.get(nid, n + 1):
                first[nid] = sp["char_start"]
            nid = parent_of[nid]
    marker_chunk = {nid: chunk_at(off) for nid, off in first.items()}
    markers = [
        {"node_id": nid,
         "indicator": nodes[nid].get("indicator_display") or nid,
         "heading": nodes[nid].get("heading_src", ""),
         "locator": marker_locator(nodes[nid]),
         "before_chunk": chunks[marker_chunk[nid]]["chunk_id"]}
        for nid in sorted(marker_chunk, key=lambda x: (marker_chunk[x], rank[x]))
    ]

    # ---- announcements
    placed: list = []
    unplaced: list = []
    for nd in doc["nodes"]:
        announced = _commentary(nd).get("announced")
        if not announced or not chunks:
            continue
        nid, parent = nd["id"], nd.get("parent_id")
        if target.contains(announced):
            idx = chunk_at(min(target.offset(announced), n - 1))
        elif parent in marker_chunk:
            idx = marker_chunk[parent]
        elif marker_chunk.get(nid, 0) > 0:
            idx = marker_chunk[nid] - 1
        else:
            unplaced.append(nid)
            continue
        placed.append((idx, rank[nid], nd))
    placed.sort(key=lambda t: (t[0], t[1]))
    announcements = [
        {"node_id": nd["id"],
         "indicator": nd.get("indicator_display") or nd["id"],
         "heading": nd.get("heading_src", ""),
         "after_chunk": chunks[idx]["chunk_id"],
         "parent_id": nd.get("parent_id")}
        for idx, _, nd in placed
    ]

    fallback_counts = {f: sum(1 for c in chunks if c["fallback"] == f) for f in FALLBACKS}
    ot_target = outlined_text["target"]
    return {
        "schema": SCHEMA_ID,
        "metadata": {
            "target": {"text_id": target.text_id, "sha256": target.sha256,
                       "first_linehead": target.first_linehead,
                       "last_linehead": target.last_linehead, "length": n},
            "target_role": ot_target["role"],
            "outline_ref": dict(outline_ref or outlined_text["outline_ref"]),
            "sentence_rule": sentences["sentence_rule"],
            "sentence_strategy": sentences.get("strategy"),
            "size_budget": {"sentence_cap": sentence_cap, "chars": size_chars},
            "merge_rule": MERGE_RULE,
            "marker_rule": MARKER_RULE,
            "announcement_rule": ANNOUNCEMENT_RULE,
            "chunk_ids": "c<k>, k = 1-based position in text order",
            "coverage": {"start": 0, "end": n},
            "unplaced_announcements": unplaced,
            "counts": {
                "chunks": len(chunks),
                "units": sum(1 for s in segs if s.span is not None),
                "merged_chunks": sum(1 for c in chunks if len(c["leaf_ids"]) > 1),
                "markers": len(markers),
                "announcements": len(announcements),
                "announcements_unplaced": len(unplaced),
                "sentences": sum(c["n_sentences"] for c in chunks),
                "chars": n,
                "unoutlined_chars": sum(s.n_chars for s in segs if s.span is None),
                "chars_without_sentence": uncovered,
                "fallback": fallback_counts,
            },
        },
        "markers": markers,
        "announcements": announcements,
        "chunks": chunks,
    }


# ------------------------------------------------------------------------------ validation and run


def validate_chunks(chunks: dict) -> list:
    """Error messages of chunks.schema.json for `chunks` (empty list = valid)."""
    import jsonschema

    schema = jsonio.read_json(SCHEMA_PATH)
    validator = jsonschema.Draft202012Validator(schema)
    return ["%s: %s" % ("/".join(str(p) for p in e.absolute_path) or "<root>", e.message)
            for e in sorted(validator.iter_errors(chunks), key=lambda e: list(e.absolute_path))]


def parse_span(span: str | None) -> tuple | None:
    """'A..B' -> (A, B); None stays None."""
    if not span:
        return None
    a, sep, b = span.partition("..")
    if not sep or not a or not b:
        raise ValueError("span must be FIRST..LAST lineheads, got %r" % span)
    return a, b


def run(outline_path, outlined_text_path, sentences_path, target_source, out_dir, *,
        span: tuple | None = None, sentence_cap: int = DEFAULT_SENTENCE_CAP,
        size_chars: int | None = DEFAULT_SIZE_CHARS, frozen: str | None = None) -> dict:
    """Read the three artefacts and the target, write chunks.json / chunks.md / chunks.docx into
    out_dir. The target span defaults to the outlined-text's first..last linehead; the split guard
    checks it (test / reserve lines need `frozen`). Returns {"paths": {...}, "chunks": dict}."""
    from ..common.outline_doc import pipeline_commit
    from ..common.paths import repo_relative
    from ..common.splits import SplitGuard
    from ..ingest.text import load_input_text
    from . import render

    doc = jsonio.read_json(outline_path)
    outlined_text = jsonio.read_json(outlined_text_path)
    sentences = jsonio.read_json(sentences_path)
    outline_ref = {"path": repo_relative(outline_path), "sha256": jsonio.sha256_file(outline_path)}
    recorded = outlined_text["outline_ref"].get("sha256")
    if recorded and recorded != outline_ref["sha256"]:
        raise ValueError("outlined-text was built from a different outline (sha256 %s, %s is %s)"
                         % (recorded[:12], outline_path, outline_ref["sha256"][:12]))
    ot = outlined_text["target"]
    span = span or (ot["first_linehead"], ot["last_linehead"])
    target = load_input_text(target_source, span=span, role=ot["role"])
    guard = SplitGuard(frozen=frozen)
    guard.check_lines([r["linehead"] for r in target.lines], purpose="chunk target")

    chunks = build_chunks(doc, outlined_text, sentences, target, sentence_cap=sentence_cap,
                          size_chars=size_chars, outline_ref=outline_ref)
    commit = pipeline_commit()
    chunks["metadata"]["generated_by"] = "chinese_workflow.chunk @ %s%s" % (
        (commit["commit"] or "unknown")[:12], "+dirty" if commit["dirty"] else "")
    chunks["metadata"]["inputs"] = {
        "outlined_text": {"path": repo_relative(outlined_text_path),
                          "sha256": jsonio.sha256_file(outlined_text_path)},
        "sentences": {"path": repo_relative(sentences_path),
                      "sha256": jsonio.sha256_file(sentences_path)},
        "target_source": str(target_source),
        "span": list(span),
    }
    chunks["metadata"]["split_guard"] = guard.report
    errors = validate_chunks(chunks)
    if errors:
        raise ValueError("chunks.json fails its schema: %s" % errors[:5])

    out_dir = Path(out_dir)
    paths = {"chunks_json": jsonio.write_json(chunks, out_dir / "chunks.json")}
    md_path = out_dir / "chunks.md"
    md_path.write_text(render.render_md(chunks), encoding="utf-8")
    paths["chunks_md"] = md_path
    paths["chunks_docx"] = render.render_docx(chunks, out_dir / "chunks.docx")
    return {"paths": {k: str(v) for k, v in paths.items()}, "chunks": chunks}
