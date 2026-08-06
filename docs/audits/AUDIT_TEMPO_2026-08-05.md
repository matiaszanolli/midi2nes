# Tempo & Frame-Timing Audit — 2026-08-05

## 1. Summary

**Invariant verdict: PASS.** Frame timing stays on the 60Hz grid on the live MIDI→ROM
path. The keystone conversion
`get_frame_for_tick(tick) = round(calculate_time_ms(0, tick) / FRAME_MS)`
(`tracker/tempo_map.py:198-201`) measures time **absolutely from tick 0** on every call
via the bisect-based cumulative-ms index (`_build_tempo_index`/`_cumulative_ms`,
`:129-166`), so rounding error is bounded (±0.5 frame per note) and **does not
accumulate**. `_cumulative_ms(0) == 0.0` (tick 0 → frame 0, no off-by-one), segments are
computed in `np.float64` with no per-segment int truncation, and every mutation path
(`add_tempo_change`, `EnhancedTempoMap.add_tempo_change`, `_minimize_tempo_changes`,
`_smooth_tempo_transitions`, `_align_to_frames`) clears both `_time_cache` and
`_tempo_index`. No code changes have landed in `tracker/tempo_map.py`,
`tracker/loop_manager.py`, `tracker/parser_fast.py`, or `constants.py` since the prior
tempo audit (2026-07-19); the only touch in scope since then
(`nes/emulator_core.py`, commit `bc5467a`) added a noise-channel strike-decay curve and
did not change frame-index math.

All prior TEMPO-0x/1x findings the skill references remain fixed and in place (#93, #94,
#95, #96, #97, #98, #99, #113, #160, #208, #209, #210, #259, #260, #317, #343, #344,
#345). The D7 optimization/loop-alignment code remains unreachable from the CLI
(`optimize_tempo_changes`, `_align_to_frames`, `_minimize_tempo_changes`,
`_smooth_tempo_transitions` have no caller outside `tracker/tempo_map.py` and its tests)
and is documented in code — not re-filed. The residual inconsistency the skill's D4
section calls out — `parse_midi_to_frames_with_analysis` allegedly still having a bare
`except TempoValidationError: continue` unlike the fixed default-path parser — is **no
longer present**: both parse entry points now share `_build_tempo_map`
(`tracker/parser_fast.py:24-67`), which counts and warns on every dropped tempo change
(`:56-65`). This is stale skill prose, not a code defect; flagged for `audit-sync`, not
filed as a finding.

**Two prior findings remain open and unfixed**, re-verified present in the current code:
TEMPO-17 (#382, the three frame-alignment verdict predicates still disagree) and
TEMPO-18 (#383, base `TempoMap.__init__` still lacks the non-positive `initial_tempo`
guard `EnhancedTempoMap` has). Both are confined to dead/test-only code paths.

**One new finding this round:** `tracker/parser.py` — already known dead/test-only
(TD-26/#346) — constructs its `EnhancedTempoMap` without passing `ticks_per_beat`, so it
silently assumes PPQ 480 regardless of the parsed MIDI file's actual division. This is a
distinct root cause from #346 (which flags the whole module as unreachable, not this
specific PPQ defect) and would be a genuine HIGH-severity drift bug if that parser were
ever reconnected. LOW today because the path is confirmed unreachable in production.

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 3 (1 NEW + 2 confirmed-existing/open).

**Highest-leverage fix:** none is a live-path timing bug. If any cleanup is worth
doing, it's TEMPO-17 (#382) — unifying the three frame-alignment verdict predicates —
since it gates the FRAME_ALIGNED optimization path that would need to be trustworthy
before any future re-wiring.

## 2. Findings

### TEMPO-19: `tracker/parser.py` builds its `EnhancedTempoMap` without passing `ticks_per_beat`, hardcoding PPQ 480
- **Severity**: LOW
- **Dimension**: 5 (PPQ / Division Parsing)
- **Location**: `tracker/parser.py:30-34`
- **Status**: NEW (distinct from TD-26/#346, which flags the module as production-dead in general but does not call out this specific PPQ defect)
- **Description**: `tracker/parser.py` — the older full parser, confirmed on no
  production pipeline path and imported only by tests per `CLAUDE.md` / `_audit-common.md`
  (TD-26/#346) — builds its tempo map as:
  ```python
  tempo_map = EnhancedTempoMap(
      initial_tempo=500000,  # 120 BPM
      validation_config=config,
      optimization_strategy=None  # Disable optimization
  )
  ```
  with no `ticks_per_beat` argument, so it silently takes `EnhancedTempoMap.__init__`'s
  default of 480 (`tracker/tempo_map.py:229`) instead of `mid.ticks_per_beat` — even
  though `mid = mido.MidiFile(midi_path)` is opened two lines earlier and the real value
  is available. This is the same class of bug already fixed on the live path
  (`tracker/parser_fast.py:38` passes `ticks_per_beat=mid.ticks_per_beat`) but was never
  applied here. Unlike the two `main.py` analysis-only `EnhancedTempoMap` sites (D3,
  #98/#119), this tempo map in `parser.py` **is** fed real tick data via
  `add_tempo_change` and **is** used for every note's `get_frame_for_tick` call
  (`tracker/parser.py:46-50, 62`), so if PPQ ≠ 480 for a parsed file, every frame index it
  produces would be wrong by the ratio `480 / actual_ticks_per_beat` — a genuine
  cumulative-drift bug, not an inert one.
- **Evidence**: `tracker/parser.py:30-34` vs. the fixed sibling `tracker/parser_fast.py:36-41`
  (which explicitly comments "CRITICAL: Use the MIDI file's ticks_per_beat for accurate
  timing"). A `grep -rn "ticks_per_beat" tracker/parser.py` returns no hits — the value is
  never read from `mid`.
- **Impact**: None on shipped ROMs today — confirmed via `grep -rln "from tracker.parser
  import\|tracker\.parser\."` that no non-test module imports `tracker/parser.py`
  (TD-26/#346). It only matters if a test happens to load a MIDI fixture with PPQ ≠ 480
  through this module (producing silently wrong frame numbers in that test's assertions)
  or if the module is ever reconnected to a live pipeline stage without this being
  noticed first.
- **Related**: TD-26/#346 (parser.py production-dead, general); #93/#95 (the PPQ guards
  this module's `TempoMap.__init__` still correctly enforces `ticks_per_beat >= 1`, just
  with the wrong default value); D3's now-inert `main.py` sites (#98/#119), a different
  root cause (those never call `add_tempo_change`, so their default `ticks_per_beat` is
  provably inert — this one is fed real data and is not).
- **Suggested Fix**: Either delete `tracker/parser.py` per #346's recommendation, or, if
  it is kept for tests, pass `ticks_per_beat=mid.ticks_per_beat` at line 30 to match
  `parser_fast.py`.

### TEMPO-17: Frame-alignment verdict predicates disagree — asymmetric `% FRAME_MS` and single-segment time basis vs. `is_frame_aligned`
- **Severity**: LOW
- **Dimension**: 8 (Frame-Edge Off-By-One / verdict consistency)
- **Location**: `tracker/tempo_map.py:263-268` (`is_frame_aligned`, correct), `:477-484`
  (`_validate_frame_boundaries`, asymmetric), `:863-876` (`_check_frame_alignment`,
  asymmetric + single-segment time basis)
- **Status**: Existing: #382 (OPEN) — re-verified present in current code, not re-filed
- **Description**: `_validate_frame_boundaries` and `_check_frame_alignment` still use
  `remainder = time % FRAME_MS; if remainder > TOL: raise`, which is asymmetric (only
  catches distance *above* the lower frame boundary; a tick just below the *next*
  boundary is wrongly flagged misaligned), while `is_frame_aligned` correctly uses the
  symmetric nearest-boundary distance. `_check_frame_alignment` additionally still
  derives time from a single-segment `change.tick * (prev_tempo / ticks_per_beat)` basis
  rather than the true cumulative `calculate_time_ms(0, tick)`, so it is doubly wrong
  under multi-tempo input. All three predicates remain dead on the live path (called only
  from `tests/test_tempo_map.py`), gating the still-unreachable FRAME_ALIGNED
  optimization strategy (D7/#97).
- **Impact**: None on shipped ROMs today. Confirmed unchanged since AUDIT_TEMPO_2026-07-19.
- **Related**: #99 (TEMPO-07, tolerance-constant consolidation — the unfinished half);
  D7/#97 (the dead FRAME_ALIGNED path these gate).
- **Suggested Fix**: See #382 — rewrite both to reuse `is_frame_aligned`'s symmetric,
  cumulative-time logic.

### TEMPO-18: Base `TempoMap.__init__` lacks the non-positive `initial_tempo` guard that `EnhancedTempoMap` has
- **Severity**: LOW
- **Dimension**: 3 (Default / Missing Tempo Fallback)
- **Location**: `tracker/tempo_map.py:88-114` (base `TempoMap.__init__`) vs. `:238-241`
  (`EnhancedTempoMap.__init__` guard, #317)
- **Status**: Existing: #383 (OPEN) — re-verified present in current code, not re-filed
- **Description**: `TempoMap.__init__` still guards only `ticks_per_beat < 1`
  (`:101`), not a non-positive `initial_tempo`. `TempoMap(initial_tempo=0,
  ticks_per_beat=480)` still constructs silently; `_build_tempo_index` computes
  `us_per_tick = 0`, collapsing every tick to frame 0 with no error, and
  `get_tempo_bpm_at_tick` would raise a bare `ZeroDivisionError` rather than
  `TempoValidationError`.
- **Impact**: None today — confirmed (again) via `grep -n "TempoMap("` excluding
  `Enhanced` and tests that no live construction site instantiates the base class
  directly.
- **Related**: #317/TEMPO-14 (the sibling guard already present in `EnhancedTempoMap`);
  TD-26/#346 and TEMPO-19 above (`tracker/parser.py`, a base-`TempoMap`-adjacent dead
  path with its own distinct PPQ defect).
- **Suggested Fix**: See #383 — add the same non-positive guard to the base class.

## 3. Dimension Coverage Notes

- **D1 (drift):** Clean — absolute-from-0 conversion via `_cumulative_ms`, `np.float64`
  segment math, no truncation, caches invalidated on every mutation. No code changed
  since the prior audit's empirical 5-minute/0-frame-drift verification.
- **D2 (multi-tempo):** Clean — per-track `current_tick` reset matches MIDI delta-time
  semantics (track-local); `bisect_right(ticks, t) - 1` makes a tempo change effective
  at its own tick with no off-by-one; duplicate same-tick changes resolve last-wins via
  the tick-only stable sort + `bisect_right` (#210). The FRAME_ALIGNED re-snap in
  `add_tempo_change` (`:310-351`) that could in theory move a tick across a nearby event
  is confirmed still inert on every live construction site (`parser_fast.py`,
  `main.py`×2 pass/default `optimization_strategy=None`/never call `add_tempo_change`
  with real data); the only default-strategy construction sites left
  (`pattern_detector_parallel.py:489`, a `__main__` self-test block) never feed it real
  ticks either.
- **D3 (fallback):** `main.py:640` / `:852` analysis-only maps confirmed still inert and
  documented (#98/#119) — not re-filed. Missing-`set_tempo` correctly falls back to the
  `(0, 500000)` = 120 BPM initial tempo. `EnhancedTempoMap(initial_tempo=0)` correctly
  raises `TempoValidationError` (#317) — but see TEMPO-18 for the base-class gap. The
  skill's flagged residual inconsistency in `parse_midi_to_frames_with_analysis`'s error
  handling is **stale** — both parse entry points now share `_build_tempo_map`
  (`tracker/parser_fast.py:24-67`), which counts/warns uniformly; no bare `except:
  continue` remains on either path.
- **D4 (extreme bounds):** Widened 1–2000 BPM band with `max_tempo_change_ratio=inf`
  (#94) unchanged; dropped changes counted + warned via `print` reaching CLI output.
  Same-frame collapse (#96) and its tie-break (#344/TEMPO-15) confirmed fixed
  (`nes/emulator_core.py:37-43`: equal velocity keeps the later event, matching the
  docstring). `_frame_times` cap confirmed still absent (grep returns nothing). No
  float64 overflow risk identified.
- **D5 (PPQ):** `parser_fast.py`'s early check and `TempoMap.__init__` both gate at `< 1`
  (agree exactly, #93/#95) on the live path. New finding TEMPO-19: the dead
  `tracker/parser.py` sibling never passes `ticks_per_beat` at all, defaulting to 480.
- **D6 (loops):** `EnhancedLoopManager` (opt-in `--with-analysis` only, and
  `tracker/parser.py`, non-default) reads per-event stamped tempo instead of a
  mis-unit'd `get_tempo_at_tick` lookup (#345); `end` is treated as an exclusive index
  consistently between `detect_loops` and `generate_jump_table`. Confirmed via grep that
  `jump_table`/`generate_jump_table`/`EnhancedLoopManager` have no caller outside
  `tracker/loop_manager.py`, `tracker/parser.py`, `tracker/parser_fast.py`'s
  `--with-analysis` branch, and tests — no off-by-one found; path remains off the
  default pipeline.
- **D7 (optimization):** Confirmed unreachable from CLI (grep: no non-test caller
  outside `tracker/tempo_map.py`); WARNING docstrings in place (#97) — not re-filed.
- **D8 (frame edges):** Tick 0 → frame 0 confirmed (`_cumulative_ms(0) == 0.0`).
  `compile_channel_to_frames`'s `range(start_frame, end_frame)`
  (`nes/emulator_core.py:107`) emits the last sounding frame correctly, with
  note-off pairing (#160) deriving `end_frame` from the matching note-off where
  available. Verdict-predicate inconsistency persists → TEMPO-17 (#382, existing).

---

Suggested next step:

```
/audit-publish docs/audits/AUDIT_TEMPO_2026-08-05.md
```
