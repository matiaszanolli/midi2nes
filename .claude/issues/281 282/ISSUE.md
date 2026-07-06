# #281 & #282 — Direct-export DPCM is MMC3-only but MMC1/NROM are reachable via --mapper

## #281 (CRITICAL, mappers) — MAP-2026-07-05B-1
`CA65Exporter.export_direct_frames`'s `play_dpcm` proc hardcodes an MMC3-only
DPCM bank-switch (`lda #$46 / sta $8000 / lda dpcm_bank_table,y / sta $8001`)
emitted unconditionally whenever `has_dpcm`, with no mapper check. On MMC1,
`$8000-$9FFF` is a 5-write serial shift register, so the two raw writes corrupt
MMC1's Control register and can un-fix the engine/vector bank mid-song. Reachable
via `--no-patterns --mapper mmc1` (or `auto` for a small song) when a drum maps to
`dpcm` but doesn't resolve to a packed sample.

## #282 (HIGH, mappers) — MAP-2026-07-05B-2
`DpcmPacker.generate_assembly()` emits `.segment "DPCM_NN"` unconditionally, but
only mmc3's `nes.cfg` defines `DPCM_*` regions; MMC1/NROM linker configs don't.
When a sample actually packs, `ld65` fails with "Missing memory area assignment
for segment 'DPCM_00'". The MMC1 pre-flight silently folds the unknown segment
into its flat total, so it prints "fits" right before the hard link failure.

## Root cause (shared)
Direct-export DPCM (trigger + packer) is MMC3-only leftover code; the MMC1 Mode-2
streaming design in docs/MAPPER_MMC1_REFERENCE.md §4 was never implemented. Both
failure modes fire only on the direct-export (`--no-patterns`) path with a
non-MMC3 mapper + a non-empty `dpcm` channel (the bytecode/pattern path is already
always forced to MMC3).

## Fix
`main.py:enforce_direct_export_dpcm_mapper(mapper, mapper_choice, frames)`, called
on both direct-export branches (`run_export`, `run_full_pipeline`) right after
mapper resolution: a song with a non-empty `dpcm` channel forces MMC3 under
`auto` and raises a clean `ValueError` for an explicit `mmc1`/`nrom` — mirroring
the bytecode path's forced-MMC3 and `resolve_mapper`'s explicit-reject. No
corrupting/unlinkable ROM ships.
