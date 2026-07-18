# Performance Audit — MIDI2NES

- **Date**: 2026-07-18
- **Scope**: Compile-path performance correctness — parse speed, parallel pattern
  detection, large-file sampling, inter-stage memory, serialization cost, benchmark
  harness validity, profiling utilities, cross-stage recompute.
- **Method**: Re-read each live code path, confirmed against the shared audit
  protocol/severity rubrics, deduped against open/closed GitHub issues.

## Summary

### Finding counts by severity
| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 2 |
| LOW | 4 |
| **Total** | **6** |

### Finding counts by dimension
| Dimension | Count |
|-----------|-------|
| 1 — Parser hot-path | 0 (verified clean) |
| 2 — Parallel detector scaling | 2 |
| 3 — Large-file sampling thresholds | 1 |
| 4 — Inter-stage memory | 0 (mitigated, see notes) |
| 5 — Serialization cost | 0 (verified fixed) |
| 6 — Benchmark-harness validity | 1 |
| 7 — Profiling-utility correctness | 1 |
| 8 — Cross-stage redundant recompute | 1 |

### 3 highest-leverage fixes
1. **PERF-11 (Existing #262, MEDIUM)** — the pattern-detection benchmark inherits
   `max_pattern_length=32` (constructor default) instead of production's `12`, and
   there is no checked-in baseline + regression gate. The harness that is supposed to
   catch regressions measures a different (heavier) workload than production and has no
   pass/fail comparison — it cannot fail on a regression.
2. **PERF-12 (NEW, MEDIUM)** — after the #114 fix, work is chunked one-per-pattern-length,
   so with the pipeline defaults (min 3, max 12) there are only **10 tasks** regardless
   of input size or core count. On boxes with >10 usable cores the extra cores sit idle;
   the "distributes work across all CPU cores" claim no longer holds for the default
   config.
3. **The `indent=2` hot-intermediate concern is already resolved (#116)** — no action
   needed; see "Verified-fixed" below. The next-best real win after PERF-11/12 is
   PERF-14 (align/expose the advisory large-file threshold).

### Verified-fixed (re-confirmed against live code, no finding)
- **Dim 1** — `parse_midi_to_frames` makes two linear passes; tempo lookups are O(log T)
  via the lazily-built bisect index (`_build_tempo_index`, `_get_tempo_index`) with
  cumulative-ms precompute, invalidated on every `tempo_changes` mutation (#113 CLOSED,
  holds). Dropped-note path counts + warns, no silent swallow (#124/#125).
- **Dim 2 core** — `_collect_length_candidates` is a single O(n) hash-grouping pass per
  length; workers and the serial fallback share it; sequence/events shipped once per
  worker via `initializer=_init_pattern_worker` (#114 CLOSED, holds). Single-chunk
  guard skips the pool for trivial input (#218).
- **Dim 5** — all hot intermediates (`run_parse`, `run_map`, `run_frames`,
  `run_detect_patterns`) write `json.dumps(..., separators=(',',':'))`, not `indent=2`
  (#116 CLOSED, holds). Only the human-read benchmark report keeps `indent=2`.
- **Dim 6 partial** — benchmark imports `tracker.parser_fast.parse_midi_to_frames` and
  constructs `ParallelPatternDetector`, matching production modules; `profiler.profile`
  is a `@contextmanager` running `_end_profiling` exactly once (#117 CLOSED, holds).
- **Dim 7 partial** — tracemalloc start/stop is reference-counted via
  `_tracemalloc_acquire`/`_release` (#118 CLOSED, holds).
- **Dim 4** — the per-chunk full-sequence duplication behind PERF-04 (#115, OPEN) is
  eliminated by #114; peak is now ~`min(max_workers, chunk_count) × sequence size`.
  #115 as originally described is largely mitigated; the residual per-stage JSON copies
  are inherent to the file-based pipeline and bounded by event count. No new finding.

---

## Findings

### PERF-11: Benchmark measures `max_pattern_length=32` vs production `12`, and has no regression gate
- **Severity**: MEDIUM
- **Dimension**: 6 — Benchmark-harness validity
- **Location**: `benchmarks/performance_suite.py:217`; production param at
  `main.py:872` (`PATTERN_MAX_LENGTH=12`, defined `main.py:37`); baseline output at
  `benchmark_results/benchmark_results.json`; non-deterministic input search at
  `benchmarks/run_benchmarks.py:70`.
- **Status**: Existing: #262
- **Description**: `benchmark_pattern_detection` builds
  `ParallelPatternDetector(tempo_map, min_pattern_length=3)` with no
  `max_pattern_length`, inheriting the constructor default `32`
  (`pattern_detector_parallel.py:17`). Production passes
  `max_pattern_length=PATTERN_MAX_LENGTH` (12). The benchmark therefore times 3–32-length
  detection (more chunks, more work) against production's 3–12 — non-comparable timings.
  Separately, `benchmark_results.json` is a run output, not a versioned baseline the
  harness compares against; there is no "fail if slower than baseline by X%" gate, and
  `run_baseline_benchmark` runs on whatever `*.mid` it finds across `test_data/`,
  `examples/`, `samples/`, `.` (or a synthetic file), so inputs are non-deterministic
  across machines.
- **Evidence**: `detector = ParallelPatternDetector(tempo_map, min_pattern_length=3)`
  (`performance_suite.py:217`) vs
  `ParallelPatternDetector(..., max_pattern_length=PATTERN_MAX_LENGTH, ...)`
  (`main.py:872`).
- **Impact**: A benchmark that measures a heavier, non-production workload with no
  pass/fail comparison cannot catch a performance regression — the exact purpose of the
  harness. Greenlights regressions silently.
- **Related**: #262 (PERF-11), depends on the #114/#117 rewiring.
- **Suggested Fix**: Pass `max_pattern_length=PATTERN_MAX_LENGTH` in the benchmark; check
  in a named baseline and add a threshold comparison that exits non-zero on regression;
  pin a fixed benchmark corpus.

### PERF-12: Pattern-length chunking ceilings parallelism at ~10 tasks regardless of core count
- **Severity**: MEDIUM
- **Dimension**: 2 — Parallel detector scaling & work distribution
- **Location**: `tracker/pattern_detector_parallel.py:121-124` (work-chunk construction),
  `:143` (`pool_workers = min(self.max_workers, len(work_chunks))`); defaults at
  `main.py:36-37` (`PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12`).
- **Status**: NEW
- **Description**: The #114 fix reshaped `work_chunks` to one dict per pattern length
  (`range(min_pattern_length, min(max_pattern_length, len(sequence)) + 1)`). With the
  pipeline defaults that is at most **10 tasks** (lengths 3..12), independent of input
  size. `pool_workers` is then capped at `len(work_chunks)`, so on a box with more than
  10 usable cores several cores get zero work. Parallelism is now ceilinged by the
  pattern-length range, not by core count or event count. This is a genuine scaling
  regression relative to the "multi-core pattern detection … detects CPU cores and
  distributes work" description in `CLAUDE.md`, and makes the doc claim inaccurate for
  the default configuration.
- **Evidence**: `work_chunks = [{'pattern_length': length} for length in range(...)]`
  yields `12 - 3 + 1 = 10` entries; `pool_workers = min(self.max_workers, 10)`.
- **Impact**: No correctness impact and no OOM/timeout (the O(n) core is fast), so not
  HIGH. Wasted parallelism on many-core hosts; the multi-core claim overstates real
  scaling. Since each task is one length, work is also unbalanced (longer lengths cost
  more), so the 10 tasks are not equal-sized.
- **Related**: #114 (introduced this shape), PERF-04 #115 (memory bounded by same
  chunk count).
- **Suggested Fix**: Sub-chunk long sequences by `start`-range within each length (or
  bucket lengths across workers) so task count scales toward core count; alternatively,
  document the ceiling and update the CLAUDE.md scaling claim.

### PERF-13: No event-count serial guard before spawning the process pool (only a single-chunk guard)
- **Severity**: LOW
- **Dimension**: 2 — Parallel detector scaling & work distribution
- **Location**: `tracker/pattern_detector_parallel.py:134-136` (single-chunk guard),
  `:149-154` (pool construction with `initargs=(sequence, valid_events)`).
- **Status**: NEW
- **Description**: The only fast-path guard fires when `len(work_chunks) == 1` (i.e. the
  sequence is so short only one pattern length fits, #218). A small-but-not-tiny input —
  e.g. ~40 events, which still yields up to 10 chunks — spawns a `ProcessPoolExecutor`
  and pickles the full `sequence`/`valid_events` into every worker via `initargs`, even
  though a serial run would finish before the processes spawn. There is no "below N
  events, run `_detect_patterns_serial` inline" threshold.
- **Evidence**: `if len(work_chunks) == 1: … return self._detect_patterns_serial(...)`
  is the sole bypass; any 2+ chunk case constructs the pool unconditionally.
- **Impact**: Extra process-spawn + pickle-of-initargs latency on small inputs
  (pronounced under the `spawn` start method on macOS/Windows). No correctness impact.
- **Related**: #218 (single-chunk guard), PERF-12.
- **Suggested Fix**: Add a `len(sequence) < N` (or `len(valid_events) < N`) guard before
  pool construction that calls `_detect_patterns_serial` inline.

### PERF-14: `LARGE_FILE_THRESHOLD` is hardcoded, advisory-only, and not aligned with the two configurable sampling caps
- **Severity**: LOW
- **Dimension**: 3 — Large-file sampling trade-off
- **Location**: `main.py:861-864`; other caps at `tracker/pattern_detector.py:16`
  (`MAX_PATTERN_EVENTS=15000`), `:23` (`DETECTOR_MAX_EVENTS=1000`), config keys at
  `config/default_config.yaml:14-15`.
- **Status**: NEW
- **Description**: `MAX_PATTERN_EVENTS` (15000, parallel) and `DETECTOR_MAX_EVENTS`
  (1000, sequential) are now overridable via
  `processing.pattern_detection.max_events`/`max_pattern_events` (#219, resolved by
  `get_pattern_detection_caps`, `main.py:39-62`). But `LARGE_FILE_THRESHOLD = 10000` is
  still a bare inline literal in `run_full_pipeline`, has no `default_config.yaml` key,
  and is purely advisory (prints a hint, changes no behavior — confirmed
  `main.py:862-864`). The three numbers are not aligned: a 5,000-event file trips
  neither the 10,000 advisory nor the 15,000 parallel cap, yet would be resampled
  5,000→1,000 if the sequential fallback fires.
- **Evidence**: `LARGE_FILE_THRESHOLD = 10000` … `if len(events) > LARGE_FILE_THRESHOLD:
  print(...)` with no branch that alters detection.
- **Impact**: Cosmetic/maintainability — a magic number a user cannot tune and whose
  hint boundary does not correspond to either real sampling boundary. No output impact.
  (Content-loss framing of the samplers is deferred to `audit-patterns`.)
- **Related**: #219 (config caps), #100/#102 (shared sampler).
- **Suggested Fix**: Move `LARGE_FILE_THRESHOLD` into `default_config.yaml` alongside the
  other caps and align its default with the parallel cap, or delete the advisory branch.

### PERF-15: Redundant `EnhancedTempoMap` construction and events→frames→events round-trip across pipeline sites
- **Severity**: LOW
- **Dimension**: 8 — Cross-stage redundant recomputation
- **Location**: `tracker/parser_fast.py:203-204` (analysis path re-opens file + rebuilds
  tempo map), `main.py:646` and `main.py:854` (two fresh `EnhancedTempoMap(...)`),
  `benchmarks/performance_suite.py:216`; event re-extraction at `main.py:653` and
  `main.py:858` via `frames_to_events`.
- **Status**: NEW
- **Description**: `parse_midi_to_frames` returns `"metadata": {}` and never serializes
  tempo, so every downstream stage rebuilds a tempo map from scratch: `run_detect_patterns`
  and `run_full_pipeline` each construct a bare `EnhancedTempoMap(initial_tempo=500000)`
  (mutually exclusive per run, neither reused), and `parse_midi_to_frames_with_analysis`
  re-opens the MIDI file and rebuilds the map after already parsing once (comment: "could
  be cached from first pass"). Frames are derived from events at the frames stage, then
  events are re-extracted from frames at detection (`frames_to_events`). #119 removed the
  expensive half (per-pattern tempo analysis is now skipped via `analyze_tempo=False`),
  so what remains is cheap redundant allocation + an events↔frames round-trip, not the
  costly analysis.
- **Evidence**: `tempo_map = EnhancedTempoMap(initial_tempo=500000)` at both `main.py:646`
  and `:854`; `events = frames_to_events(frames)` at `:653` and `:858`.
- **Impact**: Minor wasted allocation/CPU; the detectors read only `note`/`volume` from
  events, so the redundant tempo maps are never wrong, just redundant. No output impact.
- **Related**: #119 (closed — costly half), #261 (shared `frames_to_events`).
- **Suggested Fix**: Optional — thread tempo/metadata through the parse JSON if a future
  stage needs it; otherwise leave as-is (the remaining cost is negligible). Cache the
  first-pass tempo map in `parse_midi_to_frames_with_analysis` (opt-in path).

### PERF-16: `MemoryMonitor` can report `peak_mb=0` for sub-interval work and silently swallows sampling errors
- **Severity**: LOW
- **Dimension**: 7 — Profiling-utility correctness
- **Location**: `utils/profiling.py:112-121` (`_monitor_loop`), `:91-110`
  (`stop_monitoring`).
- **Status**: NEW (sampling reliability); cross-ref Existing #135 (TD-10) for the
  swallow idiom.
- **Description**: `_monitor_loop` appends a sample then sleeps `interval_ms`; if
  `stop_monitoring` runs before the daemon thread's first loop iteration (work shorter
  than thread-scheduling latency), `_memory_samples` is empty and `stop_monitoring`
  returns `{"peak_mb": 0, "average_mb": 0, "samples": 0}` — a misleading zero rather
  than the RSS at start. The loop also wraps the body in `except Exception: break`,
  which discards any sampling error (and the final sample) without recording it. This is
  the `except`-swallow idiom tracked as TD-10 (#135, OPEN); note it now uses
  `except Exception:` (KeyboardInterrupt propagates), so it is narrower than the
  bare `except:` described in that issue.
- **Evidence**: `if not self._memory_samples: return {"peak_mb": 0, ...}`; loop body
  `try: … except Exception: break`.
- **Impact**: A profiled stage faster than `interval_ms` reports zero peak memory — a
  misleading metric in benchmark output, not a crash. `cpu_percent` deltas are likewise
  advisory (documented, no-interval reads). Low blast radius (dev tooling only).
- **Related**: #135 (TD-10), #118 (tracemalloc lifecycle fix).
- **Suggested Fix**: Seed `_memory_samples` with an immediate RSS read in
  `start_monitoring` so a peak is always available; log/count swallowed sampling
  exceptions instead of a bare `break`.

---

## Notes on existing/mitigated items (no new finding)
- **PERF-04 (#115, OPEN)** — "pattern-detection stage holds many full copies of the event
  sequence." The per-chunk duplication is eliminated by #114; peak is now bounded by
  `min(max_workers, chunk_count) × sequence`. The issue as written is largely mitigated;
  recommend re-scoping or closing it rather than re-reporting.
- **TD-10 (#135, OPEN)** — profiling `except` swallow; see PERF-16 cross-ref.

## Suggested next step
```
/audit-publish docs/audits/AUDIT_PERFORMANCE_2026-07-18.md
```
