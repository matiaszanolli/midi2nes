# Issue #426: PIPE-2026-08-21-3: Jukebox song_table is indexed with 8-bit current_song*5 math — banks of 52+ songs build, validate, then silently play the wrong streams

- **Finding**: PIPE-2026-08-21-3
- **Labels**: critical, pipeline, bug
- **Filed**: 2026-08-21 (audit-publish, AUDIT_PIPELINE_2026-08-21.md)
- **URL**: https://github.com/matiaszanolli/midi2nes/issues/426

---

**Severity:** CRITICAL · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-08-21.md

## Description

The jukebox exporter (`exporter/exporter_ca65.py:1623-1643`, `export_song_bank_bytecode`) emits `song_table_ptr_lo/hi/bank` with stride 5 for N songs and no cap on N. The playback engine (`nes/audio_engine.asm`, `load_song_streams_indexed`) computes the base index `current_song * 5` in the 8-bit accumulator (`asl / asl / clc / adc current_song / tay`) and walks it with an 8-bit Y register.

- At `current_song = 51` the base index is 255; the `iny` walk for channels 1-4 wraps to 0-3, so song 51 loads channels 1-4 from **song 0's** pulse1/pulse2/triangle/noise entries (shifted one channel).
- For `current_song >= 52` the multiply itself wraps (52*5 = 260 → 4), so every stream pointer/bank is read from the wrong song's (and wrong channel's) table slot.

This is reachable: each song claims at least one fresh bank (`_build_song_bytecode` returns `current_bank + 1`), so up to 60 small songs pass the exporter's `MAX_SEQUENCE_BANK` check, `check_mapper_capacity` (60 tiny per-song instrument/macro tables fit the 6144-byte CODE_8000 budget), CC65, and `validate_rom` (reset vectors and APU init are unaffected). Nothing warns at any stage. `song_instrument_ptr_*` (stride 1, max index 59) is safe; only the stride-5 table breaks.

## Evidence

Code read of both sides of the contract (exporter emission loop at `exporter_ca65.py:1629-1643`; engine math at `audio_engine.asm` `load_song_streams_indexed` — the comment even documents the `(x4)+x` trick with no range caveat). Arithmetic: 51*5 = 255 (channel walk wraps), 52*5 = 260 & 0xFF = 4. Reachability: 60-bank pool / ≥1 bank per song → 52-60-song banks pass every gate (bank-count and CODE_8000 budgets verified against `mappers/mmc3.py:193-266`).

## Impact

A 52-60-song jukebox ROM ships as "validated" but songs at index ≥ 51 play other songs' streams on the wrong channels (and desync from their instrument table) — silent playback corruption with no build-time detection. Meets the CRITICAL floor "pipeline stage emits data a downstream stage parses as valid but means something else". Bounded blast radius (banks of 52+ songs), but severity is impact, not likelihood.

## Related

#30/F-13 (jukebox feature), commit `8ea7ac3`, #127/MAP-2 (the analogous bank-count cap this slipped past because the table, not the banks, is the limit).

## Suggested Fix

Cheapest: have `export_song_bank_bytecode` raise a clear ValueError when `len(songs) > 51` (table index 5N-1 must stay ≤ 255), mirroring the `MAX_SEQUENCE_BANK` error. Alternatively widen the engine's lookup to 16-bit pointer arithmetic. Either way, add the limit to `docs/ROADMAP.md`'s v1 scope notes.

## Completeness Checks
- [ ] **RANGE**: The song-table index (5N-1) is provably ≤ 255, or the engine lookup is widened to 16-bit — no 8-bit wraparound remains reachable
- [ ] **CONTRACT**: Exporter emission and engine indexing agree on the stride-5 table's maximum size; the limit is enforced at build time with a clear error
- [ ] **SIBLING**: Same pattern checked in related tables (`song_instrument_ptr_*` stride-1 lookup, any other indexed jukebox table)
- [ ] **TESTS**: A regression test pins this specific fix (e.g. a >51-song bank export raises; a boundary-size bank builds)
- [ ] **DOC**: `docs/ROADMAP.md` v1 jukebox scope notes the song-count limit
