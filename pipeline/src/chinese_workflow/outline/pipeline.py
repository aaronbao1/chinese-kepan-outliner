"""chinese_workflow.outline.pipeline — one outline build (docs/outliner-design.md §5).

Input : an OutlineConfig (usually from projects/<id>/project.toml): the root text, the commentary (sūtra
        mode), the scheme, the span the parser reads, the outline source, the scheme prior, the resolver
        adapter; the CBETA XML files (data/raw/cbeta/ or per-file overrides such as test fixtures).
Output: in out_dir —
        outline.json          the independent outline (zh-kepan prediction; validated)
        outline.md / .docx    the same in Kurt's independent-outline format (outline.render)
        outlined-text.json    the outline plugged back into the target text (schema outlined-text/1)
        outlined-text.md      the human view of it
        target.txt            the target reading text the offsets index
        outline-report.json   parser report, doctrinal-list rejections, merge / scheme / anchor / classify
                              (out-of-span) / resolver / gloss reports, validator findings, split-guard
                              entries, and `degraded` (the local validator errors repaired and how; absent
                              when none were)

Steps: tier 1 (cb:mulu of the whole file: structure only; a span build carries the enclosing 品 pin) -> tier 2
(formula parser over the span) -> merge -> scheme prior -> number (common.outline_doc) -> root spans (anchor,
sūtra mode) -> validate, repair local errors, re-validate (outline.repair) -> out-of-span classification
(classify, sūtra mode, on the repaired document) -> resolver and gloss (llm adapter; 'none' skips) -> validate
(and repair) again, when they ran -> span starts (common.outline_doc.fill_span_starts, after the last tree
edit, so inferred nodes get them too) -> validate -> outlined-text -> render. The build fails (raises
OutlineValidationError, after writing every artefact) only on errors no repair covers; a hybrid build then
skips the resolver and gloss, whose input must validate.

Sources: tier1 = the chapter TOC only (E01's floor); tier2 = tier 1 + the formula parser (explicit
nodes only); hybrid = tier2 + resolver + gloss through the configured adapter; oracle = the Kuiji gold's
readable part (levels 1–2 + the dev subtree) for format samples (plan SK). The split guard refuses test
and reserve spans of T1718/T1723 unless a frozen outliner is named.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..common import jsonio, outline_doc
from ..common.paths import REFERENCE_OUTLINES, repo_relative
from ..common.project import resolve_span
from ..common.splits import SplitGuard
from ..ingest.lines import build_index
from ..ingest.text import InputText, load_input_text

SOURCES = ("tier1", "tier2", "hybrid", "oracle")
KUIJI_GOLD = REFERENCE_OUTLINES / "T0262" / "kuiji-xuanzan" / "outline.json"


class OutlineValidationError(RuntimeError):
    """outline.json still fails the validator after repair: errors outline.repair does not cover, or local
    ones that did not settle in repair.MAX_PASSES rounds. Raised after every artefact and the report are
    written, so the CLIs can exit 1 with the findings and the files to inspect; any other RuntimeError of a
    stage keeps its traceback. Defined here, with the build that raises it (the CLIs of this stage and the
    runner, which may import several stages, catch it), rather than in common.outline_doc, which owns the
    format and the validator call, not the build's failure policy."""


@dataclass
class OutlineConfig:
    mode: str  # "sutra" | "self-outlining"
    root: str  # CBETA file id: the sūtra (sūtra mode) or the treatise (self-outlining)
    commentary: str | None = None
    scheme_id: str = "unnamed-scheme"
    span: object = None  # span spec for the text the parser reads (see common.project.resolve_span)
    source: str = "tier2"
    target_role: str = "commentary"
    level1: list = field(default_factory=list)
    xml: dict = field(default_factory=dict)  # file id -> XML path override
    resolver: dict = field(default_factory=lambda: {"adapter": "none"})
    oracle_gold: str | None = None
    title: str = ""
    heading_style: str = "source"  # tier 2: "source" keeps the ordinal (初明持經之福), as the golds do

    @classmethod
    def from_project(cls, proj: dict) -> "OutlineConfig":
        return cls(
            mode=proj["mode"], root=proj["root"], commentary=proj.get("commentary"),
            scheme_id=proj["scheme_id"], span=proj.get("span"), source=proj.get("source", "tier2"),
            target_role=proj.get("target_role", "commentary"),
            level1=list((proj.get("scheme") or {}).get("level1") or []), xml=dict(proj.get("xml") or {}),
            resolver=dict(proj.get("resolver") or {"adapter": "none"}),
            oracle_gold=proj.get("oracle_gold"), title=proj.get("title", ""),
            heading_style=(proj.get("outline") or {}).get("heading_style", "source"),
        )

    @property
    def stated_in(self) -> str:
        """File id of the text the outline is read from (commentary in sūtra mode, else the text)."""
        return self.commentary if self.mode == "sutra" else self.root


def short_id(file_id: str) -> str:
    """'T09n0262' -> 'T0262' (the text number the golds use in metadata.text_id)."""
    m = re.match(r"^([A-Z]+)[0-9]+n(.+)$", file_id)
    return (m.group(1) + m.group(2)) if m else file_id


def _load(file_id: str, cfg: OutlineConfig, role: str) -> InputText:
    return load_input_text(cfg.xml.get(file_id, file_id), role=role)


def slice_text(full: InputText, span: tuple | None) -> InputText:
    """The span (inclusive lineheads) of an already loaded text, without re-reading the XML."""
    if span is None:
        return full
    pos = {rec["linehead"]: i for i, rec in enumerate(full.lines)}
    i, j = pos[span[0]], pos[span[1]]
    lines = full.lines[i : j + 1]
    return InputText(text_id=full.text_id, role=full.role, info=full.info, lines=lines,
                     all_lineheads=full.all_lineheads, index=build_index(lines),
                     source_path=full.source_path)


def _root_target_span(doc: dict, root: InputText, stated: InputText) -> tuple | None:
    """The root lines a run covers: from the first to the last root_text line of the nodes read from
    the run's span (commentary.explained inside `stated`) — for a dev run, the 品 the span comments
    on, not the whole level-1 part a scheme prior wraps around it."""
    starts, ends = [], []
    for n in doc["nodes"]:
        com = (n.get("locations") or {}).get("commentary") or {}
        if not stated.contains(com.get("explained")):
            continue
        rt = (n.get("locations") or {}).get("root_text") or {}
        if rt.get("start") and rt.get("end") and root.contains(rt["start"]) and root.contains(rt["end"]):
            starts.append(root.order.index(rt["start"]))
            ends.append(root.order.index(rt["end"]))
    if not starts:
        return None
    return (root.all_lineheads[min(starts)], root.all_lineheads[max(ends)])


def _validate_and_repair(doc: dict, report: dict, stage: str):
    """validate -> repair the local errors (outline.repair) -> re-validate, up to repair.MAX_PASSES rounds
    (a raised end that cascades or a clip that inverts is caught by the next round). Each round that
    changed something is recorded under report['degraded']; returns the last validator Report."""
    from . import repair

    val = outline_doc.validate(doc, "outline.json")
    for _ in range(repair.MAX_PASSES):
        local = [f for f in val.errors if repair.is_local(f)]
        if not local:
            break
        repairs = repair.repair(doc, local)
        if not repairs:
            break
        report.setdefault("degraded", []).append(
            {"stage": stage, "errors": [f.render() for f in local], "repairs": repairs})
        val = outline_doc.validate(doc, "outline.json")
    return val


def build(cfg: OutlineConfig, out_dir, *, guard: SplitGuard | None = None,
          llm_config=None) -> dict:
    """Run one outline build; returns {"paths": {...}, "report": {...}, "doc": outline dict}."""
    from . import anchor, classify, merge, render, scheme, tier1

    if cfg.source not in SOURCES:
        raise ValueError("source must be one of %s" % (SOURCES,))
    guard = guard or SplitGuard()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"config": {k: v for k, v in cfg.__dict__.items() if k != "xml"}}

    # ---- texts
    stated_full = _load(cfg.stated_in, cfg, "commentary" if cfg.mode == "sutra" else "root")
    guard.check_structure(cfg.stated_in)
    span = resolve_span(cfg.span, cfg.stated_in, stated_full.all_lineheads, guard.registry)
    stated = slice_text(stated_full, span)
    guard.check_lines([rec["linehead"] for rec in stated.lines], purpose="outline: %s prose"
                      % cfg.stated_in)
    root_full = stated_full if cfg.mode == "self-outlining" else _load(cfg.root, cfg, "root")
    if cfg.mode == "sutra":  # lemma search, root spans and a root target read all of it
        guard.check_lines(root_full.all_lineheads, purpose="outline: %s root text" % cfg.root)

    # ---- tier 1, tier 2, merge, scheme prior
    role = "commentary" if cfg.mode == "sutra" else "root"
    t1 = tier1.build(stated_full, mode=cfg.mode, role=role, span=span)
    drafts = t1.drafts
    root_pins = t1.pins
    if cfg.mode == "sutra":
        root_pins = tier1.build(root_full, mode=cfg.mode, role="root").pins
        drafts = tier1.align_pins(drafts, root_pins)
    report["tier1"] = {"drafts": len(drafts), "pins": len(t1.pins), "anomalies": t1.anomalies,
                       "carried": t1.carried}

    parser_result = None
    if cfg.source == "oracle":
        from .oracle import oracle_drafts

        gold = Path(cfg.oracle_gold) if cfg.oracle_gold else KUIJI_GOLD
        roots = oracle_drafts(gold, keep_span=span or (stated.first_linehead, stated.last_linehead))
        report["oracle"] = {"gold": repo_relative(gold)}
    else:
        by_anchor: dict = {}
        if cfg.source in ("tier2", "hybrid"):
            from . import tier2

            parser_result = tier2.parse(stated, anchors=t1.anchors, mode=cfg.mode,
                                        config={"heading_style": cfg.heading_style})
            by_anchor = parser_result.by_anchor
            report["tier2"] = {"stats": parser_result.stats, "genre_gate": parser_result.genre_gate,
                               "report": parser_result.report, "rejected": parser_result.rejected}
        anchor_ends = {p.start: p.end for p in t1.pins}
        for c in t1.carried:  # a carried pin anchors on the span's first line: the innermost one's end, unless
            if c["anchor"] not in {p.start for p in t1.pins}:  # a unit that starts there receives the drafts
                anchor_ends[c["anchor"]] = c["end"]
        line_index = {lh: i for i, lh in enumerate(stated_full.all_lineheads)}
        roots, report["merge"] = merge.attach(drafts, by_anchor, anchor_ends=anchor_ends,
                                              line_index=line_index)
        if cfg.level1 and cfg.mode == "sutra":
            roots, report["scheme"] = scheme.apply_level1(roots, cfg.level1, root_pins=root_pins,
                                                          commentary_pins=t1.pins)

    # ---- number
    commit = outline_doc.pipeline_commit()
    gen = "chinese_workflow.outline (source %s) @ %s%s" % (
        cfg.source, (commit["commit"] or "unknown")[:12], "+dirty" if commit["dirty"] else "")
    doc, _private = outline_doc.build_prediction(
        roots,
        text_id=short_id(cfg.root),
        text_title_src=root_full.info.get("title") or cfg.root,
        text_title_en=cfg.title,
        outline_mode=cfg.mode,
        root_text_id=cfg.root,
        commentary_id=cfg.commentary,
        scheme_id=cfg.scheme_id,
        source_file=repo_relative(stated_full.source_path),
        source_document={
            "kind": "commentary" if cfg.mode == "sutra" else "root-text",
            "text_id": cfg.stated_in,
            "title": stated_full.info.get("title") or cfg.stated_in,
            "url": None,
            "notes": [],
        },
        generated_by=gen,
        format_note=(
            "Prediction of the kēpàn outliner (docs/outliner-design.md): source %s over %s, span %s. "
            "Explicit nodes come from CBETA cb:mulu (tier 1) and the commentary's division formulae "
            "(tier 2); editorial nodes from the project's scheme prior; inferred nodes (if any) from "
            "the resolver adapter %s. Locators may carry ':<offset>' (character offset in the line)."
            % (cfg.source, cfg.stated_in, "%s..%s" % span if span else "whole file",
               (cfg.resolver or {}).get("adapter", "none"))
        ),
        source_sha256=jsonio.sha256_file(stated_full.source_path),
        span={"first": stated.first_linehead, "last": stated.last_linehead},
        genre_gate=(parser_result.genre_gate if parser_result else None),
    )

    # ---- root spans (sūtra mode)
    if cfg.mode == "sutra":
        doc, report["anchor"] = anchor.resolve_root_spans(doc, root_full)

    # ---- validate, repair local errors, re-validate (design §5.0 'Degradation'): the resolver's input
    # check (resolver.resolve) and the explicit-node snapshot below see the repaired document
    pre = _validate_and_repair(doc, report, "before-resolver")

    # ---- out-of-span classification (sūtra mode), on the repaired document: a repair that nulls or clips a
    # span changes what the classifier reads (the nearest spanned ancestor, the unmapped candidates). It only
    # adds notes, so `pre` stays the validation of this document.
    if cfg.mode == "sutra":
        doc, report["classify"] = classify.mark_out_of_span(doc, root_pins=root_pins,
                                                             order=root_full.order)

    # ---- resolver and gloss (model-assisted; adapter 'none' skips). Their input must validate: when errors
    # remain after repair the build skips them (resolver.resolve would raise before anything is written),
    # and the final validation below fails with the artefacts and this report on disk.
    adapter = (cfg.resolver or {}).get("adapter", "none")
    pending: list = []
    model_ran = False  # the resolver or the gloss returned: the tree may have changed
    if cfg.source == "hybrid" and adapter != "none":
        from ..llm import PendingInteractive
        from . import gloss, resolver

        before = doc
        if not pre.passed():
            skipped = {"status": "skipped: input fails validation after repair"}
            report["resolver"], report["gloss"] = dict(skipped), dict(skipped)
        else:
            try:
                doc, report["resolver"] = resolver.resolve(
                    doc, root=root_full if cfg.mode == "sutra" else None, commentary=stated,
                    config=llm_config, parser_report=(parser_result.report if parser_result else None),
                    scheme_id=cfg.scheme_id)
                model_ran = True
            except PendingInteractive as exc:  # interactive adapter: answer the requests, re-run
                pending += exc.requests
                report["resolver"] = {"status": "pending interactive responses", "requests": exc.requests,
                                      "task_report": getattr(exc, "task_report", None)}
            outline_doc.assert_explicit_unchanged(before, doc)
            try:
                doc, report["gloss"] = gloss.gloss(doc, config=llm_config, commentary=stated)
                model_ran = True
            except PendingInteractive as exc:
                pending += exc.requests
                report["gloss"] = {"status": "pending interactive responses", "requests": exc.requests}
    report["pending_interactive"] = pending

    # ---- validate (and repair what the resolver added; only when it or the gloss ran), span starts, validate
    # and write
    outline_doc.refresh_counts(doc)
    if model_ran:
        _validate_and_repair(doc, report, "after-resolver")
        # the explicit fingerprint ignores root_text, so this guards headings, levels and commentary
        # locators, not the spans a repair may raise or clip
        outline_doc.assert_explicit_unchanged(before, doc)
    # the second commentary locator, after the last edit of explained lines and tree (T2): repairs included
    outline_doc.fill_span_starts(doc)
    val = outline_doc.validate(doc, "outline.json")
    report["validation"] = {"passed": val.passed(), "errors": [f.render() for f in val.errors],
                            "warnings": [f.render() for f in val.warnings]}
    paths = {"outline": jsonio.write_json(doc, out_dir / "outline.json")}
    outline_ref = {"path": repo_relative(paths["outline"]), "sha256": jsonio.sha256_file(paths["outline"])}

    # ---- outlined-text over the target
    if cfg.target_role == "commentary" or cfg.mode == "self-outlining":
        target = stated
    else:
        target = slice_text(root_full, _root_target_span(doc, root_full, stated))
    sidecar, md = anchor.outlined_text(doc, target, target_role=("commentary" if cfg.mode == "sutra"
                                                                 and cfg.target_role == "commentary"
                                                                 else "root"),
                                       outline_ref=outline_ref)
    paths["outlined_text"] = jsonio.write_json(sidecar, out_dir / "outlined-text.json")
    (out_dir / "outlined-text.md").write_text(md, encoding="utf-8")
    paths["outlined_text_md"] = out_dir / "outlined-text.md"
    (out_dir / "target.txt").write_text(target.text, encoding="utf-8")
    paths["target"] = out_dir / "target.txt"
    report["target"] = {"text_id": target.text_id, "first": target.first_linehead,
                        "last": target.last_linehead, "sha256": target.sha256}

    # ---- render
    (out_dir / "outline.md").write_text(render.render_markdown(doc), encoding="utf-8")
    paths["outline_md"] = out_dir / "outline.md"
    paths["outline_docx"] = render.render_docx(doc, out_dir / "outline.docx")

    report["split_guard"] = guard.report
    paths["report"] = jsonio.write_json(report, out_dir / "outline-report.json")
    if not val.passed():  # only errors outline.repair does not cover (schema, not-preorder, sibling-index …)
        raise OutlineValidationError("outline.json failed validation after repair: %s"
                                     % report["validation"]["errors"][:5])
    return {"pending": pending, "paths": {k: str(v) for k, v in paths.items()}, "report": report, "doc": doc,
            "target": target, "root": root_full, "stated": stated}
