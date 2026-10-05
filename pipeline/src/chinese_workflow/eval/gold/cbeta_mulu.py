"""chinese_workflow.eval.gold.cbeta_mulu — import a CBETA `cb:mulu type="科判"` tree as a zh-kepan
gold outline. Task 7 of `docs/plans/2026-09-22-eval-datasets.md`.

Input : one CBETA P5 file that carries `cb:mulu type="科判"` nodes directly in its own markup —
        of the whole 2026R2 corpus, exactly four do (R02 F15/F28): X11n0268 楞嚴經集註 (2,611
        nodes, levels 1-28), P167n1573 修懺要旨 (127, levels 2-15), D14n8842 般若心經註解 (40,
        levels 1-10) — this module's three texts (Task 7) — and G069n1977 (15; Task 9's fixture).
        data/raw/cbeta/xml-p5/X/X11/X11n0268.xml, P/P167/P167n1573.xml, D/D14/D14n8842.xml, read
        with chinese_workflow.ingest.lines (`extract`), whose `mulu` records already resolve gaiji
        in the heading text and separate the file's own-canon linehead from any other edition's
        `lb` on the same line (X11n0268's R017 pairing, R02 G16a).
Output: data/reference-outlines/X0268/cbeta-mulu-kepan/outline.json (+ P1573/, D8842/), each with a
        PROVENANCE.md written by hand alongside it (not by this module). Every node is `origin:
        "imported"`, `gold_status: "imported-unchecked"`, `node_class: "sutra-span"` with a resolved
        `locations.root_text` (`basis: "cbeta-mulu"`) — see "node_class / outline_mode" below.

Tree construction (R02 F28: "every level present and no level skipped between consecutive nodes"
for X11n0268; checked, not assumed, for the other two):
  * One zh-kepan node per `cb:mulu type="科判"`, in document order. `heading_src` = the mulu's
    resolved text, verbatim (docs/architecture.md: CBETA text unaltered). `locations.commentary.announced`
    and `.explained` are both the line's own-canon linehead (composed by `ingest.lines`): CBETA's
    TOC-style markup gives one position per node, immediately before the content it introduces, so
    there is no separate earlier "announcement" line to distinguish (unlike Kurt's folio pairs or
    sdp's tree+HTML merge). In self-outlining mode (see below) these positions are already positions
    *in the root text itself* (`metadata.root_text_id` = this same file), which is what the schema's
    `commentary_position` docstring asks for.
  * `locations.root_text` (`basis: "cbeta-mulu"`, the schema's own name for exactly this case —
    "the lb preceding a CBETA cb:mulu 科判 node (X11n0268, R02 F28)"): `start` is that same
    linehead. Checked on all 2,778 nodes across the three files (not assumed): every `cb:mulu
    type="科判"` sits at offset 0 of its line — the very first thing after the `<lb>` that opens
    it, with no reading text between them — so "the lb preceding the mulu" and "the lb the mulu
    sits on" are the same line in every case; `start` needs no separate lookup beyond `linehead`.
    `end` is the inclusive last own-canon line before the next node that is *not* a descendant of
    this one (the next node at the same or a shallower structural level, `end_basis: "next-node"`,
    the schema's own phrase for it) — computed bottom-up: a leaf's end is (the line before) its
    immediate successor in the raw cb:mulu sequence; an interior node's end is inherited directly
    from its last child's end (by construction always >= any other descendant's, so a child's span
    always lies inside its parent's — `scripts/validate_outline.py` `[child-outside-parent]`). The
    very last `cb:mulu` in a file (and every ancestor along its rightmost branch) has no successor
    to measure against: its end is the file's own last own-canon line, `end_basis: null`, noted.
  * Nesting: a stack of (source `@level`, draft) keyed by the *source* level; a new node's parent is
    the innermost stack entry whose source level is less than the new node's (never invented: the
    output `level` is always structural, `parent.level + 1`, via `common.number_tree`). When the
    gap between the new node's source level and its parent's exceeds 1 (a level-k+2 node directly
    under a level-k node, or a node that opens the document, or a fresh top-level run, at a source
    level other than 1 with no shallower node pending — P167n1573 opens at level 2 twice, once at
    the very start and once after its first subtree closes, R02 F15 "levels 2-15") — the node is
    flagged `irregular_label` and a note gives the source level that was collapsed into a plain
    parent+1 step. This is the plan's (Task 7) "handle level jumps ... never inventing a node".
  * `merged_range`: exactly one X11n0268 `cb:mulu` (level 4, line 0185a08) holds two labels joined
    by a full-width space ("二緣覺眾　三菩薩眾") instead of two elements; kept as one node, flagged,
    heading_src verbatim.
  * `child_count_announced`: many 科判 headings end with the count CBETA's own schema example uses
    ("「分二」" -> 2, "「文為五」" -> 5): X11n0268/P167n1573 write it parenthesised ("初序分(二)"),
    D14n8842 bare ("次本文二"). The parenthesised form is an unambiguous marker: it is always kept,
    flagging `count_mismatch` (+ note) when it disagrees with the children actually present. The
    bare form is not a reliable marker on its own (many headings simply end in a numeral-like
    character; heading_src keeps it either way) — it is kept only when it equals the number of
    children actually built for that node (self-verified), otherwise silently left null. No count
    is invented; nothing is dropped from heading_src.
  * `display_label`: null. The source's own ordinal (初/二/三/四…) is fused to the heading with no
    delimiter ("初序分", "二正宗分"); splitting it out reliably (some headings do not start with an
    ordinal, e.g. inline parenthetical glosses) is not attempted here, unlike `authored.py`'s
    generated 干支 labels or sdp's leading-digit labels.

node_class / outline_mode — this follows the schema's own named example directly, not a divergence
from it. `context/baseline/outline-schema-zh.json` names X11n0268 twice: `source_document.kind`
`"root-text"` is defined as "stated in, or marked up on, the outlined text itself (a self-outlining
treatise; CBETA cb:mulu type=科判 markup as in X11n0268, R02 F28)", and `root_text_span.basis`
`"cbeta-mulu"` is defined as "the lb preceding a CBETA cb:mulu 科判 node (X11n0268, R02 F28)". Both
describe exactly this markup, so:

  * `outline_mode: "self-outlining"` (the outlined text states its own divisions — here, in its own
    `cb:mulu` markup); `source_document.kind: "root-text"`; `metadata.root_text_id` = the file's own
    CBETA id (X11n0268 etc.); `metadata.commentary_id: null` (the schema's hard constraint for this
    mode).
  * `node_class: "sutra-span"` on every node: in self-outlining mode this means the node divides the
    outlined text itself, which every `cb:mulu type="科判"` node does by construction — there is no
    separate "commentary discourse" to set apart from "root text" when the outlined text states its
    own outline over itself, unlike the sūtra-mode case (a commentary's own prefatory gates, etc.).
    `locations.root_text` is therefore populated on every node (`basis: "cbeta-mulu"`, see above),
    never null, and no node needs flag `unmapped`.

(Superseded: an earlier version of this module set `outline_mode: "sutra"`, `commentary_id` = the
file's own id, `root_text_id: null`, `node_class: "commentary-internal"` on every node, reading
`commentary_id` as "the document that states the outline" independently of whether it is also the
root text. The controller's review found this read `source_document.kind`/`root_text_span.basis`
against their own schema-docstring definitions, which name X11n0268 for the *opposite* assignment;
corrected 2026-09-22, "Fix round 1".)

Licence: CC BY-NC-SA 4.0 + CBETA's notice + release label 2026R2 (plan Global Constraint 2; R02 F7,
F29; `data/reference-outlines/NOTICE`), matching `T0262/kuiji-xuanzan`'s treatment: `eval_only:
false` because the licence permits redistribution (open question to CBETA: whether an outline
table of headings and lineheads counts as 改作, G8, not yet answered either way).

Usage : python -m chinese_workflow.eval.gold.cbeta_mulu                       the three known files
        python -m chinese_workflow.eval.gold.cbeta_mulu <xml> [--scheme ID]  one file
        python -m chinese_workflow.eval.gold.cbeta_mulu <xml> --out <path>   custom output path
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from chinese_workflow.eval.gold import common
from chinese_workflow.ingest.lines import extract

SCHEME_ID = "cbeta-mulu-kepan"
CBETA_RELEASE = "2026R2"
GENERATED_BY = "chinese_workflow.eval.gold.cbeta_mulu"
KEPAN_TYPE = "科判"

# Task 7's three files: CBETA id -> (reference-outlines folder, default location under xml-p5).
FILES = {
    "X11n0268": ("X0268", "X/X11/X11n0268.xml"),
    "P167n1573": ("P1573", "P/P167/P167n1573.xml"),
    "D14n8842": ("D8842", "D/D14/D14n8842.xml"),
}

_TEI = "{http://www.tei-c.org/ns/1.0}"

_CJK_DIGIT = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NUMERAL_CHARS = "〇一二三四五六七八九十"
_TRAILING_PAREN = re.compile(r"[(（]([%s]+)[)）]\Z" % _NUMERAL_CHARS)
_TRAILING_BARE = re.compile(r"([%s]+)\Z" % _NUMERAL_CHARS)

LICENCE = {
    "id": "CC-BY-NC-SA-4.0",
    "holder": "CBETA Foundation (財團法人佛教電子佛典基金會)",
    "statement": (
        "Derived from CBETA 電子佛典 (xml-p5 release 2026R2); headings are verbatim CBETA cb:mulu "
        "text and every location is a CBETA linehead. Released under Creative Commons "
        "Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0), with CBETA's "
        "版權宣告 attached (data/reference-outlines/NOTICE; snapshot "
        "data/raw/cbeta/LICENCE-NOTICE.txt). Non-commercial use only; never relicensed "
        "permissively. Whether an outline table of headings and lineheads counts as 改作 under "
        "CBETA's notice is an open question to CBETA (R02 F29, G8)."
    ),
    "evidence": "context/research/R02-cbeta-xml-structure-markup/findings.md F7, F15, F28, F29 (S14, S63)",
}

FORMAT_NOTE = (
    "Imported from CBETA's own cb:mulu type=\"科判\" markup in %s (R02 F15/F28), via "
    "chinese_workflow.ingest.lines. One node per cb:mulu, in document order; heading_src is the "
    "mulu's resolved text verbatim (gaiji resolved, punctuation kept, CLAUDE.md). "
    "locations.commentary.announced and .explained are both the line's own-canon linehead (CBETA's "
    "TOC-style markup gives one position per node), which in self-outlining mode is already a "
    "position in the root text itself. locations.root_text is resolved on every node (node_class "
    "sutra-span throughout): start = that same linehead (\"the lb preceding a CBETA cb:mulu 科判 "
    "node\", basis cbeta-mulu, checked to be offset 0 of its line on all nodes of all three "
    "files); end = the inclusive last own-canon line before the next node that is not this "
    "node's descendant (end_basis next-node), computed bottom-up so a child's span always lies "
    "inside its parent's; the file's very last node (and its rightmost ancestors) end at the "
    "file's last own-canon line instead (end_basis null, noted). See this module's docstring. "
    "Nesting follows the source's cb:mulu @level, attaching each node "
    "to the nearest node whose source level is smaller (never inventing an intermediate node); a "
    "gap greater than 1 (a level jump, or a node opening at a source level other than 1 with no "
    "shallower node pending) is flagged irregular_label with a note giving the source level, and "
    "the output level is always structural (parent level + 1). child_count_announced is read from "
    "a heading's trailing parenthesised CJK numeral (\"初序分(二)\" -> 2), flagging count_mismatch "
    "when it disagrees with the children actually present; a bare trailing numeral (no "
    "parentheses, D14n8842's own convention) is kept only when it already equals the children "
    "present (self-verified), otherwise left null. display_label is null (the source's ordinal is "
    "fused to the heading with no delimiter). origin: imported, source_node_id = \"<cbeta "
    "id>#<ordinal>\" (1-based position among this file's 科判 nodes, document order); gold_status: "
    "imported-unchecked (not checked against the printed 首楞嚴經指文科節 chart or any secondary "
    "source, R02 F28)."
)


# --------------------------------------------------------------------------------------- reading


@dataclass
class MuluHit:
    level: int
    heading_src: str
    linehead: str
    ordinal: int
    r017_linehead: str | None = None


@dataclass
class ReadResult:
    info: dict
    author: str | None
    hits: list  # MuluHit, document order
    unlevelled: int  # 科判 mulu with no @level (should be 0; kept as an anomaly count, not silent)
    all_lineheads: list  # every own-canon linehead of the file, in document order (root_text.end)


def read_mulu(xml_path) -> ReadResult:
    """Every cb:mulu type="科判" of one CBETA P5 file, in document order, with its own-canon
    linehead and (X11n0268 only) the paired R017 linehead (R02 F28/G16a: restricted to the file's
    own canon, not the nearest lb of any edition), plus the file's full own-canon line sequence
    (root_text.end, module docstring)."""
    ex = extract(xml_path)
    hits: list = []
    unlevelled = 0
    for rec in ex.lines:
        for m in rec["mulu"]:
            if m["type"] != KEPAN_TYPE:
                continue
            if m["level"] is None:
                unlevelled += 1
                continue
            r017 = next((a["n"] for a in rec["alt"] if a["ed"] == "R017"), None)
            hits.append(
                MuluHit(
                    level=m["level"],
                    heading_src=m["text"],
                    linehead=rec["linehead"],
                    ordinal=len(hits) + 1,
                    r017_linehead=("R017_p%s" % r017) if r017 else None,
                )
            )
    root = etree.parse(str(xml_path)).getroot()
    author = (root.findtext(".//%stitleStmt/%sauthor" % (_TEI, _TEI)) or "").strip() or None
    all_lineheads = [rec["linehead"] for rec in ex.lines]
    return ReadResult(
        info=ex.info, author=author, hits=hits, unlevelled=unlevelled, all_lineheads=all_lineheads
    )


# ------------------------------------------------------------------------------- numeral parsing


def cjk_number(s: str) -> int | None:
    """A bare CJK numeral 一..九十九 (schema style, "分二" -> 2, "十二" -> 12) as an int; None if `s`
    is not composed solely of 〇-九十 or is not a shape this parses (three or more true digits
    around a 十, e.g. hundreds, are out of range for any count observed here, R02 F28)."""
    if not s or any(ch not in _CJK_DIGIT and ch != "十" for ch in s):
        return None
    if s == "十":
        return 10
    if "十" not in s:
        return _CJK_DIGIT[s] if len(s) == 1 else None
    i = s.index("十")
    if i > 1 or len(s) - i > 2:
        return None
    tens = _CJK_DIGIT[s[i - 1]] if i == 1 else 1
    ones_part = s[i + 1 :]
    ones = 0 if not ones_part else _CJK_DIGIT.get(ones_part)
    return None if ones is None else tens * 10 + ones


def announced_count(heading: str) -> tuple:
    """(count, is_paren_marker) parsed from a trailing CJK-numeral announcement in `heading` (module
    docstring); (None, False) when none is found or it does not parse as a plain number."""
    m = _TRAILING_PAREN.search(heading)
    if m:
        n = cjk_number(m.group(1))
        return (n, True) if n is not None else (None, False)
    m = _TRAILING_BARE.search(heading)
    if m and m.start() > 0:
        n = cjk_number(m.group(1))
        if n is not None:
            return n, False
    return None, False


# --------------------------------------------------------------------------------- tree building


@dataclass
class BuildResult:
    roots: list  # nested drafts (common.py idiom: node fields + "children")
    node_count: int
    jump_count: int  # nodes flagged irregular_label for a level jump / rootless start
    merged_count: int  # nodes flagged merged_range
    count_mismatch: int  # nodes flagged count_mismatch
    counts_verified: int  # nodes whose child_count_announced was set (paren or self-verified bare)
    max_source_level: int
    unlevelled: int


def build_tree(hits: list, cbeta_id: str, all_lineheads: list, unlevelled: int = 0) -> BuildResult:
    """`all_lineheads`: every own-canon linehead of the file, in document order (module docstring,
    root_text.end)."""
    roots: list = []
    stack: list = []  # [(source level, draft)]
    pending_counts: dict = {}  # id(draft) -> (count, is_paren)
    next_linehead: dict = {}  # id(draft) -> the immediately following cb:mulu's linehead, or None
    jump_count = merged_count = 0
    max_level = 0

    for i, hit in enumerate(hits):
        while stack and stack[-1][0] >= hit.level:
            stack.pop()
        parent_level = stack[-1][0] if stack else 0
        structural_level = len(stack) + 1
        flags: list = []
        notes: list = []
        if hit.level - parent_level > 1:
            jump_count += 1
            flags.append("irregular_label")
            if not stack:
                notes.append(
                    'cb:mulu level="%d" with no preceding shallower 科判 node in the source '
                    "(document start, or a fresh top-level run); read as a document root "
                    "(structural level 1), never inventing the missing levels" % hit.level
                )
            else:
                notes.append(
                    'cb:mulu level="%d" appears directly under level="%d" in the source (no '
                    "intervening level present between them); attached to that node and given "
                    "structural level %d (parent + 1), never inventing the missing levels"
                    % (hit.level, parent_level, structural_level)
                )
        if "　" in hit.heading_src:
            merged_count += 1
            flags.append("merged_range")
            notes.append(
                "this single cb:mulu element's text holds more than one heading, joined by a "
                "full-width space in the source; kept as one node, heading_src verbatim"
            )
        if hit.r017_linehead:
            notes.append(
                "this line also carries an R017 linehead %s (R02 F28/G16a); this gold uses only "
                "the file's own %s-canon linehead" % (hit.r017_linehead, cbeta_id[0])
            )

        draft = {
            "heading_src": hit.heading_src,
            "heading_en": "",
            "display_label": None,
            "source_node_id": "%s#%d" % (cbeta_id, hit.ordinal),
            "origin": "imported",
            "node_class": "sutra-span",
            "flags": flags,
            "child_count_announced": None,
            "extent_announced": None,
            "locations": {
                "scheme": "cbeta-kepan",
                "commentary": {"announced": hit.linehead, "explained": hit.linehead},
                "root_text": None,  # filled below, bottom-up (module docstring)
            },
            "evidence": 'CBETA cb:mulu type="科判" level="%d" on %s: "%s"'
            % (hit.level, hit.linehead, hit.heading_src),
            "notes": notes,
            "children": [],
        }
        count, is_paren = announced_count(hit.heading_src)
        if count is not None:
            pending_counts[id(draft)] = (count, is_paren)
        next_linehead[id(draft)] = hits[i + 1].linehead if i + 1 < len(hits) else None
        if stack:
            stack[-1][1]["children"].append(draft)
        else:
            roots.append(draft)
        stack.append((hit.level, draft))
        max_level = max(max_level, hit.level)

    count_mismatch = counts_verified = 0
    position = {lh: i for i, lh in enumerate(all_lineheads)}
    last_position = len(all_lineheads) - 1

    def finalize(draft: dict) -> tuple:
        """Post-order: fills child_count_announced/root_text on `draft` and every descendant;
        returns (end_linehead, end_basis, note_or_None) for the parent to inherit (module
        docstring: an interior node's end is exactly its last child's end)."""
        nonlocal count_mismatch, counts_verified
        child_end = None
        for child in draft["children"]:
            child_end = finalize(child)  # last one wins: children are in document order

        entry = pending_counts.get(id(draft))
        if entry is not None:
            count, is_paren = entry
            actual = len(draft["children"])
            if is_paren:
                draft["child_count_announced"] = count
                counts_verified += 1
                if actual != count:
                    count_mismatch += 1
                    draft["flags"].append("count_mismatch")
                    draft["notes"].append(
                        "cb:mulu heading announces %d children in parentheses; %d present in "
                        "this gold's tree" % (count, actual)
                    )
            elif actual == count and actual > 0:
                draft["child_count_announced"] = count
                counts_verified += 1

        start = draft["locations"]["commentary"]["explained"]
        if child_end is not None:
            end_linehead, end_basis, end_note = child_end
        else:
            succ = next_linehead[id(draft)]
            if succ is None:
                end_linehead, end_basis = all_lineheads[last_position], None
                end_note = (
                    "last cb:mulu type=\"科判\" node in the file (no following node to bound "
                    "it); root_text.end is the file's last own-canon line"
                )
            else:
                end_pos = max(position[start], position[succ] - 1)
                end_linehead, end_basis, end_note = all_lineheads[end_pos], "next-node", None
        root_text = {
            "start": start,
            "end": end_linehead,
            "basis": "cbeta-mulu",
            "end_basis": end_basis,
            "raw": "cb:mulu-preceding lb %s to %s" % (start, end_linehead),
        }
        draft["locations"]["root_text"] = root_text
        if end_note:
            draft["notes"].append(end_note)
        return end_linehead, end_basis, end_note

    for root in roots:
        finalize(root)

    return BuildResult(
        roots=roots,
        node_count=len(hits),
        jump_count=jump_count,
        merged_count=merged_count,
        count_mismatch=count_mismatch,
        counts_verified=counts_verified,
        max_source_level=max_level,
        unlevelled=unlevelled,
    )


# ---------------------------------------------------------------------------------- gold assembly


def _metadata(cbeta_id: str, short_id: str, scheme_id: str, xml_path, read: ReadResult, nodes: list) -> dict:
    title = read.info.get("title") or cbeta_id
    return common.zh_metadata(
        nodes,
        source_file=common.repo_relative(xml_path),
        source_sha256=common.sha256_file(xml_path),
        text_id=short_id,
        text_title_src=title,
        text_title_en="",
        author=read.author,
        source_language="lzh",
        format_note=FORMAT_NOTE % cbeta_id,
        origin_note=(
            "Every node is origin 'imported' from CBETA's own cb:mulu markup and unchecked "
            "against any secondary source (gold_status imported-unchecked); node_class is "
            "sutra-span on every node (self-outlining mode: this file's own cb:mulu markup "
            "states its outline over itself), with locations.root_text resolved directly from "
            "the markup (basis cbeta-mulu, the schema's own name for this case, R02 F28; see "
            "this module's docstring, 'node_class / outline_mode')."
        ),
        generated_by=GENERATED_BY,
        anomalies=(
            ["%d cb:mulu type=\"科判\" with no @level attribute (skipped, not counted as a node)"
             % read.unlevelled]
            if read.unlevelled
            else []
        ),
        source_document={
            "kind": "root-text",
            "text_id": cbeta_id,
            "title": "%s (%s%s)" % (title, cbeta_id, ", %s" % read.author if read.author else ""),
            "url": None,
            "notes": [
                "CBETA cb:mulu type=\"科判\" markup, whose markup it is is unrecorded in the file "
                "(R02 F28); this is the schema's own named example for source_document.kind "
                "'root-text' (\"a self-outlining treatise; CBETA cb:mulu type=科判 markup as in "
                "X11n0268\", context/baseline/outline-schema-zh.json)."
            ],
        },
        outline_mode="self-outlining",
        root_text_id=cbeta_id,
        commentary_id=None,
        scheme_id=scheme_id,
        seeded_by=None,
        gold_status="imported-unchecked",
        licence=dict(LICENCE),
        eval_only=False,
        cbeta_release=CBETA_RELEASE,
        display_label_rule=(
            "null on every node: the source's own ordinal (初/二/三…) is fused to the heading "
            "text with no delimiter and is not split out (see this module's docstring)"
        ),
    )


def build_gold(xml_path, cbeta_id: str, short_id: str, scheme_id: str = SCHEME_ID):
    """Read `xml_path`'s cb:mulu type="科判" tree and build its zh-kepan gold document.
    Returns (doc, BuildResult)."""
    read = read_mulu(xml_path)
    built = build_tree(read.hits, cbeta_id, read.all_lineheads, unlevelled=read.unlevelled)
    nodes = common.number_tree(built.roots)
    doc = {
        "metadata": _metadata(cbeta_id, short_id, scheme_id, xml_path, read, nodes),
        "nodes": nodes,
    }
    return doc, built


# ------------------------------------------------------------------------------------------ CLI


def _default_xml(cbeta_dir: Path, cbeta_id: str) -> Path:
    for base in (cbeta_dir, common.REPO_ROOT / "data" / "raw" / "cbeta" / "xml-p5"):
        p = base / FILES[cbeta_id][1]
        if p.exists():
            return p
    return cbeta_dir / FILES[cbeta_id][1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m chinese_workflow.eval.gold.cbeta_mulu",
        description=__doc__.split("\n\n")[0],
    )
    ap.add_argument("xml", nargs="?", help="a CBETA P5 file with cb:mulu type=\"科判\"; omit to "
                    "build all three of Task 7's files (X11n0268, P167n1573, D14n8842)")
    ap.add_argument("--scheme", default=SCHEME_ID, help="metadata.scheme_id (default: %s)" % SCHEME_ID)
    ap.add_argument("--out", type=Path, help="output outline.json path (single-file mode only)")
    ap.add_argument(
        "--cbeta-dir",
        type=Path,
        default=common.REPO_ROOT / "data" / "raw" / "cbeta" / "xml-p5",
        help="root of the xml-p5 clone (default: data/raw/cbeta/xml-p5)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=common.REPO_ROOT / "data" / "reference-outlines",
        help="root of data/reference-outlines (batch mode only)",
    )
    args = ap.parse_args(argv)

    def run_one(xml_path: Path, cbeta_id: str, short_id: str, out_path: Path) -> bool:
        if not xml_path.exists():
            print("SKIP  %s: not found (%s)" % (cbeta_id, xml_path))
            return True
        doc, built = build_gold(xml_path, cbeta_id, short_id, args.scheme)
        rep = common.validate(doc, common.repo_relative(out_path))
        ok = rep.passed()
        if ok:
            common.write_json(doc, out_path)
        print(
            "%s  %s  nodes=%d  max_source_level=%d  jumps=%d  merged=%d  count_mismatch=%d  "
            "counts_verified=%d  errors=%d  warnings=%d"
            % (
                "PASS" if ok else "FAIL",
                common.repo_relative(out_path),
                built.node_count,
                built.max_source_level,
                built.jump_count,
                built.merged_count,
                built.count_mismatch,
                built.counts_verified,
                len(rep.errors),
                len(rep.warnings),
            )
        )
        for f in rep.errors[:10]:
            print(f.render())
        return ok

    failed = 0
    if args.xml:
        xml_path = Path(args.xml)
        root_id = extract(xml_path).info.get("xml_id") if xml_path.exists() else None
        root_id = root_id or xml_path.stem
        short_id = FILES.get(root_id, (root_id, None))[0]
        out_path = args.out or (args.out_dir / short_id / args.scheme / "outline.json")
        failed += not run_one(xml_path, root_id, short_id, out_path)
    else:
        for cbeta_id, (short_id, _rel) in FILES.items():
            xml_path = _default_xml(args.cbeta_dir, cbeta_id)
            out_path = args.out_dir / short_id / args.scheme / "outline.json"
            failed += not run_one(xml_path, cbeta_id, short_id, out_path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
