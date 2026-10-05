"""ingest stage of chinese_workflow. See README.md in this directory for the I/O contract.

The line extractor (lines.py) is exported lazily, so that
`python -m chinese_workflow.ingest.lines` does not import the module twice.
"""

__all__ = [
    "Extraction",
    "TextIndex",
    "build_index",
    "extract",
    "find",
    "find_spans",
    "is_punct",
    "iter_lines",
    "strip_punct",
]


def __getattr__(name):
    if name in __all__:
        from . import lines

        return getattr(lines, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
