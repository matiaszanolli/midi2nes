# REG-21: PatternDetector (bare, test-only dead code) hangs at n≈1000 events — O(n²×length-range) per-start rescan

**Severity:** MEDIUM · **Domain:** regression · **Source:** discovered while verifying fix-issue batch #332/#333/#338/#339 (2026-07-18)

## Description
`tracker/pattern_detector.py`'s bare `PatternDetector` class (distinct from the
actively-used `EnhancedPatternDetector`) implements an O(n² × pattern-length-range)
per-start rescan: for every `(length, start)` pair it calls `_detect_pattern_variations`
and `_find_pattern_matches`, each themselves an O(n) scan. At `n ≈ DETECTOR_MAX_EVENTS`
(1000, the class's own internal sampling cap) with the default `max_pattern_length=32`,
this becomes computationally infeasible — effectively an indefinite hang, not just slow.

Confirmed pre-existing on `master` via `git stash` (unrelated to any pattern-detector
work in #332/#333). `grep` confirms `PatternDetector` (bare) is imported **only** by
`tests/test_patterns.py` — no production code path constructs it (`main.py` and every
other module use `EnhancedPatternDetector` or `ParallelPatternDetector` instead). So this
cannot hang a real MIDI→ROM build; it only hangs anyone who runs the full
`test_patterns.py` file (or the whole suite) unscoped.

## Evidence
```
$ git stash   # revert to unmodified tracker/pattern_detector_parallel.py
$ timeout 30 python -m pytest -q \
    "tests/test_patterns.py::TestEventLimitConsolidation::test_sequential_detector_binds_at_detector_max_events" -v
# exit 124 (timeout) — hangs on ORIGINAL, unmodified code

$ grep -rn "from tracker.pattern_detector import.*\bPatternDetector\b" --include="*.py" . | grep -v EnhancedPatternDetector
tests/test_patterns.py:742
tests/test_patterns.py:1001
tests/test_patterns.py:1008
tests/test_patterns.py:1251
# only test_patterns.py — no production importer
```
At least two test methods hit the catastrophic-n zone (both sample down to
`DETECTOR_MAX_EVENTS=1000` internally before the O(n²×L) pass runs):
- `TestEventLimitConsolidation::test_sequential_detector_binds_at_detector_max_events` (feeds 2000 events)
- `TestLargeFilePolicy::test_base_detector_uniformly_samples_not_head_cuts` (feeds 3000 events)

## Impact
No ROM/production impact (dead code path). Developer-productivity impact: the full
`test_patterns.py` file (and by extension an unscoped `pytest` run) hangs indefinitely
rather than completing or failing fast, which silently discourages ever running the full
suite — a plausible root cause of established practice in this repo to always scope
`pytest` invocations to specific files rather than running the whole suite.

## Related
Same "test-only dead code" category as TD-26 (`tracker/parser.py`, #346) — the old full
parser kept alive only by tests, now documented as not on any pipeline path. This is a
more severe instance: dead code that actively hangs rather than just drifting silently.

## Suggested Fix
Pick one:
1. **Delete** `PatternDetector` (bare) and migrate its ~4 test call sites to
   `EnhancedPatternDetector` (which already has the O(n) hash-grouping optimization and
   is the real, tested, production sequential detector) — likely the cleanest option,
   mirroring the TD-26 recommendation for `tracker/parser.py`.
2. If `PatternDetector` is meant to stay as a reference/baseline implementation, cap its
   effective `n` far below the catastrophic zone (e.g. assert/warn above a few hundred
   events) so a future test author can't reintroduce this hang by accident, and add a
   fast bound-check test.
3. At minimum, mark the two affected tests `@pytest.mark.slow` (or similar) with a
   generous but finite timeout so a full suite run degrades to "slow" rather than
   "hangs forever."

## Completeness Checks
- [ ] **TESTS**: whichever fix is chosen, a test confirms `test_patterns.py` runs to
      completion (or fails/skips fast) in a full-suite, non-scoped `pytest` invocation
- [ ] **SIBLING**: confirm no other dead/legacy detector class in `tracker/` has the same
      complexity trap
- [ ] **DOC**: if deleted, no `docs/*.md` references `PatternDetector` (bare) as a live
      option
