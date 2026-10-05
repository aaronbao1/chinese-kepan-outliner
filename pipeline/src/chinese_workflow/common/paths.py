"""Repository locations. Everything is resolved relative to this file, so the package works from any
working directory of a source checkout (pip install -e pipeline)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # pipeline/src/chinese_workflow/common/paths.py
DATA = REPO_ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
REGISTRY = DATA / "eval-sets.json"
REFERENCE_OUTLINES = DATA / "reference-outlines"
SCHEMAS = REPO_ROOT / "pipeline" / "schemas"
PROJECTS = REPO_ROOT / "projects"
SKILLS = REPO_ROOT / "skills"
VALIDATOR = REPO_ROOT / "scripts" / "validate_outline.py"
CBETA_RAW = RAW / "cbeta"
CBETA_XML_P5 = CBETA_RAW / "xml-p5"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
CBETA_RELEASE = "2026R2"


def cbeta_xml_path(file_id: str) -> Path | None:
    """Local CBETA P5 file for a file id such as 'T34n1723': the pinned per-work copy under
    data/raw/cbeta/ first, then the whole-corpus clone data/raw/cbeta/xml-p5/<canon>/<vol>/.
    None when neither exists (a checkout without data/raw/)."""
    direct = CBETA_RAW / f"{file_id}.xml"
    if direct.exists():
        return direct
    canon = file_id.split("n")[0]  # 'T34'
    letters = "".join(ch for ch in canon if ch.isalpha())
    clone = CBETA_XML_P5 / letters / canon / f"{file_id}.xml"
    return clone if clone.exists() else None


def repo_relative(path) -> str:
    """Repository-relative form of a path (the absolute path when outside the repository)."""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)
