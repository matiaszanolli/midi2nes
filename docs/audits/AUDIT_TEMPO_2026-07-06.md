# Tempo & Frame-Timing Audit — 2026-07-06

## Summary

**Invariant verdict: frame timing stays on the 60Hz grid.** Re-verified empirically
against the current tree. A 5-minute, 120 BPM song (`ticks_per_beat=480`, 288,000 ticks)
lands the final frame at exactly frame **18000** — **0 frames** of drift. The absolute
error `|get_frame_for_tick − exact|` sampled over 1,200 consecutive beats is **0.0**:
`calculate_time_ms(0, tick)` integrates from tick 0 on every call via the bisect index
(`_cumulative_ms(end) − _cumulative_ms(start)`, `tracker/tempo_map.py:158-190`), with no
accumulating running counter. Boundary checks pass: tick 0 → frame 0
(`calculate_time_ms(0,0)` short-circuits to `0.0`), and a mid-song tempo change at tick 960
leaves that tick at 1000.0 ms → frame 60 (the change applies only to the *following*
segment, not the boundary tick itself).

**No new defects.** The tempo/frame-timing code is byte-identical to the state audited on
2026-07-05 (last commit touching `tracker/tempo_map.py`, `tracker/parser_fast.py`,
`tracker/loop_manager.py`, `nes/emulator_core.py` is `2823594`, dated 2026-07-05 22:22).
All fixes confirmed on the prior pass remain in place: tick-0 tempo validation (#208),
zero/negative tempo guard (#209), duplicate-tick stable tie-break (#210), `_frame_times`
removal (#211), the O(log T) bisect index (#113), SMPTE/zero PPQ guards (#93/#95), the
widened 1–2000 BPM band with count-and-warn (#94), same-frame note collapse (#96), the
single `FRAME_ALIGNMENT_TOLERANCE_MS` constant (#99), and note-off pairing (#160).

**Every open finding is already filed.** The four residual items are all pre-existing OPEN
issues — two dead-code/inert-config items (#97, #98) and the two `parse_midi_to_frames_with_analysis`
LOW inconsistencies (#259, #260) that were raised NEW on the 2026-07-05 pass and have since
been filed. Per the dedup protocol they are noted here and skipped, not re-filed. **0 NEW
findings this pass.**

| Severity | Count | of which NEW |
|----------|-------|--------------|
| CRITICAL | 0     | 0 |
| HIGH     | 0     | 0 |
| MEDIUM   | 0     | 0 |
| LOW      | 4     | 0 (all Existing/open) |
| **Total**| **4** | **0** |

**Highest-leverage fix:** none is load-bearing — the live ROM timing path is clean. The
cheapest cleanup remains folding the two analysis-path items (#259/#260) into the
`parse_midi_to_frames_with_analysis` refactor implied by #97/#98: pass
`ticks_per_beat=mid.ticks_per_beat` and count/warn on dropped tempo changes exactly like
the default `parse_midi_to_frames` already does — or, better, reuse the tempo map the first
pass already built instead of rebuilding it.

---

## Findings

All four are pre-existing OPEN issues; details preserved for traceability.

### TEMPO-06 (dup): default-PPQ tempo maps in `main.py` are inert
- **Severity**: LOW
- **Dimension**: 3 (Default / Missing Tempo Fallback)
- **Location**: `main.py:621` (`run_detect_patterns`, `analyze_tempo=False`) and `main.py:811`
  (`run_full_pipeline`) — both `EnhancedTempoMap(initial_tempo=500000)` with no `ticks_per_beat`.
- **Status**: Existing: #98
- **Description**: Both sites default `ticks_per_beat` to 480 regardless of the MIDI file's real
  PPQ. Confirmed inert: neither map ever receives an `add_tempo_change`, and its only consumer
  (`EnhancedPatternDetector` tempo metadata over already-framed events) calls `get_tempo_at_tick`,
  which returns the constant 500000 without any tick→time math. The `run_detect_patterns` site
  additionally passes `analyze_tempo=False`, short-circuiting the analysis entirely.
- **Evidence**: `main.py:618-624` comment states the detector's positions "are already-quantized
  frame positions, not MIDI ticks" and skips tempo analysis (`#119`). Grep confirms no
  `calculate_time_ms`/`get_frame_for_tick` call on either map.
- **Impact**: No ROM ships wrong music. Latent trap: if either call site is ever changed to feed
  real ticks or add tempo changes, the hardcoded 480 would silently diverge from the file's PPQ.
- **Related**: #259 (TEMPO-13, a third site with the same omission but non-inert tempo data), #97.
- **Suggested Fix**: Pass `ticks_per_beat` through, or remove the maps if the metadata is unused.

### TEMPO-05 (dup): dead optimization & loop-alignment code on the live path
- **Severity**: LOW
- **Dimension**: 7 (Validation / Optimization Fidelity) / 6 (Loop-Point Frame Alignment)
- **Location**: `tracker/tempo_map.py:668-688` (`optimize_tempo_changes`), `:622-666`
  (`_align_to_frames`), `:581-593` (`_minimize_tempo_changes`), `:595-620`
  (`_smooth_tempo_transitions`); `tracker/loop_manager.py:115-159` (`EnhancedLoopManager`).
- **Status**: Existing: #97
- **Description**: `optimize_tempo_changes` is never invoked from any live path —
  `parse_midi_to_frames` (`:65`) and both `main.py` sites pass/default `optimization_strategy=None`
  and never call it. `EnhancedLoopManager` is instantiated only in
  `parse_midi_to_frames_with_analysis` and the older `tracker/parser.py`, neither on the default
  pipeline. Within this dead code, `EnhancedLoopManager.detect_loops` passes loop *frame/position*
  values to `get_tempo_at_tick` (`loop_manager.py:127-128`) — a frame-vs-tick unit mismatch — but
  it only taints discarded loop metadata.
- **Evidence**: Grep finds no call to `optimize_tempo_changes()` outside `tempo_map.py` and its
  tests; `_smooth_tempo_transitions` linearly interpolates µs/quarter, which is not linear in
  elapsed time (would change segment duration if ever wired up).
- **Impact**: None today (unreachable). Re-wiring it later without fixing the interpolation/units
  would ship a live timing bug.
- **Related**: #98, #259.
- **Suggested Fix**: Remove the dead optimization/loop methods, or guard + test them before wiring.

### TEMPO-12 (dup): `parse_midi_to_frames_with_analysis` silently drops out-of-range tempo changes
- **Severity**: LOW
- **Dimension**: 4 (Extreme Tempo Bounds)
- **Location**: `tracker/parser_fast.py:197-201` (`except TempoValidationError: continue`, no
  counter/warning), vs. the fixed default path at `tracker/parser_fast.py:84-93`.
- **Status**: Existing: #259
- **Description**: The default `parse_midi_to_frames` was fixed under #94 to count dropped tempo
  changes and warn. Its sibling `parse_midi_to_frames_with_analysis` rebuilds its own tempo map and
  still uses the pre-#94 silent `continue`, so a rejected tempo change vanishes with no trace.
- **Evidence**: `parser_fast.py:197-201` — bare `except TempoValidationError: continue`.
- **Impact**: Off the live ROM path (`--with-analysis` only; its metadata is not consumed by the
  default pipeline). Consistency/observability gap only.
- **Related**: #94 (closed, introduced the count-and-warn), #260.
- **Suggested Fix**: Mirror the default path (count + single warning), or share one tempo-collection
  helper between the two passes.

### TEMPO-13 (dup): analysis parser builds its tempo map without `ticks_per_beat`, then feeds it real ticks
- **Severity**: LOW
- **Dimension**: 5 (PPQ / Division Parsing) / 3
- **Location**: `tracker/parser_fast.py:185-189` (`EnhancedTempoMap(initial_tempo=500000,
  validation_config=config, optimization_strategy=None)` — no `ticks_per_beat`, defaults to 480)
  combined with `:193-201` (adds real tempo changes at the file's actual ticks).
- **Status**: Existing: #260
- **Description**: Unlike the default parser (`:61-66`, which passes `ticks_per_beat=mid.ticks_per_beat`),
  the analysis rebuild takes the constructor default of 480 and then records real tick-keyed tempo
  changes. If the file's PPQ ≠ 480, `ticks_per_beat` disagrees with the stored ticks. Distinct from
  #98's `main.py` sites (which never call `add_tempo_change` at all) because here real tempo data is
  recorded.
- **Evidence**: Inert today only because the two consumers (`get_tempo_at_tick` and
  `EnhancedPatternDetector._analyze_pattern_tempo`) never run tick→time math on this map. No
  `calculate_time_ms`/`get_frame_for_tick` is called on it.
- **Impact**: No wrong output today; fragile latent trap if any future analysis-path change runs
  time math on this map.
- **Related**: #98, #259.
- **Suggested Fix**: Pass `ticks_per_beat=mid.ticks_per_beat`, or reuse the first pass's tempo map.

---

## Confirmed-fixed (re-verified, not re-reported)

- **#208** tick-0 tempo validation — `add_tempo_change` calls `_validate_basic_tempo` before the
  tick-0 early return (`tempo_map.py:266-282`). In place.
- **#209** zero/negative tempo — `_validate_basic_tempo` (`:396-399`) and `_validate_tempo_change`
  (`:426-429`) raise `TempoValidationError` on `tempo <= 0` before dividing. In place.
- **#210** duplicate-tick tie-break — `add_tempo_change` sorts `key=lambda c: c[0]` (`:125`),
  stable "last event wins"; `_align_to_frames` uses the same key (`:665`). In place.
- **#211 / TEMPO-11** `_frame_times` dead array — removed (0 grep matches for `_frame_times`/
  `_frame_cache`). In place.
- **#113** O(log T) bisect index — `_build_tempo_index`/`_cumulative_ms` (`:129-166`);
  `calculate_time_ms(0, tick)` remains an exact from-zero computation. Re-verified 0-frame drift on
  a synthetic 5-minute song (final frame 18000).
- **#93/#95** SMPTE/zero/negative `ticks_per_beat` — `TempoMap.__init__` raises `ValueError` for
  `ticks_per_beat is None or < 1` (`:101-107`); `parse_midi_to_frames` rejects it earlier (`:40-45`).
  Both agree on the `< 1` boundary. In place.
- **#94** widened 1–2000 BPM band + count-and-warn in the default parser (`:54-93`). In place
  (TEMPO-12/#259 is the still-open analysis-path sibling).
- **#96** same-frame note collapse in `nes/emulator_core.py:16-46` (louder wins, later wins on tie,
  warns with count). In place.
- **#99** single `FRAME_ALIGNMENT_TOLERANCE_MS = 0.5` (`:23`) referenced by `is_frame_aligned`
  (`:259`), `_validate_frame_boundaries` (`:472`), `_check_frame_alignment` (`:839`). In place.
- **#160** note-off pairing — `compile_channel_to_frames` derives `end_frame` from the matching
  note-off in `all_events_sorted` (captured pre-collapse), falling back to `sustain_frames` only when
  unpaired (`nes/emulator_core.py:54-93`); `range(start_frame, end_frame)` correctly emits up to but
  not including the note-off frame. In place.

---

## Dedup notes

- Pre-fetched `/tmp/audit/issues.json`: the only OPEN tempo issues are #97, #98, #259, #260 — all
  four are reported above as Existing and skipped. #208/#209/#210/#211 are absent from the open list
  because they were filed and fixed (referenced by name in the current code comments).
- `docs/audits/AUDIT_TEMPO_2026-07-05.md` is the prior pass; the code is byte-identical to it
  (no commits since 2026-07-05 22:22), so its findings and confirmed-fixed list carry forward
  unchanged. Earlier passes (`AUDIT_TEMPO_2026-07-03.md`, `AUDIT_TEMPO_2026-06-29.md`) cover
  TEMPO-01…TEMPO-11.
- No other domain audit report references these items.

---

Suggested next step:
```
/audit-publish docs/audits/AUDIT_TEMPO_2026-07-06.md
```
