#!/usr/bin/env python3
"""scripts/survey_cbeta_xml_p5.py — corpus-wide cb:mulu survey of CBETA xml-p5 and lb/pb cross-release diff.

Input : data/raw/cbeta/xml-p5/        shallow clone of cbeta-org/xml-p5 at tag 2026R2 (scripts/fetch_cbeta_xml_p5.sh)
        data/raw/cbeta/xml-p5-2018/   shallow clone of cbeta-org/xml-p5-2018 (same script), used only by --diff
        data/raw/cbeta-metadata/T.json, X.json, ...   DILA work-info tables (scripts/fetch_cbeta_metadata.sh), optional:
                                      give each file its work id's orig_category (Taishō/Xuzangjing 部) and CBETA 部類
Output: data/raw/cbeta/survey/mulu-survey.tsv        one row per XML file in the 2026R2 clone (all canons)
        data/raw/cbeta/survey/mulu-nodes-kepan.tsv   every cb:mulu node whose @type is 科判, verbatim text, with lb
        data/raw/cbeta/survey/lb-pb-diff-T.tsv       one row per T-canon file present in either clone (--diff)
        data/raw/cbeta/survey/note-app-census-T.tsv  one row per T-canon file: Taishō orig notes vs stand-off app coverage (--census)
        data/raw/cbeta/survey/SUMMARY.txt            the aggregate counts quoted in R02 findings (deterministic)

Rules (recorded here because the findings cite them):
  * "level" = cb:mulu/@level parsed as int; nodes without @level (the 卷 system) are counted separately and never
    contribute to max_level.  "level>=2" counts nodes with an integer @level >= 2.
  * "sūtra file" (T canon) = file whose Taishō number is 0001–1420 (Taishō volumes 1–21, 阿含部 … 密教部);
    "commentary file" = Taishō number 1693–1850 (經疏部 1693–1803, 律疏部 1804–1815, 論疏部 1816–1850).
    The number is parsed from the file name (T09n0262 -> 262; suffix letters such as T0220a are ignored).
    Independently, "orig_category" from DILA's work-info table is reported per file (work id = canon + 4-digit number
    + suffix, so T05n0220/T06n0220/T07n0220 -> T0220), and the summary cross-tabulates both rules.
  * Note/app census: an "orig note id" is note[@type='orig']/@n; it "has an app" when some app/@from equals
    "#beg"+id or app/@n equals id (both anchoring styles occur); "residue" = orig ids with no app.
  * For the lb/pb diff, the lb set is the set of distinct lb/@n whose @ed contains the token "T" (the file's own
    canon), and the pb set is the set of (pb/@n, pb/@xml:id) pairs with the same @ed rule; lb with type="old" are
    excluded (CBETA's converters skip them).  A file is "identical" when both sets are equal.

Only the standard library plus lxml.  Deterministic: re-running rewrites byte-identical outputs.
"""
import os
import re
import sys
from collections import Counter

from lxml import etree

TEI = "http://www.tei-c.org/ns/1.0"
CB = "http://www.cbeta.org/ns/1.0"
XMLNS = "http://www.w3.org/XML/1998/namespace"
T = "{%s}" % TEI
C = "{%s}" % CB

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NEW = os.path.join(ROOT, "data/raw/cbeta/xml-p5")
OLD = os.path.join(ROOT, "data/raw/cbeta/xml-p5-2018")
OUT = os.path.join(ROOT, "data/raw/cbeta/survey")

NUM_RE = re.compile(r"^([A-Z]+)(\d+)n([A-Za-z]?\d+)([A-Za-z]?)$")


def xml_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        if os.path.basename(dirpath) == "schema":
            continue
        for fn in filenames:
            if fn.endswith(".xml"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def parse_name(path):
    base = os.path.basename(path)[:-4]
    m = NUM_RE.match(base)
    if not m:
        return base, None, None, None
    canon, vol, num, suffix = m.groups()
    numd = re.sub(r"^[A-Za-z]", "", num)
    return base, canon, int(vol), int(numd) if numd.isdigit() else None


def load_work_info():
    """{work_id: (orig_category, category, title)} from data/raw/cbeta-metadata/<canon>.json, if present."""
    import json
    d = os.path.join(ROOT, "data/raw/cbeta-metadata")
    info = {}
    if not os.path.isdir(d):
        return info
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".json"):
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    info[k] = (v.get("orig_category") or "", v.get("category") or "", v.get("title") or "")
    return info


def work_id(base):
    m = NUM_RE.match(base)
    if not m:
        return base
    canon, vol, num, suffix = m.groups()
    numd = re.sub(r"^[A-Za-z]", "", num)
    letter = num[0] if not num[0].isdigit() else ""
    return "%s%s%s%s" % (canon, letter, numd.zfill(4), suffix)


SUTRA_ORIG = ("阿含部", "本緣部", "般若部", "法華部", "華嚴部", "寶積部", "涅槃部", "大集部", "經集部", "密教部")
COMMENTARY_ORIG = ("經疏部", "律疏部", "論疏部")


def t_class(canon, num):
    if canon != "T" or num is None:
        return ""
    if 1 <= num <= 1420:
        return "sutra"
    if 1693 <= num <= 1850:
        return "commentary"
    return "other"


def prev_lb(el):
    """@n of the nearest preceding lb in document order (within the file)."""
    for p in el.iter_ancestors() if hasattr(el, "iter_ancestors") else []:
        pass
    node = el
    while node is not None:
        prev = node.getprevious()
        while prev is not None:
            if prev.tag == T + "lb":
                return prev.get("n")
            found = None
            for d in prev.iter(T + "lb"):
                found = d
            if found is not None:
                return found.get("n")
            prev = prev.getprevious()
        node = node.getparent()
    return ""


def survey():
    os.makedirs(OUT, exist_ok=True)
    files = xml_files(NEW)
    info = load_work_info()
    rows = []
    kepan_nodes = []
    for i, path in enumerate(files):
        base, canon, vol, num = parse_name(path)
        try:
            tree = etree.parse(path)
        except etree.XMLSyntaxError as e:  # record and continue
            rows.append([base, canon or "", str(vol or ""), str(num or ""), t_class(canon, num), "PARSE-ERROR:%s" % e] + [""] * 15)
            continue
        root = tree.getroot()
        title_el = root.find(".//%stitleStmt/%stitle[@level='m']" % (T, T))
        title = (title_el.text or "").strip() if title_el is not None else ""
        hdate_el = root.find(".//%spublicationStmt/%sdate" % (T, T))
        hdate = (hdate_el.text or "").strip()[:10] if hdate_el is not None else ""
        mulus = list(root.iter(C + "mulu"))
        types = Counter()
        max_level_by_type = {}
        n_level = Counter()
        n_nolevel = 0
        max_level = 0
        for m in mulus:
            ty = m.get("type") or "(untyped)"
            types[ty] += 1
            lv = m.get("level")
            if lv is None or not lv.isdigit():
                n_nolevel += 1
                continue
            lv = int(lv)
            n_level[lv] += 1
            max_level = max(max_level, lv)
            max_level_by_type[ty] = max(max_level_by_type.get(ty, 0), lv)
            if ty == "科判":
                kepan_nodes.append([base, m.get("level") or "", m.get("n") or "", prev_lb(m),
                                    " ".join((m.text or "").split())])
        n_ge2 = sum(v for k, v in n_level.items() if k >= 2)
        div_types = Counter((d.get("type") or "(untyped)") for d in root.iter(C + "div"))
        n_juan = len(root.findall(".//%smilestone[@unit='juan']" % T))
        n_lb = sum(1 for _ in root.iter(T + "lb"))
        n_pb = sum(1 for _ in root.iter(T + "pb"))
        wid = work_id(base)
        oc, cc, _t = info.get(wid, ("", "", ""))
        rows.append([
            base, canon or "", str(vol or ""), str(num or ""), t_class(canon, num), title, hdate,
            str(len(mulus)), str(n_nolevel), str(max_level), str(n_ge2),
            ";".join("%s:%d" % (k, v) for k, v in sorted(types.items())),
            ";".join("%s:%d" % (k, v) for k, v in sorted(max_level_by_type.items())),
            ";".join("L%d:%d" % (k, v) for k, v in sorted(n_level.items())),
            str(types.get("科判", 0)), str(types.get("分", 0)),
            ";".join("%s:%d" % (k, v) for k, v in sorted(div_types.items())),
            str(n_juan), str(n_lb), str(n_pb), wid, oc, cc,
        ])
        if (i + 1) % 500 == 0:
            print("  surveyed %d/%d" % (i + 1, len(files)), file=sys.stderr)
    header = ["file", "canon", "vol", "num", "t_class", "title", "header_date", "n_mulu", "n_mulu_nolevel",
              "max_level", "n_level_ge2", "types", "max_level_by_type", "nodes_per_level", "n_kepan", "n_fen",
              "div_types", "n_juan_milestones", "n_lb", "n_pb", "work_id", "orig_category", "category"]
    with open(os.path.join(OUT, "mulu-survey.tsv"), "w", encoding="utf-8") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    with open(os.path.join(OUT, "mulu-nodes-kepan.tsv"), "w", encoding="utf-8") as f:
        f.write("file\tlevel\tn\tprev_lb\ttext\n")
        for r in kepan_nodes:
            f.write("\t".join(r) + "\n")
    return rows, kepan_nodes


def lb_pb_sets(path, canon):
    root = etree.parse(path).getroot()
    lbs = set()
    lb_all = 0
    for lb in root.iter(T + "lb"):
        lb_all += 1
        if lb.get("type") == "old":
            continue
        ed = (lb.get("ed") or "").split()
        if canon in ed:
            lbs.add(lb.get("n") or "")
    pbs = set()
    for pb in root.iter(T + "pb"):
        ed = (pb.get("ed") or "").split()
        if canon in ed:
            pbs.add((pb.get("n") or "", pb.get(("{%s}" % XMLNS) + "id") or ""))
    return lbs, pbs, lb_all


def diff():
    os.makedirs(OUT, exist_ok=True)
    new = {os.path.basename(p): p for p in xml_files(os.path.join(NEW, "T"))}
    old = {os.path.basename(p): p for p in xml_files(os.path.join(OLD, "T"))}
    names = sorted(set(new) | set(old))
    rows = []
    for i, name in enumerate(names):
        base = name[:-4]
        if name in new and name in old:
            ln, pn, an = lb_pb_sets(new[name], "T")
            lo, po, ao = lb_pb_sets(old[name], "T")
            only_new = sorted(ln - lo)
            only_old = sorted(lo - ln)
            pb_same = pn == po
            status = "identical" if (not only_new and not only_old and pb_same) else "differs"
            rows.append([base, "both", status, str(len(lo)), str(len(ln)), str(ao), str(an),
                         str(len(only_old)), str(len(only_new)),
                         ",".join(only_old[:8]), ",".join(only_new[:8]),
                         "same" if pb_same else "differs:%d/%d" % (len(po - pn), len(pn - po))])
        elif name in new:
            rows.append([base, "2026R2-only", "", "", "", "", "", "", "", "", "", ""])
        else:
            rows.append([base, "2018-only", "", "", "", "", "", "", "", "", "", ""])
        if (i + 1) % 500 == 0:
            print("  diffed %d/%d" % (i + 1, len(names)), file=sys.stderr)
    header = ["file", "presence", "status", "lb_n_2018", "lb_n_2026R2", "lb_elements_2018", "lb_elements_2026R2",
              "n_only_2018", "n_only_2026R2", "only_2018_sample", "only_2026R2_sample", "pb_set"]
    with open(os.path.join(OUT, "lb-pb-diff-T.tsv"), "w", encoding="utf-8") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    return rows


def census():
    """T-canon census of Taishō footnotes (note type=orig) against the stand-off apparatus (app)."""
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for path in xml_files(os.path.join(NEW, "T")):
        root = etree.parse(path).getroot()
        orig = [n for n in root.iter(T + "note") if n.get("type") == "orig"]
        orig_ids = set(n.get("n") for n in orig if n.get("n"))
        apps = list(root.iter(T + "app"))
        app_ids = set()
        for a in apps:
            f = a.get("from")
            if f and f.startswith("#beg"):
                app_ids.add(f[4:])
            if a.get("n"):
                app_ids.add(a.get("n"))
        wits = [w.text for w in root.iter(T + "witness")]
        back_app = root.find(".//%sback//%sdiv[@type='apparatus']" % (T, C))
        # residue classification by Taishō footnote syntax: a variant note carries ＝ / ＋ / － / 〔 / 【sigla】;
        # a note with Latin script and none of those is a Sanskrit/Pāli gloss or parallel reference.
        seen = set()
        res_sig = res_lat = res_other = 0
        for n in orig:
            nid = n.get("n")
            if not nid or nid in app_ids or nid in seen:
                continue
            seen.add(nid)
            txt = "".join(n.itertext())
            if re.search(r"[＝＋－〔【]", txt):
                res_sig += 1
            elif re.search(r"[A-Za-z]", txt):
                res_lat += 1
            else:
                res_other += 1
        rows.append([os.path.basename(path)[:-4], len(orig), len(orig_ids), len(apps), len(orig_ids & app_ids),
                     len(orig_ids - app_ids), len(wits), back_app is not None, res_sig, res_lat, res_other])
    with open(os.path.join(OUT, "note-app-census-T.tsv"), "w", encoding="utf-8") as f:
        f.write("file\torig_note_elements\torig_note_ids\tapp_elements\torig_ids_with_app\torig_ids_without_app\tn_witness\thas_back_apparatus\tresidue_variant_syntax\tresidue_latin_gloss\tresidue_other\n")
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")
    return rows


def summarize(rows, kepan_nodes, diff_rows, census_rows):
    out = []
    ok = [r for r in rows if not r[5].startswith("PARSE-ERROR")]
    out.append("files surveyed: %d (parse errors: %d)" % (len(rows), len(rows) - len(ok)))
    by_canon = Counter(r[1] for r in ok)
    out.append("files per canon: " + ", ".join("%s=%d" % kv for kv in sorted(by_canon.items())))
    with_kepan = [r for r in ok if int(r[14]) > 0]
    out.append("files with cb:mulu type=科判: %d -> %s" % (len(with_kepan), ", ".join("%s(%s)" % (r[0], r[14]) for r in with_kepan)))
    out.append("科判 nodes total: %d" % len(kepan_nodes))
    with_fen = [r for r in ok if int(r[15]) > 0]
    out.append("files with cb:mulu type=分: %d" % len(with_fen))
    for cls in ("sutra", "commentary", "other"):
        n = [r for r in with_fen if r[4] == cls]
        out.append("  T %s files with type=分: %d -> %s" % (cls, len(n), ", ".join("%s(%s)" % (r[0], r[15]) for r in n)))
    nonT = [r for r in with_fen if r[1] != "T"]
    out.append("  non-T files with type=分: %d" % len(nonT))
    # type vocabulary corpus-wide
    tv = Counter()
    for r in ok:
        for kv in r[11].split(";"):
            if kv:
                k, v = kv.rsplit(":", 1)
                tv[k] += int(v)
    out.append("cb:mulu @type vocabulary (nodes): " + ", ".join("%s=%d" % kv for kv in tv.most_common()))
    fv = Counter()
    for r in ok:
        for kv in r[11].split(";"):
            if kv:
                fv[kv.rsplit(":", 1)[0]] += 1
    out.append("cb:mulu @type vocabulary (files): " + ", ".join("%s=%d" % kv for kv in fv.most_common()))
    ml = Counter(int(r[9]) for r in ok)
    out.append("max_level distribution (files): " + ", ".join("L%d=%d" % kv for kv in sorted(ml.items())))
    tfiles = [r for r in ok if r[1] == "T"]
    out.append("T files: %d; T files with any level>=2 node: %d; T files with max_level>=3: %d" % (
        len(tfiles), sum(1 for r in tfiles if int(r[10]) > 0), sum(1 for r in tfiles if int(r[9]) >= 3)))
    for cls in ("sutra", "commentary", "other"):
        c = [r for r in tfiles if r[4] == cls]
        out.append("  T %s: %d files; with level>=2: %d; max_level>=3: %d; deepest: %s" % (
            cls, len(c), sum(1 for r in c if int(r[10]) > 0), sum(1 for r in c if int(r[9]) >= 3),
            ", ".join("%s(L%s,%s nodes)" % (r[0], r[9], r[7]) for r in sorted(c, key=lambda r: -int(r[9]))[:8])))
    comm = sorted([r for r in tfiles if r[4] == "commentary" and int(r[10]) > 0], key=lambda r: r[0])
    out.append("T commentaries (1693-1850) with level>=2 mulu nodes: %d" % len(comm))
    for r in comm:
        out.append("  %s\t%s\tmax_level=%s\tn_mulu=%s\tlevel>=2=%s\ttypes=%s" % (r[0], r[5], r[9], r[7], r[10], r[11]))
    xfiles = [r for r in ok if r[1] == "X"]
    xdeep = sorted([r for r in xfiles if int(r[10]) > 0], key=lambda r: -int(r[9]))
    out.append("X files: %d; with level>=2: %d; max_level>=3: %d" % (len(xfiles), len(xdeep), sum(1 for r in xfiles if int(r[9]) >= 3)))
    out.append("  X deepest 15: " + ", ".join("%s %s(L%s,%s)" % (r[0], r[5], r[9], r[7]) for r in xdeep[:15]))
    # cross-check the number rule against DILA orig_category (work-info), when present
    if any(r[21] for r in tfiles):
        oc_sutra = [r for r in tfiles if r[21] in SUTRA_ORIG]
        oc_comm = [r for r in tfiles if r[21] in COMMENTARY_ORIG]
        out.append("DILA orig_category cross-check: T files with orig_category in %s: %d (number rule 'sutra': %d; both: %d); "
                   "orig_category in %s: %d (number rule 'commentary': %d; both: %d)" % (
                       "/".join(SUTRA_ORIG), len(oc_sutra), len([r for r in tfiles if r[4] == "sutra"]),
                       len([r for r in oc_sutra if r[4] == "sutra"]), "/".join(COMMENTARY_ORIG), len(oc_comm),
                       len([r for r in tfiles if r[4] == "commentary"]), len([r for r in oc_comm if r[4] == "commentary"])))
        out.append("  T files with orig_category in sutra 部 carrying type=分: %d -> %s" % (
            len([r for r in oc_sutra if int(r[15]) > 0]), ", ".join("%s[%s](%s)" % (r[0], r[21], r[15]) for r in oc_sutra if int(r[15]) > 0)))
        out.append("  T files with orig_category in sutra 部 with level>=2: %d; max_level>=3: %d" % (
            len([r for r in oc_sutra if int(r[10]) > 0]), len([r for r in oc_sutra if int(r[9]) >= 3])))
        out.append("  T orig_category values among files with level>=2: " + ", ".join(
            "%s=%d" % kv for kv in Counter(r[21] for r in tfiles if int(r[10]) > 0).most_common()))
        xc = [r for r in xfiles if int(r[10]) > 0]
        out.append("  X orig_category values among files with level>=2: " + ", ".join(
            "%s=%d" % kv for kv in Counter(r[21] for r in xc).most_common()))
        xcomm = sorted([r for r in xc if "疏" in r[21] or "釋經" in r[21] or "釋論" in r[21] or "釋律" in r[21]], key=lambda r: (-int(r[9]), r[0]))
        out.append("  X commentary files (orig_category contains 疏/釋經/釋論/釋律) with level>=2: %d; max_level>=3: %d; top 25 by depth:" % (
            len(xcomm), len([r for r in xcomm if int(r[9]) >= 3])))
        for r in xcomm[:25]:
            out.append("    %s\t%s\t[%s]\tmax_level=%s\tn_mulu=%s\tlevel>=2=%s\ttypes=%s" % (r[0], r[5], r[21], r[9], r[7], r[10], r[11]))
    untyped = [r for r in ok if "(untyped)" in r[11]]
    out.append("files with untyped cb:mulu nodes: %d" % len(untyped))
    if diff_rows:
        both = [r for r in diff_rows if r[1] == "both"]
        ident = [r for r in both if r[2] == "identical"]
        out.append("lb/pb diff T canon: files in both=%d identical=%d differs=%d; 2018-only=%d; 2026R2-only=%d" % (
            len(both), len(ident), len(both) - len(ident),
            sum(1 for r in diff_rows if r[1] == "2018-only"), sum(1 for r in diff_rows if r[1] == "2026R2-only")))
        d = [r for r in both if r[2] == "differs"]
        out.append("  differing files: " + ", ".join("%s(-%s/+%s,pb %s)" % (r[0], r[7], r[8], r[11]) for r in d))
        out.append("  2018-only: " + ", ".join(r[0] for r in diff_rows if r[1] == "2018-only"))
        out.append("  2026R2-only: " + ", ".join(r[0] for r in diff_rows if r[1] == "2026R2-only"))
    if census_rows:
        n = len(census_rows)
        tot_ids = sum(r[2] for r in census_rows); tot_with = sum(r[4] for r in census_rows)
        withids = [r for r in census_rows if r[2] > 0]
        res = sorted(r[5] / r[2] for r in withids)
        out.append("note/app census T canon: files=%d; with >=1 orig note=%d; with >=1 app=%d; with back apparatus div=%d; "
                   "orig-note ids=%d, with app=%d (%.2f%%), without=%d; orig-note elements=%d; app elements=%d" % (
                       n, len(withids), sum(1 for r in census_rows if r[3] > 0), sum(1 for r in census_rows if r[7]),
                       tot_ids, tot_with, 100.0 * tot_with / tot_ids, tot_ids - tot_with,
                       sum(r[1] for r in census_rows), sum(r[3] for r in census_rows)))
        out.append("  per-file residue (files with orig ids): median=%.3f; files with residue 0=%d, >=25%%=%d, >=50%%=%d, =100%%=%d; "
                   "files with orig ids but no app=%d; files whose listWit is only 【CB】【大】=%d" % (
                       res[len(res) // 2], sum(1 for v in res if v == 0), sum(1 for v in res if v >= 0.25),
                       sum(1 for v in res if v >= 0.5), sum(1 for v in res if v == 1.0),
                       sum(1 for r in withids if r[3] == 0), sum(1 for r in census_rows if r[6] == 2)))
        out.append("  residue by footnote syntax: variant-like (＝/＋/－/〔/【)=%d, Latin-script gloss or parallel ref=%d, other=%d" % (
            sum(r[8] for r in census_rows), sum(r[9] for r in census_rows), sum(r[10] for r in census_rows)))
        vb = sorted(census_rows, key=lambda r: -r[8])[:8]
        out.append("  files with most variant-like residue: " + ", ".join("%s(%d of %d residue)" % (r[0], r[8], r[5]) for r in vb))
        big = sorted(census_rows, key=lambda r: -r[5])[:8]
        out.append("  largest absolute residue: " + ", ".join("%s(%d of %d)" % (r[0], r[5], r[2]) for r in big))
    text = "\n".join(out) + "\n"
    with open(os.path.join(OUT, "SUMMARY.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    do_diff = "--diff" in sys.argv or "--all" in sys.argv
    do_census = "--census" in sys.argv or "--all" in sys.argv
    do_survey = "--survey" in sys.argv or "--all" in sys.argv or not (do_diff or do_census)
    rows, kepan_nodes = survey() if do_survey else ([], [])
    diff_rows = diff() if do_diff else []
    census_rows = census() if do_census else []
    if do_survey:
        summarize(rows, kepan_nodes, diff_rows, census_rows)
