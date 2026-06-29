# D-11: Drum noise-fallback discarded when a real noise track already exists

Issue: #74 — https://github.com/matiaszanolli/midi2nes/issues/74
Labels: bug, medium, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`assign_tracks_to_nes_channels` calls `map_drums_to_dpcm` and routes the returned `noise_events` only `if noise_events and not nes_tracks['noise']`. When a song already has a tonal/effects track assigned to `noise` (the multi-track heuristic at lines 235-240 can fill it, or a track named "drum"), the drum noise-fallback hits — the very toms/cymbals D-10 pushed to noise — are silently dropped.

## Location
`tracker/track_mapper.py:243-249`

## Evidence
`track_mapper.py:248` `if noise_events and not nes_tracks['noise']:`.

## Impact
On songs with both a noise-channel part and unmapped drums, those drum hits vanish entirely (not even noise). Combined with D-10's mass fallthrough, this can drop most percussion. MEDIUM (workaround: the noise channel is single, a true hardware limit), but the silent discard is the concern.

## Hardware ref
NES has a single Noise channel (`docs/APU_NOISE_REFERENCE.md`), so some contention is unavoidable; the issue is the *silent* drop with no warning.

## Related
D-10.

## Suggested Fix
When dropping drum noise-fallback because `noise` is occupied, emit a warning, or merge by frame priority instead of discarding wholesale.

## Completeness Checks
- [ ] **CHANNEL**: Noise-channel contention handled per single-channel hardware limit
- [ ] **TESTS**: A regression test pins this specific fix (drop is warned, not silent)
