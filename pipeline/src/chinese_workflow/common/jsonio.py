"""UTF-8 JSON I/O and hashes. CJK stays literal; one key per line (indent=1), as the golds are written."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dumps(doc) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1) + "\n"


def write_json(doc, path) -> Path:
    """Write `doc` to `path` (parents created) and return the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(doc), encoding="utf-8")
    return path


def read_jsonl(path) -> list:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(records, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(doc) -> str:
    """Canonical JSON (sorted keys, no whitespace, CJK literal): the input of request and config hashes."""
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(doc) -> str:
    return sha256_text(canonical(doc))
