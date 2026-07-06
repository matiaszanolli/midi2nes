# MAP-2026-07-05B-3: No guard against a --mapper mismatch between export and prepare/compile for direct-export bank-packing

GitHub: https://github.com/matiaszanolli/midi2nes/issues/283

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-05.md (MAP-2026-07-05B-3)

## Description
The step-by-step CLI is `parse → map → frames → export → prepare → compile`. `export`'s direct-export bin-packing (`CA65Exporter._pack_direct_tables_into_banks`) commits `RODATA_BANK_NN` bank assignments into `music.asm` based on whatever `--mapper` value `export` was given at that time. If a user runs `export` with one `--mapper` and `prepare`/`compile` with a different one, `resolve_mapper()`/`_requires_mmc3_bytecode_engine` (`main.py:167-181`) only raises a clear error for the *bytecode*-mode mismatch case. There is no equivalent check for "this `music.asm`'s segment layout was bin-packed for mapper X":

- `export --mapper mmc1` (bin-packed into `RODATA_BANK_00..NN`) then `prepare` with the default `mmc3`: `MMC3Mapper.validate_segment_sizes()` doesn't recognize `RODATA_BANK_NN` either, so `check_mapper_capacity` likely passes, and the failure surfaces only as a raw `ld65` "undefined segment" error at compile time.
- The reverse direction (export with default mmc3, then `prepare --mapper mmc1`) *is* caught cleanly by `MMC1Mapper.validate_segment_sizes` treating the whole flat `RODATA` as bank 0.

So the failure mode depends on the *direction* of the mismatch: one direction fails with a clear pre-flight message, the other with a confusing raw linker error. Not a silent-corruption risk (both directions fail before producing a ROM), but a real UX/defense-in-depth gap — this exact class of problem is what `_requires_mmc3_bytecode_engine` was already built to guard for the bytecode case.

## Evidence
Code read of `resolve_mapper`/`check_mapper_capacity`/`MMC1Mapper.validate_segment_sizes`/`MMC3Mapper.validate_segment_sizes`; confirmed no marker analogous to the `"MMC3 Macro Bytecode"` string exists for "this `music.asm` was bin-packed for MMC1 bank N".

## Impact
Confusing (not silent) failures for anyone using the step-by-step subcommands with a different `--mapper` at `export` vs. `prepare`/`compile` — a workflow the codebase explicitly supports (each subcommand parses `--mapper` independently) but doesn't validate end-to-end.

## Related
This is the mirror-image gap to `_requires_mmc3_bytecode_engine`, which already solves the analogous problem for the bytecode-export case.

## Suggested Fix
Add a marker (or a segment-name convention check) that `prepare`/`compile` can use to detect "this `music.asm`'s `RODATA_BANK_NN` segments were bin-packed for a specific mapper" and raise the same clear `ValueError` `_requires_mmc3_bytecode_engine` does today, rather than relying on whichever downstream check happens to catch the mismatch first.

## Completeness Checks
- [ ] **CC65**: Confirm the eventual `ld65` error (if the guard is bypassed) still surfaces as a clean `CompilationError`
- [ ] **SIBLING**: Mirror the existing `_requires_mmc3_bytecode_engine` guard's design for this bank-packing case
- [ ] **TESTS**: A regression test exports with `--mapper mmc1` then prepares with the default `mmc3` and asserts a clear pre-flight error instead of a raw `ld65` failure
