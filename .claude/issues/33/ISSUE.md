# F-14: SongBank.add_song_from_midi uses the old full parser, not parser_fast — third parser drift

**Severity:** LOW · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-06-28.md
**Issue:** #33

## Description
Song-bank ingestion parses MIDI with tracker.parser.parse_midi_to_frames (older full parser, song_bank.py:7,61), while every pipeline path uses parser_fast (main.py:35,264). The two populate metadata differently (old parser fills per-track metadata parser.py:92-104; fast parser returns {} parser_fast.py:84) and may differ in note/event handling. A banked song is parsed by a different code path than the one that would render it.

## Evidence
song_bank.py:7 import; parser.py:102-104 vs parser_fast.py:83-85 differing return shapes.

## Impact
If the song-bank path is ever wired to ROM output (F-13), notes/timing could differ from the main pipeline. Today only affects bank metadata. LOW (latent).

## Related
F-13

## Suggested Fix
Point song_bank.py at parser_fast (or share a single front-end) so bank ingestion matches pipeline note handling.

**Location:** `nes/song_bank.py:7,61`; pipeline uses `tracker.parser_fast` (`main.py:35,264`)
