"""chinese_workflow.outline.resolver — the model-assisted part of the outliner
(docs/outliner-design.md §5.6; plan M6): inferred root spans, inferred children, adjudicated
parser-report entries.

Input : resolve(doc, *, root, commentary, config, tasks, parser_report, scheme_id,
                subdivide_min_chars, exemplar_pool)
          doc         a zh-kepan outline document that validates (outline.json after merge and
                      anchor)
          root        InputText of the root text (sūtra mode); None in self-outlining mode
          commentary  InputText of the commentary (sūtra mode), or of the outlined text itself in
                      self-outlining mode (as outline/pipeline.py passes it); None = model-only run
          config      llm.LLMConfig (adapter none | replay | claude | interactive)
          tasks       any of ("root-spans", "subdivide", "adjudicate"), always run in that order
          parser_report
                      tier 2's unresolved entries (default: doc metadata.parser_report)
          scheme_id   scheme of the inferred nodes (default: model-<first 8 hex of the prompt
                      sha256>)
          subdivide_min_chars
                      a leaf whose span is longer is offered for subdivision (every leaf with a
                      span in a model-only run)
          exemplar_pool
                      registry dataset ids of exemplar outlines; empty by default (plan
                      Appendix H 8b)
Output: (new doc, report). The new doc is renumbered (common.outline_doc.to_drafts +
        build_prediction, metadata kept) and validates; every explicit node is unchanged
        (assert_explicit_unchanged). The report: adapter, model, prompt files and sha256, scheme,
        the size budgets, and per task the requests and the longest user message, answered /
        no-model / pending counts, invalid responses, accepted items, rejected items with reasons,
        answers that changed nothing ('reported'), overrun ranges ('overruns'), the windows of
        too-long leaves, candidates the model did not answer or that were skipped, and the id map
        when ids moved.
Prompts: skills/chinese-kepan-outliner/references/resolver-prompt.md (the `## system` and
        `## task: …` sections), output-contract.md, level1-prior.md and formula-table.md when
        present, read at runtime (one prompt source for the skill and the headless run).

Requests are built per unit: per 品 (the outermost nodes whose part_type names 品; else the level-1
nodes; nodes above them form a 'top' unit) in sūtra mode, per window of at most WINDOW_CHARS
characters in self-outlining mode. Each carries the ancestor path, the unit's nodes as a numbered
list, the task's candidates, and the text lines the candidates need (`<linehead>\\t<text>`).
Sizes count characters as rendered. A unit's candidates share as few requests as the budgets allow:
a user message holds at most MAX_REQUEST_CHARS, a shared text block at most MAX_TEXT_CHARS, and an
outline listing longer than MAX_OUTLINE_CHARS keeps only the candidates' context. A candidate whose
own lines do not fit one request is skipped (root-spans, adjudicate) or, for a subdivide leaf, sent
in windows of WINDOW_CHARS text characters with context on either side, one request each.

Merge rules (each item separately; a rejected item is reported, never merged):
  root-spans  sutra-span nodes flagged 'unmapped' (sūtra mode) and not marked out-of-span by
              outline.classify (those are listed under `skipped` with kind 'out-of-span'):
              start/end root lineheads inside the admissible range (inside every ancestor's
              span, not before the elder sibling's end, not after the younger sibling's start,
              around the node's own descendants); root_text.basis 'inferred', flag 'unmapped'
              removed, a note names adapter, model, confidence, rationale.
  subdivide   sutra-span leaves with a span longer than subdivide_min_chars (all leaves with a span
              in a model-only run): divisions up to depth 3, each divided node with >= 2 children
              in order inside its span, not overlapping (one shared line allowed); origin
              'inferred', confidence < 1, evidence = rationale, scheme_id; in self-outlining mode
              the model's explained line (inside the child's span) or else the start. Uncovered
              ranges are gaps between the depth-1 divisions; 'overrun' ranges are reported, no span
              changes. The windows of a too-long leaf give depth-1 starts in their cores, joined
              into one division after every window is read (_stitch_windows).
  adjudicate  parser-report entries: 'ignore' is recorded; 'attach' adds inferred children under an
              existing target with a span, wholly before or after its existing children.
After every accepted item the tree is renumbered, assert_explicit_unchanged(input, new) and
common.outline_doc.validate must pass, else the item is rejected.
"""

from __future__ import annotations

import copy
import re
from bisect import bisect_right
from dataclasses import dataclass, field
from itertools import accumulate, pairwise

from ..common.jsonio import canonical, read_json, sha256_json, sha256_text
from ..common.lineheads import is_ref, strip_offset
from ..common.outline_doc import (
    assert_explicit_unchanged,
    build_prediction,
    children_map,
    to_drafts,
    validate,
)
from ..common.paths import REPO_ROOT, SCHEMAS, SKILLS
from ..common.splits import SplitGuard, SplitViolation
from ..llm import (
    InvalidResponse,
    LLMConfig,
    NoModel,
    PendingInteractive,
    Refusal,
    call,
    request_hash,
)
from .classify import OUT_OF_SPAN_PREFIX, is_out_of_span

TASKS = ("root-spans", "subdivide", "adjudicate")
SCHEMA_NAMES = {
    "root-spans": "resolver-root-spans",
    "subdivide": "resolver-subdivide",
    "adjudicate": "resolver-adjudicate",
}
REFERENCES = SKILLS / "chinese-kepan-outliner" / "references"
RESOLVER_PROMPT = "resolver-prompt.md"
RESOLVER_REFERENCES = ("output-contract.md", "level1-prior.md")
OPTIONAL_REFERENCES = ("formula-table.md",)
# Sizes are characters of the request as rendered (a text line is `<linehead>\t<text>\n`, about twice
# its text for CBETA lines), except WINDOW_CHARS, which counts the text's own characters. The request
# budget binds; a block may take most of it, so a unit's whole commentary still goes in one request
# when it fits (the Zhiyi dev 卷: 49,747 characters in a 71,544-character request).
WINDOW_CHARS = 4000  # self-outlining unit window, and the core of one window of a too-long leaf
MAX_TEXT_CHARS = 60000  # one text block of a request that several candidates share
MAX_OUTLINE_CHARS = 20000  # the unit's outline listing; a longer one keeps the candidates' context
MAX_REQUEST_CHARS = (
    100000  # one user message; a unit that needs more is split into several requests
)
GAP_LINE = "⋯"  # stands for lines (or outline nodes) a request leaves out
SECTION_RE = re.compile(r"^## (system|task: [a-z0-9-]+)[ \t]*$")
SCHEME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
COUNT_KEYS = ("node_count", "max_depth", "nodes_per_level")
REPORT_LINE_KEYS = ("linehead", "line", "announced", "explained", "first", "start", "at")


class _Reject(Exception):
    """An item that breaks a merge rule (the message is the reason)."""


# -------------------------------------------------------------------------------------- prompts


@dataclass
class Prompts:
    system: str
    tasks: dict  # task name -> task section text
    files: dict  # file name -> sha256 of its text
    # sha256 over files (name -> sha256): the prompt hash of the report and of model-<sha8>
    sha: str


def prompt_sections(text: str) -> dict:
    """{'system': …, 'task: root-spans': …} from a prompt template; text before the first section is
    the human header and is dropped."""
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = SECTION_RE.match(line)
        if m:
            if name is not None:
                out[name] = "\n".join(buf).strip()
            name, buf = m.group(1), []
        elif name is not None:
            buf.append(line)
    if name is not None:
        out[name] = "\n".join(buf).strip()
    return out


def load_prompts(main: str, references: tuple = (), optional: tuple = (), base=None) -> Prompts:
    """The system prompt (main's `## system` section, then each reference file in full) and the task
    sections of `main`, with the sha256 of every file used."""
    base = base or REFERENCES
    text = (base / main).read_text(encoding="utf-8")
    secs = prompt_sections(text)
    if "system" not in secs:
        raise ValueError("%s has no '## system' section" % main)
    files = {main: sha256_text(text)}
    parts = [secs["system"]]
    for name in tuple(references) + tuple(optional):
        path = base / name
        if not path.exists():
            if name in optional:
                continue
            raise FileNotFoundError(path)
        ref = path.read_text(encoding="utf-8")
        files[name] = sha256_text(ref)
        parts.append("# Reference: %s\n\n%s" % (name, ref.strip()))
    tasks = {k[len("task: ") :]: v for k, v in secs.items() if k.startswith("task: ")}
    return Prompts(
        system="\n\n".join(parts) + "\n", tasks=tasks, files=files, sha=sha256_json(files)
    )


def load_schema(name: str) -> dict:
    return read_json(SCHEMAS / ("%s.schema.json" % name))


def exemplar_block(pool, guard: SplitGuard | None = None) -> str:
    """Exemplar outlines for the system prompt, from registry datasets named one by one. Refused (by
    the split guard, before any file is read): eval-only and out-of-domain golds, and any gold of a
    split text (its nodes cover test / reserve spans). Empty pool -> ''."""
    if not pool:
        return ""
    guard = guard or SplitGuard()
    datasets = []
    for ds_id in pool:
        ds = guard.check_gold(ds_id, as_input=True)
        if ds.get("split_scope") or ds.get("split") in ("test", "reserve"):
            raise SplitViolation(
                "%s is scored on split spans and may not be exemplar material" % ds_id
            )
        datasets.append(ds)
    blocks = ["# Exemplar outlines (format only; not the text you are working on)"]
    for ds in datasets:
        path = REPO_ROOT / ds["path"]
        if path.suffix != ".json":
            raise ValueError("exemplar %s is not an outline document: %s" % (ds["id"], ds["path"]))
        nodes = read_json(path).get("nodes") or []
        lines = ["## %s" % ds["id"]]
        for n in nodes[:40]:
            lines.append(
                "%s%s 「%s」 %s"
                % (
                    "  " * (n.get("level", 1) - 1),
                    n.get("indicator_display") or n.get("id"),
                    n.get("heading_src", ""),
                    n.get("heading_en", ""),
                )
            )
        blocks.append("\n".join(lines))
    return "\n\n" + "\n\n".join(blocks) + "\n"


# ---------------------------------------------------------------------------- texts and positions


class _Lines:
    """The loaded lines of one InputText, in document order."""

    def __init__(self, text):
        self.text = text
        self.text_id = text.text_id
        self.lineheads = [rec["linehead"] for rec in text.lines]
        self.pos = {lh: i for i, lh in enumerate(self.lineheads)}
        self.lengths = [len(rec["text"]) for rec in text.lines]
        self.texts = [rec["text"] for rec in text.lines]
        self._chars = list(accumulate(self.lengths, initial=0))
        self._size = list(
            accumulate((len(h) + n + 2 for h, n in zip(self.lineheads, self.lengths)), initial=0)
        )

    def has(self, ref) -> bool:
        return isinstance(ref, str) and strip_offset(ref) in self.pos

    def i(self, ref) -> int:
        return self.pos[strip_offset(ref)]

    @property
    def last(self) -> int:
        return len(self.lineheads) - 1

    def chars(self, a: int, b: int) -> int:
        """Text characters of lines a..b."""
        return self._chars[b + 1] - self._chars[a]

    def size(self, a: int, b: int) -> int:
        """Characters of lines a..b as rendered: `<linehead>\\t<text>` and a newline each."""
        return self._size[b + 1] - self._size[a]

    def head(self, a: int, b: int, budget: int) -> int:
        """The last line e (a - 1 when none) such that lines a..e render within budget, e <= b."""
        e = bisect_right(self._size, self._size[a] + budget) - 2
        return min(max(e, a - 1), b)

    def render(self, a: int, b: int) -> str:
        return "\n".join("%s\t%s" % (self.lineheads[k], self.texts[k]) for k in range(a, b + 1))


@dataclass
class _Texts:
    mode: str  # 'sutra' | 'self-outlining'
    # S: the text sutra-span spans index (the root in sūtra mode, the text itself otherwise);
    # C: the text commentary positions index (the commentary, or the text itself)
    S: _Lines | None
    C: _Lines | None
    model_only: bool

    def describe(self) -> str:
        if self.mode != "sutra":
            return "self-outlining mode: the text %s outlines itself" % (self.C or self.S).text_id
        if self.model_only:
            return "sūtra mode, model-only: root text %s, no commentary" % self.S.text_id
        return "sūtra mode: root text %s, commentary %s" % (
            self.S.text_id if self.S else "(not given)",
            self.C.text_id if self.C else "(not given)",
        )


def _texts(doc: dict, root, commentary) -> _Texts:
    mode = doc["metadata"].get("outline_mode") or "sutra"
    if mode == "sutra":
        return _Texts(
            mode,
            _Lines(root) if root is not None else None,
            _Lines(commentary) if commentary is not None else None,
            model_only=commentary is None,
        )
    own = commentary if commentary is not None else root
    lines = _Lines(own) if own is not None else None
    return _Texts(mode, lines, lines, model_only=False)


def _comm(n) -> dict:
    return ((n.get("locations") or {}).get("commentary")) or {}


def _rt(n) -> dict:
    return ((n.get("locations") or {}).get("root_text")) or {}


class _View:
    """Positions of one numbered document's nodes in the texts."""

    def __init__(self, doc: dict, tx: _Texts):
        self.doc, self.tx = doc, tx
        self.nodes = doc["nodes"]
        self.by_id = {n["id"]: n for n in self.nodes}
        self.index = {n["id"]: k for k, n in enumerate(self.nodes)}
        self.kids = children_map(self.nodes)
        self.rows: dict = {}  # unit key -> its numbered outline listing

    def ancestors(self, n) -> list:
        out, p = [], n.get("parent_id")
        while p is not None:
            out.append(self.by_id[p])
            p = self.by_id[p].get("parent_id")
        return list(reversed(out))

    def subtree(self, n) -> list:
        k = self.index[n["id"]]
        out = [n]
        for m in self.nodes[k + 1 :]:
            if m["level"] <= n["level"]:
                break
            out.append(m)
        return out

    def explained(self, n) -> int | None:
        e = _comm(n).get("explained")
        return self.tx.C.i(e) if self.tx.C is not None and self.tx.C.has(e) else None

    def comm_span(self, n) -> tuple | None:
        """(first, last) commentary line of the node's treatment: its explained line up to the line
        before the next explained line after its subtree (that line itself when equal)."""
        start = self.explained(n)
        if start is None:
            return None
        k = self.index[n["id"]] + len(self.subtree(n))
        for m in self.nodes[k:]:
            nxt = self.explained(m)
            if nxt is not None and nxt >= start:
                return (start, max(start, nxt - 1))
        return (start, self.tx.C.last)

    def span(self, n) -> tuple | None:
        """(start, end) of the node's span in the text sutra-span nodes divide (end None if
        unknown)."""
        S = self.tx.S
        if S is None:
            return None
        rt = _rt(n)
        if S.has(rt.get("start")):
            s = S.i(rt["start"])
            e = S.i(rt["end"]) if S.has(rt.get("end")) else None
            return (s, e if e is None or e >= s else None)
        if self.tx.mode != "sutra":
            return self.comm_span(n)
        return None

    def full_span(self, n) -> tuple | None:
        sp = self.span(n)
        return sp if sp is not None and sp[1] is not None else None

    def admissible(self, n) -> tuple:
        """(lo, hi, cover) for a root span of n: inside every ancestor's span, not before the elder
        siblings' ends, not after the next younger sibling's start, around the descendants'
        spans."""
        S = self.tx.S
        lo, hi = 0, S.last
        for a in self.ancestors(n):
            sp = self.span(a)
            if sp is not None:
                lo = max(lo, sp[0])
                if sp[1] is not None:
                    hi = min(hi, sp[1])
        sibs = self.kids.get(n.get("parent_id"), [])
        k = next(i for i, s in enumerate(sibs) if s["id"] == n["id"])
        for s in sibs[:k]:
            sp = self.span(s)
            if sp is not None:
                lo = max(lo, sp[1] if sp[1] is not None else sp[0])
        for s in sibs[k + 1 :]:
            sp = self.span(s)
            if sp is not None:
                hi = min(hi, sp[0])
                break
        cover = None
        for d in self.subtree(n)[1:]:
            sp = self.span(d)
            if sp is not None:
                e = sp[1] if sp[1] is not None else sp[0]
                cover = (sp[0], e) if cover is None else (min(cover[0], sp[0]), max(cover[1], e))
        return lo, hi, cover


# ------------------------------------------------------------------------------------------ units


@dataclass
class _Unit:
    key: str
    root_id: str | None
    members: list  # node ids in document order


def _units(view: _View) -> list:
    """Request units: 品 subtrees (or level-1 subtrees) plus 'top' in sūtra mode; windows of at most
    WINDOW_CHARS characters of the text in self-outlining mode."""
    nodes = view.nodes
    if view.tx.mode != "sutra" and view.tx.C is not None:
        C = view.tx.C
        windows, start, size = [], 0, 0
        for k, n_chars in enumerate(C.lengths):
            if size and size + n_chars > WINDOW_CHARS:
                windows.append((start, k - 1))
                start, size = k, 0
            size += n_chars
        windows.append((start, C.last))
        members: dict = {}
        w = 0
        for n in nodes:
            pos = view.explained(n)
            if pos is None:
                sp = view.span(n)
                pos = sp[0] if sp else None
            if pos is not None:
                w = next(j for j, (a, b) in enumerate(windows) if a <= pos <= b)
            members.setdefault(w, []).append(n["id"])
        return [_Unit("w%d" % (j + 1), None, members[j]) for j in sorted(members)]
    pin = {n["id"] for n in nodes if "品" in (n.get("part_type") or "")}
    if pin:
        roots = [
            n
            for n in nodes
            if n["id"] in pin and not any(a["id"] in pin for a in view.ancestors(n))
        ]
    else:
        roots = [n for n in nodes if n["level"] == 1]
    units, taken = [], set()
    for r in roots:
        ids = [m["id"] for m in view.subtree(r)]
        taken.update(ids)
        units.append(_Unit(r["id"], r["id"], ids))
    rest = [n["id"] for n in nodes if n["id"] not in taken]
    if rest:
        units.append(_Unit("top", None, rest))
    return units


def _unit_comm_range(view: _View, unit: _Unit) -> tuple | None:
    """Commentary lines of a unit: from its first explained line to the line before the next
    explained line of a node outside the unit (in document order after the unit's last member)."""
    C = view.tx.C
    if C is None:
        return None
    pos = [p for p in (view.explained(view.by_id[i]) for i in unit.members) if p is not None]
    if not pos:
        return None
    lo, hi = min(pos), max(pos)
    last = max(view.index[i] for i in unit.members)
    member = set(unit.members)
    end = C.last
    for m in view.nodes[last + 1 :]:
        if m["id"] in member:
            continue
        p = view.explained(m)
        if p is not None and p > hi:
            end = p - 1
            break
    return (lo, max(hi, end))


def _union(ranges) -> tuple | None:
    ranges = [r for r in ranges if r is not None]
    if not ranges:
        return None
    return (min(r[0] for r in ranges), max(r[1] for r in ranges))


def _merge(ranges) -> list:
    """Sorted, disjoint ranges: overlapping or adjacent ranges are joined."""
    out: list = []
    for a, b in sorted(r for r in ranges if r is not None):
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _minus(ranges, cut) -> list:
    """The parts of `ranges` outside `cut`."""
    out = []
    for a, b in _merge(ranges):
        for c, d in _merge(cut):
            if d < a or c > b:
                continue
            if c > a:
                out.append((a, c - 1))
            a = d + 1
            if a > b:
                break
        if a <= b:
            out.append((a, b))
    return out


def _size(L: _Lines, ranges) -> int:
    return sum(L.size(a, b) for a, b in ranges)


def _heads(L: _Lines, ranges, budget: int) -> list:
    """The head of each range, all within `budget` rendered characters: a range shorter than an
    equal share is kept whole and leaves the rest of its share to the others."""
    ranges = sorted(_merge(ranges), key=lambda r: L.size(*r))
    out, room = [], budget
    while ranges:
        share = room // len(ranges)
        if L.size(*ranges[0]) <= share:
            r = ranges.pop(0)
            out.append(r)
            room -= L.size(*r)
            continue
        for a, b in ranges:
            e = L.head(a, b, share)
            if e >= a:
                out.append((a, e))
        break
    return _merge(out)


# ---------------------------------------------------------------------------------- rendering


def _fmt_node(view: _View, n: dict, base_level: int) -> str:
    bits = [
        "%s%s L%d %s"
        % ("  " * max(n["level"] - base_level, 0), n["id"], n["level"], n.get("origin"))
    ]
    if n.get("origin") == "inferred" and n.get("confidence") is not None:
        bits[0] += "(%.2f)" % n["confidence"]
    bits[0] += " %s 「%s」" % (n.get("node_class"), n.get("heading_src", ""))
    rt = _rt(n)
    if rt.get("start"):
        bits.append("root %s–%s (%s)" % (rt.get("start"), rt.get("end"), rt.get("basis")))
    elif view.tx.mode == "sutra" and n.get("node_class") == "sutra-span":
        bits.append("root: none")
    c = _comm(n)
    if c.get("announced") or c.get("explained"):
        bits.append("announced %s, explained %s" % (c.get("announced"), c.get("explained")))
    if n.get("flags"):
        bits.append("flags %s" % ",".join(n["flags"]))
    if n.get("child_count_announced"):
        bits.append("announced children %d" % n["child_count_announced"])
    if n.get("extent_announced"):
        bits.append("extent 「%s」" % n["extent_announced"])
    for label, raw in (("commentary wording", c.get("raw")), ("lemma", rt.get("raw"))):
        if raw:
            bits.append("%s 「%s」" % (label, raw))
    return " | ".join(bits)


def _outline_rows(view: _View, unit: _Unit) -> list:
    rows = view.rows.get(unit.key)
    if rows is None:
        base = min(view.by_id[i]["level"] for i in unit.members)
        rows = [
            "%d. %s" % (k, _fmt_node(view, view.by_id[i], base))
            for k, i in enumerate(unit.members, 1)
        ]
        view.rows[unit.key] = rows
    return rows


def _outline_context(view: _View, unit: _Unit, focus, siblings: bool) -> set:
    """The focus nodes with their ancestors in the unit, and either their subtrees and the siblings
    of each (siblings=True) or their children and their own neighbours (siblings=False)."""
    member, keep = set(unit.members), set()
    for f in focus:
        n = view.by_id.get(f)
        if n is None:
            continue
        chain = [a for a in view.ancestors(n) if a["id"] in member] + [n]
        keep.update(a["id"] for a in chain)
        below = view.subtree(n) if siblings else view.kids.get(n["id"], [])
        keep.update(m["id"] for m in below)
        for c in chain if siblings else [n]:
            sibs = [s["id"] for s in view.kids.get(c.get("parent_id"), [])]
            k = sibs.index(c["id"])
            keep.update(sibs if siblings else sibs[max(k - 1, 0) : k + 2])
    return keep & member


def _outline_block(view: _View, unit: _Unit, focus=()) -> str:
    """The unit's nodes, numbered; when that is longer than MAX_OUTLINE_CHARS, only the context of
    the focus nodes, each run of left-out nodes standing as one GAP_LINE row."""
    rows = _outline_rows(view, unit)
    text = "\n".join(rows)
    if len(text) <= MAX_OUTLINE_CHARS or not focus:
        return text
    for siblings in (True, False):
        keep = _outline_context(view, unit, focus, siblings)
        out, left = [], 0
        for row, i in zip(rows, unit.members):
            if i not in keep:
                left += 1
                continue
            if left:
                out.append("%s (%d nodes not shown)" % (GAP_LINE, left))
            out.append(row)
            left = 0
        if left:
            out.append("%s (%d nodes not shown)" % (GAP_LINE, left))
        text = "\n".join(out)
        if len(text) <= MAX_OUTLINE_CHARS:
            break
    return text


def _ancestor_line(view: _View, unit: _Unit) -> str:
    first = view.by_id[unit.members[0]]
    anc = [a for a in view.ancestors(first) if a["id"] not in set(unit.members)]
    if not anc:
        return "(top level)"
    return " > ".join("%s 「%s」" % (a["id"], a.get("heading_src", "")) for a in anc)


TEXTS = ("C", "S")  # the order of a request's text blocks: commentary, then root text


def _title(tx: _Texts, t: str) -> str:
    if tx.mode != "sutra":
        return "Text"
    return "Commentary" if t == "C" else "Root text"


def _block_head(title: str, L: _Lines, ranges: list) -> str:
    head = "## %s %s, lines %s" % (
        title,
        L.text_id,
        ", ".join("%s–%s" % (L.lineheads[a], L.lineheads[b]) for a, b in ranges),
    )
    if len(ranges) > 1:
        head += " (%s stands for lines not shown)" % GAP_LINE
    return head


def _text_block(title: str, L: _Lines | None, ranges) -> str:
    if L is None or not ranges:
        return ""
    body = ("\n%s\n" % GAP_LINE).join(L.render(a, b) for a, b in ranges)
    return "%s\n\n%s" % (_block_head(title, L, ranges), body)


def _block_len(title: str, L: _Lines | None, ranges) -> int:
    """What a text block adds to a user message, without rendering it."""
    if L is None or not ranges:
        return 0
    body = _size(L, ranges) - len(ranges) + (len(ranges) - 1) * (len(GAP_LINE) + 2)
    return len(_block_head(title, L, ranges)) + 2 + body + 2


def _user_message(
    prompts: Prompts,
    task: str,
    view: _View,
    unit: _Unit,
    focus: list,
    question_title: str,
    question_lines: list,
    blocks: dict,
) -> str:
    """blocks: 'C' | 'S' -> line ranges to show (self-outlining mode: 'S' only, the text itself)."""
    tx = view.tx
    parts = (
        [
            prompts.tasks[task],
            "",
            "# Unit %s" % unit.key,
            "",
            "Mode: %s." % tx.describe(),
            "Ancestor path: %s" % _ancestor_line(view, unit),
            "",
            "## Outline of this unit (explicit nodes are fixed)",
            "",
            _outline_block(view, unit, focus),
            "",
            "## %s" % question_title,
            "",
        ]
        + question_lines
        + [""]
    )
    texts = {"C": tx.C, "S": tx.S}
    for t in TEXTS:
        b = _text_block(_title(tx, t), texts[t], blocks.get(t))
        if b:
            parts.append(b + "\n")
    return "\n".join(parts).rstrip() + "\n"


# ------------------------------------------------------------------------------------ requests


@dataclass
class _Job:
    task: str
    unit: str
    request: dict
    candidates: dict  # candidate id -> info (node id, report entry, or a leaf's window)
    key: str = ""


def _request(
    system: str, task: str, unit: _Unit, text: str, candidates: list, extra: dict | None = None
) -> dict:
    return {
        "system": system,
        "messages": [{"role": "user", "content": text}],
        "schema_name": SCHEMA_NAMES[task],
        "meta": {"task": task, "unit": unit.key, "candidates": list(candidates), **(extra or {})},
    }


@dataclass
class _Item:
    """One candidate of a request: its line under the question title, the nodes whose context the
    outline listing keeps, and the text it needs ('C' commentary | 'S' the text spans index)."""

    id: str
    line: str
    focus: list
    need: dict  # text -> ranges shown whole
    want: dict  # text -> ranges shown as far as the budget allows (each range's head)
    info: object = None  # the job's candidate value
    whole: bool = False  # want ranges whole or not at all
    meta: dict | None = None  # request meta beyond task, unit and candidates


@dataclass
class _Ask:
    task: str
    title: str  # the heading the candidates are listed under
    wide: dict = field(default_factory=dict)  # text -> the unit's range, shown whole when it fits


def _compose(view: _View, unit: _Unit, prompts: Prompts, ask: _Ask, items: list) -> tuple:
    """(user message, fits) of one request carrying `items`. Every need range is shown whole. Per
    text, the rest is the first that fits of: the hull of the unit's wide range and the items'
    ranges, the hull of the items' ranges, those ranges apart; else the need ranges and the heads
    of the want ranges. A text block holds at most MAX_TEXT_CHARS (more only for the need ranges of
    a lone item), and fits means the message holds at most MAX_REQUEST_CHARS and, when items share
    it, no item's text was cut and every block is within MAX_TEXT_CHARS."""
    tx = view.tx
    texts = {"C": tx.C, "S": tx.S} if tx.mode == "sutra" else {"C": None, "S": tx.S}

    def where(t):  # in self-outlining mode the commentary positions index the text itself
        return t if tx.mode == "sutra" else "S"

    need, want, wide = {}, {}, {}
    for it in items:
        for t, rs in it.need.items():
            need.setdefault(where(t), []).extend(r for r in rs if r is not None)
        for t, rs in it.want.items():
            want.setdefault(where(t), []).extend(r for r in rs if r is not None)
    for t, r in ask.wide.items():
        if r is not None:
            wide.setdefault(where(t), []).append(r)
    focus = [f for it in items for f in it.focus]
    lines = [it.line for it in items]
    blocks = {t: _merge(rs) for t, rs in need.items() if texts[t] is not None}

    def message():
        return _user_message(prompts, ask.task, view, unit, focus, ask.title, lines, blocks)

    room = MAX_REQUEST_CHARS - len(message())
    cut = False
    for t in TEXTS:
        L, own = texts[t], blocks.get(t, [])
        w = _merge(want.get(t, []))
        if L is None or not (own or w or t in wide):
            continue
        title, base = _title(tx, t), _size(L, own)
        cost = _block_len(title, L, own)
        cap = max(MAX_TEXT_CHARS, base)
        options = [[_union(wide[t] + own + w)]] if t in wide else []
        if own or w:
            options += [[_union(own + w)], _merge(own + w)]
        chosen = next(
            (o for o in options if _size(L, o) <= cap and _block_len(title, L, o) - cost <= room),
            None,
        )
        if chosen is None:
            rest = _minus(w, own)
            chosen, cut = own, cut or bool(rest)
            allow = min(cap - base, room)
            while rest and not any(it.whole for it in items) and allow > 0:
                trial = _merge(own + _heads(L, rest, allow))
                over = _block_len(title, L, trial) - cost - room
                if over <= 0:
                    chosen = trial
                    break
                allow -= over
        room -= _block_len(title, L, chosen) - cost
        blocks[t] = chosen
    text = message()
    fits = len(text) <= MAX_REQUEST_CHARS
    if len(items) > 1:
        fits = fits and not cut
        fits = fits and all(_size(texts[t], rs) <= MAX_TEXT_CHARS for t, rs in blocks.items())
    return text, fits


def _jobs(view, unit, prompts, system, ask: _Ask, items: list, alone) -> list:
    """The items in document order, as few to a request as the budgets allow; an item that does not
    fit a request by itself goes to alone(item)."""
    groups, cur, cur_text = [], [], ""
    for it in items:
        if cur:
            text, fits = _compose(view, unit, prompts, ask, cur + [it])
            if fits:
                cur, cur_text = cur + [it], text
                continue
            groups.append((cur, cur_text))
        text, fits = _compose(view, unit, prompts, ask, [it])
        if fits:
            cur, cur_text = [it], text
        else:
            cur, cur_text = [], ""
            alone(it)
    if cur:
        groups.append((cur, cur_text))
    jobs = []
    for group, text in groups:
        extra: dict = {}
        for it in group:
            for k, v in (it.meta or {}).items():
                extra.setdefault(k, {}).update(v)
        ids = [it.id for it in group]
        jobs.append(
            _Job(
                ask.task,
                unit.key,
                _request(system, ask.task, unit, text, ids, extra),
                {it.id: it.info for it in group},
            )
        )
    return jobs


def _jobs_root_spans(
    view: _View, units: list, prompts: Prompts, system: str, skipped: list
) -> list:
    tx = view.tx
    if tx.mode != "sutra" or tx.S is None:
        return []
    jobs = []
    for unit in units:
        items = []
        for i in unit.members:
            n = view.by_id[i]
            if n.get("node_class") != "sutra-span" or "unmapped" not in (n.get("flags") or []):
                continue
            if is_out_of_span(n):  # classify: the announced extent lies beyond the unit's 品
                skipped.append(
                    {
                        "unit": unit.key,
                        "node_id": i,
                        "kind": "out-of-span",
                        "reason": next(x for x in n["notes"] if x.startswith(OUT_OF_SPAN_PREFIX)),
                    }
                )
                continue
            lo, hi, cover = view.admissible(n)
            if lo > hi:
                skipped.append({"unit": unit.key, "node_id": i, "reason": "empty admissible range"})
                continue
            c, rt = _comm(n), _rt(n)
            line = "- %s 「%s」: admissible root range %s–%s" % (
                i,
                n.get("heading_src", ""),
                tx.S.lineheads[lo],
                tx.S.lineheads[hi],
            )
            if cover:
                line += "; must cover %s–%s" % (
                    tx.S.lineheads[cover[0]],
                    tx.S.lineheads[cover[1]],
                )
            for label, v in (
                ("explained", c.get("explained")),
                ("commentary wording", c.get("raw")),
                ("lemma", rt.get("raw")),
                ("extent", n.get("extent_announced")),
            ):
                if v:
                    line += "; %s %s" % (label, v)
            items.append(_Item(i, line, [i], {"S": [(lo, hi)]}, {"C": [view.comm_span(n)]}, info=i))

        def alone(it, unit=unit):
            lo, hi = it.need["S"][0]
            skipped.append(
                {
                    "unit": unit.key,
                    "node_id": it.id,
                    "reason": "admissible range %s–%s (%d characters as rendered) does not fit "
                    "one request of %d characters"
                    % (
                        tx.S.lineheads[lo],
                        tx.S.lineheads[hi],
                        tx.S.size(lo, hi),
                        MAX_REQUEST_CHARS,
                    ),
                }
            )

        ask = _Ask("root-spans", "Nodes to resolve", {"C": _unit_comm_range(view, unit)})
        jobs += _jobs(view, unit, prompts, system, ask, items, alone)
    return jobs


def _windows(L: _Lines, span: tuple) -> list:
    """[(core, shown)] of a span too long for one request: cores of at most WINDOW_CHARS text
    characters (one line at least) in order, each shown with up to WINDOW_CHARS // 4 characters of
    the span on either side."""
    a, b = span
    cores, start, size = [], a, 0
    for k in range(a, b + 1):
        if size and size + L.lengths[k] > WINDOW_CHARS:
            cores.append((start, k - 1))
            start, size = k, 0
        size += L.lengths[k]
    cores.append((start, b))
    margin, out = WINDOW_CHARS // 4, []
    for c0, c1 in cores:
        s0, s1 = c0, c1
        while s0 > a and L.chars(s0 - 1, c0 - 1) <= margin:
            s0 -= 1
        while s1 < b and L.chars(c1 + 1, s1 + 1) <= margin:
            s1 += 1
        out.append(((c0, c1), (s0, s1)))
    return out


def _jobs_subdivide(
    view: _View, units: list, prompts: Prompts, system: str, min_chars: int, skipped: list
) -> list:
    tx = view.tx
    S = tx.S
    if S is None:
        return []
    jobs = []
    for unit in units:
        items = []
        for i in unit.members:
            n = view.by_id[i]
            if n.get("node_class") != "sutra-span" or view.kids.get(i):
                continue
            sp = view.full_span(n)
            if sp is None:
                continue
            size = S.chars(*sp)
            if not (tx.model_only or size > min_chars):
                continue
            line = "- %s 「%s」: span %s–%s (%d characters)" % (
                i,
                n.get("heading_src", ""),
                S.lineheads[sp[0]],
                S.lineheads[sp[1]],
                size,
            )
            want = {} if tx.model_only else {"C": [view.comm_span(n)]}
            items.append(_Item(i, line, [i], {"S": [sp]}, want, info=i))
        wide = {} if tx.model_only else {"C": _unit_comm_range(view, unit)}
        long_leaves: list = []
        jobs += _jobs(
            view,
            unit,
            prompts,
            system,
            _Ask("subdivide", "Leaves to subdivide", wide),
            items,
            long_leaves.append,
        )
        for it in long_leaves:  # too long for one request: one request per window of the leaf
            sp = it.need["S"][0]
            wins = _windows(S, sp)
            for k, (core, shown) in enumerate(wins, 1):
                pos = {
                    "window": k,
                    "of": len(wins),
                    "core": [S.lineheads[core[0]], S.lineheads[core[1]]],
                    "shown": [S.lineheads[shown[0]], S.lineheads[shown[1]]],
                }
                line = (
                    "%s; too long for one request: window %d of %d, core %s–%s (give the "
                    "divisions that begin here), lines %s–%s shown"
                    % (it.line, k, len(wins), *pos["core"], *pos["shown"])
                )
                win = _Item(
                    it.id,
                    line,
                    [it.id],
                    {"S": [shown]},
                    it.want,
                    info=dict(pos, core=core, shown=shown, leaf=sp),
                    whole=True,
                    meta={"windows": {it.id: pos}},
                )

                def lost(w, unit=unit):
                    skipped.append(
                        {
                            "unit": unit.key,
                            "node_id": w.id,
                            "window": w.info["window"],
                            "reason": "window does not fit one request of %d characters"
                            % MAX_REQUEST_CHARS,
                        }
                    )

                jobs += _jobs(
                    view,
                    unit,
                    prompts,
                    system,
                    _Ask("subdivide", "Leaves to subdivide"),
                    [win],
                    lost,
                )
    return jobs


def _report_entries(parser_report) -> list:
    """[(report_id, entry, linehead or None)] with ids 'pr<k>' where an entry has none."""
    out = []
    for k, e in enumerate(parser_report or [], 1):
        entry = e if isinstance(e, dict) else {"entry": e}
        rid = str(entry.get("id") or entry.get("report_id") or "pr%d" % k)
        line = None
        for key in REPORT_LINE_KEYS:
            v = entry.get(key)
            if is_ref(v):
                line = strip_offset(v)
                break
        out.append((rid, entry, line))
    return out


def _holder(view: _View, unit: _Unit, p: int) -> dict | None:
    """The deepest node of the unit whose commentary treatment contains commentary line p."""
    best = None
    for i in unit.members:
        n = view.by_id[i]
        sp = view.comm_span(n)
        if sp and sp[0] <= p <= sp[1] and (best is None or n["level"] >= best["level"]):
            best = n
    return best


def _jobs_adjudicate(
    view: _View, units: list, prompts: Prompts, system: str, parser_report, skipped: list
) -> list:
    tx = view.tx
    entries = _report_entries(parser_report)
    if not entries:
        return []
    if tx.C is None:
        skipped.extend({"report_id": rid, "reason": "no commentary text"} for rid, _, _ in entries)
        return []
    ranges = {u.key: _unit_comm_range(view, u) for u in units}
    placed: dict = {}
    for rid, entry, line in entries:
        target = None
        if line is not None and tx.C.has(line):
            p = tx.C.i(line)
            inside = [
                u for u in units if ranges[u.key] and ranges[u.key][0] <= p <= ranges[u.key][1]
            ]
            before = [u for u in units if ranges[u.key] and ranges[u.key][0] <= p]
            target = (inside or before[-1:] or units[:1] or [None])[0]
        if target is None:
            skipped.append({"report_id": rid, "reason": "entry has no line of the commentary"})
            continue
        placed.setdefault(target.key, []).append((rid, entry, line))
    jobs = []
    for unit in units:
        got = placed.get(unit.key)
        if not got:
            continue
        items = []
        for rid, entry, line in got:
            p = tx.C.i(line)
            holder = _holder(view, unit, p)
            want = {}
            if tx.S is not None and holder is not None:  # the likely targets: it or its children
                want["S"] = [view.full_span(holder)]
            items.append(
                _Item(
                    rid,
                    "- report_id %s (line %s): %s" % (rid, line, canonical(entry)),
                    [holder["id"] if holder else unit.members[0]],
                    {"C": [(max(p - 2, 0), min(p + 2, tx.C.last))]},
                    want,
                    info={"entry": entry, "line": line},
                )
            )
        wide = {"C": _unit_comm_range(view, unit)}
        if tx.S is not None:
            wide["S"] = _union([view.full_span(view.by_id[i]) for i in unit.members])

        def alone(it, unit=unit):
            skipped.append(
                {
                    "unit": unit.key,
                    "report_id": it.id,
                    "reason": "the entry does not fit one request of %d characters"
                    % MAX_REQUEST_CHARS,
                }
            )

        ask = _Ask("adjudicate", "Parser-report entries", wide)
        jobs += _jobs(view, unit, prompts, system, ask, items, alone)
    return jobs


# ---------------------------------------------------------------------------------------- merge


class _Merger:
    """The draft tree of one task, merged item by item; every accepted state is numbered, checked
    against the input's explicit nodes and validated."""

    def __init__(self, doc: dict, before: dict):
        self.meta = {k: v for k, v in doc["metadata"].items() if k not in COUNT_KEYS}
        self.before = before
        self.drafts = to_drafts(doc)
        self.doc = doc
        self.o2n = {n["id"]: n["id"] for n in doc["nodes"]}
        self.changed = False
        self.new = 0

    @staticmethod
    def find(drafts: list, orig_id: str) -> dict:
        stack = list(drafts)
        while stack:
            d = stack.pop()
            if d.get("_orig_id") == orig_id:
                return d
            stack.extend(d.get("children") or [])
        raise _Reject("node %s not found" % orig_id)

    def new_id(self) -> str:
        self.new += 1
        return "+%d" % self.new

    def apply(self, mutate) -> str | None:
        """Apply mutate(drafts) on a copy; keep it when the numbered result passes both checks.
        Returns None, or the reason for rejecting it."""
        trial = copy.deepcopy(self.drafts)
        try:
            mutate(trial)
        except _Reject as exc:
            return str(exc)
        doc, private = build_prediction(trial, **self.meta)
        try:
            assert_explicit_unchanged(self.before, doc)
        except AssertionError as exc:
            return str(exc)
        rep = validate(doc)
        if not rep.passed():
            return "validator: %s" % "; ".join(f.render() for f in rep.errors[:3])
        self.drafts, self.doc, self.changed = trial, doc, True
        self.o2n = {v["_orig_id"]: nid for nid, v in private.items() if v.get("_orig_id")}
        return None


def _check_meta(item: dict) -> None:
    conf = item.get("confidence")
    if not isinstance(conf, (int, float)) or not 0 <= conf < 1:
        raise _Reject("confidence must be in [0, 1), got %r" % conf)
    if not str(item.get("rationale") or "").strip():
        raise _Reject("empty rationale")


def _check_children(L: _Lines, children: list, lo: int, hi: int, what: str) -> list:
    """Line indexes [(s, e)] of children that lie in [lo, hi], in order, overlapping at most on one
    shared boundary line."""
    out, prev = [], None
    for k, ch in enumerate(children, 1):
        _check_meta(ch)
        s, e = ch.get("start"), ch.get("end")
        if not (L.has(s) and L.has(e)):
            raise _Reject("child %d: %s–%s are not lines of %s" % (k, s, e, L.text_id))
        si, ei = L.i(s), L.i(e)
        if si > ei:
            raise _Reject("child %d: start %s after end %s" % (k, s, e))
        if si < lo or ei > hi:
            raise _Reject(
                "child %d: %s–%s outside %s %s–%s"
                % (k, s, e, what, L.lineheads[lo], L.lineheads[hi])
            )
        if prev is not None and si < prev:
            raise _Reject(
                "child %d: starts at %s, before the previous child's end %s (children "
                "must be in text order without overlap)" % (k, s, L.lineheads[prev])
            )
        out.append((si, ei))
        prev = ei
    return out


def _check_tree(L: _Lines, children: list, lo: int, hi: int) -> list:
    """Subdivide children in outline order, each with a depth (1 = a child of the leaf, d + 1 = a
    child of the nearest division of depth d before it), as a tree [[child, (s, e), kids]]: every
    divided node has at least two children, in text order inside its span."""
    roots: list = []
    stack: list = []  # [(depth, entry)] of the open divisions
    for k, ch in enumerate(children, 1):
        d = ch.get("depth", 1)
        top = stack[-1][0] if stack else 0
        if not isinstance(d, int) or not 1 <= d <= top + 1:
            raise _Reject(
                "child %d: depth %r after depth %d (a division is one level below the division "
                "before it, or level with it or one of its ancestors)" % (k, d, top)
            )
        while stack and stack[-1][0] >= d:
            stack.pop()
        entry = [ch, None, []]
        (stack[-1][1][2] if stack else roots).append(entry)
        stack.append((d, entry))

    def check(group, lo, hi, what):
        if len(group) < 2:
            raise _Reject("a division needs at least two children (%s)" % what)
        for entry, pos in zip(group, _check_children(L, [e[0] for e in group], lo, hi, what)):
            entry[1] = pos
            if entry[2]:
                check(entry[2], *pos, "the span of 「%s」" % entry[0].get("heading_src", ""))

    if roots:
        check(roots, lo, hi, "the leaf's span")
    return roots


def _check_uncovered(
    L: _Lines, uncovered: list, tree: list, lo: int, hi: int, what: str = "the leaf's span"
) -> list:
    """[(s, e, item)] of the uncovered ranges: inside [lo, hi], and in text order with the top
    divisions without overlap (one shared boundary line allowed)."""
    out = []
    for k, u in enumerate(uncovered, 1):
        s, e = u.get("start"), u.get("end")
        if not (L.has(s) and L.has(e)):
            raise _Reject("uncovered %d: %s–%s are not lines of %s" % (k, s, e, L.text_id))
        si, ei = L.i(s), L.i(e)
        if si > ei:
            raise _Reject("uncovered %d: start %s after end %s" % (k, s, e))
        if si < lo or ei > hi:
            raise _Reject(
                "uncovered %d: %s–%s outside %s %s–%s"
                % (k, s, e, what, L.lineheads[lo], L.lineheads[hi])
            )
        if not str(u.get("rationale") or "").strip():
            raise _Reject("uncovered %d: empty rationale" % k)
        out.append((si, ei, u))
    segs = sorted(
        [(p[0], p[1], "the division 「%s」" % ch.get("heading_src", "")) for ch, p, _ in tree]
        + [(si, ei, "uncovered %d" % k) for k, (si, ei, _) in enumerate(out, 1)]
    )
    for (_, a1, an), (b0, _, bn) in pairwise(segs):
        if b0 < a1:
            raise _Reject(
                "%s overlaps %s (uncovered lines are the gaps between divisions)" % (bn, an)
            )
    return out


def _check_explained(tx: _Texts, tree: list, after: int | None = None, fill: bool = True) -> None:
    """Children's explained lines: in sūtra mode commentary lines; in self-outlining mode lines of
    the text inside the child's own span. Given lines run in outline order (pre-order) from `after`,
    the parent's: the outlined text places nodes by them, and one before an earlier node's cannot be
    placed. With fill, a self-outlining child without one gets its start, or the explained line
    before it in outline order when that is later and still inside its span."""
    L = tx.C if tx.mode == "sutra" else tx.S

    def walk(entries, prev):
        for ch, (si, ei), kids in entries:
            e, what, p = ch.get("explained"), "「%s」" % ch.get("heading_src", ""), None
            if e is not None and L is not None:
                if not L.has(e):
                    raise _Reject("%s: explained %s is not a line of %s" % (what, e, L.text_id))
                p = L.i(e)
                if tx.mode != "sutra" and not si <= p <= ei:
                    raise _Reject(
                        "%s: explained %s is outside its span %s–%s"
                        % (what, e, L.lineheads[si], L.lineheads[ei])
                    )
                if prev is not None and p < prev:
                    raise _Reject(
                        "%s: explained %s comes before %s, the explained line before it in "
                        "outline order" % (what, e, L.lineheads[prev])
                    )
            elif tx.mode != "sutra" and fill:
                p = si if prev is None else max(si, prev)
                if p > ei:
                    raise _Reject(
                        "%s: its span %s–%s ends before %s, the explained line before it in "
                        "outline order"
                        % (what, L.lineheads[si], L.lineheads[ei], L.lineheads[prev])
                    )
                ch["explained"] = L.lineheads[p]
            prev = p if p is not None else prev
            prev = walk(kids, prev)
        return prev

    walk(tree, after)


def _new_node(
    child: dict, parent: dict, tx: _Texts, *, scheme: str, note: str, announced: str | None = None
) -> dict:
    node_class = parent.get("node_class") or "sutra-span"
    start, end = strip_offset(child["start"]), strip_offset(child["end"])
    span = {"start": start, "end": end, "basis": "inferred", "end_basis": None, "raw": ""}
    if tx.mode == "sutra" and node_class == "sutra-span":
        expl = child.get("explained")
        expl = strip_offset(expl) if (tx.C is not None and tx.C.has(expl)) else None
        comm = {"announced": announced, "explained": expl} if (announced or expl) else None
        root_text = span
    elif tx.mode == "sutra":  # a commentary-internal target: the lines are commentary lines
        comm, root_text = {"announced": announced, "explained": start}, None
    else:  # self-outlining: the model's explained line (checked inside the span), else the start
        expl = child.get("explained")
        expl = strip_offset(expl) if (tx.C is not None and tx.C.has(expl)) else start
        comm = {"announced": announced, "explained": expl}
        root_text = span if node_class == "sutra-span" else None
    return {
        "heading_src": str(child.get("heading_src") or ""),
        "heading_en": "",
        "source_language": "lzh",
        "locations": {"scheme": "cbeta-kepan", "commentary": comm, "root_text": root_text},
        "origin": "inferred",
        "confidence": float(child["confidence"]),
        "evidence": str(child["rationale"]).strip(),
        "notes": [note],
        "node_class": node_class,
        "flags": [],
        "scheme_id": scheme,
        "children": [],
    }


@dataclass
class _TaskState:
    task: str
    tx: _Texts
    merger: _Merger
    config: LLMConfig
    scheme: str
    report: dict = field(default_factory=dict)

    returned_model: str | None = None
    # subdivide: leaf id -> {unit, of, parts: {window: (job, children, positions, uncovered)}}
    windows: dict = field(default_factory=dict)

    def note(self, key: str) -> str:
        out = "inferred by %s (%s adapter), resolver task %s, request %s" % (
            self.config.model,
            self.config.adapter,
            self.task,
            key[:12],
        )
        if self.returned_model and self.returned_model != self.config.model:
            out += ", answered by %s" % self.returned_model
        return out

    def view(self) -> _View:
        return _View(self.merger.doc, self.tx)

    def current(self, orig_id: str) -> dict:
        nid = self.merger.o2n.get(orig_id)
        if nid is None:
            raise _Reject("node %s is not in the outline" % orig_id)
        return self.view().by_id[nid]

    def accept(self, job: _Job, item_id: str, reason: str | None, detail: dict) -> bool:
        row = {"unit": job.unit, "request": job.key[:12], "id": item_id, **detail}
        if reason is None:
            self.report["accepted"].append(row)
            return True
        row["reason"] = reason
        self.report["rejected"].append(row)
        return False


def _merge_root_spans(st: _TaskState, job: _Job, response: dict) -> None:
    items = list(response.get("spans") or [])
    order = st.view().index
    items.sort(key=lambda it: order.get(st.merger.o2n.get(it.get("node_id"), ""), len(order)))
    done = set()
    for item in items:
        oid = str(item.get("node_id"))
        detail = {
            "start": item.get("start"),
            "end": item.get("end"),
            "confidence": item.get("confidence"),
        }
        try:
            if oid not in job.candidates:
                raise _Reject("not listed under 'Nodes to resolve'")
            if oid in done:
                raise _Reject("answered twice in one response")
            _check_meta(item)
            view, S = st.view(), st.tx.S
            n = st.current(oid)
            if "unmapped" not in (n.get("flags") or []):
                raise _Reject("no longer unmapped")
            s, e = item.get("start"), item.get("end")
            if not (S.has(s) and S.has(e)):
                raise _Reject("%s–%s are not lines of %s" % (s, e, S.text_id))
            si, ei = S.i(s), S.i(e)
            if si > ei:
                raise _Reject("start %s after end %s" % (s, e))
            lo, hi, cover = view.admissible(n)
            if si < lo or ei > hi:
                raise _Reject(
                    "span %s–%s outside the admissible range %s–%s (parent span, elder "
                    "sibling's end, younger sibling's start)"
                    % (s, e, S.lineheads[lo], S.lineheads[hi])
                )
            if cover and (si > cover[0] or ei < cover[1]):
                raise _Reject(
                    "span %s–%s does not cover the node's descendants %s–%s"
                    % (s, e, S.lineheads[cover[0]], S.lineheads[cover[1]])
                )
        except _Reject as exc:
            st.accept(job, oid, str(exc), detail)
            continue
        note = "root_text: %s; confidence %.2f; %s" % (
            st.note(job.key),
            float(item["confidence"]),
            str(item["rationale"]).strip(),
        )
        s, e = strip_offset(s), strip_offset(e)

        def mutate(drafts, oid=oid, s=s, e=e, note=note):
            d = _Merger.find(drafts, oid)
            loc = d.get("locations") or {}
            old = (loc.get("root_text") or {}) if loc.get("scheme") == "cbeta-kepan" else {}
            if loc.get("scheme") != "cbeta-kepan":
                loc = {
                    "scheme": "cbeta-kepan",
                    "commentary": None,
                    "root_text": None,
                    **({"raw": loc["raw"]} if loc.get("raw") else {}),
                }
            loc["root_text"] = {
                "start": s,
                "end": e,
                "basis": "inferred",
                "end_basis": None,
                "raw": old.get("raw") or "",
            }
            d["locations"] = loc
            d["flags"] = [f for f in d.get("flags") or [] if f != "unmapped"]
            d["notes"] = list(d.get("notes") or []) + [note]

        if st.accept(job, oid, st.merger.apply(mutate), detail):
            done.add(oid)


def _new_tree(tree: list, parent: dict, tx: _Texts, *, scheme: str, note: str) -> list:
    out = []
    for ch, _, kids in tree:
        node = _new_node(ch, parent, tx, scheme=scheme, note=note)
        node["children"] = _new_tree(kids, parent, tx, scheme=scheme, note=note)
        out.append(node)
    return out


def _with_ids(merger: _Merger, drafts: list) -> list:
    return [
        dict(d, _orig_id=merger.new_id(), children=_with_ids(merger, d["children"])) for d in drafts
    ]


def _apply_division(
    st: _TaskState, job: _Job, pid: str, children: list, uncovered: list, detail: dict
) -> bool:
    """Check and merge one division of leaf pid (children with depths, uncovered ranges); an answer
    with uncovered ranges and no children changes nothing and is listed under 'reported'. Overrun
    ranges are listed under 'overruns' (report only: an explicit node's span never changes)."""
    S = st.tx.S
    try:
        view = st.view()
        n = st.current(pid)
        if view.kids.get(n["id"]):
            raise _Reject("no longer a leaf")
        sp = view.full_span(n)
        if sp is None:
            raise _Reject("the leaf has no span")
        if len(children) == 1:
            raise _Reject("a division needs at least two children")
        tree = _check_tree(S, children, sp[0], sp[1])
        gaps = _check_uncovered(S, uncovered, tree, sp[0], sp[1])
        _check_explained(st.tx, tree, view.explained(n))
    except _Reject as exc:
        st.accept(job, pid, str(exc), detail)
        return False
    found = [
        {
            "unit": job.unit,
            "request": job.key[:12],
            "id": pid,
            "start": S.lineheads[si],
            "end": S.lineheads[ei],
            "kind": u["kind"],
            "rationale": str(u["rationale"]).strip(),
        }
        for si, ei, u in gaps
    ]
    overruns = [f for f in found if f["kind"] == "overrun"]
    detail = dict(detail, uncovered=[{k: f[k] for k in ("start", "end", "kind")} for f in found])
    if not tree:
        st.report["reported"].append(
            {"unit": job.unit, "request": job.key[:12], "id": pid, **detail}
        )
        st.report["overruns"].extend(overruns)
        return True
    new = _new_tree(tree, n, st.tx, scheme=st.scheme, note=st.note(job.key))

    def mutate(drafts, pid=pid, new=new):
        d = _Merger.find(drafts, pid)
        if d.get("children"):
            raise _Reject("no longer a leaf")
        d["children"] = _with_ids(st.merger, new)

    if st.accept(job, pid, st.merger.apply(mutate), detail):
        st.report["overruns"].extend(overruns)
        return True
    return False


def _merge_subdivide(st: _TaskState, job: _Job, response: dict) -> None:
    done = set()
    for item in response.get("divisions") or []:
        pid = str(item.get("parent_id"))
        children = list(item.get("children") or [])
        uncovered = list(item.get("uncovered") or [])
        detail = {"children": len(children)}
        if pid not in job.candidates:
            st.accept(job, pid, "not listed under 'Leaves to subdivide'", detail)
            continue
        if pid in done:
            st.accept(job, pid, "divided twice in one response", detail)
            continue
        info = job.candidates[pid]
        if isinstance(info, dict) and "window" in info:
            ok = _merge_window(st, job, pid, info, children, uncovered, detail)
        elif children or uncovered:
            ok = _apply_division(st, job, pid, children, uncovered, detail)
        else:  # the leaf reads as one unit
            st.report["reported"].append(
                {"unit": job.unit, "request": job.key[:12], "id": pid, **detail, "uncovered": []}
            )
            ok = True
        if ok:
            done.add(pid)


def _merge_window(
    st: _TaskState, job: _Job, pid: str, info: dict, children: list, uncovered: list, detail: dict
) -> bool:
    """Check one window's answer for a too-long leaf: depth-1 divisions and uncovered ranges that
    begin in the window's core, in order inside the lines shown. They are kept for _stitch_windows,
    which merges the leaf's division once every window has been read."""
    S = st.tx.S
    (c0, c1), (s0, s1), last = info["core"], info["shown"], info["leaf"][1]
    detail = dict(detail, window=info["window"])
    # an uncovered range that runs on past the lines shown ends at the last one shown
    uncovered = [
        dict(u, end=S.lineheads[s1]) if S.has(u.get("end")) and s1 < S.i(u["end"]) <= last else u
        for u in uncovered
    ]
    try:
        for k, ch in enumerate(children, 1):
            if ch.get("depth", 1) != 1:
                raise _Reject(
                    "child %d: depth %r: a window takes depth-1 divisions only" % (k, ch["depth"])
                )
        pos = _check_children(S, children, s0, s1, "the lines shown") if children else []
        tree = [[ch, p, []] for ch, p in zip(children, pos)]
        gaps = _check_uncovered(S, uncovered, tree, s0, s1, "the lines shown")
        _check_explained(st.tx, tree, fill=False)
    except _Reject as exc:
        st.accept(job, pid, str(exc), detail)
        return False
    # what begins outside the core belongs to a neighbouring window, which reports it
    kept = [(ch, p) for ch, p in zip(children, pos) if c0 <= p[0] <= c1]
    gaps_kept = [(si, ei, u, ei >= s1 and s1 < last) for si, ei, u in gaps if c0 <= si <= c1]
    parts = st.windows.setdefault(pid, {"unit": job.unit, "of": info["of"], "parts": {}})
    parts["parts"][info["window"]] = (job, kept, gaps_kept)
    st.report["windows"].append(
        {
            "unit": job.unit,
            "request": job.key[:12],
            "id": pid,
            "window": info["window"],
            "of": info["of"],
            "starts": len(kept),
            "uncovered": len(gaps_kept),
            "dropped": len(children) + len(gaps) - len(kept) - len(gaps_kept),
        }
    )
    return True


def _stitch_windows(st: _TaskState) -> None:
    """One division per windowed leaf from its windows' answers: each division runs from its start
    to the line before the next division or uncovered range begins (to that line itself when the
    model ended it there), the last one to the leaf's end; a window whose answer is missing or was
    rejected adds no boundary, so the division before it runs on."""
    S = st.tx.S
    for pid, w in st.windows.items():
        parts = [w["parts"][k] for k in sorted(w["parts"])]
        segs = []  # (start, end, is_child, item, runs_on)
        for _, kept, gaps in parts:
            segs += [(p[0], p[1], 1, ch, False) for ch, p in kept]
            segs += [(si, ei, 0, u, on) for si, ei, u, on in gaps]
        segs.sort(key=lambda s: (s[0], s[2]))
        try:
            sp = st.view().full_span(st.current(pid))
        except _Reject:
            sp = None
        end_of_leaf = sp[1] if sp else S.last
        children, uncovered = [], []
        for k, (si, ei, is_child, x, runs_on) in enumerate(segs):
            nxt = segs[k + 1][0] if k + 1 < len(segs) else None
            if is_child:
                end = end_of_leaf if nxt is None else (nxt if ei == nxt else max(si, nxt - 1))
                child = dict(x, start=S.lineheads[si], end=S.lineheads[end], depth=1)
                e = child.get("explained")
                if st.tx.mode != "sutra" and e is not None and S.i(e) > end:
                    child["explained"] = None  # past the division's joined end: its start stands
                children.append(child)
            else:
                if runs_on:
                    end = end_of_leaf if nxt is None else max(si, nxt - 1)
                else:
                    end = ei if nxt is None else max(si, min(ei, nxt - 1))
                uncovered.append(dict(x, start=S.lineheads[si], end=S.lineheads[end]))
        if len(children) == 1:  # one division: the leaf reads as one unit
            children = []
        detail = {"children": len(children), "windows": sorted(w["parts"]), "of": w["of"]}
        _apply_division(st, parts[0][0], pid, children, uncovered, detail)


def _merge_adjudicate(st: _TaskState, job: _Job, response: dict) -> None:
    done = set()
    for item in response.get("decisions") or []:
        rid = str(item.get("report_id"))
        decision = item.get("decision")
        children = list(item.get("children") or [])
        detail = {
            "decision": decision,
            "target_node_id": item.get("target_node_id"),
            "children": len(children),
            "confidence": item.get("confidence"),
        }
        try:
            if rid not in job.candidates:
                raise _Reject("not listed under 'Parser-report entries'")
            if rid in done:
                raise _Reject("decided twice in one response")
            _check_meta(item)
            if decision == "ignore":
                done.add(rid)
                st.report["ignored"].append(
                    {
                        "unit": job.unit,
                        "request": job.key[:12],
                        "id": rid,
                        "confidence": item["confidence"],
                        "rationale": str(item["rationale"]).strip(),
                    }
                )
                continue
            tid = item.get("target_node_id")
            if not tid:
                raise _Reject("attach without target_node_id")
            view = st.view()
            target = st.current(str(tid))
            if not children:
                raise _Reject("attach without children")
            tx = st.tx
            commentary_lines = tx.mode == "sutra" and target.get("node_class") != "sutra-span"
            L = tx.C if commentary_lines else tx.S
            rng = view.comm_span(target) if commentary_lines else view.full_span(target)
            if L is None or rng is None:
                raise _Reject("the target %s has no span to divide" % tid)
            pos = _check_children(L, children, rng[0], rng[1], "the target's span")
            existing = []
            for c in view.kids.get(target["id"], []):
                p = view.explained(c) if commentary_lines else (view.span(c) or (None,))[0]
                if p is None:
                    raise _Reject("cannot place the children among %s's existing children" % tid)
                sp = view.comm_span(c) if commentary_lines else view.span(c)
                existing.append((p, sp[1] if sp and sp[1] is not None else p))
            first, last = pos[0][0], pos[-1][1]
            if existing and all(e <= first for _, e in existing):
                where = "after"
            elif existing and all(p >= last for p, _ in existing):
                where = "before"
            elif existing:
                raise _Reject("the children would interleave with %s's existing children" % tid)
            else:
                where = "after"
            if not commentary_lines:
                tree = [[ch, p, []] for ch, p in zip(children, pos)]
                _check_explained(tx, tree, view.explained(target))
        except _Reject as exc:
            st.accept(job, rid, str(exc), detail)
            continue
        line = job.candidates[rid]["line"]
        announced = line if (line and st.tx.C is not None and st.tx.C.has(line)) else None
        note = st.note(job.key) + "; parser-report entry %s" % rid
        new = [
            _new_node(ch, target, st.tx, scheme=st.scheme, note=note, announced=announced)
            for ch in children
        ]

        def mutate(drafts, tid=str(tid), new=new, where=where):
            d = _Merger.find(drafts, tid)
            fresh = [dict(x, _orig_id=st.merger.new_id()) for x in new]
            old = list(d.get("children") or [])
            d["children"] = old + fresh if where == "after" else fresh + old

        if st.accept(job, rid, st.merger.apply(mutate), detail):
            done.add(rid)


MERGERS = {
    "root-spans": _merge_root_spans,
    "subdivide": _merge_subdivide,
    "adjudicate": _merge_adjudicate,
}


# ------------------------------------------------------------------------------------- resolve


def resolve(
    doc: dict,
    *,
    root=None,
    commentary=None,
    config: LLMConfig,
    tasks: tuple = TASKS,
    parser_report: list | None = None,
    scheme_id: str | None = None,
    subdivide_min_chars: int = 360,
    exemplar_pool: tuple = (),
) -> tuple[dict, dict]:
    """Run the resolver tasks over `doc`; see the module docstring. Raises PendingInteractive (with
    every request file of the task that is waiting) when the interactive adapter has unanswered
    requests, ReplayMiss on a cassette miss, BudgetExceeded when the claude adapter's cap is hit."""
    config = config if config is not None else LLMConfig()
    unknown = sorted(set(tasks) - set(TASKS))
    if unknown:
        raise ValueError("unknown resolver task(s): %s" % ", ".join(unknown))
    first = validate(doc)
    if not first.passed():
        raise ValueError(
            "the input outline does not validate: %s"
            % "; ".join(f.render() for f in first.errors[:3])
        )
    prompts = load_prompts(RESOLVER_PROMPT, RESOLVER_REFERENCES, OPTIONAL_REFERENCES)
    missing = [t for t in TASKS if t not in prompts.tasks]
    if missing:
        raise ValueError("%s lacks task sections: %s" % (RESOLVER_PROMPT, ", ".join(missing)))
    system = prompts.system + exemplar_block(tuple(exemplar_pool))
    scheme = scheme_id or "model-%s" % prompts.sha[:8]
    if not SCHEME_RE.match(scheme):
        raise ValueError("scheme_id %r does not match the zh-kepan scheme_id pattern" % scheme)
    tx = _texts(doc, root, commentary)
    if parser_report is None:
        parser_report = doc["metadata"].get("parser_report") or []

    report = {
        "adapter": config.adapter,
        "model": config.model,
        "mode": tx.describe(),
        "prompts": dict(prompts.files),
        "prompt_sha256": prompts.sha,
        "system_sha256": sha256_text(system),
        "exemplar_pool": list(exemplar_pool),
        "scheme_id": scheme,
        "subdivide_min_chars": subdivide_min_chars,
        "budget": {
            "max_request_chars": MAX_REQUEST_CHARS,
            "max_text_chars": MAX_TEXT_CHARS,
            "max_outline_chars": MAX_OUTLINE_CHARS,
            "window_chars": WINDOW_CHARS,
        },
        "tasks": {},
    }
    current = copy.deepcopy(doc)
    for task in TASKS:
        if task not in tasks:
            continue
        current, report["tasks"][task] = _run_task(
            task,
            current,
            doc,
            tx,
            prompts,
            system,
            config,
            scheme,
            parser_report,
            subdivide_min_chars,
        )
    counts = [t for t in report["tasks"].values()]
    asked = sum(t["requests"] for t in counts)
    answered = sum(t["answered"] for t in counts)
    no_model = sum(t["no_model"] for t in counts)
    if asked and no_model == asked:
        report["status"] = "skipped: no model"
    elif no_model:
        report["status"] = "partial: %d of %d requests had no model" % (no_model, asked)
    else:
        report["status"] = "ok" if asked else "nothing to ask"
    report["answered"] = answered
    return current, report


def _run_task(
    task, current, before, tx, prompts, system, config, scheme, parser_report, min_chars
) -> tuple[dict, dict]:
    view = _View(current, tx)
    units = _units(view)
    skipped: list = []
    if task == "root-spans":
        jobs = _jobs_root_spans(view, units, prompts, system, skipped)
    elif task == "subdivide":
        jobs = _jobs_subdivide(view, units, prompts, system, min_chars, skipped)
    else:
        jobs = _jobs_adjudicate(view, units, prompts, system, parser_report, skipped)
    schema = load_schema(SCHEMA_NAMES[task])
    name = "resolver/%s" % task
    trep = {
        "requests": len(jobs),
        "request_chars_max": max(
            (len(j.request["messages"][0]["content"]) for j in jobs), default=0
        ),
        "answered": 0,
        "no_model": 0,
        "pending": 0,
        "invalid": [],
        "accepted": [],
        "rejected": [],
        "ignored": [],
        "reported": [],
        "overruns": [],
        "windows": [],
        "not_answered": [],
        "skipped": skipped,
    }
    st = _TaskState(task, tx, _Merger(current, before), config, scheme, trep)
    pending: list = []
    for job in jobs:
        job.key = request_hash(name, job.request, schema, config.model)
        info: dict = {}
        try:
            response = call(name, job.request, schema, config, info=info)
        except NoModel:
            trep["no_model"] += 1
            continue
        except PendingInteractive as exc:
            trep["pending"] += 1
            pending.extend(exc.requests)
            continue
        except (InvalidResponse, Refusal) as exc:
            trep["invalid"].append({"unit": job.unit, "request": job.key[:12], "error": str(exc)})
            continue
        trep["answered"] += 1
        st.returned_model = info.get("returned_model")
        MERGERS[task](st, job, response)
        seen = {
            r["id"]
            for key in ("accepted", "rejected", "ignored", "reported", "windows")
            for r in trep[key]
            if r["request"] == job.key[:12]
        }
        for c, info in job.candidates.items():
            if c not in seen:
                row = {"unit": job.unit, "id": c}
                if isinstance(info, dict) and "window" in info:
                    row["window"] = info["window"]
                trep["not_answered"].append(row)
    if pending:
        exc = PendingInteractive(
            pending,
            "resolver task %s: %d request(s) await a response in %s"
            % (task, len(pending), config.llm_dir / "responses"),
        )
        exc.task_report = trep  # requests and skipped candidates, for the pipeline report while answers wait
        raise exc
    if st.windows:
        _stitch_windows(st)
    moved = {o: n for o, n in st.merger.o2n.items() if not o.startswith("+") and o != n}
    if moved:
        trep["renumbered"] = moved
    result = st.merger.doc if st.merger.changed else current
    return result, trep
