# PERF-06: Benchmark harness measures the wrong modules and has no regression gate

**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
The benchmark harness does not exercise the production hot path:

1. `from tracker.parser import parse_midi_to_frames` (`benchmarks/performance_suite.py:18`) — the **slow full parser**, while the production `run_parse` uses `tracker/parser_fast.py` (`main.py:41`). The "parse" stage benchmark never measures the 120x fast path.
2. `benchmark_pattern_detection` constructs `EnhancedPatternDetector` (`:197-198`, serial `tracker/pattern_detector.py`), while the production detect-patterns path uses `ParallelPatternDetector` (`main.py:476`). The benchmark measures the *fallback*, not the default.
3. **Stale double-measure.** `benchmark_parse_stage` (and the other `benchmark_*_stage`) run the work inside `with self.profiler.profile("parse")` — whose body already calls `_end_profiling(...)` and **stops tracemalloc**. Then the method calls `self.profiler._end_profiling("parse", True)` a **second time** (`:160`) *after* the `with` block exits, re-reading RSS post-work and hitting the `except` branch because tracemalloc is already stopped. The returned `BenchmarkResult` reports a `memory_peak_mb` that fell back to current RSS rather than the traced peak.
4. **No regression gate.** `benchmark_results/benchmark_results.json` is a checked-in *run output*, not a versioned baseline the harness diffs against. There is no "fail if slower than baseline by X%" gate.
5. **Non-deterministic inputs.** `run_baseline_benchmark` globs `test_data/`, `examples/`, `samples/`, `.` for `*.mid` and silently benchmarks whatever it finds (`benchmarks/run_benchmarks.py:69-77`), making results incomparable across machines/runs.

## Location
`benchmarks/performance_suite.py:18` (imports `tracker.parser`), `:197-198` (`EnhancedPatternDetector`), `:152-160` (double `_end_profiling`); `benchmarks/run_benchmarks.py:69-77` (non-deterministic input search); `benchmark_results/benchmark_results.json` (checked-in run output, no comparison)

## Evidence
Import at `:18`; detector at `:197-198`; `with self.profiler.profile("parse"): result = parse_wrapper()` immediately followed by `return result, self.profiler._end_profiling("parse", True)` (`:157-160`).

## Impact
A regression in `parser_fast` or `ParallelPatternDetector` is invisible to the benchmark; reported memory peaks are unreliable. A benchmark that measures the wrong code is worse than none → MEDIUM (highest-leverage despite severity).

## Related
PERF-07 (shared tracemalloc-stop bug), #46/REG-06 (parallel detector untested).

## Suggested Fix
Import `parse_midi_to_frames` from `tracker.parser_fast` and use `ParallelPatternDetector` in `benchmark_pattern_detection`. Have `profile()` *return* its `BenchmarkResult` and delete the second `_end_profiling` call. Check in a committed baseline and add a percent-threshold comparison; benchmark a committed deterministic fixture set, not a glob.

## Completeness Checks
- [ ] **FALLBACK**: Switching the benchmark to `ParallelPatternDetector` still exercises the fallback path separately
- [ ] **SIBLING**: All `benchmark_*_stage` methods de-duplicated of the double `_end_profiling`
- [ ] **TESTS**: A deterministic fixture + baseline-comparison gate is added
- [ ] **DOC**: Benchmark docs updated to name the fast parser + parallel detector
