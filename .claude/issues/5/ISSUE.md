# M-1: Default (patterns-on) music.asm references linker segments MMC3 nes.cfg does not define — link fails

**Severity:** CRITICAL · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
The default pipeline runs with pattern compression on, which routes `export_tables_with_patterns()` into the "MMC3 Macro Bytecode" branch (`patterns` truthy). That branch writes the DPCM lookup tables, pitch tables, `instrument_table`, and all macro data into `.segment "CODE_8000"`, and writes the per-channel sequence bytecode into `.segment "BANK_00"`, `.segment "BANK_01"`, … The MMC3 linker config defines segments `HEADER, ZEROPAGE, BSS, OAM, DPCM_00..59, CODE, RODATA, DPCM, VECTORS` — it has **no `CODE_8000` and no `BANK_NN`** (bank segments are named `DPCM_00..59` loading into `PRG_BANK_00..59`). `ld65` aborts on a segment with no matching config entry, so the default pipeline cannot link.

## Evidence
```
exporter/exporter_ca65.py:672   lines.append('.segment "CODE_8000"')
exporter/exporter_ca65.py:890   lines.append(f'.segment "BANK_{current_bank:02d}"')
mappers/mmc3.py:37-79           generate_linker_config(): SEGMENTS = HEADER/ZEROPAGE/BSS/OAM/DPCM_00..59/CODE/RODATA/DPCM/VECTORS — no CODE_8000, no BANK_NN
main.py:57,424                  use_patterns defaults True → patterns branch
```

## Impact
Every default `python main.py in.mid out.nes` invocation fails at the `ld65` step. Blast radius: the entire default pipeline. The `--no-patterns` path is the only path that can reach the linker cleanly.

## Related
M-2 (APU init); possibly issue #3 "Output seems silent".

## Suggested Fix
Add `CODE_8000` and `BANK_00..N` segments to `MMC3Mapper.generate_linker_config()`, or rename the exporter segments to the cfg existing `CODE` / `PRG_BANK_NN`. Add a CI test that runs `ca65`/`ld65` on a tiny MIDI through the default (patterns-on) path.
