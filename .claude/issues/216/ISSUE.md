# MAP-5: Stale comment in exporter_ca65.py claims MMC3 embeds its own .segment HEADER — no longer true since #22

- **Issue:** https://github.com/matiaszanolli/midi2nes/issues/216
- **Labels:** low, mappers, bug
- **Source report:** `docs/audits/AUDIT_MAPPERS_2026-07-03.md`
- **Finding ID:** MAP-5
- **Severity:** LOW

## Body filed

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-07-03.md

## Description
`export_direct_frames(..., standalone=True)`'s header emission still guards with
`if '.segment "HEADER"' not in header_asm: lines.append('.segment "HEADER"')` and a
comment explaining "MMC3 embeds its own `.segment \"HEADER\"`; NROM/MMC1 don't." That was
true before #22 (fixed in commit `007f5c4`); `MMC3Mapper.generate_header_asm()`
(`mappers/mmc3.py:38-48`) now returns bare `.byte` lines identically to NROM/MMC1
(`mappers/nrom.py:39-44`, `mappers/mmc1.py:40-45`). The guard branch is harmless (it
still emits `.segment "HEADER"` correctly for every mapper today, since none of them
embed it anymore), but the comment misdescribes current mapper behavior.

## Evidence
```
exporter/exporter_ca65.py:109  # MMC3 embeds its own `.segment "HEADER"`; NROM/MMC1 don't.
exporter/exporter_ca65.py:110  if '.segment "HEADER"' not in header_asm:
mappers/mmc3.py:43             .byte "NES", $1A                          # no .segment here anymore
```
Confirmed against current code (2026-07-03): the stale comment is still present verbatim
in `exporter/exporter_ca65.py:109-111`, and `MMC3Mapper.generate_header_asm()` returns
only bare `.byte` lines (no `.segment` directive).

## Impact
None on behavior; misleads a future reader into thinking the branch is still load-bearing
for MMC3 specifically.

## Suggested Fix
Update the comment to state all three mappers return bare header bytes today, or simplify
by removing the now-always-true guard and unconditionally appending `.segment "HEADER"`.

**Related:** #22.

## Completeness Checks
- [ ] **DOC**: If behavior contradicted a `docs/*.md`, the doc was corrected
- [ ] **SIBLING**: Same pattern checked in related files (other exporters, other channels, other mappers)
