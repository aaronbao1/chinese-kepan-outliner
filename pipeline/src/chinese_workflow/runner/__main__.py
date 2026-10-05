"""python -m chinese_workflow.runner run PROJECT.toml — one headless run of the outliner pipeline.

Input : projects/<id>/project.toml (common.project), the CBETA XML it names.
Output: a run directory (default data/processed/<project id>/, gitignored):
          run.json                 commit and dirty flag, CBETA release, input sha256, config hash,
                                   adapter/model, per-stage counts, split-guard report
          input-text/              ingest artefacts of the text the outline is stated in (and the root)
          outline/                 outline.json, outline.md/.docx, outlined-text.json/.md, target.txt,
                                   outline-report.json
          segment/sentences.json
          chunk/chunks.json, chunks.md, chunks.docx, invariants.json
          export/<text>.<scheme>.jsonld (when allowed: not for eval-only or OOD inputs)
        Exit 0 when every stage ran and the chunk invariants hold (an outline repaired by outline.repair
        counts as validating; stages.outline.degraded says how many repairs); 1 otherwise, including an
        outline that fails validation after repair; 2 when the split guard refused the run.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from ..common import jsonio, outline_doc
from ..common.paths import PROCESSED, repo_relative
from ..common.project import load_project
from ..common.splits import SplitGuard, SplitViolation


def run(project_path, out_dir=None, *, frozen: str | None = None, llm_config=None) -> dict:
    from .. import segment as segment_stage
    from ..chunk import chunker
    from ..chunk import render as chunk_render
    from ..eval import chunk_invariants
    from ..ingest import run as ingest_run
    from ..outline.__main__ import _llm_config
    from ..outline.pipeline import OutlineConfig, build

    proj = load_project(project_path)
    out = Path(out_dir) if out_dir else PROCESSED / proj["id"]
    out.mkdir(parents=True, exist_ok=True)
    guard = SplitGuard(frozen=frozen)
    cfg = OutlineConfig.from_project(proj)
    stages: dict = {}

    # outline (reads and guards the spans itself)
    llm_config = llm_config or _llm_config(cfg.resolver, out / "outline")
    res = build(cfg, out / "outline", guard=guard, llm_config=llm_config)
    doc, target = res["doc"], res["target"]
    stages["outline"] = {"nodes": doc["metadata"]["node_count"], "max_depth": doc["metadata"]["max_depth"],
                         "validation": res["report"]["validation"]["passed"],
                         "warnings": len(res["report"]["validation"]["warnings"]),
                         "degraded": sum(len(e["repairs"]) for e in res["report"].get("degraded", []))}

    # ingest artefacts of the stated text's span and of the target (already guarded above)
    stated = res["stated"]
    ingest_paths = {}
    for text, role in ((stated, "commentary" if cfg.mode == "sutra" else "root"), (target, "target")):
        if text.text_id in ingest_paths:
            continue
        span = (text.first_linehead, text.last_linehead)
        src = cfg.xml.get(text.text_id, text.text_id)
        ingest_paths[text.text_id] = ingest_run.run(src, role="commentary" if role == "commentary"
                                                    else "root", out_dir=out / "input-text", span=span,
                                                    guard=guard)
    stages["ingest"] = {k: v.get("counts") for k, v in ingest_paths.items()}

    # segment
    outlined = jsonio.read_json(res["paths"]["outlined_text"])
    sentences = segment_stage.run(target, outlined, strategy=int(proj["segment"].get("strategy", 2)))
    jsonio.write_json(sentences, out / "segment" / "sentences.json")
    stages["segment"] = {"sentences": len(sentences["sentences"]), "strategy": sentences["strategy"]}

    # chunk -> the interlinear outline
    outline_ref = {"path": repo_relative(res["paths"]["outline"]),
                   "sha256": jsonio.sha256_file(res["paths"]["outline"])}
    chunks = chunker.build_chunks(doc, outlined, sentences, target,
                                  sentence_cap=int(proj["chunk"].get("sentence_cap", 6)),
                                  size_chars=proj["chunk"].get("size_chars", 180),
                                  outline_ref=outline_ref)
    jsonio.write_json(chunks, out / "chunk" / "chunks.json")
    (out / "chunk" / "chunks.md").write_text(chunk_render.render_md(chunks), encoding="utf-8")
    chunk_render.render_docx(chunks, out / "chunk" / "chunks.docx")
    inv = chunk_invariants.check(chunks, outlined, sentences, doc)
    jsonio.write_json(inv, out / "chunk" / "invariants.json")
    stages["chunk"] = {"chunks": len(chunks["chunks"]), "invariants_ok": inv["ok"],
                       "stats": inv.get("stats")}

    # export (knowledge graph v0)
    if proj["export"].get("enabled", True):
        from ..export import jsonld

        hist_path = out / "export" / "id-history.json"
        history = jsonio.read_json(hist_path) if hist_path.exists() else None
        try:
            graph, history = jsonld.export(doc, id_history=history, frozen=frozen)
            name = "%s.%s.jsonld" % (doc["metadata"]["text_id"], doc["metadata"]["scheme_id"])
            jsonio.write_json(graph, out / "export" / name)
            jsonio.write_json(history, hist_path)
            stages["export"] = {"file": name, "nodes": sum(1 for x in graph.get("@graph", [])
                                                           if "cw:origin" in x)}
        except (ValueError, PermissionError) as exc:  # the export's own guards
            stages["export"] = {"refused": str(exc)}

    commit = outline_doc.pipeline_commit()
    run_json = {
        "project": repo_relative(project_path),
        "project_config_sha256": jsonio.sha256_json({k: v for k, v in proj.items()
                                                     if not k.startswith("_")}),
        "pipeline": commit,
        "date": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "cbeta_release": doc["metadata"].get("cbeta_release"),
        "inputs": {text.text_id: {"path": repo_relative(text.source_path),
                                  "sha256": jsonio.sha256_file(text.source_path)}
                   for text in (res["stated"], res["root"])},
        "frozen": frozen,
        "resolver": cfg.resolver,
        "llm": _llm_summary(out / "outline" / "llm"),
        "stages": stages,
        "split_guard": guard.report,
    }
    jsonio.write_json(run_json, out / "run.json")
    return {"out": str(out), "run": run_json, "ok": stages["outline"]["validation"] and inv["ok"]}


def _llm_summary(llm_dir: Path) -> dict:
    ledger = llm_dir / "ledger.json"
    return jsonio.read_json(ledger) if ledger.exists() else {"calls": 0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m chinese_workflow.runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a project end to end")
    r.add_argument("project")
    r.add_argument("--out")
    r.add_argument("--frozen")
    args = ap.parse_args(argv)
    from ..ingest.text import CbetaFileMissing
    from ..outline.pipeline import OutlineValidationError

    try:
        result = run(args.project, args.out, frozen=args.frozen)
    except SplitViolation as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 2
    except OutlineValidationError as exc:
        # the outline build wrote its artefacts, but outline.json still fails validation after repair, so no
        # later stage ran. Any other RuntimeError (a stage's own failure) keeps its traceback.
        print("failed: %s" % exc, file=sys.stderr)
        return 1
    except CbetaFileMissing as exc:  # a CBETA file the project names is not fetched yet (a fresh clone)
        print("failed: %s" % exc, file=sys.stderr)
        return 1
    print(json.dumps({"out": result["out"], "ok": result["ok"], "stages": result["run"]["stages"]},
                     ensure_ascii=False, indent=1))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
