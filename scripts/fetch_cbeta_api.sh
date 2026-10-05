#!/usr/bin/env bash
# scripts/fetch_cbeta_api.sh — fetch the CBETA API (https://cbdata.dila.edu.tw/stable/, DILA) responses that research thread
# R07 (context/research/R07-sabcad-vs-kepan-comparison/) cites for indicator conventions, the Vinaya/Song/Qing/Republican
# samples and the 玄贊科 catalogue leads, plus the works/toc outline trees used as oracles by the ingest tests
# (tests/unit/test_ingest_lines.py; R02 F8), into data/raw/cbeta-api/ (gitignored), recording sha256 in scripts/CHECKSUMS.
#
# The API is documented at https://cbdata.dila.edu.tw/ (see R07 F8 / R04 F36). Endpoints used here:
#   /stable/toc?q=<work>                      work-level metadata (title, byline, dynasty, juan count, cjk_chars)  -> toc-<work>.json
#   /stable/juans?work=<work>&juan=<n>         one juan as JSON whose results[0] is HTML with <span class="lb" id="T..._p...">
#                                              line ids (CBETA line ids; punctuation is CBETA's)                   -> juan-<work>-<n>.json
#   /stable/search?q=<term>                    full-text hit list by work                                          -> search-<slug>.json
#   /stable/search/kwic?q=<term>&work=<w>&juan=<n>   keyword-in-context lines with lb                              -> kwic-<w>-<n>-<slug>.json
#   /stable/works/toc?work=<work>              CBETA Online's outline tree for one work, built by cbeta-api toc.rake from
#                                              the XML's lb/milestone/cb:mulu (R02 F4/F8; fields title, file, juan, lb,
#                                              type, n, isFolder, children) — the oracle for the ingest mulu tree         -> works-toc-<work>.json
#
# Input : network only + the REQUESTS table below.
# Output: data/raw/cbeta-api/*.json ; scripts/CHECKSUMS lines for data/raw/cbeta-api/* (other scripts' lines preserved):
#           <sha256 of the file bytes>  <path>  # GET <url> (unversioned server), fetched <date>, <n> bytes,
#           content-sha256 <sha256 of the JSON without its top-level "time" field>
#         content-sha256 = sha256 of json.dumps(<parsed file minus top-level "time">, sort_keys=True, ensure_ascii=False,
#         separators=(",", ":")) encoded as UTF-8 (function content_sha_of below).
#
# Usage : bash scripts/fetch_cbeta_api.sh            fetch whatever is missing or mismatched, then (re)write CHECKSUMS;
#                                                    each download is compared with the recorded content-sha256 and
#                                                    reported as "same" or "CHANGED"
#         bash scripts/fetch_cbeta_api.sh --check    recompute both hashes of every data/raw/cbeta-api/ entry and compare
#                                                    (local integrity; no network)
#         bash scripts/fetch_cbeta_api.sh --force    re-download everything
#
# Idempotent: a file on disk whose bytes match its CHECKSUMS line is not re-downloaded and its line (original fetch date)
# is kept; a line written before content-sha256 existed gets it appended, computed from that verified file.
#
# Provenance / licence: the API serves CBETA text (CC BY-NC-SA per https://cbeta.org/copyright, snapshot in
# data/raw/cbeta/LICENCE-NOTICE.txt). The server is unversioned (the XML behind it tracks CBETA quarterly releases).
# Every toc, search, kwic and works/toc response (22 of the 34) carries a per-request server timing field at top level
# ("time": 0.0005…), so its bytes, and the sha256 in column 1, change on every fetch even when the served content does
# not; juans responses have no such field and re-fetch byte-identically (checked 2026-09-22 on works/toc T0262, toc
# X1126, search 玄贊科 and juans T1804/1: after removing "time", live == saved). Column 1 therefore proves only that the
# local file is the one fetched on the recorded date. Whether a fresh fetch (e.g. on a new clone) returned the same
# oracle is decided by content-sha256: "same" means only "time" differs, "CHANGED" means the served content changed.
# A fetch writes a new line (new column-1 sha256, today's date) for every download whose bytes differ from the record.
# Politeness: one request at a time, 0.4 s sleep between requests, curl --retry 3. Portability: bash 3.2+, curl, awk,
# sed, python3 (JSON check and content-sha256).

set -euo pipefail

BASE="https://cbdata.dila.edu.tw/stable"
UA="chinese-workflow fetch script (research use; curl)"
SLEEP="0.4"

# URL path+query (percent-encoded) | local file name
REQUESTS='
/toc?q=X1126|toc-X1126.json
/toc?q=X1127|toc-X1127.json
/toc?q=X1129|toc-X1129.json
/toc?q=X1130|toc-X1130.json
/toc?q=X0743|toc-X0743.json
/toc?q=T1804|toc-T1804.json
/toc?q=X0605|toc-X0605.json
/toc?q=X0606|toc-X0606.json
/toc?q=X0607|toc-X0607.json
/toc?q=X0622|toc-X0622.json
/toc?q=X0624|toc-X0624.json
/toc?q=X0274|toc-X0274.json
/toc?q=X0275|toc-X0275.json
/toc?q=TX0007|toc-TX0007.json
/juans?work=X1126&juan=1|juan-X1126-1.json
/juans?work=X1127&juan=1|juan-X1127-1.json
/juans?work=X1129&juan=1|juan-X1129-1.json
/juans?work=X1130&juan=1|juan-X1130-1.json
/juans?work=X0743&juan=1|juan-X0743-1.json
/juans?work=X0743&juan=2|juan-X0743-2.json
/juans?work=X0743&juan=3|juan-X0743-3.json
/juans?work=T1804&juan=1|juan-T1804-1.json
/juans?work=TX0007&juan=1|juan-TX0007-1.json
/juans?work=X0622&juan=1|juan-X0622-1.json
/juans?work=X0274&juan=1|juan-X0274-1.json
/juans?work=X0605&juan=1|juan-X0605-1.json
/search?q=%E7%8E%84%E8%B4%8A%E7%A7%91|search-xuanzanke.json
/search/kwic?q=%E7%8E%84%E8%B4%8A%E7%A7%91&work=TX0007&juan=1|kwic-TX0007-1-xuanzanke.json
/works/toc?work=T0262|works-toc-T0262.json
/works/toc?work=T1718|works-toc-T1718.json
/works/toc?work=T1723|works-toc-T1723.json
/works/toc?work=T1602|works-toc-T1602.json
/works/toc?work=T1605|works-toc-T1605.json
/works/toc?work=X0268|works-toc-X0268.json
'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
OUT_DIR="data/raw/cbeta-api"
PREFIX="data/raw/cbeta-api/"
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
# the content-sha256 recorded in a CHECKSUMS line (empty for a line written before it existed)
content_sha_in() { printf '%s\n' "$1" | sed -n 's/.*content-sha256 \([0-9a-f]\{64\}\).*/\1/p'; }
# sha256 of the response without its per-request "time" field (see header)
content_sha_of() {
  python3 -c 'import hashlib,json,sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
if isinstance(d, dict):
    d.pop("time", None)
s = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
print(hashlib.sha256(s.encode("utf-8")).hexdigest())' "$1"
}
# a CHECKSUMS line with content-sha256 appended when it lacks one ($2 = the verified local file)
with_content_sha() {
  if [ -n "$(content_sha_in "$1")" ]; then printf '%s\n' "$1"
  else printf '%s, content-sha256 %s\n' "$1" "$(content_sha_of "$2")"; fi
}

fetch_url() {
  local url="$1" dest="$2" tmp hdr bytes clen
  mkdir -p "$(dirname "$dest")"
  tmp="$(mktemp "${dest}.part.XXXXXX")"; hdr="$(mktemp "${dest}.hdr.XXXXXX")"
  if ! curl -fsSL --retry 3 --retry-delay 2 --max-time 300 -A "$UA" -D "$hdr" -o "$tmp" "$url"; then
    rm -f "$tmp" "$hdr"; echo "ERROR: download failed: $url" >&2; return 1
  fi
  bytes="$(wc -c < "$tmp" | tr -d ' ')"
  clen="$(grep -i '^content-length:' "$hdr" | tail -1 | tr -dc '0-9' || true)"
  if [ -n "$clen" ] && [ "$clen" != "$bytes" ]; then
    rm -f "$tmp" "$hdr"; echo "ERROR: got $bytes bytes, Content-Length said $clen: $url" >&2; return 1
  fi
  # every response must be JSON (the API answers errors as JSON too, so also require no "error" key at top level)
  if ! python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(1 if (isinstance(d,dict) and d.get("error")) else 0)' "$tmp"; then
    rm -f "$tmp" "$hdr"; echo "ERROR: response is not JSON or carries an error key: $url" >&2; return 1
  fi
  mv "$tmp" "$dest"; rm -f "$hdr"
  printf '%s\n' "$bytes"
}

expected_rels() { printf '%s\n' "$REQUESTS" | awk -F'|' -v o="$OUT_DIR/" 'NF>=2 { print o $2 }'; }

# ---------------------------------------------------------------- --check
if [ "$MODE" = "check" ]; then
  [ -f "$CHECKSUMS" ] || { echo "ERROR: $CHECKSUMS missing; run: bash scripts/fetch_cbeta_api.sh" >&2; exit 1; }
  fail=0; n=0
  while IFS= read -r rel; do
    n=$((n+1))
    line="$(recorded_line "$rel")"; want="${line%% *}"
    if [ -z "$line" ]; then echo "NO-LINE   $rel"; fail=1; continue; fi
    if [ ! -f "$rel" ]; then echo "MISSING   $rel"; fail=1; continue; fi
    wantc="$(content_sha_in "$line")"
    if [ -n "$wantc" ] && [ "$(content_sha_of "$rel")" = "$wantc" ]; then csame="1"; else csame=""; fi
    if [ "$(sha256_of "$rel")" = "$want" ]; then
      if [ -z "$wantc" ]; then echo "OK        $rel (no content-sha256 recorded; a plain fetch adds it)"
      elif [ -n "$csame" ]; then echo "OK        $rel"
      else echo "MISMATCH  $rel (bytes match but content-sha256 does not: the CHECKSUMS line is inconsistent)"; fail=1; fi
    elif [ -n "$csame" ]; then echo "MISMATCH  $rel (bytes differ; content without \"time\" is as recorded)"; fail=1
    else echo "MISMATCH  $rel"; fail=1; fi
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
TODAY="$(date +%F)"
NEW="$OUT_DIR/.checksums.new"; rm -f "$NEW"
CHANGED="$OUT_DIR/.changed"; rm -f "$CHANGED"

printf '%s\n' "$REQUESTS" | awk -F'|' 'NF>=2' | while IFS='|' read -r path name; do
  dest="${OUT_DIR}/${name}"; rel="$dest"
  old="$(recorded_line "$rel")"
  if [ -z "$FORCE" ] && [ -f "$dest" ] && [ -n "$old" ] && [ "$(sha256_of "$dest")" = "${old%% *}" ]; then
    echo "keep      $rel"; with_content_sha "$old" "$dest" >> "$NEW"; continue
  fi
  url="${BASE}${path}"
  echo "fetch     $rel  <-  $url"
  bytes="$(fetch_url "$url" "$dest")" || exit 1
  sha="$(sha256_of "$dest")"; csha="$(content_sha_of "$dest")"; oldc="$(content_sha_in "$old")"
  if [ -n "$old" ] && [ "$sha" = "${old%% *}" ]; then
    echo "same      $rel (bytes as recorded; line kept)"; with_content_sha "$old" "$dest" >> "$NEW"
  else
    if [ -n "$oldc" ] && [ "$csha" = "$oldc" ]; then
      echo "same      $rel (content as recorded; only \"time\" differs)"
    elif [ -n "$oldc" ]; then
      echo "CHANGED   $rel (content differs from the recorded fetch)"; printf '%s\n' "$rel" >> "$CHANGED"
    fi
    printf '%s  %s  # GET cbdata.dila.edu.tw/stable%s (unversioned server), fetched %s, %s bytes, content-sha256 %s\n' "$sha" "$rel" "$path" "$TODAY" "$bytes" "$csha" >> "$NEW"
  fi
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
if [ -f "$CHANGED" ]; then
  echo "WARNING: $(wc -l < "$CHANGED" | tr -d ' ') response(s) differ in content from the recorded fetch; re-check the tests and" \
       "findings that use them before trusting them as oracles:" >&2
  sed 's/^/  /' "$CHANGED" >&2; rm -f "$CHANGED"
fi
