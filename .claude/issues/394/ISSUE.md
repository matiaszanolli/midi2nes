# REG-24: test_base_detector_uniformly_samples_not_head_cuts takes ~99s standalone — likely the real driver behind #355's hang

**Severity:** MEDIUM · **Domain:** regression · **Source:** docs/audits/AUDIT_REGRESSION_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/394

## Description
This test feeds `PatternDetector` 3000 maximally-repetitive events, hitting close to the
detector's self-documented "O(n^2)-ish" worst case. Directly instrumented: 99.14 seconds
wall-clock. Not marked `@pytest.mark.slow` unlike comparable ROM-compile tests. Very
likely explains or compounds the open #355/REG-22 "hang" report, whose repro used
30-40s timeouts — well under this test's measured runtime.

## Location
`tests/test_patterns.py:769-787`; underlying cost in `tracker/pattern_detector.py:244-277`
(self-documented "O(n^2)-ish" at line 215)

## Impact
Any scoped run of `tests/test_patterns.py` now takes 100+ extra seconds for this one test.

## Suggested Fix
Shrink the test's input to the minimum needed to prove the uniform-sampling property, or
mark it `@pytest.mark.slow` so fast scoped runs skip it. Recommend re-investigating #355
with this timing data.
