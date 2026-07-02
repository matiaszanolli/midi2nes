# NH-16: Sub-C1 notes get `base_timer = 0`, emitting a +127 pitch macro that wraps the 11-bit timer

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

## Description
`midi_note_to_timer_value` (`exporter/exporter_ca65.py:47-49`) returns **0** for
`midi_note < 24` instead of a clamped table value. The live core clamps the frame's
`pitch` to the channel range (`nes/pitch_table.py:100`, note < 24 -> `pitch = table[24]`),
but the frame's `note` field stays the raw MIDI note (`nes/emulator_core.py:93,107`) and
neither `tracker/track_mapper.py` nor the exporter clamps it upward. In bytecode mode the
pitch macro is `pitch_val - base_timer = table[24] - 0`, clamped by `_encode_macro_offset`
to `+127`. At runtime the engine indexes the full 0-127 period table with the raw note
(clamped to `$7FF`/near-`$7FF` for sub-24 entries) and adds +127: the 11-bit timer
overflows into bit 3 of the high byte, part of the length-load field of
`$4003`/`$4007`/`$400B`, so the written timer-high bits are wrong and the period wraps to
a tiny value.

## Location
`exporter/exporter_ca65.py:47-49` (`midi_note_to_timer_value` guard `return 0`),
`:983-984` (only an *upper* note clamp — no lower clamp to 24), `:1016-1018`/`:1032-1034`
(offset = `pitch_val - base_timer`); consumer `nes/audio_engine.asm:390-399,422-431,449-457`
(16-bit add, high byte `ora #$08` -> `$4003/$4007/$400B`).

## Evidence
Reproduced numerically against HEAD code:
```
pulse1  note 21: frame_pitch=2047 base_timer=0 offset=+127 table[21]=2047 sum=0x87E (>0x7FF)
triangle note 21: frame_pitch=1709 base_timer=0 offset=+127 table[21]=2032 sum=0x86F (>0x7FF)
```
`0x87E` writes `$4002=$7E`, `$4003=$08` -> effective timer `126` -> ~875 Hz for a note that
should be ~27.5 Hz (A0). The direct-export path is unaffected (it re-clamps the frame
`pitch` at `exporter/exporter_ca65.py:203-204` and never uses `base_timer`).

## Impact
Any melodic content below C1 (piano A0-B0, 5-string bass low B, octave-down synth bass)
plays 4-5 octaves too high on pulse/triangle in the **default** (patterns) pipeline.
Noise/DPCM are unaffected.

## Related
#41 (same anti-pattern in a dead method), closed #78/#16 (previous base-timer scale mismatches in this exact expression), NH-18 (same engine add path).

## Hardware ref
`docs/APU_PITCH_TABLE_REFERENCE.md` §1/§3 (timers are 11-bit and the full 0-127 table is
clamp-generated — a base of 0 is not a legal period source); `docs/APU_PULSE_REFERENCE.md`
§2 (`$4003` = `llll.lHHH` — only 3 timer-high bits, the rest is the length-counter load
field).

## Suggested Fix
Make `midi_note_to_timer_value` clamp instead of returning 0
(`midi_note = max(24, min(midi_note, 119))` then index the per-channel table), and/or
clamp `note` to >= 24 for tone channels next to the existing `note > 95` clamp at
`exporter/exporter_ca65.py:983-984` so note and pitch stay on the same scale.

## Completeness Checks
- [ ] **RANGE**: If the fix emits NES values, they are clamped to hardware range (byte / 11-bit timer)
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
