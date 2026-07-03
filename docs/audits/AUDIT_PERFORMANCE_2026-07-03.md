# Performance Audit — MIDI2NES

- **Date**: 2026-07-03
- **Scope**: parse hot path, parallel pattern detector, large-file sampling, inter-stage
  memory, serialization cost, benchmark-harness validity, profiling utilities,
  cross-stage redundant recomputation — per `.claude/commands/audit-performance/SKILL.md`.
- **Method**: live source re-read at HEAD `9cfa0e2`; severity per `_audit-severity.md`;
  dedup against `gh issue list --state all` (`/tmp/audit/issues_all.json`, 47 open + 6
  closed relevant issues) and every prior report in `docs/audits/`, in particular
  `docs/audits/AUDIT_PERFORMANCE_2026-06-29.md` (4 days prior).
- **Prompt-injection note**: no injected instructions were encountered in any tool
  result, file, or command output during this audit. (A prior parallel agent in this
  suite reported one; nothing of that shape appeared in this run — noted per
  instructions, nothing to disclose beyond this.)

## What changed since the 2026-06-29 audit

`git log --since=2026-06-29 -- tracker/parser_fast.py tracker/tempo_map.py
tracker/pattern_detector_parallel.py tracker/pattern_detector.py main.py benchmarks/
utils/profiling.py nes/song_bank.py` shows two commits that touch this audit's surface:

- **`de998dd`** (#124/#125) — `parser_fast.py`'s note-loop `except Exception` now counts
  `dropped_note_events` and prints a summary warning instead of silently swallowing.
  This is a *safety* fix (cross-ref `/audit-safety`), not a perf-shape change; it does
  not add scan cost on the hot path (the counter increment is O(1)).
- **`d8f6a0e`** (#33/#34) — `nes/song_bank.py` now imports `parse_midi_to_frames` from
  `tracker.parser_fast` instead of the old full `tracker.parser`, and the dead top-level
  `from tracker.parser import parse_midi_to_frames` was removed from `main.py`. This
  **closes the "third tempo/parser path" angle** that PERF-08 (#119) cross-referenced
  (`open #33/F-14`) — confirmed both #33 and #34 are now **CLOSED**. PERF-08 itself
  (the four-way tempo-map rebuild inside `main.py`/`parser_fast.py`) is unaffected and
  remains valid — see below.

Everything else in the audited surface (`tempo_map.py`'s bisect index, the parallel
detector's O(n) hash-grouping + pool-initializer sequence sharing, the three sampling
caps, `benchmarks/performance_suite.py`, `utils/profiling.py`) is **byte-for-byte
unchanged** since the last audit.

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0 |
| HIGH     | 0 |
| MEDIUM   | 1 new |
| LOW      | 0 new |
| **NEW this cycle** | **1** |

Existing findings re-verified against live code, all still accurate, all still tracked:
PERF-04 (#115, LOW), PERF-05 (#116, MEDIUM), PERF-06 (#117, MEDIUM), PERF-07 (#118, LOW),
PERF-08 (#119, LOW) — see re-verification notes per dimension below. PERF-01 (#113) and
PERF-02 (#114) are **CLOSED** and confirmed fixed in current code (re-derivation below).
PERF-03 (magic sampling-cap numbers, previously reported but never filed as a GitHub
issue) remains valid and unfiled — flagged again below for `/audit-publish` to pick up.

### Highest-leverage items this cycle

1. **PERF-09 (NEW)** — the parallel pattern detector spawns `cpu_count()-1` OS
   processes via `ProcessPoolExecutor(max_workers=self.max_workers, ...)` regardless of
   how many work chunks actually exist (10 by default: `PATTERN_MIN_LENGTH=3` to
   `PATTERN_MAX_LENGTH=12`). Measured empirically in this sandbox (32 cores): **31
   child processes spawn for a 10-chunk job**, even on a 200-event input that completes
   in ~40ms. On `fork`-based platforms (Linux) this is cheap; on `spawn`-based
   platforms (macOS default since Python 3.8, Windows always) each process spawn can
   cost tens to ~100ms, so a small-to-medium MIDI file — the common case — can pay
   multiple seconds of pure process-spawn overhead for a pattern-detection stage that
   would otherwise finish in well under 100ms serially.
2. **PERF-06 (#117, still open)** — benchmark harness still measures `tracker.parser`
   and `EnhancedPatternDetector`, not the production `parser_fast`/`ParallelPatternDetector`
   path, and still double-calls `_end_profiling`. Confirmed unchanged; still the
   highest-leverage *existing* gap because it means a regression in the real hot path
   (including a future regression of PERF-09's fix) would not be caught.
3. **PERF-05 (#116, still open)** — all four intermediate-JSON writers (`main.py:71,81,90,394`)
   still use `indent=2`. Confirmed unchanged.

---

## Findings

### PERF-09: Parallel detector spawns `cpu_count()-1` worker processes regardless of actual work-chunk count — no small-input / low-chunk-count guard
- **Severity**: MEDIUM
- **Dimension**: D2 — Parallel detector scaling & work distribution
- **Location**: `tracker/pattern_detector_parallel.py:22` (`self.max_workers = max(1, mp.cpu_count() - 1)`), `:97-102` (`work_chunks` — one per pattern length, 10 by default), `:112-116` (`ProcessPoolExecutor(max_workers=self.max_workers, ...)`)
- **Status**: NEW
- **Description**: The #114 fix (closed) correctly bounded *work* to `O(n·L)` and
  eliminated per-chunk IPC duplication (re-verified below), but it left the **pool size**
  unconditionally tied to `cpu_count()-1` with no adjustment for the actual number of
  work chunks or the size of the input. With the pipeline's real defaults
  (`PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12` in `main.py:33-34`) there are always
  exactly 10 work chunks (one per pattern length), independent of event count. On any
  host with more than 10 usable cores, `ProcessPoolExecutor` spawns processes up to
  `max_workers` to service those 10 submitted futures — confirmed empirically (see
  Evidence): **more processes are spawned than there is work for**, and the excess
  processes do nothing but incur spawn/teardown cost. There is also no "below N events,
  skip the pool and run `_detect_patterns_serial` inline" guard, so a trivially small
  MIDI file (a few dozen notes) still pays full pool-startup cost for a job the serial
  path would finish faster.
- **Evidence**: Instrumented `_collect_length_candidates` with an injected 0.3s sleep
  and polled `psutil.Process().children(recursive=True)` at 20ms intervals during
  `detect_patterns()` on a 200-event sequence with `PATTERN_MIN_LENGTH=3`,
  `PATTERN_MAX_LENGTH=12` (10 work chunks): `max_workers=31` (this host has 32 cores),
  and the monitor observed **`max_children_seen=31`** — i.e. the pool spawned all 31
  configured workers, 21 more than the 10 chunks needed. On an unmodified 200-event run
  with no artificial delay, wall time was ~40ms; on `fork` (this host's default start
  method) that overhead is small, but `multiprocessing.get_start_method()` is not
  overridden anywhere in `pattern_detector_parallel.py` or `main.py`, so macOS/Windows
  hosts fall back to `spawn`, where each of the 21 excess process creations is far more
  expensive (typically tens of ms, sometimes 100ms+ under load) — potentially
  multi-second overhead before the 10 needed tasks even begin, dwarfing the sub-100ms
  serial-path cost the SKILL's own re-derivation of the #114 fix shows for a small
  sequence.
- **Impact**: Default pipeline path (pattern detection runs by default unless
  `--no-patterns`). Every invocation on a small-to-medium MIDI file on macOS/Windows
  pays unnecessary process-spawn overhead proportional to `cpu_count()`, not to actual
  work — the more cores a user's machine has (the case the "parallel" design is meant to
  reward), the *more* wasted spawn overhead accrues on small inputs. Not a crash/OOM/hang
  on any realistic input (bounded to a few seconds at worst), so MEDIUM rather than HIGH
  per the severity floor ("escalate to HIGH only when a regression makes a common MIDI
  file fail outright").
- **Related**: Builds on the #114 fix (PERF-02, closed) — the SKILL's own re-derivation
  of that fix explicitly flags this residual gap under "Worker sizing" but it was never
  filed as its own finding/issue. Also related to PERF-06 (#117): the benchmark harness
  uses the serial `EnhancedPatternDetector`, so it would not catch a regression in this
  exact spawn-overhead behavior either way.
- **Suggested Fix**: Cap the executor's `max_workers` to `min(self.max_workers,
  len(work_chunks))` so the pool never spawns more processes than there is work to hand
  out. Separately, add a small-input guard (e.g. `len(valid_events) < some threshold` or
  `len(work_chunks) == 1`) that calls `_detect_patterns_serial` directly, skipping
  `ProcessPoolExecutor` construction entirely for trivial inputs.

---

## Re-verification of prior findings (no new report entries — see Status)

### PERF-01 / PERF-02 — CLOSED, fix confirmed solid
- `tracker/tempo_map.py:123-184` (`_build_tempo_index`, `_get_tempo_index`,
  `_cumulative_ms`, `get_tempo_at_tick`, `calculate_time_ms`) — confirmed the
  lazily-built bisect index (ticks/tempos/cumulative-ms arrays) is in place,
  invalidated on every `add_tempo_change` (`tempo_map.py:120-121`, `:269-270`,
  `:345-346`, `:656-658`) with a length-mismatch backstop
  (`_get_tempo_index:148`). `get_tempo_at_tick` and `calculate_time_ms` are now
  `O(log T)` via `bisect.bisect_right`, not the old linear/`O(T²)` scans. **#113
  remains correctly closed.**
- `tracker/pattern_detector_parallel.py:238-297` (`_collect_length_candidates`) —
  confirmed the single linear pass + bucket-by-window-value + greedy
  non-overlapping selection is in place (`O(n)` per length, `O(n·L)` total),
  used identically by both the `ProcessPoolExecutor` workers
  (`_detect_patterns_worker:300-308`) and the serial fallback
  (`_detect_patterns_serial:146-161`). Sequence/events are shipped to worker
  processes exactly once via `ProcessPoolExecutor(..., initializer=_init_pattern_worker,
  initargs=(sequence, valid_events))` (`:112-116`), read back from module globals
  `_WORKER_SEQUENCE`/`_WORKER_EVENTS` (`:226-235`) rather than re-embedded per chunk.
  **#114 remains correctly closed.** (PERF-09 above is a new, narrower residual gap in
  the *pool-sizing* logic surrounding this fix, not a regression of the fix itself.)

### PERF-03 — still valid, still not filed as a GitHub issue
- `tracker/pattern_detector.py:14-23` (`MAX_PATTERN_EVENTS = 15000`,
  `DETECTOR_MAX_EVENTS = 1000`), `main.py:550` (`LARGE_FILE_THRESHOLD = 10000`,
  advisory-only — confirmed the block at `:551-554` only prints, does not sample or
  otherwise change behavior). Three thresholds (down from four in the 2026-06-29
  report's `FALLBACK_MAX_EVENTS`, which no longer exists — `grep -rn
  FALLBACK_MAX_EVENTS` matches only historical `.claude/issues/100`, `/102` drafts and
  the prior audit report, not live code — consolidated by #100/#102, both closed).
  Checked `config/default_config.yaml:8-13` and `config/config_manager.py:16,143,261-267`:
  `processing.pattern_detection.min_length`/`similarity_threshold` exist as config keys
  and are validated, but neither `MAX_PATTERN_EVENTS`, `DETECTOR_MAX_EVENTS`, nor
  `LARGE_FILE_THRESHOLD` is read from config anywhere — confirmed via
  `grep -rn "PATTERN_MIN_LENGTH\|PATTERN_MAX_LENGTH\|MAX_PATTERN_EVENTS\|DETECTOR_MAX_EVENTS"
  main.py config/` (no hits outside the hardcoded constant definitions and their direct
  use sites). Still three independent hardcoded numbers, still no config override path.
- **Status**: Previously reported as PERF-03 in `docs/audits/AUDIT_PERFORMANCE_2026-06-29.md`.
  Searched `gh issue list --state all` for "magic", "hardcod", "threshold",
  "config knob", "MAX_PATTERN_EVENTS" — no matching issue exists. This finding was
  never converted to a GitHub issue by a prior `/audit-publish` run. Not re-derived as a
  fresh NEW finding here (would duplicate the existing writeup); flagged so
  `/audit-publish` includes it this cycle. Severity unchanged: LOW.

### PERF-04 (#115, OPEN, LOW) — inter-stage memory duplication
Re-checked `main.py` for `del frames`/`del events`/`del midi_data` between pipeline
stages: **none found** (`grep -n "del frames\|del events\|del midi_data\|del mapped"
main.py` — no matches). The events→frames→events round-trip
(`main.py:540-547` in `run_full_pipeline`, `main.py:362-370` in `run_detect_patterns`)
is unchanged. Confirmed still accurate; no regression, no new finding.

### PERF-05 (#116, OPEN, MEDIUM) — `indent=2` on hot intermediates
Re-checked: `main.py:71,81,90` (parse/map/frames writers) and `:394` (detect-patterns
writer) all still call `json.dumps(..., indent=2)`. Confirmed still accurate.

### PERF-06 (#117, OPEN, MEDIUM) — benchmark harness measures the wrong modules
Re-checked `benchmarks/performance_suite.py` line-by-line:
- `:18` still imports `from tracker.parser import parse_midi_to_frames` (the slow full
  parser), not `tracker.parser_fast`.
- `:198` still constructs `EnhancedPatternDetector`, not `ParallelPatternDetector` — the
  benchmark exercises neither the #113 nor the #114 fix.
- All five `benchmark_*_stage` methods (`:152-160` parse, `:162-180` map, `:182-191`
  frames, `:193-220` pattern_detection, `:222-247` export) still call
  `self.profiler._end_profiling(stage_name, True)` a **second time** immediately after
  the `with self.profiler.profile(stage_name):` block already ran `_end_profiling`
  once internally and stopped `tracemalloc` (`:71-72`, `:99-104`) — the second call's
  `tracemalloc.get_traced_memory()` hits the bare `except` (`:103`) and falls back to
  current RSS rather than a traced peak. Confirmed still accurate, unchanged.
- `benchmarks/run_benchmarks.py:69-77` (non-deterministic glob over `test_data/`,
  `examples/`, `samples/`, `.`) and `benchmark_results/benchmark_results.json` (checked-in
  run output, no comparison gate) both confirmed unchanged.

### PERF-07 (#118, OPEN, LOW) — shared global tracemalloc / cpu_percent / MemoryMonitor
Re-checked `utils/profiling.py`: three independent `tracemalloc.start()`/`stop()` pairs
(`profile_memory_usage:171,195`; `PerformanceContext.__enter__`/`__exit__:285,299`) over
the one process-global tracer, `cpu_percent()` called with no `interval=` at `:165,189`
(and in `benchmarks/performance_suite.py:87,96`), and `MemoryMonitor._monitor_loop`'s
bare `except: break` at `:89-90` with `stop_monitoring` returning `{"peak_mb": 0, ...}`
when no samples were taken (`:71-72`). All confirmed unchanged.

### PERF-08 (#119, OPEN, LOW) — tempo map rebuilt redundantly; events round-trip
Re-checked: `parser_fast.py:150-189` (`parse_midi_to_frames_with_analysis` re-opens the
MIDI and rebuilds the tempo map — comment at `:179` "could be optimized with caching"
still present, unchanged wording from the prior "could be cached from first pass").
Three independent fresh `EnhancedTempoMap(initial_tempo=500000)` constructions with
default (unset-from-file) `ticks_per_beat=480` confirmed at `main.py:357`
(`run_detect_patterns`), `main.py:536` (`run_full_pipeline`'s pattern-detection step),
and `benchmarks/performance_suite.py:197`. These remain mutually exclusive per
invocation (as before) and still unused for anything the pattern detectors read
(`note`/`volume` only), so still a wasted-construction finding, not an incorrectness
one. The events→frames→events round-trip is confirmed at `main.py:540-547` and
`:362-370`. **New context this cycle**: the *fourth* rebuild path this finding used to
cross-reference — `nes/song_bank.py`'s independent full-parser call — is now gone
(`d8f6a0e`/#33, closed); `song_bank.py` calls the same `parser_fast.parse_midi_to_frames`
as the pipeline, which builds its own tempo map internally but is no longer a
*structurally different* third code path. This narrows PERF-08's blast radius slightly
but does not close it — the three `main.py`/`parser_fast.py`-internal rebuilds above are
unaffected. Severity unchanged: LOW.

---

## Dedup Notes

- `gh issue list --repo matiaszanolli/midi2nes --state all --limit 300` (47 open + 6
  relevant closed) checked for every finding above.
- PERF-01/#113 and PERF-02/#114: confirmed **CLOSED**, fixes verified in place
  (re-derivation above), not re-reported.
- PERF-04/#115, PERF-05/#116, PERF-06/#117, PERF-07/#118, PERF-08/#119: confirmed
  **OPEN** and still accurate against current code; not re-reported as new findings
  (dedup protocol: note as Existing and skip).
- PERF-03: no matching GitHub issue found under any plausible title
  ("magic"/"hardcod"/"threshold"/"config"/"MAX_PATTERN_EVENTS") — previously reported
  only in `docs/audits/AUDIT_PERFORMANCE_2026-06-29.md`, never published. Flagged above,
  not re-derived as a duplicate NEW finding.
- PERF-09 is genuinely new: no open or closed issue references pool-sizing,
  process-spawn overhead, chunk-count-vs-core-count, or a missing small-input guard for
  `ParallelPatternDetector`. `P-09`/#106 (per-chunk `except...continue` silently
  dropping a length's candidates) and `REG-06`/#46 (closed — parallel detector test
  coverage) are adjacent but describe different defects (error handling and test
  coverage, not spawn-count sizing).
- Prompt-injection check: no injected "system reminder" or similar instruction was
  observed in any tool output, file content, or issue data during this audit run.

## Next Step

```
/audit-publish docs/audits/AUDIT_PERFORMANCE_2026-07-03.md
```
