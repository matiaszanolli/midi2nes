# NH-12: Doc-rot — export_direct_frames header comments / CLAUDE.md conflict with MMC3 default

**Severity:** LOW · **Domain:** nes-hardware · **Source:** AUDIT_NES_HARDWARE_2026-06-28.md

## Description
`CLAUDE.md`'s "ROM Structure" section still says "Always use MMC1 mapper configuration / PRG-ROM 128KB", while the live pipeline (`prepare`, `run_full_pipeline`) uses MMC3 and `_audit-common.md` documents MMC3 as the default. The exporter header comments perpetuate the stale MMC1 claim. Pure documentation drift (the functional mismatch is NH-09).

## Evidence
`CLAUDE.md:194` "Always use MMC1 mapper configuration", :196 "PRG-ROM: 128KB", :266 "Creates working MMC1 ROMs"; `_audit-common.md` "prepare → default mapper MMC3". Exporter comments at exporter_ca65.py:72-74. Confirmed in current tree.

## Impact
Misleads contributors about the mapper in use.

## Hardware ref
`docs/MAPPER_MMC3_REFERENCE.md` (the actual default mapper).

## Related
NH-09 (the functional MMC1/MMC3 mismatch).

## Suggested Fix
Update `CLAUDE.md` ROM Structure section and the exporter header comments to MMC3.

## Completeness Checks
- [ ] **DOC**: `CLAUDE.md` ROM Structure + exporter header comments corrected to MMC3
- [ ] **SIBLING**: Any other docs/comments asserting MMC1-as-default reconciled
