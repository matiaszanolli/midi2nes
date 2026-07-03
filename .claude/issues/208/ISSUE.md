# TEMPO-08: tick == 0 tempo changes bypass all validation — zero/negative initial tempo silently corrupts the whole song

Issue: #208

**Severity:** CRITICAL · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-03.md

## Description
`EnhancedTempoMap.add_tempo_change` special-cases `tick == 0` to replace the initial tempo directly (`self.tempo_changes[0] = (0, tempo)`) and returns immediately — **before** `_validate_basic_tempo` (BPM-range check) is ever called. Every other tick goes through `_validate_basic_tempo`, which would reject a 0 or out-of-range BPM. A MIDI file whose very first `set_tempo` meta-event (at tick 0, which is exactly where DAWs conventionally place the initial tempo) carries `tempo=0` or a negative value is therefore accepted unconditionally, with no `TempoValidationError` and no warning. This is the same class of bug as the already-fixed #93 (negative frame indices) and #95 (`ticks_per_beat==0` -> `inf`), but reachable through the *tempo* value at tick 0 rather than `ticks_per_beat` — a path those fixes did not close.

## Location
`tracker/tempo_map.py:262-271` (the `if tick == 0:` early-return branch of `EnhancedTempoMap.add_tempo_change`); contrast with the validated path at `:277` (`self._validate_basic_tempo(change)`) taken for every `tick != 0`.

## Evidence
Built and parsed a real `.mid` file (`ticks_per_beat=480`) whose first event is `MetaMessage('set_tempo', tempo=0, time=0)`, followed by two notes, then a later `set_tempo(500000)` recovery event, through the actual `parse_midi_to_frames`. Every event before the real tempo change collapses onto frame 0 (`us_per_tick = tempo/ticks_per_beat = 0`). Separately, a negative tempo at tick 0 (`add_tempo_change(0, -500000, ...)`) is accepted with no error and produces negative frame indices for the entire song (`get_frame_for_tick(480) -> -30`), reproducing #93's exact symptom via a different, un-guarded entry point. Re-verified against current code (lines 262-271 unchanged from the audit's citation).

## Impact
Silent, total corruption of song timing from t=0. Every note before the (if any) next valid tempo change either collapses onto one frame (tempo=0 — the emulator core's same-frame collapse, #96, then drops all but one note) or is written at negative JSON frame keys (negative tempo), which downstream stages (`nes/emulator_core.py`, exporters) do not guard against. No error, no warning — the ROM compiles "successfully" with scrambled or missing music.

## Related
Same symptom class as closed #93 (SMPTE/negative `ticks_per_beat`) and closed #95 (`ticks_per_beat==0`), but via the tempo value at tick 0, which those fixes' guards do not cover. Distinct root cause from #209 (TEMPO-09, the `tick > 0` counterpart).

## Suggested Fix
Call `_validate_basic_tempo(change)` (or at minimum a `tempo >= 1` and BPM-range check) before the `tick == 0` early return in `EnhancedTempoMap.add_tempo_change`, so tick 0 is held to the same standard as every other tick.

## Completeness Checks
- [ ] **SIBLING**: Same tick==0-bypasses-validation pattern checked for any other early-return branch keyed on tick (base `TempoMap.add_tempo_change`, `_validate_tempo_change`)
- [ ] **TESTS**: A regression test pins `tempo=0` and negative-tempo at tick 0 both raising `TempoValidationError`
