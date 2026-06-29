# MAP-1: Capacity pre-flight measures total bytes against full 510 KB PRG, but the binding limit is the 8 KB fixed segment the tables land in

**Severity:** MEDIUM · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-29.md

## Description
The `#11` capacity gate (`check_mapper_capacity`, `main.py:94-104`) sums every `.byte`/`.word`/`.incbin` byte in `music.asm` and compares the total to `mapper.can_fit_data()` → `get_data_capacity()` = `512*1024 - 2048` = **522,240 bytes** for MMC3 (`mappers/base.py:147`).

But the MMC3 linker config loads the **direct-export** frame tables into `RODATA`, and `RODATA` loads into `PRG_FIX`, whose `MEMORY` region is only **`$1FFA` = 8,186 bytes** (`mappers/mmc3.py:56,81`) — shared with `CODE`. The direct export (`exporter/exporter_ca65.py`) emits dense, frame-indexed tables of `max_frame+1` bytes each (≈13–16 tables × frames). At 60 FPS even a ~12-second song (~720 frames × ~16 tables ≈ 11.5 KB) overflows the 8 KB `PRG_FIX` region — yet `check_mapper_capacity` reports it "fits MMC3 (510 KB)" and lets it through, so `ld65` aborts with a raw `PRG_FIX` region-overflow instead of the friendly budget message the gate was added to provide.

## Evidence
```
main.py:97-98     data_size = estimate_music_data_size(...)   # sums ALL .byte/.word
                  if not mapper.can_fit_data(data_size): raise ValueError(...)
base.py:147       return self.prg_rom_size - 2048             # 522240 for MMC3
mmc3.py:56        'PRG_FIX: start = $E000, size = $1FFA, ...'  # only 8186 bytes
mmc3.py:80-81     'CODE: load = PRG_FIX' / 'RODATA: load = PRG_FIX'
exporter_ca65.py  '.segment "RODATA"'                          # direct tables go here
```
Worked example: 60 s song → ~3,600 frames → ~57 KB of RODATA tables; gate says "11 % of 510 KB, fits"; `ld65` errors `PRG_FIX overflow by ...`.

## Impact
The capacity gate gives false reassurance and does not prevent the raw `ld65` error it was meant to replace, for the `--no-patterns` (direct) path on the default MMC3 mapper. Blast radius: any direct export longer than a few seconds. Not CRITICAL because `ld65` *does* catch the overflow and the compiler surfaces it (`cc65_wrapper.py`) and the pre-build backup is restored — so the ROM is never silently corrupted; the defect is a wrong/misleading budget, not silent truncation.

## Hardware ref
`docs/MAPPER_MMC3_REFERENCE.md` §6 (memory map: `$E000-$FFFF` fixed last 8 KB holds driver + note lookup tables).

## Suggested Fix
Have `check_mapper_capacity` size against the *segment the data actually lands in*: for the direct export, compare RODATA+CODE bytes to the `PRG_FIX` region size (8,186 − engine size); for the bytecode export, validate each `BANK_NN` ≤ 8 KB and bank count ≤ 60 and `CODE_8000` ≤ 8 KB. A single 510 KB ceiling is only correct if the data is actually distributed across the 60 swap banks (which only the bytecode path does).

## Related
Prior M-3 (the gate just added), MAP-2 (#sibling), #28 (M-8 flat MIN_ROM_SIZE).

## Completeness Checks
- [ ] **CONTRACT**: If a stage's JSON shape changes, the consumer stage was updated in lockstep
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (other mappers, bytecode vs direct export path)
- [ ] **TESTS**: A regression test pins this specific fix (oversized direct export → clear budget error pre-link)
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected