# Tempo & Frame-Timing Audit — 2026-08-07

## 1. Summary

**Invariant verdict: PASS.** Frame timing stays on the 60Hz grid on the live MIDI→ROM
path. The keystone conversion
`get_frame_for_tick(tick) = round(calculate_time_ms(0, tick) / FRAME_MS)`
(`tracker/tempo_map.py:209-212`) measures time **absolutely from tick 0** on every call
via the bisect-based cumulative-ms index (`_build_tempo_index`/`_cumulative_ms`,
`:140-177`), so rounding error is bounded (±0.5 frame per note) and **does not
accumulate**. `_cumulative_ms(0) == 0.0` (tick 0 → frame 0, no off-by-one), segments are
computed in `np.float64` with no per-segment int truncation, and every mutation path
(`add_tempo_change`, `EnhancedTempoMap.add_tempo_change`, `_minimize_tempo_changes`,
`_smooth_tempo_transitions`, `_align_to_frames`) still clears both `_time_cache` and
`_tempo_index`.

**All three previously-open LOW findings from the 2026-08-06 audit are now fixed.**
Between that audit and this one, commit `7c30b35` (2026-08-06, "reconcile
frame-alignment predicates") fixed #382 (TEMPO-17): `_validate_frame_boundaries`
(`tracker/tempo_map.py:488-502`) and `_check_frame_alignment` (`:881-898`) now both
delegate to `is_frame_aligned`'s symmetric nearest-boundary distance instead of the old
asymmetric `% FRAME_MS` test, and `_check_frame_alignment` no longer uses a
single-segment time basis. The same commit fixed #383 (TEMPO-18): base
`TempoMap.__init__` (`:88-118`) now guards `initial_tempo <= 0` in addition to the
existing `ticks_per_beat < 1` guard. Commit `e6853a3` (2026-08-07, "fix parser.py's
hardcoded PPQ") fixed #396 (TEMPO-19): `tracker/parser.py:30-35` now passes
`ticks_per_beat=mid.ticks_per_beat` to its `EnhancedTempoMap` constructor instead of
silently defaulting to 480. All three fixes were re-derived from the current source
(not taken on faith) and confirmed present exactly as described.

Re-verifying `gh issue list --state all`: every TEMPO-0x/1x issue the skill and prior
audits reference (#93-#99, #113, #160, #208-#211, #259, #260, #317, #343-#345, #382,
#383, #396) is now **CLOSED**. No open issue in the repo carries the `tempo` label.

**Context per the task brief:** the new `song build` subcommand (`main.py:927`
`run_song_build`, helper `midi_to_frames_for_song` at `main.py:878-907`) parses each
song's MIDI via the exact same `tracker.parser_fast.parse_midi_to_frames` call
`run_full_pipeline` uses — confirmed by reading `midi_to_frames_for_song`, which
imports and calls `parse_fast` with no separate tempo-map construction of its own. It
introduces no new tick→frame math; each song's `frames` dict is independently
frame-indexed from its own tempo map exactly as a single-song build would be, and the
multi-song bytecode exporter (`exporter/exporter_ca65.py:1533`
`export_song_bank_bytecode`) serializes each song's already-frame-indexed data
independently with no cross-song frame-offset arithmetic. `SongMetadata.tempo_base`
(`nes/song_bank.py:20`) is descriptive JSON metadata only, never fed into a
`TempoMap`/frame calculation. No tempo-subsystem changes and no new findings from this
feature.

**No new findings this round.** Re-derivation of all 8 dimensions against the current
code surfaced no defect. The dead/inert code paths flagged by prior audits (D3's two
`main.py` analysis-only tempo maps, `ParallelPatternDetector`'s stored-but-unused
`tempo_map`, D6's `EnhancedLoopManager`, D7's `optimize_tempo_changes` family, and the
FRAME_ALIGNED re-snap branch in `add_tempo_change`) remain confirmed unreachable from
every live construction site — re-grepped this round, not assumed.

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 0 (0 NEW, 3 closed-since-last-audit,
0 still open).

**Highest-leverage fix:** none — there is no open tempo-domain issue and no live-path
defect. The subsystem is in as clean a state as any tempo audit has found it.

## 2. Findings

No findings to report this round — all previously-tracked issues are closed and no new
defects were identified across the 8 audited dimensions.

## 3. Dimension Coverage Notes

- **D1 (drift):** Clean. `calculate_time_ms(0, tick)` (`tracker/tempo_map.py:187-201`)
  is exact (`_cumulative_ms(end) - _cumulative_ms(start)`, both computed from the same
  segmentation), `_build_tempo_index` (`:140-159`) does per-segment math in
  `np.float64` with no truncation, and both `_time_cache` and `_tempo_index` are
  cleared on every mutation path I re-traced (`TempoMap.add_tempo_change:127-138`,
  `EnhancedTempoMap.add_tempo_change:300-301,376-377`, `_minimize_tempo_changes`
  callers via `optimize_tempo_changes:730-739`, `_align_to_frames` same). No
  regression since the 2026-08-06 empirical verification of this identity.
- **D2 (multi-tempo):** Clean. Per-track `current_tick` reset
  (`tracker/parser_fast.py:45,118`) matches MIDI delta-time semantics (track-local,
  absolute tick per track). `bisect_right(ticks, tick) - 1`
  (`_cumulative_ms:172`, `get_tempo_at_tick:182`) makes a tempo change effective at its
  own tick with no off-by-one. Duplicate same-tick changes resolve last-wins via the
  tick-only stable sort (`tempo_changes.sort(key=lambda c: c[0])`, `:136`) plus
  `bisect_right` (#210, unchanged). The FRAME_ALIGNED re-snap in
  `add_tempo_change` (`:321-362`) that could in theory move a tick across a nearby
  event is confirmed still inert: re-grepped every `.add_tempo_change(` call site
  (`tracker/parser_fast.py:51`, `tracker/parser.py:47`) and both construct their
  `EnhancedTempoMap` with `optimization_strategy=None`.
- **D3 (fallback):** `main.py:749` / `:1115` analysis-only `EnhancedTempoMap`s remain
  inert — re-confirmed neither is ever passed to `.add_tempo_change(`, and
  `ParallelPatternDetector` (`tracker/pattern_detector_parallel.py`) stores
  `self.tempo_map` at construction but never calls `add_tempo_change` or
  `get_tempo_at_tick` on it anywhere in that module. Missing-`set_tempo` correctly
  falls back to `(0, 500000)` = 120 BPM. `EnhancedTempoMap(initial_tempo=0)` raises
  `TempoValidationError` (`:249-252`); the base `TempoMap(initial_tempo=0)` now does
  too (`:114-118`, the #383/TEMPO-18 fix), closing the last gap here.
  `parse_midi_to_frames_with_analysis` now shares `_parse_frames_and_tempo_map` /
  `_build_tempo_map` with `parse_midi_to_frames` (`tracker/parser_fast.py:24-67,
  70-95, 192-201`) — a single tempo-map build with the same count-and-warn behavior
  on rejected changes, so the "still has a bare `except: continue`" residual the skill
  describes as unresolved is itself stale prose; the shared refactor (#335/PERF-15)
  already fixed it before this audit, matching #259/#260 both being CLOSED.
- **D4 (extreme bounds):** Widened 1-2000 BPM band with `max_tempo_change_ratio=inf`
  (`tracker/parser_fast.py:103-109`) unchanged; dropped changes counted and warned via
  `print` (`_build_tempo_map:56-65`), reaching CLI stdout unfiltered. Same-frame
  collapse (#96) and its tie-break (#344/TEMPO-15) confirmed fixed
  (`nes/emulator_core.py:38-42`: equal velocity keeps the later event, matching the
  docstring at `:42`). No fixed-size `_frame_times` buffer found (grep for
  `_frame_times` across `tracker/tempo_map.py` returns nothing). No float64 overflow
  risk identified in `_build_tempo_index`/`_cumulative_ms`.
- **D5 (PPQ):** `parser_fast.py`'s early check (`:89-94`) and `TempoMap.__init__`
  (`:101`) both gate at `< 1` (agree exactly, #93/#95). `tracker/parser.py:30-35` now
  also passes `ticks_per_beat=mid.ticks_per_beat` (the #396/TEMPO-19 fix, verified by
  reading the file directly) — this was the last PPQ-drop path in the codebase; none
  remain. No exporter or loop path independently re-derives timing without going
  through a `TempoMap`.
- **D6 (loops):** `EnhancedLoopManager` (`tracker/loop_manager.py:115-183`) remains
  opt-in only (`--with-analysis` and the non-default `tracker/parser.py`) — re-grepped,
  its only callers outside tests are `tracker/parser_fast.py`'s
  `parse_midi_to_frames_with_analysis` and `tracker/parser.py`. It reads per-event
  stamped tempo (`events[loop_info['start']]['tempo']`, `:138-139`) instead of a
  mis-unit'd `get_tempo_at_tick` lookup (#345, still fixed); `end` is treated as an
  exclusive index consistently between `detect_loops` (`tracker/loop_manager.py:39`)
  and `generate_jump_table`/`EnhancedLoopManager.generate_jump_table`
  (`:103,163`). No off-by-one found; path remains off the default pipeline and
  unaffected by the new `song build` feature (confirmed: `midi_to_frames_for_song`
  calls plain `parse_midi_to_frames`, never the `--with-analysis` variant).
- **D7 (optimization):** Confirmed unreachable from CLI — re-grepped `optimize_tempo_changes`,
  `_align_to_frames`, `_smooth_tempo_transitions`, `_minimize_tempo_changes` for any
  caller outside `tracker/tempo_map.py` itself and `tests/`; none found. WARNING
  docstrings remain in place (#97, `_smooth_tempo_transitions:625-636`,
  `optimize_tempo_changes:712-719`).
- **D8 (frame edges):** Tick 0 → frame 0 confirmed (`_cumulative_ms(0) == 0.0`, no
  special-case needed since the loop in `_build_tempo_index` starts cumulative ms at
  0.0 and `_cumulative_ms(0)` resolves `i=0, seg_ticks=0`). `compile_channel_to_frames`'s
  `range(start_frame, end_frame)` (`nes/emulator_core.py:106`) emits the last sounding
  frame correctly, with note-off pairing (#160) deriving `end_frame` from the matching
  note-off where available (`:79-89`). The three frame-alignment verdict predicates
  (`is_frame_aligned:274-279`, `_validate_frame_boundaries:488-502`,
  `_check_frame_alignment:881-898`) now agree — re-read all three in full and confirmed
  the latter two both call `is_frame_aligned(tick)` and derive their `off_by` message
  from the same symmetric `abs(time_ms - frame_number * FRAME_MS)` distance on the true
  cumulative `calculate_time_ms(0, tick)`, closing TEMPO-17/#382. The deliberately-separate
  re-snap search inside `add_tempo_change` (`:321-362`, tolerances `1.0`/`2.0`ms,
  asymmetric `% FRAME_MS`) remains a distinct, documented exception (it adjusts ticks,
  not verdicts) and remains unreachable from any live construction site per D2 above, so
  the "could a re-snapped tick later fail a verdict predicate" risk the skill flags
  stays theoretical, not live.

---

No new findings — nothing to publish this round. For reference, the equivalent command
once a new tempo finding exists:

```
/audit-publish docs/audits/AUDIT_TEMPO_2026-08-07.md
```
