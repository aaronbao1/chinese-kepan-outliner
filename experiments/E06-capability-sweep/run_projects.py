"""E06 whole-pipeline runs: `python -m chinese_workflow.runner run` on every projects/*/project.toml.

Input : projects/<id>/project.toml (adapter as in the toml: 'none'); the CBETA XML they name.
Output: experiments/E06-capability-sweep/runs/project-<id>/ (the runner's run directories; gitignored),
        experiments/E06-capability-sweep/projects.json (structured results: exit code, time, outline
        size and shape, chunk invariants, chunk size distributions, export, split-guard log).
        Hand-written qualitative notes, when experiments/E06-capability-sweep/projects-notes.json
        exists, are merged in under each project's "qualitative" key.

No --frozen is passed: the runner's split guard stays armed, so any read of a test or reserve span of
T34n1718 / T34n1723 would be refused (exit 2) rather than performed. The projects read only dev spans
of those files (or unsplit texts), which the guard log in projects.json records. Nothing here reads a
gold; no heading text of a Lotus-sūtra (T0262 / T1718 / T1723) prediction is written (only node ids),
so that no string that might coincide with an eval-only sdp heading lands in this file.

Run: cd pipeline && .venv/bin/python ../experiments/E06-capability-sweep/run_projects.py [--no-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PIPELINE = REPO / "pipeline"
PY = PIPELINE / ".venv" / "bin" / "python"
FROZEN_TAG = "outliner-v0-frozen-2026-10-01"
TINY_CHARS = 20


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def toml_load(path: Path) -> dict:
    import tomllib

    return tomllib.loads(path.read_text(encoding="utf-8"))


def dist(values: list) -> dict:
    """min / p10 / p25 / median / p75 / p90 / max / mean of a list of numbers (nearest rank)."""
    if not values:
        return {"n": 0}
    v = sorted(values)

    def q(p):
        return v[min(len(v) - 1, max(0, round(p * (len(v) - 1))))]

    return {"n": len(v), "min": v[0], "p10": q(0.10), "p25": q(0.25), "median": statistics.median(v),
            "p75": q(0.75), "p90": q(0.90), "max": v[-1], "mean": round(statistics.fmean(v), 1)}


def hist(values: list, edges: list) -> dict:
    """Counts per [edges[i], edges[i+1]) bucket, plus '>=last'."""
    out = {}
    for lo, hi in zip(edges, edges[1:]):
        out["%d-%d" % (lo, hi - 1)] = sum(1 for x in values if lo <= x < hi)
    out[">=%d" % edges[-1]] = sum(1 for x in values if x >= edges[-1])
    return out


def line_of(ref: str | None) -> str | None:
    return ref.split(":", 1)[0] if ref else None


def run_project(pid: str, toml: Path, out: Path) -> dict:
    cmd = [str(PY), "-m", "chinese_workflow.runner", "run", str(Path("..") / toml.relative_to(REPO)),
           "--out", str(Path("..") / out.relative_to(REPO))]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, cwd=PIPELINE, capture_output=True, text=True)
    secs = time.perf_counter() - t0
    return {"command": "cd pipeline && " + " ".join(["python"] + cmd[1:]), "exit_code": proc.returncode,
            "seconds": round(secs, 2), "stderr_tail": proc.stderr.strip().splitlines()[-5:]}


def analyse_outline(run: Path, proj: dict) -> dict:
    doc = load(run / "outline" / "outline.json")
    rep = load(run / "outline" / "outline-report.json")
    nodes = doc["nodes"]
    meta = doc["metadata"]
    kids = Counter(n.get("parent_id") for n in nodes if n.get("parent_id"))
    internal = [n for n in nodes if kids.get(n["id"])]
    leaves = [n for n in nodes if not kids.get(n["id"])]
    com = [((n.get("locations") or {}).get("commentary") or {}) for n in nodes]
    explained_null = [n["id"] for n, c in zip(nodes, com) if not c.get("explained")]
    listed_only = [n["id"] for n, c in zip(nodes, com) if c.get("announced") and c.get("announced") == c.get("explained")]
    sutra = meta.get("outline_mode") == "sutra"
    root_null = [n["id"] for n in nodes if sutra and not (n.get("locations") or {}).get("root_text")]
    root_null_sutra_span = [n["id"] for n in nodes if sutra and n.get("node_class") != "commentary-internal"
                            and not (n.get("locations") or {}).get("root_text")]
    warnings = rep["validation"]["warnings"]
    wkinds = Counter(w.split("[", 1)[1].split("]", 1)[0] if "[" in w else "other" for w in warnings)
    t2 = rep.get("tier2") or {}
    hlen = [len(n.get("heading_src") or "") for n in nodes]
    # longest chain of single-child internal nodes
    by_id = {n["id"]: n for n in nodes}

    def chain(nid):
        k = [m for m in nodes if m.get("parent_id") == nid]
        return 1 + chain(k[0]["id"]) if len(k) == 1 else 0

    single = [n["id"] for n in internal if kids[n["id"]] == 1]
    longest_single_chain = max([chain(n["id"]) for n in nodes] or [0])
    # node starts across the stated span (lines of the text the outline is read from)
    stated_id = meta["source_document"]["text_id"]
    lines = [json.loads(x)["linehead"] for x in
             (run / "input-text" / ("%s.lines.jsonl" % stated_id)).read_text(encoding="utf-8").splitlines() if x.strip()]
    pos = {lh: i for i, lh in enumerate(lines)}
    starts = sorted({pos[line_of(c.get("explained"))] for c in com if line_of(c.get("explained")) in pos})
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    span_cov = None
    if starts and lines:
        span_cov = {"stated_text": stated_id, "span_lines": len(lines),
                    "first_node_line_index": starts[0], "last_node_line_index": starts[-1],
                    "frac_of_span_after_last_node_start": round((len(lines) - 1 - starts[-1]) / len(lines), 3),
                    "largest_gap_between_node_starts_lines": max(gaps) if gaps else None,
                    "distinct_node_start_lines": len(starts)}
    anchor_codes = Counter(a.get("code") for a in (rep.get("anchor") or []))
    return {
        "nodes": meta["node_count"], "max_depth": meta["max_depth"], "leaves": len(leaves),
        "nodes_per_level": meta.get("nodes_per_level"),
        "origin": dict(Counter(n["origin"] for n in nodes)),
        "node_class": dict(Counter(n["node_class"] for n in nodes)),
        "flags": dict(Counter(f for n in nodes for f in n.get("flags") or [])),
        "explained_null": len(explained_null),
        "listed_only_announced_eq_explained": len(listed_only),
        "root_text_null": len(root_null) if sutra else None,
        "root_text_null_excluding_commentary_internal": len(root_null_sutra_span) if sutra else None,
        "anchor_report_codes": dict(anchor_codes),
        "internal_nodes": len(internal), "single_child_internal_nodes": len(single),
        "longest_single_child_chain": longest_single_chain,
        "max_children": max(kids.values()) if kids else 0,
        "heading_chars": dist(hlen), "headings_over_20_chars": sum(1 for x in hlen if x > 20),
        "validation_passed": rep["validation"]["passed"], "validation_errors": len(rep["validation"]["errors"]),
        "validation_warnings": len(warnings), "validation_warning_kinds": dict(wkinds),
        "tier1": {"drafts": rep["tier1"]["drafts"], "pins": rep["tier1"]["pins"],
                  "anomalies": len(rep["tier1"].get("anomalies") or [])},
        "tier2_stats": t2.get("stats"),
        "genre_gate": (t2.get("genre_gate") or {}).get("decision"),
        "rejected_doctrinal_lists": len(t2.get("rejected") or []),
        "merge_report_kinds": dict(Counter(m.get("kind") for m in rep.get("merge") or [])),
        "scheme_report_kinds": dict(Counter(s.get("kind") for s in rep.get("scheme") or [])),
        "node_start_coverage": span_cov,
        "pending_interactive": len(rep.get("pending_interactive") or []),
    }


def analyse_outlined_text(run: Path) -> dict:
    ot = load(run / "outline" / "outlined-text.json")
    sizes = [s["char_end"] - s["char_start"] for s in ot["spans"]]
    big = max(ot["spans"], key=lambda s: s["char_end"] - s["char_start"]) if ot["spans"] else None
    length = ot["target"]["length"]
    return {"target": ot["target"]["text_id"], "target_chars": length,
            "coverage_ratio": round(ot["coverage"]["ratio"], 4), "overlaps": ot["coverage"]["overlaps"],
            "gaps": [{"chars": g["char_end"] - g["char_start"], "reason": g["reason"]} for g in ot["gaps"]],
            "spans": len(ot["spans"]), "span_kinds": dict(Counter(s["kind"] for s in ot["spans"])),
            "span_chars": dist(sizes),
            "largest_span": ({"node_id": big["node_id"], "kind": big["kind"],
                              "chars": big["char_end"] - big["char_start"],
                              "frac_of_target": round((big["char_end"] - big["char_start"]) / length, 3)}
                             if big else None),
            "nodes_without_span": len(ot.get("unplaced") or [])}


def analyse_chunks(run: Path, proj: dict) -> dict:
    ch = load(run / "chunk" / "chunks.json")
    inv = load(run / "chunk" / "invariants.json")
    sent = load(run / "segment" / "sentences.json")["sentences"]
    cap = int(proj.get("chunk", {}).get("sentence_cap", 6))
    budget = int(proj.get("chunk", {}).get("size_chars", 180))
    chunks = ch["chunks"]
    chars = [c["n_chars"] for c in chunks]
    sents = [c["n_sentences"] for c in chunks]
    slen = [s["char_end"] - s["char_start"] for s in sent]
    over = [{"chunk_id": c["chunk_id"], "n_chars": c["n_chars"], "n_sentences": c["n_sentences"],
             "fallback": c["fallback"]} for c in chunks if c["n_chars"] > budget]
    failures = {k: len(v.get("violations") or []) for k, v in inv["invariants"].items() if not v.get("ok")}
    return {
        "chunks": len(chunks), "invariants_ok": inv["ok"],
        "invariants_checked": sorted(inv["invariants"]), "invariant_failures": failures,
        "budget": {"sentence_cap": cap, "size_chars": budget},
        "chars": dist(chars), "chars_hist": hist(chars, [0, 20, 50, 100, 150, budget + 1]),
        "sentences": dist(sents), "sentences_hist": dict(sorted(Counter(sents).items())),
        "tiny_chunks_lt_%d_chars" % TINY_CHARS: sum(1 for x in chars if x < TINY_CHARS),
        "single_sentence_chunks": sum(1 for x in sents if x == 1),
        "zero_sentence_chunks": sum(1 for x in sents if x == 0),
        "over_size_chars": over, "over_sentence_cap": sum(1 for x in sents if x > cap),
        "fallback": dict(Counter(c["fallback"] for c in chunks)),
        "stats_from_invariants": inv.get("stats"),
        "sentence_units": {"n": len(sent), "kinds": dict(Counter(s.get("kind") for s in sent)),
                           "chars": dist(slen), "over_size_chars": sum(1 for x in slen if x > budget)},
    }


def analyse(pid: str, run: Path, proj: dict, ran: dict) -> dict:
    rec = {"project": pid, "mode": proj.get("mode"), "target_role": proj.get("target_role"),
           "span": proj.get("span"), "source": proj.get("source"),
           "adapter": (proj.get("resolver") or {}).get("adapter"), "run_dir": str(run.relative_to(REPO))}
    rec.update(ran)
    rj = run / "run.json"
    if not rj.exists():
        rec["error"] = "no run.json"
        return rec
    r = load(rj)
    guard = r.get("split_guard") or []
    touched = sorted({s for e in guard for s in e.get("splits", [])})
    rec["run_json"] = {"pipeline": r.get("pipeline"), "frozen": r.get("frozen"),
                       "cbeta_release": r.get("cbeta_release"), "llm_calls": (r.get("llm") or {}).get("calls"),
                       "inputs": r.get("inputs"), "stages": {k: v for k, v in r["stages"].items() if k != "chunk"}}
    rec["split_guard"] = {"splits_touched": touched,
                          "test_or_reserve_read": bool(set(touched) & {"test", "reserve"}),
                          "entries": guard}
    rec["outline"] = analyse_outline(run, proj)
    rec["outlined_text"] = analyse_outlined_text(run)
    rec["chunk"] = analyse_chunks(run, proj)
    exp = r["stages"].get("export") or {}
    efile = run / "export" / exp["file"] if exp.get("file") else None
    rec["export"] = {"written": bool(efile and efile.exists()), "file": exp.get("file"),
                     "nodes": exp.get("nodes"), "refused": exp.get("refused")}
    rec["files_present"] = {p: (run / p).exists() for p in
                            ("outline/outline.md", "outline/outline.docx", "outline/outlined-text.md",
                             "chunk/chunks.md", "chunk/chunks.docx")}
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-run", action="store_true", help="analyse existing run directories only")
    args = ap.parse_args(argv)
    tag_commit = git("rev-parse", FROZEN_TAG + "^{commit}")
    head = git("rev-parse", "HEAD")
    pipeline_same = subprocess.run(["git", "diff", "--quiet", FROZEN_TAG, "--", "pipeline/"], cwd=REPO).returncode == 0
    untracked_pipeline = git("status", "--porcelain", "--", "pipeline/")
    prior = load(HERE / "projects.json") if (args.no_run and (HERE / "projects.json").exists()) else {}
    notes = load(HERE / "projects-notes.json") if (HERE / "projects-notes.json").exists() else {}
    results = {}
    for toml in sorted((REPO / "projects").glob("*/project.toml")):
        proj = toml_load(toml)
        pid = proj["id"]
        run = HERE / "runs" / ("project-%s" % pid)
        if args.no_run:
            ran = {k: (prior.get("projects", {}).get(pid) or {}).get(k)
                   for k in ("command", "exit_code", "seconds", "stderr_tail")}
        else:
            ran = run_project(pid, toml, run)
        rec = analyse(pid, run, proj, ran)
        if pid in (notes.get("projects") or {}):
            rec["qualitative"] = notes["projects"][pid]
        results[pid] = rec
    out = {
        "schema": "e06-projects/1",
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "frozen_tag": FROZEN_TAG, "frozen_tag_commit": tag_commit, "head": head,
        "pipeline_identical_to_tag": pipeline_same and not untracked_pipeline,
        "frozen_flag_passed": False,
        "frozen_flag_note": "runner run without --frozen: the split guard stays armed (a test/reserve read "
                            "would be refused, exit 2); run.json therefore records frozen: null. "
                            "pipeline.dirty is true because files outside pipeline/ are modified; "
                            "pipeline/ itself is byte-identical to the tag (pipeline_identical_to_tag).",
        "projects": results,
        "summary": {pid: {"exit_code": r.get("exit_code"), "seconds": r.get("seconds"),
                          "nodes": (r.get("outline") or {}).get("nodes"),
                          "max_depth": (r.get("outline") or {}).get("max_depth"),
                          "chunks": (r.get("chunk") or {}).get("chunks"),
                          "invariants_ok": (r.get("chunk") or {}).get("invariants_ok"),
                          "export_written": (r.get("export") or {}).get("written")}
                    for pid, r in results.items()},
    }
    if notes.get("cross_project"):
        out["cross_project_observations"] = notes["cross_project"]
    (HERE / "projects.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    json.dump(out["summary"], sys.stdout, indent=1)
    print()
    return 0 if all(r.get("exit_code") == 0 for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
