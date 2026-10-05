#!/usr/bin/env bash
# scripts/fetch_cbeta_xml_p5.sh — shallow-clone the two CBETA XML P5 corpus repositories used for the R02
# corpus-wide surveys (cb:mulu type/level census, T-canon lb/pb cross-release diff), pinned by commit.
#
# Input : network only (github.com)
# Output: data/raw/cbeta/xml-p5/        cbeta-org/xml-p5      at tag 2026R2  = commit dbdea41071e1e260ad84b72faefd4587333cf76d
#                                       ("CBETA 2026.R2", 2026-09-06 02:53:36 +0800; 5017 XML files in 26 canon dirs; no LICENSE file,
#                                        README points to https://www.cbeta.org/copyright.php)
#         data/raw/cbeta/xml-p5-2018/   cbeta-org/xml-p5-2018 (archived pre-2019-01-08 P5) at commit 1a9010b2004b632d60d6d5bf588e7035c70c37f8
#                                       ("Update README.md", 2019-01-08 19:51:12 +0800; 4717 XML files; the repo is frozen, so its
#                                        default branch head is the pin)
#         data/raw/cbeta/survey/        written by scripts/survey_cbeta_xml_p5.py (run separately; see its header)
#         scripts/CHECKSUMS             lines for the two archived reference files (S17) and the survey outputs are appended by
#                                       hand in this pass (see the "# xml-p5-2018 commit 1a9010b2" and "# derived" comments there);
#                                       the clones themselves are pinned by commit hash, not per-file sha256 (5017 + 4717 files).
#
# Usage : bash scripts/fetch_cbeta_xml_p5.sh            clone whatever is missing (idempotent; a clone at the right commit is kept)
#         bash scripts/fetch_cbeta_xml_p5.sh --check    verify both clones are at the pinned commits and clean; exit 1 otherwise
#
# Size  : about 2.5 GB (xml-p5) + 2.3 GB (xml-p5-2018) on disk, .git included (du -sh, 2026-10-04; the .git dirs are
#         515 MB and 474 MB). Both are gitignored (data/raw/). Never commit them. No project under projects/ needs
#         either clone: scripts/fetch_cbeta.sh fetches every file they name.
# Licence: CBETA 版權宣告 (CC BY-NC-SA 4.0 for 類別 A materials; see data/raw/cbeta/LICENCE-NOTICE.txt and
#          context/research/R02-cbeta-xml-structure-markup/findings.md § 3).
# Politeness: two git clones, nothing else.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

NEW_DIR="data/raw/cbeta/xml-p5";      NEW_URL="https://github.com/cbeta-org/xml-p5";      NEW_TAG="2026R2"
NEW_COMMIT="dbdea41071e1e260ad84b72faefd4587333cf76d"
OLD_DIR="data/raw/cbeta/xml-p5-2018"; OLD_URL="https://github.com/cbeta-org/xml-p5-2018"
OLD_COMMIT="1a9010b2004b632d60d6d5bf588e7035c70c37f8"

MODE="fetch"
case "${1:-}" in
  "") ;;
  --check) MODE="check" ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

head_of() { git -C "$1" rev-parse HEAD 2>/dev/null || true; }

check_one() {  # dir commit label
  local dir="$1" want="$2" label="$3" have
  if [ ! -d "$dir/.git" ]; then echo "MISSING   $dir ($label)"; return 1; fi
  have="$(head_of "$dir")"
  if [ "$have" != "$want" ]; then echo "MISMATCH  $dir is at ${have:0:10}, pinned ${want:0:10} ($label)"; return 1; fi
  if [ -n "$(git -C "$dir" status --porcelain)" ]; then echo "DIRTY     $dir has local modifications ($label)"; return 1; fi
  echo "OK        $dir @ ${have:0:10} ($label, $(find "$dir" -name '*.xml' -not -path '*/.git/*' | wc -l | tr -d ' ') xml files)"
}

if [ "$MODE" = "check" ]; then
  fail=0
  check_one "$NEW_DIR" "$NEW_COMMIT" "xml-p5 tag $NEW_TAG" || fail=1
  check_one "$OLD_DIR" "$OLD_COMMIT" "xml-p5-2018 archive" || fail=1
  exit $fail
fi

mkdir -p data/raw/cbeta
if [ "$(head_of "$NEW_DIR")" = "$NEW_COMMIT" ]; then
  echo "keep      $NEW_DIR @ ${NEW_COMMIT:0:10}"
else
  rm -rf "$NEW_DIR"
  echo "clone     $NEW_DIR  <-  $NEW_URL @ tag $NEW_TAG"
  git clone --depth 1 --branch "$NEW_TAG" --single-branch "$NEW_URL" "$NEW_DIR"
  [ "$(head_of "$NEW_DIR")" = "$NEW_COMMIT" ] || { echo "ERROR: tag $NEW_TAG resolved to $(head_of "$NEW_DIR"), expected $NEW_COMMIT (tag moved?)" >&2; exit 1; }
fi
if [ "$(head_of "$OLD_DIR")" = "$OLD_COMMIT" ]; then
  echo "keep      $OLD_DIR @ ${OLD_COMMIT:0:10}"
else
  rm -rf "$OLD_DIR"
  echo "clone     $OLD_DIR  <-  $OLD_URL (archived default branch)"
  git clone --depth 1 --single-branch "$OLD_URL" "$OLD_DIR"
  [ "$(head_of "$OLD_DIR")" = "$OLD_COMMIT" ] || { echo "ERROR: xml-p5-2018 head is $(head_of "$OLD_DIR"), expected $OLD_COMMIT (archive changed?)" >&2; exit 1; }
fi
echo "done. Next: python3 scripts/survey_cbeta_xml_p5.py --all   (writes data/raw/cbeta/survey/)"
