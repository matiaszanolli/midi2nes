# NH-09: export_direct_frames emits an iNES header for MMC1 while the pipeline builds MMC3

**Severity:** MEDIUM · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

GitHub issue: #36

## Description
Standalone direct export hardcodes `.byte $10 ; Mapper 1 (MMC1)` and `$08 ; 128K PRG ROM (MMC1)`. The prepare/full pipeline uses `MMC3Mapper`. A standalone ROM declares MMC1 regardless of the project's MMC3 linker config — header/linker mismatch.

## Evidence
Header bytes at exporter_ca65.py:72 and :74 vs prepare default MMC3.

## Impact
Standalone direct-export ROMs misdeclare the mapper; bites only when this path produces a final ROM.

## Hardware ref
`docs/NES_APU_REFERENCE.md`; `docs/MAPPER_MMC1_REFERENCE.md` / `docs/MAPPER_MMC3_REFERENCE.md`.

## Related
NH-01, NH-12.

## Suggested Fix
Parameterize the header mapper byte/PRG size from the selected mapper, or document the direct path as MMC1-only.
