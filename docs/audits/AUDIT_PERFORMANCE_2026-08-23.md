# Performance Audit — MIDI2NES

- **Date**: 2026-08-23
- **Scope**: Compile-path performance correctness — parser hot path (Dim 1),
  parallel pattern detector (Dim 2), large-file sampling (Dim 3), inter-stage
  memory (Dim 4), serialization cost (Dim 5), benchmark-harness validity
  (Dim 6), profiling utilities (Dim 7), cross-stage recompute (Dim 8) — plus
  a delta review of everything committed since the 2026-08-21 performance
  audit.
- **Method**: Diffed every Dim 1–8 file's `git log` against the 2026-08-21
  audit's baseline. Seven files had moved since then (`tracker/parser_fast.py`,
  `tracker/pattern_detector_parallel.py`, `tracker/pattern_detector.py`,
  `benchmarks/run_benchmarks.py`, `utils/profiling.py`, `nes/emulator_core.py`,
  `config/default_config.yaml`); read the full diff of each commit that
  touched them (`2ed6c1c`, `efecc87`, `d1bafed`, `a9a7a21`, `d9feba1`,
  `0a16a93`) and assessed for performance impact rather than trusting commit
  summaries. Re-verified the three carried-forward `song build` findings
  (PERF-B-01/02/04) against current line numbers since `main.py`'s
  `run_song_build` and `nes/song_bank.py`'s `import_bank` were both touched
  by intervening commits (`8ea7ac3`, `934b597`, `a9a7a21`) for unrelated
  reasons. Deduped against `gh issue list --limit 200 --json
  number,title,state,labels` (204 issues at time of dedup) plus a direct
  `gh issue view 262` check on the one PERF issue the skill doc still claims
  is open.

## Summary

**No new performance findings.** Every file touched since the last audit
either has no asymptotic/memory impact (dead-local cleanup, a doc-scope
correctness fix, an O(1)-per-event same-pitch-retrigger fix) or is a genuine
further improvement on top of already-fixed issues:

- **#438** dropped the now-unused `events` payload from the pattern-detector
  worker-pool initializer — the #114 IPC fix (each worker gets `sequence`
  once) no longer also ships a redundant `valid_events` copy per worker.
- **#459** lowered `DETECTOR_MAX_EVENTS` from 1000 → 300, closing the gap the
  2026-08-21 report's Dim 6 verification had already priced at ~26s
  worst-case latency for the sequential fallback detector; 300 keeps it in
  the low single digits of seconds.

The three real findings are again **PERF-B-01, PERF-B-02, PERF-B-04** —
carried forward unchanged from AUDIT_PERFORMANCE_2026-08-07 (repeated in
2026-08-21), still describing the exact same `song build` memory/ordering
shape, still never filed as GitHub issues. Re-verified at their current
(shifted) line numbers below; nothing about them has changed except where
they live in the file.

### Finding counts

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 2 |
| LOW | 1 |
| **Total** | **3** (all carried forward from AUDIT_PERFORMANCE_2026-08-07/08-21, still unpublished; re-verified live) |

### Counts per dimension

| Dimension | Findings |
|---|---|
| 1 — Parser hot path | 0 (re-verified clean; `channel_programs` build-once fix, #492, is correctness-only and O(1) either way) |
| 2 — Parallel detector scaling | 0 (re-verified clean; #438 trims IPC further) |
| 3 — Large-file sampling | 0 (`DETECTOR_MAX_EVENTS` 1000→300 via #459, all three caps still config-overridable and aligned) |
| 4 — Inter-stage memory | 2 (PERF-B-01, PERF-B-02 — `song build` only, carried forward) |
| 5 — Serialization cost | 0 (compact separators intact on all four hot intermediates) |
| 6 — Benchmark validity | 0 (fixtures + baseline gate intact; `max_pattern_length` still matches production; #262 confirmed CLOSED via `gh issue view`) |
| 7 — Profiling utilities | 0 (tracemalloc refcount, `cpu_times()` deltas, seeded `MemoryMonitor` all intact; #465's dead-local cleanup is a no-op change) |
| 8 — Cross-stage recompute | 1 (PERF-B-04 — fail-late capacity check, carried forward; won't-fix #376 comments intact) |

### Highest-leverage items

1. **PERF-B-02 (MEDIUM)** — `run_song_build` still holds every song's full
   frames dict simultaneously before the single batched
   `export_song_bank_bytecode` call — ~12–13 MB per 3-minute/5-channel song
   (measured in the 2026-08-07 audit), ~250 MB for a 20-song jukebox.
2. **PERF-B-01 (MEDIUM)** — `SongBank.import_bank` still eagerly
   materializes every song's stored `segments` (full raw parsed-event lists)
   on every `song build`, though the build path only ever reads `midi_path`
   and `metadata['order']`.
3. **Publish the backlog** — same process gap as the last two reports: these
   three findings have now survived three consecutive performance audits
   (2026-08-07, 2026-08-21, this one) without ever becoming a GitHub issue.
   Run `/audit-publish` on this report. Secondarily, `/audit-sync` on
   `.claude/commands/audit-performance/SKILL.md`: it still marks **PERF-11
   (#262) as OPEN** (confirmed CLOSED via `gh issue view 262`, and its fix —
   `benchmarks/performance_suite.py:242-243` passing
   `max_pattern_length=PATTERN_MAX_LENGTH` — has been in place since before
   the 2026-08-21 audit verified it) and Dimension 2's prose still describes
   a flat **"10 tasks... a fixed task count regardless of cores"** chunking
   ceiling that `#332`'s dynamic `_build_work_chunks` (sub-chunking each
   pattern length toward `max_workers * 2`) replaced before the 2026-08-21
   audit as well. `d9feba1` touched this same SKILL.md file two days ago
   (only to bump one number, `DETECTOR_MAX_EVENTS` 1000→300) without fixing
   either of these two long-standing stale claims — a `/audit-sync` pass
   would resolve both in one edit.

---

## Findings

### PERF-B-01: `song build` deserializes every song's unused stored `segments` payload from the bank JSON
- **Severity**: MEDIUM
- **Dimension**: 4 — Inter-stage memory
- **Location**: `nes/song_bank.py:244` (`import_bank`'s `json.loads(path.read_text())`), `nes/song_bank.py:290` (eager `self.songs = songs`), `nes/song_bank.py:167` (`add_song` stores `'segments': segments`, what `song add` writes), `main.py:1033-1035` (`run_song_build`'s per-song loop reads only `midi_path`)
- **Status**: Existing — AUDIT_PERFORMANCE_2026-08-07 PERF-B-01, re-carried in AUDIT_PERFORMANCE_2026-08-21 (no GitHub issue filed; re-verified live 2026-08-23)
- **Description**: `song add` stores each song's full parsed-event list
  under `songs[name]['segments']` in the bank JSON (`add_song`,
  `nes/song_bank.py:133-167`). `import_bank` JSON-parses and materializes
  all of it unconditionally — `self.songs = songs` at line 290, unchanged
  since the last audit's line 227 (the file grew by ~63 lines from the
  intervening per-entry-validation and docstring commits, but the
  eager-load shape itself did not change). `run_song_build`'s per-song loop
  (`main.py:1032-1059`) never reads `segments`; it deliberately re-parses
  each song from its recorded `midi_path` because the stored events predate
  NES channel mapping. Every `song build` therefore pays a JSON-parse +
  object-materialization cost proportional to the sum of all songs' raw
  event counts, for data that is immediately unreachable.
- **Evidence**: `grep -n "segments" main.py` inside the `run_song_build`
  region (`main.py:999-1117`) returns nothing; the only per-song fields read
  are `song_data.get('midi_path')` (line 1035) and
  `song_data['metadata'].get('order', 0)` (line 1026).
  `nes/song_bank.py:126-131` shows `segments` is built from the full
  `parse_midi_to_frames` event list via `_process_segments`.
- **Impact**: Avoidable multi-MB parse + RSS cost on the hot path of the
  `song build` command, scaling with total bank size. Not
  correctness-affecting.
- **Related**: PERF-B-02 (same command, same "hold more than needed"
  shape). TD-33 (#468, OPEN) is a different concern — capacity-model
  accuracy, not this memory shape.
- **Suggested Fix**: A metadata-only bank loader (reads `bank_info` plus
  per-song `metadata`/`midi_path`, skips `segments`) used by
  `run_song_build`; or make `segments` lazy behind a getter.

### PERF-B-02: `run_song_build` holds every song's full frames dict simultaneously before the single batched export call
- **Severity**: MEDIUM
- **Dimension**: 4 — Inter-stage memory
- **Location**: `main.py:1032-1059` (per-song loop, `songs.append({'frames': frames})` at line 1059), `main.py:1083` (single batched `export_song_bank_bytecode` call), `exporter/exporter_ca65.py` (`_build_song_bytecode` — self-contained per song apart from the running `start_bank`; now shares a common `_emit_bytecode_preamble` with the single-song path per #466, which does not change this per-song self-containment)
- **Status**: Existing — AUDIT_PERFORMANCE_2026-08-07 PERF-B-02, re-carried in AUDIT_PERFORMANCE_2026-08-21 (no GitHub issue filed; re-verified live 2026-08-23)
- **Description**: The build loop appends every song's entire frames dict
  (`{channel: {frame_num: {note, volume, ...}}}`, one entry per 1/60s tick
  per channel) to `songs` before `export_song_bank_bytecode` is called once
  on the complete list. Nothing requires all N frames dicts to coexist —
  `_build_song_bytecode` consumes only its own song's frames plus the
  scalar `next_bank` carried forward. The 2026-08-07 audit measured
  ~12.5–13.2 MB per 3-minute/5-channel song's frames dict via
  `tracemalloc`, i.e. ~250 MB held simultaneously for a 20-song jukebox —
  the feature's headline use case. This reintroduces at song granularity
  the "input outlives its successor" pattern that #371/PERF-A-01
  deliberately eliminated at pipeline-stage granularity.
- **Evidence**: `main.py:1059` `songs.append({'frames': frames})` inside the
  loop; export at `main.py:1083` after the loop ends; no `del`/streaming
  between. The #466 preamble-dedup refactor (`a9a7a21`) touched only
  `exporter/exporter_ca65.py`'s shared preamble emission, not this loop or
  the export call site.
- **Impact**: Peak RSS scales linearly with song count × song length. Stays
  MEDIUM per the severity rubric: a typical bank (≤10 short chiptunes)
  stays well under 100 MB — no demonstrated OOM on common input.
- **Related**: #371/PERF-A-01 (CLOSED — same category, different
  granularity; not a regression of it). PERF-B-04 compounds it.
- **Suggested Fix**: Interleave: call `_build_song_bytecode` immediately
  after each song's frames are built, accumulate only the returned asm
  lines/`channel_start_banks`/`next_bank`, `del frames` per iteration; have
  `export_song_bank_bytecode` assemble header/footer around pre-built
  bodies. Output is unchanged by the exporter's own self-containment
  guarantee.

### PERF-B-04: Song-bank capacity overflow is detected only after all N songs are fully parsed, mapped, and held in memory
- **Severity**: LOW
- **Dimension**: 8 — Cross-stage recompute (fail-late ordering) / 4 — memory
- **Status**: Existing — AUDIT_PERFORMANCE_2026-08-07 PERF-B-04, re-carried in AUDIT_PERFORMANCE_2026-08-21 (no GitHub issue filed; re-verified live 2026-08-23)
- **Location**: `main.py:1032-1059` (unconditional full parse/map loop),
  `main.py:1083` (`export_song_bank_bytecode`, raises `ValueError` on
  bytecode-bank overflow), `main.py:1379` (`check_mapper_capacity` inside
  the shared `build_and_validate_rom` helper, called from `run_song_build`
  at `main.py:1093-1096`)
- **Description**: A bank whose combined bytecode can never fit the MMC3
  sequence-bank budget still pays the entire N-song parse+map+frame-build
  cost — and holds all N frames dicts per PERF-B-02 — before either the
  exporter's own overflow check or the post-build `check_mapper_capacity`
  gate can fail. No cheap early estimate gates the loop. `#467`'s refactor
  (`934b597`, further tidied by `a9a7a21`) changed *how* the failure path
  reports and cleans up (reusing `build_and_validate_rom`'s
  backup/restore + typed-exception contract instead of a bespoke inline
  sequence) but did not move the capacity check earlier — it is still the
  last thing that runs, after every song's data is already resident.
- **Evidence**: The parse loop (`main.py:1032-1059`) completes for every
  song before `export_song_bank_bytecode` (line 1083) or
  `check_mapper_capacity` (line 1379, inside `build_and_validate_rom`) run;
  both are inside the `tempfile.TemporaryDirectory` block opened at line
  1077.
- **Impact**: Low — the failure is loud and correct, just late. An exact
  early estimate is impossible pre-export (bytecode size depends on
  macro/instrument dedup), hence LOW.
- **Related**: PERF-B-02 — the interleaving fix resolves this for free
  (check the running `next_bank` after each song, failing at the offending
  song instead of after all N).
- **Suggested Fix**: None dedicated; falls out of the PERF-B-02 refactor.

---

## Verify-the-fix results (all pass — no regressions)

- **Dim 1**: `2ed6c1c` moved `channel_programs = {}` out of the per-track
  loop in `tracker/parser_fast.py` to fix a cross-track program-change
  correctness bug (#492) — a pure constant-factor change (one dict
  allocation instead of N), not a complexity change; the single
  two-pass/bisect-index shape (#113) is untouched. `parse_midi_to_frames`
  is still the sole front-end (`parser.py` removed, #346).
- **Dim 2**: `efecc87` (#438) dropped `_WORKER_EVENTS` and the now-unused
  `events` param from `_init_pattern_worker`/`initargs` — since #332's
  hash-grouping rewrite, workers only bucket window positions
  (`_WORKER_SEQUENCE`-only); candidate selection runs in the parent
  process against its own `valid_events`, so shipping `events` to every
  worker was dead IPC weight. This is a further reduction on top of #114,
  not a reintroduction of it. `SERIAL_EVENT_THRESHOLD = 200` inline-serial
  guard (#333) and `_build_work_chunks`'s dynamic `max_workers * 2` target
  chunk count (#332) both still present (`tracker/pattern_detector_parallel.py:15,116-146`)
  — the 10-task ceiling the skill doc still describes is confirmed gone.
- **Dim 3**: `d9feba1` (#459) lowered `DETECTOR_MAX_EVENTS` 1000 → 300
  (`tracker/pattern_detector.py:36`, `config/default_config.yaml`) after
  re-measuring the sequential detector's worst-case latency at ~26s for
  n=1000 vs ~2.5s for n=300, closing a stall that a prior fix (`e645cc9`)
  had only ever landed on an unmerged branch. `main.py:56`
  (`LARGE_FILE_THRESHOLD_DEFAULT = MAX_PATTERN_EVENTS`) still keeps all
  three caps aligned and config-overridable (`main.py:69-85`).
  `d1bafed` (#495) deleted the dead, never-called `_optimize_patterns`
  method from `tracker/pattern_detector.py` — no live code path used it,
  so no latency or memory change; `detect_patterns`'s own inline selection
  (the code that actually runs) was untouched, and lossless round-trip was
  re-verified in that same commit's test run.
- **Dim 4**: `del midi_data`/`del mapped` in both branches of
  `run_full_pipeline` (`main.py:1453,1472,1481`, #371, now additionally
  pinned by `TestRunFullPipelineMemoryOverhead`'s source-inspection tests
  per the comment at `main.py:1136-1142`) and `del frames` in
  `run_detect_patterns` (`main.py:817`) both still present.
- **Dim 5**: all four hot intermediates still written with
  `separators=(',', ':')` (`main.py:256,275,286,845`, #116).
- **Dim 6**: `gh issue view 262` confirms **CLOSED**;
  `benchmarks/performance_suite.py:240-243` still constructs
  `ParallelPatternDetector(..., min_pattern_length=PATTERN_MIN_LENGTH,
  max_pattern_length=PATTERN_MAX_LENGTH)`, matching production's 3–12
  range rather than the old inherited-default 3–32. Fixtures/baseline gate
  (`benchmarks/fixtures/`, `benchmarks/baseline.json`) untouched since the
  last audit verified them. `a9a7a21`'s `run_batch_benchmarks` dead-`results=`
  cleanup in `benchmarks/run_benchmarks.py` is a no-op (the call was already
  used only for its side effects).
- **Dim 7**: `a9a7a21`'s `except Exception:` (drop unused `as e`) in
  `utils/profiling.py:337` is a no-op — the `except` block still re-raises
  unconditionally. Refcounted tracemalloc acquire/release (#118),
  `cpu_times()`-delta CPU percent (#374), and seeded `MemoryMonitor`
  (#336/#375) all unchanged and unverified-as-regressed since no code in
  their call paths moved.
- **Dim 8**: `0a16a93`'s same-pitch-retrigger fix
  (`nes/emulator_core.py:71-76,106-129,157-159`, #481) adds two O(1)
  per-event bookkeeping variables (`prev_end_frame`/`prev_note_pitch`) and
  one extra comparison per event inside the existing single pass over
  `events` — no new loop, no complexity change. The `#376/PERF-A-06
  (won't-fix)` comments and the events↔frames round-trip trade-off remain
  as documented and unchanged.

## Delta review (commits since 2026-08-21 audit)

- `2ed6c1c` (#492/#493) — `channel_programs` build-once fix + arranger
  audit-doc corrections. Perf-neutral (Dim 1, see above).
- `efecc87` (#435-#438) — patterns-domain fixes; `#438` is a genuine
  further IPC reduction on the parallel detector (Dim 2).
- `d1bafed` (#495/#497/#498) — dead-code removal + doc-line resync;
  perf-neutral.
- `a9a7a21` (#465-#467) — dead-local cleanup in `benchmarks/run_benchmarks.py`
  / `utils/profiling.py` (no-op); `exporter/exporter_ca65.py` preamble
  dedup (verified byte-identical output per the commit's own testing, not
  independently re-verified here as it's an exporter-correctness concern,
  cross-ref `audit-exporters`); song-build test-gap fill only.
- `d9feba1` (#459) — `DETECTOR_MAX_EVENTS` 1000→300, a genuine Dim 3/6
  latency-bound improvement (see above). Also touched this SKILL.md file
  but only to update that one number — the two other stale claims
  (`#262` OPEN, the 10-task chunk ceiling) it left untouched are noted
  under "Highest-leverage items" above.
- `0a16a93` (#481/#482) — same-pitch-retrigger + DPCM sentinel fixes;
  O(1)-per-event addition, perf-neutral (Dim 8, see above).
- `a63be2d` — on-screen volume-bar visualizer (`nes/visualizer.py`,
  `--visualizer` build mode). This is 6502-runtime/ROM-build tooling, not
  part of the Python compile-path surface this audit covers (parse,
  detect, memory, serialization, benchmarking, profiling) — out of scope,
  not reviewed here.

## Process notes

1. **PERF-B-01/02/04 have now survived three consecutive performance
   audits (2026-08-07, 2026-08-21, this one) unpublished.** Recommend
   `/audit-publish` on this report to finally file them.
2. **`.claude/commands/audit-performance/SKILL.md` prose is still stale**
   in two specific spots, despite being edited two days ago (`d9feba1`):
   Dimension 6 still marks PERF-11/#262 as OPEN (confirmed CLOSED), and
   Dimension 2 + the Skeptical Checklist still describe a flat "10 tasks"
   parallel-detector chunk ceiling that #332's dynamic
   `max_workers * 2`-target chunking replaced before the 2026-08-21 audit.
   Recommend `/audit-sync` to close both in one pass — worth flagging
   explicitly since the file *was* touched in the interim without fixing
   either.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PERFORMANCE_2026-08-23.md
```
