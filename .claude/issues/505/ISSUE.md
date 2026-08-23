# PERF-B-02: run_song_build holds every song's full frames dict simultaneously before the single batched export call

**Severity:** MEDIUM · **Domain:** performance
**Source:** AUDIT_PERFORMANCE_2026-08-23.md (carried forward from AUDIT_PERFORMANCE_2026-08-07 / 2026-08-21, filed for the first time here)
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/505

## Description
The `run_song_build` per-song loop (`main.py:1032-1059`) appends every song's entire
frames dict (`{channel: {frame_num: {note, volume, ...}}}`) to `songs` before
`export_song_bank_bytecode` is called once on the complete list (`main.py:1083`).
Nothing requires all N frames dicts to coexist — `_build_song_bytecode`
(`exporter/exporter_ca65.py`) consumes only its own song's frames plus the scalar
`next_bank` carried forward; it is otherwise self-contained per song. The 2026-08-07
audit measured ~12.5-13.2 MB per 3-minute/5-channel song's frames dict via
`tracemalloc`, i.e. ~250 MB held simultaneously for a 20-song jukebox. This
reintroduces at song granularity the "input outlives its successor" pattern that
#371/PERF-A-01 deliberately eliminated at pipeline-stage granularity.

## Evidence
- `main.py:1059` `songs.append({'frames': frames})` inside the per-song loop.
- `main.py:1083` `exporter.export_song_bank_bytecode(songs, str(music_asm))` — single
  batched call after the loop ends; no `del`/streaming between song iterations.
- #466's preamble-dedup refactor touched only the shared preamble emission, not this
  loop or `_build_song_bytecode`'s per-song self-containment.

## Impact
Peak RSS scales linearly with song count × song length. Typical banks stay well under
100 MB — MEDIUM, not HIGH (no demonstrated OOM on common input).

## Related
#371/PERF-A-01 (CLOSED, same category/different granularity). PERF-B-01 (#504).
PERF-B-04 (#506) compounds this.

## Suggested Fix
Interleave: call `_build_song_bytecode` immediately after each song's frames are
built, accumulate only the returned asm lines/`channel_start_banks`/`next_bank`,
`del frames` per iteration.
