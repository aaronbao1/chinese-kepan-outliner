"""Project files: projects/<id>/project.toml (docs/outliner-design.md §11).

TOML because Python 3.11+ reads it with the standard library (tomllib); the plan's project.yaml would add a
dependency. A project names the texts, the mode, the scheme and the run settings of one (text, commentary)
pair. load_project() returns a plain dict with defaults filled in; resolve_span() turns a span spec into
inclusive lineheads.

    id = "lotus-kuiji-dharani-comm"
    title = "..."
    mode = "sutra"                    # or "self-outlining"
    root = "T09n0262"                 # CBETA file id: the sūtra (sūtra mode) or the treatise (self-outlining)
    commentary = "T34n1723"           # sūtra mode only
    scheme_id = "kuiji-xuanzan"
    target_role = "commentary"        # the text the outlined-text and the chunks are over
    span = "dev"                      # dev | validation | whole | "<first linehead>..<last linehead>"
    source = "tier2"                  # tier1 | tier2 | hybrid | oracle
    [xml]                             # optional per-file XML overrides (fixtures), paths relative to the repo
    T34n1723 = "tests/fixtures/cbeta-xml-p5/T34n1723-excerpt-p0850a19-p0850b19.xml"
    [[scheme.level1]]                 # optional scheme prior (design §5.3)
    heading_src = "序分"; from_pin = "序品"; to_pin = "序品"; source = "..."
    [resolver]                        # adapter = none | replay | claude | interactive; model; cassette
    [chunk]                           # sentence_cap = 6; size_chars = 180
    [segment]                         # strategy = 2
    [export]                          # enabled = true
    [outline]                         # heading_style = "source" (ordinal kept, as the golds) | "label"
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from .paths import REPO_ROOT
from .splits import load_registry, named_span

DEFAULTS = {
    "title": "",
    "mode": "sutra",
    "commentary": None,
    "scheme_id": "unnamed-scheme",
    "target_role": "commentary",
    "span": "whole",
    "source": "tier2",
    "xml": {},
    "scheme": {"level1": []},
    "resolver": {"adapter": "none", "model": None, "cassette": None},
    "chunk": {"sentence_cap": 6, "size_chars": 180},
    "segment": {"strategy": 2},
    "export": {"enabled": True},
    "outline": {"heading_style": "source"},
}


def load_project(path) -> dict:
    path = Path(path)
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    proj = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    for key, value in raw.items():
        if isinstance(value, dict) and isinstance(proj.get(key), dict):
            proj[key] = {**proj[key], **value}
        else:
            proj[key] = value
    proj["_path"] = str(path)
    if "id" not in proj:
        proj["id"] = path.parent.name
    if proj["mode"] not in ("sutra", "self-outlining"):
        raise ValueError("mode must be sutra or self-outlining: %r" % proj["mode"])
    if proj["mode"] == "sutra" and not proj.get("commentary"):
        raise ValueError("sūtra mode needs a commentary file id")
    if proj["mode"] == "self-outlining":
        proj["commentary"] = None
        proj["target_role"] = "root"
    proj["xml"] = {k: str((REPO_ROOT / v).resolve()) if not Path(v).is_absolute() else v
                   for k, v in proj["xml"].items()}
    cassette = proj["resolver"].get("cassette")
    if cassette and not Path(cassette).is_absolute():
        proj["resolver"]["cassette"] = str((REPO_ROOT / cassette).resolve())
    return proj


def resolve_span(spec, file_id: str, all_lineheads: list, registry: dict | None = None):
    """A span spec -> (first, last) inclusive lineheads, or None for the whole file.

    'dev' / 'validation' / 'test' take the registry's span of that split in `file_id` (a split file,
    T34n1718 or T34n1723; its end-exclusive end becomes the previous line); 'whole' / None -> None;
    'A..B' -> (A, B)."""
    if spec in (None, "", "whole"):
        return None
    if isinstance(spec, (list, tuple)):
        return (spec[0], spec[1])
    if ".." in spec:
        a, b = spec.split("..", 1)
        return (a.strip(), b.strip())
    registry = registry or load_registry()
    spans = named_span(registry, file_id, spec)
    if not spans:
        raise ValueError("no %s span for %s in data/eval-sets.json" % (spec, file_id))
    start, end = spans[0]
    pos = {lh: i for i, lh in enumerate(all_lineheads)}
    if start not in pos:
        raise ValueError("span start %s not in %s" % (start, file_id))
    if end is None:
        last = all_lineheads[-1]
    elif end in pos:
        last = all_lineheads[pos[end] - 1]
    else:  # a fixture excerpt that stops before the exclusive end
        last = all_lineheads[-1]
    return (start, last)
