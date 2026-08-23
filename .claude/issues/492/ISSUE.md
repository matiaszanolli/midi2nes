# ARR-2026-08-23-1: Program change on one MIDI track is invisible to another track sharing its channel

- **Issue**: #492

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-08-23.md

## Description
`tracker/parser_fast.py`'s `channel_programs` dict (tracks each MIDI channel's currently-active
GM program, feeding the `program` key stamped onto every note event) is reset to `{}` inside
the per-track loop (`for i, track in enumerate(mid.tracks):`), i.e. scoped **per track**, not
per file. A `program_change` message on one track only updates the active program for note
events emitted from that *same* track.

If a different track carries note events on the same MIDI channel with no local
`program_change` of its own — a real GM/Type-1 convention where a dedicated "conductor" track
issues program changes for channels whose notes live on other tracks — those notes silently
read back `program=0` (Acoustic Grand Piano) via the `channel_programs.get(msg.channel, 0)`
default, instead of the real instrument set on that channel.

This is a distinct root cause from the already-fixed #308/ARR-NEW-5, which was about
*within-track* event ordering (first-event vs. most-common selection), not cross-track channel
scope. `git log -p` on `channel_programs` shows only its original #86 introduction and no
later commit addressing cross-track scope.

## Evidence
`tracker/parser_fast.py:117-125`:
```python
for i, track in enumerate(mid.tracks):
    current_tick = 0
    track_name = f"track_{i}"
    channel_programs = {}   # <-- reset PER TRACK, not once per file
    for msg in track:
        ...
        elif msg.type == 'program_change':
            channel_programs[msg.channel] = msg.program
        elif msg.type in ['note_on', 'note_off']:
            ...
            "program": channel_programs.get(msg.channel, 0),
```

Constructed a 2-track MIDI (Track 0 "Conductor": `program_change(channel=5, program=40)` only,
no notes; Track 1 "Violin": notes on channel 5, no local `program_change`) and ran it
end-to-end:
```
parse_midi_to_frames(...)['events']['Violin'][0]['program'] == 0   # should be 40
analyze_midi_events(...) -> TrackAnalysis(program=0, duty=DUTY_50, style=SUSTAIN, priority=8)
# correct GM program 40 (Violin) would give duty=DUTY_25, style=LEGATO, priority=7
```
No test in `tests/test_parser_fast.py` or `tests/test_arranger*.py` builds a multi-track MIDI
sharing a channel across tracks.

## Impact
Silent, no warning, no crash — playable but musically wrong. The affected track's GM-curated
duty cycle, play style, and `_assign_channels` drop-priority are wrong, and
`_determine_role`'s GM-hint bonus (+3.0) is credited to the wrong role bucket. Blast radius:
MIDI files that centralize program changes on a setup/conductor track rather than repeating
them on every track sharing a channel (more common in DAW/sequencer exports than hand-authored
GM files).

## Suggested Fix
Build `channel_programs` once across the whole file, before the per-track note-emission pass
— carry a single dict across the `for i, track in enumerate(mid.tracks)` loop instead of
resetting it per track — so a program change on any track updates the active program for
every subsequent note on that channel, regardless of which track issues the note.

## Related
Distinct from #308/ARR-NEW-5 (CLOSED — fixed the within-track first-vs-most-common selection;
did not touch `channel_programs`'s scope).

## Completeness Checks
- [ ] **SIBLING**: Confirm no other cross-track/cross-channel state in `parser_fast.py` (e.g. tempo, controller state) makes the same per-track-reset assumption
- [ ] **TESTS**: A regression test covers a program change on one track affecting note events on a different track sharing the same MIDI channel
