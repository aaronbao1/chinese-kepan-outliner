"""CBETA lineheads: 'T34n1723_p0850b01', optionally with a character offset ':12'.

Grammar as in context/baseline/outline-schema-zh.json (cbeta_ref) and scripts/validate_outline.py
(CBETA_REF_RE). String comparison of two lineheads of one file gives document order inside T34n1718 and
T34n1723 (checked by tests/unit/test_kepan_cases.py), but not in every file (T09n0262's 附文 lines run out
of order), so code that needs document order uses LineOrder, built from the file's own line list.
"""

from __future__ import annotations

import re
from typing import Iterable, NamedTuple

REF_RE = re.compile(
    r"^(?P<file>[A-Z]+[0-9]+n[0-9A-Za-z]+)_p(?P<page>[0-9a-z][0-9]{3})(?P<reg>[a-z])(?P<line>[0-9]{2})"
    r"(?::(?P<off>[0-9]+))?\Z"
)


class Ref(NamedTuple):
    file: str
    page: str
    register: str
    line: int
    offset: int | None

    @property
    def linehead(self) -> str:
        return "%s_p%s%s%02d" % (self.file, self.page, self.register, self.line)


def parse(ref: str) -> Ref:
    m = REF_RE.match(ref)
    if not m:
        raise ValueError("not a CBETA linehead: %r" % ref)
    off = m.group("off")
    return Ref(m.group("file"), m.group("page"), m.group("reg"), int(m.group("line")),
               int(off) if off is not None else None)


def is_ref(ref) -> bool:
    return isinstance(ref, str) and REF_RE.match(ref) is not None


def strip_offset(ref: str | None) -> str | None:
    """'T34n1723_p0850b01:12' -> 'T34n1723_p0850b01' (None stays None)."""
    if ref is None:
        return None
    return ref.split(":", 1)[0]


def file_id(ref: str) -> str:
    """'T34n1723_p0850b01' -> 'T34n1723'."""
    return ref.split("_p", 1)[0]


def with_offset(linehead: str, offset: int | None) -> str:
    return linehead if not offset else "%s:%d" % (linehead, offset)


class LineOrder:
    """Document order of one file's lines: index(linehead), distance(a, b) in lines, and range queries.

    Built from the linehead list of chinese_workflow.ingest.lines (the file's own edition, in document
    order)."""

    def __init__(self, lineheads: Iterable[str]):
        self.lineheads = list(lineheads)
        self._pos = {lh: i for i, lh in enumerate(self.lineheads)}

    def __contains__(self, ref) -> bool:
        return strip_offset(ref) in self._pos

    def index(self, ref: str) -> int:
        return self._pos[strip_offset(ref)]

    def distance(self, a: str, b: str) -> int:
        """Absolute distance in lines between two lineheads of this file."""
        return abs(self.index(a) - self.index(b))

    def between(self, start: str, end: str) -> list:
        """Lineheads from start through end, inclusive."""
        i, j = self.index(start), self.index(end)
        return self.lineheads[i : j + 1]

    def prev(self, ref: str) -> str | None:
        i = self.index(ref)
        return self.lineheads[i - 1] if i > 0 else None

    def next(self, ref: str) -> str | None:
        i = self.index(ref)
        return self.lineheads[i + 1] if i + 1 < len(self.lineheads) else None
