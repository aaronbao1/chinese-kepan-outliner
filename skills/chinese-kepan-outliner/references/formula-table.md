# Formula table (tier-2 parser)

The human-readable mirror of `pipeline/src/chinese_workflow/outline/tier2/formulae.py`. When the parser report (`outline-report.json` → `tier2.report`) or a resolver request asks you about a passage, this table says what the rules already recognise and how they read it. Slugs are those of `tests/fixtures/kepan-formulae/README.md`; rows come from R01 (F3, F13, F21–F24) and the Kuiji variants of R07 F17 / R03 F25. All weights and thresholds are HYPOTHESIS, tuned on dev material only (the parser cases, the T1723 陀羅尼品 dev span, the T1718 dev span, texts outside every split).

## Statement kinds

| Kind | Examples | What the parser does |
|---|---|---|
| lemma | 經「A至B」。贊曰： · 「A」下 at a sentence start · 如是我聞。贊曰： · 「…」述曰 | opens a treatment unit; the lemma goes to the node the unit enters first, and down its chain of first children (`root_text.raw` = A至B, `basis: lemma`, start left for the anchor stage) |
| announce | X有N：… · 分N · 分為N · 文為N · 大分為N · 文有N分 · 總有N分 · 說有N分 · 凡有N段 · X中有N · 初中亦N · 二中復N · 就X又N · 就X開文為N · 就中初…次… · X中，初…次… · 有N，合為M類 · 有十六句，大分為三 | announces N children of a target node; items become children at once (announced = explained = the item's line) |
| gate | 三門分別：一來意，二釋名，三解妨 · 略以六門料簡 · 略作五門明義 | a wrapper node headed by the phrase; items `commentary-internal` unless they carry root-text locators |
| enter | 此初 · 今初 · 此初也 · 此初文也 · 此初聖 · 第N(、)X · 自下第N X · N、X者 · N、X， · 初、X也 / 次、X也 · 下明X · 下X · 此X。 · X者 · 品第N段X · N「A」下，X · 已說X分。次說Y分 · X論者，謂如有一 (self-outlining: the listed doctrine X, 計我 → 我) · 云何修行X門？ · 所言X者 (self-outlining) · 「X」者 / 「X」，此翻… / 「X」兩句 at a sentence start (Zhiyi: a word of the sūtra taken up; sūtra mode) · N、就X(位)?中(，亦先舉，次辨，後結。)?(即有其M)? (善導: X a listed item or the next 就X中 sibling, the run taking no item past its division's announced count when the run is all the division holds; M its child count; 就此X中 is anaphoric, 就上X中 with a short X is a re-division, not an entry; 上品 / 上輩 are names and enter) · N、從A下，至B已來，Y (善導's unbracketed item: lemma A至B, heading Y; A and B are bare words, A two characters at least; strong when A is an incipit or the item states 至B已來, else weak: still placed where a division waits for a span item, never an `unmatched-enter`) | moves the cursor to a node (explained = the marker, or the lemma when the marker opens the unit); creates the node when the text takes up an item that was counted but not listed; an X者 whose X opens with a function word (若無常者) is not read |
| close | 上明X · 上來X竟 · 已說X分 · (上來雖有N句不同，)(廣\|總\|略)(明\|解\|料簡\|辨\|辯)X竟 (善導; a bare 明 / 解 / 料簡 only after the 上來雖有N句不同， lead, never a bare 辨 / 辯) | returns the cursor to X (so a following 第N / 下明 names X's sibling); 廣明X竟 pops to X's parent (also when X is found by label outside the cursor chain), but 廣料簡X竟 (the sorting of X is over, its items follow) counts when X names a node in the chain and puts the cursor on X, not on its parent; a 廣X竟 that names no node is not counted and is reported `unmatched-close` |
| uddana | 嗢拕南曰：界、相、如理… | one child per verse item; fillers 與 / 及 / 最為後 / 分別 / 略辯相應知 dropped; with a count before the head (何等十六？) a closing phrase (名十六異論) and a verse-initial 執 / 謂 are dropped |
| chart | 科文 lines: ordinal + label + inline note (child count on non-leaves, incipit on leaves) | the chart is rebuilt with a stack of open counts (X0231, X0584); used when most lines of the span are chart lines |

## Target of an announcement (from its subject)

| Subject | Target |
|---|---|
| 品文 · 此品 · 此經 · 今此經中 · 經文 · 分文 / 帖文 (…分文為三) · items that are chapter ranges (從〈X〉至〈Y〉) | the tier-1 node (品) or the text: a **wrapper** node headed by the phrase (品文分三, 三門分別) |
| 答中 · 問中 | the item whose label contains 答 / 問 |
| 初中 · 初文 · 中初文 · 前中 · 初分之中 · 初復有N | the first item (created and headed by the subject when the cursor was counted but not listed: 中初文 under 二天) |
| 後中 · N中 · 二中 | the last item · item N |
| X中 · 就X · 釋X · 列X · X者 (topic clause) | the node labelled X (similarity ≥ 0.75; wrappers are transparent) |
| 又就前X中 · 就前X中 · 就上X中 (X one or two characters; also 就上序中即有其二, which the 就X中 entry rule leaves to this row) | a **re-division** of the item whose label contains X: 前X the earliest announced among same-named candidates (T1753 又就前序中 → the 五門's 明其序分, not the 耆闍會's), 上X the one named last; 就此X中 is the cursor |
| bare (有N / 於中有N / 此中有N) after a lemma or an entry marker | the cursor |
| bare, right after a listing | the listed item most of the new labels share characters with (七佛讚揚 ← 總讚 / 別讚 / 勸讚) |
| an announcement inside another's listing (一、X，有二：…) | that item |
| a substantive subject naming nothing announced (釋同聞眾為三) | a new node headed by the subject, under the nearest node the text entered by a marker |
| anything else, or after an entry marker that could not be placed | **report** (`ambiguous-target`), not attached |

Counted classes: a label that opens with a numeral (二聖, 二天, 十神) is a count hint; 此初聖 enters 二聖 and creates its first member, 第二聖 / 第二天王 create the second; an explicit count (十神。有七) overrides the hint.

Quoted-lemma glosses (Zhiyi, T1718 dev; `lemma_zhe`): 「X」者 / 「X」，… at a sentence start takes up the word X of the sūtra (`root_text.raw` = X). It is a sub-gloss of the open gloss unit when X is part of that unit's word or its 名也 after a 姓也; else it enters an item named X up the cursor chain, or a child of a listed item it partly names (王舍城 under 王城耆山); else a new member of the nearest division still taking members (an open count 五或六或七, a count not reached, a gloss-listed division); else a sibling of the open unit, or the first member of the node the text is in. ≥ 3 one-clause glosses right after a count-only / open-count announcement are its listing. While a gloss unit is open, a weak marker naming a node already taken up is a mention of it (Zhiyi's 約教釋 restates the head word: 大者，… under 「大」者), not a move. Not a unit: a gloss inside a 經「A至B」。贊曰 unit (Kuiji: a word of the lemma; counted in `tier2.stats.gloss_in_lemma_unit`), a title word, a gloss before the first division (`lemma-gloss-at-stub`), X with a 、, the comma form after a sentence citing with 云：「.

## Labels (README label rule)

Split at ordinal words (一…十, 一者, 第一, 初, 次, 後, 先, 餘, 中間, 中) or, unnumbered, at ； / 、 / ， (whichever gives the announced count), or at span items (從…至…). An item ends at 。 or ；, at the next ordinal, or where a nested announcement with its own listing starts; commas do not end it. Removed: the ordinal; locators (「A」下, 從…(下)至…(已來), 始於…訖…, 〈X〉訖〈Y〉, counts of lines / verses / 品: 四行, 有八句, 此十三品, 疏末一偈); a copula after a locator (為, 名, 是, 是其); a final 也. Document order: 初…後…中間… lists 1, 3, 2. `heading_src` follows this rule by default; `config={"heading_style": "source"}` keeps the ordinal (初明持經之福, the Kuiji gold's form).

## Doctrinal-list filter (rejected, reported in `tier2.rejected`)

Against a division: classifier names kinds (種, 義, 相, 事, 對, 品 after 分為 …); 謂 / 所謂 / 為 introduces the items; inside a question (問：) or a citation (X云「…」); the subject is a term (總持有四, 佛有三義, 住有二種); items are bare terms or definitions (X，謂Y); the subject closes a 、-list (戒、定、慧為三分); distributive 各 / 各各; a division reported from another master (有師, 光宅, 舊云 … — rejected outright).
For a division: classifier names text parts (分, 段, 科, 門分別); a division verb (分為, 開為, 大分為); the subject is the text / chapter / a text part / an announced node; it follows a lemma or an entry marker; items ordered 初…後; items carry lemma / span / extent locators; items say what the text does (明, 說, 標, 釋, 結, 歎 …); an anaphor (今初 / 此初) follows; in self-outlining mode a 云何為N？ enumeration. In self-outlining mode a listing at least half of whose items the text then takes up in order (所言X者 / X者 / 云何修行X門？, within 2,000 characters or up to the next close statement: 已說X分, 上明X, X竟) drops the kinds / term / definition penalties (reason "take-up override: k/n items taken up in order"); a head whose count question opens the next sentence (X有N種義，clause。云何為N？一者…) is listed from the question, and that listing earns the 云何為N？ enumeration bonus only when its items are so taken up. Items that reappear with root-text spans (大明一乘凡有二種 … 自從經初至〈神力品〉) override the list signals.

## Genre gate

A work whose title marks 註 / 注 (without 疏 / 記 / 鈔 / 贊 / 義 / 述 / 論 / 文句 / 玄 …) and whose accepted announcements are sparse (< 0.4 per 1,000 characters) states no structure (T1775 注維摩詰經, R07 F2): no tier-2 nodes; the decision and its evidence are in `metadata.genre_gate`. The evidence also counts sentence-initial X曰： / X云： attributions ("collected glosses" when ≥ 3 names each recur ≥ 3 times: T1775 什 / 肇 / 生, X0268 孤山 / 苕溪 / 長水); the count does not decide. Under the gate the machine still reports what it saw: `tier2.rejected` and the report kinds below.

## What goes to the parser report

`unmatched-enter` (a strong marker naming no node in scope), `unmatched-close` (a 善導 close, 廣明X竟 / 廣料簡X竟, whose X names no node in the cursor chain, and for a 廣明X竟 no entered node by label either: not counted, the cursor does not move), `ambiguous-target` (the rules above do not decide), `incomplete-listing` (announced N, listed fewer), `divided-twice`, `target-by-sequence` (a bare announcement after a new lemma attached to the next item not yet taken up — check it), `not-taken-up` (self-outlining: a listed item never entered, given no explained position), `anchor-outside-span`, `lemma-gloss-at-stub` (a 「X」者 before any division: a title word or the preamble), `gated-announcement` / `gated-enter` / `gated-close` (a no-structure text's accepted announcements, strong entry markers and closing markers; nothing was built). Each entry has `linehead`, `offset`, `text` and `reason`; the resolver's `adjudicate` task answers them.
