# MAP-2026-07-19-2: Direct-export DPCM has no music.asm marker for the split prepare/compile flow

Issue: #362
Labels: medium, mappers, bug

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-19.md

## Description
The direct-export DPCM guard `enforce_direct_export_dpcm_mapper` (which forces MMC3 for `auto` and rejects an explicit `nrom`/`mmc1` because `play_dpcm` writes MMC3's `$8000`/`$8001` ports and `DpcmPacker` emits MMC3-only `DPCM_NN` segments) runs **only** where the in-memory `frames` dict is available — i.e. the `export` subcommand and `run_full_pipeline`. A direct-export DPCM `music.asm` (necessarily built as MMC3, since `export` forces it) carries **no marker** identifying it as DPCM/MMC3-only, unlike the bytecode path ("MMC3 Macro Bytecode") and the MMC1 bank-packed path ("Direct export bank-packed for MMC1"). So `main.py prepare --mapper nrom music.asm proj/` (then `compile`) runs `resolve_mapper('nrom', music.asm)` which finds neither marker and honors NROM; `check_mapper_capacity` with NROM sums the `DPCM_NN` bytes into the flat total (NROM/`base.validate_segment_sizes` has no `DPCM_NN` branch) and passes if small; the mismatch surfaces only as a raw `ld65` "Missing memory area assignment for DPCM_00" at link time.

## Location
`main.py:321-354` (`enforce_direct_export_dpcm_mapper`, requires `frames`, called only at `main.py:611` / `main.py:1010`); `main.py:276-318` (`resolve_mapper`, the only guard the marker-less `prepare`/`compile` path has) checks `_requires_mmc3_bytecode_engine` (marker `"MMC3 Macro Bytecode"`) and `_direct_export_packed_mapper_name` (marker `"; Direct export bank-packed for …"`) but **not** direct-export DPCM; `exporter/exporter_ca65.py:206-207` stamps the bank-pack marker only when `direct_export_bank_size()` is not `None` (MMC3 returns `None`, so a direct-export DPCM `music.asm` gets **no** marker).

## Evidence
`export_direct_frames` (`exporter/exporter_ca65.py:206`) — `if mapper is not None and mapper.direct_export_bank_size() is not None:` — MMC3's `direct_export_bank_size()` is the inherited `None`, so the marker line is never emitted for the exact mapper direct-export DPCM is forced onto. `resolve_mapper` (`main.py:289-303`) has no DPCM branch; `NROMMapper`/`BaseMapper.validate_segment_sizes` treat `DPCM_NN` as generic flat data.

## Impact
The manual step-by-step flow `export --no-patterns` (a DPCM song → MMC3) followed by `prepare`/`compile --mapper nrom|mmc1`. Fails cleanly at `ld65` (no broken ROM), but with a cryptic linker error instead of the clean "DPCM is MMC3-only" `ValueError` the single-command pipeline gives. This is the one remaining hole in the split-flow hardening that #283/#285 (bank-pack marker) and #297/#269 (nes.cfg marker) otherwise closed.

## Related
#281/#282 (`enforce_direct_export_dpcm_mapper`); #283/#285 (`_direct_export_packed_mapper_name` marker); #297/#269 (`nes.cfg` mapper marker) — this finding is the direct-DPCM analogue those markers don't cover.

## Hardware ref
`docs/MAPPER_MMC3_REFERENCE.md` §5 (DPCM sample banks swapped via R6 at `$8000`/`$8001` — MMC3-only); `docs/MAPPER_MMC1_REFERENCE.md` §4 (MMC1 DPCM streaming unimplemented).

## Suggested Fix
Stamp a `"; Direct export DPCM (MMC3-only)"` marker in `export_direct_frames`/`DpcmPacker` output when a DPCM channel is present, and have `resolve_mapper` force MMC3 / reject non-MMC3 on it — mirroring the bank-pack marker. Or teach `resolve_mapper`/`validate_segment_sizes` to treat any `DPCM_NN` segment in a non-MMC3 target as an unsupported-mapper error up front.

## Completeness Checks
- [ ] **CONTRACT**: The `prepare`/`compile` split-flow marker matches what `export`/`run_full_pipeline` enforce in-memory
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface (the raw `ld65` DPCM_00 error remains a backstop)
- [ ] **SIBLING**: Same marker pattern checked against bytecode + bank-pack markers
- [ ] **TESTS**: A regression test pins `prepare --mapper nrom` rejecting a direct-export DPCM music.asm up front
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
