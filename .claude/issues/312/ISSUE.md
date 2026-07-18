# PAT-11: coverage_ratio can collapse to ~1% on a fully-periodic song once uniform sampling triggers

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-18.md
**Filed as:** #312

## Description
Uniform `np.linspace(0, n-1, cap)` sampling of a song whose musical period does not divide the sampling stride puts retained samples out of phase with the period, destroying the exact repeats the detector keys on. A genuinely ~100%-periodic song can report near-zero `coverage_ratio` after sampling triggers.

## Location
`tracker/pattern_detector.py:26-38` (`sample_events_for_detection`), consumed via `pattern_detector.py:204-207` and `pattern_detector_parallel.py:60`; coverage computed at `pattern_detector.py:879-881`.

## Suggested Fix
When sampling triggered, label the coverage line as measured "over the N sampled events (lossy)". No behavior change to detection/export warranted.

## Related
#257/PAT-08, PAT-10 (#311)
