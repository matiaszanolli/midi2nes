# NH-HW-2026-08-22-2: last_dpcm_note's $FF sentinel collides with a legitimate DPCM note value in direct-export

**Filed:** https://github.com/matiaszanolli/midi2nes/issues/482
**Severity:** MEDIUM · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-08-22.md

## Description
#432's fix seeded all four `last_*_note` BSS bytes with `$FF`, reasoning (correctly, for three of the four) that MIDI notes are 0-127 so `$FF` can never collide with a legitimate first note. That reasoning does not hold for `last_dpcm_note`: the DPCM channel's "note" is not a MIDI pitch but `min(255, dense_id + 1)` — a dense, song-local sample index — and direct-export explicitly supports the full `0-255` range (`docs/APU_DMC_REFERENCE.md` §6). A song that references ≥254 distinct DPCM samples has a legitimate `note = 255` (`$FF`) value. If the sample encoded as (or collapsed to) `dense_id = 254` happens to be the **first** DPCM trigger the song plays, `play_dpcm`'s `cmp last_dpcm_note` reads `$FF == $FF` and takes the `@done` branch — the exact bug #432 was written to eliminate, reintroduced for this one channel by the sentinel choice itself.

## Location
`exporter/exporter_ca65.py:813-825` (`reset` proc), `:992-995` (non-standalone `init_music`), vs. `nes/emulator_core.py:235` (`"note": min(255, dense_id + 1)`) and `exporter/exporter_ca65.py:335` (raw `& 0xFF` emission with no re-mapping)

## Evidence
`nes/emulator_core.py:235` confirms `255` is reachable; `exporter/exporter_ca65.py:335` emits it straight into the `dpcm_note` table. `play_dpcm`'s `cmp last_dpcm_note` / `beq @done` guard has no channel-specific carve-out. Tone channels are safe: their note values are inherently ≤ 127 (`$7F`).

## Hardware ref
`docs/APU_DMC_REFERENCE.md` §6 "255-Distinct-Sample Ceiling Per Song"

## Related
#432/NH-HW-2026-08-21-5, #343/DP-DPCM-04, #369/EXP-2026-07-19-1

## Suggested Fix
Seed `last_dpcm_note` with `$00` (the documented rest/no-trigger sentinel) instead of `$FF`, letting the existing `cmp #0` / `beq @done` "rest, nothing to trigger" branch (fixed under #107/NH-14) do double duty — `note=0` is reserved as the rest sentinel on this channel specifically, unlike the tone channels where `$FF` was the correct choice.
