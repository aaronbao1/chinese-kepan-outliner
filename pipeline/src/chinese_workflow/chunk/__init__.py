"""chunk stage of chinese_workflow. See README.md in this directory for the I/O contract.

    build_chunks(doc, outlined_text, sentences, target, ...) -> chunks/1 dict   (chunker.py)
    run(outline, outlined_text, sentences, target, out_dir, ...) -> writes chunks.json/.md/.docx
    render_md / parse_md / render_docx                                        (render.py)

Exported lazily, so that `python -m chinese_workflow.chunk` does not import a module twice.
"""

__all__ = ["build_chunks", "parse_md", "render_docx", "render_md", "run", "validate_chunks"]

_WHERE = {"build_chunks": "chunker", "run": "chunker", "validate_chunks": "chunker",
          "render_md": "render", "parse_md": "render", "render_docx": "render"}


def __getattr__(name):
    if name in _WHERE:
        import importlib

        return getattr(importlib.import_module("%s.%s" % (__name__, _WHERE[name])), name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
