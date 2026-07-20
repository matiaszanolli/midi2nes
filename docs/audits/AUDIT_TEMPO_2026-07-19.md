# Tempo & Frame-Timing Audit — 2026-07-19

## 1. Summary

**Invariant verdict: PASS.** Frame timing stays on the 60Hz grid on the live
MIDI→ROM path. The keystone conversion
`get_frame_for_tick(tick) = round(calculate_time_ms(0, tick) / FRAME_MS)`
(`tracker/tempo_map.py:198-201`) measures time **absolutely from tick 0** on every
call, so rounding error is bounded (±0.5 frame per note) and **does not accumulate**.
Empirically re-verified: a 5-minute song at 120 BPM / PPQ 480 (288 000 ticks) lands
its final note on frame **18000**, exactly `round(300000 / FRAME_MS)`, drift = 0
frames. The bisect cumulative-ms index (`_build_tempo_index` / `_cumulative_ms`,
`:129-166`) integrates each segment in `np.float64` with no per-segment int
truncation, `_cumulative_ms(0) == 0.0` (tick 0 → frame 0, no off-by-one), and the
`bisect_right(ticks, t) - 1` boundary makes a tempo change effective *at* its tick
(mid-song multi-tempo boundaries land correctly, D2). Every mutation path clears both
`_time_cache` and `_tempo_index` (D1 staleness clean).

All prior TEMPO-0x/1x findings the skill references are confirmed fixed and in place
(#93, #94, #95, #96, #97, #98, #99, #113, #160, #208, #209, #210, #259, #260, #317,
#344, #345). The optimization/loop-alignment code (D7, #97) remains unreachable from
the CLI (`optimize_tempo_changes`, `_align_to_frames`, `_minimize_tempo_changes`,
`_smooth_tempo_transitions` have no caller outside `tracker/tempo_map.py` and its
tests) and is documented in code — not re-filed. The prior `TEMPO-15` same-frame
tie-break discrepancy is now **fixed** in the current code
(`nes/emulator_core.py:37-38` keeps the later event on a velocity tie, matching its
docstring) — not re-filed.

**One correctness gap the two most recent tempo audits missed:** the three
frame-alignment *verdict* predicates that #99 was meant to unify reference the same
tolerance *constant* but compute alignment with **inconsistent math** and return
contradictory verdicts for the same tick. This is real but confined to dead
(test-only) code, so it is LOW.

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 2 (2 NEW).

**Highest-leverage fix:** TEMPO-17 — make `_validate_frame_boundaries` and
`_check_frame_alignment` use the same symmetric, cumulative-time alignment test as
`is_frame_aligned`, so the #99 consolidation is actually complete before any future
wiring of the FRAME_ALIGNED optimization path relies on these verdicts.

## 2. Findings

### TEMPO-17: Frame-alignment verdict predicates disagree — asymmetric `% FRAME_MS` and single-segment time basis vs. `is_frame_aligned`
- **Severity**: LOW
- **Dimension**: 8 (Frame-Edge Off-By-One / verdict consistency)
- **Location**: `tracker/tempo_map.py:477-484` (`_validate_frame_boundaries`), `:863-876` (`_check_frame_alignment`), vs. `:263-268` (`is_frame_aligned`)
- **Status**: NEW (incomplete #99 consolidation; not caught by AUDIT_TEMPO_2026-07-17/-07-18, which verified only that all three reference `FRAME_ALIGNMENT_TOLERANCE_MS`)
- **Description**: #99 consolidated the *tolerance value* into one constant but left the
  three predicates computing alignment three different ways, so they return
  contradictory verdicts:
  - `is_frame_aligned` (`:265-268`) is **correct**: it rounds to the nearest frame
    (`np.round(time_ms / FRAME_MS)`) and checks the **symmetric** distance
    `abs(time_ms - frame_number*FRAME_MS) < TOL`. A time just *below* a frame boundary
    is aligned.
  - `_validate_frame_boundaries` (`:480-481`) checks `remainder = time % FRAME_MS; if
    remainder > TOL: raise`. This is **asymmetric**: `remainder` measures distance only
    *above* the lower boundary, range `[0, FRAME_MS)`. A time `< TOL` *below* the next
    boundary has `remainder ≈ FRAME_MS - ε` and is wrongly judged misaligned. The
    correct test would be `remainder < TOL or remainder > FRAME_MS - TOL`.
  - `_check_frame_alignment` (`:867-872`) has the same asymmetric modulo test **and** a
    second defect: it derives time as `change.tick * (prev_tempo / ticks_per_beat)` —
    a **single-segment** basis that assumes the whole song from tick 0 ran at the tempo
    immediately preceding the change. For any song with an earlier tempo change this is
    not the true cumulative time (`calculate_time_ms(0, tick)`), so its verdict is
    doubly wrong under multi-tempo input.
- **Evidence**: With `EnhancedTempoMap(500000, ticks_per_beat=480)` and a tempo change
  to 300000 µs/qtr at tick 480, at **tick 506** the true cumulative time is 516.250 ms
  = 0.417 ms below frame boundary 31 (516.667 ms):
  ```
  is_frame_aligned(506)            -> True   (correct: 0.417 ms from a boundary)
  _validate_frame_boundaries(506)  -> RAISES (516.250 % 16.667 = 16.250 > 0.5)
  _check_frame_alignment(506)      -> RAISES (single-seg basis = 316.250 ms, rem 16.250)
  ```
  All three claim to answer "is tick 506 frame-aligned?"; one says yes, two say no.
- **Impact**: None on shipped ROMs today — all three predicates are dead on the live
  path (`_validate_frame_boundaries`/`_check_frame_alignment` are called only from
  `tests/test_tempo_map.py`; `is_frame_aligned` likewise). Blast radius is latent: these
  are the validity gate for the FRAME_ALIGNED optimization strategy (D7, currently
  unreachable). If that path is ever wired in, valid tempo changes landing just below a
  frame boundary would be spuriously rejected/mis-reported, and multi-tempo songs would
  be judged against a wrong time basis. It also makes the test suite assert
  self-contradictory behavior, masking the gap.
- **Related**: #99 (TEMPO-07, tolerance consolidation — this is the unfinished half); D7/#97 (the dead FRAME_ALIGNED path these gate).
- **Suggested Fix**: Rewrite both `_validate_frame_boundaries` and
  `_check_frame_alignment` to reuse `is_frame_aligned`'s logic — symmetric
  nearest-boundary distance on `calculate_time_ms(0, tick)` (the true cumulative time) —
  rather than an asymmetric `% FRAME_MS` test, and drop the single-segment
  `tick * us_per_tick` computation in `_check_frame_alignment`. Update the pinning tests
  accordingly.

### TEMPO-18: Base `TempoMap.__init__` lacks the non-positive `initial_tempo` guard that `EnhancedTempoMap` has
- **Severity**: LOW
- **Dimension**: 3 (Default / Missing Tempo Fallback)
- **Location**: `tracker/tempo_map.py:88-114` (base `TempoMap.__init__`) vs. `:238-241` (`EnhancedTempoMap.__init__` guard, #317)
- **Status**: NEW
- **Description**: `EnhancedTempoMap.__init__` rejects `initial_tempo <= 0` with a
  `TempoValidationError` before its BPM division (#317/TEMPO-14). The base
  `TempoMap.__init__` guards only `ticks_per_beat` (`:101`), not `initial_tempo`. A base
  `TempoMap(initial_tempo=0)` constructs silently; `get_tempo_bpm_at_tick` would then
  `ZeroDivisionError`, and `_build_tempo_index` computes `us_per_tick = 0`, collapsing
  **every** tick to time 0.0 → frame 0 with no error.
- **Evidence**: `TempoMap(initial_tempo=0, ticks_per_beat=480).get_frame_for_tick(1000)`
  returns `0` (all events pile onto frame 0) instead of raising. A grep for
  `TempoMap(` excluding `Enhanced` and tests returns **no** live construction site, so
  this is currently unreachable in production.
- **Impact**: None today (no live caller constructs the base class with untrusted
  tempo — the live front-end `tracker/parser_fast.py` uses `EnhancedTempoMap`). It is a
  defense-in-depth gap: `TempoMap` is a public exported symbol (`__all__`, `:880`) whose
  hardened subclass validates a case the base silently mis-handles.
- **Related**: #317/TEMPO-14 (the sibling guard in `EnhancedTempoMap`); TD-26/#346 (`tracker/parser.py`, a base-`TempoMap`-adjacent dead path).
- **Suggested Fix**: Add the same `if initial_tempo <= 0: raise TempoValidationError`
  (or `ValueError` for the base class, which does not import the tempo exception) at the
  top of `TempoMap.__init__`, mirroring the existing `ticks_per_beat` guard.

## 3. Dimension Coverage Notes

- **D1 (drift):** Clean — verified 0-frame drift over 5 min; absolute-from-0 conversion, float64 index, caches invalidated on every mutation.
- **D2 (multi-tempo):** Clean — per-track `current_tick` reset is correct MIDI semantics (delta times are track-local); segment boundary inclusive/exclusive is consistent; duplicate same-tick changes resolve last-wins via stable tick-only sort + `bisect_right` (#210).
- **D3 (fallback):** `main.py:683` / `:895` analysis-only maps confirmed inert and documented (#98/#119) — not re-filed. Missing-`set_tempo` correctly falls back to the `(0, 500000)` = 120 BPM initial. `EnhancedTempoMap(initial_tempo=0)` correctly raises (#317). New TEMPO-18 covers the un-hardened base class.
- **D4 (extreme bounds):** Widened 1–2000 BPM band with `max_tempo_change_ratio=inf` (#94); dropped changes counted + warned via `print` to stdout (reaches CLI). Same-frame collapse (#96) and its tie-break (#344/TEMPO-15) confirmed fixed. `_frame_times` cap confirmed gone. No overflow in float64.
- **D5 (PPQ):** `parser_fast` early check and `TempoMap.__init__` both gate at `< 1` (agree exactly, #93/#95). No constructor bypasses the guard on the live path.
- **D6 (loops):** `EnhancedLoopManager` (opt-in `--with-analysis` only) reads per-event stamped tempo instead of mis-unit'd `get_tempo_at_tick` (#345); `end` treated as exclusive index (`events[end-1]`). No off-by-one found; path is off the default pipeline.
- **D7 (optimization):** Confirmed unreachable from CLI (grep: no non-test caller); documented WARNING docstrings in place (#97) — not re-filed.
- **D8 (frame edges):** Tick 0 → frame 0 confirmed; `compile_channel_to_frames` `range(start, end)` emits the last sounding frame correctly with note-off pairing (#160). Verdict-predicate inconsistency → TEMPO-17.

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_TEMPO_2026-07-19.md
```
