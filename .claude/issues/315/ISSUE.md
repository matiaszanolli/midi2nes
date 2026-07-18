# DP-07: DEFAULT_MIDI_DRUM_MAPPING role names don't match dpcm_index.json filenames for 14 of 40 GM percussion roles

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-18.md
**Filed as:** #315

## Description
14 of 40 role names produced by DEFAULT_MIDI_DRUM_MAPPING have no matching key in dpcm_index.json, so those GM percussion notes fall back to the noise channel. 6 of the 14 have real samples under different filenames (tamborin, whistle1/2, guiro1/2, mario_2_woodblock, cuica1/2, stickrim/sticks).

## Location
`dpcm_sampler/drum_engine.py:8-56` (DEFAULT_MIDI_DRUM_MAPPING); dpcm_index.json

## Suggested Fix
Add filename aliases (tambourine→tamborin, whistle_short/long→whistle1/2, guiro_short/long→guiro1/2, cuica_mute/open→cuica1/2, woodblock_hi/lo→mario_2_woodblock, side_stick→stickrim); accept splash/vibraslap/triangle mute-open as true asset gaps.

## Related
D-15 (AUDIT_DPCM_2026-07-03.md, never filed), #73/D-10
