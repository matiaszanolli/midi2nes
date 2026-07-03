# #209: TEMPO-09: set_tempo(tempo=0) at any tick > 0 raises an unguarded ZeroDivisionError, crashing the entire parse

**Severity:** HIGH · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-03.md
**Labels:** bug, high, tempo

## Description
`_validate_basic_tempo` computes `bpm = 60_000_000 / change.tempo` (`tracker/tempo_map.py:382`) with no zero-guard, before the BPM-range check that would otherwise reject an invalid tempo via the intended `TempoValidationError` path. For `tick > 0` (the tick-0 bypass described in the companion issue does not apply here — this path *does* reach `_validate_basic_tempo` via `add_tempo_change:277`), a `set_tempo` meta-event with `tempo=0` raises a raw `ZeroDivisionError`, a different exception class than the one `parse_midi_to_frames`'s per-tempo-change handler explicitly guards against (`except TempoValidationError: continue`, `tracker/parser_fast.py:72`, added for #94 specifically to make invalid tempo changes non-fatal). The `ZeroDivisionError` therefore propagates uncaught out of `parse_midi_to_frames`, aborting the entire pipeline run for the whole file — not just the offending section.

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
                ~~~~~~~~~~~~^~~~~~~~~~~~~~~~
ZeroDivisionError: division by zero
```
Re-verified against current code: `tracker/tempo_map.py:382` (`_validate_basic_tempo`) and `:405` (`_validate_tempo_change`, same unguarded division) both lack a `change.tempo >= 1` check; `tracker/parser_fast.py:72` still only catches `TempoValidationError`.

## Impact
Total pipeline failure (no JSON, no ROM, an unhandled Python traceback surfaced to the CLI user) for any MIDI file containing a degenerate/corrupted `tempo=0` event anywhere after tick 0 — precisely the class of malformed input the `except TempoValidationError` guard at `parser_fast.py:72` (added for #94) was written to make non-fatal. A single bad meta-event in one track kills the whole conversion instead of being counted/warned like every other rejected tempo change. There is a workaround (repair the source MIDI), so this is not CRITICAL, but it is a hard crash on realistic (if unusual) input where graceful degradation was clearly the intended design.

## Suggested Fix
Guard `change.tempo >= 1` at the top of `_validate_basic_tempo` (and `_validate_tempo_change`) and raise `TempoValidationError` instead of dividing, so the existing `except TempoValidationError: continue` in `parser_fast.py` catches it like any other invalid tempo (and increments `dropped_tempo_changes` so the user is warned, per #94's fix).

## Completeness Checks
- [ ] **CONTRACT**: `dropped_tempo_changes` warning path in `parser_fast.py` still fires for this newly-guarded case (no silent drop without the existing warning)
- [ ] **SIBLING**: Both `_validate_basic_tempo` (:382) and `_validate_tempo_change` (:405) get the same zero-guard
- [ ] **TESTS**: A regression test pins `tempo=0` at `tick > 0` raising `TempoValidationError` (not `ZeroDivisionError`) and being dropped/warned rather than crashing the parse

---

# #210: TEMPO-10: Duplicate tempo changes at the same tick resolve by numeric tempo value, not insertion order

**Severity:** HIGH · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-07-03.md
**Labels:** bug, high, tempo

## Description
`tempo_changes` is a list of `(tick, tempo)` tuples (`tracker/tempo_map.py:118-119`, `TempoMap.add_tempo_change`: `self.tempo_changes.append((tick, tempo)); self.tempo_changes.sort()`). `sort()` on tuples orders first by `tick`, then — for equal ticks — by `tempo` **ascending**, not by insertion order. `get_tempo_at_tick`/`_cumulative_ms` (`:152-168`) then pick the *last* entry at or before the query tick via `bisect.bisect_right(ticks, tick) - 1`, which for a tied tick means "the numerically largest tempo value wins," not "the tempo change that was added last."

Standard MIDI semantics require that when two `set_tempo` events land on the same tick (plausible in multi-track files, or two meta-events with a 0 delta-time between them), the one that appears **later in processing order** is authoritative. This code silently substitutes "larger tempo value" for "later in order," which are unrelated.

## Evidence
Built and parsed a real `.mid` file with tempo events in file order `500000 → 600000 → 250000`, the second and third at the identical tick (480, delta-time 0 between them). Per standard MIDI order, 250000 (240 BPM) should be the active tempo from tick 480 onward. The actual parsed output:
```
track_0 {'frame': 30, 'note': 60, ..., 'tempo': 600000}   # should be 250000
track_0 {'frame': 66, 'note': 60, ..., 'tempo': 600000}
track_0 {'frame': 66, 'note': 64, ..., 'tempo': 600000}
track_0 {'frame': 138,'note': 64, ..., 'tempo': 600000}
```
600000 won — not because it was processed last (it wasn't; 250000 was), but because it is numerically larger and `sort()` places it after `(480, 250000)` in the tuple ordering. Confirmed directly against current code:
```python
tm = TempoMap(ticks_per_beat=480)
tm.add_tempo_change(1000, 600000)   # added first
tm.add_tempo_change(1000, 400000)   # added second, should win
tm.tempo_changes -> [(0, 500000), (1000, 400000), (1000, 600000)]
tm.get_tempo_at_tick(1000) -> 600000   # wrong: the first-added value wins because it sorts last
```

## Impact
Wrong tempo for the remainder of the song (or section) from the tied tick onward, silently — same impact class as the already-fixed #94 (dropped tempo changes), just via a different root cause (tie-break order instead of validation rejection). Reachable on the live default pipeline (`parse_midi_to_frames` calls `EnhancedTempoMap.add_tempo_change` per `set_tempo` event in file order, with `optimization_strategy=None` so no re-snapping intervenes).

## Suggested Fix
Track insertion order explicitly (e.g. append `(tick, tempo, seq)` with a monotonic `seq` counter, or use a stable structure keyed by tick that always overwrites on re-insertion) so that for duplicate ticks the most-recently-added tempo is authoritative, matching MIDI event order rather than numeric tempo value.

## Completeness Checks
- [ ] **CONTRACT**: `EnhancedTempoMap.enhanced_changes.sort(key=lambda x: x.tick)` (stable sort, keyed on tick only) still reflects the same fixed tie-break semantics after the change
- [ ] **SIBLING**: `_build_tempo_index` (`tracker/tempo_map.py:123-142`) consumes `self.tempo_changes` directly — verify it doesn't need its own tie-break fix once insertion order is tracked
- [ ] **TESTS**: A regression test pins duplicate-tick insertion order winning over numeric tempo value
