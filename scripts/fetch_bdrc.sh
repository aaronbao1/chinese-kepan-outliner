#!/usr/bin/env bash
# scripts/fetch_bdrc.sh — fetch the BDRC Buddhist Digital Ontology (core/bdo.ttl) from https://github.com/buda-base/owl-schema
# pinned to one commit, into data/raw/bdrc/ (gitignored), recording sha256 in scripts/CHECKSUMS.
#
# Why: R07 (sa bcad vs kēpàn) needs to see how BDRC models outlines and locations (bdo:Outline / bdo:hasOutline?,
# bdo:contentLocation…) before writing the Chinese extension of context/baseline/outline-schema.json.
#
# Input : network only (raw.githubusercontent.com) + the FILES table below.
# Output: data/raw/bdrc/owl-schema/core/bdo.ttl   the ontology, bytes untouched (Turtle, UTF-8)
#         scripts/CHECKSUMS                       lines for data/raw/bdrc/*; other scripts' lines preserved
#
# Usage : bash scripts/fetch_bdrc.sh            fetch whatever is missing or mismatched, then (re)write CHECKSUMS
#         bash scripts/fetch_bdrc.sh --check    recompute sha256 of every data/raw/bdrc/ entry and compare; exit 1 on any
#                                               mismatch or missing file/line, exit 0 when everything matches
#         bash scripts/fetch_bdrc.sh --force    re-download everything (CHECKSUMS lines get today's date)
#
# Idempotent: a file already on disk whose sha256 equals its CHECKSUMS line is not re-downloaded and its line (with the
# original fetch date) is kept byte-for-byte.
#
# Pinning / discovery (done 2026-09-22):
#   repository default branch master, HEAD 4f3bf4a15582adfe19b0bdf82f24607363638008
#       GET https://api.github.com/repos/buda-base/owl-schema/git/refs/heads/master     (HTTP 200)
#       GET https://api.github.com/repos/buda-base/owl-schema  -> pushed_at 2025-10-14T08:18:44Z, license: null
#       GET https://api.github.com/repos/buda-base/owl-schema/contents/core -> bdo.ttl 161536 bytes,
#           git blob 8ce5453931700a7a94943d72450100b88499c91d
#   Licence: the GitHub licence field is null and no LICENSE file was listed; the README (R07 S30) was fetched on
#   2026-09-16. Treat the file as read-only reference material; do not redistribute.
#
# Politeness: one request at a time, 0.4 s sleep between requests, curl --retry 3.
# Portability: bash 3.2+ (macOS), curl, awk; sha256 via sha256sum or shasum.

set -euo pipefail

COMMIT="4f3bf4a15582adfe19b0bdf82f24607363638008"
BASE="https://raw.githubusercontent.com/buda-base/owl-schema/${COMMIT}"
UA="chinese-workflow fetch script (research use; curl)"
SLEEP="0.4"

# repo path | local path under OUT_DIR | expected bytes | git blob sha-1
FILES='
core/bdo.ttl|core/bdo.ttl|161536|8ce5453931700a7a94943d72450100b88499c91d
'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
OUT_DIR="data/raw/bdrc/owl-schema"
PREFIX="data/raw/bdrc/"
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

fetch_url() {
  local url="$1" dest="$2" tmp hdr bytes clen
  mkdir -p "$(dirname "$dest")"
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

expected_rels() { printf '%s\n' "$FILES" | awk -F'|' -v o="$OUT_DIR/" 'NF>=3 { print o $2 }'; }

# ---------------------------------------------------------------- --check
if [ "$MODE" = "check" ]; then
  [ -f "$CHECKSUMS" ] || { echo "ERROR: $CHECKSUMS missing; run: bash scripts/fetch_bdrc.sh" >&2; exit 1; }
  fail=0; n=0
  while IFS= read -r rel; do
    n=$((n+1))
    want="$(recorded_sha "$rel")"
    if [ -z "$want" ]; then echo "NO-LINE   $rel"; fail=1; continue; fi
    if [ ! -f "$rel" ]; then echo "MISSING   $rel"; fail=1; continue; fi
    if [ "$(sha256_of "$rel")" = "$want" ]; then echo "OK        $rel"; else echo "MISMATCH  $rel"; fail=1; fi
  done <<EOT
$(expected_rels)
EOT
  while read -r sha path _rest; do
    case "$sha" in ''|'#'*) continue ;; esac
    case "$path" in "$PREFIX"*) ;; *) continue ;; esac
    if expected_rels | grep -qxF "$path"; then continue; fi
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
TODAY="$(date +%F)"   # local date, matching the "accessed" dates used in context/research/*/sources.md
NEW="$OUT_DIR/.checksums.new"; rm -f "$NEW"

printf '%s\n' "$FILES" | awk -F'|' 'NF>=3' | while IFS='|' read -r repo_path local_path size blob; do
  dest="${OUT_DIR}/${local_path}"; rel="$dest"
  old="$(recorded_line "$rel")"
  if [ -z "$FORCE" ] && [ -f "$dest" ] && [ -n "$old" ] && [ "$(sha256_of "$dest")" = "${old%% *}" ]; then
    echo "keep      $rel"; printf '%s\n' "$old" >> "$NEW"; continue
  fi
  url="${BASE}/${repo_path}"
  echo "fetch     $rel  <-  $url"
  bytes="$(fetch_url "$url" "$dest")" || exit 1
  if [ "$bytes" != "$size" ]; then
    echo "ERROR: $rel is $bytes bytes but the repository listing at commit ${COMMIT:0:7} says $size; aborting" >&2
    rm -f "$dest"; exit 1
  fi
  printf '%s  %s  # buda-base/owl-schema commit %s, fetched %s\n' "$(sha256_of "$dest")" "$rel" "${COMMIT:0:12}" "$TODAY" >> "$NEW"
  sleep "$SLEEP"
done

tmp="$(mktemp "${CHECKSUMS}.XXXXXX")"
{
  printf '%s\n' "$HEADER"
  if [ -f "$CHECKSUMS" ]; then
    awk -v p="$PREFIX" '$1 ~ /^#/ { next } index($2, p) == 1 { next } NF { print }' "$CHECKSUMS"
  fi
  cat "$NEW"
} > "$tmp"
mv "$tmp" "$CHECKSUMS"; rm -f "$NEW"
echo "wrote     $CHECKSUMS ($(grep -c "  $PREFIX" "$CHECKSUMS") entries under $PREFIX)"
