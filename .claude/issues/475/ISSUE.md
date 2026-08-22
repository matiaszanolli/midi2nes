# 475: REG-36: test_ca65_export.py writes 17 scratch .asm files into the repo root via CWD-relative paths

URL: https://github.com/matiaszanolli/midi2nes/issues/475
Labels: bug, low, regression

**Severity:** LOW · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-08-21.md

## Description
Seventeen tests across `TestCA65Exporter`-family classes and `TestExportSongBankBytecode` write their exporter output to bare relative paths (`Path("test_*.asm")`), which resolve against the process CWD — i.e. the repo root under the documented `python -m pytest` invocation. Each is wrapped in `try/finally: out.unlink()`, so the steady-state leak #231 had is absent (verified: no `test_*.asm` in the repo root after running the file today) — but the files still transit the repo root: a hard kill between write and `finally` leaves them behind, two tests using the same name would collide under `pytest-xdist`/parallel CI, and a same-named checked-in file would be silently clobbered. `tests/conftest.py` already provides the `temp_dir` fixture these classes ignore.

## Evidence
- `grep -n 'Path("test_' tests/test_ca65_export.py` → 17 sites (confirmed): lines 203, 316, 352, 402, 420, 441, 469, 482, 526-527, 579, 625, 647, 668, 706, 735, 758.
- `temp_dir` fixture confirmed present at `tests/conftest.py:50-54`.

## Impact
Hygiene/parallel-safety only on currently-working tests — LOW.

## Related
#231/REG-13 (precedent — `tests/test_drum_mapping.py` had the same pattern with a steady-state leak; that fix holds and now uses `tests/fixtures/` + `tempfile.TemporaryDirectory`)

## Suggested Fix
Convert the `unittest.TestCase` classes to create `self.tmp = tempfile.TemporaryDirectory()` in `setUp` (mirroring `TestJukeboxCompilationIntegration`, which already does this) and write outputs under it, dropping the per-test `try/finally` boilerplate.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
