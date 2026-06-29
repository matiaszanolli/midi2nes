# P-03: Three inconsistent event limits across detectors (1000 / 2000 / 15000), only one of which actually binds

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-06-29.md

## Description
There are three different limits. Current state: `sample_events_for_detection` = 15000 (shared, uniform); `PatternDetector` internal hard cut = 1000 (head); `ThreadedPatternDetector` stride = 2000; pipeline fallback `FALLBACK_MAX_EVENTS` = 2000. Because the 1000 head-cut (P-01) sits *below* the 15000 sample and runs on the same `EnhancedPatternDetector`, the effective binding limit for the sequential path is 1000, not the documented 15000 — the limits do not compose, they shadow each other.

## Location
`tracker/pattern_detector.py:13` (`MAX_PATTERN_EVENTS = 15000`) & `:143` (`MAX_EVENTS = 1000`); `tracker/pattern_detector_parallel.py:49` (`sample_events_for_detection` → 15000) & `:379-380` (`if len(sequence) > 2000: step = len(sequence) // 2000`); `main.py:485` (`FALLBACK_MAX_EVENTS = 2000`).

## Evidence
Verified: `MAX_PATTERN_EVENTS = 15000` (`pattern_detector.py:13`) vs `MAX_EVENTS = 1000` (`:143`); `ParallelPatternDetector` samples to 15000 (`:49`); `ThreadedPatternDetector` strides to 2000 (`:379-380`).

## Impact
Confusing, undocumented decimation behavior; the "15000 shared policy" comment is misleading because 1000 wins. Inconsistent results between the parallel default (15000) and the sequential fallback / subcommand (effectively 1000).

## Related
P-01, #21 (closed).

## Suggested Fix
Pick one policy (the shared `sample_events_for_detection`) and route all three detectors through it; delete the per-detector hard caps.

## Completeness Checks
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **SIBLING**: Same pattern checked in related files (all three detectors + pipeline fallback)
- [ ] **TESTS**: A regression test pins the single effective limit
- [ ] **DOC**: If behavior contradicted a `docs/*.md` or code comment, it was corrected
