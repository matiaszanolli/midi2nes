# NH-HW-2026-08-21-4: --arranger sub-C1 triangle notes serialize to a detuned pitch — arranger pitch skips the channel-range clamp the serializer assumes

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/431
**Severity:** MEDIUM
**Domain:** nes-hardware
**Source report:** docs/audits/AUDIT_NES_HARDWARE_2026-08-21.md
**Filed:** 2026-08-21

## Location
- `arranger/pipeline_integration.py:351-380` (`midi_note_to_nes_pitch` clamps only to MIDI 0-127)
- `arranger/pipeline_integration.py:314-320` (triangle frames get `pitch = table[note]` unclamped)
- vs. `exporter/exporter_ca65.py:1212-1220` (serializer floors the stream note at 24, assuming the
  frame pitch was already channel-clamped — true only for the legacy front-end)
- `exporter/exporter_ca65.py:84-99` (`_encode_macro_offset` clamps the delta to +127)

## Description
The legacy front-end clamps notes to the channel range (triangle 24-96) before table lookup; the
arranger's `midi_note_to_nes_pitch` does not. A bass note 21 produces `pitch = table[21] = 2032`
while the serializer computes `base = table[24] = 1709`, giving raw offset +323 clamped to +127.
Runtime period 1709+127=1836 is neither the intended nor the hardware-representable pitch — a
detuned note roughly a quarter-tone below C1.

## Impact
`--arranger` songs with bass below MIDI 21-23 on triangle play those notes detuned on every
bytecode ROM. Stays in-range (no silence/hardware violation) — wrong-but-in-range, MEDIUM.
Legacy front-end unaffected.

## Suggested Fix
Clamp the note to `CHANNEL_RANGES[channel]` inside `midi_note_to_nes_pitch`, matching
`PitchProcessor.get_channel_pitch`.

## Related
#158/NH-16, #89/ARR-06, #298/EXP-10.

## Dedup check
Searched fresh `gh issue list --state open` snapshot (6 open issues at filing time) and audit
history — no match found.
