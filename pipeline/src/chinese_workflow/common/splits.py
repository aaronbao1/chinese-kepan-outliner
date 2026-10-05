"""The split guard (docs/outliner-design.md §3; plan Appendix C rule 5; data/EVAL-SETS.md).

data/eval-sets.json is the only split source. The guard refuses, unless a frozen outliner is named:
  * reading any line of a test or reserve span of a split text (T34n1718, T34n1723; lines no span holds
    are reserve, EVAL-SETS rule 1);
  * using an out-of-domain gold as a scoring target (every OOD gold is an OOD test until the registry-roles
    decision, plan Appendix H item 8b); OOD golds are never inputs or prompt material, frozen or not.
Structure-only reads of a whole file (tier 1: cb:mulu / head / juan markup) are allowed and recorded.

The lookup restates chinese_workflow.eval.registry.split_of (stages may not import eval); a test checks
that the two agree on every span boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .jsonio import read_json
from .paths import REGISTRY

BLOCKED = ("test", "reserve")


class SplitViolation(RuntimeError):
    """A read or a score the split discipline forbids without --frozen."""


def load_registry(path=REGISTRY) -> dict:
    return read_json(path)


def split_file_ids(registry: dict) -> dict:
    """{file id: text id} of the split texts, e.g. {'T34n1718': 'T1718', 'T34n1723': 'T1723'}."""
    return {spec["file"]: text for text, spec in registry["splits"]["texts"].items()}


def split_of_line(registry: dict, linehead: str) -> str:
    """The split of one linehead: 'dev' | 'validation' | 'test' | 'reserve' for lines of a split text,
    'unsplit' for any other file."""
    fid = linehead.split("_p", 1)[0]
    text = split_file_ids(registry).get(fid)
    if text is None:
        return "unsplit"
    spec = registry["splits"]["texts"][text]
    lh = linehead.split(":", 1)[0]
    for span in spec["spans"]:
        if span["start"] <= lh and (span["end"] is None or lh < span["end"]):
            return span["split"]
    return spec["unlisted"]


def named_span(registry: dict, file_id: str, split: str) -> list:
    """[(start, end_exclusive)] of the spans of one split in one split file (e.g. the dev span of T34n1723)."""
    text = split_file_ids(registry).get(file_id)
    if text is None:
        return []
    return [(s["start"], s["end"]) for s in registry["splits"]["texts"][text]["spans"]
            if s["split"] == split]


def is_ood(ds: dict) -> bool:
    """An out-of-domain gold (registry field split == 'out-of-domain')."""
    return ds.get("split") == "out-of-domain"


def is_eval_only(ds: dict) -> bool:
    """An eval-only dataset: its file lives under data/raw/ (gitignored; the sdp golds and derivatives)."""
    return str(ds.get("path", "")).startswith("data/raw/")


@dataclass
class SplitGuard:
    """Checks and records every span a run reads. frozen = the tag of a frozen outliner, or None."""

    frozen: str | None = None
    registry: dict = field(default_factory=load_registry)
    report: list = field(default_factory=list)

    def check_lines(self, lineheads, purpose: str = "read") -> set:
        """Check the lines a stage is about to read (an iterable of lineheads of one file). Returns the
        set of splits touched; raises SplitViolation on test/reserve lines unless frozen."""
        lineheads = list(lineheads)
        splits = {split_of_line(self.registry, lh) for lh in lineheads}
        blocked = sorted(splits & set(BLOCKED))
        entry = {"purpose": purpose, "splits": sorted(splits), "frozen": self.frozen}
        if lineheads:
            entry["first"], entry["last"] = lineheads[0], lineheads[-1]
        self.report.append(entry)
        if blocked and not self.frozen:
            raise SplitViolation(
                "%s touches %s lines (%s..%s); pass --frozen <tag> to read them with a frozen outliner"
                % (purpose, "/".join(blocked), entry.get("first"), entry.get("last"))
            )
        return splits

    def check_structure(self, file_id: str) -> None:
        """Record a structure-only read (cb:mulu / head / juan markup) of a whole file; always allowed."""
        self.report.append({"purpose": "structure-only", "file": file_id, "frozen": self.frozen})

    def check_gold(self, dataset_id: str, as_input: bool = False) -> dict:
        """The registry entry of a gold about to be scored (or, as_input=True, read as input material).
        OOD golds: refused as input always, as a scoring target unless frozen. Eval-only golds: refused as
        input always."""
        ds = next((d for d in self.registry["datasets"] if d["id"] == dataset_id), None)
        if ds is None:
            raise KeyError(dataset_id)
        ood = is_ood(ds)
        self.report.append({"purpose": "input" if as_input else "score", "dataset": dataset_id,
                            "ood": ood, "frozen": self.frozen})
        if as_input and (ood or is_eval_only(ds)):
            raise SplitViolation("%s may not be used as input or prompt material" % dataset_id)
        if ood and not self.frozen:
            raise SplitViolation(
                "%s is an out-of-domain gold (an OOD test until the registry-roles decision); "
                "score it only with --frozen <tag>" % dataset_id
            )
        return ds
