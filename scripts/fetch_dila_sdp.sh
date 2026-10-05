#!/usr/bin/env bash
# scripts/fetch_dila_sdp.sh — fetch the 法華經數位資料庫 (Saddharmapuṇḍarīka Database, CHIBS/DDBC; http://sdp.chibs.edu.tw/,
# "Version2" reader ui.html, 2010) files that carry its 科判 of T0262 妙法蓮華經 and its commentary 法華文句 T1718, into
# data/raw/dila-sdp/ (gitignored), and record sha256 in scripts/CHECKSUMS.
#
# The reader is an ExtJS 3.2 page whose data comes from an eXist-db backend behind exeQuery.php (plain http; no auth):
#   POST id=<docid>&getTreeNode=yes   -> JSON array of child nodes  [{"id":"T0262D01_005","text":"…","leaf":false},…]
#   POST id=<node-id>&getHtml=yes     -> HTML of the whole 卷 that contains the node: nested <div class="content" id="T0262D<level>_<seq>">
#                                        with <div class="head_title">【n title】<a class="link2oth" id="<version>D<level>_<seq>">…</a></div>
#                                        and Taishō line anchors <a name="0001a05" class="ref">[0001a05]</a>
# Node ids follow DILA's DocID + "D" + depth + "_" + sequence scheme (as in the YBh TEI); getTreeNode only returns one
# level of children at a time (the ExtJS tree lazy-loads), so a full tree needs one POST per non-leaf node — done by the
# depth-first recursion helper scripts/sdp_tree.py (stdlib-only Python; same 0.4 s pacing, one request at a time), which
# this script calls for T0262 and T1718 to write tree-T0262-full.json / tree-T1718-full.json.
#
# getHtml is per 卷 (T0262: 7 juan, one getHtml call each, as fetched here since 2026-09-21). For T1718, checked
# empirically (2026-09-22, id=T1718D01_002 "序品" and id=T1718D01_004 "2 正宗分"): getHtml returns the whole 卷-HALF
# (上 or 下) containing the queried node — 20 halves, not 10 whole 卷 — e.g. id=T1718D01_002 (which sits in 卷第一上)
# returned anchors 0001a01…0009b07, stopping exactly at 卷第一下's own first anchor (0009b07, included once as the
# file's last item, never anything past it); id=T1718D01_004 (which sits in 卷第三上, though "2 正宗分" is a top-level
# node spanning 品 2-20) returned only 0030b11…0037b11 (卷第三上), not the whole of 正宗分. So T1718 needs one getHtml
# call per 卷-half, written as data/raw/dila-sdp/T1718-juan<k>.html with k = "1a".."10b" (T34n1718.xml's own
# cb:mulu/@n for its 卷 milestones — the chinese_workflow.ingest.lines 卷 boundaries checked against these files in
# tests/unit/test_sdp_fetch_outputs.py). The node ids in POSTS below were found by walking tree-T1718-full.json in
# document order and probing candidate ids' getHtml one at a time until one landed cleanly inside each half.
#
# T1718 getHtml gaps (found 2026-09-22; not fixed by trying harder -- see below): only 9 of the 20 halves are
# reachable this way -- 1a, 2a, 2b, 3a, 3b, 4a, 4b, 5b, 6b. The other 11 (1b, 5a, 6a, 7a, 7b, 8a, 8b, 9a, 9b, 10a,
# 10b) could not be fetched: every candidate id tried for them -- roughly 900 getHtml requests across every
# strategy available (shallow depth-2/3 chapter-grouping ids like T1718D02_004..D02_014, and an exhaustive,
# depth-first, one-at-a-time scan of all 878 leaves and then all 541 depth>=10 leaves in tree-T1718-full.json,
# document order, from where 6b was found to the end of the tree) -- returned one of two failure shapes, every
# time, deterministically on repeat: (a) HTTP 200 with the literal 19-byte body "query maybe faile\n" (the same
# defect getTreeNode shows for its 27 unreachable nodes, see below), or (b) HTTP 200 with a *different* HTML page
# than requested: a fixed, non-contiguous jumble of anchors (e.g. querying deep inside what should be 卷五上 or
# 卷六上/6b-onward returns anchors 0051c08…0149a29 with page gaps at 53-55, 56-58, 59-61, 61-141, the same exact
# body for dozens of unrelated ids) rather than that node's own 卷-half. No id anywhere in the tree -- leaf or
# container, shallow or deep -- was found whose getHtml lands cleanly past 卷第六下 (page 0090b20). This is a
# genuine, wide server-side data gap in sdp for roughly the back half of T1718 (卷五上 onward), not a node-id
# selection problem; do not keep guessing ids to "fix" it, and do not fabricate the missing files. A person with
# access to CHIBS/DILA could ask whether their eXist-db content for this range is intact.
#
# Input : network only (sdp.chibs.edu.tw) + the GET/POST/TREE tables below.
# Output: data/raw/dila-sdp/ui.html, js-config.js, js-Init.js, js-functions.js, js-ref.js, js-lang-zh_TW.js, js-lang-eng.js
#                                                     the reader and its configuration (document list, id scheme, line-ref formats)
#         data/raw/dila-sdp/index.php.html            landing page (計畫小組 釋惠敏 等; "last updated: 2026 - 繼續維護中"; no licence text)
#         data/raw/dila-sdp/about-progress.html       計畫進度表 (which texts got xml + 科判, by project year)
#         data/raw/dila-sdp/about-versions.html       版本資訊 (editions used, 標點參考書目)
#         data/raw/dila-sdp/news-2006.html            最新消息 2006 (dates of 文句/玄義/釋籤 科判 completion)
#         data/raw/dila-sdp/tree-T0262-root.json      top-level nodes of the T0262 tree
#         data/raw/dila-sdp/tree-T1718-root.json      top-level nodes of the 法華文句 T1718 tree (same three-part 科判)
#         data/raw/dila-sdp/T0262-juan1.html … T0262-juan7.html   the full T0262 with the 科判 interleaved (2,017 nodes)
#         data/raw/dila-sdp/tree-T0262-full.json      full recursive getTreeNode walk of T0262 (scripts/sdp_tree.py):
#                                                      measured 2026-09-22 = 2,048 nodes / 1,345 leaves / 19 levels / 0 fetch_error
#                                                      (R04 F30 reported the same 2,048 / 1,345 / 19 on 2026-09-21 -- exact agreement)
#         data/raw/dila-sdp/tree-T1718-full.json      full recursive getTreeNode walk of T1718 (scripts/sdp_tree.py):
#                                                      measured 2026-09-22 = 1,453 nodes / 878 leaves / 19 levels / 27 nodes
#                                                      recorded with fetch_error (getTreeNode returns the literal body
#                                                      "query maybe faile" for these, deterministically, confirmed by a second
#                                                      retry pass on all 27 -- a server-side defect, not transient; of the 27,
#                                                      1 (T1718D08_018) has its content recoverable from a T1718-juan*.html we
#                                                      do have (a <div class="content" id="T1718D08_018"> in juan3a.html) --
#                                                      the other 26 sit in the same "T1718 getHtml gaps" region above, so
#                                                      neither the tree API nor the HTML we could fetch carries them)
#         data/raw/dila-sdp/T1718-juan1a.html, 2a, 2b, 3a, 3b, 4a, 4b, 5b, 6b.html   9 of T1718's 20 卷-halves with the
#                                                      科判 interleaved (the other 11 are a server-side gap, not fetched --
#                                                      see "T1718 getHtml gaps" above; never fabricated)
#         scripts/CHECKSUMS                           lines for data/raw/dila-sdp/*; other scripts' lines preserved
#
# Usage : bash scripts/fetch_dila_sdp.sh            fetch whatever is missing or mismatched, then (re)write CHECKSUMS
#         bash scripts/fetch_dila_sdp.sh --check    recompute sha256 of every data/raw/dila-sdp/ entry and compare
#         bash scripts/fetch_dila_sdp.sh --force    re-download everything
#
# Provenance / licence (checked 2026-09-21; data/README.md): the site publishes NO licence
# or terms text (landing page, reader, 關於本站 pages); the 計畫小組 page ends "Copyright 2003-2007". Treat these files as
# eval-only reference material until CHIBS/DILA state reuse terms (Gap 11 of R04). The server is unversioned and "繼續維護中";
# a --check MISMATCH after a fresh fetch means the site changed. Note: https://sdp.chibs.edu.tw/ serves a different DILA site;
# the Lotus database is plain http only.
#
# Politeness: one request at a time, 0.4 s sleep between requests, curl --retry 3 (scripts/sdp_tree.py: same pacing,
# its own retry/backoff — see its own header).
# Portability: bash 3.2+ (macOS), curl, awk, python3 (stdlib only, for scripts/sdp_tree.py); sha256 via sha256sum or shasum.

set -euo pipefail

BASE="http://sdp.chibs.edu.tw"
UA="chinese-workflow fetch script (research use; curl)"
SLEEP="0.4"

# GET: URL path | local file name
GETS='
/ui.html|ui.html
/js/config.js|js-config.js
/js/Init.js|js-Init.js
/js/functions.js|js-functions.js
/js/ref.js|js-ref.js
/js/lang/zh_TW.js|js-lang-zh_TW.js
/js/lang/eng.js|js-lang-eng.js
/index.php|index.php.html
/sdp_intro/aboutSDP/aboutsdp-002.htm|about-progress.html
/sdp_intro/refsdp/refsdp-006.htm|about-versions.html
/sdp_intro/news/news-003.htm|news-2006.html
'
# POST to /exeQuery.php: form body | local file name
POSTS='
id=T0262&getTreeNode=yes|tree-T0262-root.json
id=T1718&getTreeNode=yes|tree-T1718-root.json
id=T0262D02_010&getHtml=yes|T0262-juan1.html
id=T0262D05_025&getHtml=yes|T0262-juan2.html
id=T0262D06_042&getHtml=yes|T0262-juan3.html
id=T0262D03_014&getHtml=yes|T0262-juan4.html
id=T0262D03_019&getHtml=yes|T0262-juan5.html
id=T0262D03_020&getHtml=yes|T0262-juan6.html
id=T0262D02_019&getHtml=yes|T0262-juan7.html
id=T1718D01_002&getHtml=yes|T1718-juan1a.html
id=T1718D07_002&getHtml=yes|T1718-juan2a.html
id=T1718D06_006&getHtml=yes|T1718-juan2b.html
id=T1718D01_004&getHtml=yes|T1718-juan3a.html
id=T1718D08_025&getHtml=yes|T1718-juan3b.html
id=T1718D08_029&getHtml=yes|T1718-juan4a.html
id=T1718D10_026&getHtml=yes|T1718-juan4b.html
id=T1718D12_035&getHtml=yes|T1718-juan5b.html
id=T1718D14_063&getHtml=yes|T1718-juan6b.html
'
# T1718-juan1b.html, 5a, 6a, 7a, 7b, 8a, 8b, 9a, 9b, 10a, 10b are DELIBERATELY ABSENT from this
# table: sdp's getHtml has a genuine, reproducible data gap for these 11 halves (see header
# "T1718 getHtml gaps" for the evidence -- roughly 900 distinct node-id probes across every
# strategy tried, none recovered them). Do not add placeholder ids here; a future run of this
# script (or a person who finds a working id) should add a real line to POSTS above.
# Recursive getTreeNode trees (scripts/sdp_tree.py, not curl -- one HTTP request per non-leaf node,
# depth-first, --sleep apart; can take several minutes): document id | local file name
TREES='
T0262|tree-T0262-full.json
T1718|tree-T1718-full.json
'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
OUT_DIR="data/raw/dila-sdp"
PREFIX="data/raw/dila-sdp/"
CHECKSUMS="scripts/CHECKSUMS"
HEADER='# sha256  path  # provenance   (written by the scripts/fetch_*.sh scripts, each owning the lines under its own data/raw/<source>/ prefix; verify with "bash scripts/fetch_<source>.sh --check")'

MODE="fetch"; FORCE=""
case "${1:-}" in
  "") ;;
  --check) MODE="check" ;;
  --force) FORCE="1" ;;
  *) echo "usage: $0 [--check|--force]" >&2; exit 2 ;;
esac

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}
recorded_line() {
  [ -f "$CHECKSUMS" ] || return 0
  awk -v p="$1" '$1 !~ /^#/ && $2 == p { print; exit }' "$CHECKSUMS"
}
recorded_sha() { recorded_line "$1" | awk '{ print $1 }'; }
jfield() { python3 -c "import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])" "$1" "$2"; }  # $1 a JSON object string, $2 a key

# fetch_url <url> <dest> [<post-body>] -> downloads (GET, or POST when a body is given) to a temp file, checks Content-Length
# when present, moves into place, prints byte count
fetch_url() {
  local url="$1" dest="$2" body="${3:-}" tmp hdr bytes clen
  tmp="$(mktemp "${dest}.part.XXXXXX")"; hdr="$(mktemp "${dest}.hdr.XXXXXX")"
  if [ -n "$body" ]; then
    curl -fsSL --retry 3 --retry-delay 2 --max-time 300 -A "$UA" -D "$hdr" -o "$tmp" -X POST -d "$body" "$url" || { rm -f "$tmp" "$hdr"; echo "ERROR: POST failed: $url ($body)" >&2; return 1; }
  else
    curl -fsSL --retry 3 --retry-delay 2 --max-time 300 -A "$UA" -D "$hdr" -o "$tmp" "$url" || { rm -f "$tmp" "$hdr"; echo "ERROR: download failed: $url" >&2; return 1; }
  fi
  bytes="$(wc -c < "$tmp" | tr -d ' ')"
  clen="$(grep -i '^content-length:' "$hdr" | tail -1 | tr -dc '0-9' || true)"
  if [ -n "$clen" ] && [ "$clen" != "$bytes" ]; then
    rm -f "$tmp" "$hdr"; echo "ERROR: got $bytes bytes, Content-Length said $clen: $url" >&2; return 1
  fi
  mv "$tmp" "$dest"; rm -f "$hdr"
  printf '%s\n' "$bytes"
}

expected="$(printf '%s\n%s\n%s\n' "$GETS" "$POSTS" "$TREES" | awk -F'|' 'NF>=2 { print $2 }')"

# ---------------------------------------------------------------- --check
if [ "$MODE" = "check" ]; then
  [ -f "$CHECKSUMS" ] || { echo "ERROR: $CHECKSUMS missing; run: bash scripts/fetch_dila_sdp.sh" >&2; exit 1; }
  fail=0; n=0
  for base in $expected; do
    rel="${PREFIX}${base}"; n=$((n+1))
    want="$(recorded_sha "$rel")"
    if [ -z "$want" ]; then echo "NO-LINE   $rel"; fail=1; continue; fi
    if [ ! -f "$rel" ]; then echo "MISSING   $rel"; fail=1; continue; fi
    if [ "$(sha256_of "$rel")" = "$want" ]; then echo "OK        $rel"; else echo "MISMATCH  $rel"; fail=1; fi
  done
  while read -r sha path _rest; do
    case "$sha" in ''|'#'*) continue ;; esac
    case "$path" in "$PREFIX"*) ;; *) continue ;; esac
    if printf '%s\n' "$expected" | grep -qxF "${path#$PREFIX}"; then continue; fi
    n=$((n+1))
    if [ ! -f "$path" ]; then echo "MISSING   $path (extra entry)"; fail=1
    elif [ "$(sha256_of "$path")" = "$sha" ]; then echo "OK        $path (extra entry)"
    else echo "MISMATCH  $path (extra entry)"; fail=1; fi
  done < "$CHECKSUMS"
  echo "checked $n entries under $PREFIX; $( [ $fail -eq 0 ] && echo ALL OK || echo FAILURES )"
  exit $fail
fi

# ---------------------------------------------------------------- fetch
mkdir -p "$OUT_DIR"
TODAY="$(date +%F)"
rm -f "$OUT_DIR/.checksums.new"

printf '%s\n' "$GETS" | awk -F'|' 'NF>=2' | while IFS='|' read -r path base; do
  dest="${OUT_DIR}/${base}"; rel="${PREFIX}${base}"
  old="$(recorded_line "$rel")"
  if [ -z "$FORCE" ] && [ -f "$dest" ] && [ -n "$old" ] && [ "$(sha256_of "$dest")" = "${old%% *}" ]; then
    echo "keep      $rel"; printf '%s\n' "$old" >> "$OUT_DIR/.checksums.new"; continue
  fi
  echo "fetch     $rel  <-  GET ${BASE}${path}"
  bytes="$(fetch_url "${BASE}${path}" "$dest")" || exit 1
  printf '%s  %s  # GET sdp.chibs.edu.tw%s (unversioned server), fetched %s, %s bytes\n' "$(sha256_of "$dest")" "$rel" "$path" "$TODAY" "$bytes" >> "$OUT_DIR/.checksums.new"
  sleep "$SLEEP"
done

printf '%s\n' "$TREES" | awk -F'|' 'NF>=2' | while IFS='|' read -r docid base; do
  dest="${OUT_DIR}/${base}"; rel="${PREFIX}${base}"
  old="$(recorded_line "$rel")"
  if [ -z "$FORCE" ] && [ -f "$dest" ] && [ -n "$old" ] && [ "$(sha256_of "$dest")" = "${old%% *}" ]; then
    summary="$(python3 "$REPO_ROOT/scripts/sdp_tree.py" --stats "$dest")"
    echo "keep      $rel  ($(jfield "$summary" nodes) nodes, $(jfield "$summary" leaves) leaves, $(jfield "$summary" max_depth) levels, $(jfield "$summary" errors) fetch_error node(s))"
    printf '%s\n' "$old" >> "$OUT_DIR/.checksums.new"
    continue
  fi
  echo "fetch     $rel  <-  scripts/sdp_tree.py $docid  (recursive getTreeNode walk, one request at a time; can take several minutes -- resumable via ${dest}.partial.json if interrupted)"
  # write straight to $dest, not a mktemp temp file: sdp_tree.py itself only ever writes $dest on
  # full success (its own atomicity), and its checkpoint file's name is derived from $dest, so a
  # rerun after a BLOCKED exit resumes instead of starting over (a randomized tmp name would break
  # that -- the checkpoint from the previous attempt would never be found again)
  summary="$(python3 "$REPO_ROOT/scripts/sdp_tree.py" "$docid" "$dest" --sleep "$SLEEP")" || { echo "ERROR: scripts/sdp_tree.py failed for $docid; ${dest}.partial.json holds this run's progress; rerun to resume" >&2; exit 1; }
  bytes="$(wc -c < "$dest" | tr -d ' ')"
  nodes="$(jfield "$summary" nodes)"; leaves="$(jfield "$summary" leaves)"
  depth="$(jfield "$summary" max_depth)"; reqs="$(jfield "$summary" requests)"
  errs="$(jfield "$summary" errors)"
  echo "          $docid tree: $nodes nodes, $leaves leaves, $depth levels, $reqs getTreeNode requests, $errs fetch_error node(s)"
  if [ "$errs" != "0" ]; then
    echo "          fetch_error node ids: $(python3 -c "import json,sys; print(', '.join(json.loads(sys.argv[1])['error_ids']))" "$summary")"
  fi
  printf '%s  %s  # derived by scripts/sdp_tree.py from sdp.chibs.edu.tw/exeQuery.php id=%s (recursive getTreeNode walk, unversioned server), fetched %s, %s bytes, %s nodes / %s leaves / %s levels / %s requests / %s fetch_error node(s)\n' "$(sha256_of "$dest")" "$rel" "$docid" "$TODAY" "$bytes" "$nodes" "$leaves" "$depth" "$reqs" "$errs" >> "$OUT_DIR/.checksums.new"
done

printf '%s\n' "$POSTS" | awk -F'|' 'NF>=2' | while IFS='|' read -r body base; do
  dest="${OUT_DIR}/${base}"; rel="${PREFIX}${base}"
  old="$(recorded_line "$rel")"
  if [ -z "$FORCE" ] && [ -f "$dest" ] && [ -n "$old" ] && [ "$(sha256_of "$dest")" = "${old%% *}" ]; then
    echo "keep      $rel"; printf '%s\n' "$old" >> "$OUT_DIR/.checksums.new"; continue
  fi
  echo "fetch     $rel  <-  POST ${BASE}/exeQuery.php  $body"
  bytes="$(fetch_url "${BASE}/exeQuery.php" "$dest" "$body")" || exit 1
  case "$base" in
    T0262-juan*.html) grep -q '<div class="content" id="T0262D' "$dest" || { echo "ERROR: $rel has no T0262 content divs; server changed?" >&2; exit 1; } ;;
    T1718-juan*.html) grep -q '<div class="content" id="T1718D' "$dest" || { echo "ERROR: $rel has no T1718 content divs; server changed?" >&2; exit 1; } ;;
    tree-*.json)      grep -q '"id":' "$dest" || { echo "ERROR: $rel is not a node list; server changed?" >&2; exit 1; } ;;
  esac
  printf '%s  %s  # POST sdp.chibs.edu.tw/exeQuery.php %s (unversioned server), fetched %s, %s bytes\n' "$(sha256_of "$dest")" "$rel" "$body" "$TODAY" "$bytes" >> "$OUT_DIR/.checksums.new"
  sleep "$SLEEP"
done

# coverage check: the seven juan files must anchor 0001a01 … 0062c14 with no gap between consecutive files
prev=""
for j in 1 2 3 4 5 6 7; do
  f="$OUT_DIR/T0262-juan$j.html"
  first="$(grep -o 'name="[0-9]\{4\}[abc][0-9]\{2\}"' "$f" | head -1 | sed 's/name="//; s/"//')"
  last="$(grep -o 'name="[0-9]\{4\}[abc][0-9]\{2\}"' "$f" | tail -1 | sed 's/name="//; s/"//')"
  echo "juan $j   lines $first -> $last   nodes $(grep -c '<div class="content" id="T0262D' "$f")"
  prev="$last"
done
echo "total nodes: $(cat "$OUT_DIR"/T0262-juan?.html | grep -c '<div class="content" id="T0262D')"

# T1718 coverage: print each fetched 卷-half's own anchor range (a first/last print like the T0262
# check above, not a hard assertion -- exact 卷 boundaries from T34n1718.xml are checked against
# these files in tests/unit/test_sdp_fetch_outputs.py). Only 9 of the 20 keys have a POSTS entry
# (see "T1718 getHtml gaps" in the header); the rest print as GAP, not an error.
for k in 1a 1b 2a 2b 3a 3b 4a 4b 5a 5b 6a 6b 7a 7b 8a 8b 9a 9b 10a 10b; do
  f="$OUT_DIR/T1718-juan$k.html"
  if [ ! -f "$f" ]; then
    echo "T1718 juan$k   GAP (not fetched -- see \"T1718 getHtml gaps\" in this script's header)"
    continue
  fi
  first="$(grep -o 'name="[0-9]\{4\}[abc][0-9]\{2\}"' "$f" | head -1 | sed 's/name="//; s/"//')"
  last="$(grep -o 'name="[0-9]\{4\}[abc][0-9]\{2\}"' "$f" | tail -1 | sed 's/name="//; s/"//')"
  echo "T1718 juan$k   lines $first -> $last   nodes $(grep -c '<div class="content" id="T1718D' "$f")"
done

tmp="$(mktemp "${CHECKSUMS}.XXXXXX")"
{
  printf '%s\n' "$HEADER"
  if [ -f "$CHECKSUMS" ]; then
    awk -v p="$PREFIX" '$1 ~ /^#/ { next } index($2, p) == 1 { next } NF { print }' "$CHECKSUMS"
  fi
  cat "$OUT_DIR/.checksums.new"
} > "$tmp"
mv "$tmp" "$CHECKSUMS"; rm -f "$OUT_DIR/.checksums.new"
echo "wrote     $CHECKSUMS ($(grep -c "  $PREFIX" "$CHECKSUMS") entries under $PREFIX)"
