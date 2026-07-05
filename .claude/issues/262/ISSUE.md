**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-05.md

## Description
The #117 fix correctly switched the benchmark to the production `ParallelPatternDetector`, but did not pass the production **parameters**. `benchmark_pattern_detection` (`benchmarks/performance_suite.py:218`) omits `max_pattern_length`, so it defaults to `32` (`tracker/pattern_detector_parallel.py:17`), whereas the full pipeline and the `detect-patterns` subcommand both construct the detector with `max_pattern_length=PATTERN_MAX_LENGTH` (`=12`, `main.py:743`, and the sequential path at `:510-511`/`:751`).

Work-chunk count is `max_pattern_length - min_pattern_length + 1`, so the benchmark exercises up to **30** pattern lengths where production exercises **10** — inflating measured pattern-detection time relative to the real path and measuring a work profile production never runs.

Separately, `benchmarks/run_benchmarks.py` still has no checked-in baseline or "fail if slower than X%" gate, so even a correct measurement cannot catch a regression automatically.

## Evidence
- `benchmarks/performance_suite.py:218`: `ParallelPatternDetector(tempo_map, min_pattern_length=3)` — passes only `min_pattern_length`.
- `tracker/pattern_detector_parallel.py:17`: signature default `max_pattern_length=32`.
- `main.py:35-36`: `PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12`.
- `main.py:743`: production passes `max_pattern_length=PATTERN_MAX_LENGTH`.
- No `baseline`/`compare` logic exists in `benchmarks/run_benchmarks.py` (only `run_baseline_benchmark`, which *establishes* numbers, never compares).

## Impact
The reported pattern-detection `duration_ms` is not comparable to what the production pipeline actually spends, and without a baseline comparison there is no automated regression signal. Cosmetic/measurement-fidelity, dev-tooling only → LOW.

## Suggested Fix
Pass `max_pattern_length=PATTERN_MAX_LENGTH` (import the constant, or mirror 12) in `benchmark_pattern_detection`. Longer term, check a versioned baseline into `benchmark_results/` and add a comparison step that fails on a configurable regression threshold.

## Related
Same method as PERF-10; both are residuals of the #117 fix.

## Completeness Checks
- [ ] **CONTRACT**: The benchmark constructs the detector with the same `min`/`max` pattern-length parameters production uses (`PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`)
- [ ] **SIBLING**: Parameter parity checked against both production call sites (`main.py:743` parallel, `main.py:751` sequential)
- [ ] **TESTS**: Missing/weak coverage — a baseline comparison gate would pin regressions
- [ ] **DOC**: No `docs/*.md` contradicted by the fix
