#!/usr/bin/env python3
"""X0231 (華嚴經疏科文) and X0584 (法華三大部科文): true tree depth, leaf counts, leaf classification against the root text.

Input : data/raw/cbeta/X05n0231.xml, T10n0279.xml, T35n1735.xml, X27n0584.xml, T09n0262.xml, T34n1718.xml
        (CBETA xml-p5 tag 2026R2, fetched by scripts/fetch_cbeta.sh; sha256 in scripts/CHECKSUMS)
Output: out/x0231_items.tsv, out/x0584_items.tsv  one row per <item>: xml:id, section, local depth, true depth, is_leaf, is_stub,
                                                   heading, inline note, incipit, class, root-text CJK offset, span marks, span chars
        stdout                                     the numbers quoted in SUMMARY.md

Encoding facts (read off the XML, 2026-09-22):
  * A 科文 node is <item>heading[<note place="inline">X</note>][<list>children</list>]</item>, lists rend="no-marker".
  * The chart is cut into segments: a node whose children are charted later is left as a stub (leaf item, often with a trailing ○
    in X0584, sometimes with a numeral note giving the child count) and the children resume as a new top-level <list> whose first
    item repeats the stub's heading prefixed by ○ (△/▲ in X0231). X0231 has 373 top-level lists (300 ○), X0584 506 (502 ○).
    So the raw XML nesting depth (27 / 29) is the depth *within a segment*; the true depth is recovered by linking each segment
    head to the nearest preceding stub with the same normalised heading.
  * Incipit of a leaf: X0231 — the inline note when it is not a numeral (「初法<note>佛子</note>」); X0584 — the run before 下 in the
    heading (「二文云下正明今經」 → 文云). A numeral note on a leaf = children announced but not charted (count-only stub).
Classification of a leaf with an incipit of ≥ 2 CJK chars, against the root text's running text (lem kept; note/rdg/mulu dropped):
  pass 1  leaves whose incipit occurs 1–3 times in the root text are skeleton candidates; a longest strictly increasing subsequence
          over (document order, text position) picks a consistent monotone skeleton;
  pass 2  every other leaf is searched for its first occurrence between the previous accepted anchor and the next skeleton anchor
          → sutra-span; found in the root text only outside that interval → sutra-elsewhere (treated as not a root-text span);
          not in the root text but in the commentary's running text → commentary-internal; else unresolved.
  Span size of a sutra-span leaf = 。？！； marks in the root text from its anchor to the next accepted anchor (R04 F27 proxy).
Python 3.9 + lxml. Deterministic.
"""
import bisect
import os
import re
import statistics

from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.normpath(os.path.join(HERE, "..", "..", "data", "raw", "cbeta"))
OUT = os.path.join(HERE, "out")
TEI = "{http://www.tei-c.org/ns/1.0}"
CB = "{http://www.cbeta.org/ns/1.0}"
NS = {"t": "http://www.tei-c.org/ns/1.0", "cb": "http://www.cbeta.org/ns/1.0"}
SENT = "。？！；"
NUMERAL = set("一二三四五六七八九十百千")
ORDINAL = "一二三四五六七八九十初次後又第○△▲"
CJK = re.compile(r"[㐀-䶿一-鿿\U00020000-\U0002ffff]")
SEG_MARKS = "○△▲"


def running_text(path):
    tree = etree.parse(path)
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
    punct = re.sub(r"\s+", "", "".join(parts))
    cjk_chars, idx = [], []
    for i, ch in enumerate(punct):
        if CJK.match(ch):
            cjk_chars.append(ch)
            idx.append(i)
    return punct, "".join(cjk_chars), idx


def item_parts(item):
    heading, note, is_leaf = [], None, True
    if item.text:
        heading.append(item.text)
    for c in item:
        if c.tag == TEI + "list":
            is_leaf = False
        elif c.tag == TEI + "note":
            if note is None and c.get("place") == "inline":
                note = "".join(c.itertext())
        elif c.tag != TEI + "g":
            heading.append("".join(c.itertext()))
        if c.tail:
            heading.append(c.tail)
    return re.sub(r"\s+", "", "".join(heading)), (re.sub(r"\s+", "", note) if note is not None else None), is_leaf


def norm_heading(h):
    return h.strip(SEG_MARKS).replace("○", "")


def strip_incipit(h):
    """'二妙法下正釋五重玄義' → '二正釋五重玄義' (drop the incipit run before the first 下 within 7 chars)."""
    m = re.match(rf"^([{ORDINAL}]*)(.{{1,6}}?)下(.*)$", h)
    if m:
        return m.group(1) + m.group(3)
    return h


def incipit_from_heading(h):
    m = re.match(rf"^[{ORDINAL}]*(.{{1,6}}?)下(.+)$", h)
    return m.group(1) if m else None


def parse_chart(path, incipit_mode):
    """Return items (document order) with section, local depth, true depth, stub links."""
    tree = etree.parse(path)
    body = tree.find(".//t:body", NS)
    items = []
    section = ""
    for el in body.iter():
        if el.tag == CB + "mulu" and el.get("type") == "其他":
            section = (el.text or "").strip()
        elif el.tag == TEI + "item":
            h, note, leaf = item_parts(el)
            d = 0
            p = el.getparent()
            while p is not None:
                if p.tag == TEI + "list":
                    d += 1
                p = p.getparent()
            top = el.getparent().getparent().tag != TEI + "item"  # item of a top-level list
            if incipit_mode == "note":
                inc = note if (note is not None and not set(note) <= NUMERAL) else incipit_from_heading(h)
            else:
                inc = incipit_from_heading(h)
            items.append({"id": el.get("{http://www.w3.org/XML/1998/namespace}id"), "section": section, "local": d,
                          "heading": h, "note": note or "", "leaf": leaf, "top": top, "incipit": inc, "true": None,
                          "stub": False, "parent": None})
    # link segments in one document-order pass (a stub always precedes the segment that resumes it): every item of a top-level
    # list is a segment head; its parent is the nearest preceding leaf item whose normalised heading (with or without its incipit)
    # equals the head's normalised heading. True depth: head = parent.true + 1 (or local depth for a genuine root); inside a
    # segment true = head.true + (local − head.local).
    by_norm = {}
    unlinked = 0
    linked = 0
    head = None
    for i, it in enumerate(items):
        if it["top"]:
            key = norm_heading(it["heading"])
            cands = by_norm.get(key, [])
            cands2 = by_norm.get(strip_incipit(key), []) if strip_incipit(key) != key else []
            parent = None
            for lst in (cands, cands2):
                prev = [j for j in lst if j < i and items[j]["leaf"] and not items[j]["stub"]]
                if prev:
                    parent = prev[-1]
                    break
            if parent is not None:
                items[parent]["stub"] = True
                it["parent"] = parent
                it["true"] = items[parent]["true"] + 1
                linked += 1
            else:
                if it["heading"][:1] in SEG_MARKS:
                    unlinked += 1
                it["true"] = it["local"]
            head = it
        else:
            it["true"] = head["true"] + (it["local"] - head["local"])
        h = norm_heading(it["heading"])
        by_norm.setdefault(h, []).append(i)
        hs = strip_incipit(h)
        if hs != h:
            by_norm.setdefault(hs, []).append(i)
    return items, linked, unlinked


def lis_skeleton(cands):
    """cands: list of (leaf_index, [positions]) in document order → set of (leaf_index, pos) forming a longest strictly increasing chain."""
    seq = []  # (pos, leaf_index) — positions per leaf added in decreasing order so at most one per leaf is chosen
    for li, poss in cands:
        for p in sorted(poss, reverse=True):
            seq.append((p, li))
    tails, tails_idx, prev = [], [], [-1] * len(seq)
    for k, (p, li) in enumerate(seq):
        j = bisect.bisect_left(tails, p)
        if j == len(tails):
            tails.append(p)
            tails_idx.append(k)
        else:
            tails[j] = p
            tails_idx[j] = k
        prev[k] = tails_idx[j - 1] if j > 0 else -1
    out = []
    k = tails_idx[-1] if tails_idx else -1
    while k >= 0:
        out.append((seq[k][1], seq[k][0]))
        k = prev[k]
    return dict(reversed(out))


def occurrences(inc, text, cap=100000):
    out = []
    p = text.find(inc)
    while p >= 0 and len(out) < cap:
        out.append(p)
        p = text.find(inc, p + 1)
    return out


def classify(items, sutra, comm, section_filter=None):
    s_punct, s_cjk, s_idx = sutra
    c_cjk = comm[1]
    leaves = [i for i, it in enumerate(items) if it["leaf"] and not it["stub"] and (section_filter is None or it["section"] == section_filter)]
    occ_cache = {}
    for i in leaves:
        it = items[i]
        inc = it["incipit"]
        it["class"] = ""
        if inc is None or inc == "":
            it["class"] = "count-only" if (it["note"] and set(it["note"]) <= NUMERAL) else "no-incipit"
            continue
        inc = "".join(ch for ch in inc if CJK.match(ch))
        it["inc"] = inc
        if len(inc) < 2:
            it["class"] = "unresolved-short"
            continue
        if inc not in occ_cache:
            occ_cache[inc] = occurrences(inc, s_cjk)
    cands = [(i, occ_cache[items[i]["inc"]]) for i in leaves if items[i].get("inc") and 1 <= len(occ_cache.get(items[i]["inc"], [])) <= 3]
    skel = lis_skeleton(cands)
    skel_order = sorted(skel.items())
    skel_leaf_idx = [k for k, _ in skel_order]
    anchors = []
    cursor = 0
    for i in leaves:
        it = items[i]
        if it["class"]:
            continue
        inc = it["inc"]
        if i in skel:
            it["class"] = "sutra-span"
            it["pos"] = skel[i]
            cursor = skel[i]
            anchors.append((i, skel[i]))
            continue
        j = bisect.bisect_right(skel_leaf_idx, i)
        upper = skel_order[j][1] if j < len(skel_order) else len(s_cjk)
        poss = occ_cache[inc]
        k = bisect.bisect_right(poss, cursor) if anchors else bisect.bisect_left(poss, cursor)  # strictly after the last anchor
        if k < len(poss) and poss[k] < upper:
            it["class"] = "sutra-span"
            it["pos"] = poss[k]
            cursor = poss[k]
            anchors.append((i, poss[k]))
        elif poss:
            it["class"] = "sutra-elsewhere" + ("+comm" if inc in c_cjk else "")
        elif inc in c_cjk:
            it["class"] = "commentary-internal"
        else:
            it["class"] = "unresolved"
    sizes, chars = [], []
    for k, (i, p) in enumerate(anchors):
        q = anchors[k + 1][1] if k + 1 < len(anchors) else len(s_cjk)
        a = s_idx[p]
        b = s_idx[q] if q < len(s_idx) else len(s_punct)
        marks = sum(1 for ch in s_punct[a:b] if ch in SENT)
        items[i]["marks"] = marks
        items[i]["chars"] = q - p
        sizes.append(marks)
        chars.append(q - p)
    return leaves, skel, anchors, sizes, chars


def pct(arr, q):
    return arr[min(len(arr) - 1, int(q * len(arr)))]


def summarise(name, items, leaves, skel, anchors, sizes, chars, sutra, first_body_heading=None):
    from collections import Counter
    print(f"\n## {name}")
    cl = Counter(items[i]["class"] for i in leaves)
    print(f"leaves considered {len(leaves)}; classes: {dict(cl.most_common())}")
    print(f"skeleton anchors (rare incipits, LIS) {len(skel)}; accepted sutra-span anchors {len(anchors)}")
    if sizes:
        ss, cs = sorted(sizes), sorted(chars)
        print(f"sutra-span leaf spans: sentence marks median {statistics.median(ss)}, mean {statistics.mean(ss):.2f}, p90 {pct(ss,0.9)}, max {max(ss)}; "
              f"≤6 marks {100*sum(1 for x in ss if x<=6)/len(ss):.1f} %, ≤1 {100*sum(1 for x in ss if x<=1)/len(ss):.1f} %, 0 {100*sum(1 for x in ss if x==0)/len(ss):.1f} %")
        print(f"  CJK chars median {statistics.median(cs)}, mean {statistics.mean(cs):.1f}, p90 {pct(cs,0.9)}, max {max(cs)}")
        by_len = Counter((len(items[i].get("inc", "")), items[i]["class"]) for i in leaves if items[i].get("inc"))
        print("  (incipit length, class) counts:", dict(sorted(by_len.items())))
        s_punct, s_cjk, _ = sutra
        print(f"  root text: {len(s_cjk)} CJK chars, {sum(1 for ch in s_punct if ch in SENT)} sentence marks; first anchor at CJK offset {anchors[0][1]}, last at {anchors[-1][1]}")
        # monotonicity sanity: gaps between consecutive anchors
        gaps = [anchors[k + 1][1] - anchors[k][1] for k in range(len(anchors) - 1)]
        print(f"  anchor gaps: median {statistics.median(gaps)}, p90 {pct(sorted(gaps),0.9)}, max {max(gaps)}; zero-gap (same position) {sum(1 for g in gaps if g == 0)}")
        if first_body_heading is not None:
            print(f"  sutra-span leaves before the item 「{first_body_heading[0]}」 (index {first_body_heading[1]}): {sum(1 for i, _ in anchors if i < first_body_heading[1])}")
        # diagnostics: the 8 largest spans, class mix per document decile, and a fixed sample of sutra-elsewhere leaves
        big = sorted(((items[i]["marks"], i) for i, _ in anchors), reverse=True)[:8]
        print("  largest spans (marks, item index, heading, incipit, next-anchor heading):")
        idx_of = {i: k for k, (i, _) in enumerate(anchors)}
        for m, i in big:
            k = idx_of[i]
            nxt = items[anchors[k + 1][0]]["heading"] + "(" + items[anchors[k + 1][0]].get("inc", "") + ")" if k + 1 < len(anchors) else "END"
            print(f"    {m:5d} #{i} 「{items[i]['heading']}」({items[i].get('inc','')}) → {nxt}")
        n = len(leaves)
        print("  class mix per decile of the leaf sequence (span / elsewhere / comm-internal):")
        for d in range(10):
            seg = leaves[d * n // 10:(d + 1) * n // 10]
            c = Counter(items[i]["class"] for i in seg)
            print(f"    d{d}: {c.get('sutra-span',0)} / {c.get('sutra-elsewhere+comm',0)+c.get('sutra-elsewhere',0)} / {c.get('commentary-internal',0)}")
        ex = [i for i in leaves if items[i]["class"].startswith("sutra-elsewhere")]
        print("  every 250th sutra-elsewhere leaf (heading(incipit)), with its preceding item:")
        for i in ex[::250][:16]:
            print(f"    #{i} 「{items[i]['heading']}」({items[i].get('inc','')})   prev: 「{items[i-1]['heading']}」({items[i-1].get('inc','') or items[i-1]['note']}) [{items[i-1].get('class','')}]")


def depth_report(name, items, linked, unlinked):
    from collections import Counter
    leaves = [it for it in items if it["leaf"] and not it["stub"]]
    stubs = sum(1 for it in items if it["stub"])
    print(f"\n## {name}: items {len(items)}, segments linked {linked}, unlinked ○-heads {unlinked}, stubs {stubs}, "
          f"leaves (non-stub) {len(leaves)}, max local nesting {max(it['local'] for it in items)}, max TRUE depth {max(it['true'] for it in items)}")
    ld = Counter(it["true"] for it in leaves)
    print("  leaf true-depth histogram:", dict(sorted(ld.items())))
    print("  leaf true depth median", statistics.median([it["true"] for it in leaves]))
    for sec in sorted(set(it["section"] for it in items), key=lambda s: [it["section"] for it in items].index(s)):
        si = [it for it in items if it["section"] == sec]
        sl = [it for it in si if it["leaf"] and not it["stub"]]
        print(f"  section 「{sec}」: items {len(si)}, leaves {len(sl)}, max true depth {max(it['true'] for it in si)}")


def write_tsv(path, items):
    with open(path, "w", encoding="utf-8") as f:
        f.write("xml_id\tsection\tlocal_depth\ttrue_depth\tis_leaf\tis_stub\theading\tinline_note\tincipit\tclass\tsutra_cjk_pos\tspan_sent_marks\tspan_cjk_chars\n")
        for it in items:
            f.write("\t".join(str(x) for x in [it["id"], it["section"], it["local"], it["true"], int(it["leaf"]), int(it["stub"]), it["heading"],
                                               it["note"], it.get("inc", it["incipit"] or ""), it.get("class", ""), it.get("pos", ""),
                                               it.get("marks", ""), it.get("chars", "")]) + "\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    # ---------------------------------------------------------------- X0231
    items, linked, unlinked = parse_chart(os.path.join(RAW, "X05n0231.xml"), "note")
    depth_report("X0231 華嚴經疏科文", items, linked, unlinked)
    t0279 = running_text(os.path.join(RAW, "T10n0279.xml"))
    t1735 = running_text(os.path.join(RAW, "T35n1735.xml"))
    body_idx = next(((it["heading"], i) for i, it in enumerate(items) if "釋本文" in it["heading"] or "別解文義" in it["heading"] or "正釋經文" in it["heading"]), None)
    leaves, skel, anchors, sizes, chars = classify(items, t0279, t1735, section_filter="經疏科文")
    summarise("X0231 section 經疏科文 leaves vs T0279 (root) / T1735 (commentary)", items, leaves, skel, anchors, sizes, chars, t0279, body_idx)
    # the 鈔序科文 section is a chart of the 鈔's preface: classify for completeness
    leaves2, skel2, anchors2, sizes2, chars2 = classify(items, t0279, t1735, section_filter="經疏鈔序科文")
    summarise("X0231 section 經疏鈔序科文 (preface chart) vs T0279 / T1735", items, leaves2, skel2, anchors2, sizes2, chars2, t0279)
    write_tsv(os.path.join(OUT, "x0231_items.tsv"), items)
    # ---------------------------------------------------------------- X0584
    yitems, ylinked, yunlinked = parse_chart(os.path.join(RAW, "X27n0584.xml"), "heading")
    depth_report("X0584 法華三大部科文", yitems, ylinked, yunlinked)
    t0262 = running_text(os.path.join(RAW, "T09n0262.xml"))
    t1718 = running_text(os.path.join(RAW, "T34n1718.xml"))
    yl, ys, ya, ysz, ych = classify(yitems, t0262, t1718, section_filter="妙法蓮華經文句科文")
    summarise("X0584 section 妙法蓮華經文句科文 leaves vs T0262 (root) / T1718 (文句)", yitems, yl, ys, ya, ysz, ych, t0262)
    write_tsv(os.path.join(OUT, "x0584_items.tsv"), yitems)


if __name__ == "__main__":
    main()
