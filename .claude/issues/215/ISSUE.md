# MAP-4: MMC3 nes.cfg declares an unused OAM memory region and segment — harmless ld65 warning on every build

- **Issue:** https://github.com/matiaszanolli/midi2nes/issues/215
- **Labels:** low, mappers, bug
- **Source report:** `docs/audits/AUDIT_MAPPERS_2026-07-03.md`
- **Finding ID:** MAP-4
- **Severity:** LOW

## Body filed

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-03.md

## Description
The MMC3 linker config reserves a `$0200-$02FF` `OAM` (sprite Object Attribute Memory)
region and declares a matching `.segment "OAM"`, but neither `nes/project_builder.py`'s
generated `main.asm` nor `exporter/exporter_ca65.py`'s `music.asm` nor
`nes/debug_overlay.py` ever emit anything into `.segment "OAM"` — this is a music-only
ROM generator with no sprite/graphics engine. `ld65` warns on every default build.

## Evidence
Reproduced on the same real build as MAP-1 (same report):
```
ld65: Warning: .../nes.cfg(203): Segment 'OAM' does not exist
$ grep -rn '"OAM"' nes/project_builder.py exporter/exporter_ca65.py nes/debug_overlay.py
(no matches)
```
Confirmed against current code (2026-07-03): `mappers/mmc3.py:54` declares the `OAM`
memory region and `mappers/mmc3.py:78` declares the `OAM` segment; no producer file
references `.segment "OAM"`.

## Impact
Cosmetic — an extra warning line in every MMC3 build's `ld65` output (which also now
includes the real MAP-1 overflow warnings, making it harder to spot the actionable ones
among noise). No effect on the produced ROM's correctness.

## Suggested Fix
Either remove the unused `OAM` `MEMORY`/`SEGMENTS` entries from `mappers/mmc3.py:54,78`,
or wire up an actual OAM shadow-buffer segment usage if sprite support is planned (see
`docs/ROADMAP.md`).

## Completeness Checks
- [ ] **CC65**: If the compiler/cc65 path changes, nonzero exit + stderr still surface
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
- [ ] **TESTS**: A regression test pins this specific fix
