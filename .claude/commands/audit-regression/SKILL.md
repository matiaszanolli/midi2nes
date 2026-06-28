---
description: "Audit test-suite health — coverage gaps, weak assertions, flaky/stale tests"
argument-hint: "[--limit <N>]"
---

# Regression / Test-Hygiene Audit

Audit the **test suite itself**: where coverage is missing on code that can break, where
tests assert too little to catch a regression, and where tests are stale, flaky, or testing
the wrong thing. The output is a prioritized list of tests to add or strengthen — the safety
net for every other audit's fixes.

Shared protocol: `.claude/commands/_audit-common.md`. Severity:
`.claude/commands/_audit-severity.md` — a coverage gap on working code is LOW, but a gap on
a path that *has had bugs* or that emits NES register data is MEDIUM (the blast radius is a
silently-broken ROM).

## Parameters
- `--limit <N>` — cap findings (report the top N by risk). Default: no cap.

## Step 1: Inventory
```bash
ls tests/                                   # 43 test_*.py + conftest.py
python -m pytest -q --collect-only | tail -5
python -m pytest --cov=. --cov-report=term-missing -q   # if pytest-cov present
```
Cross-reference `tests/` against `_audit-common.md` § Project Layout: every subsystem
should have at least one test module. Map test file → subsystem it covers.

## Step 2: Coverage-Gap Dimensions

### Dimension 1: Untested subsystems / modules
A source module with no corresponding test, or only an import-smoke test. Weight by risk:
the NES-register path (`nes/emulator_core.py`, `nes/pitch_table.py`,
`nes/envelope_processor.py`), the exporters, the mappers, and the compiler are the
high-blast-radius gaps. A module with `--cov` < ~50% on a pipeline path is a finding.

### Dimension 2: Weak assertions
Tests that run code but assert almost nothing — `assert result is not None`, `assert
len(x) > 0` where the *values* matter. The NES-output tests especially must assert exact
register bytes / timer values, not just shape. Flag tests that would pass even if the music
came out wrong.

### Dimension 3: Round-trip / end-to-end gaps
The properties that unit tests miss: parse→...→ROM produces a valid ROM
(`tests/test_e2e_pipeline.py` is the anchor — is it exercised for arranger mode and
`--no-patterns`?); pattern compress→decompress equals the original; a generated `.nes`
passes `debug/check_rom.py`. Missing round-trip coverage on compression is MEDIUM
(it guards a CRITICAL failure mode).

### Dimension 4: Stale / wrong-target tests
Tests referencing renamed symbols, skipped/`xfail` tests with no tracking issue, tests that
assert old (now-incorrect) behavior, or tests pinned to checked-in artifact files that have
since changed. Confirm against current code.

### Dimension 5: Determinism / flakiness
Tests depending on multiprocessing scheduling (`ParallelPatternDetector`), dict/set
ordering, wall-clock timing, or filesystem temp paths without isolation. These pass locally
and fail in CI. Flag any test whose outcome can vary run-to-run.

### Dimension 6: Fixture & isolation hygiene
Tests that write into the repo root instead of a temp dir, leak state between tests, or
depend on a prior test having run. Check `tests/conftest.py` for shared fixtures and whether
they're used consistently.

## Step 3: For each gap, specify the test
Don't just say "needs a test" — name the module, the property to assert, and the concrete
input (a `test_midi/` sample or a crafted JSON). A finding the `/fix-issue` pipeline can
act on directly.

## Output
Write to: **`docs/audits/AUDIT_REGRESSION_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Coverage map** — subsystem → test module(s) → rough coverage / gap.
2. **Findings** — base format + `Dimension`; each names the test to add/strengthen.
3. **Prioritized backlog** — the top tests to write first, by blast radius.

Then suggest:
```
/audit-publish docs/audits/AUDIT_REGRESSION_<TODAY>.md
```
