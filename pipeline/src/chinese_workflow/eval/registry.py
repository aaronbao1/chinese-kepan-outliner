"""chinese_workflow.eval.registry — the eval-set registry data/eval-sets.json: read access for the
scorer (split lookup, dataset lookup, served T1718 卷-halves, scoring scope) and the recomputation of its
computed parts and of the tables in its guide data/EVAL-SETS.md.

Input : data/eval-sets.json (hand-written registry: splits, datasets with path / format / split scope)
        + every file a dataset names (gold outlines under data/reference-outlines/ and data/raw/dila-sdp/gold/,
        the sdp heading check and crosswalk, tests/fixtures/ cases and excerpts)
        + data/EVAL-SETS.md (hand-written prose with marker blocks `<!-- eval-sets:NAME begin -->` …
        `<!-- eval-sets:NAME end -->` for NAME in datasets, split-spans, splits, juan-halves, heading-check).
Output: main(["--write"]) rewrites data/eval-sets.json with each dataset's `file_metadata` (mirrored from
                 the gold's metadata) and `counts` (computed from the file) replaced — a dataset whose file is
                 absent (eval-only files under data/raw/ on a fresh checkout) keeps its recorded blocks — and
                 the computed part of a dataset's `scoring_scope` (`served_juan_halves`, derived from
                 splits.texts.<text>.juan_halves); it rewrites the marker blocks of data/EVAL-SETS.md as tables
                 rendered from the registry (text outside the markers is left alone).
        main(["--check"]) (default) writes nothing; prints one line per dataset (ok / DIFF / absent) and one
                 for the guide's tables, and exits 1 if anything present differs.
        Standard library only (scripts/eval_sets.py runs it under any python3). Deterministic: the same files
        give the same bytes. CLI: python3 scripts/eval_sets.py [--check | --write] [--registry PATH]
        [--guide PATH], or python -m chinese_workflow.eval.registry.

Read access (what a scorer calls; final review 2026-09-22, R1/R2):
  load_registry(path=REGISTRY)           the registry as a dict
  dataset(registry, dataset_id)          one dataset entry (KeyError if unknown)
  split_spans(registry, text)            [(split, start, end)] of a split text (end exclusive, None = end of file)
  split_of(registry, text, linehead)     the split of a linehead: the first listed span holding it, else
                                         `unlisted` (reserve)
  served_juan_halves(registry, text)     [{half, start, end}] of the 卷-halves sdp serves (end exclusive);
                                         a dataset's scoring_scope may open the first at the file start
  in_scoring_scope(registry, dataset_id, linehead)
                                         whether a predicted node whose key locator is `linehead` is in the
                                         dataset's machine-readable scoring scope (a dataset without
                                         `scoring_scope`: always True)

Counts per format (all derived from the file, never typed):
  zh-kepan-outline  nodes, max_depth, leaves, node_class / origin / flags tallies, how many nodes have
                    commentary.explained and root_text, root_text basis / end_basis tallies, and — when the
                    dataset has a split_scope — nodes and flags per split of the scoped locator (the split of
                    a linehead is looked up in the registry's own spans; "no locator" when it is null); for
                    golds with metadata.coverage_spans, the node count of each covered subtree.
  heading-check     class tallies overall, per window kind, per split bucket (own window in dev / validation /
                    test / outside every split; inherited windows and no-text nodes as their own buckets, as
                    HEADING-CHECK.md reports them), and the noise-baseline table read from HEADING-CHECK.md.
  crosswalk-tsv     rows, status and corroborated tallies.
  cases-jsonl       cases, kind / formula tallies, cases per source text.
  tei-xml-excerpt   bytes, sha256.
  aligned-text      lines of chinese.txt, first / last line id, lines per split of T1723, tibetan.txt lines.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]  # pipeline/src/chinese_workflow/eval/registry.py
REGISTRY = REPO / "data" / "eval-sets.json"
GUIDE = REPO / "data" / "EVAL-SETS.md"
NO_LOCATOR = "no locator"
METADATA_KEYS = (
    "text_id",
    "scheme_id",
    "outline_mode",
    "root_text_id",
    "commentary_id",
    "gold_status",
    "seeded_by",
    "eval_only",
    "cbeta_release",
)


# --------------------------------------------------------------------------------- registry, splits


def load_registry(path: Path = REGISTRY) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def split_texts(registry: dict) -> dict:
    return registry["splits"]["texts"]


def split_of(registry: dict, text: str, linehead: str) -> str:
    """Split of a linehead of a split text (T1718 / T1723): the first listed span holding it, else `unlisted`."""
    spec = split_texts(registry)[text]
    for span in spec["spans"]:
        if span["start"] <= linehead and (span["end"] is None or linehead < span["end"]):
            return span["split"]
    return spec["unlisted"]


def text_of_linehead(registry: dict, linehead: str) -> str | None:
    file_id = linehead.split("_p")[0]
    for text, spec in split_texts(registry).items():
        if spec["file"] == file_id:
            return text
    return None


def dataset(registry: dict, dataset_id: str) -> dict:
    """The registry entry of one dataset, by id (KeyError if it is not registered)."""
    for ds in registry["datasets"]:
        if ds["id"] == dataset_id:
            return ds
    raise KeyError(dataset_id)


def split_spans(registry: dict, text: str) -> list:
    """[(split, start, end)] of a split text in registry order; start inclusive, end exclusive, end None
    = to the end of the file. Lines no span holds are `unlisted` (reserve)."""
    return [(s["split"], s["start"], s["end"]) for s in split_texts(registry)[text]["spans"]]


def served_juan_halves(registry: dict, text: str = "T1718") -> list:
    """[{half, start, end}] of the 卷-halves whose pages sdp serves, in file order, from
    splits.texts.<text>.juan_halves; start inclusive, end exclusive (the next half's start; None for the
    file's last half)."""
    halves = split_texts(registry)[text]["juan_halves"]
    starts = list(halves["starts"].items())
    out = []
    for i, (half, start) in enumerate(starts):
        if half in halves["served_by_sdp"]:
            end = starts[i + 1][1] if i + 1 < len(starts) else None
            out.append({"half": half, "start": start, "end": end})
    return out


def computed_scoring_scope(registry: dict, ds: dict) -> dict | None:
    """A dataset's `scoring_scope` with its computed part filled in, or None when it declares none.
    restrict_to "served_juan_halves" -> served_juan_halves = the served 卷-halves of scope.text."""
    scope = ds.get("scoring_scope")
    if not scope:
        return None
    if scope.get("restrict_to") != "served_juan_halves":
        raise ValueError(
            f"{ds['id']}: unknown scoring_scope.restrict_to {scope.get('restrict_to')!r}"
        )
    served = served_juan_halves(registry, scope["text"])
    first = next(iter(split_texts(registry)[scope["text"]]["juan_halves"]["starts"]))
    if scope.get("first_half_from_file_start") and served and served[0]["half"] == first:
        # the first half's page also carries the front matter before its 卷 mulu
        served[0] = {**served[0], "start": None}
    return {**scope, "served_juan_halves": served}


def in_scoring_scope(registry: dict, dataset_id: str, linehead: str | None) -> bool:
    """Whether a predicted node whose key locator (the dataset's scoring_scope.key) is `linehead` lies in
    the dataset's machine-readable scoring scope. A dataset without `scoring_scope` has no such
    restriction (True; coverage_spans and the rules of data/EVAL-SETS.md item 5 still apply). With one,
    a node without that locator, or with a line of another file, is out of scope."""
    scope = dataset(registry, dataset_id).get("scoring_scope")
    if not scope:
        return True
    if linehead is None:
        return False
    if linehead.split("_p")[0] != split_texts(registry)[scope["text"]]["file"]:
        return False
    return any(
        (h["start"] is None or h["start"] <= linehead) and (h["end"] is None or linehead < h["end"])
        for h in scope["served_juan_halves"]
    )


# ----------------------------------------------------------------------------------------- counters


def _tally(values) -> dict:
    """Counter as a key-sorted dict; a None value is counted under "null"."""
    return dict(sorted(Counter("null" if v is None else v for v in values).items()))


def _explained(node: dict):
    loc = node.get("locations") or {}
    return (
        (loc.get("commentary") or {}).get("explained")
        if loc.get("scheme") == "cbeta-kepan"
        else None
    )


def _root_text(node: dict):
    loc = node.get("locations") or {}
    return loc.get("root_text") if loc.get("scheme") == "cbeta-kepan" else None


def _scoped_locator(node: dict, by: str):
    if by.startswith("locations.commentary.explained"):
        return _explained(node)
    if by.startswith("locations.root_text.start"):
        rt = _root_text(node)
        return rt.get("start") if rt else None
    raise ValueError(f"unknown split_scope.by: {by}")


def file_metadata(doc: dict) -> dict:
    meta = doc.get("metadata", {})
    out = {k: meta.get(k) for k in METADATA_KEYS}
    out["licence_id"] = (meta.get("licence") or {}).get("id")
    out["outline_profile"] = meta.get("outline_profile")
    return out


def outline_counts(doc: dict, registry: dict, split_scope: dict | None) -> dict:
    nodes = doc["nodes"]
    parents = {n["parent_id"] for n in nodes if n.get("parent_id")}
    roots = [_root_text(n) for n in nodes]
    counts = {
        "nodes": len(nodes),
        "max_depth": max((n["level"] for n in nodes), default=0),
        "leaves": sum(1 for n in nodes if n["id"] not in parents),
        "node_class": _tally(n.get("node_class") for n in nodes),
        "origin": _tally(n.get("origin") for n in nodes),
        "flags": _tally(f for n in nodes for f in n.get("flags") or []),
        "with_commentary_explained": sum(1 for n in nodes if _explained(n)),
        "with_root_text": sum(1 for r in roots if r),
        "root_text_basis": _tally(r.get("basis") for r in roots if r),
        "root_text_end_basis": _tally(r.get("end_basis") for r in roots if r),
    }
    if split_scope:
        by_split: dict = {}
        for n in nodes:
            lh = _scoped_locator(n, split_scope["by"])
            if lh is None:
                key = NO_LOCATOR
            elif text_of_linehead(registry, lh) != split_scope["text"]:
                raise ValueError(
                    f"{n['id']}: {lh} is not a line of split text {split_scope['text']}"
                )
            else:
                key = split_of(registry, split_scope["text"], lh)
            slot = by_split.setdefault(key, {"nodes": 0, "flags": Counter()})
            slot["nodes"] += 1
            slot["flags"].update(n.get("flags") or [])
        counts["by_split"] = {
            k: {"nodes": v["nodes"], "flags": dict(sorted(v["flags"].items()))}
            for k, v in sorted(by_split.items())
        }
    spans = doc.get("metadata", {}).get("coverage_spans")
    if spans:
        out = []
        for entry in spans:
            nid = entry.get("node_id")
            if nid is None:
                sub = [
                    n
                    for n in nodes
                    if entry.get("max_level") is None or n["level"] <= entry["max_level"]
                ]
            else:
                sub = [n for n in nodes if n["id"] == nid or n["id"].startswith(nid + ".")]
            out.append(
                {
                    "node_id": nid,
                    "heading_src": entry.get("heading_src"),
                    "max_level": entry.get("max_level"),
                    "nodes": len(sub),
                }
            )
        counts["coverage_spans"] = out
    return counts


def _noise_table(md_path: Path) -> dict:
    """The noise-baseline table of HEADING-CHECK.md (written by eval.gold.sdp_check.write_report)."""
    text = md_path.read_text(encoding="utf-8")
    i = text.find("**Noise baseline**")
    if i < 0:
        raise ValueError(f"{md_path}: no noise-baseline section")
    rows = re.findall(r"^\| (verbatim|partial|absent) \| (\d+) \| ", text[i:], flags=re.M)
    table = {cls: int(n) for cls, n in rows[:3]}
    if len(table) != 3:
        raise ValueError(f"{md_path}: noise-baseline table not found")
    return table


def heading_check_counts(tsv: Path, md: Path) -> dict:
    with open(tsv, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    def bucket(r: dict) -> str:
        if r["window_kind"] == "inherited":
            return "inherited window (location unknown)"
        if r["window_kind"] == "no-text":
            return "no-text"
        return (
            f"own window, {r['split']}"
            if r["split"]
            else "own window, outside every split (mostly reserve)"
        )

    per_bucket: dict = {}
    for r in rows:
        per_bucket.setdefault(bucket(r), Counter())[r["class"]] += 1
    return {
        "nodes": len(rows),
        "class": _tally(r["class"] for r in rows),
        "window_kind": _tally(r["window_kind"] for r in rows),
        "by_split": {k: dict(sorted(v.items())) for k, v in sorted(per_bucket.items())},
        "noise_baseline": _noise_table(md),
    }


def crosswalk_counts(tsv: Path) -> dict:
    with open(tsv, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    return {
        "rows": len(rows),
        "status": _tally(re.sub(r"^gap-.*", "gap", r["status"]) for r in rows),
        "corroborated": _tally(r["corroborated"] for r in rows),
        "t0262_nodes": len({r["t0262_sdp_id"] for r in rows}),
    }


def cases_counts(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        cases = [json.loads(line) for line in fh if line.strip()]
    return {
        "cases": len(cases),
        "kind": _tally(c["kind"] for c in cases),
        "formula_slugs": len({c["formula"] for c in cases if c["formula"]}),
        "source": _tally(c["source"] for c in cases),
    }


def bytes_counts(path: Path) -> dict:
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def aligned_text_counts(chinese: Path, registry: dict) -> dict:
    ids = [
        ln.split("\t", 1)[0]
        for ln in chinese.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    file_id = split_texts(registry)["T1723"]["file"]
    tibetan = chinese.with_name("tibetan.txt")
    return {
        "chinese_lines": len(ids),
        "first": ids[0],
        "last": ids[-1],
        "chinese_lines_by_split": _tally(
            split_of(registry, "T1723", f"{file_id}_p{i}") for i in ids
        ),
        "tibetan_lines": len(tibetan.read_text(encoding="utf-8").splitlines())
        if tibetan.exists()
        else None,
    }


def compute(dataset: dict, registry: dict, repo: Path = REPO) -> dict | None:
    """{'file_metadata': ..., 'counts': ...} for a dataset whose files are present, else None."""
    path = repo / dataset["path"]
    extra = [repo / p for p in dataset.get("extra_paths", [])]
    fmt = dataset["format"]
    if not path.exists() or (fmt == "heading-check" and not all(p.exists() for p in extra)):
        return None
    if fmt == "zh-kepan-outline":
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        return {
            "file_metadata": file_metadata(doc),
            "counts": outline_counts(doc, registry, dataset.get("split_scope")),
        }
    if fmt == "heading-check":
        return {"counts": heading_check_counts(path, extra[0])}
    if fmt == "crosswalk-tsv":
        return {"counts": crosswalk_counts(path)}
    if fmt == "cases-jsonl":
        return {"counts": cases_counts(path)}
    if fmt == "tei-xml-excerpt":
        return {"counts": bytes_counts(path)}
    if fmt == "aligned-text":
        return {"counts": aligned_text_counts(path, registry)}
    raise ValueError(f"{dataset['id']}: unknown format {fmt}")


def dump(registry: dict) -> str:
    return json.dumps(registry, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------------- tables in data/EVAL-SETS.md

BLOCK_RE = re.compile(
    r"(<!-- eval-sets:(?P<name>[a-z-]+) begin -->\n)(?P<body>.*?)(<!-- eval-sets:(?P=name) end -->)",
    re.S,
)
SPLIT_ORDER = ("dev", "validation", "test", "reserve", NO_LOCATOR)
CLASS_ORDER = ("verbatim", "partial", "absent", "no-text")


def _n(x) -> str:
    return f"{x:,}" if isinstance(x, int) else ("—" if x is None else str(x))


def _size(ds: dict) -> str:
    c = ds.get("counts") or {}
    fmt = ds["format"]
    if fmt == "zh-kepan-outline":
        return f"{_n(c['nodes'])} nodes, depth {c['max_depth']}, {_n(c['leaves'])} leaves"
    if fmt == "heading-check":
        return f"{_n(c['nodes'])} nodes checked"
    if fmt == "crosswalk-tsv":
        return f"{_n(c['rows'])} links"
    if fmt == "cases-jsonl":
        return f"{_n(c['cases'])} cases ({', '.join(f'{k} {v}' for k, v in c['kind'].items())})"
    if fmt == "tei-xml-excerpt":
        return f"{_n(c['bytes'])} bytes"
    if fmt == "aligned-text":
        return f"{_n(c['chinese_lines'])} zh lines + {_n(c['tibetan_lines'])} bo lines"
    return "—"


def _licence(ds: dict) -> str:
    meta = ds.get("file_metadata")
    lid = meta["licence_id"] if meta else ds.get("licence_id")
    return lid or "none (eval-only)"


def _datasets_table(registry: dict) -> str:
    rows = [
        "| Dataset | File | In git | Anchors | Licence | gold_status | Size | Split | Used by |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for ds in registry["datasets"]:
        meta = ds.get("file_metadata") or {}
        scope = ds.get("split_scope")
        if scope:
            split = f"per node, by {scope['by'].split(' ')[0]} in {scope['text']}"
        elif ds.get("split_follows"):
            split = f"as `{ds['split_follows']}`"
        else:
            split = ds.get("split", "—")
        rows.append(
            "| "
            + " | ".join(
                [
                    f"`{ds['id']}`",
                    f"`{ds['path']}`",
                    "yes" if ds["committed"] else "no (gitignored)",
                    ds.get("anchors", "—"),
                    _licence(ds),
                    meta.get("gold_status") or "—",
                    _size(ds),
                    split,
                    ", ".join(e["id"] for e in ds.get("experiments", [])) or "—",
                ]
            )
            + " |"
        )
    return "\n".join(rows) + "\n"


def _split_spans_table(registry: dict) -> str:
    rows = [
        "| Text (file) | Split | Start (inclusive) | End (exclusive) | What |",
        "|---|---|---|---|---|",
    ]
    for text, spec in split_texts(registry).items():
        for span in spec["spans"]:
            end = f"`{span['end']}`" if span["end"] else "end of file"
            rows.append(
                f"| {text} (`{spec['file']}`) | **{span['split']}** | `{span['start']}` | {end} | "
                f"{span['label']} |"
            )
        rows.append(
            f"| {text} (`{spec['file']}`) | {spec['unlisted']} | every line no span above holds | | |"
        )
    return "\n".join(rows) + "\n"


def _splits_table(registry: dict) -> str:
    rows = [
        "| Gold | Split text, locator | " + " | ".join(SPLIT_ORDER) + " |",
        "|---|---|" + "---|" * len(SPLIT_ORDER),
    ]
    for ds in registry["datasets"]:
        scope = ds.get("split_scope")
        if not scope or not ds.get("counts"):
            continue
        by = ds["counts"]["by_split"]
        cells = []
        for key in SPLIT_ORDER:
            slot = by.get(key)
            if slot is None:
                cells.append("0")
                continue
            flags = ", ".join(f"{f} {_n(k)}" for f, k in slot["flags"].items())
            cells.append(_n(slot["nodes"]) + (f" ({flags})" if flags else ""))
        rows.append(
            f"| `{ds['id']}` | {scope['text']}, {scope['by'].split(' ')[0]} | "
            + " | ".join(cells)
            + " |"
        )
    return "\n".join(rows) + "\n"


def _juan_table(registry: dict) -> str:
    spec = split_texts(registry)["T1718"]
    halves = spec["juan_halves"]
    starts = list(halves["starts"].items())
    rows = ["| 卷-half | First line | Served by sdp | Split(s) it overlaps |", "|---|---|---|---|"]
    for i, (half, start) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else None
        hit = []
        for span in spec["spans"]:
            s_end = span["end"]
            if (end is None or span["start"] < end) and (s_end is None or start < s_end):
                hit.append(span["split"])
        if start < min(s["start"] for s in spec["spans"]):  # begins before every listed span
            hit.insert(0, spec["unlisted"])
        rows.append(
            f"| {half} | `{start}` | {'yes' if half in halves['served_by_sdp'] else '**no**'} | "
            f"{', '.join(dict.fromkeys(hit))} |"
        )
    return "\n".join(rows) + "\n"


def _heading_check_table(registry: dict) -> str:
    ds = next(d for d in registry["datasets"] if d["format"] == "heading-check")
    c = ds["counts"]
    rows = [
        "| Nodes | " + " | ".join(CLASS_ORDER) + " | total |",
        "|---|" + "---|" * (len(CLASS_ORDER) + 1),
    ]

    def row(label: str, tally: dict) -> str:
        return (
            f"| {label} | "
            + " | ".join(_n(tally.get(k, 0)) for k in CLASS_ORDER)
            + f" | {_n(sum(tally.values()))} |"
        )

    rows.append(row("**all**", c["class"]))
    for key, tally in c["by_split"].items():
        rows.append(row(key, tally))
    noise = c["noise_baseline"]
    rows.append(
        f"| noise baseline (random other heading, own windows, 3 reshuffles) | {_n(noise['verbatim'])} | "
        f"{_n(noise['partial'])} | {_n(noise['absent'])} | — | {_n(sum(noise.values()))} |"
    )
    return "\n".join(rows) + "\n"


def render_blocks(registry: dict) -> dict:
    """The generated tables of data/EVAL-SETS.md, by marker name."""
    return {
        "datasets": _datasets_table(registry),
        "split-spans": _split_spans_table(registry),
        "splits": _splits_table(registry),
        "juan-halves": _juan_table(registry),
        "heading-check": _heading_check_table(registry),
    }


def guide_blocks(text: str) -> dict:
    return {m.group("name"): m.group("body") for m in BLOCK_RE.finditer(text)}


def apply_blocks(text: str, blocks: dict) -> str:
    missing = set(blocks) - set(guide_blocks(text))
    if missing:
        raise ValueError(f"data/EVAL-SETS.md lacks the marker block(s) {sorted(missing)}")
    return BLOCK_RE.sub(lambda m: m.group(1) + blocks[m.group("name")] + m.group(4), text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="compare only (default)")
    mode.add_argument("--write", action="store_true", help="rewrite the computed blocks in place")
    ap.add_argument("--registry", type=Path, default=REGISTRY)
    ap.add_argument("--guide", type=Path, default=GUIDE)
    args = ap.parse_args(argv)

    registry = load_registry(args.registry)
    differ = 0
    for ds in registry["datasets"]:
        got = compute(ds, registry)
        parts = dict(got or {})
        scope = computed_scoring_scope(registry, ds)  # from the registry itself, file or no file
        if scope is not None:
            parts["scoring_scope"] = scope
        same = all(ds.get(k) == v for k, v in parts.items())
        differ += not same
        if got is None and same:
            print(f"absent  {ds['id']}  ({ds['path']}; recorded blocks kept)")
        else:
            print(
                f"{'ok' if same else 'DIFF':<7} {ds['id']}"
                + ("  (file absent)" if got is None else "")
            )
        if args.write:
            ds.update(parts)
    guide = args.guide.read_text(encoding="utf-8")
    new_guide = apply_blocks(guide, render_blocks(registry))
    print(f"{'ok' if new_guide == guide else 'DIFF':<7} {args.guide.name} tables")
    if args.write:
        args.registry.write_text(dump(registry), encoding="utf-8")
        args.guide.write_text(new_guide, encoding="utf-8")
        print(f"wrote {args.registry} and {args.guide}")
        return 0
    return 1 if differ or new_guide != guide else 0


if __name__ == "__main__":
    sys.exit(main())
