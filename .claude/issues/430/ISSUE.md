# NH-HW-2026-08-21-2: Direct-export playback never plays the final frame table entry — off-by-one in the range/loop guards

**GitHub Issue:** https://github.com/matiaszanolli/midi2nes/issues/430
**Severity:** MEDIUM
**Domain:** nes-hardware
**Source report:** docs/audits/AUDIT_NES_HARDWARE_2026-08-21.md
**Filed:** 2026-08-21

## Location
- `exporter/exporter_ca65.py:854-863` (`play_music_frame` range guard: `bcs @done` treats
  `frame_counter == max_frame` as out of range)
- `exporter/exporter_ca65.py:829-841` (standalone `nmi` loop reset)
- `exporter/exporter_ca65.py:971-983` (non-standalone `update_music`, same reset)

## Description
Frame tables are emitted with `max_frame + 1` entries (indices `0..max_frame`). `play_music_frame`
refuses to play when `frame_counter >= max_frame`, and both loop resets fire at
`frame_counter == max_frame` — so index `max_frame` (the final frame, always populated) is dead
data. Degenerate case: a 1-frame song (`max_frame = 0`) never plays anything.

## Impact
Every `--no-patterns` / direct-export ROM drops the song's final frame — usually near-inaudible,
but a 1-frame terminal event (drum trigger, staccato note) is dropped entirely, and a 1-frame song
produces total silence. Bytecode path unaffected (stream-driven, `$FF`-terminated).

## Suggested Fix
Play while `frame_counter <= max_frame` (or compare against `max_frame + 1`), and reset the loop
counter accordingly.

## Related
None open.

## Dedup check
Searched fresh `gh issue list --state open` snapshot (6 open issues at filing time) and audit
history — no match found.
