---
description: "Audit performance — parse speed, pattern-detection parallelism, memory footprint"
argument-hint: "[--focus <dims>]"
---

# Performance Audit

Correctness-of-performance audit of the MIDI2NES compile path: parse speed, the
multi-core pattern detector, and memory footprint across pipeline stages. The goal is
not micro-optimization — it is to find places where the code does *asymptotically*
more work than it should (accidental O(n²), redundant passes), where memory grows
unbounded on a realistic file, or where "parallel"/"fast" claims do not hold in the
production path.

Shared protocol (layout, dedup, finding format): `.claude/commands/_audit-common.md`.
Severity rubric: `.claude/commands/_audit-severity.md`. Performance findings are
usually **MEDIUM/LOW**; escalate to **HIGH** only when a regression makes a *common*
MIDI file fail outright — OOM or a timeout/hang on input a user would realistically
feed in. Cosmetic mis-reporting (a wrong stat, a slow-but-correct stage) stays MEDIUM
or LOW.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 2,3`). Default: all.

## Extra Per-Finding Field
- **Dimension**: one of the dimensions below.

## Dimensions

### Dimension 1: Parser hot-path efficiency
`tracker/parser_fast.py` is the default front-end (`run_parse` in `main.py` imports
`parse_midi_to_frames` from it). Confirm the speed claim is structural, not accidental:
- `parse_midi_to_frames` makes **two passes** over `mid.tracks` — one for `set_tempo`,
  one for notes. Neither pass re-parses per event (no nested scan of the track inside
  the per-message loop). `tempo_map.get_frame_for_tick` / `get_tempo_at_tick` are
  O(log T) lookups, not a linear scan of all tempo changes per note. Since #113 (now
  **CLOSED**) these are backed by a lazily-built bisect index (`_build_tempo_index` in
  `tracker/tempo_map.py`) over the sorted `tempo_changes`, with cumulative ms
  precomputed so `calculate_time_ms(0, tick)` is one bisect. Re-verify this holds if
  `tempo_map.py` changes again — the fix relies on `add_tempo_change` keeping
  `tempo_changes` sorted and the index being invalidated whenever it mutates.
- `parse_midi_to_frames_with_analysis` re-opens the file (`mido.MidiFile(midi_path)`)
  and **rebuilds the tempo map from scratch** after already parsing once — the comment
  literally says "could be cached from first pass" (still true, unchanged). Redundant
  pass = real but bounded cost (MEDIUM if on a hot path; the analysis variant is
  opt-in, so likely LOW).
- The note loop's `except Exception as e: ... continue` is still broad (catches any
  error type), but it **no longer swallows silently**: it increments a
  `dropped_note_events` counter, records `last_drop_reason`, and prints a warning with
  the count and last error after the loop (#124/#125, closed — see
  `de998dd`). From a *performance* angle the breadth of the catch could still mask a
  slow/throwing tempo lookup mid-run without identifying which note failed, but it can
  no longer hide an entire run's worth of failures unnoticed. Cross-ref `/audit-safety`
  for the catch-breadth question itself; here note only that the count/warn behavior
  is now in place, not a bare swallow.

### Dimension 2: Parallel detector scaling & work distribution
`tracker/pattern_detector_parallel.py` — `ParallelPatternDetector._detect_patterns_parallel`,
the shared `_collect_length_candidates` helper, and the module-level worker
`_detect_patterns_worker`. PERF-02 (#114) described this as O(n²·L) with full-sequence
per-chunk IPC; #114 is now **CLOSED** and both halves of that finding are fixed in the
current code — verify the fix is complete rather than re-reporting the old shape:
- **Quadratic core: fixed.** The old per-`start` rebuild-and-rescan is gone.
  `_collect_length_candidates` now makes a single linear pass per pattern length,
  bucketing every window by its tuple value (`groups.setdefault(window, []).append(start)`),
  then greedily selects non-overlapping matches per bucket — O(n) per length, O(n·L)
  total across `min_pattern_length..max_pattern_length`. Both the `ProcessPoolExecutor`
  workers (`_detect_patterns_worker`) and the serial fallback (`_detect_patterns_serial`)
  call this *same* helper, so the two paths are now algorithmically equivalent (the old
  serial fallback used a different scan). Verify this equivalence still holds if either
  path is touched again.
- **Chunking now shaped by pattern length, not the `start` range.** `work_chunks` is one
  dict per pattern length (`{'pattern_length': length}` for `length in
  range(min_pattern_length, min(max_pattern_length, len(sequence)) + 1)`). With the
  pipeline's actual defaults (`PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12` in
  `main.py`) that is only **10 tasks**, independent of input size. On a box with more
  than 10 usable cores (`self.max_workers = max(1, mp.cpu_count() - 1)`), several
  workers get zero work — parallelism is now ceilinged by the pattern-length range
  rather than by core count or event count. This is new coarse-grained-parallelism
  behavior introduced by the #114 fix; confirm whether it matters given how fast the
  O(n) core now is (likely LOW/MEDIUM at most, but check on a very large sampled
  sequence before dismissing it).
- **IPC bloat: fixed.** `sequence`/`valid_events` are no longer embedded in every
  `work_chunk`. `ProcessPoolExecutor(..., initializer=_init_pattern_worker,
  initargs=(sequence, valid_events))` ships them **once per worker process** into
  module globals (`_WORKER_SEQUENCE`/`_WORKER_EVENTS`); `_detect_patterns_worker` reads
  those globals instead of a per-chunk copy. Confirm every code path that constructs
  the pool goes through this initializer (currently the only construction site is
  `_detect_patterns_parallel`) and that no other call site reintroduces a heavy
  per-chunk dict.
- **Worker sizing**: `self.max_workers = max(1, mp.cpu_count() - 1)` is still used only
  for the executor's `max_workers`. There is still no "below N events, run serial
  inline" guard before spinning up the `ProcessPoolExecutor` — a tiny input still pays
  process-spawn + pickle-of-`initargs` overhead, even though there are now at most
  `max_pattern_length - min_pattern_length + 1` tasks to hand out.
- **Fallback path**: the documented graceful fallback to serial (`_detect_patterns_serial`)
  still fires from the `try/except` around the `ProcessPoolExecutor` block. Per-chunk
  `future.result(timeout=30)` failures are still caught and *skipped* (`pbar.write`)
  rather than raised or retried — this now drops just one pattern-length's candidates
  instead of one start-range chunk's worth, but the drop is still a bare printed line
  with no counted/propagated warning the way the parser's dropped-note path now has
  (Dimension 1, #124) — note the asymmetry rather than re-reporting the drop itself as
  new.

### Dimension 3: Large-file sampling trade-off (speed vs dropped content)
Three thresholds now exist across two files — do not conflate them (there were two
before the shared-sampling consolidation, #100/#102):
- `MAX_PATTERN_EVENTS = 15000` — defined in `tracker/pattern_detector.py` (it is **not**
  a local constant inside `pattern_detector_parallel.py`; both detectors import the
  shared `sample_events_for_detection` from `tracker/pattern_detector.py`).
  `ParallelPatternDetector.detect_patterns` calls `sample_events_for_detection(valid_events)`
  with this default, downsampling via `np.linspace` when exceeded. This still **drops
  events from pattern analysis** — a speed/quality trade-off.
- `DETECTOR_MAX_EVENTS = 1000` — a second, separate cap in the same file, for the
  O(n²)-ish sequential `EnhancedPatternDetector`. It is used by the `detect-patterns`
  subcommand (`run_detect_patterns` in `main.py`) and by the full pipeline's sequential
  fallback when parallel detection raises. Both call sites sample **uniformly straight
  to this number** (`sample_events_for_detection(events, DETECTOR_MAX_EVENTS)`) rather
  than letting the detector's internal cap silently re-sample a larger sample (#100),
  so the printed "sampled to N" warning matches what is actually retained.
- `LARGE_FILE_THRESHOLD = 10000` in `main.py` (`run_full_pipeline`'s pattern-detection
  stage) — still only prints a "consider --no-patterns" hint, does not change behavior.
  Confirm it is purely advisory.
- Whether events dropped by either sampler still reach the exporter (song intact, just
  less-compressed) vs. are lost from output entirely is a **content-loss** question —
  cross-reference `.claude/commands/audit-patterns/SKILL.md` for that angle; report
  only the *performance* framing here: three hardcoded magic numbers, no
  `config/default_config.yaml` override, and they are not aligned with each other —
  e.g. a 5,000-event file trips neither the 10,000 advisory threshold nor the 15,000
  parallel-sampling cap, but would still be resampled 5,000→1,000 if the sequential
  fallback fires.

### Dimension 4: Inter-stage memory (whole-file JSON, dict copies, duplication)
Every pipeline stage reads its input fully into memory (via `load_json_stage`, which
still ultimately does `json.loads(Path(...).read_text())`) and writes its output fully
— `main.py` `run_parse`/`run_map`/`run_frames` each hold the whole dict, then
`Path(...).write_text(json.dumps(...))`. Audit:
- Frame data duplication: parsed events → mapped events → frames dict are three full
  in-memory copies of roughly the same data; the frames structure
  (`{channel: {frame_num: {...}}}`) is the largest. On a long song this is the memory
  high-water mark. No stage `del`s the previous stage's structure while building the
  next (no streaming) — unchanged.
- `ParallelPatternDetector`'s memory shape changed with the #114 fix (Dimension 2): it
  still holds `sequence` and `valid_events` for the duration of detection, plus
  `all_candidate_patterns` accumulated across all per-length results — but the
  **per-chunk full-sequence duplication is gone**. Each worker process now holds one
  copy of `sequence`/`valid_events` via the pool initializer, not one copy per chunk;
  peak memory is roughly `(workers actually used) × sequence size`, bounded by
  `min(max_workers, chunk_count)` (chunk_count = pattern-length range, see Dimension 2)
  rather than by the old chunk count driven by the `start` range.
- Large dict copies: `ProfilerRegistry.get_profiles()` in `utils/profiling.py` returns
  `self._profiles.copy()` — fine for small registries, note only if it can grow large
  (unchanged).

### Dimension 5: Serialization cost
All intermediate JSON in `main.py` is written with **`json.dumps(..., indent=2)`**:
`run_parse`, `run_map`, `run_frames`, and `run_detect_patterns`'s pattern-output writer
(`patterns.json`). `indent=2` pretty-prints with newlines + spaces per element — on a
frames dict with tens of thousands of entries this multiplies output size and write
time vs. compact (`separators=(',',':')`) serialization, and these are *intermediate*
artifacts a human rarely reads. `benchmarks/performance_suite.py` `generate_report` and
`run_benchmark` in `main.py` also use `indent=2`, which is fine for reports (not
hot intermediates). Flag the hot intermediates (frames especially) as the place where
compact JSON is the easy win. MEDIUM at most (correct output, just bloated/slow).

### Dimension 6: Benchmark-harness validity (does it measure the real path?)
This is the highest-leverage dimension — a benchmark that measures the *wrong* code is
worse than none, because it greenlights regressions. PERF-06 (#117) is still **OPEN**;
all of the following still hold against current code:
- `benchmarks/performance_suite.py` imports `from tracker.parser import
  parse_midi_to_frames` — the **slow full parser**, NOT `tracker/parser_fast.py` that
  the production `run_parse` actually uses (`main.py:69` inside `run_parse`, and again
  at `main.py:504` inside `run_full_pipeline`). The "parse" stage benchmark therefore
  does not measure the 120x fast path at all.
- Same file's `benchmark_pattern_detection` uses `EnhancedPatternDetector` (serial,
  `tracker/pattern_detector.py`), while the production detect-patterns stage in `main.py`
  uses `ParallelPatternDetector` (`tracker/pattern_detector_parallel.py`). The benchmark
  measures the fallback, not the default — and now also does not exercise the #114
  fix at all (Dimension 2), since that fix lives entirely in the parallel path.
- `PerformanceProfiler.profile` (`benchmarks/performance_suite.py`) is a context
  manager that builds a `BenchmarkResult` on exit via `_end_profiling` but **discards
  it** (the result is a local inside `profile`); every per-stage method
  (`benchmark_parse_stage`, `benchmark_map_stage`, `benchmark_frames_stage`,
  `benchmark_pattern_detection`, `benchmark_export_stage`) then calls
  `self.profiler._end_profiling(stage_name, True)` a *second* time after the `with`
  block, re-reading memory after the work has already returned and after
  `tracemalloc.stop()` already ran once. Verify the reported `duration_ms`/
  `memory_peak_mb` actually correspond to the measured block and are not
  double-counted or stale (the second call's `tracemalloc.get_traced_memory()` runs
  against a stopped/restarted tracer, so its "peak" is suspect).
- Baselines: `benchmark_results/benchmark_results.json` is checked into the repo, but
  it is a *run output*, not a versioned baseline the harness compares against — there
  is no regression gate (no "fail if slower than baseline by X%"). Note the absence; a
  benchmark with no checked-in baseline and no comparison cannot catch a regression.
- `run_baseline_benchmark` in `benchmarks/run_benchmarks.py` searches `test_data/`,
  `examples/`, `samples/`, `.` for `*.mid` and silently runs on whatever it finds (or
  nothing) — non-deterministic inputs make results incomparable across machines/runs.

### Dimension 7: Profiling-utility correctness
`utils/profiling.py` (`get_memory_usage`, `log_memory_usage`, `MemoryMonitor`,
`profile_memory_usage`, `PerformanceContext`). PERF-07 (#118) is still **OPEN**; all of
the following still hold against current code:
- `tracemalloc` lifecycle: every profiler (`profile_memory_usage`'s wrapper and
  `PerformanceContext.__enter__`/`__exit__`) starts `tracemalloc.start()` and stops it
  in a `try/except: pass`. Nested profilers (e.g. a `@profile_memory_usage` function
  called inside a `PerformanceContext`) share one global tracemalloc; the inner
  `stop()` blinds the outer one. Flag if profilers can nest on the real pipeline.
- `process.cpu_percent()` is called once at start and once at end with no interval —
  the first call after process start returns `0.0` and the second measures since the
  first, so `cpu_percent` deltas are unreliable. MEDIUM/LOW (a misleading metric, not a
  crash).
- `MemoryMonitor._monitor_loop` swallows all exceptions with bare `except: break` and
  samples on a daemon thread; verify `stop_monitoring`'s `join(timeout=1.0)` cannot lose
  samples or report `{"peak_mb": 0}` when the work is shorter than `interval_ms`.
- `get_memory_usage` returns RSS/VMS/percent/available — confirm these are the values the
  callers (`main.py` `run_benchmark_memory`, `run_benchmarks.py`) actually print, and that
  none divide by zero on a total of 0.

### Dimension 8: Cross-stage redundant recomputation
Work done more than once across the pipeline because results are not passed forward.
PERF-08 (#119) is still **OPEN**:
- The tempo map is rebuilt independently in `tracker/parser_fast.py`
  (`parse_midi_to_frames`), again in `parse_midi_to_frames_with_analysis`, and a *fresh*
  `EnhancedTempoMap(initial_tempo=500000)` is constructed **twice more** in `main.py` —
  once in the `detect-patterns` subcommand handler (`run_detect_patterns`) and once
  inline in `run_full_pipeline`'s pattern-detection step (these two are mutually
  exclusive per single invocation, but neither reuses the other) — plus again in
  `benchmarks/performance_suite.py`'s `benchmark_pattern_detection`. None of these
  reuse the tempo data already computed at parse time (it is not serialized into the
  parse JSON — `parse_midi_to_frames` returns `"metadata": {}`). Both of `main.py`'s
  fresh tempo maps also default to `ticks_per_beat=480` rather than the source file's
  actual resolution, but since the pattern detectors only read `note`/`volume` from
  events (not tempo), this is a wasted construction rather than an incorrect one today
  — note the recompute; the fix is to thread tempo through the JSON contract.
- Frame data is re-derived from events at frames stage, then events are *re-extracted
  from frames* in the pattern-detection stage — confirmed in both `main.py`'s
  `run_detect_patterns` and the inline pattern-detection block of `run_full_pipeline`,
  each of which rebuilds an `events` list out of the `frames` dict. Confirm and flag
  the round-trip (events → frames → events).

## Cross-Dimension Dedup
A single root cause can surface in several dimensions. The #114 fix collapsed what used
to be a Dim 2 + Dim 4 shared root cause (quadratic scan driving the need for Dim 3's
sampling cap, and the IPC bloat inflating Dim 4's memory picture) into a much smaller
remaining surface (the coarse pattern-length chunking noted in both Dim 2 and Dim 4).
Report it once in the most actionable dimension and cross-reference. Where a finding is
really about *content loss* from sampling, defer the loss framing to
`.claude/commands/audit-patterns/SKILL.md` and keep only the performance angle here.

## Skeptical Checklist
Before writing any finding, confirm against the live code:
- [ ] Is the cost actually super-linear, or just a big constant? Show the nested loop /
      per-element rescan, not a hunch. (The old Dim 2 rescan is fixed — don't
      re-report it without re-reading `_collect_length_candidates` first.)
- [ ] Does the "parallel" path measurably parallelize, or is total work bounded by a
      fixed task count regardless of cores (the pattern-length chunk count, currently
      10 by default, not core count)?
- [ ] On a *small* input, does the parallel detector pay process-spawn + pickle
      overhead that exceeds a serial run? Is there a guard?
- [ ] Does the benchmark import/exercise the **same** module the production CLI runs
      (`parser_fast` vs `parser`, `ParallelPatternDetector` vs `EnhancedPatternDetector`)?
- [ ] Is there a checked-in baseline AND a comparison that would fail on regression? If
      not, the harness cannot catch what this audit is for.
- [ ] Is the memory growth bounded by event count, or does it duplicate the full
      sequence per work-chunk / per stage? (Per-chunk duplication is fixed; per-worker
      duplication via the pool initializer still exists — is it bounded sensibly?)
- [ ] For HIGH: name a *common* MIDI file size that OOMs or times out — otherwise it is
      MEDIUM/LOW.
- [ ] Re-read the path and try to disprove the finding before keeping it.

## Output
Save the report to: **`docs/audits/AUDIT_PERFORMANCE_<TODAY>.md`** (YYYY-MM-DD).
Structure:
1. **Summary** — finding counts per severity and per dimension; the 3 highest-leverage
   fixes (likely: benchmark measures wrong path; `indent=2` on frames intermediate; the
   new coarse pattern-length-chunk parallelism ceiling from the #114 fix).
2. **Findings** — base per-finding format from `_audit-common.md` plus the `Dimension`
   field.

Do NOT create GitHub issues directly. Then suggest:
```
/audit-publish docs/audits/AUDIT_PERFORMANCE_<TODAY>.md
```
