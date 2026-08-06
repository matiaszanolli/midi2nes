# MAP-2026-08-05-1: --debug + --mapper mmc1 links debug_update into a switchable bank, crashing the first NMI

**Severity:** CRITICAL · **Domain:** mappers · **Source:** docs/audits/AUDIT_MAPPERS_2026-08-05.md
**GitHub:** https://github.com/matiaszanolli/midi2nes/issues/388

## Description
`NESProjectBuilder.prepare_project` appends the `--debug` overlay's generated assembly to
`music_content` with no `.segment` directive of its own, so it inherits whichever segment
was last active — `RODATA` in the realistic pipeline (DPCM packer stub tables end in
`.segment "RODATA"` and are appended whenever `dpcm_index.json` exists). On MMC1, `RODATA`
shares the switchable `PRG_BANK_00` window while `CODE`/`VECTORS` load into the always-mapped
fixed bank. MMC1's direct-export bank-packing leaves a non-zero bank switched in after the
last table read, and `nmi:` calls `jsr debug_update` right after `jsr update_music` with no
bank restore — so the CPU executes whatever bytes happen to sit at that offset in the
currently-switched bank (part of a note/timer table) as opcodes.

## Location
- `nes/project_builder.py:142-148`, `nes/project_builder.py:366-376`
- `mappers/mmc1.py:99,102`
- `exporter/exporter_ca65.py:149-174`
- `main.py:596-618`, `main.py:999-1022`

## Impact
Every ROM built with `--mapper mmc1 --debug` whose direct-export tables need more than one
16 KB bank crashes/hangs on the first NMI. Zero test coverage for this combination.

## Suggested Fix
1. Prepend an explicit `.segment "CODE"` before appending debug-overlay / DPCM-stub content
   in `nes/project_builder.py`.
2. Defense in depth: explicitly re-select bank 0 before `jsr debug_update` in the `nmi:`
   template when the mapper has a switchable direct-export bank.
3. Add a regression test building an MMC1 `--debug` project spanning ≥2 banks.
