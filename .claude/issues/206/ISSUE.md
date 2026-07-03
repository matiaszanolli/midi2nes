# ARR-11: Drum-name heuristic overrides definitive non-drum channel info

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/206
**Source finding:** NEW-2 in `docs/audits/AUDIT_ARRANGER_2026-07-03.md`
**Filed:** 2026-07-03

**Severity:** MEDIUM · **Domain:** arranger

## Description
`analyze_midi_events` (`arranger/pipeline_integration.py:110-116`) computes `track_channel` from
the first event that carries channel info, then marks a track as drums if
`track_channel == 9 or 'drum' in name.lower() or name in ('9', 9)`. The channel check and the
name heuristic are combined with `or`, not applied as "channel info wins when present, name is
only a fallback." So a track that carries definitive, non-percussion channel info (e.g. channel
0) but whose name happens to contain "drum" is still rerouted through `_analyze_drum_track`,
discarding its actual pitch content.

## Evidence
```python
events = {'Drum Fill Reference': [
    {'frame':0,'note':60,'volume':100,'type':'note_on','channel':0},
    {'frame':30,'note':60,'volume':0,'type':'note_off','channel':0},
    {'frame':40,'note':64,'volume':100,'type':'note_on','channel':0},
    {'frame':70,'note':64,'volume':0,'type':'note_off','channel':0},
]}
plan, _, _ = analyze_midi_events(events)
# plan.tracks[0].is_drum_track == True, role == PERCUSSION
# plan.noise_tracks == [0]; plan.pulse1_tracks == []; plan.triangle_tracks == []
```
`tests/test_arranger_drum_detection.py` does not cover this "channel present and non-drum, name
matches" conflict case.

## Impact
A pitched track is silently reduced to unpitched noise/DPCM hits whenever its name happens to
match the heuristic, even though the MIDI's own channel metadata says it isn't percussion.

## Related
#85 (channel-9 detection this heuristic complements), #205 (NEW-1, companion finding).

## Suggested Fix
When `track_channel` is known (not `None`), let it be authoritative
(`is_drum = track_channel == 9`); only fall back to the name heuristic when
`track_channel is None`.

## Dedup check
Searched open issues in `/tmp/audit/issues_arranger.json` — no match found. Filed as NEW.
