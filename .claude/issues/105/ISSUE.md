# P-08: ThreadedPatternDetector is dead code with an unlocked len(patterns) ID race and unconditional empty variations

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-06-29.md

## Description
`ThreadedPatternDetector` builds pattern IDs from `len(patterns)` read *before* acquiring `pattern_lock`, so concurrent threads can derive colliding base IDs (mitigated only by the appended `_{start}`/per-length differences, not guaranteed unique). It also returns `"variations": {}` unconditionally where the other producers return a per-pattern dict. A grep shows **no non-test caller** of `ThreadedPatternDetector` anywhere in the live tree — it is dead.

## Location
`tracker/pattern_detector_parallel.py:314-441` — class def at `:314`; `:396` `f"pattern_{len(patterns)}_{start}"` read outside `pattern_lock` (lock acquired at `:406`); `:361` `"variations": {}`.

## Evidence
Verified: `grep -rn ThreadedPatternDetector` returns only the class definition at `pattern_detector_parallel.py:314` — zero callers (not even a test references it). The `len(patterns)` read at `:396` precedes the `with pattern_lock:` block at `:406`.

## Impact
None today (dead). LOW.

## Related
P-05, #46.

## Suggested Fix
Delete `ThreadedPatternDetector` or, if retained, move the `len(patterns)` read inside the lock and return a real `variations` shape.

## Completeness Checks
- [ ] **FALLBACK**: removing it does not affect the parallel→serial fallback path
- [ ] **TESTS**: if retained, a concurrency test pins unique IDs; if deleted, no test imports it
