# Performance Audit — MIDI2NES

- **Date**: 2026-08-21
- **Scope**: Compile-path performance correctness — parser hot path (Dim 1),
  parallel pattern detector (Dim 2), large-file sampling (Dim 3), inter-stage
  memory (Dim 4), serialization cost (Dim 5), benchmark-harness validity
  (Dim 6), profiling utilities (Dim 7), cross-stage recompute (Dim 8) — plus
  a delta review of everything committed since the 2026-08-07 performance
  audit.
- **Method**: Verified every previously-closed PERF fix against the live tree
  (`master`, HEAD `949f0c6`) with direct reads/greps rather than trusting
  prior report text. Established the code delta since the last performance
  audit via `git log`: only three commits, of which one (`949f0c6`) is
  audit-skill docs only; the two code commits (`8ea7ac3` — song-build
  JUKEBOX_BUILD gate + per-song CODE_8000 reset; `ffccf51` — drum-mapping
  `volume`-key fix) were read in full diff and assessed for performance
  impact. Every core Dim 1–8 file (`tracker/parser_fast.py`,
  `tracker/tempo_map.py`, `tracker/pattern_detector_parallel.py`,
  `tracker/pattern_detector.py`, `benchmarks/performance_suite.py`,
  `benchmarks/run_benchmarks.py`, `utils/profiling.py`,
  `nes/emulator_core.py`, `config/default_config.yaml`) is untouched since
  before the 2026-08-07 audit verified it clean; spot-verification of each
  fix was still performed (details in "Verify-the-fix results" below).
  Deduped against `gh issue list --state all --limit 500` → 304 issues saved
  to `/tmp/audit/issues.json` (note: a plain open-only `gh issue list`
  returns just 2 issues here — nearly the entire PERF history is closed, so
  `--state all` is mandatory for dedup, same caution as the two prior
  reports). Maximum issue number is **#414** — confirming that **none of the
  2026-08-07 audit suite's findings (including PERF-B-01/02/04 below) were
  ever published as GitHub issues**.

## Summary

**No new performance findings.** The two code commits since the last audit
are perf-neutral correctness fixes (constant-time changes: one emitted
`.segment` line per song, a `defaultdict` swap, a dual-key `.get`, and a
gate-condition change), and the entire previously-audited Dim 1–8 surface
remains exactly as the 2026-08-07 audit verified it — every historical PERF
issue (#113, #114, #116–#119, #218, #219, #261, #262, #332–#336, #371–#376)
is still genuinely fixed in the live tree.

The three real findings in this report are **carried forward from the
2026-08-07 report, which was committed to `docs/audits/` but never run
through `/audit-publish`** — no GitHub issue exists for any of them, and all
three were re-verified as still present at current line numbers (the
`song build` code they live in has not changed since `c864426`). They are
re-listed here in full so publishing this report files them.

### Finding counts

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | 2 |
| LOW | 1 |
| **Total** | **3** (all carried forward from AUDIT_PERFORMANCE_2026-08-07, unpublished; re-verified live) |

### Counts per dimension

| Dimension | Findings |
|---|---|
| 1 — Parser hot path | 0 (re-verified clean; even the analysis-variant redundancy is fixed, #335) |
| 2 — Parallel detector scaling | 0 (re-verified clean; chunk ceiling #332, serial guard #333, drop-recovery #106 all in place) |
| 3 — Large-file sampling | 0 (all three caps config-overridable and aligned; #219/#334) |
| 4 — Inter-stage memory | 2 (PERF-B-01, PERF-B-02 — `song build` only, carried forward) |
| 5 — Serialization cost | 0 (compact separators on all four hot intermediates, #116) |
| 6 — Benchmark validity | 0 (fixtures + baseline gate intact; export benchmark exercises the shared `_build_song_bytecode` core) |
| 7 — Profiling utilities | 0 (tracemalloc refcount, `cpu_times()` deltas, seeded MemoryMonitor all intact) |
| 8 — Cross-stage recompute | 1 (PERF-B-04 — fail-late capacity check, carried forward; won't-fix #376 comments intact) |

### Highest-leverage fixes

1. **PERF-B-02 (MEDIUM)** — `run_song_build` holds every song's full frames
   dict (~12–13 MB per 3-minute/5-channel song, measured with `tracemalloc`
   in the prior audit and independently reproduced) simultaneously before
   the single batched `export_song_bank_bytecode` call — ~250 MB for a
   20-song jukebox. Interleaving `_build_song_bytecode` per song (it is
   self-contained apart from the `start_bank` integer) cuts the peak to one
   song's frames.
2. **PERF-B-01 (MEDIUM)** — `SongBank.import_bank` eagerly materializes
   every song's stored `segments` (full raw parsed-event lists) on every
   `song build`, though the build path only ever reads `midi_path` and
   `metadata['order']`.
3. **Publish the backlog** — the highest-leverage *process* fix: the entire
   2026-08-07 audit suite's findings were committed as reports but never
   filed as issues (max issue is #414, predating them). Run
   `/audit-publish` on this report. Secondarily, run `/audit-sync` on
   `.claude/commands/audit-performance/SKILL.md` — its prose still calls
   #262 OPEN, describes the 10-task chunk ceiling, the chunk-drop asymmetry,
   and a hardcoded `LARGE_FILE_THRESHOLD = 10000` as live, and calls the
   analysis-parser redundancy "still true" — all five are fixed in the tree
   (#262/#332/#106/#334/#335), and `949f0c6` updated 13 sibling skill files
   but not this one.

---

## Findings

### PERF-B-01: `song build` deserializes every song's unused stored `segments` payload from the bank JSON
- **Severity**: MEDIUM
- **Dimension**: 4 — Inter-stage memory
- **Location**: `nes/song_bank.py:200-227` (`SongBank.import_bank`, eager `self.songs = data['songs']` at line 227), `nes/song_bank.py:97-110` (`_process_segments` — what `song add` stores), `main.py:940-963` (`run_song_build` reads only `midi_path` / `metadata['order']`)
- **Status**: Existing — AUDIT_PERFORMANCE_2026-08-07 PERF-B-01 (no GitHub issue filed; re-verified live 2026-08-21)
- **Description**: `song add` stores each song's full parsed-event list under
  `songs[name]['segments']` in the bank JSON. `import_bank` JSON-parses and
  materializes all of it unconditionally (`self.songs = data['songs']`,
  line 227 — unchanged by `8ea7ac3`, which only rewrote the class
  docstring). `run_song_build`'s loop (`main.py:961-987`) never touches
  `segments`; it deliberately re-parses each song from its recorded
  `midi_path` because the stored events predate NES channel mapping. Every
  `song build` therefore pays a JSON-parse + object-materialization cost
  proportional to the sum of all songs' raw event counts, for data that is
  immediately unreachable.
- **Evidence**: `grep -n "segments" main.py` inside the `run_song_build`
  region (lines 927-1027) returns nothing; the only per-song fields read are
  `song_data.get('midi_path')` (line 963) and `metadata.get('order', 0)`
  (line 954). `nes/song_bank.py:105-110` shows `segments['events']` is the
  full `parse_midi_to_frames` event list.
- **Impact**: Avoidable multi-MB parse + RSS cost on the hot path of the
  `song build` command, scaling with total bank size. Not
  correctness-affecting.
- **Related**: PERF-B-02 (same command, same "hold more than needed" shape).
- **Suggested Fix**: A metadata-only bank loader (reads `bank_info` plus
  per-song `metadata`/`midi_path`, skips `segments`) used by
  `run_song_build`; or make `segments` lazy behind `get_song_data`.

### PERF-B-02: `run_song_build` holds every song's full frames dict simultaneously before the single batched export call
- **Severity**: MEDIUM
- **Dimension**: 4 — Inter-stage memory
- **Location**: `main.py:960-987` (per-song loop, `songs.append({'frames': frames})` at line 987), `main.py:998` (single batched `export_song_bank_bytecode` call), `exporter/exporter_ca65.py:1102,1613` (`_build_song_bytecode` — self-contained per song apart from `start_bank`)
- **Status**: Existing — AUDIT_PERFORMANCE_2026-08-07 PERF-B-02 (no GitHub issue filed; re-verified live 2026-08-21)
- **Description**: The build loop appends every song's entire frames dict
  (`{channel: {frame_num: {note, volume, ...}}}`, one entry per 1/60 s tick
  per channel) to `songs` before `export_song_bank_bytecode` is called once
  on the complete list. Per the exporter's own design (verified again at
  `exporter_ca65.py:1613` — each `_build_song_bytecode` call consumes only
  its own song's frames plus the scalar `next_bank` carried forward),
  nothing requires all N frames dicts to coexist. The prior audit measured
  ~12.5–13.2 MB per 3-minute/5-channel song's frames dict via `tracemalloc`
  (two independent runs, same order of magnitude), i.e. ~250-265 MB held
  simultaneously for a 20-song jukebox — the feature's headline use case.
  This reintroduces at song granularity the "input outlives its successor"
  pattern that #371/PERF-A-01 deliberately eliminated at stage granularity.
- **Evidence**: `main.py:987` `songs.append({'frames': frames})` inside the
  loop; export at `main.py:998` after the loop; no `del`/streaming between.
  Code unchanged since `c864426` (git log on `main.py`).
- **Impact**: Peak RSS scales linearly with song count × song length. Stays
  MEDIUM per the severity rubric: a typical bank (≤10 short chiptunes) stays
  well under 100 MB — no demonstrated OOM on common input.
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
- **Status**: Existing — AUDIT_PERFORMANCE_2026-08-07 PERF-B-04 (no GitHub issue filed; re-verified live 2026-08-21)
- **Location**: `main.py:961-987` (unconditional full parse loop), `main.py:998-1010` (export raises `ValueError` on overflow; explicit `check_mapper_capacity` at line 1007)
- **Description**: A bank whose combined bytecode can never fit the MMC3
  sequence-bank budget (`MAX_SEQUENCE_BANK`, enforced inside
  `_build_song_bytecode`) still pays the entire N-song
  parse+map+frame-build cost — and holds all N frames dicts per PERF-B-02 —
  before the export/capacity stage can fail. No cheap early estimate gates
  the loop.
- **Evidence**: The parse loop completes for every song before
  `export_song_bank_bytecode` (line 998) or `check_mapper_capacity`
  (line 1007) runs; both are inside the `tempfile.TemporaryDirectory` block
  that opens at line 992.
- **Impact**: Low — the failure is loud and correct, just late. An exact
  early estimate is impossible pre-export (bytecode size depends on
  macro/instrument dedup), hence LOW.
- **Related**: PERF-B-02 — the interleaving fix resolves this for free
  (check the running `next_bank` after each song, failing at the offending
  song instead of after all N).
- **Suggested Fix**: None dedicated; falls out of the PERF-B-02 refactor.

---

## Verify-the-fix results (all pass — no regressions)

Every core file is untouched since the 2026-08-07 audit verified it
(per-file `git log -1`); each fix was still spot-verified live:

- **Dim 1**: `tracker/parser_fast.py` — single shared
  `_parse_frames_and_tempo_map` pass; `dropped_note_events` counter + loud
  post-loop warning (lines 115-169, #124); `tracker/tempo_map.py` bisect
  index (`_build_tempo_index`, O(log T) lookups, #113). The
  analysis-variant (`parse_midi_to_frames_with_analysis`, line 192) no
  longer re-opens the file or rebuilds the tempo map (#335) and is
  test-only — the skill prose calling this "still true, unchanged" is
  stale.
- **Dim 2**: `tracker/pattern_detector_parallel.py` —
  `SERIAL_EVENT_THRESHOLD = 200` inline-serial guard (#333); single-chunk
  pool skip and `pool_workers = min(max_workers, len(chunks))` (#218);
  `_build_work_chunks` sub-chunks each length's start range toward
  `max_workers * 2` tasks with a 2000-start floor (#332 — the 10-task
  ceiling is gone); sequence/events shipped once per worker via the pool
  `initializer` (#114); failed chunks are retried serially in-process and
  any true loss is counted in `failed_subchunks` and surfaced in a
  persistent end-of-run warning (#106) — the chunk-drop asymmetry the skill
  still describes is fixed. Serial fallback and workers share
  `_collect_length_candidates`; deterministic `(-score, start, length)`
  tie-break (#46). The greedy overlap selection is O(total matched cells)
  ≈ O(n·ΣL) — linear, not quadratic.
- **Dim 3**: `MAX_PATTERN_EVENTS = 15000` / `DETECTOR_MAX_EVENTS = 1000`
  (`tracker/pattern_detector.py:16,23`) are per-instance overridable
  (#219) and surfaced in `config/default_config.yaml`
  (`max_events`/`max_pattern_events`/`large_file_threshold`, lines 14-16);
  `main.py:44` aligns `LARGE_FILE_THRESHOLD_DEFAULT = MAX_PATTERN_EVENTS`
  (#334) and it remains advisory-only.
- **Dim 4**: `del midi_data`/`del mapped` in both branches of
  `run_full_pipeline` (`main.py:1346,1365,1374`, #371) and `del frames` in
  `run_detect_patterns` (`main.py:760`).
- **Dim 5**: all four hot intermediates written with
  `separators=(',', ':')` (`main.py:223,242,251,782`, #116); reports keep
  `indent=2` appropriately.
- **Dim 6**: benchmark imports `tracker.parser_fast.parse_midi_to_frames`,
  `ParallelPatternDetector`, and `PATTERN_MIN_LENGTH`/`PATTERN_MAX_LENGTH`
  from `constants` (#117/#262); `profile` is a `@contextmanager` running
  `_end_profiling` exactly once; `benchmarks/fixtures/` holds 3 committed
  `.mid` files and `benchmarks/baseline.json` exists with per-stage medians
  (#372/#373); `compare_to_baseline` skips stages absent from the baseline
  and treats a missing baseline as "nothing to compare" (lines 510-548).
  The `song build` export path needs no separate benchmark stage: the
  benchmarked `export_tables_with_patterns` and the jukebox
  `export_song_bank_bytecode` share the `_build_song_bytecode` hot core
  (`exporter_ca65.py:1500,1613`); the jukebox-only glue is O(songs) table
  emission.
- **Dim 7**: refcounted `_tracemalloc_acquire`/`_tracemalloc_release`
  shared by both profilers (#118); `cpu_percent` computed from
  `cpu_times()` deltas / wall time at both call sites (#374);
  `MemoryMonitor` seeds `_memory_samples` with a start-of-run RSS sample so
  sub-interval work never reports `peak_mb=0` (#336), and the monitor loop
  survives transient sampling errors up to a consecutive-failure cap
  (#375).
- **Dim 8**: `analyze_tempo=False` at both detector construction sites with
  the documented `#376/PERF-A-06 (won't-fix)` comments intact
  (`main.py:741-752,1110,1144`); the events↔frames round-trip remains the
  deliberate trade-off documented there. The double capacity gate
  (`main.py:1007`/`1275` + `nes/project_builder.py:239`) is deliberate,
  documented defense-in-depth (library vs CLI entry, pre- vs
  post-transform music.asm) — two linear passes over music.asm, dwarfed by
  the CC65 assemble that follows; not a finding.

## Delta review (commits since 2026-08-07 audit)

- `8ea7ac3` — one constant `.segment "CODE_8000"` line emitted per
  `_build_song_bytecode` call; `song_count is not None` gate replaces
  `> 1`; docstring updates. Perf-neutral.
- `ffccf51` — `defaultdict` for role scores; dual-key
  `e.get('velocity', e.get('volume', 0))`; drum-track routing now drops
  with a warning instead of stuffing the dpcm slot. All O(1)-per-event;
  perf-neutral.
- `949f0c6` — audit-skill docs only; no source code.

## Process notes

1. **The 2026-08-07 audit suite's findings were never published.** Highest
   issue number is #414, which predates all 12 reports committed in
   `89de10a`. This report re-lists the performance ones so publishing it
   recovers them; the other 11 reports' findings are equally unfiled.
2. **`.claude/commands/audit-performance/SKILL.md` prose has drifted from
   the code** (says #262 is OPEN; describes the 10-task parallelism
   ceiling, the un-recovered chunk drop, `LARGE_FILE_THRESHOLD = 10000`
   hardcoded in `main.py`, and the analysis-parser redundancy as live —
   all fixed via #262/#332/#106/#334/#335). `949f0c6` refreshed 13 sibling
   skill files but not this one. Recommend `/audit-sync` — noted here as a
   process item, not a code finding.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PERFORMANCE_2026-08-21.md
```
