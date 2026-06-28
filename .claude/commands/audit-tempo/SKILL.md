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
- `nes/emulator_core.py` — consumes the `frame` field; `compile_channel_to_frames` ranges over integer frames.
- `main.py` — `run_full_pipeline` constructs `EnhancedTempoMap(initial_tempo=500000)`.
- `constants.py` — `FRAME_RATE_HZ = 60`, `FRAME_MS = 1000 / 60`.

## Parameters (from $ARGUMENTS)
- `--focus <dims>` — comma-separated dimension numbers (e.g. `--focus 1,7`). Default: all dimensions.

## Extra Per-Finding Field
- **Dimension**: one of the 8 below.

## Dimensions

### Dimension 1: Tick→Frame Conversion & Cumulative Drift
The keystone. `get_frame_for_tick` in `tracker/tempo_map.py` does
`round(calculate_time_ms(0, tick) / FRAME_MS)` — i.e. it measures time from tick 0 each
call, so error should be *absolute*, not accumulated. Verify that:
- `calculate_time_ms(0, tick)` really integrates from 0 every time (no running counter that drifts).
- The per-segment math `us_per_tick = tempo / ticks_per_beat` then `(ticks * us_per_tick)/1000` does not lose precision at large tick counts (float64 is used — confirm it stays float64 and isn't truncated to int per segment).
- `round()` (banker's vs arithmetic) at frame boundaries does not systematically bias one direction over thousands of notes.
- The `_time_cache` keyed on `(start_tick, end_tick)` cannot return a stale value after a tempo change (caches are cleared in `add_tempo_change` — confirm every mutation path clears them).
Construct the skeptical check: a 5-minute song at 120 BPM should land the final note within ±1 frame of `total_ms/FRAME_MS`. Drift that grows with song length = HIGH.

### Dimension 2: Mid-Song & Multiple Tempo Changes
`calculate_time_ms` walks tempo segments via `get_tempo_at_tick` and the "find next
tempo change" inner loop. Audit:
- Tempo changes collected per-track in `parse_midi_to_frames` (`tracker/parser_fast.py`) each reset `current_tick` per track — confirm a `set_tempo` in track N lands at the correct absolute tick, not a wrong track-local one.
- A tempo change *between* two notes shifts every subsequent frame index; verify the segment boundaries in `calculate_time_ms` are inclusive/exclusive consistently (off-by-one at the change tick).
- `EnhancedTempoMap.add_tempo_change` FRAME_ALIGNED path *mutates* `change.tick` via binary search — confirm this re-snapping does not move a tempo change across a note and reorder events.
- Duplicate tempo changes at the same tick (multi-track MIDI) — does the last-wins behavior of `get_tempo_at_tick` match MIDI semantics?

### Dimension 3: Default / Missing Tempo Fallback
`main.py run_full_pipeline` builds `EnhancedTempoMap(initial_tempo=500000)` — 120 BPM —
**without passing `ticks_per_beat`, so it defaults to 480** even though the MIDI file may
declare a different PPQ. `tracker/parser_fast.py` *does* pass `ticks_per_beat=mid.ticks_per_beat`.
Audit:
- Whether the two construction sites (parser vs `main.py`) can disagree on PPQ and produce different frame timing for the same file (the `main.py` one is used for pattern detection on already-framed data, so check whether the PPQ mismatch actually affects output or is inert — confirm, don't assume).
- A MIDI file with **no** `set_tempo` event: does the initial `(0, 500000)` correctly stand in (120 BPM), and is that documented behavior?
- `initial_tempo=0` or negative would divide-by-zero in `60_000_000 / initial_tempo` in the `EnhancedTempoMap.__init__` validation — confirm the guard order.

### Dimension 4: Extreme Tempo Bounds
`TempoValidationConfig` defaults to 20–600 BPM; `parse_midi_to_frames` overrides to
40–250 BPM and silently `continue`s on `TempoValidationError`. Audit:
- A legitimate slow/fast MIDI tempo (e.g. < 40 or > 250 BPM) is **silently dropped** in the fast parser (`except TempoValidationError: continue`) — the song then plays at the wrong tempo with no warning. Weigh against the dedup/severity rules (silent wrong output).
- Very fast tempo: can two distinct note ticks `round()` to the **same** frame (0-length / overlapping notes) in `nes/emulator_core.py compile_channel_to_frames` where `end_frame = start_frame + sustain_frames`? Confirm a note never collapses to zero length silently.
- Very slow tempo / very high tick counts: `_frame_times = np.arange(0, 10000)` in `EnhancedTempoMap.__init__` — is 10000 frames (~166s) a hidden cap anything relies on? Confirm it is unused vs a real bound.
- Overflow: extremely large `tick * us_per_tick` staying in float64 range.

### Dimension 5: PPQ / Division Parsing
`ticks_per_beat` flows from `mid.ticks_per_beat` (mido). Audit:
- SMPTE / negative division (mido exposes frame-based timing differently) — does anything assume PPQ (metrical) division? A negative or SMPTE `ticks_per_beat` would corrupt `us_per_tick`.
- `ticks_per_beat == 0` guard (division by zero in `_ticks_to_ms` / `calculate_time_ms`).
- Whether `main.py`'s hardcoded default-480 path (Dimension 3) is the only place PPQ is dropped, or if any exporter/loop path re-derives timing without it.

### Dimension 6: Loop-Point Frame Alignment
`tracker/loop_manager.py` operates in **event/tick positions**, and `EnhancedLoopManager`
records tempo state into `tempo_map.loop_points`. For a loop to be seamless, the loop
start and end must map to frame indices whose difference equals the loop's playback
length with no gap or double-count. Audit:
- `detect_loops` builds `start`/`end` from pattern `positions` + `length` — confirm these positions are in the same unit (frames vs ticks) the engine loops on; a unit mismatch makes loops jump.
- The jump-table key `loop_info['end']` and value `start_pos` (`generate_jump_table`): is the loop point inclusive of the end frame (replays one frame) or exclusive (drops one frame)? Off-by-one here is an audible click every loop.
- `register_loop_point` / the `loop_points` dict only stores *tempo* at the boundaries — confirm a tempo change spanning the loop boundary doesn't leave the loop restarting at the wrong tempo.

### Dimension 7: Validation / Optimization Fidelity
`optimize_tempo_changes` (and `_align_to_frames`, `_minimize_tempo_changes`,
`_smooth_tempo_transitions`) can *rewrite* the tempo list. The invariant: optimization
may change *representation* but must not change *musical timing* of notes. Audit:
- `_align_to_frames` binary-searches a new tick for each tempo change (±`ticks_per_beat`) — confirm it only snaps to the *nearest* frame boundary and cannot move a change far enough to alter which frame following notes land on.
- `_minimize_tempo_changes` drops changes within 5% — confirm dropped changes truly don't shift downstream frames (5% tempo over a long segment is real drift).
- `_smooth_tempo_transitions` *adds* intermediate tempo changes — confirm total elapsed time across the segment is preserved (linear interpolation of µs/quarter is **not** linear in elapsed time; flag if it changes segment duration).
- Whether `optimize_tempo_changes` is actually called in the default pipeline or is dead on the live path (check `main.py` / `parser_fast.py` call sites).

### Dimension 8: Frame-Edge Off-By-One (frame 0 and final frame)
Boundary correctness:
- Tick 0 → frame 0 (`calculate_time_ms(0,0)` short-circuits to `0.0` → frame 0). Confirm the first note isn't dropped or shifted to frame 1.
- The final note's frame and `compile_channel_to_frames`'s `range(start_frame, end_frame)` — confirm the last frame of the song is emitted (exclusive `range` not truncating it).
- `is_frame_aligned` / `find_nearest_frame_aligned_tick` tolerances (`< 0.001`, `> 1.0`, `> 2.0` ms) — inconsistent thresholds across methods can accept a change as "aligned" in one path and reject it in another.

## Cross-Dimension Dedup
The default-PPQ-480 issue (D3) and a PPQ-parsing gap (D5) can be the same root cause —
report once in the most actionable dimension and cross-reference. Likewise drift (D1)
and optimization-induced drift (D7) — distinguish "math drifts" from "optimization moved it".

## Output
Write to: **`docs/audits/AUDIT_TEMPO_<TODAY>.md`** (YYYY-MM-DD). Structure:
1. **Summary** — invariant verdict (does frame timing stay on the 60Hz grid?), counts per severity, the highest-leverage fix.
2. **Findings** — base format from `_audit-common.md` + the `Dimension` field.

Then suggest:
```
/audit-publish docs/audits/AUDIT_TEMPO_<TODAY>.md
```
