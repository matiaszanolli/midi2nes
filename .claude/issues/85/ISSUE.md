# ARR-02: Drum tracks are never detected on the live path — noise/DPCM channels stay empty for ordinary GM MIDI

**Severity:** HIGH · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-06-29.md

## Description
`analyze_midi_events` flags a drum track only when the track *name* contains `"drum"` or equals `"9"`/`9`. But `parser_fast.parse_midi_to_frames` names tracks `track_{i}` (or the literal `track_name` meta) and **discards the MIDI channel** (`msg.channel` is never read). GM percussion lives on MIDI channel 10 (index 9), which the arranger drum test was clearly meant to catch (`track_name == "9"`), but no track is ever keyed by channel number. So unless a MIDI happens to name a track with the substring "drum", drums are scored as ordinary pitched voices and routed to pulse/triangle; `plan.noise_tracks` / `plan.dpcm_tracks` stay empty.

## Location
- `arranger/pipeline_integration.py:107-108`
- `tracker/parser_fast.py:51-76`

## Evidence
```python
# pipeline_integration.py:108
if "drum" in str(track_name).lower() or track_name == "9" or track_name == 9:
    analyzer.mark_drum_track(track_idx)
# parser_fast.py: track_name = f"track_{i}"   (msg.channel never inspected)
```

## Impact
For typical GM MIDI, percussion is mis-routed onto tone channels (stealing a pulse/triangle from real melodic/bass content) and the noise+DPCM channels produce nothing. Musically wrong arrangement on every drummed song; combined with ARR-01 the drum path is dead end-to-end. Elevated to HIGH because it produces wrong output on common input (drummed GM MIDI is the norm).

## Related
ARR-01 (the noise/DPCM contract that would matter once detection works), #44 (no test exercises this).

## Suggested Fix
Pass MIDI channel through `parser_fast` (retain `msg.channel`) and flag channel-9 tracks as drums in `analyze_midi_events`; keep the name heuristic as a fallback.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
