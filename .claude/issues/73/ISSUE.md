# D-10: ADVANCED_MIDI_DRUM_MAPPING (the default) only defines kick & snare — toms/cymbals dropped

Issue: #73 — https://github.com/matiaszanolli/midi2nes/issues/73
Labels: bug, medium, dpcm
Filed from: AUDIT_DPCM_2026-06-29.md

---

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
