# PERF-12
**Filed as:** #332

**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-18.md

## Description
The #114 fix reshaped `work_chunks` to one dict per pattern length (`tracker/pattern_detector_parallel.py:120-124`: `for length in range(min_pattern_length, min(max_pattern_length, len(sequence)) + 1)`). With the pipeline defaults (`PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12`) that is at most **10 tasks** (lengths 3..12), independent of input size. `pool_workers = min(self.max_workers, len(work_chunks))` (`:143`) is then capped at `len(work_chunks)`, so on a box with more than 10 usable cores several cores get zero work. Parallelism is now ceilinged by the pattern-length range, not by core count or event count — making the "multi-core pattern detection … detects CPU cores and distributes work" description in `CLAUDE.md` inaccurate for the default configuration.

## Evidence
`work_chunks = [{'pattern_length': length} for length in range(...)]` yields `12 - 3 + 1 = 10` entries; `pool_workers = min(self.max_workers, 10)` (`:143`).

## Impact
No correctness impact and no OOM/timeout (the O(n) core is fast), so not HIGH. Wasted parallelism on many-core hosts; the multi-core claim overstates real scaling. Since each task is one length, work is also unbalanced (longer lengths cost more), so the 10 tasks are not equal-sized.

## Related
#114 (introduced this shape), PERF-04/#115 (memory bounded by same chunk count).

## Suggested Fix
Sub-chunk long sequences by `start`-range within each length (or bucket lengths across workers) so task count scales toward core count; alternatively, document the ceiling and update the CLAUDE.md scaling claim.

## Completeness Checks
- [ ] **FALLBACK**: the `_detect_patterns_serial` path still produces identical results after any chunk-shape change
- [ ] **TESTS**: a test asserts task count scales past the pattern-length range on a large input (or the doc claim is corrected)
- [ ] **DOC**: CLAUDE.md "distributes work across all CPU cores" claim reconciled with actual scaling