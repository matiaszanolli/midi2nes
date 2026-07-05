ARR-NEW-1: Drum tracks lose all noise percussion — DPCM assignment overwrites NOISE in set_arrangement

**Severity:** CRITICAL · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-05.md

## Description
`_assign_channels` puts a drum track into **both** `plan.noise_tracks` and `plan.dpcm_tracks` (it claims noise, and dpcm if free). `set_arrangement` then maps tracks to channels through a single `Dict[int, NESChannel]` keyed by `track_id`, assigning NOISE first and DPCM second — so the DPCM write **overwrites** the NOISE write for that same track id. The result is `track_assignments == {drum_track: DPCM}`. In `allocate_frame`, that track's notes are collected only under `NESChannel.DPCM`; `_allocate_noise` always receives an empty list and returns `None`, so the noise channel emits **zero** frames. Every drum whose `GM_DRUM_MAP` routing is NOISE (all hi-hats, cymbals, toms mapped to noise, electric snare, etc.) is silently discarded. Only the kick/snare that `_allocate_dpcm` accepts (notes 35/36/38) survive.

## Location
`arranger/voice_allocator.py:89-101` (`set_arrangement`), enabled by `arranger/role_analyzer.py:316-324` (drum track added to both channel lists).

## Evidence
Reproduced with a 6-hit drum kit (kick 36, closed-hat 42, snare 38, open-hat 46, elec-snare 40, pedal-hat 44) via `arrange_for_nes`:
```
noise frames: 0    dpcm frames: 8
track_assignments: {0: 'dpcm'}      # NOISE overwritten by DPCM
noise_tracks [0]   dpcm_tracks [0]  # same track in both lists
```
Overwrite site (`voice_allocator.py:98-101`):
```python
for track_id in plan.noise_tracks:
    self.track_assignments[track_id] = NESChannel.NOISE   # written
for track_id in plan.dpcm_tracks:
    self.track_assignments[track_id] = NESChannel.DPCM    # overwrites same key
```
`tests/test_voice_allocator.py` misses this because every test calls `_allocate_noise` / `_allocate_dpcm` **directly** with hand-built note lists and never routes through `set_arrangement`.

## Impact
On the live `python main.py --arranger song.mid out.nes` path, any song with a drum track loses its entire noise percussion layer (hi-hats drive the groove) with no warning, no `plan.notes` entry, and no `verbose` diagnostic. Only kick/snare DPCM hits remain. This is the CRITICAL "a MIDI event class dropped on the floor with no warning, changing the song" case in `_audit-severity.md`.

## Suggested Fix
A drum track needs to occupy noise *and* DPCM simultaneously. `track_assignments` cannot be a 1:1 `Dict[int, NESChannel]`. Either (a) give drum tracks a dedicated routing that dispatches notes to *both* `_allocate_noise` and `_allocate_dpcm` (per-note by `get_drum_mapping(pitch).channel`), or (b) key channel assignment by a `(track_id, channel)` pair / `Dict[int, List[NESChannel]]` so the DPCM entry does not clobber NOISE. Add an end-to-end `set_arrangement`→`allocate_frame` test with a mixed noise+DPCM kit.

## Related
#205 (ARR-10, same "drum claims two channels" design); ARR-NEW-3 (period-0 floor, masked by this bug).

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other channels, other allocators)
- [ ] **TESTS**: An end-to-end `set_arrangement`→`allocate_frame` regression test with a mixed noise+DPCM kit pins this fix
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
