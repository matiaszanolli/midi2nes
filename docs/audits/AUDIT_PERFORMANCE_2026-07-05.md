# Performance Audit — MIDI2NES

- **Date**: 2026-07-05
- **Scope**: parse hot path, parallel pattern detector scaling, large-file sampling,
  inter-stage memory, serialization cost, benchmark-harness validity, profiling
  utilities, cross-stage redundant recomputation — per
  `.claude/commands/audit-performance/SKILL.md`.
- **Method**: live source re-read at HEAD `a7de0d4`; severity per `_audit-severity.md`;
  dedup against the pre-fetched open-issue list (`/tmp/audit/issues.json`, 36 open) and
  every prior report in `docs/audits/`, in particular
  `docs/audits/AUDIT_PERFORMANCE_2026-07-03.md` (2 days prior).
- **Prompt-injection note**: no injected instructions were encountered in any tool
  result, file, or command output during this audit.

## What changed since the 2026-07-03 audit

Two commits landed on this audit's surface and closed most of the previously-open PERF
findings — this cycle is largely a **fix-verification** pass:

- **`91bcead`** (#116/#117/#118/#119) — "compact intermediate JSON, correct benchmark
  modules, nesting-safe tracemalloc, skip dead tempo analysis". Addresses PERF-05
  (indent=2 → compact), PERF-06 (benchmark now imports `parser_fast` +
  `ParallelPatternDetector`, `_end_profiling` runs once via a `ProfileHandle`), PERF-07
  (reference-counted `_tracemalloc_acquire`/`_release`), and PERF-08's dead-analysis half
  (`analyze_tempo=False`).
- **`e8b39b2`** (#218/#219) — "cap parallel pattern-detector worker pool and add
  config-driven sampling caps". Addresses PERF-09 (`pool_workers = min(max_workers,
  len(work_chunks))` + single-chunk serial guard) and PERF-03 (`get_pattern_detection_caps`
  reads `processing.pattern_detection.max_events`/`max_pattern_events` from config).

All prior fixes were re-verified in place against current code (see "Re-verification"
below). The remaining live surface (`tempo_map.py` bisect index, `_collect_length_candidates`
O(n) grouping, the three sampling caps) is unchanged and confirmed correct.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 new |
| LOW      | 1 new |
| **NEW this cycle** | **2** |

One prior finding remains open and re-verified: **PERF-04 (#115, LOW)** — inter-stage
event-sequence duplication + events→frames→events round-trip, still present (no `del`
between stages). PERF-01/#113, PERF-02/#114, PERF-03/#219, PERF-05/#116, PERF-06/#117,
PERF-07/#118, PERF-08/#119, PERF-09/#218 are all **confirmed fixed**.

### Highest-leverage items this cycle

1. **PERF-10 (NEW, MEDIUM)** — the just-fixed pattern-detection benchmark
   (`benchmark_pattern_detection`, part of the #117 fix) **crashes on any
   drum-containing MIDI**: it iterates every key of the `frames` dict without skipping
   the `dpcm_sample_map` side table (a `str→int` map, not a per-frame channel), so
   `frame_data.get('note')` runs on an `int` → `AttributeError`. Production stages got
   the `dpcm_sample_map` skip guard in #200; the benchmark did not. The exact stage the
   audit exists to protect from regression is therefore un-measurable on the common
   (percussion) input.
2. **PERF-11 (NEW, LOW)** — the same benchmark still doesn't match production
   *parameters*: it constructs `ParallelPatternDetector(tempo_map, min_pattern_length=3)`
   leaving `max_pattern_length` at the constructor default **32**, whereas the production
   pipeline passes `PATTERN_MAX_LENGTH=12`. The benchmark measures ~30 pattern-length
   work-chunks vs production's 10, and there is still no checked-in baseline or
   regression gate.
3. **PERF-04 (#115, still open, LOW)** — no stage `del`s the prior stage's structure;
   parsed→mapped→frames→events are held simultaneously. Unchanged.

---

## Findings

### PERF-10: Pattern-detection benchmark crashes on drum MIDIs — `dpcm_sample_map` not skipped in frames iteration
- **Severity**: MEDIUM
- **Dimension**: D6 — Benchmark-harness validity (does it measure the real path?)
- **Location**: `benchmarks/performance_suite.py:220-229` (`benchmark_pattern_detection`'s
  `for channel_name, channel_frames in frames_data.items(): for frame_num, frame_data in
  channel_frames.items(): ... frame_data.get('note', 0)`)
- **Status**: NEW
- **Description**: `NESEmulatorCore.process_all_tracks` injects a **non-channel** key
  `dpcm_sample_map` into the returned `frames` dict whenever a song references any DPCM
  drum samples (`nes/emulator_core.py:232-235`): its value is `{str(dense_id): raw_id}`
  — a flat `str→int` map, not the `{frame_num: {note, volume, ...}}` shape every real
  channel has. The two production consumers of this dict explicitly skip it
  (`main.py:520-521` in `run_detect_patterns`, `main.py:721-722` in `run_full_pipeline`:
  `if channel_name == 'dpcm_sample_map': continue`). The benchmark's pattern-detection
  stage — introduced/rewired by the #117 fix to finally use the real
  `ParallelPatternDetector` — has **no such guard**. On a `dpcm_sample_map` entry,
  `channel_frames` is `{str(dense_id): raw_id}`, so the inner loop binds `frame_data` to
  an `int` (`raw_id`) and calls `int.get('note', 0)` → `AttributeError: 'int' object has
  no attribute 'get'`.
- **Evidence**: Emission is conditional on referenced drum ids:
  `nes/emulator_core.py:232` `if referenced_ids: processed['dpcm_sample_map'] = {str(dense_id): raw_id ...}`.
  The benchmark iteration at `benchmarks/performance_suite.py:222-228` lacks the
  `if channel_name == 'dpcm_sample_map': continue` line both production sites carry. The
  profile context manager re-raises (`performance_suite.py:91-94` `except Exception: ...
  raise`), and `run_full_pipeline` catches it at `:325-337`, recording a
  `stage="pipeline_error"` result — so **both the pattern-detection and export stages are
  lost** for that file, and only parse/map/frames are timed.
- **Impact**: Dev-tooling only — no generated ROM or user output is affected. But the
  benchmark harness is the audit's regression backstop, and this makes its most
  important stage (pattern detection — the slowest, and the one carrying the #114/#218
  parallelism fixes) **un-measurable on the common percussion-containing MIDI**, silently
  degrading to a caught "Pipeline failed" line. A future regression in the parallel
  detector would go uncaught on exactly the inputs most likely to exercise it. MEDIUM per
  the SKILL's Dimension-6 framing ("a benchmark that measures the wrong code is worse than
  none") — bounded to dev tooling, so not HIGH.
- **Related**: Root cause shared with #200/D-14 (the `dpcm_sample_map` side table);
  production stages were guarded there, the benchmark was missed. Adjacent to PERF-11
  (same method, parameter-fidelity gap) and PERF-06/#117 (the fix that wired this stage
  to the real detector).
- **Suggested Fix**: Add `if channel_name == 'dpcm_sample_map': continue` inside the
  channel loop in `benchmark_pattern_detection` (mirror `main.py:520-521`). Consider a
  shared `frames_to_events(frames)` helper so all three call sites cannot drift again.

### PERF-11: Pattern-detection benchmark uses `max_pattern_length=32` (default) vs production's 12; still no regression baseline
- **Severity**: LOW
- **Dimension**: D6 — Benchmark-harness validity
- **Location**: `benchmarks/performance_suite.py:218`
  (`ParallelPatternDetector(tempo_map, min_pattern_length=3)`),
  `tracker/pattern_detector_parallel.py:17` (`max_pattern_length=32` default),
  `main.py:35-36` (`PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12`),
  `benchmarks/run_benchmarks.py:60-92` (no baseline comparison)
- **Status**: NEW
- **Description**: The #117 fix correctly switched the benchmark to the production
  `ParallelPatternDetector`, but did not pass the production **parameters**. The benchmark
  omits `max_pattern_length`, so it defaults to `32`, whereas the full pipeline and the
  `detect-patterns` subcommand both construct the detector with `max_pattern_length=PATTERN_MAX_LENGTH`
  (`=12`, `main.py:743`, and the sequential path at `:510-512`/`:751`). Work-chunk count
  is `max_pattern_length - min_pattern_length + 1` (`pattern_detector_parallel.py:112-116`),
  so the benchmark exercises up to **30** pattern lengths where production exercises
  **10** — inflating the measured pattern-detection time relative to the real path and
  measuring a work profile production never runs. Separately, `run_benchmarks.py` still
  has no checked-in baseline or "fail if slower than X%" gate (the glob at `:35` is now
  `sorted()` for intra-dir determinism, but still searches `["test_data","examples","samples","."]`
  and runs on whatever `*.mid` it happens to find), so even a correct measurement cannot
  catch a regression automatically.
- **Evidence**: `benchmarks/performance_suite.py:218` passes only `min_pattern_length=3`;
  `tracker/pattern_detector_parallel.py:17` signature `max_pattern_length=32`;
  `main.py:743` passes `max_pattern_length=PATTERN_MAX_LENGTH`. No `baseline`/`compare`
  logic exists in `benchmarks/run_benchmarks.py` (grep: only `run_baseline_benchmark`
  which *establishes* numbers, never compares).
- **Impact**: The reported pattern-detection `duration_ms` is not comparable to what the
  production pipeline actually spends, and without a baseline comparison there is no
  automated regression signal. Cosmetic/measurement-fidelity, dev-tooling only → LOW.
- **Related**: Same method as PERF-10; both are residuals of the PERF-06/#117 fix.
- **Suggested Fix**: Pass `max_pattern_length=PATTERN_MAX_LENGTH` (import the constant, or
  mirror 12) in `benchmark_pattern_detection`. Longer term, check a versioned baseline
  into `benchmark_results/` and add a comparison step that fails on a configurable
  regression threshold.

---

## Re-verification of prior findings (fixed or still-open — no new report entry)

### PERF-01 / #113 (CLOSED) — tempo lookups O(log T) via bisect index — confirmed fixed
`tracker/tempo_map.py:6` `import bisect`; `:113-114`/`:127` the `_tempo_index` cache is
set to `None` on mutation; `:129-147` `_build_tempo_index`; `:150-155` `_get_tempo_index`
lazily rebuilds. Bisect index intact, invalidated on mutation. **Correctly closed.**

### PERF-02 / #114 (CLOSED) — O(n·L) hash grouping + one-shot pool IPC — confirmed fixed
`tracker/pattern_detector_parallel.py:268-335` (`_collect_length_candidates`) is the
single linear bucket-by-window pass + greedy non-overlapping selection, used by both the
worker (`:338-346`) and serial fallback (`:174-189`). Sequence/events shipped once via
`ProcessPoolExecutor(..., initializer=_init_pattern_worker, initargs=(sequence, valid_events))`
(`:140-144`) into module globals (`:256-265`). **Correctly closed.**

### PERF-03 / #219 (FIXED) — sampling caps now config-overridable
`main.py:38-54` `get_pattern_detection_caps` resolves `max_events`/`max_pattern_events`
from `processing.pattern_detection.*`; wired at `main.py:502` (subcommand) and `:738`
(pipeline). Config schema, defaults, and validation present:
`config/config_manager.py:21-22,150-151,274-280`, `config/default_config.yaml:14-15`.
`ParallelPatternDetector.__init__` now takes `max_pattern_events` (`pattern_detector_parallel.py:18,25,61`).
The advisory-only `LARGE_FILE_THRESHOLD=10000` (`main.py:732-735`) still only prints —
confirmed still advisory. The three constants are no longer un-overridable. **Fixed.**

### PERF-04 / #115 (OPEN) — inter-stage memory duplication + events round-trip
`grep -n "del frames\|del events\|del mapped\|del midi_data" main.py` → **no matches**;
parsed→mapped→frames→events are held concurrently, and events are re-extracted from the
`frames` dict at `main.py:514-528` (subcommand) and `:716-729` (pipeline). Unchanged,
still accurate. Existing: **#115**, LOW.

### PERF-05 / #116 (FIXED) — compact intermediate JSON
`main.py:93,103,112,553` all now `json.dumps(..., separators=(',', ':'))` (parse/map/
frames/detect-patterns writers). Only `main.py:1321` (benchmark report) keeps `indent=2`,
which is correct for a human-read report. **Fixed.**

### PERF-06 / #117 (FIXED, with residuals) — benchmark measures the real modules
`benchmarks/performance_suite.py:18` imports `tracker.parser_fast`; `:21`/`:218` use
`ParallelPatternDetector`; `:76-94` the `profile` context manager runs `_end_profiling`
exactly once via a `ProfileHandle` (`:89`). The double-call is gone. Residual parameter
and baseline gaps carried forward as **PERF-11** above.

### PERF-07 / #118 (FIXED, with residual) — nesting-safe tracemalloc
`utils/profiling.py:25-45` reference-counted `_tracemalloc_acquire`/`_release` under a
`threading.Lock`, used by both `profile_memory_usage` (`:209,242`) and `PerformanceContext`
(`:330,347`) and the benchmark suite (`:99,122`). `get_traced_memory` now guards
`except RuntimeError` (`:233,344`) instead of a bare except. Residuals: `cpu_percent()`
still called with no `interval=` (`:203,227`) but now documented as advisory (`:198`);
`MemoryMonitor._monitor_loop` bare `except: break` (`:122`) remains and is tracked
separately as **TD-10/#135**. Core nesting bug **fixed.**

### PERF-08 / #119 (FIXED, dead-analysis half) — skip inert per-pattern tempo analysis
`EnhancedPatternDetector` is now constructed with `analyze_tempo=False` on both fallback
sites (`main.py:512`, `:751`), so the discarded constant-tempo per-pattern analysis no
longer runs. Residual (unchanged, trivial cost): a fresh `EnhancedTempoMap(initial_tempo=500000)`
is still constructed at `main.py:509` and `:714`, and `parse_midi_to_frames_with_analysis`
still re-opens the file to rebuild the tempo map (`tracker/parser_fast.py:163,192`
"could be cached from first pass" — #221 guarded the reopen for *safety* but did not
eliminate it; that path is opt-in via `--with-analysis`, not on the default pipeline).
The dead-work half is **fixed**; the wasted-construction residual is O(1) and not
separately worth a finding.

### PERF-09 / #218 (FIXED) — pool never over-spawns; single-chunk serial guard
`tracker/pattern_detector_parallel.py:125-127` short-circuits to `_detect_patterns_serial`
when there is exactly one work chunk; `:134` `pool_workers = min(self.max_workers,
len(work_chunks))` caps the executor at the chunk count. The old `cpu_count()-1`-sized
over-spawn is gone. **Fixed.**

---

## Dedup Notes

- Dedup ran against `/tmp/audit/issues.json` (36 OPEN issues; per instructions `gh` was
  not re-invoked) plus every `docs/audits/AUDIT_PERFORMANCE_*.md` and the 2026-07-05
  DPCM/pipeline reports.
- Only one PERF issue is open (`#115`/PERF-04); #113/#114/#116/#117/#118/#119 are absent
  from the open list (closed), consistent with commits `91bcead`/`e8b39b2` above — each
  verified fixed in code rather than assumed.
- PERF-10 and PERF-11 are genuinely new: no open issue mentions `benchmark`, `dpcm_sample_map`,
  or `max_pattern_length` in a performance context (the one `benchmark` hit, #223/SAFE-12,
  is about bare `except` in tooling — a different defect). No prior audit under
  `docs/audits/` covers the benchmark `dpcm_sample_map` crash (the two 2026-07-05 reports
  that mention `dpcm_sample_map` do so about production stages, not the benchmark).
- Prompt-injection check: none observed in any tool output, file content, or issue data.

## Next Step

```
/audit-publish docs/audits/AUDIT_PERFORMANCE_2026-07-05.md
```
