# Performance Audit — MIDI2NES

- **Date**: 2026-07-19
- **Scope**: Compile-path performance correctness — parser hot path, parallel
  pattern detector, large-file sampling, inter-stage memory, serialization cost,
  benchmark-harness validity, profiling utilities, cross-stage recompute.
- **Focus**: all dimensions (1–8)
- **Method**: Re-read every live code path named in the skill against the current
  tree; attempted to disprove each candidate finding before keeping it.

## Summary

The performance surface has been **substantially hardened since the skill text was
written**. Every major open item the skill anticipated is now fixed in the live code
and verified in this pass:

| Item (skill reference) | Status in live code |
|---|---|
| PERF-11 / #262 — benchmark `max_pattern_length=32` drift | **Fixed**: `benchmark_pattern_detection` now imports `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` from `constants` and passes both (`benchmarks/performance_suite.py:27,224-228`). |
| PERF-12 / #332 — coarse 10-task pattern-length chunking | **Fixed**: `_build_work_chunks` sub-chunks each length's start-range toward `max_workers*2` (`tracker/pattern_detector_parallel.py:116-146`). |
| PERF-13 / #333 — no "run serial below N events" guard | **Fixed**: `SERIAL_EVENT_THRESHOLD = 200` short-circuits pool construction (`:15,166-169`); single-chunk case also skips the pool (`:180-182`). |
| PERF-15 / #335 — analysis variant re-opens file, rebuilds tempo map | **Fixed**: both parse entry points share `_parse_frames_and_tempo_map` (`tracker/parser_fast.py:70-173,201`). |
| PERF-16 / #336 — `MemoryMonitor` reports `peak_mb=0` on sub-interval work | **Fixed**: seeded with an immediate RSS sample (`utils/profiling.py:87-91`). |
| #117 — benchmark measured wrong modules / double-counted profiler | **Fixed**: imports `parser_fast` + `ParallelPatternDetector`; `profile()` is a `@contextmanager` running `_end_profiling` once (`benchmarks/performance_suite.py:18-21,78-96`). |
| #118 — tracemalloc nesting blinds outer profiler | **Fixed**: reference-counted `_tracemalloc_acquire/release` (`utils/profiling.py:23-43`). |
| #119 — discarded per-pattern tempo analysis | **Fixed**: `analyze_tempo=False` at both detect sites (`main.py:686,923`). |
| Dim 3 — three unaligned magic thresholds, no config override | **Fixed**: `max_events`/`max_pattern_events`/`large_file_threshold` are in `config/default_config.yaml:14-16`, resolved via `get_pattern_detection_caps` (`main.py:43-73`), and aligned (`LARGE_FILE_THRESHOLD_DEFAULT = MAX_PATTERN_EVENTS = 15000`). |
| Dim 5 — `indent=2` on hot intermediates (frames especially) | **Fixed**: `run_parse`/`run_map`/`run_frames`/`run_detect_patterns` all write `separators=(',',':')` (`main.py:112,131,140,716`). |
| Dim 1 — O(log T) tempo lookups | **Verified intact**: bisect index `_build_tempo_index`, invalidated on every mutation (`tracker/tempo_map.py:6,111-171`). |

What remains are **6 low-impact residuals**, all in tooling/profiling and cross-stage
plumbing — none affect ROM correctness, none OOM or time out a common MIDI file, so
none rises above MEDIUM.

### Finding counts

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 1 |
| LOW | 5 |
| **Total** | **6** |

### Counts per dimension

| Dimension | Findings |
|---|---|
| 1 — Parser hot path | 0 |
| 2 — Parallel detector scaling | 0 |
| 3 — Large-file sampling | 0 |
| 4 — Inter-stage memory | 1 (PERF-A-01) |
| 5 — Serialization cost | 0 |
| 6 — Benchmark validity | 2 (PERF-A-02, PERF-A-03) |
| 7 — Profiling utilities | 2 (PERF-A-04, PERF-A-05) |
| 8 — Cross-stage recompute | 1 (PERF-A-06) |

### Highest-leverage fixes

1. **PERF-A-02** — add a checked-in baseline + regression gate to the benchmark
   harness; without it the suite that this whole audit protects cannot fail on a
   slowdown (the surviving half of the now-closed #262).
2. **PERF-A-04** — the benchmark `cpu_percent` figure is a delta of two
   interval-less `psutil` calls; it is printed as if meaningful but is advisory noise.
3. **PERF-A-01** — the parsed→mapped→frames pipeline holds three full in-memory
   copies of roughly the same data with no `del`/streaming; it is the memory
   high-water mark on a long song (bounded, correct, but the real optimization target).

---

## Findings

### PERF-A-01: Inter-stage frame/event data held as three full in-memory copies with no streaming
- **Severity**: LOW
- **Dimension**: 4 — Inter-stage memory
- **Location**: `main.py:100-140` (`run_parse`/`run_map`/`run_frames`), `main.py:75-108` (`load_json_stage`)
- **Status**: NEW
- **Description**: Every pipeline stage reads its entire input JSON into memory
  (`load_json_stage` → `json.loads(Path(...).read_text())`) and writes its entire
  output at once. Across parse → map → frames the same musical data exists as three
  successive full structures (parsed events → per-channel mapped events → the
  `{channel: {frame_num: {...}}}` frames dict, the largest of the three). No stage
  `del`s the prior structure while building the next, and there is no streaming, so
  the frames stage's peak holds both its input and output simultaneously.
- **Evidence**: `main.py:137-140` — `mapped = load_json_stage(args.input, [], 'map')`
  then `frames = emulator.process_all_tracks(mapped)` then
  `Path(args.output).write_text(json.dumps(frames, ...))`; `mapped` is never released
  before `frames` is fully materialized. `run_full_pipeline` chains the same stages
  in-process in a temp dir.
- **Impact**: Constant-factor (≈3×) memory overhead on the single largest structure,
  bounded by event count. Output is correct; no OOM on a common MIDI file. Blast
  radius: memory footprint only, all channels/stages.
- **Related**: Dimension 4 in the skill; cross-references PERF-A-06 (the events↔frames
  round-trip that creates a further transient copy).
- **Suggested Fix**: When the step-by-step CLI is not in use, have `run_full_pipeline`
  `del` each stage's input dict once its successor is built; longer term, consider a
  streaming/generator hand-off for the frames stage. Low priority — measure before
  investing.

### PERF-A-02: Benchmark harness has no checked-in baseline and no regression gate
- **Severity**: LOW
- **Dimension**: 6 — Benchmark validity
- **Location**: `benchmarks/run_benchmarks.py:59-168` (`run_baseline_benchmark`), `benchmarks/performance_suite.py:371-475` (`generate_report`)
- **Status**: NEW (surviving half of the now-closed #262/PERF-11 — the param-drift half was fixed; the gate half was never implemented)
- **Description**: The harness now measures the correct production modules with the
  correct pattern-length bounds (#262 fixed), but it still only *emits* a JSON report.
  There is no versioned baseline it compares against and no "fail if slower than
  baseline by X%" assertion. `benchmark_results/…json` is a run output, not a
  regression fixture. A benchmark with no comparison cannot catch the regressions this
  audit exists to prevent — it will greenlight a 2× slowdown silently.
- **Evidence**: `generate_report` (`performance_suite.py:371`) writes averages/p95 but
  compares against nothing; `run_baseline_benchmark` prints advisory thresholds
  (`run_benchmarks.py:149-162`, e.g. `if pattern_avg > 1000: print("… slow")`) that are
  absolute heuristics, not baseline deltas, and are print-only (no non-zero exit).
- **Impact**: Performance regressions in the parser or detector pass CI/local runs
  unnoticed. Blast radius: the entire performance-correctness safety net.
- **Related**: #262 (closed); Dimension 6.
- **Suggested Fix**: Check in a small deterministic baseline (see PERF-A-03) and a
  comparison step that exits non-zero when a stage's median exceeds baseline by a
  configurable margin.

### PERF-A-03: Baseline benchmark input set is machine-dependent
- **Severity**: LOW
- **Dimension**: 6 — Benchmark validity
- **Location**: `benchmarks/run_benchmarks.py:70-98`
- **Status**: NEW
- **Description**: `run_baseline_benchmark` globs `test_data/`, `examples/`, `samples/`
  and `.` for `*.mid` and benchmarks whatever it finds (first 5). Traversal order is now
  sorted (deterministic per machine, #117), but the *set* of files still depends on
  what happens to be present, so results are not comparable across machines or over
  time — undermining any future baseline gate (PERF-A-02).
- **Evidence**: `test_dirs = ["test_data", "examples", "samples", "."]` then
  `test_files.extend(find_test_files(test_dir, "*.mid"))`, truncated to
  `test_files[:5]` (`:70-98`). Falls back to a not-implemented synthetic generator
  (`create_synthetic_midi` returns `False`, `:38-56`).
- **Impact**: Cross-run/cross-machine numbers are incomparable; the harness cannot
  anchor a stable baseline. Tooling only.
- **Related**: PERF-A-02; Dimension 6.
- **Suggested Fix**: Commit one or two small fixture `.mid` files under a dedicated
  `benchmarks/fixtures/` dir and benchmark exactly those by default, independent of the
  working tree.

### PERF-A-04: `cpu_percent` reported as a delta of two interval-less psutil calls
- **Severity**: MEDIUM
- **Dimension**: 7 — Profiling utilities
- **Location**: `benchmarks/performance_suite.py:107,115` (`_start_profiling`/`_end_profiling`), `utils/profiling.py:217,241,270`
- **Status**: NEW
- **Description**: CPU usage is captured as `process.cpu_percent()` at start and end
  with **no `interval=`**. Per psutil semantics the first non-blocking call returns
  `0.0` and each later call measures CPU since the *previous* call, so the reported
  `cpu_percent` (and, in `profile_memory_usage`, `cpu_after - cpu_before`) is advisory
  noise, not a per-stage figure. It is printed in the benchmark report and per-stage
  `[PROFILE]` lines as though meaningful. This is a misleading-stat gap (cf. the
  "reported stat inaccurate (cosmetic but misleading)" MEDIUM row in the severity
  rubric), not a crash.
- **Evidence**: `performance_suite.py:107` `self._start_cpu = self.process.cpu_percent()`
  (unused thereafter) and `:115` `cpu_percent = self.process.cpu_percent()` fed into
  `BenchmarkResult.cpu_percent`; `utils/profiling.py:270`
  `cpu_percent=cpu_after - cpu_before`. The code comment at `utils/profiling.py:213-216`
  acknowledges the reading is advisory-only (an `interval=` would add blocking latency)
  — the value is retained and displayed anyway.
- **Impact**: A `cpu_percent` column that looks authoritative but is unreliable can
  misdirect optimization effort. Benchmark output only; no production effect.
- **Related**: Dimension 7; #118 (the tracemalloc half was fixed there).
- **Suggested Fix**: Either drop the `cpu_percent` field from reported results, or
  compute it as `cpu_times()` deltas divided by wall time (no blocking), and label it
  accordingly.

### PERF-A-05: `MemoryMonitor` sampling loop terminates permanently on the first transient error
- **Severity**: LOW
- **Dimension**: 7 — Profiling utilities
- **Location**: `utils/profiling.py:121-137` (`_monitor_loop`)
- **Status**: NEW
- **Description**: The daemon sampling loop catches `Exception`, increments
  `_sampling_errors`, and **`break`s** — one sampling hiccup ends all further sampling
  for the run, so `peak_mb`/`average_mb` are computed from a truncated sample set. The
  error is now counted and surfaced via `sampling_errors` (#336), which is the
  mitigation; but a single transient read failure (not process death) still blinds the
  rest of the monitored window rather than skipping one sample and continuing.
- **Evidence**: `utils/profiling.py:129-137` — `except Exception: self._sampling_errors
  += 1; break`. The comment documents this as intentional ("self.process may no longer
  be readable"), which holds for process death but not for a transient read.
- **Impact**: Under-reported peak memory if a sample fails mid-run. Profiling output
  only. Caller can now detect it via `sampling_errors > 0`.
- **Related**: #336 (seed-sample fix); Dimension 7.
- **Suggested Fix**: `continue` past a transient sampling error (keeping the counter),
  and only `break` after a small consecutive-failure threshold or on a specific
  process-gone exception (`psutil.NoSuchProcess`).

### PERF-A-06: Fresh tempo map rebuilt at each detect site + events↔frames round-trip; parse-time tempo never threaded forward
- **Severity**: LOW
- **Dimension**: 8 — Cross-stage recompute
- **Location**: `main.py:683-690` (`run_detect_patterns`), `main.py:895-899` (`run_full_pipeline`), `tracker/parser_fast.py:186-189` (parse returns `"metadata": {}`)
- **Status**: NEW
- **Description**: Two residual redundancies remain after #119 removed the expensive
  per-pattern tempo analysis: (a) each detect site constructs a fresh
  `EnhancedTempoMap(initial_tempo=500000)` defaulting to `ticks_per_beat=480` rather
  than the source file's resolution, because the parse stage discards its tempo map
  (`parse_midi_to_frames` returns empty `metadata`), so tempo is recomputed/redefaulted
  rather than reused; and (b) events are re-extracted from the frames dict
  (`frames_to_events`) that was itself derived from events at the frames stage — an
  events → frames → events round-trip. Both are cheap now (the tempo object is only
  allocated, not analyzed, and the detectors read only `note`/`volume`), so this is a
  correctness-neutral efficiency residual, not the costly path #119 addressed.
- **Evidence**: `main.py:683` `tempo_map = EnhancedTempoMap(initial_tempo=500000)`
  (default `ticks_per_beat=480`) and `:690` `events = frames_to_events(frames)`;
  mirrored at `:895`/`:899`. `parse_midi_to_frames` (`parser_fast.py:186-189`) returns
  `"metadata": {}`, so nothing tempo-related survives the parse JSON.
- **Impact**: A redundant object allocation and a full events-list rebuild per run;
  no output difference (detectors ignore tempo). Negligible cost on common files.
- **Related**: #119 (closed — costly half fixed), #261 (shared `frames_to_events`
  extractor); Dimension 8.
- **Suggested Fix**: Low priority. If ever addressed, serialize the tempo summary into
  the parse JSON and pass it forward, and/or have the frames stage retain the event
  list it derived frames from so the detector need not re-extract it.

---

## Notes / non-findings (verified, deliberately not reported)

- **Parallel detector correctness & scaling (Dim 2)**: `_collect_window_groups` is
  O(n) hash-bucketing per length; `_build_work_chunks` sub-chunks start-ranges toward
  `max_workers*2`; sequence/events ship once per worker via the pool `initializer`;
  serial and parallel paths share `_collect_window_groups`/`_select_candidates_from_groups`
  and produce equivalent results; failed sub-chunks are recovered in-process and, if
  still failing, counted and surfaced after the bar. Nothing to report.
- **Deterministic pattern selection**: `_select_best_patterns` tie-breaks on
  `(-score, start, length)` so selection is independent of worker completion order
  (#46). Verified.
- **Sampling caps (Dim 3)**: all three thresholds are config-overridable and aligned;
  the sequential and parallel paths sample via the same
  `sample_events_for_detection`. Content-loss framing is deferred to `audit-patterns`
  per the skill.
- **Serialization (Dim 5)**: hot intermediates use compact separators; only human-read
  reports keep `indent=2` (`main.py:1546`, `performance_suite.py:460`), which is
  appropriate.
- **Parser (Dim 1)**: two-pass structure, no per-event rescan, O(log T) bisect tempo
  lookups with index invalidation on mutation. The broad note-loop `except` counts and
  warns (cross-ref `audit-safety` for the catch breadth). Verified.
