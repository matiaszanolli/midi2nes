**Severity:** HIGH · **Domain:** exporters · **Source:** AUDIT_EXPORTERS_2026-06-29.md

Triangle continuation frames use the pulse `/16` base timer, corrupting sustained-triangle pitch.

## Description
On the **first** frame of a note (`:990`) `base_timer` is computed with the channel, so triangle correctly uses `NES_TRIANGLE_TABLE`. On every **continuation** frame of the same note (`:1005`, the `else` branch that extends `dur`) the `channel` argument is omitted, so `midi_note_to_timer_value` defaults `channel=None` and returns `NES_NOTE_TABLE` (the pulse `/16` table). The per-frame `pitch_offset` is then `triangle_pitch_val − pulse_base_timer`, a large constant (e.g. for note 36: `854 − 1709 = −855`, clamped to `−128`). The engine adds that offset to the genuine triangle period each frame.

## Location
`exporter/exporter_ca65.py:1005` (`base_timer = self.midi_note_to_timer_value(note)` — **no `channel` arg**) vs `:990` (`...(note, channel)`).

## Spec ref
`docs/APU_TRIANGLE_REFERENCE.md` (triangle period table is an octave below pulse for the same note); `docs/APU_PITCH_TABLE_REFERENCE.md`. Consumer: `audio_engine.asm` adds `temp_pitch` to `triangle_period_*`.

## Evidence
```python
990:  base_timer = self.midi_note_to_timer_value(note, channel)   # first frame: correct
1005: base_timer = self.midi_note_to_timer_value(note)            # continuation: pulse table
```
Pulse vs triangle timer: note 36 = 1709 vs 854 (diff −855), note 48 = 854 vs 426 (−428), note 60 = 426 vs 212 (−214) — all far beyond the ±127 clamp.

## Impact
Every held triangle note (≥2 frames — essentially all bass/lead-triangle content) gets a spurious −128 pitch offset on its sustain frames, detuning it. Macro-bytecode (default) path, triangle channel. The first frame plays in tune, then the note bends; audible on every song with sustained triangle.

## Related
Octave fixes at `exporter/exporter_ca65.py:50-57` / `:877-897` — same class of bug re-introduced on the continuation call site.

## Suggested Fix
Pass `channel` on the `:1005` call: `base_timer = self.midi_note_to_timer_value(note, channel)`. (The same `pitch_val - base_timer` line is otherwise identical to the first-frame branch.)

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels)
- [ ] **TESTS**: A regression test pins this specific fix
