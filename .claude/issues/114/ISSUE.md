# PERF-02: Pattern matcher is O(n²·L) with full-sequence per-chunk IPC

**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
Two coupled inefficiencies in the parallel pattern matcher:

1. **Quadratic core.** For each `start` in a chunk the worker rebuilds `tuple(sequence[start:start+pattern_length])` and then **rescans the entire sequence from `pos=0`** (`tracker/pattern_detector_parallel.py:282-288`) to find matches — O(n) per start, repeated for every start and every pattern length → **O(n²·L)** total work. Splitting the `start` range across workers (`:99`) only divides wall-time by core count; **total work is unchanged**. The `sample_events_for_detection` cap exists precisely to bound this.
2. **Per-chunk IPC duplication.** Every `work_chunk` dict embeds the **full `sequence` and full `valid_events`** (`:102-103`). The number of chunks is ≈ `lengths × max_workers`. So the entire n-element sequence is pickled and shipped ≈ `(max_pattern_length-min_pattern_length) × max_workers` times — on a 15000-event cap with `max_pattern_length=12` and 16 cores that is ~160 copies of a 15000-tuple list pickled across the process boundary. Serialization + memory can rival the compute.

## Location
`tracker/pattern_detector_parallel.py:256-311` (`_detect_patterns_worker`), `:89-109` (`_detect_patterns_parallel` chunk construction)

## Evidence
Worker inner `while pos <= len(sequence) - pattern_len` (`:282`) is independent of `start_offset`/`end_offset`; chunk dict carries `'sequence': sequence, 'events': valid_events` verbatim (`:102-103`).

## Impact
Default pipeline + `detect-patterns` subcommand. Wall-time scales with cores but the algorithm stays quadratic; IPC bloat raises peak memory. Bounded by the 15000 cap so it does not OOM a common file → MEDIUM.

## Related
PERF-03 / #102 (sampling cap band-aid over the asymptotics), PERF-04 (memory), #46/REG-06 (multi-core path untested — a coverage gap, distinct from this algorithmic finding).

## Suggested Fix
Replace the rescan with a single suffix-hash / rolling-hash pass that records all equal windows in O(n) per length (O(n·L) total). Ship `sequence`/`valid_events` **once** via a `ProcessPoolExecutor` initializer (module global) instead of per chunk.

## Completeness Checks
- [ ] **ROUNDTRIP**: Hash-based matching yields the same patterns/references as the current rescan (decompressed playback unchanged)
- [ ] **FALLBACK**: The `EnhancedPatternDetector` fallback still fires if the parallel path errors
- [ ] **TESTS**: A regression test pins pattern equivalence before/after the algorithm change

