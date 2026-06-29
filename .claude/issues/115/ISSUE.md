# PERF-04: Pattern-detection stage holds many full copies of the event sequence simultaneously

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
At the pattern-detection high-water mark the process holds, concurrently: the `frames` dict (largest structure), the `events` list rebuilt from it (`main.py:456-464`), `valid_events` (filtered copy), the sampled `valid_events` (another copy), `sequence` (tuple-of-pairs copy), every `work_chunk` each re-embedding the full `sequence`/`valid_events` (PERF-02), and `all_candidate_patterns` (each candidate copies a `pattern` tuple + a `positions` list + an `events` slice). None of the prior structures is `del`'d before the detector runs. The multiplier vs. raw event count is roughly `frames + 3×events + (lengths×workers)×events`.

## Location
`main.py:456-464` (events rebuilt from frames), `tracker/pattern_detector_parallel.py:42,49,56,93-109,113` (`valid_events`, sampled copy, `sequence`, every `work_chunk`, `all_candidate_patterns`)

## Evidence
No `del frames` / `del events` between stages; `work_chunks` build at `:101-108` each re-embed the full sequence.

## Impact
Raises peak RSS on large files; bounded by the 15000-event sample so it does not OOM a common file → LOW. Cross-references PERF-02's per-chunk duplication as the dominant term.

## Related
PERF-02 (per-chunk duplication is the dominant term).

## Suggested Fix
`del frames`/`del events` once consumed; ship the sequence to workers once (PERF-02 fix) so `work_chunks` carry only offsets.

## Completeness Checks
- [ ] **SIBLING**: The same hold-everything pattern checked at the `run_detect_patterns` subcommand path
- [ ] **TESTS**: A peak-RSS guard / smoke test on a large fixture, if feasible
