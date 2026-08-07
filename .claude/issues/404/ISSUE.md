# ARR-NEW-5-LEGACY: legacy track_mapper also mis-splits a Type-0/multi-channel MIDI track — channel-9 drums duplicated onto triangle/pulse

**Severity:** LOW · **Domain:** arranger · **Source:** SIBLING check while fixing #329 (ARR-NEW-5)
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/404

## Description
`assign_tracks_to_nes_channels`'s single-track branch (`len(midi_events) == 1`, the Type-0
case) calls `split_polyphonic_track`, which buckets every event into pulse1/pulse2/triangle
purely by raw MIDI pitch number (`note >= 60` -> pulse1, `>= 48` -> pulse2, else -> triangle)
-- no channel awareness at all, so channel-9 percussion (kick=36, hi-hat=42, ...) lands in
`triangle` right alongside genuine bass notes just because their pitch numbers are < 48.

Separately, the function also runs an unconditional `map_drums_to_dpcm` fallback over the
whole `midi_events` dict regardless of the branch taken above; empirically the noise-only
hi-hat was dropped from `noise` entirely in one repro.

## Location
- `tracker/track_mapper.py` (`assign_tracks_to_nes_channels`, `split_polyphonic_track`)

## Impact
Legacy (non-`--arranger`) Type-0 MIDI with channel-9 drums: every channel-9 hit also plays
as a wrong extra low-pitched note on triangle/pulse, and noise-only percussion can be
silently dropped rather than reaching NOISE.

## Suggested Fix
Exclude channel-9 events from `split_polyphonic_track`'s input (or split by channel first,
mirroring #329's `_split_events_by_channel`), so channel-9 content never reaches the
pitch-based pulse/triangle split; confirm the noise-fallback path doesn't silently drop
noise-only percussion.
