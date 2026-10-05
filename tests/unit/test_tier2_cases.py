"""Tier-2 detectors against the labelled parser cases (tests/fixtures/kepan-formulae/cases.jsonl).

Scoring (per case; the labels are a machine draft not yet reviewed by Aaron, so floors, not 100 %):
  * division with a child count: the first accepted announcement / gate / uddāna of
    chinese_workflow.outline.tier2.detect(text) has the expected child_count and labels (label rule of
    the cases README), the expected anaphor after it (今初 / 此初 …), and, for `applies_to` [1], the
    target hint 'index:1';
  * division with a heading (an entry marker: 二「海月」下，十異名菩薩 / 第二聖 / 下二天 / 次說立義分): the
    first non-anaphor entry marker has the expected heading, ordinal and lemma;
  * not-division: no accepted announcement;
  * genre-gate (T1775 注維摩詰經): no accepted announcement and no accepted entry marker, with the work
    title read from the raw XML when present (the genre gate), else from the filter alone;
  * chart-note (X0231, X0584 科文): scored only when the raw XML is present, because a chart needs the
    inline-note markup and line breaks that the case text drops; the lines are rebuilt from the file.
  * lemma-zhe (Zhiyi's 「X」者, E06 review B6): a heading case checks the first lemma_zhe entry's heading
    and lemma; a listing case (child_count given) runs parse() on the text and checks the labels as
    listed-only children taken up by the later gloss; a negative checks that no lemma_zhe entry is live
    (not emitted, or emitted with accepted False for a title word).

Achieved on 2026-09-27 (Claude Opus 5.5) and extended 2026-10-02 (T6: pos-uddana-04, lun-zhe-wei-ru-you-yi-01/02;
T11: you-n-takeup-01..03, neg-you-n-takeup-01, you-n-deferred-01/02; T7: pos-cong-xia-zhi-fen-04; T8: the 善導
idioms jiu-x-zhong ×11, cong-xia-zhi-lai ×3, ming-x-jing ×3, and pos-you-n-05, the in-sentence 即有其七 first filed under
jiu-x-zhong; T10: lemma-zhe ×7), which the floors below assert: all 148 cases with
data/raw/ present: 148/148 — division 112/112, not-division 28/28, close 3/3, genre-gate 5/5; every formula slug
100 % (chart-note 3/3). Without data/raw/: the 3 chart cases are skipped and the gate cases are scored by the filter
alone: 145/145. A case may carry "mode": "self-outlining" (T1666 cases); score() runs the detectors in that mode. A
`close` case needs a closing statement naming X; a not-division case of jiu-x-zhong must also open no 就X中 node.
Run: cd pipeline && .venv/bin/python -m pytest ../tests/unit/test_tier2_cases.py -q
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

from chinese_workflow.common.outline_doc import build_prediction, validate
from chinese_workflow.common.paths import cbeta_xml_path
from chinese_workflow.ingest.lines import build_index
from chinese_workflow.ingest.text import InputText, load_input_text
from chinese_workflow.outline.tier2 import detect, parse
from chinese_workflow.outline.tier2 import parser as tier2_parser
from chinese_workflow.outline.tier2.filters import genre_gate
from chinese_workflow.outline.tier2.formulae import parse_num
from chinese_workflow.outline.tier2.labels import clean_label, parse_listing, uddana_count, uddana_listing
from chinese_workflow.outline.tier2.parser import REDIVISION_RE, sim

REPO = Path(__file__).resolve().parents[2]
CASES = [json.loads(line) for line in
         (REPO / "tests" / "fixtures" / "kepan-formulae" / "cases.jsonl").read_text("utf-8").splitlines()
         if line.strip()]

# floors = what the parser reaches (module docstring); a regression fails the test
FLOOR_ALL = {"division": 112, "not-division": 28, "genre-gate": 5, "close": 3}
FLOOR_NO_RAW = {"division": 109, "not-division": 28, "genre-gate": 5, "close": 3}
SELF_OUTLINING_SLUGS = {"lun-zhe-wei-ru-you-yi"}  # formulas detected in self-outlining mode only
# a not-division case of these formulae must also open no node of the named entry kind
ENTER_FORMULAS = {"jiu-x-zhong": "jiu_zhong"}


# ------------------------------------------------------------------------------------ helpers


def _file_id(case: dict) -> str:
    return case["linehead"].split("_p", 1)[0]


def _title(case: dict) -> str | None:
    fid = _file_id(case)
    if cbeta_xml_path(fid) is None:
        return None
    return load_input_text(fid).info.get("title") or None


def _chart_markup(case: dict):
    """(lines, notes) of a chart case rebuilt from the raw file: the case text is the concatenation of
    consecutive lines from its linehead."""
    fid = _file_id(case)
    if cbeta_xml_path(fid) is None:
        return None
    t = load_input_text(fid)
    i = t.all_lineheads.index(case["linehead"])
    j = i
    while j < len(t.all_lineheads) and len("".join(
            t.index.line_text(lh) for lh in t.all_lineheads[i:j + 1])) < len(case["text"]):
        j += 1
    span = load_input_text(fid, span=(t.all_lineheads[i], t.all_lineheads[j]))
    if span.text != case["text"]:
        return None
    lines = [(span.index.starts[k], span.index.starts[k] + span.index.lengths[k], lh)
             for k, lh in enumerate(span.index.lineheads)]
    notes = [(span.index.starts[k] + a, span.index.starts[k] + b)
             for k, rec in enumerate(span.lines) for a, b in rec["inline_notes"]]
    return lines, notes


def score(case: dict) -> tuple:
    """(scored, ok, why)."""
    exp = case["expected"]
    kw: dict = {}
    if case["formula"] in SELF_OUTLINING_SLUGS:
        kw["mode"] = "self-outlining"
    if case["formula"] == "chart-note":
        markup = _chart_markup(case)
        if markup is None:
            return False, False, "chart case needs data/raw/"
        kw["lines"], kw["notes"] = markup
    if case["kind"] == "genre-gate":
        kw["title"] = _title(case)
    if case.get("mode"):
        kw["mode"] = case["mode"]
    ds = detect(case["text"], **kw)
    if case["formula"] == "lemma-zhe":
        return _score_lemma_zhe(case, ds)
    anns = [d for d in ds if d["kind"] in ("announce", "gate", "uddana", "chart")
            or d["kind"] == "enter" and d["count"]]  # 就X中即有其M carries its own count (T1753)
    acc = [d for d in anns if d["accepted"]]
    if case["kind"] == "not-division":
        opens = [d for d in ds if d["kind"] == "enter"
                 and d["enter_kind"] == ENTER_FORMULAS.get(case["formula"])]
        return True, not acc and not opens, "accepted %s, opens %s" % (
            [d["text"][:24] for d in acc], [d["marker"] for d in opens])
    if case["kind"] == "close":
        closes = [d for d in ds if d["kind"] == "close"]
        return True, bool(closes) and closes[0]["heading"] == exp["close"], \
            "closes %s" % [d["heading"] for d in closes]
    if case["kind"] == "genre-gate":
        ents = [d for d in ds if d["kind"] == "enter" and d["accepted"] is not False
                and d["strength"] == "strong"]
        return True, not acc and not (kw["title"] and ents), "structure under the gate"
    why = []
    if exp["child_count"] is not None:
        if not acc:
            return True, False, "no accepted announcement"
        d = acc[0]
        if d["count"] != exp["child_count"]:
            why.append("count %s != %s" % (d["count"], exp["child_count"]))
        if exp["labels"] and d["labels"] != exp["labels"]:
            why.append("labels %s != %s" % (d["labels"], exp["labels"]))
        if exp["anaphor"] and d["anaphor"] != exp["anaphor"]:
            why.append("anaphor %r != %r" % (d["anaphor"], exp["anaphor"]))
        if exp.get("applies_to") == [1] and d["target"] != "index:1":
            why.append("target %r" % d["target"])
    if exp.get("heading"):
        if case["formula"] == "chart-note":
            d = acc[0] if acc else {}
            got = (d.get("heading"), d.get("ordinal"))
        else:
            ents = [d for d in ds if d["kind"] == "enter" and d["enter_kind"] != "anaphor"]
            if not ents:
                return True, False, "no entry marker"
            e = ents[0]
            got = (e["heading"], e["ordinal"])
            if exp.get("lemma"):
                lem = e["lemma"] or next((d["lemma"] for d in ds if d["kind"] == "lemma"), None)
                if not lem or lem["raw"] != exp["lemma"]:
                    why.append("lemma %r != %r" % (lem and lem["raw"], exp["lemma"]))
        if got[0] != exp["heading"]:
            why.append("heading %r != %r" % (got[0], exp["heading"]))
        if exp.get("ordinal") is not None and got[1] != exp["ordinal"]:
            why.append("ordinal %r != %r" % (got[1], exp["ordinal"]))
    if exp.get("opens") is False:
        strong = [d for d in ds if d["kind"] == "enter" and d["strength"] == "strong"
                  and d["enter_kind"] != "anaphor"]
        if strong:
            why.append("opens %r" % strong[0]["marker"])
    return True, not why, "; ".join(why)


def _walk(drafts):
    for d in drafts:
        yield d
        yield from _walk(d["children"])


def _score_lemma_zhe(case: dict, ds: list) -> tuple:
    """Zhiyi's 「X」者 device (README `lemma-zhe`). Negative: no live lemma_zhe entry. Listing case
    (child_count given): parse() lists the labels as listed-only children of one node (announced ==
    explained, root_text.raw == X) and the later gloss takes item 1 up. Heading case: the first
    lemma_zhe entry has the expected heading and lemma."""
    exp = case["expected"]
    lz = [d for d in ds if d["kind"] == "enter" and d["enter_kind"] == "lemma_zhe"]
    if case["kind"] == "not-division":
        live = [d["heading"] for d in lz if d["accepted"] is not False]
        return True, not live, "lemma_zhe entered %s" % live
    if exp["child_count"] is not None:
        res = parse(snippet_text(case["text"]), anchors=[])
        nodes = list(_walk(res.by_anchor[None]))
        div = next((d for d in nodes
                    if [c["heading_src"] for c in d["children"]] == exp["labels"]), None)
        if div is None:
            return True, False, "no node lists %s; nodes %s" % (exp["labels"], [d["heading_src"] for d in nodes])
        why = []
        for i, c in enumerate(div["children"]):
            com = c["locations"]["commentary"]
            listed = com["announced"] == com["explained"]
            if i == 0 and listed:
                why.append("item 1 not taken up by the later gloss")
            if i > 0 and not listed:
                why.append("item %d not listed-only" % (i + 1))
            rt = c["locations"]["root_text"]
            if not rt or rt["raw"] != c["heading_src"]:
                why.append("item %d root_text.raw %r" % (i + 1, rt and rt["raw"]))
        return True, not why, "; ".join(why)
    if not lz:
        return True, False, "no lemma_zhe entry marker"
    e = lz[0]
    why = []
    if e["heading"] != exp["heading"]:
        why.append("heading %r != %r" % (e["heading"], exp["heading"]))
    if exp.get("lemma") and (e["lemma"] or {}).get("raw") != exp["lemma"]:
        why.append("lemma %r != %r" % (e["lemma"] and e["lemma"]["raw"], exp["lemma"]))
    return True, not why, "; ".join(why)


@pytest.fixture(scope="module")
def results() -> list:
    return [(c,) + score(c) for c in CASES]


def _table(results) -> str:
    by = collections.defaultdict(lambda: [0, 0])
    for c, scored, ok, _ in results:
        if scored:
            by[c["formula"] or "(none)"][0] += ok
            by[c["formula"] or "(none)"][1] += 1
    return "\n".join("%-20s %d/%d" % (k, v[0], v[1]) for k, v in sorted(by.items()))


def test_case_pass_rates(results):
    raw = any(cbeta_xml_path(_file_id(c)) for c in CASES if c["formula"] == "chart-note")
    floors = FLOOR_ALL if raw else FLOOR_NO_RAW
    kinds = collections.Counter()
    for c, scored, ok, _ in results:
        if scored and ok:
            kinds[c["kind"]] += 1
    fails = [(c["id"], why) for c, scored, ok, why in results if scored and not ok]
    report = "per formula:\n%s\nfailures: %s" % (_table(results), fails)
    for kind, floor in floors.items():
        assert kinds[kind] >= floor, "%s: %d < floor %d\n%s" % (kind, kinds[kind], floor, report)


def test_every_formula_passes_its_cases(results):
    """Each formula slug scores all of its scorable cases (the achieved 100 %, docstring)."""
    by = collections.defaultdict(list)
    for c, scored, ok, why in results:
        if scored:
            by[c["formula"]].append((ok, c["id"], why))
    bad = {k: [(i, w) for ok, i, w in v if not ok] for k, v in by.items() if not all(x[0] for x in v)}
    assert not bad, bad


def test_labels_are_verbatim_substrings(results):
    """Every label the detector returns is a contiguous piece of the case text (label rule)."""
    for c in CASES:
        for d in detect(c["text"], mode=c.get("mode", "sutra")):
            for lab in d["labels"]:
                assert lab and lab in c["text"], (c["id"], lab)
            for it in d["items"]:
                assert c["text"][it["start"]:it["end"]], (c["id"], it)


# ------------------------------------------------------------------------------------ units


def snippet_text(s: str) -> InputText:
    """An InputText over a snippet (one pseudo line), to run parse() on case-sized text."""
    lh = "X00n0000_p0001a01"
    rec = {"linehead": lh, "text": s, "inline_notes": [], "heads": [], "mulu": []}
    return InputText(text_id="X00n0000", role="commentary", info={"title": "snippet"}, lines=[rec],
                     all_lineheads=[lh], index=build_index([rec]))


def test_parse_num():
    assert [parse_num(x) for x in ("一", "十", "十一", "二十", "三十三", "兩", "廿", "百")] == \
        [1, 10, 11, 20, 33, 2, 20, 100]
    assert parse_num("一三") is None and parse_num("") is None


def test_similarity():
    assert sim("明神呪之方", "明神呪之方") == 1.0
    assert sim("說立義分", "立義分") == 0.9
    assert sim("修行", "信法有大利益，常念修行諸波羅蜜故") < 0.75  # a short word inside a long label
    assert sim("明數", "數") == 0.9


def test_label_rule_locators():
    t = "從〈踊出〉訖經十四品，約本開權顯實"
    assert clean_label(t, 0, len(t))["label"] == "約本開權顯實"
    t = "「爾時優婆離」下，至「若他觀者名為邪觀」，是發請廣說分"
    lab = clean_label(t, 0, len(t))
    assert lab["label"] == "發請廣說分" and lab["lemma"]["a"] == "爾時優婆離"
    t = "品為序"
    assert clean_label(t, 0, len(t))["label"] == "序"


def test_listing_document_order_and_counts():
    t = "初二略明、後二總結、中間廣歎。"
    lst = parse_listing(t, 0, count=None, head_cls="句")
    assert lst.labels() == ["略明", "廣歎", "總結"]
    t = "：一說經通所因。「如是我聞」等，諸經通有故。二說經別所緣。"
    assert parse_listing(t, 0, count=2).labels() == ["說經通所因", "說經別所緣"]


# X0268 楞嚴經集註 body sentences (outside its chart region p0170a01–p0179a09; X0268 is OOD but its source
# text may be quoted): three collected glossators, three attributions each
X0268_ATTRIBUTIONS = ("長水云：「目即眼根，心即意識。」長水云：「一，多心體也。徧，局身體也。」長水云：「外不相知，云在外則不相知也。」"
                      "孤山云：「此三問將破心目之執，故先定之。」孤山云：「身內至近，尚不見知，況外物至遠乎？」孤山云：「既無來處，心體自無。」"
                      "苕溪云：「此縱計也。」苕溪云：「見面若成，復以前難，縱其所計。」苕溪云：「如云雖識二月，何謂真月？」")


def test_attributions_count():
    from chinese_workflow.outline.tier2.filters import attributions
    assert attributions(X0268_ATTRIBUTIONS) == {"長水": 3, "孤山": 3, "苕溪": 3}
    # the commentator's own voice, dialogue, function words and 云何 questions are not attributions
    assert attributions("贊曰：此初也。答曰：不然。又問曰：何故。於汝意云何？諸師云：非也。下文云：是。") == {}
    assert attributions("什曰：大士凡有三種。肇曰：此明其義。生曰：自此以下大論法理也。") == {"什": 1, "肇": 1, "生": 1}


def test_genre_gate_function():
    assert genre_gate("注維摩詰經", n_accepted=0, n_chars=10000)["decision"] == "no-structure"
    assert genre_gate("妙法蓮華經玄贊", n_accepted=0, n_chars=10000)["decision"] == "outline"
    assert genre_gate("注維摩詰經", n_accepted=50, n_chars=10000)["decision"] == "outline"
    coll = {"孤山": 3, "苕溪": 3, "長水": 3}
    g = genre_gate("楞嚴經集註", n_accepted=0, n_chars=10000, attributions=coll)
    assert g["decision"] == "no-structure" and "collected glosses" in g["evidence"]
    assert "9 attributions (X曰：/ X云：) by 3 names, 3 of them >= 3 times (孤山、苕溪、長水)" in g["evidence"]
    # the attribution count never changes the decision: a 疏 with collected glosses still outlines, a 註
    # without them is still gated
    assert genre_gate("觀無量壽佛經疏", n_accepted=0, n_chars=10000, attributions=coll)["decision"] == "outline"
    assert genre_gate("注維摩詰經", n_accepted=0, n_chars=10000, attributions={"別本": 27})["decision"] == "no-structure"
    assert "collected glosses" not in genre_gate("觀無量壽佛經疏", n_accepted=5, n_chars=10000,
                                                 attributions={"諸師": 7, "讚": 6})["evidence"]


def test_reported_division_rejected():
    ds = detect("有師作三段：初序、次正、後流通。")  # synthetic (no split-text quotation)
    ann = [d for d in ds if d["kind"] == "announce"]
    assert ann and not ann[0]["accepted"]
    assert any("another master" in r for r in ann[0]["reasons"])


def test_parse_snippet_member_of_counted_class():
    """此初聖 enters 二聖 and its first member (README pos-you-n-02, anaphor_path [1, 1])."""
    case = next(c for c in CASES if c["expected"] and c["expected"].get("anaphor_path") == [1, 1])
    res = parse(snippet_text(case["text"]), anchors=[])
    top = res.by_anchor[None]
    assert len(top) == 1  # 明神呪之方, entered by 下明
    classes = top[0]["children"]
    assert [c["heading_src"] for c in classes] == case["expected"]["labels"]
    assert classes[0]["children"] and classes[0]["children"][0]["_source_heading"] == "初聖"


def test_parse_snippet_overlap_rule():
    """A bare 有N right after a listing divides the item its labels share characters with (七佛讚揚)."""
    t = "有七：一標名，二請說，三正說，四勸勿惱法師，五更說偈喻罪，六請身護，七佛讚揚。有三：初總讚，次別讚，後勸讚。"
    res = parse(snippet_text(t), anchors=[])
    kids = res.by_anchor[None][0]["children"]
    assert [c["heading_src"] for c in kids[-1]["children"]] == ["總讚", "別讚", "勸讚"]
    assert not any(c["children"] for c in kids[:-1])


# T1718 dev p0003a19–a26: the open-count 通序, its six one-clause glosses, the first take-up
TONGXU_RUN = ("序有通、別，從「如是」去、至「却坐一面」，通序也；從「爾時世尊」去、至品，別序也。通序通諸教；"
              "別序別一經。通序為五或六或七云云。「如是」者，舉所聞之法體。「我聞」者，能持之人也。「一時」者，"
              "聞持和合，非異時也。「佛」者，時從佛聞也。「王城耆山」，聞持之所也。「與大比丘」者，是聞持之伴也。"
              "此皆因緣和合，次第相生。又「如是」者，三世佛經初皆安「如是」，諸佛道同不與世諍，世界悉檀也；")


def test_lemma_zhe_listing_run_then_members():
    """Six glosses after 通序為五或六或七 are listed-only items (announced == explained, lemma = X);
    又「如是」者 enters item 1; a later 「住」者 (not listed) becomes a member of the open-count
    division; 「王舍城」者 (sim 0.5 to the listed 王城耆山) becomes that item's child."""
    t = TONGXU_RUN + "「住」者，能住住所住。「王舍城」者，天竺稱羅閱祇伽羅。"
    res = parse(snippet_text(t), anchors=[])
    tong = next(d for d in _walk(res.by_anchor[None]) if d["heading_src"] == "通序")
    kids = tong["children"]
    assert [c["heading_src"] for c in kids] == ["如是", "我聞", "一時", "佛", "王城耆山", "與大比丘", "住"]
    assert kids[0]["locations"]["commentary"]["explained"] == "X00n0000_p0001a01:%d" % t.index("又「如是」者")
    for c in kids[1:6]:
        com = c["locations"]["commentary"]
        assert com["announced"] == com["explained"] and ":" in com["announced"]
    assert all(c["locations"]["root_text"]["raw"] == c["heading_src"] for c in kids)
    assert [c["heading_src"] for c in kids[4]["children"]] == ["王舍城"]
    assert any("lemma_zhe listing" in n for n in kids[1]["notes"])
    assert any("(lemma_zhe)" in n for n in kids[6]["notes"])
    assert res.stats["gloss_listed"] == 6 and res.stats["enters_lemma_zhe"] == 3
    assert tong["child_count_announced"] is None and "count_mismatch" not in tong["flags"]


# T1718 dev p0006a17–c01, unabridged: the head word 大 glossed, then Zhiyi's 約教釋 restates it three times
# (大者，… / 又大者，… / 勝者，…) and 多者 / 勝者 name no node
LEI_RUN = ("就多知識眾為六：一類、二數、三位、四歎、五列名、六結。一、類者，皆是大比丘氣類也。譬群方"
           "貴賤，各有班輩。今諸比丘，皆眾所知識、高譽大德也。《釋論》明「與」者，共義，舉七一解共，"
           "謂一時、一處、一戒、一心、一見、一道、一解脫也。若歷教，應各明七一：三藏一七一，通教二七"
           "一，別教無量七一，圓教一七一。若未發迹，正是三藏、通教中七一，直明兩意幾異，時、處、戒、"
           "解脫是同，心、見、道三種則異；若至開三顯一，即得入圓教七一也。《法華》論四種聲聞，今開住"
           "果者為兩：析法住果是三藏聲聞，體法住果是通教聲聞。開應化者為兩：登地應化別教聲聞，登住應"
           "化圓教聲聞。開佛道聲聞亦為兩：令他次第聞佛道是別教聲聞，令他不次第聞佛道即圓聲聞。聲聞義"
           "浩然，云何以證涅槃者判之云云。「大」者，《釋論》明「大」者，亦言多，亦言勝，器量尊重為天"
           "王等大人所敬故言大，升出九十五種道外故言勝，遍知內外經書故言多，又數至一萬二千故言多。今"
           "明有大道故、有大用故、有大知故，故言大。勝者，道勝、用勝、知勝，故言勝。多者，道多、用多"
           "、知多，故言多。道即性念處，大於一切智外道；用即共念處，勝神通外道；知即緣念處，多四韋陀"
           "外道也。約教釋大、多、勝者，大人所敬等，是三藏中釋耳。大者，大力羅漢所敬也；多者，遍知生"
           "滅即無生滅法也；勝者，勝三藏四門也，此通教釋也。又大者，體法大力羅漢所敬也；多者，恒沙佛"
           "法皆知也；勝者，勝二乘人，此別教釋也。又大者，諸大菩薩所敬也；多者，法界不可量法悉知也；"
           "勝者，勝諸菩薩也，此圓教釋也。本迹者，此諸大德久為諸佛之所咨嗟，本得勝幢三昧超諸外道，先"
           "已成就種智遍知，迹來輔佛行化，示作愛見中大、多、勝，欲引乳入酪；又作三藏中大、多、勝，欲"
           "引酪入生蘇；示方等中大、多、勝，欲引生蘇入熟蘇；示轉教作《般若》中大、多、勝；欲引熟蘇入"
           "醍醐故作《法華》中大、多、勝也，然其本地大、多、勝又矣云云。觀心者，空觀為大，假觀為多，"
           "中觀為勝。又直就中觀心性廣博猶若虛空，故名大；雙遮二邊入寂滅海，故名勝；雙照二諦多所含容"
           "，一心一切心，故名多也。")


def test_lemma_zhe_sub_gloss_and_sibling():
    """Inside a counted class: a gloss opens the first member of the node the text is in; the next
    gloss is its sibling; X contained in the open unit's word is a sub-gloss (T1718 dev p0003c27 /
    p0004b01 and the 比丘 / 眾 / 二、明數者 tail abridged to the markers; p0006a17–c01 unabridged). The weak
    markers inside 「大」者's discussion that name the entered node 大 (大者, 又大者 twice) are mentions, not
    moves: counted in tier2.stats.weak_mentions (多者 / 勝者 / 約教釋大、多、勝者 name no node)."""
    t = LEI_RUN + "「比丘」者，秦言淨命。「眾」者，天竺云僧伽。二、明數者，萬二千人也。"
    res = parse(snippet_text(t), anchors=[])
    six = next(d for d in _walk(res.by_anchor[None]) if d["child_count_announced"] == 6)
    lei = six["children"][0]
    assert [c["heading_src"] for c in lei["children"]] == ["大", "比丘", "眾"]
    assert not any(c["children"] for c in lei["children"])  # 大者 / 又大者 are no sub-glosses of 大
    assert not six["children"][1]["children"]  # 二、明數者 still resolves to item 2
    assert res.stats["weak_mentions"] == 3 and res.stats["enters_lemma_zhe"] == 3
    t2 = TONGXU_RUN + "「我聞」者，或「聞如是」。釋「聞」者，阿難侍佛二十餘年。「一時」者，肇師云：「法王啟運嘉會之時」者，世界也。"
    res2 = parse(snippet_text(t2), anchors=[])
    tong = next(d for d in _walk(res2.by_anchor[None]) if d["heading_src"] == "通序")
    by = {c["heading_src"]: c for c in tong["children"]}
    assert [c["heading_src"] for c in by["我聞"]["children"]] == ["聞"]
    assert by["一時"]["locations"]["commentary"]["explained"] == "X00n0000_p0001a01:%d" % t2.rindex("「一時」者")


def test_lemma_zhe_not_a_unit():
    """A title word before any division is reported, not entered; inside a 經「…」。贊曰 unit (Kuiji)
    a 「X」者 is a word gloss (T1723 dev p0850b08–b10, abridged); a citation fragment and a 、-list are
    not emitted by the scanner."""
    res = parse(snippet_text("委釋經題已如上說。「序」者，訓庠序，謂階位、賓主、問答悉庠序也。"), anchors=[])
    assert res.stats["nodes"] == 0 and [r["kind"] for r in res.report] == ["lemma-gloss-at-stub"]
    res = parse(snippet_text("經「爾時毘沙門至無諸衰患」。贊曰：下二天。中初文有三：初標，次說，後結勝。「毘沙門」者此云多聞。"),
                anchors=[])
    assert res.stats["gloss_in_lemma_unit"] == 1 and res.stats["enters_lemma_zhe"] == 0
    assert "毘沙門" not in [d["heading_src"] for d in _walk(res.by_anchor[None])]
    ds = detect("論云：「迦羅是實時」，示內弟子時；食時著衣者，為人也。「三摩耶是假時」，破外道邪見者，對治也。")
    assert not [d for d in ds if d["enter_kind"] == "lemma_zhe"]
    ds = detect("令無量人正法出家也。「難陀、跋難陀」，兄弟，居須彌邊海。")
    assert not [d for d in ds if d["enter_kind"] == "lemma_zhe"]
    ds = detect("下文云：「佛自住大乘」，即別、圓二觀云云。「中」者，佛好中道。")  # the 者 form stays a unit
    assert [d["heading"] for d in ds if d["enter_kind"] == "lemma_zhe"] == ["中"]


def test_prose_sutra_citation_does_not_arm_the_kuiji_guard():
    """Only a 經「…」 with its opener behind it (經「A至B」。贊曰) makes the 「X」者 that follows a word gloss of
    that lemma. A 經「…」 in prose is a citation (T33n1705: 經「千」字者非, a textual note, swallowed the real
    take-up 「有十心」者): the gloss after it still enters, and the parse equals the one without the citation."""
    base = ("就多知識眾為六：一類、二數、三位、四歎、五列名、六結。一、類者，皆是大比丘氣類也。")
    gloss = "「大」者，亦言多，亦言勝。「比丘」者，秦言淨命。「眾」者，天竺云僧伽。二、明數者，萬二千人也。"
    cite = "瓔珞中有六性，亦名六慧。經「千」字者非。"  # T1705 wording; the 經「…」 has no opener behind it

    def shape(res):
        six = next(d for d in _walk(res.by_anchor[None]) if d["child_count_announced"] == 6)
        return [(c["heading_src"], [g["heading_src"] for g in c["children"]]) for c in six["children"]]

    plain = parse(snippet_text(base + gloss), anchors=[])
    cited = parse(snippet_text(base + cite + gloss), anchors=[])
    assert cited.stats["gloss_in_lemma_unit"] == 0 and cited.stats["enters_lemma_zhe"] == 3
    assert shape(cited) == shape(plain) and shape(cited)[0] == ("類", ["大", "比丘", "眾"])
    # the citation is still a lemma statement (it opens a unit), tagged apart from Kuiji's
    sts = [d for d in detect(base + cite + gloss) if d["kind"] == "lemma"]
    assert [d["formula"] for d in sts] == ["sutra-cite"]
    # with its opener it is Kuiji's lemma and the gloss stays a word gloss of it
    kuiji = parse(snippet_text(base + "經「千」字者非。贊曰：" + gloss), anchors=[])
    assert kuiji.stats["gloss_in_lemma_unit"] == 3 and kuiji.stats["enters_lemma_zhe"] == 0


def test_prose_sutra_citation_inside_a_kuiji_unit_does_not_disarm_the_guard():
    """A 如經「…」等 in the body of a 經「A至B」。贊曰 unit (T33n1700 p0142c15, inside a 「…」述曰 unit) is a prose
    citation: it neither arms nor disarms the word-gloss guard, so the 「X」者 word glosses behind it are still
    counted in the unit, not entered as lemma_zhe nodes (751403d made it disarm: +4 false nodes on T1700)."""
    t = ("經「爾時毘沙門至無諸衰患」。贊曰：下二天。如經「以要言之」等，其義可知。"
         "「毘沙門」者此云多聞。「吠室羅末拏」者此云普聞。「提頭賴吒」者此云持國。")
    res = parse(snippet_text(t), anchors=[])
    assert res.stats["gloss_in_lemma_unit"] == 3 and res.stats["enters_lemma_zhe"] == 0
    assert not [d for d in _walk(res.by_anchor[None]) if d["heading_src"] in ("毘沙門", "吠室羅末拏", "提頭賴吒")]
    # the in-unit citation is still a lemma statement (sutra-cite), after the unit's own zanyue-lemma one
    sts = [d["formula"] for d in detect(t) if d["kind"] == "lemma"]
    assert sts == ["zanyue-lemma", "sutra-cite"]


SIX = "就多知識眾為六：一類、二數、三位、四歎、五列名、六結。"  # T1718 dev p0006a17–a18
# T1718 dev p0007c05–c24, unabridged: 四、歎德 and its glosses (「…」 sentence-initial after 論云：「…。」當知…耳。)
TAN_RUN = ("四、歎德，文有五句歎上三德。《法華論》云：「初句總，後句別。」當知諸句皆歎羅漢句耳。「諸"
           "漏已盡，無復煩惱」，此兩句歎上殺賊。漏者三漏也，《成論》云：「失道故名漏。」律云：「癡人"
           "造業，開諸漏門。」毘曇云：「漏落生死。」論、律語異而同明漏義。良由賊誑失於理寶，貧窮孤露"
           "造諸惡業、致生死苦，亡法身、失慧命、喪重寶，皆是賊義。不應謂是不生義歎德也。煩惱者，即九"
           "十八使，流扼纏蓋等逼惱行人。煩惱是能潤，漏業是所潤，能所既盡，正是殺賊義，那得作不生歎耶"
           "？「逮得己利」一句，是歎應供，三界因果皆名為他，智斷功德皆名己利，己利具足故成應供。「盡"
           "諸有結，心得自在」兩句，是歎不生。諸有即二十五有，生處也；結即二十五有，生因也。因盡果亡"
           "，歎不生明矣！不應作殺賊歎也。羅漢但應結盡，未應有盡；有盡者，因中說果，又盡在不久也。「"
           "心得自在」者，定具足名心自在，慧具足名慧自在，慧自在未必心自在，心自在必慧自在。")
# T1718 dev p0008a09–a22, unabridged: 五、列名, the surname 憍陳如 (姓也) and its name 阿若 (名也)
LIEMING_RUN = ("五、列名，略舉二十一尊者，佛諸弟子皆備眾行，而隱其圓能各從一德標名者，欲引偏好故。《增一"
               "阿含》云：「憍陳如比丘，皆共上座名者，有德大人相隨，舍利弗共智慧深利者相隨，目連共神通大"
               "力者相隨。」皆掌一法，引諸偏好意也。若欲消名須識其行，從德立號無往不通也。一一羅漢例作四"
               "釋云云。「憍陳如」，姓也，此翻火器，婆羅門種，其先事火，從此命族。火有二義：照也、燒也。"
               "照則闇不生，燒則物不生，此以不生為姓。「阿若」者，名也，此翻已知，或言無知，無知者非無所"
               "知也，乃是知無耳，若依二諦即是知真，以無生智為名也。")


def test_verse_section_citation_has_its_opener():
    """Kuiji's head citation of a verse section is 經「A至B」。頌曰： (the opener 頌曰, as 贊曰 before it): a
    zanyue-lemma that arms the word-gloss guard, not a prose `sutra-cite`."""
    t = "經「爾時毘沙門至無諸衰患」。頌曰：此頌有三。「毘沙門」者此云多聞。"
    assert [d["formula"] for d in detect(t) if d["kind"] == "lemma"] == ["zanyue-lemma"]
    res = parse(snippet_text(t), anchors=[])
    assert res.stats["gloss_in_lemma_unit"] == 1 and res.stats["enters_lemma_zhe"] == 0


def test_detect_survives_a_doubled_numeral_subject():
    """一一之中各有四種 (T38n1782 p1009a07): the subject 一一之中 reads as a numeral phrase but parse_num("一一")
    is None, so _target_hint must not format it with %d (a TypeError out of detect(); parse() was never
    affected, `_target` guards the None). The hint falls through to the later rules (not an index)."""
    t = "四、同事善友，善事相同故。一一之中各有四種，皆應親近。"
    ann = [d for d in detect(t) if d["kind"] == "announce"]
    assert len(ann) == 1 and not str(ann[0]["target"]).startswith("index:")
    assert parse(snippet_text(t), anchors=[]).stats["nodes"] == 0
    # a numeral that does parse keeps its index hint
    assert [detect(t)[0]["target"] for t in ("二中有二：一者甲、二者乙。", "後中有二：一者甲、二者乙。")] == [
        "index:2", "index:-1"]


def _six_items(text: str) -> list:
    res = parse(snippet_text(text), anchors=[])
    six = next(d for d in _walk(res.by_anchor[None]) if d["child_count_announced"] == 6)
    return six["children"]


def test_lemma_zhe_extent_glosses_enter_with_their_extent():
    """「逮得己利」一句 / 「盡諸有結，心得自在」兩句 are members of 四歎 that carry their extent; the comma form
    「諸漏已盡，無復煩惱」，… after 《法華論》云：「…。」當知…耳。 is not a citation fragment (the 當知 sentence
    is the one before it); 「心得自在」者 is a sub-gloss of the two-sentence unit (T1718 dev p0007c05–c24)."""
    kids = _six_items(SIX + TAN_RUN)
    tan = kids[3]
    assert [c["heading_src"] for c in tan["children"]] == ["諸漏已盡，無復煩惱", "逮得己利", "盡諸有結，心得自在"]
    assert [c["extent_announced"] for c in tan["children"]] == [None, "一句", "兩句"]
    assert [g["heading_src"] for g in tan["children"][2]["children"]] == ["心得自在"]


def test_lemma_zhe_name_after_surname_is_a_sub_gloss():
    """「阿若」者，名也 after 「憍陳如」，姓也 is a sub-gloss of the surname's unit although 阿若 is no part of 憍陳如
    (T1718 dev p0008a09–a22); with 姓也 changed to a plain remark it is the unit's sibling."""
    lie = _six_items(SIX + LIEMING_RUN)[4]
    assert [c["heading_src"] for c in lie["children"]] == ["憍陳如"]
    assert [g["heading_src"] for g in lie["children"][0]["children"]] == ["阿若"]
    lie2 = _six_items(SIX + LIEMING_RUN.replace("「憍陳如」，姓也", "「憍陳如」，是也"))[4]
    assert [c["heading_src"] for c in lie2["children"]] == ["憍陳如", "阿若"]


def test_citation_filter_looks_through_a_quotation_holding_a_period():
    """R2c: the comma form after a sentence that cites with 云：「 is a fragment of the citation, also when the
    quotation holds a 。 (論云：「甲。乙」。「X」，… and, at a ；-start, 論云：「甲。乙」，丙；「X」，…): the
    look-back does not stop at the 。 inside the quotation. A 。 that closes it ends the sentence
    (「初句總，後句別。」當知…耳。 returns the 當知 sentence). No dev instance of either: synthetic."""
    from chinese_workflow.outline.tier2.scanner import _prev_sentence

    t = "論云：「迦羅是實時。示內弟子時」。「三摩耶是假時」，破外道邪見者，對治也。"
    assert _prev_sentence(t, t.index("「三摩耶")) == "論云：「迦羅是實時。示內弟子時」。"
    assert not [d for d in detect(t) if d["enter_kind"] == "lemma_zhe"]
    t = "論云：「迦羅是實時。示內弟子時」，次第釋之；「三摩耶是假時」，破外道邪見者，對治也。"
    assert _prev_sentence(t, t.index("「三摩耶")) == "論云：「迦羅是實時。示內弟子時」，次第釋之；"
    assert not [d for d in detect(t) if d["enter_kind"] == "lemma_zhe"]
    t = "論云：「迦羅是實時。示內弟子時。」"  # a sentence ending 。」 is looked through to its opener
    assert _prev_sentence(t + "「X」，", len(t)) == t
    # 「X」 right after 。」 is no sentence start (scanner._sentence_starts); behind a ○ it is one
    assert not [d for d in detect(t + "「三摩耶是假時」，破外道邪見者。") if d["enter_kind"] == "lemma_zhe"]
    assert not [d for d in detect(t + "○「三摩耶是假時」，破外道邪見者。") if d["enter_kind"] == "lemma_zhe"]
    t = "《法華論》云：「初句總，後句別。」當知諸句皆歎羅漢句耳。「諸漏已盡」，此兩句歎上殺賊。"
    assert _prev_sentence(t, t.index("「諸漏")) == "當知諸句皆歎羅漢句耳。"
    # without 云：「 the same shapes are glosses
    for t in ("迦羅是實時。示內弟子時。「三摩耶是假時」，破外道邪見者，對治也。",
              "迦羅是實時，示內弟子時；「三摩耶是假時」，破外道邪見者，對治也。"):
        assert [d["heading"] for d in detect(t) if d["enter_kind"] == "lemma_zhe"] == ["三摩耶是假時"]
    # and the 者 form after a citation stays a unit in both positions
    t = "論云：「迦羅是實時。示內弟子時」，次第釋之；「中」者，佛好中道。"
    assert [d["heading"] for d in detect(t) if d["enter_kind"] == "lemma_zhe"] == []  # ；-start: any form
    t = "論云：「迦羅是實時。示內弟子時」。「中」者，佛好中道。"
    assert [d["heading"] for d in detect(t) if d["enter_kind"] == "lemma_zhe"] == ["中"]


def test_lemma_zhe_second_gloss_of_a_taken_up_item_is_a_mention():
    """A second 「X」者 for an item that was already taken up restates it: no duplicate-headed member, no
    move, counted in tier2.stats.gloss_repeats (又「如是」者 once item 1 is entered; 又「X」者 restating the
    open unit's own word or a gloss beside it). A bare 「X」者 repeating a gloss is another occurrence of
    the word and a node. A one-character label matched only through sim()'s 0.9 rule (佛 / 佛子) names no
    repeat. T1718 dev p0003a19–a26 (TONGXU_RUN) with synthetic repeats."""
    def tong_kids(text):
        res = parse(snippet_text(text), anchors=[])
        tong = next(d for d in _walk(res.by_anchor[None]) if d["heading_src"] == "通序")
        return [c["heading_src"] for c in tong["children"]], res.stats

    base = TONGXU_RUN + "「住」者，能住住所住。"
    kids, stats = tong_kids(base)
    assert kids == ["如是", "我聞", "一時", "佛", "王城耆山", "與大比丘", "住"] and stats["gloss_repeats"] == 0
    kids, stats = tong_kids(base + "又「如是」者，四悉檀各有所為也。又「住」者，住處也。")
    assert kids == ["如是", "我聞", "一時", "佛", "王城耆山", "與大比丘", "住"]  # 如是 (item) and 住 (unit) repeated
    assert stats["gloss_repeats"] == 2 and stats["enters_lemma_zhe"] == 2
    kids, stats = tong_kids(TONGXU_RUN + "「佛」者，時從佛聞也。「住」者，能住住所住。「佛子」者，菩薩也。")
    assert kids[3:] == ["佛", "王城耆山", "與大比丘", "住", "佛子"] and stats["gloss_repeats"] == 0
    # under a counted class: 又「大」者 after 比丘 restates the gloss beside the open unit (a mention); a bare
    # 「大」者 is another occurrence of the word in the sūtra and a node (T1705: 「何以故」者 twice under 標)
    cls = SIX + "一、類者，皆是大比丘氣類也。「大」者，亦言多。「比丘」者，秦言淨命。"
    kids = _six_items(cls + "又「大」者，亦言勝。")
    assert [g["heading_src"] for g in kids[0]["children"]] == ["大", "比丘"]
    kids = _six_items(cls + "「大」者，亦言勝。")
    assert [g["heading_src"] for g in kids[0]["children"]] == ["大", "比丘", "大"]


def test_no_structure_keeps_the_machines_evidence():
    """Under the genre gate no node is built, but the filter's rejections and the statements the machine
    would have acted on are reported, so outline-report.json and the resolver's adjudicate task see them."""
    # gate-you-n-01 (T1775, allowed) + a synthetic strong entry marker and closing marker, each at a sentence
    # start (after 肇曰： the scanner sees no sentence start: 肇曰 is not one of the commentary OPENERS)
    t = "什曰：大士凡有三種，一者出家、二者在家、三者他方來。第二、明其義也。上明大士竟。"
    text = snippet_text(t)
    text.info["title"] = "注維摩詰經"
    res = parse(text, anchors=[])
    assert res.genre_gate["decision"] == "no-structure" and res.by_anchor == {None: []}
    assert [r["text"][:6] for r in res.rejected] == ["大士凡有三種"]
    assert all(set(r) == {"linehead", "offset", "text", "reason"} for r in res.rejected)
    assert "classifier 種 names kinds" in res.rejected[0]["reason"]
    kinds = [(r["kind"], r["text"]) for r in res.report]
    assert ("gated-enter", "第二、明其義也") in kinds and ("gated-close", "上明大士竟") in kinds
    assert all(set(r) == {"id", "linehead", "offset", "kind", "text", "reason"} for r in res.report)
    assert res.stats["rejected"] == 1 and res.stats["gated_enters"] == 1 and res.stats["gated_closes"] == 1
    assert res.stats["nodes"] == 0 and res.stats["announcements"] == 0


def _self_doc(res) -> dict:
    """The numbered self-outlining document of a snippet's drafts (what the pipeline validates)."""
    doc, _ = build_prediction(
        res.by_anchor[None], text_id="X00n0000", text_title_src="snippet", outline_mode="self-outlining",
        root_text_id="X00n0000", commentary_id=None, scheme_id="self", source_file="snippet",
        source_document={"kind": "root-text", "text_id": "X00n0000", "title": "snippet"},
        generated_by="tests/unit/test_tier2_cases.py", format_note="tier-2 drafts, self-outlining")
    return doc


# synthetic, after T31n1602 p0521b11-p0524a28 (E06 failed cell tier2-OOD-T1602): an uddāna lists 常、斷、空
# and the text takes up the younger item 斷 before its elder 常
UDDANA_OUT_OF_ORDER = "何等為三？嗢柁南曰：常、斷、空。斷論者，謂執斷見。常論者，謂執常見。空論者，謂執空見。"


def test_self_mode_entered_out_of_order_is_demoted():
    """Self-outlining: an item entered before its elder sibling's treatment loses its explained
    position (reported) instead of breaking sibling order, so the outline still validates."""
    res = parse(snippet_text(UDDANA_OUT_OF_ORDER), anchors=[], mode="self-outlining")
    items = res.by_anchor[None][0]["children"]
    assert [c["heading_src"] for c in items] == ["常", "斷", "空"]
    exp = [c["locations"]["commentary"]["explained"] for c in items]
    assert exp[0] == "X00n0000_p0001a01:%d" % UDDANA_OUT_OF_ORDER.index("常論者")
    assert exp[1] is None
    assert exp[2] == "X00n0000_p0001a01:%d" % UDDANA_OUT_OF_ORDER.index("空論者")
    assert any("out of order" in n for n in items[1]["notes"])
    assert [r["text"] for r in res.report if r["kind"] == "entered-out-of-order"] == ["斷"]
    rep = validate(_self_doc(res))
    assert not rep.errors, [(e.code, e.message) for e in rep.errors[:5]]


def test_uddana_division_starts_at_the_uddana():
    """嗢拕南曰 has no subject: the division it heads is explained at 嗢, and its raw holds the head only
    (not the text from the start of the span, as when subject_start defaulted to 0)."""
    res = parse(snippet_text(UDDANA_OUT_OF_ORDER), anchors=[], mode="self-outlining")
    wrapper = res.by_anchor[None][0]
    com = wrapper["locations"]["commentary"]
    assert com["explained"] == "X00n0000_p0001a01:%d" % UDDANA_OUT_OF_ORDER.index("嗢")
    assert "何等為三" not in com["raw"]
    assert set(com["raw"].split(" | ")) == {"嗢柁南曰："}


# T31n1602 p0521b11-b16 (outside every split): the uddāna of the 十六異論. Its head gives the count, its last
# piece 名十六異論 restates it, and its first piece carries the verse's verb 執 (E06 review B4).
UDDANA_T1602 = ("何等十六？嗢柁南曰：執因中有果、顯了、有去來、我、常、宿作因、自在等、害法、邊無邊、矯亂、見無因、"
                "斷、空、計勝、淨、吉祥，名十六異論。")
SIXTEEN = ["因中有果", "顯了", "有去來", "我", "常", "宿作因", "自在等", "害法", "邊無邊", "矯亂", "見無因", "斷", "空",
           "計勝", "淨", "吉祥"]


def test_uddana_closing_phrase_and_lead_verb():
    """One item too many against the announced count: the closing phrase goes and the verse-initial 執 goes
    (labels.uddana_listing). With no count the closer still goes (it carries a numeral) but 執 stays; a count
    that matches the pieces keeps both."""
    pos = UDDANA_T1602.index("曰：") + 2
    assert uddana_count(UDDANA_T1602, UDDANA_T1602.index("嗢")) == 16
    assert uddana_listing(UDDANA_T1602, pos, expected=16).labels() == SIXTEEN
    assert uddana_listing(UDDANA_T1602, pos, expected=None).labels() == ["執因中有果"] + SIXTEEN[1:]
    assert uddana_listing(UDDANA_T1602, pos, expected=17).labels() == ["執因中有果"] + SIXTEEN[1:] + ["名十六異論"]
    d = next(d for d in detect(UDDANA_T1602) if d["kind"] == "uddana")
    assert d["count"] == 16 and d["labels"] == SIXTEEN


def test_uddana_count_reads_the_announced_head_only():
    """何等N？ / 云何為N？ / 有N種。 right before the head give the count; any other lead-in, or none, gives None."""
    for s, n in (("何等為三？嗢柁南曰：", 3), ("云何為十六？嗢柁南曰：", 16), ("有三種。嗢拕南曰：", 3),
                 ("如是已說。嗢柁南曰：", None), ("嗢柁南曰：", None)):
        assert uddana_count(s, s.index("嗢")) == n, s
    s = "此中有三門，別嗢拕南曰：" + "界、相、如理。"  # the head the scanner passes starts at the 別 prefix
    assert uddana_count(s, s.index("別")) == 3


def test_x_zhe_with_a_function_head_subject_is_no_enter():
    """若無常者 (T31n1602 p0524a11) is a conditional, not a take-up: X_ZHE_RE yields no enter when x opens with
    a FUNCTION_HEAD character (scanner._enter_at). On the dev spans no such marker ever moved the cursor
    (instrumented builds, E06 review §1 item 9); the optional prefix is not x, so 其X者 still enters."""
    s = "若無常者，此所作因體是變異，而執我有所作，不應道理。"
    for mode in ("sutra", "self-outlining"):
        assert [d for d in detect(s, mode=mode) if d["kind"] == "enter"] == []
    assert [d["heading"] for d in detect("其來意者，…。") if d["kind"] == "enter"] == ["來意"]


def test_num_zhe_chu_needs_its_separator():
    """初、X者 is ordinal 1 (T1753 p0252b04); 初若無常者 is not: 初 is an adverb there, and read as an ordinal the
    marker would bypass the function-word exclusion that X_ZHE_RE applies to 若無常者 (final review 2026-10-03).
    It is left to the weak X者 reading, which only a listed label can take up."""
    got = [d for d in detect("初、解化前序者，就此序中，即有其四。") if d["kind"] == "enter"]
    assert [(d["enter_kind"], d["heading"], d["ordinal"]) for d in got] == [("num_zhe", "解化前序", 1)]
    got = [d for d in detect("初若無常者，此所作因體是變異。") if d["kind"] == "enter"]
    assert [(d["enter_kind"], d["ordinal"]) for d in got] == [("x_zhe", None)]


# T31n1602 sentences in the order of the text under a synthetic head: the uddāna lists 我、常、斷, 計X論者，謂如有一
# takes each up, and the conditionals 若無常者 / 若我斷者 inside the treatments must not (E06 review B4)
PROPONENT_SNIPPET = (
    "何等為三？嗢柁南曰：我、常、斷。"
    "計我論者，謂如有一，若沙門若婆羅門，起如是見立如是論：有我、有薩埵。"
    "若無常者，此所作因體是變異，而執我有所作，不應道理。"
    "計常論者，謂如有一，若沙門若婆羅門，起如是見，立如是論：我及世間皆是常住。"
    "若我斷者，汝先所說麁色四大所造之身，不應道理。"
    "斷見論者，謂如有一，若沙門若婆羅門，起如是見立如是論：乃至我有麁色四大所造之身，住持未壞。")


def test_proponent_enter_takes_up_the_listed_doctrine():
    """Self-outlining: X論者，謂如有一 enters the listed item sim() maps X to (計我 -> 我 by x[-1], 斷見 -> 斷 by
    x[0]) through the x_zhe resolution path; the conditionals no longer move the cursor, so the siblings stay in
    order and nothing is reported. Sūtra mode has no such kind: there the marker is a weak X者 with x = 計我論."""
    res = parse(snippet_text(PROPONENT_SNIPPET), anchors=[], mode="self-outlining")
    items = res.by_anchor[None][0]["children"]
    assert [c["heading_src"] for c in items] == ["我", "常", "斷"]
    got = [c["locations"]["commentary"]["explained"] for c in items]
    assert got == ["X00n0000_p0001a01:%d" % PROPONENT_SNIPPET.index(k) for k in ("計我論者", "計常論者", "斷見論者")]
    assert res.report == []
    assert items[0]["locations"]["commentary"]["raw"].split(" | ")[-1] == "計我論者"
    ds = detect(PROPONENT_SNIPPET, mode="self-outlining")
    assert [(d["enter_kind"], d["heading"]) for d in ds if d["kind"] == "enter"] == \
        [("proponent", "計我"), ("proponent", "計常"), ("proponent", "斷見")]
    res = parse(snippet_text(PROPONENT_SNIPPET), anchors=[])
    assert res.by_anchor[None][0]["children"][0]["locations"]["commentary"]["explained"] == \
        "X00n0000_p0001a01:%d" % PROPONENT_SNIPPET.index("我、常")


# ------------------------------------------------------------------- self-outlining take-up (E06 B7)
# T1666 大乘起信論 is outside every split. Verified 2026-10-02: five of the nine listings the filter rejected in
# project-qixin-self are taken up in order as sentence-initial 所言X者 / X者 / 云何修行X門？; the deferred
# 云何為N？ shape hides the items of 此識有二種義 (p0576b10) and 修行有五門 (p0581c14).
TAKEUP = ("覺與不覺有二種相。云何為二？一者、同相，二者、異相。同相者，譬如種種瓦器皆同微塵性相，"
          "如是無漏無明種種業幻皆同真如性相。")
DEFERRED = "此識有二種義，能攝一切法、生一切法。云何為二？一者、覺義，二者、不覺義。所言覺義者，謂心體離念。"
MEN = ("修行有五門，能成此信。云何為五？一者、施門，二者、戒門，三者、忍門，四者、進門，五者、止觀門。"
       "云何修行施門？若見一切來求索者，所有財物隨力施與，以自捨慳貪令彼歡喜。若見厄難恐怖危逼，隨己堪任施與無畏。"
       "若有眾生來求法者，隨己能解方便為說。不應貪求名利恭敬，唯念自利利他迴向菩提故。"
       "云何修行戒門？所謂不殺、不盜、不婬、不兩舌、不惡口、不妄言、不綺語，遠離貪嫉、欺詐、諂曲、瞋恚、邪見。"
       "若出家者為折伏煩惱故，亦應遠離憒閙、常處寂靜，修習少欲知足頭陀等行。乃至小罪心生怖畏，慚愧改悔，"
       "不得輕於如來所制禁戒。當護譏嫌，不令眾生妄起過罪故。"
       "云何修行忍門？所謂應忍他人之惱，心不懷報；亦當忍於利、衰、毀、譽、稱、譏、苦、樂等法故。")
NO_TAKEUP = "此妄境界熏習義則有二種。云何為二？一者、增長念熏習，二者、增長取熏習。妄心熏習義則有二種。"


def walk_all(ds):
    for d in ds:
        yield d
        yield from walk_all(d["children"])


def test_taken_up_counts_in_order():
    from chinese_workflow.outline.tier2.filters import taken_up
    from chinese_workflow.outline.tier2.scanner import scan
    st = next(s for s in scan(TAKEUP, mode="self-outlining") if s.kind == "announce")
    assert st.labels == ["同相", "異相"]
    assert taken_up(TAKEUP, st, len(TAKEUP)) == (1, 2)
    # order matters: 同相者 is found at the end (k = 1), then 異相者 must follow it and does not (k stays 1)
    swapped = "覺與不覺有二種相。云何為二？一者、同相，二者、異相。異相者，如種種瓦器各各不同。同相者，譬如瓦器。"
    st = next(s for s in scan(swapped, mode="self-outlining") if s.kind == "announce")
    assert taken_up(swapped, st, len(swapped)) == (1, 2)
    st = next(s for s in scan(NO_TAKEUP, mode="self-outlining") if s.kind == "announce")
    assert taken_up(NO_TAKEUP, st, len(NO_TAKEUP)) == (0, 2)
    # the bound cuts the search: nothing after the listing end
    st = next(s for s in scan(TAKEUP, mode="self-outlining") if s.kind == "announce")
    assert taken_up(TAKEUP, st, st.end) == (0, 2)


def test_judge_take_up_override_is_mode_gated():
    ds = detect(TAKEUP, mode="self-outlining")
    ann = [d for d in ds if d["kind"] == "announce"][0]
    assert ann["accepted"] and ann["labels"] == ["同相", "異相"]
    assert "take-up override: 1/2 items taken up in order (self-outlining)" in ann["reasons"]
    assert not any(r.startswith(("-1 classifier", "-1 subject is a term")) for r in ann["reasons"])
    assert "-1 items are terms" in ann["reasons"]  # kept: the override drops the list-shape penalties only
    sutra = [d for d in detect(TAKEUP) if d["kind"] == "announce"][0]
    assert not sutra["accepted"] and not any("take-up" in r for r in sutra["reasons"])
    neg = [d for d in detect(NO_TAKEUP, mode="self-outlining") if d["kind"] == "announce"]
    assert neg and not any(d["accepted"] for d in neg)


def test_deferred_count_question_reparses_the_listing():
    from chinese_workflow.outline.tier2.scanner import scan
    st = next(s for s in scan(DEFERRED, mode="self-outlining") if s.kind == "announce")
    assert st.labels == ["覺義", "不覺義"] and st.listing.rhetorical and st.listing.deferred and st.count == 2
    st = next(s for s in scan(DEFERRED, mode="sutra") if s.kind == "announce")
    assert st.labels == ["能攝一切法", "生一切法"] and not st.listing.deferred  # sūtra mode: unchanged
    ann = [d for d in detect(DEFERRED, mode="self-outlining") if d["kind"] == "announce"][0]
    assert ann["accepted"] and "take-up override: 1/2 items taken up in order (self-outlining)" in ann["reasons"]


def test_yunhe_men_enters_the_listed_items():
    res = parse(snippet_text(MEN), anchors=[], mode="self-outlining")
    top = res.by_anchor[None]
    assert len(top) == 1 and [c["heading_src"] for c in top[0]["children"]] == ["施門", "戒門", "忍門", "進門", "止觀門"]
    assert "count_mismatch" not in top[0]["flags"]
    first = top[0]["children"][0]["locations"]["commentary"]
    assert first["explained"] == "X00n0000_p0001a01:%d" % MEN.index("云何修行施門")
    assert "云何修行施門？" in first["raw"]
    for i, name in ((1, "戒門"), (2, "忍門")):  # items 1-3 are taken up (3 of 5): what earns the deferred listing its +2
        assert top[0]["children"][i]["locations"]["commentary"]["explained"] == \
            "X00n0000_p0001a01:%d" % MEN.index("云何修行" + name)
    sutra = parse(snippet_text(MEN), anchors=[])
    assert sutra.by_anchor[None][0]["children"] == [] and "count_mismatch" in sutra.by_anchor[None][0]["flags"]


def test_unresolved_suoyan_does_not_block_the_next_announcement():
    # synthetic: 所言X者 names nothing announced; the bare listing after it must still attach to the cursor
    t = "所言空者，謂心無妄。此識有二種義，能攝一切法、生一切法。云何為二？一者、覺義，二者、不覺義。所言覺義者，謂心體離念。"
    res = parse(snippet_text(t), anchors=[], mode="self-outlining")
    kinds = [r["kind"] for r in res.report]
    assert kinds.count("unmatched-enter") == 1 and "ambiguous-target" not in kinds
    assert [d["heading_src"] for d in walk_all(res.by_anchor[None])][-2:] == ["覺義", "不覺義"]


# a strong entry marker that names no announced node moves the text to a place we cannot place (lost): the next bare
# announcement is not attached (ambiguous-target). An unresolved 所言X者 glosses a term and neither sets nor clears it.
LOST_HEAD = ("修行有二門，能成此信。云何為二？一者、施門，二者、戒門。云何修行施門？若見來求者施與。"
             "云何修行忍門？若人來惱應忍。")  # 云何修行忍門？ names no listed 門


def test_unresolved_suoyan_keeps_an_earlier_lost_state():
    for between in ("", "所言空者，謂心無妄。"):
        res = parse(snippet_text(LOST_HEAD + between + DEFERRED), anchors=[], mode="self-outlining")
        amb = [r for r in res.report if r["kind"] == "ambiguous-target"]
        assert len(amb) == 1 and amb[0]["text"].startswith("此識有二種義"), between
        want = ["云何修行忍門？"] + (["所言空者"] if between else [])
        assert [r["text"] for r in res.report if r["kind"] == "unmatched-enter"][:len(want)] == want
        # the bare listing is not hung on the cursor (施門): 覺義 / 不覺義 are not in the tree
        assert [d["heading_src"] for d in walk_all(res.by_anchor[None])] == ["修行", "施門", "戒門"], between


# the take-up search runs from the listing's end to min(end + TAKE_UP_WINDOW, the next close statement, end of text)
CLOSE_HEAD = "覺與不覺有二種相。云何為二？一者、同相，二者、異相。"
CLOSE_TAIL = "同相者，譬如瓦器皆同微塵。異相者，如種種瓦器各各不同。"
CLOSE_MID = "已說立義分。次說解釋分。"


def _filler(n: int) -> str:
    return "心性不生不滅。" * (n // 7)  # no marker, no listing


def test_take_up_search_stops_at_the_next_close_statement():
    taken = parse(snippet_text(CLOSE_HEAD + CLOSE_TAIL + CLOSE_MID), anchors=[], mode="self-outlining")
    assert taken.rejected == [] and taken.stats["announcements"] == 1  # take-ups before the close: counted
    # the take-ups lie after 已說立義分: they belong to the next part. With no text between the listing and the close
    # the close statement starts exactly where the listing ends (t.index(CLOSE_MID) == len(CLOSE_HEAD))
    for gap in ("", "此謂二相差別義。"):
        res = parse(snippet_text(CLOSE_HEAD + gap + CLOSE_MID + CLOSE_TAIL), anchors=[], mode="self-outlining")
        assert [r["text"] for r in res.rejected] == [CLOSE_HEAD], repr(gap)
        assert res.stats["announcements"] == 0, repr(gap)


def test_take_up_window_bounds_the_search():
    from chinese_workflow.outline.tier2.filters import TAKE_UP_WINDOW
    near = parse(snippet_text(CLOSE_HEAD + _filler(TAKE_UP_WINDOW - 200) + CLOSE_TAIL), anchors=[],
                 mode="self-outlining")  # about 1,800 characters of other text between the listing and 同相者
    assert near.rejected == [] and near.stats["announcements"] == 1
    far = parse(snippet_text(CLOSE_HEAD + _filler(TAKE_UP_WINDOW + 100) + CLOSE_TAIL), anchors=[],
                mode="self-outlining")  # about 2,100: past the window
    assert [r["text"] for r in far.rejected] == [CLOSE_HEAD] and far.stats["announcements"] == 0


# a listing the deferred count question exposes (X有N種，clause。云何為N？) earns the +2 云何為N？ bonus only when its
# items are taken up (T1602 glossary lists 有五種處 p0518b01 / 有五種相 p0582c04 are not); one whose question follows the
# head directly keeps the bonus. Under the genre gate (no take_up_bound) a deferred listing gets none.
def test_deferred_listing_earns_the_count_question_bonus_only_when_taken_up():
    from chinese_workflow.outline.tier2.filters import judge
    from chinese_workflow.outline.tier2.scanner import scan

    def announce(text):
        return next(s for s in scan(text, mode="self-outlining") if s.kind == "announce")

    bonus = lambda reasons: [r for r in reasons if r.startswith("+2 云何為N？")]  # noqa: E731
    bare = DEFERRED.split("所言覺義者")[0]
    for text, expect in ((DEFERRED, True), (bare, False)):
        st = announce(text)
        assert st.listing.deferred and st.labels == ["覺義", "不覺義"]
        acc, reasons, _ = judge(st, text, mode="self-outlining", take_up_bound=len(text))
        assert acc is expect and bool(bonus(reasons)) is expect, reasons
    assert bonus(judge(announce(DEFERRED), DEFERRED, mode="self-outlining")[1]) == []
    res = parse(snippet_text(bare), anchors=[], mode="self-outlining")  # untaken: rejected, nothing built
    assert len(res.rejected) == 1 and not list(walk_all(res.by_anchor[None]))
    st = announce(NO_TAKEUP)  # not deferred: the question follows the head's sentence
    assert not st.listing.deferred
    acc, reasons, _ = judge(st, NO_TAKEUP, mode="self-outlining", take_up_bound=st.end)
    assert bonus(reasons) == ["+2 云何為N？ enumeration (self-outlining)"] and not acc


DEFINED = ("真如有二種相。云何為二？一者、體大，謂一切法真如平等不增減故；"
           "二者、相大，謂如來藏具足無量性功德故。")
DEFINED_TAKEUP = "體大者，謂一切法真如平等。相大者，謂如來藏具足功德。"


def test_judge_take_up_drops_the_defined_items_penalty():
    from chinese_workflow.outline.tier2.filters import judge
    from chinese_workflow.outline.tier2.scanner import scan
    text = DEFINED + DEFINED_TAKEUP
    st = next(s for s in scan(text, mode="self-outlining") if s.kind == "announce")
    assert [lab.split("，")[0] for lab in st.labels] == ["體大", "相大"]
    acc, reasons, score = judge(st, text, mode="self-outlining", take_up_bound=len(text))
    assert acc and score == 2
    assert not any(r.startswith(("-1 classifier", "-1 subject is a term", "-2 items are defined")) for r in reasons)
    assert "take-up override: 2/2 items taken up in order (self-outlining)" in reasons
    acc, reasons, score = judge(st, text, mode="self-outlining", take_up_bound=st.end)  # nothing to take up
    assert not acc and score == -2 and "-2 items are defined (X，謂Y)" in reasons


# T37n1753_p0251c09-c27 (善導, outside every split): the 五門 listing, the 耆闍會's three parts, the summary, then
# 又就前序中復分為二 — a re-division of the first 門, 明其序分, not of the 耆闍會's 序分 nearer the cursor
SHANDAO_REDIVISION = (
    "從此以下就文料簡，略作五門明義：一、從如是我聞下，至五苦所逼云何見極樂世界已來，明其序分。二、從日觀初句佛告韋提汝"
    "及眾生下，至下品下生已來，明正宗分。三、從說是語時下，至諸天發心已來，正明得益分。四從阿難白佛下，至韋提等歡喜已來，"
    "明流通分。此之四義，佛在王宮一會正說。五、從阿難為耆闍大眾傳說，復是一會，亦有三分：一、從爾時世尊足步虛空還耆闍崛"
    "山已來，明其序分。二、從阿難廣為大眾說如上事已來，明正宗分。三、從一切大眾歡喜奉行已來，明流通分。然化必有由，故先明序。"
    "由序既興，正陳所說，次明正宗。為說既周，欲以所說傳持末代，歎勝勸學，後明流通。上來雖有五義不同。略料簡序、正、流通"
    "義竟。又就前序中復分為二：一、從如是我聞一句，名為證信序。二、從一時下至云何見極樂世界已來，正明發起序。"
)
# after T37n1753_p0252c02-c07 (善導, outside every split): 就此眾中 is anaphoric (the node the text is in), not the name
# of an item. The two labels of the original and the lemma's last word are shortened by their final 眾, so the text
# carries no 3-character string that tests/unit/test_sdp_eval_only_guard.py would flag in a tracked file. The item
# 四、從與大比丘下，至而為上首已來，明佛徒眾 that precedes it in the text is left out: as a strong 從A下至B已來
# marker (T8) it would report unmatched-enter, since no listing of the snippet announces it.
SHANDAO_ANAPHOR = (
    "就此眾中，即分為二：一者聲聞，二者菩薩。就聲聞中，即有其九："
    "初言與者，佛身兼眾，故名為與。二者總大。三者相大。四者眾大。五者耆年大。六者數大。七者尊宿大。八者內有實德大。九者果證大。"
)


def test_redivision_of_an_earlier_item_divides_that_item():
    """又就前序中復分為二 divides the 五門's 明其序分 (the former 序, announced first), not a new sibling wrapper and not
    the 耆闍會's 明其序分 nearer the cursor; the item's explained position moves to the re-division."""
    res = parse(snippet_text(SHANDAO_REDIVISION), anchors=[])
    top = res.by_anchor[None]
    assert len(top) == 1 and top[0]["heading_src"] == "五門明義"
    items = top[0]["children"]
    assert [c["heading_src"] for c in items] == ["明其序分", "明正宗分", "正明得益分", "明流通分", "復是一會"]
    xu = items[0]
    assert [c["heading_src"] for c in xu["children"]] == ["證信序", "正明發起序"]
    assert xu["locations"]["commentary"]["explained"] == \
        "X00n0000_p0001a01:%d" % SHANDAO_REDIVISION.index("又就前序中")
    assert xu["children"][0]["_lemma"]["a"] == "如是我聞一句"
    assert [c["heading_src"] for c in items[4]["children"]] == ["明其序分", "明正宗分", "明流通分"]
    assert all(not c["children"] for c in items[4]["children"])
    assert not [d["heading_src"] for d in walk_all(top) if d["_tier2_kind"] == "subject"]
    # nothing to report but the 略料簡序、正、流通義竟 that closes the sorting of the whole 五門 (names no node)
    assert [r["kind"] for r in res.report] == ["unmatched-close"]


def test_anaphoric_jiu_ci_x_zhong_creates_no_node():
    """就此眾中，即分為二 divides the node the text is in (here the snippet's root, so a wrapper headed by the
    announcement); 此 never names an item and the re-division rule does not fire."""
    assert REDIVISION_RE.fullmatch("就此眾中") is None and REDIVISION_RE.fullmatch("又就前序中")
    assert REDIVISION_RE.fullmatch("次就上品中生位中") is None  # 上品中生 is a grade's name, not 上 + X
    res = parse(snippet_text(SHANDAO_ANAPHOR), anchors=[])
    top = res.by_anchor[None]
    assert len(top) == 1 and top[0]["_tier2_kind"] == "wrapper"
    assert [c["heading_src"] for c in top[0]["children"]] == ["聲聞", "菩薩"]
    assert not [d["heading_src"] for d in walk_all(top) if d["_tier2_kind"] == "subject"]
    assert res.report == []


# the 五門 of SHANDAO_REDIVISION reduced to three; %s fills the second item's name and the re-division head
SHANDAO_SAN_MEN = (
    "從此以下就文料簡，略作三門明義：一、從如是我聞下，至云何見極樂世界已來，明其序分。二、從日觀初句佛告韋提汝及眾生下，"
    "至下品下生已來，%s。三、從阿難白佛下，至韋提等歡喜已來，明流通分。上來雖有三義不同。%s："
    "一、從如是我聞一句，名為證信序。二、從一時下至云何見極樂世界已來，正明發起序。"
)


def test_redivision_core_with_several_headings_reports_ambiguous_target():
    """A core (序) contained in two differently named items (明其序分, 明正宗序分) cannot tell them apart: the earliest
    announced is still chosen (前 = the former), and one ambiguous-target entry records the guess."""
    res = parse(snippet_text(SHANDAO_SAN_MEN % ("明正宗序分", "又就前序中復分為二")), anchors=[])
    items = res.by_anchor[None][0]["children"]
    assert [c["heading_src"] for c in items] == ["明其序分", "明正宗序分", "明流通分"]
    assert [c["heading_src"] for c in items[0]["children"]] == ["證信序", "正明發起序"]
    assert not items[1]["children"] and not items[2]["children"]
    assert [r["kind"] for r in res.report] == ["ambiguous-target"]
    assert "「序」" in res.report[0]["reason"] and "明其序分、明正宗序分" in res.report[0]["reason"]
    assert res.report[0]["text"].startswith("又就前序中")
    # one heading among the candidates (the 五門 text above): nothing to report (its 略料簡序、正、流通義竟 names no node)
    assert [r["kind"] for r in parse(snippet_text(SHANDAO_REDIVISION), anchors=[]).report] == ["unmatched-close"]


def test_redivision_ignores_a_lone_part_word_core():
    """就前分中 / 就前文中 / 就前段中 / 於上文中 / 就前科中: 分 / 文 / 段 / 科 is contained in every 明X分 label and names
    no item, so the re-division rule does not fire; the announcement falls to the later rules (here a node headed
    by its own subject) instead of dividing the earliest 明其序分."""
    for subj in ("就前分中", "就前文中", "就前段中", "於上文中", "就前科中", "又就前分之中"):
        assert REDIVISION_RE.fullmatch(subj) is None, subj
    assert REDIVISION_RE.fullmatch("又就前序中") and REDIVISION_RE.fullmatch("就前文分中")
    res = parse(snippet_text(SHANDAO_SAN_MEN % ("明正宗分", "又就前分中復分為二")), anchors=[])
    top = res.by_anchor[None]
    assert [c["heading_src"] for c in top[0]["children"]] == ["明其序分", "明正宗分", "明流通分"]
    assert not [d for c in top[0]["children"] for d in c["children"]]  # no listed item is re-divided
    assert [d["heading_src"] for d in top[1:]] == ["就前分"] and top[1]["_tier2_kind"] == "subject"
    assert not [r for r in res.report if r["kind"] == "ambiguous-target"]


# abridged from T37n1753 p0251c25-p0253b09 (outside every split); the opening listing stands in for 又就前序中
# 復分為二 (Task 7), 細分為七 is cut to its first two items, 禁父緣 to two of its seven. The four items of 化前序 are
# all kept (shortened): with fewer than the announced 四 the listing of 即有其四 would run on into 二、就禁父緣中 and
# swallow it. The last lemma is shortened by its final 眾 (tests/unit/test_sdp_eval_only_guard.py), as in SHANDAO_ANAPHOR.
SHANDAO_RUN = (
    "序中有二：一、證信序。二、正明發起序。"
    "二、就發起序中，細分為二：初、從一時佛在下，至法王子而為上首已來，明化前序。"
    "二、從王舍大城下，至顏色和悅已來，正明發起序禁父之緣。"
    "初、解化前序者。就此序中，即有其四。初、言一時者，正明起化之時。二、言佛者。"
    "三、從在王舍城已下，正明如來遊化之處。四、從與大比丘下，至而為上首已來，明佛徒眾。"
    "廣明化前序竟。"
    "二、就禁父緣中即有其二：一、從爾時王舍大城以下，總明起化處。言起化處者。即有其二。一明闍王起惡。二明如來赴請。"
    "二、從有一太子下，至惡友之教已來，正明闍王怳忽之間，信受惡人所誤。"
    "上來雖有二句不同，廣明禁父緣竟。"
)


def _pos(s: str, needle: str) -> str:
    return "X00n0000_p0001a01:%d" % s.index(needle)


def test_parse_snippet_shandao_entries_items_and_closes():
    """善導 (T1753): 二、就發起序中 enters the listed item by label; 初、解化前序者 (初 as ordinal 1) enters child 1;
    the anaphoric 就此序中，即有其四 divides the cursor (化前序) and opens nothing; 廣明化前序竟 pops the cursor to
    發起序; 二、就禁父緣中 enters child 2 by ordinal + gapped containment (禁父緣 in 正明發起序禁父之緣) and 即有其二
    gives its count; the two 從A下至B已來 items become its children with A至B lemmas, item 2 attaching to 禁父緣
    and not to item 1's 一明…二明… sub-list; the recap close pops back to 發起序."""
    res = parse(snippet_text(SHANDAO_RUN), anchors=[])
    wrapper = res.by_anchor[None][0]
    fqx = wrapper["children"][1]
    assert fqx["heading_src"] == "正明發起序"
    assert fqx["locations"]["commentary"]["explained"] == _pos(SHANDAO_RUN, "二、就發起序中")
    assert [c["heading_src"] for c in fqx["children"]] == ["明化前序", "正明發起序禁父之緣"]
    hqx, jfy = fqx["children"]
    assert hqx["locations"]["commentary"]["explained"] == _pos(SHANDAO_RUN, "初、解化前序者")
    assert hqx["child_count_announced"] == 4
    assert jfy["locations"]["commentary"]["explained"] == _pos(SHANDAO_RUN, "二、就禁父緣中")
    assert jfy["child_count_announced"] == 2
    assert [c["heading_src"] for c in jfy["children"]] == ["總明起化處", "正明闍王怳忽之間，信受惡人所誤"]
    assert jfy["children"][0]["locations"]["root_text"]["raw"] == "爾時王舍大城"
    assert jfy["children"][1]["locations"]["root_text"]["raw"] == "有一太子至惡友之教"
    assert [c["heading_src"] for c in jfy["children"][0]["children"]] == ["明闍王起惡", "明如來赴請"]
    assert res.stats["closes"] == 2
    assert res.stats["enters"] == 6  # 發起序, 化前序, 禁父緣, item 1, 言起化處者 (x_zhe), item 2
    assert not [r for r in res.report if r["kind"] == "unmatched-enter"]
    src = parse(snippet_text(SHANDAO_RUN), anchors=[], config={"heading_style": "source"})
    item1 = src.by_anchor[None][0]["children"][1]["children"][1]["children"][0]
    assert item1["heading_src"] == "一、總明起化處"


def _shape(drafts) -> list:
    """The headings of a draft tree, nested: [(heading, [children …]) …]."""
    return [(d["heading_src"], _shape(d["children"])) for d in drafts]


def _cursors_after_closes(monkeypatch, text: str, **kw):
    """parse(snippet_text(text)) with the cursor's heading and the closes counted by each close statement
    recorded: (result, [(close heading, counted 0/1, cursor heading after it)])."""
    seen = []
    orig = tier2_parser._Machine._close

    def wrapped(self, st):
        before = self.stats["closes"]
        orig(self, st)
        seen.append((st.heading_verbatim, self.stats["closes"] - before, self.cursor.heading))

    monkeypatch.setattr(tier2_parser._Machine, "_close", wrapped)
    return parse(snippet_text(text), anchors=[], **kw), seen


def test_parse_snippet_liaojian_close_counts_and_the_cursor_stays_in_x(monkeypatch):
    """廣料簡X竟 ends the sorting of X, whose items are treated next (p0252b02 廣料簡發起序竟, then 初、解化前序者),
    so the cursor goes to X, not to X's parent (popping would lose X's items: T1753 288 enters -> 219). A 料簡
    close that names a node in the cursor chain is counted; one that names none is reported (unmatched-close),
    not counted, not dropped. The tree is the same with or without either statement."""
    base, _ = _cursors_after_closes(monkeypatch, SHANDAO_RUN)
    named = SHANDAO_RUN.replace("初、解化前序者", "上來雖有二句不同，廣料簡發起序竟。初、解化前序者")
    res, seen = _cursors_after_closes(monkeypatch, named)
    assert seen[0] == ("廣料簡發起序", 1, "正明發起序")
    assert res.stats["closes"] == base.stats["closes"] + 1 == 3
    assert res.stats["enters"] == base.stats["enters"] and res.stats["enters_unresolved"] == 0
    assert _shape(res.by_anchor[None]) == _shape(base.by_anchor[None])
    assert not [r for r in res.report if r["kind"] in ("unmatched-enter", "unmatched-close")]
    none = SHANDAO_RUN.replace("初、解化前序者", "上來雖有二句不同，略料簡甲乙義竟。初、解化前序者")
    res, seen = _cursors_after_closes(monkeypatch, none)
    assert seen[0] == ("略料簡甲乙義", 0, "正明發起序")
    assert res.stats["closes"] == base.stats["closes"] == 2 and res.stats["enters_unresolved"] == 0
    assert [(r["kind"], r["text"][:14]) for r in res.report] == [("unmatched-close", "上來雖有二句不同，略料簡甲乙")]
    assert _shape(res.by_anchor[None]) == _shape(base.by_anchor[None])


def test_parse_snippet_ming_jing_close_found_outside_the_chain_pops_to_the_parent(monkeypatch):
    """廣明X竟 pops to X's parent also when X is not in the cursor chain and is found by label (化前序, a sibling
    of the 禁父緣 the text is in): the cursor goes to 發起序, not into the closed 化前序."""
    text = (SHANDAO_RUN.replace("廣明化前序竟。", "")
            .replace("上來雖有二句不同，廣明禁父緣竟。", "上來雖有四句不同，廣明化前序竟。"))
    res, seen = _cursors_after_closes(monkeypatch, text)
    assert seen == [("廣明化前序", 1, "正明發起序")]
    assert res.stats["closes"] == 1
    # a close that names no node at all is reported, not counted
    res, seen = _cursors_after_closes(monkeypatch, SHANDAO_RUN.replace("廣明化前序竟", "廣明甲乙丙竟"))
    assert seen[0][:2] == ("廣明甲乙丙", 0) and res.stats["closes"] == 1
    assert [r["kind"] for r in res.report] == ["unmatched-close"]


def test_parse_snippet_liaojian_close_found_only_outside_the_chain_is_unmatched(monkeypatch):
    """The same text with 略料簡化前序竟 for 廣明化前序竟: 化前序 is an entered node, but not in the cursor chain, and a
    料簡 close counts only for a node in the chain (docs: design 5.2, formula table): reported `unmatched-close`, not
    counted, the cursor stays where it was (禁父緣's second item), not moved to 化前序."""
    text = (SHANDAO_RUN.replace("廣明化前序竟。", "")
            .replace("上來雖有二句不同，廣明禁父緣竟。", "上來雖有四句不同，略料簡化前序竟。"))
    res, seen = _cursors_after_closes(monkeypatch, text)
    assert seen == [("略料簡化前序", 0, "正明闍王怳忽之間，信受惡人所誤")]
    assert res.stats["closes"] == 0 and [r["kind"] for r in res.report] == ["unmatched-close"]


def test_parse_snippet_jiu_zhong_run_takes_no_item_past_the_announced_count():
    """Rule (3) of _resolve_jiu_zhong appends the next 就X中 sibling to a division made of nothing but that run,
    but not past the division's announced count: 三、就下品中 under 就上輩中，即有其二 is unresolved
    (unmatched-enter), no third child; with 即有其三 it is the third."""
    text = ("就上輩中，即有其二。一、就上品中，亦先舉，次辨，後結。二、就中品中，亦先舉，次辨，後結。"
            "三、就下品中，亦先舉，次辨，後結。")
    res = parse(snippet_text(text), anchors=[])
    top = res.by_anchor[None]
    assert [d["heading_src"] for d in top] == ["上輩"] and top[0]["child_count_announced"] == 2
    assert [c["heading_src"] for c in top[0]["children"]] == ["上品", "中品"]
    assert [(r["kind"], r["text"][:6]) for r in res.report] == [("unmatched-enter", "三、就下品中")]
    assert res.stats["enters_unresolved"] == 1
    res = parse(snippet_text(text.replace("即有其二", "即有其三")), anchors=[])
    assert [c["heading_src"] for c in res.by_anchor[None][0]["children"]] == ["上品", "中品", "下品"]
    assert not res.report and res.stats["enters_unresolved"] == 0


# synthetic after T37n1753 p0261b11 / p0262b18 (the second item of each 觀 is invented): a run of 就X中 under
# a bare stub, with and without the close between the two 觀
JIU_RUN = (
    "就初日觀中，先舉，次辨，後結。即有其二。一、從佛告韋提下，至想於西方已來，正明總告總勸。"
    "二、從云何作想下，至皆見日沒已來，正明辨觀。上來雖有二句不同，廣明日觀竟。"
    "二、就水觀中，亦先舉，次辯，後結。即有其二。一、從次作水想下，至內外映徹已來，總標地體。"
    "二、從見水澄清下，至成琉璃想已來，正明辨觀。"
)


@pytest.mark.parametrize("text", [JIU_RUN, JIU_RUN.replace("上來雖有二句不同，廣明日觀竟。", "")])
def test_parse_snippet_jiu_zhong_run_under_the_stub(text):
    """就初日觀中 (no ordinal, no listing) opens the run under the stub; 二、就水觀中 becomes the stub's child 2
    because the stub's last child was entered by 就X中 — whether or not the close moved the cursor up; the
    method note 先舉，次辨，後結 is no division; the items carry A至B lemmas."""
    res = parse(snippet_text(text), anchors=[])
    top = res.by_anchor[None]
    assert [d["heading_src"] for d in top] == ["初日觀", "水觀"]
    assert [d["child_count_announced"] for d in top] == [2, 2]
    assert [len(d["children"]) for d in top] == [2, 2]
    assert top[1]["children"][0]["locations"]["root_text"]["raw"] == "次作水想至內外映徹"
    assert not [d for d in top for c in d["children"] if c["heading_src"] in ("先舉", "次辨", "後結")]
    src = parse(snippet_text(text), anchors=[], config={"heading_style": "source"})
    assert [d["heading_src"] for d in src.by_anchor[None]] == ["就初日觀中", "二、就水觀中"]


# ------------------------------------------------------------------------------------ 善導's N、從A下 item (fix round 3)


def _span_enters(text: str) -> list:
    from chinese_workflow.outline.tier2.scanner import scan
    return [st for st in scan(text) if st.kind == "enter" and st.formula == "cong-xia-zhi-lai"]


def test_ord_span_takes_no_quotation_marks_titles_or_half_an_end():
    """N、從A下，至B已來，Y: A and B are bare words (CBETA prints 善導's incipits without 「」). A quoted incipit or a
    〈品〉 title is not this idiom, and a 至 after 下 that does not open a whole 至B已來 / 已下 does not leave 至「…」 in
    the heading: the item is no 從A下 span, it falls to the weak numbered item it was before Task 8."""
    from chinese_workflow.outline.tier2.formulae import ORD_SPAN_RE

    ok = ORD_SPAN_RE.match("二、從如是我聞下，至五苦所逼已來，明其序分。")
    assert ok and ok.group("a") == "如是我聞" and ok.group("b") == "五苦所逼" and ok.group("x") == "明其序分"
    ok = ORD_SPAN_RE.match("五、從又有樂器下，至不鼓自鳴已下，正明樓外莊嚴。")  # T1753 p0265b28: 已下 for 已來
    assert ok and ok.group("b") == "不鼓自鳴" and ok.group("x") == "正明樓外莊嚴"
    assert ORD_SPAN_RE.match("二、從善哉已下，正明夫人問當聖意。").group("b") is None
    for bad in ("二、從『如是我聞』已下，至「五苦所逼」已來，序段。",  # quoted A and B
                "二、從如是我聞下，至「五苦所逼」已來，明其序分。",  # quoted B only: x would start 至「…」
                "二、從〈安樂行品〉下，至〈分別功德品〉已來，明流通分。",
                "二、從《法華》下，明序分。",
                "二、從如是我聞下，至五苦所逼，序段。",  # a 至 without 已來
                "二、從此下，至囑累，十一半是淨。",
                "二、從序下，明正宗。"):  # A of one character
        assert ORD_SPAN_RE.match(bad) is None, bad
        assert not _span_enters(bad), bad
    st = [e for e in _span_enters("二、從如是我聞下，至五苦所逼已來，明其序分。")]
    assert [(e.x, e.lemma["raw"]) for e in st] == [("明其序分", "如是我聞至五苦所逼")]


def test_ord_span_is_strong_only_when_a_is_an_incipit_or_the_item_states_its_end():
    """二、從此無間已下，明四正斷 (T42n1828; 56 such items outside T1753 at the time of the review) has no incipit and no
    end: it is the weak marker it was before Task 8 — placed where a division waits for a span item (T1753's
    三、從是為下，總結), but when nothing takes it, neither an unmatched-enter nor a lost state."""
    weak = _span_enters("二、從此無間已下，明四正斷。")
    assert [(e.strength, e.lemma, e.x) for e in weak] == [("weak", None, "明四正斷")]
    assert [e.strength for e in _span_enters("二、從善哉已下，正明夫人問當聖意。")] == ["weak"]
    assert [e.strength for e in _span_enters("二、從如是我聞已下，明序分。")] == ["strong"]  # an incipit
    assert [e.strength for e in _span_enters("二、從像觀下，至雜想觀已來，總明正報。")] == ["strong"]  # an end
    # unplaced: the weak item leaves the bare listing after it attached; the strong one loses the text
    res = parse(snippet_text("二、從此無間已下，明四正斷。" + DEFERRED), anchors=[], mode="self-outlining")
    assert not {"ambiguous-target", "unmatched-enter"} & {r["kind"] for r in res.report}
    assert res.stats["enters_unresolved"] == 0
    assert [d["heading_src"] for d in walk_all(res.by_anchor[None])][-2:] == ["覺義", "不覺義"]
    res = parse(snippet_text("二、從如是我聞已下，明四正斷。" + DEFERRED), anchors=[], mode="self-outlining")
    assert [r["text"][:6] for r in res.report if r["kind"] == "unmatched-enter"][0] == "二、從如是我"
    assert "ambiguous-target" in [r["kind"] for r in res.report] and res.stats["enters_unresolved"] == 2
    # placed: a weak item takes its place in a counted division of span items
    run = ("就水觀中，亦先舉，次辯，後結。即有其二。一、從次作水想下，至內外映徹已來，總標地體。二、從是為下，總結。")
    top = parse(snippet_text(run), anchors=[]).by_anchor[None]
    assert [c["heading_src"] for c in top[0]["children"]] == ["總標地體", "總結"]


def _ming_jing(text: str) -> list:
    from chinese_workflow.outline.tier2.scanner import scan
    return [st.x for st in scan(text) if st.kind == "close" and st.enter_kind == "ming_jing"]


def test_ming_jing_close_needs_the_prefix_or_the_recap_lead():
    """廣明X竟 (T1753) is a close; a bare 解所緣竟 / 辨色聚訖 (the same words are ordinary prose, 357 sentence starts
    over CBETA before this, 39 in T1753) is not. The (廣|總|略) prefix or the 上來雖有N句不同， lead is required, and 辨 /
    辯 only after the prefix."""
    from chinese_workflow.outline.tier2.formulae import MING_JING_RE

    assert MING_JING_RE.match("廣明化前序竟").group("x") == "化前序"  # prefix alone
    m = MING_JING_RE.match("上來雖有七句不同，廣明禁父緣竟")
    assert m and m.group("x") == "禁父緣" and m.group("v") == "廣明"
    m = MING_JING_RE.match("上來雖有七段不同，料簡發起序竟")  # the lead licenses a bare 明 / 解 / 料簡
    assert m and m.group("x") == "發起序" and m.group("v") == "料簡"
    assert MING_JING_RE.match("總料簡下輩三位竟").group("x") == "下輩三位"
    assert MING_JING_RE.match("略辯五門竟").group("x") == "五門"  # 辯 after the prefix
    for bad in ("解所緣竟", "辨色聚訖", "明三聚淨戒竟",  # no prefix, no lead
                "上來雖有五句不同，辨色聚竟",  # the lead does not license a bare 辨
                "上來雖有五句不同，辯色聚竟"):
        assert MING_JING_RE.match(bad) is None, bad
    assert _ming_jing("上來雖有七句不同，廣明禁父緣竟。") == ["禁父緣"]
    assert _ming_jing("廣明化前序竟。解所緣竟。辨色聚訖。") == ["化前序"]


def test_jiu_x_zhong_with_a_short_up_x_is_a_redivision_not_an_entry():
    """就上序中即有其二 points back at the 明其序分 announced earlier (Task 7's re-division, 上 + one or two
    characters), exactly as 又就前序中復分為二 does: it enters nothing (before this round it made a sibling node 上序).
    A grade's name still enters: 上品 / 上輩, and 次就上品中生位中 (T1753; X longer than three characters)."""
    from chinese_workflow.outline.tier2.formulae import jiu_x_zhong_anaphoric
    from chinese_workflow.outline.tier2.scanner import scan

    for x in ("此序", "前序", "上來", "上文", "上序", "上義", "上法"):
        assert jiu_x_zhong_anaphoric(x), x
    for x in ("上品", "上輩", "上品中生", "上品上生", "水觀", "初日觀", "禁父緣"):
        assert not jiu_x_zhong_anaphoric(x), x
    jiu = lambda t: [st.x for st in scan(t) if st.kind == "enter" and st.enter_kind == "jiu_zhong"]
    assert jiu("就上序中即有其二：一、從如是我聞一句，名為證信序。") == []
    assert jiu("二、就上義中，法、喻一對。") == []  # with an ordinal too (X08n0236)
    assert jiu("次就上品中生位中，亦先舉，次辨，後結。即有其二。") == ["上品中生"]
    assert jiu("二、就上品中，亦先舉，次辨，後結。") == ["上品"]
    res = parse(snippet_text(SHANDAO_SAN_MEN % ("明正宗分", "就上序中即有其二")), anchors=[])
    top = res.by_anchor[None]
    assert [d["heading_src"] for d in top] == ["三門明義"]  # no 上序 node beside it
    assert [c["heading_src"] for c in top[0]["children"][0]["children"]] == ["證信序", "正明發起序"]
    assert res.stats["enters"] == 0 and not res.report
    res = parse(snippet_text(SHANDAO_SAN_MEN % ("明正宗分", "次就上品中生位中，亦先舉，次辨，後結。即有其二")), anchors=[])
    assert [d["heading_src"] for d in res.by_anchor[None]] == ["三門明義", "上品中生"]
