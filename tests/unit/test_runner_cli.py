"""The runner's command line, `python -m chinese_workflow.runner run PROJECT.toml`, when a CBETA file
the project names is not on disk (a fresh clone before scripts/fetch_cbeta.sh): one line that names the
file and the fetch script, exit 1, no traceback. The exception stays a FileNotFoundError for every other
caller."""

from __future__ import annotations

import pytest

from chinese_workflow.common.paths import cbeta_xml_path
from chinese_workflow.ingest.text import CbetaFileMissing, load_input_text
from chinese_workflow.runner.__main__ import main

ABSENT = "T99n9999"  # no CBETA file has this id


def test_an_absent_file_id_raises_cbeta_file_missing():
    assert cbeta_xml_path(ABSENT) is None
    with pytest.raises(CbetaFileMissing) as exc:
        load_input_text(ABSENT)
    assert isinstance(exc.value, FileNotFoundError)
    assert "scripts/fetch_cbeta.sh" in str(exc.value) and "scripts/fetch_cbeta_xml_p5.sh" in str(exc.value)


def test_the_runner_reports_a_missing_cbeta_file_in_one_line(tmp_path, capsys):
    project = tmp_path / "project.toml"
    project.write_text('id = "absent"\nmode = "self-outlining"\nroot = "%s"\nspan = "whole"\n' % ABSENT,
                       encoding="utf-8")
    rc = main(["run", str(project), "--out", str(tmp_path / "out")])
    err = capsys.readouterr().err
    assert rc == 1
    assert err.startswith("failed: no local CBETA XML for %s" % ABSENT), err
    assert "Traceback" not in err and len(err.strip().splitlines()) == 1, err
