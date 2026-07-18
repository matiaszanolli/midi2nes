# #308 — ARR-NEW-5: track GM-program hint ignores program changes after the first note

**Severity:** LOW · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-17.md · **Status:** NEW

## Description
`parser_fast.py` correctly stamps each note event with the channel's *currently active* GM program (`channel_programs.get(msg.channel, 0)`), so a program change mid-track is faithfully carried per event. But the arranger collapses a track to a single representative program by taking the **first** event whose `program` is not `None`:

```python
# arranger/pipeline_integration.py:134-137
track_program = next(
    (e['program'] for e in events if e.get('program') is not None), 0
)
analyzer.set_track_program(track_idx, track_program)
```

Because the parser always sets `program` (defaulting to 0), `is not None` is always true, so `next()` always returns the *first note's* program and never looks further. If a `program_change` arrives **after** the first note-on (or the first note precedes its patch assignment), the track is analyzed as program 0 (Acoustic Grand Piano) even though its real instrument is set moments later. The GM role/timbre/duty hint (`role_scores[gm_mapping.role] += 3.0`, consumed by `VoiceRoleAnalyzer._determine_role` → `get_instrument_mapping(analysis.program)`) is then keyed off the wrong instrument.

## Evidence
Reproduced: a track whose first note carries `program=0` and whose later notes carry `program=38` yields `track program used: 0` from `analyze_midi_events`. The in-code comment ("GM programs are conventionally set once per track before any notes") documents the assumption, but MIDI does not guarantee it, and the parser already preserves the correct per-note program that this selection discards.

## Impact
Role detection for such tracks leans on the wrong GM hint. Because `_determine_role` also weights pitch/density/velocity/polyphony, the final role is often still reasonable and channel allocation stays playable — hence LOW, not MEDIUM. No data loss; ROM boots and plays. Blast radius: only tracks that set/change their patch after their first note (uncommon in well-formed GM files, more likely in DAW exports with a leading pickup note).

## Suggested Fix
Pick the most frequently-occurring (mode) program across the track's note events, or the program active at the track's densest region, rather than the first event's value; or, at minimum, prefer the first *non-zero* program when one exists. Add a test covering a program change that arrives after the first note-on.

## Completeness Checks
- [ ] **CONTRACT**: the fix consumes the per-note `program` the parser already stamps (no new stage-shape change)
- [ ] **SIBLING**: check whether any other role/instrument selection makes the same "first event" assumption
- [ ] **TESTS**: a test asserts a `program_change` after the first note-on picks the right instrument
