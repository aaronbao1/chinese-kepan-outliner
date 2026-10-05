"""The tier-2 formula inventory: numerals, ordinal words, classifiers and the regular expressions of the
statement kinds (docs/outliner-design.md §5.2 "Detectors"). Mirrored for readers in
skills/chinese-kepan-outliner/references/formula-table.md.

Input : nothing (constants).
Output: compiled patterns and word sets used by scanner.py, labels.py and filters.py.

Provenance of the rows:
  * R01 formula table (context/research/R01-kepan-tradition-and-coverage/findings.md F3, F13, F21-F24):
    文為N, 分為N：從…至…, 就X又N (F24: key on 就…又N, not 就中), 就X開文為N, X中有N, 初中亦N / N中復N,
    ordinal + 「lemma」下 + heading, 文有N分, X中有N句, 大分為N, 文別有N, 從X下至Y明其Z分, 總有N分,
    說有N分 / 已說X分。次說Y分, 凡有N段, charts (heading + inline note), 嗢拕南曰.
  * Kuiji variants, R07 F17 (分為N, bare 分N, 有N, 中有N, 此中, 初中, N中 / 後中, 自下第N, 今初) and
    R03 F25 (三門分別：一來意，二釋名，三解妨; 略以六門料簡; 經「A至B」。贊曰：… 有N：初…後…; 品第N段).
  * T1666 self-outlining idioms (E06 B7, outside every split): X有N種義，clause。云何為N？一者…; 云何修行X門？; 所言X者.
  * tests/fixtures/kepan-formulae/README.md: the slugs, the label rule and the review-first notes.
Everything here is a HYPOTHESIS tuned on dev material (the parser cases, the T1723 陀羅尼品 dev span,
the T1718 dev span, and texts outside every split); the achieved rates are in the test modules.
"""

from __future__ import annotations

import re

# ------------------------------------------------------------------------------------------ numerals

DIGIT = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
NUM_CHARS = "一二兩三四五六七八九十廿卅百"
NUM = "[%s]+" % NUM_CHARS
DIGITS_RE = "一二三四五六七八九"


def parse_num(s: str) -> int | None:
    """Chinese numeral 1..199 (一, 十, 十一, 二十, 二十一, 廿, 卅, 百) -> int; None when not a numeral."""
    if not s or any(c not in NUM_CHARS for c in s):
        return None
    s = s.replace("廿", "二十").replace("卅", "三十")
    total = 0
    if "百" in s:
        head, _, s = s.partition("百")
        total += 100 * (DIGIT.get(head, 1) if head else 1)
        if not s:
            return total
    if "十" in s:
        head, _, tail = s.partition("十")
        if len(head) > 1 or len(tail) > 1 or "十" in tail:
            return None
        tens = DIGIT.get(head, None) if head else 1
        ones = DIGIT.get(tail, None) if tail else 0
        if tens is None or ones is None:
            return None
        return total + 10 * tens + ones
    if len(s) == 1 and s in DIGIT:
        return total + DIGIT[s]
    return None


# ------------------------------------------------------------------------------------- punctuation

SENT_END = "。？！"  # a sentence ends here (CBETA 新式標點)
CLAUSE_END = SENT_END + "；"
SOFT = "，、：；"
QUOTE_OPEN, QUOTE_CLOSE = "「『", "」』"
BOOK = "《》〈〉"
ALL_PUNCT = SENT_END + SOFT + QUOTE_OPEN + QUOTE_CLOSE + BOOK + "．.,:;!?（）()○　 "

# commentary openers: the commentary's own voice after a lemma (R03 F25: 經「A至B」。贊曰：)
OPENERS = ("贊曰", "述曰", "疏曰", "釋曰", "解曰", "記曰", "義曰", "私曰", "頌曰")  # 頌曰: 經「A至B」。頌曰： (Kuiji's verse sections)
OPENER_RE = re.compile(r"(?:%s)[：:]?" % "|".join(OPENERS))

# ------------------------------------------------------------------------------------- classifiers
# the word after N in 有N? / 分為N?. Structural: parts of a text. Extent: lines, verses, chapters
# (a count of text, R07 F5). Everything else names kinds of a thing (R07 F17's doctrinal lists).
STRUCT_CLS = {"分", "段", "節", "章", "科", "門", "別", "重", "文", "周", "番", "例"}
EXTENT_CLS = {"句", "行", "頌", "偈", "紙", "卷"}
DOCTRINAL_CLS = {
    "種", "義", "事", "相", "對", "德", "法", "位", "名", "身", "智", "障", "蓋", "生", "乘", "因", "果",
    "心", "品", "類", "意", "解", "釋", "喻", "譬", "雙", "階", "字", "處", "時", "人", "眾", "會", "部",
    "教", "藏", "輪", "說", "問", "答", "疑", "難", "請", "勝", "用", "益", "失", "過", "力", "觀", "門",
    "句", "緣", "願", "業", "識", "界", "地", "佛", "天", "道", "理", "聲", "根", "性", "念", "定", "慧",
    "戒", "施", "行", "徳", "宗", "趣", "旨", "條",
}
ALL_CLS = STRUCT_CLS | EXTENT_CLS | DOCTRINAL_CLS
CLS_RE = "[%s]" % "".join(sorted(ALL_CLS))

# ------------------------------------------------------------------------------------ announcements
# A head: (adverbs)(verb)(N)(classifier)? followed by a boundary or a listing. The subject is what
# precedes the head in its clause (scanner._subject).
PRE = "[今此然又且即則略大總凡細別更亦復各通就於說廣略合]"
VERBS = (
    "大分為", "細分為", "分為", "分成", "分作", "開為", "開成", "開作", "判為", "判作", "科為", "束為",
    "離為", "攝為", "合為", "分", "開", "判", "科", "為", "有", "作",
)
# 其 between the verb and the count: 善導's 即有其七 (T1753, E06 review B3; 0 hits of 有其N in both dev spans)
HEAD_RE = re.compile(
    r"(?P<pre>%s{0,3})(?P<verb>%s)(?:其)?(?P<num>%s)(?P<cls>%s{0,2}?)(?=(?P<after>[：:，,。；;、]|$|初|先|第|一))"
    % (PRE, "|".join(VERBS), NUM, CLS_RE)
)
# 初中亦二 / 二中復二 / 比丘又二 / 就初段又二: no verb, an adverb before the count
ADV_HEAD_RE = re.compile(
    r"(?P<verb>[亦復又更])(?P<num>%s)(?P<cls>%s{0,1}?)(?=(?P<after>[：:，,。；]|$|初|先|第|一))"
    % (NUM, CLS_RE)
)
# N門分別 / 略以N門料簡 / 略作N門明義 / 以N門施設建立 (R03 F25; gate when 分別 / 料簡)
GATE_RE = re.compile(
    r"(?P<pre>(?:[略聊今先試]?[以作用就約]|[略聊今先])?)(?P<num>%s)門(?P<verb>分別|料簡|明義|解釋|分釋|"
    r"辨釋|施設建立|建立|釋)(?P<after>者)?" % NUM
)
GATE_VERBS = ("分別", "料簡")
# 通序為五或六或七云云 (T1718 dev): a division whose count is left open
ALT_COUNT_RE = re.compile(r"(?P<verb>為|有|分為|開為)(?P<num>%s(?:或%s)+)(?=[，,。；]|云云)" % (NUM, NUM))
# 就中初牒、次疑 (R01 jiu-zhong): a listing with no count after 就中 / 於中
JIUZHONG_RE = re.compile(r"(?P<verb>就中|於中|中[，,])(?=初[、，,]?[^中]|先|第一|一[、，])")
# 善導 (T1753, E06 review B3): (N、)?(又|次下先|次)?就X(位)?中 (，亦先舉，次辨，後結。)? (即有其M)? at a clause start
# enters X — a listed item, or the next of a run (就初日觀中 … 二、就水觀中) — and M is X's child count. Accepted
# only with an ordinal, the method note or the count (scanner._enter_at). X headed by 此 / 前 / 上來 is an
# anaphor to the node the text is in (就此序中; 又就前序中 is a re-division) and takes the announcement path.
JIU_X_ZHONG_RE = re.compile(
    r"(?P<m>(?:(?P<n>[一二三四五六七八九十]{1,3})[、，,])?(?P<pre>又|次下先|次下|先|次|今|復)?"
    r"就(?P<x>[^，,。；：:、「」]{1,12}?)(?:位)?中)(?=[，,。：:；]|即有其|亦有其|復有其|亦先舉|先舉)"
    r"(?P<tail>[，,]?(?:亦)?先舉[，、,]次[辨辯](?:[，、,]後結)?[。，,]?)?"
    r"(?:[，,]?(?P<cv>即|亦|復)?有其(?P<num>[一二三四五六七八九十]{1,3})(?P<cls>[句門段分義種]?)(?=[：:，,。；]|$))?"
)
JIU_X_ZHONG_ANAPHORS = ("此", "前", "上來", "上文")
# 就上序中即有其二 names an item announced earlier (Task 7's re-division, parser.REDIVISION_RE: 上 + one or two
# characters), so it is no entry either; 就上義中 / 就上法中 (X08n0236) read the same way. A grade's name is: 上品 / 上輩
# stay entries, and 上品中生 / 上品上生 (T1753 p0270c15 …) are longer than three characters.
JIU_X_ZHONG_UP_RE = re.compile(r"上[^品輩]{1,2}")


def jiu_x_zhong_anaphoric(x: str) -> bool:
    """Whether the X of 就X中 points back at a node already named rather than naming an item."""
    return x.startswith(JIU_X_ZHONG_ANAPHORS) or JIU_X_ZHONG_UP_RE.fullmatch(x) is not None
# a count used as a question: 云何為五？ (T1666), 何等為三
RHETORICAL_RE = re.compile(r"(?:云何|何等|何者|何謂|何名)$")
# X有N種義，<clause>。云何為N？一者… (T1666 p0576b10 此識有二種義，能攝一切法、生一切法。云何為二？) and
# 修行有五門，能成此信。云何為五？ (p0581c14): the head's sentence ends in a clause and the count question
# opens the next sentence; self-outlining mode re-parses the listing from the question (scanner.scan)
DEFERRED_RHETORICAL_RE = re.compile(
    r"[，,][^。？！；]{1,20}。(?=(?:云何|何等)(?:為|名)?(?P<n>%s)[？?])" % NUM
)

# ------------------------------------------------------------------------------------ ordinal words
# list items (label rule 1): 一…十, 一者, 第一, 初, 次, 後, 先, 餘, 中間, 中, 前
ORD_NUM_RE = re.compile(r"(?P<di>第)?(?P<n>[一二三四五六七八九十]{1,3})(?P<zhe>者|是)?(?P<p>[、，,：:])?")
ORD_WORD_RE = re.compile(r"(?P<w>中間|初|次|後|先|餘|中|前|最後)(?P<p>[、，,：:])?")
# words that can start an unnumbered item in a span list (fen-wei-n-cong-zhi, fan-you-n-duan)
SPAN_ITEM_START = ("從", "自從", "始於", "始從", "自", "至")

# ------------------------------------------------------------------------------------ locators
# label rule 2: a locator in front of an item's name
LEMMA_XIA_RE = re.compile(r"「(?P<a>[^」]{1,40})」(?:等)?(?:以下|已下|下|去)[，,、]?")
SPAN_RE = re.compile(
    r"(?:自從|從|始於|始從|自)(?P<a>「[^」]{1,40}」|〈[^〉]{1,20}〉|[^，,。；、]{1,24}?)"
    r"(?:以下|已下|下|去)?[，,、]?"
    r"(?:(?P<to>乃至|至于|至於|終於|至|訖|盡|竟|已至)(?P<b>「[^」]{1,40}」|〈[^〉]{1,20}〉|[^，,。；]{0,24}?))?"
    r"(?:[一二三四五六七八九十]+品半?)?(?:已來|以來|已還|已前|來)?[，,]"
)
SPAN_WEAK_RE = re.compile(  # 始於序品，訖安樂行， (fan-you-n-duan-01)
    r"始於[^，,。；]{1,20}[，,](?:訖|至|終於)[^，,。；]{1,20}[，,]"
)
BOOKSPAN_RE = re.compile(  # 〈方便品〉訖〈分別功德〉十九行偈，
    r"〈[^〉]{1,20}〉(?:訖|至|盡|竟)〈[^〉]{1,20}〉[^，,。；]{0,10}[，,]"
)
EXTENT_RE = re.compile(
    r"(?:(?:此|凡|有|合|疏末|經末|末|餘|上|下)?(?P<n>[一二三四五六七八九十兩]+)(?P<u>行|句|頌|偈|品)(?P<half>半)?"
    r"(?:偈)?|(?:此|凡)?(?:品|章))[，,]?"
)
COPULA_RE = re.compile(r"(?:名為|是其|名|為|是)")

# ------------------------------------------------------------------------------------ lemmas
# 經「A至B」。贊曰： — R03 F25. 至 is often a small-print inline note in CBETA (T1723 dev span).
SUTRA_LEMMA_RE = re.compile(r"經[：:]?「(?P<q>[^」]{1,80})」[。．]?")
# 「A」下 / 從「A」下至「B」 / 從「A」去、至「B」 at a sentence start (R01 ordinal-lemma-xia, T1718)
QUOTE_XIA_RE = re.compile(
    r"(?:從)?「(?P<a>[^」]{1,40})」(?:以下|已下|下|去)[，,、]?(?:(?:至|訖|盡|竟)「(?P<b>[^」]{1,40})」[，,]?)?"
)
# 「X」者， / 「X」，… / 「X」N句 at a sentence start: Zhiyi's take-up of a word of the sūtra (T1718 dev: 37
# sentence-initial occurrences, 27 of them units; E06 review §1 item 2, B6). The follow set is what the
# dev text has: 者 (22), a comma (13), an extent 一句 / 兩句 (2). X ≤ 14 characters, the 'term' bound of
# scanner._quote_kind: the longest dev unit is 8 (諸漏已盡，無復煩惱), T33n1705 (outside every split)
# reaches 14; a longer sentence-initial quotation is a cited passage. Prefixes: 又「如是」者 (resumptive),
# 釋「聞」者 (a sub-gloss). 「A」下 is QUOTE_XIA_RE; the parser decides what the gloss opens.
LEMMA_ZHE_RE = re.compile(
    r"(?P<pre>又|釋|今釋|次釋|次|後)?「(?P<a>[^「」]{1,14})」"
    r"(?P<f>者|[，,]|(?P<ext>此?[一二三四五六七八九十兩]{1,2}[句行頌偈]))"
)
# words of the title lines (序品第一, 卷第一) glossed in a preamble: 「序」者 / 「品」者 (T1718 p0001b23, b27)
TITLE_WORDS = ("序", "品", "經", "卷")

# ------------------------------------------------------------------------------------ entry markers
# anaphors (R07 F17 今初; T1723 dev 此初 / 此初聖; T1772 此初也; T1782 此初文也)
ANAPHOR_RE = re.compile(
    r"(?P<m>(?:此|今)(?:即)?初(?P<x>[^\s，,。；：:「」]{0,2}?)(?:文|段|分)?(?:也)?)(?=[。，,；：:]|$)"
)
# 第二聖 / 第三、化佛說法 / 自下第二明天願果 / 次第二 …
ORD_ENTER_RE = re.compile(
    r"(?P<m>(?P<pre>自下|從此已下|從此以下|已下|以下|次|下)?第(?P<n>[一二三四五六七八九十]{1,3})(?:段|科|門)?[、，,]?)"
    r"(?P<x>[^。；？！]{0,16}?)(?:也)?(?=[。；？！]|$)"
)
# 序有通、別，從「如是」去、至「却坐一面」，通序也；從「爾時世尊」去、至品，別序也 (T1718 dev): a short
# 、-list after X有 whose items are then assigned root-text spans
YOU_LIST_RE = re.compile(
    r"(?P<subj>[^，,。；：:、「」○\s]{1,4})有(?P<items>[^，,。；：:、「」]{1,2}(?:、[^，,。；：:、「」]{1,2}){1,4})[，,]"
    r"(?=(?:從|自))"
)
# N、X者 (T1718: 二、所以者，四、示相者；二、明數者)
# 初、解化前序者 (T1753 p0252b04; 0 clause-initial 初、X者 in the dev spans): 初 is ordinal 1, and only with its
# separator behind it (the lookahead): 初若無常者 is a clause that begins 初 as an adverb, not an item
NUM_ZHE_RE = re.compile(
    r"(?P<m>(?P<n>初(?=[、，,])|[一二三四五六七八九十]{1,3})[、，,]?(?P<x>[^，,。；：:「」]{1,8}?)者)(?=[，,：:。])")
# N、X， (T1718: 四、歎德，五、列名，) — weak
NUM_ITEM_RE = re.compile(r"(?P<m>(?P<n>[一二三四五六七八九十]{1,3})、(?P<x>[^，,。；：:「」]{1,8}))(?=[，,。；])")
# X者，(label + 者: 來意者，釋名者，解妨者 in the dev span) — weak, resolved against labels only
X_ZHE_RE = re.compile(r"(?P<m>(?:所言|言|其|又|次|今)?(?P<x>[^，,。；：:「」『』〈〉《》\s]{1,8}?)者)(?=[，,：:。；]|$)")
# self-outlining only (scanner._enter_at): 云何修行施門？ takes up 施門 of 修行有五門 (T1666 p0581c17); 所言覺義者
# takes up 覺義 of 此識有二種義 (p0576b11). 修行 is required: a bare 云何X門？ matches 云何名為生滅門？.
YUNHE_XIUXING_RE = re.compile(r"(?P<m>云何修行(?P<x>[^。？！，,；：:「」]{1,6}?門)[？?])")
SUOYAN_RE = re.compile(r"(?P<m>(?:復次[，,]?)?所言(?P<x>[^，,。；：:「」『』\s]{1,8}?)者)(?=[，,：:。；]|$)")
# X論者，謂如有一 / X見者，謂如有一 (T31n1602 p0521b23–p0530c12): a treatise takes up a listed heterodox doctrine by
# naming its proponents; x is the doctrine's name (計我, 妄計清淨), which sim() maps to the listed item (我, 淨).
# (論|見)者 is mandatory: with it optional the tail also matches the text's 9 理者，謂如有一 (definitions).
# Self-outlining mode only; strong (E06 review B4).
PROPONENT_RE = re.compile(r"(?P<m>(?P<x>[^，,。；：:「」『』\s]{1,8}?)(?:論|見)者)(?=[，,]謂如有一)")
# 下明神呪之方 / 下二天 (T1723 dev, after 贊曰：); 次明X / 後明X
XIA_RE = re.compile(r"(?P<m>(?P<pre>自下|下|次|後|今)(?P<v>明|釋|辨|說|顯|解|列)?)(?P<x>[^。；？！，,：:]{1,20}?)(?:也)?(?=[。；？！]|$)")
# 初、散花也。/ 次、X也。/ 二、X也。 (T1772): an item named where it is taken up, after 有N：
NEXT_ITEM_RE = re.compile(
    r"(?P<m>(?P<w>初|次|後|第?[一二三四五六七八九十]{1,2})[、，,])(?P<x>[^。；，,：:「」]{1,16}?)也(?=[。；]|$)"
)
# a subject that names a part: not a bare function word (雖 / 分之 / 若 …)
FUNCTION_HEAD = "雖若如故則而但且乃即亦皆既由因以為其之所於此彼是有無不"
# 品第三段時眾獲益 (T1723 dev, R03 F25)
PIN_DUAN_RE = re.compile(r"(?P<m>品第(?P<n>[一二三四五六七八九十]{1,3})(?:段|科|分))(?P<x>[^。；？！]{0,20}?)(?:也)?(?=[。；？！]|$)")
# 此十神。 (T1723 dev: a pointer + the name of a listed item, right after 贊曰：)
THIS_RE = re.compile(r"(?P<m>此(?:即|是|明)?(?P<x>[^\s，,。；：:「」]{1,8}?)(?:也)?)(?=[。；]|$)")
# N「A」下，X (R01 ordinal-lemma-xia): 二「海月」下，十異名菩薩。
ORD_LEMMA_RE = re.compile(
    r"(?P<m>(?P<n>[一二三四五六七八九十]{1,3})[、，,]?「(?P<a>[^」]{1,40})」(?:以下|已下|下)[，,]?)"
    r"(?P<x>[^。；？！]{1,30}?)(?:也)?(?=[。；？！]|$)"
)
# 善導's inline item (T1753): N、從A(以|已)?下(，)?(至B(已來|已下)，)?Y — CBETA prints the incipits without 「」; the item's
# lemma is A至B (A alone when no end is given) and Y its heading (E06 review B3; README cong-xia-zhi-lai).
# 下 must be followed by a comma or 至/訖, so 從上品下生者已下 keeps 上品下生者 as A. A and B are bare words: no
# quotation or title marks (「」『』〈〉《》, a quoted incipit is the 「A」下 idiom; 從〈安樂行〉下 names a 品), A has
# two characters at least, and a 至 / 訖 after 下 must open a whole 至B已來 / 至B已下 (T1753 p0265b28; else 至「…」 stayed in the heading).
_SPAN_WORD = "[^，,。；：:「」『』〈〉《》]"
ORD_SPAN_RE = re.compile(
    r"(?P<m>(?P<n>初|[一二三四五六七八九十]{1,3})[、，,]從(?P<a>%s{2,24}?)(?:以下|已下|下)(?=[，,至訖])"
    r"(?:[，,]?(?:至|訖)(?P<b>%s{1,24}?)(?:已來|以來|已下|以下)[，,]?|(?![，,]?[至訖])[，,]?))"
    r"(?P<x>[^。；？！]{1,30}?)(?:也)?(?=[。；？！]|$)" % (_SPAN_WORD, _SPAN_WORD)
)
# 已說X分。次說Y分 (R01 shuo-you-n-fen, T1666 self-outlining)
YISHUO_RE = re.compile(r"(?P<m>已說(?P<x>[^。；，,]{1,10}))(?=[。；]|$)")
CISHUO_RE = re.compile(r"(?P<m>(?P<pre>初|次|今|後)(?P<x>說[^。；，,]{1,10}))(?=[。；]|$)")
# 善導's close (T1753): (上來雖有N句不同，)?(廣|總|略)?(明|解|料簡)X(竟|訖) at a clause start; X is the node just
# finished (the cursor or an ancestor). Tried before CLOSE_RE, which keys on 上來 and would name 雖有N句不同. A close
# needs the (廣|總|略) prefix or the recap lead (a bare 明X竟 / 解所緣竟 / 辨色聚訖 is common prose: 357 sentence
# starts over CBETA, 39 in T1753), and 辨 / 辯 only after the prefix (廣辯X竟).
MING_JING_RE = re.compile(
    r"(?P<m>(?P<lead>上來雖有[一二三四五六七八九十]{1,3}[句段門義種眾]不同[，,。])?"
    r"(?P<v>(?:廣|總|略)(?:明|解|料簡|辨|辯)|(?(lead)(?:明|解|料簡)|(?!)))"
    r"(?P<x>[^。；，,：:]{1,12}?)(?:竟|訖))(?=[。；，,]|$)"
)
# closing markers: 上明X / 上來X竟 / X竟 (T1718 舉類義竟; T1772 上明植因發願)
CLOSE_RE = re.compile(r"(?P<m>(?:上來|上已|上)(?:明|釋|辨|說)?(?P<x>[^。；，,]{1,12}?)(?:竟|訖|已)?)(?=[。；，,]|$)")
# uddāna (R01 uddana, T1579): 嗢拕南曰： verse up to 。
UDDANA_RE = re.compile(r"(?:總|別)?(?:嗢拕南|嗢柁南|嗢陀南|嗢怛南|鄔拕南|溫陀南)曰[：:]?")
UDDANA_FILLERS = ("最為後", "略辯相應知", "分別", "應知", "及", "與", "并")
# the count announced right before an uddāna (何等十六？嗢柁南曰：, T31n1602 p0521b11; 有N種。嗢拕南曰：). With one
# piece too many, the last piece restating the count (名十六異論) is a closing phrase, not an item, and a
# verse-initial verb on the first piece (執因中有果) is not part of its label (E06 review B4).
UDDANA_HEAD_RE = re.compile(
    r"(?:(?:何等|云何)(?:為|名)?(?P<n>%s)(?:種|者)?[？?。]?|有(?P<n2>%s)(?:種|分|門)?[，,。：:]?)$" % (NUM, NUM))
UDDANA_CLOSERS = ("是名", "總名", "如是", "名")
UDDANA_LEAD_VERBS = ("執", "謂")

# ------------------------------------------------------------------------------------ vocabulary
# words that name what a stretch of text does (label side of the doctrinal-list filter, design §5.2)
TEXT_VERBS = set("明說標釋結歎嘆讚請問答辨辯顯示列序牒舉述彰敘引證勸許返舉印誡告付勅囑總別正通")
TEXT_WORDS = ("流通", "長行", "偈頌", "重頌", "正宗", "由序", "序分", "發起", "證信", "經文", "本文",
              "問答", "徵釋", "結勸", "總標", "別釋", "總結", "別明")
# subjects that are parts of a text (design §5.2 filter)
STRUCT_SUBJECTS = ("文", "品", "經", "此", "中", "初", "次", "後", "答", "問", "段", "章", "頌", "偈",
                   "長行", "本文", "經文", "正宗", "流通", "序", "論", "疏")
DOCTRINAL_INTRO = ("謂", "所謂", "即", "云")
QUESTION_OPEN = ("問曰", "問：", "問:", "或問")
# attributions X曰： / X云： at a sentence start (genre-gate evidence, R07 F2; E06 B9). NAME is 1-3 characters:
# 註 works attribute by surname character (T1775 什 / 肇 / 生) or by two-character names (X0268 孤山 / 苕溪 /
# 長水 / 資中). Excluded: the commentator's own openers (贊曰 / 述曰 …), dialogue (問曰 / 答曰), function
# words (又問曰, 諸師云, 下文云, 故曰) and 云何 questions (於汝意云何).
ATTRIBUTION_STOP = ("又此故下諸彼是其今若如或問答經論疏文義本者說言有無不所云曰則即亦復皆乃何而且與及別前後上總釋"
                    "贊述解記私讚雖苟既於")
ATTRIBUTION_RE = re.compile(
    r"(?:^|[。？！；」])(?P<who>[^\s，,。？！；：:、「」『』〈〉《》○%s]{1,3})(?:曰|云)(?!何)[：:]?" % ATTRIBUTION_STOP
)
ZHU_TITLE_RE = re.compile(r"[註注]")
PASS_TITLE_RE = re.compile(r"疏|記|鈔|贊|文句|義|述|論|玄|釋|章|科")
