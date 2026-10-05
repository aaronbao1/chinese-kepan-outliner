#!/usr/bin/env bash
# scripts/fetch_cbeta_metadata.sh — fetch DILA's per-work metadata tables (title, Taishō/Xuzangjing 原書分類 = orig_category,
# CBETA 部類 = category, byline, dynasty …) from https://github.com/DILA-edu/cbeta-metadata (MIT), pinned to a commit,
# into data/raw/cbeta-metadata/ (gitignored), and record sha256 lines in scripts/CHECKSUMS.
#
# Input : network only (raw.githubusercontent.com)
# Output: data/raw/cbeta-metadata/T.json, X.json      work-info tables for the T and X canons ({"T0001": {vol, type, orig_category,
#                                                      category, title, juans, byline, dynasty, time_from, time_to, contributors}})
#         data/raw/cbeta-metadata/work-info-README.md  field documentation ("2022-10 起停用，請改用 … Authority-Databases", but the
#                                                      tables are still in the repo and still what cbeta-api reads)
#         data/raw/cbeta-metadata/README.md, LICENSE   repo README and MIT licence
#         scripts/CHECKSUMS                             lines under data/raw/cbeta-metadata/ (other scripts' lines preserved)
# Used by: scripts/survey_cbeta_xml_p5.py (joins orig_category/category to every xml-p5 file by work id).
#
# Usage : bash scripts/fetch_cbeta_metadata.sh           fetch missing/mismatched files, rewrite our CHECKSUMS lines
#         bash scripts/fetch_cbeta_metadata.sh --check   recompute sha256 and compare; exit 1 on mismatch/missing
#
# Pin (2026-09-22): master = commit af914b8d3ce6b7c929cbef5cef061e00bddda929 ("update textref/cbeta.csv for DocuSky", 2026-07-30)
#   GET https://api.github.com/repos/DILA-edu/cbeta-metadata/commits?per_page=1
# Politeness: one request at a time, 0.4 s between requests.
set -euo pipefail

COMMIT="af914b8d3ce6b7c929cbef5cef061e00bddda929"
BASE="https://raw.githubusercontent.com/DILA-edu/cbeta-metadata/${COMMIT}"
UA="chinese-workflow fetch script (research use; curl)"
SLEEP="0.4"
# repo path | local basename
FILES='
work-info/T.json|T.json
work-info/X.json|X.json
work-info/README.md|work-info-README.md
README.md|README.md
LICENSE|LICENSE
'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
OUT_DIR="data/raw/cbeta-metadata"; PREFIX="data/raw/cbeta-metadata/"; CHECKSUMS="scripts/CHECKSUMS"

MODE="fetch"
case "${1:-}" in "") ;; --check) MODE="check" ;; *) echo "usage: $0 [--check]" >&2; exit 2 ;; esac

sha256_of() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
recorded_line() { [ -f "$CHECKSUMS" ] || return 0; awk -v p="$1" '$1 !~ /^#/ && $2 == p { print; exit }' "$CHECKSUMS"; }

if [ "$MODE" = "check" ]; then
  fail=0
  printf '%s\n' "$FILES" | awk -F'|' 'NF>=2' | while IFS='|' read -r _src base; do
    rel="${PREFIX}${base}"; line="$(recorded_line "$rel")"
    if [ -z "$line" ]; then echo "NO-LINE   $rel"; exit 1; fi
    if [ ! -f "$rel" ]; then echo "MISSING   $rel"; exit 1; fi
    if [ "$(sha256_of "$rel")" = "${line%% *}" ]; then echo "OK        $rel"; else echo "MISMATCH  $rel"; exit 1; fi
  done || fail=1
  exit $fail
fi

mkdir -p "$OUT_DIR"; TODAY="$(date +%F)"; NEW="$(mktemp)"
printf '%s\n' "$FILES" | awk -F'|' 'NF>=2' | while IFS='|' read -r src base; do
  rel="${PREFIX}${base}"; old="$(recorded_line "$rel")"
  if [ -f "$rel" ] && [ -n "$old" ] && [ "$(sha256_of "$rel")" = "${old%% *}" ]; then
    echo "keep      $rel"; printf '%s\n' "$old" >> "$NEW"; continue
  fi
  url="${BASE}/${src}"; tmp="$(mktemp "${rel}.part.XXXXXX")"; hdr="$(mktemp)"
  echo "fetch     $rel  <-  $url"
  curl -fsSL --retry 3 --retry-delay 2 -A "$UA" -D "$hdr" -o "$tmp" "$url"
  bytes="$(wc -c < "$tmp" | tr -d ' ')"; clen="$(grep -i '^content-length:' "$hdr" | tail -1 | tr -dc '0-9' || true)"
  if [ -n "$clen" ] && [ "$clen" != "$bytes" ]; then rm -f "$tmp" "$hdr"; echo "ERROR: got $bytes bytes, Content-Length $clen: $url" >&2; exit 1; fi
  mv "$tmp" "$rel"; rm -f "$hdr"
  printf '%s  %s  # DILA-edu/cbeta-metadata commit %s (%s), fetched %s, %s bytes\n' "$(sha256_of "$rel")" "$rel" "${COMMIT:0:12}" "$src" "$TODAY" "$bytes" >> "$NEW"
  sleep "$SLEEP"
done

tmp="$(mktemp "${CHECKSUMS}.XXXXXX")"
{ awk -v p="$PREFIX" 'index($2, p) == 1 { next } { print }' "$CHECKSUMS"; cat "$NEW"; } > "$tmp"
mv "$tmp" "$CHECKSUMS"; rm -f "$NEW"
echo "wrote     $CHECKSUMS ($(grep -c "  $PREFIX" "$CHECKSUMS") entries under $PREFIX)"
