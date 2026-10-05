#!/usr/bin/env python3
"""Level-1 division announcements in juan 1 of the T 經疏部 (and 律疏部 / 論疏部) works.

Input : out/api/juans_<work>_1.json (cached by census.py fetch), out/api/catalog_orig-T.0NN.json, out/api/all-works.json,
        level1_adjudication.tsv (versioned, next to this script) (work \t adjudicated_N \t note) written by hand after reading the matches
Output: out/level1_matches.tsv   every regex match with 30 chars of context (work, family, N, unit, context)
        out/level1_per_work.tsv  per work: first-match N/unit, tripartite-vocabulary flags, adjudicated N
        stdout                   distribution tables
Text : the juans HTML is reduced to running text by dropping span.lb (line heads), span.lineInfo, a.noteAnchor,
       div.footnote*, a.facsimile and the <head>; CBETA punctuation is kept (span.pc) so the patterns can use 。；：.
Python 3.9 + lxml.
"""
import csv
import json
import os
import re
import sys
from collections import Counter

from lxml import html as lhtml

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
API = os.path.join(OUT, "api")

N = "[一二三四五六七八九十]+"
FAMILY_A = re.compile(
    r"(此經|一經|經文|一部|此論|一論|論文|大文|全經|通經|就文|正文|今文|此品|經)"
    r"[^。；：？！]{0,6}?"
    r"(大分為|分為|開為|判為|略為|略分為|分作|開作|別有|總有|凡有|略有|具有|有|分|開|判)"
    rf"({N})(分|段|門|科|章|節|周|意)")
FAMILY_B = re.compile(rf"(大分為|大分|總分為|大科分|大判|文別有|總有|凡有)({N})(分|段|門|科|章|節)?")
TRI_SEQ = re.compile(r"序[分說]?[、，]?正[宗說]?[分]?[、，]?流通")
NUMVAL = {c: i + 1 for i, c in enumerate("一二三四五六七八九")}
NUMVAL["十"] = 10


def cjk_num(s):
    if s in NUMVAL:
        return NUMVAL[s]
    if s.startswith("十") and len(s) == 2:
        return 10 + NUMVAL[s[1]]
    if s.endswith("十") and len(s) == 2:
        return NUMVAL[s[0]] * 10
    if len(s) == 3 and s[1] == "十":
        return NUMVAL[s[0]] * 10 + NUMVAL[s[2]]
    return None


def juan_text(work, juan=1):
    p = os.path.join(API, f"juans_{work}_{juan}.json")
    if not os.path.exists(p):
        return None
    data = json.load(open(p, encoding="utf-8"))
    res = data.get("results")
    if not res:
        return None
    doc = lhtml.fromstring(res[0])
    for el in doc.xpath('//*[contains(@class,"lb") and not(contains(@class,"lb-"))] | //*[contains(@class,"lineInfo")] | '
                        '//*[contains(@class,"noteAnchor")] | //*[contains(@class,"footnote")] | //*[contains(@class,"facsimile")] | //head'):
        el.drop_tree()
    txt = doc.text_content()
    return re.sub(r"\s+", "", txt)


def works_by_part():
    out = {}
    for i in range(35, 48):
        p = os.path.join(API, f"catalog_orig-T.{i:03d}.json")
        if not os.path.exists(p):
            continue
        part = "經疏部" if i <= 41 else ("律疏部" if i == 42 else "論疏部")
        for r in json.load(open(p, encoding="utf-8"))["results"]:
            if r.get("node_type") == "work":
                out[r["work"]] = (part, r["label"])
    return out


def main():
    titles = {w["work"]: w["title"] for w in json.load(open(os.path.join(API, "all-works.json"), encoding="utf-8"))}
    parts = works_by_part()
    adjud = {}
    ap = os.path.join(HERE, "level1_adjudication.tsv")
    if os.path.exists(ap):
        for row in csv.reader(open(ap, encoding="utf-8"), delimiter="\t"):
            if row and not row[0].startswith("#") and len(row) >= 2:
                adjud[row[0]] = (row[1], row[2] if len(row) > 2 else "")
    per_work = []
    with open(os.path.join(OUT, "level1_matches.tsv"), "w", encoding="utf-8") as mf:
        mf.write("work\tpart\ttitle\tfamily\tN\tunit\tpos\tcontext\n")
        for w in sorted(parts):
            part, label = parts[w]
            txt = juan_text(w)
            if txt is None:
                per_work.append([w, part, titles.get(w, ""), "", "", "", "", "", "", "no-text"])
                continue
            matches = []
            for fam, rx in (("A", FAMILY_A), ("B", FAMILY_B)):
                for m in rx.finditer(txt):
                    n = m.group(3) if fam == "A" else m.group(2)
                    unit = m.group(4) if fam == "A" else (m.group(3) or "")
                    matches.append((m.start(), fam, n, unit, txt[max(0, m.start() - 30):m.end() + 30]))
            matches.sort()
            for pos, fam, n, unit, ctx in matches:
                mf.write(f"{w}\t{part}\t{titles.get(w, '')}\t{fam}\t{n}\t{unit}\t{pos}\t{ctx}\n")
            first = matches[0] if matches else None
            has_tri = int("序分" in txt and ("正宗分" in txt or "正說分" in txt or "正宗" in txt or "正說" in txt) and "流通分" in txt)
            has_tri_seq = int(bool(TRI_SEQ.search(txt)))
            per_work.append([w, part, titles.get(w, ""), len(txt), len(matches),
                             first[2] if first else "", first[3] if first else "", cjk_num(first[2]) if first else "",
                             f"tri={has_tri} seq={has_tri_seq}", adjud.get(w, ("", ""))[0], adjud.get(w, ("", ""))[1]])
    with open(os.path.join(OUT, "level1_per_work.tsv"), "w", encoding="utf-8") as f:
        f.write("work\tpart\ttitle\tjuan1_chars\tn_matches\tfirst_N\tfirst_unit\tfirst_N_int\ttripartite_flags\tadjudicated_N\tadjudication_note\n")
        for r in per_work:
            f.write("\t".join(str(x) for x in r) + "\n")
    # distributions
    for part in ("經疏部", "律疏部", "論疏部"):
        rows = [r for r in per_work if r[1] == part]
        print(f"\n## {part}: {len(rows)} works, juan 1 text available for {sum(1 for r in rows if r[3] != '')}")
        c = Counter((r[7] if r[7] != "" else "none") for r in rows if len(r) > 9)
        print("  first regex match N:", dict(sorted(c.items(), key=lambda kv: (str(kv[0]) == 'none', kv[0] if isinstance(kv[0], int) else 0))))
        tri = Counter(r[8] for r in rows if len(r) > 9)
        print("  tripartite vocabulary (序分∧正宗∧流通分 / 序正流通 sequence):", dict(tri))
        if any(r[9] for r in rows if len(r) > 9):
            ca = Counter((r[9] or "unadjudicated") for r in rows)
            print("  adjudicated level-1 N:", dict(sorted(ca.items(), key=lambda kv: str(kv[0]))))


if __name__ == "__main__":
    main()
