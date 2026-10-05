# tests/fixtures/kepan-formulae/

Labelled cases for the tier-2 explicit-division parser (the stateful rule parser in
`pipeline/src/chinese_workflow/outline/tier2/` that detects kēpàn division statements in commentary prose).
`cases.jsonl` holds 148 cases, one JSON object per line. `tests/unit/test_kepan_cases.py` checks the cases
themselves, and `tests/unit/test_tier2_cases.py` runs the parser on them.

Every `text` was cut from `chinese_workflow.ingest.lines` output over the CBETA 2026R2 files in
`data/raw/cbeta/` (T1718, T1721, T1723, T1724, T1735) and `data/raw/cbeta/xml-p5/**` (the rest), between a
start and an end string taken from the same output. No Chinese was typed by hand. CBETA's punctuation is kept.
Built 2026-09-22 by Claude (Opus 5.5), with cases added after the E06 review (the sections below that cite it);
**the labels are a machine draft, not yet reviewed by a person.**

## Review first

These cases carry the most judgment. Review them before the rest (list from the build, re-checked against
`cases.jsonl` 2026-09-22; the label-rule rows added in the final review of the branch):

| Case(s) | What to check |
|---|---|
| `pos-you-n-02` | 有五，合為三類 read as 3 children (the five speakers in three classes); heading 明神呪之方 with no ordinal written; anaphor 此初聖 enters the first member of child 1 (`anaphor_path` [1, 1]) |
| `pos-zanyue-lemma-05` | 下二天 opens child 2 of the three classes, but 中初文有三 divides its first member (毘沙門), one level below the heading (`applies_to` [1]) |
| `pos-you-n-04` | the 有三 list attaches to the last child of the preceding 有七 list (七佛讚揚), not to 十神 |
| `pos-zhong-you-n-ju-01`, `pos-zhong-you-n-ju-02` | children in document order, not in the order the text lists them (listed 初、後、中間 and 初總、後結、中十別) |
| `neg-wen-wei-n-01` | the 列數者 list of four interpretive modes inside child 1 of 文為四: a list, not a division (R07 F2) |
| `neg-you-n-03`–`neg-you-n-05` (T1724), `neg-you-n-07`–`neg-you-n-10` (T1721), `neg-you-n-11`–`neg-you-n-14` (T1782) | 「有N」 lists read as doctrine (kinds or senses of a term), not as divisions of the text |
| `pos-jiu-you-n-03`, `pos-chu-zhong-yi-n-05` | label rule vs meaning: the rule keeps what follows a comma, so label 1 of jiu-you-n-03 carries the extent 文有十句 and label 1 of chu-zhong-yi-n-05 the old-translation note 舊有二頌. Decide whether an extent or a note after the name belongs in the label (then say so in the rule) or not (then trim the labels) |
| `pos-chu-zhong-yi-n-06` | label rule item 1 splits at every ordinal word 一…十, but both labels keep 三 inside a term (三自性, 三無性). Decide whether a numeral that begins a term is an ordinal (rule 1 as written) or not (then say so in the rule) |
| `pos-da-fen-wei-n-01` | label 4 keeps the reason clause 為順經文有四分故, which contains a count (有四分) that rule 1 would read as a nested announcement ending the item. Decide where item 4 ends |
| `pos-cong-xia-zhi-fen-01` | label 5 (復是一會) is what rule 2 leaves once the locator 從…傳說 is removed; the meaning (Ānanda's retelling to the assembly on the mountain) is in the removed part. Decide whether rule 2 applies when the locator is the whole content |
| `pos-lemma-zhe-05`, `neg-lemma-zhe-02` | the listing-run rule (six one-clause glosses = the listing of 通序為五或六或七; the seventh, 又「如是」者, is the take-up) and the title-word rule (序 / 品 / 經 / 卷) are read from the T1718 dev span alone (E06 review B6); check that 「王城耆山」 (comma form, no 者) belongs to the run and that 中 (「中」者 p0005c28, after a sentence with 云：「) must stay a unit |
| `pos-da-fen-wei-n-03` | the text has 今初 twice: the leading one enters child 1 of the preceding division, the closing one is this case's `anaphor`. The test checks only that the anaphor is a substring; say which occurrence is meant (e.g. an offset) |

**Case ids.** The negatives were renumbered once, in fix round 1 of the build. Freeze the ids once a reviewer
has checked the cases. From then on a correction changes `expected` or `why`, never an id; a new case takes a new
number, and a withdrawn id is not reused. Parser test results refer to the ids.

## Fields

| Field | Meaning |
|---|---|
| `id` | `pos-<formula>-NN` (division), `neg-<formula>-NN` (not-division), `gate-<formula or source>-NN` (genre-gate), `close-<formula>-NN` (closing marker). Unique. |
| `kind` | `division`: the text states a kēpàn division (it announces children, or opens one node). `not-division`: the text matches a formula on the surface but divides no text, e.g. a doctrinal 「有N」 list. `genre-gate`: 註-genre text (T1775 注維摩詰經) where the parser should emit no division structure at all, whatever the surface. `close`: the text closes a node (上來雖有N句不同，廣明X竟); the parser must emit a closing statement naming X and no division. |
| `formula` | Slug of the formula the case exercises (tables below). For negatives and genre-gate cases it is the formula the text would falsely trigger; `null` only for genre-gate cases that match no formula. |
| `source` | CBETA text id, e.g. `T1723`, `X0577`. |
| `linehead` | CBETA linehead of the line where `text` starts (schema grammar, e.g. `T34n1723_p0850a20`). |
| `text` | Verbatim reading text as `ingest.lines` gives it (inline notes included, line breaks dropped). May run over several lines. |
| `expected` | `null` unless `kind` is `division` or `close`. For `division`: `{child_count, labels, anaphor}` plus the optional `heading`, `ordinal`, `lemma`, `applies_to`, `anaphor_path`, `opens`. For `close`: `{close}`. |
| `why` | One line: what the case tests. |
| `mode` | Optional. `"self-outlining"` when the case is a root-text treatise outlining itself (T1666); the detectors run in that mode. Default `"sutra"`. |

`expected` for divisions:

- `child_count`: number of children the statement announces, i.e. what the parser should emit. It is not always the
  numeral written: 「有二十句，初二略明、後二總結、中間廣歎」 has 3 children (二十句 counts lines), 「有五，合為三類」 has 3.
  `null` when the statement announces no children (a heading such as 三「在摩竭」下，處成就也, or 已說因緣分。次說立義分).
- `labels`: the children's labels by the label rule below, in document order of the children (not listing order:
  初…後…中間… lists 1, 3, 2); `[]` when the statement lists none. When non-empty, its length equals `child_count`.
- `anaphor`: the entry marker after the listing that says which node the text is now in (今初, 此初, 此初也, 此初文也,
  此初聖), verbatim; `null` if the case has none.
- `anaphor_path` (optional): 1-based child indices from the announced division down to the node the anaphor enters.
  Omitted when it is `[1]` (the first child), the usual case. pos-you-n-02 has `[1, 1]`: 此初聖 enters the first 聖
  of the first child 二聖.
- `heading` / `ordinal` / `lemma` (optional): for statements that open a node — its title by the label rule, its
  sibling number only when written (下明… and 下二天 write none), and the root-text lemma cited (the incipit before
  下, or the 經「A至B」 span), verbatim. `"ordinal": null` says that none is written (次下先就上品上生位中). For 善導's
  unbracketed spans 從A下，至B已來 (T1753) the lemma is A至B — what the anchor receives — or A when no end is given.
- `applies_to` (optional): 1-based child indices from the node the statement opens to the node whose children are
  announced; omitted when the children belong to that node itself. pos-zanyue-lemma-05 has `[1]`: 下二天 opens 二天,
  and 中初文有三 divides its first member (毘沙門), not 二天.
- `opens` (optional, `false`): no strong entry marker opens a node in this text; the division belongs to the
  node the text is already in (就此序中，即有其四: 此 is an anaphor). Checked only when present.
- `close` (kind `close` only): the name X the closing formula gives (廣明禁父緣竟 -> 禁父緣), verbatim.

### Label rule

A label (and a `heading`) is one verbatim, contiguous piece of `text`, found as follows.

1. Items: the listing is split at each ordinal word (一…十, 一者, 第一, 品第三段, 初, 次, 後, 先, 餘, 中間, 中) or, in
   unnumbered lists, at 、. An item ends at the next ordinal, at 。 or ；, or where a nested announcement (有N, 分N, 為N)
   starts; commas do not end an item.
2. From the front of the item remove: the ordinal word and the punctuation after it; a pointer word 此 / 下 ('below');
   a locator — a lemma incipit with 下／以下／已下 (「純陀」下, 文云下), a span 從…(下)(至／訖／竟／盡／乃至)…(已來／以來),
   始於…訖…, or a count of lines, verses or 品 with the punctuation after it (四行, 二句, 三頌, 七頌半, 有八句, 十九句,
   此十三品, 疏末一偈); then a copula joining locator and name (為, 名, 是, 是其).
3. From the end remove a final 也 and the punctuation.
4. Charts: the inline note (child count or incipit) is not part of the label. Uddānas: the metrical fillers 與, 及,
   最為後, 分別 and the closing 略辯相應知 are dropped.
5. Everything else stays: 明／明其／正明／說, 者, internal commas, clauses inside the item (so pos-jiu-zhong-02 has
   明順戒，則三寶住持，辨比丘事 and pos-fen-wei-n-cong-zhi-03 keeps the description before 自利).

The test checks what it can: every label, heading, lemma and anaphor is an exact substring of `text`; labels and
headings do not start or end with punctuation, do not end in 也, and do not start with an ordinal word.

## Splits (`data/EVAL-SETS.md`, rule 5)

Spans are CBETA lineheads, start inclusive, end exclusive. Cases and fixtures may quote only the dev spans of
T1718 and T1723, or other texts:

| Text | dev (allowed) | validation | test | reserve |
|---|---|---|---|---|
| T1718 | `T34n1718_p0001b18`–`T34n1718_p0016b02` | `T34n1718_p0016b02`–`T34n1718_p0036a26` | `T34n1718_p0036a26`–`T34n1718_p0063b11` | `T34n1718_p0063b11` to the end |
| T1723 | `T34n1723_p0850a19`–`T34n1723_p0850b20` (陀羅尼品) | — | `T34n1723_p0651a06`–`T34n1723_p0694b22`; `T34n1723_p0734b07`–`T34n1723_p0737b04` | everything else |

The test encodes these spans and, with raw XML present, enforces three things: a T1718/T1723 case starts
(always) and ends inside dev; **no case shares more than 8 consecutive characters (punctuation ignored) with the
T1718 validation/test or T1723 test spans** (`SHARED_RUN_MAX`; the largest now is 8, 位四歎德五列名六 in
pos-jiu-kai-wen-wei-n-01, then 7, stock formulae such as 以六門料簡一敘); and no case from another text is a
verbatim copy of T1718/T1723 text outside dev. With the reserve spans the largest shared run is 13, all stock
formulae or stock doctrinal lists (三門分別一來意二釋名三解妨 is the dev-span gate itself; 略以五門分別一出體二釋名三 in T1724).

Sources avoided because they reproduce T1718/T1723 text: T1719 法華文句記 and X0596 妙經文句私志記 (sub-commentaries
on 法華文句), X0584's 文句科文 (from `X27n0584_p0686a01`, a chart of T1718's divisions; the X0584 case is from its
玄義科文, `X27n0584_p0551a01`–), and X0594 法華經疏義纘 (its survey of earlier divisions was not checked against
T1723, so it is left out). T1724 法華玄贊義決 is a sub-commentary on T1723; its cases pass the checks above.

## R01 formula rows

The rows of the table "Explicit division formulae observed" of research thread R01 (F3, F13, F21–F24),
restated here because the research notes are not part of this repository. Row 3 is split in two because F24
says the parser should key on 就…又N, not 就中.

| Slug | R01 row | Positives (source ×n) |
|---|---|---|
| `wen-wei-n` | 文為N：一、…；二、… | T1718 ×2 (dev), T1721 |
| `fen-wei-n-cong-zhi` | 分為N：從…至… (span) | T1718 (dev), T1746, T1798 |
| `jiu-you-n` | 就X又N，初…次… (F24) | T1721 ×2, T1735 |
| `jiu-zhong` | 就中初…次… (same row, second form) | T1721, T1804 ×2 |
| `jiu-kai-wen-wei-n` | 就X開文為N：一、…；二、… | T1721, T1744, T1699 |
| `zhong-you-n` | X中有N：一…，二… (also R07 F17's 中有N) | T1723 (dev), T1724, T1721 |
| `chu-zhong-yi-n` | 初中亦二 ／ 二中復N (nested; also R07 F17's 初中 and N中) | T1735 ×3, T1772, T1782, T1830 |
| `ordinal-lemma-xia` | 序號 + 「lemma」下 + 標題 | T1735 ×3 |
| `wen-you-n-fen` | 文有N分 | T1735 ×2, T1759 |
| `zhong-you-n-ju` | X中，有N句，初…後…中間… | T1735 ×2, T1782 |
| `da-fen-wei-n` | 大分為N：一…；二「lemma」下…；三…; 今初 | T1736 ×2, T1735 |
| `wen-bie-you-n` | 文別有N：一者…、二「lemma」下…分 | T1764, T1745 ×2 |
| `cong-xia-zhi-fen` | 從X下至Y明其Z分 (span) | T1753 ×4 (04: 又就前序中 re-division, 2026-10-03) |
| `zong-you-n-fen` | 總有N分：一、…；二、… (Indian śāstra; also 略有N分) | T1530 ×2, T1772 |
| `shuo-you-n-fen` | 說有N分 ／ 已說X分。次說Y分 (root-text self-outline) | T1666 ×2, T1667 |
| `fan-you-n-duan` | 凡有N段：始於…訖… (span) | X0577, T1763 ×2, T1721 (凡有二種 whose kinds are then given 品 ranges) |
| `chart-note` | Chart: heading + inline note (child count on non-leaves, incipit on leaves) + nested items | X0231 ×2, X0584 |
| `uddana` | 嗢拕南曰 (uddāna) | T1579 ×3, T1602 (count head 何等十六, closing phrase 名十六異論) |

Every row has at least two positives in allowed sources.

## Kuiji variants (R07 F17, R03 F25)

The announcement variants R07 F17 counted over T1723 and the formulas R03 F25 quotes. Allowed Kuiji-style
sources: the T1723 dev span (陀羅尼品) and T1724 (慧沼's sub-commentary on T1723); where those have fewer than two,
positives come from other works of Kuiji (T1700, T1757, T1758, T1772, T1782, T1829, T1830) or Huizhao (T1832),
which rule 5 does not restrict. Searches (regex over `ingest.lines` text; T1723 over its dev span only):
N中／後中 and 今初 over all 17 T-canon works CBETA credits to 窺基 (T1695, T1700, T1710, T1723, T1757, T1758, T1772,
T1782, T1816, T1829, T1830, T1831, T1834, T1835, T1836, T1840, T1861) and the 7 credited to 慧沼 (T1724, T1788,
T1802, T1841, T1842, T1862, T1863); N門料簡 and 今為N解 over all of T33–T45; the other variants over T1700, T1710,
T1757, T1772 and T1782, where two positives were found. "Attested" means used as a division.

| Variant | Slug | T1723 dev span | T1724 | Positives |
|---|---|---|---|---|
| 分為N (F17) | `fen-wei-n` | no | only 加行位分為三品 (a grading; negative) | T1772 ×2 |
| bare 分N (F17) | `fen-n` | 品文分三 | no | T1723, T1782 |
| 有N (F17) | `you-n` | yes, several | 31 hits of 有N[：，。], lists inside its 問／答 discussions; not used as positives, 3 doctrinal ones used as negatives | T1723 ×4 |
| 中有N (F17) | R01 `zhong-you-n` | 答中有三 | 明經品得名中有二 | see R01 table |
| 此中 (F17) | `ci-zhong` | no | only doctrinal uses (此中六對, used as a negative) | T1782 ×2, T1700 |
| 初中 (F17) | R01 `chu-zhong-yi-n` | no | only 初中後善 (sūtra wording; negative) | T1772, T1782 |
| N中／後中 (F17) | R01 `chu-zhong-yi-n` | no | no | T1830 後中有二 (also T1829 p0106a18 後中有二, not used) |
| 自下第N (F17) | `zixia-di-n` | no | no | T1772, T1782, T1757 |
| 今初 (F17) | anaphor, recorded in `expected.anaphor` | no (the dev span has 此初, 此初聖) | no | 今初 in T1735/T1736 cases; 此初 / 此初聖 / 此初也 / 此初文也 in T1723, T1772, T1782 cases. In those 24 works 今初 occurs 14 times, mostly inside running phrases (今初見, 今初唱, 今初無漏創證); not checked one by one, not used. |
| 三門分別：一來意，二釋名，三解妨 and N門分別 (F25) | `men-fenbie` | 0850a20 | 五門分別 (0866c16) | T1723, T1724, T1782, T1772 |
| 略以六門料簡 and N門料簡 (F25) | `men-liaojian` | no | no | T1758 (略以六門料簡, verbatim), T1829 (以六門料簡), T1832 (略以九門料簡); also T1733 略作五門料簡, T1753 先作七門料簡, T1837 略以五門料簡 (not used) |
| 經「…」。贊曰：… 有N：初…後… (F25, e.g. 品第六段) | `zanyue-lemma` | yes (5 used) | no (no 經「」 lemma or 贊曰 in T1724) | T1723 ×5, T1772 |
| 今為二解 (F25) | — | no | 有二解 occurs only as alternative answers inside 問／答, not a division | **Attested once** as an announcement of alternative whole-sūtra divisions: T1788 `T39n1788_p0183a23` (慧沼 金光明最勝王經疏) 「今為二解。一云：初之一品同於今古，從〈壽量品〉盡〈依空滿願品〉，此之九品明經正宗，餘二十一品竝是流通」. The other 今為N解 found (T1832 ×4, T1816, T1831, T1778 今為三解) introduce alternative readings of a doctrine or a word. One attestation is below the two-positive bar, so there is no slug and no case. |

## 善導 idioms (E06 review 2026-10-02 §2 B3; T1753 is outside every split)

| Slug | Form | Positives / negatives |
|---|---|---|
| `jiu-x-zhong` | (N、)?(又\|次下先\|次)?就X(位)?中(，亦先舉，次辨，後結。)?(即\|亦)有其M — enters X, M children; X headed by 此 is an anaphor (`opens: false`) | pos ×9 (5 entries, 4 anaphoric divisions), neg ×2. Two texts of the original draft were replaced because their strings are heading strings of the eval-only sdp gold (tests/unit/test_sdp_eval_only_guard.py): the replacements were an in-sentence 就此意中即有其七 and 就依報中即有其三; the 就此眾中，即分為二 form is the unit test `SHANDAO_ANAPHOR`. The in-sentence 正明就此意中即有其七 is now `pos-you-n-05`: the 就X中 rule is tried at sentence starts only, so the case only ever tested the 其 of HEAD_RE (`you-n`); the five sentence-initial anaphoric 就此X中，即有其N of T1753 are all in the cases (06, 07, 09, 10 and `neg-jiu-x-zhong-01`). X headed by 此 / 前 / 上來 / 上文, or by 上 + one or two characters other than 品 / 輩 (就上序中即有其二, re-divided by the parser), is no entry; unit tests `test_jiu_x_zhong_with_a_short_up_x_…` |
| `cong-xia-zhi-lai` | N、從A(以\|已)?下(，)?(至B(已來\|已下)，)?Y — item N with lemma A至B and heading Y (the inline form of `cong-xia-zhi-fen`); A and B are bare words (no 「」『』〈〉《》), A has two characters at least; the item is strong when A is an incipit or it states 至B已來, else weak | pos ×3 (the strong / weak split and the quotation-mark rule are unit tests `test_ord_span_…`) |
| `ming-x-jing` | (上來雖有N句不同，)?(廣\|總\|略)(明\|解\|料簡\|辨\|辯)X(竟\|訖), or after the 上來雖有N句不同， lead a bare 明 / 解 / 料簡 — closes X | close ×3 (the prefix-or-lead rule is unit test `test_ming_jing_close_needs_the_prefix_or_the_recap_lead`) |

## Treatise variants (E06 review B4)

Self-outlining take-ups in the Yogācāra treatise dialect, from T1602 顯揚聖教論 (outside every split). They are
detected in self-outlining mode only, and `tests/unit/test_tier2_cases.py` scores these cases in that mode.

| Variant | Slug | Positives |
|---|---|---|
| X論者，謂如有一… / X見者，謂如有一… — a listed heterodox doctrine taken up by naming its proponents; (論\|見)者 is mandatory, since without it the tail also matches the text's 9 理者，謂如有一 (definitions) | `lun-zhe-wei-ru-you-yi` | T1602 ×2 (計我論者 p0523b15, 皆宿作因論者 p0526c06); 14 such sentences in T1602, all among its 十六異論 |

## Self-outlining take-up (T1666)

Idioms of a treatise that outlines itself (T1666 大乘起信論, outside every split; E06 B7). Their cases carry
`"mode": "self-outlining"`, and the filter and the scanner apply the rules below in that mode only.

| Variant | Slug | Cases |
|---|---|---|
| X有N種… whose items the text then takes up in order as sentence-initial 所言X者 / X者 / 云何修行X門？ (at least half of them, within 2,000 characters or up to the next close statement: 已說X分, 上明X, X竟); the list-shape penalties are dropped | `you-n-takeup` | 3 positives (覺與不覺有二種相 p0577a22, 真如熏習義有二種 p0578b19, 是我見有二種 p0579c27) + 1 negative (此妄境界熏習義則有二種 p0578a27, items never taken up) |
| X有N種義，clause。云何為N？一者… — the head's sentence ends in a clause and the count question opens the next sentence; the listing is the enumeration after the question, and it earns the +2 云何為N？ only when its items are taken up | `you-n-deferred` | 2 positives (此識有二種義 p0576b10, 修行有五門 p0581c14: the case text runs to 云何修行忍門？, three of the five 門 taken up) |

## Zhiyi devices (E06 review, 2026-10-02)

Non-formulaic take-ups the R01 table has no row for. Allowed sources: the T1718 dev span; T33n1705 仁王經疏 (outside every split) for density checks only.

| Slug | Device | Positives | Negatives |
|---|---|---|---|
| `lemma-zhe` | 「X」者 / 「X」，… / 「X」N句 at a sentence start: the commentator takes up the word X of the sūtra (the heading and the lemma are X). A run of ≥ 3 one-clause glosses right after a count or open-count announcement is that announcement's listing (listed-only items), scored with `parse()` (`pos-lemma-zhe-05`, `child_count` = the run length, `labels` = the Xs). Not a unit: X with a 、; the comma form after a sentence citing with 云：「; a title word (序 / 品 / 經 / 卷) or any gloss before the first division; a gloss inside a 經「A至B」。贊曰 unit (Kuiji, T1723 dev p0850b09, no case: the dev chapter's only instance) | T1718 ×5 (dev) | T1718 ×2 (dev) |

## Negatives and genre gate

- 26 `not-division` cases. 17 are 「有N」 doctrinal lists (kinds or senses of a term: 總持有四, 佛有三義, 住有二種,
  鬼有二種, 教有二種, 通有四種, 戒有三種, …) from T1723 dev, T1718 dev, T1721, T1724, T1735, T1745, T1764, T1782,
  T1829. The other six are surface triggers: 此中六對 and 加行位分為三品 (T1724), 念分為四 (T1757), 初中後善 (T1724),
  又直就中觀心性 (T1718 dev, R01 F24's 就 + 中觀) and 列數者：一因緣、二約教、三本迹、四觀心 (T1718 dev, cited as a
  non-structural list in R07 F2). T1721's 大明一乘凡有二種 looks like such a list but maps each kind to 品 ranges, so
  it is a positive (`fan-you-n-duan`). The last is `neg-you-n-takeup-01` (T1666, self-outlining; see above); and two
  `lemma-zhe` negatives (a citation fragment, a title word) from T1718 dev (see Zhiyi devices). The `jiu-x-zhong`
  negatives are counted in the 善導 section.
- 5 `genre-gate` cases from T1775 注維摩詰經 (`data/raw/cbeta/xml-p5/T/T38/T38n1775.xml`): three glosses with
  有N lists, one 生曰：自此以下大論法理也 (a section opener in form), one plain gloss (R07 F2's example).

## Sources

Texts used (file under `data/raw/cbeta/` or `data/raw/cbeta/xml-p5/<canon>/<vol>/`):
T1530 佛地經論, T1579 瑜伽師地論, T1602 顯揚聖教論, T1666 / T1667 大乘起信論, T1699 金剛般若疏, T1700 金剛般若經贊述, T1718 妙法蓮華經文句
(dev only), T1721 法華義疏, T1723 妙法蓮華經玄贊 (dev only), T1724 法華玄贊義決, T1735 華嚴經疏, T1736 華嚴經隨疏演義鈔,
T1744 勝鬘寶窟, T1745 無量壽經義疏, T1746 無量壽經義疏 (吉藏), T1753 觀無量壽佛經疏, T1757 阿彌陀經疏, T1758
阿彌陀經通贊疏, T1759 阿彌陀經疏 (元曉), T1763 大般涅槃經集解, T1764 大般涅槃經義記, T1772 觀彌勒上生兜率天經贊,
T1775 注維摩詰經, T1782 說無垢稱經疏, T1798 金剛頂經大瑜伽祕密心地法門義訣, T1804 四分律刪繁補闕行事鈔, T1829
瑜伽師地論略纂, T1830 成唯識論述記, T1832 成唯識論了義燈, X0231 華嚴經疏科文, X0577 法華經疏 (竺道生), X0584 法華三大部科文
(玄義科文 only).

Licence: the texts are CBETA 2026R2 (CC BY-NC-SA 4.0 with CBETA's 版權宣告, reproduced in
`data/reference-outlines/NOTICE` from the snapshot `data/raw/cbeta/LICENCE-NOTICE.txt`); these excerpts are redistributed for non-commercial research under the same
terms.

Run: `cd pipeline && .venv/bin/python -m pytest ../tests/unit/test_kepan_cases.py -q`.
