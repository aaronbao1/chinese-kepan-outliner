#!/usr/bin/env bash
# scripts/quickstart.sh — from a fresh clone to an outliner run: offline pipeline, no model, no API key.
#
# Input : projects/<id>/project.toml (default: lotus-kuiji-dharani-comm); network for the Python packages (PyPI) and
#         for the CBETA files the project names (raw.githubusercontent.com, cbeta.org), unless they are already here.
# Output: pipeline/.venv/                 created if missing; the package installed editable with its dev extra
#         data/raw/cbeta/<file id>.xml     the project's texts, via scripts/fetch_cbeta.sh (gitignored)
#         data/processed/<id>/             the run directory (gitignored): run.json, input-text/, outline/, segment/,
#                                          chunk/, export/ (pipeline/src/chinese_workflow/runner/__main__.py)
#
# Usage : bash scripts/quickstart.sh                    the default project, lotus-kuiji-dharani-comm
#         bash scripts/quickstart.sh qixin-self         one or more project ids (the directory names under projects/)
#         bash scripts/quickstart.sh --all              every project under projects/
#         QUICKSTART_PYTHON=/path/to/python3.12 bash scripts/quickstart.sh    the interpreter for the venv (>= 3.11)
#
# Steps : 1. pipeline/.venv. An existing venv is reused. Otherwise $QUICKSTART_PYTHON if set, else the first
#            Python >= 3.11 among python3.13, python3.12, python3.11 and python3, makes it with `-m venv` (an
#            interpreter whose pyexpat module cannot load, as with some Homebrew builds on recent macOS, is passed over:
#            its ensurepip fails). If none works and uv is installed, `uv venv --managed-python --python 3.12` makes it,
#            downloading a uv-managed CPython if needed. Then `pip install -e '.[dev]'` from pipeline/ (`uv pip` in a
#            uv venv), skipped when the venv already imports this checkout's package and its dependencies.
#         2. The project's root and commentary file ids that are not on disk are fetched with
#            `bash scripts/fetch_cbeta.sh <ids>` (a file outside its table needs scripts/fetch_cbeta_xml_p5.sh).
#         3. `python -m chinese_workflow.runner run ../projects/<id>/project.toml` from pipeline/.
# The shipped projects call no model ([resolver] adapter = "none"). The script runs no tests; for the tests:
#   cd pipeline && .venv/bin/python -m pytest -q
# Exit: 0 when every run exited 0; otherwise the last non-zero exit status.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
VENV="pipeline/.venv"
VPY="$VENV/bin/python"
DEFAULT_PROJECT="lotus-kuiji-dharani-comm"

usage() {
  cat <<EOF
usage: bash scripts/quickstart.sh [--all | PROJECT_ID ...]
  PROJECT_ID   a directory under projects/ (default: $DEFAULT_PROJECT); available:
$(for d in projects/*/project.toml; do d="${d%/project.toml}"; printf '               %s\n' "${d#projects/}"; done)
  --all        run every project
  QUICKSTART_PYTHON=/path/to/python   the interpreter for pipeline/.venv (>= 3.11)
EOF
}

PROJECTS=""
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --all) for d in projects/*/project.toml; do d="${d%/project.toml}"; PROJECTS="$PROJECTS ${d#projects/}"; done ;;
    -*) usage >&2; exit 2 ;;
    *) PROJECTS="$PROJECTS $arg" ;;
  esac
done
[ -n "$PROJECTS" ] || PROJECTS="$DEFAULT_PROJECT"
for p in $PROJECTS; do
  [ -f "projects/$p/project.toml" ] || { echo "ERROR: no projects/$p/project.toml" >&2; usage >&2; exit 2; }
done

# ---------------------------------------------------------------- 1. the venv
# usable <python> -> true for Python >= 3.11 whose pyexpat loads (ensurepip, and so `-m venv`, needs it)
usable() {
  "$1" -c 'import sys, pyexpat; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

make_venv() {
  local candidates="python3.13 python3.12 python3.11 python3" c py
  if [ -n "${QUICKSTART_PYTHON:-}" ]; then
    usable "$QUICKSTART_PYTHON" || { echo "ERROR: QUICKSTART_PYTHON=$QUICKSTART_PYTHON is not a working Python >= 3.11" >&2; exit 1; }
    candidates="$QUICKSTART_PYTHON"
  fi
  for c in $candidates; do
    py="$(command -v "$c" || true)"
    [ -n "$py" ] || continue
    if ! usable "$py"; then
      if "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
        echo "skip      $py ($("$py" --version 2>&1)): its pyexpat module does not load, so -m venv would fail"
      else
        echo "skip      $py ($("$py" --version 2>&1)): older than 3.11"
      fi
      continue
    fi
    echo "venv      $VENV  <-  $py -m venv  ($("$py" --version 2>&1))"
    if "$py" -m venv "$VENV"; then return 0; fi
    rm -rf "$VENV"; echo "note      '$py -m venv' failed" >&2
  done
  if command -v uv >/dev/null 2>&1; then
    echo "venv      $VENV  <-  uv venv --managed-python --python 3.12  (no system Python >= 3.11 could make a venv)"
    uv venv --managed-python --python 3.12 "$VENV"
    return 0
  fi
  echo "ERROR: needs Python >= 3.11 (the package reads project.toml with tomllib, new in 3.11). macOS's" >&2
  echo "       /usr/bin/python3 is 3.9. Install Python 3.11+ (and set QUICKSTART_PYTHON) or uv, then re-run." >&2
  exit 1
}

# installed -> true when the venv imports this checkout's package and the dependencies the runner and tests need
installed() {
  "$VPY" - "$REPO_ROOT/pipeline/src" <<'PY' >/dev/null 2>&1
import pathlib, sys
import chinese_workflow, jsonschema, lxml, pytest  # noqa: F401
src = pathlib.Path(sys.argv[1]).resolve()
sys.exit(0 if src in pathlib.Path(chinese_workflow.__file__).resolve().parents else 1)
PY
}

if [ -x "$VPY" ]; then
  "$VPY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || {
    echo "ERROR: $VENV is $("$VPY" --version 2>&1); the package needs Python >= 3.11. Remove $VENV and re-run." >&2; exit 1; }
  echo "venv      $VENV  (exists, $("$VPY" --version 2>&1))"
else
  make_venv
fi
if installed; then
  echo "install   skipped: $VENV already has chinese_workflow (this checkout), lxml, jsonschema and pytest"
elif [ -x "$VENV/bin/pip" ]; then
  echo "install   (cd pipeline && .venv/bin/python -m pip install -e '.[dev]')"
  (cd pipeline && .venv/bin/python -m pip install --quiet -e '.[dev]')
elif command -v uv >/dev/null 2>&1; then
  echo "install   (cd pipeline && uv pip install --python .venv -e '.[dev]')"
  (cd pipeline && uv pip install --quiet --python .venv -e '.[dev]')
else
  echo "ERROR: $VENV has no pip and uv is not installed; remove $VENV and re-run" >&2; exit 1
fi
installed || { echo "ERROR: the install did not give a working package in $VENV" >&2; exit 1; }

# ---------------------------------------------------------------- 2. the CBETA files
# missing_ids <project.toml> -> the project's root and commentary file ids with no local XML, one per line
missing_ids() {
  "$VPY" - "$1" <<'PY'
import sys
from chinese_workflow.common.paths import cbeta_xml_path
from chinese_workflow.common.project import load_project
proj = load_project(sys.argv[1])
for fid in (proj["root"], proj.get("commentary")):
    if fid and fid not in proj["xml"] and cbeta_xml_path(fid) is None:
        print(fid)
PY
}

missing=""
for p in $PROJECTS; do
  ids="$(missing_ids "projects/$p/project.toml")"
  for id in $ids; do case " $missing " in *" $id "*) ;; *) missing="$missing $id" ;; esac; done
done
if [ -n "$missing" ]; then
  echo "fetch     bash scripts/fetch_cbeta.sh$missing"
  # shellcheck disable=SC2086
  bash scripts/fetch_cbeta.sh $missing
else
  echo "fetch     skipped: every CBETA file the project names is already under data/raw/cbeta/"
fi

# ---------------------------------------------------------------- 3. the runs
status=0
for p in $PROJECTS; do
  echo
  echo "run       (cd pipeline && .venv/bin/python -m chinese_workflow.runner run ../projects/$p/project.toml)"
  rc=0
  (cd pipeline && .venv/bin/python -m chinese_workflow.runner run "../projects/$p/project.toml") || rc=$?
  out="data/processed/$p"
  if [ $rc -eq 0 ]; then
    echo "done      $p: exit 0. Outputs in $out/:"
    echo "            outline/outline.md, .docx      the independent outline"
    echo "            outline/outlined-text.md       the outlined-text"
    echo "            chunk/chunks.md, .docx         the interlinear outline (outlined-and-chunked-text)"
    echo "            export/*.jsonld                the knowledge-graph export"
    echo "            run.json                       commit, inputs and their sha256, per-stage counts"
  else
    echo "failed    $p: exit $rc (see the message above)" >&2; status=$rc
  fi
done
echo
echo "tests     cd pipeline && .venv/bin/python -m pytest -q"
exit $status
