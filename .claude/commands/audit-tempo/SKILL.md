---
description: "Audit tempo map and 60Hz frame-timing accuracy"
argument-hint: "[--focus <dims>]"
---

# Tempo & Frame-Timing Audit

Audit the subsystem that turns MIDI time (PPQ ticks + tempo in microseconds/quarter)
into the integer 60Hz frame indices everything downstream is keyed on. The core
invariant: a tick converts to a frame index that is **absolute from t=0**, so rounding
error must stay bounded — it must not accumulate into audible drift over a long song.

Shared protocol: `.claude/commands/_audit-common.md` (project layout, the 60Hz frame
model, the float-frame-timing rule, dedup, finding format). Severity:
`.claude/commands/_audit-severity.md` — note in particular that **frame-timing drift off
the 60Hz grid over a song is HIGH**. Do not restate either file; apply them.

Primary code under audit (confirm line numbers before quoting):
- `tracker/tempo_map.py` — `TempoMap` / `EnhancedTempoMap` (tempo changes, `calculate_time_ms`, `get_frame_for_tick`, `add_tempo_change`, validation, `optimize_tempo_changes` / `_align_to_frames`).
- `tracker/loop_manager.py` — `LoopManager` / `EnhancedLoopManager` (loop-point detection + tempo state via `register_loop_point` / `loop_points`).
- `tracker/parser_fast.py` — `parse_midi_to_frames` (the default front-end; collects `set_tempo` and calls `get_frame_for_tick`).
- `nes/emulator_core.py` — consumes the `frame` field; `compile_channel_to_frames` ranges over integer frames; `_collapse_same_frame_events` dedupes same-frame note-ons.
- `main.py` — `run_detect_patterns` and `run_full_pipeline` each construct their own `EnhancedTempoMap(initial_tempo=500000)` for pattern-detection tempo metadata.
- `constants.py` — `FRAME_RATE_HZ = 60`, `FRAME_MS = 1000 / FRAME_RATE_HZ`.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 1,7`). Default: all dimensions.

## Extra Per-Finding Field
- **Dimension**: one of the 8 below.

## Dimensions

### Dimension 1: Tick→Frame Conversion & Cumulative Drift
The keystone. `get_frame_for_tick` in `tracker/tempo_map.py` (~line 192) does
`round(calculate_time_ms(0, tick) / FRAME_MS)` — i.e. it measures time from tick 0 each
call, so error should be *absolute*, not accumulated. Since #113, the lookup is bisect-based
over a precomputed `(ticks, tempos, cumulative_ms)` index (`_build_tempo_index`,
`_get_tempo_index`, `_cumulative_ms`, lines ~123-160) rather than a linear per-segment scan.
Verify that:
- `calculate_time_ms(0, tick)` (line ~170) still integrates from 0 every time via
  `_cumulative_ms(end) - _cumulative_ms(start)` — confirm this identity is exact (no running
  counter that drifts) now that it's index-based rather than a direct walk.
- `_build_tempo_index` (lines ~123-142) does the per-segment math in `np.float64` and does not
  truncate to int per segment at large tick counts.
- `round()` (banker's vs arithmetic) at frame boundaries does not systematically bias one direction over thousands of notes.
- The `_time_cache` keyed on `(start_tick, end_tick)` (line ~176) and the `_tempo_index` (line ~114)
  cannot return a stale value after a tempo change — confirm every mutation path (`add_tempo_change`
  base at line ~116-121, `EnhancedTempoMap.add_tempo_change` at line ~258-346, `_minimize_tempo_changes`,
  `_smooth_tempo_transitions`, `_align_to_frames`) clears both.
Construct the skeptical check: a 5-minute song at 120 BPM should land the final note within ±1 frame of `total_ms/FRAME_MS`. Drift that grows with song length = HIGH.

### Dimension 2: Mid-Song & Multiple Tempo Changes
`calculate_time_ms` now delegates to the bisect-based `_cumulative_ms` (Dimension 1) instead of
walking `get_tempo_at_tick` in a loop. Audit:
- Tempo changes collected per-track in `parse_midi_to_frames` (`tracker/parser_fast.py`, lines ~60-77) each reset `current_tick` per track — confirm a `set_tempo` in track N lands at the correct absolute tick, not a wrong track-local one.
- A tempo change *between* two notes shifts every subsequent frame index; verify the segment boundaries in `_cumulative_ms`/`_build_tempo_index` are inclusive/exclusive consistently (off-by-one at the change tick).
- `EnhancedTempoMap.add_tempo_change`'s FRAME_ALIGNED path (lines ~290-331) *mutates* `change.tick` via binary search — confirm this re-snapping does not move a tempo change across a note and reorder events.
- Duplicate tempo changes at the same tick (multi-track MIDI) — does the last-wins/sort behavior of `tempo_changes.sort()` (line ~119) plus `get_tempo_at_tick`'s `bisect_right` (line ~165) match MIDI semantics?

### Dimension 3: Default / Missing Tempo Fallback
`main.py`'s `run_detect_patterns` (line ~621) and `run_full_pipeline` (line ~811) each build
`EnhancedTempoMap(initial_tempo=500000)` — 120 BPM — **without passing `ticks_per_beat`, so it
defaults to 480** even though the MIDI file may declare a different PPQ. `tracker/parser_fast.py`
(line ~51) *does* pass `ticks_per_beat=mid.ticks_per_beat`. Audit:
- Whether the PPQ mismatch actually matters: these two `main.py` tempo maps are constructed fresh,
  used only for `EnhancedPatternDetector`/`ParallelPatternDetector` tempo-metadata analysis on
  already-framed data (events carry `frame`, not `tick`), and never receive an `add_tempo_change`
  call — `get_tempo_at_tick` therefore always returns the constant `500000` regardless of
  `ticks_per_beat`. **Confirmed inert** for the current call sites (`tracker/pattern_detector.py`
  `_analyze_pattern_tempo`/`_analyze_variation_tempos` treat the position index as "tick" against a
  tempo map with a single flat entry). This is dead/misleading configuration (LOW: doesn't affect
  ROM output today) rather than a live timing bug — but it is fragile: if either call site is ever
  changed to feed real ticks or add tempo changes, the hardcoded 480 would silently diverge from the
  file's actual PPQ. Flag as tech debt / latent trap, not as an active HIGH drift bug (#98 — CLOSED:
both construction sites now carry an "analysis-only" comment documenting the inertness, so do NOT
re-file; re-flag only if a call site starts deriving timing from these maps).
- A MIDI file with **no** `set_tempo` event: does the initial `(0, 500000)` correctly stand in (120 BPM), and is that documented behavior?
- `initial_tempo=0` or negative: `EnhancedTempoMap.__init__` (line ~229) computes
  `60_000_000 / initial_tempo` for BPM validation *before* calling `super().__init__` — confirm this
  order (division happens before the base class's `ticks_per_beat` guard) can't itself raise an
  unguarded `ZeroDivisionError` for `initial_tempo=0` instead of the intended `TempoValidationError`.

### Dimension 4: Extreme Tempo Bounds
`TempoValidationConfig` defaults to 20-600 BPM (`tracker/tempo_map.py` line ~34-38).
`parse_midi_to_frames` (`tracker/parser_fast.py`, lines ~42-48) now widens this to
**1-2000 BPM with `max_tempo_change_ratio=float('inf')`** rather than the old 40-250 BPM /
ratio-3.0 override, and on the rare remaining `TempoValidationError` it counts and warns
(lines ~72-81) instead of silently `continue`-ing — **this was TEMPO-02 (#94), now fixed**.
Verify fix completeness:
- Any legitimate tempo that could still fall outside the widened 1-2000 BPM band (e.g. a MIDI
  encoding an extreme fermata or glitch tempo) is still dropped, just now with a warning printed —
  confirm the warning actually reaches the user in the CLI output path and isn't swallowed upstream.
- `parse_midi_to_frames_with_analysis` (`tracker/parser_fast.py`, lines ~150-229, used only via
  `parser_fast.py --with-analysis` and in `tests/test_parser_fast.py` — **not** on the default
  pipeline path) rebuilds its own tempo map (lines ~166-177) and still has a bare
  `except TempoValidationError: continue` (lines ~186-189) with no counting/warning, unlike the
  fixed default-path parser. Low-severity residual inconsistency since it's off the live path, but
  worth aligning for consistency.
- Same-frame note collapse: `nes/emulator_core.py`'s `_collapse_same_frame_events` (lines ~16-46,
  called from `compile_channel_to_frames` line ~64) now explicitly detects when two note-ons quantize
  to the same 60Hz frame on a monophonic channel, keeps the louder one, and prints a warning with a
  dropped count — **this was TEMPO-04 (#96), now fixed**. Verify fix completeness: confirm ties
  (equal velocity) deterministically keep the later event as documented (line ~39), and that the
  arranger path (which allocates/arpeggiates polyphony across channels) genuinely never hits this
  collapse for legitimately polyphonic content.
- Very slow tempo / very high tick counts: the previously-dead `_frame_times = np.arange(0, 10000)`
  buffer in `EnhancedTempoMap.__init__` has since been removed — grep for `_frame_times` in
  `tracker/tempo_map.py` now returns nothing. There is no fixed frame-count buffer capping anything;
  confirm nothing has reintroduced such a cap.
- Overflow: extremely large `tick * us_per_tick` staying in float64 range (`_build_tempo_index` /
  `_cumulative_ms`, lines ~137-160).

### Dimension 5: PPQ / Division Parsing
`ticks_per_beat` flows from `mid.ticks_per_beat` (mido). **TEMPO-01 (#93) and TEMPO-03 (#95) are
now fixed**: `TempoMap.__init__` (`tracker/tempo_map.py`, lines ~96-107) raises `ValueError` for
any `ticks_per_beat is None or ticks_per_beat < 1`, covering both the SMPTE-negative case (#93) and
the zero case (#95) with one guard, applied to every constructor (base `TempoMap` and
`EnhancedTempoMap`, and every caller including `tracker/parser.py`). `parse_midi_to_frames`
(`tracker/parser_fast.py`, lines ~22-33) additionally rejects SMPTE/non-positive division up front
with an actionable message before constructing the tempo map at all. Verify fix completeness:
- Confirm there is no remaining construction path that bypasses `TempoMap.__init__` (e.g. a
  subclass or test helper that sets `self.ticks_per_beat` directly without going through `__init__`).
- Confirm the two guards (parser_fast's early check and `TempoMap.__init__`'s check) agree on the
  boundary (`< 1` in both) so neither is stricter/looser than the other in a way that changes which
  files fail parsing.
- Whether `main.py`'s hardcoded default-480 path (Dimension 3) is the only place PPQ is dropped, or if any exporter/loop path re-derives timing without it.

### Dimension 6: Loop-Point Frame Alignment
`tracker/loop_manager.py` operates in **event/tick positions**, and `EnhancedLoopManager`
records tempo state into `tempo_map.loop_points`. For a loop to be seamless, the loop
start and end must map to frame indices whose difference equals the loop's playback
length with no gap or double-count. Note: `EnhancedLoopManager` is not on the default pipeline
path today — it's only instantiated in `parse_midi_to_frames_with_analysis`
(`tracker/parser_fast.py` line ~193, opt-in `--with-analysis`) and in the older
`tracker/parser.py` (line ~84, not the default front-end per `CLAUDE.md`). Audit anyway, since it
is reachable and its correctness matters whenever either path is used:
- `detect_loops` (`tracker/loop_manager.py`, lines ~11-50) builds `start`/`end` from pattern `positions` + `length` — confirm these positions are in the same unit (frames vs ticks) the engine loops on; a unit mismatch makes loops jump.
- The jump-table key `loop_info['end']` and value `start_pos` (`generate_jump_table`, lines ~93-112 / ~144-159): is the loop point inclusive of the end frame (replays one frame) or exclusive (drops one frame)? Off-by-one here is an audible click every loop.
- `register_loop_point` (line ~503) / the `loop_points` dict only stores *tempo* at the boundaries — confirm a tempo change spanning the loop boundary doesn't leave the loop restarting at the wrong tempo.

### Dimension 7: Validation / Optimization Fidelity
`optimize_tempo_changes` (`tracker/tempo_map.py`, lines ~668-688) and `_align_to_frames`
(~622-666), `_minimize_tempo_changes` (~581-593), `_smooth_tempo_transitions` (~595-620) can
*rewrite* the tempo list. **Confirmed still dead on the live path (TEMPO-05, #97 — CLOSED,
documented in code)**: both `tracker/parser_fast.py`'s `parse_midi_to_frames` (line ~53) and
`main.py`'s `EnhancedTempoMap` construction sites (lines ~621, ~811) pass or default to
`optimization_strategy=None` / never call `optimize_tempo_changes()` — grep confirms no call site
outside `tracker/tempo_map.py` itself and its tests. #97 was closed by adding WARNING docstrings to
`optimize_tempo_changes` and `_smooth_tempo_transitions` (the µs/quarter-interpolation timing hazard
below is now documented in code), so do NOT re-file it — re-flag only if a real call site appears.
The invariant if it's ever wired up: optimization
may change *representation* but must not change *musical timing* of notes. Audit:
- `_align_to_frames` binary-searches a new tick for each tempo change (±`ticks_per_beat`) — confirm it only snaps to the *nearest* frame boundary and cannot move a change far enough to alter which frame following notes land on.
- `_minimize_tempo_changes` drops changes within 5% — confirm dropped changes truly don't shift downstream frames (5% tempo over a long segment is real drift).
- `_smooth_tempo_transitions` *adds* intermediate tempo changes — confirm total elapsed time across the segment is preserved (linear interpolation of µs/quarter is **not** linear in elapsed time; flag if it changes segment duration).
- Given it's unreachable from the CLI today, weigh this as LOW (dead code / tech debt) rather than a
  live functional bug — but flag loudly if you find it silently corrupts timing, since re-wiring it
  later would then ship a live bug.

### Dimension 8: Frame-Edge Off-By-One (frame 0 and final frame)
Boundary correctness:
- Tick 0 → frame 0 (`calculate_time_ms(0,0)` short-circuits to `0.0` at line ~179 → frame 0). Confirm the first note isn't dropped or shifted to frame 1.
- The final note's frame and `compile_channel_to_frames`'s `range(start_frame, end_frame)`
  (`nes/emulator_core.py`, line ~101) — confirm the last frame of the song is emitted (exclusive
  `range` not truncating it). Note note-off pairing (#160) now derives `end_frame` from the
  matching note-off event where available (lines ~76-86), falling back to `sustain_frames` only
  when unpaired.
- Frame-alignment tolerance consolidation (**TEMPO-07, #99, now fixed**): `is_frame_aligned`
  (line ~254), `_validate_frame_boundaries` (line ~468), and `_check_frame_alignment` (line ~830) all
  now reference the single `FRAME_ALIGNMENT_TOLERANCE_MS = 0.5` constant (line ~23) instead of
  independent hardcoded thresholds. The dead `_frame_cache` (assigned but never read) was removed in
  the same fix. Verify fix completeness:
  - `add_tempo_change`'s best-effort re-snap search (lines ~299, 319, 328) still uses its own
    hardcoded tolerances (`1.0`, `2.0` ms) — this is called out in the code comment (lines ~21-22) as
    deliberately separate because it *adjusts* ticks rather than *verdicts* alignment. Confirm this
    distinction actually holds: could a tick accepted by the wider re-snap tolerance later fail one of
    the three verdict predicates (or vice versa), producing a tempo change that "succeeded" but is
    then reported as misaligned elsewhere?
  - `find_nearest_frame_aligned_tick` (line ~359) and `_align_to_frames` (line ~622) use a
    `0.001` ms exact-match short-circuit — confirm this doesn't leave a not-quite-aligned tick
    (between 0.001 and 0.5ms off) that the verdict predicates would then call "aligned" but that
    wasn't actually snapped.

## Cross-Dimension Dedup
The default-PPQ-480 issue (D3, now confirmed inert/tech-debt rather than a live bug) and the
PPQ-parsing fixes (D5, #93/#95, now fixed) are related but distinct root causes — report them
separately since one is closed and one is an open (low-severity) latent trap. Likewise drift (D1)
and optimization-induced drift (D7, dead code) — distinguish "math drifts" from "optimization moved
it" (and note D7's code is currently unreachable).

## Output
Write to: **`docs/audits/AUDIT_TEMPO_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — invariant verdict (does frame timing stay on the 60Hz grid?), counts per severity, the highest-leverage fix.
2. **Findings** — base format from `_audit-common.md` + the `Dimension` field.

Then suggest:
```
/audit-publish docs/audits/AUDIT_TEMPO_<TODAY>.md
```
