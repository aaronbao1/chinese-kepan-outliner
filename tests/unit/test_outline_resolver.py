"""outline.resolver and outline.gloss on SYNTHETIC texts (fictional T99n9998 commentary, T99n9999
root text, T99n9997 self-outlining text; no real CBETA text), fully offline.

The replay test reads tests/fixtures/llm-cassettes/outline-resolver-synthetic.jsonl, whose answers
are written by _answer() below (no model was called). A request hash covers the prompt templates in
skills/chinese-kepan-outliner/references/, the schemas and the request text, so editing any of them
makes the cassette stale; re-record it with

    cd pipeline
    REGEN_LLM_CASSETTES=1 .venv/bin/python -m pytest ../tests/unit/test_outline_resolver.py -q

The other tests answer through the interactive adapter in a temporary run directory, which is also
how the cassette is recorded.
"""

from __future__ import annotations

import copy
import itertools
import json
import os
from pathlib import Path

import pytest

from chinese_workflow.common import outline_doc
from chinese_workflow.common.jsonio import read_json
from chinese_workflow.common.paths import FIXTURES
from chinese_workflow.common.splits import SplitViolation
from chinese_workflow.ingest.lines import build_index
from chinese_workflow.ingest.text import InputText
from chinese_workflow.llm import LLMConfig, PendingInteractive, ReplayMiss
from chinese_workflow.llm.cache import read_records
from chinese_workflow.outline import gloss as gloss_mod
from chinese_workflow.outline import resolver

CASSETTE = FIXTURES / "llm-cassettes" / "outline-resolver-synthetic.jsonl"
REGEN = os.environ.get("REGEN_LLM_CASSETTES") == "1"
PARSER_REPORT = [
    {
        "id": "pr1",
        "kind": "announce-target-ambiguous",
        "linehead": "T99n9998_p0002a20",
        "text": "此偈有二：初頌因，後頌果",
        "reason": "target ambiguous (SYNTHETIC)",
    }
]
EN = {
    "3_1.1_2.1_3": "The occasion of the teaching",
    "3_1.1_2.2_3": "The teaching proper",
    "3_1.2_2.1_3": "Verses on the cause",
    "3_1.2_2.2_3": "Verses on the result",
}


def _text(file_id: str, fill: str, special: dict | None = None, pages=(1, 2)) -> InputText:
    """A synthetic InputText: pages x registers a-c x lines 01-29."""
    special = special or {}
    lhs = [
        "%s_p%04d%s%02d" % (file_id, p, r, n) for p in pages for r in "abc" for n in range(1, 30)
    ]
    recs = [{"linehead": lh, "text": special.get(lh, fill % (k + 1))} for k, lh in enumerate(lhs)]
    return InputText(
        text_id=file_id, role=None, info={}, lines=recs, all_lineheads=lhs, index=build_index(recs)
    )


ROOT = _text("T99n9999", "合成經文第%03d行文句。")
COMM = _text(
    "T99n9998", "合成疏文第%03d行釋義。", {"T99n9998_p0002a20": "此偈有二：初頌因，後頌果。"}
)


def _doc() -> dict:
    """tests/fixtures/outline-zh/minimal.json with 後別序 (2_1.2_2) left unmapped by the anchor."""
    doc = read_json(FIXTURES / "outline-zh" / "minimal.json")
    n = next(n for n in doc["nodes"] if n["id"] == "2_1.2_2")
    n["locations"]["root_text"] = None
    n["flags"] = ["no_gloss", "unmapped"]
    assert outline_doc.validate(doc).passed()
    return doc


def _answer(task: str, meta: dict) -> dict:
    """The synthetic 'model': fixed answers for the synthetic doc."""
    if task == "resolver/root-spans":
        return {
            "spans": [
                {
                    "node_id": "2_1.2_2",
                    "start": "T99n9999_p0001a04",
                    "end": "T99n9999_p0001b02",
                    "confidence": 0.8,
                    "rationale": "別序 follows 通序 (經「如是我聞」, a01–a03) to the end of 序分 "
                    "(SYNTHETIC)",
                }
            ]
        }
    if task == "resolver/subdivide":
        return {
            "divisions": [
                {
                    "parent_id": "3_1.1_2",
                    "children": [
                        {
                            "heading_src": "初敘緣起",
                            "start": "T99n9999_p0001b03",
                            "end": "T99n9999_p0001c29",
                            "depth": 1,
                            "explained": "T99n9998_p0001c04",
                            "confidence": 0.6,
                            "rationale": "the occasion precedes the teaching (SYNTHETIC)",
                        },
                        {
                            "heading_src": "後正說法",
                            "start": "T99n9999_p0002a01",
                            "end": "T99n9999_p0002b05",
                            "depth": 1,
                            "explained": None,
                            "confidence": 0.55,
                            "rationale": "the teaching starts at a change of speaker (SYNTHETIC)",
                        },
                    ],
                    "uncovered": [],
                }
            ]
        }
    if task == "resolver/adjudicate":
        return {
            "decisions": [
                {
                    "report_id": "pr1",
                    "decision": "attach",
                    "target_node_id": "3_1.2_2",
                    "confidence": 0.7,
                    "rationale": "「此偈有二」 divides the verses 偈有十行 (SYNTHETIC)",
                    "children": [
                        {
                            "heading_src": "初頌因",
                            "start": "T99n9999_p0002b06",
                            "end": "T99n9999_p0002b20",
                            "explained": "T99n9998_p0002a21",
                            "confidence": 0.7,
                            "rationale": "「初頌因」 (SYNTHETIC)",
                        },
                        {
                            "heading_src": "後頌果",
                            "start": "T99n9999_p0002b21",
                            "end": "T99n9999_p0002c10",
                            "explained": None,
                            "confidence": 0.7,
                            "rationale": "「後頌果」 (SYNTHETIC)",
                        },
                    ],
                }
            ]
        }
    if task == "gloss":
        return {
            "glosses": [{"node_id": i, "heading_en": EN[i]} for i in meta["candidates"] if i in EN]
        }
    raise AssertionError(task)


def _drive(run, answer, rounds: int = 10):
    """Call run() until no interactive request is pending, answering each request file."""
    for _ in range(rounds):
        try:
            return run()
        except PendingInteractive as exc:
            for req in exc.requests:
                rec = json.loads(Path(req).read_text(encoding="utf-8"))
                Path(rec["response_path"]).write_text(
                    json.dumps(answer(rec["task"], rec["request"]["meta"]), ensure_ascii=False),
                    encoding="utf-8",
                )
    raise AssertionError("still pending after %d rounds" % rounds)


def _full_run(cfg, doc=None):
    doc = doc if doc is not None else _doc()
    out, rep = resolver.resolve(
        doc, root=ROOT, commentary=COMM, config=cfg, parser_report=PARSER_REPORT
    )
    out2, grep = gloss_mod.gloss(out, config=cfg, commentary=COMM)
    return out, rep, out2, grep


def _record_cassette(tmp_path: Path) -> None:
    cfg = LLMConfig(adapter="interactive", run_dir=tmp_path / "record")
    _drive(lambda: _full_run(cfg), _answer)
    recs = read_records(tmp_path / "record" / "llm" / "responses.jsonl")
    CASSETTE.parent.mkdir(parents=True, exist_ok=True)
    with open(CASSETTE, "w", encoding="utf-8") as fh:
        for rec in recs:
            rec = dict(
                rec,
                date="2026-10-01",
                synthetic="answer written by tests/unit/test_outline_resolver.py _answer(); "
                "no model was called",
            )
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def _nodes(doc) -> dict:
    return {n["id"]: n for n in doc["nodes"]}


def _explicit(doc) -> dict:
    return {n["heading_src"]: n for n in doc["nodes"] if n["origin"] != "inferred"}


# ------------------------------------------------------------------------------------ the replay


def test_resolver_and_gloss_replay_synthetic_cassette(tmp_path):
    if REGEN:
        _record_cassette(tmp_path)
    cfg = LLMConfig(adapter="replay", cassette=CASSETTE, run_dir=tmp_path / "run")
    before = _doc()
    try:
        out, rep, glossed, grep = _full_run(cfg, before)
    except ReplayMiss as exc:
        pytest.fail(
            "cassette %s is stale (%s); re-record it: see this module's docstring"
            % (CASSETTE.name, exc)
        )
    assert rep["status"] == "ok" and rep["adapter"] == "replay"
    assert set(rep["prompts"]) >= {"resolver-prompt.md", "output-contract.md", "level1-prior.md"}
    for task in resolver.TASKS:
        t = rep["tasks"][task]
        assert t["requests"] == t["answered"] == 1 and not t["rejected"] and not t["invalid"], task
    nodes = _nodes(out)

    # root-spans: filled inside the parent, basis inferred, unmapped removed, provenance noted
    n = nodes["2_1.2_2"]
    assert n["locations"]["root_text"] == {
        "start": "T99n9999_p0001a04",
        "end": "T99n9999_p0001b02",
        "basis": "inferred",
        "end_basis": None,
        "raw": "",
    }
    assert n["flags"] == ["no_gloss"] and n["origin"] == "explicit"
    assert "claude-opus-5 (replay adapter)" in n["notes"][-1] and "0.80" in n["notes"][-1]
    old = _nodes(before)["2_1.2_2"]
    for key in set(old) | set(n):  # every other field of the explicit node is unchanged
        if key in ("flags", "notes", "locations"):
            continue
        assert n.get(key) == old.get(key), key
    assert n["notes"][: len(old["notes"])] == old["notes"]
    assert n["locations"]["commentary"] == old["locations"]["commentary"]

    # subdivide: two inferred children under the long leaf 初長行; 後偈頌 was offered, not answered
    kids = [nodes["3_1.1_2.1_3"], nodes["3_1.1_2.2_3"]]
    assert [k["heading_src"] for k in kids] == ["初敘緣起", "後正說法"]
    scheme = rep["scheme_id"]
    assert scheme.startswith("model-") and len(scheme) == len("model-") + 8
    for k in kids:
        assert k["origin"] == "inferred" and 0 < k["confidence"] < 1 and k["evidence"]
        assert k["scheme_id"] == scheme and k["node_class"] == "sutra-span"
        assert k["locations"]["root_text"]["basis"] == "inferred"
        assert "replay adapter" in k["notes"][0]
    assert kids[0]["locations"]["commentary"] == {
        "announced": None,
        "explained": "T99n9998_p0001c04",
    }
    assert kids[1]["locations"]["commentary"] is None
    assert {"unit": "3_1", "id": "3_1.2_2"} in rep["tasks"]["subdivide"]["not_answered"]

    # adjudicate: the parser-report entry attached two children under 後偈頌, announced at its line
    adj = [nodes["3_1.2_2.1_3"], nodes["3_1.2_2.2_3"]]
    assert [k["heading_src"] for k in adj] == ["初頌因", "後頌果"]
    assert all(k["locations"]["commentary"]["announced"] == "T99n9998_p0002a20" for k in adj)
    assert "parser-report entry pr1" in adj[0]["notes"][0]

    # the explicit nodes are unchanged and the document validates
    outline_doc.assert_explicit_unchanged(before, out)
    assert outline_doc.validate(out).passed()
    assert [n["heading_src"] for n in before["nodes"]] == [
        n["heading_src"] for n in out["nodes"] if n["origin"] != "inferred" or n["id"] == "4_1"
    ]

    # gloss: heading_en of the four new nodes, with provenance; nothing else changes
    assert grep["status"] == "ok" and grep["filled"] == 4
    g = _nodes(glossed)
    for nid, en in EN.items():
        assert g[nid]["heading_en"] == en
        assert g[nid]["notes"][-1] == "heading_en: gloss by claude-opus-5 (replay)"
    assert g["2_1"]["heading_en"] == nodes["2_1"]["heading_en"]
    outline_doc.assert_explicit_unchanged(before, glossed)
    assert outline_doc.validate(glossed).passed()

    # the replayed responses land in the run's cache, and a re-run is served from it (an empty
    # cassette: every request is answered by the run's own cache, so the result is identical)
    assert len(read_records(tmp_path / "run" / "llm" / "responses.jsonl")) == 4
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    cfg2 = LLMConfig(adapter="replay", cassette=empty, run_dir=tmp_path / "run")
    assert _full_run(cfg2, _doc()) == (out, rep, glossed, grep)
    # with adapter 'none' the cached answers are still used (the cache is consulted first)
    again, rep3 = resolver.resolve(
        _doc(),
        root=ROOT,
        commentary=COMM,
        parser_report=PARSER_REPORT,
        config=LLMConfig(adapter="none", run_dir=tmp_path / "run"),
    )
    assert rep3["status"] == "ok" and len(again["nodes"]) == len(out["nodes"])


def test_committed_cassette_is_synthetic_and_valid():
    recs = read_records(CASSETTE)
    assert len(recs) == 4
    for rec in recs:
        assert rec.get("persist", True) is not False
        assert "synthetic" in rec and rec["returned_model"] is None
        name = rec["request"]["schema_name"]
        schema = read_json(
            FIXTURES.parent.parent / "pipeline" / "schemas" / ("%s.schema.json" % name)
        )
        from chinese_workflow.llm import validation_errors

        assert validation_errors(schema, rec["response"]) == []
        for msg in rec["request"]["messages"]:  # only the fictional texts are quoted
            assert "T34n" not in msg["content"] and "T09n" not in msg["content"]


# --------------------------------------------------------------------------- no model, pending


def test_adapter_none_leaves_the_doc_unchanged():
    doc = _doc()
    out, rep = resolver.resolve(
        doc, root=ROOT, commentary=COMM, config=LLMConfig(), parser_report=PARSER_REPORT
    )
    assert out == doc and rep["status"] == "skipped: no model"
    assert {t: v["requests"] for t, v in rep["tasks"].items()} == {
        "root-spans": 1,
        "subdivide": 1,
        "adjudicate": 1,
    }
    out2, grep = gloss_mod.gloss(doc, config=LLMConfig(), commentary=COMM)
    assert out2 == doc and grep == {"status": "skipped: no model"}
    assert gloss_mod.gloss(doc, config=None)[1] == {"status": "skipped: no model"}


def test_out_of_span_nodes_are_not_root_span_candidates():
    """outline.classify marked a node (note prefix OUT_OF_SPAN_PREFIX): the resolver never asks for its
    root span and lists it under skipped with kind out-of-span (E06 review B2)."""
    from chinese_workflow.outline.classify import OUT_OF_SPAN_NOTE

    doc = _doc()
    n = next(n for n in doc["nodes"] if n["id"] == "2_1.2_2")
    n["notes"] = list(n["notes"]) + [OUT_OF_SPAN_NOTE % "SYNTHETIC: names 2 parts, the ancestor holds 1"]
    assert outline_doc.validate(doc).passed()
    out, rep = resolver.resolve(
        doc, root=ROOT, commentary=COMM, config=LLMConfig(), tasks=("root-spans",)
    )
    assert out == doc and rep["status"] == "nothing to ask"
    task = rep["tasks"]["root-spans"]
    assert task["requests"] == 0
    assert [(s["node_id"], s["kind"]) for s in task["skipped"]] == [("2_1.2_2", "out-of-span")]
    assert task["skipped"][0]["reason"] == OUT_OF_SPAN_NOTE % "SYNTHETIC: names 2 parts, the ancestor holds 1"


def test_pending_interactive_carries_the_task_report(tmp_path):
    cfg = LLMConfig(adapter="interactive", run_dir=tmp_path)
    with pytest.raises(PendingInteractive) as exc:
        resolver.resolve(_doc(), root=ROOT, commentary=COMM, config=cfg, tasks=("root-spans",))
    rep = exc.value.task_report
    assert rep["requests"] == 1 and rep["pending"] == 1 and rep["skipped"] == []


def test_interactive_writes_every_request_of_a_task(tmp_path):
    cfg = LLMConfig(adapter="interactive", run_dir=tmp_path)
    with pytest.raises(PendingInteractive) as exc:
        resolver.resolve(_doc(), root=ROOT, commentary=COMM, config=cfg)
    [req] = exc.value.requests
    rec = json.loads(Path(req).read_text(encoding="utf-8"))
    assert rec["task"] == "resolver/root-spans" and rec["request"]["meta"]["candidates"] == [
        "2_1.2_2"
    ]
    md = Path(req).with_suffix(".md").read_text(encoding="utf-8")
    assert "## Nodes to resolve" in md and "T99n9999_p0001a03\t" in md
    assert "admissible root range T99n9999_p0001a03–T99n9999_p0001b02" in md


def test_input_must_validate_and_tasks_must_exist():
    doc = _doc()
    with pytest.raises(ValueError):
        resolver.resolve(doc, root=ROOT, commentary=COMM, config=LLMConfig(), tasks=("guess",))
    bad = copy.deepcopy(doc)
    bad["nodes"][3]["flags"] = []  # a sutra-span node without a root span must be flagged
    with pytest.raises(ValueError):
        resolver.resolve(bad, root=ROOT, commentary=COMM, config=LLMConfig())


def test_exemplar_pool_refuses_eval_only_ood_and_split_golds():
    for ds in ("cbeta-mulu-X0268", "ybh-T1602", "sdp-T1718-zhiyi-wenju", "kuiji-xuanzan"):
        with pytest.raises(SplitViolation):
            resolver.resolve(
                _doc(), root=ROOT, commentary=COMM, config=LLMConfig(), exemplar_pool=(ds,)
            )
    assert resolver.exemplar_block(()) == ""


def test_claude_adapter_through_the_resolver_with_a_fake_sdk(tmp_path):
    """The claude path end to end, offline: the fake SDK answers root-spans and reports a fallback
    model; the note names it and the ledger prices the call."""
    from types import SimpleNamespace

    answer = _answer("resolver/root-spans", {})
    calls = []

    class _S:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            usage = SimpleNamespace(
                input_tokens=4000,
                output_tokens=300,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            )
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=json.dumps(answer))],
                stop_reason="end_turn",
                model="claude-opus-4-8",
                usage=usage,
            )

    class _M:
        def stream(self, **kw):
            calls.append(kw)
            return _S()

    fake = SimpleNamespace(beta=SimpleNamespace(messages=_M()), messages=_M())
    cfg = LLMConfig(adapter="claude", run_dir=tmp_path, client=fake)
    out, rep = resolver.resolve(
        _doc(), root=ROOT, commentary=COMM, config=cfg, tasks=("root-spans",)
    )
    assert rep["status"] == "ok" and rep["tasks"]["root-spans"]["accepted"][0]["id"] == "2_1.2_2"
    [kw] = calls
    assert "spans" in kw["output_config"]["format"]["schema"]["properties"]
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["system"][0]["text"].startswith("You are the model-assisted step")
    assert "## Nodes to resolve" in kw["messages"][0]["content"]
    note = _nodes(out)["2_1.2_2"]["notes"][-1]
    assert "claude-opus-5 (claude adapter)" in note and "answered by claude-opus-4-8" in note
    ledger = json.loads((tmp_path / "llm" / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["totals"]["cost_usd"] == pytest.approx((5 * 4000 + 25 * 300) / 1e6)


# --------------------------------------------------------------------- malicious / broken answers


def _run_with(tmp_path, tasks, answer, doc=None):
    cfg = LLMConfig(adapter="interactive", run_dir=tmp_path)
    doc = doc if doc is not None else _doc()
    out, rep = _drive(
        lambda: resolver.resolve(
            doc, root=ROOT, commentary=COMM, config=cfg, tasks=tasks, parser_report=PARSER_REPORT
        ),
        answer,
    )
    outline_doc.assert_explicit_unchanged(doc, out)
    assert outline_doc.validate(out).passed()
    return doc, out, rep


def _span(nid, start, end, conf=0.7):
    return {"node_id": nid, "start": start, "end": end, "confidence": conf, "rationale": "x"}


@pytest.mark.parametrize(
    "item, why",
    [
        (
            _span("2_1.2_2", "T99n9999_p0002a01", "T99n9999_p0002a05"),
            "outside the admissible range",
        ),
        (
            _span("2_1.2_2", "T99n9999_p0001a02", "T99n9999_p0001b02"),
            "outside the admissible range",
        ),
        (_span("2_1.2_2", "T99n9999_p0001b02", "T99n9999_p0001a04"), "after end"),
        (_span("2_1.2_2", "T99n9999_p0001a04:3", "T99n9998_p0001b02"), "not lines of"),
        (_span("2_1.2_2", "T99n9999_p0001a04", "T99n9999_p0001b02", conf=1.0), "confidence"),
        (_span("3_1", "T99n9999_p0001a01", "T99n9999_p0001a02"), "not listed"),
    ],
)
def test_root_span_answers_that_break_the_rules_are_rejected(tmp_path, item, why):
    doc, out, rep = _run_with(tmp_path, ("root-spans",), lambda t, m: {"spans": [item]})
    [rej] = rep["tasks"]["root-spans"]["rejected"]
    assert why in rej["reason"], rej
    assert out == doc  # nothing merged
    assert "unmapped" in _nodes(out)["2_1.2_2"]["flags"]


def test_a_node_answered_twice_is_merged_once(tmp_path):
    good = _span("2_1.2_2", "T99n9999_p0001a04", "T99n9999_p0001b02")
    _, _, rep = _run_with(tmp_path, ("root-spans",), lambda t, m: {"spans": [good, good]})
    t = rep["tasks"]["root-spans"]
    assert len(t["accepted"]) == 1 and "twice" in t["rejected"][0]["reason"]


def _division(children, parent="3_1.1_2", uncovered=()):
    return {
        "divisions": [{"parent_id": parent, "children": children, "uncovered": list(uncovered)}]
    }


def _child(start, end, conf=0.6, heading="初", rationale="cue", depth=1, explained=None):
    return {
        "heading_src": heading,
        "start": start,
        "end": end,
        "depth": depth,
        "explained": explained,
        "confidence": conf,
        "rationale": rationale,
    }


def _gap(start, end, kind="paratext", rationale="cue"):
    return {"start": start, "end": end, "kind": kind, "rationale": rationale}


A = ("T99n9999_p0001b03", "T99n9999_p0001c29")
B = ("T99n9999_p0002a01", "T99n9999_p0002b05")


@pytest.mark.parametrize(
    "answer, why",
    [
        (_division([_child(*B), _child(*A)]), "text order"),  # reordered children
        (_division([_child(*A), _child("T99n9999_p0002a01", "T99n9999_p0002c01")]), "outside"),
        (_division([_child(*A)]), "at least two"),
        (_division([_child(*A), _child(*B, conf=1)]), "confidence"),
        (_division([_child(*A), _child(*B, rationale=" ")]), "rationale"),
        (_division([_child(*A), _child(*B)], parent="3_1"), "not listed"),  # an inner explicit node
        (_division([_child(*A), dict(_child(*B), explained="T99n9999_p0002a01")]), "explained"),
    ],
)
def test_subdivide_answers_that_break_the_rules_are_rejected(tmp_path, answer, why):
    doc, out, rep = _run_with(tmp_path, ("subdivide",), lambda t, m: answer)
    [rej] = rep["tasks"]["subdivide"]["rejected"]
    assert why in rej["reason"], rej
    assert out == doc


def _decision(target, children, decision="attach", rid="pr1"):
    """An adjudicate answer; its children are enumerated items, so they carry no subdivide depth."""
    return {
        "decisions": [
            {
                "report_id": rid,
                "decision": decision,
                "target_node_id": target,
                "children": [{k: v for k, v in c.items() if k != "depth"} for c in children],
                "confidence": 0.6,
                "rationale": "cue",
            }
        ]
    }


@pytest.mark.parametrize(
    "answer, why",
    [
        # attaching under 正宗分 3_1 would interleave with (and so reorder) its explicit children
        (
            _decision(
                "3_1",
                [
                    _child("T99n9999_p0001b03", "T99n9999_p0001b10"),
                    _child("T99n9999_p0001b11", "T99n9999_p0001c01"),
                ],
            ),
            "interleave",
        ),
        (_decision("9_1", [_child(*A)]), "not in the outline"),
        (_decision("3_1.2_2", [_child(*A)]), "outside"),
        (_decision(None, [_child(*A)]), "without target"),
        (
            _decision("3_1.2_2", [_child("T99n9999_p0002b06", "T99n9999_p0002b10")], rid="pr9"),
            "not listed",
        ),
    ],
)
def test_adjudicate_answers_that_break_the_rules_are_rejected(tmp_path, answer, why):
    doc, out, rep = _run_with(tmp_path, ("adjudicate",), lambda t, m: answer)
    [rej] = rep["tasks"]["adjudicate"]["rejected"]
    assert why in rej["reason"], rej
    assert out == doc


def test_adjudicate_ignore_and_attach_after_existing_children(tmp_path):
    doc, out, rep = _run_with(
        tmp_path, ("adjudicate",), lambda t, m: _decision(None, [], decision="ignore")
    )
    assert out == doc and rep["tasks"]["adjudicate"]["ignored"][0]["id"] == "pr1"
    # attach under 正宗分 after its explicit children: allowed, explicit ids keep their order
    doc2 = _doc()
    for n in doc2["nodes"]:  # make room: shorten 後偈頌 so a tail is left inside 正宗分
        if n["id"] == "3_1.2_2":
            n["locations"]["root_text"]["end"] = "T99n9999_p0002c05"
    _, out2, rep2 = _run_with(
        tmp_path / "b",
        ("adjudicate",),
        lambda t, m: _decision(
            "3_1",
            [
                _child("T99n9999_p0002c06", "T99n9999_p0002c08"),
                _child("T99n9999_p0002c09", "T99n9999_p0002c10"),
            ],
        ),
        doc=doc2,
    )
    assert len(rep2["tasks"]["adjudicate"]["accepted"]) == 1
    kids = [n for n in out2["nodes"] if n["parent_id"] == "3_1"]
    assert [k["origin"] for k in kids] == ["explicit", "explicit", "inferred", "inferred"]


# --------------------------------------------------------------------------------- self-outlining


def test_self_outlining_windows_and_subdivide(tmp_path):
    text = _text("T99n9997", "合成論文第%03d行" + "義" * 40 + "。")  # 50 characters a line

    def node(heading, explained):
        return {
            "heading_src": heading,
            "evidence": "SYNTHETIC",
            "node_class": "sutra-span",
            "locations": {
                "scheme": "cbeta-kepan",
                "commentary": {"announced": None, "explained": explained},
                "root_text": None,
            },
            "children": [],
        }

    doc, _ = outline_doc.build_prediction(
        [node("初總標", "T99n9997_p0001a01"), node("後別釋", "T99n9997_p0002a01")],
        text_id="T9997",
        text_title_src="合成論（SYNTHETIC）",
        outline_mode="self-outlining",
        root_text_id="T99n9997",
        commentary_id=None,
        scheme_id="synthetic-self",
        source_file="synthetic:none",
        source_document={"kind": "synthetic", "text_id": "T99n9997", "title": "合成論"},
        generated_by="test",
        format_note="SYNTHETIC",
    )
    assert outline_doc.validate(doc).passed()
    view = resolver._View(doc, resolver._texts(doc, None, text))
    units = resolver._units(view)
    assert [(u.key, u.members) for u in units] == [("w1", ["1_1"]), ("w2", ["2_1"])]

    def answer(task, meta):
        if meta["unit"] != "w1":
            return {"divisions": []}
        return _division(
            [
                _child("T99n9997_p0001a01", "T99n9997_p0001b10", heading="初"),
                _child("T99n9997_p0001b11", "T99n9997_p0001c29", heading="後"),
            ],
            parent="1_1",
        )

    cfg = LLMConfig(adapter="interactive", run_dir=tmp_path)
    out, rep = _drive(
        lambda: resolver.resolve(
            doc,
            root=None,
            commentary=text,
            config=cfg,
            tasks=("subdivide",),
            scheme_id="synthetic-self",
        ),
        answer,
    )
    t = rep["tasks"]["subdivide"]
    assert t["requests"] == 2 and len(t["accepted"]) == 1
    kids = [n for n in out["nodes"] if n["parent_id"] == "1_1"]
    assert [k["locations"]["commentary"]["explained"] for k in kids] == [
        "T99n9997_p0001a01",
        "T99n9997_p0001b11",
    ]
    assert all(
        k["scheme_id"] == "synthetic-self" and k["locations"]["root_text"]["basis"] == "inferred"
        for k in kids
    )
    assert outline_doc.validate(out).passed()


# ------------------------------------------------------------------ nested divisions and gaps


def test_subdivide_nests_divisions_by_depth(tmp_path):
    answer = _division(
        [
            _child("T99n9999_p0001b03", "T99n9999_p0001c29", heading="初敘緣起"),
            _child("T99n9999_p0001b03", "T99n9999_p0001b20", heading="初敘時", depth=2),
            _child("T99n9999_p0001b21", "T99n9999_p0001c29", heading="後敘處", depth=2),
            _child("T99n9999_p0002a01", "T99n9999_p0002b05", heading="後正說法"),
        ]
    )
    _, out, rep = _run_with(tmp_path, ("subdivide",), lambda t, m: answer)
    assert len(rep["tasks"]["subdivide"]["accepted"]) == 1
    nodes = _nodes(out)
    assert [nodes[i]["heading_src"] for i in ("3_1.1_2.1_3", "3_1.1_2.2_3")] == [
        "初敘緣起",
        "後正說法",
    ]
    assert [nodes[i]["heading_src"] for i in ("3_1.1_2.1_3.1_4", "3_1.1_2.1_3.2_4")] == [
        "初敘時",
        "後敘處",
    ]
    grand = nodes["3_1.1_2.1_3.2_4"]
    assert grand["parent_id"] == "3_1.1_2.1_3" and grand["origin"] == "inferred"
    assert grand["locations"]["root_text"]["start"] == "T99n9999_p0001b21"


@pytest.mark.parametrize(
    "children, why",
    [
        (  # depth 3 straight after depth 1
            [
                _child("T99n9999_p0001b03", "T99n9999_p0001c29"),
                _child("T99n9999_p0001b03", "T99n9999_p0001b20", depth=3),
                _child("T99n9999_p0001b21", "T99n9999_p0001c29", depth=3),
                _child("T99n9999_p0002a01", "T99n9999_p0002b05"),
            ],
            "depth",
        ),
        (  # a single grandchild divides nothing
            [
                _child("T99n9999_p0001b03", "T99n9999_p0001c29"),
                _child("T99n9999_p0001b03", "T99n9999_p0001b20", depth=2),
                _child("T99n9999_p0002a01", "T99n9999_p0002b05"),
            ],
            "at least two",
        ),
        (  # a grandchild outside its parent's span
            [
                _child("T99n9999_p0001b03", "T99n9999_p0001c29"),
                _child("T99n9999_p0001b03", "T99n9999_p0001b20", depth=2),
                _child("T99n9999_p0001b21", "T99n9999_p0002a03", depth=2),
                _child("T99n9999_p0002a04", "T99n9999_p0002b05"),
            ],
            "outside",
        ),
    ],
)
def test_nested_divisions_that_break_the_rules_are_rejected(tmp_path, children, why):
    doc, out, rep = _run_with(tmp_path, ("subdivide",), lambda t, m: _division(children))
    [rej] = rep["tasks"]["subdivide"]["rejected"]
    assert why in rej["reason"], rej
    assert out == doc


def test_uncovered_lines_leave_gaps_and_report_overruns(tmp_path):
    answer = _division(
        [
            _child("T99n9999_p0001b03", "T99n9999_p0001c20"),
            _child("T99n9999_p0001c21", "T99n9999_p0002a29"),
        ],
        uncovered=[
            _gap("T99n9999_p0002b01", "T99n9999_p0002b02", "paratext", "卷尾題 (SYNTHETIC)"),
            _gap("T99n9999_p0002b03", "T99n9999_p0002b05", "overrun", "a new 「爾時」 section"),
        ],
    )
    _, out, rep = _run_with(tmp_path, ("subdivide",), lambda t, m: answer)
    t = rep["tasks"]["subdivide"]
    assert len(t["accepted"]) == 1 and not t["rejected"]
    nodes = _nodes(out)
    assert nodes["3_1.1_2.2_3"]["locations"]["root_text"]["end"] == "T99n9999_p0002a29"
    [over] = t["overruns"]
    assert (over["id"], over["start"], over["end"]) == (
        "3_1.1_2",
        "T99n9999_p0002b03",
        "T99n9999_p0002b05",
    )
    assert over["rationale"] == "a new 「爾時」 section"


def test_an_overrun_without_children_is_reported_and_changes_nothing(tmp_path):
    answer = _division(
        [], uncovered=[_gap("T99n9999_p0002a20", "T99n9999_p0002b05", "overrun", "later sibling")]
    )
    doc, out, rep = _run_with(tmp_path, ("subdivide",), lambda t, m: answer)
    t = rep["tasks"]["subdivide"]
    assert out == doc and not t["accepted"] and not t["rejected"]
    assert [r["id"] for r in t["reported"]] == ["3_1.1_2"]
    assert [o["start"] for o in t["overruns"]] == ["T99n9999_p0002a20"]


@pytest.mark.parametrize(
    "gap, why",
    [
        (_gap("T99n9999_p0002a20", "T99n9999_p0002b05"), "overlap"),  # inside the second child
        (_gap("T99n9999_p0002b04", "T99n9999_p0002b08"), "outside"),  # past the leaf's end
        (_gap("T99n9999_p0002b05", "T99n9999_p0002b04"), "after end"),
    ],
)
def test_uncovered_ranges_that_break_the_rules_are_rejected(tmp_path, gap, why):
    answer = _division(
        [
            _child("T99n9999_p0001b03", "T99n9999_p0001c20"),
            _child("T99n9999_p0001c21", "T99n9999_p0002a29"),
        ],
        uncovered=[gap],
    )
    doc, out, rep = _run_with(tmp_path, ("subdivide",), lambda t, m: answer)
    [rej] = rep["tasks"]["subdivide"]["rejected"]
    assert why in rej["reason"], rej
    assert out == doc


# --------------------------------------------------------------- self-outlining: explained lines


def _self_doc(text, explained: list, file_id="T99n9997") -> dict:
    def node(heading, line):
        return {
            "heading_src": heading,
            "evidence": "SYNTHETIC",
            "node_class": "sutra-span",
            "locations": {
                "scheme": "cbeta-kepan",
                "commentary": {"announced": None, "explained": line},
                "root_text": None,
            },
            "children": [],
        }

    doc, _ = outline_doc.build_prediction(
        [node("第%d段" % k, line) for k, line in enumerate(explained, 1)],
        text_id="T9997",
        text_title_src="合成論（SYNTHETIC）",
        outline_mode="self-outlining",
        root_text_id=file_id,
        commentary_id=None,
        scheme_id="synthetic-self",
        source_file="synthetic:none",
        source_document={"kind": "synthetic", "text_id": file_id, "title": "合成論"},
        generated_by="test",
        format_note="SYNTHETIC",
    )
    assert outline_doc.validate(doc).passed()
    return doc


SELF_TEXT = _text("T99n9997", "合成論文第%03d行" + "義" * 40 + "。")  # 50 characters a line


def _self_run(tmp_path, doc, answer, text=SELF_TEXT):
    cfg = LLMConfig(adapter="interactive", run_dir=tmp_path)
    out, rep = _drive(
        lambda: resolver.resolve(
            doc,
            root=None,
            commentary=text,
            config=cfg,
            tasks=("subdivide",),
            scheme_id="synthetic-self",
        ),
        answer,
    )
    outline_doc.assert_explicit_unchanged(doc, out)
    assert outline_doc.validate(out).passed()
    return out, rep


def test_self_outlining_keeps_the_explained_line_the_model_gives(tmp_path):
    doc = _self_doc(SELF_TEXT, ["T99n9997_p0001a01", "T99n9997_p0002a01"])

    def answer(task, meta):
        if meta["unit"] != "w1":
            return {"divisions": []}
        return _division(
            [
                _child("T99n9997_p0001a01", "T99n9997_p0001b10", explained="T99n9997_p0001a03"),
                _child("T99n9997_p0001b11", "T99n9997_p0001c29"),
            ],
            parent="1_1",
        )

    out, _ = _self_run(tmp_path, doc, answer)
    kids = [n for n in out["nodes"] if n["parent_id"] == "1_1"]
    assert [k["locations"]["commentary"]["explained"] for k in kids] == [
        "T99n9997_p0001a03",
        "T99n9997_p0001b11",
    ]


def test_self_outlining_rejects_an_explained_line_outside_the_child(tmp_path):
    doc = _self_doc(SELF_TEXT, ["T99n9997_p0001a01", "T99n9997_p0002a01"])

    def answer(task, meta):
        if meta["unit"] != "w1":
            return {"divisions": []}
        return _division(
            [
                _child("T99n9997_p0001a01", "T99n9997_p0001b10", explained="T99n9997_p0001b15"),
                _child("T99n9997_p0001b11", "T99n9997_p0001c29"),
            ],
            parent="1_1",
        )

    out, rep = _self_run(tmp_path, doc, answer)
    [rej] = rep["tasks"]["subdivide"]["rejected"]
    assert "explained" in rej["reason"] and out == doc


# ---------------------------------------------------------------------- request size budgets


def _requests(tmp_path, doc, tasks, root=ROOT, commentary=COMM, parser_report=None) -> list:
    """The request records the interactive adapter writes for the first task of `tasks`."""
    cfg = LLMConfig(adapter="interactive", run_dir=tmp_path)
    with pytest.raises(PendingInteractive) as exc:
        resolver.resolve(
            doc,
            root=root,
            commentary=commentary,
            config=cfg,
            tasks=tasks,
            parser_report=parser_report or [],
        )
    return [json.loads(Path(r).read_text(encoding="utf-8")) for r in exc.value.requests]


def _message(rec) -> str:
    return rec["request"]["messages"][0]["content"]


def _block_sizes(message: str) -> dict:
    """Rendered characters of each text block ('## <title> <text id>, lines …') of a user message."""
    sizes, cur = {}, None
    for line in message.split("\n"):
        if line.startswith("## "):
            cur = line.split(" ")[1] if ", lines " in line else None
            continue
        if cur is not None and "\t" in line:
            sizes[cur] = sizes.get(cur, 0) + len(line) + 1
    return sizes


def _sutra_doc(roots) -> dict:
    doc, _ = outline_doc.build_prediction(
        roots,
        text_id="T9999",
        text_title_src="合成測試經（SYNTHETIC）",
        outline_mode="sutra",
        root_text_id="T99n9999",
        commentary_id="T99n9998",
        scheme_id="synthetic-fixture",
        source_file="synthetic:none",
        source_document={"kind": "synthetic", "text_id": "T99n9998", "title": "合成測試疏"},
        generated_by="test",
        format_note="SYNTHETIC",
    )
    assert outline_doc.validate(doc).passed()
    return doc


def _span_node(heading, explained, root=None, kids=()):
    rt = None
    if root:
        rt = {"start": root[0], "end": root[1], "basis": "lemma", "end_basis": None, "raw": ""}
    return {
        "heading_src": heading,
        "evidence": "SYNTHETIC",
        "node_class": "sutra-span",
        "locations": {
            "scheme": "cbeta-kepan",
            "commentary": {"announced": None, "explained": explained},
            "root_text": rt,
        },
        "flags": [] if root else ["unmapped"],
        "children": list(kids),
    }


ROOT_LINES = ROOT.all_lineheads  # 174 lines of 12 characters: 31 characters a line as rendered


def _chapter(n_kids: int, heading: str = "第%d段", unmapped=lambda k: k % 2 == 0) -> dict:
    """One 品-like level-1 node over the whole synthetic root text, with n_kids children of 20 root
    lines each; the even ones (by default) are left unmapped."""
    kids = []
    for k in range(1, n_kids + 1):
        a, b = ROOT_LINES[(k - 1) * 20], ROOT_LINES[min(k * 20 - 1, len(ROOT_LINES) - 1)]
        kids.append(
            _span_node(
                heading % k,
                COMM.all_lineheads[10 + 3 * k],
                None if unmapped(k) else (a, b),
            )
        )
    return _sutra_doc(
        [_span_node("合成品", COMM.all_lineheads[0], (ROOT_LINES[0], ROOT_LINES[-1]), kids)]
    )


def test_lines_measure_rendered_characters():
    L = resolver._Lines(ROOT)
    assert L.chars(0, 1) == 24
    assert L.size(0, 1) == len(L.render(0, 1)) + 1 == 62


def test_the_text_budget_counts_rendered_characters(tmp_path, monkeypatch):
    """Four unmapped nodes whose admissible ranges span 1,860 text characters, which render to 4,805:
    under a 2,000-character block budget they cannot all share one request."""
    monkeypatch.setattr(resolver, "MAX_TEXT_CHARS", 2000)
    monkeypatch.setattr(resolver, "MAX_REQUEST_CHARS", 6000)
    doc = _chapter(8)
    recs = _requests(tmp_path, doc, ("root-spans",))
    asked = [c for rec in recs for c in rec["request"]["meta"]["candidates"]]
    assert sorted(asked) == ["1_1.2_2", "1_1.4_2", "1_1.6_2", "1_1.8_2"]
    assert len(recs) > 1
    for rec in recs:
        msg = _message(rec)
        assert len(msg) <= 6000
        if len(rec["request"]["meta"]["candidates"]) > 1:
            assert all(v <= 2000 for v in _block_sizes(msg).values()), _block_sizes(msg)


def test_a_long_outline_listing_shows_the_candidates_context(tmp_path, monkeypatch):
    monkeypatch.setattr(resolver, "MAX_OUTLINE_CHARS", 2000)
    doc = _chapter(8, heading="第%d段" + "長" * 300, unmapped=lambda k: k == 5)
    [rec] = _requests(tmp_path, doc, ("root-spans",))
    msg = _message(rec)
    listing = msg.split("## Outline of this unit (explicit nodes are fixed)")[1].split("## Nodes")[
        0
    ]
    assert len(listing.strip()) <= 2000
    assert "1_1.5_2 L2" in listing and "1_1.4_2 L2" in listing and "1_1.6_2 L2" in listing
    assert "1_1.1_2 L2" not in listing and "nodes not shown" in listing


def test_adjudicate_keeps_the_target_root_text_when_the_unit_is_too_long(tmp_path, monkeypatch):
    monkeypatch.setattr(resolver, "MAX_TEXT_CHARS", 1000)
    [rec] = _requests(tmp_path, _doc(), ("adjudicate",), parser_report=PARSER_REPORT)
    msg = _message(rec)
    assert "## Root text T99n9999" in msg and "T99n9999_p0002b06\t" in msg
    assert "T99n9998_p0002a20\t" in msg
    assert all(v <= 1000 for v in _block_sizes(msg).values())


def test_a_leaf_too_long_for_one_request_is_windowed(tmp_path, monkeypatch):
    """The 2_1 leaf (p0001a10 to p0006c29, 25,650 characters) cannot be shown in one 12,000-character
    request, so it is offered in WINDOW_CHARS windows; the windows' divisions are joined into one
    division of the leaf."""
    monkeypatch.setattr(resolver, "MAX_REQUEST_CHARS", 12000)
    text = _text("T99n9997", "合成論文第%03d行" + "義" * 40 + "。", pages=range(1, 7))
    doc = _self_doc(text, ["T99n9997_p0001a01", "T99n9997_p0001a10"])
    seen = []

    def answer(task, meta):
        windows = meta.get("windows") or {}
        if "2_1" not in windows:
            return {"divisions": []}
        w = windows["2_1"]
        seen.append(w["window"])
        return _division(
            [_child(w["core"][0], w["core"][1], heading="第%d段" % w["window"])], parent="2_1"
        )

    out, rep = _self_run(tmp_path, doc, answer, text=text)
    t = rep["tasks"]["subdivide"]
    assert t["skipped"] == [] and not t["rejected"] and not t["invalid"]
    n = max(seen)
    assert sorted(seen) == list(range(1, n + 1)) and n >= 6
    assert len(t["windows"]) == n and [r["id"] for r in t["accepted"]] == ["2_1"]
    kids = [k for k in out["nodes"] if k["parent_id"] == "2_1"]
    assert [k["heading_src"] for k in kids] == ["第%d段" % k for k in range(1, n + 1)]
    spans = [
        (k["locations"]["root_text"]["start"], k["locations"]["root_text"]["end"]) for k in kids
    ]
    assert spans[0][0] == "T99n9997_p0001a10" and spans[-1][1] == "T99n9997_p0006c29"
    lh = text.all_lineheads
    for (_, end), (start, _) in itertools.pairwise(spans):
        assert lh.index(end) + 1 == lh.index(start)  # contiguous, no gap between windows
    for path in (tmp_path / "llm" / "requests").glob("*.json"):
        assert len(_message(json.loads(path.read_text(encoding="utf-8")))) <= 12000


def test_a_window_answer_that_breaks_the_rules_is_dropped_and_the_others_joined(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(resolver, "MAX_REQUEST_CHARS", 12000)
    text = _text("T99n9997", "合成論文第%03d行" + "義" * 40 + "。", pages=range(1, 7))
    doc = _self_doc(text, ["T99n9997_p0001a01", "T99n9997_p0001a10"])

    def answer(task, meta):
        windows = meta.get("windows") or {}
        if "2_1" not in windows:
            return {"divisions": []}
        w = windows["2_1"]
        kids = [_child(w["core"][0], w["core"][1], heading="第%d段" % w["window"])]
        if w["window"] == 2:
            kids = [dict(kids[0], depth=2)]  # a window takes depth-1 divisions only
        return _division(kids, parent="2_1")

    out, rep = _self_run(tmp_path, doc, answer, text=text)
    t = rep["tasks"]["subdivide"]
    assert [(r["id"], r["window"]) for r in t["rejected"]] == [("2_1", 2)]
    assert "depth" in t["rejected"][0]["reason"]
    kids = [k for k in out["nodes"] if k["parent_id"] == "2_1"]
    assert "第2段" not in [k["heading_src"] for k in kids]
    first = kids[0]["locations"]["root_text"]
    assert kids[1]["heading_src"] == "第3段"
    assert text.all_lineheads.index(first["end"]) + 1 == text.all_lineheads.index(
        kids[1]["locations"]["root_text"]["start"]
    )


# ------------------------------------------- review of 2026-10-01: explained order, window gaps


def test_self_outlining_explained_lines_run_in_outline_order(tmp_path):
    """A sub-division without an explained line takes its parent's when its own start comes first
    (in self-outlining mode positions come from explained lines, and a node placed before its parent
    in pre-order would drop out of the outlined text)."""
    from chinese_workflow.outline import anchor

    doc = _self_doc(SELF_TEXT, ["T99n9997_p0001a01", "T99n9997_p0002a01"])

    def answer(task, meta):
        if meta["unit"] != "w1":
            return {"divisions": []}
        return _division(
            [
                _child("T99n9997_p0001a01", "T99n9997_p0001b10", explained="T99n9997_p0001a05"),
                _child("T99n9997_p0001a01", "T99n9997_p0001a20", heading="Y1", depth=2),
                _child("T99n9997_p0001a21", "T99n9997_p0001b10", heading="Y2", depth=2),
                _child("T99n9997_p0001b11", "T99n9997_p0001c29", heading="Z"),
            ],
            parent="1_1",
        )

    out, rep = _self_run(tmp_path, doc, answer)
    assert len(rep["tasks"]["subdivide"]["accepted"]) == 1
    y1 = next(n for n in out["nodes"] if n["heading_src"] == "Y1")
    assert y1["locations"]["commentary"]["explained"] == "T99n9997_p0001a05"
    assert y1["locations"]["root_text"]["start"] == "T99n9997_p0001a01"
    side, _ = anchor.outlined_text(
        out, SELF_TEXT, target_role="root", outline_ref={"path": "x", "sha256": "0"}
    )
    assert side["unplaced"] == []


def test_an_explained_line_before_its_parents_is_rejected(tmp_path):
    doc = _self_doc(SELF_TEXT, ["T99n9997_p0001a01", "T99n9997_p0002a01"])

    def answer(task, meta):
        if meta["unit"] != "w1":
            return {"divisions": []}
        return _division(
            [
                _child("T99n9997_p0001a01", "T99n9997_p0001b10", explained="T99n9997_p0001a05"),
                _child(
                    "T99n9997_p0001a01", "T99n9997_p0001a20", depth=2, explained="T99n9997_p0001a02"
                ),
                _child("T99n9997_p0001a21", "T99n9997_p0001b10", depth=2),
                _child("T99n9997_p0001b11", "T99n9997_p0001c29"),
            ],
            parent="1_1",
        )

    out, rep = _self_run(tmp_path, doc, answer)
    [rej] = rep["tasks"]["subdivide"]["rejected"]
    assert "explained" in rej["reason"] and out == doc


WIN_TEXT = _text("T99n9997", "合成論文第%03d行" + "義" * 40 + "。", pages=range(1, 7))
WIN_LH = WIN_TEXT.all_lineheads


def _window_run(tmp_path, monkeypatch, per_window):
    """The 2_1 leaf of WIN_TEXT (p0001a10 to p0006c29) in windows; per_window(w) answers one."""
    monkeypatch.setattr(resolver, "MAX_REQUEST_CHARS", 12000)
    doc = _self_doc(WIN_TEXT, ["T99n9997_p0001a01", "T99n9997_p0001a10"])

    def answer(task, meta):
        windows = meta.get("windows") or {}
        if "2_1" not in windows:
            return {"divisions": []}
        return per_window(windows["2_1"])

    out, rep = _self_run(tmp_path, doc, answer, text=WIN_TEXT)
    return out, rep["tasks"]["subdivide"]


def test_an_overrun_that_runs_on_past_its_window_reaches_the_leaf_end(tmp_path, monkeypatch):
    def per_window(w):
        c0 = WIN_LH.index(w["core"][0])
        if w["window"] == 1:
            return _division(
                [_child(WIN_LH[c0], WIN_LH[c0 + 20]), _child(WIN_LH[c0 + 21], w["shown"][1])],
                parent="2_1",
            )
        if w["window"] == 3:  # a later sibling the parser missed begins here and runs on
            return _division(
                [], parent="2_1", uncovered=[_gap(w["core"][0], WIN_LH[-1], "overrun", "next")]
            )
        return _division([], parent="2_1")

    out, t = _window_run(tmp_path, monkeypatch, per_window)
    assert not t["rejected"], t["rejected"]
    [over] = t["overruns"]
    assert over["end"] == "T99n9997_p0006c29"
    kids = [k for k in out["nodes"] if k["parent_id"] == "2_1"]
    assert len(kids) == 2
    end = WIN_LH.index(kids[1]["locations"]["root_text"]["end"])
    assert end + 1 == WIN_LH.index(over["start"])


def test_a_windowed_leaf_with_one_division_and_an_overrun_is_reported(tmp_path, monkeypatch):
    def per_window(w):
        if w["window"] == 1:
            return _division([_child(w["core"][0], w["shown"][1])], parent="2_1")
        if w["window"] == w["of"]:
            return _division(
                [], parent="2_1", uncovered=[_gap(w["core"][0], w["shown"][1], "overrun", "next")]
            )
        return _division([], parent="2_1")

    out, t = _window_run(tmp_path, monkeypatch, per_window)
    assert not t["rejected"] and not t["accepted"]
    assert [r["id"] for r in t["reported"]] == ["2_1"]
    assert [o["end"] for o in t["overruns"]] == ["T99n9997_p0006c29"]
    assert not [k for k in out["nodes"] if k["parent_id"] == "2_1"]


def test_window_items_that_begin_outside_the_core_are_dropped(tmp_path, monkeypatch):
    def per_window(w):
        kids = [_child(w["core"][0], w["core"][1], heading="第%d段" % w["window"])]
        if w["window"] == 2:  # the model also restates a boundary from the left-hand context
            kids.insert(0, _child(w["shown"][0], WIN_LH[WIN_LH.index(w["core"][0]) - 1]))
        return _division(kids, parent="2_1")

    out, t = _window_run(tmp_path, monkeypatch, per_window)
    assert not t["rejected"]
    assert next(r for r in t["windows"] if r["window"] == 2)["dropped"] == 1
    kids = [k for k in out["nodes"] if k["parent_id"] == "2_1"]
    assert [k["heading_src"] for k in kids] == ["第%d段" % k for k in range(1, len(kids) + 1)]
