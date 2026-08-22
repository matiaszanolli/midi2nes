# TD-39: Closed #352's DETECTOR_MAX_EVENTS recalibration never reached master — the measured ~26s sequential-detector stall is still live

- **Issue**: #459

**Severity:** MEDIUM · **Domain:** tech-debt · **Source:** AUDIT_TECH_DEBT_2026-08-21.md

**Status:** Regression of #352 (CLOSED "Fixed in e645cc9 (branch fix/issue-352)"; the branch was never merged and `git log -L` on the line shows master's `1000` is unchanged since the #100/#99 fix)

## Description
#352's closing analysis measured the sequential `PatternDetector.detect_patterns` path (inherited unchanged by `EnhancedPatternDetector`, used by the `detect-patterns` subcommand and the pipeline's sequential fallback) at ~26s for n=1000 — the current cap — and recalibrated the cap to 300 (~2.5s worst case) because the constant's own stated purpose is to bound worst-case latency. That recalibration lives only on the unmerged branch `fix/issue-352`; master still caps at 1000, so the user-facing stall the issue was closed for remains reproducible.

Re-verified 2026-08-21: `tracker/pattern_detector.py:23` reads `DETECTOR_MAX_EVENTS = 1000` on master; `git show fix/issue-352:tracker/pattern_detector.py` reads `= 300` with a detailed comment documenting the 26s→2.86s live measurement.

## Evidence
```python
# tracker/pattern_detector.py (master, current)
DETECTOR_MAX_EVENTS = 1000

# fix/issue-352 branch
# The cap exists specifically to bound worst-case latency ("Safeguard" below) --
# it was previously 1000, a value nobody had actually timed. Measured against
# production parameters ... that took ~26s; 500 events ~6s; 300 events ~2.5s.
DETECTOR_MAX_EVENTS = 300
```
Issue #352's final comment documents the 26s→2.86s live measurement and the "hangs at n≈1000" root cause.

## Impact
`python main.py detect-patterns …` (a documented step-by-step debugging command) and the parallel detector's fallback path can stall ~26s on inputs at the cap. Workaround exists (default pipeline uses `ParallelPatternDetector`, `MAX_PATTERN_EVENTS=15000` sampling path, unaffected) → MEDIUM, not HIGH.

## Suggested Fix
Merge/re-land `e645cc9` (a one-line constant change plus its test).

## Related
TD-38 (same stranded-branch pattern); PIPE-2026-08-21-2; #352/REG-21; #355/REG-22 and #394/REG-24 (the test-suite handling of the same slowness — marking tests `slow` did not fix the production cap).

## Completeness Checks
- [ ] **FALLBACK**: The `EnhancedPatternDetector` fallback path (inherited unchanged) is re-checked after the constant change
- [ ] **TESTS**: A regression test pins `DETECTOR_MAX_EVENTS` at the recalibrated value and timing bound
