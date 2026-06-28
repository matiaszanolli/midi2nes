# NH-11: note_to_timer range guard contradicts the channel ranges it serves

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #41

## Description
`note_to_timer` raises for `midi_note >= 96` ("out of NES range (24-95)"), but `channel_ranges` allow pulse up to MIDI 108 and the table covers 0–127. Inconsistent with the rest of the module (which clamps); would reject legal pulse notes 96–108. Unused on the live path but a consistency trap.

## Evidence
`if midi_note < 24 or midi_note >= 96: raise ValueError(... "(24-95)")` (pitch_table.py:133-134) vs `channel_ranges["pulse1"] = (24, 108)` (line 68).

## Impact
None today (unused); foot-gun if adopted.

## Hardware ref
`docs/APU_PITCH_TABLE_REFERENCE.md` §2.

## Related
NH-06.

## Suggested Fix
Align the guard with the clamp policy (clamp, don't raise), or remove the dead method.
