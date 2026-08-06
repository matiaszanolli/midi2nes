# Performance Audit — MIDI2NES

- **Date**: 2026-08-05
- **Scope**: Compile-path performance correctness — parser hot path, parallel
  pattern detector, large-file sampling, inter-stage memory, serialization cost,
  benchmark-harness validity, profiling utilities, cross-stage recompute.
- **Focus**: all dimensions (1–8)
- **Method**: Re-read every live code path named in the skill against the current
  tree; checked `git log --since=2026-07-19` on every performance-relevant file
  against the prior audit's findings; deduped against
  `gh issue list --repo matiaszanolli/midi2nes` before writing anything up.

## Summary

**No performance-relevant code changed since the 2026-07-19 audit.**
`git log --since=2026-07-19` on `main.py`, `tracker/parser_fast.py`,
`tracker/pattern_detector_parallel.py`, `tracker/tempo_map.py`,
`benchmarks/performance_suite.py`, `benchmarks/run_benchmarks.py`,
`utils/profiling.py`, and `config/default_config.yaml` returns nothing. The only
touch in the affected file set was `tracker/pattern_detector.py` (#365, "require
>=3 exact occurrences before selecting a sequential pattern") — a correctness gate
inside the existing selection loop, not a change to its algorithmic shape (still
O(n) hash-bucketing per pattern length via `_collect_window_groups`); it does not
introduce or resolve a performance finding.

This audit therefore re-verifies rather than re-discovers: all 6 findings from
`docs/audits/AUDIT_PERFORMANCE_2026-07-19.md` were filed as GitHub issues
(#371–#376) and remain **OPEN** and **unregressed** — spot-checked directly against
the live code below. No new findings surfaced.

### Finding counts

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 1 |
| LOW | 5 |
| **Total** | **6** (all pre-existing, 0 new) |

### Counts per dimension

| Dimension | Findings |
|---|---|
| 1 — Parser hot path | 0 |
| 2 — Parallel detector scaling | 0 |
| 3 — Large-file sampling | 0 |
| 4 — Inter-stage memory | 1 (#371) |
| 5 — Serialization cost | 0 |
| 6 — Benchmark validity | 2 (#372, #373) |
| 7 — Profiling utilities | 2 (#374, #375) |
| 8 — Cross-stage recompute | 1 (#376) |

### Highest-leverage fixes (unchanged from prior audit — still the priority order)

1. **#372** — add a checked-in baseline + regression gate to the benchmark harness;
   without it, the suite this whole audit protects cannot fail on a slowdown.
2. **#374** — the benchmark `cpu_percent` figure is a delta of two interval-less
   `psutil` calls; it is printed as if meaningful but is advisory noise.
3. **#371** — the parsed→mapped→frames pipeline holds three full in-memory copies
   of roughly the same data with no `del`/streaming; it is the memory high-water
   mark on a long song (bounded, correct, but the real optimization target).

---

## Findings

All six findings below were originally reported in
`docs/audits/AUDIT_PERFORMANCE_2026-07-19.md` and filed as GitHub issues. Each was
re-verified against the current tree for this pass (evidence lines re-checked, not
assumed). None have been fixed or regressed; all are re-affirmed as-is.

### PERF-A-01: Inter-stage frame/event data held as three full in-memory copies with no streaming
- **Severity**: LOW
- **Dimension**: 4 — Inter-stage memory
- **Location**: `main.py:100-140` (`run_parse`/`run_map`/`run_frames`)
- **Status**: Existing: #371 (OPEN, unregressed)
- **Description**: Every pipeline stage reads its entire input JSON into memory and
  writes its entire output at once. Across parse → map → frames the same musical
  data exists as three successive full structures, the frames dict being the
  largest. No stage `del`s the prior structure while building the next.
- **Evidence**: `main.py:137-140` — `mapped = load_json_stage(...)` →
  `frames = emulator.process_all_tracks(mapped)` → `Path(args.output).write_text(...)`;
  `mapped` is never released before `frames` is fully materialized. Re-confirmed
  unchanged at these line numbers.
- **Impact**: Constant-factor (~3x) memory overhead on the single largest structure,
  bounded by event count. No OOM on a common MIDI file.
- **Related**: Dimension 4; cross-references #376 (events↔frames round-trip).
- **Suggested Fix**: Unchanged from prior report — `del` each stage's input once its
  successor is built in `run_full_pipeline`; consider streaming for the frames stage.

### PERF-A-02: Benchmark harness has no checked-in baseline and no regression gate
- **Severity**: LOW
- **Dimension**: 6 — Benchmark validity
- **Location**: `benchmarks/run_benchmarks.py:59-168` (`run_baseline_benchmark`), `benchmarks/performance_suite.py:371-475` (`generate_report`)
- **Status**: Existing: #372 (OPEN, unregressed)
- **Description**: The harness measures the correct production modules with the
  correct pattern-length bounds (`benchmark_pattern_detection` still imports
  `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH` from `constants` and passes both —
  re-confirmed at `performance_suite.py:27,226-227`), but it still only emits a JSON
  report with no versioned baseline to compare against and no fail-on-regression
  assertion.
- **Evidence**: `generate_report` writes averages/p95 but compares against nothing;
  `run_baseline_benchmark` prints absolute advisory thresholds
  (`run_benchmarks.py:149-162`), print-only, no non-zero exit on regression.
- **Impact**: Performance regressions in the parser or detector pass CI/local runs
  unnoticed.
- **Related**: Dimension 6; #373 (input-set determinism, same root gap).
- **Suggested Fix**: Unchanged — check in a small deterministic baseline (see #373)
  and a comparison step that exits non-zero when a stage's median exceeds baseline
  by a configurable margin.

### PERF-A-03: Baseline benchmark input set is machine-dependent
- **Severity**: LOW
- **Dimension**: 6 — Benchmark validity
- **Location**: `benchmarks/run_benchmarks.py:70-98`
- **Status**: Existing: #373 (OPEN, unregressed)
- **Description**: `run_baseline_benchmark` globs `test_data/`, `examples/`,
  `samples/`, `.` for `*.mid` and benchmarks the first 5 found (sorted, so
  deterministic per machine) — but the *set* still depends on what happens to be
  present on disk, so results are not comparable across machines or over time.
- **Evidence**: `test_dirs = ["test_data", "examples", "samples", "."]`, truncated
  to `test_files[:5]`; `create_synthetic_midi` fallback still returns `False`
  (not implemented). Re-confirmed unchanged.
- **Impact**: Cross-run/cross-machine numbers incomparable; blocks anchoring a
  stable baseline for #372.
- **Related**: #372; Dimension 6.
- **Suggested Fix**: Unchanged — commit fixture `.mid` files under
  `benchmarks/fixtures/` and benchmark exactly those by default.

### PERF-A-04: `cpu_percent` reported as a delta of two interval-less psutil calls
- **Severity**: MEDIUM
- **Dimension**: 7 — Profiling utilities
- **Location**: `benchmarks/performance_suite.py:217,241,270`, `utils/profiling.py:212-217`
- **Status**: Existing: #374 (OPEN, unregressed)
- **Description**: CPU usage is captured via `process.cpu_percent()` at start and
  end with no `interval=`. Per psutil semantics the first non-blocking call returns
  `0.0` and later calls measure since the previous call, so the reported
  `cpu_percent` is advisory noise, not a meaningful per-stage figure, yet it is
  printed as though authoritative.
- **Evidence**: `performance_suite.py:217` `cpu_before = process.cpu_percent()...`
  and `:270` `cpu_percent=cpu_after - cpu_before`; the comment at
  `utils/profiling.py:212-216` acknowledges this is advisory-only, and the value is
  retained/displayed anyway. Re-confirmed at current line numbers.
- **Impact**: A `cpu_percent` column that looks authoritative but is unreliable can
  misdirect optimization effort. Benchmark output only; no production effect.
- **Related**: Dimension 7.
- **Suggested Fix**: Unchanged — drop the field or compute via `cpu_times()` deltas
  over wall time, labeled accordingly.

### PERF-A-05: `MemoryMonitor` sampling loop terminates permanently on the first transient error
- **Severity**: LOW
- **Dimension**: 7 — Profiling utilities
- **Location**: `utils/profiling.py:121-137` (`_monitor_loop`)
- **Status**: Existing: #375 (OPEN, unregressed)
- **Description**: The daemon sampling loop catches `Exception`, increments
  `_sampling_errors`, and `break`s — one transient sampling hiccup ends all further
  sampling for the run.
- **Evidence**: `utils/profiling.py:129-136` — `except Exception:
  self._sampling_errors += 1; break`. Re-confirmed unchanged; `sampling_errors` is
  surfaced to callers (#336) but the loop still terminates rather than continuing.
- **Impact**: Under-reported peak memory if a sample fails mid-run. Profiling
  output only.
- **Related**: Dimension 7.
- **Suggested Fix**: Unchanged — `continue` past a transient error, `break` only
  after a consecutive-failure threshold or a specific process-gone exception.

### PERF-A-06: Fresh tempo map rebuilt at each detect site + events↔frames round-trip
- **Severity**: LOW
- **Dimension**: 8 — Cross-stage recompute
- **Location**: `main.py:683-690` (`run_detect_patterns`), `main.py:895-899` (`run_full_pipeline`), `tracker/parser_fast.py:186-189`
- **Status**: Existing: #376 (OPEN, unregressed)
- **Description**: Each pattern-detection call site constructs a fresh
  `EnhancedTempoMap(initial_tempo=500000, ticks_per_beat=480 default)` rather than
  reusing tempo data already computed at parse time (parse JSON's `metadata` stays
  `{}`), and events are re-extracted from the frames dict (`frames_to_events`) that
  was itself derived from events at the frames stage.
- **Evidence**: `main.py:683` `tempo_map = EnhancedTempoMap(initial_tempo=500000)`
  and `:690` `events = frames_to_events(frames)`, mirrored at `:895`/`:899`;
  `parse_midi_to_frames` still returns `"metadata": {}`. Re-confirmed unchanged.
- **Impact**: Redundant object allocation and a full events-list rebuild per run;
  detectors only read `note`/`volume`, so no output difference. Negligible cost on
  common files.
- **Related**: #119 (closed — costly per-pattern tempo *analysis* half was fixed);
  Dimension 8.
- **Suggested Fix**: Unchanged — low priority; serialize tempo summary into parse
  JSON and/or retain the frames stage's source event list.

---

## Notes / non-findings (re-verified against live code, no finding)

- **Dim 1 — Parser hot path**: `parse_midi_to_frames` still makes two linear passes
  over `mid.tracks` (tempo, then notes); tempo lookups are O(log T) via the
  lazily-built bisect index in `tracker/tempo_map.py`, invalidated on every
  `tempo_changes` mutation (#113, holds). Both parse entry points share
  `_parse_frames_and_tempo_map` (#335, holds) — the analysis variant no longer
  rebuilds the tempo map from scratch.
- **Dim 2 — Parallel detector scaling**: `_collect_window_groups` is O(n)
  hash-bucketing per pattern length; `_build_work_chunks` sub-chunks each length's
  start-range toward `max_workers * 2` (`tracker/pattern_detector_parallel.py:132`),
  so the old "only 10 tasks regardless of cores" ceiling (#332) is fixed —
  re-confirmed at the current line numbers. `SERIAL_EVENT_THRESHOLD = 200`
  (`:15,166`) short-circuits pool construction for small inputs (#333, holds).
  Sequence/events ship once per worker via the pool `initializer`. #365's change to
  `tracker/pattern_detector.py` (the *sequential* detector's selection loop) does
  not touch this file or its complexity.
- **Dim 3 — Large-file sampling**: all three thresholds
  (`max_events`/`max_pattern_events`/`large_file_threshold`) remain aligned and
  config-overridable via `get_pattern_detection_caps` (`main.py:45-73`) against
  `config/default_config.yaml:14-16`, which has not changed since the last audit.
- **Dim 5 — Serialization cost**: `run_parse`/`run_map`/`run_frames`/
  `run_detect_patterns` all still write `json.dumps(..., separators=(',', ':'))`
  (`main.py:112,131,140,673`) — re-confirmed at current line numbers. Only the
  human-read benchmark report and `run_benchmark`'s result dump keep `indent=2`,
  which is appropriate.
- **Dim 6 — Benchmark module correctness**: `benchmarks/performance_suite.py`
  still imports `tracker.parser_fast.parse_midi_to_frames` (the production fast
  path) and constructs `ParallelPatternDetector` with both `PATTERN_MIN_LENGTH` and
  `PATTERN_MAX_LENGTH` from `constants` (`:27,226-227`) — the #262 param-drift half
  stays fixed. `PerformanceProfiler.profile` is still a single-exit
  `@contextmanager` (no double `_end_profiling`).
- **Dim 7 — tracemalloc lifecycle**: `_tracemalloc_acquire`/`_tracemalloc_release`
  reference-counting (`utils/profiling.py:23-42`) is unchanged and still routes both
  `profile_memory_usage` and `PerformanceContext` through it — no nesting blind
  spot (#118, holds).
- **Dim 8**: no new redundant-recompute site found beyond #376; the expensive
  per-pattern tempo *analysis* half (#119) remains fixed (`analyze_tempo=False` at
  both `main.py:686` region call sites).

---

## Conclusion

Zero new performance findings this cycle. The performance surface is stable: no
commit since the 2026-07-19 audit touched any file in the performance-relevant set,
and every one of the 6 previously-filed issues (#371–#376) was independently
re-verified against current line numbers rather than assumed carried-forward. No
regressions detected.
