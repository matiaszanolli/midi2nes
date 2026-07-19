# REG-22: test_parser_fast.py + test_patterns.py together hang in pytest (each passes alone)

**Severity:** LOW · **Domain:** regression · **Source:** discovered while verifying fix-issue batch #343/#344/#345 (2026-07-18)

## Description
Running `tests/test_parser_fast.py` and `tests/test_patterns.py` together in a
single `pytest` invocation hangs indefinitely, in **either** file order. Each
file passes individually (`test_parser_fast.py`: 38 passed in 0.49s;
`test_patterns.py`: 77 passed in ~24s). This is a test-isolation issue, not a
production code bug — no MIDI→ROM build path runs these two files' code
together in-process.

Also observed (not yet reduced to the same 2-file minimal case): the wider
combination `test_pattern_integration.py` + `test_parser_fast.py` +
`test_patterns.py` + `test_loop_manager.py` + `test_enhanced_loop_patterns.py`
run together also hangs; each of those 5 files passes individually.

## Evidence
```
$ timeout 40 python -m pytest -q tests/test_parser_fast.py tests/test_patterns.py
# exit 124 (timeout), 68 dots printed then hang

$ timeout 40 python -m pytest -q tests/test_patterns.py tests/test_parser_fast.py
# exit 124 (timeout), 30 dots printed then hang -- reversed order hangs EARLIER,
# suggesting collection/import order (not just execution order) matters

$ timeout 30 python -m pytest -q tests/test_parser_fast.py   # alone
38 passed in 0.49s

$ timeout 30 python -m pytest -q tests/test_patterns.py      # alone
77 passed in 24.10s
```
Confirmed present on `master` at commit `65d43ba` (current tip as of filing),
which includes this session's #332/#333 (`ParallelPatternDetector`
sub-chunking/serial-threshold changes, PR #353) and #343/#344/#345
(PR #354) — **not yet bisected** to determine whether it predates those
changes or was introduced by them. `ParallelPatternDetector` uses real
`multiprocessing.ProcessPoolExecutor`; a leading hypothesis (unverified) is
some interaction between `test_parser_fast.py`'s fixtures/mocks and
multiprocessing/fork state left over for `test_patterns.py`'s later
`ParallelPatternDetector`-backed tests, but this needs actual investigation,
not assumption.

## Impact
No production impact — this is purely a test-execution issue. But it makes a
full unscoped `pytest` run hang, same failure mode (if not same root cause)
as #352 before its fix. Given the project's established practice of always
scoping `pytest` invocations to specific files, this may be one more reason
that practice exists, undiscovered until now because these two files are
rarely run together deliberately.

## Suggested Fix
Bisect within `test_parser_fast.py` (which test/fixture, if any, is
necessary to trigger it — e.g. binary-search by running subsets alongside
`test_patterns.py`) and within `test_patterns.py` (which of its
`ParallelPatternDetector`-backed tests is involved). Check for:
- A `mido.MidiFile`/`multiprocessing` mock or monkeypatch in
  `test_parser_fast.py` that isn't cleanly undone (`unittest.mock.patch`
  context exiting incorrectly, or module-level state mutation).
- Whether `ProcessPoolExecutor`'s `fork` start method interacts badly with
  whatever `test_parser_fast.py` leaves in the parent process (open file
  handles, threads, etc.) before workers are forked.

## Completeness Checks
- [ ] **TESTS**: once root-caused, a regression test (or CI config) prevents
      silent reintroduction — e.g. running the two files together in CI, or
      fixing the isolation bug so any file-pair ordering is safe
- [ ] **DOC**: if this turns out to be inherent/hard to fix, document the
      "always scope pytest invocations" practice explicitly (e.g. in
      CLAUDE.md) so it's a known convention, not an unwritten habit
