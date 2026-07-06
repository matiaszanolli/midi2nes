# PL-09: check_mapper_capacity silently ignores MMC1 bank-packed segments when a different mapper is chosen at prepare/compile time

GitHub: https://github.com/matiaszanolli/midi2nes/issues/285

**Severity:** HIGH · **Domain:** pipeline · **Source:** AUDIT_PIPELINE_2026-07-05.md (PL-09)

## Description
`CA65Exporter.export_direct_frames` now asks the mapper `bank_size = mapper.direct_export_bank_size()` and, when not `None`, bin-packs every direct-export frame table into per-bank segments named `RODATA_BANK_00`, `RODATA_BANK_01`, … prefixed with mapper-specific bank-switch assembly (currently only `MMC1Mapper` returns non-`None`). `MMC1Mapper.generate_linker_config()` (and its `validate_segment_sizes` override) know about `RODATA_BANK_NN`; no other mapper does.

`run_export`/`run_full_pipeline` resolve this mapper choice from the `export`-time `--mapper` flag alone and never record it anywhere the project directory or `music.asm` can be checked against later. `prepare` and `compile` each parse their own independent `--mapper` flag (default `mmc3`) and hand it to `check_mapper_capacity`, whose entire purpose is to "abort before linking... instead of a raw `ld65` region overflow." For MMC3/NROM, `validate_segment_sizes` has no branch for `RODATA_BANK_NN`, so those bytes are counted nowhere, the check reports success, and the failure is deferred to `ld65` itself with a much less actionable message.

**Both paths?** Step-by-step only. The default `run_full_pipeline` resolves one mapper object once and reuses it for `check_mapper_capacity`, `NESProjectBuilder`, and `compile_rom` — no divergence possible there. This is exclusively a gap between the independently-parsed `export --mapper` and `prepare --mapper`/`compile --mapper`.

## Evidence
Live-reproduced end-to-end with the real CC65 toolchain (`ca65`/`ld65` V2.18):
```
$ python main.py export small_frames.json small_music.asm --mapper mmc1
  Data size: 1,600 bytes (1.6 KB)
$ grep '\.segment' small_music.asm | sort -u
.segment "RODATA_BANK_00"
.segment "CODE"
.segment "RODATA"
.segment "BSS"

$ python main.py prepare small_music.asm nes_project     # default --mapper mmc3
  ✓ Music data 1,604 bytes fits the MMC3 PRG regions      <- FALSE: RODATA_BANK_00 unrecognized
  Using MMC3 with 512KB PRG-ROM
  Prepared NES project -> nes_project

$ python main.py compile nes_project out.nes --verbose
  Compiling music.asm...
  Assembled: music.asm -> music.o
  Linking ROM...
[ERROR] Failed to link ROM: ld65: Error: Missing memory area assignment for segment 'RODATA_BANK_00'
[ERROR] ROM compilation failed
```
No `out.nes` is produced — the failure is loud and no ROM ships (does not meet the CRITICAL "silently ships a broken ROM" floor), but the pre-flight gate's own stated purpose (avoid exactly this raw `ld65` message) is defeated for this input combination.

## Impact
Reachable any time a user picks `--mapper mmc1` (or `--mapper auto`, which routes 30-112KB direct-export songs to MMC1) on `export` and does not pass the identical `--mapper` to the subsequent `prepare`/`compile` step — including simply omitting `--mapper` on `prepare`/`compile` and getting their `mmc3` default. The documented step-by-step example in CLAUDE.md doesn't pass `--mapper` to `export` at all (defaults to `mmc3`, which never bank-packs), so the documented workflow is unaffected — this is an edge combination within the subcommands, not the default path.

## Related
The CRITICAL this same commit (#254/#255) fixed — MMC1 direct export silently overflowing its window with no link error at all; this finding is the "loud failure" cost of that fix landing without a matching cross-stage mapper-identity guard. #269 (PL-08, the milder already-filed sibling: `prepare --mapper auto` has no `compile` equivalent) — both stem from the same root fact that `export`/`prepare`/`compile` mapper choices have no shared source of truth outside the default pipeline.

## Suggested Fix
Either (a) record which mapper was used to bank-pack `music.asm` — e.g. a marker comment analogous to `_requires_mmc3_bytecode_engine`'s "MMC3 Macro Bytecode" string, such as `; Direct export packed for <mapper.name> bank-switching` — and teach `resolve_mapper` to read it back and force/validate that mapper the same way it already forces MMC3 for the bytecode marker; or (b) make `validate_segment_sizes` on every mapper explicitly reject any segment name it doesn't recognize as its own, turning today's false "✓ fits" into a clear "this music.asm was built for a different mapper" pre-flight error.

## Completeness Checks
- [ ] **CONTRACT**: The export→prepare mapper-choice artifact contract gets an explicit marker/check instead of silent pass-through
- [ ] **CC65**: The eventual `ld65` failure (if the guard is bypassed) stays surfaced as a clean `CompilationError`
- [ ] **SIBLING**: Mirrors the existing `_requires_mmc3_bytecode_engine` guard design for the bytecode case
- [ ] **TESTS**: A regression test exports with `--mapper mmc1` then prepares with a mismatched mapper and asserts a clear pre-flight error instead of a raw `ld65` failure
