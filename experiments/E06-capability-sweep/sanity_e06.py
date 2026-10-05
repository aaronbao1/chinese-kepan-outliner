"""E06 sanity: validate the measuring instrument (chinese_workflow.eval.score) before any E06 number is
believed (README "Method", "Sanity checks").

Input : the golds of data/eval-sets.json, read through chinese_workflow.eval.registry and scored by
        chinese_workflow.eval.score.score (the frozen pipeline at tag outliner-v0-frozen-2026-10-01, not
        modified here); line order from the CBETA XML under data/raw/cbeta/ (lineheads only).
Output: experiments/E06-capability-sweep/sanity.json — aggregate numbers only. No gold heading, note or
        (for the eval-only sdp golds) node id is printed or written.

1. Gold vs itself. Every gold, relabelled as a prediction (gold_status 'prediction', seeded_by None;
   headings/notes blanked in memory except in structure mode, where heading_src is the key), is scored
   against its own dataset id:
     split-scoped golds on dev and validation only (kuiji-xuanzan has no validation span: dev only;
     sdp-T0262 on its default key root_text.start, kuiji also on root_text.start, dev);
     OOD golds (cbeta-mulu-*, ybh-*) whole, with frozen=outliner-v0-frozen-2026-10-01.
   Expected: S-F1 = F-F1 = locator-only (heading-only) F = 1.000 at t = 0 and t = 1 on every row with
   counted nodes, and the counted gold nodes equal to the number the registry and the scope rules give.
   Gold vs itself is not a look at the outliner (no prediction is scored): nothing goes to looks.json.
2. Perturbations of an in-memory copy of an OOD gold (cbeta-mulu-P1573, frozen) and of the readable part
   of the Kuiji gold (levels 1-2 + the dev subtree, as tests/unit/test_eval_score.py builds it):
   drop ~10% of nodes (leaves only), re-parent one subtree one level deeper, shift every key line by +1,
   duplicate one leaf; for YBh structure mode (ybh-T1605, ybh-T1602) alter 10% of heading_src (leaves only,
   then any node); merged_range splits (X0268 locator mode, T1602 structure mode, EVAL-SETS item 10).
   Each expected value is computed independently of the scorer (counts, subtree sizes) before scoring.
3. Scope quirks found while reading the code paths, measured (sdp-T0262 root-text regions; headline flag).

Split discipline: never passes split test / reserve / all; the Kuiji perturbations touch only dev-subtree
lines; the Kuiji test subtrees are never printed, written or perturbed (the scorer loads the gold itself).

Run: cd pipeline && .venv/bin/python ../experiments/E06-capability-sweep/sanity_e06.py
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

from chinese_workflow.common import jsonio, outline_doc
from chinese_workflow.common.jsonio import read_json
from chinese_workflow.common.lineheads import LineOrder, file_id, strip_offset
from chinese_workflow.common.paths import REPO_ROOT, cbeta_xml_path
from chinese_workflow.common.splits import SplitViolation
from chinese_workflow.eval import registry as reg
from chinese_workflow.eval import score as sc
from chinese_workflow.ingest.lines import iter_lines

HERE = Path(__file__).resolve().parent
FROZEN = "outliner-v0-frozen-2026-10-01"
SEED = 20261001
REG = reg.load_registry()

GOLD_ROWS = [
    {"name": "sdp-T1718/commentary.explained/dev", "gold": "sdp-T1718-zhiyi-wenju", "split": "dev"},
    {"name": "sdp-T1718/commentary.explained/validation", "gold": "sdp-T1718-zhiyi-wenju",
     "split": "validation"},
    {"name": "sdp-T0262/root_text.start/dev", "gold": "sdp-T0262-zhiyi-wenju", "split": "dev"},
    {"name": "sdp-T0262/root_text.start/validation", "gold": "sdp-T0262-zhiyi-wenju",
     "split": "validation"},
    {"name": "kuiji/commentary.explained/dev", "gold": "kuiji-xuanzan", "split": "dev"},
    {"name": "kuiji/root_text.start/dev", "gold": "kuiji-xuanzan", "split": "dev",
     "key": "root_text.start"},
    {"name": "cbeta-mulu-X0268/whole", "gold": "cbeta-mulu-X0268", "frozen": FROZEN},
    {"name": "cbeta-mulu-P1573/whole", "gold": "cbeta-mulu-P1573", "frozen": FROZEN},
    {"name": "cbeta-mulu-D8842/whole", "gold": "cbeta-mulu-D8842", "frozen": FROZEN},
    {"name": "ybh-T1605/structure", "gold": "ybh-T1605", "frozen": FROZEN},
    {"name": "ybh-T1602/structure", "gold": "ybh-T1602", "frozen": FROZEN},
]


# ------------------------------------------------------------------------------------------ helpers


def load_gold(gold_id: str) -> dict:
    return read_json(REPO_ROOT / reg.dataset(REG, gold_id)["path"])


def as_prediction(doc: dict, keep_headings: bool = False) -> dict:
    """A deep copy relabelled as a prediction. The scorer never checks the prediction's gold_status
    (score.py reads it only into settings.prediction); headings, notes and evidence are blanked unless
    they are the key (structure mode)."""
    p = copy.deepcopy(doc)
    for n in p["nodes"]:
        if not keep_headings:
            n.update(heading_src="", heading_en="", evidence="", notes=[])
    md = p["metadata"]
    for k in ("coverage", "coverage_spans", "split_notes", "anomalies"):
        md.pop(k, None)
    md.update(gold_status="prediction", seeded_by=None, generated_by="E06 sanity: gold as prediction")
    return p


def r6(x):
    return None if x is None else round(x, 6)


def block(b: dict | None) -> dict | None:
    if not b:
        return None
    return {k: (r6(b[k]) if k in ("P", "R", "F") else b[k]) for k in ("P", "R", "F", "TP", "FP", "FN")}


def row_view(m: dict, name: str) -> dict:
    r = m["rows"].get(name) or {}
    if not r.get("available"):
        return {"available": False}
    det = r.get("locator_only") or r.get("heading_only")
    pd = r["per_depth"]
    return {
        "available": True,
        "s_f1": block(r["s_f1"]),
        "f_f1": block(r["f_f1"]),
        "detection": block(det),
        "detection_kind": "locator_only" if "locator_only" in r else "heading_only",
        "s_f1_without_anchor_inherited": block(r["without_anchor_inherited"]["s_f1"]),
        "per_depth_sums_ok": (sum(v["TP"] for v in pd.values()) == r["s_f1"]["TP"]
                              and sum(v["FP"] for v in pd.values()) == r["s_f1"]["FP"]
                              and sum(v["FN"] for v in pd.values()) == r["s_f1"]["FN"]),
        "exempt_under_truncated": r["exempt_under_truncated"],
        "absorbed_into_merged_range": r["absorbed_into_merged_range"],
        "matched_to_gold_outside_scope": r["matched_to_gold_outside_scope"],
    }


def view(m: dict) -> dict:
    names = ["structure"] if m["settings"]["key"] == "structure" else ["t=0", "t=1"]
    cc = m["child_count"]
    return {
        "key": m["settings"]["key"],
        "split": m["settings"]["split"],
        "frozen": m["settings"]["frozen"],
        "line_order": m["settings"]["line_order"],
        "counts": m["counts"],
        "rows": {n: row_view(m, n) for n in names},
        "child_count": {k: cc[k] for k in ("eligible", "correct", "wrong", "missing",
                                           "source_disagreements", "accuracy")},
        "headline": m["disclosures"]["headline"],
        "headline_reasons": m["disclosures"]["headline_reasons"],
        "gold_status": m["disclosures"]["gold_status"],
        "seeded_by": m["disclosures"]["seeded_by"],
        "pairing_warnings": len(m["disclosures"]["pairing_warnings"]),
        "n_notes": len(m["disclosures"]["notes"]),
    }


def all_ones(v: dict) -> bool:
    for r in v["rows"].values():
        if not r.get("available"):
            return False
        for b in ("s_f1", "f_f1", "detection", "s_f1_without_anchor_inherited"):
            if (r[b] or {}).get("F") != 1.0:
                return False
        if not r["per_depth_sums_ok"]:
            return False
    acc = v["child_count"]["accuracy"]
    return acc in (None, 1.0)


_ORDERS: dict = {}


def line_order(fid: str) -> LineOrder:
    if fid not in _ORDERS:
        _ORDERS[fid] = LineOrder(rec["linehead"] for rec in iter_lines(cbeta_xml_path(fid)))
    return _ORDERS[fid]


def children_map(doc: dict) -> dict:
    ch: dict = {}
    for n in doc["nodes"]:
        ch.setdefault(n.get("parent_id"), []).append(n["id"])
    return ch


def subtree(doc: dict, nid: str) -> list:
    ch = children_map(doc)
    out, todo = [], [nid]
    while todo:
        x = todo.pop()
        out.append(x)
        todo.extend(ch.get(x, []))
    return out


def node(doc: dict, nid: str) -> dict:
    return next(n for n in doc["nodes"] if n["id"] == nid)


def check(name: str, expected: dict, observed: dict, ok: bool, **extra) -> dict:
    return {"name": name, "expected": expected, "observed": observed, "ok": bool(ok), **extra}


def s0(m: dict, name: str = "t=0") -> dict:
    return m["rows"][name]["s_f1"]


def det(m: dict, name: str = "t=0") -> dict:
    r = m["rows"][name]
    return r.get("locator_only") or r.get("heading_only")


# ------------------------------------------------------------------------- 1. gold vs itself


def region_inherited_counts(gold_id: str, key: str, split: str) -> int:
    """Root-text scoring: gold nodes WITHOUT their own split locator that the scorer's documented region
    rule (score.py docstring, 'splits') puts into `split` — recomputed here from the registry and the
    gold's locators, to explain counted totals that differ from the registry's by_split counts."""
    ds = reg.dataset(REG, gold_id)
    by = sc._by_to_key(ds["split_scope"]["by"])
    gold = load_gold(gold_id)
    order = line_order("T09n0262")
    own = []
    for i, n in enumerate(gold["nodes"]):
        k = sc.locator(n, key)
        if k is None or k not in order:
            continue
        loc = sc.locator(n, by)
        sp = reg.split_of(REG, ds["split_scope"]["text"], loc) if loc else None
        own.append(((order.index(k), i), sp, loc is not None, n))
    own.sort(key=lambda e: e[0])
    hits = 0
    for idx, (pos, sp, has_own, n) in enumerate(own):
        if has_own:
            continue
        # last gold node in root-text order starting at or before this line (ties: last by position)
        j = max(e for e in range(len(own)) if own[e][0][0] <= pos[0])
        hits += own[j][1] == split
    return hits


def expected_counted(row: dict, gold: dict) -> tuple[int, str]:
    ds = reg.dataset(REG, row["gold"])
    key = row.get("key") or sc.default_key(ds, gold)
    if ds.get("split") == "out-of-domain":
        return ds["counts"]["nodes"], "registry counts.nodes (OOD: scored whole)"
    split = row["split"]
    if key == sc._by_to_key(ds["split_scope"]["by"]):
        return ds["counts"]["by_split"][split]["nodes"], "registry counts.by_split.%s.nodes" % split
    # root-text key: nodes with a root start among those whose own split is `split`, plus region-inherited
    by = sc._by_to_key(ds["split_scope"]["by"])
    own = sum(1 for n in gold["nodes"] if sc.locator(n, key) and sc.locator(n, by)
              and reg.split_of(REG, ds["split_scope"]["text"], sc.locator(n, by)) == split)
    inh = region_inherited_counts(row["gold"], key, split)
    return own + inh, ("nodes with %s whose own %s is %s (%d) + gold nodes without one that the region "
                       "rule assigns to %s (%d)" % (key, by, split, own, split, inh))


def gold_vs_itself() -> list:
    out = []
    for row in GOLD_ROWS:
        ds = reg.dataset(REG, row["gold"])
        gold = load_gold(row["gold"])
        structure = ds.get("anchors") == "structure-only"
        pred = as_prediction(gold, keep_headings=structure)
        kw = {k: row[k] for k in ("split", "key", "frozen") if k in row}
        m = sc.score(pred, row["gold"], registry=REG, **kw)
        v = view(m)
        exp_n, exp_basis = expected_counted(row, gold)
        gc, pc = v["counts"]["gold"]["counted"], v["counts"]["pred"]["counted"]
        v.update(name=row["name"], gold_id=row["gold"], expected_gold_counted=exp_n,
                 expected_basis=exp_basis,
                 ok=all_ones(v) and gc == exp_n and pc == gc and gc > 0)
        out.append(v)
        del gold, pred, m
    return out


# ---------------------------------------------------------------------------- 2. perturbations


def kuiji_dev_prediction() -> tuple[dict, list]:
    """Levels 1-2 of the Kuiji gold plus the subtree whose root opens the T1723 dev span (the readable
    part; tests/unit/test_eval_score.py::_kuiji_dev_prediction). Returns (prediction, dev subtree ids)."""
    gold = load_gold("kuiji-xuanzan")
    dev_start = next(s for split, s, _ in reg.split_spans(REG, "T1723") if split == "dev")
    root = next(n["id"] for n in gold["nodes"] if n["level"] == 2
                and sc.locator(n, "commentary.explained") == dev_start)
    keep = [n for n in gold["nodes"]
            if n["level"] <= 2 or n["id"] == root or n["id"].startswith(root + ".")]
    pred = as_prediction({"metadata": gold["metadata"], "nodes": keep})
    dev_ids = [n["id"] for n in pred["nodes"] if n["id"] == root or n["id"].startswith(root + ".")]
    return pred, dev_ids


def leaves(doc: dict, among: list) -> list:
    ch = children_map(doc)
    return [i for i in among if not ch.get(i)]


def p_drop_leaves(base: dict, among: list, gold_id: str, kw: dict, n_counted: int, label: str,
                  key_rows=("t=0",)) -> dict:
    rng = random.Random(SEED)
    cand = leaves(base, among)
    k = max(1, round(0.1 * n_counted))
    drop = set(rng.sample(cand, min(k, len(cand))))
    p = copy.deepcopy(base)
    p["nodes"] = [n for n in p["nodes"] if n["id"] not in drop]
    m = sc.score(p, gold_id, registry=REG, **kw)
    k = len(drop)
    exp = {"TP": n_counted - k, "FP": 0, "FN": k, "P": 1.0, "R": r6((n_counted - k) / n_counted)}
    obs = {name: {"s_f1": block(s0(m, name)), "detection": block(det(m, name))} for name in key_rows}
    ok = all(obs[name]["s_f1"][x] == exp[x] for name in key_rows for x in ("TP", "FP", "FN", "P", "R"))
    ok = ok and all(obs[name]["detection"]["R"] == exp["R"] for name in key_rows)
    return check("%s: drop %d of %d counted nodes (leaves, seeded)" % (label, k, n_counted), exp, obs, ok)


def p_reparent(base: dict, among: list, gold_id: str, kw: dict, n_counted: int, key: str,
               label: str) -> dict:
    """Move one subtree X under its previous sibling S (one level deeper, appended as S's last child;
    document order unchanged because X already follows S's subtree). Pick the largest such subtree whose
    root line is not within 1 line of any line of S's children, with at most 25% of the counted nodes."""
    ch = children_map(base)
    by_id = {n["id"]: n for n in base["nodes"]}
    amongs = set(among)
    order_cache = {}

    def idx(lh):
        f = file_id(lh)
        if f not in order_cache:
            order_cache[f] = line_order(f)
        return order_cache[f].index(lh)

    best = None
    for parent, kids in ch.items():
        for a, b in zip(kids, kids[1:]):
            if b not in amongs or a not in amongs:
                continue
            size = len(subtree(base, b))
            if size < 2 or size > 0.25 * n_counted:
                continue
            lb = sc.locator(by_id[b], key)
            near = [c for c in ch.get(a, []) if abs(idx(sc.locator(by_id[c], key)) - idx(lb)) <= 1]
            if near:
                continue
            if best is None or size > best[2]:
                best = (a, b, size)
    if best is None:
        return check("%s: re-parent one subtree" % label, {}, {"error": "no candidate"}, False)
    s_id, x_id, size = best
    p = copy.deepcopy(base)
    moved = set(subtree(p, x_id))
    for n in p["nodes"]:
        if n["id"] == x_id:
            n["parent_id"] = s_id
        if n["id"] in moved:
            n["level"] = n["level"] + 1
    m = sc.score(p, gold_id, registry=REG, **kw)
    exp = {"TP": n_counted - size, "FP": size, "FN": size, "F": r6((n_counted - size) / n_counted),
           "locator_only_F": 1.0}
    obs = {"s_f1": block(s0(m)), "locator_only": block(det(m)), "subtree_size": size,
           "s_f1_t1": block(s0(m, "t=1")) if m["rows"]["t=1"].get("available") else None}
    ok = (obs["s_f1"]["TP"] == exp["TP"] and obs["s_f1"]["FP"] == exp["FP"]
          and obs["s_f1"]["FN"] == exp["FN"] and obs["locator_only"]["F"] == 1.0)
    return check("%s: re-parent a %d-node subtree one level deeper" % (label, size), exp, obs, ok)


def adjacent_sibling_pairs(doc: dict, ids: set, key: str) -> int:
    """Sibling pairs (consecutive in order, both in `ids`) whose key lines are exactly 1 line apart."""
    ch = children_map(doc)
    by_id = {n["id"]: n for n in doc["nodes"]}
    c = 0
    for kids in ch.values():
        for a, b in zip(kids, kids[1:]):
            if a in ids and b in ids:
                la, lb = sc.locator(by_id[a], key), sc.locator(by_id[b], key)
                if la and lb and file_id(la) == file_id(lb):
                    o = line_order(file_id(la))
                    c += abs(o.index(la) - o.index(lb)) == 1
    return c


def p_shift(base: dict, among: list, gold_id: str, kw: dict, n_counted: int, key: str,
            label: str, split_text: str | None = None) -> dict:
    p = copy.deepcopy(base)
    amongs = set(among)
    left_split = 0
    part, field = key.split(".")
    for n in p["nodes"]:
        if n["id"] not in amongs:
            continue
        loc = n["locations"]
        ref = (loc.get(part) or {}).get(field)
        if not ref:
            continue
        lh = strip_offset(ref)
        o = line_order(file_id(lh))
        new = o.lineheads[o.index(lh) + 1]
        if split_text:
            left_split += reg.split_of(REG, split_text, new) != reg.split_of(REG, split_text, lh)
        loc[part][field] = new
    m = sc.score(p, gold_id, registry=REG, **kw)
    adj = adjacent_sibling_pairs(base, amongs, key)
    with order_preserving_matcher():
        m_dp = sc.score(p, gold_id, registry=REG, **kw)
        m_dp_identity = sc.score(base, gold_id, registry=REG, **kw)
    obs = {"t=0": {"s_f1": block(s0(m)), "locator_only": block(det(m))},
           "t=1": {"s_f1": block(s0(m, "t=1")), "locator_only": block(det(m, "t=1"))},
           "sibling_pairs_one_line_apart": adj, "shifted_key_lines_leaving_split": left_split,
           "attribution_order_preserving_matcher": {
               "what": "same prediction re-scored with score._match replaced in-process (restored "
                       "after) by a maximum-cardinality, order-preserving sibling alignment that "
                       "minimises total line distance (DP); diagnostic only, not the instrument",
               "t=0": block(s0(m_dp)), "t=1": block(s0(m_dp, "t=1")),
               "identity_t0_t1_F": [s0(m_dp_identity)["F"], s0(m_dp_identity, "t=1")["F"]]}}
    exp = {"t=0 S-F1": "≈ 0 (≤ 0.10)", "t=1 S-F1": "≈ 1 (≥ 0.90)", "t=1 locator-only F": 1.0}
    ok = (obs["t=0"]["s_f1"]["F"] <= 0.10 and obs["t=1"]["s_f1"]["F"] >= 0.90
          and obs["t=1"]["locator_only"]["F"] == 1.0)
    extra = {}
    if not ok:
        extra["cause"] = ("score.py _match (lines 306-318) pairs siblings greedily by line distance "
                          "first: a node shifted onto the line of its next sibling (one line apart) "
                          "takes that sibling at d=0 before its own twin at d=1; the mis-pair counts "
                          "as a TP and both subtrees are lost. With an order-preserving alignment "
                          "the same prediction scores t=1 F = %s" % s0(m_dp, "t=1")["F"])
    return check("%s: shift every key line by +1" % label, exp, obs, ok, **extra)


class order_preserving_matcher:
    """Context manager: swap score._match for an order-preserving DP alignment (diagnostic)."""

    def __enter__(self):
        self.orig = sc._match
        sc._match = _dp_match
        return self

    def __exit__(self, *exc):
        sc._match = self.orig
        return False


def _dp_match(pt, gt, dist, t):
    pairs: dict = {}
    todo = [((None,), None)]
    while todo:
        pparents, gparent = todo.pop()
        P = sorted((c for pp in pparents for c in pt.children.get(pp, ())), key=pt.pos.__getitem__)
        G = gt.children.get(gparent, [])
        n, m = len(P), len(G)
        best = [[(0, 0)] * (m + 1) for _ in range(n + 1)]
        for i in range(n - 1, -1, -1):
            for j in range(m - 1, -1, -1):
                opts = [best[i + 1][j], best[i][j + 1]]
                d = dist(pt.key[P[i]], gt.key[G[j]])
                if d is not None and d <= t:
                    b = best[i + 1][j + 1]
                    opts.append((b[0] + 1, b[1] - d))
                best[i][j] = max(opts)
        i = j = 0
        while i < n and j < m:
            d = dist(pt.key[P[i]], gt.key[G[j]])
            b = best[i + 1][j + 1]
            if d is not None and d <= t and best[i][j] == (b[0] + 1, b[1] - d):
                pairs[P[i]] = G[j]
                todo.append(((P[i],), G[j]))
                i, j = i + 1, j + 1
            elif best[i][j] == best[i + 1][j]:
                i += 1
            else:
                j += 1
    return pairs, {}


def p_duplicate(base: dict, among: list, gold_id: str, kw: dict, n_counted: int, label: str) -> dict:
    rng = random.Random(SEED + 1)
    leaf = rng.choice(leaves(base, among))
    p = copy.deepcopy(base)
    i = next(j for j, n in enumerate(p["nodes"]) if n["id"] == leaf)
    dup = copy.deepcopy(p["nodes"][i])
    dup["id"] = leaf + ".dup"
    p["nodes"].insert(i + 1, dup)
    m = sc.score(p, gold_id, registry=REG, **kw)
    exp = {"TP": n_counted, "FP": 1, "FN": 0, "P": r6(n_counted / (n_counted + 1))}
    obs = {"s_f1": block(s0(m)), "locator_only": block(det(m))}
    ok = all(obs["s_f1"][x] == exp[x] for x in ("TP", "FP", "FN", "P")) and obs["locator_only"]["FP"] == 1
    return check("%s: duplicate one leaf" % label, exp, obs, ok)


def p_alter_headings(gold_id: str, leaves_only: bool) -> dict:
    gold = load_gold(gold_id)
    base = as_prediction(gold, keep_headings=True)
    del gold
    n_all = len(base["nodes"])
    ids = [n["id"] for n in base["nodes"]]
    rng = random.Random(SEED + (2 if leaves_only else 3))
    pool = leaves(base, ids) if leaves_only else ids
    k = round(0.1 * n_all)
    alt = set(rng.sample(pool, k))
    lost = set()
    for a in alt:
        lost.update(subtree(base, a))
    for n in base["nodes"]:
        if n["id"] in alt:
            n["heading_src"] = (n.get("heading_src") or "") + "　[E06-altered-%s]" % n["id"]
    m = sc.score(base, gold_id, registry=REG, frozen=FROZEN)
    r = m["rows"]["structure"]
    exp = {"TP": n_all - len(lost), "FP": len(lost), "FN": len(lost),
           "F": r6((n_all - len(lost)) / n_all), "heading_only_TP": n_all - k}
    obs = {"s_f1": block(r["s_f1"]), "heading_only": block(r["heading_only"]), "altered": k,
           "nodes_lost_incl_descendants": len(lost)}
    ok = (obs["s_f1"]["TP"] == exp["TP"] and obs["s_f1"]["FP"] == exp["FP"]
          and obs["s_f1"]["FN"] == exp["FN"] and obs["heading_only"]["TP"] == exp["heading_only_TP"])
    return check("%s structure: alter heading_src of %d of %d nodes (%s)"
                 % (gold_id, k, n_all, "leaves only" if leaves_only else "any node; top-down loss "
                    "includes descendants"), exp, obs, ok)


def p_merged_split_locator() -> dict:
    """X0268's merged_range node split into two siblings on the same line (EVAL-SETS item 10: one TP,
    no FP)."""
    gold = load_gold("cbeta-mulu-X0268")
    base = as_prediction(gold)
    del gold
    n_all = len(base["nodes"])
    i, mr = next((j, n) for j, n in enumerate(base["nodes"]) if "merged_range" in (n.get("flags") or []))
    twin = copy.deepcopy(mr)
    twin["id"] = mr["id"] + ".split2"
    twin["flags"] = []
    sub = set(subtree(base, mr["id"]))
    j = max(k for k, n in enumerate(base["nodes"]) if n["id"] in sub)
    base["nodes"].insert(j + 1, twin)
    m = sc.score(base, "cbeta-mulu-X0268", registry=REG, frozen=FROZEN)
    exp = {"TP": n_all, "FP": 0, "FN": 0, "absorbed_into_merged_range": 1}
    obs = {"s_f1": block(s0(m)), "absorbed_into_merged_range": m["rows"]["t=0"]["absorbed_into_merged_range"]}
    ok = (obs["s_f1"]["TP"] == n_all and obs["s_f1"]["FP"] == 0 and obs["s_f1"]["FN"] == 0
          and obs["absorbed_into_merged_range"] == 1)
    return check("cbeta-mulu-X0268: split the merged_range node into two same-line siblings", exp, obs, ok)


def p_merged_split_structure(distinct: bool) -> dict:
    """A T1602 merged_range leaf split into two siblings: second part with the same heading (the
    scorer's absorption path) or with its own heading (what a real split looks like). EVAL-SETS item 10
    says a prediction that splits a merged_range node is not an error (one TP, no FP)."""
    gold = load_gold("ybh-T1602")
    base = as_prediction(gold, keep_headings=True)
    del gold
    n_all = len(base["nodes"])
    ch = children_map(base)
    i, mr = next((j, n) for j, n in enumerate(base["nodes"])
                 if "merged_range" in (n.get("flags") or []) and not ch.get(n["id"]))
    twin = copy.deepcopy(mr)
    twin["id"] = mr["id"] + ".split2"
    twin["flags"] = []
    if distinct:
        twin["heading_src"] = (mr.get("heading_src") or "") + "　[E06-split-part-2]"
    base["nodes"].insert(i + 1, twin)
    m = sc.score(base, "ybh-T1602", registry=REG, frozen=FROZEN)
    r = m["rows"]["structure"]
    exp = {"TP": n_all, "FP": 0, "FN": 0, "absorbed_into_merged_range": 1}
    obs = {"s_f1": block(r["s_f1"]), "absorbed_into_merged_range": r["absorbed_into_merged_range"]}
    ok = obs["s_f1"]["FP"] == 0 and obs["absorbed_into_merged_range"] == 1
    extra = {}
    if not ok:
        extra["cause"] = ("score.py _match absorption (lines 320-329) needs dist(pred, merged gold) <= t; "
                          "in structure mode dist is heading equality (_Scorer.dist, lines 437-440), so a "
                          "split part with its own heading is never absorbed and counts as FP, against "
                          "EVAL-SETS item 10")
    return check("ybh-T1602 structure: split a merged_range leaf into two siblings, the second with %s"
                 % ("its own heading" if distinct else "the same heading"), exp, obs, ok, **extra)


# ------------------------------------------------------------- synthetic minimal repros (no data)


def _syn_node(nid, parent, lvl, explained=None, root=None, heading="", flags=None):
    return {"id": nid, "parent_id": parent, "level": lvl, "origin": "explicit", "heading_src": heading,
            "flags": flags or [],
            "locations": {"scheme": "cbeta-kepan", "commentary": {"announced": None, "explained": explained},
                          "root_text": ({"start": root, "end": root} if root else None)}}


def synthetic_repros() -> list:
    """Invented files T99n9997 (lines a01..a19) and invented headings; nothing from any gold."""
    F = "T99n9997"
    L = ["%s_p0001a%02d" % (F, i) for i in range(1, 20)]
    out = []
    # (1) t=1 mis-pairing of a uniformly shifted prediction
    gold = {"metadata": {"gold_status": "synthetic-fixture"},
            "nodes": [_syn_node("1", None, 1, L[0]), _syn_node("1.1", "1", 2, L[1]),
                      _syn_node("1.2", "1", 2, L[2])]}
    pred = copy.deepcopy(gold)
    for n in pred["nodes"]:
        c = n["locations"]["commentary"]
        c["explained"] = L[L.index(c["explained"]) + 1]
    m = sc.score(pred, "e06-repro-unregistered", gold=gold, line_orders={F: L}, t=1, registry=REG)
    out.append({"issue": "t=1 greedy sibling matching mis-pairs a +1-shifted prediction",
                "setup": "gold 1@a01, children 1.1@a02, 1.2@a03; prediction = every line +1",
                "expected_t1": {"TP": 3, "FP": 0, "FN": 0, "F": 1.0},
                "observed_t1": block(m["rows"]["t=1"]["s_f1"]),
                "observed_t1_locator_only_F": m["rows"]["t=1"]["locator_only"]["F"]})
    # (2) root-text scoring: a region whose last gold node has no split locator is split_unknown
    reg2 = copy.deepcopy(REG)
    reg2["datasets"].append({"id": "e06-repro-root", "kind": "gold", "format": "zh-kepan-outline",
                             "path": "<in memory>", "anchors": "root",
                             "split_scope": {"text": "T1718", "by": "locations.commentary.explained"}})
    dev_start = next(s for split, s, _ in reg.split_spans(REG, "T1718") if split == "dev")
    gold = {"metadata": {"gold_status": "synthetic-fixture"},
            "nodes": [_syn_node("1", None, 1, dev_start, L[0]), _syn_node("1.1", "1", 2, dev_start, L[1]),
                      _syn_node("1.2", "1", 2, None, L[4])]}
    pred = copy.deepcopy(gold)
    pred["nodes"].append(_syn_node("1.3", "1", 2, None, L[7]))
    m = sc.score(pred, "e06-repro-root", gold=gold, registry=reg2, line_orders={F: L}, split="dev")
    out.append({"issue": "root-text split region inherits None from a gold node without its own split "
                         "locator: an unmatched prediction there is neither TP nor FP",
                "setup": "gold 1 and 1.1 explained in T1718 dev (root a01, a02); 1.2 has no explained "
                         "line (root a05); prediction = gold + an extra child 1.3 at root a08",
                "expected_if_region_followed_nearest_known_split": {"TP": 2, "FP": 1, "FN": 0},
                "observed": block(m["rows"]["t=0"]["s_f1"]),
                "observed_pred_excluded": m["counts"]["pred"]["excluded"],
                "observed_gold_excluded": m["counts"]["gold"]["excluded"]})
    # (3) structure mode: a split of a merged_range node with its own heading is FP
    gold = {"metadata": {"gold_status": "synthetic-fixture"},
            "nodes": [_syn_node("1", None, 1, heading="甲"),
                      _syn_node("1.1", "1", 2, heading="乙", flags=["merged_range"])]}
    for n in gold["nodes"]:
        n["locations"] = {"scheme": "none"}
    pred = copy.deepcopy(gold)
    pred["nodes"].append(dict(copy.deepcopy(pred["nodes"][1]), id="1.2", heading_src="丙", flags=[]))
    m = sc.score(pred, "e06-repro-structure", gold=gold, registry=REG, key="structure")
    out.append({"issue": "structure mode never absorbs a merged_range split whose parts have their own "
                         "headings (EVAL-SETS item 10: one TP, no FP)",
                "setup": "gold 甲 > 乙 (merged_range); prediction 甲 > 乙, 丙",
                "expected": {"TP": 2, "FP": 0, "FN": 0},
                "observed": block(m["rows"]["structure"]["s_f1"]),
                "absorbed": m["rows"]["structure"]["absorbed_into_merged_range"]})
    return out


def p_ood_needs_frozen() -> dict:
    try:
        sc.score({"metadata": {}, "nodes": []}, "cbeta-mulu-P1573", registry=REG)
        refused = False
    except SplitViolation:
        refused = True
    return check("guard: OOD gold scored without frozen", {"refused": True}, {"refused": refused}, refused)


def perturbations() -> list:
    out = [p_ood_needs_frozen()]
    # P1573, OOD, frozen; all nodes counted (key commentary.explained = root_text.start = own line)
    gold = load_gold("cbeta-mulu-P1573")
    base = as_prediction(gold)
    del gold
    kw = {"frozen": FROZEN}
    ids = [n["id"] for n in base["nodes"]]
    m = sc.score(base, "cbeta-mulu-P1573", registry=REG, **kw)
    n = m["counts"]["gold"]["counted"]
    out.append(check("cbeta-mulu-P1573: unperturbed copy", {"TP": n, "FP": 0, "FN": 0, "F": 1.0},
                     {"s_f1": block(s0(m))}, s0(m)["F"] == 1.0 and s0(m)["TP"] == n))
    out.append(p_drop_leaves(base, ids, "cbeta-mulu-P1573", kw, n, "cbeta-mulu-P1573", ("t=0", "t=1")))
    out.append(p_reparent(base, ids, "cbeta-mulu-P1573", kw, n, "commentary.explained", "cbeta-mulu-P1573"))
    out.append(p_shift(base, ids, "cbeta-mulu-P1573", kw, n, "commentary.explained", "cbeta-mulu-P1573"))
    out.append(p_duplicate(base, ids, "cbeta-mulu-P1573", kw, n, "cbeta-mulu-P1573"))
    # Kuiji dev subtree (levels 1-2 + 陀羅尼品 subtree; draft gold, dev split; perturb dev nodes only)
    base, dev_ids = kuiji_dev_prediction()
    kw = {"split": "dev"}
    m = sc.score(base, "kuiji-xuanzan", registry=REG, **kw)
    n = m["counts"]["gold"]["counted"]
    out.append(check("kuiji-xuanzan dev: unperturbed levels 1-2 + dev subtree",
                     {"TP": n, "FP": 0, "FN": 0, "F": 1.0, "dev_subtree_nodes": len(dev_ids)},
                     {"s_f1": block(s0(m)), "dev_subtree_nodes": len(dev_ids)},
                     s0(m)["F"] == 1.0 and s0(m)["TP"] == n == len(dev_ids)))
    out.append(p_drop_leaves(base, dev_ids, "kuiji-xuanzan", kw, n, "kuiji-xuanzan dev", ("t=0", "t=1")))
    out.append(p_reparent(base, dev_ids, "kuiji-xuanzan", kw, n, "commentary.explained", "kuiji-xuanzan dev"))
    out.append(p_shift(base, dev_ids, "kuiji-xuanzan", kw, n, "commentary.explained", "kuiji-xuanzan dev",
                       split_text="T1723"))
    out.append(p_duplicate(base, dev_ids, "kuiji-xuanzan", kw, n, "kuiji-xuanzan dev"))
    # YBh structure mode
    for gid in ("ybh-T1605", "ybh-T1602"):
        out.append(p_alter_headings(gid, leaves_only=True))
        out.append(p_alter_headings(gid, leaves_only=False))
    # merged_range (EVAL-SETS item 10)
    out.append(p_merged_split_locator())
    out.append(p_merged_split_structure(distinct=False))
    out.append(p_merged_split_structure(distinct=True))
    return out


# ---------------------------------------------------------------------------- 3. scope quirks


def t0262_region_quirk() -> dict:
    """Root-text scoring on sdp-T0262: a predicted node takes the split of the last gold node starting at
    or before its line; when that gold node has no commentary.explained, the region is None and the
    prediction is excluded (split_unknown: neither TP nor FP). Measured over the lines of T09n0262."""
    ds = reg.dataset(REG, "sdp-T0262-zhiyi-wenju")
    gold = load_gold("sdp-T0262-zhiyi-wenju")
    gt = sc._Tree(gold, "root_text.start", "gold")
    lines = sc._Lines({"T09n0262"})
    sm = sc._SplitMap(REG, ds, "root_text.start", gt, lines)
    recs = list(iter_lines(cbeta_xml_path("T09n0262")))
    pins = [i for i, r in enumerate(recs) if any(mm.get("type") == "品" for mm in r["mulu"])]
    xu = [r["linehead"] for r in recs[pins[0]:pins[1]]]
    asym = Counter()
    for g in gt.ids:
        nd = gt.by_id[g]
        gs, ps = sm.of(nd, gt.key[g], "gold"), sm.of(nd, gt.key[g], "pred")
        if gs != ps:
            asym["gold %s / pred-twin %s" % (gs, ps)] += 1
    all_lines = Counter(str(sm._region(lh)) for lh in lines.orders["T09n0262"].lineheads)
    xu_lines = Counter(str(sm._region(lh)) for lh in xu)
    del gold
    return {
        "what": "sdp-T0262 root-text scoring: split of each T09n0262 line under the region rule "
                "(None = split_unknown: a prediction there is neither TP nor FP)",
        "T09n0262_lines_by_region_split": dict(sorted(all_lines.items())),
        "xu_pin_lines_by_region_split": dict(sorted(xu_lines.items())),
        "gold_nodes_whose_pred_twin_gets_another_split": dict(asym),
        "effect_on_E06": "T0262-xu-root (序品) lies almost wholly in the validation region (309 of 319 "
                         "lines) with a 9-line dev region; predictions outside 序品 fall mostly in None "
                         "regions and are silently unscored; the asymmetric twins are reserve-only",
    }


def headline_quirk(gvi: list) -> dict:
    rows = {v["name"]: v["headline"] for v in gvi}
    return {
        "what": "disclosures.headline per gold-vs-itself row; score.py NO_HEADLINE_STATUS lacks "
                "'imported-unchecked', so an OOD (unsplit) row reports headline true",
        "headline_by_row": rows,
        "conflict": "E06 README: 'None is a headline: ... the OOD golds are imported-unchecked'",
    }


# ------------------------------------------------------------------------------------------- main


def frozen_state() -> dict:
    def git(*a):
        return subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()

    diff = subprocess.run(["git", "diff", "--quiet", FROZEN, "--", "pipeline/"], cwd=REPO_ROOT).returncode
    untracked = git("ls-files", "--others", "--exclude-standard", "--", "pipeline/")
    return {"tag": FROZEN, "tag_commit": git("rev-parse", FROZEN + "^{commit}"),
            "pipeline_identical_to_tag": diff == 0 and not untracked,
            "pipeline_commit": outline_doc.pipeline_commit()}


def main() -> int:
    state = frozen_state()
    gvi = gold_vs_itself()
    pert = perturbations()
    quirks = {"t0262_root_text_regions": t0262_region_quirk(), "headline_flag": headline_quirk(gvi),
              "pipeline_commit_dirty_flag": {
                  "what": "outline_doc.pipeline_commit() marks 'dirty' from a repo-wide git status "
                          "(common/outline_doc.py:296), so E06 builds say '+dirty' in generated_by "
                          "while pipeline/ is byte-identical to the frozen tag (frozen.pipeline_identical_"
                          "to_tag); record the latter with every E06 run",
                  "pipeline_commit": state["pipeline_commit"],
                  "pipeline_identical_to_tag": state["pipeline_identical_to_tag"]},
              "prediction_status_not_checked": {
                  "what": "score() never reads the prediction's gold_status except into "
                          "settings.prediction (score.py:764-765): a gold passed as --pred is scored "
                          "silently, and headline is decided by the gold's status and the split only"}}
    repros = synthetic_repros()
    out = {
        "schema": "e06-sanity/1",
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "script": "experiments/E06-capability-sweep/sanity_e06.py",
        "frozen": state,
        "seed": SEED,
        "note": "Aggregate numbers only. Gold vs itself is not an outliner look (no prediction scored); "
                "nothing was recorded in looks.json. Test / reserve splits were not scored.",
        "gold_vs_itself": gvi,
        "gold_vs_itself_all_ok": all(v["ok"] for v in gvi),
        "perturbations": pert,
        "perturbations_ok": sum(c["ok"] for c in pert),
        "perturbations_total": len(pert),
        "scope_quirks": quirks,
        "synthetic_repros": repros,
    }
    jsonio.write_json(out, HERE / "sanity.json")
    for v in gvi:
        r = v["rows"].get("t=0") or v["rows"].get("structure")
        print("%-46s counted %5d (expected %5d)  S-F1 %.3f  F-F1 %.3f  det %.3f  %s" % (
            v["name"], v["counts"]["gold"]["counted"], v["expected_gold_counted"], r["s_f1"]["F"],
            r["f_f1"]["F"], r["detection"]["F"], "ok" if v["ok"] else "CHECK"))
    for c in pert:
        print("%-5s %s" % ("ok" if c["ok"] else "FAIL", c["name"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
