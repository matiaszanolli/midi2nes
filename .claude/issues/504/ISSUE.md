# PERF-B-01: song build deserializes every song's unused stored segments payload from the bank JSON

**Severity:** MEDIUM · **Domain:** performance
**Source:** AUDIT_PERFORMANCE_2026-08-23.md (carried forward from AUDIT_PERFORMANCE_2026-08-07 / 2026-08-21, filed for the first time here)
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/504

## Description
`song add` stores each song's full parsed-event list under `songs[name]['segments']` in
the bank JSON (`add_song`, `nes/song_bank.py:133-167`). `SongBank.import_bank`
(`nes/song_bank.py:231-290`) JSON-parses and materializes all of it unconditionally —
`data = json.loads(path.read_text())` (line 244) followed by `self.songs = songs`
(line 290). `run_song_build`'s per-song loop (`main.py:1032-1059`) never reads
`segments`; it deliberately re-parses each song from its recorded `midi_path` because
the stored events predate NES channel mapping. Every `song build` therefore pays a
JSON-parse + object-materialization cost proportional to the sum of all songs' raw
event counts, for data that is immediately unreachable.

## Evidence
- `grep -n "segments" main.py` inside the `run_song_build` region
  (`main.py:999-1117`) returns nothing; the only per-song fields read are
  `song_data.get('midi_path')` (`main.py:1035`) and
  `song_data['metadata'].get('order', 0)` (`main.py:1026`).
- `nes/song_bank.py:125-131` (`_process_segments`) shows `segments` is built from the
  full `parse_midi_to_frames` event list.
- `nes/song_bank.py:290` `self.songs = songs` retains every song's `segments` key
  in memory for the lifetime of the `SongBank` instance.

## Impact
Avoidable multi-MB parse + RSS cost on the hot path of the `song build` command,
scaling with total bank size. Not correctness-affecting.

## Related
PERF-B-02 (#505), PERF-B-04 (#506) — same command family. TD-33 (#468, OPEN) is a
different concern (capacity-model accuracy).

## Suggested Fix
A metadata-only bank loader (reads `bank_info` plus per-song `metadata`/`midi_path`,
skips `segments`) used specifically by `run_song_build`; or make `segments` lazy
behind a getter.
