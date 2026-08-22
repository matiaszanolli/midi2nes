# Pattern Detection & Compression Audit — 2026-08-21

## Summary

**Round-trip result: LOSSLESS CONFIRMED — empirically re-verified today with a fresh
43-assertion harness (`/tmp/audit/roundtrip_test.py`), not re-read from a prior report.**

The harness ran both real producers end to end and dereferenced **every** persisted
`positions`/`references` entry back into the source sequence, comparing window content
against the stored `events` element-by-element, plus a full-sequence reconstruction diff:

1. `EnhancedPatternDetector.detect_patterns` on four fixtures — simple exact repeats,
   a transposed-decoy sequence (the #168/#170 defect class: 3 exact repeats of a base motif
   interleaved with 3 exact repeats of its +5-semitone transposition), a self-similar run
   (period < pattern length, the PAT-04/#170 probe), and a 720-event mixed sequence that
   triggers the internal `DETECTOR_MAX_EVENTS` cap check: **0 mismatches**, no frame
   double-claimed by two retained patterns, full reconstruction identical to the original.
2. `ParallelPatternDetector.detect_patterns` on both of its paths — the
   sub-`SERIAL_EVENT_THRESHOLD` serial path *and* a real 720-event
   `ProcessPoolExecutor` run (10 work chunks, multi-length, merged sub-chunk groups):
   **0 mismatches**, `references == positions` for every pattern,
   `len(events) == length` for every pattern.
3. Edge cases: empty input, 2-event input, and `max_pattern_length < min_pattern_length`
   all return the correct empty 4-key envelope on both detectors with no crash or
   garbage range.
4. **#365/PAT-A fix re-verified**: a constructed candidate with 1 exact occurrence +
   2 transposed near-occurrences was skipped entirely (nothing with
   `len(positions) < MIN_PATTERN_OCCURRENCES` persisted) and did **not** block the
   genuinely-repeating shorter exact pattern in the same sequence (persisted at
   `[15, 19, 23]` with correct content).

`export_tables_with_patterns` (`exporter/exporter_ca65.py:1447-1459`) still documents and
implements `references` as **not consumed** — `patterns` truthiness remains the sole switch
between direct-frame export and the MMC3 macro-bytecode serializer (#4). Both pipeline
entry points still pass the real `references` dict (`main.py:1222-1229` and
`main.py:697-704`), so the #379 symmetry holds.

**Code-change delta since the prior audit** (`docs/audits/AUDIT_PATTERNS_2026-08-07.md`):
`tracker/pattern_detector.py`, `tracker/pattern_detector_parallel.py`, and
`tracker/loop_manager.py` are **unchanged** (last commits `24e51d2`/`435f8d2`/`d150fe3`,
all pre-2026-08-07). `main.py` and `exporter/exporter_ca65.py` changed only for the
jukebox feature (`c864426`, `8ea7ac3`, #30/F-13), which bypasses pattern detection
entirely (`run_song_build` never calls a detector). All previously fixed defects in this
subsystem (#168, #170, #171, #172, #173, #103, #104, #106, #114, #257, #258, #302, #311,
#365, #366, #379) were spot-re-verified in code and/or empirically — **no regressions**.
All test pins are present: `TestPositionsAreExactOnly` (`tests/test_patterns.py:1318`),
`test_pattern_positions_format` / `test_pattern_positions_exclude_transposed_decoy`
(`tests/test_pattern_integration.py:123`, `:158`), the ThreadedPatternDetector-stays-gone
regression test (`tests/test_patterns.py:1282-1288`), and the parallel
`variation_count == 0` pins (`tests/test_patterns.py:1128`, `:1538`).

**Finding counts:** CRITICAL 0 · HIGH 0 · MEDIUM 2 · LOW 5 · **Total 7**
(4 NEW, 3 carried forward unfixed from the 2026-08-07 report — none of the three were
ever published as GitHub issues).

**3 highest-leverage fixes:**
1. **PAT-2026-08-21-1 (MEDIUM)** — the `--no-patterns` stub counts the `dpcm_sample_map`
   side table as "events", inflating the banner's `total_events`/sizes on every drum song;
   one-line guard, same trap #261 already fixed in `frames_to_events`.
2. **PAT-2026-08-21-2 (MEDIUM)** — `parse_midi_to_frames_with_analysis` feeds
   sampled-space pattern positions to loop detection over the *full* event list; any
   >1000-note track silently gets misaligned loop points and tempos in its metadata.
3. **PAT-2026-08-21-4 (LOW)** — stop shipping the never-read `_WORKER_EVENTS` payload
   (up to 15,000 event dicts pickled into every worker process for nothing).

---

## Findings

### PAT-2026-08-21-1: `--no-patterns` stub counts the `dpcm_sample_map` side table as events, inflating banner stats on drum songs
- **Severity**: MEDIUM
- **Dimension**: Dimension 4 (Compression-Ratio & Stats Accuracy) / Dimension 2 (schema)
- **Location**: `main.py:1084` (`detect_patterns_or_direct_export`, direct-export stub)
- **Status**: NEW
- **Description**: The stub computes
  `direct_size = sum(len(ch) for ch in frames.values())` and reports it as
  `original_size`, `compressed_size`, and `total_events`. But `frames` is not purely a
  `{channel: {frame: ...}}` dict: when a song has DPCM drums,
  `NESEmulatorCore.process_all_tracks` adds a `dpcm_sample_map` side table
  (`nes/emulator_core.py:241-247`, a `{str(dense_id): catalog_id}` map). `len()` of that
  map (the distinct-sample count) is silently added to the "event" totals. This is exactly
  the iteration trap #200/#261 fixed by adding the `DPCM_SAMPLE_MAP_KEY` skip to the
  shared `frames_to_events` extractor (`nes/emulator_core.py:253-267`) — the stub site
  does its own `frames.values()` sweep and never got the guard (it doesn't crash like the
  #261 benchmark case did, because it only calls `len()`, so the inaccuracy is silent).
  Both real detector paths go through `frames_to_events` and are unaffected.
- **Evidence**: `main.py:1084-1096` builds the stats from `direct_size`; the success
  banner then prints `Pattern coverage: 0.0% of {total_events:,} events`
  (`main.py:1411-1413`) — for a drum song in `--no-patterns` mode, `total_events`
  over-counts by the number of `dpcm_sample_map` entries, and `original_size`/
  `compressed_size` no longer mean "frame events".
- **Impact**: Misleading (cosmetic) stats on every `--no-patterns` build of a song with
  percussion — the exact defect class the severity table floors at MEDIUM ("Reported
  compression/stat inaccurate"). No effect on emitted ROM bytes. Magnitude is small
  (distinct-sample count, typically < 10), but the stub's numbers stop matching what the
  detectors would report for the identical `frames` dict, drifting the #104-unified schema
  in value semantics if not in keys.
- **Related**: #261 (PERF-10, same trap in benchmark), #200/D-14, #104 (stub schema
  unification), #17 (banner conventions).
- **Suggested Fix**: Compute
  `direct_size = sum(len(ch) for name, ch in frames.items() if name != DPCM_SAMPLE_MAP_KEY)`
  (import the constant from `nes/emulator_core.py`), or reuse `len(frames_to_events(frames))`.

### PAT-2026-08-21-2: `parse_midi_to_frames_with_analysis` feeds sampled-space pattern positions to loop detection over the full event list
- **Severity**: MEDIUM
- **Dimension**: Dimension 9 (Loop Detection Correctness) / Dimension 7 (sampling)
- **Location**: `tracker/parser_fast.py:213-239`; interacts with
  `tracker/pattern_detector.py:219-222` (internal sampling) and
  `tracker/loop_manager.py:138-139` (per-event tempo read)
- **Status**: NEW (the *path's* production-dead-but-tested status is Existing #97/#346 and
  is not the finding; this is a distinct latent correctness bug on that path)
- **Description**: `parse_midi_to_frames_with_analysis` runs
  `pattern_detector.detect_patterns(note_on_events)` and then
  `loop_manager.detect_loops(note_on_events, pattern_data['patterns'])` with the **full**
  `note_on_events` list. But `EnhancedPatternDetector` (constructed here with the default
  `max_events=DETECTOR_MAX_EVENTS=1000`) uniformly samples any larger input internally
  (`pattern_detector.py:219-222`), so every persisted `positions` value is an index into
  the **sampled** sequence. For a track with more than 1000 note-ons, the loop points
  (`loop_start = positions[-2]`, `loop_end = positions[-1] + length`) land at sampled-space
  indices, while `EnhancedLoopManager.detect_loops` dereferences them against the full
  list — `events[loop_info['start']]['tempo']` reads a completely different event's tempo
  (loop_manager.py:138-139), and the emitted `loops`/`jump_table` metadata frames are
  wrong relative to the events the caller holds. The detector even exposes `was_sampled`
  for exactly this labeling purpose (#312/PAT-11), and this caller ignores it. No
  index-out-of-range occurs (sampled indices are always < full length), so the
  misalignment is silent. `tracker/parser.py:84-100` (the production-dead full parser,
  #346/TD-26) has the same shape.
- **Evidence**: Call chain: `parser_fast.py:222` (`detect_patterns(note_on_events)`) →
  `pattern_detector.py:219-222` (sampling when `len > max_events`) → positions persisted
  in sampled index space → `parser_fast.py:225-227`
  (`detect_loops(note_on_events, pattern_data['patterns'])`) → `loop_manager.py:138-139`
  (full-list indexing with sampled-space indices).
- **Impact**: Latent — the function is off the default pipeline (only
  `run_full_pipeline` → `parse_midi_to_frames` is live; callers of the `_with_analysis`
  variant are tests and its own `__main__` block, all with small inputs today). Any future
  or external caller handing it a real-sized MIDI track (>1000 note-ons is common) gets
  loop metadata whose `start`/`end`/`tempo_state` silently mean something different than
  the events they accompany — the "hands the next stage data that means something else"
  class, discounted from HIGH because no live consumer exists.
- **Related**: #97 (path documented-and-kept), #346/TD-26, #312/PAT-11 (the `was_sampled`
  flag this caller ignores), #345/TEMPO-16 (the loop manager's tempo read this
  misalignment now feeds wrong indices into), PAT-2026-08-21-3.
- **Suggested Fix**: In `parse_midi_to_frames_with_analysis`, either construct the
  detector with `max_events=len(note_on_events)` (no sampling; this path is explicitly the
  "expensive analysis" variant), or check `pattern_detector.was_sampled` after detection
  and skip/flag loop detection when positions are not in full-event space.

### PAT-2026-08-21-3: `_analyze_pattern_tempo` still passes event indices to `get_tempo_at_tick` as ticks — the un-fixed sibling of #345
- **Severity**: LOW
- **Dimension**: Dimension 9 (loop/tempo metadata correctness)
- **Location**: `tracker/pattern_detector.py:479-507` (`_analyze_pattern_tempo`),
  `:509-528` (`_analyze_variation_tempos`)
- **Status**: NEW (#345/TEMPO-16 fixed this exact unit mismatch in
  `EnhancedLoopManager` by reading each event's stamped `tempo`; this sibling site was
  left as-is)
- **Description**: `_analyze_pattern_tempo` calls
  `self.tempo_map.get_tempo_at_tick(tick) for tick in range(pos, pos + length)` where
  `pos` is a pattern position — an index into the detection event sequence, not a MIDI
  tick. On every pipeline path this is harmless by construction (all live call sites pass
  `analyze_tempo=False` or a constant single-tempo map, as prior TEMPO audits confirmed).
  But on the one path where `analyze_tempo` defaults to True **and** the tempo map is real
  — `parse_midi_to_frames_with_analysis` (`tracker/parser_fast.py:208`) — a multi-tempo
  song gets `base_tempo`/`tempo_info` computed from "tempo at tick ≈ small event index",
  i.e. effectively always the song's initial tempo, and those wrong values are registered
  into the real map via `add_pattern_tempo`. The events already carry a stamped `tempo`
  field (`parser_fast.py:155`) — the same data source the #345 fix switched the loop
  manager to.
- **Evidence**: `pattern_detector.py:481-486` (`get_tempo_at_tick(tick)` over
  `range(pos, pos + length)`); contrast with the fixed pattern at
  `loop_manager.py:127-139` whose comment explicitly names the unit mismatch.
- **Impact**: Wrong per-pattern tempo metadata (`tempo_map.pattern_tempos`) on the
  analysis path only; nothing live consumes `pattern_tempos`
  (`optimize_pattern_tempos` is CLI-unreachable per prior TEMPO audits), hence LOW rather
  than MEDIUM. It is, however, the last remaining instance of the #345 defect class.
- **Related**: #345/TEMPO-16 (fixed sibling), #376/PERF-A-06 (won't-fix context for the
  constant analysis maps), PAT-2026-08-21-2.
- **Suggested Fix**: Mirror the #345 fix: read `events[i]['tempo']` (falling back to
  `get_tempo_at_tick` only when the key is absent), or drop the tempo-analysis pass
  entirely now that every live call site disables it.

### PAT-2026-08-21-4: `_WORKER_EVENTS` is shipped to every worker process but never read — dead initializer payload since #332
- **Severity**: LOW
- **Dimension**: Dimension 6 (Multiprocessing Safety / pool hygiene)
- **Location**: `tracker/pattern_detector_parallel.py:198-202` (`initargs`), `:359-368`
  (`_WORKER_EVENTS` global + `_init_pattern_worker`), `:463-472` (worker reads only
  `_WORKER_SEQUENCE`)
- **Status**: NEW
- **Description**: The pool initializer still stashes both `sequence` and `valid_events`
  into worker globals, but the #332/PERF-12 rewrite changed the worker entry point from
  the old candidate-building `_detect_patterns_worker` to `_detect_window_groups_worker`,
  which only buckets window positions — it reads `_WORKER_SEQUENCE` and nothing else.
  Candidate selection (the only step that needs `events`, in
  `_select_candidates_from_groups`) now runs in the **parent** process
  (`:244-253`) with the parent's `valid_events`. `grep -n _WORKER_EVENTS` confirms the
  global is assigned (`:360`, `:366-368`) and never read anywhere. So up to
  `MAX_PATTERN_EVENTS` = 15,000 event dicts are pickled and unpickled once per spawned
  worker (up to `cpu_count()-1` processes) purely as dead weight.
- **Evidence**: `_detect_window_groups_worker` (`:463-472`) touches only
  `_WORKER_SEQUENCE`; no other function references `_WORKER_EVENTS`.
- **Impact**: Wasted per-worker spawn cost (memory + pickle time, most visible under the
  `spawn` start method on macOS/Windows) and a drift trap: the module comment (`:356-358`)
  and prior audit reports describe the events as live shared worker data, which no longer
  matches the code. No correctness impact — verified by today's clean pool-path
  round-trip.
- **Related**: #332/PERF-12 (the rewrite that orphaned it), #114 (original initializer
  design), #218.
- **Suggested Fix**: Drop `valid_events` from `initargs`, `_init_pattern_worker`'s
  signature, and the `_WORKER_EVENTS` global; update the `:356-358` comment.

### PAT-2026-08-21-5: `detect-patterns` subcommand's persisted JSON still omits the documented `variations` key
- **Severity**: LOW
- **Dimension**: Dimension 2 (`pattern_result` Schema Integrity)
- **Location**: `main.py:776-781` (`run_detect_patterns`'s `output` dict)
- **Status**: Existing — carried forward unfixed from
  `docs/audits/AUDIT_PATTERNS_2026-08-07.md` (PAT-2026-08-07-A); never published as a
  GitHub issue
- **Description**: The detector returns the 4-key envelope, but the on-disk JSON the
  subcommand writes keeps only `patterns`/`references`/`stats`, dropping `variations` —
  while `_audit-common.md`'s documented detect-patterns contract promises all four.
  Distinct from the fixed #258/PAT-09 (the in-memory `--no-patterns` stub). Harmless
  today: the only consumer (`run_export` via `load_json_stage`) requires just
  `patterns`/`references`.
- **Evidence**: `output = {'patterns': ..., 'references': ..., 'stats': ...}` at
  `main.py:777-781`; `pattern_result['variations']` is discarded.
- **Impact**: On-disk stage artifact diverges from the documented contract; a future
  consumer reading `variations` from the file KeyErrors only on this path.
- **Related**: #258/PAT-09, #104, prior report PAT-2026-08-07-A.
- **Suggested Fix**: Add `'variations': pattern_result['variations']` to the persisted
  dict (or amend the documented contract to 3 keys on disk).

### PAT-2026-08-21-6: `PatternDetector._optimize_patterns` remains dead code with an unshared, diverging scoring formula
- **Severity**: LOW
- **Dimension**: Dimension 8 (match semantics) / tech-debt
- **Location**: `tracker/pattern_detector.py:369-406`
- **Status**: Existing — carried forward unfixed from
  `docs/audits/AUDIT_PATTERNS_2026-08-07.md` (PAT-2026-08-07-B); never published as a
  GitHub issue
- **Description**: `_optimize_patterns` is never called by `detect_patterns` (which does
  its own selection inline at `:305-346`) or by any live code; it duplicates the
  overlap-selection idea with a private score
  (`(exact + 0.8·variations) · length`) that ignores the shared `score_pattern` (#103)
  and the #365 exact-occurrence gate — a drift trap for anyone who assumes it participates
  in selection.
- **Evidence**: `grep -rn "_optimize_patterns"` matches only its definition and tests.
- **Impact**: None at runtime; maintainability/drift risk only.
- **Related**: #103, #365/PAT-A, #131/TD-03 (prior copy-paste drift in this file), prior
  report PAT-2026-08-07-B.
- **Suggested Fix**: Delete it (with its test) or rewrite it on top of `score_pattern`
  with a comment stating who calls it.

### PAT-2026-08-21-7: audit-patterns SKILL.md line references have drifted further from the live tree
- **Severity**: LOW
- **Dimension**: Meta (doc-rot in the audit skill itself)
- **Location**: `.claude/commands/audit-patterns/SKILL.md` (Dimensions 1-9 line
  citations); also `.claude/commands/_audit-common.md`'s detect-patterns contract line
  (still says the `--no-patterns` stub reports `compression_ratio` **1.0**, contradicting
  the fixed `0` convention it elsewhere endorses, #17/#104)
- **Status**: Existing — superset of PAT-2026-08-07-C from
  `docs/audits/AUDIT_PATTERNS_2026-08-07.md`; never published as a GitHub issue
- **Description**: Confirmed-stale references as of today: `PATTERN_MIN_LENGTH`/
  `PATTERN_MAX_LENGTH` cited at *main.py:36-37* → actually `constants.py:18-19`;
  exporter contract cited at *exporter/exporter_ca65.py:962-971* → actually
  `exporter/exporter_ca65.py:1447-1459`; the pipeline fallback cited at *main.py:827-853*
  → actually `main.py:1134-1160`; the fallback re-trim at *main.py:844* → `main.py:1151`;
  banner sites *main.py:655/:1199/:871/:1048* → `main.py:787/:1409/:1091/:1411`; the
  ThreadedPatternDetector regression test at *tests/test_patterns.py:1184-1190* →
  `tests/test_patterns.py:1282-1288`; most `tracker/pattern_detector.py` internals shifted
  (~+39 lines: `score_pattern` :41→`:52`, `detect_patterns` :396→`:424`,
  `compress_patterns` :799-829→`:838-868`, `_hash_pattern` :831-841→`:870-880`,
  `calculate_compression_stats` :843-891→`:882-930`, selection loop :305-323→`:311-346`,
  `_find_pattern_matches` :320-338→`:348-367`) and `tracker/pattern_detector_parallel.py`
  internals shifted (~+70 lines: `_empty_result` :274-283→`:344-353`, `_select_best_patterns`
  :216-254→`:286-324`, `_collect_length_candidates` :301-368→`:437-460`, initializer
  :289-298→`:359-368`). The stale `LARGE_FILE_THRESHOLD = 10000` at *main.py:818* is now
  `LARGE_FILE_THRESHOLD_DEFAULT = MAX_PATTERN_EVENTS` (15000) at `main.py:44` (#334).
- **Evidence**: Each pair verified by grep/read during this audit.
- **Impact**: Future audits chase wrong line numbers; the `_audit-common.md` "1.0" stub
  claim actively contradicts the code and this skill's own Dimension 2 text.
- **Related**: prior report PAT-2026-08-07-C, #334/PERF-14, #17, #104.
- **Suggested Fix**: Run `/audit-sync` over `audit-patterns/SKILL.md` and
  `_audit-common.md` (fix the stub `compression_ratio` sentence to `0`), then
  `.claude/commands/_audit-validate.sh`.

---

## Dimension-by-Dimension Verification Notes

- **Dim 1 (round-trip)**: LOSSLESS — see Summary. Harness at `/tmp/audit/roundtrip_test.py`
  (43 checks, 0 failures), covering both detectors, both parallel sub-paths, decoys,
  self-similar runs, and compressor invariants (`len(events)==length`,
  `references == positions`, no double-claimed frame, full reconstruction).
- **Dim 2 (schema)**: Both detectors and the `--no-patterns` stub emit the identical
  4-key envelope and 7-key `stats`; empty-input envelopes match across detectors
  (verified empirically). `_get_variation_summary` shapes remain unified (#172), the
  parallel path emitting `variation_count=0` with neutral `(0, 0)` ranges by design and
  pinned by tests (`tests/test_patterns.py:1128`, `:1538`). Residual gaps:
  PAT-2026-08-21-5 (on-disk file), PAT-2026-08-21-1 (stub value semantics).
- **Dim 3 (offsets/lengths)**: `references == positions`, exact-only, verified per
  position. Overlap accounting verified — no double-write, and unpatterned tail frames
  are untouched (export derives from `frames`, #4). Both entry points pass the real
  `references` dict (#379 symmetry holds: `main.py:697-704` and `main.py:1222-1229`).
- **Dim 4 (stats)**: All three banner sites print "% reduction (patterned subset only)"
  plus a distinct coverage line (`main.py:787-797`, `:1409-1413`); every real call passes
  `total_events` as the post-sampling analyzed count (#257), and the lossy-coverage
  suffix fires on `detector.was_sampled or fallback_sampled` (#378). One inaccuracy
  found: PAT-2026-08-21-1.
- **Dim 5 (parallel vs sequential + fallback)**: Shared `score_pattern` confirmed at both
  call sites; parallel passes `variation_count=0` (pinned). The
  `_collect_length_candidates` docstring still owns the PAT-05/#171 non-equivalence caveat
  (`pattern_detector_parallel.py:445-455`). Inner serial fallback returns the bare
  patterns dict via `_select_best_patterns` and its only caller re-wraps through the
  compressor (`:86-104`) — traced. The #106 recovery is intact in its #332-updated form:
  failed sub-chunks retry in-process via `_collect_window_groups` (`:227`), and only
  double failures land in `failed_subchunks` with a durable end-of-run warning
  (`:258-262`). The outer `main.py` fallback samples to the same `max_events` the
  sequential detector caps at (`main.py:1151`), so the warning reports the retained count
  (#100).
- **Dim 6 (multiprocessing)**: `_init_pattern_worker`/`_detect_window_groups_worker`/
  `_collect_window_groups` are module-level; `initargs` carries only plain lists;
  chunks are tiny `{'pattern_length', 'start_range'}` dicts; workers mutate no shared
  state; verified live with a 10-chunk pool run. One hygiene finding: PAT-2026-08-21-4
  (`_WORKER_EVENTS` is dead payload). `ThreadedPatternDetector` stays gone (regression
  test at `tests/test_patterns.py:1282-1288`).
- **Dim 7 (sampling)**: Exactly two caps (`DETECTOR_MAX_EVENTS=1000`,
  `MAX_PATTERN_EVENTS=15000`), one shared `sample_events_for_detection`
  (uniform `np.linspace`). The advisory threshold (`main.py:1128`) guards only a print.
  Export still derives every byte from `frames`, never the sampled sequence — sampling
  degrades detection quality only, except on the off-pipeline analysis path where it
  misaligns loop metadata (PAT-2026-08-21-2).
- **Dim 8 (bounds/semantics)**: All three entry points use `PATTERN_MIN_LENGTH`/
  `PATTERN_MAX_LENGTH` from `constants.py` (`main.py:750-751`, `:1136`, `:1144`).
  `max < min` and `len < min` produce clean empty results (verified empirically).
  PAT-04/#170 (`pos = start_pos + pattern_len`, `pattern_detector.py:358`),
  PAT-07/#173 (raw-tuple `_hash_pattern`, `:870-880`), #365 (exact-occurrence gate with
  skip-not-block, `:322-323`), and #366 (drum-scan non-overlap, `:696-712`) all still in
  place. Residual: PAT-2026-08-21-6 (dead `_optimize_patterns`).
- **Dim 9 (loops)**: `detect_loops` guards `len(positions) > 1`; `end <= start` filtered
  in both jump-table generators; the write/read tempo-key format matches
  (`loop_manager.py:141` vs `:167`); same-`end` jump-table clobber remains structurally
  impossible post-`_optimize_loops` (any two ranges sharing `end` overlap at `end-1`).
  #345's stamped-tempo fix intact (`:138-139`). With #168/#170 closed, `positions` stays
  exact-only/non-self-overlapping, so loops can't anchor on non-repeats. Two latent
  findings on the only (off-pipeline) consumer path: PAT-2026-08-21-2, PAT-2026-08-21-3.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_PATTERNS_2026-08-21.md
```
