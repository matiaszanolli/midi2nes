# P-06: No-patterns stub stats keys drift from the detectors keys (dead keys, latent KeyError trap)

**Severity:** LOW · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-06-29.md

## Description
The `--no-patterns` stub emits `stats` with keys `compression_ratio, original_events, compressed_size, patterns_found`; the detectors emit `compression_ratio, original_size, compressed_size, unique_patterns`. The `original_events`/`patterns_found` keys exist nowhere else and `original_size`/`unique_patterns` are absent from the stub. A grep of every reader (`main.py`, `debug/`, `nes/`) shows only `compression_ratio` is ever read, so the drift is currently harmless — but the divergent shapes are a trap for any future consumer that assumes one schema.

## Location
stub `main.py:504-507`; detectors `tracker/pattern_detector.py:774-777`, `tracker/pattern_detector_parallel.py:34,251`.

## Evidence
Verified: stub keys `original_events` (`main.py:505`), `patterns_found` (`:507`); detector keys `original_size`/`unique_patterns` (`pattern_detector.py:774,777`; `pattern_detector_parallel.py:34`). Reader grep returns only `pattern_result["stats"]["compression_ratio"]` (`main.py:314,626`).

## Impact
None today (dead keys). LOW maintainability/consistency risk.

## Related
F-07/#17, P-07.

## Suggested Fix
Make the stub emit the same four keys as the detectors (`original_size`, `unique_patterns`), dropping the bespoke `original_events`/`patterns_found`.

## Completeness Checks
- [ ] **CONTRACT**: stub `stats` shape matches the detectors `stats` shape
- [ ] **SIBLING**: both detectors emit the same `stats` keys
- [ ] **TESTS**: a test asserts the stub/detector `stats` schemas agree
