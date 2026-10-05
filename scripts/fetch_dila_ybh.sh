#!/usr/bin/env bash
# scripts/fetch_dila_ybh.sh — fetch the standalone 科判 files and the text+科判 archives of three items of DILA's
# 瑜伽師地論資料庫 (YBh; https://ybh.dila.edu.tw/) into data/raw/dila-ybh/ (gitignored), plus a snapshot of the download
# page that carries the licence footer, and record sha256 in scripts/CHECKSUMS.
#
# Input : network only (ybh.dila.edu.tw) + the FILES table below.
# Output: data/raw/dila-ybh/T1579-kp.txt          瑜伽師地論 T1579, 科判 only (UTF-8, no BOM; one node per line, 2-space indent per
#                                                 level, label = depth letter A…Z,a… + sibling number, e.g. "      D1 問")
#         data/raw/dila-ybh/T1579-text-kp.zip     the same outline interleaved with the CBETA text (zip holding one T1579-kp.txt
#                                                 with 【D1 問】 headings; no Taishō line refs, juan headers only)
#         data/raw/dila-ybh/T1602-kp.txt, T1602-text-kp.zip     顯揚聖教論 T1602
#         data/raw/dila-ybh/T1605-kp.txt, T1605-text-kp.zip     大乘阿毘達磨集論 T1605 (the T1606-kp.txt served on 2026-09-21 was
#                                                               byte-identical to T1605-kp.txt, sha256 bddb5f66…, so it is not fetched)
#         data/raw/dila-ybh/download-page.html    verbatim snapshot of the download page (licence footer "© CC BY-SA 4.0")
#         scripts/CHECKSUMS                       lines for data/raw/dila-ybh/*; other scripts' lines preserved
#
# Usage : bash scripts/fetch_dila_ybh.sh            fetch whatever is missing or mismatched, then (re)write CHECKSUMS
#         bash scripts/fetch_dila_ybh.sh --check    recompute sha256 of every data/raw/dila-ybh/ entry and compare; exit 1 on any
#                                                   mismatch or missing file/line, exit 0 when everything matches
#         bash scripts/fetch_dila_ybh.sh --force    re-download everything (CHECKSUMS lines get today's date)
#
# Idempotent: a file already on disk whose sha256 equals its CHECKSUMS line is not re-downloaded and its line (with the
# original fetch date) is kept byte-for-byte.
#
# Provenance (checked 2026-09-21; see data/README.md):
#   download page  https://ybh.dila.edu.tw/pages/download?locale=zh&menu=download   ("更新紀錄 (2026-08-06)"; file dates 2026-06)
#   file URLs      https://ybh.dila.edu.tw/download2/kp/<code>-kp.txt   and   https://ybh.dila.edu.tw/download2/text-kp/<code>-text-kp.zip
#   The server is not versioned: DILA may replace these files at any time. The CHECKSUMS lines therefore record what was
#   fetched on the recorded date; a --check MISMATCH after a fresh fetch means DILA updated the file, not corruption.
#   Byte counts observed 2026-09-21: T1579-kp.txt 508614, T1579-text-kp.zip 1090454, T1602-kp.txt 96186,
#   T1602-text-kp.zip 186628, T1605-kp.txt 109166, T1605-text-kp.zip 65634.
#
# Licence (download page footer, verbatim HTML text): © CC BY-SA 4.0   (icons cc / by / sa; no NC icon). Page footer:
# "法鼓文理學院 DILA 1999-2026". Derived outlines must therefore be redistributed under CC BY-SA 4.0 with attribution to DILA
# (the outline sources DILA names per node — 【倫科】 遁倫 T1828, 【韓科】 韓清淨 — are given in the site's 使用說明：科判區).
# Raw files are gitignored; never commit them.
#
# Politeness: one request at a time, 0.4 s sleep between requests, curl --retry 3.
# Portability: bash 3.2+ (macOS), curl, awk; sha256 via sha256sum or shasum.

set -euo pipefail

BASE="https://ybh.dila.edu.tw"
UA="chinese-workflow fetch script (research use; curl)"
SLEEP="0.4"

# URL path | local file name
FILES='
/download2/kp/T1579-kp.txt|T1579-kp.txt
/download2/text-kp/T1579-text-kp.zip|T1579-text-kp.zip
/download2/kp/T1602-kp.txt|T1602-kp.txt
/download2/text-kp/T1602-text-kp.zip|T1602-text-kp.zip
/download2/kp/T1605-kp.txt|T1605-kp.txt
/download2/text-kp/T1605-text-kp.zip|T1605-text-kp.zip
/pages/download?locale=zh&menu=download|download-page.html
'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
OUT_DIR="data/raw/dila-ybh"
PREFIX="data/raw/dila-ybh/"
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

# fetch_url <url> <dest>  -> downloads to a temp file, checks Content-Length when present, moves into place, prints byte count
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

expected="$(printf '%s\n' "$FILES" | awk -F'|' 'NF>=2 { print $2 }')"

# ---------------------------------------------------------------- --check
if [ "$MODE" = "check" ]; then
  [ -f "$CHECKSUMS" ] || { echo "ERROR: $CHECKSUMS missing; run: bash scripts/fetch_dila_ybh.sh" >&2; exit 1; }
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
printf '%s\n' "$FILES" | awk -F'|' 'NF>=2' | while IFS='|' read -r path base; do
  dest="${OUT_DIR}/${base}"; rel="${PREFIX}${base}"
  old="$(recorded_line "$rel")"
  if [ -z "$FORCE" ] && [ -f "$dest" ] && [ -n "$old" ] && [ "$(sha256_of "$dest")" = "${old%% *}" ]; then
    echo "keep      $rel"; printf '%s\n' "$old" >> "$OUT_DIR/.checksums.new"; continue
  fi
  url="${BASE}${path}"
  echo "fetch     $rel  <-  $url"
  bytes="$(fetch_url "$url" "$dest")" || exit 1
  printf '%s  %s  # ybh.dila.edu.tw%s (unversioned server), fetched %s, %s bytes\n' "$(sha256_of "$dest")" "$rel" "$path" "$TODAY" "$bytes" >> "$OUT_DIR/.checksums.new"
  sleep "$SLEEP"
done

# licence sanity check on the snapshot
if ! grep -q 'CC BY-SA 4.0' "$OUT_DIR/download-page.html"; then
  echo "WARNING: the download page no longer contains 'CC BY-SA 4.0' — re-check the licence before using these files" >&2
fi

# rewrite CHECKSUMS: header, other scripts' lines (in their order), then ours
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
