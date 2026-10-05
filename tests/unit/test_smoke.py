"""Smoke test: the package imports. Replace with real tests as stages land."""


def test_import():
    import chinese_workflow  # noqa: F401

    assert chinese_workflow.__version__
