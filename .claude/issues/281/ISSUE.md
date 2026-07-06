# MAP-2026-07-05B-1: Direct-export DPCM trigger hardcodes MMC3 bank-switch registers regardless of resolved --mapper, corrupting MMC1's serial control port

Filed from: `docs/audits/AUDIT_MAPPERS_2026-07-05.md`
GitHub: https://github.com/matiaszanolli/midi2nes/issues/281
Severity: CRITICAL · Domain: mappers

**Severity:** CRITICAL · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-05.md (MAP-2026-07-05B-1)

## Description
`CA65Exporter.export_direct_frames`'s `play_dpcm` proc (`exporter/exporter_ca65.py:769-815`) hardcodes an MMC3-only DPCM-bank-switch sequence:

```
'    ; MMC3: swap DPCM sample bank into $C000 (R6)',
'    lda #$46',
'    sta $8000',
'    lda dpcm_bank_table,y',
'    sta $8001',
```

This is emitted **unconditionally** whenever `has_dpcm` is true, with no check of `mapper.mapper_number` and no use of `mapper.generate_bank_switch_code()` — unlike every other mapper-aware part of this proc family added in #254/#255 (bin-packing, `_emit_table_read_lines`, `_emit_safe_beq`), and unlike the bytecode engine's equivalent trigger (`seq_cmd_dpcm_play`), which *is* correctly gated `if is_bytecode` (MMC3-only).

For MMC1, `$8000-$9FFF` is not an atomic "select register, write value" port — it's a 5-write serial shift register (`docs/MAPPER_MMC1_REFERENCE.md` §1-§3). `play_dpcm`'s two raw writes partially advance MMC1's shift-register state on every drum hit, completing a different, effectively random 5-bit Control-register value roughly every 2.5 triggers. If the assembled value's PRG-mode bits land on Mode 0/1/2 instead of the Mode 3 this project's `generate_init_code` configures (`mappers/mmc1.py:108-133`), the fixed bank holding the engine/vectors at `$C000-$FFFF` **stops being fixed**, and the CPU can resume execution from an arbitrary PRG bank mid-song.

This is also exactly the gap `docs/MAPPER_MMC1_REFERENCE.md` §4 describes: DPCM-via-MMC1 requires Mode 2 (engine fixed at `$8000-$BFFF`, DPCM bank-switched at `$C000-$FFFF`, matching DMC hardware's fixed fetch range) — that design was never implemented; `play_dpcm` is unmodified MMC3-only leftover code.

## Evidence
Reproduced end-to-end with the real CC65 toolchain (`ca65`/`ld65` V2.18):
1. `CA65Exporter().export_direct_frames(frames_with_dpcm, 'music.asm', standalone=False, mapper=MMC1Mapper())` emits the MMC3 snippet verbatim.
2. A full MMC1 project (`NESProjectBuilder(mapper=MMC1Mapper())`) with the DPCM packer's zero-samples dummy-stub branch (the state the codebase's own `dpcm_pack_warning` already anticipates and warns about, but doesn't block on) builds clean:
   ```
   $ ca65 main.asm -o main.o && ca65 music.asm -o music.o && ld65 -C nes.cfg main.o music.o -o game.nes
   $ echo $?
   0
   $ ls -la game.nes
   -rw-rw-r-- 1 matias matias 131088 ... game.nes
   ```
   Correctly-sized 128KB+16-byte ROM, no error anywhere in the build/size-check chain.

## Impact
Every `--no-patterns --mapper mmc1` (or `--mapper auto` for a small song) build of a MIDI file with a percussion/drum note mapped to `dpcm` that does **not** end up with a real packed sample (missing/stale `dpcm_index.json`, an unresolved id, etc.) ships a ROM that builds clean, passes size checks, boots, and can brick/crash mid-song on the first drum hit. #254 made real drum resolution common (previously most named drums fell back to noise); #255 made `--mapper mmc1`/`auto` reachable from the CLI — this combination is now realistically reachable, not theoretical.

## Related
Sibling finding: MMC1/NROM `nes.cfg` also define no `DPCM_NN` region at all, so the case where a sample *does* pack fails to link instead (filed separately). Together, MMC1/NROM DPCM support is currently broken via two independent failure modes.

## Suggested Fix
Gate the MMC3-specific `play_dpcm` bank-switch on the mapper, mirroring `nes/project_builder.py`'s `if is_bytecode` guard. Shortest fix: only emit the `$8000`/`$8001` R6-select lines when `mapper is not None and mapper.mapper_number == 4`; for MMC1/NROM either (a) skip DPCM bank-switching and require packed samples to fit the mapper's one fixed-visible region, or (b) implement the Mode-2/`$C000`-streaming design `docs/MAPPER_MMC1_REFERENCE.md` §4 already documents. Add an integration test building an MMC1 ROM with a `dpcm` channel present, asserting the emitted code never writes registers that don't exist for the target mapper.

## Completeness Checks
- [ ] **CC65**: A real ca65/ld65 build with a non-MMC3 mapper + DPCM channel is asserted to either succeed correctly or fail cleanly at the pre-flight stage, not silently link a corrupting ROM
- [ ] **SIBLING**: Verify the fix mirrors the existing MMC3-only gate already used at `seq_cmd_dpcm_play` (bytecode engine)
- [ ] **TESTS**: A regression test builds an MMC1 project with an unresolved `dpcm` channel and asserts the emitted `play_dpcm` code never touches `$8000`/`$8001` unless the mapper is MMC3
