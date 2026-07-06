# MAP-2026-07-05B-2: MMC1/NROM nes.cfg define no DPCM_NN region -- any resolved DPCM sample fails to link

GitHub: https://github.com/matiaszanolli/midi2nes/issues/282

**Severity:** HIGH · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-05.md (MAP-2026-07-05B-2)

## Description
`DpcmPacker.generate_assembly()` (`dpcm_sampler/dpcm_packer.py:97-108`) emits `.segment "DPCM_{bank_id:02d}"` for every bank of packed raw sample bytes, unconditionally, regardless of which `--mapper` was resolved. `MMC1Mapper.generate_linker_config()` (`mappers/mmc1.py:61-106`) and `NROMMapper.generate_linker_config()` (`mappers/nrom.py:46-61`) define no `DPCM_*` region at all — only `mappers/mmc3.py` does (`DPCM_{i:02d}: load = PRG_BANK_{i:02d}` per swap bank).

`DpcmPacker.generate_assembly()` is invoked unconditionally by both `run_export` and `run_full_pipeline` whenever `dpcm_index.json` exists and the song references any sample id. When at least one sample actually packs (realistically common post-#254), its bytes land in a `DPCM_NN` segment that MMC1/NROM's `nes.cfg` simply doesn't define — `ld65` refuses to link.

The pre-flight capacity gate doesn't catch this either: `MMC1Mapper.validate_segment_sizes()` (`mappers/mmc1.py:168-228`) only recognizes `RODATA`/`RODATA_BANK_*` specially; a `DPCM_00` segment falls into the generic `else: flat_total += size` bucket and is silently folded into the flat 112KB total. As long as the aggregate stays under capacity, the pre-flight prints "✓ Music data ... fits the MMC1 PRG regions" immediately before `ld65` hard-fails.

## Evidence
Reproduced with the real toolchain. Took an MMC1 project and injected one fake packed-sample segment matching what `DpcmPacker` emits for a real sample:
```
.segment "DPCM_00"
    .align 64
    dpcm_sample_0:
    .byte $55,$55,$55,$55
```
```
$ ca65 main.asm -o main.o && ca65 music.asm -o music.o && ld65 -C nes.cfg main.o music.o -o game.nes
ld65: Error: Missing memory area assignment for segment 'DPCM_00'
$ echo $?
1
```
Confirmed the same result applies to NROM (its `nes.cfg` likewise has no `DPCM_*` region).

## Impact
Any `--no-patterns --mapper mmc1`/`nrom` (or `--mapper auto` routing to either, which happens for any song under ~30-112KB) build of a song whose drum hits **do** resolve to real `.dmc` samples (the common case — this repo ships 1,923 real `.dmc` files matching `dpcm_index.json`, and #254 fixed drum resolution to actually work) fails outright at the link stage. Not silent (`ld65`'s nonzero exit is correctly surfaced as a `CompilationError`), but it means MMC1/NROM direct export is currently unusable for any song with drums that actually pack — contradicting `docs/MAPPER_MMC1_REFERENCE.md`'s stated purpose for choosing MMC1 ("supports massive DPCM drum kits... an advanced memory mapper is required").

## Related
Sibling finding (filed separately, CRITICAL): the case where samples *don't* resolve is silent instead of a link failure. Together, MMC1/NROM DPCM support is currently all-broken via two different failure modes.

## Suggested Fix
Either (a) don't invoke `DpcmPacker` for a resolved mapper that has no `DPCM_*` capability yet (MMC1/NROM), and fail the pre-flight cleanly with "this mapper does not support DPCM samples in direct-export mode" when `sample_ids` is non-empty, or (b) extend `MMC1Mapper.generate_linker_config()` with `DPCM_NN` regions as part of the Mode-2 design fix (see the sibling CRITICAL finding). Also teach `validate_segment_sizes()` to flag an unrecognized `DPCM_*`/other unbacked segment name explicitly rather than silently folding it into the flat total.

## Completeness Checks
- [ ] **CC65**: `ld65`'s "missing memory area" error is confirmed surfaced as a clean `CompilationError`, not swallowed
- [ ] **SIBLING**: Check the same gap doesn't exist for any future non-MMC3 mapper added later
- [ ] **TESTS**: A regression test builds an MMC1/NROM project with a resolved DPCM sample and asserts either a clean pre-flight rejection or a successful link (not a raw `ld65` error reaching the user)
