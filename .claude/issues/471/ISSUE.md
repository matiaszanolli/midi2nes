# 471: REG-30: Drum-mapper tests are direction-blind — melodic input is never asserted to produce zero drum output

URL: https://github.com/matiaszanolli/midi2nes/issues/471
Labels: bug, high, regression

**Severity:** HIGH · **Domain:** regression · **Source:** AUDIT_REGRESSION_2026-08-21.md

## Description
`ffccf51` fixed DP-DPCM-12 (the `velocity`-only guard that made `map_drums` dead on real `'volume'`-keyed input) and added exactly two tests — both feeding drum-shaped fixtures (notes 36/38 under key `9`). Neither the new tests nor any of the other 29 tests in the file feed a *melodic* event stream and assert it produces **no** drum output; nor does any integration test run a melodic MIDI through `parse → assign_tracks_to_nes_channels` asserting `dpcm`/`noise` stay empty.

Because `map_drums` scans every track's every event with no `channel == 9` filter, un-deadening it turned every melodic note-on into a phantom GM-percussion lookup — and the suite stayed green. Confirmed on current tree: `dpcm_sampler/enhanced_drum_mapper.py`'s `map_drums` loop (`for ch, events in midi_events.items(): ... for e in events:`) has no channel filter anywhere.

The positive test itself is also weak: it asserts only `len(dpcm_events) + len(noise_events) == 2`, so it cannot distinguish DPCM from noise routing nor verify sample identity.

## Evidence
- `grep -i melodic tests/test_enhanced_drum_mapper.py` → no matches (re-verified).
- The two `ffccf51` tests assert combined counts only (`tests/test_enhanced_drum_mapper.py:104,124`).
- `dpcm_sampler/enhanced_drum_mapper.py`'s `map_drums` (~line 294-360) loops over `midi_events.items()` with no channel filter — confirmed by direct read.
- Underlying live defect: **PIPE-2026-08-21-1** (issue #425, CRITICAL) — repro via `test_midi/simple_loop.mid` (channel 0, zero percussion) → `map` emits `dpcm: 12 events`.

## Impact
A CRITICAL silent-song-corruption defect on effectively every legacy-mode melodic build was undetectable by the suite; the same blindness will hide any future regression in the drum/melody routing boundary.

## Related
#425 (PIPE-2026-08-21-1), `ffccf51`, docs/audits/AUDIT_DPCM_2026-08-07.md (DP-DPCM-11/12)

## Suggested Fix
Two tests. (1) Unit: in `tests/test_enhanced_drum_mapper.py`, feed `map_drums` a melodic stream (`{0: [{'note': 60, 'volume': 100, 'frame': 0, 'channel': 0}, …]}`, notes 60/64/67) and assert `([], [])` — red today, green once the channel-9 filter lands. (2) Integration: parse `test_midi/simple_loop.mid` through `assign_tracks_to_nes_channels` and assert `nes_tracks['dpcm'] == []` and `nes_tracks['noise'] == []`. Also strengthen `test_map_drums_reads_volume_key_not_just_velocity` to assert *which* list each event landed in and its resolved `sample_id`.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
