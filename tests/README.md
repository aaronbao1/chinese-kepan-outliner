# tests/

- `unit/`: pytest unit tests for `pipeline/`, one file per module or gold (for example `test_tier2_cases.py`, `test_eval_score.py`, `test_chunk_invariants.py`). `test_stage_boundaries.py` checks that no stage imports another stage's internals, and `test_sdp_eval_only_guard.py` fails if an sdp heading appears in any tracked file.
- `e2e/`: end-to-end runs of a project file through every stage (`test_outliner_e2e.py`): offline runs on the committed dev excerpts (`fixtures/projects/`), a replay of recorded resolver answers, and runs of the real projects in `projects/`, which need `data/raw/`.
- `eval/`: empty. The scorer is `pipeline/src/chinese_workflow/eval/score.py`; it scores an independent outline (`outline.json`) against a gold registered in `data/eval-sets.json`, and its tests are `unit/test_eval_score.py`.
- `fixtures/`:
  - `cbeta-xml-p5/`: verbatim CBETA XML with the header intact: excerpts holding the T1723 dev span and the T0262 chapter it comments on, and the whole of the short G1977;
  - `cbeta-api/`: saved CBETA API responses (catalogue, title search, full-text counts and three `works/toc` trees), offline evidence for E00 and the oracle for the tier-1 and ingest tests;
  - `kepan-formulae/`: the 148 parser cases (division formulae quoted from dev spans or texts outside the splits);
  - `llm-cassettes/`: recorded model answers for the replay adapter;
  - `outline-base/` and `outline-zh/`: minimal synthetic outlines under the base schema and the `zh-kepan` profile;
  - `sdp-synthetic/`: invented files in sdp's formats, for the sdp gold builder's tests (no sdp content);
  - `dila-ybh/`: the head of the DILA YBh 科判 file of T1605;
  - `scorer/`: the scorer's synthetic gold and registry;
  - `projects/`: the project files of the offline runs.

  Keep each fixture near 50 KB or less; the T1723 excerpt is 60 KB because its CBETA header alone is 56 KB. Fixtures quote only dev spans or texts outside T1718 and T1723 (`data/EVAL-SETS.md`, "Rules for gold data", rule 5).

`unit/test_gold_kuiji_testsplit.py` holds assertions about test-split answer keys. Do not open it while developing a parser or outliner that is evaluated on those spans; `data/EVAL-SETS.md`, "Do not open while developing", lists every such file.

Run from `pipeline/`: `.venv/bin/python -m pytest` (`pipeline/pyproject.toml` points pytest at `../tests` and puts `src/` on the path). Tests that need fetched data under `data/raw/` skip when it is absent; [`../scripts/README.md`](../scripts/README.md) says which script fetches what. Expected counts:
- With every source fetched (all `scripts/fetch_*.sh`, the survey `scripts/survey_cbeta_xml_p5.py`, and the sdp gold build of `data/EVAL-SETS.md`, "Rebuilding and checking"): 1,372 passed, 11 skipped, 1 xfailed. The 11 skips are the 卷-halves of T1718 that sdp's server does not serve. The xfail is a strict one: Shandao's commentary in `projects/guanjing-shandao` should leave at most 25 % of its lemmas unplaced, and it leaves 42.8 % (`docs/outliner-design.md` §5.5).
- With less data more tests skip: after Quickstart step 1 alone (`bash scripts/fetch_cbeta.sh`), 1,258 passed, 125 skipped, 1 xfailed; with no `data/raw/` at all, 1,115 passed and 269 skipped (the xfail is then skipped too). The skipped tests need the whole-corpus clone (`fetch_cbeta_xml_p5.sh`), sdp, YBh, the CBETA API responses or the BDRC ontology.
- In a copy without `.git` (for example from `git archive`), the 2 end-to-end tests that check `run.json`'s pipeline commit fail, and the tests that list git-tracked files skip.

If `data/raw/*` are symlinks into another checkout (as in a git worktree), a few tests that check gold paths fail (`test_gold_registry`'s eval-only check, `test_gold_ybh`, `test_gold_cbeta_mulu`, `test_gold_authored`). Use real directories.
