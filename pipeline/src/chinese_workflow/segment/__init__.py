"""segment stage of chinese_workflow. See README.md in this directory for the I/O contract.

Input : target InputText (+ optional outlined-text/1). Output: sentences/1 (segment.run).
The API (segment.py) is exported lazily, like chinese_workflow.ingest.
"""

__all__ = ["KINDS", "check", "run", "validate"]


def __getattr__(name):
    if name in __all__:
        from . import segment

        return getattr(segment, name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
