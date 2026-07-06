# #296 — ARR-NEW-4: _apply_sustain merges fast sequential notes into false chords; arpeggiator drops half

**Severity:** MEDIUM · **Domain:** arranger · **Source:** AUDIT_ARRANGER_2026-07-06.md · **Status:** NEW

## Description
`_apply_sustain` (`arranger/pipeline_integration.py:15-69`), reached unconditionally via `analyze_midi_events` (`:174-175`, `sustain=True` default) → `arrange_for_nes` (`:210`), groups notes whose start frames fall within `chord_tolerance = 2` frames of the group's first note (`:35`) and extends **every** note in that group to the group's `max_end` (`:47-67`). This is intended to repair genuinely staggered chords, but it cannot distinguish a staggered chord from a fast *sequential monophonic* run: if a melody's notes are ≤2 frames apart, each adjacent pair is treated as a 2-note "chord". The earlier note is stretched so it now overlaps the later note, manufacturing polyphony where the source is monophonic. `_allocate_pulse` (`arranger/voice_allocator.py:236-254`) then arpeggiates the false dyad; because the overlap window is only ~2 frames while the arp holds each step for `arp_speed=3` frames, the arp never advances past the root, and the second note of every pair is **never emitted on any channel**. The notes are silently lost — no `plan.notes` entry, no `verbose` diagnostic.

## Evidence
Reproduced. Input melody `[60,62,64,65,67,69,71,72]`, each note 2 frames long, played strictly sequentially (note *i* at frame *i*·2), single track, channel 0:
```
spacing=2  sustain=ON  (default): pulse1 set = [60, 64, 67, 71]   # 62,65,69,72 DROPPED
spacing=2  sustain=OFF          : pulse1 set = [60,62,64,65,67,69,71,72]  # all present
spacing=3+ sustain=ON           : all 8 notes present
```
`sustain` is not exposed by `arrange_for_nes` or the CLI, so the user has no way to turn it off. No arranger test exercises `_apply_sustain`.

## Impact
On the live `python main.py --arranger song.mid out.nes` path, any pulse-routed melodic passage with notes ≤2 frames (≈33 ms) apart — fast runs, trills, grace/ornament notes, 32nd-notes at high tempo — silently loses about every other note. The ROM still boots and plays, and most moderate-tempo material is unaffected (trigger is narrow: >2-frame spacing is clean), so MEDIUM — but it is genuine, unwarned MIDI-note data loss with no user workaround, escalating for fast-passage-heavy material.

## Suggested Fix
Only bridge/extend notes that are actually simultaneous (true chords), not ones that merely start within 2 frames of each other — e.g. require the earlier note's original `end_frame` to be at/after the next note's `start_frame` before extending, so a sequential run is left untouched. Alternatively expose `sustain` as an `arrange_for_nes`/CLI parameter. Add a test asserting a fast sequential monophonic run round-trips every note.

## Completeness Checks
- [ ] **CONTRACT**: the `frames` handoff to Step-4 still carries every source note (no silent drop)
- [ ] **TESTS**: a test asserts a fast sequential monophonic run (≤2-frame spacing) round-trips every note through `arrange_for_nes`
- [ ] **SIBLING**: verify the legacy front-end (which does not run `_apply_sustain`) is unaffected and behaviour stays consistent
