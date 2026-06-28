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
  one for notes. Verify neither pass re-parses per event (no nested scan of the track
  inside the per-message loop) and that `tempo_map.get_frame_for_tick` /
  `get_tempo_at_tick` are O(1)-ish lookups, not a linear scan of all tempo changes per
  note (that would make parsing O(notes × tempo_changes)).
- `parse_midi_to_frames_with_analysis` re-opens the file (`mido.MidiFile(midi_path)`)
  and **rebuilds the tempo map from scratch** after already parsing once — the comment
  literally says "could be cached from first pass". Redundant pass = real but bounded
  cost (MEDIUM if on a hot path; the analysis variant is opt-in, so likely LOW).
- The broad `except Exception: continue` in the note loop swallows *every* per-event
  error silently — a perf-relevant correctness gap if it masks a slow/throwing tempo
  lookup. Cross-ref `/audit-safety` rather than re-reporting the swallow itself.

### Dimension 2: Parallel detector scaling & work distribution
`tracker/pattern_detector_parallel.py`, `ParallelPatternDetector._detect_patterns_parallel`
and the module-level worker `_detect_patterns_worker`:
- **Quadratic core**: for each `start` offset the worker rebuilds `tuple(sequence[...])`
  and then **rescans the entire sequence** (`pos` from 0 to end) to find matches —
  O(n) per start, O(n²) per pattern length, O(n²·L) overall. Chunking only splits the
  *start* range across workers; total work is unchanged, so wall-time scales with cores
  but the algorithm is still quadratic in event count. Flag the O(n²) as the root cost;
  the sampling cap (Dim 3) is the band-aid.
- **Worker sizing**: `self.max_workers = max(1, mp.cpu_count() - 1)`. Check it is used
  consistently for both the executor and the `chunk_size` math
  (`(len(sequence) - length + 1) // self.max_workers`). On a 1-core box this is 1 worker
  with full `ProcessPoolExecutor` overhead — verify small inputs do not pay process-spawn
  + pickle cost for negligible work (there is no "below N events, run serial inline"
  guard before building `work_chunks`).
- **IPC bloat**: each `work_chunk` dict embeds the **full `sequence` and full
  `valid_events`** (lines building `work_chunks`). With thousands of chunks, the entire
  sequence is pickled and shipped to workers once per chunk — memory + serialization
  cost that can dwarf the compute. This is a strong MEDIUM (HIGH if it OOMs on a common
  file).
- **Fallback path**: confirm the documented graceful fallback to serial
  (`_detect_patterns_serial`) actually fires — the `try/except` around the
  `ProcessPoolExecutor` block. Per-chunk `future.result(timeout=30)` failures are caught
  and *skipped* (pbar.write), which silently drops candidate patterns rather than
  falling back; note whether that is acceptable.

### Dimension 3: Large-file sampling trade-off (speed vs dropped content)
Two *different* thresholds exist — do not conflate them:
- `MAX_EVENTS = 15000` inside `ParallelPatternDetector.detect_patterns`
  (`tracker/pattern_detector_parallel.py`): when exceeded, `np.linspace` downsamples the
  sequence to 15000 events. This **drops events from pattern analysis** — a speed/quality
  trade-off. Whether the dropped events still reach the exporter (so the song is intact,
  just less-compressed) vs. are lost from output is a **content-loss** question that is
  CRITICAL-adjacent — cross-reference `.claude/commands/audit-patterns/SKILL.md` for the
  round-trip/data-loss angle; here, report only the *performance* framing (cap chosen for
  speed, magic number, no config knob).
- `LARGE_FILE_THRESHOLD = 10000` in `main.py`'s detect-patterns stage — only prints a
  "consider --no-patterns" hint, does not change behavior. Confirm it is purely advisory.
- Flag both as hardcoded magic numbers with no `config/default_config.yaml` override and
  no relationship to each other (a file between 10k and 15k events trips the warning but
  not the sampler).

### Dimension 4: Inter-stage memory (whole-file JSON, dict copies, duplication)
Every pipeline stage reads its input fully into memory and writes its output fully —
`main.py` `run_parse`/`run_map`/`run_frames` each do
`json.loads(Path(...).read_text())` then hold the whole dict, then
`Path(...).write_text(json.dumps(...))`. Audit:
- Frame data duplication: parsed events → mapped events → frames dict are three full
  in-memory copies of roughly the same data; the frames structure
  (`{channel: {frame_num: {...}}}`) is the largest. On a long song this is the memory
  high-water mark. Check whether any stage holds the *previous* stage's structure alive
  while building the next (no `del` / streaming).
- `ParallelPatternDetector` additionally holds `sequence`, `valid_events`, every
  `work_chunk` (each with full copies — see Dim 2), and `all_candidate_patterns`
  simultaneously. Estimate the multiplier vs. raw event count.
- Large dict copies: `ProfilerRegistry.get_profiles()` in `utils/profiling.py` returns
  `self._profiles.copy()` — fine for small registries, note only if it can grow large.

### Dimension 5: Serialization cost
All intermediate JSON in `main.py` is written with **`json.dumps(..., indent=2)`**
(`run_parse`, `run_map`, `run_frames`, and the export-output writer). `indent=2`
pretty-prints with newlines + spaces per element — on a frames dict with tens of
thousands of entries this multiplies output size and write time vs. compact
(`separators=(',',':')`) serialization, and these are *intermediate* artifacts a human
rarely reads. `benchmarks/performance_suite.py` `generate_report` and
`run_benchmark` in `main.py` also use `indent=2`, which is fine for reports. Flag the
hot intermediates (frames especially) as the place where compact JSON is the easy win.
MEDIUM at most (correct output, just bloated/slow).

### Dimension 6: Benchmark-harness validity (does it measure the real path?)
This is the highest-leverage dimension — a benchmark that measures the *wrong* code is
worse than none, because it greenlights regressions:
- `benchmarks/performance_suite.py` imports `from tracker.parser import
  parse_midi_to_frames` — the **slow full parser**, NOT `tracker/parser_fast.py` that the
  production `run_parse` actually uses (`main.py` line ~35). The "parse" stage benchmark
  therefore does not measure the 120x fast path at all.
- Same file's `benchmark_pattern_detection` uses `EnhancedPatternDetector` (serial,
  `tracker/pattern_detector.py`), while the production detect-patterns stage in `main.py`
  uses `ParallelPatternDetector` (`tracker/pattern_detector_parallel.py`). The benchmark
  measures the fallback, not the default.
- `PerformanceProfiler.profile` is a context manager that builds a `BenchmarkResult` on
  exit but **discards it** (the result is a local in `profile`); the per-stage methods
  instead call `self.profiler._end_profiling(...)` a *second* time after the `with`
  block, re-reading memory after the work has already returned. Verify the reported
  `duration_ms`/`memory_peak_mb` actually correspond to the measured block and are not
  double-counted or stale.
- Baselines: `benchmark_results/benchmark_results.json` is checked in, but it is a *run
  output*, not a versioned baseline the harness compares against — there is no
  regression gate (no "fail if slower than baseline by X%"). Note the absence; a
  benchmark with no checked-in baseline and no comparison cannot catch a regression.
- `run_baseline_benchmark` in `benchmarks/run_benchmarks.py` searches `test_data/`,
  `examples/`, `samples/`, `.` for `*.mid` and silently runs on whatever it finds (or
  nothing) — non-deterministic inputs make results incomparable across machines/runs.

### Dimension 7: Profiling-utility correctness
`utils/profiling.py` (`get_memory_usage`, `log_memory_usage`, `MemoryMonitor`,
`profile_memory_usage`, `PerformanceContext`):
- `tracemalloc` lifecycle: every profiler starts `tracemalloc.start()` and stops it in a
  `try/except: pass`. Nested profilers (e.g. a `@profile_memory_usage` function called
  inside a `PerformanceContext`) share one global tracemalloc; the inner `stop()` blinds
  the outer one. Flag if profilers can nest on the real pipeline.
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
Work done more than once across the pipeline because results are not passed forward:
- The tempo map is rebuilt independently in `tracker/parser_fast.py`
  (`parse_midi_to_frames`), again in `parse_midi_to_frames_with_analysis`, and a *fresh*
  `EnhancedTempoMap(initial_tempo=500000)` is constructed in `main.py`'s detect-patterns
  stage and in `benchmarks/performance_suite.py` — none reuse the tempo data already
  computed at parse time (it is not serialized into the parse JSON). Note the recompute;
  the fix is to thread tempo through the JSON contract.
- Frame data is re-derived from events at frames stage, then events are *re-extracted
  from frames* in the pattern-detection stage (`main.py` rebuilds an `events` list out of
  the frames dict). Confirm and flag the round-trip (events → frames → events).

## Cross-Dimension Dedup
A single root cause can surface in several dimensions (the O(n²) match scan drives both
Dim 2 and the need for Dim 3's sampling cap; the IPC bloat is both Dim 2 and Dim 4).
Report it once in the most actionable dimension and cross-reference. Where a finding is
really about *content loss* from sampling, defer the loss framing to
`.claude/commands/audit-patterns/SKILL.md` and keep only the performance angle here.

## Skeptical Checklist
Before writing any finding, confirm against the live code:
- [ ] Is the cost actually super-linear, or just a big constant? Show the nested loop /
      per-element rescan, not a hunch.
- [ ] Does the "parallel" path measurably parallelize, or is total work O(n²) regardless
      of cores (cores cut wall-time, not work)?
- [ ] On a *small* input, does the parallel detector pay process-spawn + pickle overhead
      that exceeds a serial run? Is there a guard?
- [ ] Does the benchmark import/exercise the **same** module the production CLI runs
      (`parser_fast` vs `parser`, `ParallelPatternDetector` vs `EnhancedPatternDetector`)?
- [ ] Is there a checked-in baseline AND a comparison that would fail on regression? If
      not, the harness cannot catch what this audit is for.
- [ ] Is the memory growth bounded by event count, or does it duplicate the full
      sequence per work-chunk / per stage?
- [ ] For HIGH: name a *common* MIDI file size that OOMs or times out — otherwise it is
      MEDIUM/LOW.
- [ ] Re-read the path and try to disprove the finding before keeping it.

## Output
Save the report to: **`docs/audits/AUDIT_PERFORMANCE_<TODAY>.md`** (YYYY-MM-DD).
Structure:
1. **Summary** — finding counts per severity and per dimension; the 3 highest-leverage
   fixes (likely: benchmark measures wrong path; O(n²) detector + per-chunk IPC bloat;
   `indent=2` on frames intermediate).
2. **Findings** — base per-finding format from `_audit-common.md` plus the `Dimension`
   field.

Do NOT create GitHub issues directly. Then suggest:
```
/audit-publish docs/audits/AUDIT_PERFORMANCE_<TODAY>.md
```
