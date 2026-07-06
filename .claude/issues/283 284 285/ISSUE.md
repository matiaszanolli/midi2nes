# #283, #285 (same bug) + #284 (doc sibling) — direct-export bank-pack mapper-identity gap

## #285 (HIGH, pipeline) — PL-09  &  #283 (MEDIUM, mappers) — MAP-2026-07-05B-3
Two audits filed the same defect. `CA65Exporter.export_direct_frames` bin-packs
direct-export frame tables into `RODATA_BANK_NN` segments that only MMC1's linker
config defines (a mapper's `direct_export_bank_size()` is non-None only for MMC1).
`export` resolves its mapper from its own `--mapper` flag and records it nowhere;
`prepare`/`compile` parse an independent `--mapper` (default mmc3). A mismatch —
e.g. `export --mapper mmc1` then `prepare` with the mmc3 default — passes
`check_mapper_capacity` (MMC3's `validate_segment_sizes` has no `RODATA_BANK_NN`
branch, so those bytes count nowhere) and the failure is deferred to a raw
`ld65: Missing memory area assignment for segment 'RODATA_BANK_00'`, defeating the
pre-flight gate's stated purpose. Only the step-by-step subcommands diverge; the
default `run_full_pipeline` resolves one mapper and reuses it. This is the
direct-export mirror of the bytecode-path gap `_requires_mmc3_bytecode_engine`
already guards.

Live-reproduced: `export --mapper mmc1` emits `RODATA_BANK_00`; `prepare` (mmc3
default) prints "✓ fits" then `ld65` hard-fails at compile.

## #284 (LOW, docs) — MAP-2026-07-05B-4
`docs/MAPPER_MMC1_REFERENCE.md` §4 claims `midi2nes` "must initialize the MMC1 to
Mode 2" for `$C000` DPCM streaming, but the shipped `MMC1Mapper.generate_init_code`
configures Mode 3 (`$0C`): engine/vectors fixed at `$C000-$FFFF`, frame tables
banked at `$8000-$BFFF`. The Mode-2 DPCM design was never implemented. Doc-rot that
misleads anyone auditing MMC1 bank-switching against "the reference doc."

## Fix
- Exporter stamps `; Direct export bank-packed for <mapper.name>` when it bin-packs
  (banked mappers only).
- `main._direct_export_packed_mapper_name()` reads it back; `resolve_mapper` forces
  that mapper under `auto` and raises a clean `ValueError` on an explicit mismatch —
  covering both `prepare` and `compile` (both route through `resolve_mapper`).
- §4 rewritten to describe the shipped Mode-3 design (frame-table capacity banking,
  no MMC1 DPCM) and mark Mode-2 `$C000` DPCM streaming as a NOT-YET-IMPLEMENTED
  future target (#281/#282 reject DPCM on MMC1 today).
