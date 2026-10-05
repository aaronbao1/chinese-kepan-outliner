#!/usr/bin/env python3
"""Re-check every primary-text quote in R01 findings.md character-for-character.

Input : the QUOTES table below (quote as written in context/research/R01-*/findings.md, work, juan);
        data/raw/cbeta/<file>.xml for works on disk (running text with CBETA punctuation: lem kept, rdg/note dropped);
        out/api/juans_<work>_<juan>.json for the rest (fetched by census.py fetch).
Output: stdout: EXACT (found verbatim), PUNCT (found ignoring punctuation/brackets, with the source's own punctuation shown),
        NEAR (best fuzzy window shown), MISSING.
Python 3.9 + lxml.
"""
import difflib
import json
import os
import re

from lxml import etree
from lxml import html as lhtml

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.normpath(os.path.join(HERE, "..", "..", "data", "raw", "cbeta"))
API = os.path.join(HERE, "out", "api")
NS = {"t": "http://www.tei-c.org/ns/1.0", "cb": "http://www.cbeta.org/ns/1.0"}
TEI = "{http://www.tei-c.org/ns/1.0}"
CB = "{http://www.cbeta.org/ns/1.0}"
LOCAL = {"T1718": "T34n1718.xml", "T1721": "T34n1721.xml", "T1723": "T34n1723.xml", "T1735": "T35n1735.xml",
         "X0231": "X05n0231.xml", "T0235": "T08n0235.xml", "T0279": "T10n0279.xml", "T1724": "T34n1724.xml"}

# (quote as in findings.md, work, juan, where in findings.md)
QUOTES = [
    ("然諸佛說經本無章段", "T1707", 1, "F1"),
    ("河西道朗開此經為五門", "T1721", 1, "F1"),
    ("龍光法師開此經為二段", "T1721", 1, "F1"),
    ("說有五分。云何為五？一者、因緣分，二者、立義分", "T1666", 1, "F1/F13/formula table"),
    ("經無大小例開三段，序、正、流通", "T1721", 1, "F2"),
    ("彌天高判，冥符西域，今古同遵", "T1735", 1, "F2"),
    ("始自道安法師分經以為三段", "T1707", 1, "F2"),
    ("總有三分：一、教起因緣分；二、聖教所說分", "T1530", 1, "F2/formula table"),
    ("此經始終文別有五：一者序分、二『純陀』下開宗顯德分", "T1764", 1, "F2/formula table"),
    ("此經所明，凡有三段：始於序品，訖安樂行", "X0577", 1, "F2/formula table"),
    ("從序至〈安樂行〉十四品，約迹開權顯實", "T1718", 1, "F2"),
    ("凡十五品半，名正；從偈後盡經，凡十一品半，名流通", "T1718", 1, "F5"),
    ("夫分節經文悉是人情，蘭菊各擅其美", "T1718", 1, "F5"),
    ("古講師但敷弘義理、不分章段", "T1718", 1, "F8"),
    ("今帖文為四：一、列數；二、所以；三、引證；四、示相", "T1718", 1, "formula table"),
    ("又一時分為二：從序至安樂行十四品", "T1718", 1, "formula table"),
    ("就中又二，初眾集威儀", "T1718", 2, "formula table"),
    ("就無學眾開文為六：一、標通號；二、唱數", "T1721", 1, "formula table"),
    ("破疑執中有二：一破疑，二破執", "T1723", 1, "formula table"),
    ("初中亦二", "T1735", 5, "formula table"),
    ("二「海月」下，十異名菩薩", "T1735", 5, "formula table"),
    ("初歡喜地，文有八分", "T1735", 31, "formula table"),
    ("二歎德中，有二十句，初二略明、後二總結、中間廣歎", "T1735", 31, "formula table / F6"),
    ("大分為四", "T1736", 1, "formula table (search-stage summary)"),
    ("從日觀初句", "T1753", 2, "formula table (span start)"),
    ("至下品下生已來明正宗分", "T1753", 2, "formula table (span end)"),
    ("釋斯鈔序啟以三門三初題目大方次撰人清涼後本文", "X0231", 1, "formula table"),
    ("嗢拕南曰：五識相應、意、有尋伺等三", "T1579", 1, "formula table / F13"),
    ("餘之別名，可隨義釋", "T1735", 31, "F6 caveat"),
    ("肇曰", "T1775", 1, "F12 (gloss marker)"),
    ("什曰", "T1775", 1, "F12 (gloss marker)"),
    ("攝頌", "T0026", 1, "F1/F13 (term presence)"),
]

PUNCT = re.compile(r"[，。、；：？！「」『』〈〉《》（）\(\)\[\]【】…‧·\s]")


def local_text(work):
    tree = etree.parse(os.path.join(RAW, LOCAL[work]))
    body = tree.find(".//t:body", NS)
    drop = {TEI + "note", TEI + "rdg", CB + "mulu", CB + "juan", CB + "jhead"}
    parts = []

    def rec(e):
        if e.tag in drop:
            return
        if e.text:
            parts.append(e.text)
        for c in e:
            rec(c)
            if c.tail:
                parts.append(c.tail)

    rec(body)
    return re.sub(r"\s+", "", "".join(parts))


def api_text(work, juan):
    p = os.path.join(API, f"juans_{work}_{juan}.json")
    if not os.path.exists(p):
        return None
    res = json.load(open(p, encoding="utf-8")).get("results")
    if not res:
        return None
    doc = lhtml.fromstring(res[0])
    for el in doc.xpath('//*[contains(@class,"lb") and not(contains(@class,"lb-"))] | //*[contains(@class,"lineInfo")] | '
                        '//*[contains(@class,"noteAnchor")] | //*[contains(@class,"footnote")] | //*[contains(@class,"facsimile")] | //head'):
        el.drop_tree()
    return re.sub(r"\s+", "", doc.text_content())


def main():
    cache = {}
    for quote, work, juan, where in QUOTES:
        key = (work, "local" if work in LOCAL else juan)
        if key not in cache:
            cache[key] = local_text(work) if work in LOCAL else api_text(work, juan)
        txt = cache[key]
        src = "local XML" if work in LOCAL else f"API juans {work}/{juan}"
        if txt is None:
            print(f"NO-TEXT   {work}/{juan} [{where}] 「{quote}」 ({src} not on disk)")
            continue
        if quote in txt:
            i = txt.find(quote)
            print(f"EXACT     {work}/{juan} [{where}] 「{quote}」 ×{txt.count(quote)} ({src}); context …{txt[max(0,i-12):i]}[{quote}]{txt[i+len(quote):i+len(quote)+12]}…")
            continue
        q0 = PUNCT.sub("", quote)
        t0 = PUNCT.sub("", txt)
        if q0 in t0:
            # recover the source's own punctuation for the span
            pos = t0.find(q0)
            # map back: walk txt counting non-punct chars
            k = 0
            start = None
            for i, ch in enumerate(txt):
                if PUNCT.match(ch):
                    continue
                if k == pos:
                    start = i
                if k == pos + len(q0) - 1:
                    end = i + 1
                    break
                k += 1
            print(f"PUNCT     {work}/{juan} [{where}] 「{quote}」 → source reads 「{txt[start:end]}」 ({src}; ×{t0.count(q0)})")
            continue
        # fuzzy: best window
        best = (0, "")
        w = len(q0)
        step = max(1, w // 4)
        for i in range(0, max(1, len(t0) - w), step):
            r = difflib.SequenceMatcher(None, q0, t0[i:i + w + 4]).ratio()
            if r > best[0]:
                best = (r, t0[i:i + w + 4])
        print(f"NEAR      {work}/{juan} [{where}] 「{quote}」 not found; best window (ratio {best[0]:.2f}) 「{best[1]}」 ({src})")


if __name__ == "__main__":
    main()
