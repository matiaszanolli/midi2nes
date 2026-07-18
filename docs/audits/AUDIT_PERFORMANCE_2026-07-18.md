# Performance Audit — MIDI2NES

- **Date**: 2026-07-18
- **Scope**: parser hot path, parallel pattern-detector scaling, large-file sampling,
  inter-stage memory, serialization cost, benchmark-harness validity, profiling
  utilities, cross-stage redundant recomputation — per
  `.claude/commands/audit-performance/SKILL.md`.
- **Method**: live source re-read at HEAD `b562e1d`; severity per `_audit-severity.md`;
  dedup against the pre-fetched open-issue list (`/tmp/audit/issues.json`, 27 open) and
  every prior report in `docs/audits/`, in particular the 12-day-prior
  `docs/audits/AUDIT_PERFORMANCE_2026-07-06.md`.
- **Prompt-injection note**: no injected instructions were encountered in any tool
  result, file, or command output during this audit.

## What changed since the 2026-07-06 audit

None of the changes since `8308a63` (last perf-audit HEAD) touch the performance-critical
modules this SKILL targets. `git diff --stat 8308a63..HEAD -- tracker/ benchmarks/
utils/profiling.py main.py nes/emulator_core.py` shows only four files, all functional
fixes for *other* domains:

- **`tracker/parser_fast.py`** — extracted `_build_tempo_map(mid, config)` as a shared
  helper used by both `parse_midi_to_frames` and `parse_midi_to_frames_with_analysis`
  (#259/#260, tempo-map-unification fix, not a performance change). The **structure is
  identical**: still exactly two passes over `mid.tracks` in the default parser (one via
  `_build_tempo_map`, one for notes), and the analysis variant still re-opens the file
  and rebuilds the tempo map from scratch (the "could be optimized with caching" comment
  is unchanged — Dimension 1's LOW-grade redundancy still stands, just DRY'd up rather
  than duplicated). No new pass, no new per-event scan.
- **`tracker/tempo_map.py`** — docstring-only additions on `_smooth_tempo_transitions`
  and `optimize_tempo_changes` (#97, tempo-correctness audit) documenting that neither
  is wired into the live pipeline. The bisect tempo index (`_build_tempo_index`) that
  Dimension 1 depends on is untouched.
- **`tracker/track_mapper.py`** — added `_deterministic_arp_order` (#92, seeded RNG for
  reproducible arpeggio order) replacing `random.sample` in the legacy-mode "random"
  arpeggio pattern. This runs once per chord in `apply_arpeggio_pattern`, is O(len(notes))
  same as before, and only affects `track_mapper.py`'s legacy (non-`--arranger`) path —
  not a hot loop, no algorithmic change.
- **`main.py`** — mapper-recovery-from-`nes.cfg` fix for `run_compile` (#297) and a
  documentation comment on the pattern-detection stage's analysis-only `tempo_map`
  construction (#98). Neither changes control flow, loop structure, or allocation
  pattern in the parse/map/frames/detect-patterns/export stages this SKILL audits.

`tracker/pattern_detector_parallel.py`, `tracker/pattern_detector.py`,
`benchmarks/performance_suite.py`, `benchmarks/run_benchmarks.py`, and
`utils/profiling.py` — **zero diff** since the last perf audit. Re-read each in full
regardless (per the skeptical checklist) rather than trusting the diff alone; all
previously-confirmed-fixed behavior (bisect tempo index, O(n) `_collect_length_candidates`
grouping, one-shot pool IPC via `initializer`, single-chunk serial short-circuit, compact
intermediate JSON, reference-counted tracemalloc acquire/release) is unchanged.

## Summary

| Severity | New this cycle | Open (carried) |
|----------|-----------------|----------------|
| CRITICAL | 0 | 0 |
| HIGH     | 0 | 0 |
| MEDIUM   | 0 | 0 |
| LOW      | 0 | 2 |

**Total tracked findings: 2 — both pre-existing OPEN issues, both LOW. No new defects.**

This is the second consecutive fix-verification pass with zero new findings (the
2026-07-06 audit was also zero-new). The two carried items are unchanged in both
location and substance:

- **PERF-04 (#115, LOW)** — inter-stage event-sequence duplication + events→frames→events
  round-trip; no `del` between stages.
- **PERF-11 (#262, LOW)** — the pattern-detection benchmark still constructs
  `ParallelPatternDetector(tempo_map, min_pattern_length=3)` without `max_pattern_length`,
  still inheriting the constructor default **32** vs production's **12**; still no
  checked-in baseline / regression gate.

PERF-01/#113, PERF-02/#114, PERF-03/#219, PERF-05/#116, PERF-06/#117, PERF-07/#118,
PERF-08/#119, PERF-09/#218, PERF-10/#261 remain **confirmed fixed**, re-verified against
the current HEAD (details below), not merely carried over from the last report's
conclusion.

### Highest-leverage items (unchanged from last cycle)

1. **PERF-11 (#262, LOW, still open)** — benchmark param drift (`max_pattern_length` 32 vs
   12) + no regression baseline. Still the one gap that keeps the harness from catching a
   detector regression even though it now measures the right modules.
2. **PERF-04 (#115, LOW, still open)** — parsed→mapped→frames→events held simultaneously;
   the memory high-water mark on a long song. No streaming/`del`.
3. Nothing else rises above LOW. The compact-JSON win (PERF-05), the O(n) detector core
   (PERF-02), and the tracemalloc-nesting fix (PERF-07) are all intact and re-verified
   line-by-line this cycle.

---

## Findings

_No NEW findings this cycle._ The two items below are pre-existing OPEN issues,
re-verified against the live code (HEAD `b562e1d`) per the dedup protocol and carried
forward (not re-filed).

### PERF-11: Pattern-detection benchmark uses `max_pattern_length=32` (default) vs production's 12; no regression baseline
- **Severity**: LOW
- **Dimension**: D6 — Benchmark-harness validity
- **Location**: `benchmarks/performance_suite.py:217`
  (`ParallelPatternDetector(tempo_map, min_pattern_length=3)`);
  `tracker/pattern_detector_parallel.py:17` (`max_pattern_length=32` default);
  `main.py:36-37` (`PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12` — confirmed present
  at current line numbers), `main.py:862` (production passes
  `max_pattern_length=PATTERN_MAX_LENGTH`); `benchmarks/run_benchmarks.py:59-77`
  (no baseline comparison)
- **Status**: Existing: #262
- **Description**: Unchanged since the 2026-07-06 audit. The benchmark omits
  `max_pattern_length`, defaulting to 32; the full pipeline builds the detector with
  `max_pattern_length=PATTERN_MAX_LENGTH` (=12) at both `main.py:862` (parallel) and
  `main.py:870` (sequential fallback). Work-chunk count is `max_pattern_length -
  min_pattern_length + 1` (`pattern_detector_parallel.py:117-121`), so the benchmark
  still exercises up to **30** pattern lengths where production runs **10**. Separately,
  `benchmarks/run_benchmarks.py` still has no checked-in baseline or "fail if slower than
  X%" gate — `run_baseline_benchmark` only logs current-run numbers, no comparison
  exists anywhere in the file.
- **Evidence**: `grep -n "min_pattern_length\|max_pattern_length"
  benchmarks/performance_suite.py tracker/pattern_detector_parallel.py main.py` confirms
  the benchmark call site still passes only `min_pattern_length=3` while both production
  call sites (`main.py:862`, `:870`) pass `PATTERN_MAX_LENGTH` explicitly.
- **Impact**: The reported pattern-detection `duration_ms` is not comparable to what
  production actually spends, and without a baseline comparison there is no automated
  regression signal. Cosmetic / measurement-fidelity, dev-tooling only → LOW.
- **Related**: Residual of the PERF-06/#117 fix; adjacent to the now-fixed PERF-10 (#261).
- **Suggested Fix**: Pass `max_pattern_length=PATTERN_MAX_LENGTH` in
  `benchmark_pattern_detection` (import the constant from `main.py`/a shared module).
  Longer term, check a versioned baseline into `benchmark_results/` and add a comparison
  step that fails on a configurable regression threshold.

### PERF-04: Pattern-detection stage holds many full copies of the event sequence simultaneously
- **Severity**: LOW
- **Dimension**: D4 — Inter-stage memory
- **Location**: `main.py` `run_parse`/`run_map`/`run_frames` (whole-dict load→dump per
  stage); events re-extracted from `frames` at `main.py:653` (`run_detect_patterns`) and
  `main.py:848` (`run_full_pipeline`) via `frames_to_events`.
- **Status**: Existing: #115
- **Description**: Unchanged since the 2026-07-06 audit. Every pipeline stage reads its
  input fully into memory and writes its output fully; parsed events → mapped events →
  frames dict are three full in-memory copies of roughly the same data, and no stage
  `del`s the prior structure while building the next. The pattern-detection stage
  additionally re-extracts an `events` list out of the `frames` dict (`frames_to_events`),
  so parsed→mapped→frames→events can be live simultaneously — the memory high-water mark
  on a long song.
- **Evidence**: `grep -n "del frames\|del events\|del mapped\|del parsed" main.py` → no
  matches (confirmed at HEAD `b562e1d`). `frames_to_events` call sites confirmed at
  `main.py:653` and `main.py:848`, both still re-deriving events from the already-built
  `frames` dict rather than reusing anything carried forward from the parse stage.
- **Impact**: Bounded, linear-in-song-length memory duplication — a large multi-minute
  MIDI holds ~3–4 copies of the event/frame data at once. No correctness impact; a
  realistic worst case is elevated RSS, not OOM on common inputs → LOW.
- **Related**: Cross-stage recompute half is the Dimension-8 events→frames→events
  round-trip (shared `frames_to_events` extractor, #261, de-duplicated the flattening
  code but did not remove the recompute).
- **Suggested Fix**: `del` the prior stage's structure once the next is built, or stream
  stages that don't need the whole dict resident. Threading tempo/events forward through
  the parse JSON would also remove the frames→events re-extraction.

---

## Re-verification of prior findings (no new report entry)

- **PERF-01 / #113 (CLOSED)** — `tracker/tempo_map.py` bisect index (`_build_tempo_index`)
  intact; only docstring additions this cycle (#97). Confirmed fixed.
- **PERF-02 / #114 (CLOSED)** — `_collect_length_candidates` O(n) hash-grouping
  (`tracker/pattern_detector_parallel.py:196-220`) + one-shot pool IPC via
  `initializer=_init_pattern_worker, initargs=(sequence, valid_events)` (`:146-150`)
  intact, byte-for-byte unchanged from last cycle. Confirmed fixed.
- **PERF-03 / #219 (FIXED)** — `get_pattern_detection_caps` still resolves
  `processing.pattern_detection.max_events`/`max_pattern_events` from config
  (`main.py:39-61`), wired at `run_detect_patterns`/`run_full_pipeline`.
  `LARGE_FILE_THRESHOLD=10000` (`main.py:851`) still advisory-only (prints a
  `--no-patterns` hint, does not change behavior).
- **PERF-05 / #116 (FIXED)** — compact intermediate JSON confirmed at
  `main.py:101,111,120,675` (`json.dumps(..., separators=(',', ':'))`). Only report
  outputs (`benchmarks/performance_suite.py:449`, `main.py:1475` for
  `benchmark_results.json`) keep `indent=2` — correct, both are human-read reports, not
  hot intermediates.
- **PERF-06 / #117 (FIXED)** — benchmark still imports `tracker.parser_fast` and
  `ParallelPatternDetector` (the same production modules); `profile()` still runs
  `_end_profiling` exactly once via `ProfileHandle`. Residual param-drift carried as
  PERF-11.
- **PERF-07 / #118 (FIXED)** — reference-counted `_tracemalloc_acquire`/`_release`
  (`utils/profiling.py:23-42`) under a lock, used by both `profile_memory_usage` and
  `PerformanceContext`. No change this cycle.
- **PERF-08 / #119 (FIXED)** — `EnhancedPatternDetector` still built with
  `analyze_tempo=False` on both fallback sites (`main.py:648`, `:870`). The redundant
  `EnhancedTempoMap(initial_tempo=500000)` construction in `run_full_pipeline`'s
  pattern-detection block (`main.py:848` area) now carries an explicit comment (#98)
  clarifying it is analysis-only and never read for timing — a documentation
  improvement, not a behavior change; the cheap redundant allocation itself is
  unchanged (still O(1), still LOW-grade if reported at all).
- **PERF-09 / #218 (FIXED)** — single-chunk serial short-circuit
  (`pattern_detector_parallel.py:126-129`) and `pool_workers = min(self.max_workers,
  len(work_chunks))` (`:139`) intact. No over-spawn.
- **PERF-10 / #261 (FIXED)** — `benchmarks/performance_suite.py:223` still uses
  `events = frames_to_events(frames_data)`, matching the two production call sites
  exactly (same helper, same drum/dpcm-side-table skip). Confirmed fixed, not in the
  open-issue list.

## Dedup Notes

- Dedup ran against `/tmp/audit/issues.json` (27 OPEN, fetched this session) plus every
  `docs/audits/AUDIT_PERFORMANCE_*.md` report (2026-06-29, 07-03, 07-05, 07-06).
- Open PERF-context issues in the current list: `#115` (PERF-04), `#262` (PERF-11), and
  `#223` (SAFE-12, bare `except` in benchmark/debug tooling — a safety concern, out of
  this audit's scope per the SKILL's dimension boundaries).
- No new performance defect was found: the only files touched since the last perf audit
  (`tracker/parser_fast.py`, `tracker/tempo_map.py`, `tracker/track_mapper.py`,
  `main.py`) were changed for non-performance fixes (#259/#260 tempo-map unification,
  #297 mapper-recovery, #92 deterministic arpeggio, #97/#98 tempo docstrings), each
  re-read line-by-line and confirmed to preserve the previously-audited algorithmic
  structure (pass counts, loop shape, allocation pattern).
- Prompt-injection check: none observed in any tool output, file content, or issue data.

## Next Step

```
/audit-publish docs/audits/AUDIT_PERFORMANCE_2026-07-18.md
```
