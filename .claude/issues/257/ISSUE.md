# PAT-08: coverage_ratio divides sampled-space patterned count by full-song total, understating coverage under sampling

GitHub: #257

**Severity:** MEDIUM · **Domain:** patterns · **Source:** AUDIT_PATTERNS_2026-07-05.md

## Description
`coverage_ratio = patterned_events / total_events * 100`, but the two operands are measured in **different event spaces**. `total_events` is captured as `len(events)` **before** the detector's internal uniform sampling (`tracker/pattern_detector.py:404`, captured before `super().detect_patterns()` at `:407`), while `patterned_events` (`== original_size`) is summed over the **sampled** sequence's positions (`:851`). For any song exceeding the cap (`DETECTOR_MAX_EVENTS = 1000` sequential, `MAX_PATTERN_EVENTS = 15000` parallel), the numerator can be at most the sampled size while the denominator is the full song, so reported coverage is scaled down by ~`(sampled / total)`.

Introduced by the #169/PAT-03 coverage fix in `84955f3`.

## Evidence
`tracker/pattern_detector.py:404` — `total_events = len(events)` captured pre-sampling (comment at `:400-404` confirms "captured before super().detect_patterns() does its own internal validation/sampling").
`tracker/pattern_detector.py:847-854` — `patterned_events = original_size`; `coverage_ratio = (patterned_events / total_events) * 100`.
Parallel twin: `tracker/pattern_detector_parallel.py:48,77-79`.
Trigger: `main.py:545` and `main.py:745` pass the full `events` list straight into `detector.detect_patterns` with no pre-sampling on the default parallel path.

Direct repro — a 60-event, period-4 (~fully patterned) sequence with the cap forced to 20:
```
Warning: Large sequence (60 events), uniformly sampling to 20 for performance
total_events= 60  patterned_events= 12  coverage_ratio= 20.0
```
The song is essentially 100% patterned, but the banner prints "Pattern coverage: 20.0% of 60 events". The `detect-patterns` subcommand and the sequential *fallback* pre-sample before calling `detect_patterns`, so `total_events` already equals the retained count there and the mismatch does not occur on those two paths.

## Impact
Metrics-only (no ROM byte changes — every emitted byte still derives from `frames`, #4). Direction is conservative (understates, never over-claims), so it is not the "96% on an unpatterned song" over-claim #169 fixed — but it is the same class of misleading number the `coverage_ratio` field was *added* to prevent, now wrong for large songs on the default path. A user could wrongly conclude a large, highly-repetitive song is barely compressible.

## Suggested Fix
Compute `coverage_ratio` against the size of the sequence actually analyzed (`len(sampled_sequence)`), not the pre-sampling `total_events`; or scale `patterned_events` by `total_events / sampled_len`; or, minimally, when sampling triggered, relabel the banner as "of N sampled events" and surface the same approximate-stats note the fallback path already prints (`main.py:760-766`).

## Related
#169/PAT-03 (the fix this regresses), #21/#100 (sampling policy), #176/PL-03 (approximate-stats warning already printed on the fallback path only).

## Completeness Checks
- [ ] **ROUNDTRIP**: Confirm this is metrics-only — no change to emitted ROM bytes / decompressed playback
- [ ] **FALLBACK**: Verify both parallel and sequential-fallback paths report coverage in the same event space
- [ ] **SIBLING**: Fix applied to the parallel twin (`pattern_detector_parallel.py:48,77-79`), not only the sequential detector
- [ ] **TESTS**: A regression test pins coverage_ratio ~= 100% for a fully-patterned song that exceeds the sampling cap
- [ ] **DOC**: If the banner wording changes, any doc describing the coverage line is updated
