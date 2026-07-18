# PERF-13
**Filed as:** #333

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-18.md

## Description
The only fast-path guard fires when `len(work_chunks) == 1` (`tracker/pattern_detector_parallel.py:134-136`, i.e. the sequence is so short only one pattern length fits, #218). A small-but-not-tiny input — e.g. ~40 events, which still yields up to 10 chunks — spawns a `ProcessPoolExecutor` and pickles the full `sequence`/`valid_events` into every worker via `initargs` (`:149-154`), even though a serial run would finish before the processes spawn. There is no "below N events, run `_detect_patterns_serial` inline" threshold.

## Evidence
`if len(work_chunks) == 1: … return self._detect_patterns_serial(...)` is the sole bypass; any 2+ chunk case constructs the pool unconditionally.

## Impact
Extra process-spawn + pickle-of-initargs latency on small inputs (pronounced under the `spawn` start method on macOS/Windows). No correctness impact.

## Related
#218 (single-chunk guard), PERF-12.

## Suggested Fix
Add a `len(sequence) < N` (or `len(valid_events) < N`) guard before pool construction that calls `_detect_patterns_serial` inline.

## Completeness Checks
- [ ] **FALLBACK**: the serial path invoked by the new guard returns identical results to the pool path
- [ ] **TESTS**: a test asserts a small (~40-event) input does not construct a process pool