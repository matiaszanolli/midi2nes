# Performance Audit — MIDI2NES

- **Date**: 2026-08-06
- **Scope**: Compile-path performance correctness — parser hot path, parallel
  pattern detector, large-file sampling, inter-stage memory, serialization cost,
  benchmark-harness validity, profiling utilities, cross-stage recompute.
- **Focus**: all dimensions (1–8)
- **Method**: Re-read every live code path named in the skill against the current
  tree (branch `fix/issues-136-137-167-202`); ran `git log --since=2026-08-05` on
  every performance-relevant file against the prior audit's findings; deduped
  against `gh issue list --repo matiaszanolli/midi2nes` and, for each issue marked
  CLOSED, verified the cited fix commit is actually reachable from the audited
  tree (`git merge-base --is-ancestor <sha> HEAD`) rather than trusting the closed
  state at face value.

## Summary

**No performance-relevant source file changed since the 2026-08-05 audit.**
`git log --since=2026-08-05` on `main.py`, `tracker/parser_fast.py`,
`tracker/pattern_detector_parallel.py`, `tracker/pattern_detector.py`,
`tracker/tempo_map.py`, `benchmarks/performance_suite.py`,
`benchmarks/run_benchmarks.py`, `utils/profiling.py`, `config/default_config.yaml`,
and `nes/emulator_core.py` returns nothing; the one commit made on this branch
today (`20f627e`, DPCM/exporter emitter refactor for #136/#137/#202) touches
`arranger/`, `dpcm_sampler/`, and `exporter/exporter_ca65.py` only — none of it is
on the performance surface.

**The headline finding this cycle is not a code regression — it is a dedup-process
failure.** Three of the six findings originally reported in
`docs/audits/AUDIT_PERFORMANCE_2026-07-19.md` (#372, #373, #374) were marked
**CLOSED** on GitHub between 2026-08-06T01:29 and 01:36, each with a comment citing
a specific fix commit (`8a6bf15`, `8a6bf15`, `e990f6a`). None of those three commits
are reachable from `master` or from this branch (`git merge-base --is-ancestor`
returns false for all three) — they exist only on local branches
(`fix/issues-372-373-benchmark-baseline-gate`, `fix/issue-374-cpu-percent-accuracy`)
for which **no PR was ever opened** (`gh pr list --state all` has no PR touching
either branch name). The actual code in the tree being audited still has the
exact defect each issue described, byte-for-byte identical to the 2026-08-05
re-verification. Per the shared dedup protocol ("If CLOSED: verify the fix is in
place. If regressed, report as 'Regression of #NNN'"), all three are re-reported
below as regressions of their own closure. By contrast #371's fix (`89bdeb7`) *is*
an ancestor of `master` (merged via PR #400) and is correctly reflected in the
current code (`del midi_data`/`del mapped` present in `run_full_pipeline`).

The other two prior findings, #375 and #376, remain correctly **OPEN** on GitHub
and unregressed — re-confirmed against current line numbers.

### Finding counts

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 1 |
| LOW | 5 |
| **Total** | **6** (all pre-existing; 0 code regressions; 3 falsely-closed-issue re-affirmations) |

### Counts per dimension

| Dimension | Findings |
|---|---|
| 1 — Parser hot path | 0 |
| 2 — Parallel detector scaling | 0 |
| 3 — Large-file sampling | 0 |
| 4 — Inter-stage memory | 0 (#371 confirmed fixed and merged) |
| 5 — Serialization cost | 0 |
| 6 — Benchmark validity | 2 (#372, #373 — falsely closed, unmerged fix) |
| 7 — Profiling utilities | 2 (#374 — falsely closed, unmerged fix; #375 — open) |
| 8 — Cross-stage recompute | 1 (#376 — open) |

### Highest-leverage fixes

1. **Process fix, not code fix: merge or reopen #372/#373/#374.** The actual code
   fixes already exist and were verified sound on their branches; they simply need
   a PR into `master`. Until then the benchmark harness still has no baseline/gate
   and `cpu_percent` is still the unreliable interval-less delta — same as before
   the issues were (incorrectly) closed. This is the fastest possible win: no new
   engineering, just landing already-written commits.
2. **#376** — thread parse-time tempo data forward instead of reconstructing
   `EnhancedTempoMap` at each of the two pattern-detection call sites, and avoid
   the frames→events round trip.
3. **#375** — `MemoryMonitor._monitor_loop`'s `except Exception: ... break` ends
   sampling permanently on one transient error; should `continue` past a single
   hiccup.

---

## Findings

### PERF-A-02R: Benchmark harness baseline/regression-gate fix exists only on an unmerged branch
- **Severity**: LOW
- **Dimension**: 6 — Benchmark validity
- **Location**: `benchmarks/run_benchmarks.py`, `benchmarks/performance_suite.py` (current tree — fix absent); fix present only on unmerged branch `fix/issues-372-373-benchmark-baseline-gate` at commit `8a6bf15`
- **Status**: Regression of #372 (issue closed 2026-08-06T01:36 as "Fixed in 8a6bf15", but `8a6bf15` is not an ancestor of `master` or of this branch — no PR was ever opened for it)
- **Description**: GitHub issue #372 ("Benchmark harness has no checked-in baseline
  and no regression gate") was closed with a comment pointing to commit `8a6bf15`,
  which does add `benchmarks/baseline.json`, `benchmarks/fixtures/*.mid`, and a
  regression-gate diff to `run_benchmarks.py`/`performance_suite.py`. That commit,
  however, sits on a branch that was never merged (`gh pr list --repo
  matiaszanolli/midi2nes --state all` returns no PR for
  `fix/issues-372-373-benchmark-baseline-gate`). The tree actually being audited —
  this branch and `master` alike — has none of it: `benchmarks/` still contains
  only `performance_suite.py`/`run_benchmarks.py`/`__pycache__`, no `fixtures/` dir,
  no `baseline.json` anywhere in the repo.
- **Evidence**: `git merge-base --is-ancestor 8a6bf15 HEAD` → exit 1 (not an
  ancestor); same against `master` → exit 1. `find . -iname "*baseline*"` returns
  nothing. `gh issue view 372 --json closedAt,comments` shows the closing comment
  "Fixed in 8a6bf15 (branch fix/issues-372-373-benchmark-baseline-gate)."
- **Impact**: The audit trail says this is fixed; the code says it isn't. Anyone
  trusting the issue tracker (including a future audit's dedup step, or
  `/audit-publish` skipping a "CLOSED" match) will silently drop real, still-open
  work. `run_baseline_benchmark` still globs whatever `.mid` files happen to be on
  disk and the suite still has no fail-on-regression assertion — a real slowdown
  in the parser or detector still passes unnoticed.
- **Related**: #373 (same commit, same branch, same gap); Dimension 6; prior
  reports `docs/audits/AUDIT_PERFORMANCE_2026-07-19.md` and `..._2026-08-05.md`.
- **Suggested Fix**: Open a PR from `fix/issues-372-373-benchmark-baseline-gate`
  against `master` and merge it — the fix is already written and, per its own
  diff, adds deterministic fixtures plus a checked-in baseline. If the branch has
  since drifted, rebase and re-verify `benchmarks/fixtures/*.mid` +
  `benchmarks/baseline.json` land in the tree.

### PERF-A-03R: Deterministic-fixture fix exists only on the same unmerged branch as #372
- **Severity**: LOW
- **Dimension**: 6 — Benchmark validity
- **Location**: `benchmarks/run_benchmarks.py` (current tree — fix absent); fix present only on unmerged branch `fix/issues-372-373-benchmark-baseline-gate` at commit `8a6bf15`
- **Status**: Regression of #373 (issue closed 2026-08-06T01:36 as "Fixed in 8a6bf15", same unmerged commit as #372)
- **Description**: Issue #373 ("Baseline benchmark input set is machine-dependent")
  was closed with the same commit/comment as #372, and is fixed by the same diff
  (`benchmarks/fixtures/multiple_tracks.mid`, `simple_loop.mid`,
  `tempo_changes.mid`). Since that commit never landed on `master`, the live
  `run_baseline_benchmark` in the audited tree is unchanged: it still globs
  `test_data/`, `examples/`, `samples/`, `.` for `*.mid` and benchmarks whatever
  the first 5 (sorted) happen to be on the machine running it.
- **Evidence**: Same `merge-base` check as PERF-A-02R; `git diff HEAD 8a6bf15
  --stat` shows `benchmarks/fixtures/*.mid` and `benchmarks/baseline.json` only
  on the other side of the diff, i.e. absent from `HEAD`.
- **Impact**: Cross-run/cross-machine benchmark numbers remain incomparable;
  blocks anchoring a stable baseline for #372's gate (same root cause, same fix
  commit — report once, cross-reference).
- **Related**: #372 (identical root cause and fix); Dimension 6.
- **Suggested Fix**: Same as #372 — merging that one PR resolves both issues
  simultaneously, as originally intended.

### PERF-A-04R: `cpu_percent` accuracy fix exists only on an unmerged branch
- **Severity**: MEDIUM
- **Dimension**: 7 — Profiling utilities
- **Location**: `benchmarks/performance_suite.py:217,241,270`, `utils/profiling.py:212-217` (current tree — fix absent); fix present only on unmerged branch `fix/issue-374-cpu-percent-accuracy` at commit `e990f6a`
- **Status**: Regression of #374 (issue closed 2026-08-06T01:29 as "Fixed in e990f6a", but `e990f6a` is not an ancestor of `master` or of this branch — no PR was ever opened for it)
- **Description**: Issue #374 ("`cpu_percent` reported as a delta of two
  interval-less psutil calls") was closed with a comment citing commit `e990f6a`
  ("compute cpu_percent from cpu_times() deltas instead of interval-less
  cpu_percent()"). That commit is not reachable from `master` or this branch —
  `fix/issue-374-cpu-percent-accuracy` has no associated PR. The live code is
  unchanged from the original finding: `process.cpu_percent()` is still called
  once with no `interval=` at the start of a stage and once at the end, and the
  delta of two such calls is still what gets surfaced as `cpu_percent`.
- **Evidence**: `performance_suite.py:217` `cpu_before = process.cpu_percent() if
  include_cpu else 0` and `:270` `cpu_percent=cpu_after - cpu_before if
  include_cpu else 0`, re-confirmed present at these lines today. `utils/
  profiling.py:212-216`'s comment still only *documents* the caveat rather than
  fixing it. `git merge-base --is-ancestor e990f6a HEAD` → not an ancestor.
- **Impact**: Same as originally reported — a `cpu_percent` benchmark column that
  reads as authoritative but is `psutil`-documented advisory noise for the first
  call and a same-process double-measurement thereafter; can misdirect
  optimization effort. Benchmark output only, no production-path effect.
- **Related**: Dimension 7; prior reports (2026-07-19, 2026-08-05).
- **Suggested Fix**: Open a PR from `fix/issue-374-cpu-percent-accuracy` and merge
  it — per its own diff it switches to `cpu_times()` deltas over wall-clock time,
  which is the correct fix already written.

### PERF-A-05: `MemoryMonitor` sampling loop terminates permanently on the first transient error
- **Severity**: LOW
- **Dimension**: 7 — Profiling utilities
- **Location**: `utils/profiling.py:121-137` (`_monitor_loop`)
- **Status**: Existing: #375 (OPEN, unregressed — verified correctly still open)
- **Description**: The daemon sampling loop catches `Exception`, increments
  `_sampling_errors`, and `break`s — one transient sampling hiccup ends all
  further sampling for the rest of the run.
- **Evidence**: `utils/profiling.py:129,136-137` —
  ```
  except Exception:
      ...
      self._sampling_errors += 1
      break
  ```
  Re-confirmed unchanged at current line numbers; `sampling_errors` is surfaced to
  callers (`_monitor_loop`'s stats dict, line 118) but the loop still terminates
  rather than continuing.
- **Impact**: Under-reported peak memory if any single sample fails mid-run
  (e.g. a transient `psutil` read failure). Profiling output only; no effect on
  ROM correctness.
- **Related**: Dimension 7.
- **Suggested Fix**: `continue` past a transient error instead of `break`; only
  stop the loop after a consecutive-failure threshold, or on a specific
  process-gone exception (e.g. `psutil.NoSuchProcess`) that genuinely means
  sampling can never succeed again.

### PERF-A-06: Fresh tempo map rebuilt at each detect site + events↔frames round-trip
- **Severity**: LOW
- **Dimension**: 8 — Cross-stage recompute
- **Location**: `main.py:735` (`run_detect_patterns`), `main.py:959,963` (`run_full_pipeline`), `tracker/parser_fast.py:186-189`
- **Status**: Existing: #376 (OPEN, unregressed — verified correctly still open)
- **Description**: Each pattern-detection call site constructs a fresh
  `EnhancedTempoMap(initial_tempo=500000)` (defaulting `ticks_per_beat=480`)
  rather than reusing tempo data already computed during parsing — the parse
  JSON's `metadata` key stays `{}` (`parse_midi_to_frames` in
  `tracker/parser_fast.py`) — and events are re-extracted from the `frames` dict
  via `frames_to_events` (`nes/emulator_core.py`) even though `frames` was itself
  derived from an events list one stage earlier.
- **Evidence**: `main.py:735` `tempo_map = EnhancedTempoMap(initial_tempo=500000)
  # 120 BPM default` and `:742` `events = frames_to_events(frames)`; mirrored at
  `:959` and `:963` inside `run_full_pipeline`'s inline pattern-detection block.
  `tracker/parser_fast.py:186-189` still returns `"metadata": {}`.
- **Impact**: Redundant object construction and a full events-list rebuild per
  run. Both pattern detectors only read `note`/`volume` from events (not tempo),
  so this is wasted work, not incorrect output — negligible cost on a common
  file, but it is duplicated at two call sites and would compound if a future
  change made either fresh tempo map's `ticks_per_beat=480` default matter (the
  source file's actual resolution is discarded here).
- **Related**: #119 (closed — the costly per-pattern tempo *analysis* half of this
  same recompute chain was already fixed via `analyze_tempo=False`); Dimension 8.
- **Suggested Fix**: Low priority. Serialize a tempo summary into the parse-stage
  JSON so `run_detect_patterns`/`run_full_pipeline` can reuse it instead of
  reconstructing `EnhancedTempoMap` from a hardcoded default, and/or retain the
  frames stage's source event list to avoid the frames→events round trip.

---

## Notes / non-findings (re-verified against live code, no finding)

- **Dim 1 — Parser hot path**: `parse_midi_to_frames`/`parse_midi_to_frames_with_analysis`
  still share `_parse_frames_and_tempo_map` (one file open, one tempo-map build,
  one note pass) — re-confirmed at `tracker/parser_fast.py:70-173`. Tempo lookups
  route through `tracker/tempo_map.py`'s lazily-built bisect index
  (`_build_tempo_index`/`_get_tempo_index`, `tempo_map.py:129-156`), invalidated on
  every `tempo_changes` mutation via `add_tempo_change`. The note loop's broad
  `except Exception` at `parser_fast.py:157` no longer swallows silently — it
  counts `dropped_note_events` and warns with `last_drop_reason` after the loop
  (`:163-171`). No change since 2026-08-05.
- **Dim 2 — Parallel detector scaling**: `_collect_window_groups`
  (`tracker/pattern_detector_parallel.py:371-390`) is still O(n) hash-bucketing
  per pattern length; `_build_work_chunks` (`:116-146`) still sub-chunks each
  length's start-range toward `self.max_workers * 2`
  (`target_total_chunks = max(len(lengths), self.max_workers * 2)`, `:132`), so
  the fixed-10-task ceiling the base skill prose describes (`#332`, already fixed
  before the 2026-08-05 audit) remains fixed — the skill's Dimension 2 narrative
  describes a pre-#332 shape and should not be re-reported without checking
  `_build_work_chunks` first. `SERIAL_EVENT_THRESHOLD = 200` (`:15,166`)
  short-circuits pool construction for small inputs. `sequence`/`events` still
  ship once per worker via `_init_pattern_worker` into `_WORKER_SEQUENCE`/
  `_WORKER_EVENTS` module globals (`:359-368`), not per-chunk. No change since
  2026-08-05.
- **Dim 3 — Large-file sampling**: all three thresholds (`DETECTOR_MAX_EVENTS=1000`,
  `MAX_PATTERN_EVENTS=15000` in `tracker/pattern_detector.py:16,23`;
  `LARGE_FILE_THRESHOLD_DEFAULT = MAX_PATTERN_EVENTS` in `main.py:44`) remain
  aligned and are all overridable via `get_pattern_detection_caps`
  (`main.py:46-74`) against `config/default_config.yaml:14-16`, unchanged since
  the 2026-07-19 audit fixed the original misalignment (#334).
- **Dim 4 — Inter-stage memory**: `run_full_pipeline` still `del`s `midi_data`
  (both the `--arranger` and legacy branches, `main.py:922,930`) and `mapped`
  (legacy branch, `:939`) once each stage's successor is built — #371's fix
  (merged via PR #400, commit `89bdeb7`, confirmed an ancestor of both this
  branch and `master`) is genuinely in place, unlike #372/#373/#374 below.
- **Dim 5 — Serialization cost**: `run_parse`/`run_map`/`run_frames`/
  `run_detect_patterns` all still write `json.dumps(..., separators=(',', ':'))`
  (`main.py:223,242,251,768`) — compact, not `indent=2`, on every hot
  intermediate. Only `run_benchmark`'s result dump (`main.py:1572`) and the
  benchmark report generator use `indent=2`, which is appropriate for
  human-read output. No change since 2026-08-05.
- **Dim 6 — Benchmark module correctness (import/param correctness only)**:
  `benchmarks/performance_suite.py:18` still imports
  `tracker.parser_fast.parse_midi_to_frames` (the production fast path) and
  `:27,226-227` still constructs `ParallelPatternDetector` with both
  `PATTERN_MIN_LENGTH` and `PATTERN_MAX_LENGTH` imported from `constants` — the
  #262 param-drift half stays fixed and is unaffected by the #372/#373/#374
  closure issue (that issue is about the *baseline/gate*, not module/param
  correctness). `PerformanceProfiler.profile` (`:78-95`) is still a single-exit
  `@contextmanager` — no double `_end_profiling`.
- **Dim 7 — tracemalloc lifecycle**: `_tracemalloc_acquire`/`_tracemalloc_release`
  reference-counting (`utils/profiling.py:27-42`) is unchanged and still routes
  both `profile_memory_usage` and `PerformanceContext` through it (`:223,256,
  344,361`) — no nesting blind spot (#118, holds).
- **Dim 8**: no new redundant-recompute site found beyond #376; the expensive
  per-pattern tempo *analysis* half (#119) remains fixed
  (`analyze_tempo=False` at `main.py:738` and `:987`).

---

## Process note for `/audit-publish` and future dedup passes

This cycle's dedup step (`gh issue view <n> --json closedAt,stateReason,comments`)
caught something the simpler "is it CLOSED?" check in the shared protocol would
have missed: a closed issue whose citing commit is not actually in the tree. The
protocol's existing instruction — *"If CLOSED: verify the fix is in place"* —
already covers this, but "verify" needs to mean `git merge-base --is-ancestor
<cited-sha> HEAD` (or checking the PR that merged it), not just reading the
issue's `state` field or trusting a closing comment. Recommend `/audit-publish`
apply the same check before treating any "Existing: #NNN (CLOSED)" match as a
reason to skip filing.

## Conclusion

Zero genuinely new performance findings this cycle, and zero code regressions —
every performance-relevant source file is byte-identical to the 2026-08-05 audit
pass. The material development is a **dedup-integrity gap**: three issues
(#372, #373, #374) were closed citing commits that were never merged, so the
underlying defects are still live in `master` and in every branch built from it,
identical to their original 2026-07-19 description. #371 (correctly merged),
#375, and #376 remain as previously verified. Recommend reopening #372/#373/#374
(or merging their already-written fix branches) rather than filing new issue
numbers for the same defects.
