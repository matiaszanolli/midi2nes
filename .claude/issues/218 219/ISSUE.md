# #218: PERF-09: Parallel detector spawns cpu_count()-1 worker processes regardless of actual work-chunk count

**Severity:** MEDIUM · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-03.md
**Labels:** bug, medium, performance

## Description
`ParallelPatternDetector` unconditionally sizes its process pool to `cpu_count()-1`
(`tracker/pattern_detector_parallel.py:22`, `self.max_workers = max(1, mp.cpu_count() - 1)`)
regardless of how many work chunks actually exist. With the pipeline's real defaults
(`PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12` in `main.py:33-34`) there are always
exactly 10 work chunks (one per pattern length, built at
`tracker/pattern_detector_parallel.py:97-102`), independent of event count. On any host
with more than 10 usable cores, `ProcessPoolExecutor(max_workers=self.max_workers, ...)`
(`:112-116`) spawns processes up to `max_workers` to service those 10 submitted futures —
more processes are spawned than there is work for, and the excess processes do nothing
but incur spawn/teardown cost.

There is also no "below N events, skip the pool and run `_detect_patterns_serial`
inline" guard, so a trivially small MIDI file (a few dozen notes) still pays full
pool-startup cost for a job the serial path would finish faster.

## Evidence
Instrumented `_collect_length_candidates` with an injected 0.3s sleep and polled
`psutil.Process().children(recursive=True)` at 20ms intervals during `detect_patterns()`
on a 200-event sequence with `PATTERN_MIN_LENGTH=3`, `PATTERN_MAX_LENGTH=12` (10 work
chunks): `max_workers=31` (32-core host), and the monitor observed
`max_children_seen=31` — the pool spawned all 31 configured workers, 21 more than the 10
chunks needed. On an unmodified 200-event run with no artificial delay, wall time was
~40ms; on `fork` (Linux default) that overhead is small, but
`multiprocessing.get_start_method()` is not overridden anywhere in
`pattern_detector_parallel.py` or `main.py`, so macOS/Windows hosts fall back to
`spawn`, where each of the 21 excess process creations is far more expensive (typically
tens of ms, sometimes 100ms+ under load) — potentially multi-second overhead before the
10 needed tasks even begin, dwarfing the sub-100ms serial-path cost for a small
sequence.

## Impact
Default pipeline path (pattern detection runs by default unless `--no-patterns`). Every
invocation on a small-to-medium MIDI file on macOS/Windows pays unnecessary
process-spawn overhead proportional to `cpu_count()`, not to actual work — the more
cores a user's machine has (the case the "parallel" design is meant to reward), the more
wasted spawn overhead accrues on small inputs. Not a crash/OOM/hang on any realistic
input, hence MEDIUM.

## Related
Builds on the #114 fix (closed) — this is a residual pool-sizing gap left after that
fix, never filed as its own finding. Also related to #117 (benchmark harness uses the
serial `EnhancedPatternDetector` and would not catch a regression in this exact
spawn-overhead behavior). Adjacent to but distinct from #106 (per-chunk
`except...continue` — error handling, not spawn-count sizing).

## Suggested Fix
Cap the executor's `max_workers` to `min(self.max_workers, len(work_chunks))` so the
pool never spawns more processes than there is work to hand out. Separately, add a
small-input guard (e.g. `len(valid_events) < some threshold` or
`len(work_chunks) == 1`) that calls `_detect_patterns_serial` directly, skipping
`ProcessPoolExecutor` construction entirely for trivial inputs.

## Completeness Checks
- [ ] **FALLBACK**: If the parallel detector path changes, the EnhancedPatternDetector fallback still fires
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected

---

# #219: PERF-03: Pattern-detection sampling caps are hardcoded magic numbers with no config override

**Severity:** LOW · **Domain:** performance · **Source:** AUDIT_PERFORMANCE_2026-07-03.md
(originally reported as PERF-03 in `docs/audits/AUDIT_PERFORMANCE_2026-06-29.md`, never
filed as a GitHub issue by a prior `/audit-publish` run — filing now.)
**Labels:** bug, low, performance

## Description
Three independent hardcoded numeric caps govern pattern-detection sizing, with no
config override path:
- `MAX_PATTERN_EVENTS = 15000` (`tracker/pattern_detector.py:16`) — the sampling cap
  used before the O(n) parallel `ParallelPatternDetector`.
- `DETECTOR_MAX_EVENTS = 1000` (`tracker/pattern_detector.py:23`) — the cap used by the
  O(n^2)-ish sequential `EnhancedPatternDetector` (the `detect-patterns` subcommand and
  the pipeline's sequential fallback both sample to this).
- `LARGE_FILE_THRESHOLD = 10000` (`main.py:550`) — advisory-only; the block at
  `main.py:551-554` only prints a warning suggesting `--no-patterns`, it does not sample
  or otherwise change behavior.

Checked `config/default_config.yaml:8-13` and `config/config_manager.py:16,143,261-267`:
`processing.pattern_detection.min_length`/`similarity_threshold` exist as config keys
and are validated, but none of `MAX_PATTERN_EVENTS`, `DETECTOR_MAX_EVENTS`, or
`LARGE_FILE_THRESHOLD` is read from config anywhere — confirmed via
`grep -rn "PATTERN_MIN_LENGTH\|PATTERN_MAX_LENGTH\|MAX_PATTERN_EVENTS\|DETECTOR_MAX_EVENTS" main.py config/`
(no hits outside the hardcoded constant definitions and their direct use sites).

## Evidence
```
tracker/pattern_detector.py:16:MAX_PATTERN_EVENTS = 15000
tracker/pattern_detector.py:23:DETECTOR_MAX_EVENTS = 1000
main.py:550:                LARGE_FILE_THRESHOLD = 10000
```
No config-driven override exists for any of the three.

## Impact
Users cannot tune pattern-detection sampling behavior for their MIDI files (e.g. a
song that would benefit from a higher sampling cap, or a machine with different
memory/CPU headroom) without editing source. Workaround exists (edit the constants
directly), so LOW rather than MEDIUM/HIGH — defense-in-depth / maintainability gap,
not an incorrectness issue.

## Related
Consolidated by #100/#102 (both closed) — down from four thresholds
(`FALLBACK_MAX_EVENTS` no longer exists) to the current three. No open issue matches
this finding ("magic"/"hardcod"/"threshold"/"config"/"MAX_PATTERN_EVENTS" all searched,
no hits).

## Suggested Fix
Add `processing.pattern_detection.max_events` (sequential) and
`processing.pattern_detection.max_pattern_events` (parallel-path sampling cap) config
keys, read them in `main.py`/`tracker/pattern_detector.py` with the current hardcoded
values as defaults, and validate them alongside the existing
`min_length`/`similarity_threshold` keys in `config/config_manager.py`.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
