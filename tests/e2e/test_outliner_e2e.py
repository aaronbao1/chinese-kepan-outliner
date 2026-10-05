"""End to end: project file -> run directory, through every stage of the outliner pipeline.

Offline tests run on the committed dev excerpts (tests/fixtures/projects/dharani-offline*.toml): no
data/raw/, no network, no model (resolver adapter 'none'). Raw-gated tests run the real projects over the
T1723 dev span and score the result against the Kuiji gold's dev split — a development number on a
Claude-seeded draft gold, never a headline (data/EVAL-SETS.md item 11).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chinese_workflow.common import outline_doc
from chinese_workflow.common.paths import REPO_ROOT, cbeta_xml_path
from chinese_workflow.common.splits import SplitViolation
from chinese_workflow.outline.pipeline import OutlineValidationError
from chinese_workflow.runner.__main__ import run

FIXTURE_PROJECTS = REPO_ROOT / "tests" / "fixtures" / "projects"
RAW = cbeta_xml_path("T34n1723") is not None and cbeta_xml_path("T09n0262") is not None
raw_only = pytest.mark.skipif(not RAW, reason="needs data/raw/cbeta (scripts/fetch_cbeta.sh)")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("project", ["dharani-offline.toml", "dharani-offline-root.toml"])
def test_offline_run_produces_every_artefact(tmp_path, project):
    result = run(FIXTURE_PROJECTS / project, tmp_path / "run")
    out = Path(result["out"])
    assert result["ok"], result["run"]["stages"]
    for rel in ("run.json", "outline/outline.json", "outline/outline.md", "outline/outline.docx",
                "outline/outlined-text.json", "outline/outlined-text.md", "segment/sentences.json",
                "chunk/chunks.json", "chunk/chunks.md", "chunk/chunks.docx", "chunk/invariants.json"):
        assert (out / rel).exists(), rel
    doc = _load(out / "outline" / "outline.json")
    assert outline_doc.validate(doc).passed()
    assert "degraded" not in _load(out / "outline" / "outline-report.json")  # a dev build needs no repair
    assert doc["metadata"]["gold_status"] == "prediction"
    headings = [n["heading_src"] for n in doc["nodes"]]
    assert "陀羅尼品" in headings
    # tier 2 found structure inside the 品 (the gate and the text division at least)
    dharani = next(n for n in doc["nodes"] if n["heading_src"] == "陀羅尼品")
    below = [n for n in doc["nodes"] if n["id"].startswith(dharani["id"] + ".")]
    assert len(below) >= 10
    inv = _load(out / "chunk" / "invariants.json")
    assert inv["ok"], inv
    run_json = _load(out / "run.json")
    assert run_json["split_guard"] and run_json["pipeline"]["commit"]


def test_offline_run_is_deterministic(tmp_path):
    a = run(FIXTURE_PROJECTS / "dharani-offline.toml", tmp_path / "a")
    b = run(FIXTURE_PROJECTS / "dharani-offline.toml", tmp_path / "b")
    for rel in ("outline/outline.json", "outline/outlined-text.json", "chunk/chunks.md"):
        ta = (Path(a["out"]) / rel).read_text(encoding="utf-8")
        tb = (Path(b["out"]) / rel).read_text(encoding="utf-8")
        assert ta.replace(str(tmp_path / "a"), "") == tb.replace(str(tmp_path / "b"), ""), rel


def test_offline_hybrid_run_replays_the_interactive_answers(tmp_path):
    """source hybrid: tier 2 + the resolver's root spans + the gloss, answered once by a Claude Code
    session through the interactive adapter and replayed here (dharani-offline-hybrid.toml). To
    re-record after a change to tier 2 or the prompt references: run the outline build of that project
    with --adapter interactive, answer the request files, re-run, and copy <out>/llm/responses.jsonl
    over tests/fixtures/llm-cassettes/dharani-dev-interactive.jsonl. A request whose hash did not change
    keeps its recorded answer. The root-spans record was last answered on 2026-10-02 and has since
    been carried to new request hashes (its `carried_from` field: only request.system changed, the
    answer was not re-recorded); it should be re-answered before the next freeze tag. The gloss records
    are the first recording's (2026-09-28)."""
    explicit = run(FIXTURE_PROJECTS / "dharani-offline.toml", tmp_path / "explicit")
    hybrid = run(FIXTURE_PROJECTS / "dharani-offline-hybrid.toml", tmp_path / "hybrid")
    assert hybrid["ok"], hybrid["run"]["stages"]
    before = _load(Path(explicit["out"]) / "outline" / "outline.json")
    after = _load(Path(hybrid["out"]) / "outline" / "outline.json")
    outline_doc.assert_explicit_unchanged(before, after)
    unmapped_before = sum("unmapped" in n["flags"] for n in before["nodes"])
    unmapped_after = sum("unmapped" in n["flags"] for n in after["nodes"])
    assert unmapped_before >= 25 and unmapped_after == 0
    assert all(n["heading_en"] for n in after["nodes"])
    inferred = [n for n in after["nodes"]
                if (n["locations"].get("root_text") or {}).get("basis") == "inferred"]
    assert inferred and all(any("claude-code-session" in note for note in n["notes"])
                            for n in inferred)


@raw_only
def test_real_project_refuses_reserve(tmp_path):
    from chinese_workflow.outline.pipeline import OutlineConfig, build

    cfg = OutlineConfig(mode="sutra", root="T09n0262", commentary="T34n1723",
                        scheme_id="kuiji-xuanzan", span="T34n1723_p0850a19..T34n1723_p0850c05")
    with pytest.raises(SplitViolation):
        build(cfg, tmp_path / "o")


@raw_only
def test_real_dev_run_scores_on_the_dev_split(tmp_path):
    from chinese_workflow.eval.score import score

    result = run(REPO_ROOT / "projects" / "lotus-kuiji-dharani-comm" / "project.toml", tmp_path / "r")
    assert result["ok"], result["run"]["stages"]
    doc = _load(Path(result["out"]) / "outline" / "outline.json")
    m = score(doc, "kuiji-xuanzan", split="dev")
    assert m["disclosures"]["headline"] is False
    # levels 1–2 come from tier 1 and the scheme prior, so the 陀羅尼品 chain matches
    assert m["s_f1"]["TP"] >= 2


GUANJING = cbeta_xml_path("T37n1753") is not None and cbeta_xml_path("T12n0365") is not None


@pytest.fixture(scope="module")
def guanjing_run(tmp_path_factory):
    """One run of projects/guanjing-shandao (whole texts, outside every split) shared by the tests below:
    (outline.json, outline-report.json)."""
    result = run(REPO_ROOT / "projects" / "guanjing-shandao" / "project.toml",
                 tmp_path_factory.mktemp("guanjing") / "r")
    assert result["ok"], result["run"]["stages"]
    out = Path(result["out"]) / "outline"
    return _load(out / "outline.json"), _load(out / "outline-report.json")


def _guanjing_lemmas(doc, rep):
    """(lemma nodes, the lemma-not-found entries of the anchor report)."""
    with_raw = [n for n in doc["nodes"] if (n["locations"].get("root_text") or {}).get("raw")]
    return with_raw, [a for a in rep["anchor"] if a["code"] == "lemma-not-found"]


@pytest.mark.skipif(not GUANJING, reason="needs T37n1753 and T12n0365 under data/raw/cbeta")
def test_guanjing_run_keeps_the_counts_of_task_8(guanjing_run):
    """projects/guanjing-shandao (T0365 with 善導's T1753, whole texts, outside every split) after the fix rounds of
    Task 8 (2026-10-03). The plan's gate was lemma-not-found / lemma nodes <= 25 %: **NOT reached**, 42.8 % (89 of 208;
    119 lemmas placed; 卷二 4/52, 卷三 31/98, 卷四 54/58). The residual is a last item of one 觀 quoted loosely (作此觀
    for 作是觀者) that matches the same words one or more 觀 later and strands the next 觀: cousins, which the sibling
    lookahead cannot see (docs/outliner-design.md 5.5). 54 of the 89 are 卷四 lemmas, searched from p0346b15 (47) and
    p0346b19 (7): 卷三's misplaced tail (普觀 at p0346a18, 雜想觀 at p0346b06:17) carries the cursor to the sūtra's last
    lines, and rule A does not fire on 卷三. The assertions below are floors and ceilings at today's counts, so a
    regression fails; they are not a claim that the target is met (the xfail below says so)."""
    doc, rep = guanjing_run
    assert rep["validation"]["passed"] is True and len(doc["nodes"]) >= 589
    t2 = rep["tier2"]["stats"]
    assert t2["closes"] >= 30 and t2["enters"] >= 287 and t2["enters_unresolved"] <= 9 and t2["nodes"] >= 585
    codes = [a["code"] for a in rep["anchor"]]
    with_raw, lnf = _guanjing_lemmas(doc, rep)
    juan = lambda i: i.split(".")[0]
    # the ratio and the placed count, not an absolute count of misses: more lemma nodes must not hide a worse ratio
    assert len(with_raw) >= 208 and len(lnf) / len(with_raw) <= 0.43  # 42.8 % today; the plan's gate is 0.25
    assert len(with_raw) - len(lnf) >= 119  # lemmas placed
    ceiling = {"2_1": 4, "3_1": 31, "4_1": 54}
    for j, most in ceiling.items():
        assert sum(1 for a in lnf if juan(a["node_id"]) == j) <= most, j
    # diagnostic counts (how often rules A and B acted on this text), not quality measures: lower is not better
    assert codes.count("end-clamped") <= 12 and codes.count("lemma-lookahead") <= 1


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="plan gate not met; see design §5.5")
@pytest.mark.skipif(not GUANJING, reason="needs T37n1753 and T12n0365 under data/raw/cbeta")
def test_guanjing_run_meets_the_plan_gate(guanjing_run):
    """The plan's gate for Task 8: lemma-not-found / lemma nodes <= 25 % on the guanjing project. Not met (42.8 %,
    design 5.5 "Gate not met"); strict, so the run that meets it fails this test until the xfail is removed."""
    with_raw, lnf = _guanjing_lemmas(*guanjing_run)
    assert len(lnf) / len(with_raw) <= 0.25


def test_runner_hands_its_split_guard_to_ingest_and_frozen_to_export(tmp_path, monkeypatch):
    """Review of 2026-09-27: a frozen run must not be refused by a fresh, unfrozen guard inside ingest,
    and ingest's checks belong in run.json's split_guard."""
    from chinese_workflow.export import jsonld
    from chinese_workflow.ingest import run as ingest_run

    seen = {}
    real_ingest, real_export = ingest_run.run, jsonld.export

    def spy_ingest(*args, **kwargs):
        seen.setdefault("guards", []).append(kwargs.get("guard"))
        return real_ingest(*args, **kwargs)

    def spy_export(*args, **kwargs):
        seen["frozen"] = kwargs.get("frozen", "missing")
        return real_export(*args, **kwargs)

    monkeypatch.setattr(ingest_run, "run", spy_ingest)
    monkeypatch.setattr(jsonld, "export", spy_export)
    result = run(FIXTURE_PROJECTS / "dharani-offline.toml", tmp_path / "run", frozen="spy-tag")
    assert result["ok"]
    assert seen["guards"] and all(g is not None and g.frozen == "spy-tag" for g in seen["guards"])
    assert seen["frozen"] == "spy-tag"


def test_offline_run_degrades_instead_of_failing(tmp_path, monkeypatch):
    """E06 review B5: a local validator error ([sibling-order] here, forced by swapping two leaf siblings'
    root spans after the anchor) is repaired before the resolver and reported under `degraded`; the run
    completes with exit status 0 semantics (result['ok']) and a validating outline.json."""
    from chinese_workflow.outline import anchor

    A, B = "1_1.1_2.2_3.2_4.2_5.1_6", "1_1.1_2.2_3.2_4.2_5.2_6"
    real = anchor.resolve_root_spans

    def swapped(doc, root):
        out, report = real(doc, root)
        by_id = {n["id"]: n for n in out["nodes"]}
        a, b = by_id[A]["locations"], by_id[B]["locations"]
        a["root_text"], b["root_text"] = b["root_text"], a["root_text"]
        return out, report

    monkeypatch.setattr(anchor, "resolve_root_spans", swapped)
    result = run(FIXTURE_PROJECTS / "dharani-offline.toml", tmp_path / "run")
    assert result["ok"] and result["run"]["stages"]["outline"]["degraded"] == 1
    report = _load(Path(result["out"]) / "outline" / "outline-report.json")
    assert report["validation"]["passed"] and [e["stage"] for e in report["degraded"]] == ["before-resolver"]
    (entry,) = report["degraded"]
    assert entry["errors"][0].startswith("  error   [sibling-order] %s: root_text.start T09n0262_p0059a07" % B)
    assert entry["repairs"] == [{"kind": "demoted", "node_id": B, "code": "sibling-order",
                                 "locator": "root_text.start", "was": "T09n0262_p0059a07"}]
    doc = _load(Path(result["out"]) / "outline" / "outline.json")
    assert outline_doc.validate(doc).passed()
    node = next(n for n in doc["nodes"] if n["id"] == B)
    assert node["locations"]["root_text"]["start"] is None and "unmapped" in node["flags"]
    assert node["notes"][-1] == "demoted: sibling-order, was T09n0262_p0059a07"


def test_outline_cli_exit_codes(tmp_path, monkeypatch, capsys):
    """0 with a `degraded` count when the outline validates after repair; 1, no traceback, when errors remain."""
    from chinese_workflow.outline import __main__ as cli

    argv = ["build", "--mode", "self-outlining", "--root", "T99n9999", "--out", str(tmp_path)]
    fake = {"pending": [], "paths": {"outline": str(tmp_path / "outline.json")},
            "doc": {"metadata": {"node_count": 1, "max_depth": 1}},
            "report": {"validation": {"passed": True, "warnings": []},
                       "degraded": [{"stage": "before-resolver", "errors": ["e"],
                                     "repairs": [{"kind": "demoted"}]}]}}
    monkeypatch.setattr(cli, "build", lambda cfg, out, *, guard=None, llm_config=None: fake)
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["degraded"] == 1

    def boom(cfg, out, *, guard=None, llm_config=None):
        raise OutlineValidationError("outline.json failed validation after repair: ['  error   [schema] $.nodes[0]: x']")

    monkeypatch.setattr(cli, "build", boom)
    assert cli.main(argv) == 1
    assert capsys.readouterr().err.startswith("failed: outline.json failed validation after repair")

    def other_failure(cfg, out, *, guard=None, llm_config=None):
        raise RuntimeError("some other stage failed")

    monkeypatch.setattr(cli, "build", other_failure)  # not an outline validation failure: keeps its traceback
    with pytest.raises(RuntimeError, match="some other stage failed"):
        cli.main(argv)


def _inject_local_and_hard_errors(monkeypatch):
    """After the anchor: swap two leaf siblings' root spans ([sibling-order], local) and drop the first node's
    sibling_index ([schema], no repair covers it)."""
    from chinese_workflow.outline import anchor

    A, B = "1_1.1_2.2_3.2_4.2_5.1_6", "1_1.1_2.2_3.2_4.2_5.2_6"
    real = anchor.resolve_root_spans

    def broken(doc, root):
        out, report = real(doc, root)
        by_id = {n["id"]: n for n in out["nodes"]}
        a, b = by_id[A]["locations"], by_id[B]["locations"]
        a["root_text"], b["root_text"] = b["root_text"], a["root_text"]
        del out["nodes"][0]["sibling_index"]
        return out, report

    monkeypatch.setattr(anchor, "resolve_root_spans", broken)
    return B


def test_hybrid_build_with_a_hard_error_skips_the_resolver_and_fails_cleanly(tmp_path, monkeypatch, capsys):
    """Review of Task 9: a hybrid build whose document still fails validation after repair used to hand it to
    resolver.resolve, whose input check raised an uncaught ValueError (traceback, nothing written). Now the
    resolver and gloss are skipped, every artefact and outline-report.json are written (with the
    first-pass errors and the skipped status), and the CLI exits 1 with a 'failed:' line."""
    from chinese_workflow.outline import resolver
    from chinese_workflow.runner.__main__ import main

    B = _inject_local_and_hard_errors(monkeypatch)

    def must_not_run(*args, **kwargs):
        raise AssertionError("the resolver must not run on an input that fails validation")

    monkeypatch.setattr(resolver, "resolve", must_not_run)
    out = tmp_path / "run"
    assert main(["run", str(FIXTURE_PROJECTS / "dharani-offline-hybrid.toml"), "--out", str(out)]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("failed: outline.json failed validation after repair")
    assert "Traceback" not in captured.err and captured.out == ""
    for rel in ("outline.json", "outline.md", "outline.docx", "outlined-text.json", "outlined-text.md",
                "target.txt", "outline-report.json"):
        assert (out / "outline" / rel).exists(), rel
    report = _load(out / "outline" / "outline-report.json")
    assert report["resolver"] == {"status": "skipped: input fails validation after repair"}
    assert report["gloss"] == {"status": "skipped: input fails validation after repair"}
    assert [e["stage"] for e in report["degraded"]] == ["before-resolver"]  # nothing ran after it
    (entry,) = report["degraded"]
    assert entry["errors"][0].startswith("  error   [sibling-order] %s: root_text.start" % B)
    assert [r["kind"] for r in entry["repairs"]] == ["demoted"]
    assert not report["validation"]["passed"]
    assert any("sibling_index" in e for e in report["validation"]["errors"])


def test_the_after_resolver_pass_runs_only_when_the_resolver_or_gloss_ran(tmp_path, monkeypatch):
    """Review of Task 9: tier2 (and hybrid with adapter none) builds must not re-validate an unchanged
    document under the 'after-resolver' label."""
    from chinese_workflow.outline import pipeline

    stages = []
    real = pipeline._validate_and_repair

    def spy(doc, report, stage):
        stages.append(stage)
        return real(doc, report, stage)

    monkeypatch.setattr(pipeline, "_validate_and_repair", spy)
    run(FIXTURE_PROJECTS / "dharani-offline.toml", tmp_path / "tier2")
    assert stages == ["before-resolver"]
    stages.clear()
    run(FIXTURE_PROJECTS / "dharani-offline-hybrid.toml", tmp_path / "hybrid")
    assert stages == ["before-resolver", "after-resolver"]
