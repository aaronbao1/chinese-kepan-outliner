"""chinese_workflow.outline.tier1 — tier 1 of the explicit-structure parser: the chapter table
of contents from CBETA's cb:mulu markup (docs/outliner-design.md §5.1; plan M2, "chapter floor").

Input : one InputText (chinese_workflow.ingest.text), read for *structure only*: the cb:mulu,
        head, juan and enclosing-div markup that chinese_workflow.ingest.lines records per line
        (`mulu`, `heads`, `juan_marks`, `div_types`) over the whole file, plus the reading text of
        the mulu lines inside the requested span (for `evidence`). When the InputText holds only a
        span, the file is re-read from InputText.source_path, so pins and 卷 cover the whole file.
Output: Tier1Result:
  drafts     draft nodes (common.outline_doc idiom: node fields + "children"), document order,
             for the mulu inside `span` (inclusive lineheads; default: the InputText's own lines),
             preceded, in sūtra mode, by an editorial draft for every typed unit the span starts
             inside whose mulu line is before the span ("carried" pins, below);
  pins       [Pin]: every typed cb:mulu of the file other than 卷 and 科判, i.e. the text's
             chapter units (品, 序, 附文, 分, 會 …; @type verbatim), with their line span;
  juan       [{"n", "linehead", "label"}]: the 卷 system (cb:mulu type=卷, else cb:juan
             fun=open), which is not an outline node (design §5.1; kept for the renderer);
  anomalies  [str]: markup inside the span not turned into a node (untyped mulu, typed mulu
             without @level);
  anchors    [{"anchor", "heading_src", "part_type"}] of the drafts in pre-order, for tier 2.
  carried    [{"anchor", "pin_start", "end", "heading_src", "part_type", "level"}]: the carried
             pins (anchor = the span's first line, where tier 2 attaches the span's drafts).

Modes (metadata.outline_mode; mapping D3):
  * "sutra", role "commentary": every typed, levelled cb:mulu except 卷 becomes an explicit
    draft with `commentary.explained` = its line and `root_text` None + flag `unmapped` until
    align_pins gives the 品 drafts their chapter span in the root text. Typed mulu nest by @level.
  * "sutra", role "root": only `pins` / `juan` are used (the root 品 table); no drafts.
  * "self-outlining" (any role): typed mulu nest by @level and each draft carries its span in the
    outlined text: `commentary.explained` = `root_text.start` = the mulu's line, `root_text.end`
    by the next-node rule. 科判-typed mulu (X11n0268, P167n1573, D14n8842, G069n1977; R02
    F15/F28) thereby make a full kēpàn, with basis "cbeta-mulu" and end_basis "next-node" (the
    schema's names for this case). Other types get basis "chapter": their markup fixes both ends.

Rules and their sources:
  * @type and @level pass through verbatim, never hard-coded (ingest/README.md; R02 F11/F17).
  * T09n0262 = 7 卷 + 32 level-1 mulu (28 品, 3 序, 1 附文) + 1 level-2 序 under the 附文 (R02
    F20); T34n1723 = 20 卷 + 28 品 + 10 *untyped* level-2 mulu, which are per-卷 continuation
    markers (R02 F27, R04 F37): untyped mulu are dropped as nodes and listed in `anomalies`.
  * Unit end (the next-node rule of the schema's root_text_span.end_basis, which the golds use):
    the line before the next typed mulu of the same or a shallower level, in the file's own line
    order (T09n0262 puts its 附文 p0198a10–b11 between 妙音菩薩品 and 普門品, so string order is
    not document order); the last unit ends at the file's last line. Tier 1 knows lines only (all
    mulu of the fixtures sit at offset 0), so an end is never before its start line. Then, when
    the mulu sits in a cb:div, trailing lines outside that div are trimmed: the 卷 close/open and
    translator lines between two 品 (T09n0262 方便品 ends p0010b20, not p0010b27 where 卷第二
    opens) and a colophon after the last unit. This is the Kuiji gold's convention for its 28
    chapter spans (levels 1–2 of data/reference-outlines/T0262/kuiji-xuanzan), and it reproduces
    the gold's 陀羅尼品 root span T09n0262_p0058b08–p0059b27. Last, a parent's end is raised to its
    last descendant's end, so its span holds its children: a 科判 mulu's cb:div can be just the
    quoted root text (type=orig), and its child's mulu another div (X11n0268 p0190a06, E06), so
    trimming each unit alone gave 211 child-outside-parent errors. The note records the raise.
  * Carried pins (E06 review B2): a span build whose first line lies inside a 品 (or 序 / 附文 …)
    whose cb:mulu is before the span emits that unit as an editorial ancestor (origin "editorial",
    note CARRIED_NOTE, explained = the mulu line, _anchor = the span's first line). Without it a
    span build has no 品 pin, tier-2 drafts sit at the top level and the resolver's admissible
    range becomes the whole sūtra (tier1-T1718-validation: 0 drafts, 16 skipped). align_pins gives
    a carried 品 the root chapter like any other 品 draft; a span straddling two units carries the
    first (its unit ends before the second's mulu) and reads the second as usual.
  * Pin names (pin_name): CBETA's mulu text ("26 陀羅尼品"), the root head ("妙法蓮華經陀羅尼品
    第二十六"), Kuiji's ("陀羅尼品") and Zhiyi's ("釋陀羅尼品", works/toc T1718) all give
    "陀羅尼". Matching (find_pin): exact name, a pin not yet taken first; else the longest common
    substring ≥ 2 characters (T34n1723 從地涌出品 ~ T09n0262 從地踊出品, 壽量品 ~ 如來壽量品,
    觀世音普門品 ~ 觀世音菩薩普門品); else a one-character name found in exactly one candidate
    (持品 ~ 勸持品).
  * evidence: "<linehead>: <line text>" when the mulu's line is a heading line (its reading text
    is a head/jhead text), else "cb:mulu type=<type> level=<level> on <linehead>: <mulu text>";
    these are the two forms of the Kuiji gold's level-2 evidence, and the second never copies
    prose into the outline.
  * child_count_announced (科判 only): a trailing parenthesised count "(二)" always, flag
    count_mismatch when the children differ; a bare trailing count ("分二") only when it equals
    the children present (the rule of eval.gold.cbeta_mulu, restated here: stages may not import
    eval).

Divergence from the orchestrator brief: `raw` keys are omitted from `commentary` / `root_text`
instead of set to None, because the zh schema types them as strings (a null fails validation).

Provenance: R02 F11, F15, F17, F20, F27, F28 (context/research/R02-cbeta-xml-structure-markup);
docs/outliner-design.md §5.1; the works/toc oracle tests/fixtures/cbeta-api/works-toc-*.json.
Deterministic; standard library plus chinese_workflow.common / chinese_workflow.ingest.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

from ..common.lineheads import strip_offset
from ..ingest.lines import extract
from ..ingest.text import InputText

JUAN_TYPE = "卷"
KEPAN_TYPE = "科判"
CHAPTER_TYPE = "品"
MODES = ("sutra", "self-outlining")
ROLES = ("root", "commentary")
TITLE_PREFIXES = ("妙法蓮華經",)  # a sūtra title fused to a chapter head (T09n0262 heads)

_BRACKETS = re.compile(r"[〈〉《》「」『』【】()（）\s　]")
_LEADING_NUMBER = re.compile(r"^[0-9]+")
_TRAILING_ORDINAL = re.compile(r"第[〇零一二三四五六七八九十百]+$")
_CJK_DIGIT = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
              "九": 9}
_NUMERALS = "〇一二三四五六七八九十"
_TRAILING_PAREN = re.compile(r"[(（]([%s]+)[)）]$" % _NUMERALS)
_TRAILING_BARE = re.compile(r"([%s]+)$" % _NUMERALS)


@dataclass
class Pin:
    """One chapter-level unit of a text (a root 品 table entry)."""

    name: str  # normalized name used for matching, e.g. "陀羅尼"
    heading: str  # mulu text as CBETA gives it, e.g. "26 陀羅尼品"
    start: str  # linehead of the mulu line
    end: str  # last line of the unit, inclusive
    part_type: str  # mulu @type verbatim: "品", "序", "附文" …
    level: int | None


@dataclass
class Tier1Result:
    drafts: list = field(default_factory=list)
    pins: list = field(default_factory=list)
    juan: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)
    anchors: list = field(default_factory=list)
    carried: list = field(default_factory=list)  # pins carried into a span build (module docstring)


# ------------------------------------------------------------------------------------ names


def pin_name(heading: str) -> str:
    """Normalized chapter name for matching: brackets and spaces removed; CBETA's leading mulu
    number, a fused sūtra title (TITLE_PREFIXES), a trailing 第N ordinal, Zhiyi's leading 釋 (釋X品)
    and the 品 suffix stripped. "妙法蓮華經陀羅尼品第二十六", "26 陀羅尼品", "〈陀羅尼品〉",
    "釋陀羅尼品" -> "陀羅尼"."""
    s = _BRACKETS.sub("", heading or "")
    s = _LEADING_NUMBER.sub("", s)
    for prefix in TITLE_PREFIXES:
        if s.startswith(prefix) and len(s) > len(prefix):
            s = s[len(prefix):]
    s = _TRAILING_ORDINAL.sub("", s)
    if s.startswith("釋") and s.endswith(CHAPTER_TYPE) and len(s) > 2:
        s = s[1:]
    if s.endswith(CHAPTER_TYPE) and len(s) > 1:
        s = s[:-1]
    return s


def _common_substring(a: str, b: str) -> int:
    """Length of the longest common substring of a and b."""
    best = 0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def find_pin(name: str, pins: list, *, used: set | None = None) -> tuple:
    """(index into pins, how) of the pin a normalized chapter name matches, else (None, None).
    how: "exact", "overlap N" or "contained". Pins whose index is not in `used` are preferred at
    every step; ties go to the smaller length difference, then to document order."""
    used = used or set()
    if not name:
        return None, None
    order = sorted(range(len(pins)), key=lambda i: (i in used, i))
    for i in order:
        if pins[i].name == name:
            return i, "exact"
    for pool in ([i for i in order if i not in used], order):
        scored = [(_common_substring(name, pins[i].name), -abs(len(name) - len(pins[i].name)), -i)
                  for i in pool]
        if scored:
            best = max(scored)
            if best[0] >= 2:
                return -best[2], "overlap %d" % best[0]
    if len(name) == 1:
        hits = [i for i in range(len(pins)) if name in pins[i].name]
        if len(hits) == 1:
            return hits[0], "contained"
    return None, None


# ----------------------------------------------------------------------------- file reading


def _records(text: InputText) -> list:
    """The line records of the whole file (structure is always read whole-file)."""
    if len(text.lines) == len(text.all_lineheads):
        return text.lines
    if not text.source_path:
        raise ValueError("InputText %s holds a span and has no source_path for the whole file"
                         % text.text_id)
    return extract(text.source_path).lines


def _span_positions(records: list, span: tuple | None, text: InputText) -> tuple:
    """(first, last) record positions of the drafting span, inclusive."""
    pos = {rec["linehead"]: i for i, rec in enumerate(records)}
    if span is None:
        if not text.lines:
            return 0, -1
        span = (text.lines[0]["linehead"], text.lines[-1]["linehead"])
    first, last = strip_offset(span[0]), strip_offset(span[1])
    if first not in pos or last not in pos:
        raise KeyError("span %s..%s is not in %s" % (first, last, text.text_id))
    if pos[first] > pos[last]:
        raise ValueError("span %s..%s runs backwards" % (first, last))
    return pos[first], pos[last]


def _mulu_entries(records: list) -> list:
    """Every cb:mulu of the file as a dict with its line position, document order."""
    out = []
    for i, rec in enumerate(records):
        for m in rec["mulu"]:
            out.append({"pos": i, "lh": rec["linehead"], "level": m["level"], "type": m["type"],
                        "n": m["n"], "text": m["text"], "offset": m["offset"],
                        "div_type": m["div_type"]})
    return out


def _unit_end(k: int, units: list, records: list) -> tuple:
    """(end position, reached_next_node) of units[k]: the next-node rule, then trimmed back over
    trailing lines outside the unit's cb:div (module docstring)."""
    u = units[k]
    nxt = next((v for v in units[k + 1:] if v["level"] <= u["level"]), None)
    end = max(u["pos"], nxt["pos"] - 1) if nxt is not None else len(records) - 1
    if u["div_type"]:
        while end > u["pos"] and u["div_type"] not in (records[end]["div_types"] or []):
            end -= 1
    return end, nxt is not None


def _unit_ends(units: list, records: list) -> list:
    """[(end position, reached_next_node, trimmed end or None)] of every unit: _unit_end, then a
    parent's end raised to its last descendant's (module docstring); the third value is the end it
    replaced, None when nothing was raised. Units nest by @level as in build()."""
    ends = [[*_unit_end(k, units, records), None] for k in range(len(units))]
    parent, stack = [], []
    for k, u in enumerate(units):
        while stack and units[stack[-1]]["level"] >= u["level"]:
            stack.pop()
        parent.append(stack[-1] if stack else None)
        stack.append(k)
    for k in range(len(units) - 1, -1, -1):  # descendants follow their parent: raised before it is read
        p = parent[k]
        if p is not None and ends[k][0] > ends[p][0]:
            if ends[p][2] is None:
                ends[p][2] = ends[p][0]
            ends[p][0] = ends[k][0]
    return [tuple(e) for e in ends]


def _evidence(rec: dict, m: dict) -> str:
    heads = {h["text"] for h in rec["heads"]}
    if m["type"] != KEPAN_TYPE and rec["text"] and rec["text"] in heads:
        return "%s: %s" % (rec["linehead"], rec["text"])
    return "cb:mulu type=%s level=%s on %s: %s" % (m["type"], m["level"], rec["linehead"],
                                                   m["text"])


CARRIED_NOTE = ("pin carried from %s: cb:mulu type=%s level=%s lies before the span %s..%s; editorial "
                "ancestor for the span's part of the unit (%s..%s)")


def _carried_units(units: list, ends: list, first: int) -> list:
    """Indexes of the typed, levelled, non-科判 units whose mulu line lies before the span and whose
    unit (next-node end, trimmed and raised: _unit_ends) still holds the span's first line. Document
    order = outermost first, so nesting by @level works as in build()."""
    return [k for k, u in enumerate(units)
            if u["type"] != KEPAN_TYPE and u["pos"] < first <= ends[k][0]]


def _carried_draft(u: dict, end_pos: int, records: list, first: int, last: int) -> dict:
    """An editorial ancestor for a unit the span starts inside (sūtra mode; module docstring).
    commentary.explained is the mulu line (tier 1's rule; it lies outside the span, so the node has no
    position in the span's outlined text and a span-restricted scorer never counts it); the private
    _anchor is the span's first line, which is where tier 2 and merge attach the span's drafts."""
    anchor = records[first]["linehead"]
    return {
        "heading_src": u["text"],
        "part_type": u["type"],
        "origin": "editorial",
        "evidence": "cb:mulu type=%s level=%s on %s: %s" % (u["type"], u["level"], u["lh"], u["text"]),
        "node_class": "sutra-span",
        "flags": ["unmapped"],
        "notes": [CARRIED_NOTE % (u["lh"], u["type"], u["level"], anchor, records[last]["linehead"],
                                  anchor, records[min(end_pos, last)]["linehead"])],
        "locations": {"scheme": "cbeta-kepan",
                      "commentary": {"announced": None, "explained": u["lh"]},
                      "root_text": None},
        "_anchor": anchor,
        "_carried_from": u["lh"],
        "children": [],
    }


def _cjk_number(s: str) -> int | None:
    """一..九十九 as an int; None for anything else."""
    if not s or any(ch not in _CJK_DIGIT and ch != "十" for ch in s):
        return None
    if "十" not in s:
        return _CJK_DIGIT[s] if len(s) == 1 else None
    i = s.index("十")
    if i > 1 or len(s) - i > 2:
        return None
    tens = _CJK_DIGIT[s[0]] if i == 1 else 1
    ones = _CJK_DIGIT.get(s[i + 1:]) if s[i + 1:] else 0
    return None if ones is None or tens == 0 else tens * 10 + ones


def _announced_count(heading: str) -> tuple:
    """(count, parenthesised) of a trailing count in a 科判 heading, or (None, False)."""
    m = _TRAILING_PAREN.search(heading)
    if m:
        n = _cjk_number(m.group(1))
        return (n, True) if n is not None else (None, False)
    m = _TRAILING_BARE.search(heading)
    if m and m.start() > 0:
        return _cjk_number(m.group(1)), False
    return None, False


# ------------------------------------------------------------------------------------ build


def build(text: InputText, *, mode: str, role: str, span: tuple | None = None) -> Tier1Result:
    """Tier 1 over one text (module docstring). `span` = (first, last) lineheads, inclusive:
    drafts are emitted only for mulu on those lines (default: the InputText's own lines); pins,
    juan and the unit ends are computed over the whole file."""
    if mode not in MODES:
        raise ValueError("mode must be one of %s, not %r" % (MODES, mode))
    if role not in ROLES:
        raise ValueError("role must be one of %s, not %r" % (ROLES, role))
    records = _records(text)
    first, last = _span_positions(records, span, text)
    res = Tier1Result()

    units = []  # typed, levelled, not 卷: the nodes of the table of contents
    for e in _mulu_entries(records):
        inside = first <= e["pos"] <= last
        if e["type"] == JUAN_TYPE:
            res.juan.append({"n": e["n"], "linehead": e["lh"], "label": e["text"]})
        elif not e["type"]:
            if inside:
                res.anomalies.append(
                    "untyped cb:mulu level=%s %r on %s dropped: a per-卷 continuation marker, "
                    "not an outline node (R02 F27)" % (e["level"], e["text"], e["lh"]))
        elif e["level"] is None:
            if inside:
                res.anomalies.append("cb:mulu type=%s without @level on %s (%r) dropped"
                                     % (e["type"], e["lh"], e["text"]))
        else:
            units.append(e)
    if not res.juan:  # no 卷 mulu: fall back to the cb:juan open marks
        for rec in records:
            for jm in rec["juan_marks"]:
                if jm["fun"] == "open":
                    res.juan.append({"n": jm["n"], "linehead": rec["linehead"], "label": ""})

    ends = _unit_ends(units, records)
    for k, u in enumerate(units):
        if u["type"] != KEPAN_TYPE:
            res.pins.append(Pin(name=pin_name(u["text"]), heading=u["text"], start=u["lh"],
                                end=records[ends[k][0]]["linehead"], part_type=u["type"],
                                level=u["level"]))
    if mode == "sutra" and role == "root":
        return res

    stack: list = []  # [(source level, draft)]
    counts: dict = {}  # id(draft) -> (count, parenthesised)
    if mode == "sutra":  # the span starts inside a unit whose mulu line is before it: carry the unit
        for k in _carried_units(units, ends, first):
            u = units[k]
            draft = _carried_draft(u, ends[k][0], records, first, last)
            (stack[-1][1]["children"] if stack else res.drafts).append(draft)
            stack.append((u["level"], draft))
            res.carried.append({"anchor": draft["_anchor"], "pin_start": u["lh"],
                                "end": records[ends[k][0]]["linehead"], "heading_src": u["text"],
                                "part_type": u["type"], "level": u["level"]})
        if not res.carried and units and first not in {u["pos"] for u in units} \
                and any(u["pos"] < first for u in units):
            res.anomalies.append("no typed cb:mulu unit holds the span's first line %s (it lies "
                                 "between units or after the last); no pin carried"
                                 % records[first]["linehead"])
    for k, u in enumerate(units):
        if not first <= u["pos"] <= last:
            continue
        while stack and stack[-1][0] >= u["level"]:
            stack.pop()
        flags, notes = _nesting_notes(u, stack, units[:k])
        if mode == "self-outlining":
            root_text = _self_span(u, ends[k], records, notes)
        else:
            root_text = None
            flags.append("unmapped")
        draft = {
            "heading_src": u["text"],
            "part_type": u["type"],
            "origin": "explicit",
            "confidence": 1.0,
            "evidence": _evidence(records[u["pos"]], u),
            "node_class": "sutra-span",
            "flags": flags,
            "notes": notes,
            "locations": {"scheme": "cbeta-kepan",
                          "commentary": {"announced": None, "explained": u["lh"]},
                          "root_text": root_text},
            "_anchor": u["lh"],
            "children": [],
        }
        if u["type"] == KEPAN_TYPE:
            count, paren = _announced_count(u["text"])
            if count is not None:
                counts[id(draft)] = (count, paren)
        (stack[-1][1]["children"] if stack else res.drafts).append(draft)
        stack.append((u["level"], draft))

    for d in iter_drafts(res.drafts):
        if id(d) in counts:
            _set_count(d, *counts[id(d)])
    res.anchors = [{"anchor": d["_anchor"], "heading_src": d["heading_src"],
                    "part_type": d["part_type"]} for d in iter_drafts(res.drafts)]
    return res


def _nesting_notes(u: dict, stack: list, before: list) -> tuple:
    """(flags, notes) for a unit whose @level skips a level (never inventing one)."""
    if stack and u["level"] - stack[-1][0] > 1:
        return ["irregular_label"], ["cb:mulu level=%d directly under level=%d; attached one "
                                     "level down, no level invented" % (u["level"], stack[-1][0])]
    if not stack and u["level"] > 1:
        if any(v["level"] < u["level"] for v in before):
            return [], ["cb:mulu level=%d whose parent mulu lies before the span: a top-level "
                        "draft here" % u["level"]]
        return ["irregular_label"], ["cb:mulu level=%d with no shallower mulu before it in the "
                                     "file; read as a top-level node" % u["level"]]
    return [], []


def _self_span(u: dict, end: tuple, records: list, notes: list) -> dict:
    """Self-outlining root_text of a unit: its own line to its next-node end."""
    end_pos, reached, trimmed = end
    kepan = u["type"] == KEPAN_TYPE
    if not reached:
        notes.append("last unit of its branch in the file: root_text.end is the file's last line"
                     + (" of its cb:div" if u["div_type"] else ""))
    if trimmed is not None:
        notes.append("root_text.end extended from %s (the last line of its cb:div type=%s) to %s, the "
                     "end of its last descendant" % (records[trimmed]["linehead"], u["div_type"],
                                                     records[end_pos]["linehead"]))
    return {"start": u["lh"], "end": records[end_pos]["linehead"],
            "basis": "cbeta-mulu" if kepan else "chapter",
            "end_basis": "next-node" if kepan and reached else None}


def _set_count(d: dict, count: int, paren: bool) -> None:
    present = len(d["children"])
    if paren:
        d["child_count_announced"] = count
        if present != count:
            d["flags"].append("count_mismatch")
            d["notes"].append("heading announces %d children; %d present" % (count, present))
    elif present == count > 0:
        d["child_count_announced"] = count


def iter_drafts(drafts: list):
    """Pre-order walk over a draft tree."""
    for d in drafts:
        yield d
        yield from iter_drafts(d.get("children") or [])


# ------------------------------------------------------------------------------------ align


def align_pins(drafts: list, root_pins: list) -> list:
    """Sūtra mode: give every commentary 品 draft (part_type 品, at any depth) the root text's
    chapter span, matched by name (pin_name / find_pin) against the root pins of type 品:
    root_text = {start, end, basis "chapter", end_basis None}, flag `unmapped` removed. A draft
    with no match keeps root_text None and flag `unmapped`, with a note. Exact matches are made
    for all drafts first, so a fuzzy match never takes a pin another draft names exactly. Returns
    a deep copy; the input is not modified."""
    out = copy.deepcopy(drafts)
    chapters = [p for p in root_pins if p.part_type == CHAPTER_TYPE]
    targets = [d for d in iter_drafts(out) if d.get("part_type") == CHAPTER_TYPE]
    used: set = set()
    matched: dict = {}
    for d in targets:
        name = pin_name(d.get("heading_src", ""))
        i = next((k for k, p in enumerate(chapters) if p.name == name and k not in used), None)
        if i is not None:
            used.add(i)
            matched[id(d)] = (i, "exact")
    for d in targets:
        if id(d) not in matched:
            i, how = find_pin(pin_name(d.get("heading_src", "")), chapters, used=used)
            if i is not None:
                used.add(i)
                matched[id(d)] = (i, how)
    for d in targets:
        flags = d.setdefault("flags", [])
        notes = d.setdefault("notes", [])
        loc = d.setdefault("locations", {"scheme": "cbeta-kepan", "commentary": None,
                                         "root_text": None})
        if id(d) not in matched:
            loc["root_text"] = None
            if "unmapped" not in flags:
                flags.append("unmapped")
            notes.append("tier 1: no root-text 品 matches %r by name" % d.get("heading_src"))
            continue
        i, how = matched[id(d)]
        pin = chapters[i]
        loc["root_text"] = {"start": pin.start, "end": pin.end, "basis": "chapter",
                            "end_basis": None}
        d["flags"] = [f for f in flags if f != "unmapped"]
        if how != "exact":
            notes.append("tier 1: root 品 %r (%s..%s) matched by name, %s (%r ~ %r)"
                         % (pin.heading, pin.start, pin.end, how, pin_name(d["heading_src"]),
                            pin.name))
    return out
