# TEMPO-09: set_tempo(tempo=0) at any tick > 0 raises an unguarded ZeroDivisionError, crashing the entire parse

Issue: #209

**Severity:** HIGH · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-03.md

## Description
`_validate_basic_tempo` computes `bpm = 60_000_000 / change.tempo` with no zero-guard, before the BPM-range check that would otherwise reject an invalid tempo via the intended `TempoValidationError` path. For `tick > 0` (the tick-0 bypass of #208/TEMPO-08 does not apply here — this path *does* reach `_validate_basic_tempo`), a `set_tempo` meta-event with `tempo=0` raises a raw `ZeroDivisionError`, a different exception class than the one `parse_midi_to_frames`'s per-tempo-change handler explicitly guards against (`except TempoValidationError: continue`, added by #94 specifically to make invalid tempo changes non-fatal). The `ZeroDivisionError` therefore propagates uncaught out of `parse_midi_to_frames`, aborting the entire pipeline run for the whole file.

## Location
`tracker/tempo_map.py:382` (`bpm = round(60_000_000 / change.tempo, 6)` in `_validate_basic_tempo`), reached via `add_tempo_change` at `:277`; the call site that fails to catch it is `tracker/parser_fast.py:65-77` (`except TempoValidationError: continue` — does not catch `ZeroDivisionError`).

## Evidence
Built and parsed a real `.mid` file with a `set_tempo(tempo=0)` meta-event after an initial valid tempo and one note, through the actual `parse_midi_to_frames`:
```
Traceback (most recent call last):
  File "tracker/parser_fast.py", line 67, in parse_midi_to_frames
    tempo_map.add_tempo_change(
  File "tracker/tempo_map.py", line 277, in add_tempo_change
    self._validate_basic_tempo(change)
  File "tracker/tempo_map.py", line 382, in _validate_basic_tempo
    bpm = round(60_000_000 / change.tempo, 6)
ZeroDivisionError: division by zero
```
Re-verified against current code: `tracker/tempo_map.py:382` and `:405` (`_validate_tempo_change`, same unguarded division) both lack a `change.tempo >= 1` check; `tracker/parser_fast.py:72` still only catches `TempoValidationError`.

## Impact
Total pipeline failure (no JSON, no ROM, an unhandled Python traceback surfaced to the CLI user) for any MIDI file containing a degenerate/corrupted `tempo=0` event anywhere after tick 0. A single bad meta-event in one track kills the whole conversion instead of being counted/warned like every other rejected tempo change. There is a workaround (repair the source MIDI), so this is not CRITICAL, but it is a hard crash on realistic (if unusual) input where graceful degradation was clearly the intended design.

## Related
#208 (TEMPO-08, same `tempo == 0` degenerate value, but the `tick == 0` counterpart silently corrupts instead of crashing); the `except TempoValidationError` guard this bypasses was introduced for #94 (TEMPO-02, closed).

## Suggested Fix
Guard `change.tempo >= 1` at the top of `_validate_basic_tempo` (and `_validate_tempo_change`) and raise `TempoValidationError` instead of dividing, so the existing `except TempoValidationError: continue` in `parser_fast.py` catches it like any other invalid tempo (and increments `dropped_tempo_changes` so the user is warned, per #94's fix).

## Completeness Checks
- [ ] **CONTRACT**: `dropped_tempo_changes` warning path in `parser_fast.py` still fires for this newly-guarded case (no silent drop without the existing warning)
- [ ] **SIBLING**: Both `_validate_basic_tempo` (:382) and `_validate_tempo_change` (:405) get the same zero-guard
- [ ] **TESTS**: A regression test pins `tempo=0` at `tick > 0` raising `TempoValidationError` (not `ZeroDivisionError`) and being dropped/warned rather than crashing the parse
