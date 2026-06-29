# TEMPO-01: SMPTE / negative ticks_per_beat produces negative frame indices

Issue: #93

**Severity:** HIGH · **Domain:** tempo · **Source:** AUDIT_TEMPO_2026-06-29.md

## Description
`parse_midi_to_frames` passes `ticks_per_beat=mid.ticks_per_beat` to `EnhancedTempoMap` with no validation (`tracker/parser_fast.py:24-29`). For SMPTE-division MIDI files (division word with bit 15 set), **mido returns `ticks_per_beat` as a negative integer**. `calculate_time_ms` (`tracker/tempo_map.py:129`) then computes `us_per_tick = tempo / ticks_per_beat < 0`, so elapsed time is negative and `round(time_ms / FRAME_MS)` in `get_frame_for_tick` (`:144-147`) yields **negative frame indices**. Nothing downstream guards against a negative `frame`, so events are written at negative JSON keys / negative `range()` bounds and silently corrupt the song.

## Location
`tracker/parser_fast.py:24-29` (and `:14` where `mid = mido.MidiFile`); consumed in `tracker/tempo_map.py:129` and `:144-147`.

## Evidence
Constructed a raw SMPTE header (`division = -3200`); `mido.MidiFile` parsed it with `ticks_per_beat == -3200`. Then:
```
EnhancedTempoMap(initial_tempo=500000, ticks_per_beat=-3200, optimization_strategy=None)
tm.calculate_time_ms(0, 6400)  -> -1000.0
tm.get_frame_for_tick(6400)    -> -60
```

## Impact
Any SMPTE-timed MIDI (legal, exported by some DAWs/notation tools) compiles to garbage: notes at negative frames, wrong total length, likely silent or scrambled playback. Blast radius is the whole song, at the parse stage, for every channel. No error surfaces.

## Related
TEMPO-03 (`ticks_per_beat == 0` from same unvalidated boundary); SAFE-07 in `docs/audits/AUDIT_SAFETY_2026-06-29.md` (per-event drop, different line).

## Suggested Fix
In `parse_midi_to_frames`, after opening the file, check `mid.ticks_per_beat > 0`; if mido reports a non-metrical (SMPTE) division, either raise a clear error or convert SMPTE frame/sub-frame timing to a positive PPQ before constructing the tempo map. Add an assertion in `TempoMap.__init__` that `ticks_per_beat >= 1`.

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **SIBLING**: Same unvalidated `ticks_per_beat` boundary checked in `parser.py` / other tempo-map constructors
- [ ] **TESTS**: A regression test pins SMPTE/negative-division rejection or conversion
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
