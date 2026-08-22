# ARR-2026-08-21-2: Overlapping same-pitch notes are destroyed by active_notes overwrite — legato/repeated-note passages lose almost all their sound

**GitHub Issue:** #449
**Source Report:** docs/audits/AUDIT_ARRANGER_2026-08-21.md
**Severity:** HIGH · **Domain:** arranger
**Filed:** 2026-08-21

**Severity:** HIGH · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-08-21.md

## Description
`analyze_midi_events` pairs note-ons and note-offs with a single-slot `active_notes[note] = (frame, vel, chan, program)` dict. A note-on for a pitch that is already active **overwrites** the first onset: the first note never becomes a `NoteInfo` at all, and the one note-off that follows closes the *second* onset at the first note's off-frame, truncating it to the overlap window; the second note-off finds nothing active and is discarded. Overlapping same-pitch notes are routine in real MIDI (DAW legato exports, piano pedal, doubled unison voices on one channel), and `tracker/parser_fast.py` faithfully delivers them in chronological order — so the arranger silently deletes both notes except for the few frames where they overlap.

## Location
`arranger/pipeline_integration.py:200-216` (`analyze_midi_events` note-on/off pairing)

## Evidence
Reproduced against this tree (`/tmp/audit/overlap_test.py`). Input: on(C4)@f0, on(C4)@f98, off@f100, off@f200 — two notes intended to cover frames 0–200.
- Arranger: **one `NoteInfo(start=98, end=100)`** — 2 frames of sound out of 200.
- Legacy `NESEmulatorCore.compile_channel_to_frames` on the same events: frames 0–99 covered (both onsets kept; second truncated by its imperfect off-search, but no silent vanishing).

## Impact
Any `--arranger` build of MIDI with legato-overlapped repeated pitches loses those notes with **no warning** (the loss happens before role analysis, so it also skews density/polyphony statistics and thus role detection). A repeated-note melody line with characteristic 1–2-tick overlaps can lose every note but the last. This is silent data loss changing the song on realistic input — HIGH per `_audit-severity.md` ("wrong output under realistic input"; the legacy front-end does not share the defect, so the two modes diverge audibly on the same file).

## Related
#296/ARR-NEW-4 (a different note-merging loss in `_apply_sustain`, fixed; this one is upstream of sustain), #96 (legacy same-frame collapse warns — contrast: this path has no diagnostic).

## Suggested Fix
On a note-on for an already-active pitch, close the active note at the new onset frame (implicit note-off / re-trigger semantics) before re-arming the slot; optionally count and warn like the legacy `_collapse_same_frame_events` does.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
