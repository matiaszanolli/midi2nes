# Performance Audit — MIDI2NES

- **Date**: 2026-06-29
- **Scope**: parse hot path, parallel pattern detector, large-file sampling, inter-stage memory, serialization cost, benchmark-harness validity, profiling utilities, cross-stage redundant recomputation.
- **Method**: live source re-read per `.claude/commands/audit-performance/SKILL.md`; severity per `_audit-severity.md`; dedup against `/tmp/audit/issues.json` (22 open issues) and `docs/audits/`.

> Note on SKILL drift: the SKILL references an inline `MAX_EVENTS = 15000` + `np.linspace` block in `ParallelPatternDetector.detect_patterns`, and a `LARGE_FILE_THRESHOLD` that "does not change behavior". Both have since been refactored (#21): sampling now lives in `tracker/pattern_detector.py::sample_events_for_detection` (`MAX_PATTERN_EVENTS = 15000`) and is shared by both entry points. Findings below reflect the **current** tree.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 5 |
| LOW      | 4 |
| **Total**| **9** |

By dimension: D1 parse hot-path (1), D2 parallel detector (2), D3 sampling magic numbers (1), D4 inter-stage memory (1, x-ref), D5 serialization (1), D6 benchmark validity (2), D7 profiling (1), D8 redundant recompute (1, folded). NEW findings: 9 (none dedup to an open issue; the closest open issues are about *correctness/coverage*, not the performance angle reported here).

### Three highest-leverage fixes
1. **PERF-06 — the benchmark harness measures the wrong modules** (`tracker.parser` not `parser_fast`; `EnhancedPatternDetector` not `ParallelPatternDetector`). It cannot catch a regression in the production hot path, and there is no checked-in baseline + comparison gate. Highest leverage because a wrong benchmark greenlights regressions silently.
2. **PERF-02 — the pattern matcher is O(n²·L) and ships the full sequence to every worker.** Cores cut wall-time, not total work; the `sample_events_for_detection` cap (PERF-03) is a band-aid over the asymptotics. Per-chunk IPC duplicates the whole sequence ~`lengths × workers` times.
3. **PERF-05 — every intermediate JSON is written with `indent=2`.** The frames artifact (largest, tens of thousands of entries) pays a 2–3x size/write-time penalty for a file no human reads.

---

## Findings

### PERF-01: Parser frame/tempo lookup is O(notes × tempo_changes), not O(1)
- **Severity**: MEDIUM
- **Dimension**: D1 — Parser hot-path efficiency
- **Location**: `tracker/parser_fast.py:63,75`; `tracker/tempo_map.py:95-103` (`get_tempo_at_tick`), `:105-136` (`calculate_time_ms`), `:144-147` (`get_frame_for_tick`)
- **Status**: NEW
- **Description**: The SKILL's claim that `get_frame_for_tick` / `get_tempo_at_tick` are "O(1)-ish" does **not** hold. In the per-note loop (`parser_fast.py:60-76`) each `note_on`/`note_off` calls both:
  - `get_tempo_at_tick(current_tick)` — a **linear scan of all tempo changes** (`tempo_map.py:98-102`), O(T) per note.
  - `get_frame_for_tick(current_tick)` → `calculate_time_ms(0, tick)` (`tempo_map.py:146`). `calculate_time_ms` walks tick-segment by tick-segment and, **for each segment, does another linear scan** of `self.tempo_changes` to find the next change boundary (`tempo_map.py:118-133`) — O(T²) for a tick past every change, only memoised on the exact `(0, tick)` pair via `_time_cache`.
  Total parse cost is therefore **O(N·T + D·T²)** where N = note events, T = tempo changes, D = distinct ticks. For the common case T is tiny (1–3), so this is a small constant and the "120x" claim survives. But a MIDI with heavy tempo automation (hundreds of `set_tempo`, e.g. a ritardando-laden orchestral export) makes parse super-linear.
- **Evidence**: `get_tempo_at_tick` loops `for change_tick, tempo in self.tempo_changes` (no bisect); `calculate_time_ms` nests `for change_tick, _ in self.tempo_changes` inside its `while current_tick < end_tick` loop.
- **Impact**: Parse stage only; degrades on tempo-dense MIDI. Not OOM, not a crash → MEDIUM, escalation to HIGH would need a *common* file that times out, which a tempo-dense-but-modest file does not reach.
- **Related**: PERF-08 (tempo map rebuilt multiple times); the same O(T) scan recurs everywhere `get_tempo_at_tick` is called.
- **Suggested Fix**: `self.tempo_changes` is kept sorted (`add_tempo_change` sorts) — replace the linear scans with `bisect.bisect_right` over a precomputed tick array, and precompute cumulative ms-at-each-change so `calculate_time_ms(0, tick)` is one bisect + one multiply.

### PERF-02: Pattern matcher is O(n²·L) with full-sequence per-chunk IPC
- **Severity**: MEDIUM
- **Dimension**: D2 — Parallel detector scaling & work distribution
- **Location**: `tracker/pattern_detector_parallel.py:256-311` (`_detect_patterns_worker`), `:89-109` (`_detect_patterns_parallel` chunk construction)
- **Status**: NEW
- **Description**: Two coupled inefficiencies:
  1. **Quadratic core.** For each `start` in a chunk the worker rebuilds `tuple(sequence[start:start+pattern_length])` and then **rescans the entire sequence from `pos=0`** (`:282-288`) to find matches — O(n) per start, repeated for every start and every pattern length → **O(n²·L)** total work. Splitting the `start` range across workers (`:99`) only divides wall-time by core count; **total work is unchanged**. The `sample_events_for_detection` cap (PERF-03) exists precisely to bound this.
  2. **Per-chunk IPC duplication.** Every `work_chunk` dict embeds the **full `sequence` and full `valid_events`** (`:102-103`). The number of chunks is ≈ `lengths × max_workers` (one chunk per `chunk_size` slice of the start range, with `chunk_size = (n-length+1)//max_workers`). So the entire n-element sequence is pickled and shipped ≈ `(max_pattern_length-min_pattern_length) × max_workers` times — bounded, but on a 15000-event cap with `max_pattern_length=12` and 16 cores that is ~10×16 = 160 copies of a 15000-tuple list pickled across the process boundary. Serialization + memory can rival the compute.
- **Evidence**: worker inner `while pos <= len(sequence) - pattern_len` (`:282`) is independent of `start_offset`/`end_offset`; chunk dict carries `'sequence': sequence, 'events': valid_events` verbatim.
- **Impact**: Default pipeline + `detect-patterns` subcommand. Wall-time scales with cores but the algorithm stays quadratic; IPC bloat raises peak memory. Bounded by the 15000 cap so it does not OOM a common file → MEDIUM (would be HIGH if it OOM'd realistic input).
- **Related**: PERF-03 (sampling band-aid), PERF-04 (memory), open #46/REG-06 (multi-core path untested — a *coverage* gap, distinct from this *algorithmic* finding).
- **Suggested Fix**: Replace the rescan with a single suffix-hash / rolling-hash pass that records all equal windows in O(n) per length (O(n·L) total). Ship `sequence`/`valid_events` **once** via a `ProcessPoolExecutor` initializer (module global) instead of per chunk.

### PERF-03: Pattern-detection caps are hardcoded magic numbers with no config knob
- **Severity**: LOW
- **Dimension**: D3 — Large-file sampling trade-off
- **Location**: `tracker/pattern_detector.py:13` (`MAX_PATTERN_EVENTS = 15000`), `:143` (`MAX_EVENTS = 1000` in `EnhancedPatternDetector.detect_patterns`); `main.py:467` (`LARGE_FILE_THRESHOLD = 10000`), `:485` (`FALLBACK_MAX_EVENTS = 2000`)
- **Status**: NEW
- **Description**: Four unrelated, hardcoded thresholds govern pattern-detection scale, none overridable from `config/default_config.yaml`:
  - `MAX_PATTERN_EVENTS = 15000` — shared uniform-sampling cap (lossy).
  - `MAX_EVENTS = 1000` — a **second, head-truncating** cap inside `EnhancedPatternDetector.detect_patterns` (`pattern_detector.py:143-147`, `sequence = sequence[:MAX_EVENTS]`). This truncates rather than uniformly samples, and is *below* the 15000 shared cap, so the serial detector silently considers only the first 1000 events even after sampling spread them.
  - `LARGE_FILE_THRESHOLD = 10000` — purely advisory; only prints a "consider --no-patterns" hint (`main.py:468-471`), confirmed not to change behavior.
  - `FALLBACK_MAX_EVENTS = 2000` — sampling cap on the serial fallback path.
  A file between 10000 and 15000 events trips the advisory warning but not the sampler; the relationships between the four numbers are undocumented.
- **Evidence**: see lines above; `LARGE_FILE_THRESHOLD` block contains only `print(...)` statements.
- **Impact**: Misleading/confusing thresholds; the `MAX_EVENTS = 1000` head-truncation in the serial detector is the most surprising (analysis quality silently capped). Performance framing only — the *content-loss* angle is deferred to `.claude/commands/audit-patterns/SKILL.md`.
- **Related**: open #21 (shared large-file policy) introduced `sample_events_for_detection`; PERF-02.
- **Suggested Fix**: Surface the caps as `config/default_config.yaml` keys; either remove the redundant `MAX_EVENTS = 1000` head-truncation or route it through `sample_events_for_detection` so it samples uniformly and respects the shared cap.

### PERF-04: Pattern-detection stage holds many full copies of the event sequence simultaneously
- **Severity**: LOW
- **Dimension**: D4 — Inter-stage memory
- **Location**: `main.py:456-464` (events rebuilt from frames), `tracker/pattern_detector_parallel.py:42,49,56,93-109,113` (`valid_events`, sampled copy, `sequence`, every `work_chunk`, `all_candidate_patterns`)
- **Status**: NEW
- **Description**: At the pattern-detection high-water mark the process holds, concurrently: the `frames` dict (largest structure), the `events` list rebuilt from it (`main.py:456-464`), `valid_events` (filtered copy), the sampled `valid_events` (another copy), `sequence` (tuple-of-pairs copy), every `work_chunk` each re-embedding the full `sequence`/`valid_events` (PERF-02), and `all_candidate_patterns` (each candidate copies `pattern` tuple + a `positions` list + an `events` slice). None of the prior structures is `del`'d before the detector runs. The multiplier vs. raw event count is roughly `frames + 3×events + (lengths×workers)×events`.
- **Evidence**: no `del frames` / `del events` between stages; `work_chunks` build at `:101-108`.
- **Impact**: Raises peak RSS on large files; bounded by the 15000-event sample so it does not OOM a common file → LOW. Cross-references PERF-02's per-chunk duplication as the dominant term.
- **Related**: PERF-02. `ProfilerRegistry.get_profiles()` returns `self._profiles.copy()` (`utils/profiling.py:106`) — fine, registry stays small; noted, not a finding.
- **Suggested Fix**: `del frames`/`del events` once consumed; ship the sequence to workers once (PERF-02 fix) so `work_chunks` carry only offsets.

### PERF-05: All intermediate pipeline JSON is written with `indent=2`
- **Severity**: MEDIUM
- **Dimension**: D5 — Serialization cost
- **Location**: `main.py:43` (parse), `:52` (map), `:59` (frames), `:312` (detect-patterns output)
- **Status**: NEW
- **Description**: `run_parse`, `run_map`, `run_frames`, and the `detect-patterns` writer all serialize with `json.dumps(..., indent=2)`. The frames artifact — `{channel: {frame_num: {note, volume, ...}}}` with tens of thousands of inner dicts — is pretty-printed with a newline and leading spaces per element. Versus compact `separators=(',',':')`, `indent=2` typically inflates output size 2–3x and proportionally increases write time and the downstream `read_text()`/`json.loads` parse time of the next stage. These are machine-only intermediates a human rarely opens. (The benchmark/report writers at `main.py:959`, `benchmarks/performance_suite.py:438` are human-facing reports — `indent=2` is fine there.)
- **Evidence**: four `write_text(json.dumps(..., indent=2))` call sites listed above.
- **Impact**: Larger temp files + slower write/read on every multi-step run; the full pipeline writes these to a `TemporaryDirectory` so the cost is per-run, not persisted. Correct output, just bloated/slow → MEDIUM.
- **Related**: PERF-04 (the frames structure is the memory high-water mark too).
- **Suggested Fix**: Use `json.dumps(data, separators=(',',':'))` for the parse/map/frames/detect-patterns intermediates; keep `indent=2` only on the human-read report writers.

### PERF-06: Benchmark harness measures the wrong modules and has no regression gate
- **Severity**: MEDIUM
- **Dimension**: D6 — Benchmark-harness validity
- **Location**: `benchmarks/performance_suite.py:18` (imports `tracker.parser`), `:21,:197-198` (`EnhancedPatternDetector`), `:152-160` (double `_end_profiling`); `benchmarks/run_benchmarks.py:69-77` (non-deterministic input search); `benchmark_results/benchmark_results.json` (checked-in run output, no comparison)
- **Status**: NEW
- **Description**: The harness does not exercise the production hot path:
  1. `from tracker.parser import parse_midi_to_frames` (`:18`) — the **slow full parser**, while the production `run_parse` uses `tracker/parser_fast.py` (`main.py:41`). The "parse" stage benchmark never measures the 120x fast path.
  2. `benchmark_pattern_detection` constructs `EnhancedPatternDetector` (`:197-198`, serial `tracker/pattern_detector.py`), while the production detect-patterns path uses `ParallelPatternDetector` (`main.py:476`). The benchmark measures the *fallback*, not the default.
  3. **Stale double-measure.** `benchmark_parse_stage` (and the other `benchmark_*_stage`) run the work inside `with self.profiler.profile("parse")` — whose `__exit__`/`profile` body already calls `_end_profiling(stage_name, True)` and **stops tracemalloc** (`:72`, `:102`). Then the method calls `self.profiler._end_profiling("parse", True)` a **second time** (`:160`) *after* the `with` block has exited, re-reading RSS post-work and hitting the `except` branch because tracemalloc is already stopped (`:99-104`). The returned `BenchmarkResult` therefore reports a duration measured from a stale `self._start_time` (still valid) but a `memory_peak_mb` that fell back to current RSS rather than the traced peak. Reported metrics do not correspond cleanly to the measured block.
  4. **No regression gate.** `benchmark_results/benchmark_results.json` is a checked-in *run output*, not a versioned baseline the harness diffs against. There is no "fail if slower than baseline by X%" — so the benchmark cannot catch the regression it exists to catch.
  5. **Non-deterministic inputs.** `run_baseline_benchmark` globs `test_data/`, `examples/`, `samples/`, `.` for `*.mid` and silently benchmarks whatever it finds (`run_benchmarks.py:69-77`), making results incomparable across machines/runs.
- **Evidence**: import at `:18`; detector at `:197`; the `with self.profiler.profile("parse"): result = parse_wrapper()` immediately followed by `return result, self.profiler._end_profiling("parse", True)` (`:157-160`).
- **Impact**: A regression in `parser_fast` or `ParallelPatternDetector` is invisible to the benchmark; the reported memory peaks are unreliable. A benchmark that measures the wrong code is worse than none → MEDIUM (highest-leverage despite severity).
- **Related**: PERF-07 (shared tracemalloc-stop bug), open #46/REG-06 (parallel detector untested).
- **Suggested Fix**: Import `parse_midi_to_frames` from `tracker.parser_fast` and use `ParallelPatternDetector` in `benchmark_pattern_detection`. Have `profile()` *return* its `BenchmarkResult` (via the context object) and delete the second `_end_profiling` call. Check in a committed baseline and add a percent-threshold comparison; benchmark a committed deterministic fixture set, not a glob.

### PERF-07: Shared global tracemalloc — nested profilers blind each other
- **Severity**: LOW
- **Dimension**: D7 — Profiling-utility correctness
- **Location**: `utils/profiling.py:171,195` (`profile_memory_usage`), `:285,299` (`PerformanceContext`), `:87-89` (`MemoryMonitor` cpu/sample), `benchmarks/performance_suite.py:82,102` (`PerformanceProfiler`)
- **Status**: NEW
- **Description**: Every profiler calls the **global** `tracemalloc.start()` and stops it in a `try/except: pass`. If a `@profile_memory_usage`-decorated function runs inside a `PerformanceContext` (or two `PerformanceProfiler.profile` blocks nest), the inner `tracemalloc.stop()` (`:195` / `:299`) tears down tracing for the still-running outer profiler, whose later `get_traced_memory()` then hits the bare `except` and reports current RSS instead of the traced peak. Secondary issues in the same module: `cpu_percent()` is sampled with no interval so the first call after process start returns `0.0` and deltas are unreliable (the SKILL's D7 concern; the benchmark suite computes `cpu_after - cpu_before` at `performance_suite.py:96` from two intervalless calls); and `MemoryMonitor._monitor_loop` swallows all exceptions with bare `except: break` (`:89-90`), so for work shorter than `interval_ms=100` no sample is taken and `stop_monitoring` returns `{"peak_mb": 0}` (`:71-72`) — `max(peak_traced, 0)` masks it, but a pure-`MemoryMonitor` caller would see a 0 peak.
- **Evidence**: three independent `tracemalloc.start()`/`stop()` pairs over one global; `process.cpu_percent()` called once at start with no `interval=`.
- **Impact**: Profiling metrics only — never affects generated ROMs. Misleading numbers, not a crash → LOW.
- **Related**: PERF-06 (the benchmark suite is the main consumer and double-stops tracemalloc).
- **Suggested Fix**: Guard `tracemalloc.start()` with `tracemalloc.is_tracing()` and only `stop()` if this profiler started it (reference-count or skip nested starts). Sample `cpu_percent()` with a small interval or document it as advisory.

### PERF-08: Tempo map rebuilt from scratch up to four times; events round-trip through frames
- **Severity**: LOW
- **Dimension**: D8 — Cross-stage redundant recomputation (folds the D1 analysis-variant redundancy)
- **Location**: `tracker/parser_fast.py:24-48` (build #1), `:103-125` (`parse_midi_to_frames_with_analysis` re-opens the file and rebuilds — comment at `:115` "this could be cached from first pass"); `main.py:453` (`EnhancedTempoMap(initial_tempo=500000)` fresh, default-tick — never given the real `ticks_per_beat`); `benchmarks/performance_suite.py:197`; events round-trip at `main.py:281-293` and `:456-464`
- **Status**: NEW
- **Description**: The tempo map computed at parse time is **not serialized into the parse JSON** (`parser_fast.py:85` returns `"metadata": {}`), so every downstream consumer rebuilds it:
  - `parse_midi_to_frames_with_analysis` re-opens the MIDI and rebuilds the tempo map after `parse_midi_to_frames` already built one (`:116-125`) — the inline comment admits it could be cached. This variant is opt-in, so the cost is bounded.
  - The detect-patterns stage constructs a fresh `EnhancedTempoMap(initial_tempo=500000)` (`main.py:453`) **with the default `ticks_per_beat=480`**, not the file's resolution — and then never actually uses it for timing (the detector only reads `note`/`volume`), so it is a wasted construction.
  Separately, events are derived into `frames` at the frames stage and then **re-extracted from `frames` back into an `events` list** for pattern detection (`main.py:456-464`, and again in `run_detect_patterns` at `:281-293`) — an events→frames→events round-trip.
- **Evidence**: `parse_midi_to_frames_with_analysis` rebuild loop at `:117-125`; `main.py:453` fresh tempo map; the events-rebuild loops cited.
- **Impact**: Wasted CPU, not incorrect output (the detector ignores tempo). LOW. The `EnhancedTempoMap` at `main.py:453` getting the wrong `ticks_per_beat` is harmless *only because* it is unused — a latent trap if a future change starts reading it.
- **Related**: PERF-01 (each rebuild repays the O(T) scan cost); open #33/F-14 (`SongBank` uses yet another parser — third tempo path).
- **Suggested Fix**: Thread the computed tempo data through the parse JSON contract so downstream stages deserialize rather than recompute; drop the unused `EnhancedTempoMap` at `main.py:453` or pass it real parameters.

---

## Dedup Notes

- No prior PERFORMANCE audit exists in `docs/audits/` (only MAPPERS, NES_HARDWARE, PIPELINE, REGRESSION dated 2026-06-28).
- Open issues touching adjacent code but **not** these performance angles: #46/REG-06 (parallel detector *test coverage*, not algorithm), #21 (shared large-file *policy*, the fix PERF-03 builds on), #33/F-14 (`SongBank` third parser — correctness drift, referenced by PERF-08). None duplicates a finding here; all marked NEW.
- The PIPELINE audit (F-04, F-09) covers the fallback-truncation *content-loss* angle; this report deliberately reports only the *performance* framing of sampling (PERF-03) and defers content-loss to `audit-patterns`.

## Next Step

```
/audit-publish docs/audits/AUDIT_PERFORMANCE_2026-06-29.md
```
