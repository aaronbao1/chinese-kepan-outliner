#!/usr/bin/env python3
"""E00 kēpàn census — fetch stage and cluster/genre tables.

Input : CBETA API (https://cbdata.dila.edu.tw/stable/, v4.6.7, data 2026R2), public, no key.
Output: out/api/…            verbatim JSON responses (cache; gitignored)
        out/works_TX.csv      every T and X work with 底本 部 (orig 部) and CBETA 部類, from the catalogue crawl
        out/clusters.csv      CBETA 部類 cluster nodes: root texts vs commentaries, genre classes
        out/commentaries.csv  every T/X commentary in a cluster (+ works/toc stats for the 158 T 疏部 works)
        out/toc_stats.csv     works/toc node count / depth / level>=2 types for the 158 T 疏部 works
        out/title_hits.csv    search/title hits for 科 / 科文 / 科註 / 科解 / 科節 / 科判
        out/fulltext_counts.json  search?q=序分|正宗分|流通分&rows=0 num_found
Usage : python3 census.py fetch     # crawl + cache (0.4 s pacing, sequential, resumable)
        python3 census.py report    # build the CSV tables from the cache and print the summary tables
Python 3.9; stdlib + requests. Deterministic given the cache.
"""
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from urllib.parse import quote

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
API_DIR = os.path.join(OUT, "api")
BASE = "https://cbdata.dila.edu.tw/stable"
UA = "chinese-workflow E00 census (research use; python-requests)"
SLEEP = 0.4
SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA

CJK_NUM = "一二三四五六七八九十"
# Taishō 底本 部 ranges (from catalog_entry?q=orig-T, 2026-09-22)
T_RANGES = {
    "阿含部": (1, 151), "本緣部": (152, 219), "般若部": (220, 261), "法華部": (262, 277),
    "華嚴部": (278, 309), "寶積部": (310, 373), "涅槃部": (374, 396), "大集部": (397, 424),
    "經集部": (425, 847), "密教部": (848, 1420), "律部": (1421, 1504), "釋經論部": (1505, 1535),
    "毘曇部": (1536, 1563), "中觀部": (1564, 1578), "瑜伽部": (1579, 1627), "論集部": (1628, 1692),
    "經疏部": (1693, 1803), "律疏部": (1804, 1815), "論疏部": (1816, 1850), "諸宗部": (1851, 2025),
    "史傳部": (2026, 2120), "事彙部": (2121, 2136), "外教部": (2137, 2144), "目錄部": (2145, 2184),
    "續經疏部": (2185, 2245), "續律疏部": (2246, 2248), "續論疏部": (2249, 2295), "續諸宗部": (2296, 2700),
    "悉曇部": (2701, 2731), "古逸部": (2732, 2864), "疑似部": (2865, 2920),
}
T_ROOT_PARTS = {"阿含部", "本緣部", "般若部", "法華部", "華嚴部", "寶積部", "涅槃部", "大集部", "經集部",
                "密教部", "律部", "釋經論部", "毘曇部", "中觀部", "瑜伽部", "論集部"}
T_SUTRA_PARTS = {"阿含部", "本緣部", "般若部", "法華部", "華嚴部", "寶積部", "涅槃部", "大集部", "經集部", "密教部"}
T_VINAYA_PARTS = {"律部"}
T_SASTRA_PARTS = {"釋經論部", "毘曇部", "中觀部", "瑜伽部", "論集部"}
T_COMM_PARTS = {"經疏部", "律疏部", "論疏部", "諸宗部", "續經疏部", "續律疏部", "續論疏部", "續諸宗部", "古逸部", "疑似部"}
# 卍續藏 底本 部 (from catalog_entry?q=orig-X)
X_ROOT_PARTS = {"印度撰述"}
X_COMM_PARTS = {"大小乘釋經部", "大小乘釋律部", "大小乘釋論部", "諸宗著述部"}

TITLE_TERMS = ["科", "科文", "科註", "科解", "科節", "科判"]
FULLTEXT_TERMS = ["序分", "正宗分", "流通分"]
# fascicles needed by quote_check.py (R01 quotes from works not on local disk); fetched here so all API traffic is one paced stream
EXTRA_JUANS = [("T1707", 1), ("T1666", 1), ("T1530", 1), ("T1764", 1), ("X0577", 1), ("T1736", 1),
               ("T1753", 1), ("T1753", 2), ("T1579", 1), ("T1775", 1), ("T0026", 1), ("T1700", 1)]


# ----------------------------------------------------------------------------- fetch helpers
def cache_path(name):
    return os.path.join(API_DIR, name + ".json")


def get_json(url, name, params=None):
    """GET url (with params) → parsed JSON, cached under out/api/<name>.json. Sequential, 0.4 s pacing."""
    p = cache_path(name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    for attempt in range(4):
        try:
            r = SESSION.get(url, params=params, timeout=120)
            time.sleep(SLEEP)
            if r.status_code == 200:
                data = r.json()
                os.makedirs(API_DIR, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                return data
            print(f"  HTTP {r.status_code} for {r.url}; attempt {attempt+1}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  error {e!r} for {url}; attempt {attempt+1}", file=sys.stderr)
        time.sleep(2 + 3 * attempt)
    raise SystemExit(f"giving up on {url}")


def crawl_catalog(root, max_depth=12, skip_prefixes=()):
    """Recursively fetch catalog_entry?q=<node> for every folder node under root. Returns {node_n: results}."""
    tree = {}
    stack = [(root, 0)]
    while stack:
        n, depth = stack.pop()
        if any(n.startswith(s) for s in skip_prefixes):
            continue
        data = get_json(f"{BASE}/catalog_entry", f"catalog_{n}", params={"q": n})
        results = data.get("results", [])
        tree[n] = results
        if depth >= max_depth:
            continue
        for r in reversed(results):  # keep document order when popping
            if r.get("node_type") is None:  # folder
                stack.append((r["n"], depth + 1))
    return tree


def t_part(work):
    """底本 部 of a T work from its number (the orig-T crawl confirms; this is the fallback for parsing)."""
    m = re.match(r"T(\d+)", work)
    if not m:
        return None
    n = int(m.group(1))
    for part, (a, b) in T_RANGES.items():
        if a <= n <= b:
            return part
    return None


def fetch():
    os.makedirs(API_DIR, exist_ok=True)
    print("all-works.json")
    get_json(f"{BASE}/download/all-works.json", "all-works")
    print("orig-T crawl")
    crawl_catalog("orig-T")
    print("orig-X crawl")
    crawl_catalog("orig-X")
    print("CBETA 部類 crawl (root, then 001–019 recursive; 020–023 top level only)")
    get_json(f"{BASE}/catalog_entry", "catalog_CBETA", params={"q": "CBETA"})
    for i in range(1, 24):
        n = f"CBETA.{i:03d}"
        if i <= 19:
            crawl_catalog(n)
        else:
            get_json(f"{BASE}/catalog_entry", f"catalog_{n}", params={"q": n})
    # the 158 T 疏部 works: metadata, works/toc, juan 1
    works = commentary_works_T()
    print(f"{len(works)} T 經疏部/律疏部/論疏部 works: works, works/toc, juans juan=1")
    for w in works:
        get_json(f"{BASE}/works", f"works_{w}", params={"work": w})
        get_json(f"{BASE}/works/toc", f"toc_{w}", params={"work": w})
        get_json(f"{BASE}/juans", f"juans_{w}_1", params={"work": w, "juan": 1})
    print("title searches")
    for t in TITLE_TERMS:
        get_json(f"{BASE}/search/title", f"title_{t}", params={"q": t})
    get_json(f"{BASE}/search/title", "title200_科", params={"q": "科", "rows": 200})  # the default page is 20 rows; 科 has 93 hits
    print("full-text counts (rows=0)")
    for t in FULLTEXT_TERMS:
        get_json(f"{BASE}/search", f"search_{t}", params={"q": t, "rows": 0})
    print("extra fascicles for quote_check.py")
    for w, j in EXTRA_JUANS:
        get_json(f"{BASE}/juans", f"juans_{w}_{j}", params={"work": w, "juan": j})
    print("fetch done")


def commentary_works_T():
    """T works in 經疏部 (orig-T.035–041), 律疏部 (042), 論疏部 (043–047), from the cached orig-T crawl."""
    out = []
    for i in range(35, 48):
        data = json.load(open(cache_path(f"catalog_orig-T.{i:03d}"), encoding="utf-8"))
        for r in data["results"]:
            if r.get("node_type") == "work":
                out.append(r["work"])
    return out


# ----------------------------------------------------------------------------- report
def load_tree(prefix):
    tree = {}
    for fn in os.listdir(API_DIR):
        if fn.startswith(f"catalog_{prefix}") and fn.endswith(".json"):
            n = fn[len("catalog_"):-len(".json")]
            tree[n] = json.load(open(os.path.join(API_DIR, fn), encoding="utf-8")).get("results", [])
    return tree


def orig_parts():
    """{work: (canon, 底本 部)} for every T and X work from the orig crawls."""
    part_of = {}
    for prefix, canon in (("orig-T", "T"), ("orig-X", "X")):
        tree = load_tree(prefix)
        # top-level labels give the 部 name per node id
        top = {r["n"]: r["label"] for r in tree.get(prefix, [])}
        for n, results in tree.items():
            if n == prefix:
                continue
            top_n = ".".join(n.split(".")[:2])
            label = top.get(top_n, "")
            part = part_from_label(label, canon)
            for r in results:
                if r.get("node_type") == "work":
                    part_of[r["work"]] = (canon, part, r.get("category"), r.get("creators"), r["label"])
    return part_of


def part_from_label(label, canon):
    # 'T33 經疏部一 T1693-1717' → 經疏部 ; 'X03-37 大小乘釋經部 X0208-0675' → 大小乘釋經部
    m = re.search(r"\s([一-鿿]+?)(?:[一二三四五六七八九十]+|上|下|全)?\s", label + " ")
    if not m:
        return None
    name = m.group(1)
    if canon == "T":
        if name in T_RANGES:          # exact first: 律疏部 must not fall into 律部 by prefix
            return name
        for part in T_RANGES:         # e.g. '般若部一～三' → 般若部
            if name.startswith(part):
                return part
        return name
    return name


def genre_class(title):
    if any(k in title for k in ("疏", "文句", "玄贊", "科")):
        return "疏"
    if "注" in title or "註" in title:
        return "注"
    return "other"


def toc_stats(work):
    p = cache_path(f"toc_{work}")
    if not os.path.exists(p):
        return None
    data = json.load(open(p, encoding="utf-8"))
    results = data.get("results")
    if not results:
        return {"nodes": 0, "depth": 0, "types_l2plus": "", "l1_types": ""}
    mulu = results[0].get("mulu", results[0]) if isinstance(results, list) else results
    nodes = mulu if isinstance(mulu, list) else mulu.get("children", [])
    count = 0
    depth = 0
    l2 = Counter()
    l1 = Counter()

    def rec(items, d):
        nonlocal count, depth
        for it in items:
            count += 1
            depth = max(depth, d)
            (l1 if d == 1 else l2)[it.get("type") or "∅"] += 1
            rec(it.get("children", []) or [], d + 1)

    rec(nodes, 1)
    return {"nodes": count, "depth": depth,
            "types_l2plus": " ".join(f"{k}:{v}" for k, v in l2.most_common()),
            "l1_types": " ".join(f"{k}:{v}" for k, v in l1.most_common())}


def report():
    os.makedirs(OUT, exist_ok=True)
    allworks = {w["work"]: w for w in json.load(open(cache_path("all-works"), encoding="utf-8"))}
    part_of = orig_parts()
    # works_TX.csv
    with open(os.path.join(OUT, "works_TX.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["work", "canon", "orig_part", "cbeta_category", "creators", "title"])
        for w in sorted(part_of):
            canon, part, cat, cr, label = part_of[w]
            wr.writerow([w, canon, part, cat, cr, allworks.get(w, {}).get("title", "")])
    # denominators
    denom = Counter()
    for w, (canon, part, *_rest) in part_of.items():
        if canon == "T" and part in T_ROOT_PARTS:
            denom[part] += 1
        if canon == "X" and part in X_ROOT_PARTS:
            denom["X 印度撰述"] += 1
    # clusters from the CBETA 部類 tree
    tree = load_tree("CBETA")
    label_of = {}
    children_of = defaultdict(list)
    for n, results in tree.items():
        for r in results:
            label_of[r["n"]] = r["label"]
            children_of[n].append(r)

    def descendant_works(n):
        out = []
        for r in children_of.get(n, []):
            if r.get("node_type") == "work":
                out.append(r["work"])
            elif r.get("node_type") is None:
                out.extend(descendant_works(r["n"]))
        return out

    def is_root(w):
        canon, part = part_of.get(w, (None, None, None, None, None))[:2]
        return (canon == "T" and part in T_ROOT_PARTS) or (canon == "X" and part in X_ROOT_PARTS)

    def is_comm(w):
        """T works in the Chinese-authored 部 and X works in the 釋經／釋律／釋論／諸宗著述 部. Other canons (F, L, P, J, K, G, …)
        are mostly other editions of the same texts and cannot be classified by 部 here: they are counted but never as commentaries."""
        canon, part = part_of.get(w, (None, None, None, None, None))[:2]
        if canon == "T":
            return part in T_COMM_PARTS
        if canon == "X":
            return part in X_COMM_PARTS
        return False

    # A cluster = a *minimal* folder node below the 部類 top (n has ≥ 2 dots) whose descendants include ≥ 1 root text and
    # ≥ 1 commentary and none of whose descendant folders also does. A work may sit in several clusters (CBETA lists some works
    # under two 部類, e.g. T0365 under 寶積部類 and 淨土宗部類); counts over works are taken over distinct ids.
    # Where CBETA files a root folder and its 疏 folder as siblings (so the only common ancestor is the whole 部類), the pairing is
    # supplied by MANUAL_LINKS below, each entry checked against the titles in all-works.json on 2026-09-22.
    def is_folder_qualifying(n):
        ws = descendant_works(n)
        return any(is_root(w) for w in ws) and any(is_comm(w) for w in ws)

    def descendant_folders(n):
        out = []
        for r in children_of.get(n, []):
            if r.get("node_type") is None:
                out.append(r["n"])
                out.extend(descendant_folders(r["n"]))
        return out

    # Rule (2026-09-22, replaces the 'minimal node' draft): every commentary placement is attached to its DEEPEST qualifying
    # ancestor folder (a folder with n ≥ 2 dots whose descendants hold ≥ 1 root text and ≥ 1 commentary). A cluster's roots
    # are the root texts among that folder's descendants that are not inside a deeper qualifying folder (which forms its own
    # cluster, e.g. 釋摩訶衍論 T1668 + its 疏 inside the 起信論 node). Commentaries whose only qualifying ancestor would be the 部類
    # top (阿含經疏, 俱舍論疏, 四分律疏, 密教疏 …) stay unattached unless MANUAL_LINKS pairs them.
    qualifying = {n for n in tree if n.count(".") >= 2 and is_folder_qualifying(n)}
    parent_of = {}
    for n, results in tree.items():
        for r in results:
            if r.get("node_type") is None:
                parent_of[r["n"]] = n
    placements = defaultdict(list)  # comm work → list of folder ids where it is a direct child
    for n, results in tree.items():
        for r in results:
            if r.get("node_type") == "work" and is_comm(r["work"]):
                placements[r["work"]].append(n)
    cluster_comms = defaultdict(set)
    unattached = {}
    for w, folders in placements.items():
        for f in folders:
            a = f
            while a is not None and a not in qualifying:
                a = parent_of.get(a)
            if a is None:
                unattached[w] = f
            else:
                cluster_comms[a].add(w)
    clusters = []
    for n in sorted(cluster_comms):
        deeper_q = [d for d in descendant_folders(n) if d in qualifying]
        inside_deeper = set()
        for d in deeper_q:
            inside_deeper.update(descendant_works(d))
        roots = sorted({w for w in descendant_works(n) if is_root(w) and w not in inside_deeper})
        clusters.append((n, label_of.get(n, ""), roots, sorted(cluster_comms[n]), "auto"))
    # manual sibling links: node → (root work ids, recursive?) ; per-work overrides for a mixed node
    MANUAL_LINKS = {
        "CBETA.001.008": (["T0014", "T0603"], True),            # 人本欲生經註 T1693 / 陰持入經註 T1694 → 人本欲生經 / 陰持入經 (阿含部類 sibling folders)
        "CBETA.012.006": (["T1558", "T1559"], True),            # 俱舍論疏 T1821–23, X0836–42 → 俱舍論 / 俱舍釋論 (毘曇部類 sibling folders)
        "CBETA.011.002": (["T1428"], True),                     # 四分律疏 T1804–07, X0708 … (+古逸疏 T2787–96) → 四分律 (律部類 sibling folders)
        "CBETA.010.002.004": (["T0945"], True),                 # 首楞嚴義疏注經 etc. → 大佛頂首楞嚴經 (密教部類: root under 諸佛頂儀軌, 疏 under 密教疏)
        "CBETA.010.002.008": (["T0967"], True),                 # 佛頂尊勝陀羅尼經教跡義記 T1803, X0445 → 佛頂尊勝陀羅尼經
        "CBETA.010.002.009": (["T0848"], True),                 # 大日經義釋 X0438–39 → 大毘盧遮那成佛神變加持經
    }
    MANUAL_WORK_ROOT = {  # direct works of CBETA.010.002 密教疏 (mixed node)
        "T1796": "T0848", "T1797": "T0848", "T1798": "T0865", "T1800": "T1043", "T1801": "T1043", "T1802": "T1071",
        "X0446": "T1076", "X0447": "T1081",
        # X 釋經／釋律 works filed in folders without a root text (titles checked in all-works.json, 2026-09-22)
        "X0211": "T0279", "X0218": "T0279", "X0220": "T0279", "X0235": "T0279", "X0236": "T0279", "X0237": "T0279",
        "X0238": "T0279", "X0239": "T0279", "X0240": "T0279", "X0241": "T0279", "X0242": "T0279",   # 華嚴 digests/綱要 → 80卷 華嚴經
        "X0448": "T0220", "X0449": "T0220",                                                            # 大般若經關法／綱要
        "X0702": "T1501", "X0703": "T1499",                                                            # 菩薩戒本箋要 → 菩薩戒本; 菩薩戒羯磨文釋 → 菩薩戒羯磨文
        "X0709": "T1428", "X0749": "T0087",                                                            # 毗尼止持會集 → 四分律; 齋經科註 → 齋經
        # left unattached on purpose: X0784 大乘四論玄義 (treatise), X0844 異部宗輪論疏述記 (root T2031 is filed in 史傳部)
    }
    for n, (roots, recursive) in MANUAL_LINKS.items():
        if n not in tree or n in qualifying:
            continue
        ws = descendant_works(n) if recursive else [r["work"] for r in children_of.get(n, []) if r.get("node_type") == "work"]
        comms = sorted({w for w in ws if is_comm(w) and w not in cluster_comms.get(n, set())})
        clusters.append((n, label_of.get(n, "") + " [manual link]", roots, comms, "manual"))
    by_root = defaultdict(list)
    already = {w for _n, _l, _r, comms, _h in clusters for w in comms}
    for w, r in MANUAL_WORK_ROOT.items():
        if w not in already:
            by_root[r].append(w)
    for r, cs in by_root.items():
        clusters.append(("manual/" + r, f"works → {r} {allworks.get(r, {}).get('title', '')} [manual link]", [r], sorted(cs), "manual"))
    # school / collection nodes: qualifying only through a root inside a deeper sub-cluster, no root of their own
    school = [(n, l, r, c) for n, l, r, c, h in clusters if not r]
    clusters = [c for c in clusters if c[2]]
    print(f"[clusters] nodes with commentaries but no own root text (school collections, not clusters): "
          + "; ".join(f"{l[:30]} ({len(c)} works)" for n, l, r, c in school))
    print(f"[clusters] qualifying folders below 部類 top: {len(qualifying)}, clusters with commentaries: {len(cluster_comms)}, manual: {len(clusters) - len(cluster_comms)}; "
          f"commentary placements unattached at 部類 level: {len(unattached)}")
    # cluster table
    rows = []
    comm_rows = []
    for n, label, roots, comms, how in clusters:
        bulei = label_of.get(".".join(n.split(".")[:2]), "")
        classes = Counter()
        by_canon = Counter()
        for w in comms:
            title = allworks.get(w, {}).get("title", "")
            g = genre_class(title)
            classes[g] += 1
            by_canon[w[0] if w[0] in "TX" and w[1].isdigit() else "other"] += 1
            comm_rows.append({"work": w, "title": title, "canon": part_of.get(w, ("other",))[0] if w in part_of else "other",
                              "orig_part": part_of.get(w, (None, None))[1] if w in part_of else "",
                              "creators": part_of.get(w, (None, None, None, None))[3] if w in part_of else "",
                              "genre": g, "cluster": n, "cluster_label": label, "bulei": bulei,
                              "n_juan": len(allworks.get(w, {}).get("juans", []))})
        t_roots = [w for w in roots if w.startswith("T")]
        n_shu_T = sum(1 for w in comms if w in part_of and part_of[w][0] == "T" and part_of[w][1] in {"經疏部", "律疏部", "論疏部"})
        rows.append({"cluster": n, "label": label, "how": how, "bulei": bulei, "n_root": len(roots), "n_root_T": len(t_roots),
                     "roots": " ".join(roots), "n_comm": len(comms), "n_comm_T": by_canon["T"], "n_comm_T_shubu": n_shu_T,
                     "n_comm_X": by_canon["X"], "n_comm_other": by_canon["other"], "n_疏": classes["疏"], "n_注": classes["注"],
                     "n_other": classes["other"], "has_疏": int(classes["疏"] > 0), "has_non注": int(classes["疏"] + classes["other"] > 0)})
    with open(os.path.join(OUT, "clusters.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    # toc stats for the 158
    tstats = {}
    for w in commentary_works_T():
        s = toc_stats(w)
        if s:
            tstats[w] = s
    with open(os.path.join(OUT, "toc_stats.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["work", "title", "orig_part", "nodes", "depth", "l1_types", "types_l2plus"])
        for w, s in tstats.items():
            wr.writerow([w, allworks.get(w, {}).get("title", ""), part_of.get(w, (None, None))[1], s["nodes"], s["depth"], s["l1_types"], s["types_l2plus"]])
    for r in comm_rows:
        s = tstats.get(r["work"])
        r["toc_nodes"] = s["nodes"] if s else ""
        r["toc_depth"] = s["depth"] if s else ""
    with open(os.path.join(OUT, "commentaries.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(comm_rows[0].keys()))
        wr.writeheader()
        wr.writerows(comm_rows)
    # title hits
    with open(os.path.join(OUT, "title_hits.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["term", "work", "title", "byline", "orig_part"])
        for t in TITLE_TERMS:
            p = cache_path(f"title_{t}")
            if not os.path.exists(p):
                continue
            for r in json.load(open(p, encoding="utf-8")).get("results", []):
                wr.writerow([t, r["work"], r.get("content"), r.get("byline"), part_of.get(r["work"], (None, None))[1]])
    ft = {}
    for t in FULLTEXT_TERMS:
        p = cache_path(f"search_{t}")
        if os.path.exists(p):
            ft[t] = json.load(open(p, encoding="utf-8")).get("num_found")
    json.dump(ft, open(os.path.join(OUT, "fulltext_counts.json"), "w"), ensure_ascii=False, indent=1)

    # ------------------------------------------------------------------ printed summary
    print("## Denominators (works per 底本 部, from orig-T / orig-X crawl)")
    for part in T_RANGES:
        if part in T_ROOT_PARTS:
            print(f"  {part}: {denom[part]}")
    n_sutra = sum(denom[p] for p in T_SUTRA_PARTS)
    n_vin = sum(denom[p] for p in T_VINAYA_PARTS)
    n_sas = sum(denom[p] for p in T_SASTRA_PARTS)
    print(f"  T sūtra numbers (阿含…密教) {n_sutra}; vinaya {n_vin}; śāstra {n_sas}; total {n_sutra+n_vin+n_sas}; X 印度撰述 {denom['X 印度撰述']}")
    comm_counts = Counter(part_of[w][1] for w in part_of if part_of[w][0] == "T" and part_of[w][1] in T_COMM_PARTS)
    print("  T commentary 部:", dict(comm_counts))
    xcomm = Counter(part_of[w][1] for w in part_of if part_of[w][0] == "X")
    print("  X 部:", dict(xcomm))
    assigned = {w for _n, _l, _r, comms, _h in clusters for w in comms}
    distinct_comm = len(assigned)
    print(f"\n## Clusters: {len(rows)} root-text clusters ({sum(1 for r in rows if r['how']=='auto')} from the 部類 tree, {sum(1 for r in rows if r['how']=='manual')} manual sibling links); "
          f"distinct commentaries in clusters {distinct_comm} (cluster rows sum to {len(comm_rows)}; duplicates = works CBETA files under two 部類)")
    all_comm_T = [w for w in part_of if part_of[w][0] == "T" and part_of[w][1] in {"經疏部", "律疏部", "論疏部"}]
    unassigned = [w for w in all_comm_T if w not in assigned]
    print(f"  T 經疏/律疏/論疏 works in no root-text cluster (attached only at 部類 level): {len(unassigned)}")
    for w in unassigned:
        print(f"    {w} {allworks.get(w, {}).get('title','')} [{part_of[w][2]}]")
    all_comm_X = [w for w in part_of if part_of[w][0] == "X" and part_of[w][1] in {"大小乘釋經部", "大小乘釋律部", "大小乘釋論部"}]
    unassigned_X = [w for w in all_comm_X if w not in assigned]
    print(f"  X 釋經/釋律/釋論 works in no root-text cluster: {len(unassigned_X)} (first 15: {[(w, allworks.get(w, {}).get('title','')) for w in unassigned_X[:15]]})")
    roots_in_clusters = set()
    roots_with_疏 = set()
    roots_with_non注 = set()
    for n, label, roots, comms, how in clusters:
        for w in roots:
            if w.startswith("T") and is_root(w):
                roots_in_clusters.add(w)
        r = next(x for x in rows if x["cluster"] == n)
        if r["has_疏"]:
            roots_with_疏.update(w for w in roots if w.startswith("T") and is_root(w))
        if r["has_non注"]:
            roots_with_non注.update(w for w in roots if w.startswith("T") and is_root(w))
    total_root = n_sutra + n_vin + n_sas
    print(f"  T root numbers (T0001–T1692) in a cluster with ≥1 commentary: {len(roots_in_clusters)} / {total_root} = {100*len(roots_in_clusters)/total_root:.1f} %")
    print(f"  … with ≥1 class-疏 commentary: {len(roots_with_疏)} = {100*len(roots_with_疏)/total_root:.1f} %")
    print(f"  … with ≥1 non-注 commentary (upper bound): {len(roots_with_non注)} = {100*len(roots_with_non注)/total_root:.1f} %")
    for name, parts in (("sūtra", T_SUTRA_PARTS), ("vinaya", T_VINAYA_PARTS), ("śāstra", T_SASTRA_PARTS)):
        d = sum(denom[p] for p in parts)
        a = sum(1 for w in roots_in_clusters if part_of[w][1] in parts)
        b = sum(1 for w in roots_with_疏 if part_of[w][1] in parts)
        print(f"    {name}: any-commentary cluster {a}/{d} ({100*a/d:.1f} %), class-疏 {b}/{d} ({100*b/d:.1f} %)")
    print("  per 底本 部 (root numbers in a class-疏 cluster / total):")
    for part in T_RANGES:
        if part in T_ROOT_PARTS:
            b = sum(1 for w in roots_with_疏 if part_of[w][1] == part)
            a = sum(1 for w in roots_in_clusters if part_of[w][1] == part)
            print(f"    {part}: 疏 {b}, any {a}, of {denom[part]}")
    print("\n## Clusters ranked by number of commentaries (T+X+other)")
    top = sorted(rows, key=lambda r: -r["n_comm"])
    cum = 0
    tot = sum(r["n_comm"] for r in rows)
    for i, r in enumerate(top[:40], 1):
        cum += r["n_comm"]
        print(f"  {i:2d}. {r['label'][:60]:60s} roots {r['n_root']:3d}  comm {r['n_comm']:3d} (T {r['n_comm_T']}, X {r['n_comm_X']}, other {r['n_comm_other']}; 疏 {r['n_疏']}, 注 {r['n_注']}, other {r['n_other']})  cum {100*cum/tot:.0f} %")
    print(f"  total commentaries in clusters: {tot}")
    print("\n## Genre classes over all cluster commentaries (T / X / other)")
    for canon in ("T", "X", "other"):
        c = Counter(r["genre"] for r in comm_rows if (r["work"][0] == canon and r["work"][1].isdigit()) or (canon == "other" and not (r["work"][0] in "TX" and r["work"][1].isdigit())))
        print(f"  {canon}: {dict(c)}")
    print("\n## works/toc for the 158 T 疏部 works")
    dep = Counter(s["depth"] for s in tstats.values())
    print("  depth histogram:", dict(sorted(dep.items())))
    for w, s in sorted(tstats.items(), key=lambda kv: -kv[1]["nodes"]):
        if s["depth"] >= 2:
            print(f"  {w} {allworks.get(w, {}).get('title','')[:20]:20s} nodes {s['nodes']:5d} depth {s['depth']}  L1 {s['l1_types']}  L2+ {s['types_l2plus']}")
    print("\n## title hits (num_found / rows returned):", {t: (json.load(open(cache_path(f'title_{t}'), encoding='utf-8')).get('num_found'), len(json.load(open(cache_path(f'title_{t}'), encoding='utf-8')).get('results', []))) for t in TITLE_TERMS if os.path.exists(cache_path(f'title_{t}'))})
    p200 = cache_path("title200_科")
    if os.path.exists(p200):
        r200 = json.load(open(p200, encoding="utf-8")).get("results", [])
        canon_c = Counter(re.match(r"[A-Z]+", r["work"]).group(0) for r in r200)
        print(f"  科 with rows=200: {len(r200)} rows; by canon {dict(canon_c)}; T/X works: {sorted(r['work'] for r in r200 if r['work'][0] in 'TX' and r['work'][1].isdigit())}")
    tx_ke = [(w, allworks[w]["title"]) for w in allworks if (w.startswith("T") or w.startswith("X")) and w[1].isdigit() and "科" in allworks[w]["title"]]
    print(f"  local filter: T/X titles containing 科: {len(tx_ke)} (T {sum(1 for w,_ in tx_ke if w.startswith('T'))}, X {sum(1 for w,_ in tx_ke if w.startswith('X'))})")
    print("  full-text work counts:", ft)
    families_report(rows, comm_rows, part_of, allworks)


def families_report(rows, comm_rows, part_of, allworks):
    """Merge clusters that share a root work (the same 淨土 texts are filed under 寶積部類 and 淨土宗部類) and rank families by
    distinct commentaries; print genre classes per 底本 部 for the Chinese-authored 部."""
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    rootsets = {r["cluster"]: set(r["roots"].split()) for r in rows}
    ids = list(rootsets)
    for i in ids:
        parent.setdefault(i, i)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if rootsets[ids[i]] & rootsets[ids[j]]:
                parent[find(ids[i])] = find(ids[j])
    fam = defaultdict(lambda: {"label": None, "roots": set(), "comms": set()})
    for r in rows:
        f = find(r["cluster"])
        fam[f]["label"] = fam[f]["label"] or r["label"][:40]
        fam[f]["roots"] |= rootsets[r["cluster"]]
    for c in comm_rows:
        fam[find(c["cluster"])]["comms"].add(c["work"])
    out = []
    for f, d in fam.items():
        g = Counter(genre_class(allworks.get(w, {}).get("title", "")) for w in d["comms"])
        out.append((len(d["comms"]), d["label"], len(d["roots"]), sum(1 for w in d["comms"] if w[0] == "T"), sum(1 for w in d["comms"] if w[0] == "X"), g["疏"], g["注"], g["other"], sorted(d["roots"])[:6]))
    out.sort(reverse=True)
    tot = sum(r[0] for r in out)
    print(f"\n## Families (clusters merged on shared root works): {len(out)}; distinct commentaries {tot}")
    cum = 0
    for i, r in enumerate(out[:30], 1):
        cum += r[0]
        print(f"  {i:2d}. {r[1]:40s} roots {r[2]:3d} comm {r[0]:3d} (T {r[3]}, X {r[4]}; 疏 {r[5]}, 注 {r[6]}, other {r[7]}) cum {100*cum/tot:.0f} %  {r[8]}")
    print(f"  families with ≥5 commentaries: {sum(1 for r in out if r[0] >= 5)}; ≥10: {sum(1 for r in out if r[0] >= 10)}; with ≥1 class-疏: {sum(1 for r in out if r[5] > 0)}")
    with open(os.path.join(OUT, "families.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["rank", "label", "n_root", "n_comm", "n_comm_T", "n_comm_X", "n_疏", "n_注", "n_other", "roots_first6"])
        for i, r in enumerate(out, 1):
            wr.writerow([i, r[1], r[2], r[0], r[3], r[4], r[5], r[6], r[7], " ".join(r[8])])
    print("\n## Genre classes by 底本 部 (title rule)")
    for canon, parts in (("T", ["經疏部", "律疏部", "論疏部", "諸宗部"]), ("X", ["大小乘釋經部", "大小乘釋律部", "大小乘釋論部", "諸宗著述部"])):
        for p in parts:
            ws = [w for w, v in part_of.items() if v[0] == canon and v[1] == p]
            c = Counter(genre_class(allworks.get(w, {}).get("title", "")) for w in ws)
            print(f"  {canon} {p}: {len(ws)} works; 疏 {c['疏']}, 注 {c['注']}, other {c['other']}; titles containing 科: {sum(1 for w in ws if '科' in allworks.get(w, {}).get('title', ''))}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "fetch":
        fetch()
    elif cmd == "report":
        report()
    else:
        raise SystemExit(__doc__)
