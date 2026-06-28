# NH-02: Triangle channel uses the pulse timer formula → every triangle note an octave low

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #12

## Description
`PitchProcessor.get_channel_pitch(note, 'triangle')` returns `self.note_table[note]`, built with the pulse formula `timer = fCPU/(16*freq) - 1` (pitch_table.py:87). Triangle hardware uses `f = fCPU/(32*(t+1))` — for the same timer the triangle sounds one octave lower. No separate triangle table, no octave compensation.

## Evidence
A4 (MIDI 69): `generate_note_table()[69] = 253` → triangle `1789773/(32*254) ≈ 220 Hz = A3`. Correct triangle timer for A4 is 126.

## Impact
Every triangle note (typically the bassline) is an octave flat on every ROM via `export_direct_frames`.

## Hardware ref
`docs/APU_PITCH_TABLE_REFERENCE.md` §1; `docs/APU_TRIANGLE_REFERENCE.md` §3.

## Related
NH-03.

## Suggested Fix
Generate a distinct triangle table using the `/32` formula and select it by channel in `get_channel_pitch`.
