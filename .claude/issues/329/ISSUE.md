# ARR-NEW-5: Multi-channel/Type-0 MIDI tracks mis-arranged
**Filed as:** #329

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-18.md

## Description
`parser_fast` groups events by MIDI *track* only (`track_events[track_name]`), never by channel. A Type-0 MIDI (one track carrying all 16 channels, including channel-9 drums) — and any multi-channel Type-1 track — therefore reaches the arranger as a single merged voice. `analyze_midi_events` then (a) samples the drum flag from only the *first* event that has a channel: `track_channel = next((e['channel'] for e in events if …), None)` then `is_drum_track = track_channel == 9` (`arranger/pipeline_integration.py:120-124`), so unless that first event happens to be channel 9 the whole track is `is_drum_track=False`; and (b) derives one GM program via `Counter(programs).most_common(1)` across *all* mixed channels (`:138`). Result: channel-9 percussion is analyzed as pitched notes and routed to pulse/triangle — it never reaches NOISE/DPCM — while the melodic program hint is skewed by the drum channel's program 0.

## Evidence
Empirically reproduced. A single track `{'track_0': [...]}` with melody on channel 0 (program 80) and kick/hat on channel 9 yields `role=MELODY, is_drum=False, program=0, noise_tracks=[], dpcm_tracks=[]` — all percussion routed to pulse1 as pitched notes.

Location: `arranger/pipeline_integration.py:120-139`; root cause `tracker/parser_fast.py:109-153`.

## Impact
Whole-song musical corruption for a very common export class (Type-0 MIDI): drums lost from the percussion channels, melody timbre mis-hinted. Playable (no crash), so not CRITICAL, but musically wrong across the entire song — the `--arranger` path silently degrades. The legacy path shares the same track granularity, but the arranger's drum detection specifically only inspects the first channel, giving a false impression of channel-9 support.

## Related
#85/#86 (added the per-event channel/program the fix should split on); the name-heuristic drum fallback (`pipeline_integration.py:126-127`) is effectively unreachable via `parser_fast` since every real event carries a channel.

## Suggested Fix
Split events by `(track, channel)` before role analysis (either in `parser_fast` or at the top of `analyze_midi_events`), so channel-9 events become their own drum track and each pitched channel gets its own GM program and role.

## Completeness Checks
- [ ] **CONTRACT**: if the split changes the frames dict's track granularity, downstream role/allocation consumers updated in lockstep
- [ ] **SIBLING**: legacy `track_mapper` path checked for the same Type-0 merge behavior
- [ ] **TESTS**: a regression test feeds a Type-0 MIDI (melody + channel-9 drums in one track) and asserts drums reach NOISE/DPCM