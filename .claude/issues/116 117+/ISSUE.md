# #116: PERF-05: All intermediate pipeline JSON is written with indent=2

**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
`run_parse`, `run_map`, `run_frames`, and the `detect-patterns` writer all serialize with `json.dumps(..., indent=2)`. The frames artifact — `{channel: {frame_num: {note, volume, ...}}}` with tens of thousands of inner dicts — is pretty-printed with a newline and leading spaces per element. Versus compact `separators=(',',':')`, `indent=2` typically inflates output size 2–3x and proportionally increases write time and the downstream `read_text()`/`json.loads` parse time of the next stage. These are machine-only intermediates a human rarely opens. (The benchmark/report writers at `main.py:959`, `benchmarks/performance_suite.py:438` are human-facing reports — `indent=2` is fine there.)

## Location
`main.py:43` (parse), `:52` (map), `:59` (frames), `:312` (detect-patterns output)

## Suggested Fix
Use `json.dumps(data, separators=(',',':'))` for the parse/map/frames/detect-patterns intermediates; keep `indent=2` only on the human-read report writers.

## Completeness Checks
- [ ] **CONTRACT**: Compact output is still valid JSON the next stage parses unchanged
- [ ] **SIBLING**: All four intermediate writers switched; human-facing report writers left at `indent=2`
- [ ] **TESTS**: Round-trip test that compact intermediates load identically

---

# #117: PERF-06: Benchmark harness measures the wrong modules and has no regression gate

**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
1. `from tracker.parser import parse_midi_to_frames` (`benchmarks/performance_suite.py:18`) — the slow full parser, while production `run_parse` uses `tracker/parser_fast.py`. The benchmark never measures the 120x fast path.
2. `benchmark_pattern_detection` constructs `EnhancedPatternDetector` (serial), while production uses `ParallelPatternDetector`. Benchmark measures the fallback, not the default.
3. Stale double-measure: `benchmark_parse_stage` runs work inside `with self.profiler.profile("parse")` (whose body already stops tracemalloc), then calls `self.profiler._end_profiling("parse", True)` a second time after the `with` block exits — hits the `except` branch, reports current RSS instead of traced peak.
4. No regression gate: `benchmark_results/benchmark_results.json` is a checked-in run output, not a versioned baseline diffed against.
5. Non-deterministic inputs: `run_baseline_benchmark` globs `test_data/`, `examples/`, `samples/`, `.` for `*.mid`.

## Suggested Fix
Import `parse_midi_to_frames` from `tracker.parser_fast` and use `ParallelPatternDetector` in `benchmark_pattern_detection`. Have `profile()` return its `BenchmarkResult` and delete the second `_end_profiling` call. Check in a committed baseline and add a percent-threshold comparison; benchmark a committed deterministic fixture set, not a glob.

## Completeness Checks
- [ ] **FALLBACK**: Switching the benchmark to `ParallelPatternDetector` still exercises the fallback path separately
- [ ] **SIBLING**: All `benchmark_*_stage` methods de-duplicated of the double `_end_profiling`
- [ ] **TESTS**: A deterministic fixture + baseline-comparison gate is added
- [ ] **DOC**: Benchmark docs updated to name the fast parser + parallel detector

---

# #118: PERF-07: Shared global tracemalloc — nested profilers blind each other

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
Every profiler calls the global `tracemalloc.start()` and stops it in a `try/except: pass`. If a `@profile_memory_usage`-decorated function runs inside a `PerformanceContext` (or two `PerformanceProfiler.profile` blocks nest), the inner `tracemalloc.stop()` tears down tracing for the still-running outer profiler, whose later `get_traced_memory()` then hits the bare `except` and reports current RSS instead of the traced peak.

Secondary issues:
- `cpu_percent()` sampled with no interval — first call after process start returns `0.0`.
- `MemoryMonitor._monitor_loop` swallows all exceptions with bare `except: break`; for work shorter than `interval_ms=100` no sample taken, `stop_monitoring` returns `{"peak_mb": 0}`.

## Suggested Fix
Guard `tracemalloc.start()` with `tracemalloc.is_tracing()` and only `stop()` if this profiler started it (reference-count or skip nested starts). Sample `cpu_percent()` with a small interval or document it as advisory.

## Completeness Checks
- [ ] **SIBLING**: All three `tracemalloc.start()`/`stop()` pairs guarded consistently
- [ ] **TESTS**: A nested-profiler test confirms the outer peak survives the inner stop

---

# #119: PERF-08: Tempo map rebuilt from scratch up to four times; events round-trip through frames

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-06-29.md

## Description
The tempo map computed at parse time is not serialized into the parse JSON (`parse_midi_to_frames` returns `"metadata": {}`), so every downstream consumer rebuilds it:
- `parse_midi_to_frames_with_analysis` re-opens the MIDI and rebuilds the tempo map after `parse_midi_to_frames` already built one — inline comment admits "this could be cached from first pass."
- The detect-patterns stage constructs a fresh `EnhancedTempoMap(initial_tempo=500000)` with the default `ticks_per_beat=480`, not the file's resolution — and never uses it for timing (detector only reads note/volume) — wasted construction.

Separately, events are derived into `frames` at the frames stage and then re-extracted from `frames` back into an `events` list for pattern detection (both in `run_full_pipeline` and `run_detect_patterns`) — an events→frames→events round-trip.

## Impact
Wasted CPU, not incorrect output (the detector ignores tempo). LOW. The `EnhancedTempoMap` getting the wrong `ticks_per_beat` is harmless only because it is unused — a latent trap if a future change starts reading it.

## Suggested Fix
Thread the computed tempo data through the parse JSON contract so downstream stages deserialize rather than recompute; drop the unused `EnhancedTempoMap` in detect-patterns or pass it real parameters.

## Completeness Checks
- [ ] **CONTRACT**: If tempo data is added to the parse JSON, the consumer stages read it in lockstep
- [ ] **SIBLING**: The events round-trip removed at both call sites
- [ ] **TESTS**: A test pins that threading tempo through the contract yields identical frames
