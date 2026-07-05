**Severity:** HIGH · **Domain:** dpcm · **Source:** AUDIT_DPCM_2026-07-05.md

## Description
Commit `b49a649` (#200, #201) fixed D-14 by (a) adding named drum samples to `dpcm_index.json`, and (b) renumbering each song's *referenced* catalog ids to a compact song-local `0..N-1` "dense" range in `NESEmulatorCore.process_all_tracks` before the single-byte `note` encoding (`note = min(255, dense_id + 1)`), emitting a `dpcm_sample_map` (dense→catalog) side table so the export/pack stage can recover the real `.dmc` files. This is the correct fix: a real song references far fewer than 255 distinct drums, so the byte ceiling is never hit and no aliasing occurs.

But the **same commit** also added a `MAX_SAFE_SAMPLE_ID = 254` guard in `EnhancedDrumMapper` that runs in the earlier `map` stage and drops any hit whose *raw catalog* id exceeds 254 to the noise fallback (lines 298-304, 389-392, 471-476), incrementing `_oversized_sample_id_count`. The guard's premise — "this id would collide with another sample once clamped to a single byte downstream" — is exactly the collision the dense-remap already prevents. Because the guard fires in `map_drums` (map stage) *before* `process_all_tracks` (frames stage), it removes the high-id hits before the dense-remap can renumber them, so the remap never sees them.

The shipped `dpcm_index.json` now has 1941 samples, and **all 26 resolvable drum-role names sit at ids ≥ 1083** (kick=1318, snare=1620, hihat_closed=1926, tom_mid=1924, crash=1929, ride=1526, cowbell=1119, clap=1096, …). Every one exceeds 254, so every resolvable drum hit is routed to noise. `map_drums` emits **zero** DPCM events on the shipped catalog, and `nes/emulator_core.py`'s dense-remap is dead code for it.

## Location
- `dpcm_sampler/enhanced_drum_mapper.py:202` (`MAX_SAFE_SAMPLE_ID = 254`), `:298-304` (non-pattern hit → noise when id > 254), `:389-392` (pattern path), `:471-476` (layered path)
- vs. the dense-remap it pre-empts at `nes/emulator_core.py:213-235`
- shipped `dpcm_index.json` (named drums at ids 1083–1940)

Verified against current code: guard present at `enhanced_drum_mapper.py:202,298,389,471`; dense-remap present at `nes/emulator_core.py:189-234` (`note = min(255, dense_id + 1)`, `dpcm_sample_map` emitted).

## Evidence
```
$ python3 -c "
from dpcm_sampler.enhanced_drum_mapper import EnhancedDrumMapper
m = EnhancedDrumMapper(dpcm_index_path='dpcm_index.json')
events = {'drums':[{'frame':0,'note':36,'velocity':100},   # kick
                   {'frame':10,'note':38,'velocity':100},   # snare
                   {'frame':20,'note':42,'velocity':100}]}  # closed hi-hat
dpcm, noise = m.map_drums(events)
print('DPCM:', dpcm); print('NOISE:', noise)"
Warning: 3 drum hit(s) resolved to a DPCM sample id > 254 (out of 1941 in
    dpcm_index.json) — routed to noise instead of risking aliasing ...
DPCM: []
NOISE: [{'frame': 0, 'note': 36, ...}, {'frame': 10, ...}, ...]
```
All three named drums resolve to real sample names (`kick`, `snare`, `hihat_closed`), but their catalog ids (1318, 1620, 1926) all exceed 254, so all three drop to noise. 0 of the 26 resolvable role names have id ≤ 254.

The dense-remap the guard pre-empts is proven correct in isolation (`tests/test_audio_fixes.py:160,165`: `sample_id=200 → dpcm_sample_map {'0':200}`, `sample_id=9999 → {'0':9999}`) — but no test drives it end-to-end **through** `map_drums`, so the guard swallowing every hit was never caught.

## Impact
On the shipped `dpcm_index.json`, every song built through the default pipeline (or `export`) loses **all** of its DPCM percussion — every drum hit plays as noise instead of the sampled drum the mapping resolved. A stdout warning is printed (so not fully silent), but the drums are gone from DPCM and the recently-added named samples + the dense-remap infrastructure are both inert. Blast radius: every drummed song on the shipped catalog. Kept below CRITICAL only because playback still produces audible (noise) percussion rather than a broken ROM.

## Related
#200/D-14 (the fix this defeats), #201 (the role-name samples added at ids >254 that this guard then discards), prior D-15 (asset gap — now data-present but guard-blocked), D-18. Introduced by the same fix commit `b49a649`.

## Suggested Fix
Remove the `MAX_SAFE_SAMPLE_ID` guard from `EnhancedDrumMapper` (lines 298-304, 389-392, 471-476) — the dense-remap in `process_all_tracks` already guarantees no catalog id reaches the byte encoding unremapped, and `map_drums` output always flows through `process_all_tracks` before export. If a belt-and-suspenders check is still wanted, move it to the *dense* id after remapping (assert `dense_id + 1 <= 255`, i.e. a song references ≤ 254 distinct drums) rather than the raw catalog id. Add an end-to-end test that drives `map_drums` → `process_all_tracks` with the real shipped index and asserts a kick+snare song produces two distinct non-noise DPCM events.

## Completeness Checks
- [ ] **CONTRACT**: The `map` stage output (drum→DPCM vs noise routing) stays consistent with what `process_all_tracks` (frames stage) expects to dense-remap
- [ ] **SIBLING**: All three guard sites (non-pattern, pattern, layered paths) fixed together
- [ ] **TESTS**: An end-to-end test drives `map_drums` → `process_all_tracks` with the shipped `dpcm_index.json` and asserts non-noise DPCM events
- [ ] **DOC**: If DPCM behavior is documented anywhere, it reflects that shipped-catalog drums now produce DPCM events
