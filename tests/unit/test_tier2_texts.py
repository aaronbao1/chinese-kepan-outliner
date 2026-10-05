"""Tier 2 on whole texts and on the T1718 dev span (raw-gated: each test skips when its CBETA file is not
under data/raw/cbeta/, which is gitignored; scripts/fetch_cbeta*.sh).

  * T1718 dev span (T34n1718_p0001b18..p0016b01; the split guard is asserted): the parser runs, divides
    the sūtra into three at p0002a07, takes up the division announced at p0003a19 there, and enters the
    six-item list announced at p0006a18 at p0007a29 / p0007b04 / p0007c05 / p0008a09. When the eval-only
    sdp gold is present, the dev nodes' explained lines in 卷一上 (the 品 line excluded, tier 1's job) are
    compared line-for-line with ours (locator-only; nothing of the gold but lineheads is read into the
    assertion). Achieved 2026-09-27: 4 of the 4 distinct sdp lines; T10: the 「X」者 units — 27 entered, the
    通序 listing of six, ten arhat names under 列名, ≥ 9 nodes in 卷一下 (from 0), largest leaf < 20 % (from
    55 %). Nothing of the sdp gold is read by that test.
  * T1666 大乘起信論, self-outlining mode (說有五分 / 已說X分。次說Y分, R01 shuo-you-n-fen): one wrapper with
    the five parts, each taken up at its 初說 / 次說 line; 立義分 -> 法 / 義, 義 -> three; 解釋分 -> three;
    the numbered document passes the validator (self-outlining: explained siblings in order); the listings the
    treatise then treats item by item (所言X者 / X者 / 云何修行X門？) are divisions, 4 of the 9 once-rejected
    listings stay rejected (E06 B7).
  * T1775 注維摩詰經: the genre gate says no-structure; the report keeps the filter's rejections and the gated statements, and the evidence counts 什曰 / 肇曰 / 生曰 as collected glosses.
  * T1772 觀彌勒上生兜率天經贊 (Kuiji, 經文。贊曰 units): the gate 五門分別 and the whole-text division
    總有三分 at top level; the five 通序 items taken up at 一時 / 佛 / 住 … lines by 第二、… 第五、.
  * T1753 觀無量壽佛經疏 (從X下至Y明其Z分): the five-part span division, its fifth item divided in three; the 十三觀 of
    卷三 as siblings entered by N、就X中, their items from 一、從A下至B已來, 30 closes (善導's three idioms, E06 B3).
  * X0231 華嚴經疏科文 (chart): chart lines rebuilt into a tree (釋斯鈔序啟以三門 -> 3).
  * Robustness: T1782, T1700, T1724, T1757, T1758, T1735 run without error; every draft is well formed.
Run: cd pipeline && .venv/bin/python -m pytest ../tests/unit/test_tier2_texts.py -q
"""

from __future__ import annotations

import json
import time

import pytest

from chinese_workflow.common.lineheads import is_ref, strip_offset
from chinese_workflow.common.outline_doc import build_prediction, validate
from chinese_workflow.common.paths import RAW, cbeta_xml_path
from chinese_workflow.common.splits import SplitGuard
from chinese_workflow.ingest.text import load_input_text
from chinese_workflow.outline.anchor import listed_only
from chinese_workflow.outline.tier2 import parse

SDP_T1718 = RAW / "dila-sdp" / "gold" / "T1718.zhiyi-wenju-sdp.outline.json"


def need(file_id: str):
    if cbeta_xml_path(file_id) is None:
        pytest.skip("%s not under data/raw/cbeta/ (gitignored)" % file_id)


def pin_anchors(text) -> list:
    return [{"anchor": r["linehead"], "heading_src": m["text"], "part_type": "品"}
            for r in text.lines for m in r["mulu"] if m["type"] == "品"]


def walk(drafts):
    for d in drafts:
        yield d
        yield from walk(d["children"])


def lines_of(drafts) -> set:
    return {strip_offset(d["locations"]["commentary"]["explained"]) for d in walk(drafts)
            if d["locations"]["commentary"]["explained"]}


def well_formed(res, text):
    for drafts in res.by_anchor.values():
        for d in walk(drafts):
            c = d["locations"]["commentary"]
            assert d["heading_src"], d
            assert c["explained"] is None or is_ref(c["explained"]) and text.contains(c["explained"])
            assert c["announced"] is None or is_ref(c["announced"])
            assert d["node_class"] in ("sutra-span", "commentary-internal")
            assert d["origin"] == "explicit" and d["confidence"] == 1.0
            rt = d["locations"]["root_text"]
            assert rt is None or (rt["basis"] == "lemma" and rt["start"] is None and rt["raw"])
            assert d["node_class"] == "sutra-span" or rt is None
            for part in d["evidence"].split(" | "):
                lh, _, line = part.partition(": ")
                assert text.index.line_text(lh) == line
    for r in res.report:
        assert set(r) == {"id", "linehead", "offset", "kind", "text", "reason"}
    assert res.genre_gate["decision"] in ("outline", "no-structure")


# ------------------------------------------------------------------------------------ T1718 dev


DEV = ("T34n1718_p0001b18", "T34n1718_p0016b01")


@pytest.fixture(scope="module")
def t1718():
    need("T34n1718")
    text = load_input_text("T34n1718", span=DEV, role="commentary")
    assert SplitGuard().check_lines([r["linehead"] for r in text.lines]) == {"dev"}
    return text, parse(text, anchors=pin_anchors(text))


def test_t1718_dev_runs(t1718):
    text, res = t1718
    well_formed(res, text)
    assert res.genre_gate["decision"] == "outline"
    assert res.stats["nodes"] >= 25


def test_t1718_dev_divisions(t1718):
    _, res = t1718
    drafts = [d for v in res.by_anchor.values() for d in v]
    three = [d for d in drafts if strip_offset(d["locations"]["commentary"]["explained"])
             == "T34n1718_p0002a07"]
    assert three and three[0]["child_count_announced"] == 3
    first = three[0]["children"][0]
    assert strip_offset(first["locations"]["commentary"]["explained"]) == "T34n1718_p0003a19"
    six = [d for d in walk(drafts) if d["child_count_announced"] == 6]
    assert six
    entered = [strip_offset(c["locations"]["commentary"]["explained"]) for c in six[0]["children"]]
    for lh in ("T34n1718_p0007a29", "T34n1718_p0007b04", "T34n1718_p0007c05", "T34n1718_p0008a09"):
        assert lh in entered


def test_t1718_dev_lemma_gloss_units(t1718):
    """Zhiyi's 「X」者 take-ups (E06 review B6): the shape of the dev outline with no gold read. The
    parser's heading_style here is 'label' (五列名 -> 列名)."""
    text, res = t1718
    nodes = list(walk([d for v in res.by_anchor.values() for d in v]))
    entered = [d for d in nodes if any("(lemma_zhe)" in n for n in d["notes"])]
    assert len(entered) >= 20, [d["heading_src"] for d in entered]
    # no gloss unit is made of a title word, the citation fragment or the story aside (label style: 初序 is
    # headed 序 by the 三分 division, not by a gloss)
    assert not {d["heading_src"] for d in entered} & {"序", "品", "三摩耶是假時", "難陀、跋難陀"}
    assert [r["text"] for r in res.report if r["kind"] == "lemma-gloss-at-stub"] == ["「序」者", "「品」者"]
    # today's audit counters: weak markers that named a taken-up node inside a gloss unit (mentions, not
    # moves) and glosses repeating a taken-up item (no dev gloss does)
    assert res.stats["weak_mentions"] == 8 and res.stats["gloss_repeats"] == 0
    tong = next(d for d in nodes if d["heading_src"] == "通序")
    kids = [c["heading_src"] for c in tong["children"]]
    assert kids[:6] == ["如是", "我聞", "一時", "佛", "王城耆山", "與大比丘"]
    assert {"住", "中", "同聞眾"} <= set(kids[6:]), kids
    by = {c["heading_src"]: c for c in tong["children"]}
    assert strip_offset(by["如是"]["locations"]["commentary"]["explained"]) == "T34n1718_p0003a25"
    assert [c["heading_src"] for c in by["我聞"]["children"]] == ["聞"]
    assert [c["heading_src"] for c in by["王城耆山"]["children"]] == ["王舍城", "耆闍崛山"]
    assert listed_only(by["王城耆山"])
    lei = next(d for d in nodes if d["heading_src"] == "類")
    assert [c["heading_src"] for c in lei["children"]] == ["大", "比丘", "眾"]
    tan = next(d for d in nodes if d["heading_src"] == "歎")
    assert [c["heading_src"] for c in tan["children"]] == ["諸漏已盡，無復煩惱", "逮得己利", "盡諸有結，心得自在"]
    assert [c["extent_announced"] for c in tan["children"]] == [None, "一句", "兩句"]
    assert [c["heading_src"] for c in tan["children"][2]["children"]] == ["心得自在"]
    names = next(d for d in nodes if d["heading_src"] == "列名")
    assert [c["heading_src"] for c in names["children"]] == [
        "憍陳如", "摩訶迦葉", "優樓頻蠡", "那提", "伽耶", "舍利弗", "大目揵連", "摩訶迦栴延", "阿㝹樓馱", "劫賓那"]
    assert [c["heading_src"] for c in names["children"][0]["children"]] == ["阿若"]
    assert all(c["locations"]["root_text"]["raw"] == c["heading_src"] for c in names["children"])
    lower = [d for d in nodes if d["locations"]["commentary"]["explained"]
             and "T34n1718_p0009b07" <= strip_offset(d["locations"]["commentary"]["explained"]) < "T34n1718_p0016b02"]
    assert len(lower) >= 9, [d["heading_src"] for d in lower]
    # the largest stretch with no node start (the commentary-target leaf) < 20 % of the span
    starts = sorted({text.offset(d["locations"]["commentary"]["explained"]) for d in nodes
                     if d["locations"]["commentary"]["explained"] and not listed_only(d)})
    gaps = [b - a for a, b in zip(starts, starts[1:] + [len(text.text)])]
    assert max(gaps) / len(text.text) < 0.20, max(gaps)


def test_t1718_dev_locators_vs_sdp(t1718):
    """Locator-only comparison with the eval-only sdp gold's dev nodes in 卷一上 (lineheads only)."""
    if not SDP_T1718.exists():
        pytest.skip("sdp gold absent (eval-only, gitignored)")
    _, res = t1718
    nodes = json.loads(SDP_T1718.read_text(encoding="utf-8"))["nodes"]
    gold = set()
    for n in nodes:
        e = strip_offset(((n.get("locations") or {}).get("commentary") or {}).get("explained"))
        if e and "T34n1718_p0001b18" <= e < "T34n1718_p0009b07" and n["level"] > 1:
            gold.add(e)
    ours = lines_of([d for v in res.by_anchor.values() for d in v])
    assert len(gold & ours) >= 4, (len(gold & ours), len(gold))


# ------------------------------------------------------------------------------------ T1666


@pytest.fixture(scope="module")
def t1666():
    need("T32n1666")
    text = load_input_text("T32n1666")
    return text, parse(text, anchors=[], mode="self-outlining")


def test_t1666_five_parts(t1666):
    text, res = t1666
    well_formed(res, text)
    top = res.by_anchor[None]
    assert len(top) == 1 and top[0]["child_count_announced"] == 5
    parts = top[0]["children"]
    assert [p["heading_src"] for p in parts] == ["因緣分", "立義分", "解釋分", "修行信心分", "勸修利益分"]
    for p in parts:  # each taken up at the line of its 初說 / 次說 marker
        lh = strip_offset(p["locations"]["commentary"]["explained"])
        assert text.index.line_text(lh).startswith(("初說", "次說")), (p["heading_src"], lh)
    by = {p["heading_src"]: p for p in parts}
    assert [c["heading_src"] for c in by["立義分"]["children"]] == ["法", "義"]
    assert len(by["立義分"]["children"][1]["children"]) == 3
    assert [c["heading_src"] for c in by["解釋分"]["children"]] == ["顯示正義", "對治邪執", "分別發趣道相"]
    assert len(by["因緣分"]["children"]) == 8


def test_t1666_validates(t1666):
    _, res = t1666
    doc, _ = build_prediction(
        res.by_anchor[None], text_id="T32n1666", text_title_src="大乘起信論",
        outline_mode="self-outlining", root_text_id="T32n1666", commentary_id=None, scheme_id="self",
        source_file="data/raw/cbeta/xml-p5/T/T32/T32n1666.xml",
        source_document={"kind": "root-text", "text_id": "T32n1666", "title": "大乘起信論"},
        generated_by="tests/unit/test_tier2_texts.py", format_note="tier-2 drafts, self-outlining")
    rep = validate(doc)
    assert not rep.errors, [(e.code, e.message) for e in rep.errors[:5]]


def test_t1666_takes_up_the_treated_listings(t1666):
    """E06 B7: a listing the treatise then treats item by item is a division (taken_up), and a count question
    that opens the next sentence lists its items (此識有二種義 p0576b10, 修行有五門 p0581c14). The four 有N種 listings
    that define their items inline stay rejected (inline-treated items are a separate decision)."""
    _, res = t1666
    assert sorted(r["linehead"] for r in res.rejected) == [
        "T32n1666_p0577c07", "T32n1666_p0578a27", "T32n1666_p0578b15", "T32n1666_p0580c18"]
    assert res.stats["nodes"] >= 60
    by = {}
    for d in walk(res.by_anchor[None]):
        by.setdefault(d["heading_src"], d)
    kids = lambda h: [c["heading_src"] for c in by[h]["children"]]  # noqa: E731
    assert kids("心生滅門") == ["覺義", "不覺義"]
    assert kids("覺與不覺") == ["同相", "異相"]
    assert kids("我見") == ["人我見", "法我見"]
    assert kids("略說發心") == ["信成就發心", "解行發心", "證發心"]
    assert kids("修行") == ["施門", "戒門", "忍門", "進門", "止觀門"]
    men = by["修行"]
    assert "count_mismatch" not in men["flags"]
    lines = [strip_offset(c["locations"]["commentary"]["explained"]) for c in men["children"]]
    assert lines == sorted(lines) and len(set(lines)) == 5  # each 門 taken up at its own 云何修行X門？ line
    unresolved = [r["text"] for r in res.report if r["kind"] == "unmatched-enter"]
    assert unresolved == ["所言空者", "所言不空者", "所言止者", "所言觀者"]
    # a resolved 所言X者 takes its item up at the marker: 覺義 / 不覺義 of 此識有二種義 (p0576b10)
    assert by["覺義"]["locations"]["commentary"]["explained"] == "T32n1666_p0576b11:17"
    assert by["不覺義"]["locations"]["commentary"]["explained"] == "T32n1666_p0576c29:18"


# ------------------------------------------------------------------------------------ other texts


def test_t1775_genre_gate():
    need("T38n1775")
    text = load_input_text("T38n1775")
    res = parse(text, anchors=pin_anchors(text))
    assert res.genre_gate["decision"] == "no-structure"
    assert all(v == [] for v in res.by_anchor.values())
    assert "注維摩詰經" in res.genre_gate["evidence"]
    ev = res.genre_gate["evidence"]
    assert "attributions (X曰：/ X云：)" in ev and "collected glosses" in ev and "肇" in ev
    assert "glossator" not in ev
    assert len(res.rejected) >= 50 and all(set(r) == {"linehead", "offset", "text", "reason"} for r in res.rejected)
    kinds = {r["kind"] for r in res.report}
    assert {"gated-announcement", "gated-enter", "gated-close"} <= kinds
    assert res.stats["nodes"] == 0 and res.stats["gated_closes"] >= 30


def test_t1772_kuiji_units():
    need("T38n1772")
    text = load_input_text("T38n1772")
    res = parse(text, anchors=[])
    well_formed(res, text)
    gate, three = res.by_anchor[None][:2]
    assert gate["node_class"] == "commentary-internal" and gate["child_count_announced"] == 5
    assert [c["heading_src"] for c in three["children"]] == ["說經因起分", "發請廣說分", "聞名喜行分"]
    tongxu = next(d for d in walk([three]) if d["heading_src"] == "通序")
    lines = [strip_offset(c["locations"]["commentary"]["explained"]) for c in tongxu["children"]]
    assert lines[1:] == ["T38n1772_p0280c19", "T38n1772_p0281a22", "T38n1772_p0281b09",
                         "T38n1772_p0281c24"]


def test_t1753_span_division():
    need("T37n1753")
    text = load_input_text("T37n1753")
    res = parse(text, anchors=[])
    well_formed(res, text)
    five = next(d for d in walk(res.by_anchor[None]) if d["heading_src"] == "五門明義")
    labels = [c["heading_src"] for c in five["children"]]
    assert labels[:4] == ["明其序分", "明正宗分", "正明得益分", "明流通分"]
    assert five["children"][4]["child_count_announced"] == 3
    # 又就前序中復分為二 (p0251c25) re-divides the first 門; 二、就發起序中，細分為七 (p0252a21) its second item
    xu = five["children"][0]
    assert [c["heading_src"] for c in xu["children"]] == ["證信序", "正明發起序"]
    assert strip_offset(xu["locations"]["commentary"]["explained"]) == "T37n1753_p0251c25"
    assert len(xu["children"][1]["children"]) == 7
    assert not [d for d in walk(res.by_anchor[None]) if d["heading_src"] in ("就前序", "又就前序中")]


GUAN = ["初日觀", "水觀", "地想觀", "寶樹觀", "寶池觀", "寶樓觀", "華座觀", "像觀", "真身觀", "觀音觀", "勢至觀", "普觀",
        "雜想觀"]


def test_t1753_shandao_idioms():
    """善導's three idioms on the whole 疏 (E06 review B3): the 十三觀 of 卷三 are entered by N、就X中 as siblings
    of one parent — with anchors=[] (no 卷 anchors) that parent is 卷一's 七門料簡 wrapper (announced 七, four 門
    entered, 17 children in the end: the residual of the run's count guard, design 5.2; the anchored build is
    unaffected); 普觀's six 一、從A下至B已來 items are all its children; 水觀 finds 5 of 6 (its item 3, 三、從瑠璃地上下,
    opens right after a verse quoted as 『…』」 with no 。 before the 」, which _sentence_starts does not read as a
    sentence start: a residual); 地想觀's item 1, 一、從此想成時者, has no 下 and is no span item; 先舉／次辨／後結 is
    no division; the closes resolve. Achieved 2026-10-03 (anchors=[]): 288 enters (7 unresolved: 三、從在王舍城已下 and
    四、從與大比丘下 of 化前序 in a listing that mixes 初、言X者, 二、從像觀下, 第二福者, 三、就得益分中 + 三、從應時
    即見極樂已下, 五、就耆闍會中; a weak item that nothing takes, 二、從韋提已下, is no longer one of them), 30 closes (38
    廣X竟 statements: 廣料簡發起序竟 counts and leaves the cursor in 發起序; 地觀, 序、正、流通義, 定善一門義, 上輩三品
    義意, 中輩三品, 下輩三位, 得益分, 耆闍分 name no node in the chain and are reported `unmatched-close`), 659 nodes."""
    need("T37n1753")
    text = load_input_text("T37n1753")
    res = parse(text, anchors=[])
    well_formed(res, text)
    drafts = res.by_anchor[None]
    parents = [d for d in walk(drafts)
               if [c["heading_src"] for c in d["children"] if c["heading_src"] in GUAN] == GUAN]
    assert len(parents) == 1, [h for h in GUAN if not any(d["heading_src"] == h for d in walk(drafts))]
    pu = next(c for c in parents[0]["children"] if c["heading_src"] == "普觀")
    assert strip_offset(pu["locations"]["commentary"]["explained"]) == "T37n1753_p0269b22"
    assert pu["child_count_announced"] == 6 and len(pu["children"]) == 6
    shui = next(c for c in parents[0]["children"] if c["heading_src"] == "水觀")
    assert shui["child_count_announced"] == 6 and len(shui["children"]) >= 5
    assert shui["children"][0]["locations"]["root_text"]["raw"] == "次作水想至內外映徹"
    assert not any(d["heading_src"] in ("先舉", "次辨", "後結") for d in walk(drafts))
    assert res.stats["closes"] >= 30 and res.stats["enters"] >= 288 and res.stats["enters_unresolved"] <= 7


def test_x0231_chart():
    need("X05n0231")
    text = load_input_text("X05n0231")
    res = parse(text, anchors=[])
    top = res.by_anchor[None]
    head = next(d for d in top if d["heading_src"] == "釋斯鈔序啟以三門")
    assert [c["heading_src"] for c in head["children"]] == ["題目", "撰人", "本文"]
    assert res.stats["nodes"] > 1000


@pytest.mark.parametrize("file_id", ["T38n1782", "T33n1700", "T34n1724", "T37n1757", "T37n1758",
                                     "T35n1735"])
def test_runs_on_other_commentaries(file_id):
    need(file_id)
    text = load_input_text(file_id)
    t0 = time.time()
    res = parse(text, anchors=pin_anchors(text))
    assert time.time() - t0 < 60
    well_formed(res, text)
    assert res.stats["nodes"] > 0 and res.genre_gate["decision"] == "outline"


def test_unbracketed_incipit_is_kept_as_lemma():
    """善導's 從A下，至B已來 (T1753, printed by CBETA without 「」) keeps A至B as the node's lemma, so
    the anchor can place it in the root text; chapter or section names stay locators only."""
    from chinese_workflow.outline.tier2.labels import clean_label

    s = "從如是我聞下，至五苦所逼云何見極樂世界已來，明其序分。"
    lab = clean_label(s, 0, len(s))
    assert lab["label"] == "明其序分"
    assert lab["lemma"]["a"] == "如是我聞" and lab["lemma"]["b"] == "五苦所逼云何見極樂世界"
    assert lab["lemma"]["unbracketed"] is True
    s = "從序至〈安樂行〉十四品，約迹開權顯實；"
    lab = clean_label(s, 0, len(s))
    assert lab["label"] == "約迹開權顯實" and lab["lemma"] is None
