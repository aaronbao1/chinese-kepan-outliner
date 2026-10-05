"""chinese_workflow.outline.gloss — the gloss sub-step: English headings for an outline (docs/
outliner-design.md §5.6; divergence D17, proposed 2026-09-27, pending Aaron).

Input : gloss(doc, *, config, commentary=None)
          doc         a zh-kepan outline document that validates
          config      llm.LLMConfig; adapter 'none' (or config None) skips the step
          commentary  InputText of the commentary (sūtra mode) or of the outlined text
                      (self-outlining mode): its explained line gives each node a short context;
                      optional
Output: (new doc, report). Every node whose heading_en is empty and that the model glosses gets
        heading_en = the gloss and a note "heading_en: gloss by <model> (<adapter>)"; nothing else
        changes (explicit nodes keep every fingerprinted field; the doc still validates). With
        adapter 'none' the doc is returned unchanged with report {"status": "skipped: no model"}.
Requests: one per unit (per 品 or level-1 subtree, plus 'top', in sūtra mode; per window in
        self-outlining mode; the units of outline/resolver.py), listing node ids, levels,
        heading_src and the context; the prompt is
        skills/chinese-kepan-outliner/references/gloss-prompt.md, the answer schema
        pipeline/schemas/gloss.schema.json ({glosses: [{node_id, heading_en}]}).
"""

from __future__ import annotations

import copy

from ..common.jsonio import sha256_text
from ..common.outline_doc import assert_explicit_unchanged, validate
from ..llm import (
    InvalidResponse,
    LLMConfig,
    NoModel,
    PendingInteractive,
    Refusal,
    call,
    request_hash,
)
from .resolver import _Lines, _Texts, _units, _View, load_prompts, load_schema

GLOSS_PROMPT = "gloss-prompt.md"
TASK = "gloss"
CONTEXT_CHARS = 60


def _context(view: _View, n: dict) -> str:
    C = view.tx.C
    p = view.explained(n)
    if C is None or p is None:
        return ""
    text = C.texts[p]
    return text if len(text) <= CONTEXT_CHARS else text[:CONTEXT_CHARS] + "…"


def _message(prompts, view: _View, unit, targets: list) -> str:
    first = view.by_id[unit.members[0]]
    anc = [a for a in view.ancestors(first) if a["id"] not in set(unit.members)]
    path = (
        " > ".join(
            "%s 「%s」 %s" % (a["id"], a.get("heading_src", ""), a.get("heading_en", ""))
            for a in anc
        )
        or "(top level)"
    )
    lines = []
    for n in targets:
        parents = [a.get("heading_src", "") for a in view.ancestors(n)][-2:]
        line = "- %s (level %d) 「%s」" % (n["id"], n["level"], n.get("heading_src", ""))
        if parents:
            line += "; under %s" % " > ".join("「%s」" % h for h in parents)
        ctx = _context(view, n)
        if ctx:
            line += "; context line: %s" % ctx
        lines.append(line)
    return (
        "\n".join(
            [
                prompts.tasks[TASK],
                "",
                "# Unit %s" % unit.key,
                "",
                "Ancestor path: %s" % path,
                "",
                "## Nodes to gloss",
                "",
            ]
            + lines
        )
        + "\n"
    )


def gloss(doc: dict, *, config: LLMConfig | None, commentary=None) -> tuple[dict, dict]:
    """Fill heading_en through the model; see the module docstring."""
    if config is None or config.adapter == "none":
        return copy.deepcopy(doc), {"status": "skipped: no model"}
    prompts = load_prompts(GLOSS_PROMPT)
    if TASK not in prompts.tasks:
        raise ValueError("%s has no '## task: gloss' section" % GLOSS_PROMPT)
    schema = load_schema("gloss")
    mode = doc["metadata"].get("outline_mode") or "sutra"
    lines = _Lines(commentary) if commentary is not None else None
    tx = _Texts(mode, lines if mode != "sutra" else None, lines, model_only=commentary is None)
    new = copy.deepcopy(doc)
    view = _View(new, tx)
    report = {
        "adapter": config.adapter,
        "model": config.model,
        "prompts": dict(prompts.files),
        "prompt_sha256": prompts.sha,
        "system_sha256": sha256_text(prompts.system),
        "requests": 0,
        "answered": 0,
        "filled": 0,
        "invalid": [],
        "rejected": [],
        "not_answered": [],
    }
    note = "heading_en: gloss by %s (%s)" % (config.model, config.adapter)
    pending: list = []
    no_model = 0
    for unit in _units(view):
        targets = [
            view.by_id[i]
            for i in unit.members
            if not str(view.by_id[i].get("heading_en") or "").strip()
        ]
        if not targets:
            continue
        ids = [n["id"] for n in targets]
        request = {
            "system": prompts.system,
            "messages": [{"role": "user", "content": _message(prompts, view, unit, targets)}],
            "schema_name": "gloss",
            "meta": {"task": TASK, "unit": unit.key, "candidates": ids},
        }
        key = request_hash(TASK, request, schema, config.model)
        report["requests"] += 1
        info: dict = {}
        try:
            response = call(TASK, request, schema, config, info=info)
        except NoModel:
            no_model += 1
            continue
        except PendingInteractive as exc:
            pending.extend(exc.requests)
            continue
        except (InvalidResponse, Refusal) as exc:
            report["invalid"].append({"unit": unit.key, "request": key[:12], "error": str(exc)})
            continue
        report["answered"] += 1
        unit_note = note
        if info.get("returned_model") and info["returned_model"] != config.model:
            unit_note += ", answered by %s" % info["returned_model"]
        done = set()
        for item in response.get("glosses") or []:
            nid, text = str(item.get("node_id")), str(item.get("heading_en") or "").strip()
            reason = None
            if nid not in ids:
                reason = "not listed under 'Nodes to gloss'"
            elif nid in done:
                reason = "glossed twice in one response"
            elif not text:
                reason = "empty heading_en"
            if reason:
                report["rejected"].append(
                    {"unit": unit.key, "request": key[:12], "id": nid, "reason": reason}
                )
                continue
            node = view.by_id[nid]
            node["heading_en"] = text
            node["notes"] = list(node.get("notes") or []) + [unit_note]
            done.add(nid)
            report["filled"] += 1
        report["not_answered"].extend({"unit": unit.key, "id": i} for i in ids if i not in done)
    if pending:
        raise PendingInteractive(
            pending,
            "gloss: %d request(s) await a response in %s"
            % (len(pending), config.llm_dir / "responses"),
        )
    assert_explicit_unchanged(doc, new)
    rep = validate(new)
    if not rep.passed():  # heading_en is free text, so this means the input did not validate
        raise ValueError(
            "glossed outline does not validate: %s" % "; ".join(f.render() for f in rep.errors[:3])
        )
    if report["requests"] and no_model == report["requests"]:
        report["status"] = "skipped: no model"
    else:
        report["status"] = "ok" if report["requests"] else "nothing to gloss"
    return new, report
