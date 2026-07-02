# NH-20: Default front-end discards MIDI note durations — every note is capped at 4 frames (~67 ms)

**Severity:** HIGH · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-07-01.md

## Description
`tracker/parser_fast.py:100-116` faithfully emits `note_off` events (velocity 0) at their
correct frames, so durations survive parsing. The legacy mapper then drops them
(`track_mapper.py:159-161`), and `compile_channel_to_frames` skips any velocity-0 event and
substitutes a fixed 4-frame sustain for every note. At 120 BPM a quarter note is 30 frames:
it sounds for 4 and is silent for 26. A held whole note (2s) becomes a 67ms blip. The
engine-side machinery for real durations exists and is unused: the bytecode length commands
support arbitrary durations via chaining (`docs/AUDIO_BYTECODE_SPEC.md` §3), and the
documented note-off strategy assumes the sequencer counts actual note lengths. The
`--arranger` front-end, by contrast, pairs note-on/note-off into `NoteInfo` with real
`start_frame`/`end_frame` and emits frames for the full duration — confirming durations are
available and representable end-to-end.

## Location
`nes/emulator_core.py:63-76` (`velocity == 0: continue` — "We simulate note-off via time";
`end_frame = start_frame + sustain_frames` with `sustain_frames=4`; lookahead only truncates
at the next note-on), `nes/emulator_core.py:112-122` (`process_all_tracks` never passes a
different `sustain_frames`); `tracker/track_mapper.py:11,159-161` (note-offs dropped before
the core: "ignoring note-offs").

## Evidence
The three code sites above; no caller overrides `sustain_frames`; no warning is printed.
This silently changes every song on the default path. The `--arranger` front-end pairs
note-on/note-off into `NoteInfo` with real durations
(`arranger/pipeline_integration.py:118-160`, `arranger/voice_allocator.py:327-370`),
confirming the fix is representable end-to-end.

## Impact
All melodic/sustained material on the default `python main.py in.mid out.nes` path plays
staccato: pads, held basses, legato melodies are truncated to <= 67ms. Blast radius: every
ROM built without `--arranger`, both export paths (the frames are already truncated before
export).

## Related
NH-17 (the one place a note *does* sustain — forever), NH-19 (the drum variant of the same duration gap), #3.

## Hardware ref
`docs/APU_LENGTH_COUNTER_REFERENCE.md` §5 ("To achieve precise, tracker-like note
durations, our 60Hz Macro Sequencer will bypass the hardware length counter … the 6502
sequencer will count frames in software based on our custom Length Commands (`$60-$7F`)");
`docs/AUDIO_BYTECODE_SPEC.md` §3 Length Commands. The NES has no 4-frame limit — the
truncation is purely the Python front-end.

## Suggested Fix
In the legacy path, compute each note's end frame from its matching note-off (fall back to
`sustain_frames` only for missing note-offs, as the arranger does), or route the default
pipeline through the arranger's duration pairing. Keep the next-note truncation.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
