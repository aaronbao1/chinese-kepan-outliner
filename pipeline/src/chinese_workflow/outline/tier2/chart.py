"""Charts (科文): kēpàn printed one item per line (R01 chart-note; X0231 華嚴經疏科文, X0584 法華三大部科文).

Input : line records (ingest.lines) with their inline notes, or a snippet with line starts and note spans.
Output: chart items [{start, end, linehead, ordinal, label, count, incipit}] and, from them, a tree.

A chart line is ordinal + label + an inline note: the note is the child count on a non-leaf (三, 二) and
the incipit of the root text on a leaf (大方, 至聖); X0584 leaves carry no note. A label may open with a
lemma incipit + 下 (文云下正明今經, 所言下釋題), removed by the label rule (README label rule 2). The tree
is rebuilt with a stack: a line with a count takes the next lines as its children until that many are
placed. The heading line of a chart section (釋斯鈔序啟以三門 + 三) has no ordinal.
"""

from __future__ import annotations

import re

from .formulae import parse_num

ORD_RE = re.compile(r"^(?:第?[一二三四五六七八九十]{1,3}(?:者)?|初|次|後|先|中|前)(?=[^一二三四五六七八九十])")
INCIPIT_XIA_RE = re.compile(r"^[^\s下]{1,4}(?:以下|已下|下)(?=..)")
MAX_LINE = 36


def chart_items(text: str, lines: list, notes: list) -> list:
    """lines: [(start, end, linehead)] of the text; notes: [(start, end)] inline-note spans (global).
    One item per line that has a label; the notes inside the line become its count or incipit."""
    out = []
    for start, end, lh in lines:
        own = [(a, b) for a, b in notes if start <= a < end]
        body = "".join(text[i] for i in range(start, end) if not any(a <= i < b for a, b in own))
        body = body.strip("○　 ")
        if not body or len(body) > MAX_LINE:
            continue
        note = "".join(text[a:b] for a, b in own).strip("○　 ")
        count = parse_num(note) if note else None
        m = ORD_RE.match(body)
        ordinal = m.group(0) if m else ""
        label = body[len(ordinal):].lstrip("、，,：: ")
        m = INCIPIT_XIA_RE.match(label)
        incipit = None
        if m and ordinal:
            incipit = m.group(0)
            label = label[m.end():]
        if count is None and note:
            incipit = note
        out.append({"start": start, "end": end, "linehead": lh, "ordinal": ordinal, "label": label,
                    "count": count if count and count >= 2 else None, "incipit": incipit})
    return out


def is_chart(items: list, n_lines: int) -> bool:
    """A text (or span) is a chart when most of its lines are chart items with an ordinal or a count."""
    marked = [it for it in items if it["ordinal"] or it["count"]]
    return len(marked) >= 5 and len(marked) >= 0.5 * max(n_lines, 1)


def chart_tree(items: list) -> list:
    """[{item, children}] from the items in order (stack of open counts)."""
    roots: list = []
    stack: list = []  # [node, remaining]
    for it in items:
        if not it["ordinal"] and not it["count"]:
            continue
        node = {"item": it, "children": []}
        while stack and stack[-1][1] <= 0:
            stack.pop()
        if stack and it["ordinal"]:
            stack[-1][0]["children"].append(node)
            stack[-1][1] -= 1
        else:
            roots.append(node)
            stack = []
        if it["count"]:
            stack.append([node, it["count"]])
    return roots
