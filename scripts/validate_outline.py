#!/usr/bin/env python3
"""scripts/validate_outline.py — validate independent-outline JSON files against the base or the Chinese (zh-kepan)
outline schema, plus the structural invariants a JSON Schema cannot express.

Input : one or more outline JSON files, e.g.
            tests/fixtures/outline-base/minimal-base.json   synthetic base-schema example
            tests/fixtures/outline-zh/minimal.json          synthetic zh-kepan example
        context/baseline/outline-schema.json                base schema (the Tibetan workflow's independent-outline format)
        context/baseline/outline-schema-zh.json             Chinese kēpàn extension, a superset of the base
                                                            (divergence D15 in docs/chinese-workflow-mapping.md)
Output: stdout only — one summary line per file (PASS/FAIL, schema used, node count, depth, error/warning counts),
        then its errors and warnings, then a total line. Writes nothing.
        Exit status: 0 = every file passed; 1 = at least one file failed (or, with --strict, has a warning);
        2 = bad invocation (argparse).

Usage : python3 scripts/validate_outline.py FILE [FILE ...]
        python3 scripts/validate_outline.py --schema zh tests/fixtures/outline-base/minimal-base.json    force a schema
        python3 scripts/validate_outline.py --strict FILE          warnings count as failures
        python3 scripts/validate_outline.py --quiet FILE           summary lines only
        python3 scripts/validate_outline.py --max-messages 0 FILE  print every message (default: first 25 per file)

Schema choice (--schema auto, the default): a document whose metadata.outline_profile is "zh-kepan" is validated
against outline-schema-zh.json, anything else against outline-schema.json. --schema base|zh forces one. The zh
*structural* rules below follow the document's profile, not the schema chosen, so forcing --schema zh on a base document
checks it exactly as a base document (it must pass: the zh schema is a superset).

Structural checks (error unless marked "warning"; codes in brackets are what tests assert on):
  [duplicate-id]           node ids are unique.
  [order-not-increasing] / [order-position]
                           node.order is strictly increasing and equals the 1-based position in the nodes array.
  [level-path] [id-path] [path-token-level]
                           level == len(path); id == '.'.join(path); the k-th path token ends in '_k'.
  [parent-unresolved] [parent-after-child] [parent-not-ancestor] [level-parent] [parent-null]
                           parent_id names a node that precedes this one and whose path is a proper prefix of this
                           node's path; when it is the structural parent (path[:-1]), parent level == level - 1;
                           parent_id is null only at level 1 or when no ancestor is present.
  [parent-not-structural] [parent-not-nearest] / warning [parent-nearest-ancestor] [parent-missing]
                           Kurt's convention (context/baseline/outline-schema.json, parent_id): when the
                           structural parent is absent from the source, parent_id is the nearest *present* ancestor
                           and the node carries a note — accepted with a warning in base documents; an error under
                           zh-kepan, whose ids are generated, so every structural parent exists.
  [not-preorder]           document order is a pre-order traversal: each node's parent is the previous node or one of
                           the previous node's ancestors.
  [sibling-index] [id-sibling-index]
                           where sibling_index is present (required under zh-kepan): among the nodes sharing a
                           parent_id, sibling_index runs 1..k in document order; under zh-kepan the last id token's
                           value equals sibling_index.
  [metadata-count] [metadata-depth] [metadata-per-level]
                           metadata.node_count / max_depth / nodes_per_level agree with the nodes.
  [cbeta-order]            a CBETA span's start <= end when both are in the same text file (compared as page,
                           register, line, and character offset when both carry one): cbeta-line start/end and
                           cbeta-kepan root_text start/end. Refs in two files of one metadata.work_files entry are
                           ordered by the file's position in that entry first. Pages of different front-matter series
                           ('a001' vs '0001') and refs in unrelated files are not ordered (warning
                           [cbeta-incomparable]).
  warning [announce-after-explain]
                           cbeta-kepan commentary.announced <= commentary.explained (the Tibetan format's convention:
                           first <= explained); a warning because the Chinese case is
                           not yet measured.
  [sibling-order]          among consecutive siblings (same parent_id) of one scheme (node.scheme_id, else
                           metadata.scheme_id; a parallel lens is its own group), a locator does not decrease in
                           document order (equal is allowed: same-line siblings, R06 F23). root_text.start: error
                           under zh-kepan; commentary.explained: error in self-outlining mode, where it is the
                           explained locator, warning in sūtra mode; base documents: cbeta-line start and the
                           acip-folio explained folio, warning.
                           docs/architecture.md §4 (siblings monotone) and §5 step 3 (root spans monotone).
  [child-outside-parent]   a node's root span (cbeta-kepan root_text, or cbeta-line start/end) lies inside its
                           parent's: parent.start <= child.start and child.end (else child.start) <= parent.end,
                           where comparable. Error under zh-kepan, warning otherwise.
  [cbeta-text-id]          (zh-kepan) a ref's file prefix is the text it is declared in, or another file of the same
                           metadata.work_files entry: root_text.text_id or metadata.root_text_id; commentary.text_id,
                           else metadata.commentary_id in sūtra mode or metadata.root_text_id in self-outlining mode.
                           In sūtra mode with commentary_id null (the stating work has no CBETA id to cite) a commentary
                           position needs its own text_id.
  [work-files]             (zh-kepan) a file id appears in one metadata.work_files entry only.
  [class-root-text] [sutra-span-unmapped]
                           (zh-kepan) node_class 'commentary-internal' has root_text null; in sūtra mode
                           (metadata.outline_mode 'sutra', whether or not commentary_id is set) a 'sutra-span' node
                           without a root span (root_text null, or location scheme 'none' / 'unparsed') carries flag
                           'unmapped'.
  warning [child-count]    (zh-kepan) child_count_announced equals the number of children present unless the node
                           carries flag 'count_mismatch'.
  warning [display-label-level]
                           (zh-kepan) a display_label that starts with a 干支 symbol uses the symbol of the node's
                           level (甲 = 1 … 癸 = 10, 子 = 11 … 亥 = 22; R07 F15).
  [unindexed-after]        unindexed_entries[*].after_node_id names an existing node.
  [key-whitespace]         (base documents) ids, path tokens, parent ids, after_node_id, folios and CBETA refs
                           contain no whitespace. The base schema's patterns end in '$', which Python's re.search
                           (used by jsonschema) also matches before a final newline, unlike ECMA-262, the regex
                           dialect JSON Schema specifies; the zh schema's own patterns end in (?![\\s\\S]) instead.
JSON Schema errors are reported as [schema] with the JSON path and the failing keyword; for the location oneOf the
branch selected by locations.scheme is reported instead of the generic "not valid under any of the given schemas".
Structural checks read only well-typed values and skip the rest, which the schema layer reports (the count checks
sibling-index, child-count and metadata depth/per-level are skipped when a node or its parent_id/level is ill-typed,
since the counts would be off by the node left out); if either layer still raises, the file gets an [internal] error
with the exception and the run goes on to the next file.

Provenance: the base rules restate context/baseline/outline-schema.json (modelled on the outline format of
Kurt Keutzer's Tibetan workflow); the zh rules implement context/baseline/outline-schema-zh.json (R07 F5/F6/F15, R06 F7/F23/F24,
R03 F22-F24, R04 F25-F34, R02 F6/F13/F18). Nothing here is a claim about CBETA beyond the ref grammar in that schema.

Dependencies: Python standard library + jsonschema (Draft 2020-12). Deterministic; reads only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATHS = {
    "base": REPO_ROOT / "context/baseline/outline-schema.json",
    "zh": REPO_ROOT / "context/baseline/outline-schema-zh.json",
}
ZH_PROFILE = "zh-kepan"

# Loose parser for CBETA line refs: accepts both the base pattern ([A-Z]+\d+n…_p\d{4}[a-c]\d{2}) and the zh pattern
# (all canons, letter-initial front-matter pages, registers a–h…, optional ':<offset>'). Grammar is enforced by the
# schemas; this only splits a ref into comparable parts. \Z, not $: '$' would also match before a final newline.
CBETA_REF_RE = re.compile(
    r"^(?P<text>[A-Z]+[0-9]+n[0-9A-Za-z]+)_p(?P<page>[0-9a-z][0-9]{3})(?P<reg>[a-z])(?P<line>[0-9]{2})"
    r"(?::(?P<off>[0-9]+))?\Z"
)
TOKEN_RE = re.compile(r"^(?P<value>.+)_(?P<level>[0-9]+)\Z")
FOLIO_RE = re.compile(r"^(?P<num>[0-9]+)(?P<side>[AB])\Z")  # acip-folio '12A' < '12B' < '13A'
WHITESPACE_RE = re.compile(r"\s")
GANZHI = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"  # 10 天干 + 12 地支 = level 1..22 (R07 F14/F15)


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    code: str
    where: str  # node id, JSON path, or "metadata"
    message: str

    def render(self) -> str:
        return f"  {self.severity:<7} [{self.code}] {self.where}: {self.message}"


@dataclass
class Report:
    path: str
    schema: str | None = None
    profile: str | None = None
    node_count: int | None = None
    max_depth: int | None = None
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    def codes(self, severity: str | None = None) -> set[str]:
        return {f.code for f in self.findings if severity is None or f.severity == severity}

    def passed(self, strict: bool = False) -> bool:
        return not self.errors and not (strict and self.warnings)


_SCHEMA_CACHE: dict[str, dict] = {}


def load_schema(name: str) -> dict:
    if name not in _SCHEMA_CACHE:
        with open(SCHEMA_PATHS[name], encoding="utf-8") as fh:
            _SCHEMA_CACHE[name] = json.load(fh)
    return _SCHEMA_CACHE[name]


def is_zh_profile(doc: object) -> bool:
    return isinstance(doc, dict) and isinstance(doc.get("metadata"), dict) and \
        doc["metadata"].get("outline_profile") == ZH_PROFILE


def choose_schema(doc: object, choice: str = "auto") -> str:
    if choice in ("base", "zh"):
        return choice
    return "zh" if is_zh_profile(doc) else "base"


# ---------------------------------------------------------------------------------------------------------------
# JSON Schema layer


def _json_path(parts) -> str:
    out = "$"
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else f".{p}"
    return out


def _short(value: object, limit: int = 60) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _leaf_errors(error: jsonschema.ValidationError) -> list[jsonschema.ValidationError]:
    """Replace an uninformative oneOf/anyOf error by the errors of the branch that was meant.

    For the location oneOf the meant branch is the one whose `scheme` const equals the instance's scheme; for any
    other combinator the branch whose errors reach deepest into the instance is taken (a null-or-object union fails
    shallowly on the null branch and deeply on the object branch)."""
    if error.validator not in ("oneOf", "anyOf"):
        return [error]
    if not error.context:  # several branches matched (e.g. a non-object passes every object-only branch)
        error.message = f"{_short(error.instance)} is valid under more than one {error.validator} branch"
        return [error]
    branches: dict[int, list] = defaultdict(list)
    for sub in error.context:
        branches[sub.schema_path[0]].append(sub)
    chosen = None
    inst = error.instance
    if isinstance(inst, dict) and "scheme" in inst and isinstance(error.validator_value, list):
        for i, branch in enumerate(error.validator_value):
            const = branch.get("properties", {}).get("scheme", {}).get("const") if isinstance(branch, dict) else None
            if const is not None and const == inst.get("scheme"):
                chosen = i
                break
        if chosen is None:
            known = [b.get("properties", {}).get("scheme", {}).get("const") for b in error.validator_value
                     if isinstance(b, dict)]
            error.message = f"unknown location scheme {inst.get('scheme')!r}; expected one of {known}"
            return [error]
        if chosen not in branches:  # the branch matched; the oneOf failed because another matched too
            return [error]
    if chosen is None:
        def depth(i):
            return max(len(e.path) for e in branches[i])
        chosen = max(sorted(branches), key=depth)
    out = []
    for sub in branches[chosen]:
        out.extend(_leaf_errors(sub))
    return out


def schema_findings(doc: object, schema_name: str) -> list[Finding]:
    validator = jsonschema.Draft202012Validator(load_schema(schema_name))
    out, seen = [], set()
    for err in sorted(validator.iter_errors(doc), key=lambda e: (list(map(str, e.path)), e.message)):
        for leaf in _leaf_errors(err):
            where = _json_path(leaf.absolute_path)
            message = f"{leaf.message} (keyword: {leaf.validator})"
            if (where, message) in seen:  # the zh 'then' branch re-applies base checks to the same value
                continue
            seen.add((where, message))
            out.append(Finding("error", "schema", where, message))
    return out


# ---------------------------------------------------------------------------------------------------------------
# structural layer


def parse_ref(ref: object):
    """-> (text, page_series, page_number, register, line, offset|None) or None if not a parsable ref."""
    if not isinstance(ref, str):
        return None
    m = CBETA_REF_RE.match(ref)
    if not m:
        return None
    page = m.group("page")
    series = "" if page[0].isdigit() else page[0]
    number = int(page) if series == "" else int(page[1:])
    off = m.group("off")
    return (m.group("text"), series, number, m.group("reg"), int(m.group("line")), None if off is None else int(off))


def compare_refs(a: str, b: str, file_rank: dict | None = None):
    """-1/0/1 comparing two refs; None when not comparable.

    Refs in one text file compare by page, register, line, and by character offset when both carry one on the same
    line; other page series in one file are not comparable. Refs in two files compare only when file_rank (from
    metadata.work_files, see _file_rank) puts both files in one work, by the files' positions in it."""
    pa, pb = parse_ref(a), parse_ref(b)
    if pa is None or pb is None:
        return None
    if pa[0] != pb[0]:
        ra, rb = (file_rank or {}).get(pa[0]), (file_rank or {}).get(pb[0])
        if ra is None or rb is None or ra[0] != rb[0]:
            return None
        return (ra[1] > rb[1]) - (ra[1] < rb[1])
    if pa[1] != pb[1]:
        return None
    ka, kb = (pa[2], pa[3], pa[4]), (pb[2], pb[3], pb[4])
    if ka == kb and pa[5] is not None and pb[5] is not None:
        ka, kb = ka + (pa[5],), kb + (pb[5],)
    return (ka > kb) - (ka < kb)


def compare_folios(a: object, b: object):
    """-1/0/1 comparing two acip folios ('12A' < '12B' < '13A'); None when either is not a folio."""
    ma = FOLIO_RE.match(a) if isinstance(a, str) else None
    mb = FOLIO_RE.match(b) if isinstance(b, str) else None
    if not ma or not mb:
        return None
    ka, kb = (int(ma.group("num")), ma.group("side")), (int(mb.group("num")), mb.group("side"))
    return (ka > kb) - (ka < kb)


def _file_rank(work_files: object) -> tuple[dict, list[Finding]]:
    """metadata.work_files -> {file id: (entry index, position in entry)}, plus a finding per file listed in two
    entries (the first listing wins). Ill-typed parts are skipped; the schema layer reports them."""
    rank: dict[str, tuple[int, int]] = {}
    out: list[Finding] = []
    for w, files in enumerate(work_files if isinstance(work_files, list) else []):
        for k, f in enumerate(files if isinstance(files, list) else []):
            if not isinstance(f, str):
                continue
            if f in rank and rank[f][0] != w:
                out.append(Finding("error", "work-files", "metadata",
                                   f"{f} is listed in work_files entries {rank[f][0]} and {w}"))
                continue
            rank.setdefault(f, (w, k))
    return rank, out


def _check_span(out, where, a, b, what, severity, code, file_rank=None):
    if a is None or b is None:
        return
    c = compare_refs(a, b, file_rank)
    if c is None:
        if parse_ref(a) and parse_ref(b):
            out.append(Finding("warning", "cbeta-incomparable", where, f"{what}: {a} and {b} cannot be ordered "
                                                                      "(different files or page series)"))
    elif c > 0:
        out.append(Finding(severity, code, where, f"{what}: {a} comes after {b}"))


def _root_span(n: dict):
    """(start, end) of a node's root-text span: cbeta-kepan root_text, or a cbeta-line location; None if it has none."""
    loc = n.get("locations") if isinstance(n.get("locations"), dict) else {}
    if loc.get("scheme") == "cbeta-kepan":
        rt = loc.get("root_text")
        return (rt.get("start"), rt.get("end")) if isinstance(rt, dict) else None
    if loc.get("scheme") == "cbeta-line":
        return (loc.get("start"), loc.get("end"))
    return None


def _explained(n: dict):
    """(kind, value) of the position where a node's own treatment begins in the stating text: cbeta-kepan
    commentary.explained or the acip-folio explained folio; None if it has none."""
    loc = n.get("locations") if isinstance(n.get("locations"), dict) else {}
    if loc.get("scheme") == "cbeta-kepan" and isinstance(loc.get("commentary"), dict):
        return "ref", loc["commentary"].get("explained")
    if loc.get("scheme") == "acip-folio":
        return "folio", loc.get("explained")
    return None


def structural_findings(doc: object, zh: bool) -> list[Finding]:
    out: list[Finding] = []
    if not isinstance(doc, dict):
        return out
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    raw_nodes = doc.get("nodes")
    if not isinstance(raw_nodes, list):
        return out
    nodes = [n for n in raw_nodes if isinstance(n, dict)]
    position = {id(n): k for k, n in enumerate(raw_nodes)}

    def nid(n):
        return n.get("id") if isinstance(n.get("id"), str) else f"$.nodes[{position[id(n)]}]"

    def good_path(n):
        p = n.get("path")
        return p if isinstance(p, list) and p and all(isinstance(t, str) for t in p) else None

    # ids unique
    by_id: dict[str, dict] = {}
    for n in nodes:
        i = n.get("id")
        if not isinstance(i, str):
            continue
        if i in by_id:
            out.append(Finding("error", "duplicate-id", i, f"id used again at order {n.get('order')} "
                                                          f"(first at order {by_id[i].get('order')})"))
        else:
            by_id[i] = n

    # order
    prev = None
    for n in nodes:
        o, pos = n.get("order"), position[id(n)] + 1  # position in the raw array: a non-object node still counts
        if not isinstance(o, int):
            continue
        if prev is not None and o <= prev:
            out.append(Finding("error", "order-not-increasing", nid(n), f"order {o} after order {prev}"))
        elif o != pos:
            out.append(Finding("error", "order-position", nid(n), f"order {o} but node is at position {pos}"))
        prev = o

    # level / path / id
    for n in nodes:
        path, level = good_path(n), n.get("level")
        if path is None:
            continue
        if isinstance(level, int) and level != len(path):
            out.append(Finding("error", "level-path", nid(n), f"level {level} but len(path) = {len(path)}"))
        if isinstance(n.get("id"), str) and n["id"] != ".".join(path):
            out.append(Finding("error", "id-path", nid(n), f"id is not '.'.join(path) = {'.'.join(path)!r}"))
        for k, tok in enumerate(path, 1):
            m = TOKEN_RE.match(tok)
            if m and int(m.group("level")) != k:
                out.append(Finding("error", "path-token-level", nid(n),
                                   f"path token {k} is {tok!r}; its level suffix should be _{k}"))

    # parents
    for n in nodes:
        path, pid = good_path(n), n.get("parent_id")
        if path is None:
            continue
        structural = ".".join(path[:-1]) if len(path) > 1 else None
        present_ancestors = [".".join(path[:k]) for k in range(len(path) - 1, 0, -1) if ".".join(path[:k]) in by_id]
        if pid is None:
            if structural is None:
                continue
            if present_ancestors:
                out.append(Finding("error", "parent-null", nid(n),
                                   f"parent_id is null but ancestor {present_ancestors[0]} is present"))
            else:
                out.append(Finding("error" if zh else "warning", "parent-missing", nid(n),
                                   "level > 1 and no ancestor is present in the document"))
            continue
        if not isinstance(pid, str):
            continue  # a type error, reported by the schema layer
        if pid not in by_id:
            out.append(Finding("error", "parent-unresolved", nid(n), f"parent_id {pid!r} names no node"))
            continue
        parent = by_id[pid]
        if isinstance(parent.get("order"), int) and isinstance(n.get("order"), int) and parent["order"] >= n["order"]:
            out.append(Finding("error", "parent-after-child", nid(n), f"parent {pid} does not precede the node"))
        ppath = good_path(parent)
        if ppath is None:
            continue  # the parent's path is ill-typed, a schema error; nothing to compare against
        if len(ppath) >= len(path) or path[:len(ppath)] != ppath:
            out.append(Finding("error", "parent-not-ancestor", nid(n), f"parent {pid}'s path is not a proper prefix "
                                                                      "of the node's path"))
            continue
        if pid == structural:
            if isinstance(parent.get("level"), int) and isinstance(n.get("level"), int) \
                    and parent["level"] != n["level"] - 1:
                out.append(Finding("error", "level-parent", nid(n),
                                   f"level {n['level']} but parent {pid} has level {parent['level']}"))
        elif structural in by_id:
            out.append(Finding("error", "parent-not-structural", nid(n),
                               f"structural parent {structural} is present but parent_id is {pid}"))
        elif zh:
            out.append(Finding("error", "parent-not-structural", nid(n),
                               f"structural parent {structural} absent (zh-kepan ids are generated, so it must exist)"))
        elif present_ancestors and pid != present_ancestors[0]:
            out.append(Finding("error", "parent-not-nearest", nid(n),
                               f"parent_id {pid} is not the nearest present ancestor {present_ancestors[0]}"))
        else:
            out.append(Finding("warning", "parent-nearest-ancestor", nid(n),
                               f"structural parent {structural} absent; parent_id is the nearest present ancestor"
                               + ("" if n.get("notes") else " (and the node has no note saying so)")))

    # pre-order: the parent of node i+1 is node i or one of node i's ancestors (via parent_id links)
    chain: dict[str, set] = {}
    prev_id = None
    for n in nodes:
        i, pid = n.get("id"), n.get("parent_id")
        if not isinstance(i, str) or by_id.get(i) is not n or not (pid is None or isinstance(pid, str)):
            prev_id = None  # ill-typed id or parent_id (a schema error): the chain restarts at the next node
            continue
        pid = pid if pid in by_id else None
        if pid is not None and prev_id is not None and pid not in chain.get(prev_id, set()):
            out.append(Finding("error", "not-preorder", i, f"parent {pid} is neither the previous node {prev_id} "
                                                          "nor one of its ancestors"))
        chain[i] = (chain.get(pid, set()) if pid is not None else set()) | {i}
        prev_id = i

    # sibling_index
    children: dict[object, list] = defaultdict(list)  # parent_id (str or None) -> child nodes in document order
    for n in nodes:
        pid = n.get("parent_id")
        if pid is None or isinstance(pid, str):
            children[pid].append(n)
    # sibling counts need every node placed under its parent; a non-object node or an ill-typed parent_id (schema
    # errors) would shift them, so the count checks (sibling_index here, child-count below) are then skipped
    tree_known = len(nodes) == len(raw_nodes) and all(n.get("parent_id") is None or isinstance(n.get("parent_id"), str)
                                                       for n in nodes)
    if tree_known and (zh or any("sibling_index" in n for n in nodes)):
        for pid, kids in children.items():
            for k, n in enumerate(kids, 1):
                si = n.get("sibling_index")
                if not isinstance(si, int):
                    continue
                if si != k:
                    out.append(Finding("error", "sibling-index", nid(n),
                                       f"sibling_index {si}, but the node is child {k} of "
                                       f"{pid if pid is not None else 'the document root'} in document order"))
                path = good_path(n)
                if zh and path:
                    m = TOKEN_RE.match(path[-1])
                    if m and m.group("value") != str(si):
                        out.append(Finding("error", "id-sibling-index", nid(n),
                                           f"last id token {path[-1]!r} does not carry sibling_index {si}"))

    # metadata counts
    levels = [n["level"] for n in nodes if isinstance(n.get("level"), int)]
    levels_known = len(levels) == len(raw_nodes)  # else a node or its level is ill-typed (schema error): skip
    if isinstance(meta.get("node_count"), int) and meta["node_count"] != len(raw_nodes):
        out.append(Finding("error", "metadata-count", "metadata",
                           f"node_count {meta['node_count']} but {len(raw_nodes)} nodes"))
    if levels_known and isinstance(meta.get("max_depth"), int) and meta["max_depth"] != max(levels, default=0):
        out.append(Finding("error", "metadata-depth", "metadata",
                           f"max_depth {meta['max_depth']} but deepest node has level {max(levels, default=0)}"))
    if levels_known and isinstance(meta.get("nodes_per_level"), dict):
        expected = {str(lv): c for lv, c in sorted(Counter(levels).items())}
        given = {k: v for k, v in meta["nodes_per_level"].items() if v != 0}
        if given != expected:
            out.append(Finding("error", "metadata-per-level", "metadata",
                               f"nodes_per_level {given} but the nodes give {expected}"))

    # locations
    # outline_mode decides the sūtra-mode rules, not commentary_id: commentary_id is null both for a self-outlining
    # text and for a sūtra-mode outline whose stating work has no CBETA id (YBh T1605 <- 韓清淨's 科文, R04 F3).
    # A missing or unknown mode is a schema error; the mode-specific rules are then skipped.
    mode = meta.get("outline_mode") if zh else None
    sutra_mode, self_mode = mode == "sutra", mode == "self-outlining"
    commentary_id, root_text_id = meta.get("commentary_id"), meta.get("root_text_id")
    file_rank, work_findings = _file_rank(meta.get("work_files"))
    if zh:
        out.extend(work_findings)

    def same_work(text_id: str) -> set:
        """The files a ref declared in text_id may lie in: text_id's metadata.work_files entry, or text_id alone."""
        if text_id in file_rank:
            entry = file_rank[text_id][0]
            return {f for f, (e, _) in file_rank.items() if e == entry}
        return {text_id}

    if self_mode:
        commentary_default = root_text_id  # the outlined text states its own outline
    elif sutra_mode:
        commentary_default = commentary_id  # may be null: stating work outside CBETA
    else:
        commentary_default = commentary_id or root_text_id
    for n in nodes:
        if not isinstance(n.get("locations"), dict):
            continue  # missing or ill-typed locations: a schema error, and no scheme to read the rules from
        loc = n["locations"]
        scheme, where = loc.get("scheme"), nid(n)
        flags = n.get("flags")
        if scheme == "cbeta-line":
            _check_span(out, where, loc.get("start"), loc.get("end"), "cbeta-line span", "error", "cbeta-order",
                        file_rank)
        unflagged = isinstance(flags, list) and "unmapped" not in flags  # ill-typed flags: schema error, skip
        if sutra_mode and n.get("node_class") == "sutra-span" and unflagged:
            if scheme != "cbeta-kepan":
                out.append(Finding("error", "sutra-span-unmapped", where,
                                   f"sūtra-mode sutra-span node with location scheme {scheme!r} (no root span) must "
                                   "carry flag 'unmapped'"))
            elif loc.get("root_text") is None:
                out.append(Finding("error", "sutra-span-unmapped", where,
                                   "sūtra-mode sutra-span node without root_text must carry flag 'unmapped'"))
        if scheme != "cbeta-kepan":
            continue
        com = loc.get("commentary") if isinstance(loc.get("commentary"), dict) else None
        root = loc.get("root_text") if isinstance(loc.get("root_text"), dict) else None
        if root:
            _check_span(out, where, root.get("start"), root.get("end"), "root_text span", "error", "cbeta-order",
                        file_rank)
        if com:
            _check_span(out, where, com.get("announced"), com.get("explained"), "commentary announced/explained",
                        "warning", "announce-after-explain", file_rank)
        if not zh:
            continue
        for label, obj, keys, declared in (
            ("root_text", root, ("start", "end"), (root or {}).get("text_id") or root_text_id),
            ("commentary", com, ("announced", "explained"), (com or {}).get("text_id") or commentary_default),
        ):
            if not obj:
                continue
            if declared is None and label == "commentary" and sutra_mode:
                for key in keys:
                    if parse_ref(obj.get(key)):
                        out.append(Finding("error", "cbeta-text-id", where,
                                           f"{label}.{key} {obj.get(key)}: metadata.commentary_id is null (stating "
                                           "work without a CBETA id), so a commentary position needs its own text_id"))
                continue
            if not isinstance(declared, str):
                continue
            allowed = same_work(declared)
            for key in keys:
                parsed = parse_ref(obj.get(key))
                if parsed and parsed[0] not in allowed:
                    also = f" or the other files of its work {sorted(allowed - {declared})}" if len(allowed) > 1 else ""
                    out.append(Finding("error", "cbeta-text-id", where,
                                       f"{label}.{key} {obj.get(key)} is not in {declared}{also}"))
        if n.get("node_class") == "commentary-internal" and loc.get("root_text") is not None:
            out.append(Finding("error", "class-root-text", where, "commentary-internal node has a root_text span"))

    # span order across nodes (docs/architecture.md §4: siblings monotone; §5 step 3: root spans monotone)
    def ref_or_none(v):
        return v if parse_ref(v) else None

    def cmp_refs(a, b):
        return compare_refs(a, b, file_rank)

    def root_start(n):
        span = _root_span(n)
        return ref_or_none(span[0]) if span else None

    def explained_ref(n):
        e = _explained(n)
        return ref_or_none(e[1]) if e and e[0] == "ref" else None

    def explained_folio(n):
        e = _explained(n)
        return e[1] if e and e[0] == "folio" and isinstance(e[1], str) and FOLIO_RE.match(e[1]) else None

    locators = (  # (what, getter, comparison, severity)
        ("root_text.start" if zh else "start", root_start, cmp_refs, "error" if zh else "warning"),
        ("commentary.explained", explained_ref, cmp_refs, "error" if self_mode else "warning"),
        ("explained folio", explained_folio, compare_folios, "warning"),
    )
    main_scheme = meta.get("scheme_id")
    sibling_groups: dict[tuple, list] = defaultdict(list)
    for pid, kids in children.items():
        for n in kids:
            s = n.get("scheme_id")
            sibling_groups[(pid, s if isinstance(s, str) and s != main_scheme else None)].append(n)
    for kids in sibling_groups.values():
        for what, get, cmp, severity in locators:
            last = None  # (node, value) of the nearest elder sibling that has this locator
            for n in kids:
                v = get(n)
                if v is None:
                    continue
                if last is not None and (cmp(last[1], v) or 0) > 0:
                    out.append(Finding(severity, "sibling-order", nid(n),
                                       f"{what} {v} comes before {what} {last[1]} of its elder sibling "
                                       f"{nid(last[0])}"))
                last = (n, v)
    for n in nodes:
        pid = n.get("parent_id")
        if not isinstance(pid, str) or pid not in by_id:
            continue
        child, parent = _root_span(n), _root_span(by_id[pid])
        if not child or not parent:
            continue
        c_start, p_start, p_end = ref_or_none(child[0]), ref_or_none(parent[0]), ref_or_none(parent[1])
        c_end = ref_or_none(child[1]) or c_start
        severity = "error" if zh else "warning"
        if c_start and p_start and (cmp_refs(p_start, c_start) or 0) > 0:
            out.append(Finding(severity, "child-outside-parent", nid(n),
                               f"root span starts at {c_start}, before its parent {pid} starts ({p_start})"))
        if c_end and p_end and (cmp_refs(c_end, p_end) or 0) > 0:
            out.append(Finding(severity, "child-outside-parent", nid(n),
                               f"root span reaches {c_end}, after its parent {pid} ends ({p_end})"))

    if zh:
        for n in nodes:
            flags = n.get("flags") if isinstance(n.get("flags"), list) else []
            cc = n.get("child_count_announced")
            if tree_known and isinstance(cc, int) and isinstance(n.get("id"), str) and "count_mismatch" not in flags:
                present = len(children.get(n["id"], []))
                if present != cc:
                    out.append(Finding("warning", "child-count", nid(n), f"child_count_announced {cc} but {present} "
                                                                         "children present (flag count_mismatch "
                                                                         "if intended)"))
            dl, level = n.get("display_label"), n.get("level")
            if isinstance(dl, str) and dl and dl[0] in GANZHI and isinstance(level, int) \
                    and GANZHI.index(dl[0]) + 1 != level:
                out.append(Finding("warning", "display-label-level", nid(n),
                                   f"display_label {dl!r} starts with the level-{GANZHI.index(dl[0]) + 1} symbol "
                                   f"but the node is at level {level}"))

    # unindexed entries
    entries = doc.get("unindexed_entries")
    entries = [e if isinstance(e, dict) else {} for e in entries] if isinstance(entries, list) else []
    for k, e in enumerate(entries):
        after = e.get("after_node_id")
        if isinstance(after, str) and after not in by_id:
            out.append(Finding("error", "unindexed-after", f"$.unindexed_entries[{k}]",
                               f"after_node_id {after!r} names no node"))

    # whitespace in keys and refs of base documents (the zh schema's patterns already exclude it, see the docstring)
    if not zh:
        for n in nodes:
            loc = n.get("locations") if isinstance(n.get("locations"), dict) else {}
            values = [("id", n.get("id")), ("parent_id", n.get("parent_id")),
                      ("folio_first", n.get("folio_first")), ("folio_explained", n.get("folio_explained"))]
            values += [(f"path[{k}]", t) for k, t in enumerate(good_path(n) or [])]
            values += [(f"locations.{key}", loc.get(key)) for key in ("text_id", "start", "end", "first", "explained")]
            for sub in ("commentary", "root_text"):
                obj = loc.get(sub) if isinstance(loc.get(sub), dict) else {}
                values += [(f"locations.{sub}.{key}", v) for key, v in obj.items() if key != "raw"]
            for label, v in values:
                if isinstance(v, str) and WHITESPACE_RE.search(v):
                    out.append(Finding("error", "key-whitespace", nid(n), f"{label} {v!r} contains whitespace"))
        for k, e in enumerate(entries):
            after = e.get("after_node_id")
            if isinstance(after, str) and WHITESPACE_RE.search(after):
                out.append(Finding("error", "key-whitespace", f"$.unindexed_entries[{k}]",
                                   f"after_node_id {after!r} contains whitespace"))
    return out


# ---------------------------------------------------------------------------------------------------------------


def validate_document(doc: object, schema_choice: str = "auto", path: str = "<document>") -> Report:
    name = choose_schema(doc, schema_choice)
    zh = is_zh_profile(doc)
    rep = Report(path=path, schema=name, profile=ZH_PROFILE if zh else None)
    if isinstance(doc, dict) and isinstance(doc.get("nodes"), list):
        rep.node_count = len(doc["nodes"])
        levels = [n.get("level") for n in doc["nodes"] if isinstance(n, dict) and isinstance(n.get("level"), int)]
        rep.max_depth = max(levels, default=0)
    layers = (("schema", lambda: schema_findings(doc, name)), ("structural", lambda: structural_findings(doc, zh)))
    for layer, run in layers:
        try:
            rep.findings.extend(run())
        except Exception as exc:  # a validator bug on odd input must not abort a multi-file run
            rep.findings.append(Finding("error", "internal", "$", f"{layer} layer raised {type(exc).__name__}: {exc} "
                                                                 "(a validator bug; please report the input)"))
    return rep


def validate_file(path: Path, schema_choice: str = "auto") -> Report:
    shown = _display_path(path)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        rep = Report(path=shown)
        rep.findings.append(Finding("error", "json", shown, f"cannot read JSON: {exc}"))
        return rep
    return validate_document(doc, schema_choice, shown)


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="outline JSON file(s)")
    ap.add_argument("--schema", choices=("auto", "base", "zh"), default="auto",
                    help="auto (default): zh when metadata.outline_profile == 'zh-kepan', else base")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--quiet", action="store_true", help="print summary lines only")
    ap.add_argument("--max-messages", type=int, default=25, help="messages printed per file (0 = all)")
    args = ap.parse_args(argv)

    failed = 0
    for path in args.files:
        rep = validate_file(path, args.schema)
        ok = rep.passed(args.strict)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {rep.path}  schema={rep.schema or '-'}  profile={rep.profile or '-'}  "
              f"nodes={rep.node_count if rep.node_count is not None else '-'}  "
              f"max_depth={rep.max_depth if rep.max_depth is not None else '-'}  "
              f"errors={len(rep.errors)}  warnings={len(rep.warnings)}")
        if args.quiet:
            continue
        shown = rep.errors + rep.warnings
        limit = len(shown) if args.max_messages <= 0 else args.max_messages
        for f in shown[:limit]:
            print(f.render())
        if len(shown) > limit:
            print(f"  … {len(shown) - limit} more (use --max-messages 0)")
    total = len(args.files)
    print(f"validated {total} file(s): {total - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
