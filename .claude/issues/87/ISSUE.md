# ARR-04: Arranger DPCM/noise routing is hardcoded and diverges from GM_DRUM_MAP and dpcm_index.json

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-06-29.md

## Description
`VoiceAllocator._allocate_dpcm` and `_allocate_noise` re-derive drum routing with hardcoded note lists and magic sample indices instead of consulting `get_drum_mapping`/`GM_DRUM_MAP` (which are imported into `role_analyzer.py`/`pipeline_integration.py` but never used at allocation time). Two divergences: (a) note 40 is "Electric Snare → NOISE (noise_period=4)" in `GM_DRUM_MAP` but is treated as a DPCM snare in `_allocate_dpcm` (`note.pitch in [38, 40] → return 1`); (b) the DPCM sample indices `0` (kick), `1` (snare), `2` (generic) do not match `dpcm_index.json`, where `id 0 = "Hit 1"`, `id 1 = "Kick"`, `id 2 = "Snare"` — so the arranger "kick" would trigger "Hit 1", its "snare" would trigger "Kick", and generic would trigger "Snare". `_allocate_noise` also discards the curated `GM_DRUM_MAP.noise_period` values, recomputing `(pitch-36)//6` clamped 0–15.

## Location
- `arranger/voice_allocator.py:256-280`
- contrast `arranger/gm_instruments.py:1202-1268`; data `dpcm_index.json`

## Evidence
```python
# voice_allocator.py:273-280
if note.pitch in [35, 36]: return 0   # "kick" -> dpcm_index id 0 == "Hit 1"
elif note.pitch in [38, 40]: return 1 # "snare" -> id 1 == "Kick"
return 2                              # generic -> id 2 == "Snare"
# :258  noise_period = max(0, min(15, (note.pitch - 36) // 6))  (ignores GM_DRUM_MAP)
```

## Impact
Wrong DPCM samples fire and noise periods are uncurated whenever drums reach the allocator — but this is currently unreachable due to ARR-01 (DPCM silenced) and ARR-02 (drums undetected), so it is latent. MEDIUM (duplicate/divergent routing that would mis-play once the upstream bugs are fixed).

## Related
ARR-01, ARR-02, DPCM audit (#64–#76).

## Suggested Fix
Drive `_allocate_dpcm`/`_allocate_noise` from `get_drum_mapping(pitch)` (use its `noise_period`, and resolve sample ids via `dpcm_index.json` by name, not literals).

## Completeness Checks
- [ ] **CHANNEL**: Triangle has no volume/duty; per-channel pitch table is the correct one
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
