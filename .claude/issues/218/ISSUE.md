# PERF-09: Parallel detector spawns cpu_count()-1 worker processes regardless of actual work-chunk count

- **GitHub Issue**: https://github.com/matiaszanolli/midi2nes/issues/218
- **Labels**: medium, performance, bug
- **Source Report**: docs/audits/AUDIT_PERFORMANCE_2026-07-03.md
- **Severity**: MEDIUM
- **Dimension**: D2 — Parallel detector scaling & work distribution
- **Location**: `tracker/pattern_detector_parallel.py:22` (`self.max_workers = max(1, mp.cpu_count() - 1)`), `:97-102` (`work_chunks` — one per pattern length, 10 by default), `:112-116` (`ProcessPoolExecutor(max_workers=self.max_workers, ...)`)
- **Status filed as**: NEW

## Description
`ParallelPatternDetector` unconditionally sizes its process pool to `cpu_count()-1`
regardless of how many work chunks actually exist. With the pipeline's real defaults
(`PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12` in `main.py:33-34`) there are always
exactly 10 work chunks (one per pattern length), independent of event count. On any
host with more than 10 usable cores, `ProcessPoolExecutor` spawns processes up to
`max_workers` to service those 10 submitted futures — more processes are spawned than
there is work for, and the excess processes do nothing but incur spawn/teardown cost.
There is also no small-input guard to skip the pool and run `_detect_patterns_serial`
inline.

## Evidence
Instrumented `_collect_length_candidates` with an injected 0.3s sleep and polled
`psutil.Process().children(recursive=True)` at 20ms intervals during `detect_patterns()`
on a 200-event sequence (10 work chunks): `max_workers=31` (32-core host), and the
monitor observed `max_children_seen=31` — 21 more processes than the 10 chunks needed.
`multiprocessing.get_start_method()` is not overridden anywhere in
`pattern_detector_parallel.py` or `main.py`, so macOS/Windows hosts fall back to
`spawn`, where each excess process creation is expensive (tens to 100ms+), potentially
multi-second overhead before the 10 needed tasks even begin.

## Impact
Default pipeline path (pattern detection runs by default unless `--no-patterns`). Every
invocation on a small-to-medium MIDI file on macOS/Windows pays unnecessary
process-spawn overhead proportional to `cpu_count()`, not to actual work. Not a
crash/OOM/hang on any realistic input, hence MEDIUM.

## Related
Builds on the #114 fix (closed) — residual pool-sizing gap left after that fix, never
filed as its own finding until now. Also related to #117 (benchmark harness uses the
serial `EnhancedPatternDetector`, would not catch a regression here). Adjacent to but
distinct from #106 (per-chunk `except...continue` error handling, not spawn sizing).

## Suggested Fix
Cap the executor's `max_workers` to `min(self.max_workers, len(work_chunks))`.
Separately, add a small-input guard that calls `_detect_patterns_serial` directly,
skipping `ProcessPoolExecutor` construction entirely for trivial inputs.

## Completeness Checks
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
