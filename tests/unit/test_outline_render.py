"""outline.render: Kurt's independent-outline format (docx + markdown), base and zh-kepan documents.

Design: docs/outliner-design.md §5.7. zh tests use only the synthetic fixture
tests/fixtures/outline-zh/minimal.json; the determinism test also renders the synthetic base
document tests/fixtures/outline-base/minimal-base.json.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
import zipfile

import pytest

from chinese_workflow.common.jsonio import read_json
from chinese_workflow.common.paths import FIXTURES
from chinese_workflow.outline import render

BASE_MINIMAL = FIXTURES / "outline-base/minimal-base.json"
ZH_MINIMAL = FIXTURES / "outline-zh/minimal.json"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


@pytest.fixture(scope="module")
def base_minimal():
    return read_json(BASE_MINIMAL)


@pytest.fixture(scope="module")
def zh_minimal():
    return read_json(ZH_MINIMAL)


def _docx_paragraphs(path) -> list:
    """[(runs [(text, bold, subscript)], w:ind left or None)] of a docx (zipfile + ElementTree)."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.iter(W + "p"):
        runs = []
        for r in p.iter(W + "r"):
            rpr = r.find(W + "rPr")
            bold = rpr is not None and rpr.find(W + "b") is not None
            va = rpr.find(W + "vertAlign") if rpr is not None else None
            sub = va is not None and va.get(W + "val") == "subscript"
            runs.append(("".join(t.text or "" for t in r.iter(W + "t")), bold, sub))
        ind = p.find(W + "pPr/" + W + "ind")
        out.append((runs, ind.get(W + "left") if ind is not None else None))
    return out


def _display(runs) -> str:
    return "".join(t.translate(SUB) if sub else t for t, _, sub in runs)


# ---------------------------------------------------------------------------------------- zh-kepan

ZH_ENTRIES = [
    "[1₁ – Explaining the title][T99n9998_p0001a05, T99n9998_p0001a06] 甲一 一釋題目",
    ("[2₁ – Introduction][T99n9998_p0001a05, T99n9998_p0001b01] 甲二 二序分 "
     "{T99n9999_p0001a01–T99n9999_p0001b02}"),
    ("[2₁1₂ – General introduction][T99n9998_p0001b01, T99n9998_p0001b01] 乙一 初通序 "
     "{T99n9999_p0001a01–T99n9999_p0001a03}"),
    ("[2₁2₂ – Specific introduction][T99n9998_p0001b01, T99n9998_p0001b09] 乙二 後別序 "
     "{T99n9999_p0001a04–T99n9999_p0001b02}"),
    ("[3₁ – Main teaching][T99n9998_p0001a05, T99n9998_p0001c03] 甲三 三正宗分 "
     "{T99n9999_p0001b03–T99n9999_p0002c10}"),
    ("[3₁1₂ – Prose][T99n9998_p0001c03, T99n9998_p0001c04] 乙一 初長行 "
     "{T99n9999_p0001b03–T99n9999_p0002b05}"),
    ("[3₁2₂ – Verses][T99n9998_p0001c03, T99n9998_p0002a11:4] 乙二 後偈頌 "
     "{T99n9999_p0002b06–T99n9999_p0002c10}"),
    ("[4₁ – Dissemination (inferred)][T99n9998_p0002b01, T99n9998_p0002b01] 甲四 "
     "{T99n9999_p0002c11–T99n9999_p0002c20} (inferred, 0.6)"),
]
ZH_META_LINE = ("text: T9999 · scheme: synthetic-fixture · mode: sutra · root text: T99n9999 · "
                "commentary: T99n9998 · gold status: synthetic-fixture")


def test_zh_docx(zh_minimal, tmp_path):
    paras = _docx_paragraphs(render.render_docx(zh_minimal, tmp_path / "zh.docx"))
    front, entries = paras[:4], paras[4:]
    assert front[0][0] == [("合成測試經（SYNTHETIC — not a real text） 科判", True, False)]
    subtitle = "An Outline for Synthetic test sūtra (SYNTHETIC — not a real text)"
    assert _display(front[1][0]) == subtitle
    assert _display(front[2][0]) == ZH_META_LINE
    assert _display(front[3][0]) == render.FORMAT_NOTE_ZH
    assert [_display(runs) for runs, _ in entries] == ZH_ENTRIES
    assert [ind for _, ind in entries] == [None, None, "144", "144", None, "144", "144", None]
    runs = entries[2][0]  # 2₁1₂: values bold, levels bold subscript digits
    assert runs[:5] == [("[", False, False), ("2", True, False), ("1", True, True),
                        ("1", True, False), ("2", True, True)]
    assert all(bold for text, bold, sub in runs if sub)
    assert sum(1 for _, _, sub in runs if sub) == 2


def test_zh_markdown(zh_minimal):
    lines = render.render_markdown(zh_minimal).splitlines()
    assert lines[0] == "# 合成測試經（SYNTHETIC — not a real text） 科判"
    assert ZH_META_LINE in lines and render.FORMAT_NOTE_ZH in lines
    items = [ln for ln in lines if ln.lstrip().startswith("- ")]
    levels = [n["level"] for n in zh_minimal["nodes"]]
    assert items == ["  " * (lv - 1) + "- " + e for lv, e in zip(levels, ZH_ENTRIES)]


def test_zh_entry_variants(zh_minimal):
    """null announced, no position, self-outlining mode (no root span), editorial origin, dagger."""
    doc = copy.deepcopy(zh_minimal)
    n = doc["nodes"][1]
    n["locations"]["commentary"]["announced"] = None
    n["dagger"] = True
    assert render.zh_entry_tail(n, doc["metadata"]) == (
        " – Introduction][T99n9998_p0001b01, T99n9998_p0001b01] 甲二 二序分 "
        "{T99n9999_p0001a01–T99n9999_p0001b02}†")
    e = {**doc["nodes"][0], "locations": {"scheme": "none"}, "origin": "editorial",
         "heading_en": ""}
    assert render.zh_entry_tail(e, doc["metadata"]) == "][—, —] 甲一 一釋題目 (editorial)"
    meta = {**doc["metadata"], "outline_mode": "self-outlining"}
    assert render.root_span(doc["nodes"][2], meta) is None


# ------------------------------------------------------------------------------ determinism, CLI


def test_render_is_deterministic(base_minimal, zh_minimal, tmp_path):
    for name, doc in (("base", base_minimal), ("zh", zh_minimal)):
        a = render.render_docx(doc, tmp_path / f"{name}-a.docx").read_bytes()
        b = render.render_docx(copy.deepcopy(doc), tmp_path / f"{name}-b.docx").read_bytes()
        assert a == b
        assert render.render_markdown(doc) == render.render_markdown(copy.deepcopy(doc))


def test_cli(tmp_path, capsys):
    md, docx = tmp_path / "out" / "outline.md", tmp_path / "out" / "outline.docx"
    assert render.main([str(ZH_MINIMAL), "--md", str(md), "--docx", str(docx)]) == 0
    assert md.read_text(encoding="utf-8") == render.render_markdown(read_json(ZH_MINIMAL))
    assert zipfile.is_zipfile(docx)
    capsys.readouterr()
    assert render.main([str(ZH_MINIMAL)]) == 0
    assert capsys.readouterr().out == render.render_markdown(read_json(ZH_MINIMAL))
