# NH-09: export_direct_frames emits an iNES header for MMC1 while the pipeline builds MMC3

**Severity:** MEDIUM · **Domain:** nes-hardware/mappers · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

Standalone direct export hardcodes `.byte $08 ; 128K PRG (MMC1)` and `.byte $10 ; Mapper 1`
while prepare/full pipeline uses MMC3Mapper. A standalone ROM misdeclares the mapper.

## Suggested Fix
Parameterize the header mapper byte/PRG size from the selected mapper.
