"""E07 capability sweep v1: the outliner at tag outliner-v1-frozen-2026-10-03 (= 014c125, main after the E06
follow-up) on every non-test dataset of E06's README matrix, scored by the repo scorer. Ported from
../E06-capability-sweep/run_e06.py; what changed is listed under "E07 changes" below.

Input : the CBETA XML under data/raw/cbeta/ (T09n0262, T34n1718, T34n1723; X11n0268, P167n1573,
        D14n8842, T31n1605, T31n1602 from the xml-p5 clone); the golds of data/eval-sets.json, read
        only by chinese_workflow.eval.score (and, for the T1723 oracle arm, by outline.oracle);
        for the hybrid and model-only arms, the interactive adapter's response files
        runs/<cell>/llm/responses/<hash>.json written by whoever answers the requests.
Output: experiments/E07-capability-sweep-v1/runs/<arm>-<set>/ (gitignored): the outline build, cell.json
          (build state: pending requests, rounds, guard log summary), llm/ (interactive requests and
          responses), score-<row>.json (full scorer output);
        runs/_inputs/<file>.no-kepan.xml (+ .json): the OOD 科判 inputs with CBETA's cb:mulu
          type="科判" removed (the gold's own markup; see "OOD 科判 golds" below);
        experiments/E07-capability-sweep-v1/metrics.json and SUMMARY.md (aggregate numbers only; no
          node-level locator of an eval-only sdp gold),
        looks-e07.json (every validation and OOD scoring event of E07: kind `look` for a new (set, row, arm,
          outline, gold), `recompute` for a re-score of one already seen), and one entry in
          experiments/E01-explicit-recovery/looks.json per set and score run that adds new looks
          (E01's convention: entries are appended, never edited).
        Nothing here prints or writes a gold heading or note.
Run   : cd pipeline && .venv/bin/python ../experiments/E07-capability-sweep-v1/run_e07.py <subcommand>
          build [--set S ...] [--arm A ...]   build cells; re-run after response files are written
          pending [--json]                    request files without a response, across runs/
          score [--rescore] [--partial-look]  score every cell with no pending request; a NEW
                                              validation look on a set waits until every
                                              non-diagnostic arm of that set is scorable (or failed),
                                              so a look is one pass, unless --partial-look
          status                              one line per cell

Cells and choices (README "Method"; every choice the README leaves open is listed in SUMMARY.md):
  * Every build runs under SplitGuard() WITHOUT a frozen tag, so the guard itself refuses any test or
    reserve line (the OOD builds read only unsplit files and need no tag). The guard is created per
    build attempt in build_cell and its summary is kept in cell.json also when the build fails.
    frozen=outliner-v0-frozen-2026-10-01 is passed only to OOD score rows (the scorer requires it),
    and only when pipeline/ was byte-identical to the tag both when the cell was built (cell.json
    provenance) and when it is scored; otherwise the OOD row is not scored ("not frozen").
  * T1718-devval (added after review; not in the README matrix): T34n1718 built over dev+validation
    (the T0262-xu-root span, target_role commentary) and scored on the dev and validation rows. A
    validation-only build (T1718-validation, the README row) cannot match any validation gold node:
    all of them hang under dev ancestors in the scoring tree (design check reachability), so its S-F1
    is 0 by construction; the devval build supplies those ancestors as uncounted, matchable nodes.
  * hybrid = OutlineConfig(source="hybrid", resolver={"adapter": "interactive"}) with the llm dir in
    the cell's run dir (outline/__main__.py _llm_config: model INTERACTIVE_MODEL). The frozen pipeline
    runs gloss even while the resolver waits, so gloss requests written in that state are listed as
    `deferred` (they change once the resolver's nodes are merged).
  * model-only (T0262 root-text sets): outline/pipeline.build has no model-only path (it always
    passes the commentary to the resolver), so it is wired here from public functions: the tier-1 root
    品 pin of the target chapter -> the set's level-1 scheme prior (scheme.apply_level1, the same prior
    the tier2/hybrid arms of the set get) -> outline_doc.build_prediction -> resolver.resolve(...,
    commentary=None, tasks=("subdivide",), scheme_id=None => model-<prompt sha8>, D21) for up to
    MODEL_ONLY_ROUNDS rounds (each round re-offers every leaf) -> validate. No gloss.
  * OOD 科判 golds (X0268, P1573, D8842): tier 1 turns CBETA's cb:mulu type="科判" into explicit nodes,
    and those elements ARE the gold, so the README arms tier1/tier2/hybrid read a copy of the XML with
    the 科判 cb:mulu removed (E06 README H4 = E07 README H11: "tier 1 (no 科判-typed mulu)"); the lines and their reading
    text are checked identical to the original. tier1-markup / tier2-markup read the original XML:
    LEAKED diagnostic rows (tier 1 copies the gold), never hypothesis rows; no hybrid on it.
  * Identical requests in two cells (same hash) are answered once: build copies a response file from
    another cell's responses/ when the hash matches.

E07 changes (README "Method"; everything else is E06's harness as it was):
  * TAG outliner-v1-frozen-2026-10-03 (014c125); look note "E07 look #3".
  * A `commentary.span_start` row (row name <split>-span) beside every commentary.explained row of the
    T1718 and T1723 commentary sets (review of E06, A3); validation span rows are part of look #3.
  * Every row carries the follow-up scorer's diagnostics (fn_split, the TP-rule pair, key_lines,
    fp_by_kind, and the ancestor_consistent / reanchor / depth_offset_hist triple) at t = 0 and t = 1.
  * OOD rows are an `ood-look`: kind ood-look in looks-e07.json, held like a validation look until
    every non-diagnostic arm of the set is scorable; never written to E01's looks.json (a split log).
  * cell.json keeps the build's `degraded` repairs (outline.pipeline._validate_and_repair).
  * design_checks.request_sizes: every request .md under runs/ (answered or not), for README H7.
  * SUMMARY.md has an E06 column (E06's metrics.json, same set / arm / row) and a diagnostics table.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

from chinese_workflow.common import jsonio, outline_doc
from chinese_workflow.common.paths import REGISTRY, REPO_ROOT, cbeta_xml_path, repo_relative
from chinese_workflow.common.project import resolve_span
from chinese_workflow.common.splits import SplitGuard, split_of_line
from chinese_workflow.eval import registry as reg
from chinese_workflow.eval.score import score
from chinese_workflow.llm import LLMConfig, PendingInteractive
from chinese_workflow.outline.__main__ import INTERACTIVE_MODEL
from chinese_workflow.outline.pipeline import OutlineConfig, build, slice_text

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
INPUTS = RUNS / "_inputs"
E01_LOOKS = HERE.parent / "E01-explicit-recovery" / "looks.json"
LOOKS_E07 = HERE / "looks-e07.json"
TAG = "outliner-v1-frozen-2026-10-03"
E06_METRICS = HERE.parent / "E06-capability-sweep" / "metrics.json"
LOOK_NOTE = "E07 look #3, frozen outliner-v1-frozen-2026-10-03"
MODEL_ONLY_ROUNDS = 3
KEPAN = "科判"
CB_NS = "http://www.cbeta.org/ns/1.0"

KUIJI_LEVEL1 = [  # as run_e01.py and projects/lotus-kuiji-dharani-*/project.toml (R03 F22)
    {"heading_src": "序分", "from_pin": "序品", "to_pin": "序品", "source": "R03 F22"},
    {"heading_src": "正宗", "from_pin": "方便品", "to_pin": "授學無學人記品", "source": "R03 F22"},
    {"heading_src": "流通", "from_pin": "法師品", "to_pin": "普賢菩薩勸發品", "source": "R03 F22"},
]
XU_SPAN = "dev+validation"  # resolved by xu_span(): T34n1718_p0001b18 .. the line before p0036a26
SPAN_SPLITS = {"dev": ("dev",), "validation": ("validation",), XU_SPAN: ("dev", "validation")}


def _sutra(commentary, scheme_id, span, level1, target_role, arms, rows, target_pin=None):
    return dict(kind="sutra", root="T09n0262", commentary=commentary, scheme_id=scheme_id, span=span,
                level1=level1, target_role=target_role, arms=arms, rows=rows, target_pin=target_pin)


def _self(root, scheme_id, gold, key, arms, sanitize):
    return dict(kind="self", root=root, scheme_id=scheme_id, span=None, arms=arms, sanitize=sanitize,
                rows=[dict(row="whole", gold=gold, key=key, split=None, frozen=TAG, ood_look=True)])


SETS = {
    "T1718-dev": _sutra("T34n1718", "zhiyi-wenju", "dev", [], "commentary", ("tier1", "tier2", "hybrid"),
                        [dict(row="dev", gold="sdp-T1718-zhiyi-wenju", key="commentary.explained",
                              split="dev")]),
    "T1718-validation": _sutra("T34n1718", "zhiyi-wenju", "validation", [], "commentary",
                               ("tier1", "tier2", "hybrid"),
                               [dict(row="validation", gold="sdp-T1718-zhiyi-wenju",
                                     key="commentary.explained", split="validation", look=True)]),
    "T1718-devval": _sutra("T34n1718", "zhiyi-wenju", XU_SPAN, [], "commentary",
                           ("tier1", "tier2", "hybrid"),
                           [dict(row="dev", gold="sdp-T1718-zhiyi-wenju", key="commentary.explained",
                                 split="dev"),
                            dict(row="validation", gold="sdp-T1718-zhiyi-wenju",
                                 key="commentary.explained", split="validation", look=True)]),
    "T1723-dev": _sutra("T34n1723", "kuiji-xuanzan", "dev", KUIJI_LEVEL1, "commentary",
                        ("tier1", "tier2", "hybrid", "oracle"),
                        [dict(row="dev", gold="kuiji-xuanzan", key="commentary.explained", split="dev")]),
    "T0262-dharani-root": _sutra("T34n1723", "kuiji-xuanzan", "dev", KUIJI_LEVEL1, "root",
                                 ("tier2", "hybrid", "model-only"),
                                 [dict(row="dev", gold="kuiji-xuanzan", key="root_text.start",
                                       split="dev")], target_pin="陀羅尼"),
    "T0262-xu-root": _sutra("T34n1718", "zhiyi-wenju", XU_SPAN, [], "root",
                            ("tier1", "tier2", "hybrid", "model-only"),
                            [dict(row="dev", gold="sdp-T0262-zhiyi-wenju", key="root_text.start",
                                  split="dev"),
                             dict(row="validation", gold="sdp-T0262-zhiyi-wenju", key="root_text.start",
                                  split="validation", look=True)], target_pin="序"),
    "OOD-X0268": _self("X11n0268", "x0268-self", "cbeta-mulu-X0268", None,
                       ("tier1", "tier2", "hybrid", "tier1-markup", "tier2-markup"), True),
    "OOD-P1573": _self("P167n1573", "p1573-self", "cbeta-mulu-P1573", None,
                       ("tier1", "tier2", "hybrid", "tier1-markup", "tier2-markup"), True),
    "OOD-D8842": _self("D14n8842", "d8842-self", "cbeta-mulu-D8842", None,
                       ("tier1", "tier2", "hybrid", "tier1-markup", "tier2-markup"), True),
    "OOD-T1605": _self("T31n1605", "t1605-self", "ybh-T1605", "structure", ("tier1", "tier2", "hybrid"),
                       False),
    "OOD-T1602": _self("T31n1602", "t1602-self", "ybh-T1602", "structure", ("tier1", "tier2", "hybrid"),
                       False),
}
SPAN_KEY_SETS = ("T1718-dev", "T1718-validation", "T1718-devval", "T1723-dev")


def _add_span_rows():
    """E07: a commentary.span_start row (<split>-span) beside every commentary.explained row of the
    commentary sets (review of E06, A3); a validation span row is part of the same look."""
    for name in SPAN_KEY_SETS:
        rows = SETS[name]["rows"]
        rows += [dict(r, row="%s-span" % r["row"], key="commentary.span_start") for r in list(rows)
                 if r["key"] == "commentary.explained"]


_add_span_rows()
LLM_ARMS = ("hybrid", "model-only")
DIAGNOSTIC_ARMS = ("tier1-markup", "tier2-markup")  # LEAKED: the gold's own markup is the input

DESIGN_CHOICES = [  # every decision the README leaves open (written into SUMMARY.md and metrics.json)
    "Guard: every build runs SplitGuard() WITHOUT the frozen tag, so the guard itself refuses any test "
    "or reserve line (cell.json guard logs show splits_read dev/validation/unsplit only). The OOD builds "
    "read only unsplit files and structure-only markup, which the guard always allows, so they need no "
    "tag (review 2026-10-01: a tag there only switches refusals off). The guard is created per build "
    "attempt in build_cell; a failed cell keeps its guard summary. frozen=TAG is passed only to OOD "
    "score rows (the scorer refuses OOD golds otherwise) and to OOD gold-vs-itself rows; no dev / "
    "validation score passes frozen, so the scorer's own guard still refuses counted test/reserve nodes.",
    "Frozen discipline for OOD rows: each cell.json records provenance() at build time; an OOD row is "
    "scored with frozen=TAG only when pipeline/ was byte-identical to the tag (git diff --quiet TAG -- "
    "pipeline/, no untracked files) both at build time and at score time; otherwise the row is not "
    "scored (status 'not frozen'). The outlines' generated_by '+dirty' is repo-wide and is not used.",
    "T0262-xu-root and T1718-devval span: resolve_span('dev').start .. resolve_span('validation').last on "
    "T34n1718, i.e. T34n1718_p0001b18..T34n1718_p0036a25, asserted to end on the line before p0036a26; "
    "xu_span reads only T34n1718's lineheads, recorded as a structure-only guard entry "
    "(design_checks.xu_span_guard).",
    "T1718-devval (E06: added after review, outside E06's README matrix; E07 pre-registers it in H5/H6): the "
    "README's T1718-validation row builds over the validation span only, and every counted validation "
    "node of sdp-T1718 hangs under dev ancestors in the scorer's top-down tree (design check "
    "reachability), so S-F1 / F-F1 there are 0 for every arm by construction. T1718-devval builds "
    "T34n1718 over dev+validation (target_role commentary) and scores the dev and validation rows; "
    "dev nodes are then matchable, uncounted ancestors. Its validation row is part of look #3 (logged). "
    "E07's H5 reads both T1718-validation and T1718-devval.",
    "T0262-xu-root predictions are NOT restricted to 序品: under the scorer's root-text region rule a "
    "prediction is counted only in a dev/validation gold region, and no T09n0262 line outside 序品 lies in "
    "one (design check xu_region, computed from gold locators only), so a restriction would change no "
    "counted node. Predictions in a region with no split (outside 序品, and the 序品 title line) are "
    "split_unknown: neither TP nor FP.",
    "model-only (pipeline.build has no model-only path): tier-1 root 品 pin of the target chapter -> the "
    "set's level-1 prior (Kuiji's 3 parts for T0262-dharani-root, as its tier2/hybrid arms; none for "
    "T0262-xu-root, as projects/lotus-zhiyi-wenju) -> build_prediction (sutra mode, commentary_id null, "
    "source_document kind root-text, scheme model-<prompt sha8>, D21) -> resolver.resolve(commentary=None, "
    "tasks=('subdivide',), scheme_id=None); no anchor.resolve_root_spans (the pin carries its span); "
    "no gloss.",
    "model-only rounds: up to %d subdivide rounds, each re-offering every leaf (the resolver's model-only "
    "rule); a round that accepts no division ends the loop (the next request would be identical)."
    % MODEL_ONLY_ROUNDS,
    "model-only keeps the level-1 prior because top-down matching needs the predicted 陀羅尼品 at the "
    "gold's level 2 (under 流通); without it no node could match.",
    "OOD 科判 sets: the README arms tier1/tier2/hybrid read runs/_inputs/<file>.no-kepan.xml (cb:mulu "
    "type=科判 removed, tails kept; lines, reading text, heads, notes, juan marks checked identical; "
    "div_types may deepen only on lines that opened with a removed 科判 mulu), matching E06 README H4's (= E07 H11's) "
    "'tier 1 (no 科判-typed mulu)'; tier1-markup / tier2-markup read the original XML: LEAKED "
    "diagnostics, reported apart from the results (metrics design_checks.leaked_markup, SUMMARY "
    "'Leaked diagnostics'), never hypothesis rows; no hybrid on the original (its requests would show "
    "the gold's labels to the model).",
    "OOD scheme ids: x0268-self, p1573-self, d8842-self, t1605-self, t1602-self (the scorer only warns "
    "on scheme pairing); YBh rows use the dataset default key (structure); cbeta-mulu rows the default "
    "(commentary.explained = the self line).",
    "Headline: every E07 row reports disclosures.headline = false with its reasons (README: 'None is a "
    "headline'); the scorer's own flag is kept as scorer_headline. The scorer withholds headline only for "
    "draft/synthetic/prediction golds and dev/validation splits, so it says true on the unsplit "
    "imported-unchecked OOD rows.",
    "hybrid = OutlineConfig(source hybrid, resolver adapter interactive) + LLMConfig(adapter "
    "interactive, run_dir = the cell dir, model %s), as outline/__main__.py _llm_config; all three "
    "resolver tasks (pipeline default) then gloss." % INTERACTIVE_MODEL,
    "Gloss requests the frozen pipeline writes while the resolver still waits are listed as 'deferred' "
    "(answer after the resolver finishes; their hash changes when the resolver adds nodes). A cell is "
    "scored only with zero open, deferred or invalid requests, although gloss fills heading_en only, "
    "which no score reads.",
    "Identical requests (same hash) in two cells are answered once: build copies the response file "
    "from the other cell (hybrid-T1723-dev and hybrid-T0262-dharani-root build the same outline; only "
    "target_role differs; likewise hybrid-T1718-devval and hybrid-T0262-xu-root); `pending` marks the "
    "second as duplicate_of.",
    "An invalid response (fails JSON or its schema) blocks its cell and is listed by `pending` with state "
    "invalid until the response file is rewritten.",
    "Score cache: a row is re-scored when the cell's outline.json sha256, the gold's sha256, the row "
    "settings, the frozen value actually passed, the registry (data/eval-sets.json) sha256 or the "
    "scorer identity (tag commit while pipeline/ is identical to the tag, else a hash of "
    "pipeline/src) change; score --rescore forces it. The gold-vs-itself sanity cache uses the same "
    "registry and scorer fields.",
    "Validation looks (E07 look #3; OOD rows: kind ood-look): a validation row scored for a (set, row, arm, outline sha256, "
    "gold sha256) not seen before is a `look` event in looks-e07.json; a re-score of one already seen "
    "(e.g. after a cache-key change) is a `recompute` event, not a new look. A new look on a set waits "
    "until every non-diagnostic arm of the set is scorable or failed (one pass over all arms), unless "
    "`score --partial-look`. E01's looks.json gets one appended entry per set and score run with new "
    "looks (arms + outline sha256), built from the unflushed look events in looks-e07.json and written "
    "in a finally block, so a scoring error later in the run cannot drop it. (E06 history: E06's first "
    "pass, 2026-10-01T09:40, predated this rule.) E07 scored look #3 and the OOD look in one score run "
    "after every LLM cell had 0 open requests; E06's saved outlines rescored by the v1 scorer are logged "
    "as kind recompute-e06 (no new system output) and not written to E01's looks.json.",
    "Sanity rows: every gold scored against itself on every set row (not looks: no system output).",
    "Design check reachability: for each split-scoped row, the counted gold nodes (the scorer's split, "
    "served-scope and coverage rules, recomputed with its own _Tree/_SplitMap) whose scoring-tree "
    "ancestors all lie in a split the cell's build span covers, or are level-1 nodes the set's level-1 "
    "prior supplies; zero reachable = S-F1 0 by construction. Aggregate counts only.",
    "metrics.json and SUMMARY.md carry aggregate rows only (counts, P/R/F, per depth, child counts) and "
    "no node-level locator of an eval-only gold (design check xu_region keeps only the number of the sdp "
    "gold's dev level-1 nodes and their line offsets from the tier-1 pin); the full scorer outputs, with "
    "dev diagnostics (node ids), stay in runs/<cell>/score-<row>.json (gitignored).",
    "Deterministic cells are rebuilt on every `build` (idempotent; under 2 s each); LLM cells are "
    "rebuilt to consume response files.",
    "E07 (README 'Method'): everything above is E06's harness unchanged except TAG "
    "(outliner-v1-frozen-2026-10-03 = 014c125), the look note (E07 look #3) and the items below; "
    "'E06' in the items above reads as E07 where it names this run.",
    "E07 span_start rows: every commentary.explained row of T1718-dev, T1718-validation, T1718-devval and "
    "T1723-dev has a twin row <row>-span with --key commentary.span_start (review of E06, A3); the "
    "validation span rows are part of look #3. Gold-vs-itself on a span row scores the gold with "
    "span_start = explained (never inherited), the scorer's own reading of a gold under that key.",
    "E07 OOD look: each OOD row is held until every non-diagnostic arm of its set is scorable, then "
    "scored once and logged as kind ood-look in looks-e07.json (not in E01's looks.json, which logs "
    "split looks). The *-markup LEAKED rows are not looks.",
    "E07 diagnostics: every row keeps the follow-up scorer's fn_split, TP-rule pair, key_lines, "
    "fp_by_kind and the ancestor_consistent / reanchor / depth_offset_hist triple at t = 0 and t = 1 "
    "(metrics.json rows[*].diag; SUMMARY diagnostics tables). The triple is read only together.",
    "E07 comparison: SUMMARY's E06 columns are E06's metrics.json values for the same set, arm and row "
    "(frozen v0, 8498eb3; no E06 row exists for the span rows). E06's numbers were computed by the v0 "
    "scorer; the follow-up changed the scorer (diagnostic fields, span_start key, splits rule kept), so "
    "a changed value can come from the scorer as well as from the outliner: rescoring E06's saved "
    "outlines with the v1 scorer (e06_rescored in metrics.json) separates the two.",
    "E07 degraded builds: cell.json 'degraded' lists each repair round of outline.pipeline."
    "_validate_and_repair (stage, errors, repairs by kind); a degraded cell is built and scored.",
]


def cells(sets=None, arms=None):
    for name, spec in SETS.items():
        if sets and name not in sets:
            continue
        for arm in spec["arms"]:
            if arms and arm not in arms:
                continue
            yield name, spec, arm


def cell_dir(name: str, arm: str) -> Path:
    return RUNS / ("%s-%s" % (arm, name))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------------------------------ provenance


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


_PROV: dict = {}


def provenance() -> dict:
    """Pipeline commit, the frozen tag, whether pipeline/ is byte-identical to it, the scorer identity
    (score cache key), registry, README and harness sha256. Computed once per process."""
    if _PROV:
        return dict(_PROV)
    diff = subprocess.run(["git", "diff", "--quiet", TAG, "--", "pipeline/"], cwd=REPO_ROOT).returncode
    untracked = _git("status", "--porcelain", "--untracked-files=all", "--", "pipeline/")
    untracked = [ln for ln in untracked.splitlines() if ln.startswith("??")
                 and "__pycache__" not in ln and ".egg-info" not in ln]
    identical = diff == 0 and not untracked
    tag_commit = _git("rev-parse", TAG + "^{commit}") or None
    if identical and tag_commit:
        scorer = "tag:%s" % tag_commit
    else:  # a working tree that differs from the tag: hash every pipeline source file
        h = hashlib.sha256()
        for f in sorted((REPO_ROOT / "pipeline" / "src").rglob("*.py")):
            h.update(repo_relative(f).encode() + b"\0" + f.read_bytes() + b"\0")
        scorer = "worktree:%s" % h.hexdigest()
    _PROV.update({
        "pipeline_commit": outline_doc.pipeline_commit(),
        "tag": TAG,
        "tag_commit": tag_commit,
        "pipeline_identical_to_tag": identical,
        "scorer": scorer,
        "registry_sha256": jsonio.sha256_file(REGISTRY),
        "readme_sha256": jsonio.sha256_file(HERE / "README.md"),
        "harness_sha256": jsonio.sha256_file(Path(__file__)),
    })
    return dict(_PROV)


# ------------------------------------------------------------------------------- OOD 科判 inputs


def no_kepan_xml(file_id: str) -> tuple[Path, dict]:
    """A copy of the file's CBETA XML without its cb:mulu type="科判" elements (their tails kept), and
    the check that every line, its reading text, heads and notes are unchanged (only `mulu` loses the
    科判 entries). Cached under runs/_inputs/ by the source sha256."""
    from lxml import etree

    from chinese_workflow.ingest.lines import extract

    src = cbeta_xml_path(file_id)
    out = INPUTS / ("%s.no-kepan.xml" % file_id)
    meta_path = INPUTS / ("%s.no-kepan.json" % file_id)
    src_sha = jsonio.sha256_file(src)
    if out.exists() and meta_path.exists():
        meta = jsonio.read_json(meta_path)
        if meta.get("source_sha256") == src_sha and meta.get("sha256") == jsonio.sha256_file(out):
            return out, meta
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    tree = etree.parse(str(src), parser)
    removed = 0
    for el in list(tree.iter("{%s}mulu" % CB_NS)):
        if el.get("type") != KEPAN:
            continue
        parent, tail = el.getparent(), el.tail
        if tail:
            prev = el.getprevious()
            if prev is not None:
                prev.tail = (prev.tail or "") + tail
            else:
                parent.text = (parent.text or "") + tail
        parent.remove(el)
        removed += 1
    INPUTS.mkdir(parents=True, exist_ok=True)
    tree.write(str(out), encoding="UTF-8", xml_declaration=True)
    a, b = extract(src).lines, extract(out).lines
    problems = []
    shifted = 0
    if [r["linehead"] for r in a] != [r["linehead"] for r in b]:
        problems.append("lineheads differ")
    for ra, rb in zip(a, b):
        for k in ("text", "heads", "excluded_notes", "inline_notes", "juan_marks"):
            if ra.get(k) != rb.get(k):
                problems.append("%s: %s differs" % (ra["linehead"], k))
                break
        if ra["div_types"] != rb["div_types"]:
            # ingest.lines takes div_types where the line's first content starts; on a line that
            # opened with the removed 科判 cb:mulu that is now the next element, one div deeper.
            # Allowed only as that case: a 科判 mulu at offset 0 and the old stack a prefix of the new
            # (tier 1's unit-end trim, its only reader, tests membership, which a deeper stack keeps)
            opened = bool(ra["mulu"]) and ra["mulu"][0]["type"] == KEPAN and ra["mulu"][0]["offset"] == 0
            if opened and rb["div_types"][: len(ra["div_types"])] == ra["div_types"]:
                shifted += 1
            else:
                problems.append("%s: div_types differs" % ra["linehead"])
        if [m for m in ra["mulu"] if m["type"] != KEPAN] != rb["mulu"]:
            problems.append("%s: non-科判 mulu differ" % ra["linehead"])
        if len(problems) > 5:
            break
    if problems:
        raise RuntimeError("sanitized %s differs beyond the 科判 mulu: %s" % (file_id, problems[:5]))
    kept_kepan = sum(1 for r in b for m in r["mulu"] if m["type"] == KEPAN)
    meta = {"file_id": file_id, "source": repo_relative(src), "source_sha256": src_sha,
            "path": repo_relative(out), "sha256": jsonio.sha256_file(out), "removed_kepan_mulu": removed,
            "kepan_mulu_left": kept_kepan, "lines": len(b), "div_types_shifted_lines": shifted,
            "check": "lineheads, text, heads, notes and juan marks identical to the source; mulu "
                     "identical minus type=科判; div_types identical except on lines that opened with a "
                     "removed 科判 mulu, where the stack is read one div deeper (old stack a prefix)"}
    jsonio.write_json(meta, meta_path)
    return out, meta


def kepan_label_leak(file_id: str) -> dict:
    """Does ingest put the gold's own 科判 labels (cb:mulu text) into the reading text? Counts only:
    labels found on their own line / within two lines / anywhere in the file (no label is printed)."""
    from chinese_workflow.ingest.text import load_input_text

    t = load_input_text(file_id, role="root")
    texts = [rec["text"] for rec in t.lines]
    full = "".join(texts)
    kp = [(i, m["text"]) for i, rec in enumerate(t.lines) for m in rec["mulu"] if m["type"] == KEPAN]
    own = sum(1 for i, s in kp if s and s in texts[i])
    near = sum(1 for i, s in kp if s and s in "".join(texts[max(0, i - 2): i + 3]))
    anywhere = [len(s) for i, s in kp if s and s in full]
    return {"kepan_mulu": len(kp), "label_in_own_line_text": own, "label_within_2_lines": near,
            "label_anywhere_in_text": len(anywhere),
            "anywhere_label_lengths": dict(sorted(Counter(anywhere).items())),
            "rule": "ingest.lines: cb:mulu content is never reading text (reported in `mulu` only)"}


# ---------------------------------------------------------------------------------------- spans


_XU = {}


def xu_span() -> str:
    """T0262-xu-root: Zhiyi's commentary over the T1718 dev + validation spans, i.e. the dev start
    to the last line before T34n1718_p0036a26 (the test span's start), never at or past it."""
    if "span" not in _XU:
        from chinese_workflow.ingest.lines import iter_lines

        guard = SplitGuard()
        guard.check_structure("T34n1718")  # lineheads only (no reading text): a structure-only read
        lhs = [rec["linehead"] for rec in iter_lines(cbeta_xml_path("T34n1718"))]
        registry = reg.load_registry()
        first, _ = resolve_span("dev", "T34n1718", lhs, registry)
        _, last = resolve_span("validation", "T34n1718", lhs, registry)
        assert last < "T34n1718_p0036a26" and lhs[lhs.index(last) + 1] == "T34n1718_p0036a26"
        assert split_of_line(registry, first) == "dev" and split_of_line(registry, last) == "validation"
        _XU["span"] = "%s..%s" % (first, last)
        _XU["guard"] = {"what": "xu_span: lineheads of T34n1718 (to resolve the dev+validation span)",
                        "entries": guard.report, "span": _XU["span"]}
    return _XU["span"]


def span_of(spec: dict):
    return xu_span() if spec["span"] == XU_SPAN else spec["span"]


# ---------------------------------------------------------------------------------------- llm


def llm_config(out: Path) -> LLMConfig:
    """The CLI's interactive config (outline/__main__.py _llm_config): run_dir = the cell's dir."""
    return LLMConfig(adapter="interactive", run_dir=out, model=INTERACTIVE_MODEL)


def _request_info(req_json: Path) -> dict:
    rec = jsonio.read_json(req_json)
    md = req_json.with_suffix(".md")
    request = rec.get("request") or {}
    prompt_chars = len(request.get("system") or "") + sum(
        len(m.get("content")) if isinstance(m.get("content"), str)
        else sum(len(b.get("text", "")) for b in m.get("content") or [])
        for m in request.get("messages") or [])
    resp = req_json.parent.parent / "responses" / req_json.name
    return {"hash": req_json.stem, "task": rec.get("task"), "request": repo_relative(req_json),
            "md": repo_relative(md), "response": repo_relative(resp),
            "md_chars": len(md.read_text(encoding="utf-8")) if md.exists() else None,
            "prompt_chars": prompt_chars,
            "candidates": len(((request.get("meta") or {}).get("candidates")) or [])}


def share_responses(out: Path) -> list:
    """Copy into this cell a response another cell already has for an identical request (same hash)."""
    reqs = out / "llm" / "requests"
    if not reqs.exists():
        return []
    copied = []
    for req in sorted(reqs.glob("*.json")):
        resp = out / "llm" / "responses" / req.name
        if resp.exists():
            continue
        for other in sorted(RUNS.glob("*/llm/responses/%s" % req.name)):
            if other.parent.parent.parent == out:
                continue
            resp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(other, resp)
            copied.append({"hash": req.stem, "from": repo_relative(other)})
            break
    return copied


def _invalid_hashes(report: dict) -> list:
    """Short hashes of requests whose response file was rejected (resolver tasks and gloss)."""
    out = []
    for task in ((report.get("resolver") or {}).get("tasks") or {}).values():
        out += [e.get("request") for e in task.get("invalid") or []]
    out += [e.get("request") for e in (report.get("gloss") or {}).get("invalid") or []]
    return [h for h in out if h]


# ---------------------------------------------------------------------------------------- build


def _origin_counts(doc: dict) -> dict:
    return dict(sorted(Counter(n.get("origin") for n in doc["nodes"]).items()))


def _guard_summary(entries: list) -> dict:
    splits = sorted({s for e in entries for s in e.get("splits") or []})
    return {"entries": len(entries), "splits_read": splits,
            "frozen": sorted({str(e.get("frozen")) for e in entries}),
            "test_or_reserve_read": bool(set(splits) & {"test", "reserve"})}


def pipeline_cell(name: str, spec: dict, arm: str, out: Path, guard: SplitGuard) -> dict:
    """tier1 / tier2 / hybrid / oracle (and the OOD *-markup diagnostics) through outline.pipeline.build.
    `guard` is build_cell's SplitGuard() (no frozen tag; module docstring)."""
    source = arm.split("-")[0]
    llm = None
    extra: dict = {}
    if spec["kind"] == "sutra":
        cfg = OutlineConfig(mode="sutra", root=spec["root"], commentary=spec["commentary"],
                            scheme_id=spec["scheme_id"], span=span_of(spec), source=source,
                            target_role=spec["target_role"], level1=list(spec["level1"]))
    else:
        xml = {}
        if spec["sanitize"] and not arm.endswith("-markup"):
            path, meta = no_kepan_xml(spec["root"])
            xml = {spec["root"]: str(path)}
            extra["input"] = meta
        elif arm.endswith("-markup"):
            extra["leaked"] = ("diagnostic: the input XML carries the gold's own cb:mulu type=科判, which "
                               "tier 1 turns into explicit nodes (outline/tier1.py, self-outlining mode)")
        cfg = OutlineConfig(mode="self-outlining", root=spec["root"], commentary=None,
                            scheme_id=spec["scheme_id"], span=None, source=source, target_role="root",
                            xml=xml)
    if source == "hybrid":
        cfg.resolver = {"adapter": "interactive"}
        llm = llm_config(out)
    res = build(cfg, out, guard=guard, llm_config=llm)
    rep = res["report"]
    pending = []
    resolver_pending = isinstance(rep.get("resolver"), dict) and "requests" in rep["resolver"]
    for p in res["pending"]:
        info = _request_info(Path(p))
        info["state"] = "deferred" if (info["task"] == "gloss" and resolver_pending) else "open"
        pending.append(info)
    state = {
        "status": "pending" if pending or _invalid_hashes(rep) else "built",
        "nodes": res["doc"]["metadata"]["node_count"],
        "max_depth": res["doc"]["metadata"]["max_depth"],
        "origins": _origin_counts(res["doc"]),
        "pending": pending,
        "invalid": _invalid_hashes(rep),
        "tier2_rejected_doctrinal_lists": len(((rep.get("tier2") or {}).get("rejected")) or []),
        "degraded": [{"stage": e.get("stage"), "errors": len(e.get("errors") or []),
                      "repairs": len(e.get("repairs") or []),
                      "repair_kinds": dict(Counter(str((x or {}).get("kind")) if isinstance(x, dict)
                                                   else "?" for x in e.get("repairs") or []))}
                     for e in rep.get("degraded") or []],
        "guard": _guard_summary(rep.get("split_guard") or []),
        "config": {"mode": cfg.mode, "root": cfg.root, "commentary": cfg.commentary,
                   "scheme_id": cfg.scheme_id, "span": cfg.span, "source": cfg.source,
                   "target_role": cfg.target_role, "level1": [e["heading_src"] for e in cfg.level1],
                   "xml_override": {k: repo_relative(v) for k, v in cfg.xml.items()},
                   "resolver": cfg.resolver, "guard_frozen": guard.frozen},
        **extra,
    }
    if source == "hybrid":
        state["resolver"] = _resolver_summary(rep.get("resolver"))
        state["gloss"] = {k: v for k, v in (rep.get("gloss") or {}).items()
                          if k in ("status", "requests", "answered", "filled")}
        if isinstance((rep.get("gloss") or {}).get("requests"), list):
            state["gloss"]["requests"] = len(rep["gloss"]["requests"])
    return state


def _resolver_summary(r) -> dict:
    if not isinstance(r, dict):
        return {}
    if "tasks" not in r:  # pending: {"status", "requests": [paths]}
        tasks = Counter(jsonio.read_json(p).get("task") for p in r.get("requests") or [])
        return {"status": r.get("status"), "pending_by_task": dict(tasks)}
    out = {"status": r.get("status"), "scheme_id": r.get("scheme_id"), "tasks": {}}
    for t, tr in r["tasks"].items():
        out["tasks"][t] = {k: (len(v) if isinstance(v, list) else v) for k, v in tr.items()
                           if k in ("requests", "answered", "no_model", "pending", "invalid", "accepted",
                                    "rejected", "ignored", "not_answered", "skipped")}
    return out


def model_only_cell(name: str, spec: dict, arm: str, out: Path, guard: SplitGuard) -> dict:
    """The model outlines the root text's target 品 with no commentary (module docstring)."""
    from chinese_workflow.ingest.text import load_input_text
    from chinese_workflow.outline import anchor, render, resolver, scheme, tier1

    root = load_input_text(spec["root"], role="root")
    guard.check_lines(root.all_lineheads, purpose="model-only: %s root text" % spec["root"])
    pins = tier1.build(root, mode="sutra", role="root").pins
    pin = next(p for p in pins if p.part_type == tier1.CHAPTER_TYPE and p.name == spec["target_pin"])
    draft = {
        "heading_src": pin.heading, "part_type": pin.part_type, "origin": "explicit", "confidence": 1.0,
        "evidence": "cb:mulu type=%s level=%s on %s: %s" % (pin.part_type, pin.level, pin.start,
                                                           pin.heading),
        "node_class": "sutra-span", "flags": [],
        "notes": ["tier 1 root 品 pin (model-only run: no commentary)"],
        "locations": {"scheme": "cbeta-kepan", "commentary": None,
                      "root_text": {"start": pin.start, "end": pin.end, "basis": "chapter",
                                    "end_basis": None}},
        "children": [],
    }
    roots, scheme_report = [draft], []
    if spec["level1"]:
        roots, scheme_report = scheme.apply_level1(roots, spec["level1"], root_pins=pins)
    prompts = resolver.load_prompts(resolver.RESOLVER_PROMPT, resolver.RESOLVER_REFERENCES,
                                    resolver.OPTIONAL_REFERENCES)
    model_scheme = "model-%s" % prompts.sha[:8]  # resolver.resolve's default for scheme_id=None (D21)
    commit = outline_doc.pipeline_commit()
    doc, _ = outline_doc.build_prediction(
        roots, text_id="T0262", text_title_src=root.info.get("title") or spec["root"],
        outline_mode="sutra", root_text_id=spec["root"], commentary_id=None, scheme_id=model_scheme,
        source_file=repo_relative(root.source_path),
        source_document={"kind": "root-text", "text_id": spec["root"],
                         "title": root.info.get("title") or spec["root"], "url": None,
                         "notes": ["model-only run (E07, D21): the resolver outlines the root text's "
                                   "%s with no commentary" % pin.heading]},
        generated_by="experiments/E07-capability-sweep-v1/run_e07.py model-only over chinese_workflow."
                     "outline (tier1 pin + scheme prior + resolver subdivide) @ %s%s"
                     % ((commit["commit"] or "unknown")[:12], "+dirty" if commit["dirty"] else ""),
        format_note="Model-only prediction (D21): the tier-1 root 品 pin %s..%s%s, subdivided by the "
                    "resolver's subdivide task (interactive adapter, no commentary) for up to %d rounds."
                    % (pin.start, pin.end, " under the project's level-1 scheme prior"
                       if spec["level1"] else "", MODEL_ONLY_ROUNDS),
        source_sha256=jsonio.sha256_file(root.source_path),
        span={"first": pin.start, "last": pin.end}, genre_gate=None)
    first = outline_doc.validate(doc)
    if not first.passed():
        raise RuntimeError("model-only skeleton fails validation: %s"
                           % [f.render() for f in first.errors[:5]])
    llm = llm_config(out)
    rounds, pending = [], []
    for r in range(1, MODEL_ONLY_ROUNDS + 1):
        before = doc
        try:
            doc, rep = resolver.resolve(doc, root=root, commentary=None, config=llm,
                                        tasks=("subdivide",), scheme_id=None)
        except PendingInteractive as exc:
            pending = [str(p) for p in exc.requests]
            rounds.append({"round": r, "status": "pending", "requests": len(pending)})
            break
        outline_doc.assert_explicit_unchanged(before, doc)
        sub = rep["tasks"]["subdivide"]
        rounds.append({"round": r, "status": rep["status"], "requests": sub["requests"],
                       "accepted": len(sub["accepted"]), "rejected": len(sub["rejected"]),
                       "invalid": len(sub["invalid"]), "skipped": len(sub["skipped"]),
                       "nodes_after": len(doc["nodes"]),
                       "invalid_hashes": [e["request"] for e in sub["invalid"]],
                       "invalid_errors": {e["request"]: e.get("error") for e in sub["invalid"]}})
        if len(doc["nodes"]) == len(before["nodes"]):
            break  # nothing accepted: a further round would re-offer the same leaves (same request)
    outline_doc.refresh_counts(doc)
    val = outline_doc.validate(doc, "outline.json")
    out.mkdir(parents=True, exist_ok=True)
    opath = jsonio.write_json(doc, out / "outline.json")
    (out / "outline.md").write_text(render.render_markdown(doc), encoding="utf-8")
    target = slice_text(root, (pin.start, pin.end))
    sidecar, md = anchor.outlined_text(doc, target, target_role="root",
                                       outline_ref={"path": repo_relative(opath),
                                                    "sha256": jsonio.sha256_file(opath)})
    jsonio.write_json(sidecar, out / "outlined-text.json")
    (out / "outlined-text.md").write_text(md, encoding="utf-8")
    (out / "target.txt").write_text(target.text, encoding="utf-8")
    jsonio.write_json({"scheme": scheme_report, "rounds": rounds, "split_guard": guard.report,
                       "validation": {"passed": val.passed(), "errors": [f.render() for f in val.errors],
                                      "warnings": [f.render() for f in val.warnings]}},
                      out / "outline-report.json")
    if not val.passed():
        raise RuntimeError("model-only outline fails validation: %s" % [f.render() for f in val.errors[:5]])
    infos = []
    for p in pending:
        info = _request_info(Path(p))
        info["state"] = "open"
        infos.append(info)
    return {
        "status": "pending" if infos or any(rd.get("invalid_hashes") for rd in rounds) else "built",
        "nodes": doc["metadata"]["node_count"], "max_depth": doc["metadata"]["max_depth"],
        "origins": _origin_counts(doc), "pending": infos,
        "invalid": [h for rd in rounds for h in rd.get("invalid_hashes", [])],
        "rounds": rounds, "rounds_max": MODEL_ONLY_ROUNDS, "model_scheme": model_scheme,
        "guard": _guard_summary(guard.report),
        "config": {"mode": "sutra", "root": spec["root"], "commentary": None, "target_pin": pin.heading,
                   "target_span": [pin.start, pin.end],
                   "level1": [e["heading_src"] for e in spec["level1"]],
                   "resolver": {"adapter": "interactive", "tasks": ["subdivide"],
                                "model": INTERACTIVE_MODEL}, "guard_frozen": guard.frozen},
    }


def build_cell(name: str, spec: dict, arm: str) -> dict:
    out = cell_dir(name, arm)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    copied: list = []
    state: dict = {}
    guard = SplitGuard()
    try:
        for _ in range(4):  # build; when another cell already answered a new request, rebuild
            if arm in LLM_ARMS:
                copied += share_responses(out)
            guard = SplitGuard()  # no frozen tag (module docstring); one per build attempt
            state = (model_only_cell if arm == "model-only" else pipeline_cell)(name, spec, arm, out,
                                                                                 guard)
            if arm not in LLM_ARMS or not share_responses_probe(out):
                break
    except Exception as exc:  # noqa: BLE001 - a failed cell is recorded, the sweep goes on
        state = {"status": "failed", "error": "%s: %s" % (type(exc).__name__, exc),
                 "traceback": traceback.format_exc(),
                 "guard": _guard_summary(guard.report),  # what the failed attempt read
                 "guard_log": [{k: v for k, v in e.items()} for e in guard.report]}
    state.update({"cell": out.name, "set": name, "arm": arm, "built_at": now(),
                  "seconds": round(time.time() - t0, 1), "reused_responses": copied,
                  "diagnostic": arm in DIAGNOSTIC_ARMS,
                  "provenance": {k: v for k, v in provenance().items()
                                 if k in ("pipeline_commit", "tag", "tag_commit",
                                          "pipeline_identical_to_tag", "scorer", "harness_sha256")}})
    opath = out / "outline.json"
    if state["status"] != "failed" and opath.exists():
        state["outline_sha256"] = jsonio.sha256_file(opath)
    jsonio.write_json(state, out / "cell.json")
    return state


def share_responses_probe(out: Path) -> bool:
    """True when another cell holds a response to one of this cell's unanswered requests."""
    reqs = out / "llm" / "requests"
    if not reqs.exists():
        return False
    for req in reqs.glob("*.json"):
        if (out / "llm" / "responses" / req.name).exists():
            continue
        if any(o.parent.parent.parent != out for o in RUNS.glob("*/llm/responses/%s" % req.name)):
            return True
    return False


def cmd_build(args) -> int:
    rc = 0
    for name, spec, arm in cells(args.set, args.arm):
        st = build_cell(name, spec, arm)
        line = "%-34s %-8s nodes %-5s pending %-3d %5.1fs" % (
            st["cell"], st["status"], st.get("nodes", "-"),
            sum(1 for p in st.get("pending") or [] if p["state"] in ("open", "deferred")),
            st["seconds"])
        if st["status"] == "failed":
            line += "  " + st["error"][:160]
            rc = 1
        print(line, flush=True)
    return rc


# ------------------------------------------------------------------------------------------ pending


def load_cell(name: str, arm: str) -> dict | None:
    p = cell_dir(name, arm) / "cell.json"
    return jsonio.read_json(p) if p.exists() else None


def pending_requests() -> list:
    """Every request file under runs/ without a response, with its state: open (the cell's last build
    waits on it), deferred (gloss written while the resolver waits), stale (no longer asked by the
    last build), or invalid (a response exists and was rejected)."""
    owners = {cell_dir(n, a).name: (n, a) for n, _, a in cells()}
    out = []
    for req in sorted(RUNS.glob("*/llm/requests/*.json")):
        cdir = req.parent.parent.parent
        name, arm = owners.get(cdir.name, (None, None))
        st = load_cell(name, arm) if name else None
        listed = {p["hash"]: p for p in (st or {}).get("pending") or []}
        resp = cdir / "llm" / "responses" / req.name
        invalid = {h for h in (st or {}).get("invalid") or []}
        if resp.exists():
            if req.stem[:12] in invalid:
                state = "invalid"
            else:
                continue
        else:
            state = listed[req.stem]["state"] if req.stem in listed else "stale"
        info = _request_info(req)
        info.update({"cell": cdir.name, "set": name, "arm": arm, "state": state})
        out.append(info)
    seen: dict = {}
    for info in out:  # identical requests in two cells: answer the first, build copies it
        if info["state"] in ("open", "deferred"):
            if info["hash"] in seen:
                info["duplicate_of"] = seen[info["hash"]]
            else:
                seen[info["hash"]] = info["cell"]
    return out


def pending_summary(items: list) -> dict:
    by_cell: dict = {}
    by_task: dict = {}
    totals = Counter()
    for it in items:
        dup = bool(it.get("duplicate_of"))
        key = it["state"] + ("_duplicate" if dup else "")
        totals[key] += 1
        c = by_cell.setdefault(it["cell"], Counter())
        c[key] += 1
        if it["state"] == "open" and not dup:
            c["open_md_chars"] += it["md_chars"] or 0
        t = by_task.setdefault(it["task"], Counter())
        t[key] += 1
        if it["state"] in ("open", "deferred") and not dup:
            t["md_chars"] += it["md_chars"] or 0
            t["max_md_chars"] = max(t["max_md_chars"], it["md_chars"] or 0)
    answer_now = [it for it in items if it["state"] == "open" and not it.get("duplicate_of")]
    sizes = sorted(it["md_chars"] or 0 for it in answer_now)
    return {
        "totals": dict(totals),
        "answer_now": len(answer_now),
        "answer_now_md_chars": {"sum": sum(sizes), "min": sizes[0] if sizes else None,
                                "median": sizes[len(sizes) // 2] if sizes else None,
                                "max": sizes[-1] if sizes else None},
        "by_cell": {k: dict(v) for k, v in sorted(by_cell.items())},
        "by_task": {k: dict(v) for k, v in sorted(by_task.items())},
        "how_to_answer": "read each open request's .md, write the JSON answer to its response path, "
                         "then re-run `run_e07.py build` (deferred gloss requests are re-asked after "
                         "the cell's resolver finishes; duplicates are copied from the first cell)",
    }


def invalid_reason(it: dict) -> str | None:
    """The pipeline's rejection message for an invalid response (E07: for the answerer's retry)."""
    out = RUNS / it["cell"]
    h = it["hash"][:12]
    rep = out / "outline-report.json"
    if rep.exists():
        r = jsonio.read_json(rep)
        for task in ((r.get("resolver") or {}).get("tasks") or {}).values():
            for e in task.get("invalid") or []:
                if e.get("request") == h:
                    return e.get("error")
        for e in (r.get("gloss") or {}).get("invalid") or []:
            if e.get("request") == h:
                return e.get("error")
        for rd in r.get("rounds") or []:
            if h in (rd.get("invalid_errors") or {}):
                return rd["invalid_errors"][h]
    st = load_cell(it["set"], it["arm"]) or {}
    for rd in st.get("rounds") or []:
        if h in (rd.get("invalid_errors") or {}):
            return rd["invalid_errors"][h]
    return None


def cmd_pending(args) -> int:
    items = pending_requests()
    if args.set:
        items = [it for it in items if it["set"] in args.set]
    summ = pending_summary(items)
    if args.compact:  # E07: one line per request to answer now (open or invalid, not a duplicate)
        todo = [it for it in items if it["state"] in ("open", "invalid") and not it.get("duplicate_of")]
        for it in todo:
            print("%s %s %s %s %s" % (it["state"], it["cell"], it["task"], it["hash"], it["md_chars"]))
            if it["state"] == "invalid":
                print("REASON %s" % " ".join(str(invalid_reason(it)).split())[:600])
        print("END open=%d invalid=%d deferred=%d" % (
            sum(1 for it in todo if it["state"] == "open"), sum(1 for it in todo if it["state"] == "invalid"),
            sum(1 for it in items if it["state"] == "deferred")))
        return 0
    if args.json:
        json.dump({"generated": now(), "summary": summ, "requests": items}, sys.stdout,
                  ensure_ascii=False, indent=1)
        print()
        return 0
    for it in items:
        print("%-9s %-34s %-22s %6s chars  %s%s" % (
            it["state"], it["cell"], it["task"], it["md_chars"], it["md"],
            "  (duplicate of %s)" % it["duplicate_of"] if it.get("duplicate_of") else ""))
    print(json.dumps({k: summ[k] for k in ("totals", "answer_now", "answer_now_md_chars")},
                     ensure_ascii=False))
    return 0


# -------------------------------------------------------------------------------------------- score

E07_NO_HEADLINE = "E07 README: 'None is a headline' (dev / validation, draft or imported-unchecked golds)"


def _headline_reasons(m: dict, name: str, arm: str) -> list:
    """Why an E07 row is not a headline: the scorer's reasons plus the README's (since the review of E06
    the scorer's NO_HEADLINE_STATUS includes imported-unchecked; the README's reasons are added anyway)."""
    d = m["disclosures"]
    reasons = list(d.get("headline_reasons") or [])
    if d.get("gold_status") == "imported-unchecked":
        reasons.append("gold_status imported-unchecked (E07 README)")
    if name.startswith("OOD-"):
        reasons.append("out-of-domain set (E07 README)")
    if arm in DIAGNOSTIC_ARMS:
        reasons.append("LEAKED input: the OOD gold's own 科判 markup (diagnostic, not a hypothesis row)")
    reasons.append(E07_NO_HEADLINE)
    return reasons


DIAG_FIELDS = ("fn_split", "tp_rule", "s_f1_both_counted", "tp_uncounted_pred", "tp_le_counted_pred",
               "key_lines", "fp_by_kind", "without_span_start_inherited", "ancestor_consistent",
               "reanchor", "depth_offset_hist")


def _diag(r: dict) -> dict | None:
    """The follow-up scorer's diagnostic fields of one t-row (E07; aggregate numbers only)."""
    if not r.get("available"):
        return None
    return {k: r.get(k) for k in DIAG_FIELDS if k in r}


def _row(m: dict, name: str, arm: str) -> dict:
    """The aggregate parts of one scorer result (no gold ids, headings or notes)."""
    head = m["rows"].get(m["headline_row"], {})
    t1 = m["rows"].get("t=1", {})
    cc = m.get("child_count") or {}
    disclosures = {k: m["disclosures"].get(k) for k in (
        "gold_status", "seeded_by", "eval_only", "split", "t", "key", "pairing_warnings", "notes")}
    disclosures.update({"headline": False, "headline_reasons": _headline_reasons(m, name, arm),
                        "scorer_headline": m["disclosures"].get("headline")})
    return {
        "headline_row": m["headline_row"],
        "s_f1": m.get("s_f1"),
        "f_f1": m.get("f_f1"),
        "s_f1_t1": t1.get("s_f1") if t1.get("available") else None,
        "f_f1_t1": t1.get("f_f1") if t1.get("available") else None,
        "locator_only": head.get("locator_only"),
        "locator_only_t1": t1.get("locator_only") if t1.get("available") else None,
        "heading_only": head.get("heading_only"),
        "without_anchor_inherited": head.get("without_anchor_inherited"),
        "per_depth": head.get("per_depth"),
        "exempt_under_truncated": head.get("exempt_under_truncated"),
        "absorbed_into_merged_range": head.get("absorbed_into_merged_range"),
        "matched_to_gold_outside_scope": head.get("matched_to_gold_outside_scope"),
        "child_count": {k: cc.get(k) for k in ("eligible", "correct", "wrong", "missing",
                                               "source_disagreements", "accuracy")},
        "diag": {"t=0": _diag(m["rows"].get("t=0", {})), "t=1": _diag(t1)},
        "counts": m["counts"],
        "disclosures": disclosures,
        "settings": {k: m["settings"].get(k) for k in ("key", "split", "frozen", "line_order")},
    }


def _gold_sha(gold_id: str, registry: dict) -> str:
    return jsonio.sha256_file(REPO_ROOT / reg.dataset(registry, gold_id)["path"])


def frozen_for(rowspec: dict, st: dict | None, prov: dict) -> tuple[str | None, str | None]:
    """(frozen value to pass, reason the row is not scored). An OOD row gets frozen=TAG only when
    pipeline/ is identical to the tag now AND was when the cell was built (cell.json provenance)."""
    if not rowspec.get("frozen"):
        return None, None
    built = (st or {}).get("provenance") or {}
    if not prov["pipeline_identical_to_tag"]:
        return None, "not frozen: pipeline/ differs from %s now" % TAG
    if not built.get("pipeline_identical_to_tag") or built.get("tag_commit") != prov["tag_commit"]:
        return None, ("not frozen: the cell was built without provenance or with pipeline/ differing "
                      "from %s (rebuild it)" % TAG)
    return rowspec["frozen"], None


def row_inputs(out: Path, rowspec: dict, registry: dict, prov: dict, frozen: str | None) -> dict:
    """The score cache key of one cell and one score row."""
    return {"outline_sha256": jsonio.sha256_file(out / "outline.json"), "gold": rowspec["gold"],
            "gold_sha256": _gold_sha(rowspec["gold"], registry), "key": rowspec["key"],
            "split": rowspec["split"], "frozen": frozen, "registry_sha256": prov["registry_sha256"],
            "scorer": prov["scorer"]}


def cached_row(out: Path, rowspec: dict, inputs: dict) -> dict | None:
    cache = out / ("score-%s.json" % rowspec["row"])
    if cache.exists():
        old = jsonio.read_json(cache)
        if old.get("inputs") == inputs:
            return old["metrics"]
    return None


def compute_row(out: Path, rowspec: dict, inputs: dict, registry: dict) -> dict:
    m = score(jsonio.read_json(out / "outline.json"), rowspec["gold"], key=rowspec["key"],
              split=rowspec["split"], frozen=inputs["frozen"], registry=registry)
    jsonio.write_json({"inputs": inputs, "scored_at": now(), "metrics": m},
                      out / ("score-%s.json" % rowspec["row"]))
    return m


def gold_self(registry: dict, prov: dict) -> dict:
    """Sanity (README "Method"): each gold scored against itself on every row of the matrix. No system
    output is involved, so these are not looks. OOD rows follow frozen_for's pipeline/ rule."""
    cache_p = RUNS / "_sanity" / "gold-self.json"
    cache = jsonio.read_json(cache_p) if cache_p.exists() else {}
    out = {}
    for name, spec in SETS.items():
        for r in spec["rows"]:
            k = "%s/%s" % (name, r["row"])
            if r.get("frozen") and not prov["pipeline_identical_to_tag"]:
                out[k] = {"status": "not frozen: pipeline/ differs from %s" % TAG}
                continue
            sig = [r["gold"], _gold_sha(r["gold"], registry), r["key"], r["split"], r.get("frozen"),
                   prov["registry_sha256"], prov["scorer"], "e07-triple"]
            if cache.get(k, {}).get("sig") == sig:
                out[k] = cache[k]
                continue
            gold = jsonio.read_json(REPO_ROOT / reg.dataset(registry, r["gold"])["path"])
            if r["key"] == "commentary.span_start":
                # E07: the scorer reads a gold at its explained line under this key (no gold has the
                # field), so the gold as a prediction carries span_start = explained, never inherited
                for n in gold["nodes"]:
                    c = (n.get("locations") or {}).get("commentary")
                    if isinstance(c, dict) and c.get("explained"):
                        c["span_start"], c["span_start_inherited"] = c["explained"], False
            m = score(gold, r["gold"], key=r["key"], split=r["split"], frozen=r.get("frozen"),
                      registry=registry)
            d1 = m["rows"].get("t=1") or {}
            out[k] = {"sig": sig, "s_f1": m.get("s_f1"), "f_f1": m.get("f_f1"),
                      "gold_counted": m["counts"]["gold"]["counted"],
                      # E07: the attachment-tolerant triple of a gold against itself (expect F 1, 0 anchors,
                      # every offset 0), or unavailable above AC_MAX_FOREST_NODES
                      "triple_t1": {"ac_F": (d1.get("ancestor_consistent") or {}).get("F"),
                                    "anchors": (d1.get("reanchor") or {}).get("anchors"),
                                    "offset_mode": (d1.get("depth_offset_hist") or {}).get("mode"),
                                    "available": (d1.get("ancestor_consistent") or {}).get("available")}}
    jsonio.write_json(out, cache_p)
    return out


def xu_region_check(registry: dict) -> dict:
    """T0262-xu-root: may a prediction outside 序品 be counted? Under the scorer's root-text rule a
    predicted node takes the split of the gold region its root line falls in, so it is counted in the
    dev / validation rows only when that region's split is dev / validation. Counted from the gold's
    locators only (lines of T09n0262 per region split); no heading is read and no gold locator is
    written (the sdp gold is eval-only: only counts and line offsets from the tier-1 pin)."""
    import bisect

    from chinese_workflow.ingest.lines import iter_lines
    from chinese_workflow.ingest.text import load_input_text
    from chinese_workflow.outline import tier1

    guard = SplitGuard()
    guard.check_structure("T09n0262")
    lhs = [rec["linehead"] for rec in iter_lines(cbeta_xml_path("T09n0262"))]
    guard.check_lines(lhs, purpose="design check xu_region: T09n0262 lineheads and 品 pins")
    idx = {lh: i for i, lh in enumerate(lhs)}
    pins = tier1.build(load_input_text("T09n0262", role="root"), mode="sutra", role="root").pins
    xu = next(p for p in pins if p.part_type == "品" and p.name == "序")
    lo, hi = idx[xu.start], idx[xu.end]
    gold = jsonio.read_json(REPO_ROOT / reg.dataset(registry, "sdp-T0262-zhiyi-wenju")["path"])
    ent = []
    for k, n in enumerate(gold["nodes"]):
        loc = n.get("locations") or {}
        if loc.get("scheme") != "cbeta-kepan":
            continue
        rs = ((loc.get("root_text") or {}).get("start") or "").split(":")[0]
        ex = ((loc.get("commentary") or {}).get("explained") or "").split(":")[0]
        if rs not in idx:
            continue
        sp = reg.split_of(registry, "T1718", ex) if ex.startswith("T34n1718") else None
        ent.append(((idx[rs], k), sp))
    ent.sort()
    keys = [e[0] for e in ent]
    c = Counter()
    for i in range(len(lhs)):
        j = bisect.bisect_right(keys, (i, 10 ** 9)) - 1
        sp = ent[j][1] if j >= 0 else None
        c["%s/%s" % ("xu" if lo <= i <= hi else "outside", sp)] += 1
    j = bisect.bisect_right(keys, (lo, 10 ** 9)) - 1
    pin_region = ent[j][1] if j >= 0 else None  # the region the tier-1 序品 pin's own line falls in
    outside_counted = sum(v for k, v in c.items() if k.split("/")[0] == "outside"
                          and k.split("/")[1] in ("dev", "validation"))
    # the gold's top nodes counted in dev vs the tier-1 序品 node every arm puts at level 1
    tops = sorted({((n.get("locations") or {}).get("root_text") or {}).get("start", "").split(":")[0]
                   for n in gold["nodes"] if n.get("level") == 1
                   and (((n.get("locations") or {}).get("commentary") or {}).get("explained") or "")
                   .startswith("T34n1718")
                   and reg.split_of(registry, "T1718", n["locations"]["commentary"]["explained"]
                                    .split(":")[0]) == "dev"})
    return {"xu_span": [xu.start, xu.end], "lines_by_region_split": dict(sorted(c.items())),
            "top_level": {"tier1_pin_start": xu.start, "gold_dev_level1_start_lines": len(tops),
                          "line_offsets_from_tier1_pin": sorted(idx[t] - idx[xu.start]
                                                                for t in tops if t in idx)},
            "tier1_pin_line_region_split": pin_region,  # None = split_unknown: not counted
            "outside_lines_in_dev_or_validation_regions": outside_counted,
            "restriction_applied": outside_counted > 0,
            "decision": "no restriction needed: the scorer's region rule never counts a prediction "
                        "outside 序品 in the dev or validation row" if outside_counted == 0 else
                        "predictions outside 序品 can be counted: restrict them",
            "guard": _guard_summary(guard.report)}


def reachability_check(registry: dict, sanity: dict) -> dict:
    """For each split-scoped row: how many counted gold nodes the cell's build can reach at all. Matching
    is top-down (score.py _match), so a counted gold node is matchable only if every ancestor in the
    scorer's tree can be matched too: an ancestor of a split the cell's build span covers, or a level-1
    node the set's level-1 scheme prior supplies. Recomputed with the scorer's own _Tree / _SplitMap and
    its split, served-scope and coverage rules; aggregate counts only (no id, line or heading)."""
    from chinese_workflow.common.lineheads import file_id, strip_offset
    from chinese_workflow.eval import score as sc

    trees: dict = {}
    out: dict = {}
    for name, spec in SETS.items():
        if spec["kind"] != "sutra":
            continue
        covered = set(SPAN_SPLITS[spec["span"]])
        for r in spec["rows"]:
            gid, key, split = r["gold"], r["key"], r["split"]
            if (gid, key) not in trees:
                ds = reg.dataset(registry, gid)
                gold = jsonio.read_json(REPO_ROOT / ds["path"])
                gt = sc._Tree(gold, key, "gold")
                lines = sc._Lines({file_id(k) for k in gt.key.values()})
                sm = sc._SplitMap(registry, ds, key, gt, lines)
                sp = {g: sm.of(gt.by_id[g], gt.key[g], "gold") for g in gt.key}
                trees[(gid, key)] = (ds, gold, gt, lines, sp)
            ds, gold, gt, lines, sp = trees[(gid, key)]
            served_key = sc._by_to_key(ds["scoring_scope"]["key"]) if ds.get("scoring_scope") else None
            coverage = (gold.get("metadata") or {}).get("coverage_spans") or []

            def in_cov(g):
                for e in coverage:
                    span = e.get("commentary" if key in ("commentary.explained", "commentary.span_start")
                                 else "root_text") or {}
                    if not (span.get("start") and span.get("end")):
                        continue
                    if lines.within(gt.key[g], strip_offset(span["start"]), strip_offset(span["end"])) \
                            and (e.get("max_level") is None or gt.level[g] <= e["max_level"]):
                        return True
                return False

            counted = [g for g in gt.key if sp[g] == split
                       and (served_key is None
                            or reg.in_scoring_scope(registry, gid, sc.locator(gt.by_id[g], served_key)))
                       and (not coverage or in_cov(g))]
            reach, blocked = 0, Counter()
            for g in counted:
                bad = set()
                a = gt.parent[g]
                while a is not None:
                    if sp[a] not in covered and not (spec["level1"] and gt.level[a] == 1):
                        bad.add(str(sp[a]))
                    a = gt.parent[a]
                if bad:
                    blocked["/".join(sorted(bad))] += 1
                else:
                    reach += 1
            self_row = sanity.get("%s/%s" % (name, r["row"])) or {}
            out["%s/%s" % (name, r["row"])] = {
                "build_span_splits": sorted(covered), "level1_prior": bool(spec["level1"]),
                "counted": len(counted),
                "counted_matches_gold_self": len(counted) == self_row.get("gold_counted"),
                "reachable": reach,
                "unreachable_by_ancestor_split": dict(sorted(blocked.items())),
                "zero_by_construction": bool(counted) and reach == 0,
            }
    return out


# ------------------------------------------------------------------------------------------ looks


LOOKS_NOTE = ("Every validation-row score computed by run_e07.py (a cached re-read is not a new score). "
              "kind `look` = a (set, row, arm, outline sha256, gold sha256) scored for the first time; kind "
              "`recompute` = a re-score of one already seen (e.g. after a score-cache key change): no new "
              "information. Each score run appends one entry per set with new looks to "
              "experiments/E01-explicit-recovery/looks.json (e01_entry = that entry's date); "
              "arms_not_yet_scorable lists the set's arms that were still pending at that look.")


def load_looks() -> dict:
    """looks-e07.json, migrated to format 2 (format 1: e01_entries keyed by set, events without kind;
    gold sha256 back-filled from the cell's score cache when its outline sha256 matches)."""
    if not LOOKS_E07.exists():
        return {"note": LOOKS_NOTE, "format": 2, "e01_entries": [], "events": []}
    looks = jsonio.read_json(LOOKS_E07)
    if looks.get("format") != 2:
        old = looks.get("e01_entries") or {}
        by_set = old if isinstance(old, dict) else {}
        for ev in looks.get("events") or []:
            hit = by_set.get(ev["set"])
            ev.setdefault("kind", "look")
            ev.setdefault("e01_entry", hit["date"] if hit and ev["arm"] in hit.get("arms", [])
                          and ev["date"] <= hit["date"] else None)
            if "gold_sha256" not in ev:
                cache = cell_dir(ev["set"], ev["arm"]) / ("score-%s.json" % ev["row"])
                inp = jsonio.read_json(cache).get("inputs", {}) if cache.exists() else {}
                if inp.get("outline_sha256") == ev.get("outline_sha256") and inp.get("gold_sha256"):
                    ev["gold_sha256"] = inp["gold_sha256"]
                    ev["gold_sha256_from"] = "score cache at migration"
        looks = {"note": LOOKS_NOTE, "format": 2, "migrated_from_format_1": now(),
                 "e01_entries": list(old.values()) if isinstance(old, dict) else list(old),
                 "events": looks.get("events") or []}
    looks["note"] = LOOKS_NOTE
    return looks


def save_looks(looks: dict) -> None:
    jsonio.write_json(looks, LOOKS_E07)


def look_seen(looks: dict, cand: dict, kind: str = "look") -> bool:
    for e in looks["events"]:
        if e.get("kind") == kind and all(e.get(k) == cand[k] for k in ("set", "row", "arm",
                                                                        "outline_sha256")) \
                and e.get("gold_sha256") in (None, cand["gold_sha256"]):
            return True
    return False


def record_look(looks: dict, cand: dict, new: bool, blockers: list, prov: dict, inputs: dict,
                kind: str = "look") -> None:
    ev = dict(cand, date=now(), kind=kind if new else "recompute",
              registry_sha256=inputs["registry_sha256"], scorer=inputs["scorer"],
              commit=prov["pipeline_commit"], tag=TAG)
    if new:
        ev.update({"arms_not_yet_scorable": blockers, "e01_entry": None})
    looks["events"].append(ev)
    save_looks(looks)


def flush_e01_looks(prov: dict) -> list:
    """Append to E01's looks.json one entry per set whose look events have no E01 entry yet (E01's
    convention: append, never edit). Built from looks-e07.json, so it also catches looks recorded by an
    earlier run that stopped before its flush."""
    looks = load_looks()
    todo: dict = {}
    for e in looks["events"]:
        if e.get("kind") == "look" and not e.get("e01_entry"):
            todo.setdefault(e["set"], []).append(e)
    if not todo:
        save_looks(looks)
        return []
    e01 = jsonio.read_json(E01_LOOKS)
    date = now()
    added = []
    for name, evs in todo.items():
        earlier = [x for x in looks["e01_entries"] if x["set"] == name]
        entry = {"date": date, "split": "validation", "set": name, "commit": prov["pipeline_commit"],
                 "arms": sorted({e["arm"] for e in evs}),
                 "outline_sha256": {e["arm"]: e["outline_sha256"] for e in evs},
                 "scored_at": sorted({e["date"] for e in evs}),
                 "arms_not_yet_scorable": sorted({b for e in evs for b in e.get("arms_not_yet_scorable")
                                                  or []}),
                 "note": LOOK_NOTE + ("; continues the E06 entry of %s for this set (arms scored in a "
                                      "later pass)" % earlier[-1]["date"] if earlier else "")}
        e01["looks"].append(entry)
        looks["e01_entries"].append(entry)
        for e in evs:
            e["e01_entry"] = date
        added.append(name)
    jsonio.write_json(e01, E01_LOOKS)
    save_looks(looks)
    return added


def looks_summary(looks: dict) -> dict:
    """Per set with a validation row: each non-diagnostic arm's first look and the passes it took."""
    out = {}
    for name, spec in SETS.items():
        if not any(r.get("look") or r.get("ood_look") for r in spec["rows"]):
            continue
        arms = [a for a in spec["arms"] if a not in DIAGNOSTIC_ARMS]
        evs = [e for e in looks["events"] if e["set"] == name]
        first = {a: min((e["date"] for e in evs if e["arm"] == a
                         and e.get("kind") in ("look", "ood-look")), default=None) for a in arms}
        dates = sorted({d for d in first.values() if d})
        out[name] = {
            "first_look_by_arm": first,
            "kind": "ood-look" if name.startswith("OOD-") else "look",
            "look_events": sum(1 for e in evs if e.get("kind") in ("look", "ood-look")),
            "recompute_events": sum(1 for e in evs if e.get("kind") == "recompute"),
            "arms_not_looked": [a for a in arms if not first[a]],
            "passes": len({d[:16] for d in dates}),
            "one_pass_over_all_arms": bool(dates) and all(first.values())
                                      and len({d[:16] for d in dates}) == 1,
            "e01_entries": [{"date": x["date"], "arms": x["arms"]} for x in looks["e01_entries"]
                            if x["set"] == name],
        }
    return out


def cell_blockers(st: dict | None) -> str | None:
    if st is None:
        return "not built"
    if st["status"] == "failed":
        return "failed"
    open_ = sum(1 for p in st.get("pending") or [] if p["state"] == "open")
    deferred = sum(1 for p in st.get("pending") or [] if p["state"] == "deferred")
    if open_ or deferred or st.get("invalid"):
        bits = ["%d open" % open_] + (["%d deferred" % deferred] if deferred else []) + (
            ["%d invalid" % len(st["invalid"])] if st.get("invalid") else [])
        return "pending (%s)" % ", ".join(bits)
    return None


def look_blockers(name: str, spec: dict) -> list:
    """Non-diagnostic arms of a set that are not yet scorable (failed arms are final: they never block)."""
    out = []
    for arm in spec["arms"]:
        if arm in DIAGNOSTIC_ARMS:
            continue
        b = cell_blockers(load_cell(name, arm))
        if b is not None and b != "failed":
            out.append("%s: %s" % (arm, b))
    return out


FINDINGS = [  # what the E07 runs and their verification pass surfaced (at the v1 tag); SUMMARY "Problems".
    # E06's list (frozen v0) is in ../E06-capability-sweep/metrics.json "findings". Mechanisms: README Result.
    "Regression (Zhiyi root anchoring, not pre-registered): the follow-up's 「X」者 lemma-gloss device "
    "(outline/tier2/parser.py _resolve_lemma_zhe, partial-name rule GLOSS_PARTIAL = 0.5, Task 10, 2a356cc) "
    "attaches two glosses to one- and two-character listed items of 序品's opening, so the anchor puts "
    "their lemmas on later sūtra lines. T0262-xu-root tier 2: dev counted predictions 8 -> 4 (AC-F1 t=1 "
    "capped at 0.533), validation locator-only 0.197 -> 0.015 (aggregate). Dev counterfactual "
    "GLOSS_PARTIAL = 0.95 restores E06's dev row. Both misfiring glosses lie in T1718's validation "
    "commentary, which Task 10's dev-only acceptance could not see; a fix motivated by them is "
    "validation-informed and must be justified on dev or out-of-split text. A second, separate loss: the "
    "method-list rule (c40d9b2) drops 10 verse-section starts. anchor.py itself is not the cause (swapped "
    "between tags: starts unchanged).",
    "Measurement: commentary.span_start is valid only for golds keyed by sdp's chained span-start rule. "
    "On the Kuiji gold (take-up lines) the oracle scores 0.400 under it (12 of 14 dev first children "
    "inherit an earlier line), so the T1723 dev-span rows measure the convention clash, not the outliner.",
    "Measurement: T1718-dev's span_start locator-only gain (0.164 -> 0.295, H4) is entirely inherited "
    "first-child positions stacking on one gold line that carries 6 stacked gold nodes; without "
    "inherited predictions it is 0.182. E06's outline under the same key loses (0.244 -> 0.146).",
    "Resolver: on hybrid-T1718-dev the one accepted subdivide (7 inferred nodes under 6_5) duplicates an "
    "explicit subtree tier 2 already built (twin under 9_5; 6 of 7 headings identical). No key counts them "
    "(no commentary locator), so hybrid = tier2 on every T1718 row.",
    "Resolver: Zhiyi root-spans requests are built from mis-anchored siblings: admissible ranges exclude "
    "the true lines. hybrid-T1718-dev accepted 0 of 25; validation 84 of 112 and devval 138 of 204 not "
    "answered; one-line admissible ranges 67 of 112 (validation) and 44 of 204 (devval), against 19 of 35 "
    "and 21 of 55 in E06. Review B2's aim (no one-line or whole-sūtra range) is met only for whole-sūtra.",
    "Cost: gloss request content includes ancestors' English glosses, so each answered ancestor re-keys "
    "every descendant window: 559 request files, 300 consumed by the final builds, 229 answered and "
    "unused plus 30 never answered (all gloss). A sequential API adapter would not pay this; an "
    "interactive run does. 351 of 518 answer agents were gloss, which no score reads.",
    "Resolver design: X0268's 300k-character leaf is subdivided in 76 depth-1-only windows, so the hybrid "
    "outline is flat (273 of 338 nodes at level 2, one parent with 259 children); every windowed answer "
    "reported a window-grain problem. Locator-only rises 0.000 -> 0.174, S-F1 stays 0.000.",
    "model-only: subdivide now nests up to depth 3 per answer (schema resolver-subdivide/2), so the tree "
    "grows 21 -> 224 nodes on xu-root in 3 rounds and had not converged (round 3 still divided 40 of 72 "
    "leaves). 4 of its 7 counted dev TPs at t=1 pair nodes that cover different text (the gold chain "
    "shares one start line).",
    "H7: MAX_REQUEST_CHARS (100,000) caps the user message only (max 99,834); the rendered .md adds a "
    "20,294-character system prompt (14,090 at the v0 tag) and the schema, so 3 files (2 distinct "
    "requests) exceed 120,000.",
    "Projects (guanjing, outside every split): largest span 27.0 % -> 20.7 % of the target (a preamble "
    "of 11,188 characters carried by 97 chunks; 3 of its node's 4 children are listed-only and never "
    "taken up); largest label 25.9 % -> 17.5 % of chunks; lemma-not-found 89 of 208 (42.8 %, plan gate "
    "<= 25 % not met, as recorded in design 5.5). The '26 % -> 3 %' figure some notes give is the largest "
    "childless node (3.2 %), not the measure a chunk's label follows.",
    "Reading the xu-root rows: SUMMARY's 'S-F1 t=1 F' column uses the gold-counted TP rule (tier1 dev "
    "0.167 with 0 counted predictions is an uncounted-prediction artefact); the both-counted value is "
    "in the diagnostics table. The 'E06 outline, v1 scorer' table's both-counted column is t = 0.",
]


E06_RUNS = HERE.parent / "E06-capability-sweep" / "runs"
E06_TAG = "outliner-v0-frozen-2026-10-01"


def e06_rescore(registry: dict, prov: dict, looks: dict) -> dict:
    """E06's saved outlines (frozen v0) scored by the v1 scorer on E07's rows, so that a change between
    the E06 and E07 columns can be split into scorer and outliner. A span row reads a copy of the E06
    outline with span_start filled (outline_doc.fill_span_starts, as `python -m chinese_workflow.outline
    span-start` does for a saved outline). OOD rows pass frozen=E06's tag (the outline's own outliner).
    A validation or OOD row of an outline E06 already looked at is kind `recompute-e06` in
    looks-e07.json: no new system output is scored. Cached under runs/_e06_rescored/."""
    import copy

    cache_dir = RUNS / "_e06_rescored"
    out: dict = {}
    for name, spec, arm in cells():
        cdir = E06_RUNS / ("%s-%s" % (arm, name))
        opath = cdir / "outline.json"
        if not opath.exists():
            continue
        st = jsonio.read_json(cdir / "cell.json") if (cdir / "cell.json").exists() else {}
        if st.get("status") in ("failed", "pending"):
            continue
        osha = jsonio.sha256_file(opath)
        for r in spec["rows"]:
            frozen = E06_TAG if r.get("frozen") else None
            inputs = {"outline_sha256": osha, "gold": r["gold"], "gold_sha256": _gold_sha(r["gold"], registry),
                      "key": r["key"], "split": r["split"], "frozen": frozen,
                      "registry_sha256": prov["registry_sha256"], "scorer": prov["scorer"]}
            cp = cache_dir / ("%s-%s-%s.json" % (arm, name, r["row"]))
            m = None
            if cp.exists():
                old = jsonio.read_json(cp)
                if old.get("inputs") == inputs:
                    m = old["metrics"]
            if m is None:
                doc = jsonio.read_json(opath)
                if r["key"] == "commentary.span_start":
                    doc = outline_doc.fill_span_starts(copy.deepcopy(doc))
                m = score(doc, r["gold"], key=r["key"], split=r["split"], frozen=frozen, registry=registry)
                cache_dir.mkdir(parents=True, exist_ok=True)
                jsonio.write_json({"inputs": inputs, "scored_at": now(), "metrics": m}, cp)
                if (r.get("look") or r.get("ood_look")) and arm not in DIAGNOSTIC_ARMS:
                    looks["events"].append({"set": name, "row": r["row"], "arm": arm, "outline_sha256": osha,
                                            "gold_sha256": inputs["gold_sha256"], "date": now(),
                                            "kind": "recompute-e06", "scorer": prov["scorer"],
                                            "commit": prov["pipeline_commit"], "tag": TAG,
                                            "note": "E06's saved outline (frozen v0) rescored by the v1 "
                                                    "scorer; no new system output"})
                    save_looks(looks)
            out.setdefault(name, {}).setdefault(arm, {"rows": {}})["rows"][r["row"]] = _row(m, name, arm)
    return out


def request_sizes() -> dict:
    """README H7: the size of every request .md under runs/ (answered or not), per task and in all."""
    sizes, by_task = [], {}
    for md in sorted(RUNS.glob("*/llm/requests/*.md")):
        n = len(md.read_text(encoding="utf-8"))
        rec = md.with_suffix(".json")
        task = jsonio.read_json(rec).get("task") if rec.exists() else None
        sizes.append((n, md.parent.parent.parent.name, md.stem))
        t = by_task.setdefault(str(task), {"files": 0, "max": 0, "over_100000": 0, "over_120000": 0})
        t["files"] += 1
        t["max"] = max(t["max"], n)
        t["over_100000"] += n > 100000
        t["over_120000"] += n > 120000
    sizes.sort()
    uniq = {h: n for n, _, h in sizes}
    return {"files": len(sizes), "distinct_hashes": len(uniq),
            "max": sizes[-1][0] if sizes else None,
            "max_cell": sizes[-1][1] if sizes else None,
            "median": sizes[len(sizes) // 2][0] if sizes else None,
            "sum_distinct": sum(uniq.values()),
            "over_100000": sum(1 for n, _, _ in sizes if n > 100000),
            "over_120000": sum(1 for n, _, _ in sizes if n > 120000),
            "by_task": dict(sorted(by_task.items())),
            "rule": "len(text) of runs/*/llm/requests/*.md, the rendered request the answerer reads "
                    "(system + user message + schema); README H7 bound 120,000"}


def cmd_score(args) -> int:
    registry = reg.load_registry()
    prov = provenance()
    looks = load_looks()
    save_looks(looks)  # migrate before any score cache is overwritten (gold sha256 back-fill)
    results: dict = {}
    leaked: dict = {}
    added: list = []
    try:
        for name, spec, arm in cells():
            st = load_cell(name, arm)
            block = cell_blockers(st)
            entry = {"status": block or "scored", "diagnostic": arm in DIAGNOSTIC_ARMS,
                     "nodes_predicted": (st or {}).get("nodes")}
            if block is None:
                out = cell_dir(name, arm)
                entry.update({"rows": {}, "held": {}, "outline_sha256": st.get("outline_sha256"),
                              "built_pipeline_identical_to_tag":
                                  (st.get("provenance") or {}).get("pipeline_identical_to_tag")})
                for r in spec["rows"]:
                    frozen, why = frozen_for(r, st, prov)
                    if why:
                        entry["held"][r["row"]] = why
                        continue
                    inputs = row_inputs(out, r, registry, prov, frozen)
                    m = None if args.rescore else cached_row(out, r, inputs)
                    kind = "look" if r.get("look") else "ood-look" if r.get("ood_look") else None
                    diag_arm = arm in DIAGNOSTIC_ARMS  # LEAKED rows are not looks (E06 rule)
                    if m is not None and kind and not diag_arm:
                        cand = {"set": name, "row": r["row"], "arm": arm,
                                "outline_sha256": inputs["outline_sha256"],
                                "gold_sha256": inputs["gold_sha256"]}
                        if not look_seen(looks, cand, kind):  # cached by a run killed before its event
                            record_look(looks, dict(cand, recovered_from_cache=True), True,
                                        ["unknown (recovered from the score cache)"], prov, inputs, kind)
                    if m is None:
                        cand = new = blockers = None
                        if kind and not diag_arm:
                            cand = {"set": name, "row": r["row"], "arm": arm,
                                    "outline_sha256": inputs["outline_sha256"],
                                    "gold_sha256": inputs["gold_sha256"]}
                            new = not look_seen(looks, cand, kind)
                            blockers = look_blockers(name, spec) if new else []
                            if new and blockers and not args.partial_look:
                                entry["held"][r["row"]] = (
                                    "new %s held until every non-diagnostic arm of the set is "
                                    "scorable (one pass; score --partial-look overrides): " % kind
                                    + "; ".join(blockers))
                                continue
                        m = compute_row(out, r, inputs, registry)
                        if cand is not None:
                            record_look(looks, cand, new, blockers, prov, inputs, kind)
                    entry["rows"][r["row"]] = _row(m, name, arm)
                if not entry["held"]:
                    del entry["held"]
                elif not entry["rows"]:
                    entry["status"] = "held"
            (leaked if arm in DIAGNOSTIC_ARMS else results).setdefault(name, {})[arm] = entry
    finally:
        added = flush_e01_looks(prov)
    sanity = gold_self(registry, prov)
    e06r = e06_rescore(registry, prov, load_looks())
    xu_span()
    checks = {"reachability": reachability_check(registry, sanity),
              "xu_region": xu_region_check(registry),
              "xu_span_guard": _XU.get("guard"),
              "ood_label_leak": {SETS[n]["root"]: kepan_label_leak(SETS[n]["root"])
                                 for n in ("OOD-X0268", "OOD-P1573", "OOD-D8842")},
              "ood_no_kepan_inputs": {p.stem: jsonio.read_json(p) for p in sorted(INPUTS.glob("*.json"))},
              "leaked_markup": leaked,
              "request_sizes": request_sizes()}
    failed = {}
    for name, spec, arm in cells():
        st = load_cell(name, arm)
        if st and st["status"] == "failed":
            failed[st["cell"]] = {"error": st["error"].splitlines()[0][:300],
                                  "guard": st.get("guard")}
    pend = pending_summary(pending_requests())
    metrics = {"generated": now(), "provenance": prov, "results": results, "e06_rescored": e06r,
               "sanity_gold_self": sanity,
               "design_checks": checks, "validation_looks": looks_summary(load_looks()),
               "e01_looks_added": added, "failed_cells": failed, "pending": pend,
               "design_choices": DESIGN_CHOICES, "findings": FINDINGS}
    jsonio.write_json(metrics, HERE / "metrics.json")
    (HERE / "SUMMARY.md").write_text(summary_md(metrics), encoding="utf-8")
    for group in (results, leaked):
        for name, arms in group.items():
            for arm, e in arms.items():
                fs = {r: fmt(((v.get("s_f1") or {}).get("F"))) for r, v in (e.get("rows") or {}).items()}
                fs.update({r: "held" for r in e.get("held") or {}})
                print("%-20s %-13s %-32s %s" % (name, arm, e["status"], fs or ""))
    if added:
        print("E01 looks.json: one entry added for %s" % ", ".join(added))
    return 0


# ------------------------------------------------------------------------------------------ summary


def fmt(x) -> str:
    return "—" if x is None else ("%.3f" % x if isinstance(x, float) else str(x))


DISCLOSE = {
    "sdp-T1718-zhiyi-wenju": "sdp gold, eval-only, imported-unchecked; served 卷-halves only",
    "sdp-T0262-zhiyi-wenju": "sdp gold, eval-only, imported-unchecked; root-text key, splits inherited "
                             "from T1718 (EVAL-SETS 'Root-text experiments')",
    "kuiji-xuanzan": "Kuiji gold: draft-unreviewed, seeded by claude-opus-5-5 (R06 F19): a Claude-answered "
                     "arm on it is scored against a gold the same model family drafted",
    "cbeta-mulu-X0268": "CBETA cb:mulu 科判, imported-unchecked, OOD (frozen)",
    "cbeta-mulu-P1573": "CBETA cb:mulu 科判, imported-unchecked, OOD (frozen)",
    "cbeta-mulu-D8842": "CBETA cb:mulu 科判, imported-unchecked, OOD (frozen)",
    "ybh-T1605": "DILA YBh, structure only (heading_src + depth + parent path), OOD (frozen)",
    "ybh-T1602": "DILA YBh, structure only (heading_src + depth + parent path), OOD (frozen)",
}
SET_NOTES = {
    "T1718-validation": "E06's README row. In E06 S-F1 / F-F1 were 0 here for every arm by construction "
                        "(validation-only build); whether that still holds is the design check "
                        "reachability below.",
    "T1718-devval": "E06's post-hoc cell (outside E06's README matrix): T34n1718 built over dev+validation; "
                    "the validation row is the readable parser-gate row (E07 H5) and part of look #3.",
    "T0262-xu-root": "In E06 S-F1 t=0 was 0 for every arm by construction (top-level line offset 1; design "
                     "check xu_region below); read t = 1 and locator-only beside it.",
}

TABLE_HEAD = ["| Arm | Row | S-F1 t=0 (P / R / F) | E06 S-F1 F | S-F1 t=1 F | F-F1 t=0 F"
              " | locator/heading-only F | E06 loc-only F | locator-only t=1 F | S-F1 w/o anchor_inherited F"
              " | child-count acc | gold counted | pred counted | E06 pred counted | headline |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]


def _e06_row(e06: dict, group: str, name: str, arm: str, row: str) -> dict:
    """The same set / arm / row in E06's metrics.json (E07 comparison column); {} when absent (the
    span_start rows, which E06 did not have, or a cell E06 did not score)."""
    src = ((e06.get("design_checks") or {}).get("leaked_markup") if group == "leaked"
           else e06.get(group)) or {}
    return (((src.get(name) or {}).get(arm) or {}).get("rows") or {}).get(row) or {}


def _table(arms: dict, label_suffix: str = "", name: str = "", e06: dict | None = None,
           group: str = "results") -> list:
    lines = list(TABLE_HEAD)
    e06 = e06 or {}
    for arm, e in arms.items():
        label = arm + label_suffix
        if not e.get("rows") and not e.get("held"):
            lines.append("| %s | — | %s | | | | | | | | | | | | |" % (label, e["status"]))
            continue
        for row, r in (e.get("rows") or {}).items():
            s = r.get("s_f1") or {}
            det = r.get("locator_only") or r.get("heading_only") or {}
            wai = ((r.get("without_anchor_inherited") or {}).get("s_f1") or {})
            old = _e06_row(e06, group, name, arm, row)
            odet = old.get("locator_only") or old.get("heading_only") or {}
            lines.append("| %s | %s | %s / %s / %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                         % (label, row, fmt(s.get("P")), fmt(s.get("R")), fmt(s.get("F")),
                            fmt((old.get("s_f1") or {}).get("F")),
                            fmt((r.get("s_f1_t1") or {}).get("F")), fmt((r.get("f_f1") or {}).get("F")),
                            fmt(det.get("F")), fmt(odet.get("F")),
                            fmt((r.get("locator_only_t1") or {}).get("F")), fmt(wai.get("F")),
                            fmt(r["child_count"].get("accuracy")), fmt(r["counts"]["gold"].get("counted")),
                            fmt(r["counts"]["pred"].get("counted")),
                            fmt(((old.get("counts") or {}).get("pred") or {}).get("counted")),
                            "no" if not r["disclosures"]["headline"] else "yes"))
        for row, why in (e.get("held") or {}).items():
            lines.append("| %s | %s | held: %s | | | | | | | | | | | | |" % (label, row, why))
    return lines


DIAG_HEAD = ["| Arm | Row | t | S-F1 both-counted F (TP) | TP w/ uncounted pred | gold counted / distinct lines"
             " (recall cap) | FN frontier / line-detected / cascaded | FP listed-only / internal / taken-up"
             " | AC-F1 (P / R / F) | reanchor F (anchors) | depth offset mode (share; within 1) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]


def _diag_table(arms: dict) -> list:
    """E07: the follow-up scorer's diagnostics per row and t (never headline values; the triple is read
    only together: AC-F1, the re-anchor count and the depth-offset histogram)."""
    lines = list(DIAG_HEAD)
    for arm, e in arms.items():
        for row, r in (e.get("rows") or {}).items():
            for t, d in ((r.get("diag") or {}).items()):
                if not d:
                    continue
                bc = d.get("s_f1_both_counted") or {}
                kl = d.get("key_lines") or {}
                fs = d.get("fn_split") or {}
                fk = d.get("fp_by_kind") or {}
                ac = d.get("ancestor_consistent") or {}
                ra = d.get("reanchor") or {}
                dh = d.get("depth_offset_hist") or {}
                lines.append("| %s | %s | %s | %s (%s) | %s | %s / %s (%s) | %s / %s / %s | %s / %s / %s | %s | %s | %s |"
                             % (arm, row, t[2:], fmt(bc.get("F")), fmt(bc.get("TP")),
                                fmt(d.get("tp_uncounted_pred")),
                                fmt((kl.get("gold") or {}).get("counted")),
                                fmt((kl.get("gold") or {}).get("distinct")),
                                fmt(kl.get("recall_cap_one_node_per_line")),
                                fmt(fs.get("frontier")), fmt(fs.get("frontier_line_detected")),
                                fmt(fs.get("cascaded")),
                                fmt(fk.get("listed_only")), fmt(fk.get("commentary_internal")),
                                fmt(fk.get("taken_up")),
                                ("%s / %s / %s" % (fmt(ac.get("P")), fmt(ac.get("R")), fmt(ac.get("F")))
                                 if ac.get("available") else "n/a"),
                                ("%s (%s)" % (fmt(ra.get("F")), fmt(ra.get("anchors")))
                                 if ra.get("available") else "n/a"),
                                ("%s (%s; %s)" % (dh.get("mode"), fmt(dh.get("share_at_mode")),
                                                  fmt(dh.get("share_within_1_of_mode")))
                                 if dh.get("available") else "n/a")))
    return lines


def summary_md(m: dict) -> str:
    e06 = jsonio.read_json(E06_METRICS) if E06_METRICS.exists() else {}
    p = m["provenance"]
    pc = p["pipeline_commit"]
    lines = [
        "# E07 SUMMARY",
        "",
        "Generated by `run_e07.py score` on %s. Pipeline commit `%s`%s; frozen tag `%s` = `%s`; "
        "`pipeline/` identical to the tag: **%s**. README sha256 `%s`; harness sha256 `%s`; registry "
        "sha256 `%s`. Aggregate numbers only." % (
            m["generated"][:10], (pc["commit"] or "?")[:12],
            " (repo dirty outside pipeline/)" if pc["dirty"] else "", p["tag"],
            (p["tag_commit"] or "?")[:12], p["pipeline_identical_to_tag"], p["readme_sha256"][:16],
            p["harness_sha256"][:16], p["registry_sha256"][:16]),
        "",
        "S-F1 = node F1 on (key line, depth, parent path) at t = 0 (t = 1 diagnostic, a lower bound where "
        "predicted siblings are shifted together: scorer `_match`, Problems); F-F1 also needs equal origin "
        "class; locator-only = the key line alone (detection without attachment); structure rows (YBh) "
        "match heading_src instead of a line, `heading-only` = heading alone. **No row is a headline** "
        "(README; every row's disclosures.headline is false with reasons; the scorer's own flag, true on "
        "the unsplit imported-unchecked OOD rows, is kept as scorer_headline in metrics.json). hybrid and "
        "model-only are *Claude Code answering through the interactive adapter* (model `%s`), not the "
        "`claude` API config. A `held` row is not scored yet (reason given)." % INTERACTIVE_MODEL,
        "",
    ]
    for name, arms in m["results"].items():
        spec = SETS[name]
        golds = sorted({r["gold"] for r in spec["rows"]})
        lines += ["## %s" % name, "",
                  "Gold %s, key %s, row(s) %s. %s" % (
                      ", ".join("`%s`" % g for g in golds),
                      ", ".join(sorted({str(r["key"] or "default") for r in spec["rows"]})),
                      ", ".join(r["row"] for r in spec["rows"]),
                      "; ".join(DISCLOSE.get(g, "") for g in golds)), ""]
        if name in SET_NOTES:
            lines += [SET_NOTES[name], ""]
        lines += _table(arms, name=name, e06=e06) + [""]
        rs = (m.get("e06_rescored") or {}).get(name) or {}
        if rs:
            lines += ["E06's saved outlines rescored by the v1 scorer (separates scorer from outliner; "
                      "E06 column = E06's own scorer). All values here are t = 0; the t = 1 both-counted "
                      "values are in the diagnostics table:", "",
                      "| Arm | Row | E06 S-F1 F (v0 scorer) | E06 outline, v1 scorer S-F1 F | E07 S-F1 F | "
                      "E06 outline, v1 scorer loc-only F | E07 loc-only F | E06 outline, v1 both-counted F | "
                      "E07 both-counted F |", "|---|---|---|---|---|---|---|---|---|"]
            for arm, e in rs.items():
                for row, r in e["rows"].items():
                    new = (((arms.get(arm) or {}).get("rows") or {}).get(row)) or {}
                    old = _e06_row(e06, "results", name, arm, row)
                    def det(x):
                        return (x.get("locator_only") or x.get("heading_only") or {}).get("F")
                    def bc(x):
                        return (((x.get("diag") or {}).get("t=0") or {}).get("s_f1_both_counted") or {}).get("F")
                    lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                        arm, row, fmt((old.get("s_f1") or {}).get("F")), fmt((r.get("s_f1") or {}).get("F")),
                        fmt((new.get("s_f1") or {}).get("F")), fmt(det(r)), fmt(det(new)) if new else "—",
                        fmt(bc(r)), fmt(bc(new)) if new else "—"))
            lines += [""]
        lines += ["Diagnostics (follow-up scorer, never headline values):", ""] + _diag_table(arms) + [""]
    lines += ["## Looks: validation look #3 and the OOD look (README)", ""]
    for name, v in m["validation_looks"].items():
        firsts = ", ".join("%s %s" % (a, d or "not yet") for a, d in v["first_look_by_arm"].items())
        if not v["look_events"]:
            state = "no look yet (held until every non-diagnostic arm is scorable)"
        elif v["one_pass_over_all_arms"]:
            state = "one pass over all arms"
        elif v["arms_not_looked"]:
            state = "NOT one pass: arms %s not looked yet" % ", ".join(v["arms_not_looked"])
        else:
            state = "NOT one pass: arms looked in %d passes" % v["passes"]
        lines.append("- %s: first look per arm: %s. %d look event(s), %d recompute(s); %s. E01 entries: %s."
                     % (name, firsts, v["look_events"], v["recompute_events"], state,
                        "; ".join("%s (%s)" % (x["date"], ", ".join(x["arms"]))
                                  for x in v["e01_entries"]) or "none"))
    lines += ["", "A new validation look or OOD look waits until every non-diagnostic arm of its set is "
              "scorable (`score --partial-look` overrides; E07 did not use it unless stated here).", ""]
    lines += ["## Sanity: each gold scored against itself", "",
              "| Set / row | S-F1 F | F-F1 F | gold counted | AC-F1 t=1 (anchors, offset mode) |",
              "|---|---|---|---|---|"]
    for k, v in m["sanity_gold_self"].items():
        if "status" in v:
            lines.append("| %s | %s | | |" % (k, v["status"]))
            continue
        tr = v.get("triple_t1") or {}
        lines.append("| %s | %s | %s | %s | %s |" % (
            k, fmt((v.get("s_f1") or {}).get("F")), fmt((v.get("f_f1") or {}).get("F")), v["gold_counted"],
            "%s (%s, %s)" % (fmt(tr.get("ac_F")), fmt(tr.get("anchors")), tr.get("offset_mode"))
            if tr.get("available") else "n/a (forest above cap)"))
    dc = m["design_checks"]
    xr = dc["xu_region"]
    lines += ["", "## Design checks", "",
              "Reachability (counted gold nodes whose scoring-tree ancestors the cell's build can supply; "
              "0 reachable = S-F1 0 by construction):", "",
              "| Set / row | build span splits | level-1 prior | counted | reachable | unreachable by "
              "ancestor split | zero by construction |", "|---|---|---|---|---|---|---|"]
    for k, v in dc["reachability"].items():
        lines.append("| %s | %s | %s | %d%s | %d | %s | %s |" % (
            k, "+".join(v["build_span_splits"]), "yes" if v["level1_prior"] else "no", v["counted"],
            "" if v["counted_matches_gold_self"] else " (gold-self differs)", v["reachable"],
            json.dumps(v["unreachable_by_ancestor_split"]) if v["unreachable_by_ancestor_split"] else "—",
            "**yes**" if v["zero_by_construction"] else "no"))
    lines += ["",
              "- T0262-xu-root region rule: %d T09n0262 lines outside 序品 (%s..%s) fall in a dev or "
              "validation gold region; %s." % (xr["outside_lines_in_dev_or_validation_regions"],
                                               xr["xu_span"][0], xr["xu_span"][1], xr["decision"])]
    top = xr.get("top_level") or {}
    lines.append("- T0262-xu-root top level: tier-1 序品 node at %s (the 品 title line; its region split: "
                 "%s); the sdp gold has %d dev level-1 start line(s), at line offset(s) %s from it."
                 % (top.get("tier1_pin_start"), xr.get("tier1_pin_line_region_split"),
                    top.get("gold_dev_level1_start_lines", 0),
                    top.get("line_offsets_from_tier1_pin")))
    xg = dc.get("xu_span_guard") or {}
    lines.append("- %s; guard entries %s (frozen %s)."
                 % (xg.get("what"), json.dumps([e.get("purpose") for e in xg.get("entries") or []]),
                    sorted({str(e.get("frozen")) for e in xg.get("entries") or []})))
    for fid, leak in dc["ood_label_leak"].items():
        lines.append("- %s: %d 科判 cb:mulu; labels in their own line's reading text: %d, within two "
                     "lines: %d, anywhere: %d (ingest never puts cb:mulu text into lines). Tier 1 reads "
                     "the 科判 cb:mulu as nodes, so the README arms read the no-科判 copy and the "
                     "*-markup rows are LEAKED diagnostics." % (
                         fid, leak["kepan_mulu"], leak["label_in_own_line_text"],
                         leak["label_within_2_lines"], leak["label_anywhere_in_text"]))
    for fid, meta in dc["ood_no_kepan_inputs"].items():
        lines.append("- %s: %d 科判 cb:mulu removed, %d left; %d lines, %d with a deeper div_types stack; "
                     "sha256 %s." % (fid, meta["removed_kepan_mulu"], meta["kepan_mulu_left"],
                                     meta["lines"], meta.get("div_types_shifted_lines", 0),
                                     meta["sha256"][:16]))
    if m.get("e01_looks_added"):
        lines.append("- Validation looks added to E01's looks.json in this run: %s (note %r)."
                     % (", ".join(m["e01_looks_added"]), LOOK_NOTE))
    lines += ["", "### Leaked diagnostics (not results, not hypothesis rows)", "",
              "tier1-markup / tier2-markup read the original XML, whose cb:mulu type=科判 IS the gold: "
              "tier 1 copies the gold's nodes. Shown only to measure that leak.", ""]
    for name, arms in dc["leaked_markup"].items():
        lines += ["#### %s" % name, ""] + _table(arms, " (LEAKED)", name=name, e06=e06,
                                                  group="leaked") + [""]
    pend = m["pending"]
    lines += ["## Pending requests (interactive adapter)", "",
              "Answer-now requests: %d (prompt .md sizes: sum %s, median %s, max %s characters); totals by "
              "state %s. `run_e07.py pending --json` lists each with its response path."
              % (pend["answer_now"], pend["answer_now_md_chars"]["sum"],
                 pend["answer_now_md_chars"]["median"], pend["answer_now_md_chars"]["max"],
                 json.dumps(pend["totals"], ensure_ascii=False)), "",
              "| Cell | open | deferred | duplicates | open .md chars |", "|---|---|---|---|---|"]
    for c, v in pend["by_cell"].items():
        lines.append("| %s | %s | %s | %s | %s |" % (
            c, v.get("open", 0), v.get("deferred", 0),
            v.get("open_duplicate", 0) + v.get("deferred_duplicate", 0), v.get("open_md_chars", 0)))
    lines += ["", "| Task | open | deferred | .md chars (open + deferred) | max |", "|---|---|---|---|---|"]
    for t, v in pend["by_task"].items():
        lines.append("| %s | %s | %s | %s | %s |" % (t, v.get("open", 0), v.get("deferred", 0),
                                                    v.get("md_chars", 0), v.get("max_md_chars", 0)))
    rs_ = m["design_checks"].get("request_sizes") or {}
    if rs_:
        lines += ["", "## Request sizes (README H7)", "",
                  "%d request .md files (%d distinct hashes), %s characters over distinct hashes; max %s (%s), "
                  "median %s; over 100,000: %d, over 120,000: %d. Rule: %s." % (
                      rs_["files"], rs_["distinct_hashes"], rs_["sum_distinct"], rs_["max"], rs_["max_cell"],
                      rs_["median"], rs_["over_100000"], rs_["over_120000"], rs_["rule"]), "",
                  "| Task | files | max | over 100,000 | over 120,000 |", "|---|---|---|---|---|"]
        for t, v in rs_["by_task"].items():
            lines.append("| %s | %d | %d | %d | %d |" % (t, v["files"], v["max"], v["over_100000"],
                                                         v["over_120000"]))
    pj = HERE / "projects.json"
    if pj.exists():
        pr = jsonio.read_json(pj)
        lines += ["", "## Project runs (README H13; `projects.json`)", "",
                  "Runner on every projects/*/project.toml, adapter none, pipeline/ identical to the tag: %s. "
                  "Label share = share of chunks whose label (chunk node_id) is carried by more than 31 chunks "
                  "(pre-registered); the E06 review's rule (more than 30) beside it." % pr.get(
                      "pipeline_identical_to_tag"), "",
                  "| Project | exit | nodes | chunks | invariants | largest span (frac of target) | label share "
                  ">31 E06 -> E07 | review rule >30 E06 -> E07 |", "|---|---|---|---|---|---|---|---|"]
        for pid, v in (pr.get("summary") or {}).items():
            lines.append("| %s | %s | %s | %s | %s | %s | %s -> %s | %s -> %s |" % (
                pid, v.get("exit_code"), v.get("nodes"), v.get("chunks"), v.get("invariants_ok"),
                fmt(v.get("largest_span_frac")), fmt(v.get("label_share_gt31_e06")),
                fmt(v.get("label_share_gt31")), fmt(v.get("label_share_gt30_review_rule_e06")),
                fmt(v.get("label_share_gt30_review_rule"))))
    la = HERE / "leakage-audit.json"
    if la.exists():
        a = jsonio.read_json(la).get("aggregate") or {}
        an = a.get("answer") or {}
        lines += ["", "## Leakage audit (`audit_leakage.py` -> `leakage-audit.json`)", "",
                  "Answer agents %s, tool uses %s, by class %s; drivers %s (by class %s). Test/reserve text "
                  "in any agent's tool results: %s agents; TEST SPLIT banner: %s; Do-not-open hits: %s. The "
                  "one FORBIDDEN access is a `wc` on a mistyped, non-existent copy of the agent's own "
                  "request path (README Result, 'Leakage audit'); the SUSPECT ones are listings of the "
                  "agent's own responses directory and helper scripts written from its own request." % (
                      an.get("agents"), an.get("tool_uses"), json.dumps(an.get("by_class")),
                      (a.get("driver") or {}).get("agents"), json.dumps((a.get("driver") or {}).get("by_class")),
                      an.get("agents_with_undocumented_test_or_reserve_text"),
                      an.get("agents_with_TEST_SPLIT_banner_in_results"), len(an.get("do_not_open_hits") or []))]
    lines += ["", "## Problems", ""]
    for c, v in m["failed_cells"].items():
        g = v.get("guard") or {}
        lines.append("- Failed cell `%s`: %s (guard: splits read %s)" % (
            c, v["error"], ", ".join(g.get("splits_read") or []) or "none recorded"))
    lines += ["- %s" % f for f in FINDINGS]
    lines += ["", "## Design choices (not fixed by the README)", ""]
    lines += ["%d. %s" % (k, d) for k, d in enumerate(m["design_choices"], 1)]
    lines += ["", "Per-depth rows, child counts, exclusions and scorer notes: `metrics.json`. "
              "Validation and OOD rows are aggregate only; dev diagnostics stay in `runs/` (gitignored)."]
    return "\n".join(lines) + "\n"



# ------------------------------------------------------------------------------------------- status


def cmd_status(args) -> int:
    for name, spec, arm in cells():
        st = load_cell(name, arm)
        out = cell_dir(name, arm)
        if st is None:
            print("%-34s not built" % out.name)
            continue
        c = Counter(p["state"] for p in st.get("pending") or [])
        scored = []
        for r in spec["rows"]:
            sp = out / ("score-%s.json" % r["row"])
            if sp.exists() and st.get("outline_sha256") and jsonio.read_json(sp)["inputs"].get(
                    "outline_sha256") == st.get("outline_sha256"):
                scored.append(r["row"])
        print("%-34s %-8s nodes %-5s open %-3d deferred %-3d invalid %-2d rounds %-8s scored %s" % (
            out.name, st["status"], st.get("nodes", "-"), c["open"], c["deferred"],
            len(st.get("invalid") or []),
            ",".join(rd["status"][:4] for rd in st.get("rounds") or []) or "-",
            ",".join(scored) or "-"))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build cells (idempotent; consumes response files)")
    b.add_argument("--set", action="append", choices=list(SETS))
    b.add_argument("--arm", action="append",
                   choices=sorted({a for s in SETS.values() for a in s["arms"]}))
    pnd = sub.add_parser("pending", help="request files without a response")
    pnd.add_argument("--json", action="store_true")
    pnd.add_argument("--compact", action="store_true", help="E07: one line per request to answer now")
    pnd.add_argument("--set", action="append", choices=list(SETS))
    sc = sub.add_parser("score", help="score every cell with no pending request")
    sc.add_argument("--rescore", action="store_true", help="ignore the per-cell score cache")
    sc.add_argument("--partial-look", action="store_true",
                    help="score a new validation look although other non-diagnostic arms of the set are "
                         "still pending (recorded in the look's arms_not_yet_scorable)")
    sub.add_parser("status", help="one line per cell")
    args = ap.parse_args(argv)
    return {"build": cmd_build, "pending": cmd_pending, "score": cmd_score, "status": cmd_status}[
        args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
