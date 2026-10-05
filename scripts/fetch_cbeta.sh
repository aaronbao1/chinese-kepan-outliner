#!/usr/bin/env bash
# scripts/fetch_cbeta.sh — fetch the CBETA XML P5 files this repo uses, pinned to git tag 2026R2 of
# https://github.com/cbeta-org/xml-p5, into data/raw/cbeta/ (gitignored), and record sha256 in scripts/CHECKSUMS.
#
# Input : network only (raw.githubusercontent.com, cbeta.org) + the WORKS table below.
# Output: data/raw/cbeta/<basename>.xml          verbatim CBETA XML (bytes untouched; CBETA punctuation/markup kept)
#         data/raw/cbeta/LICENCE-NOTICE.html     one-time snapshot of https://cbeta.org/copyright (版權宣告)
#         data/raw/cbeta/LICENCE-NOTICE.txt      the same rendered to plain text with pandoc, for reference
#         scripts/CHECKSUMS                      lines for files directly in data/raw/cbeta/ (not its subdirectories: the
#                                                survey/ and xml-p5-2018/ lines belong to scripts/fetch_cbeta_xml_p5.sh);
#                                                every other line is preserved
#
# Usage : bash scripts/fetch_cbeta.sh [FILE_ID ...]          fetch the listed works (default: every work in the table)
#                                                            and the licence notice, whatever is missing or mismatched;
#                                                            then update CHECKSUMS
#         bash scripts/fetch_cbeta.sh --check [FILE_ID ...]  recompute sha256 of the listed works (default: every
#                                                            data/raw/cbeta/ entry) and compare; exit 1 on any mismatch or
#                                                            missing file/line, exit 0 when everything matches
#         bash scripts/fetch_cbeta.sh --force [FILE_ID ...]  re-download the listed works and the licence notice
#         bash scripts/fetch_cbeta.sh --list                 print the table: file id, bytes, title
#         FILE_ID is a CBETA file id as in projects/*/project.toml, e.g. T34n1723. An id that is not in the table
#         stops the run: any other CBETA file comes from the whole-corpus clone, scripts/fetch_cbeta_xml_p5.sh.
#
# Idempotent: a file already on disk whose sha256 equals its CHECKSUMS line is not re-downloaded. A recorded line
# whose file has the same bytes after a (re-)download is kept byte-for-byte, with its original fetch date, in its
# place; new paths are appended. So in a fresh clone the fetch leaves scripts/CHECKSUMS unchanged and the working
# tree clean (run.json records the pipeline commit and a dirty flag). Lines get today's date only when the bytes
# differ from the recorded ones, or when no line exists yet.
#
# The licence notice is a snapshot of a live web page, not pinned data. cbeta.org serves it with per-request
# e-mail obfuscation (Cloudflare `data-cfemail` / `/cdn-cgi/l/email-protection` values), so a fresh download never
# reproduces the recorded HTML bytes, and the pandoc rendering depends on the local pandoc. Therefore: once lines
# exist, a fetch keeps them (the recorded snapshot is the provenance record; --force re-records), and --check
# reports a licence file whose bytes differ as CHANGED without failing. The XML works are checked strictly.
#
# Pinning / path discovery (done 2026-09-21 for the first 16 works, see the WORKS table):
#   tag 2026R2 -> commit dbdea41071e1e260ad84b72faefd4587333cf76d
#       GET https://api.github.com/repos/cbeta-org/xml-p5/git/refs/tags/2026R2               (HTTP 200)
#   every path below was confirmed in the recursive tree of that commit (5661 entries, truncated=false)
#       GET https://api.github.com/repos/cbeta-org/xml-p5/git/trees/dbdea41071e1e260ad84b72faefd4587333cf76d?recursive=1
#   The table records that listing's blob size (bytes) and git blob SHA-1, so a fetched file can be cross-checked
#   independently of this script:  wc -c <file>   and   git hash-object <file>
#   A downloaded file whose byte count differs from the tree's blob size aborts the run (truncation guard).
#   Works requested but not located in the tag: none (all 16 resolved; X0231 is in vol. X05, X0584 in X27,
#   B0048 and B0065 both in vol. B10 of 大藏經補編).
#   Added 2026-10-04: T12n0365, T37n1753 and T32n1666, the texts of projects/guanjing-shandao and projects/qixin-self,
#   which before then only the whole-corpus clone (fetch_cbeta_xml_p5.sh) supplied. Their size and blob SHA-1 are
#   those of the files in that clone at commit dbdea410 (wc -c, git hash-object), and a download from the tag gave
#   the same bytes.
#
# Licence: CBETA's 版權宣告 (snapshot in LICENCE-NOTICE.txt) releases 大正藏 vols 1–85, 卍新纂續藏 vols 1–90,
# 大藏經補編 vols 1–36 and the other 類別 A texts under CC BY-NC-SA 4.0, for non-profit use, with the notice
# and version information to be attached to any re-distributed or re-processed product; 商業利用 and 改作 are named
# as outside that scope (see data/README.md).
# Raw files are gitignored; never commit them.
#
# Politeness: one request at a time, 0.4 s sleep between requests, curl --retry 3.
# Portability: bash 3.2+ (macOS), curl, awk; sha256 via sha256sum or shasum; pandoc optional (plain-text rendering).

set -euo pipefail

TAG="2026R2"
TAG_COMMIT="dbdea41071e1e260ad84b72faefd4587333cf76d"
BASE="https://raw.githubusercontent.com/cbeta-org/xml-p5/${TAG}"
LICENCE_URL="https://cbeta.org/copyright"
UA="chinese-workflow fetch script (research use; curl)"
SLEEP="0.4"

# path in xml-p5 | blob size (bytes) at tag 2026R2 | git blob sha-1 (both from the tree listing) | <title level="m"> read from the fetched file
WORKS='
T/T09/T09n0262.xml|1125023|0a358b7b46e5f934c251c1feaebe7db4d6afd8b5|妙法蓮華經
T/T34/T34n1723.xml|2924340|0240d9e3950f213b33704233c0a566d20f59a34d|妙法蓮華經玄贊
T/T34/T34n1718.xml|1779083|5d4bb95c812c59ad387165894d0e24939f53d05e|妙法蓮華經文句
T/T34/T34n1721.xml|3119672|5311741cfe1f595a28211bc897a977a51dc1f243|法華義疏
T/T34/T34n1724.xml|659902|eab3fbc8fe98cd78a984b1f5fd2fd10434d00b86|法華玄贊義決
T/T33/T33n1703.xml|198305|20144b918f551f38ca8bdce4e6cbdbb6b6bff6e9|金剛般若波羅蜜經註解
T/T42/T42n1828.xml|7679759|ef5c5a3ebcc89d0f870159b5223ab88b259d0923|瑜伽論記
T/T08/T08n0235.xml|60525|57be3e4c93ac8a01f73a7fb8951d21cbaee7c866|金剛般若波羅蜜經
T/T10/T10n0279.xml|4579678|56c33cfc454062f803014831b1ed4e6ef5ac7749|大方廣佛華嚴經
T/T55/T55n2184.xml|136802|2754f33af652ce1a93fd796b45023462d502849d|新編諸宗教藏總錄
T/T35/T35n1735.xml|4543593|b900b9430371a98cd98fb511e057310229f31572|大方廣佛華嚴經疏
X/X05/X05n0231.xml|3222950|68f9ba6250502ee17ac9f340ee25f7c4384db96c|華嚴經疏科文 (卍續藏 vol. 5)
X/X27/X27n0584.xml|3306522|c73aa75c63b2c0402997f712da6272d09d85333b|法華三大部科文 (卍續藏 vol. 27)
G/G069/G069n1977.xml|5949|4bb8e54f72b81ee552bee22c73c0b47295defc51|科始終心要 (佛教大藏經 vol. 69)
B/B10/B10n0048.xml|277337|770f89c5efc1df2204448a6c539bc5b58fd7fbeb|辨了不了義善說藏論 (大藏經補編 vol. 10)
B/B10/B10n0065.xml|683444|9cbfc732618bfaf7a5b4434f628aa69c12fc6fc3|菩提道次第略論 (大藏經補編 vol. 10)
T/T12/T12n0365.xml|170086|07122ec6e08ad4fdbafc209c2afa9d01a17ecf71|佛說觀無量壽佛經
T/T37/T37n1753.xml|286593|f36cbf38a774e1ff07efaffe6180e76e6b2e1f14|觀無量壽佛經疏
T/T32/T32n1666.xml|142006|5cdce29005ed7b7e2b60243b99949923d0a24742|大乘起信論
'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
OUT_DIR="data/raw/cbeta"
PREFIX="data/raw/cbeta/"
CHECKSUMS="scripts/CHECKSUMS"
HEADER='# sha256  path  # provenance   (written by the scripts/fetch_*.sh scripts, each owning the lines under its own data/raw/<source>/ prefix; verify with "bash scripts/fetch_<source>.sh --check")'
LICENCE_FILES="LICENCE-NOTICE.html
LICENCE-NOTICE.txt"

usage() {
  cat <<EOF
usage: bash scripts/fetch_cbeta.sh [--check | --force | --list] [FILE_ID ...]
  (no option)  fetch the listed works (default: all) and the licence notice, then update scripts/CHECKSUMS
  --check      compare the files on disk with scripts/CHECKSUMS; exit 1 on a mismatch
  --force      re-download the listed works and the licence notice
  --list       print the pinned works: file id, bytes, title
  FILE_ID      a CBETA file id such as T34n1723 (see --list)
EOF
}

MODE="fetch"; FORCE=""; ONLY=""
for arg in "$@"; do
  case "$arg" in
    --check) MODE="check" ;;
    --force) FORCE="1" ;;
    --list) MODE="list" ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; exit 2 ;;
    *) ONLY="$ONLY ${arg%.xml}" ;;
  esac
done
if [ "$MODE" = "check" ] && [ -n "$FORCE" ]; then echo "ERROR: --check and --force cannot be combined" >&2; exit 2; fi

# every file id in the table, one per line (T09n0262, ...)
ALL_IDS="$(printf '%s\n' "$WORKS" | awk -F'|' 'NF>=3 { n = split($1, a, "/"); sub(/\.xml$/, "", a[n]); print a[n] }')"

if [ "$MODE" = "list" ]; then
  printf '%s\n' "$WORKS" | awk -F'|' 'NF>=3 { n = split($1, a, "/"); sub(/\.xml$/, "", a[n]); printf "%-12s %9s  %s\n", a[n], $2, $4 }'
  exit 0
fi

for id in $ONLY; do
  if ! printf '%s\n' "$ALL_IDS" | grep -qxF "$id"; then
    echo "ERROR: $id is not one of the works this script pins (list them: bash scripts/fetch_cbeta.sh --list)." >&2
    echo "       Any other CBETA file comes from the whole-corpus clone: bash scripts/fetch_cbeta_xml_p5.sh (about 5 GB)." >&2
    exit 2
  fi
done
# selected <file id>  -> true when the run covers this work (no FILE_ID given = every work)
selected() {
  [ -z "$ONLY" ] && return 0
  case " $ONLY " in *" $1 "*) return 0 ;; esac
  return 1
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

# recorded_line <relpath>  -> prints the CHECKSUMS line for that path (empty if none)
recorded_line() {
  [ -f "$CHECKSUMS" ] || return 0
  awk -v p="$1" '$1 !~ /^#/ && $2 == p { print; exit }' "$CHECKSUMS"
}
recorded_sha() { recorded_line "$1" | awk '{ print $1 }'; }

# fetch_url <url> <dest>  -> downloads to a temp file, checks Content-Length, moves into place, prints byte count
fetch_url() {
  local url="$1" dest="$2" tmp hdr bytes clen
  tmp="$(mktemp "${dest}.part.XXXXXX")"; hdr="$(mktemp "${dest}.hdr.XXXXXX")"
  if ! curl -fsSL --retry 3 --retry-delay 2 -A "$UA" -D "$hdr" -o "$tmp" "$url"; then
    rm -f "$tmp" "$hdr"; echo "ERROR: download failed: $url" >&2; return 1
  fi
  bytes="$(wc -c < "$tmp" | tr -d ' ')"
  clen="$(grep -i '^content-length:' "$hdr" | tail -1 | tr -dc '0-9' || true)"
  if [ -n "$clen" ] && [ "$clen" != "$bytes" ]; then
    rm -f "$tmp" "$hdr"; echo "ERROR: got $bytes bytes, Content-Length said $clen: $url" >&2; return 1
  fi
  mv "$tmp" "$dest"; rm -f "$hdr"
  printf '%s\n' "$bytes"
}

# ---------------------------------------------------------------- --check
if [ "$MODE" = "check" ]; then
  [ -f "$CHECKSUMS" ] || { echo "ERROR: $CHECKSUMS missing; run: bash scripts/fetch_cbeta.sh" >&2; exit 1; }
  fail=0; changed=0; n=0
  # every expected file must have a line, exist and match
  expected=""
  for id in $ALL_IDS; do selected "$id" && expected="$expected ${id}.xml"; done
  for base in $expected $LICENCE_FILES; do
    rel="${PREFIX}${base}"; n=$((n+1))
    want="$(recorded_sha "$rel")"
    if [ -z "$want" ]; then echo "NO-LINE   $rel"; fail=1; continue; fi
    if [ ! -f "$rel" ]; then echo "MISSING   $rel"; fail=1; continue; fi
    have="$(sha256_of "$rel")"
    if [ "$have" = "$want" ]; then echo "OK        $rel"
    elif printf '%s\n' "$LICENCE_FILES" | grep -qxF "$base"; then
      # a snapshot of a live page: differs on every download (see the header), so reported, not failed
      echo "CHANGED   $rel (not the recorded snapshot; expected for a re-fetched page, see the script header)"; changed=1
    else echo "MISMATCH  $rel"; fail=1; fi
  done
  # and, on a full check, every recorded line under our prefix must still hold (catches stale extra entries)
  if [ -z "$ONLY" ]; then
    known="$(printf '%s\n' "$ALL_IDS" | sed 's/$/.xml/'; printf '%s\n' "$LICENCE_FILES")"
    while read -r sha path _rest; do
      case "$sha" in ''|'#'*) continue ;; esac
      case "$path" in "$PREFIX"*/*) continue ;; "$PREFIX"*) ;; *) continue ;; esac   # subdirectories are not ours
      if printf '%s\n' "$known" | grep -qxF "${path#$PREFIX}"; then continue; fi   # already checked above
      n=$((n+1))
      if [ ! -f "$path" ]; then echo "MISSING   $path (extra entry)"; fail=1
      elif [ "$(sha256_of "$path")" = "$sha" ]; then echo "OK        $path (extra entry)"
      else echo "MISMATCH  $path (extra entry)"; fail=1; fi
    done < "$CHECKSUMS"
  fi
  if [ $fail -ne 0 ]; then verdict="FAILURES"
  elif [ $changed -ne 0 ]; then verdict="ALL OK (every XML file checked matches; the licence snapshot differs, see CHANGED)"
  else verdict="ALL OK"; fi
  echo "checked $n entries under $PREFIX; $verdict"
  exit $fail
fi

# ---------------------------------------------------------------- fetch
mkdir -p "$OUT_DIR"
TODAY="$(date +%F)"   # local date, matching the "accessed" dates used in context/research/*/sources.md
NEW="$OUT_DIR/.checksums.new"   # per-run list of CHECKSUMS lines for our prefix, in WORKS order
rm -f "$NEW"

# 1. the works
printf '%s\n' "$WORKS" | awk -F'|' 'NF>=3' | while IFS='|' read -r path size blob _title; do
  base="${path##*/}"; dest="${OUT_DIR}/${base}"; rel="${PREFIX}${base}"
  old="$(recorded_line "$rel")"
  if ! selected "${base%.xml}"; then
    [ -n "$old" ] && printf '%s\n' "$old" >> "$NEW"   # not asked for: its line stays as it is
    continue
  fi
  if [ -z "$FORCE" ] && [ -f "$dest" ] && [ -n "$old" ] && [ "$(sha256_of "$dest")" = "${old%% *}" ]; then
    echo "keep      $rel"; printf '%s\n' "$old" >> "$NEW"; continue
  fi
  url="${BASE}/${path}"
  echo "fetch     $rel  <-  $url"
  bytes="$(fetch_url "$url" "$dest")" || exit 1
  if [ "$bytes" != "$size" ]; then
    echo "ERROR: $rel is $bytes bytes but the xml-p5 tree at tag $TAG lists $size bytes (blob $blob); aborting" >&2
    rm -f "$dest"; exit 1
  fi
  new_sha="$(sha256_of "$dest")"
  if [ -n "$old" ] && [ "$new_sha" = "${old%% *}" ]; then
    printf '%s\n' "$old" >> "$NEW"   # the same bytes as recorded: the line (and its fetch date) is kept
  else
    [ -n "$old" ] && echo "WARNING: $rel differs from its recorded sha256; recording the new bytes" >&2
    printf '%s  %s  # xml-p5 tag %s, fetched %s\n' "$new_sha" "$rel" "$TAG" "$TODAY" >> "$NEW"
  fi
  sleep "$SLEEP"
done

# 2. the licence notice, fetched once (or with --force); HTML kept verbatim, plain text via pandoc for reading.
#    Recorded lines are kept unless --force: a re-fetched page never has the recorded bytes (see the header).
lic_html="${OUT_DIR}/LICENCE-NOTICE.html"; lic_txt="${OUT_DIR}/LICENCE-NOTICE.txt"
old_html="$(recorded_line "${PREFIX}LICENCE-NOTICE.html")"; old_txt="$(recorded_line "${PREFIX}LICENCE-NOTICE.txt")"
if [ -z "$FORCE" ] && [ -s "$lic_html" ] && [ -s "$lic_txt" ]; then
  echo "keep      ${PREFIX}LICENCE-NOTICE.html"; echo "keep      ${PREFIX}LICENCE-NOTICE.txt"
else
  echo "fetch     ${PREFIX}LICENCE-NOTICE.html  <-  $LICENCE_URL"
  fetch_url "$LICENCE_URL" "$lic_html" >/dev/null || exit 1
  if command -v pandoc >/dev/null 2>&1; then
    pandoc -f html -t plain --wrap=none "$lic_html" -o "$lic_txt"
  else
    echo "WARNING: pandoc not found; LICENCE-NOTICE.txt is a copy of the HTML" >&2; cp "$lic_html" "$lic_txt"
  fi
  if [ -z "$FORCE" ] && [ -n "$old_html" ] && [ "$(sha256_of "$lic_html")" != "${old_html%% *}" ]; then
    echo "note      ${PREFIX}LICENCE-NOTICE.html differs from the recorded snapshot (per-request e-mail obfuscation);" \
         "the recorded line is kept, and --check reports it as CHANGED"
  fi
fi
# lic_line <file> <recorded line> <provenance>  -> the recorded line, unless --force brought different bytes
lic_line() {
  local sha; sha="$(sha256_of "$1")"
  if [ -n "$2" ] && { [ -z "$FORCE" ] || [ "$sha" = "${2%% *}" ]; }; then printf '%s\n' "$2"
  else printf '%s  %s  # %s, fetched %s\n' "$sha" "$1" "$3" "$TODAY"; fi
}
lic_line "$lic_html" "$old_html" "snapshot of $LICENCE_URL (HTML, verbatim)" >> "$NEW"
lic_line "$lic_txt" "$old_txt" "snapshot of $LICENCE_URL rendered with pandoc -t plain" >> "$NEW"

# 3. update CHECKSUMS: the header, then every line in its place; our lines are swapped for this run's version where
#    they stand (so a run that changed nothing leaves the file byte-identical), lines of ours that are no longer in the
#    table are dropped, and new paths are appended at the end
tmp="$(mktemp "${CHECKSUMS}.XXXXXX")"
{
  printf '%s\n' "$HEADER"
  if [ -f "$CHECKSUMS" ]; then
    # our lines: files directly in $PREFIX; lines for its subdirectories (survey/, xml-p5-2018/) belong to other scripts
    awk -v p="$PREFIX" -v newf="$NEW" '
      BEGIN { while ((getline l < newf) > 0) { split(l, f, " "); line[f[2]] = l; order[++n] = f[2] } }
      $1 ~ /^#/ { next }
      index($2, p) == 1 && index(substr($2, length(p) + 1), "/") == 0 { if ($2 in line) { print line[$2]; done[$2] = 1 } next }
      NF { print }
      END { for (i = 1; i <= n; i++) if (!(order[i] in done)) print line[order[i]] }' "$CHECKSUMS"
  else
    cat "$NEW"
  fi
} > "$tmp"
# the count is of this script's lines only (files directly in $PREFIX), the same set --check counts
own_entries() { awk -v p="$PREFIX" '$1 !~ /^#/ && index($2, p) == 1 && index(substr($2, length(p) + 1), "/") == 0' "$CHECKSUMS" | wc -l | tr -d ' '; }
if [ -f "$CHECKSUMS" ] && cmp -s "$tmp" "$CHECKSUMS"; then
  rm -f "$tmp"; echo "unchanged $CHECKSUMS ($(own_entries) entries directly under $PREFIX)"
else
  mv "$tmp" "$CHECKSUMS"; echo "wrote     $CHECKSUMS ($(own_entries) entries directly under $PREFIX)"
fi
rm -f "$NEW"

# 4. report the work titles actually present in the fetched files (<title level="m"> of each TEI header)
echo "--- work titles in fetched files (<title level=\"m\">) ---"
for f in "$OUT_DIR"/*.xml; do
  [ -f "$f" ] || continue
  printf '%-16s %s\n' "$(basename "$f")" "$(grep -m1 -o '<title level="m"[^>]*>[^<]*</title>' "$f" | sed 's/<[^>]*>//g')"
done
