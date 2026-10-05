"""chinese_workflow.ingest.text — one ingested text in memory: the object every later stage reads.

InputText bundles a CBETA file's line records (chinese_workflow.ingest.lines), optionally restricted to an
inclusive span of lineheads, with a TextIndex over them (the reading text, CBETA's characters and
punctuation unchanged; global offsets = offsets into InputText.text) and the file's header info.

    load_input_text("T34n1723", span=("T34n1723_p0850a19", "T34n1723_p0850b19"), role="commentary")
    load_input_text(path_to_xml)                     # a fixture or any local P5 file

A span is (first linehead, last linehead), both inclusive. Offsets in every artefact (outlined-text.json,
sentences.json, chunks.json) index InputText.text of the *target* text over the run's span.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..common.jsonio import sha256_text
from ..common.lineheads import LineOrder, strip_offset
from ..common.paths import cbeta_xml_path
from .lines import TextIndex, build_index, extract


class CbetaFileMissing(FileNotFoundError):
    """A CBETA file id with no local XML (data/raw/ is fetched, not committed). Still a FileNotFoundError;
    the runner reports it in one line instead of a traceback."""


@dataclass
class InputText:
    text_id: str  # CBETA file id, e.g. 'T34n1723'
    role: str | None  # 'root' | 'commentary' | None
    info: dict  # header info of ingest.lines (title, punctuation, header_date, ...)
    lines: list  # line records of the span, document order
    all_lineheads: list  # every linehead of the file, document order (for LineOrder / distances)
    index: TextIndex = field(repr=False)
    source_path: str = ""

    @property
    def text(self) -> str:
        return self.index.text

    @property
    def sha256(self) -> str:
        return sha256_text(self.index.text)

    @property
    def order(self) -> LineOrder:
        return LineOrder(self.all_lineheads)

    @property
    def first_linehead(self) -> str | None:
        return self.lines[0]["linehead"] if self.lines else None

    @property
    def last_linehead(self) -> str | None:
        return self.lines[-1]["linehead"] if self.lines else None

    def record(self, linehead: str) -> dict:
        lh = strip_offset(linehead)
        for rec in self.lines:
            if rec["linehead"] == lh:
                return rec
        raise KeyError(linehead)

    def offset(self, ref: str) -> int:
        """Global offset of a locator 'T34n1723_p0850b03' or 'T34n1723_p0850b03:9' in self.text; an
        offset past the line's length is clamped to the line end."""
        lh, _, off = ref.partition(":")
        i = self.index._pos[lh]
        n = int(off) if off else 0
        return self.index.starts[i] + min(n, self.index.lengths[i])

    def locate(self, global_offset: int) -> str:
        """Global offset -> 'linehead:offset' (bare linehead when the offset is 0)."""
        lh, off = self.index.locate(global_offset)
        return lh if off == 0 else "%s:%d" % (lh, off)

    def contains(self, ref: str | None) -> bool:
        return ref is not None and strip_offset(ref) in self.index._pos


def load_input_text(source, span: tuple | None = None, role: str | None = None) -> InputText:
    """Load a CBETA file by file id (resolved under data/raw/cbeta/) or by path, restricted to `span`
    = (first, last) lineheads inclusive, or the whole file."""
    path = Path(source)
    if not path.suffix:
        found = cbeta_xml_path(str(source))
        if found is None:
            raise CbetaFileMissing(
                "no local CBETA XML for %s. Fetch it from the repository root with "
                "`bash scripts/fetch_cbeta.sh %s` if it is one "
                "of the works that script pins (`--list`); any other CBETA file comes from the "
                "whole-corpus clone, `bash scripts/fetch_cbeta_xml_p5.sh`" % (source, source))
        path = found
    ex = extract(path)
    all_lh = [rec["linehead"] for rec in ex.lines]
    if span:
        first, last = strip_offset(span[0]), strip_offset(span[1])
        i, j = all_lh.index(first), all_lh.index(last)
        lines = ex.lines[i : j + 1]
    else:
        lines = ex.lines
    return InputText(
        text_id=ex.info.get("xml_id") or path.stem,
        role=role,
        info=ex.info,
        lines=lines,
        all_lineheads=all_lh,
        index=build_index(lines),
        source_path=str(path),
    )
