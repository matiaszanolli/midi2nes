# Performance Audit — MIDI2NES

- **Date**: 2026-07-06
- **Scope**: parser hot path, parallel pattern-detector scaling, large-file sampling,
  inter-stage memory, serialization cost, benchmark-harness validity, profiling
  utilities, cross-stage redundant recomputation — per
  `.claude/commands/audit-performance/SKILL.md`.
- **Method**: live source re-read at HEAD `8308a63`; severity per `_audit-severity.md`;
  dedup against the pre-fetched open-issue list (`/tmp/audit/issues.json`, 29 open) and
  every prior report in `docs/audits/`, in particular the 1-day-prior
  `docs/audits/AUDIT_PERFORMANCE_2026-07-05.md`.
- **Prompt-injection note**: no injected instructions were encountered in any tool
  result, file, or command output during this audit.

## What changed since the 2026-07-05 audit

The performance surface changed only in ways that **close or improve** prior findings —
no new regressions. Diffing the perf modules from the last audit's HEAD (`a7de0d4`) to
`8308a63`:

- **`benchmarks/performance_suite.py`** — `benchmark_pattern_detection` now extracts events
  via the shared `frames_to_events(frames_data)` (line 223, comment cites #261) instead of
  iterating the `frames` dict inline. This **fixes PERF-10** (the 2026-07-05 MEDIUM finding
  that the benchmark crashed with `AttributeError` on any drum-containing MIDI because it
  did not skip the `dpcm_sample_map` side table). The most-important benchmark stage is now
  measurable on the common percussion input.
- **`tracker/pattern_detector_parallel.py`** — per-chunk failure now recovers **in-process**
  via `_collect_length_candidates` and records a durable end-of-run warning naming the lost
  lengths (`#106`), plus `total_events` narrowed to the post-sampling analyzed count for
  `coverage_ratio` (`#257`) and a variation-summary shape aligned with the sequential
  detector (`#172`). The `#106` change specifically resolves the Dimension-2 asymmetry the
  SKILL flagged (a per-chunk drop that was a transient `pbar.write` with no counted/propagated
  warning) — it now retries serially and surfaces a persistent count.
- **`tracker/tempo_map.py`, `tracker/parser_fast.py`, `utils/profiling.py`** — unused-import
  cleanups only; no algorithmic change. The bisect tempo index, the `_tracemalloc_acquire`/
  `_release` reference counting, and the two-pass parse structure are all intact.
- **`tracker/pattern_detector.py`, `main.py`** — `#257` coverage-ratio fixes and unrelated
  non-perf work (config-path guard, mapper resolution, note-to-timer clamp). The O(n)
  `_collect_length_candidates` grouping, the config-overridable sampling caps
  (`get_pattern_detection_caps`), compact intermediate JSON, and the production
  `max_pattern_length=PATTERN_MAX_LENGTH` (12) call site are all unchanged and confirmed.

This cycle is therefore a **fix-verification pass with zero new findings**.

## Summary

| Severity | New this cycle | Open (carried) |
|----------|----------------|----------------|
| CRITICAL | 0 | 0 |
| HIGH     | 0 | 0 |
| MEDIUM   | 0 | 0 |
| LOW      | 0 | 2 |

**Total tracked findings: 2 — both pre-existing OPEN issues, both LOW.** No new defects.

Two prior findings remain open and re-verified in place:

- **PERF-04 (#115, LOW)** — inter-stage event-sequence duplication + events→frames→events
  round-trip; no `del` between stages. Unchanged.
- **PERF-11 (#262, LOW)** — the pattern-detection benchmark constructs
  `ParallelPatternDetector(tempo_map, min_pattern_length=3)` without `max_pattern_length`,
  inheriting the constructor default **32** vs production's **12**; and there is still no
  checked-in baseline / regression gate. Unchanged.

PERF-01/#113, PERF-02/#114, PERF-03/#219, PERF-05/#116, PERF-06/#117, PERF-07/#118,
PERF-08/#119, PERF-09/#218 remain **confirmed fixed**. The prior-cycle MEDIUM **PERF-10 is
now fixed** via the `frames_to_events` rewire (#261) and is not in the open list.

### Highest-leverage items

1. **PERF-11 (#262, LOW, still open)** — benchmark param drift (`max_pattern_length` 32 vs
   12) + no regression baseline. The one remaining fidelity gap in the harness that this
   audit exists to protect: without a versioned baseline and a "fail if slower than X%"
   comparison, the harness cannot automatically catch a detector regression even when it
   measures the right modules.
2. **PERF-04 (#115, LOW, still open)** — parsed→mapped→frames→events held simultaneously; the
   memory high-water mark on a long song. No streaming/`del`.

---

## Findings

_No NEW findings this cycle._ The two items below are pre-existing OPEN issues, re-verified
against the live code per the dedup protocol and carried forward (not re-filed).

### PERF-11: Pattern-detection benchmark uses `max_pattern_length=32` (default) vs production's 12; no regression baseline
- **Severity**: LOW
- **Dimension**: D6 — Benchmark-harness validity
- **Location**: `benchmarks/performance_suite.py:217`
  (`ParallelPatternDetector(tempo_map, min_pattern_length=3)`);
  `tracker/pattern_detector_parallel.py:17` (`max_pattern_length=32` default);
  `main.py:36-37` (`PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12`), `main.py:829`
  (production passes `max_pattern_length=PATTERN_MAX_LENGTH`);
  `benchmarks/run_benchmarks.py:59-168` (no baseline comparison)
- **Status**: Existing: #262
- **Description**: The #117 fix switched the benchmark to the production
  `ParallelPatternDetector` but did not pass production **parameters**. The benchmark omits
  `max_pattern_length`, defaulting to 32; the full pipeline builds the detector with
  `max_pattern_length=PATTERN_MAX_LENGTH` (=12, `main.py:829`) and the sequential path with
  the same 12 (`main.py:622-623`). Work-chunk count is `max_pattern_length -
  min_pattern_length + 1` (`pattern_detector_parallel.py:117-121`), so the benchmark
  exercises up to **30** pattern lengths where production runs **10** — inflating the
  measured pattern-detection time relative to the real path. Separately,
  `benchmarks/run_benchmarks.py` still has no checked-in baseline or "fail if slower than
  X%" gate (`run_baseline_benchmark` only establishes numbers; there is no compare step),
  and it globs `["test_data","examples","samples","."]` for whatever `*.mid` it finds
  (`:70-77`) — non-deterministic inputs make cross-run comparison meaningless anyway.
- **Evidence**: `benchmarks/performance_suite.py:217` passes only `min_pattern_length=3`;
  `tracker/pattern_detector_parallel.py:17` signature default `max_pattern_length=32`;
  `main.py:829` passes `max_pattern_length=PATTERN_MAX_LENGTH`. No `baseline`/`compare`
  logic exists in `benchmarks/run_benchmarks.py`.
- **Impact**: The reported pattern-detection `duration_ms` is not comparable to what
  production actually spends, and without a baseline comparison there is no automated
  regression signal. Cosmetic / measurement-fidelity, dev-tooling only → LOW.
- **Related**: Residual of the PERF-06/#117 fix; adjacent to the now-fixed PERF-10 (#261,
  same method).
- **Suggested Fix**: Pass `max_pattern_length=PATTERN_MAX_LENGTH` in
  `benchmark_pattern_detection` (import the constant from `main.py`/a shared module).
  Longer term, check a versioned baseline into `benchmark_results/` and add a comparison
  step that fails on a configurable regression threshold.

### PERF-04: Pattern-detection stage holds many full copies of the event sequence simultaneously
- **Severity**: LOW
- **Dimension**: D4 — Inter-stage memory
- **Location**: `main.py` `run_parse`/`run_map`/`run_frames` (whole-dict load→dump per
  stage); events re-extracted from `frames` at `main.py:628` (`run_detect_patterns`) and
  `main.py:815` (`run_full_pipeline`) via `frames_to_events`.
- **Status**: Existing: #115
- **Description**: Every pipeline stage reads its input fully into memory and writes its
  output fully; parsed events → mapped events → frames dict are three full in-memory copies
  of roughly the same data (the frames structure is the largest), and no stage `del`s the
  prior structure while building the next. The pattern-detection stage additionally
  re-extracts an `events` list out of the `frames` dict (`frames_to_events`), so
  parsed→mapped→frames→events can be live simultaneously — the memory high-water mark on a
  long song.
- **Evidence**: `grep -n "del frames\|del events\|del mapped\|del parsed" main.py` → no
  matches (confirmed at HEAD `8308a63`). The events→frames→events round-trip stands; the
  shared `frames_to_events` extractor de-duplicated the flattening code but did not remove
  the recompute or the duplication.
- **Impact**: Bounded, linear-in-song-length memory duplication — a large multi-minute MIDI
  holds ~3–4 copies of the event/frame data at once. No correctness impact; a realistic
  worst case is elevated RSS, not OOM on common inputs → LOW.
- **Related**: Cross-stage recompute half is the Dimension-8 events→frames→events round-trip
  (also #261 for the shared extractor).
- **Suggested Fix**: `del` the prior stage's structure once the next is built, or stream
  stages that don't need the whole dict resident. Threading tempo/events forward through the
  parse JSON would also remove the frames→events re-extraction.

---

## Re-verification of prior findings (no new report entry)

- **PERF-10 (prior MEDIUM, 2026-07-05) — NOW FIXED.** `benchmarks/performance_suite.py:223`
  uses `events = frames_to_events(frames_data)` (comment cites #261), which skips the
  `dpcm_sample_map` side table exactly as the two production sites do. The
  `AttributeError` on drum MIDIs is gone; not present in the open-issue list.
- **PERF-01 / #113 (CLOSED)** — `tracker/tempo_map.py` bisect index intact (only an unused
  `Tuple` import removed this cycle). Confirmed fixed.
- **PERF-02 / #114 (CLOSED)** — `_collect_length_candidates` O(n) hash-grouping + one-shot
  pool IPC via `initializer=_init_pattern_worker, initargs=(sequence, valid_events)`
  (`pattern_detector_parallel.py:146-150`) intact. Confirmed fixed.
- **PERF-03 / #219 (FIXED)** — `get_pattern_detection_caps` resolves
  `processing.pattern_detection.max_events`/`max_pattern_events` from config (`main.py:39-61`),
  wired at `:614`/`:824`. `LARGE_FILE_THRESHOLD=10000` (`main.py:818`) still advisory-only.
- **PERF-05 / #116 (FIXED)** — compact intermediate JSON: `main.py:101,111,120,650` all
  `json.dumps(..., separators=(',', ':'))`. Only the benchmark report keeps `indent=2`
  (correct for a human-read report).
- **PERF-06 / #117 (FIXED)** — benchmark imports `tracker.parser_fast` and
  `ParallelPatternDetector`; `profile()` runs `_end_profiling` once via `ProfileHandle`.
  Residual params carried as PERF-11.
- **PERF-07 / #118 (FIXED)** — reference-counted `_tracemalloc_acquire`/`_release` under a
  lock, used by both profilers (only unused imports trimmed this cycle).
- **PERF-08 / #119 (FIXED)** — `EnhancedPatternDetector` built with `analyze_tempo=False`
  on both fallback sites (`main.py:622-623`, `:837`). Dead per-pattern tempo analysis
  removed; O(1) redundant `EnhancedTempoMap` construction residual only.
- **PERF-09 / #218 (FIXED)** — single-chunk serial short-circuit
  (`pattern_detector_parallel.py:130-132`) and `pool_workers = min(self.max_workers,
  len(work_chunks))` (`:139`) intact. No over-spawn.
- **SKILL Dimension-2 asymmetry (per-chunk drop lacked a counted warning) — IMPROVED this
  cycle.** Chunk failures now retry serially via `_collect_length_candidates` and, if still
  failing, record `failed_lengths` surfaced as a persistent end-of-run warning
  (`pattern_detector_parallel.py:156-192`, #106). No longer a bare transient `pbar.write`.

## Dedup Notes

- Dedup ran against `/tmp/audit/issues.json` (29 OPEN; `gh` not re-invoked per instructions)
  plus every `docs/audits/AUDIT_PERFORMANCE_*.md` and the 2026-07-05/07-06 reports.
- Open PERF-context issues: `#115` (PERF-04), `#262` (PERF-11), and `#223` (SAFE-12, bare
  `except` in benchmark/debug tooling — a safety concern, out of this audit's scope).
- PERF-10 is absent from the open list and verified fixed in code — not re-reported.
- No new performance defect was found: every module change since the last audit either
  closed a prior finding or was a non-perf/import cleanup, re-verified line-by-line.
- Prompt-injection check: none observed in any tool output, file content, or issue data.

## Next Step

```
/audit-publish docs/audits/AUDIT_PERFORMANCE_2026-07-06.md
```
