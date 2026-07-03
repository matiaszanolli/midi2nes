# REG-13: test_drum_mapping.py depends on a gitignored, untracked repo-root fixture and leaks invalid.json into the repo root with no cleanup

- **Issue**: #231
- **Severity**: MEDIUM
- **Dimension**: Fixture & isolation hygiene (Dim 6) + stale/wrong-target (Dim 4)
- **Location**: `tests/test_drum_mapping.py:15` (`self.test_index_path = "test_dpcm_index.json"`), `:66-68` (`test_invalid_index_file` writes `"invalid.json"`)
- **Status**: NEW
- **Source**: `docs/audits/AUDIT_REGRESSION_2026-07-03.md`

## Description
Every other test file that needs a DPCM index fixture points at the checked-in
`tests/fixtures/test_dpcm_index.json` (`test_track_mapper.py:161,205`, `test_integration.py:54,101`,
`test_enhanced_drum_mapper.py:36,57,85`). `test_drum_mapping.py` alone uses the bare relative path
`"test_dpcm_index.json"`, which resolves against the process CWD — i.e. the repo root when tests
are run the documented way (`python -m pytest` from the repo root). That root-level file is not
tracked by git (`git ls-files | grep -x test_dpcm_index.json` → no match) and is explicitly excluded
by `.gitignore:29` (`/*.json`). It currently exists on this machine only as stray, untracked cruft
(dated Sep 30 2025 — clearly a leftover from a prior manual run, not a fixture anyone maintains).
Separately, `test_invalid_index_file` (`:66-68`) does `open("invalid.json", "w")` — also a bare
relative path into the repo root — with no `tearDown`/cleanup; it also matches the `.gitignore`
`/*.json` pattern, so `git status` never surfaces it, but it persists on disk after every test run.

## Evidence
```
$ git ls-files tests/fixtures/ | grep dpcm
tests/fixtures/test_dpcm_index.json
$ git ls-files | grep -x "test_dpcm_index.json"
(no output)                                  # not tracked at repo root
$ git check-ignore -v test_dpcm_index.json invalid.json
.gitignore:29:/*.json  test_dpcm_index.json
.gitignore:29:/*.json  invalid.json
$ ls -la test_dpcm_index.json invalid.json
-rwxr-xr-x 1 matias matias 449 Sep 30  2025 test_dpcm_index.json
-rwxr-xr-x 1 matias matias  12 Jul  3 15:03 invalid.json
```

## Impact
On a fresh `git clone` (or any CI environment without that untracked leftover file —
this repo has no `.github/` CI config today, so it has never been caught), every test in
`TestDrumMapping` that reads `self.test_index_path` (`test_velocity_ranges`,
`test_sample_id_is_index_id_not_allocation_order`, `test_invalid_index_file`, `test_noise_fallback`)
would raise `FileNotFoundError` — a confusing false failure with no relation to an actual code
regression, in a file whose entire purpose is regression-guarding drum-sample-id mapping (`#65`).
Independently, the no-cleanup `invalid.json` write litters the working tree on every local run.

## Related
Adjacent to #65 (drum-sample-id regression guard) which this test file exists to protect.

## Suggested Fix
Point `self.test_index_path` at `"tests/fixtures/test_dpcm_index.json"` like the other three test
files do. Write `invalid.json` via `tempfile.TemporaryDirectory()` (or the shared `temp_dir`/`tmp_path`
fixture) with automatic cleanup instead of a bare relative path.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
