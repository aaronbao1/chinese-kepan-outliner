"""chinese_workflow.llm.cache — the JSONL response cache and the invalid-response log.

Input : <run_dir>/llm/responses.jsonl (or a cassette of the same shape), one JSON record per line:
        {hash, task, model, adapter, request, response, usage, returned_model, date}
Output: ResponseCache.get(hash) -> the last record with that hash, or None; put(record) appends.
        record_invalid(path, record) appends to <run_dir>/llm/invalid.jsonl.

Records are written with the keys sorted, one per line, CJK literal (UTF-8), so a cassette diff is
readable. Reading is tolerant of a torn last line (a killed run): it is skipped.
"""

from __future__ import annotations

import json
from pathlib import Path


def _dump(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"


def read_records(path) -> list:
    """Every parseable record of a JSONL file ([] when the file does not exist)."""
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn line from a killed run
            if isinstance(rec, dict) and "hash" in rec:
                out.append(rec)
    return out


class ResponseCache:
    """A JSONL file of answered requests keyed by request hash (the last record wins)."""

    def __init__(self, path):
        self.path = Path(path)
        self._index: dict | None = None
        self._mtime: float | None = None

    def _load(self) -> dict:
        mtime = self.path.stat().st_mtime if self.path.exists() else None
        if self._index is None or mtime != self._mtime:
            self._index = {rec["hash"]: rec for rec in read_records(self.path)}
            self._mtime = mtime
        return self._index

    def get(self, key: str) -> dict | None:
        return self._load().get(key)

    def put(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(_dump(record))
        self._index = None

    def __len__(self) -> int:
        return len(self._load())


def record_invalid(path, record: dict) -> None:
    """Append a rejected response to the invalid log."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(_dump(record))
