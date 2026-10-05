"""eval.chunk_invariants — check an interlinear outline (chunks/1) against its input artefacts.

Input:  chunks.json (chunks/1), outlined-text.json (outlined-text/1), sentences.json (sentences/1);
        optionally outline.json (the zh-kepan outline) and the text of chunks.md.
Output: {"ok": bool, "invariants": {name: {"ok": bool, "violations": [str, ...], ...}},
         "stats": {chunks, median_chars, median_sentences, over_cap, over_budget, fallback, ...}}.

    python -m chinese_workflow.eval.chunk_invariants chunks.json outlined-text.json sentences.json \
        [--outline outline.json] [--md chunks.md]    (default --md: chunks.md beside chunks.json)

Invariants (docs/outliner-design.md §7; mapping D6, D14):

  schema               chunks.json validates against pipeline/schemas/chunks.schema.json
  size_cap             n_sentences <= sentence_cap (split-leaf windows exempt); n_chars <= the
                       length budget unless the chunk holds a single sentence
  coverage             chunks tile the target text [0, length) in order, no gap or overlap; each
                       text has n_chars = char_end - char_start characters; the concatenated texts
                       hash to the target's sha256 (every chunk text is the target slice);
                       ids are c1..cN
  sentence_alignment   no sentence straddles two chunks; sentence_ids = the sentences inside it
  no_sub_leaf_split    a chunk boundary never falls inside an outlined-text span unless every chunk
                       of that span is a split-leaf window inside it; leaf_ids = the spans a chunk
                       overlaps
  merge_within_parent  a chunk's units share one merge group (a preamble's own node, a leaf's
                       parent); node_id = the smallest node covering them; outline_path ends there
  md_round_trip        chunks.md (given, or re-rendered here) reads back to the same markers,
                       announcements and chunk texts
  monotone_locators    loc_start/loc_end are CBETA refs that advance through the text (a linehead
                       once left is never revisited, offsets rise within a line) and agree with the
                       outlined-text lineheads where a chunk starts or ends with a span
  nodes_exist          every node named by a chunk, marker or announcement is in the outline (the
                       outline.json when given, else the span nodes and their id-prefix ancestors);
                       every before_chunk / after_chunk names a chunk
  markers_taken_up     every taken-up node (its subtree owns a span) has exactly one marker, placed
                       before the chunk holding its first character; markers are in document order;
                       with the outline: indicator, heading and locator follow the marker rule

This module reads files and dicts only; it does not import the outline or chunk stages. Its
chunks.md reader and writer are a second, independent implementation of the typography in
chunk/render.py.
"""

from __future__ import annotations

import argparse
import bisect
import re
import statistics
import sys
from pathlib import Path

from ..common import jsonio
from ..common.lineheads import is_ref, strip_offset
from ..common.lineheads import parse as parse_ref
from ..common.paths import SCHEMAS

INVARIANTS = ("schema", "size_cap", "coverage", "sentence_alignment", "no_sub_leaf_split",
              "merge_within_parent", "md_round_trip", "monotone_locators", "nodes_exist",
              "markers_taken_up")
MAX_VIOLATIONS = 100
ZH_ID_RE = re.compile(r"[1-9][0-9]*_[1-9][0-9]*(\.[1-9][0-9]*_[1-9][0-9]*)*\Z")
_MARKER = re.compile(r"\[([^\s\)\]\[]+)\) (.*)\]\Z", re.DOTALL)
_ANNOUNCEMENT = re.compile(r"([^\s\)\]\[]+)\) (.*)\Z", re.DOTALL)


class _Result:
    def __init__(self):
        self.violations: list = []
        self.extra: dict = {}

    def add(self, msg: str) -> None:
        self.violations.append(msg)

    def as_dict(self) -> dict:
        out = {"ok": not self.violations, "violations": self.violations[:MAX_VIOLATIONS]}
        if len(self.violations) > MAX_VIOLATIONS:
            out["n_violations"] = len(self.violations)
        out.update(self.extra)
        return out


# ------------------------------------------------------------------------------ outline structure


class _Tree:
    """Parent relation and node records: from outline.json when given, else from zh-kepan ids."""

    def __init__(self, outlined_text: dict, sentences: dict, doc: dict | None):
        self.doc = doc
        if doc is not None:
            self.nodes = {n["id"]: n for n in doc["nodes"]}
            self.parent = {n["id"]: n.get("parent_id") for n in doc["nodes"]}
            self.rank = {n["id"]: i for i, n in enumerate(doc["nodes"])}
            self.source = "outline"
        else:
            self.nodes = {}
            self.parent = {}
            ids = {s["node_id"] for s in outlined_text["spans"]}
            ids |= {s["node_id"] for s in sentences["sentences"] if s.get("node_id")}
            for nid in ids:
                self._add_prefixes(nid)
            self.rank = {}
            self.source = "outlined-text ids"

    def _add_prefixes(self, nid: str) -> None:
        if not ZH_ID_RE.match(nid):
            self.parent.setdefault(nid, None)
            return
        tokens = nid.split(".")
        for k in range(1, len(tokens) + 1):
            self.parent.setdefault(".".join(tokens[:k]), ".".join(tokens[:k - 1]) or None)

    def known(self, nid) -> bool:
        return nid in self.parent

    def parent_of(self, nid):
        return self.parent.get(nid)

    def path(self, nid) -> list:
        out = []
        while nid is not None:
            out.append(nid)
            nid = self.parent.get(nid)
        return out[::-1]

    def group(self, span: dict) -> tuple:
        nid = span["node_id"]
        if span["kind"] == "preamble":
            return ("node", nid)
        p = self.parent_of(nid)
        return ("top", nid) if p is None else ("node", p)


# ----------------------------------------------------------------------------- md read and write


def _marker_line(m: dict) -> str:
    loc = (" " + m["locator"]) if m["locator"] else ""
    return "[%s) %s%s]" % (m["indicator"], m["heading"], loc)


def render_md_independent(chunks: dict) -> str:
    before: dict = {}
    after: dict = {}
    for m in chunks["markers"]:
        before.setdefault(m["before_chunk"], []).append(_marker_line(m))
    for a in chunks["announcements"]:
        after.setdefault(a["after_chunk"], []).append("%s) %s" % (a["indicator"], a["heading"]))
    runs = []
    for c in chunks["chunks"]:
        runs.append("\n".join(before.get(c["chunk_id"], []) + [c["text"]]
                              + after.get(c["chunk_id"], [])))
    return "\n\n".join(runs) + "\n" if runs else ""


def read_md_independent(md: str) -> dict:
    """{"markers": [(indicator, heading, locator, before_chunk)], "announcements": [(indicator,
    heading, after_chunk)], "chunk_texts": [...], "errors": [...]}; chunk ids positional."""
    lines = md.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    out = {"markers": [], "announcements": [], "chunk_texts": [], "errors": []}
    pending: list = []
    in_text = False
    for i, line in enumerate(lines, 1):
        if line == "":
            if pending:
                out["errors"].append("line %d: markers without a chunk" % i)
                pending = []
            in_text = False
            continue
        if not in_text:
            m = _MARKER.match(line)
            if m:
                rest = m.group(2)
                head, sep, last = rest.rpartition(" ")
                heading, loc = (head, last) if sep and is_ref(last) else (rest, None)
                pending.append((m.group(1), heading, loc))
                continue
            out["chunk_texts"].append(line)
            cid = "c%d" % len(out["chunk_texts"])
            out["markers"].extend(p + (cid,) for p in pending)
            pending = []
            in_text = True
            continue
        a = _ANNOUNCEMENT.match(line)
        if not a:
            out["errors"].append("line %d: not an announcement line after the chunk text" % i)
            continue
        out["announcements"].append((a.group(1), a.group(2), "c%d" % len(out["chunk_texts"])))
    if pending:
        out["errors"].append("end of file: markers without a chunk")
    return out


# ------------------------------------------------------------------------------------ the checks


def _check_schema(chunks, res: _Result) -> None:
    import jsonschema

    schema = jsonio.read_json(SCHEMAS / "chunks.schema.json")
    for e in sorted(jsonschema.Draft202012Validator(schema).iter_errors(chunks),
                    key=lambda e: list(e.absolute_path)):
        res.add("%s: %s" % ("/".join(str(p) for p in e.absolute_path) or "<root>", e.message))


def _check_size(chunks, res: _Result) -> None:
    budget = chunks["metadata"]["size_budget"]
    cap, chars = budget["sentence_cap"], budget["chars"]
    for c in chunks["chunks"]:
        if c["n_sentences"] > cap and c["fallback"] != "split-leaf":
            res.add("%s: %d sentences > cap %d" % (c["chunk_id"], c["n_sentences"], cap))
        if chars is not None and c["n_chars"] > chars and c["n_sentences"] > 1:
            res.add("%s: %d characters > budget %d with %d sentences"
                    % (c["chunk_id"], c["n_chars"], chars, c["n_sentences"]))


def _check_coverage(chunks, outlined_text, res: _Result) -> None:
    target = outlined_text["target"]
    n = target["length"]
    pos = 0
    for k, c in enumerate(chunks["chunks"], 1):
        cid = c["chunk_id"]
        if cid != "c%d" % k:
            res.add("chunk %d has id %r, expected 'c%d'" % (k, cid, k))
        if c["char_start"] != pos:
            kind = "gap" if c["char_start"] > pos else "overlap"
            res.add("%s: %s before it (starts at %d, previous chunk ends at %d)"
                    % (cid, kind, c["char_start"], pos))
        if not c["char_end"] > c["char_start"]:
            res.add("%s: empty or reversed range [%d, %d)" % (cid, c["char_start"], c["char_end"]))
        if not c["n_chars"] == c["char_end"] - c["char_start"] == len(c["text"]):
            res.add("%s: n_chars %d, range %d, text length %d disagree"
                    % (cid, c["n_chars"], c["char_end"] - c["char_start"], len(c["text"])))
        pos = c["char_end"]
    if pos != n:
        res.add("chunks end at %d, target text has %d characters" % (pos, n))
    if jsonio.sha256_text("".join(c["text"] for c in chunks["chunks"])) != target["sha256"]:
        res.add("the concatenated chunk texts are not the target text (sha256 differs)")
    if chunks["metadata"]["target"]["sha256"] != target["sha256"]:
        res.add("metadata.target.sha256 differs from the outlined-text target")


def _chunk_index(chunks):
    starts = [c["char_start"] for c in chunks["chunks"]]

    def at(offset: int):
        i = bisect.bisect_right(starts, offset) - 1
        if i < 0:
            return None
        c = chunks["chunks"][i]
        return i if c["char_start"] <= offset < c["char_end"] else None

    return at


def _check_sentences(chunks, sentences, res: _Result) -> None:
    at = _chunk_index(chunks)
    expected: dict = {c["chunk_id"]: [] for c in chunks["chunks"]}
    for s in sorted(sentences["sentences"], key=lambda s: (s["char_start"], s["char_end"])):
        if s["char_end"] <= s["char_start"]:
            continue
        i, j = at(s["char_start"]), at(s["char_end"] - 1)
        if i is None or j is None:
            res.add("sentence %s [%d, %d) lies outside the chunks"
                    % (s["id"], s["char_start"], s["char_end"]))
            continue
        if i != j:
            res.add("sentence %s straddles %s and %s" % (s["id"], chunks["chunks"][i]["chunk_id"],
                                                       chunks["chunks"][j]["chunk_id"]))
        expected[chunks["chunks"][i]["chunk_id"]].append(s["id"])
    for c in chunks["chunks"]:
        if c["sentence_ids"] != expected[c["chunk_id"]]:
            res.add("%s: sentence_ids %s, the sentences inside it are %s"
                    % (c["chunk_id"], c["sentence_ids"][:8], expected[c["chunk_id"]][:8]))
        if c["n_sentences"] != len(c["sentence_ids"]):
            res.add("%s: n_sentences %d != %d sentence ids"
                    % (c["chunk_id"], c["n_sentences"], len(c["sentence_ids"])))


def _spans(outlined_text) -> list:
    return sorted((s for s in outlined_text["spans"] if s["char_end"] > s["char_start"]),
                  key=lambda s: (s["char_start"], s["char_end"]))


def _overlaps(chunk, spans) -> list:
    return [s for s in spans
            if s["char_start"] < chunk["char_end"] and chunk["char_start"] < s["char_end"]]


def _check_leaf_split(chunks, outlined_text, res: _Result) -> None:
    spans = _spans(outlined_text)
    for s in spans:
        over = [c for c in chunks["chunks"] if c["char_start"] < s["char_end"]
                and s["char_start"] < c["char_end"]]
        if len(over) > 1:
            for c in over:
                inside = c["char_start"] >= s["char_start"] and c["char_end"] <= s["char_end"]
                if c["fallback"] != "split-leaf" or not inside:
                    res.add("%s: a chunk boundary falls inside the %s span of %s [%d, %d) and the "
                            "chunk is not a split-leaf window inside it"
                            % (c["chunk_id"], s["kind"], s["node_id"], s["char_start"],
                               s["char_end"]))
    for c in chunks["chunks"]:
        ids = [s["node_id"] for s in _overlaps(c, spans)]
        if c["leaf_ids"] != ids:
            res.add("%s: leaf_ids %s, the spans it overlaps are %s"
                    % (c["chunk_id"], c["leaf_ids"], ids))
        if c["fallback"] == "unoutlined" and ids:
            res.add("%s: unoutlined but overlaps spans %s" % (c["chunk_id"], ids))
        if c["fallback"] == "split-leaf" and len(ids) != 1:
            res.add("%s: split-leaf window over %d spans" % (c["chunk_id"], len(ids)))


def _check_merge(chunks, outlined_text, tree: _Tree, res: _Result) -> None:
    spans = _spans(outlined_text)
    for c in chunks["chunks"]:
        units = _overlaps(c, spans)
        cid = c["chunk_id"]
        if not units:
            if c["node_id"] is not None or c["outline_path"]:
                res.add("%s: covers no span but has node_id %r" % (cid, c["node_id"]))
            continue
        if len(units) == 1:
            want = units[0]["node_id"]
        else:
            groups = {tree.group(u) for u in units}
            if len(groups) != 1:
                res.add("%s: merges units of different parents %s"
                        % (cid, sorted("%s:%s" % g for g in groups)))
                continue
            kind, want = next(iter(groups))
            if kind == "top":  # two top-level leaves cannot share a group; defensive
                res.add("%s: merges top-level units" % cid)
                continue
        if c["node_id"] != want:
            res.add("%s: node_id %r, the smallest node covering its units is %r"
                    % (cid, c["node_id"], want))
        if not c["outline_path"] or c["outline_path"][-1] != c["node_id"]:
            res.add("%s: outline_path %s does not end at node_id" % (cid, c["outline_path"]))
        elif tree.known(c["node_id"]) and c["outline_path"] != tree.path(c["node_id"]):
            res.add("%s: outline_path %s != root path %s"
                    % (cid, c["outline_path"], tree.path(c["node_id"])))


def _check_md(chunks, md: str | None, res: _Result) -> None:
    res.extra["source"] = "chunks.md" if md is not None else "re-rendered"
    text = md if md is not None else render_md_independent(chunks)
    back = read_md_independent(text)
    for e in back["errors"]:
        res.add(e)
    want_m = [(m["indicator"], m["heading"], m["locator"], m["before_chunk"])
              for m in chunks["markers"]]
    want_a = [(a["indicator"], a["heading"], a["after_chunk"]) for a in chunks["announcements"]]
    want_t = [c["text"] for c in chunks["chunks"]]
    if back["chunk_texts"] != want_t:
        pairs = zip(back["chunk_texts"], want_t, strict=False)
        diff = next((i for i, (x, y) in enumerate(pairs) if x != y),
                    min(len(back["chunk_texts"]), len(want_t)))
        res.add("chunk texts differ (md %d, json %d; first difference at chunk %d)"
                % (len(back["chunk_texts"]), len(want_t), diff + 1))
    if back["markers"] != want_m:
        res.add("markers differ (md %d, json %d): first md-only %s"
                % (len(back["markers"]), len(want_m),
                   next((m for m in back["markers"] if m not in want_m), None)))
    if back["announcements"] != want_a:
        res.add("announcements differ (md %d, json %d)" % (len(back["announcements"]), len(want_a)))


def _check_locators(chunks, outlined_text, res: _Result) -> None:
    # positions in reading order: start(c1), end(c1), start(c2), ...; a chunk's start may equal its
    # own end (one character), but must lie strictly after the previous chunk's end
    seen: set = set()
    prev = None  # (linehead, offset) of the previous position
    for c in chunks["chunks"]:
        for key in ("loc_start", "loc_end"):
            ref = c[key]
            if not is_ref(ref):
                res.add("%s: %s %r is not a CBETA ref" % (c["chunk_id"], key, ref))
                prev = None
                continue
            r = parse_ref(ref)
            here = (r.linehead, r.offset or 0)
            if prev is not None:
                if here[0] == prev[0]:
                    strict = key == "loc_start"
                    if here[1] < prev[1] or (strict and here[1] == prev[1]):
                        res.add("%s: %s %s does not advance past %s:%d"
                                % (c["chunk_id"], key, ref, prev[0], prev[1]))
                elif here[0] in seen:
                    res.add("%s: %s %s returns to a line already left" % (c["chunk_id"], key, ref))
            seen.add(here[0])
            prev = here
    by_start = {s["char_start"]: s for s in _spans(outlined_text)}
    by_end = {s["char_end"]: s for s in _spans(outlined_text)}
    for c in chunks["chunks"]:
        s = by_start.get(c["char_start"])
        if s and is_ref(c["loc_start"]) \
                and strip_offset(c["loc_start"]) != strip_offset(s["linehead_start"]):
            res.add("%s: loc_start %s, span of %s starts on %s"
                    % (c["chunk_id"], c["loc_start"], s["node_id"], s["linehead_start"]))
        s = by_end.get(c["char_end"])
        if s and is_ref(c["loc_end"]) \
                and strip_offset(c["loc_end"]) != strip_offset(s["linehead_end"]):
            res.add("%s: loc_end %s, span of %s ends on %s"
                    % (c["chunk_id"], c["loc_end"], s["node_id"], s["linehead_end"]))


def _check_nodes(chunks, tree: _Tree, res: _Result) -> None:
    res.extra["checked_against"] = tree.source
    ids = {c["chunk_id"] for c in chunks["chunks"]}
    for c in chunks["chunks"]:
        for nid in ([c["node_id"]] if c["node_id"] else []) + c["leaf_ids"] + c["outline_path"]:
            if not tree.known(nid):
                res.add("%s: node %s is not in the outline" % (c["chunk_id"], nid))
    for m in chunks["markers"]:
        if not tree.known(m["node_id"]):
            res.add("marker of unknown node %s" % m["node_id"])
        if m["before_chunk"] not in ids:
            res.add("marker of %s: before_chunk %s is not a chunk"
                    % (m["node_id"], m["before_chunk"]))
    for a in chunks["announcements"]:
        if tree.doc is not None and not tree.known(a["node_id"]):
            res.add("announcement of unknown node %s" % a["node_id"])
        if tree.doc is not None and a["parent_id"] != tree.parent_of(a["node_id"]):
            res.add("announcement of %s: parent_id %s, the outline says %s"
                    % (a["node_id"], a["parent_id"], tree.parent_of(a["node_id"])))
        if a["after_chunk"] not in ids:
            res.add("announcement of %s: after_chunk %s is not a chunk"
                    % (a["node_id"], a["after_chunk"]))


def _locator_rule(node: dict):
    loc = node.get("locations") or {}
    if loc.get("scheme") == "cbeta-kepan":
        comm = loc.get("commentary") or {}
        root = loc.get("root_text") or {}
        return comm.get("announced") or comm.get("explained") or root.get("start")
    if loc.get("scheme") == "cbeta-line":
        return loc.get("start")
    return None


def _check_markers(chunks, outlined_text, tree: _Tree, res: _Result) -> None:
    at = _chunk_index(chunks)
    first: dict = {}
    for s in _spans(outlined_text):
        nid = s["node_id"]
        while nid is not None:
            first[nid] = min(first.get(nid, s["char_start"]), s["char_start"])
            nid = tree.parent_of(nid)
    count: dict = {}
    for m in chunks["markers"]:
        count[m["node_id"]] = count.get(m["node_id"], 0) + 1
    for nid in sorted(first):
        if count.get(nid, 0) != 1:
            res.add("taken-up node %s has %d markers" % (nid, count.get(nid, 0)))
    order = {c["chunk_id"]: i for i, c in enumerate(chunks["chunks"])}
    last = (-1, -1)
    for m in chunks["markers"]:
        nid = m["node_id"]
        if nid not in first:
            res.add("marker of %s, which owns no text in the target" % nid)
            continue
        i = at(first[nid])
        if i is not None and m["before_chunk"] != chunks["chunks"][i]["chunk_id"]:
            res.add("marker of %s before %s; its text starts in %s"
                    % (nid, m["before_chunk"], chunks["chunks"][i]["chunk_id"]))
        key = (order.get(m["before_chunk"], -1), tree.rank.get(nid, 0))
        if key < last:
            res.add("marker of %s is out of document order" % nid)
        last = max(last, key)
        node = tree.nodes.get(nid)
        if node is not None:
            want = (node.get("indicator_display") or nid, node.get("heading_src", ""),
                    _locator_rule(node))
            got = (m["indicator"], m["heading"], m["locator"])
            if got != want:
                res.add("marker of %s reads %s, the outline gives %s" % (nid, got, want))


# ------------------------------------------------------------------------------------ entry point


def _stats(chunks) -> dict:
    cs = chunks["chunks"]
    budget = chunks["metadata"]["size_budget"]
    fallback = {f: sum(1 for c in cs if c["fallback"] == f)
                for f in ("none", "unoutlined", "split-leaf")}
    return {
        "chunks": len(cs),
        "median_chars": statistics.median(c["n_chars"] for c in cs) if cs else 0,
        "median_sentences": statistics.median(c["n_sentences"] for c in cs) if cs else 0,
        "max_chars": max((c["n_chars"] for c in cs), default=0),
        "max_sentences": max((c["n_sentences"] for c in cs), default=0),
        "over_cap": sum(1 for c in cs if c["n_sentences"] > budget["sentence_cap"]),
        "over_budget": sum(1 for c in cs if budget["chars"] is not None
                           and c["n_chars"] > budget["chars"]),
        "merged_chunks": sum(1 for c in cs if len(c["leaf_ids"]) > 1),
        "markers": len(chunks["markers"]),
        "announcements": len(chunks["announcements"]),
        "fallback": fallback,
    }


def check(chunks: dict, outlined_text: dict, sentences: dict, doc: dict | None = None, *,
          md: str | None = None) -> dict:
    """Run every invariant (see the module docstring). `doc` = outline.json; `md` = the text of
    chunks.md (when None, the md round trip re-renders the json with this module's own writer)."""
    tree = _Tree(outlined_text, sentences, doc)
    steps = {
        "schema": lambda r: _check_schema(chunks, r),
        "size_cap": lambda r: _check_size(chunks, r),
        "coverage": lambda r: _check_coverage(chunks, outlined_text, r),
        "sentence_alignment": lambda r: _check_sentences(chunks, sentences, r),
        "no_sub_leaf_split": lambda r: _check_leaf_split(chunks, outlined_text, r),
        "merge_within_parent": lambda r: _check_merge(chunks, outlined_text, tree, r),
        "md_round_trip": lambda r: _check_md(chunks, md, r),
        "monotone_locators": lambda r: _check_locators(chunks, outlined_text, r),
        "nodes_exist": lambda r: _check_nodes(chunks, tree, r),
        "markers_taken_up": lambda r: _check_markers(chunks, outlined_text, tree, r),
    }
    report = {}
    for name in INVARIANTS:
        res = _Result()
        try:
            steps[name](res)
        except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
            res.add("check could not run: %s: %s" % (type(exc).__name__, exc))
        report[name] = res.as_dict()
    try:
        stats = _stats(chunks)
    except (KeyError, TypeError) as exc:
        stats = {"error": "%s: %s" % (type(exc).__name__, exc)}
    return {"ok": all(v["ok"] for v in report.values()), "invariants": report, "stats": stats}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m chinese_workflow.eval.chunk_invariants",
                                 description="Check chunks.json against its inputs.")
    ap.add_argument("chunks")
    ap.add_argument("outlined_text")
    ap.add_argument("sentences")
    ap.add_argument("--outline", default=None)
    ap.add_argument("--md", default=None,
                    help="chunks.md (default: beside chunks.json, if present)")
    ap.add_argument("--out", default=None, help="also write the report here")
    args = ap.parse_args(argv)
    md_path = Path(args.md) if args.md else Path(args.chunks).with_suffix(".md")
    md = md_path.read_text(encoding="utf-8") if md_path.exists() else None
    report = check(jsonio.read_json(args.chunks), jsonio.read_json(args.outlined_text),
                   jsonio.read_json(args.sentences),
                   jsonio.read_json(args.outline) if args.outline else None, md=md)
    if args.out:
        jsonio.write_json(report, args.out)
    sys.stdout.write(jsonio.dumps(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
