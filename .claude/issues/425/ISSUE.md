# Issue #425: PIPE-2026-08-21-1: DP-DPCM-12's fix un-gates a channel-blind drum scan — every melodic note becomes a phantom DPCM drum trigger, and song build falsely rejects drumless songs

- **Finding**: PIPE-2026-08-21-1
- **Labels**: critical, pipeline, dpcm, bug
- **Filed**: 2026-08-21 (audit-publish, AUDIT_PIPELINE_2026-08-21.md)
- **URL**: https://github.com/matiaszanolli/midi2nes/issues/425

---

**Severity:** CRITICAL · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-21.md

## Description

`EnhancedDrumMapper.map_drums` (`dpcm_sampler/enhanced_drum_mapper.py:308-330`) iterates *every* track's *every* event and resolves each note through the GM-percussion mapping (`_resolve_dpcm_sample_name(midi_note, ...)`). It has never had a channel-9 (or any drum-track) filter — but that latent flaw was invisible because the loop guarded on `e.get('velocity', 0) == 0`, and real parsed events (`tracker/parser_fast.py`) carry `'volume'`, never `'velocity'`, so the function was dead on real input (that deadness was DP-DPCM-12).

Commit `ffccf51` applied DP-DPCM-12's suggested fix verbatim — read `'volume'` as a fallback (`velocity = e.get('velocity', e.get('volume', 0))`) — which un-deadened the scan *without adding the missing channel filter*. Now every melodic note-on with volume > 0 is treated as a GM percussion note (MIDI note 60 = High Bongo, etc.), resolved against `dpcm_index.json`, and emitted as a real `{'frame', 'sample_id', 'velocity'}` DPCM event alongside the same note's legitimate pulse/triangle mapping. Notes that resolve to no sample fall to the noise-percussion branch instead. Downstream, `NESEmulatorCore.process_all_tracks` dutifully converts these into `{note: dense_id+1, volume: 15}` DPCM frames, the DPCM packer packs the referenced samples, and the engine triggers them at every melodic note-on.

The DPCM audit's DP-DPCM-11 explicitly warned "once DP-DPCM-12 is fixed, this finding should be re-verified" — the false-positive direction it predicted is exactly what shipped. The tests added in `ffccf51` (`tests/test_enhanced_drum_mapper.py`) feed only drum-shaped input, so the melodic-pollution direction is untested.

Call site: `tracker/track_mapper.py:348` (`map_drums_to_dpcm(midi_events, ...)` — deliberately passes the **full** parsed input so channel-9 drums in any track are found).

Affected paths: `map` subcommand, default `run_full_pipeline` (legacy mode), `run_song_build` (legacy mode). `--arranger` mode is unaffected.

## Evidence

All reproduced live at `949f0c6`, `test_midi/simple_loop.mid` (single melodic track, channel 0, zero percussion):

1. `python main.py map` output: `pulse1: 24 events` … and `dpcm: 12 events` (`[{'frame': 30, 'sample_id': 1932, 'velocity': 64}, …]`) — one phantom drum per melodic note-on (notes 60/64/67, `channel: 0` on every source event).
2. Default pipeline `python main.py test_midi/simple_loop.mid out.nes` → `✓ Packed 3 DPCM samples across 1 banks` → `✅ SUCCESS!` — a drumless MIDI ships a ROM with three drum samples packed and triggered over the melody. No warning of any kind.
3. `python main.py song add test_midi/simple_loop.mid --bank b.json --name solo` then `song build b.json out.nes` → `[ERROR] Song 'solo' contains DPCM drum samples…` — the identical command sequence the 2026-08-07 audit ran successfully at `f4c2283` now hard-fails on the same drumless input.

## Impact

Silent song change on effectively **every** legacy-mode build of melodic MIDI (most melody notes sit in the GM-percussion note range 35-81): phantom percussion is layered over the music, and DPCM's DMC channel activity also perturbs the mix. In the other direction, `song build` is functionally unusable for any melodic song in legacy mode (false DPCM rejection). Meets the CRITICAL floor twice over: "silent contract corruption" and "silently changes the song".

## Related

DP-DPCM-12 / DP-DPCM-11 / DP-DPCM-13 (`docs/audits/AUDIT_DPCM_2026-08-07.md`); commit `ffccf51`; #367/DP-DPCM-05 (the partial-miss warning machinery this pollution now routinely exercises with bogus ids).

## Suggested Fix

In `map_drums`'s event loop, skip events whose `e.get('channel')` is not 9 (parsed events always carry `channel`; hand-built test dicts can default to 9). Add the regression test DP-DPCM-11 asked for — a real melodic fixture through `parse → map` asserting `dpcm`/`noise` stay empty — alongside a channel-9 fixture asserting they don't.

## Completeness Checks
- [ ] **CONTRACT**: The map-stage output (`dpcm` list) again contains only genuine channel-9 percussion; downstream consumers (`process_all_tracks`, DPCM packer, `_song_has_dpcm_events`) verified against the corrected shape
- [ ] **SIBLING**: Same pattern checked in related paths (arranger front-end, noise-percussion branch, `song build` DPCM gate)
- [ ] **TESTS**: A regression test pins this specific fix (melodic fixture → empty `dpcm`/`noise`; channel-9 fixture → non-empty)
- [ ] **DOC**: If behavior contradicted a `docs/*.md` (DPCM audit notes / ROADMAP), the doc was corrected
