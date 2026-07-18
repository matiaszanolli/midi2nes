# PERF-14
**Filed as:** #334

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-18.md

## Description
`MAX_PATTERN_EVENTS` (15000, parallel) and `DETECTOR_MAX_EVENTS` (1000, sequential) are now overridable via `processing.pattern_detection.max_events`/`max_pattern_events` (#219, resolved by `get_pattern_detection_caps`). But `LARGE_FILE_THRESHOLD = 10000` is still a bare inline literal in `run_full_pipeline` (`main.py:861`), has no `default_config.yaml` key, and is purely advisory (prints a hint, changes no behavior — `main.py:862-864`). The three numbers are not aligned: a 5,000-event file trips neither the 10,000 advisory nor the 15,000 parallel cap, yet would be resampled 5,000→1,000 if the sequential fallback fires.

## Evidence
`LARGE_FILE_THRESHOLD = 10000` … `if len(events) > LARGE_FILE_THRESHOLD: print(...)` with no branch that alters detection.

## Impact
Cosmetic/maintainability — a magic number a user cannot tune and whose hint boundary does not correspond to either real sampling boundary. No output impact.

## Related
#219 (config caps), #100/#102 (shared sampler).

## Suggested Fix
Move `LARGE_FILE_THRESHOLD` into `default_config.yaml` alongside the other caps and align its default with the parallel cap, or delete the advisory branch.

## Completeness Checks
- [ ] **TESTS**: if made configurable, a test asserts the config key is honored
- [ ] **DOC**: the advisory boundary documented or removed