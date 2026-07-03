# Issue #73: D-10: ADVANCED_MIDI_DRUM_MAPPING (the default) only defines kick & snare — toms/cymbals dropped

**Severity:** MEDIUM · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-06-29.md

## Description
`map_drums_to_dpcm`/`map_drums` default to `use_advanced=True`, which selects `ADVANCED_MIDI_DRUM_MAPPING`. That table fully defines only notes 36 (kick) and 38 (snare) and ends with a `# Add more mappings...` stub. For every other GM percussion note (40 snare2, 42/44/46 hats, 49/51/57 cymbals, 41–48 toms…), `midi_note in mapping` is False, so the code takes the `else: sample_name = mapping.get(midi_note)` branch → `None` → the event falls to `noise_events`. Additionally, the velocity-split names the advanced map *does* return for 36/38 (`kick_soft`, `kick_hard`, `snare_soft`, `snare_hard`) are **absent** from the shipped index, so even kick/snare miss DPCM and fall to noise.

## Location
- `dpcm_sampler/drum_engine.py:15-33`
- `dpcm_sampler/enhanced_drum_mapper.py:247-312`

## Evidence
`drum_engine.py:32` `# Add more mappings...`; `enhanced_drum_mapper.py:279-284,376-381`; index lookup confirmed — `kick_soft/kick_hard/snare_soft/snare_hard in dpcm_index.json` → all False (only bare names exist).

## Impact
With the default advanced mapping, essentially **all** drums fall through to the noise fallback rather than DPCM — toms/cymbals entirely, and even kick/snare at any velocity because the velocity-split sample names don't exist. Drums still make *a* sound (noise) so this is a degraded-output MEDIUM, not silent-drop, but it is far from the intended DPCM kit.

## Related
D-11 (the noise fallback is then itself at risk of being discarded).

## Suggested Fix
Flesh out `ADVANCED_MIDI_DRUM_MAPPING` across GM 35–81 and ensure the returned sample names exist in the index, or fall back to `DEFAULT_MIDI_DRUM_MAPPING` for unmapped notes before resorting to noise.

## Completeness Checks
- [ ] **TESTS**: A regression test pins this specific fix (GM percussion notes map to DPCM)
- [ ] **DOC**: drum-mapping coverage documented if behavior is intentional

---

# Issue #74: D-11: Drum noise-fallback discarded when a real noise track already exists

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
