# NH-27: NH-20's duration fix does not cover the harmony (pulse2) channel on multi-track MIDI

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/197
**Severity:** HIGH
**Domain:** nes-hardware
**Source:** docs/audits/AUDIT_NES-HARDWARE_2026-07-03.md
**Labels:** high, nes-hardware, bug

## Description
`assign_tracks_to_nes_channels`'s "multiple tracks" branch (taken for any standard multi-track MIDI file) assigns melody and bass by direct list passthrough, retaining their `note_off` events and correctly benefiting from the NH-20 fix in `compile_channel_to_frames`. The harmony track, however, is routed through `apply_arpeggio_fallback`, which calls `group_notes_by_frame` ("ignoring note-offs") and emits brand-new synthetic events with no corresponding note-off events at all. `compile_channel_to_frames`'s NH-20 note-off search can never find a match, so `end_frame` always falls back to the default 4-frame sustain (~67ms) — the pre-#160 behavior NH-20 was filed against, now scoped to pulse2 only.

## Location
- `tracker/track_mapper.py:225-228` (`nes_tracks['pulse2'] = apply_arpeggio_fallback(midi_events[ch], style="default")`)
- `tracker/track_mapper.py:10-17` (`group_notes_by_frame`)
- `tracker/track_mapper.py:21-51` (`apply_arpeggio_fallback`)
- Consumed by `nes/emulator_core.py:76-94`'s note-off search

## Impact
On any multi-track MIDI file processed by the default (non-`--arranger`) pipeline, the harmony/pulse2 channel plays only ~67ms blips regardless of the source chord's actual duration. Pulse1 (melody) and triangle (bass) are unaffected.

## Related
#160/NH-20 (this is the residual gap), NH-26 / #195 (another gap in the same producer surface).

## Suggested Fix
Either have `apply_arpeggio_fallback` emit matching note-off events at the original chord's end frame for each arpeggiated note, or route harmony through the same real-duration passthrough used for melody/bass and reserve arpeggiation for cases where the destination channel is already occupied.

## Dedup
Checked against `/tmp/audit/issues_nes-hardware.json` (47 open issues) via `gh search issues` for "pulse2 duration", "apply_arpeggio_fallback" — no open match.
